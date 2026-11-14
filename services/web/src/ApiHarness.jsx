// The API test harness (R3.16, D662): Self-test › API harness. Pick an endpoint from the API's own description, fill its
// form, call it as yourself or as one of a session's test roles, and see the status, time, headers and answer, with the
// same call as a curl line; save a call as a case with the answer expected, and run the cases one by one or all
// together (the self-test runs them too). Reads go anywhere; writes only into test data (the server refuses others).
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./auth";

const ROLES = ["super-admin", "it-admin", "model-creator", "library-admin", "model-admin", "model-sub-admin", "committer",
  "architect", "history-viewer", "report-viewer", "no-role"];

export function pathParams(path) {
  return [...String(path || "").matchAll(/\{([^}]+)\}/g)].map((m) => m[1].split(":").pop());
}

export function filledPath(path, values) {
  return String(path || "").replace(/\{([^}]+)\}/g, (all, name) => {
    const v = values[name.split(":").pop()];
    return v ? encodeURIComponent(v) : all;
  });
}

export default function ApiHarness() {
  const [eps, setEps] = useState(null);
  const [err, setErr] = useState("");
  const [find, setFind] = useState("");
  const [ep, setEp] = useState(null);
  const [values, setValues] = useState({});
  const [query, setQuery] = useState({});
  const [body, setBody] = useState("");
  const [as, setAs] = useState("me");
  const [session, setSession] = useState(null);
  const [roles, setRoles] = useState(["super-admin", "architect", "report-viewer", "no-role"]);
  const [busy, setBusy] = useState("");
  const [answer, setAnswer] = useState(null);
  const [cases, setCases] = useState([]);
  const [results, setResults] = useState(null);
  const [caseName, setCaseName] = useState("");
  const [expectStatus, setExpectStatus] = useState("");

  const loadCases = () => apiFetch("/api/v1/admin/api-harness/cases").then((x) => setCases(x.cases || [])).catch(() => {});
  useEffect(() => {
    apiFetch("/api/v1/admin/api-harness/endpoints").then((x) => setEps(x.endpoints || [])).catch((e) => setErr(e.message));
    loadCases();
  }, []);

  const shown = useMemo(() => {
    const words = find.toLowerCase().split(/\s+/).filter(Boolean);
    return (eps || []).filter((e) => words.every((w) => `${e.method} ${e.path} ${e.area} ${e.summary}`.toLowerCase().includes(w)));
  }, [eps, find]);
  const groups = useMemo(() => shown.reduce((acc, e) => { (acc[e.area] = acc[e.area] || []).push(e); return acc; }, {}), [shown]);

  const pick = (e) => {
    setEp(e); setAnswer(null); setErr("");
    const v = {};
    for (const name of pathParams(e.path)) v[name] = session?.ids?.[name] || session?.ids?.[name.replace(/_id$/, "")] || "";
    setValues(v); setQuery({});
    setBody(e.writes && e.example != null ? JSON.stringify(e.example, null, 2) : "");
    setCaseName(`${e.method.toUpperCase()} ${e.path}`);
  };

  async function start() {
    setBusy("session"); setErr("");
    try { const s = await apiFetch("/api/v1/admin/api-harness/sessions", { method: "POST", body: JSON.stringify({ roles }) }); setSession(s); }
    catch (e) { setErr(e.message); }
    setBusy("");
  }
  async function endSession() {
    if (!session) return;
    setBusy("end");
    try { await apiFetch(`/api/v1/admin/api-harness/sessions/${session.session}/end`, { method: "POST" }); setSession(null); setAs("me"); }
    catch (e) { setErr(e.message); }
    setBusy("");
  }
  async function send() {
    if (!ep) return;
    let parsed;
    if (ep.writes && body.trim()) {
      try { parsed = JSON.parse(body); } catch (e) { setErr(`The body is not JSON: ${e.message}`); return; }
    }
    setBusy("call"); setErr(""); setAnswer(null);
    try {
      const out = await apiFetch("/api/v1/admin/api-harness/call", { method: "POST", body: JSON.stringify({
        session: session?.session, method: ep.method, path: filledPath(ep.path, values), query, body: parsed, as }) });
      setAnswer(out);
    } catch (e) { setErr(e.message); }
    setBusy("");
  }
  async function saveCase() {
    if (!ep) return;
    let parsed = null;
    try { parsed = ep.writes && body.trim() ? JSON.parse(body) : null; } catch (e) { setErr(`The body is not JSON: ${e.message}`); return; }
    try {
      await apiFetch("/api/v1/admin/api-harness/cases", { method: "POST", body: JSON.stringify({
        name: caseName, method: ep.method, path: ep.path, query, body: parsed, as: as === "me" ? "super-admin" : as,
        expect_status: expectStatus ? Number(expectStatus) : answer?.status }) });
      loadCases();
    } catch (e) { setErr(e.message); }
  }
  async function runCases(ids) {
    if (!session) { setErr("Start a session first: the cases run in its test data."); return; }
    setBusy("cases"); setResults(null);
    try { setResults(await apiFetch("/api/v1/admin/api-harness/cases/run", { method: "POST", body: JSON.stringify({ session: session.session, ids }) })); }
    catch (e) { setErr(e.message); }
    setBusy("");
  }
  async function deleteCase(c) {
    try { await apiFetch(`/api/v1/admin/api-harness/cases/${c.id}`, { method: "DELETE" }); loadCases(); } catch (e) { setErr(e.message); }
  }

  return (
    <div className="api-harness">
      <p className="quiet small">Call any endpoint as yourself, or as one of a session's test roles in its own test data. Reads go anywhere;
        writes only into test data. Every call is in the audit trail. Also from the command line: <code>eax test api GET /api/v1/models --as architect</code>.</p>
      <div className="card harness-session">
        {session ? <p>Session {session.session}: roles {session.roles.join(", ")}; test data {Object.entries(session.ids || {})
          .filter(([k]) => ["model", "other_model", "project", "entity"].includes(k)).map(([k, v]) => `${k} ${String(v).slice(0, 8)}`).join(", ")}{" "}
          <button disabled={!!busy} onClick={endSession}>End the session (remove its test data)</button></p>
          : <div>
            <p className="small">A session makes test accounts for the roles ticked, and its own models and project (about a minute).</p>
            <div className="harness-roles">{ROLES.map((r) => (
              <label key={r} className="small"><input type="checkbox" checked={roles.includes(r)}
                onChange={(e) => setRoles(e.target.checked ? [...roles, r] : roles.filter((x) => x !== r))} /> {r}</label>))}</div>
            <button className="primary" disabled={!!busy} onClick={start}>{busy === "session" ? "Starting…" : "Start a session"}</button>
          </div>}
      </div>
      {err && <p className="status bad">{err}</p>}
      <div className="harness-panes">
        <div className="harness-list">
          <input placeholder="Find an endpoint (words: area, path, method)" value={find} onChange={(e) => setFind(e.target.value)} aria-label="Find an endpoint" />
          {!eps && !err && <p>Loading…</p>}
          {Object.entries(groups).map(([area, list]) => (
            <details key={area} open={!!find}>
              <summary>{area} <span className="quiet small">({list.length})</span></summary>
              <ul>{list.map((e) => (
                <li key={`${e.method} ${e.path}`}>
                  <button className={`linkish harness-ep${ep === e ? " on" : ""}`} onClick={() => pick(e)} title={e.summary}>
                    <b className={`method m-${e.method}`}>{e.method.toUpperCase()}</b> {e.path}</button></li>))}</ul>
            </details>))}
        </div>
        <div className="harness-form">
          {!ep ? <p className="quiet">Choose an endpoint on the left.</p> : <>
            <h3><b className={`method m-${ep.method}`}>{ep.method.toUpperCase()}</b> {ep.path}</h3>
            {ep.summary && <p className="small">{ep.summary}</p>}
            {pathParams(ep.path).map((n) => (
              <label key={n} className="harness-field">{n} <input value={values[n] || ""} onChange={(e) => setValues({ ...values, [n]: e.target.value })} /></label>))}
            {ep.params.filter((p) => p.in === "query").map((p) => (
              <label key={p.name} className="harness-field">?{p.name} <input value={query[p.name] || ""} onChange={(e) => setQuery({ ...query, [p.name]: e.target.value })} /></label>))}
            {ep.writes && <label className="harness-field">Body (JSON)<textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} /></label>}
            <label className="harness-field">Call as <select value={as} onChange={(e) => setAs(e.target.value)}>
              <option value="me">yourself</option>
              {(session?.roles || []).map((r) => <option key={r} value={r}>{r} (test account)</option>)}
            </select></label>
            <button className="primary" disabled={!!busy} onClick={send}>{busy === "call" ? "Sending…" : "Send"}</button>
            {answer && <div className="harness-answer">
              <p><span className={`rag ${answer.status < 300 ? "ok" : answer.status < 500 ? "warn" : "bad"}`}>{answer.status}</span> in {answer.ms} ms{answer.cut ? " (the start of the answer)" : ""}</p>
              <details><summary className="small">Headers</summary><pre className="small">{Object.entries(answer.headers || {}).map(([k, v]) => `${k}: ${v}`).join("\n")}</pre></details>
              <pre className="harness-body">{answer.json != null ? JSON.stringify(answer.json, null, 2) : answer.body}</pre>
              <p className="small">The same call: <code>{answer.curl}</code></p>
            </div>}
            <div className="harness-save">
              <label className="small">Save as a case <input value={caseName} onChange={(e) => setCaseName(e.target.value)} aria-label="Case name" /></label>
              <label className="small">expecting status <input value={expectStatus} onChange={(e) => setExpectStatus(e.target.value)} placeholder={answer ? String(answer.status) : "200"} size={4} aria-label="Expected status" /></label>
              <button onClick={saveCase} disabled={!caseName.trim()}>Save case</button>
            </div>
          </>}
        </div>
      </div>
      <h3>Saved cases ({cases.length})</h3>
      {cases.length > 0 && <p><button disabled={!!busy || !session} onClick={() => runCases([])}>{busy === "cases" ? "Running…" : "Run them all"}</button>
        {!session && <span className="quiet small"> Start a session to run them (they run in its test data); the self-test runs them too.</span>}</p>}
      {cases.length > 0 && <table className="grid-table"><thead><tr><th>Case</th><th>Call</th><th>As</th><th>Expects</th><th>Result</th><th /></tr></thead>
        <tbody>{cases.map((c) => { const r = results?.results?.find((x) => x.id === c.id); return (
          <tr key={c.id}><td>{c.name}</td><td className="small"><b>{c.method.toUpperCase()}</b> {c.path}</td><td className="small">{c.as_role}</td>
            <td className="small">{c.expect_status || "-"}</td>
            <td className="small">{r ? <span className={r.passed ? "ok-text" : "bad-text"}>{r.passed ? "passed" : "failed"}: {r.detail}</span> : ""}</td>
            <td className="nowrap small"><button className="linkish" disabled={!session || !!busy} onClick={() => runCases([c.id])}>Run</button>{" · "}
              <button className="linkish bad-text" onClick={() => deleteCase(c)}>Delete</button></td></tr>); })}</tbody></table>}
    </div>
  );
}
