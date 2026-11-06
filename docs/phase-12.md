# Build phase 12: validation and data quality

Goal: know how good the data is, where it is weakest, who should fix it, and whether it is getting better. Version
**0.13.0**, migration `0020_quality`. Decisions D239 (agreed with the owner on 6 Nov 2026 before building), D241 (weights in the metamodel), D242 (which
models are measured), D244 (score weights, colours and schedule), D245 (calculated in the background and stored), D246
(data quality where people edit), D247 (model icons), D248 (no logic in the database) and D249 (several API and job
servers).
Requirements MM-022, VAL-002, VAL-003, VAL-005, VAL-006, VAL-007, RPT-007, NXT-010.

## Status: accepted and closed (6 Nov 2026, D254)

## What phase 12 delivers

- **A Quality tab on every project model** (anyone who reads the model):
  - the **quality score** (0 to 100: half completeness, almost a third the share of entities failing no rule, a fifth
    the share that is not stale) as a ring, and its parts and counts as metric tiles: completeness, rules passed,
    fresh, orphans, seals, and **yours to fix**;
  - simple charts: **completeness by entity type** and **by owner** (weakest first), **failing rules**, and the
    **score over time**;
  - **everything drills down**: a tile or a bar opens the entities behind it (by type, owner, rule or kind), each with
    its completeness, problems, seal and the person responsible, and each entity opens its page to fix it. A drill-down
    has its own address, so it can be bookmarked or sent;
  - **actions** on the entities chosen in a drill-down: **Still current** (Model Admins, one click for one or many),
    **Attest correct** (the seal: the person responsible or a Model Admin), **Remove seal**;
  - **Measure now**: measures the model and keeps the measurement, which joins the trend and the estate (the schedule
    keeps one every week by default, D244);
  - links to the four **reports in the reporting tool**, and **Download PDF** and **Download Excel** on the tab and on
    every drill-down.
- **Score weights, colours and schedule (D244)**: Super Admins set, on Administration > Quality > **Score, colours and
  schedule**, how much completeness, rules passed and fresh count (adding up to 100; 50, 30 and 20 by default), the
  colours (green from 80, amber from 60, red below by default), the stale period and how often every model is measured
  again (**every week** by default, Sunday 03:00; day, week or month from a picker). A model may set its own on its
  Quality tab (Settings > Score and colours, Measured again); a Model Admin's change waits for a Super Admin's approval.
  Each model is scored and coloured by its own; the estate by the installation's. Scores are kept to two decimals:
  hover over a score for the exact value.
- **Calculated in the background (D245, D248)**: measuring a model is a background job. **Measure now** (Quality tab),
  **Recalculate quality** (the model page) and **Measure all** (Administration > Quality) queue it, show its progress
  and tell the person who asked when it is done. Each entity's result is stored; the Quality tab, the grids, the entity
  type scores and the estate show the **last calculation with its date**. Saving changes queues a quick job a few
  seconds later for just the entities changed; leaving a field out, or approved settings and rules, queue the whole
  model. Only one entity's page and form check it **at once**. Nothing is calculated by database triggers.
- **Where people edit (D246)**:
  - the **entity page** shows the entity's data quality at the top (hover for its parts) and the reasons that concern
    the whole entity (a rule about relationships, stale, the seal); each field that lowers it is **highlighted** with
    why: missing (and its weight), the rule it breaks, not applicable;
  - the **data entry form** highlights the counted fields left empty as you type and shows the quality as saved;
  - the **grids** have a **Quality** column and highlight the cells that lower it (hover for why), with the type's
    score and when it was calculated;
  - the **Entity types** tab has each type's overall score;
  - **Not applicable here**: a field that does not apply to one entity is left out of its completeness once a Model
    Admin approves (theirs applies at once); a rejected one can be **asked again**;
  - **Leave out for this model**: a Model Admin leaves a field out for every entity of the model, at once (the Super
    Admins are told);
  - Model Admins approve or reject "not applicable" requests on the Quality tab, and Super Admins Model Admins' changes
    on Administration > Quality, **one by one or many at once**; a rejected change can be asked for again;
  - **retired entities** are not part of data quality.
- **Model icons (D247)**: every model has an icon from the built-in library or uploaded for it alone (PNG, JPEG, WebP or
  SVG, up to 256 KB), picked when it is created and changed by its Model Admins by clicking it on the model page; shown
  wherever the model is named.
- **API and job servers (D249)**: `.\eax servers <n>` or Administration > Containers (+ and −) runs more or fewer
  copies of the api container at once; each answers API calls (nginx spreads them) and runs background jobs.
