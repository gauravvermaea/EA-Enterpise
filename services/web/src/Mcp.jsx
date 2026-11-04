// How to connect a language model to the EA Explorer MCP server.
import { useState } from "react";
import { config } from "./config";

const TOOLS = [
  ["list_models", "Every model you may read, with counts"],
  ["list_library", "The model library: reference models with industry, version and counts by type"],
  ["get_metamodel", "A model's layers, entity types and relationship types"],
  ["describe_entity_type", "Attributes, rules and allowed relationships of one type"],
  ["allowed_relationships", "Which relationships the metamodel allows from one type to another"],
  ["get_metamodel_diagram", "The metamodel (layers, or one type and its neighbours) as a Mermaid ER diagram"],
  ["list_entities", "Every entity of a model, or of one type"],
  ["get_entity", "One entity with its attribute values and relationships"],
  ["get_entity_table", "One type as a table, one column per attribute (eax.get_entity)"],
  ["list_relationships", "Every relationship of a model, or of one type, marked allowed or not"],
  ["list_relationship_types", "Relationship types with how often each is used"],
  ["check_entities", "One type's entities with their values and validation errors and warnings"],
  ["get_entity_history", "Every change to an entity, its values and relationships"],
  ["get_neighbourhood", "An entity and everything connected to it; or one way only (impact, dependencies)"],
  ["get_entity_as_of", "An entity as it was at a point in its history, beside now"],
  ["find_paths", "The shortest chains connecting two entities"],
  ["get_family_tree", "An entity's parents up to the top and its parts below"],
  ["search_entities", "Find entities by name, display ID or description"],
];

function Snippet({ title, text }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="snippet">
      <div className="snippet-head">
        <strong>{title}</strong>
        <button onClick={() => navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  );
}

export default function Mcp() {
  const laptop = config.deployment === "laptop";
  const url = laptop ? "http://localhost:8001/mcp" : `${config.publicUrl}/mcp`;
  const token = laptop ? "P^55w0rd1234&" : "<a Keycloak access token>";
  const desktop = JSON.stringify({
    mcpServers: {
      eaexplorer: {
        command: "npx",
        args: ["-y", "mcp-remote", url, "--header", "Authorization:${EAX_TOKEN}"],
        env: { EAX_TOKEN: `Bearer ${token}` },
      },
    },
  }, null, 2);
  return (
    <section>
      <h1>MCP server</h1>
      <p className="quiet">
        Connect your own language model to the repository through the Model Context Protocol. No model is
        shipped: use Claude, ChatGPT, an IDE assistant or a local model. Read only in this build; every
        build phase adds tools.
      </p>
      <table className="facts">
        <tbody>
          <tr><th>Address</th><td><code>{url}</code>{laptop && <span className="quiet"> (also {config.publicUrl}/mcp through the proxy)</span>}</td></tr>
          <tr><th>Transport</th><td>Streamable HTTP</td></tr>
          <tr><th>Sign-in</th><td>Header <code>Authorization: Bearer {token}</code>
            {laptop ? <span className="quiet"> (the laptop development token, EAX_MCP_DEV_TOKEN)</span>
              : <span className="quiet"> (the same token the REST API takes)</span>}</td></tr>
        </tbody>
      </table>

      <h2>Connect</h2>
      <Snippet title="Claude Code" text={`claude mcp add --transport http eaexplorer ${url} --header "Authorization: Bearer ${token}"`} />
      <Snippet title="Claude Desktop (claude_desktop_config.json, needs Node.js)" text={desktop} />
      {laptop && (
        <p className="quiet">
          Claude Desktop: Settings &gt; Developer &gt; Edit Config, paste the block above, then quit Claude Desktop
          completely and start it again. Do not use <em>Connectors &gt; Add custom connector</em>: it needs a public
          https address, because Anthropic's servers make those calls and cannot reach localhost.
        </p>
      )}
      <Snippet title="Test with the MCP Inspector" text={`npx @modelcontextprotocol/inspector\n# Transport: Streamable HTTP, URL: ${url}\n# Authentication: header Authorization = Bearer ${token}`} />

      <h2>Tools in this build</h2>
      <table className="grid-table">
        <tbody>{TOOLS.map(([n, d]) => <tr key={n}><th><code>{n}</code></th><td>{d}</td></tr>)}</tbody>
      </table>
      <p className="quiet">Try asking: "Which applications realise the Claims Management capability in the sample insurance model?"</p>
    </section>
  );
}
