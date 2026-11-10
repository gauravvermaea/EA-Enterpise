# Phases 26 and 27: MCP (as built, 0.18.0)

Status: **built, to be accepted** (10 Nov 2026, batch 3 run with batch 2, D421). Design: D368, D458, D459; as built:
D482 to D489. Scenario planning (27.1) is in [phase-27.1.md](phase-27.1.md).

## What an assistant can do now
The MCP server had 82 tools and 3 prompts; it now has about **120 tools and 11 prompts**. The full list, by group, is on
the MCP page's **Tools** tab and in [mcp-capabilities.md](mcp-capabilities.md).

| Group | Tools |
|---|---|
| Model operations (D458, D485) | copy_model, find_duplicates, compare_duplicates, merge_duplicates, override_parent, refresh_from_parent, list_merge_requests, get_merge_request, decide_merge_request, model_wizard, common_analysis |
| Cleaning up (D486) | change_entities, tidy_names, find_orphans, why_commit_blocked (and suggest_quality_fix) |
| Analysis (D486) | impact_analysis, application_rationalisation, cost_rollup_analysis, technology_risk_analysis, single_points_of_failure, heat_map_data, what_changed, kpi_trend |
| Writing, governance (D487) | save_report_document, principles_and_standards |
| Surveys, maturity, administration (D488) | list_surveys, create_survey, survey_action, survey_results, maturity_overview, usage_insight, housekeeping_dry_run, add_own_kpi |
| Prompts (D487) | copy_and_clean_up, build_from_material, analyse_a_model, draw_a_view, write_a_report, governance_check, plan_an_adm_project, survey_from_words |

Example: *"Make a copy of the demo estate and remove all duplicates as you see fit"*, then *"Override its parent with it"*:
copy_model (preview, confirm), find_duplicates, compare_duplicates per group, merge_duplicates (preview, confirm),
override_parent (preview, confirm).

## The rules every changing tool follows (D458, D484)
- **The person's own rights**: the tools call the same functions as the screens (merge_back, dedupe, model_wizards,
  model_ops, ...), so the same checks apply; a refusal comes back as an error the assistant passes on.
- **Machine credentials**: a credential that may only read through MCP (phase 25) gets the reading tools only.
- **Preview, then confirm**: the first call returns a preview and a confirm token; the change is made only with the
  same arguments and that token, by the same person, within 30 minutes, once (core.mcp_previews).
- **Tagged first**: the model changed is tagged ("Before … (through MCP)") so it can be restored.
- **Logged as the person's**: the change log (action mcp.<tool>, source mcp) and the AI activity log.
- **Never through MCP**: credentials, roles, service accounts.

## The AI activity log (D482)
Every call: who, when, the tool, the question (the assistant's `why`, else the arguments shortened), the answer's size
and time, what it changed (with links), the model, the machine credential, and the kind (read, preview, change,
refused, error). MCP page > **AI activity**: your own calls; Super Admins and IT Admins see everyone's, by person.
REST: `GET /api/v1/mcp/activity?who=&kind=&tool=&days=`.

## Citations (D482)
Answers carry links back into EA Explorer: models `/#/metamodel/<model>`, entities `/#/metamodel/<model>/entity/<id>`
(relative to the installation's address); the server's instructions ask the assistant to give them with the facts.

## OAuth remote connector (D483)
- On a server, add EA Explorer in the AI app as a custom connector with `https://<host>/mcp`. The app reads
  `/.well-known/oauth-protected-resource/mcp` (served by the MCP server through the proxy), which names Keycloak's realm;
  the person signs in in the browser, and the token carries their own roles.
- Keycloak client **eax-mcp** (public, PKCE S256, audience eax-api) is in the realm. **Administrators add the AI app's
  callback address** to its redirect URIs (Keycloak admin console), or allow dynamic client registration for the app's
  host (client registration policies; give such clients the eax-api audience).
- On a laptop the development token still works (`.\eax` prints it; MCP page > Connect).

## Files
- `services/api/eax/mcp_ops.py` (model operations, preview and confirm), `model_operations.py` (the plain operations,
  also used by 27.1), `mcp_analysis.py`, `mcp_more.py`, `mcp_activity.py`, `api/mcp_activity.py`; `mcp_server.py`
  (citations, the activity log hook, OAuth discovery).
- Migration `0040_mcp_activity` (core.mcp_activity, core.mcp_previews; rows only, D248).
- `deploy/keycloak/realm-eaexplorer.json.tmpl` (eax-mcp), `deploy/proxy/templates/default.conf.template` (discovery).
- Web: `Mcp.jsx` (Connect, AI activity, Tools tabs).
- Sample data: `seed/sample_mcp.py` (D489). Tests: `tests/test_mcp_ops.py`.

## Checked here, and what needs the laptop
- Here: the tests; an end-to-end session against a fresh database (copy the demo estate, merge its four duplicate
  groups, override the parent; refusals for a person without the role and for a read-only credential; every analysis
  tool); the AI activity screens.
- **Laptop / server**: adding EA Explorer as a remote connector in a real AI app and signing in through Keycloak (needs
  a public https address and the app's callback in the eax-mcp client); `.\eax clean-restart` loads the new client.
