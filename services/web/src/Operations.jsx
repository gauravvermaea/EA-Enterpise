// System admin › Operations (phases 35 and 35.1, D371): for IT Admins and Super Admins.
//   Usage        who uses what and how often, the parts used, each model's use and size, models idle for 180 days (a
//                report only: nobody is told, nothing happens to them), stale uncommitted work and loads never finished
//   Housekeeping retention rules (keep, archive or delete after N days), the dry run to confirm, the runs
//   Archive      what housekeeping archived, searched on request
//   Database     the largest tables, the slowest queries, when tables were last tidied
//   Metrics      how to read the Prometheus metrics
import { useState } from "react";
import { apiDownload, apiFetch, can } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { fmtDate, fmtDateTime, fmtNumber } from "./fmt";

const SECTIONS = [["usage", "Usage"], ["housekeeping", "Housekeeping"], ["archive", "Archive"], ["database", "Database health"], ["metrics", "Metrics"]];

export default function Operations() {
  const [s, setS] = useState("usage");
  return (
    <div className="operations">
      <div className="seg" role="tablist">
        {SECTIONS.map(([k, l]) => <button key={k} className={s === k ? "on" : ""} onClick={() => setS(k)}>{l}</button>)}
      </div>
      {s === "usage" && <Usage />}
      {s === "housekeeping" && <Housekeeping />}
      {s === "archive" && <Archive />}
      {s === "database" && <Database />}
      {s === "metrics" && <Metrics />}
    </div>
  );
}

const bytes = (n) => (n == null ? "" : n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : n > 1e3 ? `${Math.round(n / 1e3)} kB` : `${n} B`);
const AREA = { models: "Models and content", metamodel: "Metamodel", projects: "Projects", documents: "Documents", reports: "Reports",
  library: "Library", change_log: "Change log", administration: "Administration", mcp: "MCP", other: "Other" };

