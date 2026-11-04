# To do

Open items that are not part of a build phase yet, or are waiting on a test or a decision.
Tick an item (`[x]`) when it is done; remove it at the next tidy-up.

## Waiting on a test (Gaurav)

- [x] **Accept phase 1** (accepted 4 Nov 2026).
- [x] **Accept phase 2** (accepted 4 Nov 2026; checks passed, MCP tried from Claude Code).
- [ ] **Look at 0.2.1** (rest of phase 2): `.\eax clean-run`, `sample_history.sql`, then "Try it" in
  [phase-2.md](phase-2.md): picture kinds, .drawio, timeline, lineage, CSV.
- [x] **Role and permission model agreed** (4 Nov 2026, D58-D63): see the Roles sheet of the requirements
  workbook and phase 3.1 in the plan. Still to agree before phase 3.1 (marked "?" in the Roles sheet):
  who changes the metamodel (Model Admin only, or Architects too?) and whether the Model Admin also
  edits and commits content.

## Next version (phase 3)

- [ ] **SQL window read-only** (asked 4 Nov 2026): remove *Allow changes*; every run is rolled back
  at the end, whoever signs in. Changes go through the screens, the API or `psql` in the db container.

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
