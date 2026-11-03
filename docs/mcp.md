# MCP server

EA Explorer ships an MCP (Model Context Protocol) server so you can use **your own language model**
(Claude, ChatGPT, an IDE assistant, a local model) with the repository. No model is shipped or
hosted. The start page has an **MCP server** page with ready-to-copy connection settings.

| | Laptop | Server |
| --- | --- | --- |
| Address | `http://localhost:8001/mcp` (also `https://localhost/mcp`) | `https://<EAX_HOSTNAME>/mcp` |
| Transport | Streamable HTTP | Streamable HTTP |
| Sign-in | `Authorization: Bearer P^55w0rd1234&` (EAX_MCP_DEV_TOKEN) or a Keycloak token | `Authorization: Bearer <Keycloak access token>` |

On a laptop use the plain-http address: MCP clients reject the self-signed certificate of
`https://localhost`. The development token is accepted on laptops only.

## Connect

Claude Code:

```powershell
claude mcp add --transport http eaexplorer http://localhost:8001/mcp --header "Authorization: Bearer P^55w0rd1234&"
```

Claude Desktop (`claude_desktop_config.json`; needs Node.js for `npx`):

```json
{
  "mcpServers": {
    "eaexplorer": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8001/mcp", "--header", "Authorization:${EAX_TOKEN}"],
      "env": { "EAX_TOKEN": "Bearer P^55w0rd1234&" }
    }
  }
}
```

MCP Inspector (to try the tools by hand): `npx @modelcontextprotocol/inspector`, then Transport
*Streamable HTTP*, URL `http://localhost:8001/mcp`, header `Authorization: Bearer P^55w0rd1234&`.

## Tools (build phase 1: read only)

| Tool | What it returns |
| --- | --- |
| `list_models` | Every model you may read, with entity, relationship and type counts |
| `get_metamodel(model)` | Layers with their entity types, and the relationship types |
| `describe_entity_type(model, entity_type)` | Attributes (type, required, pick-list values), validation rules, allowed relationships both ways |
| `allowed_relationships(model, source_type, target_type)` | Relationship types allowed from one type to another |
| `list_entities(model, entity_type?)` | Every entity of a model, or of one type |
| `get_entity(model, entity)` | One entity (guid, display ID or name) with attribute values, relationships, parent and parts |
| `get_entity_table(model, entity_type, name?)` | One type as a table, one column per attribute (`eax.get_entity`) |
| `list_relationships(model)` | Every relationship: source, type, target |
| `search_entities(text, model?)` | Entities whose name, display ID or description contains the text |

Models, entity types and entities can be given by guid or by name. Lists come back as
`{"count": n, "items": [...]}`; errors as `{"error": "..."}`.

## How it is built and kept up to date

`services/api/eax/mcp_server.py` runs in the api container next to the REST API (uvicorn on port
8001, behind the proxy at `/mcp`; switch it off with `EAX_MCP_ENABLED=false`). Its tools call
`eax.repository`, the same functions as the REST API, so **every build phase adds its repository
functions there and the matching MCP tools at the same time**. Write tools (create and change
content, through the staging and publishing workflow) arrive with data entry.
