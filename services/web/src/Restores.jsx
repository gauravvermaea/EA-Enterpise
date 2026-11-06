// Restores (build phase 8.4, D227): Administration > Restores lists every restore, infrastructure and application, with
// its status, and opens each one's whole log. A restore runs on its own in the operations helper or the job runner; this
// page only follows it, so closing the page (or the API being stopped for the restore) changes nothing. While an
// infrastructure restore runs, every screen shows the lock page instead (RestoreLock), reached through the proxy.
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "./auth";
import { fmtDateTime } from "./fmt";
import { refreshAll, useApi } from "./ModelViews";

const STATUS = { running: "status warn", ok: "status ok", failed: "status bad", interrupted: "status bad" };
const WHAT = { full: "Everything", app: "Application (config)", "app+data": "Application and data", db: "Databases", files: "Files",
  new: "As a new model", over: "Over the model", all: "Every model" };

// the token that lets the person who started an infrastructure restore follow it while the API is stopped
export function keepToken(id, token) { try { localStorage.setItem(`eax.restore.${id}`, token); } catch { /* followed through the API only */ } }
function tokenOf(id) { try { return localStorage.getItem(`eax.restore.${id}`) || ""; } catch { return ""; } }

async function readRestore(id) {
  try { return await apiFetch(`/api/v1/admin/restores/${id}`); } catch (e) {
    const token = tokenOf(id);
    if (!token) throw e;
    const r = await fetch(`/ops-restore/${id}?token=${encodeURIComponent(token)}`, { cache: "no-store" });
    if (!r.ok) throw e;
    return r.json();
  }
}

export default function RestoresPage({ route }) {
  const id = (/#\/admin\/restores\/([A-Za-z0-9._-]+)/.exec(route || "") || [])[1];
  return id ? <RestoreLog id={id} /> : <RestoreList />;
}

function RestoreList() {
  const { data, error } = useApi("/api/v1/admin/restores");
  const [err, setErr] = useState("");
  const running = (data?.restores || []).some((r) => r.status === "running");
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(refreshAll, 5000);
    return () => clearInterval(t);
  }, [running]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  async function del(r) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Forget the restore ${r.id} and its log?`)) return;
    setErr("");
    try { await apiFetch(`/api/v1/admin/restores/${r.id}/delete`, { method: "POST" }); refreshAll(); } catch (e) { setErr(e.message); }
  }
  return (
    <div>
      <p className="quiet">Every restore, of the installation (infrastructure) and of models (application), with its whole log. A restore
        runs on its own: this page only follows it, and you can close it. Restores are started on the Backups tab, on a model's
        Backups tab, or with <code>.\eax restore</code> and <code>.\eax restore-model</code>, which list the backups to choose from.
        Logs are kept in <code>work/backups/restores</code> until deleted here.</p>
      {data.helper && <p className="status warn small">{data.helper}</p>}
      {err && <p className="status bad">{err}</p>}
      <table className="grid-table">
        <thead><tr><th>Started</th><th>Kind</th><th>Backup</th><th>What</th><th>By</th><th>Status</th><th>Finished</th><th /></tr></thead>
        <tbody>
          {data.restores.map((r) => (
            <tr key={r.id}>
              <td className="small nowrap"><a href={`#/admin/restores/${r.id}`}>{fmtDateTime(r.started)}</a></td>
              <td className="small">{r.kind === "infrastructure" ? "Infrastructure" : "Model"}</td>
              <td className="small">{r.backup}</td>
              <td className="small">{WHAT[r.what] || r.what}</td>
              <td className="small">{r.by}</td>
              <td><span className={STATUS[r.status] || ""}>{r.status}</span>{r.status === "running" && r.step && <div className="quiet small">{r.step}</div>}
                {r.error && <div className="bad-text small">{r.error.slice(0, 160)}</div>}</td>
              <td className="small nowrap">{r.finished ? fmtDateTime(r.finished) : ""}</td>
              <td className="nowrap small"><a href={`#/admin/restores/${r.id}`}>Log</a>
                {r.status !== "running" && <>{" · "}<button className="linkish" onClick={() => del(r)}>Delete</button></>}</td>
            </tr>
          ))}
          {!data.restores.length && <tr><td colSpan="8" className="quiet">No restore yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export function RestoreLog({ id, embedded }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("");
  const [follow, setFollow] = useState(true);
  const box = useRef(null);
  useEffect(() => {
    let stop = false;
    async function load() {
      try { const x = await readRestore(id); if (!stop) { setD(x); setErr(""); } } catch (e) { if (!stop) setErr(e.message); }
    }
    load();
    const t = setInterval(() => { if (!d || d.status === "running") load(); }, 3000);
    return () => { stop = true; clearInterval(t); };
  }, [id, d?.status]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (follow && box.current) box.current.scrollTop = box.current.scrollHeight; }, [d, follow]);
  const lines = (d?.log || []).filter((l) => !filter || l.toLowerCase().includes(filter.toLowerCase()));
  return (
    <div className="restore-log">
      {!embedded && <p><a href="#/admin/restores">← All restores</a></p>}
      {err && !d && <p className="status bad">{err}</p>}
      {d && <>
        <h3>{d.kind === "infrastructure" ? "Infrastructure restore" : "Model restore"}: {d.backup} <span className={STATUS[d.status] || ""}>{d.status}</span></h3>
        <p className="small">{WHAT[d.what] || d.what} · started {fmtDateTime(d.started)} by {d.by}{d.finished ? ` · finished ${fmtDateTime(d.finished)}` : ""}
          {d.status === "running" && d.step && <> · now: <b>{d.step}</b></>}</p>
        {d.error && <p className="status bad">{d.error}</p>}
        {(d.warnings || []).map((w) => <p key={w} className="status warn small">{w}</p>)}
        {d.before && <p className="small">The state before is kept as the pinned backup <code>{d.before}</code>.</p>}
        <div className="row-gap filters">
          <input type="search" placeholder="Filter the log" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <label className="small"><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow the end</label>{" "}
          <span className="quiet small">{d.lines} lines{d.lines > (d.log || []).length ? ` (the newest ${(d.log || []).length} shown; all in work/backups/restores/${d.id}/restore.log)` : ""}</span>
        </div>
        <pre className="ct-log" ref={box}>{lines.join("\n")}</pre>
        {d.status !== "running" && d.kind === "infrastructure" && <p className="small">Everyone signs in again after an infrastructure restore.</p>}
      </>}
    </div>
  );
}

