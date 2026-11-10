# Build phase 13.0.6: the project repository as a table

Goal: the project repository becomes a table, opened on the phase you came from. In it you can:
- see each document class and every document under it;
- check documents out and in with your own version;
- tag, accept or send documents for approval;
- archive or delete them.

- Version **0.14.6**, migration `0028_repository_table`.
- Decision **D290**, from the owner's requests and answers of 7 Nov 2026.

## Status: accepted and closed by the owner (8 Nov 2026, D323)

## The table

- **Where it is.**
  - **Repository tab:** a tab per phase, plus **All phases**. It opens on the phase in the link (`#/projects/<id>/repository?phase=B`).
  - **Home (ADM landing page):** the same table, in a shorter form, for the phase selected on the wheel. Its link
    **open the full repository** opens that phase.
- **Rows.** One row per **document class** (a deliverable or artifact), for example *Architecture maturity assessment* or
  *Organisation decomposition diagram*. Under it come all of its documents, and a class can hold any number.
- **Columns:**
  - Document, with its D/A mark and tags
  - State: Draft, In review, Approved, Accepted or Rejected (and archived or deleted, when shown)
  - **Your version** (free text)
  - **System version** (counted automatically)
  - Checked out (by whom)
  - Last checked in
  - Approval
- **On each class:** + Add a document, ⬇ template, **Won't need this** (with a reason) or **Needed again**.
- **At the top:**
  - **Add a document** (to any class, or to a **new class** made on the spot)
  - **Add a document class**
  - Filters by **tag** and by **file type** (pptx, docx, xlsx…)
  - **Show the not needed**, **Show archived**, **Show deleted documents**

**Who can do what.** Anyone on the project who contributes can:
- add documents and classes;
- mark a class not needed;
- tag documents;
- accept a document;
- send one for approval;
- archive or delete a document.

Stakeholders only read.

## Editing a document

1. **Check out.** One click, no questions. The file downloads, and nobody else checks in a new version meanwhile.
2. Edit it in Office.
3. **Check in…**
   - Choose the new file.
   - Say **what changed** (required).
   - Give **your version**. Left empty, it is put in for you: the last one's number up by one (0.3 draft becomes 0.4,
     v2 becomes v3), or 0.1 when there is none yet.
4. The system version goes up by one.
   - An accepted or approved document goes back to **Draft**; the accepted or approved version stays recorded.
   - An open approval request is withdrawn.

**History** lists every action with who, when, your version, the system version and the note. That covers uploads,
check-outs and check-ins, tags, accepted with its evidence, approval, archive, delete and restore.

## Accept, or send for approval

- **Accept…**
  - The document becomes **Accepted** now.
  - **Evidence** is needed: a note saying why (required) and a file, such as the email or the minutes (optional).
  - The file is kept in `00_Project/Sign-off evidence`.
  - The approval column shows who accepted it and the note.
- **Send for approval** (any document, not only deliverables). The phase's sign-off people are asked (or the whole
  project's, where a phase has none).
  - It is **approved when the quorum approves**. The quorum is a number set per project, in the wizard (People and
    sign-off) or under About › People › Change. Left empty, it is a majority. It is never more than there are people.
  - **Any rejection rejects it.** A rejection needs comments.
  - The table and the Sign-off tab show "needs N of M" and who is still to decide.

## Archive and delete

**⋯** on a document offers two choices:
- **Archive**: hides it; restore it any time.
- **Delete with all versions**: asks first.

Both are marks, not removals: nothing leaves Documents.
- Archived and deleted documents are **not loaded** with the project, so a large repository stays fast.
- They show only when **Show archived** or **Show deleted documents** is ticked, and **Restore** brings them back.
- They cannot be checked out or sent for approval until restored.

## Choosing documents in the project wizard

**Phase by phase** has a **File type** filter. It shows only the deliverables and artifacts that have a template of that
type. **Choose these** ticks them, copying only their templates of that type.

## API

