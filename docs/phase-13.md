# Build phase 13: architecture projects, the project library and the repository in Documents

Goal: set up an architecture project in one wizard (its purpose, models, viewpoints and artifacts, principles, ADM steps,
deliverables, people and who signs off), and keep its documents in Documents (Mayan) with versions and check-out, edited
in Office. Version **0.14.0**, migration `0022_projects`. Decisions D258 to D266, agreed with the owner on 6 Nov 2026
before building (the design is in [design-architecture-projects.md](design-architecture-projects.md); the master list
was reviewed as the workbook [EA_Explorer_Master_Template_Repository.xlsx](requirements/EA_Explorer_Master_Template_Repository.xlsx)
and kept whole).

Phases 13 (documents) and 15 (TOGAF projects) are merged and built in four parts: **13** (this one), **13.1** approvals,
steps and the dashboard, **13.2** the registers, **13.3** ADM cycles, child projects, merging back, generating
artifacts from the reports, and library projects (D265).

## Status: built, waiting for the owner's test

## What phase 13 delivers

### The project library (D258)

- Kept by **Super Admins only**: Administration > **Project library**. Loaded from the reviewed workbook on every start
  (tools/build_project_library.py writes `eax/seed/project_library.json`); only what is missing is added, so changes
  are kept.
- What it holds: the 4 purposes (Strategy, Portfolio, Project, Solution; a project may name its own), the 13 ADM
  phases, **116 steps**, **171 deliverables and artifacts** (each with every source that names it) and the **51 master
  folders**. On a laptop also a sample principles library (48 principles of the fictional
  Meridian Assurance Group).
- **The TOGAF templates are not in EA Explorer** (they are The Open Group's; only their names are). A Super Admin
  loads the licensed files once (D262, below). They are stored in Documents exactly as uploaded, never branded.

### Template libraries and the setup before the first project (D264)

Projects take their starting documents from **template libraries**:

| Library | What it is |
| --- | --- |
| **EA Explorer** (ours) | Ships with EA Explorer: a file for every one of the 171 deliverables and artifacts, in its folder. 108 are the owner's worked samples with the organisation's name replaced by **[Organisation]**; 63 are plain starter files (Word for documents, Excel for catalogues, matrices and registers, PowerPoint for diagrams). Nothing from The Open Group's templates. In `library/templates/ea-explorer` |
| **TOGAF 10** | The Open Group's 23 template deliverables by name; a Super Admin loads the licensed files once (D262). Never in git, never changed |
| **Your own** | Any number. **⬇ zip** on any library (a folder for every deliverable and artifact), rebrand or replace the files, add documents to any folder, zip it and upload it under a new name. A file in an item's folder is a template of that item; files in other folders are templates of that folder. Stored in Documents in the background (*loading*, then the number of files) |

**The setup** (Administration > **Project library**, Super Admins): before the first project, tick the libraries to
offer to projects and press **Finish the setup**. Until then *New project* is off and the Projects page says why. The
four ways the owner asked for are all there: load TOGAF; download ours and upload it back as your own; add documents to
its folders before uploading; or use ours as it is. Libraries can be added, offered or withdrawn at any time after.

### Creating a project: the wizard (D258)

**Projects > New project** (any user with a global role; the creator becomes its Project Admin). Eight steps:

1. **Basics**: name, purpose, description; optionally a parent project (a rerun, 13.3).
2. **Template libraries**: the libraries offered to projects (and your own private ones); pick one or more, or **add a
   library** (a zip) here: it is yours and this project's until a Super Admin offers it to every project. **Every**
   template the picked libraries have for a chosen item is copied into its folder, named `<library>-<document>` (for
   example `TOGAF 10-TOGAF® Template - Architecture Vision.docx` and `EA Explorer-Architecture Vision.docx`).
3. **Models**: add existing models, derive a child of one (a copy, with lineage), or create a new one.
4. **Viewpoints and artifacts**: pick the viewpoints the project uses.
5. **Principles**: from the library, or the project's own (a child inherits its parent's).
6. **Phase by phase**: for each ADM phase, its **steps** (accept, remove with a reason, add your own; removed standard
   steps always show crossed out) and its **deliverables and artifacts** from the library (chosen, or left as
   **not_for_use**; each marked Deliverable or Artifact; add your own).
