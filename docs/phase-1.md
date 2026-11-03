# Build phase 1: metamodel store and the ArchiMate 4 seed (read only)

Goal: see the initial metamodel in the browser before any data can be entered.
Requirements: MM-003 (layers), MM-004 (attribute data types), MM-011 (ArchiMate 4 starter
metamodel), REP-017 (typed storage of attribute values), UI-002 (browse by layer and type).

## What phase 1 delivers

- **The repository database** (migration `0002_metamodel`): models, metamodel and generic content
  tables, integrity rules, housekeeping columns and history on every table. See
  [database.md](database.md) for the design and the diagram.
- **`eax.get_entity` and `eax.get_entity_by_name`**: one table per entity type, built on demand
  from the current metamodel, plus each entity's relationships; join them in plain SQL.
- **The ArchiMate 4 starter metamodel**, loaded on first start from the EA Workbench 1.1 seed:
  7 layers, 42 element types, 11 relationship types, 3,072 allowed relationships (derived from the
  ArchiMate generic metamodel; to be checked against the specification's tables), 22 attributes,
  9 pick lists and 13 validation rules. It is a read-only **template** model.
- **A sample insurance model** (laptop only, `EAX_SEED_SAMPLE=true`): a project model with its own
  copy of the metamodel and 14 entities, 12 relationships and 58 attribute values.
- **Read-only API**, in Swagger under *metamodel*: `GET /api/v1/models`, `/models/{guid}`,
  `/models/{guid}/metamodel`, `/models/{guid}/entity-types/{guid}`, `/models/{guid}/entity-list`,
  `/models/{guid}/entities/{guid}`, `/models/{guid}/relationships`,
  `/models/{guid}/entities?type=...&name=...` (eax.get_entity).
- **Model pages** (start page, *Metamodel* tile, or *Models* in the top bar): every model as a link.
  A model opens on **Entities and relationships** (entities grouped by type, filter, each entity with
  its attribute values and linked relationships, and a list of all relationships) and has a
  **Metamodel** tab (layers, types, attributes, rules, allowed relationships).
- **MCP server** for your own language model (start page, *MCP server*): nine read-only tools over
  the same code as the REST API. See [mcp.md](mcp.md). It gains tools in every build phase.

## Demo

1. `.\eax up` (the API applies migration 0002 and loads the seed on its first start; the API log
   shows "loaded the ArchiMate 4 template and sample model").
2. Start page → **Metamodel**. Choose *ArchiMate 4 (Template, read-only)*: seven coloured layers and
   42 types. Open **Application Component**: 13 attributes, rules, and allowed relationships.
3. Choose *Sample insurance model*, open **Application Component**, press **Show Application
   Component entities**: three applications with their attributes and relationships.
4. SQL (the database is not exposed; use the container):
   ```powershell
   docker compose --env-file work/eaexplorer.env exec db psql -U postgres -d eaexplorer
   ```
   ```sql
   SELECT eax.get_entity('Application Component');
   SELECT display_id, name, lifecycle, hosting, annual_cost FROM tmp_application_component;
   SELECT * FROM tmp_application_component_rel;
   ```
5. MCP: connect Claude Code or Claude Desktop with the settings on the *MCP server* page and ask
   "Which applications realise the Claims Management capability in the sample insurance model?"
6. Nothing can be edited: there are no write calls and no edit screens yet.

## Checks

- `python -m pytest services/api/tests/test_seed.py`: the seed is consistent (every sample
  relationship is allowed, every sample attribute applies to its type, names are unique).
- `tests/sql/phase1_checks.sql`: run inside the db container after the first start:
  ```powershell
  Get-Content services/api/tests/sql/phase1_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U postgres -d eaexplorer -v ON_ERROR_STOP=1
  ```
  It ends with "phase 1 checks passed" and changes nothing.

## Upgrading a phase 0 installation

No reset is needed: on the next `.\eax up` the API applies migration 0002 and loads the seed.
The cache container is now **`dms-broker`** (used by Mayan only) and its settings are renamed
(`EAX_DMS_BROKER_PASSWORD`, `EAX_DMS_BROKER_PASSWORD_URLENC`); a new setting `EAX_SEED_SAMPLE` loads
the sample model. Easiest: delete `work\eaexplorer.env` and run `.\eax init laptop` (your data in
the Docker volumes stays).

## Not in phase 1

Editing and publishing the metamodel (phase 3), copying models and model roles (phase 4), report
views for Superset (phase 5), data entry (phase 6).
