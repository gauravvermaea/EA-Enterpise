// Project admin › Template setup (owner, 8 Nov 2026, D317): the content framework defaults every project starts from.
// Each deliverable and artifact of the project library sits in one area or several (dashed: built in; solid: chosen
// here); each template may sit in areas of its own as well, chosen also while a new template is uploaded. Entity types
// are placed in their model's metamodel and entities on their own screen. A project inherits these, then its parent
// project's choices, then makes its own.
import { useState } from "react";
import { apiFetch, apiUpload } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { AreaChecks, AreaChips, AreaPicker } from "./CfAreaPicker";

const DA = ({ kind }) => <span className={`kind-toggle ${kind === "Deliverable" ? "del" : "art"}`} title={kind}>{kind === "Deliverable" ? "D" : "A"}</span>;

export function TemplateSetup() {
  const [view, setView] = useState("classes");
  const [lib, setLib] = useState("");
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const [adding, setAdding] = useState(false);
  const { data, error } = useApi(`/api/v1/projects/library/template-setup${lib ? `?library=${lib}` : ""}`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const ql = q.trim().toLowerCase();
  const match = (...xs) => !ql || xs.join(" ").toLowerCase().includes(ql);
  async function put(url, areas) {
    try { const r = await apiFetch(url, { method: "PUT", body: JSON.stringify({ areas }) }); setMsg({ ok: true, text: r.message }); refreshAll(); }
    catch (e) { setMsg({ ok: false, text: e.message }); throw e; }
  }
  async function putRepo(id, v) {
    try { const r = await apiFetch(`/api/v1/projects/library/items/${id}/repository-area`, { method: "PUT", body: JSON.stringify({ repository_area: v }) });
      setMsg({ ok: true, text: r.message }); refreshAll(); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
  }
  const classes = data.classes.filter((c) => match(c.name, c.phase, c.type));
  const templates = (data.templates || []).filter((t) => match(t.name, t.item, t.folder));
  return (
    <div className="cf-tag">
      <p className="quiet">Where each deliverable, artifact and template sits in the content framework, and the part of the Architecture Repository each
        deliverable or artifact is filed in (its Repository area, for all its documents), for every new project. A project takes these,
        then its parent project's choices, and may change them for itself (Content framework › Tag items). Dashed: built in; solid: chosen here.
        Entity types are placed in their model's metamodel (Model admin › the model › Metamodel › Change entity type); single entities on their
        own screen (✎ Edit).</p>
      <div className="cf-views sub" role="tablist">
        <button role="tab" aria-selected={view === "classes"} className={`cf-view${view === "classes" ? " on" : ""}`} onClick={() => setView("classes")}>
          Deliverables and artifacts <span className="quiet small">{data.classes.length}</span></button>
        <button role="tab" aria-selected={view === "templates"} className={`cf-view${view === "templates" ? " on" : ""}`} onClick={() => setView("templates")}>
          Templates</button>
      </div>
      <div className="row-gap cf-tag-tools">
        {view === "templates" && <label>Library <select value={data.library?.id || ""} onChange={(e) => setLib(e.target.value)}>
          {data.libraries.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>}
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find by name" aria-label="Find by name" />
        {view === "templates" && data.library?.may_add && <button className="primary" onClick={() => setAdding(true)}>⬆ Upload a template…</button>}
        {view === "templates" && data.library && !data.library.may_add && <span className="small quiet">EA Explorer's own templates ship with it; its templates may
          still sit in areas of their own.</span>}
      </div>
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      {view === "classes" ? (
        <table className="cf-tag-table">
          <thead><tr><th>Phase</th><th>Deliverable / artifact</th><th>D/A</th><th>Content framework areas</th><th /><th>Repository area</th></tr></thead>
          <tbody>
            {classes.map((c) => (
              <tr key={c.id}>
                <td>{c.phase}</td><td><b>{c.name}</b><div className="quiet small">{c.type}</div></td><td><DA kind={c.kind} /></td>
                <td>{c.areas.length ? <AreaChips codes={c.areas} dflt={!c.chosen} small /> : <span className="quiet small">not placed</span>}</td>
                <td className="nowrap">
                  <AreaPicker value={c.chosen ? c.areas : []} dflt={c.default} label={c.areas.length ? "Change…" : "Place…"}
                    resetLabel={c.chosen ? "Back to built in" : ""} onSave={(l) => put(`/api/v1/projects/library/items/${c.id}/content-area`, l)} />
                </td>
                <td><select value={c.repository_chosen ? c.repository : ""} aria-label={`Repository area of ${c.name}`}
                  onChange={(e) => putRepo(c.id, e.target.value)}>
                  <option value="">{c.repository_default} (built in)</option>
                  {data.repository_areas.map((r) => <option key={r} value={r}>{r}</option>)}</select></td>
              </tr>
            ))}
            {!classes.length && <tr><td colSpan={6} className="quiet">Nothing matches.</td></tr>}
          </tbody>
        </table>
      ) : (
        <table className="cf-tag-table">
          <thead><tr><th>Template</th><th>For</th><th>Its deliverable's or artifact's areas</th><th>Its own areas too</th><th /></tr></thead>
          <tbody>
            {templates.map((t) => (
              <tr key={t.id}>
                <td>📄 {t.name}<div className="quiet small">{t.folder}{t.has_file ? "" : " · no file yet"}</div></td>
                <td>{t.item ? <>{t.phase} · {t.item}</> : <span className="quiet small">no deliverable or artifact</span>}</td>
                <td><AreaChips codes={t.class_areas} dflt small /></td>
                <td>{t.areas.length ? <AreaChips codes={t.areas} small /> : <span className="quiet small">none</span>}</td>
                <td className="nowrap"><AreaPicker value={t.areas} label={t.areas.length ? "Change…" : "Add areas…"}
                  resetLabel={t.areas.length ? "None of its own" : ""} onSave={(l) => put(`/api/v1/projects/library/templates/${t.id}/content-area`, l)} /></td>
              </tr>
            ))}
            {!templates.length && <tr><td colSpan={5} className="quiet">{q ? "Nothing matches." : "This library has no templates."}</td></tr>}
          </tbody>
        </table>
      )}
      {adding && <AddTemplateDialog lib={data.library} classes={data.classes} onClose={() => setAdding(false)}
        onDone={(m) => { setAdding(false); setMsg({ ok: true, text: m }); refreshAll(); }} />}
    </div>
  );
}

// Uploading a template: its file, what it is for, and where it sits (its class's areas for every project; its own too)
function AddTemplateDialog({ lib, classes, onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [item, setItem] = useState("");
  const [classAreas, setClassAreas] = useState(null);   // null: unchanged
  const [own, setOwn] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const cls = classes.find((c) => String(c.id) === item);
  const phases = [...new Set(classes.map((c) => c.phase))];
  async function send() {
    setBusy(true); setErr("");
    const fd = new FormData();
    fd.append("file", file); fd.append("item", item); fd.append("areas", own.join(","));
    if (classAreas !== null) fd.append("class_areas", classAreas.join(","));
    try { const r = await apiUpload(`/api/v1/projects/library/libraries/${lib.id}/templates`, fd); onDone(r.message); }
    catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Upload a template into ${lib.name}`} onClose={onClose} wide
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!file || busy} onClick={send}>{busy ? "Uploading..." : "Upload"}</button></>}>
      <div className="form-grid">
        <label>File <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} /></label>
        <label>For the deliverable or artifact <select value={item} onChange={(e) => { setItem(e.target.value); setClassAreas(null); }}>
          <option value="">none (a file in the library's top folder)</option>
          {phases.map((ph) => <optgroup key={ph} label={`Phase ${ph}`}>{classes.filter((c) => c.phase === ph).map((c) =>
            <option key={c.id} value={c.id}>{c.name} ({c.kind})</option>)}</optgroup>)}
        </select></label>
      </div>
      {cls && <>
        <h4>Where {cls.name} sits <span className="quiet small">for every project, with all its templates</span></h4>
        <p className="small"><AreaChips codes={classAreas ?? cls.areas} dflt={classAreas === null && !cls.chosen} small />{" "}
          {classAreas === null ? <button className="linkish small" onClick={() => setClassAreas(cls.areas)}>Change…</button>
            : <button className="linkish small" onClick={() => setClassAreas(null)}>Keep as it is</button>}</p>
        {classAreas !== null && <AreaChecks value={classAreas} onChange={setClassAreas} />}
      </>}
      <h4>This template's own areas too <span className="quiet small">optional: documents made from it sit here as well</span></h4>
      <AreaChecks value={own} onChange={setOwn} />
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}
