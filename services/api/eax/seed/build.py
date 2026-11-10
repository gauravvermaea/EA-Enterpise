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

from .. import notation
from . import archimate4 as A
from . import demo_estate as DEMO
from . import industries as IND
from . import insurance as INS
from . import togaf10 as T10

NAMESPACE = uuid.UUID("6f4c2a52-2b0e-4b5e-9d63-6b0c0e7a1000")
TEMPLATE_KEY = "archimate4-template"
SAMPLE_KEY = "sample-insurance"
# Reference models: the key includes the version, so a new version is a new model beside the old one
INSURANCE_KEY = "insurance-reference-1.0"
INSURANCE_VERSION = "1.0"
# The principles model (D270): under Root and ArchiMate 4, a metamodel of principles only
PRINCIPLE_KEY = "root-principle-model-1.0"
PRINCIPLE_SOURCE = "The Open Group Architecture Principles: A Case Study (Y082, October 2008)"
# Names and categories only; the statement, rationale and implications are filled in on the platform (see D271)
PRINCIPLES = [
    ("Business", ["Primacy of Principles", "Maximize Benefit to the Enterprise", "Compliance with Law",
                  "Available Anytime from Anywhere", "Business Continuity", "Citizenship", "De-Customization",
                  "Painless User Experience", "Self-Service", "Sharing of Information"]),
    ("Data", ["One Source", "Content Management", "Custodianship"]),
    ("Application", ["De-Skill", "Re-Use, not Re-Invent"]),
    ("Technology", ["Boundaryless Information Flow"]),
    ("Governance", ["Standardization", "Stability", "Discovery", "Separation of Development, Maintenance, and Operations"]),
]


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
# laptop test models in each state (D242), on the Lean EA metamodel: key, name, description, how it is put in that state
STATE_MODELS = [
    ("karoo-legacy-archived", "Karoo Legacy (archived)",
     "Test model: an archived (retired) model. Data quality never measures it.", "lifecycle = 'archived'"),
    ("karoo-audit-frozen", "Karoo Audit 2025 (frozen)",
     "Test model: content frozen (locked against changes to its content), for example after an audit. Not measured unless "
     "an admin ticks it.", "lock_level = 'content', lock_reason = 'Frozen after the 2025 audit'"),
    ("karoo-pilot-metamodel-locked", "Karoo Pilot (metamodel locked)",
     "Test model: its metamodel is locked but its content can still change. Measured by default.",
     "lock_level = 'metamodel', lock_reason = 'Metamodel agreed for the pilot'"),
    ("karoo-ops-maintenance", "Karoo Operations (maintenance)",
     "Test model: locked for maintenance (nobody changes it while it is worked on). Measured by default.",
     "lock_level = 'maintenance', lock_reason = 'Being restructured'"),
    ("karoo-board-read-only", "Karoo Board pack (read-only)",
     "Test model: read-only (locked by the installer). Not measured unless an admin ticks it.", "is_locked = true"),
]
EMPTY_ID = gid("model", EMPTY_KEY)
TEMPLATE_ID = gid("model", TEMPLATE_KEY)
SAMPLE_ID = gid("model", SAMPLE_KEY)
INSURANCE_ID = gid("model", INSURANCE_KEY)
PRINCIPLE_ID = gid("model", PRINCIPLE_KEY)
TOGAF10_ID = gid("model", T10.KEY)

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


def entity_links(value: str, model: str, key: str) -> str:
    """A seed Link value (D418): {entity:Name} becomes the app's link to that entity of the same seed model."""
    return re.sub(r"\{entity:([^}]+)\}", lambda x: f"#/metamodel/{model}/entity/{gid(key, 'entity', x.group(1))}", value)


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
    # domains (core.layers)
    rows = []
    for i, (domain, colour) in enumerate(A.DOMAIN_COLOURS.items(), 1):
        i_d, o = ids("layer", domain)
        rows.append([i_d, o, m, snake(domain), domain, colour, i * 10])
    out.append(insert("layer", ["id", "origin_id", "model_id", "code", "name", "colour", "sort_order"], rows))

    # entity types
    rows = []
    for i, (code, name, domain, aspect, prefix) in enumerate(A.ENTITY_TYPES, 1):
        i_d, o = ids("entity_type", code)
        rows.append([i_d, o, m, gid(model_key, "layer", domain), code, name, A.EXTENSION_DESCRIPTIONS.get(code, ""), aspect, prefix,
                     snake(code), i * 10, notation.default_notation(code), code in A.CONNECTOR_TYPES])
    out.append(insert("entity_type", ["id", "origin_id", "model_id", "layer_id", "code", "name", "description", "aspect",
                                      "id_prefix", "table_name", "sort_order", "notation", "is_connector"], rows))

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

    # attribute types: the Workbench business attributes. The Repository Area is set on the entity type, not on each
    # entity (owner, 8 Nov 2026, D318): core.entity_types.repository_area
    attrs = list(A.ATTRS)
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
            if dt == "url":
                value = entity_links(value, m, k)
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
    return reference_content_sql(INS, k, origin, keep)


