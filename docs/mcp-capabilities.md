# MCP capabilities to add (batch 3, phases 26/27)

Status: **built in 0.18.0** (10 Nov 2026, D482 to D489; [phase-26-27.md](phase-26-27.md)), except where an item says
*not built*. Each item names the tools that serve it. Adds to the 82 tools built so far
(reading the metamodel and models, search, history, views, compare, gap analysis, quality, metamodel drafts, projects,
key questions, stakeholders, documents, drawn views, entering and committing changes).

Every tool below follows the same rules (D458):
- acts **only with the person's own rights**, and within the machine-access areas of the credential used (D438–D445);
- anything that changes something first returns a **preview** and applies only when called again with confirm;
- the model being changed is **tagged first**, so it can be restored;
- the change is the person's, in the change log, marked as done through MCP;
- read-only credentials only get the reading tools.

Each item names the kind of request it serves.

## 1. Model operations (D458)
- **Copy a model / make a child**: "make a copy of this model called Claims 2028". *Built: copy_model.*
- **Dedupe**: "remove all duplicates as you see fit". Find candidates, then merge, choosing the survivor and each field's value. *Built: find_duplicates, compare_duplicates, merge_duplicates.*
- **Merge into the parent, every change accepted**: "override its parent with it". *Built: override_parent.*
- **Refresh from the parent, freeze, archive, tag, compare, common analysis, propagate** and the other model wizards. *Built: refresh_from_parent, model_wizard, tag_model, compare_models, common_analysis, decide_merge_request.*

## 2. Cleaning up a model
- **Fix quality findings in bulk**: "give every application without an owner the owner of its capability", or "mark all
  technology reviewed this year as still current". Shown as a list of changes to confirm. *Built: change_entities (with quality_findings).*
- **Tidy names**: trailing spaces, inconsistent capitals, abbreviations ("App" → "Application"), numbering. *Built: tidy_names, then change_entities.*
- **Orphans**: list entities with no relationships and suggest the likely relationships, with reasons. *Built: find_orphans.*
- **Fill attributes from descriptions**: "set the lifecycle from what the descriptions say", listing each guess and why. *Built: change_entities (the assistant reads the descriptions).*
- **Split or combine**: split an entity into two, moving chosen relationships, or combine entities. *Combine built (merge_duplicates); splitting one entity in two: not built (do it in the screens).*

## 3. Building a model from material
- **From a document or pasted text**: "read this strategy and create the drivers, goals and outcomes with their links". *Built: prompt build_from_material with add_entities, add_relationships.*
- **From a pasted table or messy spreadsheet**: maps the columns to types and attributes and loads it into the person's
  uncommitted changes (the import sheets, 10.1, and the published formats, 34). *Built: the same prompt, through the person's uncommitted changes.*
- **A metamodel workbook from a description**: "build me a metamodel for a reinsurance programme" (the D419 layout),
  as a draft to review. *Built: start_metamodel_draft and draft_set_item (a draft to review).*
- **Starter content**: a capability map, value streams or a starter landscape for an industry or domain, from the
  library's reference models (39) where one exists. *Built: list_library and copy_model from a reference model.*
- **Relationships from text**: "Claims Platform serves the claims handlers and runs on the Azure cluster". *Built: add_relationships.*

## 4. Analysis
- **Impact**: "what is affected if we retire the Policy Admin system?" (everything that depends on it, through any path). *Built: impact_analysis.*
- **Rationalisation**: applications serving the same capability, overlaps, TIME suggestions with reasons. *Built: application_rationalisation.*
- **Cost**: total cost by capability, value stream or business unit, rolled up through the relationships. *Built: cost_rollup_analysis.*
- **Technology risk**: what runs on technology past or near end of life, and which capabilities that puts at risk. *Built: technology_risk_analysis.*
- **Single points of failure** and critical paths through the landscape. *Built: single_points_of_failure.*
- **Heat maps** of capabilities by any attribute (cost, quality, maturity, investment), drawn as a view. *Built: heat_map_data (data; draw it with create_drawn_view; colouring the shapes by band: not built).*
- **What changed**: between two dates or tags, as a short narrative plus the list. *Built: what_changed.*
- **KPI trends explained** (24): "why did the quality score drop in September?" *Built: kpi_trend.*

## 5. Views and diagrams
- **Draw a view from a question**: "draw the claims landscape with its technology", as a drawn view with tidy layout. *Built: prompt draw_a_view with create_drawn_view.*
- **Update a view**: add the related entities of a chosen shape, hide a domain, bind placeholders by name. *Not built through MCP (do it in the drawn view).*
- **Explain a view** in words, for a slide or a document. *Built: get_drawn_view.*

## 6. Writing
- **Reports from the model**: an architecture definition section, a current-state summary, a roadmap narrative,
  as a project document (Word) to review. *Built: save_report_document, prompt write_a_report.*
- **Executive summary of a model** or of a comparison, gap analysis or merge request. *Built: the same, from compare_models, gap_analysis, get_merge_request.*
- **Release notes for a model**: what changed since the last tag, in plain words. *Built: what_changed, then save_report_document.*

## 7. Projects and governance
- **Plan an ADM project**: phases, deliverables and steps from a template, as a draft. *Built: prompt plan_an_adm_project with create_project, add_project_step.*
- **Draft deliverables**: stakeholder map, architecture contract, change request, compliance review, from the model. *Built: save_report_document.*
- **Check a proposed change against principles and standards**, listing which it follows or breaks. *Built: principles_and_standards, prompt governance_check.*
- **Review help**: summarise a merge request's conflicts and suggest a decision for each, with reasons (the person decides). *Built: get_merge_request, decide_merge_request.*
- **Explain why a commit is blocked** and what would fix it. *Built: why_commit_blocked.*

## 8. Surveys and maturity (38.1, 40)
- **Make a survey from plain words**: "ask the architects how they use the repository, five questions", as a draft. *Built: create_survey, prompt survey_from_words.*
- **Send, remind and close** a survey. *Built: survey_action.*
- **Summarise results**, and for a maturity assessment (Super Admins only) the gaps against target with suggested next
  steps. *Built: survey_results, maturity_overview.*

## 9. Scenarios (27.1)
- **What-if**: "make a scenario where we replace the Policy Admin system with the new platform and show the impact",
  as a scenario model to compare with today. *Built in 27.1 (scenario planning).*

## 10. Administration (Super Admins and IT Admins only)
- **Usage questions** (35): "which models haven't been used this quarter?" *Built: usage_insight.*
- **Housekeeping**: run a dry run and explain it (confirming stays in the screens). *Built: housekeeping_dry_run.*
- **Own KPIs** (24): "track the number of applications on Windows Server 2012". *Built: add_own_kpi.*
Making credentials, roles or service accounts stays in the screens, never through MCP.
