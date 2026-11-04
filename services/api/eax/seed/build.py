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
from . import insurance as INS

NAMESPACE = uuid.UUID("6f4c2a52-2b0e-4b5e-9d63-6b0c0e7a1000")
TEMPLATE_KEY = "archimate4-template"
SAMPLE_KEY = "sample-insurance"
# Reference models: the key includes the version, so a new version is a new model beside the old one
INSURANCE_KEY = "insurance-reference-1.0"
INSURANCE_VERSION = "1.0"


def gid(*parts: str) -> str:
    """A stable GUID for a seed row."""
    return str(uuid.uuid5(NAMESPACE, ":".join(parts)))


# Laptop test models (phase 3.1): a fictitious insurer derived from the insurance reference model, its
# life and commercial models derived from it, and an independent model from the template.
GROUP_KEY, LIFE_KEY, COMMERCIAL_KEY, KAROO_KEY = "fynbos-group", "fynbos-life", "fynbos-commercial", "karoo-re"
LIFE_PRODUCTS = {"Family Funeral Plan", "Individual Whole Life", "Term Assurance", "Income Protection", "Credit Life",
                 "Group Life", "Group Disability", "Umbrella Fund Risk", "Linked Investment Plan", "Simple Funeral (pilot)"}
COMMERCIAL_PRODUCTS = {"Comprehensive Motor", "Household Contents", "Buildings", "Portable Possessions",
                       "SME Multi-Peril", "Commercial Fleet", "Liability", "Engineering"}

EMPTY_KEY = "empty-root"
LEAN_KEY = "lean-ea-metamodel-1.0"
LEAN_PROJECT_KEY = "karoo-digital-lean"
EMPTY_ID = gid("model", EMPTY_KEY)
TEMPLATE_ID = gid("model", TEMPLATE_KEY)
SAMPLE_ID = gid("model", SAMPLE_KEY)
INSURANCE_ID = gid("model", INSURANCE_KEY)

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


def sample_content_sql(k: str = SAMPLE_KEY) -> str:
    """Sample entities, attribute values and relationships for the sample model (or another model
    given by its key, which gets the same content)."""
    m = gid("model", k)
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


def insurance_content_sql(k: str = INSURANCE_KEY, origin: str | None = None, keep=None) -> str:
    """The insurance reference model's entities, attribute values, parents and relationships; or a
    copy of them in another model (key k), each entity pointing at the one it was copied from (origin)
    and only those keep(type_code, name) accepts (relationships only between entities kept)."""
    m = gid("model", k)
    dtype = {code: DATA_TYPES[dt] for code, _n, dt, *_ in A.ATTRS}
    ents, vals, parents, rels = [], [], [], []
    kept = {key for key, t, name, *_ in INS.ENTITIES if keep is None or keep(t, name)}
    for key, type_code, name, desc, parent, attrs in INS.ENTITIES:
        if key not in kept:
            continue
        e = gid(k, "entity", key)
        if origin:
            ents.append([e, gid(origin, "entity", key), m, gid(k, "entity_type", type_code), name, desc])
        else:
            ents.append([e, m, gid(k, "entity_type", type_code), name, desc])
        if parent and parent in kept:
            parents.append((e, gid(k, "entity", parent)))
        for attr, value in attrs.items():
            row = {"value_text": None, "value_number": None, "value_date": None}
            row[STORAGE[dtype[attr]]] = value
            vals.append([gid(k, "attribute_value", key, attr), m, gid(k, "attribute_type", attr), e,
                         row["value_text"], row["value_number"], row["value_date"]])
    for src, rel, tgt, name in INS.RELATIONSHIPS:
        if src not in kept or tgt not in kept:
            continue
        rels.append([gid(k, "relationship", src, rel, tgt), m, gid(k, "relationship_type", rel),
                     gid(k, "entity", src), gid(k, "entity", tgt), name])
    # parents after every entity exists (one INSERT cannot point at rows it is still adding)
    parent_sql = ("UPDATE core.entities c SET parent_entity_id = p.id\nFROM (VALUES\n"
                  + ",\n".join(f"    ('{c}'::uuid, '{p}'::uuid)" for c, p in parents)
                  + "\n) AS v (child, parent)\nJOIN core.entities p ON p.guid = v.parent\n"
                  "WHERE c.guid = v.child;\n") if parents else ""
    entity_cols = ["id", "origin_id", "model_id", "entity_type_id", "name", "description"] if origin else \
        ["id", "model_id", "entity_type_id", "name", "description"]
    return (insert("entity", entity_cols, ents)
            + parent_sql
            + insert("attribute_value", ["id", "model_id", "attribute_type_id", "entity_id",
                                         "value_text", "value_number", "value_date"], vals)
            + insert("relationship", ["id", "model_id", "relationship_type_id", "source_entity_id",
                                      "target_entity_id", "name"], rels))


