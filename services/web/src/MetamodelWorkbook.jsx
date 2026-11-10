// A model from a metamodel workbook (D419, built with phase 34, D468): download the template (empty, or a model's metamodel in
// the same layout: round trip), fill it in Excel, upload it, see what it would make (added, changed, errors), make the model.
// Blank (the workbook is the whole metamodel) or added to an existing model (adds and updates, never takes away, D289).
// Whoever may create a model today (Model Creators, Library Admins, Super Admins).
import { useState } from "react";
import { apiDownload, apiUpload, needsRole } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Field, Modal, mayCreate } from "./ModelOps";

const go = (path) => { window.location.hash = path; };
const SECTIONS = [["domains", "Domains"], ["pick_lists", "Pick lists"], ["attributes", "Attributes"], ["entity_types", "Types"],
  ["relationship_types", "Relationship types"], ["allowed", "Allowed relationships"], ["rules", "Rules"]];

export function WorkbookButton() {
  const [open, setOpen] = useState(false);
  const ok = mayCreate();
  return (
    <>
      <button disabled={!ok} onClick={() => setOpen(true)}
        title={ok ? "A new model from a metamodel workbook (Excel): blank, or added to an existing model's metamodel"
          : `Creating a model: ${needsRole(["model-creator", "library-admin"])}`}>⬆ Model from a metamodel workbook</button>
      {open && <WorkbookDialog onClose={() => setOpen(false)} />}
    </>
  );
}

export function WorkbookDialog({ onClose }) {
  const { data: models } = useApi("/api/v1/models?archived=false");
  const [file, setFile] = useState(null);
  const [base, setBase] = useState("");          // "" blank, else the model it is added to
  const [from, setFrom] = useState("");          // the model whose metamodel to download
  const [p, setP] = useState(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const list = (models?.models || models || []).filter((m) => !m.is_deleted);
  function form() {
    const f = new FormData();
    f.append("file", file);
    if (base) f.append("base", base);
    return f;
  }
  async function check() {
    setBusy(true); setErr(""); setP(null);
    try {
      const out = await apiUpload("/api/v1/metamodel-workbooks/preview", form());
      setP(out); if (!name) setName(out.name || "");
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  async function make() {
    setBusy(true); setErr("");
    const f = form();
    f.append("name", name);
    try {
      const out = await apiUpload("/api/v1/metamodel-workbooks", f);
      refreshAll(); onClose(); go(`/metamodel/${out.model.id}`);
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal wide title="A model from a metamodel workbook" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button onClick={check} disabled={!file || busy}>{busy && !p ? "Checking..." : "Check it"}</button>
        <button className="primary" disabled={!p || p.errors.length > 0 || !name.trim() || busy} onClick={make}>{busy && p ? "Making..." : "Make the model"}</button></>}>
      <div className="ed-form">
      <p className="quiet">The workbook holds the metamodel only: domains, pick lists, attributes (a <b>url</b> attribute is a Link), types and
        which attributes they have, relationship types, allowed relationships with their multiplicities, and rules. Load data
        afterwards with Import and export.</p>
      <div className="merge-step">
        <h4>1. Get a workbook</h4>
        <div className="toolbar">
          <button onClick={() => apiDownload("/api/v1/metamodel-workbooks/template", "metamodel workbook.xlsx").catch((e) => setErr(e.message))}>⬇ Empty template</button>
          <span className="quiet">or a model's metamodel, to change:</span>
          <select value={from} onChange={(e) => setFrom(e.target.value)} aria-label="Model whose metamodel to download">
            <option value="">Choose a model...</option>
            {list.map((m) => <option key={m.id} value={m.id}>{m.name}{m.version_label ? ` ${m.version_label}` : ""}</option>)}
          </select>
          <button disabled={!from} onClick={() => apiDownload(`/api/v1/metamodel-workbooks/template?model=${from}`, "metamodel workbook.xlsx").catch((e) => setErr(e.message))}>⬇ Its metamodel</button>
        </div>
      </div>
      <div className="merge-step">
        <h4>2. Upload it</h4>
        <div className="toolbar">
          <input type="file" accept=".xlsx,.xlsm" onChange={(e) => { setFile(e.target.files[0] || null); setP(null); }} />
        </div>
        <div className="toolbar">
          <label><input type="radio" checked={!base} onChange={() => { setBase(""); setP(null); }} /> Blank: the workbook is the whole metamodel</label>
          <label><input type="radio" checked={!!base} onChange={() => { setBase(list[0]?.id || ""); setP(null); }} /> Added to an existing model:</label>
          <select value={base} disabled={!base} onChange={(e) => { setBase(e.target.value); setP(null); }} aria-label="Model it is added to">
            {list.map((m) => <option key={m.id} value={m.id}>{m.name}{m.version_label ? ` ${m.version_label}` : ""}</option>)}
          </select>
        </div>
        {base && <p className="quiet small">It adds to that model's metamodel and updates items with the same code; nothing is taken away.</p>}
      </div>
      {p && (
        <div className="merge-step">
          <h4>3. What it would make</h4>
          <table className="grid-table small">
            <thead><tr><th /><th className="num">In the workbook</th><th className="num">In the new model</th><th>Added</th><th>Changed</th></tr></thead>
            <tbody>{SECTIONS.map(([k, label]) => (
              <tr key={k}><td>{label}</td><td className="num">{p.workbook[k]}</td><td className="num">{p.counts[k]}</td>
                <td>{(p.added[k] || []).slice(0, 12).join(", ")}{(p.added[k] || []).length > 12 ? ` +${p.added[k].length - 12}` : ""}</td>
                <td>{(p.changed[k] || []).slice(0, 12).join(", ")}{(p.changed[k] || []).length > 12 ? ` +${p.changed[k].length - 12}` : ""}</td></tr>))}
            </tbody>
          </table>
          {p.errors.length > 0 && <div className="status bad"><b>{p.errors.length} error{p.errors.length === 1 ? "" : "s"}: fix the workbook and check it again.</b>
            <ul className="small">{p.errors.slice(0, 30).map((e, i) => <li key={i}>{e.where}: {e.message}</li>)}</ul></div>}
          {p.warnings.length > 0 && <details><summary className="status warn">{p.warnings.length} warnings</summary>
            <ul className="small">{p.warnings.map((e, i) => <li key={i}>{e.where}: {e.message}</li>)}</ul></details>}
          {!p.errors.length && <Field label="Name of the new model"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="For example Reinsurance programme" /></Field>}
          {!p.errors.length && <p className="quiet small">A project model{p.base ? ` built on ${p.base.name}` : " on Root"}; you become its Model Admin.</p>}
        </div>
      )}
      {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}