def reference_content_sql(INS, k: str, origin: str | None = None, keep=None) -> str:
    """A reference model's content (a module with ENTITIES and RELATIONSHIPS, like insurance.py and the industry
    models of phase 39) in the model with key k."""
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
        ("add", "Customer Portal", "Association", "Claims Management"),
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
    """Every laptop test model in one script (tests and manual loads); the start-up loads them step by step."""
    return "".join(sql for _key, _label, _check, sql in test_model_steps())


SEED_ACTOR = "SELECT set_config('eax.actor', 'system:seed', true);\n"


def test_model_steps() -> list[tuple[str, str, str, str]]:
    """The laptop test models as steps, loaded one transaction each in the background after the API has started (D255),
    so the models appear one by one: (key, what it loads, a query that finds it already loaded, the SQL)."""
    by_guid = "SELECT 1 FROM core.models WHERE guid = '{}'::uuid"
    sql = _test_models_parts()
    return [
        ("fynbos-group", "Fynbos Mutual (group)", by_guid.format(gid("model", GROUP_KEY)), SEED_ACTOR + sql[0]),
        ("fynbos-life-commercial", "Fynbos Life and Fynbos Commercial", by_guid.format(gid("model", COMMERCIAL_KEY)), SEED_ACTOR + sql[1]),
        ("karoo-re", "Karoo Re (independent) and its rules", by_guid.format(gid("model", KAROO_KEY)), SEED_ACTOR + sql[2]),
        ("lean", "Lean EA metamodel, Karoo Digital and a model in each state", by_guid.format(gid("model", LEAN_KEY)), SEED_ACTOR + sql[3]),
        ("demo-estate", "Protea Insurance (demo estate)", by_guid.format(gid("model", DEMO.DEMO_KEY)), SEED_ACTOR + sql[4]),
        ("quality-demo", "Data quality samples",
         "SELECT 1 FROM core.quality_rules r JOIN core.models m ON m.id = r.model_id WHERE m.name = 'Protea Insurance (demo estate)'",
         SEED_ACTOR + sql[5]),
    ]


def _test_models_parts() -> list[str]:
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
    label = "SELECT set_config('eax.history_label', 'Laptop test models', true);\n"
    return [
        label + "".join([insert("model", cols, [[group_id, INSURANCE_ID, "Fynbos Mutual (group)",
                                "Test model: Fynbos Mutual, a fictitious South African insurer, created from the Insurance "
                                "reference model. Its life and commercial models derive from it.",
                                "project", INSURANCE_ID, None, "ArchiMate 4", "Fynbos group architecture", "Insurance"]]),
        metamodel_sql(GROUP_KEY, INSURANCE_KEY),
        insurance_content_sql(GROUP_KEY, INSURANCE_KEY)]),
        label + "".join([insert("model", cols, [
            [life_id, group_id, "Fynbos Life", "Test model: the life and funeral business, derived from the Fynbos group model.",
             "project", group_id, group_id, "ArchiMate 4", "Fynbos Life architecture", "Insurance"],
            [com_id, group_id, "Fynbos Commercial", "Test model: the short-term and commercial business, derived from the "
             "Fynbos group model.", "project", group_id, group_id, "ArchiMate 4", "Fynbos Commercial architecture", "Insurance"]]),
        metamodel_sql(LIFE_KEY, GROUP_KEY),
        insurance_content_sql(LIFE_KEY, GROUP_KEY, lambda t, n: not_product(t, n, LIFE_PRODUCTS)),
        metamodel_sql(COMMERCIAL_KEY, GROUP_KEY),
        insurance_content_sql(COMMERCIAL_KEY, GROUP_KEY, lambda t, n: not_product(t, n, COMMERCIAL_PRODUCTS))]),
        label + "".join([insert("model", cols, [[karoo_id, TEMPLATE_ID, "Karoo Re (independent)",
                                "Test model: an independent model created from the ArchiMate 4 template, not related to Fynbos.",
                                "project", TEMPLATE_ID, None, "ArchiMate 4", "Karoo Re architecture", "Reinsurance"]]),
        metamodel_sql(KAROO_KEY, TEMPLATE_KEY),
        sample_content_sql(KAROO_KEY),
        rules_demo_sql()]),
        label + lean_sql(),
        label + demo_estate_sql(),
        label + quality_demo_sql(),
    ]