| Method | Route | What it does |
|---|---|---|
| POST | `/projects/<p>/items` | Add a document class (`name`, `phase`, `kind`) |
| POST | `/projects/<p>/items/<i>/not-needed` | `reason`, or `undo: true` |
| GET | `/projects/<p>/documents?show=archived,deleted` | The documents, with the hidden ones asked for |
| POST | `/projects/<p>/documents/<d>/checkout` | Check out (nothing asked) |
| POST | `/projects/<p>/documents/<d>/checkin` | Multipart: `file`, `comment` (required), `user_version` (optional) |
| POST | `/projects/<p>/documents/<d>/tags` | `tags: [...]` |
| POST | `/projects/<p>/documents/<d>/accept` | Multipart: `note` (required), `evidence` (optional) |
| POST | `/projects/<p>/documents/<d>/archive` · `/delete` | Archive or delete it, or `undo: true` to restore |
| PUT | `/projects/<p>/people` | Adds `signoff_quorum` (empty: a majority) |

## How to check it (after `.\eax clean-restart`)

1. **Open the repository.** Open a project, select phase B on the wheel, and click **open the full repository**. The
   Repository tab opens on B.
2. **Add documents.**
   - **Add a document**, choose **＋ A new class…**, name it *Capability heat map*, and add a file with version 0.2.
   - Add a second file to the same class.
3. **Edit one.**
   - **Check out**: it downloads.
   - **Check in…**: try it without "what changed" (refused). Then fill that in and leave the version empty: it becomes 0.3.
4. **Tags.** Tag two documents *Claims*, then pick *Claims* in the Tag filter. Try the **Type** filter with xlsx.
5. **Accept.** On a draft, **Accept…** with a note and the minutes as a file. It shows Accepted, and History shows the
   evidence.
6. **Approval.**
   - Set the quorum to 1 (About › People › Change), then **Send for approval**. One approval makes it Approved.
   - Send another and reject it with comments: it is Rejected.
7. **Archive and delete.**
   - Archive one document and delete another (⋯). Both disappear.
   - Tick **Show archived** and **Show deleted documents**: they are back, faded, with **Restore**.
8. **Won't need this.** Mark a class with a reason. It hides until **Show the not needed** is ticked; then **Needed again**.
9. **Wizard.** Edit the project › Phase by phase, pick **File type: pptx**, then **Choose these**.

## Also in this phase (owner, 7 Nov 2026, evening)

**Steps**
- Steps are added at any time (Steps tab and the Home page, **＋ Add a step**, with an optional due date).
- Ticking a step records who did it and when as a **sub step** of the same name under it.
- **＋ sub step** opens the step again, to complete later (with a due date and a note). Unticking takes the last
  completion back; a sub step opened by hand opens again instead.
- Saving the project wizard keeps the sub steps.

**Models**
- Each model shows **what kind of model** it is: root metamodel, library model, new (from a metamodel), copy of a
  model, copy at a tag, from a library model, or child (merges back). It shows on the Models list, the model page, the
  project's models and the wizard.
- **Select existing models** has filters: name, kind of model, metamodel, industry, owner, status, archived too.
- **A new model from a tag**: derive from an existing model as it was at one of its tags. It is always a separate copy,
  never a child (it cannot merge back).
- **＋ Add or make a model** on the project page opens the edit wizard on Models, so models can be added at any time.

**The project wizard**
- A step's required fields must be filled before moving on (the step tab shows a red dot, and Next waits).
- The models come first; a new model's suggested name follows the project's name once it is given.
- Phase by phase shows the ADM cycle to choose the phase from.
- Goals and outcomes are two grids, with **More about the goals** (rich text).
- Sponsor has **More about the sponsor** (rich text).

**The menu.** Under the five areas, every menu there was before comes back: Start, Models, Projects, Library, Compare,
Gap analysis, Common analysis, Change log, MCP, Administration, API.

**Sample projects.** On the laptop there is one sample project per project template (14). Between them they use every
way a model joins a project.

**Documents (Mayan) fixes, checked against Mayan's own source**
- A top folder is made with `parent: null`.
- Folders are found through their parent's children, because the cabinet list does not filter by label.
- Check-out is `POST /checkouts/`.
- A new version is sent as `file_new` with `action` 1.
- Tags are found page by page.

