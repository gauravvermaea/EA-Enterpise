# MCP server

EA Explorer ships an MCP (Model Context Protocol) server so you can use **your own language model**
(Claude, ChatGPT, an IDE assistant, a local model) with the repository. No model is shipped or
hosted. The start page has an **MCP server** page with ready-to-copy connection settings.

It has **82 tools** and **3 guided prompts** (build a project, build a model, fill a model): a language model can read
and analyse the repository and **build in it** (models, entities, relationships, projects, key questions, canvases),
always as the signed-in person and with their permissions; what it adds stays that person's uncommitted change until
committed, and metamodel drafts and quality rules wait for a person's review.

| | Laptop | Server |
| --- | --- | --- |
| Address | `http://localhost/mcp` or `https://localhost/mcp` (both through nginx) | `https://<EAX_HOSTNAME>/mcp` |
| Transport | Streamable HTTP | Streamable HTTP |
| Sign-in | `Authorization: Bearer P^55w0rd1234&` (EAX_MCP_DEV_TOKEN) or a Keycloak token | `Authorization: Bearer <Keycloak access token>` |

Everything goes through nginx (D107). On a laptop the MCP server answers on both
`http://localhost/mcp` (this computer only, no certificate needed) and `https://localhost/mcp`. For
https, trust the local certificate once with `.\eax trust`; MCP clients that run on Node (Claude
Code, `mcp-remote` for Claude Desktop) also need to be told about it, because Node does not read the
Windows certificate store:

```powershell
setx NODE_EXTRA_CA_CERTS "C:\path\to\EA-Explorer\work\data\tls\ca.crt"   # then open a new window
```

The development token is accepted on laptops only.

## Connect

Claude Code:

```powershell
claude mcp add --transport http eaexplorer http://localhost/mcp --header "Authorization: Bearer P^55w0rd1234&"
```

Claude Desktop (`claude_desktop_config.json`; needs Node.js for `npx`):

```json
{
  "mcpServers": {
    "eaexplorer": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost/mcp", "--header", "Authorization:${EAX_TOKEN}"],
      "env": { "EAX_TOKEN": "Bearer P^55w0rd1234&" }
    }
  }
}
```

On Windows the file is `%APPDATA%\Claude\claude_desktop_config.json` (Claude Desktop: *Settings >
Developer > Edit Config*). Save it, quit Claude Desktop completely (also from the system tray) and
start it again; *eaexplorer* then appears under the tools. The token goes in `env` on purpose: its
`^` and `&` would be mangled if it were passed on a Windows command line.

**Why not "Add custom connector"?** The *Connectors > Add custom connector* screen in Claude Desktop
and claude.ai asks for an `https://` address because Anthropic's servers make those calls, not your
computer. They cannot reach `localhost` at all, even over https. On a laptop use Claude Code or the
config file above: both run on your computer and talk to `http://localhost/mcp` on your own computer.
Custom connectors become possible on a server installation with a public https address and sign-in
through Keycloak (requirement AI-011, build phase 26).

If `claude mcp add` on Windows reports a broken header or token, the `&` was taken by the command
shell: run the command in PowerShell (not cmd), or set `EAX_MCP_DEV_TOKEN` in `work\eaexplorer.env`
to a value with letters and digits only and restart the api container.

MCP Inspector (to try the tools by hand): `npx @modelcontextprotocol/inspector`, then Transport
*Streamable HTTP*, URL `http://localhost/mcp`, header `Authorization: Bearer P^55w0rd1234&`.

## Tools

From phase 3.1 every tool answers as the person whose token it is: they see only the models their
roles and assignments allow (the database enforces it too), and the server refuses to answer when it
cannot tell who is asking. The laptop development token signs in as a Super Admin.

