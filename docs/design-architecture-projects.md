# Architecture projects and the repository: design notes (under discussion)

Phases 13 (document management in Mayan) and 15 (architecture projects and the ADM) are done **together** as one phase,
taking in project setup (16.1). Agreed with the owner on 6 Nov 2026, question by question. **Nothing is built yet**: this
records what is agreed, what is parked and what is still to discuss. Decision numbers are given when the phase is built.

## Sources read

- The owner's sample repositories (`Enterprise_Architecture/Sample_Repo`):
  - **Meridian Architecture Repository** (Initial and Populated): TOGAF repository classes `00_Read_Me_First` to
    `99_Baselines`, ADM phase workspaces (P, A, B, C-Data, C-Application, D, E, F, G, H, RM) with Deliverables and
    Artifacts, `10_Templates` (T-01 to T-15, F-01 to F-12), `11_Not_Used` (removals with reasons), phase closure records.
    Its **Tailored Architecture Framework** workbook marks every step, deliverable and artifact Kept, Modified, Added or
    Removed against TOGAF: 116 steps (93 TOGAF + 23 added), 55 deliverables (41 TOGAF + 14 added), 65 artifacts
    (41 TOGAF + 24 added), 15 templates with 151 fields, phase inputs.
  - **Phase-Wise Deliverables**: the same work in 85 numbered folders by ADM phase.
- The **TOGAF Standard, 10th Edition template deliverables** (23 Word templates in 9 phase folders). Kept **exactly as
  they are, never branded or changed**. Their README forbids using them with AI to generate content: only their names
  were read; the platform stores and hands them out unchanged.

## Agreed

1. **Architecture project.** A purpose: Strategy, Portfolio, Project or Solution (standard), or one the user adds.
   **No gates** in the ADM.
2. **Created in a wizard**, phase by phase:
   - models: add existing, derive from existing (parent and child) or create new;
   - principles: created or imported from the principles library (records with rationale and implications);
   - **steps**: from the steps library (TOGAF ADM steps and the rest): accept, remove, add your own; a removed standard
     step always shows **crossed out** with its reason;
   - **deliverables and artifacts**: chosen from the master list; each item is marked **deliverable or artifact**; the
     agreed ones go into the repository, the others into the **same folders as not_for_use** (they can be brought in later);
   - people and sign-off sets.
3. **Two ways to start**: a project **from scratch**, or **rerun the ADM on an existing project** (a child project):
   - the metamodel is copied as a child (parent and child) or an existing one is used;
   - the parent's artifacts are copied into the child's **Reference Library, read only, linked to the parent**;
   - new documents are created through the wizard;
   - the child **inherits the parent's principles**;
   - the **parent stays open** and keeps running while the child runs; at some point the child's artifacts are **merged
     into the parent**.
4. **Master template repository**: built by merging all three sources (Meridian classes, phase-wise folders, TOGAF
   phases) into one large master list, even where items repeat, each tagged with its source; presented **phase by
   phase**; the user selects what they want.
5. **Libraries** (steps, deliverables and artifacts, templates, folder structure, principles): one set for the
   organisation, changed by **Super Admins only**.
6. **Project roles** (new, separate from model roles): **Project Admin** (runs setup, people, sign-off sets, rerun,
   undoes check-outs), **Lead Architect**, **Architects** (as many as needed), **Model Admin**, **Model Sub Admin**:
   all contribute; **Stakeholders**: like a viewer, plus comment on, approve or reject documents; they do not contribute.
   New laptop test users for these roles are to be made.
7. **Sign-off**: named sign-off people, chosen from the project's people, at setup or later; one set for the whole
   project to start with, a different set per phase possible.
8. **Document life cycle**: Draft → In review → Approved, Rejected (back to Draft with the reasons), **Superseded** (a
   newer approved version replaces it), Withdrawn, Not for use.
   - An approval request reaches each sign-off person as a **notification**.
   - The requester may instead **record it as approved outside the platform, attaching the evidence** (emails, minutes);
     it shows as such.
   - **Every document approval is also logged as a decision.**
