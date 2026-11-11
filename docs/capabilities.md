# What EA Explorer does today (version 0.19.0)

One page for anyone weighing EA Explorer up: what is **built and in the box today**, area by area, and what is still
**planned**, with its build phase. "Planned" adds to what is already there; it does not mean an area is missing.
Every phase in detail: [build-phases.md](build-phases.md). Decisions: [decisions.md](decisions.md).

| Area | Today |
| --- | --- |
| Cost and licence | Free and open source (AGPL-3.0); no charge per user, per object or per module. Self-hosted: one laptop, one server or your cloud |
| Metamodel and standards | ArchiMate 4 and the TOGAF 10 content metamodel built in; your own metamodels, edited, versioned, reviewed and pushed down to the models that use them |
| Diagrams and visual analysis | Over a dozen kinds of picture drawn from the repository itself, so they are never out of date; each can be saved as a drawn view |
| Reports and BI | 30 standard reports and 49 views (each as diagram, catalogue, heat map, matrix and relationship list), roadmaps, value stream maps, gap, comparison and common analysis, quality dashboards; Apache Superset for your own |
| AI | An MCP server with about 120 tools and 11 guided prompts: your own language model reads, analyses, cleans up and changes models (copy, dedupe, override the parent, every model wizard), previewing every change for your yes and tagging first, as you and with your permissions; every call in an AI activity log |
| Collaboration and governance | Private changes until committed, conflicts at commit, child models merged back, reviews and approvals, sign-off with a quorum, stakeholder acceptance of answers, a full change log |
| Projects (TOGAF ADM) | Architecture projects from 14 templates, the TOGAF 10 library (13 phases, 116 steps, 171 deliverables and artifacts), key questions, Business Model Canvases, the Architecture Repository |
| Documents and libraries | Document management (Mayan EDMS) inside projects, the reference library, the enterprise and project libraries with search |
| Integration | A REST API (OpenAPI), signed webhooks, Excel and CSV in and out with mappings, model packages, the MCP server |
| Operations | One command (`eax`) and a console, start-up in two tiers, health, tagged backups and restores, every service switchable |

## The main screens
The top bar's main menu: **System admin**, **Model admin**, **Project admin**, **Architecture work**, **Architecture
repository**, **Reference library** and **Everything else**; and the older menu below it: **Start**, **Models**,
**Projects**, **Repository**, **Library**, **Enterprise library**, **Reference library**, **Compare**, **Gap analysis**,
**Common analysis**, **Change log**, **MCP**, **Administration** and **API**. Beside your name: **Documentation**, ? Help,
the navigation style, quick jump and Sign out.

## Documentation
- **Documentation** (beside your name, for everyone signed in): every document that ships with the version you run,
  grouped (getting started, using EA Explorer, administration and operations, command line, reference, release notes,
  design and decisions), each shown as a readable page with links between them, a search across all of them, and
  Download and Print or save as PDF (D550)
- The same documents in the **Enterprise library**, folder **EA Explorer documentation**, refreshed from the running
  version at every start, so they are always the documents of that version: new ones added, changed ones replaced,
  ones no longer shipped removed (D550)

## Finding your way
Built ([navigation.md](navigation.md), D478–D481):
- **Three ways to show a page's tabs**, chosen by each person beside their name or on My profile: **Grouped** (the
  default: about six groups, then tabs, then sub-tabs, with a breadcrumb), **Menu** (a menu down the left that folds to
  icons) or **Classic** (every tab in one row). The same links work in all three.
- **⋯ Actions** on each tab: what makes sense there and the person may do.
- **Right-click on any entity** (rows, cards, links): open, edit, graph, history, related, add to a view, delete.
- **Quick jump, Ctrl+K**: go to any tab, action, model or project by typing; near spellings work.

## On-screen help
- **? Help** (top bar) or **F1** anywhere: a help panel beside the page for what is on the screen (the pop-up, the wizard step, the sub-tab, the tab, the page), with a search over all the help (D531)
- **?** on every pop-up; a short **tooltip** on every button, tab and field (D531)
- One help catalogue for all of it, and a test that fails the build when a screen has no help ([help-catalogue.md](help-catalogue.md), D530, D532)

