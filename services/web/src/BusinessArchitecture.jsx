// The Business views tab of a model, also inside a project's Business artifacts tab (owner, 9 Nov 2026, D345, D352): the TOGAF business
// architecture catalogues, matrices and diagrams that can be made from a model, each mapped to the view that
// shows it here and to its reports (its own dashboard and the standard reports that go with it), with how much of it
// the model holds and what is missing (no elements yet, or types the metamodel lacks). Only what comes from the model:
// the Business Model Canvas is a project's own (its own tab, D344).
import { useState } from "react";
import { useApi } from "./ModelViews";
import { fmtDateTime } from "./fmt";

const GROUPS = [["catalog", "Catalogues"], ["matrix", "Matrices"], ["diagram", "Diagrams and maps"]];
const spaced = (c) => c.replace(/([a-z])([A-Z])/g, "$1 $2");

function Status({ v }) {
  if (v.entities > 0) return <span className="ba-st ok">✓ {v.entities} element{v.entities === 1 ? "" : "s"}</span>;
  if ((v.types_defined || []).length) return <span className="ba-st empty" title={`Add: ${v.types_defined.map(spaced).join(", ")}`}>no elements yet</span>;
  return <span className="ba-st missing" title={`Types this model's metamodel lacks: ${v.element_types.map(spaced).join(", ")}`}>the metamodel lacks its types</span>;
}

function Reports({ v, rep }) {
  if (!rep) return <span className="quiet small">…</span>;
  const byCode = Object.fromEntries((rep.reports || []).map((r) => [r.code, r]));
  const codes = [v.code, ...((rep.view_reports || {})[v.code] || [])].filter((c) => byCode[c]);
  if (!codes.length) return <span className="quiet small">–</span>;
  return (
    <div className="ba-reports">
      {codes.map((c) => (
        <a key={c} href={byCode[c].url} target="_blank" rel="noreferrer" className="small"
          title={c === v.code ? "This view as a dashboard in the reporting tool" : byCode[c].title}>
          {c === v.code ? "Dashboard" : `${c} ${byCode[c].title}`} ↗</a>
      ))}
    </div>
  );
}

export function BusinessArtifacts({ model }) {
  const { data, error } = useApi(model ? `/api/v1/models/${model}/views` : null);
  const { data: rep } = useApi(model ? `/api/v1/models/${model}/reports` : null);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading…</p>;
  const vps = (data.views || data).filter((v) => v.togaf_artifact);
  const group = (v) => (v.default_view === "catalog" ? "catalog" : v.default_view === "matrix" ? "matrix" : "diagram");
  const n = { ok: vps.filter((v) => v.entities > 0).length, empty: vps.filter((v) => !v.entities && (v.types_defined || []).length).length };
  return (
    <div className="ba-tab">
      <p className="quiet small">The TOGAF business architecture catalogues, matrices and diagrams that can be made from this model, each with the
        view that shows it and its reports.
        <b> {n.ok}</b> of {vps.length} have content here; {n.empty} have their types but no elements yet
        {vps.length - n.ok - n.empty ? `; ${vps.length - n.ok - n.empty} need types this model's metamodel lacks` : ""}.</p>
      {GROUPS.map(([g, label]) => (
        <section key={g} className="ba-group">
          <h4>{label}</h4>
          <table className="grid-table ba-table">
            <thead><tr><th>Artifact</th><th>View</th><th>Reports</th><th>Shows</th><th>In this model</th></tr></thead>
            <tbody>
              {vps.filter((v) => group(v) === g).map((v) => (
                <tr key={v.code}>
                  <td><b>{v.togaf_artifact}</b><div className="small quiet">{v.concerns}</div></td>
                  <td className="nowrap"><a href={`#/metamodel/${model}/views/${encodeURIComponent(v.code)}/${v.default_view || "diagram"}`}>
                    {v.code}{v.name !== v.togaf_artifact ? ` ${v.name}` : ""}</a></td>
                  <td><Reports v={v} rep={rep} /></td>
                  <td className="small quiet">{v.element_types.filter((t) => (v.types_defined || []).includes(t)).map(spaced).join(", ") || v.element_types.map(spaced).join(", ")}</td>
                  <td><Status v={v} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}

// the model page's tab
export function ModelBusinessArtifacts({ model }) {
  return <BusinessArtifacts model={model} />;
}

// the project page's Business artifacts tab (owner, 9 Nov 2026): everything business architecture in the project in one
// place: its Business Model Canvases (kept in the project, D344), its Phase B deliverables and artifacts with their
// documents, and the business views of each of its models (with their reports)
export function ProjectBusinessArtifacts({ p }) {
  const models = [...p.models].sort((a, b) => (b.home ? 1 : 0) - (a.home ? 1 : 0) || a.name.localeCompare(b.name));
  const [model, setModel] = useState(models[0]?.id || "");
  const { data: cv } = useApi(`/api/v1/projects/${p.id}/canvases`);
  const phaseB = (p.items || []).filter((i) => i.phase === "B" && i.chosen);
  const docs = (i) => (p.documents || []).filter((d) => d.item_id === i.id);
  return (
    <div className="ba-project">
      <section className="ba-box">
        <h4>Business Model Canvases <span className="small quiet">(the project's own, not from a model)</span></h4>
        {!cv ? <p className="quiet small">Loading…</p> : !cv.canvases.length ? <p className="small quiet">None yet.</p> : (
          <table className="grid-table"><thead><tr><th>Canvas</th><th>Kind</th><th>Status</th><th>Items</th><th>Changed by</th></tr></thead>
            <tbody>{cv.canvases.map((c) => <tr key={c.id}><td><a href={`#/projects/${p.id}/canvas?c=${c.id}`}><b>{c.name}</b></a></td>
              <td className="small">{c.kind}</td><td className="small">{c.status}</td><td className="small">{c.items}{c.marks ? ` (${c.marks} marked)` : ""}</td><td className="small quiet">{c.changed_by || c.created_by} · {fmtDateTime(c.changed_at || c.created_at)}</td></tr>)}</tbody></table>
        )}
        <p className="small"><a href={`#/projects/${p.id}/canvas`}>Open the Business model canvas tab</a></p>
      </section>
      <section className="ba-box">
        <h4>Phase B deliverables and artifacts</h4>
        {!phaseB.length ? <p className="small quiet">None chosen for Phase B.</p> : (
          <table className="grid-table"><thead><tr><th>Deliverable or artifact</th><th>Kind</th><th>Documents</th></tr></thead>
            <tbody>{phaseB.map((i) => <tr key={i.id}><td>{i.name}</td><td className="small">{i.kind}</td>
              <td className="small">{docs(i).length ? docs(i).map((d) => d.title || d.file_name).join(", ") : <span className="quiet">none yet</span>}</td></tr>)}</tbody></table>
        )}
        <p className="small"><a href={`#/projects/${p.id}/phases`}>Open the phases</a></p>
      </section>
      <section className="ba-box">
        <h4>Business views of the project's models</h4>
        {!models.length ? <p className="quiet small">The project has no model yet.</p> : <>
          <label className="small">In the model <select value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model">
            {models.map((m) => <option key={m.id} value={m.id}>{m.name}{m.home ? " (primary working model)" : ""}</option>)}</select></label>
          <BusinessArtifacts key={model} model={model} />
        </>}
      </section>
    </div>
  );
}
