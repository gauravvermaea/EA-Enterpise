// Scenario planning (phase 27.1, D364, D490 to D495): a project's Scenarios tab. The baseline (the Current state model)
// and each scenario model (role Scenario, and Target state) side by side: figures (annual cost, applications,
// capabilities covered, end-of-life technology, risks), the difference from the baseline, what each adds, changes and
// retires, the capabilities it touches, a suggested score; and the assessments recorded (SCN-001...) with their Word
// document and governance decision. Scenario models, what-ifs and assessments are made through MCP (the prompt
// plan_scenarios); figures include the viewer's own uncommitted changes (their what-ifs).
import { useState } from "react";
import { apiDownload } from "./auth";
import { fmtDateTime } from "./fmt";
import { useApi } from "./ModelViews";

const money = (v) => (v == null ? "" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }));
const FIG = [
  ["total_cost", "Annual cost", money, true],
  ["applications", "Applications", String, true],
  ["capabilities_covered", "Capabilities covered", String, false],
  ["technology_past_end_of_life", "Technology past end of life", String, true],
  ["technology_end_of_life_within_12_months", "End of life within 12 months", String, true],
  ["applications_to_eliminate", "Applications to eliminate", String, true],
  ["risks", "Risks", String, true],
];

function Delta({ v, lowerIsBetter, fmt = String }) {
  if (v == null || v === 0) return <span className="quiet small">same</span>;
  const good = lowerIsBetter ? v < 0 : v > 0;
  return <span className={`small scen-delta ${good ? "good" : "bad"}`}>{v > 0 ? "+" : "−"}{fmt(Math.abs(v))}</span>;
}

function Names({ label, list }) {
  if (!list || !list.length) return null;
  return (
    <details className="scen-names">
      <summary>{label} ({list.length})</summary>
      <ul className="small">{list.map((x, i) => <li key={i}>{x.name} <span className="quiet">{x.type}</span>
        {x.changes && x.changes.length ? <span className="quiet"> · {x.changes.slice(0, 4).join(", ")}</span> : null}</li>)}</ul>
    </details>
  );
}