function Usage() {
  const [days, setDays] = useState(30);
  const u = useApi(`/api/v1/operations/usage?days=${days}`);
  const [tab, setTab] = useState("people");
  if (u.error) return <p className="status bad">{u.error}</p>;
  if (!u.data) return <p>Loading...</p>;
  const d = u.data;
  const max = Math.max(1, ...d.by_day.map((x) => x.calls));
  return (
    <>
      <div className="toolbar">
        <label>Over the last <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[7, 30, 90, 365].map((n) => <option key={n} value={n}>{n} days</option>)}</select></label>
        <span className="quiet small">Counted by the API: every call by a person or a credential, per day, part and model.</span>
      </div>
      <div className="kpi-row">
        <div className="kpi"><b>{fmtNumber(d.totals.calls)}</b><span>calls</span></div>
        <div className="kpi"><b>{d.totals.people}</b><span>people and accounts</span></div>
        <div className="kpi"><b>{d.totals.models_used}</b><span>models used</span></div>
        <div className={`kpi${d.idle_models.length ? " warn" : ""}`}><b>{d.idle_models.length}</b><span>idle {d.idle_days}+ days</span></div>
        <div className={`kpi${d.stale_changes.length ? " warn" : ""}`}><b>{d.stale_changes.reduce((a, x) => a + Number(x.changes), 0)}</b><span>stale changes</span></div>
        <div className={`kpi${d.old_loads.length ? " warn" : ""}`}><b>{d.old_loads.length}</b><span>loads not finished</span></div>
      </div>
      {d.by_day.length > 1 && (
        <div className="usage-spark" aria-label="Calls per day">
          {d.by_day.map((x) => <span key={x.day} title={`${fmtDate(x.day)}: ${x.calls} calls, ${x.people} people`}
            style={{ height: `${Math.max(2, (x.calls / max) * 60)}px` }} />)}
        </div>
      )}
      <div className="seg small">
        {[["people", "People"], ["parts", "Parts used"], ["models", "Models"], ["idle", `Idle models (${d.idle_models.length})`],
          ["stale", `Stale work (${d.stale_changes.length + d.old_loads.length})`], ["creds", "Credentials"]].map(([k, l]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>))}
      </div>
      {tab === "people" && (
        <table className="grid-table">
          <thead><tr><th>Who</th><th>Calls</th><th>Days active</th><th>Mostly</th><th>Last seen</th></tr></thead>
          <tbody>{d.people.map((p) => (
            <tr key={p.username}><td>{p.username}{p.uses_machine_access && <span className="tag" title="Also with a token, API key or certificate">machine</span>}</td>
              <td>{fmtNumber(p.calls)}</td><td>{p.days_active}</td>
              <td className="small">{(p.top_areas || "").split(", ").map((a) => AREA[a] || a).join(", ")}</td>
              <td>{p.last_seen ? fmtDateTime(p.last_seen) : fmtDate(p.last_day)}</td></tr>))}</tbody>
        </table>
      )}
      {tab === "parts" && (
        <>
          <p className="small">{d.areas.map((a) => `${AREA[a.area] || a.area}: ${fmtNumber(a.calls)} calls by ${a.people}`).join(" · ")}</p>
          <table className="grid-table">
            <thead><tr><th>Area</th><th>Part</th><th>Calls</th><th>People</th><th>Last</th></tr></thead>
            <tbody>{d.features.map((f) => (
              <tr key={`${f.area}${f.feature}`}><td>{AREA[f.area] || f.area}</td><td><code>{f.feature}</code></td><td>{fmtNumber(f.calls)}</td>
                <td>{f.people}</td><td>{fmtDate(f.last_day)}</td></tr>))}</tbody>
          </table>
        </>
      )}
      {tab === "models" && <ModelTable rows={d.models} />}
      {tab === "idle" && (
        <>
          <p className="quiet">Models nobody has opened or changed through EA Explorer for {d.idle_days} days or more. A report only: nobody is told
            and nothing happens to them; archive or delete them from the model page if they are no longer needed.</p>
          {d.idle_models.length ? <ModelTable rows={d.idle_models} /> : <p className="quiet">None.</p>}
        </>
      )}
      {tab === "stale" && (
        <>
          <h3>Uncommitted changes older than {d.stale_change_days} days</h3>
          {d.stale_changes.length ? <table className="grid-table"><thead><tr><th>Model</th><th>Whose</th><th>Changes</th><th>Oldest</th></tr></thead>
            <tbody>{d.stale_changes.map((x) => <tr key={`${x.model_guid}${x.author}`}><td><a href={`#/metamodel/${x.model_guid}`}>{x.model}</a></td>
              <td>{x.author}</td><td>{x.changes}</td><td>{fmtDate(x.oldest)}</td></tr>)}</tbody></table> : <p className="quiet">None.</p>}
          <h3>Loads not added after {d.stale_load_days} days</h3>
          {d.old_loads.length ? <table className="grid-table"><thead><tr><th>Model</th><th>File</th><th>Where it stopped</th><th>Whose</th><th>Uploaded</th><th>Size</th></tr></thead>
            <tbody>{d.old_loads.map((x) => <tr key={x.guid}><td>{x.model}</td><td>{x.file_name}</td><td>{x.status}</td><td>{x.owner}</td>
              <td>{fmtDate(x.created_at)}</td><td>{bytes(x.bytes)}</td></tr>)}</tbody></table> : <p className="quiet">None.</p>}
        </>
      )}
      {tab === "creds" && (
        <>
          <table className="grid-table"><thead><tr><th>Kind</th><th>Live</th><th>Expire within two weeks</th><th>Not used for 90 days</th></tr></thead>
            <tbody>{d.credentials.map((c) => <tr key={c.kind}><td>{{ token: "Tokens", api_key: "API keys", certificate: "Client certificates" }[c.kind]}</td>
              <td>{c.live}</td><td>{c.expiring}</td><td>{c.unused}</td></tr>)}</tbody></table>
          <p><a href="#/admin/machine-access">Machine access</a></p>
        </>
      )}
    </>
  );
}

function ModelTable({ rows }) {
  return (
    <div className="table-scroll">
      <table className="grid-table">
        <thead><tr><th>Model</th><th>Kind</th><th>Entities</th><th>Relationships</th><th>History versions</th><th>Calls</th><th>People</th><th>Last used</th><th>Last changed</th></tr></thead>
        <tbody>{rows.map((m) => (
          <tr key={m.guid} className={m.archived ? "is-retired" : ""}><td><a href={`#/metamodel/${m.guid}`}>{m.name}</a></td><td>{m.kind}</td>
            <td>{fmtNumber(m.entities)}</td><td>{fmtNumber(m.relationships)}</td><td>{fmtNumber(m.versions)}</td><td>{fmtNumber(m.calls)}</td>
            <td>{m.people}</td><td>{m.last_used ? fmtDate(m.last_used) : <span className="quiet">never</span>}</td>
            <td>{m.last_changed ? fmtDate(m.last_changed) : ""}</td></tr>))}</tbody>
      </table>
    </div>
  );
}

