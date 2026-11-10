# Build phase 9: the change log

Goal: one place to see who changed what, without slowing the repository. Version **0.9.0**, migration
`0015_change_log`. Decision D180.

## Status: accepted and closed (5 Nov 2026)

## What phase 9 delivers

- **Change log** (top menu): one row per action a person takes, newest first.
  - **Columns:** when, model, user, action (with its kind: content, metamodel, model or action), the item (linked), and
    what changed: each field with its old and new value.
  - **What is logged:**
    - an entity created, changed (its fields and attribute values), deleted or restored;
    - a relationship added or removed;
    - a part of a metamodel added, changed or removed (entity types, attributes, relationship types, pick lists,
      rules, allowed relationships);
    - a model's own changes (lock, archive, rename);
    - the actions that are not a row change of their own: tags, gap analyses, comparison profiles, merges, commits
      and their requests, roll backs, models created, copied, published or deleted, roles given or removed, library
      and metamodel draft steps, saved views and views, Keycloak role mappings.
  - **One action, one row:** every change one person makes to one item in one save is a single row with its fields
    gathered. Changes made with no person set (the installer, the seed) are left out.
  - **Every route in is logged the same way:** screens, the API, MCP, merges, making a tag the latest.
- **Who sees what:**
  - everyone sees their own changes;
  - a Model Admin sees every change in the models they administer;
  - a Super Admin sees every change.
- **Filters:** search (item, model, user or value), model, person (when you see others), kind, action, item type,
  dates from and to, only my changes. The total and the top people for the filters are shown; 200 rows at a time.
- **Super Admin only:** **export** (CSV or Excel, every row the filters select, one line per field changed) and
  **delete** (the rows the filters select, or every row when no filter is set; type DELETE to confirm). Deleting
  only removes change log rows: the history of every item (History tab, roll back), commits, tags and the audit
  trail are kept, and the deletion is itself logged.
- **Its own database (D180):** the change log never slows the repository.
  - Nothing extra is written when people change things. The log is built from what the repository writes anyway
    (the history of every row and the audit trail), shipped across in the background every 5 seconds
    (`python -m eax.change_log`, started beside the API), and again just before the screen reads, so it is current.
  - A row is shipped once its transaction has finished: every history and audit row now carries its transaction, so
    a long save that finishes late is never missed.
  - **Connection string:** `EAX_CHANGELOG_DB_URL` (`postgresql://user:password@host:port/database`, the password
    URL-encoded) and `EAX_CHANGELOG_DB_SCHEMA` (default `changelog`). On a laptop it points at the same database
    (schema `changelog`); on a server point it at another database or server. Empty means the repository's
    database. The schema and tables are made on first start; the login needs to be able to create them.
- **API** (Swagger, tag *change_log*): `GET /change-log` (filters: `q`, `model`, `user`, `kind`, `action`, `item_type`,
  `from`, `to`, `mine`, `limit`, `offset`), `GET /change-log/export?format=csv|xlsx`, `POST /change-log/delete`.

## Demo

1. `.\eax clean-restart`. In the api container's log: `EA Explorer: change log shipper started`, then the demo estate
   lines.
2. As `user_super_admin`: **Change log**. The changes of the laptop's history demo and the demo estate's tags and gap
   analyses are there. Filter by *Protea Insurance*, kind *Metamodel*: the Gap entity type and its attributes.
3. As `user_architect`: change a value of an application, commit it. **Change log**: one row, *Changed entity*, the
   old and new value; only your own rows are shown.
4. As `user_model_admin`: tag a model, then open the **Change log**: *Tagged the model*, and every change in the
   models you administer.
5. As `user_super_admin`: **Excel**, then **Delete...** with a filter (one person), type DELETE: the rows go, a row
   *Deleted change log entries* is added; the entity's History tab still shows every change.

## Checks

- `tests/sql/phase9_checks.sql` (as the API's login): ends with "phase 9 checks passed". Earlier phases' checks pass.
- `pytest services/api/tests`: `test_change_log.py` (history rows to entries, one row per action, who sees what,
  the API actions logged, the screen and the migration).
- Tried here against a database built from the migrations: about 39,000 history rows shipped in under a second (the
  seed's left out), the demo estate's changes logged (275 rows), each role's view, export, delete.

## Upgrading from 8.3

`.\eax clean-restart`. An existing `work/eaexplorer.env` without the two new settings uses the repository's database
for the change log; to set them, see `deploy/templates/eaexplorer.laptop.env`.

## Not in phase 9

- Automatic clean-up of old change log rows (a retention period): with the backup schedule screens (8.4) or later.
- A Superset dashboard of the change log: the screen and its export cover it for now.

## Test checklist (for the end-to-end testing phase, 36.1)

- [ ] Each kind of change shows once, with the right old and new values and the right person.
- [ ] Each role sees what it should (own, Model Admin's models, Super Admin all).
- [ ] Export and delete as Super Admin only; history, roll back and audit untouched by a delete.
- [ ] The change log on another database server through `EAX_CHANGELOG_DB_URL`.
