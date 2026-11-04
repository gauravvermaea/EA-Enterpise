# The repository database

![Phase 1 database](images/database-phase1.png)

(Diagram source: `images/database-phase1.mmd`, a Mermaid ER diagram. The SQL is
`services/api/migrations/sql/0002_metamodel.sql`.)

Table names are plural (`core.models`, `core.entities`, `core.relationships`...); columns that
point at another table are singular with `_id` (`model_id`, `entity_type_id`).

### Tables and how they join

![Tables and joins](images/db-tables.png)

The same picture is on the SQL window. It is generated from the database's own catalog:
`python docs/images/db-tables-generate.py` (see the script for the two `mmdc` commands that
render it), after any migration that adds or renames tables.

## Where the database scripts are

Everything that creates the database is code in this repository; nothing is created by hand.

| File | What it creates |
| --- | --- |
| `deploy/postgres/initdb/01-databases.sh` | The four databases and their logins (first start of the db container only) |
| `services/api/migrations/versions/0001_foundation.py` | Schemas, the audit log, the staging tables, the heartbeat table and report view |
| `services/api/migrations/sql/0002_metamodel.sql` | Models, metamodel and content tables, integrity rules, history |
| `services/api/migrations/sql/0002_functions.sql` | `eax.get_entity`, `eax.get_entity_by_name`, `eax.drop_entity` |
| `services/api/migrations/versions/0002_metamodel.py` | Runs the two SQL files above (and drops them on downgrade) |
| `services/api/eax/jobs_schema.py` | The job queue tables (Procrastinate) |
| `services/api/eax/seed/` | The ArchiMate 4 template and the sample model (rows, not structure) |
| `services/api/tests/sql/phase1_checks.sql` | Checks for all of it, in a transaction that is rolled back |

The api container runs them in that order on every start (`entrypoint.sh`: `alembic upgrade
head`, the job tables, then the seed); each step only does what is not done yet. Each later build
phase adds its own numbered migration (`0003_...`) rather than editing an earlier one once that
phase is accepted.

## The idea

The repository is **generic**: one table for entities, one for relationships and one for attribute
values, described by a **metamodel** held in ordinary rows. A new entity type, attribute or
relationship rule is a new row, never a database change. `eax.get_entity` turns the generic rows
back into one ordinary table per type whenever you need it.

The design brings together the original EA-Metamodel-Explorer database diagram and the phase 1
proposal, and goes further than both:

| Taken from the original diagram | Taken from the proposal | Added |
| --- | --- | --- |
| Model kinds (template, project) and a parent model | Generic content with typed value columns (text, number, date, yes/no, link) | Reference models as a kind, and a lock flag for read-only models |
| One status on every item (created, under review, published, retired) | `get_entity` / `get_entity_by_name` and SQL joins between types | Integrity rules enforced by the database (see below) |
| Attribute types defined once and mapped to types (`item_attributes`) | Relationship attributes | Display IDs (APP-0012) numbered per model and type |
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

**Models form a hierarchy of any depth**, and a work copy is not a separate kind: it is a project
model with a parent. Two links on every model:

- **`parent_model_id`**: the model it merges back into. Empty for a top-level model. A copy of a
  copy of a copy is fine; each level merges into the one above it. The parent must be a working
  model (never a template or reference model), and a model can never end up under itself.
- **`source_model_id`**: the model it was created or copied from (lineage only). This can be a
  template or reference model, which can never be a parent.

A work copy usually has the same model as parent and source. Creating a model from a template copies
the metamodel rows; every copy points back through `origin_guid`. The seed does exactly this for
the sample model: its source is the ArchiMate 4 template and it has no parent.

## Integrity enforced by the database

Whatever writes to the database (API, CSV loads, diagram harvest, MCP, plain SQL), these hold:

- A template cannot hold entities.
- An entity's type, parent, relationships and attribute values are all in the same model.
- A relationship must be allowed by the metamodel for its source and target types
  (`allowed_relationships`). Example refusal: *The metamodel does not allow Serving from Data Object
  to Goal*.
- An attribute value must belong to an attribute mapped to the owner's type, sit in the column for
  its data type, be a whole number for whole-number attributes, come from the pick list for list
  attributes, and link only to entities in the same model.
- Display IDs are numbered per model and type (`APP-0001`, `APP-0002`, ...) when not given.

Validation rules (`validation_rules`: mandatory, ranges, patterns, date order...) are stored now and
applied by the API and the publishing workflow in later phases, because they can be warnings and can
depend on other fields.

## get_entity

You always name the tables; the relationship table gets `_rel` added:

```sql
SELECT eax.get_entity('Application Component', 'apps');                  -- every model you may read
SELECT eax.get_entity('Application Component', 'apps2', '<model guid>'); -- one model
SELECT eax.get_entity_by_name('Capability', 'Claims Management', 'cap');
SELECT eax.get_entity('Capability', 'caps', p_with_relationships => false);
SELECT eax.drop_entity('apps');                                           -- drop apps and apps_rel
```

Each call returns the names of the temporary tables it built:

- **`<name>`**: one row per entity: `id`, `guid`, model, `display_id`, `name`, `description`,
  parent, `status`, then one column per attribute of the type, typed by its data type (a link to
  another entity gives its name, plus `<column>_id`), then the housekeeping columns.
- **`<name>_rel`**: one row per relationship end: the entity, relationship type and verb,
  `direction` (outgoing or incoming), the other entity (id, guid, type, display ID, name) and the
  relationship's attributes as JSON.

Names are lower-case letters, digits and underscores (at most 59 characters). A name already used
in the session is refused, never replaced, so two calls cannot overwrite each other; our code uses
a fresh guid-based name for every call (`e_` + 32 hex digits). The tables are temporary: private to
the session and dropped by PostgreSQL when the connection closes. The API drops them itself before
returning, and its connection pool runs `DISCARD TEMP` whenever a connection goes back, so none
outlive the request.

The type can be given by name (`Application Component`), code (`ApplicationComponent`) or table name
(`application_component`), in any case. Two or more calls join like ordinary tables, through the
relationship table:

```sql
SELECT eax.get_entity('Application Component', 'apps');
SELECT eax.get_entity('Capability', 'caps', p_with_relationships => false);
SELECT eax.get_entity('Data Object', 'data', p_with_relationships => false);

-- each capability, the applications that realise it, their cost and the data they use
SELECT c.name AS capability, a.name AS application, a.lifecycle, a.hosting, a.annual_cost,
       string_agg(d.name, ', ' ORDER BY d.name) AS data_used
  FROM caps c
  JOIN apps_rel rc ON rc.other_entity_id = c.id AND rc.direction = 'outgoing'
                  AND rc.relationship_type = 'Realization'
  JOIN apps a      ON a.id = rc.entity_id
  LEFT JOIN apps_rel rd ON rd.entity_id = a.id AND rd.direction = 'outgoing'
                       AND rd.relationship_type = 'Access'
  LEFT JOIN data d      ON d.id = rd.other_entity_id
 GROUP BY c.name, a.name, a.lifecycle, a.hosting, a.annual_cost
 ORDER BY c.name, a.name;
```

Only models the caller may read are included (`core.can_read_model`, which model roles replace in
build phase 4). Reporting tools use persistent views in the `rpt` schema instead (build phase 5),
because they cannot see another session's temporary tables.

## Checks

`services/api/tests/sql/phase1_checks.sql` checks the seed, `get_entity`, display IDs, history and
every integrity rule against a real PostgreSQL, inside a transaction that is rolled back.