function Housekeeping() {
  const r = useApi("/api/v1/operations/retention");
  const [edit, setEdit] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(null);
  if (r.error) return <p className="status bad">{r.error}</p>;
  if (!r.data) return <p>Loading...</p>;
  const { rules, state, runs } = r.data;
  const act = async (path, body) => {
    setBusy(true); setErr("");
    try { await apiFetch(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }); refreshAll(); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const waiting = state.awaiting_confirmation;
  return (
    <>
      <div className={`banner ${state.confirmed ? "ok" : "warn"}`}>
        {state.confirmed
          ? <>Housekeeping acts on these rules {state.schedule}: a dry run of them was confirmed by {state.confirmed_run.confirmed_by} on {fmtDateTime(state.confirmed_run.confirmed_at)}.</>
          : waiting
            ? <>A dry run of these rules is waiting to be confirmed (below). Until then the nightly run only does dry runs and changes nothing.</>
            : <>These rules have no confirmed dry run, so housekeeping changes nothing. Do a dry run, look at what it would do, then confirm it.</>}
      </div>
      <div className="toolbar">
        <button disabled={busy} onClick={() => act("/api/v1/operations/housekeeping/run", { dry_run: true })}>Dry run now</button>
        <button disabled={busy || !state.confirmed} title={state.confirmed ? "" : "Confirm a dry run of these rules first"}
          onClick={() => window.confirm("Run housekeeping now? It archives and deletes what the rules say.") && act("/api/v1/operations/housekeeping/run", { dry_run: false })}>Run now</button>
      </div>
      {err && <p className="status bad">{err}</p>}
      {waiting && (
        <div className="card">
          <h3>Dry run of {fmtDateTime(waiting.started_at)}: what it would do</h3>
          <RunResults run={waiting} rules={rules} />
          <button className="primary" disabled={busy} onClick={() => act(`/api/v1/operations/housekeeping/runs/${waiting.id}/confirm`)}>Confirm: let housekeeping do this</button>
        </div>
      )}
      <h3>Retention rules</h3>
      <p className="quiet small">Nothing is deleted until an admin says so. Changing a rule asks for a new dry run before housekeeping acts again.</p>
      <table className="grid-table">
        <thead><tr><th>What</th><th>Do</th><th>After</th><th>Set by</th><th /></tr></thead>
        <tbody>{rules.map((x) => (
          <tr key={x.code}><td><b>{x.label}</b><div className="quiet small">{x.covers}</div>{x.note && <div className="small warn-text">{x.note}</div>}</td>
            <td><span className={`keep-${x.action}`}>{x.code === "history_versions" && x.action === "delete" ? "remove" : x.action}</span></td>
            <td>{x.code === "history_versions" ? (x.action === "keep" ? <span className="quiet">off</span> : years(x.after_days)) : `${x.after_days} days`}</td>
            <td className="small">{x.set_by === "installation" ? <span className="quiet">default</span> : <>{x.set_by}<div className="quiet">{fmtDate(x.set_at)}</div></>}</td>
            <td>{x.code !== "history_versions" || can("settings.manage")
              ? <button className="linkish" onClick={() => setEdit(x)}>Change</button>
              : <span className="quiet small" title="Only a Super Admin sets this rule">Super Admin</span>}</td></tr>))}</tbody>
      </table>
      <h3>Runs</h3>
      <table className="grid-table">
        <thead><tr><th>When</th><th>Kind</th><th>By</th><th>Archived</th><th>Deleted</th><th>Confirmed</th><th /></tr></thead>
        <tbody>{runs.map((x) => {
          const vals = Object.values(x.results || {});
          return (
            <tr key={x.id}><td>{fmtDateTime(x.started_at)}</td><td>{x.dry_run ? "Dry run" : "Run"}</td><td>{x.started_by}</td>
              <td>{x.dry_run ? "" : vals.reduce((a, v) => a + (v.archived || 0), 0)}</td><td>{x.dry_run ? "" : vals.reduce((a, v) => a + (v.deleted || 0), 0)}</td>
              <td className="small">{x.confirmed_at ? `${fmtDate(x.confirmed_at)} by ${x.confirmed_by}` : ""}</td>
              <td><button className="linkish" onClick={() => setOpen(x)}>Details</button></td></tr>);
        })}</tbody>
      </table>
      {open && <Modal title={`${open.dry_run ? "Dry run" : "Run"} of ${fmtDateTime(open.started_at)}`} onClose={() => setOpen(null)} wide
        actions={<button onClick={() => setOpen(null)}>Close</button>}><RunResults run={open} rules={rules} /></Modal>}
      {edit && <EditRule rule={edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); refreshAll(); }} />}
    </>
  );
}

