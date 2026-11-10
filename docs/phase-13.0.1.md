# Build phase 13.0.1: setting up and running an architecture project

Goal: a project is set up with everything TOGAF expects at its start: its models, scope, goals and outcomes, sponsor,
and notes and files. It can change while it runs. People work on it from a landing page built around the ADM crop
circle, deliverables are signed off, and a finished project is frozen or merged into another project.

- Version **0.14.2**, migration `0024_project_setup`.
- Decisions **D274 to D279**, from the owner's 22 points and answers of 7 Nov 2026.
- It takes the place of the 13.0.1 design session (D267). It pulls in "child projects and merging back" from 13.3 and
  "changing a running project".
- The approvals workflow and the dashboard stay in 13.1. Email alerts get a phase of their own.

## Status: accepted and closed by the owner (8 Nov 2026, D323)

## What it delivers

### The wizard, models first (D274, D280)

The wizard has 13 steps:

1. **Models**
2. **Primary working model**
3. Basics
4. **Scope**
5. **Goals and outcomes**
6. **Sponsor**
7. **Notes and files**
8. Template libraries
9. Views
10. Principles
11. Phase by phase
12. People and sign-off
13. Review

**Models** is where the wizard starts.
- **+ Select existing models** picks one or more models. Each is **worked on** or **referred to** (read only).
- **+ New model…** opens the new-model wizard. Choose how the model starts, then give its details (source, what is
  copied, name, description). Add as many new models as you need. Most projects have two: the current state and the
  target state.

| How it starts | What it makes |
|---|---|
| **Create empty** | A metamodel only, from a root metamodel or a library model |
| **Derive from an existing model** | A separate copy: metamodel only, or metamodel and content |
| **Derive and keep the parent-child link** | A child of a project model, which can merge back later |

**Read access.** Everyone on the project can read the models it refers to or adds. Whoever has no role on a model gets
Report Viewer. This needs the model's Model Admin (the database checks it):
- if the person saving is that Model Admin (or a Super Admin), the access is given at once;
- otherwise the model's Model Admins get a request in the application, listing who needs access.

**Primary working model.** Choose which model the goals and outcomes go into (usually the target state), or **None**. A
project without goals is fine: a library, documenting the current state, reports.

**Goals and outcomes** are **Goal** and **Outcome** entities in the project's model:
- Each outcome realises its goal, and has a measure and a target date.
- Every entity is tagged `project:<id>` so the project can find it again.
- If the model's metamodel is still being copied, the goals wait and are written when the copy is done.
- A model without Goal and Outcome types is refused at once, with the reason.

**Scope** follows TOGAF's four dimensions:
- breadth;
- depth: strategic, segment or capability;
- time: start, end and target horizon;
- architecture domains.

**Sponsor:** the name, role and contact, and their asks: what they want, by when, and how success is judged.

**Notes and files:**
- Notes are rich text. The server cleans them, so only plain formatting is kept.
- Files are uploaded as soon as the project is made, into `00_Project/Project files`.

**Derive from another project** (Basics › Start). Frozen projects can be chosen too.
- Filled in from the parent: its scope, goals, steps, deliverables and artifacts, views and libraries.
- Its principles are inherited.
- Its models are listed as "referred to"; change each one freely.

### Editing a running project (D275)

- **✎ Edit** at the top left of the project opens the same wizard on the live project. It is for the Project Admin and
  the Lead Architect.
- Saving runs in the background (task `project.updated`):
  - models added or taken out (a model taken out stays as it is);
  - goals written into the model;
  - new folders and templates added to the repository. Documents stay.
- Steps are ticked done, and unticked, by anyone who contributes.

### Templates, placeholders and views (D278)

- For each deliverable and artifact, the wizard shows the templates from every picked library. Tick the ones to copy,
  or tick **placeholder**: something to deliver whose document is made later.
- The project's own items are placeholders.
- On the project, a placeholder with no document shows **to be built**, with **Upload the first version**.
- **Views** come from the library, and the project can make its own: code `PV-<n>`, with name, concerns,
  stakeholders and element types.
- Each view is **ready** when every element type it shows is in one of the project's models' metamodels. It then
  opens in that model; the project's model is tried first.
- Otherwise it is **to build**, and lists the missing types, with a link to that model's metamodel.

### Sign-off of deliverables (D276)

- Any document can be marked deliverable (D) or artifact (A). It takes its item's kind until it is marked.
- **Raise for sign-off** asks the signers of the document's phase, or of the whole project.
  - The signers are told in the application, under Notifications › Requests.
  - On the **Sign-off** tab they **approve** or **reject**. A reject needs a comment.
  - If the person who raised it is also a signer, their approval counts as **self approved**.
