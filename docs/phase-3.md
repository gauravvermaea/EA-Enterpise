# Build phase 3: metamodel editing, metamodel versions and history, failing checks, model locks

Goal: let a project model's metamodel be changed from the screens without ever blocking on the
content already in it, keep every change as a numbered version with its history, show every entity
that fails a check, and let a model be locked. Version **0.3.0**, migration `0005_metamodel_editing`.
Decisions D64, D65, D67, D52, D72 to D76 and D87.

## Status: built, waiting for Gaurav's test

## What phase 3 delivers

- **Metamodel editor** (Metamodel tab of a project model; the *+* buttons on the Entity types and
  Relationship types tabs open the same dialogs). Every dialog has **Check impact** (what the change
  would do, nothing saved) and **Save**:
  - entity types: add, change (name, layer, display-ID prefix, aspect, description), retire, restore.
    A retired type is no longer offered for new entities and its entities become read-only (enforced by
    the database) until it is restored (D87);
  - attributes on an entity type: add, change, remove. Every data type, a new or an existing pick
    list, unit, section on the form, help text, a **default value** and mandatory. **+ Lifecycle**
    adds a phase list and a date per phase in its own section;
  - pick lists: add a list, add a value, retire a value (Metamodel > Pick lists);
  - relationship types: add, change, remove, restore;
  - mappings (which relationship type may join which source and target type): add, remove;
  - validation rules: add, change, remove; on one type or on every type. Each rule asks for its own
    kind of parameter: a **regular expression** with a live validity check, ready-made patterns and a
    box to try a value; **date pickers** for date ranges; numbers; and a choice of attribute for
    "required if" and "date order". The server refuses a pattern that does not compile, a date that
    is not a date or a range the wrong way round.
  - default values use the attribute's own input: a **date picker** for dates, a number box, yes or
    no, or the pick list's values.
- **Never blocked (D64).** A mandatory attribute added to a type that already has entities asks for
  a default (empty allowed) and whether to put it on the existing entities that have no value. The
  impact check lists the entities that will fail, or pass, because of a change; it informs and never
  stops the save.
- **Removing is real (D75).** Removing an attribute removes its value from every entity (or
  relationship) of the type. Removing a relationship type removes every relationship of that type
  from the model. Each removed value and relationship stays in the history: the entity's timeline
  shows it, and *as it was* and rollback (0.2.1) still work. The dialog says how many before you save.
  Removing a mapping keeps the relationships, which then show as outside the metamodel.
- **One change, one version (D72).** Each saved change publishes the next metamodel version at once,
  with a note saying what it was ("Added attribute Service Owner (mandatory) to Service"). There are
  no drafts.
- **Metamodel history and versions (D65)** (Metamodel > History and versions): every version with
  who, when, and each change with old and new values; **Compare** any two versions (CSV). The model
  header shows the current version.
- **Entities know their metamodel version.** Each entity records the version it was created in and
  last changed in (entity page; *Metamodel v* column in the type tables; filter on the failing-checks
  screen).
- **Failing checks** tab: every entity failing a rule, a mandatory value or a relationship outside the
  metamodel; filters by entity type, rule, severity, metamodel version and text; links to each entity;
  CSV. Fixing values on screen arrives with data entry (build phase 6).
- **Model locks (D67)** (*Lock...* beside the model name; a banner while locked):
  - *Metamodel lock*: the metamodel is read-only; content can still change;
  - *Metamodel and content lock*: nothing in the model can change;
  - *Maintenance lock*: only the person who set it can change the model (for a merge or a clean-up).
  The database enforces them for every route (screens, API, MCP, `psql`); only the installer's login
  passes. Until roles arrive (phase 3.1) any signed-in user may lock and unlock; from 3.1 only Model
  Admins. Templates and reference models keep their permanent installer lock and cannot be edited.
- **SQL window is read-only for everyone (D52)**: *Allow changes* is gone; every run is rolled back.
- **MCP**: three new tools, `get_metamodel_history`, `compare_metamodel_versions` and
  `list_failing_checks` (21 tools). See [mcp.md](mcp.md).
- **API** (`/api/v1/models/<model>/...`, all in Swagger at `/api/docs`):
  `POST metamodel/changes` (one change, `dry_run` for the impact check), `GET metamodel/versions`,
  `GET metamodel/history`, `GET metamodel/compare?from=&to=`, `GET metamodel/pick-lists`,
  `GET checks?type=`, `PUT lock` and `DELETE lock`. Every write is in the audit log.

## Demo

1. `.\eax clean-run`, sign in, open **Sample insurance model > Metamodel**. The header says
   *version 1*.
2. Pick **Business Actor** (it has one entity), *+ Attribute*: name *Accountable Executive*, Text,
   Mandatory. Leave the default empty and *Check impact*: one entity will fail one more check. Save:
   *metamodel version 2*.
3. Open **Failing checks**: Claims Department fails "Accountable Executive is required". Filter by
   entity type; download the CSV.
4. Pick **Service**, *+ Attribute* *Service Owner*, Mandatory, default *To be confirmed*, tick *Put the
   default on the existing Service entities*. Save: one entity was given the default and nothing new
   fails. Open Claims Service: the value is there and the entity says *last changed in metamodel v3*.
5. **Metamodel > History and versions**: three versions, each change with its values. Compare v1 with
   the current version.
6. On Service, *Remove* Service Owner, *Check impact*: one value will be removed. Save, then open
   Claims Service's history: the value's removal is on the timeline, labelled *metamodel v4*.
7. *Lock... > Metamodel lock*, reason "Quarterly review". The banner shows; every edit button is
   disabled; try `PUT`/`POST` from Swagger: refused with the reason. Content can still change. *Unlock*.
8. Open the **Insurance reference model**: no edit buttons (read-only reference model).
9. The SQL window has no *Allow changes*; an `UPDATE` reports that it was rolled back.

## Checks

- `tests/sql/phase3_checks.sql` (as `postgres`): version 0.3.0, a version row for every model,
  publishing labels the history, entities stamped with their metamodel version, a retired type's entities read-only, each lock refusing
  what it should (maintenance by another person too) and the installer lock unchanged. Ends with
  "phase 3 checks passed". Rolled back.
  ```powershell
  Get-Content services/api/tests/sql/phase3_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U postgres -d eaexplorer -v ON_ERROR_STOP=1
  ```
- `phase1_checks.sql` and `phase2_checks.sql` still pass.
- `pytest services/api/tests/test_metamodel_edit.py`: codes and names, typed defaults, defaults that
  cannot be stored refused, the impact comparison, unknown operations.

## Upgrading from phase 2

`.\eax clean-run` (D54: always a clean rebuild). Migration `0005` backfills the metamodel version on
every entity and adds version 1 for every model.

## Not in phase 3

- Who may edit the metamodel and lock models: roles and permissions, phase 3.1.
- Editing values on the failing-checks screen and the data entry page: phase 6.
- Carrying a child model's metamodel changes back into its parent on merge (D66): the commits and
  merge phase.