## Cost and licence
- **AGPL-3.0, no licence fees**: every user, every model, every module. The open-source parts it uses are listed in
  [licences.md](licences.md).
- **Runs where you choose**: a laptop (Docker Desktop), one server, or your cloud; your database, your backups, your
  network. Nothing is sent anywhere unless you connect it.

## Metamodel and standards
Built:
- **ArchiMate 4** seeded in full, and **six EA Explorer extensions** for TOGAF business architecture (value stream
  stage, product lifecycle stage, business scenario, control, contract, measure), each marked as an extension (D345),
  in the ArchiMate 4 domains and colours, with the allowed relationships of the owner's ArchiMate 4 guide (D392, D393).
- **Relationship multiplicity** on allowed relationships (1, `*`, 0..1, 1..*), checked by the data quality checks (D395).
- **The TOGAF 10 content metamodel**, and the TOGAF catalogues, matrices and diagrams given by views (D345).
- **Your own metamodels**: domains, entity types, attributes, pick lists, allowed relationships and validation rules,
  edited in screens or as a whole document; a **lean metamodel** to start small.
- **Link attributes** (D418): point an entity (a work package, a requirement...) at more detailed documents: one or
  more links, each with a note such as a version; any address (web, ftp, a repository document, an EA Explorer link),
  clickable where it is safe to be.
- **Versions**: every metamodel change is a published version with its note and differences; compare any two;
  **push a new version down** to the models built on it, forced or offered (phase 8.1).
- **Reviews**: a metamodel draft (by a person or a language model) waits for review, comments and approval (D115, D130).
- **Industry reference models**: Banking, Government, Healthcare, Logistics, Manufacturing, Minerals and Mining, Pharmaceuticals, Retail and Telecommunications reference models (phase 39, D470, D548: capabilities, value streams, services, processes, products, business objects and a starter application landscape, from the owner's industry packs) and Meridian Assurance, the insurance worked example (D549), beside the insurance reference model to capability level 4, and the model library to share. **Industry packs** (D546): each industry's book, workbook, metamodel Excel to study, templates, PowerPoints and ArchiMate 4 views, shipped in the repository, put into Documents at start-up and downloaded from tiles on the library's Pack tab (`eax packs`)
  your own as reference models.

Planned: ArchiMate exchange format in and out, and a conformance check (phases 33, 33.1); more industry models when the owner adds packs (39).

## Diagrams and visual analysis
Built — every picture is **drawn from the repository when you open it**, so it always shows the data as it is now:
- **Network** around an entity (1 to 3 steps), **domains** (strategy to technology, for traceability), **impact**
  (what an entity leads to or depends on, up to 6 steps) and **split** (both ways at once).
- **Hierarchy and capability maps** (nested boxes, level 1 to 4), coloured by any attribute as a **heat map**.
- **Relationship matrices** between any two types.
- **Value stream maps** (stages with the capabilities enabling each, coloured by maturity or criticality) and
  **roadmaps** (plateaus, work packages and deliverables on a timeline).
- **View diagrams** for all 49 views, and the **metamodel diagram**.
- **Business Model Canvases**, with differences between two shown in colour (D344).
- Click any box to open the entity. Every picture **opens in draw.io**, and saves as SVG, PNG or CSV.

Built (0.16.0): **drawn views** (phases 28, 29, D354): views drawn in draw.io, inside EA Explorer, with the ArchiMate 4
notation from the model's own entities (a search panel to drag them in; placeholders realised later), **two-way sync**
(D413): relationships drawn on a view go into the model at once, committed as the person (only the allowed types; deleting
a line asks: hide it in the view or delete it from the model), the model's committers edit an entity or create one from a
placeholder in its form and commit it from the drawing, the person's uncommitted changes listed in the editor to edit,
discard or commit, and a view brought up to date with the model when opened (with a note) and watched while open; draw.io's
General, Misc and Basic palettes for notes, comments, text and arrows that never touch the model (D414); each save kept as a version (with a warning when someone saved since),
Resync with the model, And/Or junctions, entities' own icons, heat maps by an attribute, exports (PNG, SVG, PDF, .drawio),
*Save as a drawn view* on every generated picture (tidied, in the ArchiMate notation), any view copied (a drawn view, a
generated picture, or a standard view's definition as the model's own view), a view as a project's evidence (a link to
the live view or one version), a stencil of all the metamodel's types whose groups each person shows or hides, and MCP
tools to draw one. Creating an entity on the drawing shows the names already in the model (the same, reordered or near spellings) with *Use this one*, and asks before making a second of the same name and type; the drawing's searches find near spellings (D454). Every type drop-down on the drawing can be typed in to find a type, with near spellings (D540). The working space (D420): the stencil on the left and a resizable bottom panel (Find in the model,
Properties, Relationships, Allowed relationships, Uncommitted changes), each pinned or folded away, in three preset
layouts (Drawing, Editing, Canvas only) remembered for the person; a pop-up on every stencil drop (bind, create, or leave
as a placeholder); related entities and allowed relationships added next to the selected object in one click; draw.io's
Format panel removed so the drawing has the room. Every view is a draw.io file kept in a views service with its own database (D405 to D409); pictures
are otherwise downloads (.drawio, PNG, SVG) that the person keeps.