# Laptop only: a few saved versions of two sample entities, made by different people a moment apart,
# so the History tab shows values set, changed and cleared and relationships added and removed (D110).
# Each step is (who, what): the seed runs every step in its own transaction, a second or two apart.
HISTORY_DEMO = [
    ("user_architect", "Customer Portal: vendor, version and cost recorded; reads claim records", [
        ("describe", "Customer Portal", "Self-service web portal for policyholders: claims and policy changes", None),
        ("set", "Customer Portal", "Vendor", "In-house"),
        ("set", "Customer Portal", "Version", "1.0"),
        ("set", "Customer Portal", "AnnualCost", 450000),
        ("add", "Customer Portal", "Access", "Claim Record"),
    ]),
    ("user_model_sub_admin", "Customer Portal goes live; Policy Administration System upgraded", [
        ("set", "Customer Portal", "Lifecycle", "Production"),
        ("set", "Customer Portal", "ArchitectureState", "Baseline"),
        ("set", "Customer Portal", "Version", "1.4"),
        ("set", "Customer Portal", "GoLiveDate", "2026-03-01"),
        ("set", "Policy Administration System", "Version", "11.0"),
        ("set", "Policy Administration System", "AnnualCost", 4600000),
    ]),
    ("user_architect", "Customer Portal: new owner, serves the claims department directly", [
        ("set", "Customer Portal", "Owner", "Head of Digital"),
        ("set", "Customer Portal", "AnnualCost", 520000),
        ("remove", "Customer Portal", "Serving", "Claims Platform"),
        ("add", "Customer Portal", "Serving", "Claims Department"),
    ]),
    ("user_model_admin", "Customer Portal made critical and moved to SaaS; Policy Administration System to be phased out", [
        ("describe", "Customer Portal", "Self-service portal for policyholders and brokers: claims, policy changes and documents", None),
        ("set", "Customer Portal", "Criticality", 5),
        ("set", "Customer Portal", "Hosting", "SaaS"),
        ("clear", "Customer Portal", "Vendor", None),
        ("add", "Customer Portal", "Realization", "Claims Management"),
        ("set", "Policy Administration System", "Lifecycle", "Phase Out"),
        ("set", "Policy Administration System", "Owner", "Head of Policy and Admin IT"),
    ]),
]


def history_demo_steps(k: str = SAMPLE_KEY) -> list[tuple[str, str]]:
    """HISTORY_DEMO as (actor, SQL) per step, for the sample model."""
    m = gid("model", k)
    dtype = {code: DATA_TYPES[dt] for code, _n, dt, *_ in A.ATTRS}
    present = {(name, attr) for _t, name, _d, attrs in A.SAMPLE_ENTITIES for attr in attrs}
    steps = []
    for actor, note, actions in HISTORY_DEMO:
        sql = [f"SELECT set_config('eax.actor', {lit(actor)}, true);\n",
               f"SELECT set_config('eax.history_label', {lit('Laptop history demo: ' + note)}, true);\n"]
        for op, name, what, value in actions:
            e = gid(k, "entity", name)
            if op == "describe":
                sql.append(f"UPDATE core.entities SET description = {lit(what)} WHERE guid = '{e}';\n")
            elif op in ("set", "clear"):
                dt = dtype[what]
                col = STORAGE[dt]
                if dt == "date" and value is not None:
                    value = date.fromisoformat(value)
                g = gid(k, "attribute_value", name, what)
                if (name, what) in present or op == "clear":
                    sql.append(f"UPDATE core.attribute_values SET {col} = {lit(value)} WHERE guid = '{g}';\n")
                else:
                    row = {"value_text": None, "value_number": None, "value_date": None}
                    row[col] = value
                    sql.append(insert("attribute_value", ["id", "model_id", "attribute_type_id", "entity_id", "value_text",
                                                          "value_number", "value_date"],
                                      [[g, m, gid(k, "attribute_type", what), e, row["value_text"], row["value_number"],
                                        row["value_date"]]]))
                    present.add((name, what))
            elif op == "add":
                sql.append(insert("relationship", ["id", "model_id", "relationship_type_id", "source_entity_id",
                                                   "target_entity_id"],
                                  [[gid(k, "relationship", name, what, value), m, gid(k, "relationship_type", what), e,
                                    gid(k, "entity", value)]]))
            elif op == "remove":
                sql.append(f"UPDATE core.relationships SET is_deleted = true "
                           f"WHERE guid = '{gid(k, 'relationship', name, what, value)}';\n")
        steps.append((actor, "".join(sql)))
    return steps