**Repository build fixes**
- Only one runner builds a project at a time.
- A build cut off by a restart is taken up again after 15 minutes.
- **Build now** shows in every state but ready.
- A class brought back into use loses its "(not_for_use)" folder suffix (and gets it when put out of use).
- Adding, choosing or not needing a class rebuilds from any state.
- Messages from Documents are put in plain words.

**Other fixes**
- Editing a project no longer drops the editor's Project Admin role.
- Finish accepts "merge and freeze" and "freeze".
- A failed model copy no longer leaves a project half made.
- **Send for approval** says when nobody is set to approve.

## And later that evening (D291)

**The project page**
- **Views**: the project's views by ADM phase. Each one opens in the project model you choose; models that can
  show every element type come first (✓), the others say what they lack. A view can be moved to another phase.
- **Reports**: the project's status phase by phase (steps done, classes with documents, documents by state, checked
  out), what is waiting for approval, the goals, CSV for Excel, and each model's reports.
- **Gaps**: a new gap analysis between two of the project's models, and the ones already made.
- **Compare**: two of its models side by side, and the common analyses of its models.

**Back up and restore** (About tab, Project Admin)
- **Back up now** keeps the project's rows, the models it works on and the latest version of each document in one file
  (`.eaxproject.zip`). Download it or delete it there.
- **Restore as a new project** brings it back:
  - models the project made come back as new models;
  - models it worked on in place, or refers to, are linked again;
  - the repository is built again and the documents are put back;
  - goals are tagged with the new project.
- **Project admin › Wizards › Restore a project from a backup file** restores a file from here or another installation.
  All of it runs in the background.

**Build now** is a background task in the task drawer. While the repository is only waiting, its notice is one line.

**MCP**: tools and prompts to build with an assistant (see [mcp.md](mcp.md)).

### How to check it
1. Open the sample Protea transformation project and look at its new tabs.
   - **Views**: click B, change the model for VP-05 and open it.
   - **Reports**: download the CSV.
   - **Gaps**: Protea Insurance to Protea claims target 2028, then + New gap analysis.
2. Back up the project:
   - **About › Back up now** (the task drawer shows it);
   - **Restore as a new project**: the new project opens, with its documents in the repository.
3. MCP: ask your assistant to "build a model for our claims capabilities" and to "set up a cloud migration project".
   It calls how_to_build and asks before it creates anything.

## Backups with documents (D292)

- **Infrastructure backup**: already held all of Documents (its database and every file version). Administration ›
  Backups now says so (**✓ Documents** in Holds), and restoring *full*, *app+data* or *files* puts it back, on the screen
  and with `.\eax restore`.
- **Application backup** (**Back up every model and project now**, the schedule, or `.\eax app-backup`): every model as
  before, and every project with the latest version of each document. **Restore all** (screen, or `.\eax restore-app`)
  puts the models back, then each project over itself; its repository is built again, changed documents get the
  backed-up file as a new version, missing ones are uploaded again, unchanged ones are left alone.
- **Project backups** on Administration › Backups: every project, **Back up now**, Download, **Restore as a new project**,
  **Upload and restore**, and for Super Admins **Put back over itself** (with the models it made).
- Restored documents are put back whenever the repository is next built (the restore task, the minute job or Build now),
  so they come back even when Documents was down during the restore.

### How to check it
1. Administration › Backups: an infrastructure backup shows **✓ Documents**.
2. **Back up every model and project now**. Open the backup (▸): the projects are listed with their document counts.
3. In a sample project, add a document and check in a new version of another. **Restore all…** on that backup: the added
   document is gone and the other has the old file as its newest version (History in Documents keeps both).
4. In cmd: `.\eax restore-app latest` does the same and builds the repositories as it goes.
5. **Project backups**: Back up now on a project, then **Restore as a new project**, and **Put back over itself**.

## Review fixes (D293)

Before the owner's test, the code was reviewed for bugs and inconsistencies. Fixed:
- **Repository:** a change made while the repository is being built is built right after; a renamed project keeps its
  folder in Documents (the folder takes the new name); a long build is not started twice.
- **Approvals:** two people approving at the same moment are both counted; one open request per document; no decisions
  on a frozen project; requests of deleted documents are not listed.