export default function ScenariosTab({ p }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/scenarios`);
  const [msg, setMsg] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet"><span className="spinner" aria-hidden="true" /> Comparing the scenarios with the baseline…</p>;
  const base = data.baseline;
  const scen = data.scenarios || [];
  async function docx(a) {
    setMsg("");
    try { await apiDownload(`/api/v1/projects/${p.id}/scenario-assessments/${a.id}/docx`, `${a.ref} ${a.title}.docx`); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <div className="scenarios-tab">
      <p className="quiet small">
        Each scenario model compared with the baseline. Figures include <b>your own uncommitted changes</b> (your what-ifs),
        so they can differ from what others see. Make scenarios, try what-ifs and record an assessment with your AI assistant
        through MCP: the prompt <code>plan_scenarios</code>.
      </p>
      {data.message && <p className="status">{data.message}</p>}
      {base && (
        <div className="scen-table-wrap">
          <table className="grid-table scen-table">
            <thead>
              <tr><th scope="col">Figure</th>
                <th scope="col"><a href={`#/metamodel/${base.id}`}>{base.name}</a><div className="quiet small">baseline{base.figures.with_my_changes ? " · with your changes" : ""}</div></th>
                {scen.map((s) => <th scope="col" key={s.id}><a href={`#/metamodel/${s.id}`}>{s.name}</a>
                  <div className="quiet small">{s.role === "target" ? "target state" : "scenario"}{s.figures?.with_my_changes ? " · with your what-ifs" : ""}</div></th>)}
              </tr>
            </thead>
            <tbody>
              {FIG.map(([k, label, fmt, lower]) => (
                <tr key={k}><th scope="row">{label}</th>
                  <td>{k === "capabilities_covered" ? `${base.figures[k]} of ${base.figures.capabilities}` : fmt(base.figures[k])}</td>
                  {scen.map((s) => <td key={s.id}>{s.error ? <span className="status bad small">{s.error}</span> : <>
                    {k === "capabilities_covered" ? `${s.figures[k]} of ${s.figures.capabilities}` : fmt(s.figures[k])}{" "}
                    <Delta v={s.difference?.[k]} lowerIsBetter={lower} fmt={fmt} /></>}</td>)}
                </tr>))}
              <tr><th scope="row">Against the baseline</th><td className="quiet small">—</td>
                {scen.map((s) => <td key={s.id} className="small">{s.comparison && <>
                  <b>{s.comparison.totals.added}</b> added · <b>{s.comparison.totals.changed}</b> changed · <b>{s.comparison.totals.retired}</b> retired</>}</td>)}</tr>
              <tr><th scope="row">Suggested score</th><td className="quiet small">5 (the baseline)</td>
                {scen.map((s) => <td key={s.id}>{s.suggested && <><span className="scen-score">{s.suggested.score}</span>
                  <div className="quiet small">{s.suggested.reasons.join("; ")}</div></>}</td>)}</tr>
            </tbody>
          </table>
        </div>
      )}
      {scen.filter((s) => s.comparison).map((s) => (
        <section key={s.id} className="scen-card">
          <h3>{s.name}</h3>
          <p className="small">{s.comparison.totals.added} added, {s.comparison.totals.changed} changed, {s.comparison.totals.retired} retired;
            relationships {s.comparison.relationships.added} added, {s.comparison.relationships.retired} retired.
            {" "}{s.comparison.capabilities_touched_count ? <>Capabilities touched: <b>{s.comparison.capabilities_touched_count}</b>.</> : "No capability touched."}</p>
          {s.comparison.by_type.length > 0 && (
            <table className="grid-table small"><thead><tr><th scope="col">Entity type</th><th scope="col">Added</th><th scope="col">Changed</th><th scope="col">Retired</th></tr></thead>
              <tbody>{s.comparison.by_type.map((t) => <tr key={t.entity_type}><td>{t.entity_type} <span className="quiet small">{t.domain}</span></td>
                <td>{t.new || ""}</td><td>{t.changed || ""}</td><td>{t.retired || ""}</td></tr>)}</tbody></table>)}
          <Names label="Added" list={s.comparison.added} />
          <Names label="Retired" list={s.comparison.retired} />
          <Names label="Changed" list={s.comparison.changed} />
          {s.comparison.capabilities_touched.length > 0 && <Names label="Capabilities touched (impact)" list={s.comparison.capabilities_touched.map((n) => ({ name: n, type: "" }))} />}
        </section>
      ))}
      <h3>Assessments</h3>
      {msg && <p className="status bad">{msg}</p>}
      {!(data.assessments || []).length ? <p className="quiet">No assessment recorded yet.</p> : (
        <table className="grid-table">
          <thead><tr><th scope="col">Ref</th><th scope="col">Assessment</th><th scope="col">Scores</th><th scope="col">Recommended</th>
            <th scope="col">Decision</th><th scope="col">By</th><th scope="col"><span className="sr-only">Document</span></th></tr></thead>
          <tbody>{data.assessments.map((a) => (
            <tr key={a.id}>
              <td className="nowrap">{a.ref}</td>
              <td><b>{a.title}</b><div className="quiet small">baseline {a.baseline}</div>
                {a.recommendation && <details className="small"><summary>Recommendation</summary>{a.recommendation.split(/\n\s*\n/).map((x, i) => <p key={i}>{x}</p>)}</details>}</td>
              <td className="small">{a.scenarios.map((s) => <div key={s.model}>{s.name}: <b>{s.score ?? "–"}</b>{s.notes ? <span className="quiet"> · {s.notes}</span> : null}</div>)}</td>
              <td>{a.recommended || <span className="quiet">—</span>}</td>
              <td className="small">{a.decision ? <a href={`#/projects/${p.id}/governance?kind=Decision`}>{a.decision.ref}</a> : <span className="quiet">none</span>}
                {a.decision && <div className="quiet">{a.decision.approval}</div>}</td>
              <td className="small">{a.created_by}<div className="quiet">{fmtDateTime(a.created_at)}{a.via === "mcp" ? " · through MCP" : ""}</div></td>
              <td><button className="small" onClick={() => docx(a)} title={a.document_name ? `Also filed in the repository: ${a.document_name}` : "Download as a Word document"}>Word</button></td>
            </tr>))}</tbody>
        </table>)}
    </div>
  );
}
