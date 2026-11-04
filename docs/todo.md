# To do

Open items that are not part of a build phase yet, or are waiting on a test or a decision.
Tick an item (`[x]`) when it is done; remove it at the next tidy-up.

## Waiting on a test (Gaurav)

- [x] **Accept phase 1** (accepted 4 Nov 2026).
- [x] **Accept phase 2** (accepted 4 Nov 2026; checks passed, MCP tried from Claude Code).
- [x] **Phase 2 closed** (4 Nov 2026, version 0.2.1).
- [x] **Role and permission model agreed** (4 Nov 2026, D58-D63): see the Roles sheet of the requirements
  workbook and phase 3.1 in the plan. Settled 4 Nov: only Model Admins change the metamodel (D89);
  Model Admins also edit and commit content (D90).

## Phase 3 (version 0.3.0)

- [x] **SQL window read-only** (D52): *Allow changes* removed; every run is rolled back.
- [x] **Phase 3 accepted** (4 Nov 2026). Was: test phase 3 (Gaurav): `.\eax clean-run`, the demo and checks in [phase-3.md](phase-3.md).

## Phase 3.1 (version 0.3.1)

- [x] **Phase 3.1 accepted** (4 Nov 2026). Was: test phase 3.1 (Gaurav): `.\eax clean-run`, the demo and checks in [phase-3.1.md](phase-3.1.md).
- [x] Superset reports by model (phase 5, D138). Mayan cabinets by model (phase 13), as planned.

## Phase 5 (version 0.5.0)

- [x] **Phase 5 runs** (4 Nov 2026): the reports basically work.
- [ ] **Check each of the 32 report dashboards** in the testing phase 36.1 (D143), with the checklist in [phase-5.md](phase-5.md).

## Deployment (to discuss when we reach the deployment phase)

- [ ] **Publish the EA Explorer images on Docker Hub** (api, web, superset, backup) so an installation can pull
  them instead of building. How to build and push (GitHub Actions on a version tag, an eax command, or
  both), the namespace and the tags are to be discussed then (owner, 4 Nov 2026).

## Decisions waiting before their phase

- [x] Import, export and survey sheets: both Excel and CSV (D88).
- [x] Retiring an entity type makes its entities read-only until it is restored (D87, built in 0.3.0).
- [x] **ETL tool for the integration phase (34.1, D91)**: Apache Hop (D128). The connectors needed are
  settled in that phase's design session.
- [ ] **Kinds of notification and request (8.1, D83)**: to agree in that phase's design session.

## Design session before phase 15 (architecture projects and repository, D103-D105)

- Projects and models: several projects on one model, or a project on a copy merged back. What happens to a project's content when
  the project closes, is merged or is abandoned? Can one project work on more than one model?
- Which registers are organisation-wide and which per project, beyond those in D104 (risks? standards waivers?).
- The ADM framework definition: TOGAF 10 phases and deliverables shipped; how an organisation adds its own; gates and who approves.
- Artefact templates: which ones ship (the TOGAF sample content in the project files is a good start), and how a catalogue,
  matrix or view is generated into a workbook or document.
- Review and approval: how it uses the actions, alerts and workflows of phase 8.1 and the commits of phase 8.
- Roles on a project (do they flow to its models, or stay separate from model roles?).

## Design session before phase 24.1 (model versions, comparison and gap analysis, D111)

- What counts as a change: which fields, attributes and relationship types; how to treat renames, moves in a hierarchy, retired
  versus deleted, and values that differ only in format (dates, numbers, case, whitespace).
- Matching across models: origin (copied from), display ID, type and name; how manual matches are kept; what to do with
  one-to-many matches (one application split into two).
- Comparison profiles: which ship (application portfolio, capabilities, technology), who may save shared ones.
- Version storage: full snapshots, or history replayed to a point; size and speed on large models.
- Gap analysis: the matrix layout (TOGAF baseline by target), what a gap carries (note, resolution, work package), and the gap
  report's Word and Excel layouts.

## Phase 4 questions (answered 4 Nov 2026)

