// Deliveries (build phase 34 and 34.1, D370, D378, D462 to D467): the Import and export tab's Deliveries part.
//   #/metamodel/<model>/import/deliveries   the model's import sources (other systems writing our published formats), their
//                                           folders, deliveries waiting for review; add or change a source (Model Admins);
//                                           upload a delivery for a source; take the files dropped in its folder
// A delivery is a load (Sheets.jsx LoadPage) from a source: matched by type and name, never deleting, values in EA Explorer
// kept unless the source's values win; a Committer accepts it as their committed load (DeliveryActions) or declines it.
import { useState } from "react";
import { apiUpload, apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Field, Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";
import { trackTask, useTask } from "./tasks";

const go = (path) => { window.location.hash = path; };
const post = (path, body, method = "POST") => apiFetch(path, { method, body: JSON.stringify(body || {}) });
const STATUS = { uploaded: "being previewed", mapping: "needs its columns mapped", previewed: "waiting for review", added: "accepted",
  undone: "accepted, then undone", declined: "declined", failed: "failed" };

export default function DeliveriesTab({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/import-sources`);
  const [editing, setEditing] = useState(null);     // {} for a new source, or the source
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  async function collect(s) {
    setErr(""); setMsg("");
    try {
      const out = await post(`/api/v1/import-sources/${s.id}/collect`);
      (out.tasks || []).forEach((t) => trackTask(t, `#/metamodel/${model}/import/deliveries`));
      setMsg(out.message + (out.failed?.length ? ` ${out.failed.map((f) => `${f.file}: ${f.why}`).join(" ")}` : ""));
      refreshAll();
    } catch (e) { setErr(e.message); }
  }
  return (
    <div className="deliveries">
      <div className="merge-step">
        <h3>Deliveries waiting for review</h3>
        <p className="quiet">Files other systems delivered in the published formats. Each is matched by type and name and shown as a
          preview: open it, check what is new, changed and kept, then <b>accept</b> it as your committed load or decline it.
          A delivery only adds and changes; it never deletes.</p>
        <DeliveryTable model={model} loads={data.waiting} empty={data.may_accept ? "Nothing waiting." : "Deliveries are reviewed by the model's Committers."} />
      </div>
      <div className="merge-step">
        <h3>Sources</h3>
        <p className="quiet">A source is another system that delivers to {m.name}. It drops files in its own folder and calls the API
          (or <code>eax import</code>), sends them to the API with a service account, or someone uploads them here. The formats and
          examples: <b>docs/import-formats.md</b>; empty templates under Download and upload.</p>
        <div className="table-scroll">
          <table className="grid-table">
            <thead><tr><th>Source</th><th>Folder (in the import folder)</th><th>Values</th><th className="num">Waiting</th>
              <th className="num">Accepted</th><th>Last delivery</th><th /></tr></thead>
            <tbody>
              {data.sources.map((s) => (
                <tr key={s.id} className={s.active ? "" : "quiet"}>
                  <td><b>{s.name}</b>{!s.active && " (off)"}<div className="quiet small">{s.description}</div>
                    <div className="quiet small">Told: {s.contact}{s.sender ? ` · sent by ${s.sender}` : ""}</div></td>
                  <td className="small"><code>{s.path}</code>{s.incoming?.length > 0 && <div className="status warn">{s.incoming.length} file{s.incoming.length === 1 ? "" : "s"} dropped, not taken yet</div>}</td>
                  <td className="small">{s.values_win ? <b>Its values win</b> : "EA Explorer's values stay; it fills empty fields"}</td>
                  <td className="num">{s.deliveries.waiting || ""}</td><td className="num">{s.deliveries.accepted || ""}</td>
                  <td className="small">{s.last_delivery_at ? fmtDateTime(s.last_delivery_at) : "never"}</td>
                  <td className="nowrap">
                    {s.active && <button onClick={() => collect(s)} title="Take the files dropped in its folder: each becomes a delivery, previewed">Take dropped files</button>}{" "}
                    {s.active && <UploadDelivery model={model} source={s} onDone={(t) => { setMsg(t); refreshAll(); }} />}{" "}
                    {data.may_manage && <button className="linkish" onClick={() => setEditing(s)}>Change</button>}
                  </td>
                </tr>
              ))}
              {!data.sources.length && <tr><td colSpan="7" className="quiet">No sources yet{data.may_manage ? ": add the first one." : "."}</td></tr>}
            </tbody>
          </table>
        </div>
        {data.may_manage && <div className="toolbar"><button className="primary" onClick={() => setEditing({})}>+ Add a source</button></div>}
        {msg && <p className="status ok">{msg}</p>}
        {err && <p className="status bad">{err}</p>}
      </div>
      <div className="merge-step">
        <h3>Earlier deliveries</h3>
        <EarlierDeliveries model={model} />
      </div>
      {editing && <SourceDialog model={model} source={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function DeliveryTable({ model, loads, empty }) {
  return (
    <div className="table-scroll">
      <table className="grid-table">
        <thead><tr><th>File</th><th>Source</th><th>Came</th><th>Status</th><th className="num">New</th><th className="num">Changed</th>
          <th className="num">Kept</th><th className="num">Problems</th></tr></thead>
        <tbody>
          {loads.map((l) => (
            <tr key={l.id}>
              <td><a href={`#/metamodel/${model}/import/load/${l.id}`}>{l.file_name}</a></td>
              <td className="small">{l.source?.name}</td>
              <td className="small">{fmtDateTime(l.created_at)}<div className="quiet">{{ folder: "dropped in its folder", api: "sent to the API", upload: "uploaded here" }[l.delivery]} by {l.created_by}</div></td>
              <td className="small">{STATUS[l.status] || l.status}{l.accepted_by ? ` by ${l.accepted_by}` : ""}{l.declined_by ? ` by ${l.declined_by}` : ""}</td>
              <td className="num">{l.summary?.new ?? ""}</td><td className="num">{l.summary?.changed ?? ""}</td>
              <td className="num">{l.summary?.kept || ""}</td><td className="num">{l.summary?.problem || ""}</td>
            </tr>
          ))}
          {!loads.length && <tr><td colSpan="8" className="quiet">{empty}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function EarlierDeliveries({ model }) {
  const { data } = useApi(`/api/v1/models/${model}/loads`);
  const done = (data?.loads || []).filter((l) => l.source && !["uploaded", "mapping", "previewed"].includes(l.status));
  return <DeliveryTable model={model} loads={done} empty="None yet." />;
}

function UploadDelivery({ model, source, onDone }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function pick(file) {
    if (!file) return;
    setBusy(true); setErr("");
    const form = new FormData();
    form.append("file", file);
    try {
      const out = await apiUpload(`/api/v1/import-sources/${source.id}/deliveries?how=upload`, form);
      trackTask(out.task, `#/metamodel/${model}/import/load/${out.load.id}`);
      go(`/metamodel/${model}/import/load/${out.load.id}`);
    } catch (e) { setErr(e.message); onDone?.(""); }
    setBusy(false);
  }
  return (
    <label className="button" title={`Upload a file ${source.name} delivered (Excel, a CSV set .zip with master.csv, or a CSV)`}>
      {busy ? "Uploading..." : "⬆ Upload a delivery"}
      <input type="file" hidden accept=".xlsx,.xlsm,.zip,.csv" onChange={(e) => pick(e.target.files[0])} />
      {err && <span className="status bad"> {err}</span>}
    </label>
  );
}

function SourceDialog({ model, source, onClose }) {
  const isNew = !source.id;
  const [f, setF] = useState({ name: source.name || "", description: source.description || "", values_win: !!source.values_win,
    contact: source.contact || "", sender: source.sender || "", active: source.active !== false });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  async function save() {
    setErr("");
    try {
      if (isNew) await post(`/api/v1/models/${model}/import-sources`, f);
      else await post(`/api/v1/import-sources/${source.id}`, f, "PATCH");
      refreshAll(); onClose();
    } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={isNew ? "Add an import source" : `Change ${source.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!f.name.trim()} onClick={save}>Save</button></>}>
      <div className="ed-form">
      <Field label="Name"><input value={f.name} onChange={set("name")} placeholder="The system that delivers, for example Configuration database" autoFocus /></Field>
      <Field label="What it delivers"><textarea rows="2" value={f.description} onChange={set("description")} /></Field>
      <p><label><input type="checkbox" checked={f.values_win} onChange={set("values_win")} /> Its values win for the fields it delivers</label><br />
        <span className="quiet small">Otherwise values already in EA Explorer stay and the delivery only fills empty fields; the preview shows what was kept.</span></p>
      <Field label="Who is told when a delivery waits" hint="a user name; you, if empty"><input value={f.contact} onChange={set("contact")} /></Field>
      <Field label="Service account that sends it" hint="optional"
        tip="It may deliver without a role on the model (System admin › Machine access, the Models area)"><input value={f.sender} onChange={set("sender")} placeholder="svc-..." /></Field>
      {!isNew && <p><label><input type="checkbox" checked={f.active} onChange={set("active")} /> On (when off, nothing is taken from it)</label></p>}
      {isNew && <p className="quiet small">Its folder is made in the import folder: deliveries/&lt;model&gt;/&lt;source&gt;/incoming.</p>}
      {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}

// on a delivery's load page: accept (a task) or decline, instead of adding it to your own changes
export function DeliveryActions({ model, load, onMessage }) {
  const [taskId, setTaskId] = useState(null);
  const [declining, setDeclining] = useState(false);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const task = useTask(taskId);
  const s = load.summary || {};
  const n = (s.new || 0) + (s.changed || 0);
  async function accept() {
    setErr("");
    try {
      const out = await post(`/api/v1/loads/${load.id}/accept`);
      trackTask(out.task, `#/metamodel/${model}/import/load/${load.id}`);
      setTaskId(out.task.id);
      onMessage?.("Accepting in the background: the bar at the top says when it is committed.");
    } catch (e) { setErr(e.message); }
  }
  async function decline() {
    setErr("");
    try { const out = await post(`/api/v1/loads/${load.id}/decline`, { note }); onMessage?.(out.message); setDeclining(false); refreshAll(); } catch (e) { setErr(e.message); }
  }
  if (load.status !== "previewed") return null;
  return (
    <>
      <button className="primary" disabled={task && !task.done} onClick={accept}
        title="Its rows become your changes and are committed at once: your load (undo it here if needed)">
        {task && !task.done ? "Accepting..." : `Accept and commit ${n} change${n === 1 ? "" : "s"}`}</button>
      <button onClick={() => setDeclining(true)}>Decline</button>
      {err && <span className="status bad"> {err}</span>}
      {declining && (
        <Modal title="Decline this delivery" onClose={() => setDeclining(false)}
          actions={<><button onClick={() => setDeclining(false)}>Cancel</button><button className="primary" onClick={decline}>Decline</button></>}>
          <div className="ed-form">
          <p>Nothing in {load.model?.name} changes. The source's contact sees why.</p>
          <Field label="Why" hint="optional"><textarea rows="3" value={note} onChange={(e) => setNote(e.target.value)} autoFocus /></Field>
          </div>
        </Modal>
      )}
    </>
  );
}
