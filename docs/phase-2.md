# Build phase 2: insurance reference model, locked models, library page and versions

Goal: show a locked insurance reference model in a library, prove nobody can change it, and give
the API and the database one version number. Version **0.2.0**.
Requirements: REF-001 to REF-004, REF-007, REF-016 (insurance reference model), MOD-004, MOD-008,
MM-023, MM-024, ADM-043 (versions), UI-017 to UI-019 (model screens). Decisions D43 to D50.

## Status: accepted on 4 November 2026 (0.2.0); 0.2.1 built, waiting for a look

## What phase 2 delivers

- **Insurance reference model 1.0** (Start > Model library, or *Library* in the top bar): a
  read-only model for a generic insurer (life, funeral and short-term) on ArchiMate 4, made generic
  from the Meridian Assurance Group repository in the TOGAF project. 715 entities: 556 capabilities
  in four levels (with their parents), 7 value streams, 20 business services, 22 processes, 12
  functions, 18 products, 24 business objects, 20 application services, 18 business actors and 18
  roles; 248 relationships, every one allowed by the ArchiMate 4 rules. Left out as company-specific:
  applications, organisation units, maturity scores, volumes, motivation, gaps and projects. Until
  the last build phase this is the only industry model (D43). Source data:
  `services/api/eax/seed/insurance.py`.
- **Locked models** (migration `0003_library`): templates and reference models cannot be changed by
  anyone, administrators and the `postgres` superuser included, whatever the route: screens, API,
  MCP, the SQL window or `psql`. The database refuses inserts, updates, deletes and truncates on
  their metamodel and content, and refuses unlocking them. Only the installer's database login,
  `eax_migrator`, may load or change them; the seed step uses it. A new version of a reference model
  is a new model beside the old one (the name is unique per version).
- **Model library page**: each reference model with its industry, version, description, counts by
  entity type and by relationship type, and *Open (read-only)*, *ER diagram* and *Copy this model*
  (copying arrives in build phase 4).
- **Model list** (*Models*): a table with search (name, description, owner, industry), a kind filter,
  archived models hidden unless asked, owner, status, counts and last change. **Model properties**
  on every model page: owner, active or archived, industry and version (reference models), created
  and changed by whom and when. Locked models show *Read-only reference model* (or template).
- **ER diagram as the metamodel graph** (D47): drag a box to move it (its lines redraw straight;
  *Reset layout* puts it back); save what you see as **SVG**, **PNG** or **.drawio**. The .drawio file
  opens in the hosted draw.io and the desktop app, one box per entity type tagged with `ea_type` and
  `ea_id`.
- **Versions** (D44): the API's version is in `services/api/version.toml`; the database's is the
  newest row of `core.schema_versions`, written by the migration that moves it. The heartbeat shows
  both and turns to **warning** when they differ; so does the Database line of the service health.
  Every phase moves both: phase N is 0.N.0.
- **Model screens for large models** (D50). Opening a model shows tabs:
  - **Entity types**: every type with its layer, entity and attribute counts; filter, sort, only
    types with entities. Click a type for **its entities as a table**: one column per attribute,
    required ones marked, missing required values shaded, rule results per row (errors and warnings,
    hover to read), search, filter by rule result, choose columns, sort, 100 per page, CSV of what
    you see. **+** on a row lists the entities related to it (relationship, direction, other entity,
    "not in metamodel" when no mapping allows it), its parent and its parts.
  - **Relationship types**: every type with how often the model uses it, how many type pairs the
    metamodel allows (the mappings) and how many uses fall outside them. Click one for its
    relationships (source, verb, target), with filter, paging and CSV.
  - **Graph**: entities and their relationships (and the parent hierarchy) drawn from the database.
    Choose entity types, or put one entity in the middle with 1 to 3 steps around it; click a box to
    move it to the middle, double-click to open it; switch line types on and off; drag, zoom, SVG
    and PNG.
  - **Metamodel** and **ER diagram** as before.
  - **Entity page**: *Details* (every field and attribute with its value, type and rule result, and
    a summary of errors and warnings), *Relations* (grouped by relationship type and direction,
    flagged when outside the metamodel, and what the metamodel allows for the type), *History* (every
    recorded change to the entity, its values and its relationships: when, who, old and new value)
    and *Graph* (its neighbourhood).
  - Validation rules (`eax/rules.py`) are checked when the screens open: required attributes,
    pick-list values, length, number ranges, patterns, date ranges and order, required-if and
    unique names. They warn, never block (D48).
  - Buttons for what comes later are shown switched off with their phase: + Entity, Edit values and
    + Relationship (phase 6, D48 and D49: a value that fails a rule is saved with an override flag and
    its details; a relationship outside the metamodel adds its type and mapping); + Entity type,
    + Attribute, + Relationship type, + Mapping and + Rule (phase 3). Reference models stay locked:
    those changes happen in a project model or a copy (phase 4).