| Tool | What it returns |
| --- | --- |
| `list_models` | Every model you may read, with entity, relationship and type counts |
| `list_library` | The model library: reference models with industry, version and counts by type |
| `get_metamodel(model)` | Domains with their entity types, and the relationship types |
| `describe_entity_type(model, entity_type)` | Attributes (type, required, pick-list values), validation rules, allowed relationships both ways |
| `allowed_relationships(model, source_type, target_type)` | Relationship types allowed from one type to another |
| `get_metamodel_diagram(model, domains?, entity_type?, relationship_types?, include_generic?, include_connected?, with_attributes?)` | The metamodel (one or more domains, or one type and its neighbours) as a Mermaid ER diagram |
| `list_entities(model, entity_type?)` | Every entity of a model, or of one type |
| `get_entity(model, entity)` | One entity (guid, display ID or name) with attribute values, relationships, parent and parts |
| `get_entity_table(model, entity_type, name?)` | One type as a table, one column per attribute (`eax.get_entity`) |
| `list_relationships(model, relationship_type?)` | Every relationship (or of one type): source, type, target, allowed by the metamodel or not |
| `list_relationship_types(model)` | Relationship types with how often each is used and how many uses break the rules |
| `check_entities(model, entity_type)` | One type's entities with their values and validation results (errors, warnings, messages) |
| `get_entity_rules(model, entity)` | Every rule applied to the entity (values, duplicates, relationships it must have): passed, failed or not applicable; and each relationship against the metamodel |
| `get_entity_history(model, entity)` | Every change to the entity, its attribute values and relationships: when, who, old and new values |
| `get_neighbourhood(model, entity, depth?, direction?, relationship_types?)` | The entity and everything within 1 to 3 steps (relationships and parent hierarchy) as nodes and edges; `direction` out or in follows one way only (impact, dependencies; up to 6 steps) |
| `find_paths(model, source, target, max_steps?, relationship_types?)` | The shortest chains connecting two entities, through relationships either way and the parent hierarchy |
| `get_family_tree(model, entity, levels?)` | Every parent of an entity up to the top and its parts down `levels` levels |
| `get_entity_as_of(model, entity, event?, at?)` | The entity as it was after a history event or at a time: every field, value and relationship then beside now |
| `get_metamodel_history(model)` | Every published metamodel version with its note, who and when, and each change: what, old and new values |
| `compare_metamodel_versions(model, from_version, to_version?)` | What differs in the metamodel between two versions (`to_version` defaults to the current one) |
| `list_failing_checks(model, entity_type?)` | Every entity failing a check (rules, mandatory values, relationships outside the metamodel), with counts by type, rule and severity |
| `search_entities(text, model?, entity_type?, attribute?, tag?)` | Search every model you may read (or one) in names, display IDs, descriptions, tags and attribute values; optionally one type, one attribute or one tag; each result says where it matched (phase 7) |
| `list_views(model?)` | The views (VP-01 to VP-49 and the organisation's own); with a model, how many of its entities each shows (phase 8.2) |
| `model_through_view(model, view)` | A model through one view: its elements with every value, and the relationships the view shows (phase 8.2) |
| `value_stream_map(model)` | Value streams, their stages in order and the capabilities enabling each, with their values (phase 8.2) |
| `roadmap(model)` | Work packages, deliverables and plateaus with dates and what each delivers (phase 8.2) |
| `list_model_tags(model)` | A model's tags (frozen snapshots): name, when, by whom, commit, locked (phase 8.3) |
| `compare_models(left, right, left_tag, right_tag)` | Two models, or tags of them: per type kept, changed, new, eliminated, the differences with their fields, relationships, metamodel (phase 8.3) |
| `list_gap_analyses(model?)` | The TOGAF gap analyses you may see, or those stored in one model (phase 8.3, D177) |
| `gap_analysis(analysis)` | One gap analysis: the model it is stored in, baseline and target, when compared, every gap with its changes, resolution and work packages (phase 8.3) |

### Metamodel drafts (phase 4, D115, D120, D130)

A language model can draft a metamodel, never change one: a person reviews the draft in **Models >
Metamodel drafts** and applies it, sends it back with comments, or rejects it.

| Tool | What it does |
| --- | --- |
| `get_metamodel_spec(model)` | A model's whole metamodel as one document (eax-metamodel/1), the pattern for drafts |
| `start_metamodel_draft(name, kind?, base?, target?, version?, note?, spec?)` | A new root metamodel (empty or from a copy of `base`) or changes to `target`; `spec` gives everything at once |
| `draft_set_item(draft, section, item)` | Add or change one domain, pick list, attribute, entity type, relationship type, allowed relationship or rule |
| `draft_remove_item(draft, section, code)` | Take an item out (with what depends on it) |
| `draft_replace(draft, spec)` | Replace the whole document |
| `get_metamodel_draft(draft)` | The draft with its checks, differences, review comments, changes since the last review and history |
| `list_metamodel_drafts(status?)` | Your drafts and those you review: draft (waiting for review), returned (sent back), applied, rejected |
| `comment_on_metamodel_draft(draft, body, section?, code?)` | A comment on the draft or on one item |
| `resolve_draft_comment(draft, comment, resolved?)` | Mark a review comment fixed |
| `resubmit_metamodel_draft(draft, note?)` | Send a fixed draft for review again: a new round |
| `list_my_notifications(show?, category?, model?)` | Your notifications (phase 8.1): open, waiting for action, resolved or all; by kind or model. Resolving them stays in the screens |
| `list_my_requests(box?, status?)` | Requests sent to you or by you (phase 8.1), active, closed or all |
| `get_request(request)` | One of your requests by number, with its comments and status trail |
| `send_request(to, subject, body?)` | Send a request to another person on your behalf, like a ticket (phase 8.1); they move it along in the screens |
| `get_report_catalogue(model)` | The model's standard reports (SR-01 to SR-30, model overview, heatmaps) with dashboard links, every entity type and attribute with its report view and column (rpt.t_<type>), and which types the standard reports use (phase 5) |

A sent-back draft can be fixed by asking your assistant, for example: "Read the comments on my draft
Retail bank metamodel, fix what they ask, mark them fixed and resubmit it."

Models, entity types and entities can be given by guid or by name. Lists come back as
`{"count": n, "items": [...]}`; errors as `{"error": "..."}`.

### Data quality (phase 12, D239)

| Tool | What it does |
| --- | --- |
| `quality_summary(model)` | The model's quality score, completeness, rules passed, fresh, orphans and seals, the weakest types and owners, and the trend |
| `quality_findings(model, entity_type?, owner?, rule?, mine?)` | The entities with problems and why, with the person responsible ("what are my gaps?") |
| `suggest_quality_fix(model, entity, changes)` | Fills in what is missing as your uncommitted change; Claude never commits it |
| `draft_quality_rule(model, rule, save?)` | Shows what a rule would find; with `save=true` it is saved, and a Model Admin's rule waits for a Super Admin's approval |

### Building with an assistant (phase 13.0.6, owner 7 Nov 2026)

Your assistant can make models and projects and work in them, as you, with your permissions. It should call
`how_to_build` first; the prompts **build_a_project**, **build_a_model** and **fill_a_model** start a guided session. It
always asks for your yes before it makes a model or a project.

| Tool | What it does |
| --- | --- |
| `how_to_build()` | The order of work and the tools to use (read first) |
| `create_model(name, start, source, copy?, tag?)` | A project model: `empty` from a root metamodel, a `copy` (now, or at a `tag`), or a `child` that can merge back |
| `add_entities(model, entity_type, rows)` | Up to 500 entities of one type, with values by attribute code |
| `update_entity(model, entity, ...)` | Change an entity's name, description, values or tags |
| `add_relationships(model, rows)` | Up to 1000 relationships; the metamodel's rules apply |
| `list_my_changes(model)` · `commit_my_changes(model, message)` · `request_my_commit(model)` | In a working model, what the assistant adds is your uncommitted change until committed |
| `tag_model(model, name)` | A baseline to compare with or copy from |
| `list_drawn_views(model)` · `get_drawn_view(model, view, version?, with_xml?)` · `create_drawn_view(model, name, entities, include_relationships?)` | A model's drawn views (draw.io, D354): list them, read one (what is on it, as it is now), make one of chosen entities laid out by domain, saved as you |
| `list_projects()` · `list_project_templates()` · `get_project(project, part)` | Read projects (summary, steps, documents, classes, approvals, views) |
| `create_project(name, template, models, goals?)` | A project from a template, with its models (referred, added, derived, created) and goals |
| `add_project_step` · `complete_project_step` · `repeat_project_step` | Steps at any time; completions kept as sub steps |
| `add_document_class` · `set_document_class_needed` · `set_document_tags` | Document classes and tags |
| `accept_document(project, document, evidence)` · `send_document_for_approval` | Accepted with evidence, or approval by the sign-off people (quorum) |

| `save_key_question(project, question, asked_by?, approach?, views?, ...)` · `answer_key_question(project, question_id, answer, documents?, ...)` · `key_question_decision(project, question_id, decision, note?, stakeholder?)` | A project's key questions (D341, D342): add or change one with the views that answer it, answer it with links to the artifacts, record the stakeholder's acceptance |
| `business_model_canvas(project, canvas?, compare_with?)` · `change_business_model_canvas(project, action, ...)` | A project's Business Model Canvases (D344): list, read block by block, compare two; add, change or cross out items, make a working copy, make a clean canvas from one |

Documents themselves (Word, Excel) are still uploaded on the project's Repository tab.

## How it is built and kept up to date

`services/api/eax/mcp_server.py` runs in the api container next to the REST API (uvicorn on port
8001 inside Docker, reached only through nginx at `/mcp`, D107; switch it off with `EAX_MCP_ENABLED=false`). Its tools call
`eax.repository`, the same functions as the REST API, so **every build phase adds its repository
functions there and the matching MCP tools at the same time**. Write tools (create and change
content, through the staging and publishing workflow) arrive with data entry.

## Phases 26/27 (0.18.0): model operations, analysis, the AI activity log, the remote connector
See [phase-26-27.md](phase-26-27.md) and [mcp-capabilities.md](mcp-capabilities.md). In short:
- about 120 tools and 11 prompts; every tool that changes something answers first with a **preview and a confirm
  token**, and changes only when called again with the same arguments and `confirm=<token>`; the model is **tagged
  first**; a read-only credential gets the reading tools only (D458, D484);
- every call is in the **AI activity log** (MCP page > AI activity; `GET /api/v1/mcp/activity`) (D482);
- answers carry **links** back to models and entities (D482);
- on a server, add EA Explorer to an AI app as a **remote connector** (`https://<host>/mcp`) and sign in through
  Keycloak in the browser: the Keycloak client is `eax-mcp`; add the app's callback address to it (D483).
