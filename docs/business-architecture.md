# Business architecture artifacts

Owner, 9 Nov 2026 (D345). The business architecture artifacts TOGAF recommends for Phase B, each given by a view
of a model, with the metamodel types they need. The Business Model Canvas is separate: a project's own canvases
([business-model-canvas.md](business-model-canvas.md), D344). Use cases are left out: they are UML, not ArchiMate.

## Where to find them

* **A model's Business views tab** (Models › a model; D352): only what can be made from the model's elements and
  relationships. Every artifact mapped to its **view** (the link shows it in its usual form: a catalogue as a
  catalog, a matrix as a matrix...) and to its **reports**: the view's own dashboard and the standard reports that
  go with it (`VIEW_REPORTS` in `eax/report_defs.py`, for example the Business Capabilities catalog with SR-02 and
  SR-16). Then what it shows and how many elements the model has for it (✓ green), whether it has the types but no
  elements yet (amber), or needs types the model's metamodel lacks (red). No Business Model Canvas here: it is not made
  from a model.
* **A project's Business artifacts tab**: everything business architecture in the project: its **Business Model
  Canvases** (kind, status, items and marks), its **Phase B deliverables and artifacts** with their documents, and the
  **business views** of any of the project's models (as on the model's tab).
* **The Views tab** of a model: the new views sit in the category *TOGAF business architecture*; each
  view that gives a TOGAF artifact says so.

## The artifacts and their views

| Kind | Artifact | View |
|---|---|---|
| Catalogue | Organization/Actor catalog | VP-27 |
| | Role catalog | VP-28 |
| | Driver/Goal/Outcome catalog | VP-29 |
| | Business Service/Function catalog | VP-30 |
| | Business Capabilities catalog | VP-31 |
| | Value Stream catalog | VP-32 |
| | Value Stream Stages catalog | VP-33 |
| | Location catalog | VP-34 |
| | Process/Event/Control/Product catalog | VP-35 |
| | Contract/Measure catalog | VP-36 |
| Matrix | Business Interaction matrix | VP-37 |
| | Actor/Role matrix | VP-38 |
| | Value Stream/Capability matrix | VP-39 |
| | Strategy/Capability matrix | VP-40 |
| | Capability/Organization matrix | VP-41 |
| Diagram | Organization Map | VP-01 Organization |
| | Process Flow diagram | VP-10 Process Cooperation |
| | Business Capability Map (heat map by maturity, importance or investment) | VP-19 Capability Map |
| | Value Stream Map | VP-20 Value Stream |
| | Goal/Outcome/Service diagram | VP-21 Outcome Realization |
| | Organization Decomposition diagram | VP-42 |
| | Functional Decomposition diagram | VP-43 |
| | Event diagram | VP-44 |
| | Business Footprint diagram | VP-45 |
| | Business Service/Information diagram | VP-46 |
| | Information Map | VP-47 |
| | Product Lifecycle diagram | VP-48 |
| Technique | Business Scenario | VP-49 |
| Deliverables | Architecture Definition Document and Architecture Requirements Specification (business), Statement of Architecture Work | the project's documents (templates in the library) |
| | Architecture Roadmap (business work packages) | VP-24, VP-25, the migration plan wizard |

VP-27 to VP-49 are EA Explorer's own views; each names element types of both ArchiMate 4 and the TOGAF 10 content
metamodel, so it works on models of either.

## Metamodel additions: EA Explorer extensions

Added to the ArchiMate 4 metamodel (and so to every model made from it, the insurance reference model and the sample
models) and, where it lacked them, to the TOGAF 10 content metamodel. Each is marked *EA Explorer extension (not an
element of the ArchiMate 4 Specification)* in its description; the 42 elements of the specification are unchanged and an
ArchiMate exchange leaves the extensions out.

| Type | What it holds | Relationships |
|---|---|---|
| Value Stream Stage | order, entry criteria, exit criteria, value item | part of a value stream (composition); stages flow or trigger one another; capabilities serve stages; a stage realises value |
| Product Lifecycle Stage | order, entry criteria, exit criteria | part of a product; stages trigger one another |
| Business Scenario | problem, environment, desired outcome | influences motivation elements; associated with actors, roles, processes |
| Control (ArchiMate) | priority, link | influences processes |
| Contract (ArchiMate) | party (vendor), start, end, annual cost, link | realises services |
| Measure (ArchiMate) | how it is measured, target | influences outcomes |

Capability gains **Importance** (high, medium, low) and **Investment** (invest, sustain, reduce) beside Maturity and
Criticality, for the capability map's heat. The value stream map now draws Value Stream Stages (and still child value
streams in models made before).

## Sample data (laptop)

Protea Insurance (demo estate) has content for every artifact: its value stream stages are Value Stream Stages with
order, entry and exit criteria and value; two products with five lifecycle stages each; two business scenarios; three
controls, three contracts and three measures; importance and investment on every capability. Six project templates
choose some of the new views (transformation, new product, operating model, capability planning, document as-is,
due diligence), so their sample projects show them.

## To test

1. Clean restart. Models › Protea Insurance (demo estate) › **Business views**: every artifact green, each with its
   view and reports (Dashboard and the SR, TC or TM reports, opening in the reporting tool).
2. Open VP-33 (a catalogue opens as a catalog), VP-39 (a matrix), VP-48 (a diagram), VP-19 as a heat map by Importance.
3. Models › Karoo Digital (lean) › Business views: most artifacts red (its metamodel lacks the types).
4. A project › **Business artifacts**: its canvases, its Phase B deliverables, and the business views of each of its models.
5. Metamodel tab of Protea: the six extension types, each described as an EA Explorer extension.