def test_models_sql() -> str:
    """Laptop test models (phase 3.1), for trying roles and model assignments:
      Fynbos Mutual (group)       project, created from the Insurance reference model (full copy)
        Fynbos Life               project, derived from the group (merges into it): life products only
        Fynbos Commercial         project, derived from the group: short-term and commercial products only
      Karoo Re (independent)      project, created from the ArchiMate 4 template, sample content, plus
                                  relationship rules and entities that break rules (D113)
    Fynbos Mutual is a fictitious insurer."""
    group_id, life_id, com_id, karoo_id = (gid("model", k) for k in (GROUP_KEY, LIFE_KEY, COMMERCIAL_KEY, KAROO_KEY))
    cols = ["id", "origin_id", "name", "description", "kind_code", "source_model_id", "parent_model_id",
            "metamodel_name", "owner", "industry"]
    not_product = lambda t, n, keep: t != "Product" or n in keep  # noqa: E731
    return "".join([
        "SELECT set_config('eax.history_label', 'Laptop test models', true);\n",
        insert("model", cols, [[group_id, INSURANCE_ID, "Fynbos Mutual (group)",
                                "Test model: Fynbos Mutual, a fictitious South African insurer, created from the Insurance "
                                "reference model. Its life and commercial models derive from it.",
                                "project", INSURANCE_ID, None, "ArchiMate 4", "Fynbos group architecture", "Insurance"]]),
        metamodel_sql(GROUP_KEY, INSURANCE_KEY),
        insurance_content_sql(GROUP_KEY, INSURANCE_KEY),
        insert("model", cols, [
            [life_id, group_id, "Fynbos Life", "Test model: the life and funeral business, derived from the Fynbos group model.",
             "project", group_id, group_id, "ArchiMate 4", "Fynbos Life architecture", "Insurance"],
            [com_id, group_id, "Fynbos Commercial", "Test model: the short-term and commercial business, derived from the "
             "Fynbos group model.", "project", group_id, group_id, "ArchiMate 4", "Fynbos Commercial architecture", "Insurance"]]),
        metamodel_sql(LIFE_KEY, GROUP_KEY),
        insurance_content_sql(LIFE_KEY, GROUP_KEY, lambda t, n: not_product(t, n, LIFE_PRODUCTS)),
        metamodel_sql(COMMERCIAL_KEY, GROUP_KEY),
        insurance_content_sql(COMMERCIAL_KEY, GROUP_KEY, lambda t, n: not_product(t, n, COMMERCIAL_PRODUCTS)),
        insert("model", cols, [[karoo_id, TEMPLATE_ID, "Karoo Re (independent)",
                                "Test model: an independent model created from the ArchiMate 4 template, not related to Fynbos.",
                                "project", TEMPLATE_ID, None, "ArchiMate 4", "Karoo Re architecture", "Reinsurance"]]),
        metamodel_sql(KAROO_KEY, TEMPLATE_KEY),
        sample_content_sql(KAROO_KEY),
        rules_demo_sql(),
        lean_sql(),
    ])


