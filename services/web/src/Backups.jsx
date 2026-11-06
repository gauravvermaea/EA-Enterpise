// Backups and restores (build phase 8.4, D216).
// Administration > Backups (IT and Super Admins): infrastructure backups (every database, the files, the config file,
// the release and image versions; tagged, pinned, restored whole or in part with the installation read only) and
// application backups (every model as a model backup file, downloadable, restorable as a new model or over itself).
// The model page's Backups tab: its Model Admins back the model up and restore it.
import { Fragment, useEffect, useRef, useState } from "react";
import { apiDownload, apiFetch, apiUpload, can, roles } from "./auth";
import { keepToken } from "./Restores";
import { fmtDateTime } from "./fmt";
import { Modal } from "./ModelOps";
import { refreshAll, useApi } from "./ModelViews";
import { trackTask } from "./tasks";

// search (D232): every word in the tag, name or who made it
const matches = (b, q) => !q.trim() || q.toLowerCase().split(/\s+/).filter(Boolean)
  .every((w) => `${b.tag || ""} ${b.name || ""} ${b.by || ""}`.toLowerCase().includes(w));

function stopBackups(act) {
  // eslint-disable-next-line no-alert
  if (!window.confirm("Stop the backups running? The partial backup is deleted (an application backup stops after the model it is on).")) return;
  act(() => apiFetch("/api/v1/admin/backups/stop", { method: "POST" }), (out) => `Stopping: ${(out.stopping || []).join(", ")}.`);
}

