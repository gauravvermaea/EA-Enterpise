"""Builds the SQL that loads the ArchiMate 4 starter metamodel (and the sample model).

Two models are created on first start:

* "ArchiMate 4" - a template model: the metamodel only, read-only. New models start from it.
* "Sample insurance model" - a project model with its own copy of the metamodel (every row's
  origin_guid points at the template row it came from) and a handful of sample entities and
  relationships, so get_entity has something to show. Laptop installs only (EAX_SEED_SAMPLE).

Every guid is derived from a fixed name (uuid5), so the seed gives the same GUIDs on every
install, and running it twice changes nothing.
"""

from __future__ import annotations

import re
import uuid
from datetime import date

from . import archimate4 as A

NAMESPACE = uuid.UUID("6f4c2a52-2b0e-4b5e-9d63-6b0c0e7a1000")
TEMPLATE_KEY = "archimate4-template"
SAMPLE_KEY = "sample-insurance"


def gid(*parts: str) -> str:
    """A stable GUID for a seed row."""
    return str(uuid.uuid5(NAMESPACE, ":".join(parts)))


TEMPLATE_ID = gid("model", TEMPLATE_KEY)
SAMPLE_ID = gid("model", SAMPLE_KEY)

# Workbench data type names -> core.data_types codes
DATA_TYPES = {
    "Text": "text", "LongText": "long_text", "Integer": "integer", "Decimal": "decimal",
    "Currency": "currency", "Percent": "percent", "Date": "date", "Boolean": "boolean",
    "List": "list", "URL": "url", "Email": "email", "EntityRef": "entity_ref",
}
STORAGE = {
    "text": "value_text", "long_text": "value_text", "list": "value_text", "url": "value_text",
    "email": "value_text", "integer": "value_number", "decimal": "value_number",
    "currency": "value_number", "percent": "value_number", "date": "value_date",
    "boolean": "value_bool", "entity_ref": "value_ref",
}
RULE_TYPES = {
    "Mandatory": "mandatory", "List": "list", "MinValue": "min_value", "MaxValue": "max_value",
    "Range": "range", "MinLength": "min_length", "MaxLength": "max_length", "Regex": "regex",
    "DateRange": "date_range", "DateOrder": "date_order", "Unique": "unique",
    "EntityRef": "entity_ref", "RequiredIf": "required_if",
}
# Workbench lists that describe the Workbench itself; the database has its own tables for these
INTERNAL_LISTS = {"DataType", "RuleType", "Severity", "RelCategory", "Domain", "YesNo", "Status"}


def snake(code: str) -> str:
    """ApplicationComponent -> application_component, GoLiveDate -> go_live_date."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", code)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    return s.strip("_").lower()


def lit(v) -> str:
    """SQL literal for a seed value (seed data only: no user input reaches this)."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, date):
        return f"DATE '{v.isoformat()}'"
    return "'" + str(v).replace("'", "''") + "'"


# Foreign-key columns and the table they point at. The seed names every row by its guid; the
# bigint keys are looked up by guid when the rows are inserted.
FOREIGN_KEYS = {
    "model_id": "model", "parent_model_id": "model", "source_model_id": "model", "layer_id": "layer",
    "entity_type_id": "entity_type", "source_type_id": "entity_type", "target_type_id": "entity_type",
    "relationship_type_id": "relationship_type", "pick_list_id": "pick_list",
    "attribute_type_id": "attribute_type", "entity_id": "entity", "source_entity_id": "entity",
    "target_entity_id": "entity", "relationship_id": "relationship",
}
RENAMED = {"id": "guid", "origin_id": "origin_guid"}

# The seed names things in the singular (also in its guid keys, which must never change); the
# database tables are plural.
TABLES = {
    "model": "models", "layer": "layers", "entity_type": "entity_types",
    "relationship_type": "relationship_types", "pick_list": "pick_lists", "pick_list_value": "pick_list_values",
    "attribute_type": "attribute_types", "item_attribute": "item_attributes",
    "validation_rule": "validation_rules", "allowed_relationship": "allowed_relationships",
    "entity": "entities", "attribute_value": "attribute_values", "relationship": "relationships",
}


def insert(table: str, cols: list[str], rows: list[list]) -> str:
    """INSERT for seed rows given by guid: id -> guid, origin_id -> origin_guid, and every foreign
    key value (a guid) is turned into the bigint key by one join per foreign-key column (fast
    for thousands of rows, unlike a lookup per value)."""
    if not rows:
        return ""
    select, joins = [], []
    for i, col in enumerate(cols):
        all_null = all(r[i] is None for r in rows)
        if all_null:
            select.append("NULL")
        elif col in FOREIGN_KEYS:
            joins.append(f"LEFT JOIN core.{TABLES[FOREIGN_KEYS[col]]} f{i} ON f{i}.guid = v.c{i}::uuid")
            select.append(f"f{i}.id")
        elif col in RENAMED:
            select.append(f"v.c{i}::uuid")
        else:
            select.append(f"v.c{i}")
    values = ",\n".join("    (" + ", ".join(lit(v) for v in r) + ")" for r in rows)
    names = ", ".join(RENAMED.get(c, c) for c in cols)
    aliases = ", ".join(f"c{i}" for i in range(len(cols)))
    return (f"INSERT INTO core.{TABLES[table]} ({names})\nSELECT {', '.join(select)}\nFROM (VALUES\n{values}\n"
            f") AS v ({aliases})\n" + "\n".join(joins) + ";\n")