9. **Producing documents**: all of these: start from the template (TOGAF ones untouched); replace it with a completely
   different format if wanted (a Word document instead of a PowerPoint); **generate from the metamodel or the reports**,
   then upload; upload new versions; write in the platform.
   - **Editing happens outside, in Microsoft Office**: users **check out** and check in documents; the Lead Architect,
     Model Admin, Project Admin and Super Admins can **undo a check-out**. No in-browser office editor (people must be
     able to show the result to others in Office).
10. **Storage in Mayan** (files, versions, check-out and check-in). **Workflow in Mayan, rules and screens in the
    platform**: Mayan holds the workflow definition, the official state of each document and its log; the platform holds
    the sign-off sets and each person's approval, checks the project roles, and moves the state in Mayan through its API
    (a service account, the real person written in the comment and in our own log); Mayan calls our API on every state
    change, for notifications, decisions and the dashboard. Project roles are not copied into Mayan.
11. **Steps**: any contributor marks a step done (who, when, optional note or evidence); the Lead Architect or Project
    Admin reopens it with a reason; no dependency on documents.
12. **Project dashboard**: completion of each phase, measured on steps done and deliverables approved in the cycle.
13. **Registers kept as records in the platform** (per project, rolled up across projects): decision log and
    architecture decision records; dispensations and change requests; compliance assessments and architecture
    contracts; risks, issues, assumptions and dependencies; requirements (with impact assessment); stakeholders and
    concerns; principles; lessons learned.
14. **Models are fully shared**: any project can use and change any model it is given access to.
16. **Merging a child into its parent**: per file, the user decides: **override** (replace the parent's version, which
    becomes Superseded) or **keep both versions**.
17. **Cycles**: an **ADM cycle as TOGAF defines it** (Preliminary to H, Requirements Management throughout). **Both**: a
    project can start a new cycle on itself (cycle 2, 3...; earlier cycles kept for history; the dashboard per cycle),
    or spawn a child project to run a cycle in parallel and merge back later.
18. **Generating an artifact**: each library artifact can name its source, a report or view we already have
    (catalogs and matrices as Excel, diagrams as draw.io, PDF where the report has one), run over the project's models;
    **Generate** saves it as a new version in the artifact's folder, and says when the model has changed since.
19. **Built in four parts**, each tested and accepted before the next:
    - **13**: Mayan's memory fixed first (fewer workers on a laptop, limit 3 GB); the master template repository and the
      libraries; projects, the project roles and their test users; the wizard; the repository in Mayan with check-out
      and check-in;
    - **13.1**: the approval workflow (Mayan states, sign-off sets, notifications, approval with evidence, decisions),
      steps and the dashboard;
    - **13.2**: the registers;
    - **13.3**: cycles, child projects, merging back, generating from reports.
20. **Where it lives**: the same PostgreSQL database as the models, in its own schema `proj` (one backup and restore,
    links to models, users, commits and notifications); the files in Mayan.
21. **The master list is reviewed as a workbook first**: the merged master template repository (phase, step or item,
    deliverable or artifact, type, folder, template, source, duplicates side by side) is built as an Excel workbook; the
    owner reviews and corrects it; the corrected workbook seeds the libraries.
22. **The build plan**: 15 and 16.1 fold into 13; 16 (project registers) becomes 13.2; 16.2 (artefacts) is covered by
    13 and 13.1; **15.1** stays (the organisation-wide standards and reference library beyond principles) and **16.3**
    stays (the other guided wizards).
23. **Template libraries** (D264, added 6 Nov 2026): EA Explorer's own (a file for every item: the samples rebranded to
    [Organisation], starter files for the rest), TOGAF 10 (loaded once) and any number of the organisation's own
    (download a library's zip, rebrand, add documents, upload under a new name). A Super Admin finishes the template
    library setup before the first project. The wizard lists the libraries; the creator picks one or more and may add
    one (private to them and the project until a Super Admin shares it). Every picked library's template for an item is
    copied, named `<library>-<document>`.
24. **Library projects** (D265, 13.3): a Project Admin makes a project into a library project, approved by a Library
    Admin; its models are copied and promoted to the library, its documents become a template library. A project made
    from a library project (or a copy of a project) starts with everything filled in, with copies of the library models
    and of the library project.

## Parked

- **Custom registers** ("anything the user wants to record"): their own fields, who defines them. To think about.

## Still to discuss

- Which library artifact maps to which report or view (when 13.3 is planned).