const size = (b) => (b == null ? "" : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);
// 20261106T010000Z -> a date and time to read
function when(stamp) {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z/.exec(stamp || "");
  return m ? fmtDateTime(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`) : stamp || "";
}
const KIND = { "on-demand": "On demand", scheduled: "Scheduled", "before-restore": "Before a restore", "before-upgrade": "Before an upgrade", legacy: "Older format" };

export default function AdminBackups() {
  const { data, error } = useApi("/api/v1/admin/backups");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [restoring, setRestoring] = useState(null);
  const [restoreModel, setRestoreModel] = useState(null);
  const running = data?.infrastructure?.state?.busy;
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(refreshAll, 4000);
    return () => clearInterval(t);
  }, [running]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const infra = data.infrastructure || {};
  async function act(fn, done) {
    setErr(""); setMsg("");
    try { const out = await fn(); if (done) setMsg(done(out)); refreshAll(); } catch (e) { setErr(e.message); }
  }
  return (
    <div className="backups">
      <p className="quiet">Two kinds of backup (D216). The <b>infrastructure backup</b> keeps everything needed to put this installation back:
        every database, the document files, the certificate, the config file, the release and image versions. The <b>application
        backup</b> keeps every model as a file you can download, restore as a new model, or take to another installation. Both run in
        the background while people work; when they run and how many are kept is set under Schedules (pinned ones are always kept). Folder: <code>{data.folder}</code>.
        {!data.on && <strong className="status bad"> Backups are switched off (Administration &gt; Services).</strong>}</p>
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}

      <Schedules data={data} act={act} />
      <InfraSection data={data} onRestore={setRestoring} act={act} />
      <AppSection data={data} act={act} onRestore={setRestoreModel} />
      {restoring && <RestoreInfra b={restoring} choices={infra.restore_choices || {}} onClose={() => { setRestoring(null); refreshAll(); }} />}
      {restoreModel && <RestoreModel b={restoreModel} onClose={() => setRestoreModel(null)} />}
    </div>
  );
}

// When each kind runs and how many are kept (D222): in the database, set here by IT and Super Admins, never in the config file
const PRESETS = [["0 1 * * *", "Every day at 01:00"], ["0 2 * * *", "Every day at 02:00"], ["0 1 * * 1-5", "Weekdays at 01:00"],
  ["0 2 * * 0", "Every Sunday at 02:00"], ["0 2 1 * *", "The 1st of every month at 02:00"]];

function Schedules({ data, act }) {
  const [edit, setEdit] = useState(null);
  const list = data.schedules || [];
  async function save() {
    await act(() => apiFetch(`/api/v1/admin/backups/schedules/${edit.kind}`, { method: "PUT", body: JSON.stringify(edit) }),
      (out) => `${out.kind === "infrastructure" ? "Infrastructure" : "Application"} backups: ${out.enabled ? out.in_words : "not scheduled"}, keeping ${out.keep}.`);
    setEdit(null);
  }
  return (
    <div className="merge-step">
      <h3>Schedules</h3>
      <table className="grid-table">
        <thead><tr><th>Backup</th><th>Scheduled</th><th>When</th><th>Tag</th><th>Keep</th><th>Warn when older than</th><th>Last run</th><th /></tr></thead>
        <tbody>
          {list.map((x) => (
            <tr key={x.kind}>
              <td><b>{x.kind === "infrastructure" ? "Infrastructure" : "Application (every model)"}</b></td>
              <td>{x.enabled ? <span className="ok-text">on</span> : <span className="quiet">off</span>}</td>
              <td className="small">{x.in_words} <span className="quiet">({data.time_zone})</span></td>
              <td className="small">{x.tag}</td>
              <td className="small">the newest {x.keep}</td>
              <td className="small">{x.kind === "infrastructure" ? `${x.warn_after_hours} hours` : ""}</td>
              <td className="small">{x.last_run_at ? `${fmtDateTime(x.last_run_at)}: ${x.last_status}` : "never"}</td>
              <td><button className="linkish" onClick={() => setEdit({ ...x })}>Change...</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {edit && (
        <Modal title={`${edit.kind === "infrastructure" ? "Infrastructure" : "Application"} backup schedule`} onClose={() => setEdit(null)}
          actions={<><button onClick={() => setEdit(null)}>Cancel</button><button className="primary" onClick={save}>Save</button></>}>
          <label className="ed-field radio"><input type="checkbox" checked={edit.enabled} onChange={(e) => setEdit({ ...edit, enabled: e.target.checked })} /> <span>Run on a schedule</span></label>
          <label className="ed-field"><span>When ({data.time_zone})</span>
            <select value={PRESETS.some(([c]) => c === edit.cron) ? edit.cron : "custom"} onChange={(e) => e.target.value !== "custom" && setEdit({ ...edit, cron: e.target.value })}>
              {PRESETS.map(([c, l]) => <option key={c} value={c}>{l}</option>)}
              <option value="custom">Another schedule (cron)...</option>
            </select></label>
          <label className="ed-field"><span>Schedule (minute hour day month weekday)</span><input value={edit.cron} onChange={(e) => setEdit({ ...edit, cron: e.target.value })} /></label>
          <label className="ed-field"><span>Tag of the backups it makes</span><input value={edit.tag} maxLength={60} onChange={(e) => setEdit({ ...edit, tag: e.target.value })} /></label>
          <label className="ed-field"><span>Keep the newest (pinned ones are always kept)</span><input type="number" min="1" max="365" value={edit.keep} onChange={(e) => setEdit({ ...edit, keep: e.target.value })} /></label>
          {edit.kind === "infrastructure" && <label className="ed-field"><span>The health check warns when the newest is older than (hours)</span>
            <input type="number" min="1" max="8760" value={edit.warn_after_hours} onChange={(e) => setEdit({ ...edit, warn_after_hours: e.target.value })} /></label>}
          <p className="quiet small">The oldest beyond the number kept are removed after each backup of that kind. Model Admins' own model backups keep the same number per model as application backups.</p>
        </Modal>
      )}
    </div>
  );
}

function InfraSection({ data, onRestore, act }) {
  const infra = data.infrastructure || {};
  const [tag, setTag] = useState("");
  const st = infra.state || {};
  const [q, setQ] = useState("");
  const all = infra.infrastructure || [];
  const list = all.filter((b) => matches(b, q));
  async function backupNow() {
    await act(async () => { const t = await apiFetch("/api/v1/admin/backups/infrastructure", { method: "POST", body: JSON.stringify({ tag }) }); trackTask(t, "#/admin/backups"); setTag(""); return t; },
      () => "Backing up in the background: it is listed here when done, and the top bar says so.");
  }
  return (
    <div className="merge-step">
      <h3>Infrastructure backups</h3>
      <p className="quiet small">{(() => { const sc = (data.schedules || []).find((x) => x.kind === "infrastructure"); return sc?.enabled ? `Scheduled ${sc.in_words}` : "Not scheduled"; })()} and on demand.
        To restore when the console cannot run: <code>.\eax restore &lt;name|tag|latest&gt; --what full|app|app+data|db|files</code>.</p>
      {infra.error && <p className="status bad">{infra.error}</p>}
      <div className="row-gap filters">
        <input value={tag} maxLength={60} onChange={(e) => setTag(e.target.value)} placeholder="Tag, e.g. before-the-demo" disabled={!data.on || st.busy} />
        <button className="primary" disabled={!data.on || st.busy} onClick={backupNow}>Back up now</button>
        {st.busy && <span className="small"><span className="spinner" aria-hidden="true" /> {st.what}...</span>}
        {st.busy && /^backup/.test(st.what || "") && <button className="danger" onClick={() => stopBackups(act)}>Stop</button>}
        <input type="search" className="push-right" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by tag, name or who" />
      </div>
      {(st.busy || st.log?.length > 0) && (
        <details open={st.busy}><summary className="small">{st.busy ? "Progress" : `Last: ${st.what} ${st.error ? `(failed: ${st.error})` : ""}`}</summary>
          <pre className="ct-pre small">{(st.log || []).join("\n")}</pre></details>
      )}
      <div className="table-scroll">
        <table className="grid-table">
          <thead><tr><th>Tag</th><th>When</th><th>Kind</th><th>By</th><th>Version</th><th>Holds</th><th>Size</th><th>Status</th><th /></tr></thead>
          <tbody>
            {list.map((b) => (
              <tr key={b.name}>
                <td><b>{b.tag || b.name}</b>{b.pinned && <span className="badge pin-badge" title="Never cleaned away">📌 pinned</span>}<div className="quiet small"><code>{b.name}</code></div></td>
                <td className="small nowrap">{when(b.created)}</td>
                <td className="small">{KIND[b.kind] || b.kind}</td>
                <td className="small">{b.by}</td>
                <td className="small">{b.version}</td>
                <td className="small">{b.parts ? <>{(b.parts.databases || []).length} databases{(b.parts.files || []).length ? `, ${b.parts.files.join(" and ")} files` : ""}{b.parts.config ? ", config" : ""}{b.parts.code ? ", versions" : ""}</> : ""}</td>
                <td className="small nowrap">{size(b.bytes)}</td>
                <td className={b.status === "ok" ? "ok-text small" : b.status === "failed" ? "bad-text small" : "small"} title={b.error || ""}>{b.status}{b.error ? `: ${b.error}` : ""}</td>
                <td className="nowrap">
                  <button className="linkish" onClick={() => act(() => apiFetch(`/api/v1/admin/backups/infrastructure/${b.name}/pin`, { method: "POST", body: JSON.stringify({ pinned: !b.pinned }) }))}>{b.pinned ? "Unpin" : "Pin"}</button>
                  {" · "}
                  <button className="linkish" disabled={b.status !== "ok" || st.busy} onClick={() => onRestore(b)}>Restore...</button>
                  {!b.pinned && <>{" · "}<button className="linkish" disabled={st.busy} onClick={() => {
                    // eslint-disable-next-line no-alert
                    if (window.confirm(`Delete the backup ${b.name}? This cannot be undone.`)) act(() => apiFetch(`/api/v1/admin/backups/infrastructure/${b.name}/delete`, { method: "POST" }), () => `${b.name} deleted.`);
                  }}>Delete</button></>}
                </td>
              </tr>
            ))}
            {!list.length && <tr><td colSpan="9" className="quiet">{all.length ? `No backup matches "${q}".` : "No infrastructure backup yet."}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AppSection({ data, act, onRestore }) {
  const app = data.application || {};
  const [tag, setTag] = useState("");
  const [open, setOpen] = useState("");
  const [q, setQ] = useState("");
  const [all, setAll] = useState(null);
  const file = useRef(null);
  const runs = (app.runs || []).filter((r) => matches(r, q));
  const superAdmin = roles().includes("super-admin");
  async function backupNow() {
    await act(async () => { const t = await apiFetch("/api/v1/admin/backups/application", { method: "POST", body: JSON.stringify({ tag }) }); trackTask(t, "#/admin/backups"); setTag(""); return t; },
      () => "Backing up every model in the background: it is listed here when done.");
  }
  async function upload(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    const form = new FormData();
    form.append("file", f);
    await act(() => apiUpload("/api/v1/admin/backups/upload", form), (out) => (out.run
      ? `The application backup '${out.tag}' (${out.models} models) is uploaded: it is listed below.`
      : `${out.model.name} is uploaded: restore it as a new model below.`));
    e.target.value = "";
  }
  return (
    <div className="merge-step">
      <h3>Application backups</h3>
      <p className="quiet small">Every model as a file: its metamodel, entities, relationships, history and tags, with an Excel workbook inside to read
        (documents and diagrams are added with document management, phase 13). Restore one as a new model, put a model back over itself,
        or take the file to another installation and upload it there.</p>
      <div className="row-gap filters">
        <input value={tag} maxLength={60} onChange={(e) => setTag(e.target.value)} placeholder="Tag, e.g. end-of-quarter" />
        <button className="primary" onClick={backupNow}>Back up every model now</button>
        <button onClick={() => file.current?.click()} title="A model (.eaxbackup.zip) or a whole application backup (.eaxapp.zip)">Upload a backup file...</button>
        <input ref={file} type="file" accept=".zip" hidden onChange={upload} />
        {(app.runs || []).some((r) => r.status === "running") && <button className="danger" onClick={() => stopBackups(act)}>Stop</button>}
        <input type="search" className="push-right" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by tag, name or who" />
      </div>
      <div className="table-scroll">
        <table className="grid-table">
          <thead><tr><th>Tag</th><th>When</th><th>By</th><th>Models</th><th>Size</th><th>Status</th><th /></tr></thead>
          <tbody>
            {runs.map((r) => (
              <Fragment key={r.name}>
                <tr>
                  <td><button className="linkish" onClick={() => setOpen(open === r.name ? "" : r.name)}>{open === r.name ? "▾" : "▸"} <b>{r.tag}</b></button>
                    {r.pinned && <span className="badge pin-badge">📌 pinned</span>}</td>
                  <td className="small nowrap">{when(r.created)}</td>
                  <td className="small">{r.by}</td>
                  <td className="small">{(r.models || []).filter((m) => m.status === "ok").length}{(r.models || []).some((m) => m.status !== "ok") ? ` (${r.models.filter((m) => m.status !== "ok").length} failed)` : ""}</td>
                  <td className="small nowrap">{size(r.bytes)}</td>
                  <td className="small">{r.status}{r.uploaded && <span className="quiet"> (uploaded)</span>}</td>
                  <td className="nowrap">{r.status !== "running" && <>
                    <button className="linkish" title="Every model in one file (.eaxapp.zip), to keep or upload to another installation"
                      onClick={() => apiDownload(`/api/v1/admin/backups/application/${r.name}/download`, `${r.name}.eaxapp.zip`).catch((e) => act(() => Promise.reject(e)))}>Download all</button>
                    {superAdmin && <>{" · "}<button className="linkish" onClick={() => setAll(r)}>Restore all...</button></>}{" · "}</>}
                    <button className="linkish" onClick={() => act(() => apiFetch(`/api/v1/admin/backups/application/${r.name}/pin`, { method: "POST", body: JSON.stringify({ pinned: !r.pinned }) }))}>{r.pinned ? "Unpin" : "Pin"}</button>
                    {!r.pinned && <>{" · "}<button className="linkish" onClick={() => {
                      // eslint-disable-next-line no-alert
                      if (window.confirm(`Delete the application backup ${r.tag} (${r.name})? This cannot be undone.`)) act(() => apiFetch(`/api/v1/admin/backups/application/${r.name}/delete`, { method: "POST" }), () => `${r.tag} deleted.`);
                    }}>Delete</button></>}</td>
                </tr>
                {open === r.name && (r.models || []).map((m) => (
                  <tr key={`${r.name}/${m.id}`} className="sub-row">
                    <td colSpan="3" className="small">↳ {m.name} <span className="quiet">({m.kind})</span>{m.status !== "ok" && <span className="bad-text"> failed: {m.error}</span>}</td>
                    <td className="small">{m.counts ? `${m.counts.entities} entities, ${m.counts.relationships} relationships` : ""}</td>
                    <td colSpan="3" className="small nowrap">{m.status === "ok" && <>
                      <button className="linkish" onClick={() => apiDownload(`/api/v1/admin/backups/application/${r.name}/${m.file}`, m.file).catch((e) => act(() => Promise.reject(e)))}>Download</button>
                      {" · "}<button className="linkish" onClick={() => onRestore({ where: "application", name: r.name, file: m.file, model: m.id, modelName: m.name, kind: m.kind })}>Restore...</button></>}</td>
                  </tr>
                ))}
              </Fragment>
            ))}
            {!runs.length && <tr><td colSpan="7" className="quiet">{(app.runs || []).length ? `No backup matches "${q}".` : "No application backup yet."}</td></tr>}
          </tbody>
        </table>
      </div>
      {all && <RestoreAll r={all} onClose={() => setAll(null)} />}
      {(app.uploaded || []).length > 0 && <>
        <h4>Uploaded from other installations</h4>
        <table className="grid-table"><tbody>
          {app.uploaded.map((u) => (
            <tr key={u.file}><td>{u.model?.name}</td><td className="small">backed up {when(u.created)} by {u.by}, version {u.version}</td>
              <td className="small">{u.counts ? `${u.counts.entities} entities` : ""}</td>
              <td className="nowrap"><button className="linkish" onClick={() => onRestore({ where: "uploaded", file: u.file, model: u.model?.id, modelName: u.model?.name, kind: u.model?.kind, newOnly: true })}>Restore as a new model...</button>
                {" · "}<button className="linkish" onClick={() => act(() => apiFetch(`/api/v1/admin/backups/uploaded/${u.file}/delete`, { method: "POST" }), () => `${u.file} deleted.`)}>Delete</button></td></tr>
          ))}
        </tbody></table>
      </>}
    </div>
  );
}

// Every model of an application backup put back over itself (D233; Super Admins)
function RestoreAll({ r, onClose }) {
  const [word, setWord] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const n = (r.models || []).filter((m) => m.status === "ok").length;
  async function go() {
    setErr(""); setBusy(true);
    try {
      const t = await apiFetch(`/api/v1/admin/backups/application/${r.name}/restore-all`, { method: "POST", body: JSON.stringify({ confirm: word }) });
      trackTask(t, "#/admin/restores");
      onClose();
      window.location.hash = "#/admin/restores";
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Restore every model of ${r.tag}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="danger" disabled={word !== "RESTORE" || busy} onClick={go}>{busy ? "Starting..." : "Restore all"}</button></>}>
      <p>Backup of {when(r.created)} by {r.by}: {n} model{n === 1 ? "" : "s"}.</p>
      <ul className="small">
        <li>Every model in it goes back to how it was in this backup, as one commit of kind restore. What each is now is kept first, as a model backup and a tag.</li>
        <li>A model that no longer exists is made again, with its name.</li>
        <li>Models made after this backup stay as they are, and so do root metamodels and library models (only project models are put back).</li>
        <li>It can be run again: a model made again by an earlier run is kept as it is.</li>
        <li>A model that cannot be restored is listed with why; the others go on. Everyone is notified; the log is on the Restores tab.</li>
      </ul>
      <label className="ed-field"><span>Type RESTORE to confirm</span><input value={word} onChange={(e) => setWord(e.target.value)} autoFocus /></label>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// Restore an infrastructure backup: choose what, type RESTORE, then follow it (the API may stop and come back)
function RestoreInfra({ b, choices, onClose }) {
  const [what, setWhat] = useState("full");
  const [word, setWord] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    setErr(""); setBusy(true);
    try {
      const out = await apiFetch(`/api/v1/admin/backups/infrastructure/${b.name}/restore`, { method: "POST", body: JSON.stringify({ what, confirm: word }) });
      if (out.restore && out.token) keepToken(out.restore, out.token);
      onClose();
      window.location.hash = out.restore ? `#/admin/restores/${out.restore}` : "#/admin/restores";
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Restore ${b.tag || b.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="danger" disabled={word !== "RESTORE" || busy} onClick={go}>{busy ? "Starting..." : "Restore"}</button></>}>
      <p>Backup of {when(b.created)}{b.version ? `, version ${b.version}` : ""}. What should come back?</p>
      <div className="restore-choices">
        {Object.entries(choices).map(([k, label]) => (
          <label key={k} className="ed-field radio"><input type="radio" name="what" checked={what === k} onChange={() => setWhat(k)} /> <span><b>{k}</b>: {label}</span></label>
        ))}
      </div>
      <p className="status warn small">A backup of the installation as it is now is taken first (pinned). The restore then runs on its own
        (it can take hours): EA Explorer shows a lock page to everyone until it has finished, and you follow its log on the Restores tab.
        Nothing live is changed until everything has been restored cleanly; if it fails, the installation stays as it was. Everyone
        signs in again afterwards. Changes made since this backup are lost{what === "app" ? " only for the config file" : ""}.</p>
      <label className="ed-field"><span>Type RESTORE to confirm</span><input value={word} onChange={(e) => setWord(e.target.value)} autoFocus /></label>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// Restore a model backup file: as a new model, or over the model it came from (type its name)
export function RestoreModel({ b, onClose, modelPage }) {
  const [mode, setMode] = useState(b.newOnly || b.kind === "template" ? "new" : modelPage ? "over" : "new");
  const [name, setName] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    setErr(""); setBusy(true);
    try {
      const t = await apiFetch("/api/v1/admin/backups/restore-model", { method: "POST", body: JSON.stringify({
        where: b.where, name: b.name, file: b.file, model: b.model, mode, new_name: name, confirm, target: b.model }) });
      trackTask(t, mode === "over" ? `#/metamodel/${b.model}/tags` : "#/metamodel");
      onClose(true);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  const canNew = can("models.create") || can("models.all");
  return (
    <Modal title={`Restore ${b.modelName}`} onClose={() => onClose(false)}
      actions={<><button onClick={() => onClose(false)}>Cancel</button>
        <button className={mode === "over" ? "danger" : "primary"} disabled={busy || (mode === "over" && confirm !== b.modelName) || (mode === "new" && !canNew)} onClick={go}>
          {busy ? "Starting..." : "Restore"}</button></>}>
      {!b.newOnly && b.kind !== "template" && (
        <div className="restore-choices">
          <label className="ed-field radio"><input type="radio" checked={mode === "over"} onChange={() => setMode("over")} />
            <span><b>Over {b.modelName}</b>: the model goes back to how it was in this backup (metamodel and content), as one commit. What it is
              now is kept first, as a model backup and as a tag, so this can be undone.</span></label>
          <label className="ed-field radio"><input type="radio" checked={mode === "new"} onChange={() => setMode("new")} />
            <span><b>As a new model</b>: a copy from the backup, next to the model (a draft, to compare or merge).</span></label>
        </div>
      )}
      {mode === "new" && <>
        <label className="ed-field"><span>Name of the new model</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder={`${b.modelName} (restored)`} /></label>
        {!canNew && <p className="status bad small">Restoring as a new model needs the Model Creator role (or Super Admin).</p>}
      </>}
      {mode === "over" && <label className="ed-field"><span>Type the model's name ({b.modelName}) to confirm</span><input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoFocus /></label>}
      <p className="quiet small">It runs in the background; the top bar says when it is done.</p>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// The model page's Backups tab (its Model Admins)
export function ModelBackupsTab({ model }) {
  const { data, error } = useApi(`/api/v1/models/${model}/backups`);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [restoring, setRestoring] = useState(null);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  async function backupNow() {
    setErr(""); setMsg("");
    try {
      const t = await apiFetch(`/api/v1/models/${model}/backups`, { method: "POST", body: JSON.stringify({ note }) });
      trackTask(t, `#/metamodel/${model}/backups`); setNote("");
      setMsg("Backing up in the background: it is listed here when done.");
    } catch (e) { setErr(e.message); }
  }
  async function pin(b) {
    try { await apiFetch(`/api/v1/models/${model}/backups/${b.file}/pin`, { method: "POST", body: JSON.stringify({ pinned: !b.pinned }) }); refreshAll(); } catch (e) { setErr(e.message); }
  }
  async function del(b) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete the backup of ${when(b.created)}? This cannot be undone.`)) return;
    try { await apiFetch(`/api/v1/models/${model}/backups/${b.file}/delete`, { method: "POST" }); refreshAll(); } catch (e) { setErr(e.message); }
  }
  const dl = (b) => (b.where === "model" ? apiDownload(`/api/v1/models/${model}/backups/${b.file}`, b.file)
    : apiDownload(`/api/v1/admin/backups/application/${b.run}/${b.file}`, b.file)).catch((e) => setErr(e.message));
  return (
    <div>
      <p className="quiet">Back {data.model.name} up before a change you expect may break it, then put it back if it does: the backup holds the
        metamodel, every entity and relationship with their history, and an Excel workbook to read. Download it to keep it elsewhere. The
        newest {data.keep} are kept, pinned ones always. Tags (the Tags tab) are the lighter way to mark a version.</p>
      <div className="row-gap filters">
        <input value={note} maxLength={80} onChange={(e) => setNote(e.target.value)} placeholder="Why, e.g. before reorganising capabilities" />
        <button className="primary" onClick={backupNow}>Back up now</button>
      </div>
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
      <table className="grid-table">
        <thead><tr><th>When</th><th>Why</th><th>By</th><th>Content</th><th>Size</th><th /></tr></thead>
        <tbody>
          {data.backups.map((b) => (
            <tr key={`${b.where}/${b.run}/${b.file}`}>
              <td className="small nowrap">{when(b.created)}{b.pinned && <span className="badge pin-badge">📌</span>}</td>
              <td className="small">{b.where === "application" ? <>Application backup <b>{b.why}</b></> : b.why}</td>
              <td className="small">{b.by}</td>
              <td className="small">{b.counts ? `${b.counts.entities} entities, ${b.counts.relationships} relationships` : ""}</td>
              <td className="small nowrap">{size(b.bytes)}</td>
              <td className="nowrap small">
                <button className="linkish" onClick={() => dl(b)}>Download</button>
                {b.where === "model" && <>{" · "}<button className="linkish" onClick={() => pin(b)}>{b.pinned ? "Unpin" : "Pin"}</button></>}
                {b.where === "model" && !b.pinned && <>{" · "}<button className="linkish" onClick={() => del(b)}>Delete</button></>}
                {" · "}<button className="linkish" onClick={() => setRestoring({ where: b.where, name: b.run, file: b.file, model: data.model.id, modelName: data.model.name, kind: data.model.kind })}>Restore...</button>
              </td>
            </tr>
          ))}
          {!data.backups.length && <tr><td colSpan="6" className="quiet">No backup of this model yet.</td></tr>}
        </tbody>
      </table>
      {(data.restores || []).length > 0 && <>
        <h4>Restores of {data.model.name}</h4>
        <table className="grid-table"><tbody>
          {data.restores.map((r) => (
            <tr key={r.id}><td className="small nowrap">{fmtDateTime(r.started)}</td><td className="small">{r.backup}</td>
              <td className="small">{r.what === "over" ? "over the model" : "as a new model"}</td><td className="small">{r.by}</td>
              <td><span className={r.status === "ok" ? "status ok" : r.status === "running" ? "status warn" : "status bad"}>{r.status}</span>
                {r.error && <div className="bad-text small">{r.error.slice(0, 200)}</div>}</td></tr>
          ))}
        </tbody></table>
      </>}
      {restoring && <RestoreModel b={restoring} modelPage onClose={(done) => { setRestoring(null); if (done) setMsg("Restoring in the background: the top bar says when it is done, and its log is listed below."); }} />}
    </div>
  );
}
