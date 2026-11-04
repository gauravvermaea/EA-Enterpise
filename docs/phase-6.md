# Build phase 6: data entry in forms

Goal: people enter and change entities and relationships through forms generated from the metamodel.
Every save is visible to everyone at once; there are no commits yet (D61). Version **0.6.0**, migration
`0010_data_entry`. Decisions D48, D49, D79, D144, D145.

## Status: built (4 Nov 2026), waiting for test (or the end-to-end test in phase 36.1, D129)

## What phase 6 delivers

- **Forms from the metamodel**: every attribute of the entity type in its sections, with the right input
  for its data type (text, long text, whole and decimal numbers, currency, percent, date, yes/no, pick list,
  web address, email, link to another entity), required marks, units and tooltips. Built-in fields: name,
  description, part of (parent), tags; the display ID is given on save.
- **Wherever entities are listed** (an entity type's table, the Data entry tab, Failing checks): *✎* edits the
  entity in its form and *+ rel* relates it to more entities. Relationship lists (*Relationship types*, and each
  type's list) have *+ Relationship* (choose the type, the source and the target; the source stays chosen for
  several targets in a row) and *✕* to remove one.
- **Entity page**: *✎ Edit*, *Retire* / *Restore*, *Delete...*; *+ Relationship* and *✕* to remove one on the
  Relations tab; *↶ Roll back to here* on a moment in the History tab. A type's entity list has *+ New* and
  *Data entry*.
- **Data entry tab** (D79): choose an entity type and its fields become columns. *+ Row* adds a row for a new
  entity, saved with *Save* (or Enter); *✎* edits a row; *+ rel* relates a saved row to existing entities
  (a new entity is saved first). *+ In a form* opens the full form, with *Save and new*.
- **Rules warn, never block** (D48): a value saved although it fails a rule is kept with a flag and the
  rules, who saved it and when; the form and the row show it; the warnings show until fixed.
- **Relationships**: *What the metamodel allows* lists the allowed relationship types and the entity type at
  the other end; *Any relationship* allows any type to any entity. If the metamodel does not allow it,
  *Add anyway* adds the mapping to the model's metamodel as a new metamodel version, flagged as added from
  data entry for a Model Admin to review (D49). Architects can do this although they cannot change the
  metamodel otherwise.
- **Tags** on entities (lower case, no duplicates), copied with model copies, in the reports as `rpt.entity_tags`.
- **Duplicate names** warn when saved.
- **Roll back**: an entity goes back to how it was just after a moment of its history (fields, tags, values,
  relationships), saved as a new version; nothing in between is lost.
- **Someone saved first**: an edit opened before someone else's save is refused with who saved, so nothing is
  overwritten unseen.
- **Who may**: Architects, Model Sub Admins and Model Admins on the model (and Super Admins). Everyone else sees
  the same buttons greyed out with the role they need (D125). Locked, library and root models, content locks
  and retired types (D87) are read-only.

## Demo

1. `.\eax clean-restart` (new migration).
2. Sign in as `user_architect`, open **Models > Sample insurance model > Data entry**, choose *Application
   Component*. Press **+ Row**, type *Underwriting Workbench*, Owner, Lifecycle *Plan*, Criticality *7*, Save:
   it saves with a warning (criticality 1 to 5) and the cell is flagged.
3. Press **+ rel** on that row: *Serving: Business Process*... pick *Register Claim*, Add.
4. Open the entity (its ID): **✎ Edit**, set Criticality to 4 and tags *underwriting, new*: the warning goes.
5. **Relations > + Relationship > Any relationship**: *Serving*, this → the other, pick *Claims Management*
   (a capability): the metamodel does not allow it; **Add anyway**. *Metamodel > History* shows the new version,
   flagged as added from data entry.
6. **History**: click the first moment, **↶ Roll back to here**: the values and relationships go back; the
   history shows the roll-back as a new moment.
7. **Retire**, then **Restore**; **Delete...** on a test entity.
8. Sign in as `user_report_viewer`: every data entry button is greyed out with the role needed.
9. **Reports > SR-01**: the new application is there (after Superset's cache, at most five minutes).

## Checks

- `tests/sql/phase6_checks.sql`, as the API's login with the sample loaded. Ends with "phase 6 checks passed".
  ```powershell
  Get-Content services/api/tests/sql/phase6_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
  ```
- Earlier phases' checks still pass.
- `pytest services/api/tests`: `test_content.py` (values coerced to their data type, bad values refused with
  the field's name, tags).

## Upgrading from phase 5

`.\eax clean-restart`. New API routes under `/api/v1/models/<model>/content/...`, `/forms/<type>`,
`/entry/<type>` and `/entity-picker`.

## Not in phase 6

- Grids with paste and bulk save, search and saved views: phase 7.
- Commits, staging and review of changes: phase 8 (design session first, D61).
- Restoring a deleted entity: phase 9 (history and change log).
- Entity tags in packages (zip and Excel): later; copies keep them.
- Model tags (a whole model at a named point, to roll back to and compare): to settle in the discussion after
  phase 6 (D145).
- Writing through MCP: phase 27 (proposals into staging).

## Test checklist (for the end-to-end testing phase, 36.1)

- [ ] Every data type has the right input and saves; bad values are refused with the field name.
- [ ] A failing rule saves with a flag and shows; fixing it clears the flag.
- [ ] + Row, Save, ✎, + rel on the Data entry tab; + In a form with Save and new.
- [ ] ✎ and + rel on a type's table and on Failing checks; + Relationship and ✕ on relationship lists.
- [ ] Relationships allowed and outside the metamodel (the mapping appears, flagged, in a new metamodel version).
- [ ] Retire, restore, delete (refused with parts or links), roll back (fields, values, tags, relationships).
- [ ] A stale edit is refused with who saved since.
- [ ] Report Viewer, IT Admin and a person with no role see everything greyed out with the role needed.
- [ ] Locked, library and root models and retired types are read-only.