def quality_demo_sql() -> str:
    """Laptop test data for data quality (phase 12, D239 to D246), on the demo estate and the test models, so every case
    can be tried after a clean rebuild:
      Protea Insurance: three quality rules (a warning relationship rule, a warning attribute rule, an error naming rule),
        Url left out of data quality for the whole model (D246), Retirement date not applicable on Actuarial Modelling
        (approved), Repository area on Complaints Tracker (waiting for a Model Admin), Landscape level waiting on the
        Chief Executive (a stakeholder), a valid seal (Billing Engine), an expired one (Broker Portal), one broken by a
        later change (Claims Platform) and one marked still current (CRM); stale entities appear once the stale period has passed (the loader cannot date content in the past)
      Contact Centre Telephony retired, so data quality leaves it out
      Every test model with a library icon (D247), Karoo Re with an uploaded one
      Fraud Analytics: a 'not applicable' a Model Admin rejected (ask again); Fynbos Commercial: a Model Admin's change a
        Super Admin rejected (ask again)
      Fynbos Life: its own score weights and colours (D244); Karoo Re: a Model Admin's change waiting for a Super Admin
      Sample insurance model left out of the measurements and Karoo Audit 2025 (frozen) ticked in (D242)"""
    P = "(SELECT id FROM core.models WHERE name = 'Protea Insurance (demo estate)')"

    def ent(name, typ="ApplicationComponent"):
        return (f"(SELECT e.id FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id WHERE e.model_id = {P} "
                f"AND t.code = '{typ}' AND e.name = '{name}' AND NOT e.is_deleted LIMIT 1)")
    return f"""SELECT set_config('eax.history_label', 'Laptop test models: data quality cases', true);
INSERT INTO core.quality_rules (model_id, code, name, kind, entity_type, spec, severity, message, created_by, modified_by) VALUES
 ({P}, 'QR-01', 'Every application serves something', 'relationship', 'ApplicationComponent',
  '{{"relationship_type": "Serving", "direction": "out", "min": 1}}', 'warning', '', 'user_model_admin', 'user_model_admin'),
 ({P}, 'QR-02', 'A retiring application has a retirement date', 'attribute', 'ApplicationComponent',
  '{{"when": {{"attribute": "Lifecycle", "op": "in", "value": ["Retiring", "Phase Out"]}}, "then": {{"attribute": "RetirementDate", "op": "filled"}}}}',
  'warning', '', 'user_model_admin', 'user_model_admin'),
 ({P}, 'QR-03', 'Application names start with a capital letter', 'naming', 'ApplicationComponent',
  '{{"pattern": "[A-Z0-9].*"}}', 'error', 'Start the name with a capital letter', 'user_model_admin', 'user_model_admin');
INSERT INTO core.quality_settings (model_id, weights, modified_by) VALUES ({P}, '{{"*": {{"attr:Url": 0}}}}', 'user_model_admin');
INSERT INTO core.quality_exemptions (model_id, entity_id, item, reason, status, requested_by, requested_at, decided_by, decided_at) VALUES
 ({P}, {ent('Actuarial Modelling')}, 'attr:RetirementDate', 'In production with no retirement planned', 'approved', 'user_architect',
  now() - interval '9 days', 'user_model_admin', now() - interval '8 days'),
 ({P}, {ent('Chief Executive', 'Stakeholder')}, 'attr:LandscapeLevel', 'A person is not on the landscape', 'pending', 'user_architect',
  now() - interval '2 hours', NULL, NULL);
INSERT INTO core.quality_exemptions (model_id, entity_id, item, reason, status, requested_by, requested_at, decided_by, decided_at,
                                     decision_note) VALUES
 ({P}, {ent('Fraud Analytics')}, 'attr:RetirementDate', 'No retirement planned', 'rejected', 'user_architect',
  now() - interval '5 days', 'user_model_admin', now() - interval '4 days', 'It is replaced next year: add the planned date');
INSERT INTO core.quality_seals (entity_id, model_id, kind, sealed_by, sealed_at, note) VALUES
 ({ent('Billing Engine')}, {P}, 'seal', 'user_model_admin', now(), 'Checked with the billing team'),
 ({ent('Broker Portal')}, {P}, 'seal', 'eax_migrator', now() - interval '400 days', 'Checked when it was loaded, long ago'),
 ({ent('CRM')}, {P}, 'current', 'user_model_admin', now(), ''),
 ({ent('Claims Platform')}, {P}, 'seal', 'user_model_admin', now() - interval '20 days', 'Checked before its last change');
INSERT INTO core.quality_settings (model_id, score_parts, bands, modified_by) VALUES
 ((SELECT id FROM core.models WHERE name = 'Fynbos Life'), '{{"completeness": 60, "rules": 30, "freshness": 10}}',
  '{{"green": 75, "amber": 50}}', 'user_super_admin');
INSERT INTO core.quality_changes (model_id, kind, payload, summary, note, requested_by) VALUES
 ((SELECT id FROM core.models WHERE name = 'Karoo Re (independent)'), 'settings',
  '{{"stale_days": 180, "cron": null, "weights": {{}}, "score_parts": {{"completeness": 40, "rules": 40, "freshness": 20}}, "bands": null}}',
  'Stale after 180 days; schedule inherited; score 40% completeness, 40% rules passed, 20% fresh; colours inherited',
  'Reinsurance treaties change twice a year', 'user_model_admin');
UPDATE core.entities SET status_code = 'retired' WHERE id = {ent('Contact Centre Telephony')};
-- model icons (D247): a library icon for each test model, and Karoo Re with an image uploaded for it alone
INSERT INTO core.model_icons (model_id, library, set_by)
SELECT m.id, v.icon, 'eax_migrator' FROM (VALUES
 ('Root', 'layers'),
 ('ArchiMate 4', 'compass'),
 ('Insurance reference model', 'umbrella'),
 ('Sample insurance model', 'shield'),
 ('Fynbos Mutual (group)', 'bank'),
 ('Fynbos Life', 'heart'),
 ('Fynbos Commercial', 'briefcase'),
 ('Lean EA metamodel', 'puzzle'),
 ('Karoo Digital (lean)', 'rocket'),
 ('Karoo Legacy (archived)', 'ship'),
 ('Karoo Audit 2025 (frozen)', 'lock'),
 ('Karoo Pilot (metamodel locked)', 'target'),
 ('Karoo Operations (maintenance)', 'gear'),
 ('Karoo Board pack (read-only)', 'chart'),
 ('Protea Insurance (demo estate)', 'leaf')) AS v (name, icon) JOIN core.models m ON m.name = v.name AND NOT m.is_deleted
ON CONFLICT (model_id) DO NOTHING;
INSERT INTO core.model_icons (model_id, content_type, data, set_by)
SELECT id, 'image/svg+xml', convert_to('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#e8590c"/><path d="M10 46 L24 24 L32 36 L40 22 L54 46 Z" fill="#fff"/><circle cx="46" cy="16" r="5" fill="#ffd43b"/></svg>', 'UTF8'), 'user_model_admin' FROM core.models WHERE name = 'Karoo Re (independent)'
ON CONFLICT (model_id) DO NOTHING;
INSERT INTO core.quality_changes (model_id, kind, payload, summary, note, requested_by, requested_at, status, decided_by, decided_at,
                                  decision_note) VALUES
 ((SELECT id FROM core.models WHERE name = 'Fynbos Commercial'), 'settings',
  '{{"stale_days": 30, "cron": null, "weights": {{}}, "score_parts": null, "bands": null}}',
  'Stale after 30 days; schedule inherited; score weights inherited; colours inherited', 'Keep it fresh', 'user_model_admin',
  now() - interval '3 days', 'rejected', 'user_super_admin', now() - interval '2 days', 'A month is too short: everything would be stale');
INSERT INTO core.quality_scope (model_id, measured, set_by) VALUES
 ((SELECT id FROM core.models WHERE name = 'Sample insurance model'), false, 'user_super_admin'),
 ((SELECT id FROM core.models WHERE name = 'Karoo Audit 2025 (frozen)'), true, 'user_super_admin');
"""