# Laptop only: rules about relationships and entities that break rules, in Karoo Re, so each entity's
# Rules tab and the Failing checks tab have something to show (D113). (type, name, description, values,
# relationships as (relationship type, other entity, outgoing?)); a key keeps two same-named entities apart.
RULE_DEMO_RULES = [
    # entity type, relationship type, other entity type, severity, message
    ("ApplicationComponent", "Realization", "Capability", "warning", "An application realises at least one capability"),
    ("ApplicationComponent", "Serving", "", "warning", "An application serves someone or something"),
    ("Capability", "Realization", "Application Component", "warning", "A capability is realised by at least one application"),
    ("Requirement", "Realization", "Goal", "error", "A requirement realises a goal"),
]
RULE_DEMO_ENTITIES = [
    ("legacy-sheet", "ApplicationComponent", "Legacy Claims Spreadsheet",
     "Rules demo: no owner, criticality out of range, a version and URL that break their patterns, a negative cost, "
     "retiring without a retirement date, and no relationships",
     {"Lifecycle": "Retiring", "Criticality": 7, "Version": "v2 beta", "AnnualCost": -500, "Url": "intranet/claims"}, []),
    ("broker-portal-1", "ApplicationComponent", "Broker Portal",
     "Rules demo: shares its name with another application, went live in 1985, retired before it went live, and realises "
     "no capability",
     {"Owner": "Broker Services", "Lifecycle": "Production", "Criticality": 3, "GoLiveDate": "1985-06-01",
      "RetirementDate": "1980-01-01"}, [("Serving", "Claims Department", True)]),
    ("broker-portal-2", "ApplicationComponent", "Broker Portal",
     "Rules demo: a second application with the same name; otherwise every rule passes",
     {"Owner": "Broker Services", "Lifecycle": "Phase In", "Criticality": 2, "Version": "0.9"},
     [("Serving", "Claims Department", True), ("Realization", "Claims Management", True)]),
    ("fraud-detection", "Capability", "Fraud Detection",
     "Rules demo: a capability level out of range, and no application realises it", {"Owner": "COO", "CapabilityLevel": 6}, []),
    ("paperless-claims", "Requirement", "Paperless claims",
     "Rules demo: a requirement that realises no goal", {"Owner": "Claims Operations", "Priority": "Should"}, []),
    ("dc-exit", "WorkPackage", "Data Centre Exit",
     "Rules demo: ends before it starts", {"Owner": "Infrastructure", "StartDate": "2026-09-01", "EndDate": "2026-03-31"}, []),
]


def rules_demo_sql(k: str = KAROO_KEY) -> str:
    """Laptop only (D113): relationship rules for Karoo Re's metamodel, and entities in Karoo Re that break
    value rules, the relationship rules and the unique-name rule, for the Rules and Failing checks tabs."""
    m = gid("model", k)
    dtype = {code: DATA_TYPES[dt] for code, _n, dt, *_ in A.ATTRS}
    rules = [[gid(k, "validation_rule", "rules-demo", t, r, o), m, gid(k, "entity_type", t), "relationships",
              "has_relationship", r, o, sev, msg, 900 + i] for i, (t, r, o, sev, msg) in enumerate(RULE_DEMO_RULES)]
    ents, vals, rels = [], [], []
    for key, t, name, desc, attrs, links in RULE_DEMO_ENTITIES:
        e = gid(k, "entity", "rules-demo", key)
        ents.append([e, m, gid(k, "entity_type", t), name, desc])
        for attr, value in attrs.items():
            col = STORAGE[dtype[attr]]
            if dtype[attr] == "date":
                value = date.fromisoformat(value)
            row = {"value_text": None, "value_number": None, "value_date": None}
            row[col] = value
            vals.append([gid(k, "attribute_value", "rules-demo", key, attr), m, gid(k, "attribute_type", attr), e,
                         row["value_text"], row["value_number"], row["value_date"]])
        for rel, other, outgoing in links:
            o = gid(k, "entity", other)
            src, tgt = (e, o) if outgoing else (o, e)
            rels.append([gid(k, "relationship", "rules-demo", key, rel, other), m, gid(k, "relationship_type", rel), src, tgt])
    return "".join([
        "SELECT set_config('eax.history_label', 'Laptop rules demo', true);\n",
        insert("validation_rule", ["id", "model_id", "entity_type_id", "field_name", "rule_type_code", "param1", "param2",
                                   "severity", "message", "sort_order"], rules),
        insert("entity", ["id", "model_id", "entity_type_id", "name", "description"], ents),
        insert("attribute_value", ["id", "model_id", "attribute_type_id", "entity_id", "value_text", "value_number",
                                   "value_date"], vals),
        insert("relationship", ["id", "model_id", "relationship_type_id", "source_entity_id", "target_entity_id"], rels),
    ])