- A decision given outside the application (an email, a signed page) can be **recorded with the evidence**. It is
  stored in `00_Project/Sign-off evidence`. This is for the person who raised it, the Project Admin or the Lead
  Architect.
- The document is **Approved** when every signer approves; its signed-off version is recorded. It is **Rejected** when
  one signer rejects.
- Checking in a new version ends an open sign-off.
- Email alerts come in a later phase (to-do list).

### The landing page (D279)

- **Home** shows the **ADM crop circle**:
  - Preliminary above;
  - phases A to H around Requirements Management;
  - each phase with a ring showing how many of its steps are done, and its document count;
  - phases you can click or open with the keyboard.
- Next to it are the chosen phase's:
  - **steps**;
  - **deliverables and artifacts**: check out, check in, upload, mark D or A, raise for sign-off;
  - **views**.
- Below the circle are "Across the cycle" and the project's **models**, which link to each model's landing page.
- The tabs are Home, **About** (scope, goals and outcomes, sponsor, notes, files, people, models), Repository, Steps,
  **Sign-off** and Principles.

### Finishing (D277)

**Finish the project…** is for the Project Admin and the Lead Architect. It runs in the background (task
`project.finished`). Choose one of:
- **Freeze it**: read only.
- **Merge it into another project**: each document's latest version is copied into that project's repository, under
  the same deliverable if it has one, otherwise in a folder "From <project>" in that phase. Then it is frozen.

For each model: **keep it as it is**, or **merge it into its parent model**, with its changes winning.

A frozen or merged project:
- is read only for everyone, Super Admins included;
- shows a banner saying so;
- can still be the parent of a new project.

## API

| Method | Route | What it does |
|---|---|---|
| PUT | `/projects/<p>` | Edit (background task; `?wait=true` in the request) |
| POST | `/projects/<p>/files` | Upload a project file |
| POST | `/projects/<p>/documents/<d>/kind` | Mark a document deliverable or artifact |
| POST | `/projects/<p>/documents/<d>/signoff` | Raise for sign-off |
| POST | `/projects/<p>/signoffs/<r>/decide` | Approve or reject |
| POST | `/projects/<p>/signoffs/<r>/record` | Record an outside decision with evidence |
| POST | `/projects/<p>/views` | Make a project view |
| POST | `/projects/<p>/finish` | Freeze or merge (background task) |

## How to check it (after `.\eax clean-restart`)

1. **New project.**
   - Models: select Protea (worked on) and Karoo Digital (referred to). Then **+ New model…** › Create empty from
     ArchiMate 4, named "… target state".
   - Primary working model: the target state.
   - Fill in Basics, Scope, two goals with outcomes, and the Sponsor with two asks.
   - Write notes with bold text and a list, and add a PDF.
   - Phase by phase: untick a template and tick a placeholder; add an item of your own.
   - Create it. The Tasks tab shows the creation.
2. **Home.** The crop circle shows each phase's step ring and document count. Click B, then C: C includes data and
   application.
3. **About.** The scope, goals (linking to the entities in Protea), sponsor, notes and files are all there.
4. **Placeholders.** A placeholder shows *to be built*; use "Upload the first version".
5. **Sign-off.**
   - Upload a deliverable and raise it for sign-off.
   - Sign in as a signer: the notification is there. Reject without a comment and you are refused; approve.
   - As the raiser, record the other signer's decision with an email file. The document is Approved (v1 signed off).
   - Check out, check in v2: it is back to Draft.
6. **Edit.** Take out the referred model, change a goal, add an outcome, add a step, put an item out of use, and save.
7. **Views.** Make a project view with a type that doesn't exist: it shows *to build* with the missing type.
8. **Derive.** Start a new project from the first one: its fields are filled in.
9. **Finish.** Merge the first project into the second: its documents appear there, and the first is read only (ticking
   a step is refused).
10. **Merge a model.** A project with a derived model: Finish › Freeze and merge the model into its parent. Its new
    entities are in the parent.

## Not in this phase

- Email (or other external) alerts for sign-off; a phase of its own.
- Model roles in a project and the project templates: built in [13.0.3](phase-13.0.3.md).
- The approvals workflow with reminders and the project dashboard (13.1).
- The registers (13.2).
- Principles as model entities (D270) and the principle text in root-principle-model (to-do list).
- An execution phase after the ADM.
- Stopping a merge or a finish that is running.
