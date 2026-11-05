# Build phase 8.3: model tags, comparison and gap analysis

Goal: name a version of a model and keep it frozen, compare models and versions with what counts chosen first, set a
model back to a version, and run TOGAF gap analyses that stay in the model with their decisions, Gap entities, views
and reports. Version **0.8.4**, migration `0014_tags` (phase 8 took 0.8.3). Decisions D111, D145, D172, D173, D175, D176, D177.

## Status: accepted and closed (5 Nov 2026)

## What phase 8.3 delivers

- **Tags tab** (every model with content). A tag is a **frozen snapshot** of the model under a name, for example
  *Baseline 2026*: its metamodel and every entity, value and relationship as committed at that moment, with the commit
  number and metamodel version. Anyone who changes the model's content tags it, renames it, locks it or deletes it; a
  locked tag is never changed or deleted (the database refuses), and only a Model Admin unlocks it. Each tag downloads as
  a model package (Excel or zip), so it can be kept, loaded elsewhere or merged into another model.
- **Each tag has its own page** (from the model's Tags tab): what it is, when and by whom it was made, the commit and
  metamodel it froze (with the metamodel in short), the actions (compare with now, Excel, zip, rename, lock or unlock,
  make the latest, delete), and its **frozen contents** to browse: entities (by type, with a filter), the types, and the
  relationships. Open an entity to see it as it was in the tag (fields, values, relationships), with a link to it as it
  is now, or a note that it is gone. The model's **Actions** menu has *Tag this model now...* (opens the new tag's page)
  and *Tags of this model*.
- **Make a tag the latest** (Model Admins, unlocked project models). A complete override, like restoring an old backup
  on top of the model: the model as it is now is tagged first (an automatic *Before restore* tag with the date and time),
  then the tag overwrites the model: the metamodel becomes the tag's (entity types, attributes, relationship types and
  pick lists added since are removed; those removed since come back) and so does the content (entities and relationships
  added since are deleted, the others set back as they were, deleted ones brought back). It is one commit of kind
  *restore*, which everyone sees at once. To go forward again, make the automatic tag the latest. You type the tag's
  name to confirm.
- **Compare** (top menu; first-class, not inside a model, D177): any two sides, each any model you may read as it is
  now or one of its tags: the same model against its own tags, or two different models each with their tags. A
  model's **Actions > Compare...** opens it with that model's latest tag against the model now; a tag's *Compare with
  now* with that tag.
  1. **What to compare**: the baseline (left) and the target (right).
  2. **Choose what counts** (the filter screen): every entity type of either side by layer with how many entities each
     side has; tick the types, and open a type with its **+** to choose its fields (name, description, parent, status,
     tags, display ID and every attribute) and its **relationships** (each relationship type, outgoing and incoming, with
     the types at the other end). The tool proposes the defaults: name, description, parent, every attribute and every
     relationship; status, tags and display ID left out; system fields (ids, dates, who changed it) never count. A
     relationship added or removed shows as a change of the entity at each chosen end (for example *Flow to: +CRM*).
     The two sides need not have the same entity types or attributes: a type only one side has is marked (*baseline
     only*, *target only*) and its entities show as new or eliminated; an attribute only one side's type has is marked and
     left out by default, so it does not show every entity as changed (tick it to count it). Choose whether the
     metamodels are compared. Save the choice as a **comparison profile**, shared by everyone (with who made it; only
     its maker or a Super Admin deletes it), and load it later.
     Or skip the screen: *Compare with the defaults*.
  3. **The result**: changed, new, eliminated and kept, relationship and metamodel differences; a summary per type (click
     one to see only it); every difference with the fields that changed (before and after), renames marked; links to the
     entities. **⇆ details** on any row shows the element's two versions side by side, like the History tab: every
     field and value of each and its relationships (in both, only in the baseline, only in the target), the
     differences highlighted, with *Only the differences* to narrow it. **Download as Excel** (summary, entities, field changes, relationships, metamodel). **Save as a gap
     analysis**.
- **Matching**: hand-made matches first, then the same entity, then origin (copied from one another, or both from the
  same entity), then type and display ID, then type and name.
