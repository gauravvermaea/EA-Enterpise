# Phase 15.3 — Business architecture artifacts (requested, design session half done)

Status: **a phase of its own** (owner, 8 Nov 2026, D335; first agreed 6 Nov 2026 as 13.4, D268). Not built yet; the
design session continues before building.

**Agreed so far (6 Nov 2026):**
- The artifacts are **entities in the model**, linked by relationships; a canvas is a view of the model and stays in
  step with it, so gaps can be found.
- **Gaps of four kinds**: baseline vs target (added, removed, changed, using the existing tags, versions, compare and
  gap analysis); completeness inside one artifact (e.g. a value proposition with no customer segment or channel, a
  segment with no revenue stream, an activity with no resource); against the architecture (items no capability,
  process or application supports); against strategy (items not traced to a driver, goal or objective, and goals with
  nothing behind them).
- **Entity types: both, chosen per model**: a pack of canvas types (Customer Segment, Value Proposition, Channel,
  Revenue Stream, Cost Item...) each mapped to its ArchiMate 4 type, so a model uses either.
- **Scope**: the Business Model Canvas, the value proposition canvas, the capability map (with heat) and value streams,
  motivation and strategy (drivers, goals, objectives, outcomes, SWOT), the customer journey and the stakeholder map.
- **When 13.4 starts: ask the owner to upload documents to study first.** Documents that forbid AI use (such as The Open
  Group's TOGAF Business Architecture guides, marked "NOT FOR AI USE OR AUTOMATED PROCESSING") are not read; only their
  titles are used. The artifact list comes from the owner and from openly licensed sources (the Business Model Canvas is
  published under CC BY-SA).
- **Candidate artifacts, from the guide titles only**: business model (Business Model Canvas), business capabilities and
  capability planning, value streams, information map, organization map, business scenarios.

**Still to discuss:**
- **Which artifacts** (beyond the agreed scope): candidates are the Business Model Canvas, value proposition canvas, business capability map,
  value chain and value streams, business motivation (drivers, goals, objectives), organisation map, actor and role
  catalogue, customer journey map, stakeholder map, SWOT, and others the owner names. The Meridian samples have most of
  them (EA Explorer's template library holds them rebranded).
- **How each works**: filled in on screen with the model's entities (the canvas is a view of the model and stays in
  step with it), drawn from the model like the report views, or a document in the project repository.
- **Where they live**: the metamodel types each needs (the insurance reference model and ArchiMate 4's motivation and
  strategy elements), viewpoints, a project's deliverables and artifacts, versions and approvals (13.1).
- **Export**: PowerPoint, PDF, draw.io, Excel.
