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
- [ ] **Test phase 3** (Gaurav): `.\eax clean-run`, the demo and checks in [phase-3.md](phase-3.md).

## Decisions waiting before their phase

- [x] Import, export and survey sheets: both Excel and CSV (D88).
- [x] Retiring an entity type makes its entities read-only until it is restored (D87, built in 0.3.0).
- [ ] **ETL tool for the integration phase (34.1, D91)**: which open-source tool (for example Apache Hop,
  Apache NiFi or Airbyte) and which connectors. To discuss before that phase.
- [ ] **Kinds of notification and request (8.1, D83)**: to agree in that phase's design session.

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

## Later (already in the requirements)

- MCP as a remote connector for claude.ai and Claude Desktop custom connectors: public https and
  Keycloak OAuth on server installations (AI-011, phase 26).
