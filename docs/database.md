# The repository database

![Phase 1 database](images/database-phase1.png)

(Diagram source: `images/database-phase1.mmd`, a Mermaid ER diagram. The SQL is
`services/api/migrations/sql/0002_metamodel.sql`.)

## The idea

The repository is **generic**: one table for entities, one for relationships and one for attribute
values, described by a **metamodel** held in ordinary rows. A new entity type, attribute or
relationship rule is a new row, never a database change. `eax.get_entity` turns the generic rows
back into one ordinary table per type whenever you need it.

The design brings together the original EA-Metamodel-Explorer database diagram and the phase 1
proposal, and goes further than both:

| Taken from the original diagram | Taken from the proposal | Added |
| --- | --- | --- |
| Model kinds (template, project, branch) and a parent model | Generic content with typed value columns (text, number, date, yes/no, link) | Reference models as a kind, and a lock flag for read-only models |
| One status on every item (created, under review, published, retired) | `get_entity` / `get_entity_by_name` and SQL joins between types | Integrity rules enforced by the database (see below) |
| Attribute types defined once and mapped to types (`item_attribute`) | Relationship attributes | Display IDs (APP-0012) numbered per model and type |
| Validation rules | Pick lists | One append-only history table for every table, with labels |
| Parent entity (hierarchies) | GUIDs for copy and merge | bigint keys for speed, guid for identity |
| Created/modified by and when, soft delete, history | | Data types with a storage kind and SQL type |

The original's `Attributes_Pointer` (sharing one value between models) is not used: copies keep
their lineage through `origin_guid` instead, which covers deep copy and merge back without values
changing in two models at once.

## Keys

| Column | On | What it is |
| --- | --- | --- |
| `id` | every table | bigint, the primary key. Every foreign key and join uses it. Internal only. |
| `guid` | every table | uuid, unique and never reused. The API, URLs, exchange files, deep copy and merge back use it. |
| `origin_guid` | every table | the guid of the row this one was copied from (empty for originals). |

## Housekeeping on every table

`status_code` (workflow status), `is_deleted` (soft delete), `created_at` / `created_by`,
`modified_at` / `modified_by` and `row_version` are kept by trigger. The acting user comes from the
setting `eax.actor`, which the API sets for each request.

Every insert, update and delete is copied to **`history.row_versions`**: the table, the row's id and
guid, its model, the version number, the operation and the whole row as JSON. A label (for
example a baseline or import name) is taken from the setting `eax.history_label`. History is
append-only: updates and deletes are refused.

## Models own their metamodel

A **model** holds its own metamodel (layers, entity types, relationship types, attribute types,
pick lists, validation rules, allowed relationships) and its content. Kinds:

| Kind | Content | Read-only | Use |
| --- | --- | --- | --- |
| template | no | yes | a metamodel to start new models from (ArchiMate 4) |
| reference | yes | yes | industry and high-level reference models |
| project | yes | no | a working model |
| branch | yes | no | a work copy that merges back to its parent |

Creating a model from a template copies the metamodel rows; every copy points back through
`origin_guid`. The seed does exactly this for the sample model.

## Integrity enforced by the database

Whatever writes to the database (API, CSV loads, diagram harvest, MCP, plain SQL), these hold:

- A template cannot hold entities.
- An entity's type, parent, relationships and attribute values are all in the same model.
- A relationship must be allowed by the metamodel for its source and target types
  (`allowed_relationship`). Example refusal: *The metamodel does not allow Serving from Data Object
  to Goal*.
- An attribute value must belong to an attribute mapped to the owner's type, sit in the column for
  its data type, be a whole number for whole-number attributes, come from the pick list for list
  attributes, and link only to entities in the same model.
- Display IDs are numbered per model and type (`APP-0001`, `APP-0002`, ...) when not given.

Validation rules (`validation_rule`: mandatory, ranges, patterns, date order...) are stored now and
applied by the API and the publishing workflow in later phases, because they can be warnings and can
depend on other fields.

## get_entity

```sql
SELECT eax.get_entity('Application Component');            -- every model you may read
SELECT eax.get_entity('Application Component', '<model guid>');
SELECT eax.get_entity_by_name('Capability', 'Claims Management');
SELECT eax.get_entity('application_component', NULL, false, 'apps');  -- no relationships, own name
```

Each call returns the names of the temporary tables it built:

- **`tmp_<type>`**: one row per entity: `id`, `guid`, model, `display_id`, `name`, `description`,
  parent, `status`, then one column per attribute of the type, typed by its data type (a link to
  another entity gives its name, plus `<column>_id`), then the housekeeping columns.
- **`tmp_<type>_rel`**: one row per relationship end: the entity, relationship type and verb,
  `direction` (outgoing or incoming), the other entity (id, guid, type, display ID, name) and the
  relationship's attributes as JSON.

The type can be given by name (`Application Component`), code (`ApplicationComponent`) or table name
(`application_component`), in any case. The tables are private to your session and replaced by the
next call for the same type; give a table name to keep several. Two calls join like ordinary tables:

```sql
SELECT eax.get_entity('Application Component');
SELECT eax.get_entity('Capability', NULL, false);
SELECT a.name AS application, r.relationship_type, c.name AS capability, c.maturity
  FROM tmp_application_component a
  JOIN tmp_application_component_rel r ON r.entity_id = a.id AND r.direction = 'outgoing'
  JOIN tmp_capability c ON c.id = r.other_entity_id;
```

Only models the caller may read are included (`core.can_read_model`, which model roles replace in
build phase 4). Reporting tools use persistent views in the `rpt` schema instead (build phase 5),
because they cannot see another session's temporary tables.

## Checks

`services/api/tests/sql/phase1_checks.sql` checks the seed, `get_entity`, display IDs, history and
every integrity rule against a real PostgreSQL, inside a transaction that is rolled back.