7. **People and sign-off**: who is on the project in which role, and who signs off, for the whole project or per phase.
8. **Review**: everything chosen, then **Create**.

The models are copied in the background as for a new model; the repository is built in Documents in the background.

### Project roles (D259, D261)

| Role | May |
| --- | --- |
| Project Admin | everything on the project: people, sign-off, items in or out of use, undo check-outs |
| Lead Architect | as Project Admin |
| Architect, Model Admin, Model Sub Admin | contribute: upload, check out, check in (Model Admin also undoes check-outs) |
| Stakeholder | read; comment, approve or reject documents (13.1); not contribute |
| Super Admin | everything on every project |

Models the project **creates or derives** give its members a model role (Project Admin, Lead Architect and Model Admin
→ Model Admin; Model Sub Admin → Model Sub Admin; Architect → Architect; Stakeholder → Report Viewer). Models **added**
keep their own people. Laptop test users: `user_project_admin`, `user_lead_architect`, `user_stakeholder` (with the
existing architect, model admin and sub admin users).

### The repository in Documents (D260)

- Each project is a **cabinet** in Mayan, with a cabinet for each master folder and each item (deliverable or
  artifact). Items not chosen get the same folder with **not_for_use** in its name; they can be brought into use (or
  put out of use) later by the Project Admin or Lead Architect.
- Every template of the project's libraries for a chosen item is copied into its folder as a starting document,
  named `<library>-<document>`; templates of other folders go into those folders. A project waits while one of its
  libraries is still loading.
