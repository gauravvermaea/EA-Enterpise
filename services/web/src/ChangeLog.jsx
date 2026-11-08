// The change log (build phase 9, D180): #/change-log
// One row per action a person takes. Everyone sees their own changes, a Model Admin every change in the models they
// administer, a Super Admin every change. Only a Super Admin exports or deletes entries (the history, roll back and
// the audit trail are never touched by a delete).
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";
import { TaskFiles } from "./TaskDrawer";
import { downloadTask } from "./tasks";

const FILTERS = ["q", "model", "user", "kind", "action", "item_type", "from", "to", "mine"];
const show = (v) => (v === null || v === undefined || v === "" ? <span className="quiet">(empty)</span> : String(v));
const when = (t) => (t ? fmtDateTime(t) : "");

function query(f, extra = {}) {
  const p = new URLSearchParams();
  FILTERS.forEach((k) => { if (f[k]) p.set(k, f[k] === true ? "1" : f[k]); });
  Object.entries(extra).forEach(([k, v]) => p.set(k, v));
  return p.toString();
}

function Details({ e }) {
  const [open, setOpen] = useState(false);
  const list = e.details || [];
  if (!list.length) return <span className="quiet small">-</span>;
  const shown = open ? list : list.slice(0, 3);
  return (
    <div className="small">
      {shown.map((d, i) => (
        <div key={i}><span className="quiet">{d.field}:</span>{" "}
          {e.source === "data" ? <><s>{show(d.old)}</s> → {show(d.new)}</> : show(d.new)}</div>
      ))}
      {list.length > 3 && <button className="linkish" onClick={() => setOpen(!open)}>{open ? "less" : `+${list.length - 3} more`}</button>}
    </div>
  );
}