- **API and MCP**: `GET /api/v1/models?search=&kind=&archived=`, `GET /api/v1/models/library`; model
  responses carry the new properties. For the model screens: `GET .../entity-types/<id>/table`,
  `.../relationship-types`, `.../relationships?type=`, `.../entities/<id>` (now with rule results,
  `allowed` per relationship and what the type may have), `.../entities/<id>/history` and
  `.../graph?focus=&depth=&type=&limit=`. MCP tools `list_library`, `list_relationship_types`,
  `check_entities`, `get_entity_history` and `get_neighbourhood` (fifteen tools now).
- **eax clean-run** and **eax clean-debug**: cleanup, init and up (or debug) in one command.

## Demo

1. `.\eax clean-run` (or `clean-debug`). The api log shows "loaded the ArchiMate 4 template,
   insurance reference model, sample model".
2. Heartbeat: API and database both **0.2.0**, status ok.
3. Start > **Model library**: the Insurance reference model 1.0, locked, 715 entities. *Open*: the
   lock badge and *Details*. *Entity types* > **Role**: the 18 roles as a table; **+** on Adviser
   lists its processes and the business actors assigned to it. *Entity types* > **Capability**: 556
   rows; filter *With errors or warnings*: 7 capabilities share a name with another (the unique
   rule). Open one: *Details*, *Relations*, *History*, *Graph*.
4. *Relationship types*: Serving used 70 times; open it. *Graph*: choose Role and Business Actor;
   type *Adviser* in the search box to put it in the middle, 2 steps out.
5. *ER diagram*: choose *Strategy*, then focus on **Capability**; drag a box; save **.drawio** and
   open it in the desktop draw.io (File > Open).
6. SQL window as `postgres`, tick *Allow changes*, and try:
   ```sql
   UPDATE core.entities SET name = 'Changed'
    WHERE model_id = (SELECT id FROM core.models WHERE name = 'Insurance reference model');
   ```
   Refused: *Model "Insurance reference model" is locked (read-only)*. The same for deleting the
   model, unlocking it or `TRUNCATE`.
7. MCP (Claude Code): "What is in the EA Explorer model library?", then "List the level 1
   capabilities of the insurance reference model".

## Checks

- `tests/sql/phase2_checks.sql` (as `postgres`): version 0.2.0, the insurance model's shape, and every
  route of change refused, `SET ROLE eax_migrator` included. Ends with "phase 2 checks passed".
- `tests/sql/phase2_installer_check.sql` (as `eax_migrator`): the installer may change a locked
  model. Both run in a rolled-back transaction.
- `tests/sql/phase1_checks.sql` still passes.
- `pytest services/api/tests/test_seed.py test_versioning.py test_rules.py`: the insurance model's
  relationships are allowed and its parents exist; the version file and the newest migration agree;
  each validation rule type reports what it should.
  ```powershell
  Get-Content services/api/tests/sql/phase2_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U postgres -d eaexplorer -v ON_ERROR_STOP=1
  ```

## Upgrading from phase 1

`.\eax clean-run`. There is a new setting (`EAX_DB_MIGRATOR_PASSWORD`) and a new database login,
created only when the database is first made, so a clean rebuild is required.

## Version 0.2.1: the rest of phase 2 (D54)

Added after acceptance, read only, no schema change (migration `0004_screens` only records the
version, so API and database stay in step).