def lean_sql() -> str:
    """Laptop test models (D81): an organisation's own root metamodel built from scratch, created from the
    Root model (not ArchiMate): Lean EA metamodel 1.0, with five types in three layers, four relationship
    types and two attributes; and Karoo Digital, a project model created from it with a little content.
    The root is not locked: its Model Admin (user_model_creator on laptops) changes it."""
    k, p = LEAN_KEY, LEAN_PROJECT_KEY
    layers = [("Business", "ffffb5"), ("Application", "b5ffff"), ("Technology", "c9e7b7")]
    types = [("Capability", "Capability", "Business", "CAP"), ("BusinessProcess", "Business Process", "Business", "PRC"),
             ("Application", "Application", "Application", "APP"), ("DataEntity", "Data Entity", "Application", "DAT"),
             ("Platform", "Platform", "Technology", "PLT")]
    rels = [("Supports", "supports", "Dependency"), ("Uses", "uses", "Dependency"),
            ("Owns", "owns", "Structural"), ("RunsOn", "runs on", "Dependency")]
    allowed = [("Application", "Supports", "Capability"), ("Application", "Supports", "BusinessProcess"),
               ("BusinessProcess", "Uses", "Application"), ("Application", "Owns", "DataEntity"),
               ("Application", "RunsOn", "Platform"), ("Capability", "Owns", "Capability")]
    attrs = [("Owner", "Owner", "text", None), ("Criticality", "Criticality", "list", "Criticality")]

    def metamodel(key, origin):
        m = gid("model", key)
        o = (lambda *x: gid(origin, *x)) if origin else (lambda *x: None)
        out = [insert("layer", ["id", "origin_id", "model_id", "code", "name", "colour", "sort_order"],
                      [[gid(key, "layer", n), o("layer", n), m, snake(n), n, c, i * 10] for i, (n, c) in enumerate(layers, 1)])]
        out.append(insert("entity_type", ["id", "origin_id", "model_id", "layer_id", "code", "name", "id_prefix", "table_name", "sort_order"],
                          [[gid(key, "entity_type", c), o("entity_type", c), m, gid(key, "layer", lay), c, n, pre, snake(c), i * 10]
                           for i, (c, n, lay, pre) in enumerate(types, 1)]))
        out.append(insert("relationship_type", ["id", "origin_id", "model_id", "code", "name", "verb", "category", "is_directed", "sort_order"],
                          [[gid(key, "relationship_type", c), o("relationship_type", c), m, c, c, v, cat, True, i * 10]
                           for i, (c, v, cat) in enumerate(rels, 1)]))
        out.append(insert("pick_list", ["id", "origin_id", "model_id", "code", "name"],
                          [[gid(key, "pick_list", "Criticality"), o("pick_list", "Criticality"), m, "Criticality", "Criticality"]]))
        out.append(insert("pick_list_value", ["id", "origin_id", "model_id", "pick_list_id", "value", "sort_order"],
                          [[gid(key, "pick_list_value", "Criticality", v), o("pick_list_value", "Criticality", v), m,
                            gid(key, "pick_list", "Criticality"), v, i * 10] for i, v in enumerate(["High", "Medium", "Low"], 1)]))
        out.append(insert("attribute_type", ["id", "origin_id", "model_id", "code", "name", "data_type_code", "pick_list_id", "column_name"],
                          [[gid(key, "attribute_type", c), o("attribute_type", c), m, c, n, dt,
                            gid(key, "pick_list", pl) if pl else None, snake(c)] for c, n, dt, pl in attrs]))
        out.append(insert("item_attribute", ["id", "origin_id", "model_id", "attribute_type_id", "entity_type_id", "is_required", "section", "sort_order"],
                          [[gid(key, "item_attribute", t, a), o("item_attribute", t, a), m, gid(key, "attribute_type", a),
                            gid(key, "entity_type", t), False, "General", j * 10]
                           for t, *_ in types for j, (a, *_r) in enumerate(attrs, 1)]))
        out.append(insert("allowed_relationship", ["id", "origin_id", "model_id", "relationship_type_id", "source_type_id", "target_type_id"],
                          [[gid(key, "allowed_relationship", s_, r, t), o("allowed_relationship", s_, r, t), m,
                            gid(key, "relationship_type", r), gid(key, "entity_type", s_), gid(key, "entity_type", t)]
                           for s_, r, t in allowed]))
        return "".join(out)

    cols = ["id", "origin_id", "name", "description", "kind_code", "source_model_id", "metamodel_name", "is_locked",
            "owner", "version_label", "industry"]
    ents = [("Capability", "Customer Onboarding"), ("Capability", "Claims Handling"), ("BusinessProcess", "Register a claim"),
            ("Application", "Karoo Portal"), ("Application", "Claims Engine"), ("DataEntity", "Claim"), ("Platform", "Azure")]
    links = [("Karoo Portal", "Supports", "Customer Onboarding"), ("Claims Engine", "Supports", "Claims Handling"),
             ("Register a claim", "Uses", "Claims Engine"), ("Claims Engine", "Owns", "Claim"), ("Claims Engine", "RunsOn", "Azure")]
    pm = gid("model", p)
    return "".join([
        "SELECT set_config('eax.history_label', 'Laptop test models: a root metamodel from scratch', true);\n",
        insert("model", cols, [[gid("model", k), None, "Lean EA metamodel",
                                "Test model: an organisation's own root metamodel built from scratch (from the Root model, "
                                "not ArchiMate): five types in three layers. Its Model Admin changes it.",
                                "template", EMPTY_ID, "Lean EA metamodel 1.0", False, "Karoo enterprise architecture", "1.0", ""]]),
        metamodel(k, None),
        insert("model", cols, [[pm, gid("model", k), "Karoo Digital (lean)",
                                "Test model: a working model created from the Lean EA metamodel.",
                                "project", gid("model", k), "Lean EA metamodel 1.0", False, "Karoo digital team", "", "Reinsurance"]]),
        metamodel(p, k),
        insert("entity", ["id", "model_id", "entity_type_id", "name"], [[gid(p, "entity", n), pm, gid(p, "entity_type", t), n] for t, n in ents]),
        insert("relationship", ["id", "model_id", "relationship_type_id", "source_entity_id", "target_entity_id"],
               [[gid(p, "relationship", a, r, b), pm, gid(p, "relationship_type", r), gid(p, "entity", a), gid(p, "entity", b)] for a, r, b in links]),
    ])


