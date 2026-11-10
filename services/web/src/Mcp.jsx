// How to connect a language model to the EA Explorer MCP server; the AI activity log (phases 26/27, D482, D483).
import { useState } from "react";
import { config } from "./config";
import { fmtDateTime } from "./fmt";
import { useApi } from "./ModelViews";

const TOOLS = [
  ["list_models", "Every model you may read, with counts"],
  ["list_library", "The model library: reference models with industry, version and counts by type"],
  ["get_metamodel", "A model's domains, entity types and relationship types"],
  ["describe_entity_type", "Attributes, rules and allowed relationships of one type"],
  ["allowed_relationships", "Which relationships the metamodel allows from one type to another"],
  ["get_metamodel_diagram", "The metamodel (domains, or one type and its neighbours) as a Mermaid ER diagram"],
  ["list_entities", "Every entity of a model, or of one type"],
  ["get_entity", "One entity with its attribute values and relationships"],
  ["get_entity_table", "One type as a table, one column per attribute (eax.get_entity)"],
  ["list_relationships", "Every relationship of a model, or of one type, marked allowed or not"],
  ["list_relationship_types", "Relationship types with how often each is used"],
  ["check_entities", "One type's entities with their values and validation errors and warnings"],
  ["get_entity_history", "Every change to an entity, its values and relationships"],
  ["get_neighbourhood", "An entity and everything connected to it; or one way only (impact, dependencies)"],
  ["get_entity_rules", "Every rule applied to an entity and its relationships: passed, failed or not applicable"],
  ["get_entity_as_of", "An entity as it was at a point in its history, beside now"],
  ["get_metamodel_history", "Every metamodel version: what changed, who and when"],
  ["compare_metamodel_versions", "What differs between two metamodel versions"],
  ["list_failing_checks", "Every entity failing a check, with counts by type, rule and severity"],
  ["find_paths", "The shortest chains connecting two entities"],
  ["get_family_tree", "An entity's parents up to the top and its parts below"],
  ["search_entities", "Find entities by name, display ID or description"],
  ["get_metamodel_spec", "A model's whole metamodel as one document (eax-metamodel/1), to start a draft from"],
  ["start_metamodel_draft", "Start a metamodel draft: a new root metamodel (empty or from a copy) or changes to a model, optionally from a whole document"],
  ["draft_set_item", "Add or change one item in a draft: a domain, pick list, attribute, entity type, relationship type, allowed relationship or rule"],
  ["draft_remove_item", "Take one item out of a draft"],
  ["draft_replace", "Replace a draft's whole metamodel document in one go"],
  ["get_metamodel_draft", "A draft with its checks, differences, review comments, changes since the last review and history"],
  ["list_metamodel_drafts", "Metamodel drafts: waiting for review, sent back for changes, applied or rejected"],
  ["comment_on_metamodel_draft", "Comment on a draft or on one of its items"],
  ["resolve_draft_comment", "Mark a review comment fixed"],
  ["resubmit_metamodel_draft", "Send a fixed draft for review again: a new round"],
];

// phases 26/27 (D458, D459): what an assistant can do; every change is previewed, confirmed and tagged first
const GROUPS = [
  ["Model operations", "copy_model, find_duplicates, compare_duplicates, merge_duplicates, override_parent, refresh_from_parent, list_merge_requests, get_merge_request, decide_merge_request, model_wizard, common_analysis, tag_model, compare_models"],
  ["Cleaning up", "change_entities (bulk fixes), tidy_names, find_orphans, suggest_quality_fix, why_commit_blocked"],
  ["Building from material", "add_entities, add_relationships, start_metamodel_draft, prompts build_from_material and fill_a_model"],
  ["Analysis", "impact_analysis, application_rationalisation, cost_rollup_analysis, technology_risk_analysis, single_points_of_failure, heat_map_data, what_changed, kpi_trend"],
  ["Views", "create_drawn_view, get_drawn_view, list_drawn_views, prompt draw_a_view"],
  ["Writing", "save_report_document (a Word document on the project's Repository tab), prompt write_a_report"],
  ["Projects and governance", "principles_and_standards, create_project, add_project_step, prompts governance_check and plan_an_adm_project"],
  ["Surveys and maturity", "list_surveys, create_survey, survey_action, survey_results, maturity_overview (Super Admins)"],
  ["Administration", "usage_insight, housekeeping_dry_run (Super Admins and IT Admins), add_own_kpi (Model Admins)"],
];
const KINDS = [["", "Every kind"], ["read", "Read"], ["preview", "Preview"], ["change", "Change"], ["refused", "Refused"], ["error", "Error"]];