def demo_estate_sql() -> str:
    """Laptop demo model "Protea Insurance (demo estate)" (phase 8.2, D161): a whole fictitious estate on
    ArchiMate 4, created from the template, so every view and report has data (eax.seed.demo_estate)."""
    k = DEMO.DEMO_KEY
    m = gid("model", k)
    dtype = {code: DATA_TYPES[dt] for code, _n, dt, *_ in A.ATTRS}
    ents, vals, parents, rels = [], [], [], []
    for type_code, name, desc, parent, attrs in DEMO.E:
        e = gid(k, "entity", name)
        ents.append([e, m, gid(k, "entity_type", type_code), name, desc])
        if parent:
            parents.append((e, gid(k, "entity", parent)))
        for attr, value in attrs.items():
            dt = dtype[attr]
            if dt == "date":
                value = date.fromisoformat(value)
            if dt == "url":
                value = entity_links(value, m, k)
            row = {"value_text": None, "value_number": None, "value_date": None}
            row[STORAGE[dt]] = value
            vals.append([gid(k, "attribute_value", name, attr), m, gid(k, "attribute_type", attr), e,
                         row["value_text"], row["value_number"], row["value_date"]])
    for src, kind, tgt in DEMO.R:
        rels.append([gid(k, "relationship", src, kind, tgt), m, gid(k, "relationship_type", kind),
                     gid(k, "entity", src), gid(k, "entity", tgt)])
    parent_sql = ("UPDATE core.entities c SET parent_entity_id = p.id\nFROM (VALUES\n"
                  + ",\n".join(f"    ('{c}'::uuid, '{p}'::uuid)" for c, p in parents)
                  + "\n) AS v (child, parent)\nJOIN core.entities p ON p.guid = v.parent\nWHERE c.guid = v.child;\n")
    cols = ["id", "origin_id", "name", "description", "kind_code", "source_model_id", "parent_model_id",
            "metamodel_name", "owner", "industry"]
    return "".join([
        "SELECT set_config('eax.history_label', 'Laptop demo estate (Protea Insurance)', true);\n",
        insert("model", cols, [[m, TEMPLATE_ID, DEMO.DEMO_NAME,
                                "Demo model: Protea Insurance, a fictitious South African insurer, with a whole estate on "
                                "ArchiMate 4 (motivation, strategy, business, application, technology, implementation and "
                                "migration) so every view and report has data. Every name is invented.",
                                "project", TEMPLATE_ID, None, "ArchiMate 4", "Protea architecture team", "Insurance"]]),
        metamodel_sql(k, TEMPLATE_KEY),
        insert("entity", ["id", "model_id", "entity_type_id", "name", "description"], ents),
        parent_sql,
        insert("attribute_value", ["id", "model_id", "attribute_type_id", "entity_id", "value_text", "value_number",
                                   "value_date"], vals),
        insert("relationship", ["id", "model_id", "relationship_type_id", "source_entity_id", "target_entity_id"], rels),
        "".join(f"UPDATE core.allowed_relationships SET source_multiplicity = {lit(sm)}, target_multiplicity = {lit(tm)} "
                f"WHERE guid = '{gid(k, 'allowed_relationship', s, r, t)}'::uuid;\n" for s, r, t, sm, tm in DEMO.MULTIPLICITY),
    ])