function RunResults({ run, rules }) {
  return (
    <table className="grid-table">
      <thead><tr><th>What</th><th>Rule</th><th>{run.dry_run ? "Would handle" : "Found"}</th>{!run.dry_run && <><th>Archived</th><th>Deleted</th></>}</tr></thead>
      <tbody>{rules.map((r) => {
        const x = run.results?.[r.code];
        if (!x) return null;
        return (
          <tr key={r.code}><td>{r.label}{x.note && <div className="quiet small">{x.note}</div>}
            {x.by_model?.length > 0 && <div className="small">{x.by_model.map((m) => `${m.model}: ${fmtNumber(m.versions)}`).join(" · ")}</div>}
            {r.code === "history_versions" && x.pinned_moments != null && <div className="quiet small">Kept because something needs them:
              the state at {x.pinned_moments} tagged or evidence moments, and {x.pinned_rows} items a governance record names.</div>}</td>
            <td>{r.code === "history_versions" && x.action === "delete" ? `remove after ${years(x.after_days)}` : `${x.action} after ${x.after_days} days`}</td>
            <td>{x.action === "keep" ? <span className="quiet">kept ({x.found})</span> : x.found}</td>
            {!run.dry_run && <><td>{x.archived}</td><td>{x.deleted}</td></>}</tr>);
      })}</tbody>
    </table>
  );
}

const years = (d) => { const y = Math.round((d / 365) * 10) / 10; return `${y} year${y === 1 ? "" : "s"}`; };