function Activity() {
  const [kind, setKind] = useState("");
  const [days, setDays] = useState(30);
  const [who, setWho] = useState("");
  const [open, setOpen] = useState(null);
  const q = new URLSearchParams({ days: String(days), ...(kind ? { kind } : {}), ...(who ? { who } : {}) });
  const { data, error } = useApi(`/api/v1/mcp/activity?${q}`);
  if (error) return <p className="status error">{error}</p>;
  if (!data) return <p><span className="spinner" aria-hidden="true" /> Loading the AI activity…</p>;
  return (
    <div className="mcp-activity">
      <p className="quiet">
        Every call an AI assistant made through MCP{data.admin ? ", by everyone (you are a Super Admin or IT Admin)" : ", as you"}:
        the tool, the question, how big the answer was and what it changed. Changes are always previewed first, confirmed,
        and the model tagged before.
      </p>
      <div className="toolbar">
        <label>Kind <select value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
        <label>Last <select value={days} onChange={(e) => setDays(Number(e.target.value))}>{[1, 7, 30, 90, 365].map((d) => <option key={d} value={d}>{d} days</option>)}</select></label>
        {data.admin && (
          <label>Person <select value={who} onChange={(e) => setWho(e.target.value)}>
            <option value="">Everyone</option><option value="me">Me</option>
            {data.people.map((p) => <option key={p.username} value={p.username}>{p.username} ({p.calls})</option>)}
          </select></label>
        )}
      </div>
      <div className="toolbar" role="group" aria-label="Calls by kind" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {Object.entries(data.by_kind).map(([k, n]) => (
          <button key={k} className={kind === k ? "primary" : ""} aria-pressed={kind === k} onClick={() => setKind(kind === k ? "" : k)}>
            <strong>{n}</strong> {KINDS.find(([c]) => c === k)?.[1]}
          </button>
        ))}
      </div>
      {data.calls.length === 0 ? <p className="quiet">No AI activity in this period.</p> : (
        <table className="grid-table">
          <thead><tr><th>When</th>{data.admin && <th>Who</th>}<th>Tool</th><th>Kind</th><th>Question</th><th>Model</th><th>Answer</th><th>Changed</th></tr></thead>
          <tbody>
            {data.calls.map((c) => (
              <tr key={c.id} className={`ai-${c.kind}`} onClick={() => setOpen(open === c.id ? null : c.id)} style={{ cursor: "pointer" }}>
                <td className="nowrap small">{fmtDateTime(c.at)}</td>
                {data.admin && <td className="small">{c.username}{c.credential && <span className="quiet"> · {c.credential}</span>}</td>}
                <td><code>{c.tool}</code></td>
                <td><span className={`badge ai-kind-${c.kind}`}>{c.kind}</span></td>
                <td>{c.summary}{c.error && <div className="small status error">{c.error}</div>}
                  {open === c.id && <pre className="small">{JSON.stringify(c.arguments, null, 2)}</pre>}</td>
                <td className="small">{c.model}</td>
                <td className="small nowrap">{c.result_size > 1024 ? `${Math.round(c.result_size / 1024)} KB` : `${c.result_size} chars`} · {c.ms} ms</td>
                <td className="small">{(c.changes || []).map((x, i) => <div key={i}>{x.link ? <a href={x.link.replace(/^\//, "")}>{x.what}</a> : x.what}
                  {x.message && <span className="quiet"> {x.message}</span>}</div>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data.by_tool.length > 0 && <p className="quiet small">Most used: {data.by_tool.map((t) => `${t.tool} (${t.calls})`).join(", ")}</p>}
    </div>
  );
}

function Connector({ url }) {
  const { data } = useApi("/api/v1/mcp/connector");
  return (
    <>
      <h2>Add as a remote connector (sign in in the browser)</h2>
      <p className="quiet">
        On a server install, add EA Explorer as a custom connector in your AI app with the address below. The app finds
        the sign-in through the OAuth discovery at <code>{data?.resource_metadata || `${url.replace(/\/mcp$/, "")}/.well-known/oauth-protected-resource/mcp`}</code>;
        you sign in to EA Explorer in the browser and the assistant then works with your own roles. Your administrator adds
        the AI app's callback address to the Keycloak client <code>{data?.client_id || "eax-mcp"}</code>, or allows the app to
        register itself (Keycloak's client registration policies).
      </p>
      <table className="facts"><tbody>
        <tr><th>Connector address</th><td><code>{data?.url || url}</code></td></tr>
        <tr><th>Sign-in</th><td>OAuth 2 with PKCE through Keycloak: <code>{data?.authorization_server || ""}</code></td></tr>
        <tr><th>Client</th><td><code>{data?.client_id || "eax-mcp"}</code> (public)</td></tr>
      </tbody></table>
    </>
  );
}

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
  const tab = (window.location.hash.split("/")[2] || "connect").split("?")[0];
  const tabs = [["connect", "Connect"], ["activity", "AI activity"], ["tools", "Tools"]];
  const laptop = config.deployment === "laptop";
  // Laptop: plain http through nginx works without trusting a certificate; https works once the local
  // certificate is trusted (.\eax trust) and Node is told about it (NODE_EXTRA_CA_CERTS), D107.
  const url = laptop ? "http://localhost/mcp" : `${config.publicUrl}/mcp`;
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
      <div className="tabs" role="tablist">
        {tabs.map(([k, n]) => <a key={k} role="tab" aria-selected={tab === k} className={`tab${tab === k ? " on" : ""}`} href={`#/mcp/${k}`}>{n}</a>)}
      </div>
      {tab === "activity" && <Activity />}
      {tab === "tools" && (
        <>
          <h2>What an assistant can do</h2>
          <p className="quiet">Every tool acts with your own rights. A tool that changes something answers first with a preview and a
            confirm token; the change is made only when the assistant calls it again with that token, after you agree, and the
            model is tagged first so it can be restored.</p>
          <table className="grid-table"><tbody>{GROUPS.map(([g, t]) => <tr key={g}><th>{g}</th><td><code className="small">{t}</code></td></tr>)}</tbody></table>
          <h2>Reading tools</h2>
          <table className="grid-table">
            <tbody>{TOOLS.map(([n, d]) => <tr key={n}><th><code>{n}</code></th><td>{d}</td></tr>)}</tbody>
          </table>
          <p className="quiet">Try asking: "Make a copy of the demo estate and remove all duplicates as you see fit", then "Override its parent with it".</p>
        </>
      )}
      {tab === "connect" && <>
      <p className="quiet">
        Connect your own language model to the repository through the Model Context Protocol. No model is
        shipped: use your own assistant or a local model. It reads, analyses and, with your yes, changes the
        repository with your own rights; every call is in the AI activity log.
      </p>
      <table className="facts">
        <tbody>
          <tr><th>Address</th><td><code>{url}</code>{laptop && <span className="quiet"> (this computer only), or <code>{config.publicUrl}/mcp</code> once you have run <code>.\eax trust</code> and
            set <code>NODE_EXTRA_CA_CERTS</code> to <code>work\data\tls\ca.crt</code></span>}</td></tr>
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
      {!laptop && <Connector url={url} />}
      </>}
    </section>
  );
}