## Reports and BI
Built:
- **30 standard reports** and audience dashboards in Apache Superset, each checked; heat maps and a model overview.
- **49 views**, each shown five ways (diagram, catalogue, heat map, matrix, relationships), with the TOGAF
  artifact each gives (D345).
- **Roadmaps, value stream maps, dependency and impact** (phase 8.2).
- **Compare** any two models or tags; **TOGAF gap analysis** with resolutions and work packages; **common analysis**
  across many models (phases 8.3, 13.0.5).
- **Data quality**: score, completeness, freshness, orphans, rules, trends, drilling to the entities (phase 12).
- **Project reports** and the project's completeness by phase.
- **Your own reports**: every entity type is a report view, so Superset (charts, dashboards, SQL) works on it directly.

- **KPI trends** (phase 24): a standard set per model (entities by type, applications by TIME and lifecycle, total
  cost, quality score, orphans, end-of-life technology) and each model's own KPIs (a count or a sum with a filter), kept
  on the 1st of each month and on every tag, on the model's KPIs tab and in report KR-01.
- **An OData feed** per model for Power BI and Excel: every entity type as a table, read only, signed in with your own
  user name and password (Basic), with your own permissions (phase 24).
- **A report designer**: choose a type, columns, related types and filters, see the first rows, and open it in the
  reporting tool's chart builder (phase 24). Scheduled reports are not offered (D365).

## AI (bring your own model)
Built ([mcp.md](mcp.md)):
- **Model operations from plain requests** (D458, phases 26/27): "make a copy of this model and remove all duplicates as
  you see fit", then "override its parent with it". Copy, dedupe, override the parent, refresh, merge requests, every
  model wizard and common analysis; every change is **previewed for your yes, then confirmed**, the model **tagged
  first**, and done with **your own rights** (a read-only credential only reads).
- **Analysis by an assistant**: impact of retiring something, application overlaps and TIME suggestions, cost by
  capability, end-of-life technology risk, single points of failure, heat maps, what changed since a tag, KPI trends;
  clean-up (bulk fixes, tidy names, orphans); Word reports into a project; principles and standards checks; surveys and
  maturity; usage questions for admins. Answers carry **links back** to the entities.
- **The AI activity log**: every call, your own or (admins) everyone's: the tool, the question, what it changed.
- **A remote connector**: add EA Explorer to an AI app and sign in through Keycloak in the browser (OAuth).
- **An MCP server** at `/mcp`, with **82 tools** and **3 guided prompts** (build a project, build a model, fill a
  model). Any model that speaks MCP works: hosted or local. None is shipped and nothing is sent to one unless you
  connect it.
