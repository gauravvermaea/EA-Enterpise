# MCP server

EA Explorer ships an MCP (Model Context Protocol) server so you can use **your own language model**
(Claude, ChatGPT, an IDE assistant, a local model) with the repository. No model is shipped or
hosted. The start page has an **MCP server** page with ready-to-copy connection settings.

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

## Tools (read only until build phase 6, apart from metamodel drafts)

From phase 3.1 every tool answers as the person whose token it is: they see only the models their
roles and assignments allow (the database enforces it too), and the server refuses to answer when it
cannot tell who is asking. The laptop development token signs in as a Super Admin.

| Tool | What it returns |
| --- | --- |
| `list_models` | Every model you may read, with entity, relationship and type counts |
| `list_library` | The model library: reference models with industry, version and counts by type |
| `get_metamodel(model)` | Layers with their entity types, and the relationship types |
| `describe_entity_type(model, entity_type)` | Attributes (type, required, pick-list values), validation rules, allowed relationships both ways |
| `allowed_relationships(model, source_type, target_type)` | Relationship types allowed from one type to another |
| `get_metamodel_diagram(model, layers?, entity_type?, relationship_types?, include_generic?, include_connected?, with_attributes?)` | The metamodel (one or more layers, or one type and its neighbours) as a Mermaid ER diagram |
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
| `search_entities(text, model?)` | Entities whose name, display ID or description contains the text |

### Metamodel drafts (phase 4, D115, D120, D130)

A language model can draft a metamodel, never change one: a person reviews the draft in **Models >
Metamodel drafts** and applies it, sends it back with comments, or rejects it.

| Tool | What it does |
| --- | --- |
| `get_metamodel_spec(model)` | A model's whole metamodel as one document (eax-metamodel/1), the pattern for drafts |
| `start_metamodel_draft(name, kind?, base?, target?, version?, note?, spec?)` | A new root metamodel (empty or from a copy of `base`) or changes to `target`; `spec` gives everything at once |
| `draft_set_item(draft, section, item)` | Add or change one layer, pick list, attribute, entity type, relationship type, allowed relationship or rule |
| `draft_remove_item(draft, section, code)` | Take an item out (with what depends on it) |
| `draft_replace(draft, spec)` | Replace the whole document |
| `get_metamodel_draft(draft)` | The draft with its checks, differences, review comments, changes since the last review and history |
| `list_metamodel_drafts(status?)` | Your drafts and those you review: draft (waiting for review), returned (sent back), applied, rejected |
| `comment_on_metamodel_draft(draft, body, section?, code?)` | A comment on the draft or on one item |
| `resolve_draft_comment(draft, comment, resolved?)` | Mark a review comment fixed |
| `resubmit_metamodel_draft(draft, note?)` | Send a fixed draft for review again: a new round |
| `get_report_catalogue(model)` | The model's standard reports (SR-01 to SR-30, model overview, heatmaps) with dashboard links, every entity type and attribute with its report view and column (rpt.t_<type>), and which types the standard reports use (phase 5) |

A sent-back draft can be fixed by asking your assistant, for example: "Read the comments on my draft
Retail bank metamodel, fix what they ask, mark them fixed and resubmit it."

Models, entity types and entities can be given by guid or by name. Lists come back as
`{"count": n, "items": [...]}`; errors as `{"error": "..."}`.

## How it is built and kept up to date

`services/api/eax/mcp_server.py` runs in the api container next to the REST API (uvicorn on port
8001 inside Docker, reached only through nginx at `/mcp`, D107; switch it off with `EAX_MCP_ENABLED=false`). Its tools call
`eax.repository`, the same functions as the REST API, so **every build phase adds its repository
functions there and the matching MCP tools at the same time**. Write tools (create and change
content, through the staging and publishing workflow) arrive with data entry.