- **Graph tab, five kinds of picture:**
  - **Network:** chosen entity types, or one entity in the middle.
  - **Layered:** bands by ArchiMate layer.
  - **Impact chain:** from one entity, follow the lines *out* (impact) or *in* (dependencies), up to 6
    steps, in columns by distance; only the relationship types switched on are followed.
  - **Hierarchy map:** nested parents and parts (the capability map), coloured by any attribute as a
    heat map.
  - **Matrix:** one entity type against another.
- **draw.io everywhere:** every picture saves as `.drawio` (boxes tagged `ea_type`, `ea_id`; nesting
  kept), and as SVG, PNG and CSV.
- **Click to open:** clicking a box (or a matrix row or column) opens the entity page. In the network
  you can choose *put it in the middle* instead.
- **Entity timeline** (History tab):
  - a timeline of moments (who, when, what);
  - click one to see every field, value and relationship as it was then, beside now (differences
    shaded, relationships removed or added since marked);
  - *Earlier*, *Later* and *Current* buttons;
  - *Roll back to this point* shown switched off until phase 6.
  - API: `GET .../entities/<id>/as-of?event=` or `?at=`; MCP tool `get_entity_as_of`.
- **Entity page, Graph tab, seven pictures of one entity:**
  - *Neighbourhood:* rings, 1 to 3 steps out.
  - *Both ways:* dependencies on the left, impact on the right.
  - *One way:* out or in, up to 6 steps.
  - *Family tree:* every parent up to the top, parts down 1 to 10 levels.
  - *By layer:* its neighbours in ArchiMate layer bands.
  - *Path to...:* the shortest chains to another entity you pick.
  - *As it was:* its relationships at a moment of its history, removed since in red, added since in
    green.
  - Each saves as .drawio, SVG, PNG and CSV. API: `.../graph?direction=split|tree`,
    `.../entities/<id>/paths?to=`. MCP tools `find_paths` and `get_family_tree`.
- **Model and lineage** on the entity page:
  - the model it is part of;
  - what the model was created from and merges into;
  - the entity it was copied from (and copies made of it);
  - the template type its type came from. All are links.
- **CSV on every page:** models, entity types, entities of a type, relationship types, relationships,
  entity details, relations, history, an entity as it was, every picture and a type's definition.
- **Current model, top right on every screen**, with a drop-down to change model. Changing model keeps the
  view you are on (entity types, relationship types, graph, metamodel, ER diagram). Away from the model
  pages it shows the last model you opened. From phase 3.1 it lists only the models you may open.
- **Library:** an *industry pack* section per reference model (guidance, workbooks, reports, diagrams,
  regulation, getting started). It's filled in phase 39, with the documents stored in Mayan (D51).

### Try it

1. `.\eax clean-run`. The heartbeat shows API and database **0.2.1**.
2. Give the sample model some history to play with (it changes the *Sample insurance model* only;
   a clean rebuild puts it back):
   ```powershell
   Get-Content services/api/tests/sql/sample_history.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U postgres -d eaexplorer -v ON_ERROR_STOP=1
   ```
3. *Models > Sample insurance model > Claims Platform > History*.
   - Click the moment before *Criticality 5 → 9*: criticality shows 5 then, 9 now.
   - Click the moment when Thandi removed the link: *Claims Department* is missing then and listed
     as *added since* (Pieter put it back).
   - *Details* shows the criticality error, saved anyway.
4. *Library > Insurance reference model > Graph*:
   - **Impact chain** from Adviser: 3 steps out reaches capabilities. Save **.drawio** and open it in
     draw.io desktop.
   - **Hierarchy map:** the capability map at 3 levels.
   - **Matrix:** Process by Role.
   - Click any box to open its page.
5. Open **Adviser** > *Graph*: try *Both ways*, *Path to...* Quotation (3 steps: assigned to, realizes,
   realizes) and *By layer*. Open **Market Intelligence** > *Family tree*. Open **Claims Platform** (sample
   model) > *Graph* > *As it was* and pick a moment before Pieter's last change: the link to Claims
   Department shows as added since.

## Not in phase 2

Copying a model (phase 4). Editing the metamodel: entity types, attributes, relationship types,
mappings and rules (phase 3). Entering and changing values and relationships, with override flags
and relationships outside the metamodel (phase 6). The other industry models, the cross-industry model, industry reports,
guidance and workbooks come in the last phase (39) with the product documentation (D43, D45).