- It works **as the person signed in**, with exactly their permissions.
- It **reads and analyses**: metamodels, entities, relationships, history at any point in time, paths and impact,
  search, views, value streams, roadmaps, comparisons, gap analyses, quality findings.
- It **builds**: models (empty, copies, children), entities and relationships in bulk, projects from templates,
  steps, documents' acceptance, key questions and their answers, Business Model Canvases.
- It **proposes, a person decides**: what it adds is the person's uncommitted change until committed; metamodel
  drafts and quality rules wait for review.

- **Plans scenarios** (phase 27.1, 0.18.0, [phase-27.1.md](phase-27.1.md)): the prompt *plan scenarios* compares a
  project's scenario models with its baseline (cost, applications, capabilities covered, end-of-life technology,
  risks, what each adds, changes and retires, the capabilities it touches, a suggested score), makes scenario models
  (the baseline tagged first), applies what-ifs ("retire X, replace it with Y") as the person's own uncommitted
  changes, and records the assessment as a Word document and a governance decision for approval; every change is
  previewed first and made only after a confirm. The project's **Scenarios** tab shows the comparison and the
  assessments.

Planned: proposals into a staging area across the whole repository (phases 26, 27).

## Collaboration and governance
Built:
- **Roles and permissions** through Keycloak (single sign-on), global and per model and per project.
- **People's skills**: each user adds their own on My profile; the Skills repository lists every user with theirs (D353).
- **Commits**: changes are private until committed; conflicts are shown at commit; roll back; Committer and History
  Viewer roles (phase 8).
- **Child models and merge back** (phases 19 and 20, 0.17.0): a child is sent for merge by its Model Admin; the
  changes are worked out three-way against the child's starting point (only the child's changes are sent; where both
  changed, a conflict); the parent's Model Admins and Committers accept or reject each change (a reason for each
  rejection), then merge it as one commit; a merge report in Word; then the child is frozen or refreshed from the parent.
  Split and merge models, propagate from parent to child (phases 8, 13.0.4).
- **Dedupe** (phase 21, 0.17.0): likely duplicates by name (near spellings) and by the same values in chosen attributes;
  compare side by side, choose the one kept and each field's value; relationships move to it; old IDs still find it;
  anyone who may change the model, committed like any change. Data entry warns when a new name looks like an existing one.
  Its own tab (Quality › Duplicates, 0.19.0): choose the type (type a few letters to find it), press Find duplicates; "No likely duplicates found" when there are none; download the result as Excel (D541).
- **Tags**: frozen snapshots to compare with, copy from or go back to.
- **Reviews and approvals**: metamodel drafts, quality rules, documents (approval by the sign-off people, with a
  quorum), the governance log (dispensations and decisions, with approval), project sign-off (D321).
- **Key questions**: each stakeholder question answered with links to the artifacts and accepted by the stakeholder (D341, D342).
- **Collecting data from people**: send stakeholders a sheet for their part of a model; review what comes back (WIZ-018).
- **Notifications and requests** (like tickets) between people, and **signed webhooks** to other systems (phase 8.1).
- **The change log**: every action, who, when, before and after; in its own database (phase 9).
- **Guided wizards** for the common jobs (phase 16.3).
- **Surveys** (phase 38.1, 0.17.0): a designer with sections, eight kinds of question and conditions; sent to people,
  global roles, models or projects through their task list and a link (never email); reminders, closing dates,
  anonymous surveys; results by question and Excel. Answers never change a model.
- **EA capability maturity** (phase 40, 0.17.0): assessments sent as surveys on nine architecture elements and six
  levels (in our own wording), scored per element and overall with targets and gaps, beside evidence EA Explorer
  measures itself, and a trend over assessments.

Planned: ownership and collaboration (22), portfolio, lifecycle and impact (23).