function DeleteDialog({ filters, total, any, onClose, onDone }) {
  const [word, setWord] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function go() {
    setBusy(true); setErr("");
    try {
      const body = { confirm: word };
      FILTERS.forEach((k) => { if (filters[k]) body[k] = filters[k]; });
      onDone(await apiFetch("/api/v1/change-log/delete", { method: "POST", body: JSON.stringify(body) }));
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title="Delete change log entries" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="danger" disabled={busy || word !== "DELETE"} onClick={go}>Delete</button></>}>
      <p>{any ? <>This deletes the <b>{total}</b> entries the filters select.</> : <>No filter is set: this deletes <b>every</b> entry of the change log ({total}).</>}</p>
      <p className="quiet small">Only the change log entries go. The history of every item (its History tab and roll back), commits, tags and
        the audit trail are kept. The deletion is logged as an entry of its own. Export first if you need a copy.</p>
      <label className="ed-field"><span>Type DELETE to confirm</span><input value={word} onChange={(e) => setWord(e.target.value)} autoFocus /></label>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

export default function ChangeLog() {
  const [f, setF] = useState({});
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(200);
  const [del, setDel] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => { const t = setTimeout(() => setF((x) => ({ ...x, q })), 350); return () => clearTimeout(t); }, [q]);
  const qs = useMemo(() => query(f, { limit }), [f, limit]);
  const { data, error } = useApi(`/api/v1/change-log?${qs}`);
  const set = (k) => (e) => { setLimit(200); setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value })); };
  const any = FILTERS.some((k) => f[k]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const you = data.you;
  const fc = data.facets;
  return (
    <div className="change-log">
      <h2>Change log</h2>
      <p className="quiet">
        Every action people take, newest first: what changed, in which model, by whom, with the old and new values. You see {you.sees}
        {you.model_admin_of.length > 0 && !you.super_admin && <> ({you.model_admin_of.map((m) => m.name).join(", ")})</>}.
        {you.super_admin && " As a Super Admin you can export and delete entries."}
      </p>
      <div className="toolbar change-log-filters">
        <input className="search" placeholder="Search item, model, user or value" value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 240 }} />
        <select value={f.model || ""} onChange={set("model")}><option value="">Every model</option>
          {fc.models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>
        {fc.users.length > 1 && <select value={f.user || ""} onChange={set("user")}><option value="">Everyone</option>
          {fc.users.map((u) => <option key={u}>{u}</option>)}</select>}
        <select value={f.kind || ""} onChange={set("kind")}><option value="">Every kind</option>
          {Object.entries(data.kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select value={f.action || ""} onChange={set("action")}><option value="">Every action</option>
          {fc.actions.map((a) => <option key={a}>{a}</option>)}</select>
        <select value={f.item_type || ""} onChange={set("item_type")}><option value="">Every item</option>
          {fc.item_types.map((a) => <option key={a}>{a}</option>)}</select>
        <label className="small">From <input type="date" value={f.from || ""} onChange={set("from")} /></label>
        <label className="small">to <input type="date" value={f.to || ""} onChange={set("to")} /></label>
        {fc.users.length > 1 && <label className="small"><input type="checkbox" checked={!!f.mine} onChange={set("mine")} /> Only my changes</label>}
        {any && <button className="linkish" onClick={() => { setF({}); setQ(""); }}>Clear the filters</button>}
      </div>
      <div className="toolbar">
        <span><b>{data.total}</b> entries{any ? " match" : ""}</span>
        {data.by_person.length > 1 && <span className="quiet small">· {data.by_person.slice(0, 5).map((p) => `${p.username} ${p.n}`).join(" · ")}</span>}
        {you.super_admin && <span className="tabs-right">
          <button onClick={() => downloadTask(`/api/v1/change-log/export?${query(f, { format: "csv" })}`, undefined, "#/change-log").catch(() => {})}>⬇ CSV</button>
          <button onClick={() => downloadTask(`/api/v1/change-log/export?${query(f, { format: "xlsx" })}`, undefined, "#/change-log").catch(() => {})}>⬇ Excel</button>
          <button className="danger" disabled={!data.total} onClick={() => setDel(true)}>Delete{any ? " these" : ""}...</button>
        </span>}
      </div>
      {you.super_admin && <TaskFiles kinds={["changelog.export"]} />}
      {msg && <p className="status ok">{msg}</p>}
      <table className="grid-table change-log-table">
        <thead><tr><th>When</th><th>Model</th><th>User</th><th>Action</th><th>Item</th><th>What changed</th></tr></thead>
        <tbody>
          {data.entries.map((e) => (
            <tr key={e.id} className={`cl-${e.kind}`}>
              <td className="small nowrap">{when(e.at)}</td>
              <td className="small">{e.model_guid ? <a href={`#/metamodel/${e.model_guid}`}>{e.model_name}</a> : <span className="quiet">{e.model_name || "-"}</span>}</td>
              <td className="small">{e.username}</td>
              <td><span className={`cl-kind ${e.kind}`}>{e.kind_name}</span> {e.action}</td>
              <td>{e.link && e.item_name ? <a href={e.link}>{e.item_name}</a> : (e.item_name || "")}
                <div className="quiet small">{e.item_type}{e.entity_type ? ` · ${e.entity_type}` : ""}</div></td>
              <td><Details e={e} />{e.commit_number && <div className="commit-note small" title="The commit this change came in with (D195)">
                Commit #{e.commit_number}{e.commit_message ? `: ${e.commit_message}` : ""}</div>}</td>
            </tr>
          ))}
          {!data.entries.length && <tr><td colSpan="6" className="quiet">{any ? "No entry matches the filters." : "No changes logged yet."}</td></tr>}
        </tbody>
      </table>
      {data.entries.length < data.total && (
        <div className="toolbar"><button onClick={() => setLimit(limit + 200)}>Show 200 more</button>
          <span className="quiet small">{data.entries.length} of {data.total} shown</span></div>
      )}
      {del && <DeleteDialog filters={f} total={data.total} any={any} onClose={() => setDel(false)}
        onDone={(out) => { setDel(false); setMsg(out.note); refreshAll(); }} />}
    </div>
  );
}
