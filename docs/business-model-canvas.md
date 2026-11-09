# Business Model Canvas

Owner, 9 Nov 2026 (D344). The Business Model Canvas is first-class in a project: a tab of its own, standing on its own.
Nothing on it changes the project's models, documents or anything else; it is not linked to model entities.

## What a project holds

| | |
|---|---|
| **Canvases** | Any number, each with a name, a **kind** (Current state, Target state, Working copy, Scenario), a **status** (Draft, Agreed) and a description |
| **The nine blocks** | Key partners, key activities, key resources, value propositions, customer relationships, channels, customer segments, cost structure, revenue streams; each item is a short text with an optional note |
| **Lineage** | An item keeps its lineage in every copy, so two canvases compare item by item |
| **History** | Every change: who, when, what |
| **Documents** | What was used to build a canvas: uploaded with it (kept in `00_Project/Business model canvases`) or a document of the project, linked |

## Working with canvases

* **Make a working copy** of any canvas. In a working copy, changes are marked by hand:
  * an item added is **green**;
  * an item changed is **amber**, its old text kept above, crossed out;
  * an item removed is **crossed out in red** and kept until the copy is cleaned up (an item added in the copy goes at once);
  * ↺ undoes a mark.
* **Make a clean canvas** from a working copy: a new canvas (a Target state by default) without the crossed-out items and
  without the marks. The working copy stays as it was.
* **Compare with…** any other canvas of the project: each block shows what was added (green), changed (amber, the old
  text crossed out) and removed (crossed out in red); the counts are on top; **Swap** turns it round. Items match by
  lineage, then by the same text in the same block.
* **Make a working copy of these changes**: from a comparison, a working copy of the first canvas with the second's changes
  marked, to adjust by hand and then clean up into a new target.
* **Copy to another project** (More…): a clean copy, keeping the lineage; its documents stay in this project.
* **Mark it agreed** / **make it a draft again**; any change to an agreed canvas makes it a draft again.
* **Export**: PDF (A3, the classic layout), PowerPoint (one slide, changes coloured and struck through) and **Open in
  draw.io** — of a canvas with its marks, or of a comparison.

Anyone on the project sees the canvases; contributors change them; a frozen project's are read only.

## Sample data (laptop)

* Protea Claims Transformation 2028: the 2026 current state (agreed, with a note and the workshop notes when Documents is
  up); a 2028 working copy with items added, changed and crossed out; the 2028 target made clean from it; a partner-led
  scenario; a working copy of the changes from 2026 to 2028.
* Fynbos Pet Insurance launch: the target business model (agreed) and a direct-only scenario.
* Fynbos acquires Karoo Re: Karoo Re today.

## API

| | |
|---|---|
| `GET/POST /api/v1/projects/<id>/canvases` | list (and the nine blocks); a new canvas `{name, kind, description}` |
| `GET/PUT/DELETE …/canvases/<cid>` | a canvas with its items, documents and history; change `{name, kind, status, description}`; remove |
| `POST …/canvases/<cid>/items` | add `{block, text, note}` |
| `POST …/canvases/<cid>/copy`, `/clean`, `/copy-to`, `/reorder`, `/documents` | a copy `{name, kind}`; a clean canvas `{name, kind}`; to another project `{project}`; `{block, ids}`; a document (multipart `file`, or `{document}`) |
| `GET …/canvases/<cid>/export?format=pdf\|pptx\|drawio[&compare=<cid>]` | the file |
| `GET/POST …/canvases/<a>/compare/<b>` | the comparison; a working copy of its changes |
| `PUT/DELETE …/canvas-items/<iid>`, `POST …/canvas-items/<iid>/restore` | change an item; remove (cross out); undo a mark |

Tables (migration 0032): `proj.canvases`, `proj.canvas_items`, `proj.canvas_documents`, `proj.canvas_events`; project
backups carry them. Rules in `eax/canvases.py` (D248); sample data in `eax/seed/sample_canvases.py`. MCP:
`business_model_canvas` (list, a canvas, a comparison) and `change_business_model_canvas`.

## To test

1. Clean restart; Protea Claims Transformation 2028 (sample) › **Business model canvas**: five canvases.
2. Open the working copy: green, amber and crossed-out items; ↺ on one; add, change and remove items.
3. **Make a clean canvas** from it; compare it with the 2026 current state; **Make a working copy of these changes**.
4. Export a canvas and a comparison as PDF and PowerPoint (open them in PowerPoint), and open one in draw.io.
5. Add a document to a canvas (upload, and link one of the project's); copy a canvas to another project.
6. As user_stakeholder: the canvases show, without the editing buttons.