## Projects (TOGAF ADM)
Built (phase 13):
- **Architecture projects** from **14 templates** (transformation, as-is documentation, build or buy, cloud migration,
  acquisition and others), each with its models in roles (current, target, transition, scenario, reference, working copy).
- **The TOGAF 10 library**: 13 phases, 116 steps, 171 deliverables and artifacts, 51 repository folders.
- Scope, goals and outcomes, stakeholders and their map, **key questions**, principles, standards, the governance
  log, the charter, calendars and the Architecture Board, tracking sheets, tasks, sign-off.
- **The Architecture Repository**, the content framework and the standards information base.
- **Business architecture**: the TOGAF Phase B artifacts with their views, and **Business Model Canvases**
  (current, target, working copies marked by hand, compare and make a new one) (D344, D345).
- **Project backups and restores**, with the project's documents, models and library.
- **Other views and documents** (0.17.0): a project tab of ten sample templates (SWOT, customer journey map, value
  proposition canvas, one-page business plan, interview guide, decision record, business case, RAID log, lessons
  learned) in Word, PowerPoint or Excel, our own wording, to download and use; and the project's **own uploads**
  (D461): anyone on the project uploads files of any type (several at once, 50 MB each) with a title and description
  and downloads them; whoever uploaded one (or the Project Admin, Lead Architect or a Super Admin) replaces it, keeping
  the earlier file as an earlier version, or deletes it. Not deliverables: no sign-off, not in the repository table.

## Documents and libraries
Built:
- **Document management** (Mayan EDMS) inside each project's repository: versions, check-out, tags, acceptance,
  approval, archive.
- **The reference library**: standards, regulations and research, with search inside the documents (D300).
- **The enterprise library and project libraries**: simple pages, links into EA Explorer and the web, the odd file,
  one search box, history and undo; or point it at your own intranet instead (phase 15.2, D346 to D351).

## Integration
Built:
- **A REST API** for everything the screens do, documented with OpenAPI at `/api/docs`.
- **Signed webhooks** for what happens in EA Explorer (phase 8.1).
- **Excel and CSV**: sheets built for the types you choose (with drop-downs), loaded with a preview, column mappings
  and undo (phase 10.1); tracking sheets in and out (13.2).
- **Model packages** to move models between installations (phase 4).
- **The MCP server**, so assistants can connect EA Explorer to whatever else they reach.
- **Machine access** (phase 25, [phase-25.md](phase-25.md)): tokens, API keys and client certificates (mutual TLS on a port
  of its own) for people and service accounts, read or read-write per API area, optionally only some models or projects,
  expiry, revoke, last used, every call in the change log; they work for the API, the OData feed and MCP.

- **Published import formats and deliveries** (phase 34, [import-formats.md](import-formats.md)): the Excel format and the
  CSV format (one CSV per sheet plus master.csv), empty templates made on the fly; import sources per model; deliveries
  dropped in a source's folder (which IT may map to SFTP or a share) and taken on request (`eax import`), sent to the API
  by a service account, or uploaded; matched by type and name, only adding and changing, EA Explorer's values kept unless
  the source's win; previewed and accepted by a Committer as their committed load, or declined. The ArchiMate 4 exchange
  format once it is published.
- **A model from a metamodel workbook** (D419): any model's metamodel downloads as a workbook (types, attributes, allowed
  relationships with multiplicities, rules); fill or change it in Excel and make a new model from it, blank or added to
  an existing model.

Not planned: connectors to particular products (they write the published formats when built), ETL and outbound feeds.

## Operations
Built ([operations.md](operations.md), [command-line-and-console.md](command-line-and-console.md)):
- **One command**, `eax`, for Windows, Linux and macOS: start, stop, status, logs, health, backup, restore, services,
  passwords; and **`eax console`**, a menu for getting EA Explorer back up.
- **Banner** (System admin, D558): one message under the top bar for everyone or admins only, information, notice or
  urgent, with optional times; nothing shows unless an admin sets one.
- **Schedules** (System admin > Command centre, `eax schedule`, D559): eax commands that run by themselves in the
  installation's time zone, e.g. a nightly backup or a demo that resets every night; kept in persist/, so they survive
  resets (D558), proved by `eax test --reset-survival` (D561).
