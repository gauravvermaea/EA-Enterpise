# Phase 27.1 — Scenario planning with AI

Status: **built, to be accepted (release 0.18.0, migration 0041, D490 to D495).** Design agreed 9 Nov 2026 (D364); built
10 Nov 2026 with batch 3, alongside batch 2 (D421).

## What it does
In an architecture project, a person and their AI assistant (through MCP) plan and compare **scenarios**: copies of the
baseline in which what-ifs are tried, each compared with the baseline, scored, and one recommended. The result is kept
with the project, as a Word document and, if wanted, as a governance decision for approval.

- **Baseline:** the project model whose role is *Current state*, or another the person names.
- **Scenarios:** the project's models with the role *Scenario*. *Target state* models are compared too, and marked as such.

## Through MCP
The guided prompt **plan_scenarios** (project, question) gives the assistant the order of work. The tools:

| Tool | What it does |
|---|---|
| `how_to_plan_scenarios` | The order of work and the tools (read first) |
| `scenario_overview` | The baseline and every scenario: figures, difference, what each adds, changes and retires by entity type, the capabilities touched, a suggested score; the assessments recorded |
| `compare_scenario` | One scenario against the baseline in full: every element and relationship change |
| `list_scenario_assessments` | The assessments recorded (SCN-001…) with their scores, recommendation, document and decision |
| `make_scenario` | A new scenario model: a separate copy or a child of the baseline (or another project model) |
| `apply_what_ifs` | What-ifs in a scenario, as the person's own uncommitted changes |
| `record_scenario_assessment` | Keep the assessment, its Word document and optionally a governance decision |

**The changing tools preview first** (D458). Called without `confirm`, they answer with what they will do and a confirm
token. Called again with the same arguments and `confirm=<token>`, they do it. The token works only for the same person,
the same tool and the same arguments, once, within 30 minutes. A read-only MCP credential (D438–D445) may only read.

### What-ifs
- `{"retire": X}`: X goes, with its relationships.
- `{"retire": X, "replace_with": Y, "type": T?}`: X's relationships move to Y where the metamodel allows, then X goes.
  - Y is new, of X's type unless T is given; or Y is an existing entity.
  - Relationships the metamodel does not allow are listed as not made.
- `{"add": Y, "type": T, "description"?, "values"?, "relationships"?: [{"type": R, "to": Z} | {"type": R, "from": Z}]}`
- `{"change": X, "name"?, "description"?, "values"?: {attribute code: value}}`

They are kept as **the person's uncommitted changes** in the scenario model (D165). Only they see them until they commit
them, and they can be thrown away from the model's Changes tab.

### Figures (D491)
Per model:
- entities and applications;
- capabilities, and how many are **covered** (related to anything in the business, application, technology or data
  domains);
- total annual cost;
- technology past, or within 12 months of, end of life;
- applications marked Eliminate, and orphans;
- **risks**: end-of-life technology plus capabilities not covered.

The figures come from the KPI standard set (phase 24). Each is worked out **as the person sees the model: its committed
content with their own uncommitted changes on top**, so a what-if shows at once for its author and not for anyone else.

The comparison is the model comparison (8.3): entities are matched by id, by origin (the entity a copy came from), and
by type and name. Display IDs are left out of the matching, because two copies number new entities separately. The
**impact** is the capabilities related to anything added, changed or retired.

The **suggested score** runs from 0 to 10, where 5 means no better and no worse than the baseline. It moves with cost,
risks, capabilities covered and the number of applications, and its reasons are listed. It is a starting point: the
person gives the score that is kept.

### Making a scenario (D492)
`make_scenario` makes a separate copy, or a child that can merge back, of the baseline or another project model, and
joins it to the project with the role Scenario.
- The source is **tagged first** ("Before scenario <name>").
- The project's people get their roles on the new model (D261).

### Assessments (D494)
`record_scenario_assessment` keeps:
- the baseline;
- each scenario's score and notes, with its figures, difference and comparison as they are at that moment;
- the recommendation and the scenario recommended;
- a reference, SCN-001 and so on.

It becomes a Word document:
- filed in the project's repository under the document class given, or one that fits (architecture definition,
  options, scenario, assessment);
- when the repository is not built yet, downloadable from the Scenarios tab instead.

With `governance="draft"` it also becomes a Decision in the governance log. With `"approval"` that decision is sent to
the project's sign-off people.

## In the screens
The project's **Scenarios** tab (Architecture group) shows the baseline and the scenarios side by side.
- **When it shows:** only in a project with a scenario model.
- **Comparison table:** figures with their difference, added / changed / retired, and the suggested score.
- **Per scenario:** what changed by entity type, the lists of names, and the capabilities touched.
- **Assessments:** each with its scores, recommendation, decision and approval state, and its Word document.

Figures include the viewer's own what-ifs. Scenarios, what-ifs and assessments are made through MCP.

API: `GET /api/v1/projects/<p>/scenarios`, `.../scenarios/<model>/compare`, `.../scenario-assessments/<a>` and
`.../scenario-assessments/<a>/docx`.

## Who
- **Reading:** anyone on the project, for the models they may read.
- **Making scenarios and recording assessments:** a contributing role on the project (not Stakeholder).
- **What-ifs:** also a role that changes the scenario model's content (Architect, Committer, Model Sub Admin, Model Admin).

Everything is in the change log as done through MCP (`mcp.scenarios.<tool>`) and in the AI activity log.

## Sample data (D495)
In **Protea build or buy (sample)**:
- **Scenario A: build** has its what-ifs committed by the Lead Architect. The Policy Administration System is replaced
  by an in-house Protea Policy Platform.
- **Scenario B: buy** has its what-ifs **pending** for user_architect. The system is replaced by a bought Policy Suite,
  and the Underwriting Rules Engine is retired.
- **SCN-001 Policy platform: build or buy** is recorded by the Architect, with a governance decision **waiting for
  approval**.

Sign in as user_architect to see B with the what-ifs; anyone else sees B without them.

## Checked (10 Nov 2026)
**End-to-end session** on a test database (a copy of a database with the sample projects, plus migrations 0040 and 0041):
- overview, then what-ifs previewed and kept;
- the what-ifs visible to the Architect only;
- a Stakeholder refused;
- a scenario made (tag, copy, roles) in a second;
- an assessment recorded, with the decision sent to three signers;
- the Word document opened;
- a bad score refused.

**Preview tokens:** another person, another tool or other arguments are refused, and a token works once.

**Seed:** runs once, and a second run adds nothing.

**Screens:** the Scenarios tab was checked in the preview as the Architect and as the Lead Architect.

**Tests:** `tests/test_scenarios.py`.
