# To do

Open items that are not part of a build phase yet, or are waiting on a test or a decision.
Tick an item (`[x]`) when it is done; remove it at the next tidy-up.

## Waiting on a test (Gaurav)

- [ ] **Accept phase 1.** Go through the demo and checks in [phase-1.md](phase-1.md): model pages,
  ER diagram, SQL window (`eax.get_entity`), `tests/sql/phase1_checks.sql`.
- [ ] **Connect Claude Desktop to the MCP server.** Claude Code is connected (4 Nov 2026). For
  Claude Desktop: Settings > Developer > Edit Config, add the `eaexplorer` block from
  [mcp.md](mcp.md) (needs Node.js 18+), quit Claude Desktop fully and restart. If it does not
  start, use `"command": "cmd"` with `"args": ["/c", "npx", ...]`.
- [ ] **Phase 0 checks not yet run:** Swagger, audit log, Superset sample dashboard, Mayan upload,
  backup and scratch restore, database not exposed ([phase-0.md](phase-0.md), demo checklist).

## Waiting on input (Gaurav)

- [ ] **Repository set-up files** for project setup (PRJ-004, build phase 16.1): share the files
  that define a project's repository structure and starter material.
- [ ] **Source for the cross-industry reference model** (build phase 2): Meridian Assurance content
  from the TOGAF project, or another source.

## Decisions to make

- [ ] **Metamodel graph (phase 2):** add dragging, PNG and .drawio export to the ER diagram tab
  (proposed), or build a separate graph view.

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
