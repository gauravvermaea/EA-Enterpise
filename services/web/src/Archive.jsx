// The archive (R2.41, D626): models taken out of the working database, kept in the archive database as their backup
// file. Their admins see the archived ones and bring them back; a Super Admin also sees the deleted ones, brings them
// back or purges them for good. Archiving and deleting start from Model Admin › a model › Lifecycle; a project (with the
// models only it uses, R2.41 part 2) from the project's About tab › Back up and restore.
import { useState } from "react";
import { apiDownload, apiFetch } from "./auth";
import { useApi } from "./ModelViews";
import { runTask } from "./tasks";
import { fmtDateTime } from "./fmt";
import { Modal } from "./ModelOps";

function size(n) { return n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`; }

export default function ArchivePage() {
  const [deleted, setDeleted] = useState(false);
  const [kind, setKind] = useState("model");
  const [tick, setTick] = useState(0);
  const { data, error } = useApi(`/api/v1/archive?kind=${kind}${deleted ? "&deleted=1" : ""}&t=${tick}`);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(0);
  async function back(r) {
    setBusy(r.id); setMsg("");
    try {
      const out = await runTask(apiFetch(`/api/v1/archive/${r.id}/restore`, { method: "POST" }), "#/archive");
      setMsg(out?.message || `${r.name} is being brought back.`); setTick((t) => t + 1);
    } catch (e) { setMsg(e.message); }
    setBusy(0);
  }
  async function purge(r) {
    const typed = window.prompt(`Purge ${r.name} for good? It cannot be brought back. Type DELETE to confirm.`); // eslint-disable-line no-alert
    if (typed !== "DELETE") return;
    try { setMsg((await apiFetch(`/api/v1/archive/${r.id}/purge`, { method: "POST", body: JSON.stringify({ confirm: "DELETE" }) })).message); setTick((t) => t + 1); }
    catch (e) { setMsg(e.message); }
  }
  if (error) return <section><h1>Archive</h1><p className="status bad">{error}</p></section>;
  return (
    <section>
      <h1>Archive</h1>
      <p className="quiet">Models and projects moved out of the working databases: they no longer slow them down and nothing of them is lost.
        Bring one back to work on it again. To archive a model: Model Admin › the model › Lifecycle › Move to the archive. To archive a
        project: the project › About › Back up and restore › Move to the archive (the models only it uses go with it).</p>
      <div className="tabs" role="tablist">
        {[["model", "Models"], ["project", "Projects"]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={kind === k} className={kind === k ? "tab active" : "tab"} onClick={() => setKind(k)}>{l}</button>))}
      </div>
      {data?.super_admin && <label><input type="checkbox" checked={deleted} onChange={(e) => setDeleted(e.target.checked)} /> Show the deleted ones too</label>}
      {msg && <p className="status">{msg}</p>}
      {!data ? <p>Loading...</p> : !data.items.length ? <p className="quiet">Nothing in the archive.</p> : (
        <table className="grid-table">
          <thead><tr><th>{kind === "project" ? "Project" : "Model"}</th><th>State</th><th>{kind === "project" ? "Its models" : "Entities"}</th><th>Moved</th><th>Why</th><th>Size</th><th /></tr></thead>
          <tbody>{data.items.map((r) => (
            <tr key={r.id}>
              <td><b>{r.name}</b>{r.summary?.description && <div className="quiet small">{r.summary.description.slice(0, 120)}</div>}</td>
              <td>{r.state === "deleted" ? <span className="bad-text">deleted</span> : "archived"}</td>
              <td className={kind === "project" ? "small" : ""}>{kind === "project" ? (r.summary?.models || []).map((x) => x.name).join(", ") : r.summary?.counts?.entities ?? ""}</td>
              <td className="small">{fmtDateTime(r.moved_at)} by {r.moved_by}</td>
              <td className="small">{r.note}</td>
              <td className="small">{size(r.file_bytes)}</td>
              <td className="row-gap">
                <button disabled={busy === r.id} onClick={() => back(r)}>{busy === r.id ? "Bringing back…" : "Bring back"}</button>
                <button onClick={() => apiDownload(`/api/v1/archive/${r.id}/download`, `${r.name}.eaxbackup.zip`)}>Download</button>
                {data.super_admin && <button className="danger" onClick={() => purge(r)}>Purge</button>}
              </td>
            </tr>))}</tbody>
        </table>)}
    </section>
  );
}

// Model Admin › a model › Lifecycle › Move to the archive (or Delete, Super Admins): what refers to it first
export function MoveToArchiveDialog({ m, superAdmin, onClose }) {
  const { data: refs, error } = useApi(`/api/v1/models/${m.id}/archive/references`);
  const [state, setState] = useState("archived");
  const [note, setNote] = useState("");
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function go() {
    setBusy(true); setErr("");
    try {
      await runTask(apiFetch(`/api/v1/models/${m.id}/archive`, { method: "POST", body: JSON.stringify({ state, note }) }), "#/archive");
      window.location.hash = "#/archive"; onClose();
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  const blocked = (refs?.blocking || []).length > 0;
  return (
    <Modal title={`Move ${m.name} to the archive`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="danger" disabled={busy || blocked || !refs || typed !== m.name} onClick={go}>{busy ? "Moving…" : state === "deleted" ? "Delete" : "Move to the archive"}</button></>}>
      <div className="ed-form">
        <p>{m.name} leaves the working database, whole, with its history: it is kept in the archive and can be brought back.
          Archiving is not freezing: to keep it here read only, freeze it instead.</p>
        {error && <p className="status bad">{error}</p>}
        {refs && blocked && <p className="status bad">It cannot move while {refs.blocking.join("; ")}.</p>}
        {refs && !blocked && (refs.copies.length > 0 || refs.open_merge_requests > 0) &&
          <p className="quiet">Also: {refs.copies.length > 0 && <>copied from it: {refs.copies.join(", ")}. </>}
            {refs.open_merge_requests > 0 && <>{refs.open_merge_requests} open merge request(s) end.</>}</p>}
        {superAdmin && <label><input type="checkbox" checked={state === "deleted"} onChange={(e) => setState(e.target.checked ? "deleted" : "archived")} />
          {" "}Delete it instead: hidden from everyone but Super Admins, kept until a Super Admin purges it</label>}
        <label>Why<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Project finished in 2026" /></label>
        <label>{`Type the model's name (${m.name}) to confirm`}<input value={typed} onChange={(e) => setTyped(e.target.value)} /></label>
        {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}

// the project › About › Back up and restore › Move to the archive (R2.41 part 2): the models that go with it and those that stay
export function MoveProjectToArchiveDialog({ p, superAdmin, onClose }) {
  const { data: refs, error } = useApi(`/api/v1/projects/${p.id}/archive/references`);
  const [state, setState] = useState("archived");
  const [note, setNote] = useState("");
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function go() {
    setBusy(true); setErr("");
    try {
      await runTask(apiFetch(`/api/v1/projects/${p.id}/archive`, { method: "POST", body: JSON.stringify({ state, note }) }), "#/archive");
      window.location.hash = "#/archive"; onClose();
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Move ${p.name} to the archive`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="danger" disabled={busy || !refs || typed !== p.name} onClick={go}>{busy ? "Moving…" : state === "deleted" ? "Delete" : "Move to the archive"}</button></>}>
      <div className="ed-form">
        <p>{p.name} leaves the working databases with its people, steps, history and documents: it is kept in the archive and can be brought back.</p>
        {error && <p className="status bad">{error}</p>}
        {refs && <>
          <p className="small"><b>Go with it</b> (only this project uses them): {refs.moving.length ? refs.moving.map((m) => m.name).join(", ") : "none"}</p>
          {refs.staying.length > 0 && <p className="small quiet"><b>Stay where they are</b>: {refs.staying.map((m) => `${m.name} (${m.why})`).join("; ")}</p>}
        </>}
        {superAdmin && <label><input type="checkbox" checked={state === "deleted"} onChange={(e) => setState(e.target.checked ? "deleted" : "archived")} />
          {" "}Delete it instead: hidden from everyone but Super Admins, kept until a Super Admin purges it</label>}
        <label>Why<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Study finished" /></label>
        <label>{`Type the project's name (${p.name}) to confirm`}<input value={typed} onChange={(e) => setTyped(e.target.value)} /></label>
        {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}

// Include archived on the model and project lists (R2.41, D647; the owner's answer 12 Nov 2026): the archived ones this
// person may see, fetched from the archive database only when ticked; read only, brought back from the Archive page.
export function ArchivedRows({ kind, q = "" }) {
  const { data, error } = useApi(`/api/v1/archive?kind=${kind}`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Fetching the archive...</p>;
  const t = q.trim().toLowerCase();
  const rows = (data.items || []).filter((r) => !t || `${r.name} ${r.summary?.description || ""}`.toLowerCase().includes(t));
  return (
    <section className="archived-results" aria-label="In the archive">
      <h3>In the archive ({rows.length})</h3>
      {!rows.length ? <p className="quiet">Nothing archived{t ? " matches" : ""}.</p> : (
        <table className="grid-table">
          <thead><tr><th>{kind === "project" ? "Project" : "Model"}</th><th>Description</th><th>Moved</th><th>By</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.id} className="is-retired">
              <td><a href={kind === "project" ? "#/archive?kind=project" : "#/archive"}>{r.name}</a> <span className="quiet small">archived</span></td>
              <td className="small">{r.summary?.description || ""}</td>
              <td className="small nowrap">{r.moved_at ? fmtDateTime(r.moved_at) : ""}</td>
              <td className="small">{r.moved_by}</td>
            </tr>))}</tbody>
        </table>)}
      <p className="quiet small">Read only here; their admins bring them back from the Archive.</p>
    </section>
  );
}