- **Gap analyses** (top menu *Compare > Gap analyses*; first-class, D177): a **source** (baseline) and a **target**, each
  any model as it is now or one of its tags, compared with a **TOGAF gap template**, and **stored in a model you
  choose**: a project model that is not locked, where you may change content; it may be the source's or the target's
  model. The storage model's roles decide access: its readers see the analysis, its Architects and above make it and
  decide the gaps, its Model Admins add Gap entities to it. The list shows every analysis you may see, with where it is
  stored, filtered by model (stored in, source or target) or name; a model's **Actions > Gap analyses** opens it filtered
  to that model:
  - templates: whole architecture; Business Architecture (phase B); Data and Application Architecture (C);
    Technology Architecture (D); capability gap analysis; requirements and motivation. Each says which types it
    compares; your own choice of types and fields can replace the template's;
  - each element is *included* (kept), *changed*, *new* (to be developed or procured) or *eliminated* (intentionally
    retired, or an accidental omission to add back), with the fields that changed;
  - **⇆ details** on each gap: the element in the baseline and in the target side by side (every field, value and
    relationship, differences highlighted);
  - every gap gets a **resolution** (retain, enhance, build, buy, replace, migrate, retire, accidental omission: add
    back, not a gap), a **note** and **work packages** (entities of the model), one by one or in bulk (tick rows, or
    the rows shown);
  - **Compare again** refreshes the gaps (a model side as it is now; a tag never changes) and keeps the notes,
    resolutions, work packages and Gap entities; gaps that went away are kept, marked gone;
  - each analysis records its baseline and target (models or tags, commits and metamodel versions), the template, and
    when and by whom it was compared;
  - **results**: each time an analysis is made or compared again its result is kept as a numbered run (#1, #2...);
    **Compare two gap results** (on the Gap analyses list, or *compare with #n* on an analysis) puts two results, of one
    analysis or of two, side by side: gaps closed, new gaps, status changed, resolution changed, unchanged. Downloaded as
    Excel (summary and comparison); nothing is saved;
  - **views**: the gap list, the **TOGAF gap matrix** (per type: baseline elements down, target elements across,
    included cells, an Eliminated column and a New row; types with gaps only, unless you tick for all), and the gaps by
    layer and type;
  - **downloads**: Excel (overview, gaps, the TOGAF gap matrix, field changes) and Word (overview, summary, new,
    eliminated and changed elements by type with resolutions, work packages and notes).
- **Gaps as Gap entities** (Model Admins): the chosen gaps (or all but the included ones) become Gap entities of the
  model, committed at once (D170), each named after its element and status, with the analysis, baseline and target
  (models, tags, commits and metamodel versions), the date compared, status and resolution as attributes and in the
  description, associated with its baseline and target elements (when in this model) and its work packages. A model
  without a Gap entity type gets one (Gap, with the attributes Gap Status, Gap Resolution, Gap Analysis, Baseline,
  Target and Compared On, and associations with every type) as a new metamodel version. Adding them again brings the
  existing Gap entities up to date. Each Gap entity is **tagged** `gap-analysis: <analysis>` and `gap-run: <analysis> #<n>`
  (the result it was made or last brought up to date from; earlier results' tags stay), so one result's gaps can be
  found, filtered and reported on.
- **Reports** (Superset, Reports tab > Gap analyses), each with the Model filter: **GR-01** gap analyses, **GR-02** gaps
  by layer and type (pivot, bar, treemap), **GR-03** the TOGAF gap matrix, **GR-04** resolutions and work packages
  (and the gaps still undecided), **GR-05** the Gap entities in the models. 116 dashboards in all.
- **MCP**: `list_model_tags`, `compare_models` (models or their tags), `list_gap_analyses` (every one you may see, or
  those stored in a model), `gap_analysis(analysis)`.
- **API** (Swagger, tag *versions*): `/tags` (every tag you may read), `/models/<m>/tags[/<t>[/entities/<e>|/download|/restore]]`, `/compare/fields`,
  `/compare`, `/compare/detail`, `/compare/download`, `/compare-profiles[/<p>]`, `/gaps` (GET, POST with `store_in`),
  `/gaps/<a>[/refresh|/items[/<i>[/detail]]|/gap-entities|/download]`, `/gap-runs` and `/gap-runs/compare?a=&b=` (Excel).

## Demo

The laptop sample comes with phase 8.3 data in the demo estate (made once at the first start, as the test users, D176):
the tags *Baseline 2026* and *Target 2028* (locked; between them the Merge test file was merged, Billing Engine and
Regulatory Reporting Tool retired, Claims Platform renamed and a few values changed), the comparison profile
*Applications and data*, the gap analyses *Whole architecture 2026 to 2028* (resolutions, notes, a work package; results
#1 and #2) and *Application Architecture since baseline*, and the Gap entities of the first, tagged with its result. So
**Tags**, **Compare**, **Gap analyses** and the GR reports show data straight away; the steps below make more.

1. `.\eax clean-restart`. Open Protea Insurance > **Tags**: the two tags; open *Baseline 2026*, then *Billing Engine* in it.
   On **Compare > Gap analyses > Whole architecture 2026 to 2028** (top menu), press **⇆ details** on a changed gap.
   **+ New gap analysis**: source *Sample insurance model* as it is now, target *Protea Insurance* tag *Target 2028*,
   stored in *Protea Insurance*: two different models, one with a tag.
2. As `user_architect`, **Protea Insurance (demo estate) > Tags**: tag it *Baseline 2026*.
3. As `user_model_admin`: **Merge > Merge test file (Excel)**, merge it (new entities, changed values, two new
   attributes). **Tags**: tag it *Target 2028*, ticking *Lock it*.
4. **Tags > Baseline 2026 > Compare with now** (opens the top-level Compare screen): *Next: choose what counts*; untick a few types, open one type's fields,
   untick Owner; save the profile; **3. Compare**. Click *changed*, open a row's fields; **Excel**.
5. **Save as a gap analysis**: *Application Architecture gap analysis*. In the analysis set a resolution on a new gap,
   tick three gaps and set *Enhance*, add a work package, write a note. Open **TOGAF gap matrix** and **By layer and
   type**; download **Excel** and **Word**. **Add the gaps as Gap entities**, then open one (Gap entity ↗).
6. **Compare again**: the notes stay. Set *Retire* on two gaps, compare again, and **compare with #1** (Excel): two
   resolutions changed. **Add the gaps as Gap entities** again: they now carry the tag of result #2 too. On the Gap
   analyses list, **Compare two gap results** with one result of each analysis.
7. **Tags > Baseline 2026 > Make this the latest...**, type the name, overwrite: the model is as it was (the merge test
   entities and the two attributes are gone). **Tags**: the automatic *Before restore* tag; make it the latest to go
   forward again; **Compare** *Target 2028* with now: nothing differs.
8. **Reports > Gap analyses**: GR-01 to GR-05. Try deleting the locked tag (refused); as `user_architect`, *Make this
   the latest* is not offered.

## Checks

- `tests/sql/phase8_3_checks.sql` (as the API's login): ends with "phase 8.3 checks passed". Earlier phases' checks pass.
- `pytest services/api/tests`: `test_versions.py` (matching by origin, display ID and name, renames, statuses, default
  fields, relationships by matched ends, templates, Excel and Word downloads, the GR reports, the tabs) and
  `test_reports.py` (every report view made by the migrations).
- Tried here against a database built from the migrations: tags of the demo estate (278 entities, 538 relationships),
  a merge, a locked tag, comparisons (tag with now, tag with tag, two models), making the baseline tag the latest
  (metamodel parts removed, 56 items in one commit; comparing the tag with the model afterwards finds nothing) and
  back to the automatic tag (identical to *Target 2028*), gap analyses with resolutions, work packages, refresh, Gap
  entities (with the Gap type added as a new metamodel version), the Excel and Word files, the GR report views.

## Upgrading from 8

`.\eax clean-restart`.

## Not in phase 8.3

- Similarity (fuzzy) matching of names: matching is exact (hand-made, same entity, origin, display ID, name ignoring
  case); similarity matching is in the plan (D178, docs/todo.md).
- Matches made by hand on the compare screen (the API takes them as `settings.matches`; a screen for them comes with
  the merge-back screens of phase 19).
- Comparing a model's history at any moment (not only tags): with history and change log, phase 9.
- KPI trends over tags: phase 24.

## Test checklist (for the end-to-end testing phase, 36.1)

- [ ] Tag, rename, lock, unlock (Model Admin only), delete; a locked tag cannot be changed or deleted.
- [ ] Make a tag the latest and back: metamodel and content identical each way; history and commits kept.
- [ ] Compare: defaults, the filter screen, profiles, every status, renames, relationships, metamodel; Excel.
- [ ] Gap analyses with each template; resolutions, notes, work packages one by one and in bulk; compare again.
- [ ] Gap entities: type added once, attributes and associations right, brought up to date when added again; run tags.
- [ ] Per-type fields and relationships on the filter screen; compare two gap results (one analysis, two analyses).
- [ ] GR-01 to GR-05 show the analyses; the Word and Excel files open in Office.
