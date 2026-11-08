// Data quality where people edit (D245, D246): an entity's score as a badge, each field's reasons (missing, a rule
// broken, not applicable), marking a field not applicable on one entity (a Model Admin approves), a Model Admin leaving
// a field out for the whole model, each entity type's score, and Recalculate (a measurement in the background).
// Kept apart from Quality.jsx so the model screens can use it without loading the whole Quality tab.
import { useEffect, useState } from "react";
import { apiFetch } from "./auth";
import { runTask } from "./tasks";

const BANDS = { green: 80, amber: 60 };
export const qTone = (v, b = BANDS) => (v == null ? "" : Number(v) >= b.green ? "good" : Number(v) >= b.amber ? "fair" : "poor");
export const q2 = (v) => (v == null ? "-" : `${Number(v).toFixed(2)}%`);
// every screen reads again: ModelViews forgets its cached answers on eax-clear-cache and sends eax-refresh
const refresh = () => window.dispatchEvent(new Event("eax-clear-cache"));

// read again on every change anywhere (refreshAll in ModelViews sends eax-refresh)
function useLive(path) {
  const [state, setState] = useState({ data: null, error: null });
  const [gen, setGen] = useState(0);
  useEffect(() => {
    const on = () => setGen((g) => g + 1);
    window.addEventListener("eax-refresh", on);
    return () => window.removeEventListener("eax-refresh", on);
  }, []);
  useEffect(() => {
    if (!path) return undefined;
    let live = true;
    apiFetch(path).then((data) => live && setState({ data, error: null })).catch((e) => live && setState({ data: null, error: e.message }));
    return () => { live = false; };
  }, [path, gen]);
  return { ...state, reload: () => setGen((g) => g + 1) };
}

// ---------------------------------------------------------------- one entity
export function useEntityQuality(model, entity) {
  return useLive(model && entity ? `/api/v1/models/${model}/entities/${entity}/quality` : null);
}

export function QualityBadge({ q, label = "Data quality" }) {
  if (!q) return null;
  const b = q.bands || BANDS;
  const p = q.parts || {};
  const title = `${label}: ${q2(q.score)} = completeness ${q2(q.completeness)} × ${p.completeness}% + rules ${q.failing ? "failing" : "passed"} × ${p.rules}% + ${q.stale ? "stale" : "fresh"} × ${p.freshness}%`;
  return (
    <span className={`q-badge ${qTone(q.score, b)}`} title={title}>
      {label} <b>{Math.round(q.score)}%</b>
      <span className="q-badge-sub"> · complete {Math.round(q.completeness)}%{q.failing ? ` · ${q.failing} rule${q.failing === 1 ? "" : "s"} failing` : ""}{q.stale ? " · stale" : ""}</span>
    </span>
  );
}

// the whole-entity reasons (stale, seal, relationship rules) under the badge
export function EntityReasons({ q }) {
  const list = q?.fields?.["*"] || [];
  if (!list.length) return null;
  return <ul className="q-reasons small">{list.map((r, i) => <li key={i} className={`q-r ${r.kind}`}>{r.message}</li>)}</ul>;
}

// the class a field's row or cell gets: failing (missing or a rule), not applicable, or waiting
export function fieldClass(q, code) {
  const list = q?.fields?.[code] || [];
  if (list.some((r) => r.kind === "rule" && r.severity === "error")) return "q-field-error";
  if (list.some((r) => r.kind === "missing" || r.kind === "rule")) return "q-field-bad";
  if (list.some((r) => r.kind === "not-applicable-pending")) return "q-field-wait";
  if (list.some((r) => r.kind === "not-applicable")) return "q-field-na";
  return "";
}

async function ask(path, body) {
  return apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });
}