- **Who is responsible** for an entity: its Owner attribute when that names a person of the installation, else whoever
  last changed it, else the model's Model Admins. Every entity always has someone. The Owner attribute's text (a person
  or a business role) is also how quality is grouped "by owner".
- **Completeness**: weighted items per entity (its description, each attribute of its type, having a relationship, or a
  relationship of a given type). By default a required attribute weighs 3, another attribute 1, the description 1 and
  having any relationship 2; 0 leaves an item out.
- **Weights in the metamodel (D241)**: each attribute has a **data quality weight** where it is defined (Metamodel tab,
  attribute dialog), and an entity type may **override** it where the attribute is added to the type. The weights travel
  with the metamodel (versions, packages, Excel, push down). The **data entry form** shows each field's weight as dots
  and the entity's **completeness as it is typed** ("Data quality: 70% complete"). A model's quality settings may still
  change any weight.
- **Rules without SQL**, four kinds: must have a relationship (type, direction, other type, at least and at most),
  attribute conditions (when one value meets a condition, another must too), cross-entity consistency (the related
  entities must not, or must all, meet a condition) and naming and uniqueness (a pattern, unique within the type or the
  model). Each rule is an **error** (a commit that breaks it is refused, saying which entities and why) or a **warning**
  (it lowers the score, shows and notifies). **What would it find?** shows what a rule finds before it is saved. The
  metamodel's own checks (required values, ranges, patterns, allowed relationships) count too.
- **Settings inherited down the hierarchy**: the stale period (one per model for every type, a year by default), the
  schedule, the weights and the rules are set on a metamodel and inherited; a model may change them. A **Model Admin's
  change waits for a Super Admin's approval** (Administration > Quality; the Super Admins are told, and the Model Admin
  is told the answer); a Super Admin's applies at once.
- **Seals**: an owner attests an entity is correct; a Model Admin marks entities still current. A seal **expires** after
  the stale period and an **edit by someone else breaks it** at once (the owner is told).