// The lock page (D227): while an infrastructure restore runs, every screen shows this instead of the application; it asks
// the proxy every 10 seconds (not the API, which may be stopped) and lets the screens back when the restore has finished.
export function useRestoreLock() {
  const [lock, setLock] = useState(null);
  useEffect(() => {
    let stop = false;
    async function check() {
      try {
        const r = await fetch("/ops-restore/active", { cache: "no-store" });
        if (r.ok) { const x = await r.json(); if (!stop) setLock((before) => (x.active ? x : before?.active ? { ...before, active: false, ended: true } : null)); }
      } catch { /* the proxy restarts at the end of a restore: ask again */ }
    }
    check();
    const t = setInterval(check, 10000);
    return () => { stop = true; clearInterval(t); };
  }, []);
  return lock;
}

export function RestoreLock({ lock }) {
  const mine = lock.id && tokenOf(lock.id);
  return (
    <div className="restore-lock">
      <div className="restore-lock-card">
        <h1>EA Explorer</h1>
        {lock.active ? <>
          <p className="status warn"><span className="spinner" aria-hidden="true" /> A backup is being restored: {lock.backup || lock.what} ({lock.what}),
            started by {lock.by} {lock.since ? `at ${fmtDateTime(lock.since)}` : ""}.</p>
          <p>EA Explorer cannot be used until it has finished. Large restores can take hours; this page checks every 10 seconds and
            opens the application again when it is done. You will be asked to sign in again.</p>
          {lock.step && <p className="small">Now: <b>{lock.step}</b></p>}
          {mine ? <RestoreLog id={lock.id} embedded /> : <p className="quiet small">The person who started it follows its log here; IT can also run <code>.\eax restores</code> and
            <code> .\eax restore-log {lock.id || "&lt;id&gt;"}</code> on the server.</p>}
        </> : <>
          <p className="status ok">The restore has finished.</p>
          <button className="primary" onClick={() => window.location.reload()}>Open EA Explorer and sign in again</button>
        </>}
      </div>
    </div>
  );
}