- [x] Package format: zip with JSON and CSV, and an Excel workbook too (D116).
- [x] Pack files: built with Mayan in phase 13 (D117).
- [x] Who curates the library: a new Library Admin role (D118).
- [x] Own roots as library models: yes, as roots of their own (D119).
- [x] AI drafting: step-by-step and whole-file tools, the person chooses; same rights as editing by hand (D120).
- [x] New framework versions: copy with mapping or upgrade in place, Model Admin chooses; delete: Super Admin, refused
  while others depend (D121).

## Waiting on input (Gaurav)

- [ ] **Repository set-up files** for project setup (PRJ-004, build phase 16.1): share the files
  that define a project's repository structure and starter material.

## Platform follow-ups (from phase 0)

- [ ] Pin the Mayan image (`mayanedms/mayanedms:s4`, ran as 4.12.2) and the other images by digest
  once the checklist passes.
- [ ] Confirm Mayan document upload and OCR jobs run with `dms-broker` (Valkey) as its only broker.
- [ ] Single sign-out: after signing out of the start page, Superset asks to sign in again.
- [ ] draw.io embed mode when self-hosted: prove before phase 28.
- [ ] Superset row filtering by model: needed from phase 5.

## Productionising stories (discuss before the final deployment scripts, phase 36)

Noted 4 Nov 2026 (D99). To discuss and settle when we build the final deployment scripts:

- [ ] **Scale-out**: run the API, job runner, reports and documents on several servers behind a load
  balancer; database and storage sized and placed for production.
- [ ] **Users on another platform**: keep the people and roles in an existing identity platform
  rather than only in our Keycloak (Keycloak federating to it, or replaced by it).
- [ ] **Integrated AD-based sign-in**: Active Directory through Keycloak, with AD groups mapped to
  Keycloak roles in Keycloak (D93); brings back SEC-003, which is "not planned now" (D73).
- [ ] **Sign-in and paths in the config file**: choose the identity providers and sign-in settings,
  and the folders and storage paths (data, backups, imports, exports, documents), in the config file
  for each deployment.
- [ ] **A key vault for secrets**: database passwords, client secrets, the break-glass password and
  every other password held in a vault (for example HashiCorp Vault, Azure Key Vault or AWS Secrets
  Manager) instead of the config file; containers read them at start.

- [ ] **End-to-end testing of phase 4 onwards** (D129): deferred to phase 36.1; the checklist is in
  docs/phase-4.md and each later phase adds its own.

- [ ] **Drafts, approvals and publishing** (D135): design session and stories in phase 38.2. Known gap: a
  Model Admin of a draft's source model cannot see the requested draft to approve it.

## Backlog (to work out later)

- [ ] **What-if analysis in the reports phase** (asked 4 Nov 2026): explore the effect of a change before
  making it (for example retiring an application: which capabilities, processes and projects lose
  support). Either built into the reports (scenarios over a copy or a baseline of the model) or done
  through a language model over the MCP tools, or both. To decide before the reports phases (5, 11).

- [ ] **Full documentation, guidebooks and inline help** (asked 4 Nov 2026, D126; to build later, phase to be
  set). Three parts:
  - *Full documentation*: a documentation site published with every version, covering every screen,
    concept (models, metamodels, roots, library, child and independent models, packages, drafts),
    role and permission, the REST API, the MCP tools, operations and upgrades.
  - *Guidebooks*: step-by-step guides per role and per task (first model, building a root metamodel,
    sharing a library model, testing an upload, drafting a metamodel with AI, giving people roles),
    with screenshots, downloadable as PDF.
  - *Inline help*: a help panel on every screen (what it is, what you can do there, what your roles
    allow), help for every field from the metamodel's own help text, a "?" beside each section that
    opens the matching guide page, and search across the help from the top bar. Builds on the tooltips
    and greyed-out controls of phase 4 (D123, D125).
  To settle: the documentation tool (kept in the repository and built with the product), whether the
  help is per version, and how the industry guides of phase 39 fit in.

## Later (already in the requirements)

- MCP as a remote connector for claude.ai and Claude Desktop custom connectors: public https and
  Keycloak OAuth on server installations (AI-011, phase 26).