- **Repository** tab: **a tab per ADM phase** (with how many items are in use), each item with its folder, its
  **templates** (⬇ straight from the project's libraries, even before the repository is built in Documents), its documents
  and actions: **Upload**, **Download**, **Check out**, **Check in** (the new file and a comment become the next version),
  **Undo check-out**, history.
- **Steps** tab: **tick a step when it is done** (anyone who contributes; who and when are shown); the Lead Architect or
  the Project Admin reopens it. Removed standard steps stay crossed out with the reason.
- **Start page**: until the template library setup is done, a highlighted **Set up architecture projects** tile at the
  top (to the setup for Super Admins; *waiting for a Super Admin* for others).
- **Edit in Office**: check out, download, edit, check in. While checked out nobody else can check in a new version (in
  EA Explorer and in Mayan). The person who checked out, the Lead Architect, a Model Admin, the Project Admin or a Super
  Admin may undo a check-out; the person is notified.
- Mayan keeps the files and versions; EA Explorer keeps the rules, the screens and who did what (one service account
  talks to Mayan; each event records the person). If Documents are still starting or off, the project shows
  *Repository: pending* and the build is retried every minute.

### The projects' own connection string (D266)

The project tables (schema `proj`) are reached through `EAX_PROJECTS_DB_URL` (empty: the repository's database, as
now), so they can move to a database of their own later. Nothing in `proj` points into the other schemas (a project's
models are kept by guid) and no query joins across them. See [Operations](operations.md#the-architecture-projects-database-d266).

### Documents' memory (D263)

Mayan was stopped for running out of memory (1.66 of 2 GB). On a laptop it now runs 2 web workers and one task per
worker queue, with 3 GB.

### The TOGAF templates: a one-time task (D262)

After the first start a Super Admin:

1. Downloads **The TOGAF Standard, 10th Edition: Template Deliverables** (The Open Group I094) from
   <https://publications.opengroup.org/i094> (a licence from The Open Group is needed).
2. Unzips it into `library/templates/togaf` in the EA Explorer folder (or the folder set by `EAX_LIBRARY_DIR`). The
   folder is never committed to git.
3. Administration > **Project library** > **⬆ Upload the TOGAF zip** (or **⬆ zip** on the TOGAF 10 row) and choose the zip
   exactly as downloaded (zips inside it are opened too). Each file is matched to its TOGAF template by name and stored in
   Documents unchanged, in the background; the row shows *loading*, then how many are loaded.

Or unzip it into `library/templates/togaf` (or the folder set by `EAX_LIBRARY_DIR`; never committed to git) and press
**Load templates from the folder**; a single template can also be uploaded on its own line. `eax up` reminds you of the
task until the folder holds the files.

## Not in this phase

- **13.1**: approvals (requests to the sign-off people, comments, approve or reject, evidence from outside, each logged
  as a decision; the document life cycle with its states in Mayan), the project
  dashboard (phase completion), documents linked to entities and picked from our screens, Mayan in backups.
- **13.0.1** (D267), a design session first: principles in the TOGAF format on a screen of their own (a project's copy
  editable), an execution phase for a project, changing a running project, creating a project fully in the background.
- **13.2**: the registers (decisions and ADRs, dispensations and changes, compliance and contracts, RAID, requirements,
  stakeholders, principles, lessons learned). Custom registers are parked.
- **13.3**: further ADM cycles, child projects (inheriting principles, the parent's artifacts read-only in the child's
  reference library), merging back per file, generating artifacts from the report views; **library projects** and
  copying a project (D265).
- Pictures inside the rebranded samples still show what they showed (only the text is rebranded); renaming or deleting
  a template library, and choosing one file per item instead of all of them, are not in this phase.
- The Mayan calls (REST API v4) were written to its documentation and are first run against a real Mayan in your test.

## Demo

1. `.\eax clean-restart`; when *All up*, sign in as `user_super_admin`.
2. **Projects**: the sample *Protea Target Architecture 2028 (sample project)* is there (made with EA Explorer's
   library), but there is no *New project*: the notice says the template library setup comes first.
3. Administration > **Project library**: the setup notice with the four ways. Do the TOGAF one-time task (*Load
   templates from the folder*). **⬇ zip** on EA Explorer: open a few files (worked samples with [Organisation],
   starter files). Rebrand two of them, add a document to the Architecture Vision folder, zip the folders and upload
   the zip as *Thotnr 2027*: *loading*, then *n files*.
4. Tick EA Explorer, TOGAF 10 and Thotnr 2027; **Finish the setup**. *New project* appears on Projects.
5. Open the sample project: Overview (people, sign-off, models, template libraries, viewpoints), **Repository**
   (*ready*; each item's folder holds *EA Explorer-...*), Steps (one removed, crossed out), Principles.
6. **Projects > New project**: walk the eight steps; in *Template libraries* pick EA Explorer and TOGAF 10 and add a
   library from a zip (it shows *not shared yet*); derive a child of Protea Insurance; remove a step with a reason;
   leave some items not_for_use; add `user_stakeholder` as Stakeholder; Create.
7. Repository: the Architecture Vision folder holds *EA Explorer-Architecture Vision.docx* and *TOGAF 10-TOGAF®
   Template - Architecture Vision.docx*. Upload a .docx into an item; **Check out**, Download, edit in Word, **Check
   in** with a comment; history shows both. Open Documents (Mayan): the project's cabinet, the version list.
8. Sign in as `user_stakeholder`: the project opens, but no Upload or Check out. As `user_lead_architect`: undo a
   check-out made by someone else; they get a notification.

## Checks

| # | Check | How | Expected |
| --- | --- | --- | --- |
| 1 | Upgrade | `.\eax clean-restart` | version 0.14.0; schema `proj` with the library loaded |
| 2 | Library | Administration > Project library | 13 phases, 116 steps, 171 items, 51 folders; libraries EA Explorer (171 files) and TOGAF 10 (0 of 23) |
| 3 | Setup gate | Projects before the setup | no *New project*; the notice; `POST /api/v1/projects` answers 409 |
| 4 | TOGAF | one-time task | 23 of 23 loaded; the togaf folder not in `git status` |
| 5 | Own library | download EA Explorer's zip, change it, upload it | *loading*, then ready with its files; private to you until shared; Super Admin shares it |
| 6 | Wizard | New project, all eight steps | created; you are its Project Admin; members notified |
| 7 | Templates copied | the new project's Repository | every picked library's template in each chosen item's folder, named library-document |
| 8 | Derived model | a derived model in the wizard | the copy appears in Models; members have model roles (D261) |
| 9 | Repository | the new project's Repository tab | *building*, then *ready*; cabinets in Mayan, not_for_use folders for items left out |
| 10 | Check-out | check out, then check in as another user | refused while checked out |
| 11 | Undo | Lead Architect undoes someone's check-out | done; that person notified |
| 12 | Stakeholder | as `user_stakeholder` | reads; no upload or check-out |
| 13 | Documents off | Services: Documents off | the repository says Documents are switched off; on again: built |
| 14 | Mayan memory | `docker stats` after a while | dms stays under 3 GB; not OOMKilled |