- **Documents:** check-out can't be taken twice, and a check-out left only in Documents is freed; the evidence file has
  the 200 MB limit; archived and deleted documents are not counted, and are not copied when a project is merged.
- **Finishing:** if it fails, the project's status goes back and the copies made go to Documents' trash.
- **Wizard:** saving keeps steps added on the Steps tab meanwhile; goals from a derived project can be removed; the File
  type filter starts again on each phase; a typed tag is kept on Save; the People step names the editor's real role.
- **Screens:** each project opens with its own filters; the repository's filters can always be cleared; Select existing
  models shows archived models when Status is archived; the Projects menu is lit on its pages; labels for screen readers.
- **Backups:** the About tab, Project admin and Administration › Backups use the same restore dialogs and local times;
  a restore over a project keeps its id and its links; libraries are linked again by name on another installation;
  documents are put back only after the restore is kept; only "not found" in Documents means a document is gone.

## Stakeholders, completion and the Home tabs (D294, D295; owner, 8 Nov 2026)

**The stakeholder matrix** (project tab **Stakeholders**, and a wizard step after Sponsor)
- Each stakeholder: name (a person or a group), role, organisation, TOGAF category, email and phone.
- **Power** and **interest** (High/Medium/Low) place it on the grid and give its class: Key players, Keep satisfied, Keep
  informed or Minimal effort. The class can be set by hand (✎ shows it was).
- **Position**: ability to disrupt; understanding and commitment now and needed (a gap is marked); support needed.
- **Concerns** and the views and document classes that answer them (one with none is flagged).
- **Engagement**: approach (from the class unless set), how often, channel, who looks after them, next contact (overdue
  in red), last contact (the latest discussion note).
- **Notes** (rich text) and **Discussions**: any number of dated rich-text notes.
- A new project starts with the kind of project's suggested stakeholders; a derived one copies its parent's.
- CSV for Excel; in backups; MCP tools.

**Completion**: steps done plus deliverables approved or accepted, each counting once; shown on the project's header and
Home, in Project admin and on Architecture work. It goes down again when a step is added or taken back, or a deliverable
goes back to Draft.

**Steps**: completing a sub step no longer completes its step; someone ticks the step itself. **+ sub step** opens the
step again.

**Home** has three sub-tabs: Documents, Steps, Views. **Gaps and comparison** is one project tab with gap analyses,
comparison and common analyses.

**Also**: several files at once in Add a document; the wizard's files wait for the repository; the lists refresh while a
repository is being built, and the task says the repository is still being built.

### How to check it
1. New project › Transformation: the Stakeholders step lists ten suggestions with their classes and the grid; change one,
   remove one, add one.
2. The project's **Stakeholders** tab: the grid and the matrix. Open the CIO: set commitment now Low and needed High (the
   gap shows), tick a view and a document class, a next contact in the past (overdue). Discussions › + Note a
   discussion: it becomes the last contact. Set the class by hand. CSV.
3. As `user_stakeholder`: the matrix shows, nothing can be changed.
4. Derive a project from it: the stakeholders come too.
5. Completion: tick a step (it rises), + sub step on it (it falls), tick the sub step (it stays), tick the step (it rises).
   Approve a deliverable (it rises).
6. Home: Documents, Steps and Views sub-tabs; the document names no longer wrap under the D/A mark.

## Not in this phase (to-do list)

- Email for approval requests and decisions (the email phase).
- Purging deleted documents from Documents for good.
- Principles (to discuss); example content (to design); LDAP and Entra ID sign-in (much later).

## Later on 8 Nov 2026 (D296, D297)
- Links and the Reference area; library projects; reference copying when a project is made.
- Project page layout: Home sub-tabs, Models tab, Gaps and comparison, sign-off link and "not signed off yet", Principles by area.
- Sign-off requests under Requests I sent; Dismiss all and Clear them all for notifications; slimmer search box fixed.
- Project admin: three library tabs; open a template library read only; new template in Project templates.
- SQL window: database diagram for models and projects.
- Architecture work: Projects/Models tabs, tiles or list, filters, pins.
- Tests: tests/test_project_layout_links.py.
- Tasks tab (D298): proj.tasks and proj.task_statuses; eax/project_tasks.py; ProjectTasks.jsx.
