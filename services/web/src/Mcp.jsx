// How to connect a language model to the EA Explorer MCP server; the AI activity log (phases 26/27, D482, D483).
import { useState } from "react";
import { config } from "./config";
import { fmtDateTime } from "./fmt";
import { useApi } from "./ModelViews";

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
      {tab === "tools" && <ToolList />}
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

// every MCP tool and what it does (owner, 13 Nov 2026, R2.54: "list all MCP tools and what they do on the MCP page"),
// read from the tools' own code by the API, so the list is always the server's
function ToolList() {
  const { data, error } = useApi("/api/v1/mcp/tools");
  const [find, setFind] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const shown = data.tools.filter((t) => !find || `${t.name} ${t.what}`.toLowerCase().includes(find.toLowerCase()));
  const areas = [...new Set(shown.map((t) => t.area))];
  return (
    <>
      <p className="quiet">The {data.count} tools an assistant can use. Each acts with your own rights; those marked <b>changes</b> preview the
        change and make it only after you agree.</p>
      <input type="search" placeholder="Find a tool" value={find} onChange={(e) => setFind(e.target.value)} aria-label="Find a tool" />
      {areas.map((a) => (
        <div key={a}>
          <h2>{a}</h2>
          <table className="grid-table">
            <tbody>{shown.filter((t) => t.area === a).map((t) => (
              <tr key={t.name}>
                <th><code>{t.name}</code>{t.changes && <span className="badge"> changes</span>}</th>
                <td>{t.what}
                  {t.params.length > 0 && <div className="quiet small">{t.params.map((p) => (
                    <span key={p.name}><code>{p.name}</code>{p.required ? "" : ` (default ${p.default})`}{" "}</span>))}</div>}
                </td>
              </tr>))}</tbody>
          </table>
        </div>))}
    </>
  );
}