- **Command centre** (System admin, IT and Super Admins, D554): every eax command from the browser with a guided form,
  a **Console** that takes eax commands as typed and `eax console`'s menu (never a shell), and the history of every run
  with its output. Delete-everything commands for Super Admins only, behind the installation's name, "I understand"
  and a backup first. The same tabs on `eax deploy`'s page.
- **Start-up in two tiers**: people can sign in within a minute or two while the rest comes up.
- **Health** of every part in the header and on Heartbeat; the administration console with settings applied at once.
- **Backups**: tagged infrastructure backups (every database, files, certificate, configuration, versions), nightly
  and on demand, pinned, restored whole or in part; application backups of every model; project backups.
- **Every optional service can be switched off** (reports, documents, draw.io, MCP, change log, backups, library),
  with a dated copy of the configuration kept.
- **Operations insight** (phase 35, [phase-35.md](phase-35.md)): who uses what and how often, models' use and size,
  idle models (a report only), stale work; Prometheus metrics at `/api/metrics`; database health.
- **Housekeeping** (phase 35.1): retention rules (keep, archive or delete after N days) with defaults that only archive,
  a nightly job that acts only after a confirmed dry run, and a searchable archive; old history versions removed only
  after an age a Super Admin sets, never those a tag, baseline or evidence needs.
- **Scaling out** (phase 36.3, [phase-36.3.md](phase-36.3.md)): API servers set on the web page, fixed or by rules;
  more hosts, a database standby, shared storage and the library on its own server, all with Docker Compose.
- **Self-test** (phase 36.1, [testing.md](testing.md)): smoke and detailed tests (API, UI, database, security) of the
  running installation in fixtures of its own, from the web page or `eax test`, with a report and a clean-up by hand.
- **Deployment** (phase 36, [deployment.md](deployment.md)): `eax deploy`, a guided wizard in the console or a local
  web page, for five kinds: this laptop; a Linux server (on it, or from here over SSH, Docker installed if missing);
  AWS, Azure and DigitalOcean (the machine, a data disk, the firewall, a fixed address, off-site backup storage and DNS
  names created from your credentials, or a machine you have). Every password generated, `--plan` to see every
  command first, Retry or Back when a step fails. A stand-alone **installer** (eax-deploy) downloads the version you
  choose from the repository link, no copy of the repository or git needed. **Moving an installation** from one of
  its backups; **passwords kept in a key vault** too (`eax secrets`: a file, AWS Secrets Manager, Azure Key Vault);
  **Active Directory groups mapped to roles** (through Keycloak's LDAP federation or Entra ID group claims).
- **Deploy from the application** (System admin › Deploy, Super Admins and IT Admins; D555): a running installation
  deploys EA Explorer to another place (a server over SSH, or AWS, Azure or DigitalOcean): plan first, progress, Retry,
  Back or Quit, the log; run by the operations helper so it survives reloads; SSH keys and cloud credentials for the
  run only unless kept, never shown again; the history of every target. Fleets of installations: release 2.
- **Updates** (phase 36, [phase-36-updates.md](phase-36-updates.md)): System admin › Updates and `eax update` move to a
  newer release from the public git repository (Prod, RC and Latest channels; forward only), with a pinned full backup
  of the code, databases, files and configuration first, one release at a time, built on the host; a failed step stops
  for Retry or Roll back (`eax rollback`); now or at a time, with a banner beforehand and What's new afterwards.
- **Releases** (8.5, [release-process.md](release-process.md)): CI on every change, versioned releases with notes
  (`tools/release.py`), a supported-versions policy, and the administrators told when an update fails or a version is
  out of support.

Planned: deployment kinds and scripts, upgrades, test automation, scale-out ([story-load-balancing.md](story-load-balancing.md))
and real-time mirrors ([story-real-time-mirrors.md](story-real-time-mirrors.md)) (phases 35 to 37).