def expand_allowed() -> list[tuple[str, str, str, str]]:
    """Turns the Workbench rule tokens (*, SAME, G:group) into concrete (source, rel, target) rows."""
    all_types = [t[0] for t in A.ENTITY_TYPES]

    def resolve(token: str) -> list[str]:
        if token == "*":
            return all_types
        if token.startswith("G:"):
            return A.G[token[2:]]
        return [token]

    seen: dict[tuple[str, str, str], str] = {}
    for src, rel, tgt, note in A.R:
        for s in resolve(src):
            targets = [s] if tgt == "SAME" else resolve(tgt)
            for t in targets:
                seen.setdefault((s, rel, t), note)
    return [(s, r, t, n) for (s, r, t), n in seen.items()]


def metamodel_sql(model_key: str, origin_key: str | None) -> str:
    """The metamodel rows for one model. origin_key: the model the rows were copied from."""
    m = gid("model", model_key)

    def ids(*parts):  # (id, origin_id)
        return gid(model_key, *parts), (gid(origin_key, *parts) if origin_key else None)

    out = []
    # layers (the ArchiMate domains)
    rows = []
    for i, (domain, colour) in enumerate(A.DOMAIN_COLOURS.items(), 1):
        i_d, o = ids("layer", domain)
        rows.append([i_d, o, m, snake(domain), domain, colour, i * 10])
    out.append(insert("layer", ["id", "origin_id", "model_id", "code", "name", "colour", "sort_order"], rows))

    # entity types
    rows = []
    for i, (code, name, domain, aspect, prefix) in enumerate(A.ENTITY_TYPES, 1):
        i_d, o = ids("entity_type", code)
        rows.append([i_d, o, m, gid(model_key, "layer", domain), code, name, aspect, prefix, snake(code), i * 10])
    out.append(insert("entity_type", ["id", "origin_id", "model_id", "layer_id", "code", "name", "aspect",
                                      "id_prefix", "table_name", "sort_order"], rows))

    # relationship types
    rows = []
    for i, (code, verb, category, directed, desc) in enumerate(A.REL_TYPES, 1):
        i_d, o = ids("relationship_type", code)
        rows.append([i_d, o, m, code, code, verb, category, directed == "Y", desc, i * 10])
    out.append(insert("relationship_type", ["id", "origin_id", "model_id", "code", "name", "verb", "category",
                                            "is_directed", "description", "sort_order"], rows))

    # pick lists and their values
    lists = {k: v for k, v in A.LISTS.items() if k not in INTERNAL_LISTS}
    rows, vrows = [], []
    for code, values in lists.items():
        i_d, o = ids("pick_list", code)
        rows.append([i_d, o, m, code, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", code)])
        for j, value in enumerate(values, 1):
            vi, vo = ids("pick_list_value", code, value)
            vrows.append([vi, vo, m, i_d, value, j * 10])
    out.append(insert("pick_list", ["id", "origin_id", "model_id", "code", "name"], rows))
    out.append(insert("pick_list_value", ["id", "origin_id", "model_id", "pick_list_id", "value", "sort_order"], vrows))

    # attribute types: the Workbench business attributes, plus Repository Area (TOGAF)
    attrs = list(A.ATTRS) + [("RepositoryArea", "Repository Area", "List", "RepositoryArea", "",
                              "Part of the TOGAF architecture repository this element belongs to")]
    rows = []
    for code, name, dtype, pick, unit, desc in attrs:
        i_d, o = ids("attribute_type", code)
        dt = DATA_TYPES[dtype]
        pl = gid(model_key, "pick_list", pick) if dt == "list" else None
        rows.append([i_d, o, m, code, name, desc, dt, pl, unit, snake(code)])
    out.append(insert("attribute_type", ["id", "origin_id", "model_id", "code", "name", "description",
                                         "data_type_code", "pick_list_id", "unit", "column_name"], rows))

    # which attributes apply to which entity type
    rows = []
    for type_code, mapped in A.MAP.items():
        mapped = list(mapped) + [("RepositoryArea", "N", "Repository")]
        first: dict[str, tuple] = {}
        for attr, mandatory, section in mapped:  # the Workbench map repeats a few (Product: Lifecycle)
            first.setdefault(attr, (attr, mandatory, section))
        for k, (attr, mandatory, section) in enumerate(first.values(), 1):
            i_d, o = ids("item_attribute", type_code, attr)
            rows.append([i_d, o, m, gid(model_key, "attribute_type", attr), gid(model_key, "entity_type", type_code),
                         mandatory == "Y", section, k * 10])
    out.append(insert("item_attribute", ["id", "origin_id", "model_id", "attribute_type_id", "entity_type_id",
                                         "is_required", "section", "sort_order"], rows))

    # validation rules (the Status rule belongs to the Workbench; status is a workflow column here)
    rows = []
    for k, (attr, type_code, rtype, p1, p2, severity, message) in enumerate(A.RULES, 1):
        if attr == "Status":
            continue
        i_d, o = ids("validation_rule", str(k))
        is_field = attr in ("Name", "Description")
        rows.append([i_d, o, m,
                     None if is_field else gid(model_key, "attribute_type", attr),
                     attr.lower() if is_field else None,
                     gid(model_key, "entity_type", type_code) if type_code else None,
                     RULE_TYPES[rtype], p1, p2, severity.lower(), message, k * 10])
    out.append(insert("validation_rule", ["id", "origin_id", "model_id", "attribute_type_id", "field_name",
                                          "entity_type_id", "rule_type_code", "param1", "param2", "severity",
                                          "message", "sort_order"], rows))

    # allowed relationships
    rows = []
    for s, r, t, note in expand_allowed():
        i_d, o = ids("allowed_relationship", s, r, t)
        rows.append([i_d, o, m, gid(model_key, "relationship_type", r), gid(model_key, "entity_type", s),
                     gid(model_key, "entity_type", t), note])
    out.append(insert("allowed_relationship", ["id", "origin_id", "model_id", "relationship_type_id",
                                               "source_type_id", "target_type_id", "note"], rows))
    return "".join(out)


def sample_content_sql() -> str:
    """Sample entities, attribute values and relationships for the sample model."""
    m, k = SAMPLE_ID, SAMPLE_KEY
    dtype = {code: DATA_TYPES[dt] for code, _n, dt, *_ in A.ATTRS}
    ents, vals, rels = [], [], []
    for type_code, name, desc, attrs in A.SAMPLE_ENTITIES:
        e = gid(k, "entity", name)
        ents.append([e, m, gid(k, "entity_type", type_code), name, desc])
        for attr, value in attrs.items():
            dt = dtype[attr]
            col = STORAGE[dt]
            if dt == "date":
                value = date.fromisoformat(value)
            row = {"value_text": None, "value_number": None, "value_date": None}
            row[col] = value
            vals.append([gid(k, "attribute_value", name, attr), m, gid(k, "attribute_type", attr), e,
                         row["value_text"], row["value_number"], row["value_date"]])
    for src, rel, tgt in A.SAMPLE_RELS:
        rels.append([gid(k, "relationship", src, rel, tgt), m, gid(k, "relationship_type", rel),
                     gid(k, "entity", src), gid(k, "entity", tgt)])
    return (insert("entity", ["id", "model_id", "entity_type_id", "name", "description"], ents)
            + insert("attribute_value", ["id", "model_id", "attribute_type_id", "entity_id",
                                         "value_text", "value_number", "value_date"], vals)
            + insert("relationship", ["id", "model_id", "relationship_type_id", "source_entity_id",
                                      "target_entity_id"], rels))


def seed_sql(with_template: bool = True, with_sample: bool = True) -> str:
    """What to load, as one script (run in one transaction). The sample needs the template."""
    parts = ["SELECT set_config('eax.actor', 'system:seed', true);\n"]
    if with_template:
        parts += [
            "SELECT set_config('eax.history_label', 'ArchiMate 4 seed', true);\n",
            insert("model", ["id", "name", "description", "kind_code", "metamodel_name", "is_locked"], [[
                TEMPLATE_ID, "ArchiMate 4",
                "The ArchiMate 4 starter metamodel: 42 elements, 11 relationship types and the allowed "
                "relationships. Read-only; new models start from it.",
                "template", "ArchiMate 4", True]]),
            metamodel_sql(TEMPLATE_KEY, None),
        ]
    if with_sample:
        parts += [
            "SELECT set_config('eax.history_label', 'Sample model', true);\n",
            # created from the template (its source); a top-level model, so no parent to merge into
            insert("model", ["id", "origin_id", "name", "description", "kind_code", "source_model_id",
                             "metamodel_name"], [[
                SAMPLE_ID, TEMPLATE_ID, "Sample insurance model",
                "Sample content for trying EA Explorer: insurance applications, capabilities, data and "
                "goals. Safe to delete.",
                "project", TEMPLATE_ID, "ArchiMate 4"]]),
            metamodel_sql(SAMPLE_KEY, TEMPLATE_KEY),
            sample_content_sql(),
        ]
    return "".join(parts)


if __name__ == "__main__":  # print the SQL, for review or a manual load
    import sys

    sys.stdout.write(seed_sql(with_template=True, with_sample="--no-sample" not in sys.argv))