- **Notifications**: the person responsible is told **as it happens** (an entity of theirs becomes incomplete in an
  important item, fails a rule, goes stale or loses its seal; checked every two minutes on the models that changed, each
  problem told once until it is fixed; a model's first measurement only records what is there) and gets a **weekly
  digest** (Mondays at 07:00 in the installation's time zone), on the bell and the webhooks.
- **Administration > Quality, the estate**: the **estate score** (each model's latest measurement, weighing as many
  entities as it has), its totals and its **weekly trend**, every model with its score, a month before and its trend
  (Super Admins and IT Admins see every model; others the models they have), each with **Measure now** and
  **Measure all now** for every model measured (one after another, with progress), the changes
  waiting for approval, and
  **Download PDF** and **Download Excel** (each model opens to its entity types).
- **Which models are measured (D242)**: on Administration > Quality (open by default), Super Admins and IT Admins see
  every model with its kind, its state as an icon (🟢 active, 🔒 metamodel locked, 🛠 maintenance, ❄ frozen, 👁 read-only,
  🗄 archived, 📚 library) and its latest score as a line and %, and tick the models that are measured; the choice stays.
  The laptop test models include one in each state (Karoo Legacy, Audit 2025, Pilot, Operations, Board pack). **Archived models are never measured.** Without a choice, project models that are
  not frozen are measured; library models, root metamodels and frozen models are not, so they add no noise. A model
  not measured is left out of the schedule, the reminders and the estate; its Quality tab still measures on request and
  says so.
- **Exports**:
  - **PDF** (ReportLab): the model's metrics, charts and findings, a drill-down's entities, or the estate;
  - **Excel**: Summary, By type, By owner and Rules with the **drill-downs as Excel groups** (the + opens a type, owner
    or rule to its entities and each entity to its findings), Findings and Entities with filters, and the Trend; names
    link back to EA Explorer.
- **Reports in the reporting tool** (RPT-007), each with its own drill-down (click a bar; Open on a row goes to the
  entity): QR-01 data quality across models (now and the trend), QR-02 completeness by type and owner, QR-03 what to
  fix, QR-04 failing rules.
- **Claude through MCP**: `quality_summary`, `quality_findings` (for example "what are my gaps?"),
  `suggest_quality_fix` (as the person's uncommitted change, never committed by Claude) and `draft_quality_rule`
  (shows what a rule finds; saved only when asked, with the same approval).

## Also in this phase

- **Tree views (D250)**: Metamodel > Tree; Entity types > Entity tree; Table or Tree inside an entity type; a Tree tab
  on each entity's page. Key and value only, each level read when it is opened, coloured by data quality, with a
  filter box, open and close all and an Excel outline.
- **Models as a list or tiles (D251)** on the Models page, each with its state (active, in the library, draft, metamodel
  locked, maintenance, frozen, read-only, archived) as an icon and words (D252).
- **Data quality in every table (D252)**: the entity type table, Data entry and the grid have a Quality column and
  highlighted cells; ↻ on a row rechecks that entity at once, **Recheck all** the whole type in the background.
- **Save, roll back and commit in the grid (D253)**: ✓ and ↶ on a row with unsaved edits; Commit (or Ask to commit) and
  Discard on a row with saved, uncommitted changes, and for all of them in the toolbar; the committed rows' data quality
  is rechecked at once. Pick lists and dates open with one click.
- **Change the icon** from Actions or by clicking the icon (✎) on the model page.

## Test data (laptop, after `.\eax clean-restart`)

Protea Insurance: three quality rules (QR-01 relationship warning, QR-02 attribute warning, QR-03 naming error), Url left
out for the model, Retirement date not applicable on Actuarial Modelling (approved), Repository area on Complaints
Tracker and Landscape level on the Chief Executive (waiting), Retirement date on Fraud Analytics (rejected: ask again),
seals valid (Billing Engine), expired (Broker Portal), broken (Claims Platform) and still current (CRM), Contact Centre
Telephony retired. Fynbos Life has its own score and colours; Karoo Re a change waiting for a Super Admin and an uploaded
icon; Fynbos Commercial a rejected change. Sample insurance model is left out of the measurements and Karoo Audit 2025
(frozen) ticked in; Karoo Legacy (archived), Audit 2025 (frozen), Pilot (metamodel locked), Operations (maintenance)
and Board pack (read-only) show each state. Nothing is measured until someone asks (or the weekly schedule): press
**Measure all** on Administration > Quality first. Stale entities appear once the stale period has passed.

## Demo

0. As `user_super_admin`: Administration > Quality > **Measure all**: it runs in the background; the cards fill in.
   Administration > Containers: **+** adds an API and job server, **−** removes it.
1. `.\eax clean-restart`. As `user_model_admin`: Protea Insurance (demo estate) > **Quality**: the score, the tiles and
   the charts. Click the weakest entity type: its entities, worst first; open one and fill in what is missing; back on
   the Quality tab, **Measure now**: the score rises and the trend has a new point.
2. **Settings, weights and rules** > **+ New rule**: QR-01 "Every application serves something", relationship,
   Application Component, Serving, outgoing, at least 1, **error**. **What would it find?** lists the applications that
   serve nothing. **Save**: it waits for a Super Admin.
3. As `user_super_admin`: Administration > **Quality**: the estate score, every model, and the rule waiting; **Approve**.
   `user_model_admin` is told.
4. As `user_architect`: change an application that serves nothing and commit: refused, naming the rule; add a Serving
   relationship and commit again: it goes through.
5. As `user_model_admin`: Quality > the **Stale** tile (or any drill-down) > choose all > **Still current**.
6. **Download PDF** and **Download Excel** on the tab, on a drill-down and on the estate; in Excel, open the + on By
   type.
7. As `user_super_admin`: Administration > Quality > **Which models are measured**: untick Karoo Digital; it leaves the
   estate. In the Metamodel tab, give the Owner attribute weight 5 and override it to 8 on Application Component; open
   **New** application in data entry: the Owner field shows its weight and the meter rises as it is filled.
8. Open **QR-03 What to fix** in the reporting tool and click a bar to drill down.
9. In Claude: "What are the worst data quality gaps in Protea, and who should fix them?"

## Checks

- `tests/sql/phase12_checks.sql`: the version, the defaults, a kept measurement, the report views and their links, a bad severity refused.
- `pytest tests/test_quality.py` also covers the stored results and background jobs, the reasons per field, not
  applicable and the bulk decisions, the model icons (image types, unsafe SVGs refused) and several servers.
- `pytest tests/test_quality.py`: conditions, the four kinds of rule, who is responsible, weights (default, inherited,
  left out), settings checked, routes, jobs, commit blocking, MCP tools, a Model Admin's change waiting for approval,
  the PDF and Excel exports with their drill-down groups, the metamodel weights (D241) and which models are measured
  (D242, archived never). `tests/test_reports.py` covers QR-01 to QR-04.

## Notes

- Quality is measured on request (the tab measures when opened) and kept on the schedule or with **Measure now** (on the Quality tab and on each model on Administration > Quality).
  It reads the whole model, which takes well under a second at the supported size (10,000 entities per model).
- The data quality improvement and data staleness **wizards** come with the wizards of phase 16.3 (WIZ-021, WIZ-022).