def seed_sql(with_template: bool = True, with_sample: bool = True, with_insurance: bool = True) -> str:
    """What to load, as one script (run in one transaction, by the installer's login eax_migrator,
    because templates and reference models are locked). The others need the template."""
    parts = ["SELECT set_config('eax.actor', 'system:seed', true);\n"]
    if with_template:
        parts += [
            "SELECT set_config('eax.history_label', 'Root model and ArchiMate 4 seed', true);\n",
            # the top of the model hierarchy (D81): every root metamodel is created from it
            insert("model", ["id", "name", "description", "kind_code", "metamodel_name", "is_locked", "owner"], [[
                EMPTY_ID, "Root",
                "The root of the model hierarchy: no layers, types or content. Every root metamodel (ArchiMate 4, "
                "ArchiMate 5 when it comes, an organisation's own) is created from it. Read-only.",
                "template", "None", True, "EA Explorer"]]),
            insert("model", ["id", "name", "description", "kind_code", "source_model_id", "metamodel_name", "is_locked",
                             "owner"], [[
                TEMPLATE_ID, "ArchiMate 4",
                "The ArchiMate 4 root metamodel: 42 elements, 11 relationship types and the allowed "
                "relationships. Read-only; new models start from it.",
                "template", EMPTY_ID, "ArchiMate 4", True, "EA Explorer"]]),
            metamodel_sql(TEMPLATE_KEY, None),
        ]
    if with_insurance:
        parts += [
            "SELECT set_config('eax.history_label', 'Insurance reference model', true);\n",
            insert("model", ["id", "origin_id", "name", "description", "kind_code", "source_model_id",
                             "metamodel_name", "is_locked", "owner", "industry", "version_label"], [[
                INSURANCE_ID, TEMPLATE_ID, "Insurance reference model",
                "Industry reference model for a generic insurer (life, funeral and short-term): "
                "capabilities to level 4, value streams, business services, processes and functions, "
                "products, business objects, application services, actors and roles, on ArchiMate 4. "
                "Read-only: copy it to start a model.",
                "reference", TEMPLATE_ID, "ArchiMate 4", True, "EA Explorer", "Insurance", INSURANCE_VERSION]]),
            metamodel_sql(INSURANCE_KEY, TEMPLATE_KEY),
            insurance_content_sql(),
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