// a field's reasons and what can be done about them
export function FieldQuality({ model, entity, code, q, typeCode, mayEdit, compact }) {
  const [msg, setMsg] = useState("");
  const list = q?.fields?.[code] || [];
  if (!list.length) return null;
  const admin = !!q?.may_approve;
  const item = code === "description" ? "field:description" : `attr:${code}`;
  async function act(fn) {
    setMsg("");
    try { const r = await fn(); if (r?.message || r?.summary) setMsg(r.message || r.summary); refresh(); } catch (e) { setMsg(e.message); }
  }
  function notApplicable() {
    // eslint-disable-next-line no-alert
    const reason = window.prompt(`Why does ${code} not apply to this entity? ${admin ? "" : "A Model Admin approves it."}`, "");
    if (!reason) return;
    act(() => ask(`/api/v1/models/${model}/quality/not-applicable`, { entity, item, reason }));
  }
  function leaveOut() {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Leave ${code} out of data quality for every entity of this model (every type that has it)? It applies at once; the Super Admins are told.`)) return;
    act(() => ask(`/api/v1/models/${model}/quality/leave-out`, { item, entity_type: "*" }));
  }
  const decide = (r, d) => act(() => ask(`/api/v1/models/${model}/quality/not-applicable/${r.id}/${d}`, {}));
  const missing = list.some((r) => r.kind === "missing") && !list.some((r) => r.kind === "not-applicable-rejected");
  return (
    <span className={`q-field-reasons${compact ? " compact" : ""}`}>
      {list.map((r, i) => (
        <span key={i} className={`q-r ${r.kind}${r.severity === "error" ? " error" : ""}`} title={r.by ? `${r.message} (${r.by})` : r.message}>
          {r.message}
          {r.kind === "not-applicable-pending" && admin && <> <button className="linkish" onClick={() => decide(r, "approve")}>Approve</button> · <button className="linkish" onClick={() => decide(r, "reject")}>Reject</button></>}
          {(r.kind === "not-applicable" || r.kind === "not-applicable-pending") && !compact && <> · <button className="linkish" onClick={() => decide(r, "withdraw")}>Undo</button></>}
          {r.kind === "not-applicable-rejected" && !compact && (mayEdit || admin) && <> · <button className="linkish" onClick={notApplicable} title="Ask again, with a better reason">Ask again</button></>}
        </span>
      ))}
      {missing && !compact && (mayEdit || admin) && <span className="q-actions small">
        <button className="linkish" onClick={notApplicable} title="It does not apply to this entity: leave it out of its completeness (a Model Admin approves)">Not applicable here</button>
        {admin && <> · <button className="linkish" onClick={leaveOut} title={`Leave it out of data quality for the whole model${typeCode ? "" : ""}`}>Leave out for this model</button></>}
      </span>}
      {msg && <span className="small status warn"> {msg}</span>}
    </span>
  );
}

// ---------------------------------------------------------------- entity types
export function useTypeQuality(model, type) {
  return useLive(model && type ? `/api/v1/models/${model}/quality/types/${encodeURIComponent(type)}` : null);
}

export function useTypeScores(model) {
  return useLive(model ? `/api/v1/models/${model}/quality/types` : null);
}

export function ScoreChip({ score, bands, title }) {
  if (score == null) return <span className="quiet small">-</span>;
  return <span className={`q-chip ${qTone(score, bands)}`} title={title || `Data quality ${q2(score)}`}>{Math.round(score)}%</span>;
}

// ---------------------------------------------------------------- Recalculate: a measurement in the background (D245)
export function useQualityJobs(model) {
  const { data, reload } = useLive(model ? `/api/v1/models/${model}/quality/jobs` : null);
  const active = (data?.jobs || []).find((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!active) return undefined;
    const t = setInterval(reload, 2500);
    return () => clearInterval(t);
  }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return { jobs: data?.jobs || [], active, reload };
}

export function RecalculateButton({ model, label = "Recalculate quality", className = "" }) {
  const { jobs, active, reload } = useQualityJobs(model);
  const [msg, setMsg] = useState("");
  const [was, setWas] = useState(null);   // the measurement asked for here (or seen running), until it has finished
  useEffect(() => { if (active && !was) setWas(active.id); }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {      // it finished (however fast): every screen reads again, the charts with them
    if (!was) return;
    const j = jobs.find((x) => x.id === was);
    if (j && (j.status === "done" || j.status === "failed")) { setWas(null); refresh(); }
  }, [jobs, was]);
  async function go() {
    setMsg("");
    try { const r = await ask(`/api/v1/models/${model}/quality/run`); setWas(r.id); reload(); } catch (e) { setMsg(e.message); }
  }
  const last = jobs.find((j) => j.status === "done" || j.status === "failed");
  return (
    <span className={`q-recalc ${className}`}>
      <button onClick={go} disabled={!!active} title="Measure this model's data quality again in the background and keep it; you are told when it is done">
        {active ? (active.status === "running" ? "Measuring..." : "Queued...") : label}</button>
      {active && <span className="small quiet"> <span className="spinner" aria-hidden="true" /> in the background; you can carry on</span>}
      {!active && last && <span className="small quiet" title={last.error || ""}> {last.status === "failed" ? `last failed: ${last.error}` : `last ${q2(last.score)}`}</span>}
      {msg && <span className="small status bad"> {msg}</span>}
    </span>
  );
}

// ---------------------------------------------------------------- recheck from the grids and tables
// ↻ on a row: that entity rechecked at once and stored (a single entity is checked at once, D248)
export function RecheckRow({ model, entity }) {
  const [busy, setBusy] = useState(false);
  async function go(ev) {
    ev.stopPropagation();
    setBusy(true);
    try { await ask(`/api/v1/models/${model}/entities/${entity}/quality/recheck`); refresh(); } catch { /* the row keeps its last result */ }
    setBusy(false);
  }
  return <button className="linkish q-recheck" onClick={go} onMouseDown={(ev) => ev.stopPropagation()} disabled={busy}
    title="Recheck this entity's data quality now">{busy ? "…" : "↻"}</button>;
}

// Recheck all: every entity of the type, in the background; the rows read again until it is done
export function RecheckAll({ model, type, label = "Recheck all" }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true); setMsg("");
    try {
      // D273: a background task, followed in the Tasks tab on the right; the rows read again when it is done
      const r = await runTask(ask(`/api/v1/models/${model}/quality/types/${encodeURIComponent(type)}/recheck`), `#/metamodel/${model}/quality`);
      setMsg(`${r.rechecked ?? r.queued ?? ""} rechecked.`.trim());
      refresh(); setBusy(false);
    } catch (e) { setMsg(e.message); setBusy(false); }
  }
  return (
    <span className="q-recalc">
      <button onClick={go} disabled={busy} title="Recheck the data quality of every entity of this type (in the background)">{busy ? "Rechecking..." : label}</button>
      {msg && <span className="small quiet"> {msg}</span>}
    </span>
  );
}

// the Quality cell of a table row: the score as last calculated and ↻
export function QualityCell({ model, entity, row, bands }) {
  const title = [row?.score == null ? "Not calculated yet" : `Data quality ${q2(row.score)}`,
    ...((row?.fields?.["*"] || []).map((x) => x.message))].join("\n");
  return <span className="nowrap"><ScoreChip score={row?.score} bands={bands} title={title} /> <RecheckRow model={model} entity={entity} /></span>;
}
