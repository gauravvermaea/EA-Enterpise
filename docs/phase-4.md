# Build phase 4: creating and copying models, library models and packages

Goal: people build their own models on screen: root metamodels, project models (child or
independent), library models, and copies of any model, with or without its content and history;
models travel between installations as one package; a model moves to another framework; and a
person's own language model can draft a metamodel for someone to review. Version **0.4.0**,
migration `0008_models`. Decisions D101, D106 (in part), D108, D115 to D125.

## Status: built, waiting for the owner's test

## What phase 4 delivers

- **New model** (*Models > + New model*, and *Create a model from this* on every model page and in the
  library). Choose what to create, its name and what it starts from:

  | Create | Who | Starts from |
  | --- | --- | --- |
  | Project model | Model Creators (and Super Admins) | a root metamodel, a library model or one of your models |
  | Root metamodel | Model Creators | nothing (a new framework under Root) or a copy of another root's metamodel |
  | Library model | Library Admins | any model; it starts as *not yet published* until a Library Admin publishes it |

  **Copy:** the metamodel only, the metamodel and the content, or the content with its history (the
  entities' history tab then shows the source's past). Content is copied in the background by the job
  runner; the new model opens at once with a *Copying...* banner (⏳) and fills in when it is done.
  Display IDs are kept.

- **Child or independent (D122).** Starting from a project model you choose:
  - **Child model**: stays linked to its parent. Its work merges back into the parent, and the parent's
    metamodel changes and attribute updates flow down to it (merges: phase 8; push-down: phase 8.1).
    Only the parent's Model Admin can make one.
  - **Independent model**: a separate copy. Nothing flows between the two and it never merges back,
    but they can be compared (phase 24.1).

  A model built on a root metamodel or a library model is always independent.
- **Library Admin (D118)**, a new global role (Keycloak `eax-library-admin`, test user
  `user_library_admin`): creates library models, promotes a project model into the library (a copy,
  published), publishes, withdraws (no new models start from it; models built on it keep working) and
  restores; uploads packages into the library; *Show withdrawn* in the library. An organisation's own
  root can be a library model (D119). New marks: 🚧 not yet published, ⛔ withdrawn, ⏳ copying.
- **Packages (D116).** *Actions > Download package (zip)*: `manifest.json`, `metamodel.json` (the
  whole metamodel, format `eax-metamodel/1`) and the content as CSV, one file per entity type plus
  `relationships.csv`. *Download as Excel*: the same in one workbook (Manifest, Layers, Pick lists,
  Attributes, Entity types, Relationship types, Allowed, Rules, Type attributes, one sheet per entity
  type, Relationships). Both upload again. *Download the metamodel (JSON)*: the metamodel alone.
- **Upload wizard (D108, D123)** (*Models > Upload a model*, and *Upload a model package* in the
  library). Choose the file: it is read and checked first (counts, errors, notes). **Where it goes** is
  a drop-down of every root metamodel: those whose metamodel matches the package completely can take
  it (the one named in the package first); the others show how many places they differ, with the
  differences on request; the last choice is *Under Root, as a root of its own*, which makes a new
  root metamodel with all the package's values. Give it a **name** (change it to upload the same
  package again beside the first, for testing) and choose library model or project model.
- **Move to another framework (D121)** (*Actions*, Model Admins): choose the target root; a preview
  matches entity types by code, then name, each changeable or left out, and says what is dropped.
  Then a **moved copy** (a new model; this one stays) or **in place** (one new metamodel version).
- **Archive, reactivate and delete.** Model Admins archive and reactivate. Super Admins delete, after
  typing the model's name; a package is saved first to the exports folder
  (`deleted-<date>-<name>.zip`); the database refuses while other models are built on it or merge
  into it (archive instead).
- **Metamodel drafts with AI (D115, D120)** (*Models > Metamodel drafts*). A person's own language
  model, through MCP, drafts a new root metamodel or changes to a model, step by step
  (`start_metamodel_draft`, `draft_set_item`, `draft_remove_item`) or as one document
  (`draft_replace`, after `get_metamodel_spec`). Drafts can also be started on screen, empty, from a
  copy of a root, or from a JSON file. The review page shows the checks, the differences, and every
  item by section with *Remove* (removing an entity type takes its allowed relationships and rules
  with it); *Apply* makes the new root (and optionally a model on it) or publishes the changes as one
  metamodel version; *Reject* says why. Whoever may make the change by hand may apply it.