function EditRule({ rule, onClose, onDone }) {
  const history = rule.code === "history_versions";
  const [action, setAction] = useState(rule.action);
  const [days, setDays] = useState(rule.after_days);
  const [err, setErr] = useState("");
  const save = async () => {
    try {
      await apiFetch(`/api/v1/operations/retention/${rule.code}`, { method: "PUT", body: JSON.stringify({ action, after_days: Number(days) }) });
      onDone();
    } catch (e) { setErr(e.message); }
  };
  return (
    <Modal title={rule.label} onClose={onClose} actions={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={save}>Save</button></>}>
      <p className="quiet">{rule.covers}</p>
      <div className="seg">{rule.actions.map((a) => <button key={a} className={action === a ? "on" : ""} onClick={() => setAction(a)}>
        {history ? (a === "keep" ? "keep all (off)" : "remove older versions") : a}</button>)}</div>
      {action !== "keep" && (history
        ? <label className="block">Remove versions older than (years, at least 1)
          <input type="number" min={1} step={1} value={Math.round(days / 365)} onChange={(e) => setDays(Number(e.target.value) * 365)} style={{ width: 90 }} /></label>
        : <label className="block">After (days, at least {rule.min_days})
          <input type="number" min={rule.min_days} value={days} onChange={(e) => setDays(e.target.value)} style={{ width: 110 }} /></label>)}
      {action === "delete" && <p className="warn-text">{history
        ? "Removed versions are gone for good (they stay only in older backups): the model's states before then can no longer be viewed or compared."
        : "Deleted records are gone for good (they stay only in older backups)."}</p>}
      {rule.note && <p className="small">{rule.note}</p>}
      <p className="quiet small">Default: {history ? "off (everything kept)" : `${rule.default.action} after ${rule.default.after_days} days`}. Housekeeping waits for a new dry run after this.</p>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

function Archive() {
  const [q, setQ] = useState("");
  const [rule, setRule] = useState("");
  const [search, setSearch] = useState("");
  const a = useApi(search !== null ? `/api/v1/operations/archive?q=${encodeURIComponent(search)}&rule=${rule}` : null);
  const [item, setItem] = useState(null);
  const view = async (id) => setItem(await apiFetch(`/api/v1/operations/archive/${id}`));
  return (
    <>
      <p className="quiet">What housekeeping archived, kept here and searched on request.</p>
      <form className="toolbar" onSubmit={(e) => { e.preventDefault(); setSearch(q); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Words in it" />
        <select value={rule} onChange={(e) => setRule(e.target.value)}>
          <option value="">Everything</option><option value="loads">Loads</option><option value="task_files">Task files</option>
          <option value="notifications">Notifications</option><option value="webhook_deliveries">Webhook deliveries</option>
          <option value="discarded_changes">Discarded changes</option></select>
        <button type="submit">Search</button>
      </form>
      {a.error && <p className="status bad">{a.error}</p>}
      {a.data && (a.data.length ? (
        <table className="grid-table">
          <thead><tr><th>What</th><th>Kind</th><th>Model</th><th>Made</th><th>Archived</th><th /></tr></thead>
          <tbody>{a.data.map((x) => (
            <tr key={x.id}><td>{x.summary}</td><td>{x.rule}</td><td>{x.model || ""}</td><td>{fmtDate(x.created_at)}</td><td>{fmtDate(x.archived_at)}</td>
              <td className="nowrap"><button className="linkish" onClick={() => view(x.id)}>Look</button>
                {x.has_file && <> · <button className="linkish" onClick={() => apiDownload(`/api/v1/operations/archive/${x.id}/file`, "archived")}>File ({bytes(x.bytes)})</button></>}</td></tr>))}</tbody>
        </table>) : <p className="quiet">Nothing found.</p>)}
      {item && <Modal title={item.summary} onClose={() => setItem(null)} wide actions={<button onClick={() => setItem(null)}>Close</button>}>
        <p className="quiet small">From {item.source_table}, made {fmtDateTime(item.created_at)}, archived {fmtDateTime(item.archived_at)}</p>
        <pre className="json-view">{JSON.stringify(item.data, null, 2)}</pre></Modal>}
    </>
  );
}

function Database() {
  const d = useApi("/api/v1/operations/database");
  if (d.error) return <p className="status bad">{d.error}</p>;
  if (!d.data) return <p>Loading...</p>;
  const x = d.data;
  return (
    <>
      <div className="kpi-row">
        <div className="kpi"><b>{bytes(x.size)}</b><span>{x.database}</span></div>
        <div className="kpi"><b>{x.connections}</b><span>connections</span></div>
      </div>
      <h3>Largest tables</h3>
      <div className="table-scroll"><table className="grid-table">
        <thead><tr><th>Table</th><th>Size (with indexes)</th><th>Rows (about)</th><th>Dead rows</th><th>Last tidied</th><th>Last analysed</th></tr></thead>
        <tbody>{x.tables.map((t) => (
          <tr key={`${t.schema}.${t.name}`}><td><code>{t.schema}.{t.name}</code></td><td>{bytes(t.bytes)}</td><td>{fmtNumber(t.rows)}</td>
            <td>{fmtNumber(t.dead_rows || 0)}</td><td>{t.last_tidied ? fmtDateTime(t.last_tidied) : <span className="quiet">not yet</span>}</td>
            <td>{t.last_analysed ? fmtDateTime(t.last_analysed) : <span className="quiet">not yet</span>}</td></tr>))}</tbody>
      </table></div>
      <h3>{x.statements ? "Slowest queries (average time)" : "Queries running for more than a second"}</h3>
      {x.slow_note && <p className="quiet small">{x.slow_note}</p>}
      {x.slow_queries.length ? <table className="grid-table">
        <thead><tr><th>Query</th>{x.statements ? <><th>Calls</th><th>Average ms</th><th>Longest ms</th></> : <><th>State</th><th>Running (s)</th></>}</tr></thead>
        <tbody>{x.slow_queries.map((q, i) => <tr key={i}><td><code className="small">{q.query}</code></td>
          {x.statements ? <><td>{q.calls}</td><td>{q.mean_ms}</td><td>{q.max_ms}</td></> : <><td>{q.state}</td><td>{q.running_s}</td></>}</tr>)}</tbody>
      </table> : <p className="quiet">None right now.</p>}
    </>
  );
}

function Metrics() {
  return (
    <>
      <p>EA Explorer gives Prometheus metrics at <code>{window.location.origin}/api/metrics</code> (the text format Prometheus reads).</p>
      <p>Prometheus reads them with a token or API key that may <b>read Administration</b>, belonging to an IT Admin or a service
        account with the IT Admin role: make one on <a href="#/admin/machine-access">Machine access</a>, then in Prometheus:</p>
      <pre className="json-view">{`scrape_configs:
  - job_name: eaexplorer
    scheme: https
    metrics_path: /api/metrics
    authorization:
      credentials: <the token>
    static_configs:
      - targets: ["${window.location.host}"]`}</pre>
      <p className="quiet small">Among them: the version, whether the API reaches its database, models, entities and relationships, people active,
        API calls today by area, uncommitted changes, background jobs by status, the age of the last backup and of the last housekeeping
        run, live credentials and the database's size.</p>
    </>
  );
}
