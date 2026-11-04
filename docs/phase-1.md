# Build phase 1: metamodel store and the ArchiMate 4 seed (read only)

Goal: see the initial metamodel in the browser before any data can be entered.
Requirements: MM-003 (layers), MM-004 (attribute data types), MM-011 (ArchiMate 4 starter
metamodel), REP-017 (typed storage of attribute values), UI-002 (browse by layer and type).

## What phase 1 delivers

- **The repository database** (migration `0002_metamodel`): models, metamodel and generic content
  tables, integrity rules, housekeeping columns and history on every table. See
  [database.md](database.md) for the design and the diagram.
- **`eax.get_entity` and `eax.get_entity_by_name`**: one table per entity type, built on demand
  from the current metamodel, plus each entity's relationships, under a table name the caller
  always gives (a used name is refused); join them in plain SQL. The tables are dropped when the
  connection closes; `eax.drop_entity(name)` drops them sooner.
- **The ArchiMate 4 starter metamodel**, loaded on first start from the EA Workbench 1.1 seed:
  7 layers, 42 element types, 11 relationship types, 3,072 allowed relationships (derived from the
  ArchiMate generic metamodel; to be checked against the specification's tables), 22 attributes,
  9 pick lists and 13 validation rules. It is a read-only **template** model.
- **A sample insurance model** (laptop only, `EAX_SEED_SAMPLE=true`): a project model with its own
  copy of the metamodel and 14 entities, 12 relationships and 58 attribute values.
- **Read-only API**, in Swagger under *metamodel*: `GET /api/v1/models`, `/models/{guid}`,
  `/models/{guid}/metamodel`, `/models/{guid}/entity-types/{guid}`, `/models/{guid}/entity-list`,
  `/models/{guid}/entities/{guid}`, `/models/{guid}/relationships`,
  `/models/{guid}/entities?type=...&name=...` (eax.get_entity), `/models/{guid}/metamodel/diagram`
  (data for the ER diagram) and `/models/{guid}/metamodel/mermaid?layer=...&type=...` (Mermaid text).
- **Model pages** (start page, *Metamodel* tile, or *Models* in the top bar): every model as a link.
  A model opens on **Entities and relationships** (entities grouped by type, filter, each entity with
  its attribute values and linked relationships, and a list of all relationships) and has a
  **Metamodel** tab (layers, types, attributes, rules, allowed relationships).
- **ER diagram** tab: the metamodel drawn as an entity-relationship diagram, generated from the
  database each time it opens, so it follows every change to the metamodel. Boxes are entity types
  with their attributes (required ones marked *), lines are the allowed relationships per source and
  target type, labelled and coloured by relationship type. Show one or more layers (optionally with
  the types they connect to), or focus on one type and every type it may connect to; switch
  relationship types on and off (Association and Specialization are off at first); hover a box to
  highlight its lines; drag, scroll to zoom, *Fit*. *Download SVG* saves the picture; *Copy as
  Mermaid* copies the same diagram as Mermaid text for GitHub, Confluence or draw.io. Layout by ELK
  (elkjs) in a web worker: right-angled lines for normal diagrams, a ring for a focused type or a
  dense layer, straight lines when very large.
- **SQL window** (start page, *SQL*, or *SQL* in the top bar; system administrators only): a
  diagram of the tables and the columns that join them (click for full size), one box to write SQL, *Run* (or Ctrl+Enter; a selection runs on its own), and the results as tables. Sign
  in with a PostgreSQL login (laptop: `eax_app` or `postgres`, password `P^55w0rd1234&`). Each run is
  one transaction, rolled back at the end unless *Allow changes* is ticked; temporary tables from
  `eax.get_entity` last for that run. At most 1,000 rows per result, 30-second limit, every run in
  the audit log. Also in Swagger as `POST /api/v1/sql/query`. On by default on laptops, off on
  servers (`EAX_SQL_CONSOLE_ENABLED`).
- **Service health** (Heartbeat screen, *Services*; `GET /api/v1/heartbeat/services`, signed in):
  checks every service at once from inside the stack: API, database, job runner, Keycloak, web
  screens, proxy, Superset, Mayan EDMS and its queue (Valkey), draw.io, MCP server and the age of
  the newest backup. Each is up, warning, down or off, with a detail and response time.
  `docker compose --env-file work/eaexplorer.env exec api python -m eax.health` prints the same.
- **MCP server** for your own language model (start page, *MCP server*): ten read-only tools over
  the same code as the REST API. See [mcp.md](mcp.md). It gains tools in every build phase.

## Demo

1. `.\eax up` (the API applies migration 0002 and loads the seed on its first start; the API log
   shows "loaded the ArchiMate 4 template and sample model").
2. Start page → **Metamodel**. Choose *ArchiMate 4 (Template, read-only)*: seven coloured layers and
   42 types. Open **Application Component**: 13 attributes, rules, and allowed relationships.
3. Choose *Sample insurance model*, open **Application Component**, press **Show Application
   Component entities**: three applications with their attributes and relationships.
4. **ER diagram** tab: the Business layer with its attributes and relationships. Click
   *Motivation*, then *All*; choose *Application Component* under *Focus on* (or click its box):
   the type in the middle with the 37 types it may connect to. Hover a box, then *Download SVG*
   and *Copy as Mermaid* (paste into https://mermaid.live).
5. SQL: start page → **SQL**, password `P^55w0rd1234&`, then run (or use `psql` in the container:
   `docker compose --env-file work/eaexplorer.env exec db psql -U postgres -d eaexplorer`):
   ```sql
   SELECT eax.get_entity('Application Component', 'apps');
   SELECT display_id, name, lifecycle, hosting, annual_cost FROM apps;
   SELECT * FROM apps_rel;
   ```
   Then a real-world join of three entity types through their relationships (two rows in the
   sample model: Claims Management and Policy Management with their applications and data):
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
6. MCP: connect Claude Code or Claude Desktop with the settings on the *MCP server* page and ask
   "Which applications realise the Claims Management capability in the sample insurance model?",
   then "Draw the ArchiMate 4 metamodel around Application Component as an ER diagram".
7. Nothing can be edited: there are no write calls and no edit screens yet.

## Checks

- `python -m pytest services/api/tests/test_seed.py`: the seed is consistent (every sample
  relationship is allowed, every sample attribute applies to its type, names are unique).
- `python -m pytest services/api/tests/test_diagram.py`: the ER diagram rules (layers, connected
  types, focus, relationship types) and the Mermaid text.
- `tests/sql/phase1_checks.sql`: run inside the db container after the first start:
  ```powershell
  Get-Content services/api/tests/sql/phase1_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U postgres -d eaexplorer -v ON_ERROR_STOP=1
  ```
  It ends with "phase 1 checks passed" and changes nothing.

Table names are plural (`core.models`, `core.entities`, `core.relationships`, ...); see
[database.md](database.md).

## Upgrading from an earlier build

Always rebuild from clean; never patch an old settings file. Settings are added or renamed between
builds (in this one `EAX_MCP_ENABLED`, `EAX_MCP_DEV_TOKEN`, `EAX_SEED_SAMPLE`, `EAX_DMS_BROKER_*`,
and the mail settings removed), and Keycloak reads its realm only on the very first start.

```powershell
.\eax cleanup --all --yes
.\eax init laptop
.\eax debug
```

`cleanup --all` removes the containers (also ones no longer in the stack), the Docker volumes and
everything in `work\`, so the databases start empty and the seed loads again.

## Not in phase 1

The interactive metamodel graph with its .drawio export (MM-023, MM-024) follows in phase 2; the ER
diagram (MM-025) is in phase 1.
Editing and publishing the metamodel (phase 3), copying models and model roles (phase 4), report
views for Superset (phase 5), data entry (phase 6).
