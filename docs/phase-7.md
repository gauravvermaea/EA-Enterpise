# Build phase 7: grids, search and saved views

Goal: work with many records at once, for content and for the metamodel, and find anything. Version
**0.7.0**, migration `0011_grids`. Decisions D147 (plan order), D150.

## Status: accepted and closed (4 Nov 2026, D157); end-to-end test in phase 36.1 (D129)

## What phase 7 delivers

- **A spreadsheet-style grid** used everywhere a grid fits:
  - click a cell and type; Enter or F2 edits, Enter moves down (below the last row starts a new row), Tab moves right;
  - Shift with arrows or click selects a block; Ctrl+C copies it and **Ctrl+V pastes blocks from Excel**, and a paste
    that runs past the last row adds rows; Delete clears; Ctrl+Z undoes; Ctrl+S saves;
  - right-click: insert a row, edit, clear, copy, delete or undelete rows;
  - changed cells are shaded (hover shows the old value), new rows green, deleted rows struck through;
  - Save sends only the changed rows; Discard forgets them; filter, sort by any column, choose columns, CSV;
  - large grids draw only the rows in view, so thousands of rows stay quick.
- **Content grids** (model page, tab **Grid**): the entities of any type (name, description, part of, tags and every
  attribute, with pick lists as drop-downs), and **all relationships** (source and target by ID or name,
  relationship type, label; *Allow outside the metamodel* adds unmapped pairs flagged, D49). Each row is saved on
  its own: 497 good rows of 500 are kept and the three bad ones are marked ⚠ with the reason. Rules still warn,
  never block (D48). Who may: as data entry (Architects, Model Sub Admins, Model Admins).
- **Metamodel grids** (tab **Metamodel > Grids**, Model Admins, D89): entity types, relationship types, attributes
  (of every type, with data type, pick list, required, section, unit, default), allowed relationships, pick-list
  values and validation rules. One Save is **one new metamodel version** with every changed row, or nothing if a
  row is wrong (that row is marked). Deleting an entity type retires it; a pick-list value is retired.
- **Search** (top bar, or press **/**): every model you can read, in names, display IDs, descriptions, tags and
  any attribute value, with filters for model, entity type, attribute (for example only Vendor) and tag; each
  result says where the text was found. The MCP tool `search_entities` does the same.
- **Saved views** on every grid: the columns shown, filter and sort, saved by name, private or **shared** with
  everyone who can read the model.
- **Favourites ★** on entities, models and saved views, and **recently opened** entities (on this browser), on the
  start page and the search page.

## Demo

1. `.\eax clean-restart` (new migration).
2. As `user_architect`: **Sample insurance model > Grid**, choose *Application Component*. Change a name; copy
   three rows from Excel (name, description) and paste below the last row: three green rows. Save: each gets an ID.
3. Paste a row with Criticality *x*: it is marked ⚠ "not a whole number"; the others are saved.
4. **Grid > Relationships (all types)**: paste `APP-0001 <tab> Serving <tab> BAC-0001`, Save.
5. Hide some columns, filter *claims*, **Save view** as *Claims apps*, shared; press ☆ on it.
6. Press **/**, search *Oracle*: the cluster is found *in Vendor*.
7. As `user_model_creator`: **Karoo Re > Metamodel > Grids > Attributes**: add two attributes to *Application
   Component*, change a section, Save: *Metamodel > History* shows one new version with both.
8. As `user_report_viewer`: the grids show, Save and + Row are greyed out with the role needed.

## Checks

- `tests/sql/phase7_checks.sql` (as the API's login). Ends with "phase 7 checks passed".
- Earlier phases' checks still pass.
- `pytest services/api/tests`: `test_grids.py` (every metamodel grid is routed, the grids only send known
  metamodel changes, a batch is one version).

## Upgrading from phase 6

`.\eax clean-restart`. New API: `/api/v1/models/<model>/grids/...`, `/metamodel/batch`, `/api/v1/search`,
`/api/v1/me/saved-views`, `/api/v1/me/favourites`.

## Not in phase 7

- Template download and CSV or Excel upload per type: phase 10.1 (D147); the grid's paste covers the quick case.
- Commits and review before changes reach everyone: phase 8.
- Context menus outside the grids, and keyboard shortcuts beyond the grid and **/**: later, with the home dashboard (10).

## Test checklist (for the end-to-end testing phase, 36.1)

- [ ] Entity grid: type, paste from Excel (inside and past the end), delete and undelete, undo, sort, filter, columns, CSV.
- [ ] Bad rows are marked with the reason and the good ones saved.
- [ ] Relationships grid by ID and by name; outside the metamodel with the box ticked.
- [ ] Each metamodel grid: add, change, delete; a wrong row saves nothing and is marked; one version per Save.
- [ ] Search with every filter; / jumps to search.
- [ ] Saved views private and shared; favourites; recent items.
- [ ] Roles: Report Viewer and others see the grids greyed out with the role needed.