# Laptop only: rules about relationships and entities that break rules, in Karoo Re, so each entity's
# Rules tab and the Failing checks tab have something to show (D113). (type, name, description, values,
# relationships as (relationship type, other entity, outgoing?)); a key keeps two same-named entities apart.
RULE_DEMO_RULES = [
    # entity type, relationship type, other entity type, severity, message
    ("ApplicationComponent", "Association", "Capability", "warning", "An application supports at least one capability"),
    ("ApplicationComponent", "Serving", "", "warning", "An application serves someone or something"),
    ("Capability", "Association", "Application Component", "warning", "A capability is supported by at least one application"),
    ("Requirement", "Realization", "Goal", "error", "A requirement realises a goal"),
]
RULE_DEMO_ENTITIES = [
    ("legacy-sheet", "ApplicationComponent", "Legacy Claims Spreadsheet",
     "Rules demo: no owner, criticality out of range, a version that breaks its pattern, a document link that is only "
     "text (kept, shown as text: D418), a negative cost, "
     "retiring without a retirement date, and no relationships",
     {"Lifecycle": "Retiring", "Criticality": 7, "Version": "v2 beta", "AnnualCost": -500, "Url": "intranet/claims"}, []),
    ("broker-portal-1", "ApplicationComponent", "Broker Portal",
     "Rules demo: shares its name with another application, went live in 1985, retired before it went live, and supports "
     "no capability",
     {"Owner": "Broker Services", "Lifecycle": "Production", "Criticality": 3, "GoLiveDate": "1985-06-01",
      "RetirementDate": "1980-01-01"}, [("Serving", "Claims Department", True)]),
    ("broker-portal-2", "ApplicationComponent", "Broker Portal",
     "Rules demo: a second application with the same name; otherwise every rule passes",
     {"Owner": "Broker Services", "Lifecycle": "Phase In", "Criticality": 2, "Version": "0.9"},
     [("Serving", "Claims Department", True), ("Association", "Claims Management", True)]),
    ("fraud-detection", "Capability", "Fraud Detection",
     "Rules demo: a capability level out of range, and no application supports it", {"Owner": "COO", "CapabilityLevel": 6}, []),
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
    Root model (not ArchiMate): Lean EA metamodel 1.0, with five types in three domains, four relationship
    types and two attributes; and Karoo Digital, a project model created from it with a little content.
    The root is not locked: its Model Admin (user_model_creator on laptops) changes it."""
    k, p = LEAN_KEY, LEAN_PROJECT_KEY
    layers = [(d, A.DOMAIN_COLOURS[d].lower()) for d in ("Business", "Application", "Technology")]
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

    def project(key, name, description, owner):
        """A small project model on the Lean EA metamodel with the same seven entities and five relationships."""
        m = gid("model", key)
        return "".join([
            insert("model", cols, [[m, gid("model", k), name, description, "project", gid("model", k), "Lean EA metamodel 1.0",
                                    False, owner, "", "Reinsurance"]]),
            metamodel(key, k),
            insert("entity", ["id", "model_id", "entity_type_id", "name"], [[gid(key, "entity", n), m, gid(key, "entity_type", t), n] for t, n in ents]),
            insert("relationship", ["id", "model_id", "relationship_type_id", "source_entity_id", "target_entity_id"],
                   [[gid(key, "relationship", a, r, b), m, gid(key, "relationship_type", r), gid(key, "entity", a), gid(key, "entity", b)]
                    for a, r, b in links])])
    # one small model in each state (D242): what data quality measures, and what it leaves out, on Administration > Quality
    states = "".join(project(key, name, desc, "Karoo enterprise architecture") for key, name, desc, _ in STATE_MODELS)
    states += "".join(f"UPDATE core.models SET {upd} WHERE guid = '{gid('model', key)}'::uuid;\n" for key, _n, _d, upd in STATE_MODELS)
    return "".join([
        "SELECT set_config('eax.history_label', 'Laptop test models: a root metamodel from scratch', true);\n",
        insert("model", cols, [[gid("model", k), None, "Lean EA metamodel",
                                "Test model: an organisation's own root metamodel built from scratch (from the Root model, "
                                "not ArchiMate): five types in three domains. Its Model Admin changes it.",
                                "template", EMPTY_ID, "Lean EA metamodel 1.0", False, "Karoo enterprise architecture", "1.0", ""]]),
        metamodel(k, None),
        insert("model", cols, [[pm, gid("model", k), "Karoo Digital (lean)",
                                "Test model: a working model created from the Lean EA metamodel.",
                                "project", gid("model", k), "Lean EA metamodel 1.0", False, "Karoo digital team", "", "Reinsurance"]]),
        metamodel(p, k),
        insert("entity", ["id", "model_id", "entity_type_id", "name"], [[gid(p, "entity", n), pm, gid(p, "entity_type", t), n] for t, n in ents]),
        insert("relationship", ["id", "model_id", "relationship_type_id", "source_entity_id", "target_entity_id"],
               [[gid(p, "relationship", a, r, b), pm, gid(p, "relationship_type", r), gid(p, "entity", a), gid(p, "entity", b)] for a, r, b in links]),
        states,
    ])


def principles_sql() -> str:
    """root-principle-model (owner, 6 Nov 2026, D270, D271): a reference model created from ArchiMate 4 (so under Root and
    ArchiMate 4) whose metamodel holds principles only: the Principle type (from ArchiMate 4's), its statement,
    rationale, implications, category and source, and principles associated with principles. Its content: The Open
    Group's architecture principles (Y082), by name and category; the text is filled in on the platform. Projects take
    their principles from it (D270). Read-only, like the other built-in models."""
    k, o = PRINCIPLE_KEY, TEMPLATE_KEY
    m = gid("model", k)
    cats = [c for c, _n in PRINCIPLES]
    attrs = [("PrincipleStatement", "Statement", "long_text", None, "What the principle says, briefly and unambiguously"),
             ("PrincipleRationale", "Rationale", "long_text", None, "The business benefits of adhering to the principle"),
             ("PrincipleImplications", "Implications", "long_text", None, "What following the principle requires of the business and IT"),
             ("PrincipleCategory", "Category", "list", "PrincipleCategory", "Business, Data, Application, Technology or Governance"),
             ("PrincipleSource", "Source", "text", None, "Where the principle comes from")]
    ent, vals = [], []
    for cat, names in PRINCIPLES:
        for n in names:
            e = gid(k, "entity", n)
            ent.append([e, m, gid(k, "entity_type", "Principle"), n, ""])
            vals.append([gid(k, "attribute_value", n, "PrincipleCategory"), m, gid(k, "attribute_type", "PrincipleCategory"), e, cat])
            vals.append([gid(k, "attribute_value", n, "PrincipleSource"), m, gid(k, "attribute_type", "PrincipleSource"), e, PRINCIPLE_SOURCE])
    return "".join([
        "SELECT set_config('eax.history_label', 'root-principle-model: principles', true);\n",
        insert("model", ["id", "origin_id", "name", "description", "kind_code", "source_model_id", "metamodel_name", "is_locked",
                         "owner", "version_label"], [[
            m, TEMPLATE_ID, "root-principle-model",
            "The architecture principles every project starts from: a metamodel of principles only (statement, rationale, "
            "implications, category, source). Created from ArchiMate 4. Read-only: projects take their principles from it "
            "and add their own in their own models.",
            "reference", TEMPLATE_ID, "Principles 1.0", True, "EA Explorer", "1.0"]]),
        insert("layer", ["id", "origin_id", "model_id", "code", "name", "colour", "sort_order"],
               [[gid(k, "layer", "Motivation"), gid(o, "layer", "Motivation"), m, "motivation", "Motivation", A.DOMAIN_COLOURS["Motivation"], 10]]),
        insert("entity_type", ["id", "origin_id", "model_id", "layer_id", "code", "name", "aspect", "id_prefix", "table_name", "sort_order"],
               [[gid(k, "entity_type", "Principle"), gid(o, "entity_type", "Principle"), m, gid(k, "layer", "Motivation"), "Principle",
                 "Principle", "Motivation", "PRI", "principle", 10]]),
        insert("relationship_type", ["id", "origin_id", "model_id", "code", "name", "verb", "category", "is_directed", "sort_order"],
               [[gid(k, "relationship_type", "Association"), gid(o, "relationship_type", "Association"), m, "Association", "Association",
                 "associated with", "Dependency", False, 10]]),
        insert("pick_list", ["id", "origin_id", "model_id", "code", "name"],
               [[gid(k, "pick_list", "PrincipleCategory"), None, m, "PrincipleCategory", "Principle Category"]]),
        insert("pick_list_value", ["id", "origin_id", "model_id", "pick_list_id", "value", "sort_order"],
               [[gid(k, "pick_list_value", "PrincipleCategory", c), None, m, gid(k, "pick_list", "PrincipleCategory"), c, i * 10]
                for i, c in enumerate(cats, 1)]),
        insert("attribute_type", ["id", "origin_id", "model_id", "code", "name", "description", "data_type_code", "pick_list_id", "column_name"],
               [[gid(k, "attribute_type", c), None, m, c, n, d, dt, gid(k, "pick_list", pl) if pl else None, snake(c)]
                for c, n, dt, pl, d in attrs]),
        insert("item_attribute", ["id", "origin_id", "model_id", "attribute_type_id", "entity_type_id", "is_required", "section", "sort_order"],
               [[gid(k, "item_attribute", "Principle", c), None, m, gid(k, "attribute_type", c), gid(k, "entity_type", "Principle"),
                 False, "Principle", i * 10] for i, (c, *_r) in enumerate(attrs, 1)]),
        insert("allowed_relationship", ["id", "origin_id", "model_id", "relationship_type_id", "source_type_id", "target_type_id"],
               [[gid(k, "allowed_relationship", "Principle", "Association", "Principle"), None, m, gid(k, "relationship_type", "Association"),
                 gid(k, "entity_type", "Principle"), gid(k, "entity_type", "Principle")]]),
        insert("entity", ["id", "model_id", "entity_type_id", "name", "description"], ent),
        insert("attribute_value", ["id", "model_id", "attribute_type_id", "entity_id", "value_text"], vals),
    ])


def seed_sql(with_template: bool = True, with_sample: bool = True, with_insurance: bool = True,
             with_principles: bool = True, with_togaf10: bool = True, with_industries=False) -> str:
    """What to load, as one script (run in one transaction, by the installer's login eax_migrator,
    because templates and reference models are locked). The others need the template."""
    parts = ["SELECT set_config('eax.actor', 'system:seed', true);\n"]
    if with_template:
        parts += [
            "SELECT set_config('eax.history_label', 'Root model and ArchiMate 4 seed', true);\n",
            # the top of the model hierarchy (D81): every root metamodel is created from it
            insert("model", ["id", "name", "description", "kind_code", "metamodel_name", "is_locked", "owner"], [[
                EMPTY_ID, "Root",
                "The root of the model hierarchy: no domains, types or content. Every root metamodel (ArchiMate 4, "
                "ArchiMate 5 when it comes, an organisation's own) is created from it. Read-only.",
                "template", "None", True, "EA Explorer"]]),
            insert("model", ["id", "name", "description", "kind_code", "source_model_id", "metamodel_name", "is_locked",
                             "owner"], [[
                TEMPLATE_ID, "ArchiMate 4",
                "The ArchiMate 4 root metamodel: the 42 elements of the specification, 6 EA Explorer extensions for the "
                "business architecture artifacts (Value Stream Stage, Product Lifecycle Stage, Business Scenario, Control, "
                "Contract, Measure), 11 relationship types and the allowed relationships. Read-only; new models start from it.",
                "template", EMPTY_ID, "ArchiMate 4", True, "EA Explorer"]]),
            metamodel_sql(TEMPLATE_KEY, None),
        ]
    if with_principles:
        parts.append(principles_sql())
    if with_togaf10:                    # the TOGAF 10 content metamodel (phase 13.1, D303)
        parts.append(T10.sql(gid, insert, snake, EMPTY_ID))
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
    # the industry reference models (phase 39, D470): True for all, or a set of industry codes
    for code, name, version, description, mod in IND.MODELS:
        if with_industries is True or (with_industries and code in with_industries):
            key = IND.key(code)
            parts += [
                f"SELECT set_config('eax.history_label', '{name} reference model', true);\n",
                insert("model", ["id", "origin_id", "name", "description", "kind_code", "source_model_id",
                                 "metamodel_name", "is_locked", "owner", "industry", "version_label"], [[
                    gid("model", key), TEMPLATE_ID, f"{name} reference model", description,
                    "reference", TEMPLATE_ID, "ArchiMate 4", True, "EA Explorer", name, version]]),
                metamodel_sql(key, TEMPLATE_KEY),
                reference_content_sql(mod, key),
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
