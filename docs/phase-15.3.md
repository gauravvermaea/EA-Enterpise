# Phase 15.3 — Business architecture artifacts (requested, design session half done)

Status: **a phase of its own** (owner, 8 Nov 2026, D335; first agreed 6 Nov 2026 as 13.4, D268). **In part built and
accepted 9 Nov 2026 (D356)**: Business Model Canvases ([business-model-canvas.md](business-model-canvas.md), D344), the
TOGAF Phase B artifacts as views with their reports and six extension types ([business-architecture.md](business-architecture.md),
D345, D352), key questions ([key-questions.md](key-questions.md), D341 to D343). The rest below was **replaced on 9 Nov 2026 (D358)** by a project tab, *Other views and documents*: templates kept in each project (SWOT and a customer journey map to start; contributors add their own), copied into the project's repository and filled in. Nothing below is built into the model.

**Agreed so far (6 Nov 2026):**
- The artifacts are **entities in the model**, linked by relationships; a canvas is a view of the model and stays in
  step with it, so gaps can be found.
- **Gaps of four kinds**: baseline vs target (added, removed, changed, using the existing tags, versions, compare and
  gap analysis); completeness inside one artifact (e.g. a value proposition with no customer segment or channel, a
  segment with no revenue stream, an activity with no resource); against the architecture (items no capability,
  process or application supports); against strategy (items not traced to a driver, goal or outcome, and goals with
  nothing behind them).
- **Entity types: both, chosen per model**: a pack of canvas types (Customer Segment, Value Proposition, Channel,
  Revenue Stream, Cost Item...) each mapped to its ArchiMate 4 type, so a model uses either.
- **Scope**: the Business Model Canvas, the value proposition canvas, the capability map (with heat) and value streams,
  motivation and strategy (drivers, goals, outcomes, SWOT), the customer journey and the stakeholder map.
- **When 13.4 starts: ask the owner to upload documents to study first.** Documents that forbid AI use (such as The Open
  Group's TOGAF Business Architecture guides, marked "NOT FOR AI USE OR AUTOMATED PROCESSING") are not read; only their
  titles are used. The artifact list comes from the owner and from openly licensed sources (the Business Model Canvas is
  published under CC BY-SA).
- **Candidate artifacts, from the guide titles only**: business model (Business Model Canvas), business capabilities and
  capability planning, value streams, information map, organization map, business scenarios.

**Still to discuss:**
- **Which artifacts** (beyond the agreed scope): candidates are the Business Model Canvas, value proposition canvas, business capability map,
  value chain and value streams, business motivation (drivers, goals, outcomes), organisation map, actor and role
  catalogue, customer journey map, stakeholder map, SWOT, and others the owner names. The Meridian samples have most of
  them (EA Explorer's template library holds them rebranded).
- **How each works**: filled in on screen with the model's entities (the canvas is a view of the model and stays in
  step with it), drawn from the model like the report views, or a document in the project repository.
- **Where they live**: the metamodel types each needs (the insurance reference model and ArchiMate 4's motivation and
  strategy elements), views, a project's deliverables and artifacts, versions and approvals (13.1).
- **Export**: PowerPoint, PDF, draw.io, Excel.

## Other views and documents: the project's own uploads (D461, 10 Nov 2026, 0.17.0)
The owner: "We should be able to upload content in other views and documents" (per project, the project team uploads).
- The tab keeps the ten sample templates and gets **Uploaded by the project** above them: name (or title), file name,
  description, type, size, who uploaded it and when, versions, and Download.
- **Anyone on the project** (any role) uploads one or more files of any type (at most 20 at once, 50 MB each), with an
  optional title and description (given to each file when several are uploaded).
- **The person who uploaded a file, the Project Admin or Lead Architect, or a Super Admin** replaces it (the new file
  becomes the next version; earlier ones stay, downloadable from *n versions*), edits its title and description, or
  deletes it. Nothing changes while the project is finished.
- Stored as ordinary project documents: `proj.documents` with origin `other` in the folder `00_Project/Other documents`
  (kind None), files and versions in Documents, so every backup carries them. New column `file_size` (migration
  `0038_other_uploads`). They are not deliverables: left out of the repository table, never signed off or accepted.
- Every upload, replace, change and delete is in the change log (`project.other_upload.*`) and the document's history.
- API: `GET/POST /projects/<p>/other-uploads`, `PUT/DELETE /projects/<p>/other-uploads/<d>`,
  `POST .../<d>/replace`, `GET .../<d>/versions`, `GET .../<d>/download?version=n` (eax/other_uploads.py).
- Sample data (laptop): Protea Claims Transformation 2028 (sample) has three uploads by the Lead Architect, an architect
  and a stakeholder; the architect's spreadsheet was replaced (two versions).
