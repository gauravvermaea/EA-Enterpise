# Phase 39 — Industry reference models

Status: **built, to be accepted (release 0.18.0; D470–D472).** As narrowed by the owner (D421): only a library of
reference models built from the owner's own industry starter packs; nothing more (no new screens, no PDFs or
PowerPoints copied into the product, no template files committed).

## What is in the library
Each is a locked reference model on ArchiMate 4 in the model library (Library › Model library, "Reference models on
ArchiMate 4"), read-only, and can be the base of a new model ("Create a model from this").

| Model | Source (the pack's worked example) | Entities | Relationships |
|---|---|---|---|
| Healthcare reference model 1.0 | Health Care pack, `Healthcare_TOGAF_Metamodel.xlsx` (Ravensmere Health Network) | 236 | 150 |
| Manufacturing reference model 1.0 | Manufacturing starter pack, `Manufacturing_TOGAF_Metamodel.xlsx` (Kestrel Industrial Group) | 235 | 156 |
| Pharmaceuticals reference model 1.0 | Pharma pack, `Pharmaceuticals_TOGAF_Metamodel.xlsx` (Calderon Therapeutics) | 235 | 162 |
| Retail reference model 1.0 | Retail starter pack, `Retail_TOGAF_Metamodel.xlsx` (Halverson Stores Group) | 236 | 155 |
| Insurance reference model 1.0 | unchanged (built earlier, D471) | 715 | 248 |
| Banking | **not loaded yet** (D472) | — | — |

Per model (all four alike): 100 capabilities (levels 1–3 with parents), 5 value streams, 10 business services, 20
processes, 10 functions, 4–5 products, 14 business objects, 12 application components (the starter landscape),
12 application services, 12 technology services, 18 business actors and 18 roles.

## How the workbook maps to ArchiMate 4
| Workbook sheet | ArchiMate 4 |
|---|---|
| O13 Business Capability | Capability (CapabilityLevel; parent) |
| O14 Value Stream | Value Stream |
| O15 Business Service | Service (Domain: Business) |
| O16 Business Process | Process |
| O17 Business Function | Function |
| O18 Product | Product |
| O20 Data Entity | Business Object (Data Classification) |
| O23 Application Component | Application Component |
| O24 Information System Service | Service (Domain: Application) |
| O25 Technology Service | Service (Domain: Technology) |
| O10 Actor, O11 Role | Business Actor, Role |

Relationships: business service and function **realise** capability; capability **serves** value stream; process
**realises** value stream; application **accesses** business object (named master or consumer); application **flow**
to application (the interface register); actor **assigned to** role; application **associated with** the business
service it supports, the product it supports and the application service it exposes (ArchiMate 4 allows only the
strict chain directly between these, D393/D394). Capability decomposition (R01) is the parent.

## Not loaded, and why
- **Company-specific records** of the invented companies: drivers, goals, outcomes, measures, principles,
  requirements, constraints, assumptions, organisation units, locations, contracts, gaps, work packages, projects,
  governance bodies, gates, decisions and change requests, compliance assessments, risks, increments, and the
  assessment columns (criticality, current and target maturity, disposition, health, users, owners). A reference
  model is industry content; these belong to a client's own model.
- **Data and technology components, data attributes, data sets, migrations, mappings, metadata, building blocks,
  reference model entries, environments, resilience tiers and network links**: detail of the worked company's estate.
- **The industry extension types** (sheet EXT, e.g. Patient, Encounter, Production Line, Validated System): they
  would need new entity types; ArchiMate 4 has no home for them without an extension.
- **Reports** (RPT sheets): computed in the workbook; EA Explorer's existing reports already cover them (application
  portfolio, capability heat map, interface catalogue, data ownership, requirements traceability, roadmap, orphan
  analysis). No new reports were made.
- **Insurance** (D471): kept as it is; the pack's metamodel workbook on the laptop is the empty template.
- **Banking** (D472): its workbooks are only in `Banking starter pack - complete set.zip`, which could not be copied
  from the laptop. Unzip it into the Banking folder and run the build (below).

## Sources read
On the laptop, `C:\Users\gaura\Enterprise_Architecture\Industry Specific Guidance`: each pack's READ ME FIRST, its
`*_EA_Metamodel_TEMPLATE.xlsx` (the structure; empty) and, for Healthcare, Manufacturing, Pharmaceuticals and Retail,
the worked example's `*_TOGAF_Metamodel.xlsx`. None is marked "not for AI use" or carries an AI-use restriction.
The learner guides, workbooks (PDF), decks and zips were not used.

## Building and adding a model
`python tools/build_industry_models.py "<Industry Specific Guidance folder>"` writes `services/api/eax/seed/
industry_<code>.py` from each pack's worked example. Add a new industry's row to `services/api/eax/seed/industries.py`;
the seed (`eax.seed`) loads every industry model that is missing on the next start, on a new install or an upgrade
(no migration). A new version is a new model beside the old one (the version is in its key).

## As built: packs and more industries (owner, 10 Nov 2026; D546 to D549)
- **Packs shipped and downloadable** (D546): the owner's packs in `library/industry-packs/<Industry>/` (58 files,
  24 MB today), put into Documents at start-up and shown as tiles on the library's Pack tab and a reference model's
  page. How it works, and `eax packs load | reload | status | collect`: [industry-packs.md](industry-packs.md).
- **More industries** (D548): Banking (267 entities, 171 relationships), Government (248, 146), Logistics (240, 162),
  Minerals and Mining (235, 145) and Telecommunications (251, 164), by the same generator from the owner's metamodels.
- **Meridian Assurance (insurance worked example)** (D549): 766 entities, 575 relationships, from
  `Insurance/Meridian_TOGAF_Metamodel.xlsx`; the Insurance reference model unchanged.
- **Still to copy from the owner's laptop** (the remote copy timed out on files over about 2 MB): the books and
  workbooks (PDF, 5 to 9 MB each), the Comparison Tool workbooks (3.6 to 5.6 MB), the Healthcare and Pharmaceuticals
  View Templates (2.5 to 2.8 MB), the Government, Logistics, Minerals and Mining and Retail ArchiMate 4 views (2 to 3 MB),
  and the Banking and Insurance "complete set" zips (16 to 17 MB). `.\eax packs collect` copies all of them in one go;
  then commit and `.\eax packs reload`.