- **Tooltips** on every new field (ⓘ), button and menu item (D123).
- **Greyed out, not hidden (D125).** Every button, menu item, option and start tile is shown to every
  role. What your roles do not allow is greyed out, and its tooltip names the role needed and who gives
  it (a User Admin for global roles, the model's Model Admin for model roles). This covers the new
  phase 4 screens and the earlier ones: the metamodel edit buttons, *Lock...*, the People tab, the role
  mapping, the SQL and Users links, and the start page tiles.
- **Layered ER diagram (D124).** *ER diagram > Layered*: one band per layer, top to bottom in the
  metamodel's layer order, each entity type in its layer's band, lines crossing between the bands
  (right-angled up to 200 lines, straight beyond). Choosing it with one layer selected shows all
  layers; the layer chips still narrow it. The bands go into SVG, PNG and .drawio, and the choice is
  remembered in your browser.
- **API**: `POST /api/v1/models`, `/models/<id>/archive|reactivate|publish|withdraw|restore|promote`,
  `DELETE /models/<id>?confirm=<name>`, `GET /models/<id>/package?format=zip|xlsx`,
  `/models/<id>/metamodel-spec`, `POST /packages/analyse` and `/packages/import` (form fields `file`,
  `placement` root or own_root, `root`, `name`, `as_kind`), `/models/<id>/framework-preview` and
  `framework-move`, `/metamodel-drafts` (list, create, get, edit, apply, reject). All in Swagger.

## Demo

1. `.\eax clean-restart` (new migration, new Keycloak role and test user): it brings the running
   containers down, then does a clean-run.
2. Sign in as `user_library_admin`, open **Library** > *Insurance reference model* > **⬇ Zip** (and
   **⬇ Excel**). Then **⬆ Upload a model package**, choose the zip: *Where it goes* lists the roots,
   *ArchiMate 4 (named in the package) · matches completely* chosen. Change the name to
   *Insurance reference model (test)* and upload as a library model: it opens, published, beside the
   original. Upload the Excel file as well, under Root as a root of its own.
3. Sign in as `user_model_creator`: **Models > + New model**, start from *Insurance reference model*,
   copy *the metamodel and the content*: the model opens with the copying banner, then 715 entities.
4. Open **Karoo Re** > *Actions > Create a model from this*: choose **Child model** (it merges back) or
   **Independent model** (a copy you can compare). Hover the ⓘ marks for what each means.
5. On your new model: *Actions > Move to another framework...* > *Lean EA metamodel*: see the type
   matches, change one, make a moved copy.
6. Open *Insurance reference model > ER diagram* and press **Layered**: the layers as bands. Untick
   Technology, Motivation and Implementation & Migration and turn attributes off for a readable picture; save as .drawio.
7. Sign in as `user_architect`: *+ New model*, *Upload a model*, most of *Actions*, *Lock...* and the
   metamodel buttons are greyed out; hover one to see the role it needs.
8. **Models > Metamodel drafts > + New draft**: a new root starting from a copy of ArchiMate 4. Open it,
   remove *Device* (its allowed relationships go too), check it passes, *Apply* with a model on it.
   Or connect your language model (see **MCP**) and ask it to draft one.
9. Sign in as `user_super_admin`: *Actions > Delete...* on *Fynbos Mutual (group)* is refused (other
   models merge into it); on your moved copy it works, and the package is in the exports folder.

## Checks

- `tests/sql/phase4_checks.sql`, as the API's login. Ends with "phase 4 checks passed". Rolled back.
  ```powershell
  Get-Content services/api/tests/sql/phase4_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
  ```
- `phase1_checks.sql` and `phase2_checks.sql` (as postgres), `phase3_checks.sql` and
  `phase3_1_checks.sql` (as eax_app) still pass. Two phase 2 checks now expect the 0.4.0 messages
  (a new reference model starts unlocked; only roots and reference models go into the library).
- `pytest services/api/tests`: `test_model_ops.py` (package reading, metamodel differences, what a
  removal takes with it, and that every API response is declared with a schema) and the rest.

## Upgrading from phase 3.1

`.\eax clean-restart` (D54: down, then clean-run). The API image installs `openpyxl` (Excel packages). The Keycloak realm has
the new role `eax-library-admin` and test user `user_library_admin`, so Keycloak's database starts
empty. Uploads up to 100 MB (nginx, on https and on the laptop's plain http).

## Not in phase 4

- Library model pack files (guidance, workbooks, any other files): phase 13, with Mayan (D117).
- Merging a child model back and pushing metamodel changes down to children: phases 8 and 8.1.
- Comparing an independent model with its source (gap analysis): phase 24.1 (D111).
- Showing the source's history inside an entity's History tab for models copied *with history*:
  the flag is stored (`history_from_source`); the History tab shows only the copy's own history
  until the history phase (9).
