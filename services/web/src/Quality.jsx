// Validation and data quality (build phase 12, D239). The model's Quality tab: the score and its parts as simple metric
// charts, each drilling down (a number or a bar opens the entities behind it, an entity opens its page) with actions
// (mark still current, attest, open in the reporting tool); the trend; and, for Model Admins, the stale period, the
// weights and the rules (a Model Admin's change waits for a Super Admin's approval). Administration > Quality shows every
// model side by side and the changes waiting for approval.
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { apiDownload, apiFetch, currentUser, roles } from "./auth";
import { fmtDateTime } from "./fmt";
import { Modal } from "./ModelOps";
import { KindMark, KINDS as MODEL_KINDS, MODEL_STATES, ModelStateBadge } from "./ModelMarks";
import { ModelIcon } from "./ModelIcon";
import { refreshAll, useApi } from "./ModelViews";
import { RecalculateButton } from "./QualityBits";

const KINDS = { incomplete: "Incomplete", failing: "Failing a rule", errors: "Failing an error rule", stale: "Stale",
  orphan: "Orphans", "seal-broken": "Seal broken", "seal-expired": "Seal expired", sealed: "Sealed", mine: "Yours to fix" };
const pct = (v) => (v == null ? "-" : `${Math.round(Number(v))}%`);
const exact = (v) => (v == null ? "not measured yet" : `${Number(v).toFixed(2)}%`);   // the actual value, on hover
// the colour thresholds (D244): the model's own, inherited, else the installation's (set by Super Admins); green from,
// amber from, red below
export const DEFAULT_BANDS = { green: 80, amber: 60 };
export const toneOf = (v, b = DEFAULT_BANDS) => (v == null ? "" : Number(v) >= b.green ? "good" : Number(v) >= b.amber ? "fair" : "poor");
const Bands = createContext(DEFAULT_BANDS);
const useTone = () => { const b = useContext(Bands) || DEFAULT_BANDS; return (v) => toneOf(v, b); };
// how often quality is measured again, in words and as a picker (the schedule is a cron line underneath)
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const parseCron = (c) => {
  const m = /^(\d+) (\d+) (\S+) \* (\S+)$/.exec(String(c || "").trim());
  if (!m) return { every: "custom", hour: 3, day: 0 };
  const hour = Number(m[2]);
  if (m[3] === "*" && m[4] === "*") return { every: "day", hour, day: 0 };
  if (m[3] === "*" && /^\d$/.test(m[4])) return { every: "week", hour, day: Number(m[4]) };
  if (m[3] === "1" && m[4] === "*") return { every: "month", hour, day: 0 };
  return { every: "custom", hour, day: 0 };
};
const toCron = (f) => (f.every === "day" ? `0 ${f.hour} * * *` : f.every === "week" ? `0 ${f.hour} * * ${f.day}` : `0 ${f.hour} 1 * *`);
export const cronText = (c) => {
  const f = parseCron(c); const at = `${String(f.hour).padStart(2, "0")}:00`;
  return f.every === "day" ? `every day at ${at}` : f.every === "week" ? `every ${DAYS[f.day]} at ${at}` : f.every === "month" ? `on the 1st of every month at ${at}` : `on the schedule ${c}`;
};
export function Frequency({ cron, onChange, disabled, allowInherit, inherited }) {
  const [custom, setCustom] = useState(cron && parseCron(cron).every === "custom");
  const f = cron ? parseCron(cron) : { every: "", hour: 3, day: 0 };
  const set = (x) => onChange(toCron({ ...f, every: f.every && f.every !== "custom" ? f.every : "week", ...x }));
  if (custom) {
    return <span className="small">cron <input value={cron || ""} disabled={disabled} onChange={(e) => onChange(e.target.value)} style={{ width: 120 }} />{" "}
      {!disabled && <button className="linkish" onClick={() => { setCustom(false); onChange(toCron({ every: "week", hour: 3, day: 0 })); }}>simple</button>}</span>;
  }
  return (
    <span className="small q-freq">
      <select value={f.every} disabled={disabled} onChange={(e) => (e.target.value === "" ? onChange(null) : e.target.value === "custom" ? setCustom(true) : set({ every: e.target.value }))}>
        {allowInherit && <option value="">as inherited ({inherited ? cronText(inherited) : "-"})</option>}
        <option value="day">every day</option><option value="week">every week</option><option value="month">every month (the 1st)</option>
        {!disabled && <option value="custom">custom (cron)...</option>}
      </select>
      {f.every === "week" && <> on <select value={f.day} disabled={disabled} onChange={(e) => set({ day: Number(e.target.value) })}>{DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></>}
      {f.every && <> at <select value={f.hour} disabled={disabled} onChange={(e) => set({ hour: Number(e.target.value) })}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}</select></>}
    </span>
  );
}
const partsText = (p) => (p ? `${p.completeness}% completeness, ${p.rules}% the entities failing no rule, ${p.freshness}% the entities not stale` : "");
const me = () => (currentUser().preferred_username || "").toLowerCase();
const go = (h) => { window.location.hash = h; };

// ---------------------------------------------------------------- simple charts (SVG, no library)
export function ScoreRing({ value, size = 132, label = "Quality score" }) {
  const tone = useTone();
  const r = size / 2 - 10;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <svg className={`q-ring ${tone(value)}`} width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${exact(value)}`}>
      <title>{`${label}: ${exact(value)}`}</title>
      <circle cx={size / 2} cy={size / 2} r={r} className="q-ring-bg" />
      {value != null && <circle cx={size / 2} cy={size / 2} r={r} className="q-ring-fg" strokeDasharray={`${(c * v) / 100} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`} />}
      <text x="50%" y="48%" textAnchor="middle" className="q-ring-num">{value == null ? "-" : Math.round(v)}</text>
      <text x="50%" y="66%" textAnchor="middle" className="q-ring-lab">{label}</text>
    </svg>
  );
}

function Bars({ rows, value, sub, onPick, max = 100, suffix = "%", empty = "Nothing to show." }) {
  const tone = useTone();
  if (!rows.length) return <p className="quiet small">{empty}</p>;
  return (
    <div className="q-bars">
      {rows.map((r) => {
        const v = Number(r[value]) || 0;
        return (
          <button key={r.name} className="q-bar" onClick={() => onPick && onPick(r)} title={`${r.name}: ${suffix === "%" ? exact(v) : v}${sub ? ` · ${sub(r)}` : ""}. Click to see the entities.`}>
            <span className="q-bar-name">{r.name}</span>
            <span className="q-bar-track"><span className={`q-bar-fill ${suffix === "%" ? tone(v) : "count"}`} style={{ width: `${Math.max(2, (100 * v) / (max || 1))}%` }} /></span>
            <span className="q-bar-val">{suffix === "%" ? pct(v) : v}</span>
            {sub && <span className="q-bar-sub quiet">{sub(r)}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function Trend({ points, height = 120, small }) {
  const pts = (points || []).filter((p) => p.score != null);
  if (pts.length < 2) return <p className="quiet small">{pts.length ? "One measurement so far: the trend shows from the second." : "No measurement kept yet."}</p>;
  const w = small ? 140 : 640;
  const h = small ? 32 : height;
  const lo = Math.max(0, Math.min(...pts.map((p) => Number(p.score))) - 5);
  const hi = Math.min(100, Math.max(...pts.map((p) => Number(p.score))) + 5);
  const x = (i) => (small ? 2 : 34) + (i * (w - (small ? 4 : 44))) / (pts.length - 1);
  const y = (v) => (small ? 2 : 8) + ((hi - v) * (h - (small ? 4 : 28))) / (hi - lo || 1);
  const line = pts.map((p, i) => `${x(i)},${y(Number(p.score))}`).join(" ");
  return (
    <svg className={small ? "q-spark" : "q-trend"} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Quality score over time">
      {!small && [lo, (lo + hi) / 2, hi].map((v) => <g key={v}><line x1="30" x2={w} y1={y(v)} y2={y(v)} className="q-grid" /><text x="0" y={y(v) + 4} className="q-axis">{Math.round(v)}</text></g>)}
      <polyline points={line} className="q-line" />
      {!small && pts.map((p, i) => <circle key={i} cx={x(i)} cy={y(Number(p.score))} r="3" className="q-dot"><title>{`${fmtDateTime(p.at)}: ${p.score}`}</title></circle>)}
      {!small && <text x={x(0)} y={h - 2} className="q-axis">{fmtDateTime(pts[0].at).slice(0, 10)}</text>}
      {!small && <text x={w} y={h - 2} textAnchor="end" className="q-axis">{fmtDateTime(pts[pts.length - 1].at).slice(0, 10)}</text>}
    </svg>
  );
}

function Tile({ label, value, sub, onClick, bad }) {
  return (
    <button className={`q-tile${bad ? " bad" : ""}`} onClick={onClick} disabled={!onClick} title={onClick ? "Click to see the entities" : undefined}>
      <span className="q-tile-num">{value}</span><span className="q-tile-label">{label}</span>{sub && <span className="q-tile-sub quiet">{sub}</span>}
    </button>
  );
}

// ---------------------------------------------------------------- the model's Quality tab
export default function QualityTab({ model, m, drill, value }) {
  const { data, error } = useApi(`/api/v1/models/${model}/quality`);
  const reports = useApi(`/api/v1/models/${model}/reports`);
  const [msg, setMsg] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p><span className="spinner" aria-hidden="true" /> Loading the quality of {m.name}...</p>;
  if (!data.has_measurement) {
    return (
      <div className="quality">
        <p>{m.name} has not been measured yet. Measuring runs in the background: you can carry on and are told when it is done.</p>
        <RecalculateButton model={model} label="Measure now" />
        <NotApplicableList model={model} data={data} />
        <QualitySettings model={model} data={data} />
      </div>
    );
  }
  const s = data.summary;
  const base = `#/metamodel/${model}/quality`;
  const qr = (reports.data?.reports || []).filter((r) => r.family === "Data quality");
  if (drill) return <Bands.Provider value={data.bands || DEFAULT_BANDS}><Drill model={model} data={data} drill={drill} value={decodeURIComponent(value || "")} base={base} reports={qr} /></Bands.Provider>;
  const scopeNote = !data.measured && <p className="status warn small">This model is not measured on the schedule and is left out of the estate
    (an admin chose so on Administration &gt; Quality, or it is frozen or archived); what you see is measured now, only for you.</p>;
  const ruleRows = (s.by_rule || []).map((r) => ({ name: `${r.rule} ${r.name}`, rule: r.rule, entities: r.entities, severity: r.severity }));
  return (
    <Bands.Provider value={data.bands || DEFAULT_BANDS}>
    <div className="quality">
      {scopeNote}
      <div className="q-head">
        <ScoreRing value={s.score} />
        <div className="q-parts">
          <p className="quiet small">The score: {partsText(s.parts)} (older than {s.stale_days} days); green from {(data.bands || DEFAULT_BANDS).green}, amber from {(data.bands || DEFAULT_BANDS).amber}, red below.
            Measured {fmtDateTime(data.measured_at)}{data.run?.by ? ` by ${data.run.by}` : ""} ({data.run?.trigger === "scheduled" ? "on the schedule" : "on demand"}); measured again {cronText(data.settings.cron)} and on demand, in the background.</p>
          <div className="q-tiles">
            <Tile label="Completeness" value={pct(s.completeness)} sub={`${s.incomplete} of ${s.entities} incomplete`} onClick={() => go(`${base}/kind/incomplete`)} />
            <Tile label="Rules passed" value={pct(s.passing)} sub={`${s.failing} failing, ${s.errors} on errors`} onClick={s.failing ? () => go(`${base}/kind/failing`) : null} bad={s.errors > 0} />
            <Tile label="Fresh" value={pct(s.fresh)} sub={`${s.stale} stale`} onClick={s.stale ? () => go(`${base}/kind/stale`) : null} />
            <Tile label="Orphans" value={s.orphans} sub="connected to nothing" onClick={s.orphans ? () => go(`${base}/kind/orphan`) : null} />
            <Tile label="Seals" value={s.seals.valid} sub={`${s.seals.broken} broken, ${s.seals.expired} expired`} onClick={s.seals.broken + s.seals.expired ? () => go(`${base}/kind/seal-broken`) : () => go(`${base}/kind/sealed`)} bad={s.seals.broken > 0} />
            <Tile label="Yours to fix" value={data.entities.filter((e) => e.responsible.includes(me()) && (e.completeness < 100 || e.failing || e.stale)).length} sub="you are responsible" onClick={() => go(`${base}/mine/me`)} />
          </div>
          <div className="row-gap">
            <RecalculateButton model={model} label="Measure now" />
            <a className="button" href={`${base}/all/all`}>All entities</a>
            <button onClick={() => apiDownload(`/api/v1/models/${model}/quality/pdf`, `${m.name} data quality.pdf`).catch((e) => setMsg(e.message))}
              title="Every metric on this page as a PDF">Download PDF</button>
            <button onClick={() => apiDownload(`/api/v1/models/${model}/quality/xlsx`, `${m.name} data quality.xlsx`).catch((e) => setMsg(e.message))}
              title="Every metric as an Excel workbook; type, owner and rule open (+) to their entities and each entity to its findings">Download Excel</button>
            {qr.map((r) => <a key={r.code} className="button" href={r.url} target="_blank" rel="noreferrer" title={r.about}>{r.code} {r.title}</a>)}
            {msg && <span className="small">{msg}</span>}
          </div>
        </div>
      </div>
      <div className="q-grid2">
        <section className="q-card"><h3>Completeness by entity type</h3><p className="quiet small">Weakest first. Click a bar for its entities.</p>
          <Bars rows={data.by_type} value="completeness" sub={(r) => `${r.entities} entities`} onPick={(r) => go(`${base}/type/${encodeURIComponent(r.name)}`)} /></section>
        <section className="q-card"><h3>Completeness by owner</h3><p className="quiet small">The Owner attribute; weakest first. Click a bar for the owner's entities.</p>
          <Bars rows={data.by_owner} value="completeness" sub={(r) => `${r.entities} entities${r.stale ? `, ${r.stale} stale` : ""}`} onPick={(r) => go(`${base}/owner/${encodeURIComponent(r.name)}`)} /></section>
        <section className="q-card"><h3>Failing rules</h3><p className="quiet small">Entities failing each rule (metamodel checks and quality rules). Click for the entities.</p>
          <Bars rows={ruleRows} value="entities" max={Math.max(1, ...ruleRows.map((r) => r.entities))} suffix="" sub={(r) => r.severity}
            onPick={(r) => go(`${base}/rule/${encodeURIComponent(r.rule)}`)} empty="No entity fails a rule." /></section>
        <section className="q-card"><h3>Score over time</h3><Trend points={data.trend} />
          <p className="quiet small">{data.trend.length} measurement{data.trend.length === 1 ? "" : "s"} kept.</p></section>
      </div>
      <NotApplicableList model={model} data={data} />
      <QualitySettings model={model} data={data} />
    </div>
    </Bands.Provider>
  );
}

// ---------------------------------------------------------------- the drill-down: the entities behind a number
function Drill({ model, data, drill, value, base, reports }) {
  const tone = useTone();
  const [picked, setPicked] = useState(new Set());
  const [open, setOpen] = useState("");
  const [msg, setMsg] = useState("");
  const [filter, setFilter] = useState("");
  const byEntity = useMemo(() => {
    const out = {};
    for (const f of data.findings) (out[f.entity] = out[f.entity] || []).push(f);
    return out;
  }, [data.findings]);
  const keep = (e) => {
    const fs = byEntity[e.entity] || [];
    if (drill === "type") return e.type_name === value;
    if (drill === "owner") return (e.owner || "(no owner)") === value;
    if (drill === "rule") return fs.some((f) => f.kind === "rule" && f.rule === value);
    if (drill === "mine") return e.responsible.includes(me()) && (e.completeness < 100 || e.failing || e.stale);
    if (drill === "kind") {
      if (value === "incomplete") return e.completeness < 100;
      if (value === "failing") return e.failing > 0;
      if (value === "errors") return e.errors > 0;
      if (value === "stale") return e.stale;
      if (value === "orphan") return e.orphan;
      if (value === "seal-broken") return e.seal === "broken" || e.seal === "expired";
      if (value === "sealed") return e.seal === "valid";
    }
    return true;
  };
  const rows = data.entities.filter(keep).filter((e) => !filter || `${e.display_id} ${e.name} ${e.owner} ${e.type_name}`.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => a.completeness - b.completeness || b.failing - a.failing);
  const title = drill === "kind" ? KINDS[value] || value : drill === "mine" ? "Yours to fix" : drill === "all" ? "Every entity"
    : drill === "rule" ? `Failing rule ${value}` : `${drill === "type" ? "Entity type" : "Owner"}: ${value}`;
  const admin = data.may_manage;
  async function act(kind) {
    setMsg("");
    try {
      const r = await apiFetch(`/api/v1/models/${model}/quality/${kind === "unseal" ? "unseal" : "seal"}`, { method: "POST",
        body: JSON.stringify({ entities: [...picked], kind }) });
      setMsg(kind === "current" ? `${r.done} marked still current.` : kind === "seal" ? `${r.done} attested correct.` : `${r.removed} seals removed.`);
      setPicked(new Set()); refreshAll();
    } catch (e) { setMsg(e.message); }
  }
  const all = rows.length > 0 && rows.every((e) => picked.has(e.entity));
  return (
    <div className="quality q-drill">
      <p className="crumbs"><a href={base}>Quality</a> › {title} <span className="quiet">({rows.length} entities)</span></p>
      <div className="row-gap filters">
        <input type="search" placeholder="Filter by name, ID, owner or type" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <span className="small">{picked.size} chosen</span>
        {admin && <button disabled={!picked.size} onClick={() => act("current")} title="One click: these are still current (renews their seal and freshness)">Still current</button>}
        <button disabled={!picked.size} onClick={() => act("seal")} title="Attest these are correct (their responsible person or a Model Admin)">Attest correct</button>
        {admin && <button disabled={!picked.size} onClick={() => act("unseal")}>Remove seal</button>}
        <button onClick={() => apiDownload(`/api/v1/models/${model}/quality/pdf?drill=${encodeURIComponent(drill)}&value=${encodeURIComponent(value)}`, `${data.model.name} ${title}.pdf`).catch((e) => setMsg(e.message))}>Download PDF</button>
        <button onClick={() => apiDownload(`/api/v1/models/${model}/quality/xlsx?drill=${encodeURIComponent(drill)}&value=${encodeURIComponent(value)}`, `${data.model.name} ${title}.xlsx`).catch((e) => setMsg(e.message))}>Download Excel</button>
        {reports.map((r) => <a key={r.code} className="button" href={r.url} target="_blank" rel="noreferrer">{r.code} in the reporting tool</a>)}
        {msg && <span className="small">{msg}</span>}
      </div>
      <div className="table-scroll">
        <table className="grid-table q-table">
          <thead><tr>
            <th><input type="checkbox" checked={all} onChange={() => setPicked(all ? new Set() : new Set(rows.map((e) => e.entity)))} aria-label="Choose all" /></th>
            <th>Entity</th><th>Type</th><th>Owner</th><th>Responsible</th><th>Completeness</th><th>Problems</th><th>Seal</th><th />
          </tr></thead>
          <tbody>
            {rows.slice(0, 500).map((e) => {
              const fs = byEntity[e.entity] || [];
              return (
                <tr key={e.entity} className={e.errors ? "q-err" : ""}>
                  <td><input type="checkbox" checked={picked.has(e.entity)} onChange={() => { const n = new Set(picked); if (n.has(e.entity)) n.delete(e.entity); else n.add(e.entity); setPicked(n); }} /></td>
                  <td><a href={`#/metamodel/${model}/entity/${e.entity}`}><b>{e.name}</b></a> <span className="quiet small">{e.display_id}</span></td>
                  <td className="small">{e.type_name}</td>
                  <td className="small">{e.owner || <span className="quiet">-</span>}</td>
                  <td className="small">{e.responsible.join(", ")}</td>
                  <td><span className="q-mini"><span className={`q-bar-fill ${tone(e.completeness)}`} style={{ width: `${e.completeness}%` }} /></span> <span className="small">{pct(e.completeness)}</span></td>
                  <td className="small">
                    {fs.length ? <button className="linkish" onClick={() => setOpen(open === e.entity ? "" : e.entity)}>{fs.length} {open === e.entity ? "▾" : "▸"}</button> : <span className="ok-text">none</span>}
                    {open === e.entity && <ul className="q-findings">{fs.map((f, i) => <li key={i} className={f.severity === "error" ? "bad-text" : ""}>{KINDS[f.kind] || f.kind}{f.rule ? ` ${f.rule}` : ""}: {f.message}</li>)}</ul>}
                  </td>
                  <td className="small">{e.seal === "valid" ? "✓ sealed" : e.seal === "none" ? "" : <span className="bad-text">{e.seal}</span>}</td>
                  <td className="small nowrap"><a href={`#/metamodel/${model}/entity/${e.entity}`}>Fix</a></td>
                </tr>
              );
            })}
            {!rows.length && <tr><td colSpan="9" className="quiet">Nothing here: well done.</td></tr>}
          </tbody>
        </table>
        {rows.length > 500 && <p className="quiet small">The first 500 of {rows.length}; filter to narrow them.</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- settings, weights and rules (Model Admins)
// fields marked not applicable on one entity, waiting for a Model Admin (D246)
function NotApplicableList({ model, data }) {
  const [msg, setMsg] = useState("");
  const [sel, setSel] = useState(new Set());
  const list = data.exemptions || [];
  if (!list.length) return null;
  async function decide(x, d) {
    setMsg("");
    try { await apiFetch(`/api/v1/models/${model}/quality/not-applicable/${x.id}/${d}`, { method: "POST", body: "{}" }); refreshAll(); } catch (e) { setMsg(e.message); }
  }
  async function decideAll(d) {
    // eslint-disable-next-line no-alert
    const note = d === "reject" ? window.prompt(`Reject ${sel.size}: why (each asker is told and can ask again)?`, "") : "";
    if (note === null) return;
    setMsg("");
    try {
      const r = await apiFetch(`/api/v1/models/${model}/quality/not-applicable/decide`, { method: "POST", body: JSON.stringify({ ids: [...sel], decision: d, note }) });
      setMsg(`${r.decided} ${r.status}${r.failed.length ? `; ${r.failed.length} not: ${r.failed.map((f) => f.why).join("; ")}` : ""}.`); setSel(new Set()); refreshAll();
    } catch (e) { setMsg(e.message); }
  }
  const toggle = (id) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  return (
    <section className="q-card">
      <h3>Not applicable, waiting for a Model Admin ({list.length})</h3>
      <p className="quiet small">People asked to leave a field out of one entity's data quality, because it does not apply there. It counts once a Model Admin approves.</p>
      {msg && <p className="status warn small">{msg}</p>}
      {data.may_manage && <div className="row-gap"><button className="primary" disabled={!sel.size} onClick={() => decideAll("approve")}>Approve {sel.size || ""} selected</button>
        <button disabled={!sel.size} onClick={() => decideAll("reject")}>Reject {sel.size || ""} selected</button></div>}
      <table className="grid-table">
        <thead><tr>{data.may_manage && <th><input type="checkbox" aria-label="Choose all" checked={sel.size === list.length} onChange={(e) => setSel(e.target.checked ? new Set(list.map((x) => x.id)) : new Set())} /></th>}
          <th>Entity</th><th>Field</th><th>Why</th><th>Asked by</th><th /></tr></thead>
        <tbody>{list.map((x) => (
          <tr key={x.id}>{data.may_manage && <td><input type="checkbox" checked={sel.has(x.id)} onChange={() => toggle(x.id)} /></td>}<td><a href={`#/metamodel/${model}/entity/${x.entity}`}>{x.display_id} {x.name}</a></td><td>{x.item.split(":")[1]}</td><td>{x.reason}</td>
            <td className="small">{x.requested_by}, {fmtDateTime(x.requested_at)}</td>
            <td className="nowrap">{data.may_manage ? <><button className="primary" onClick={() => decide(x, "approve")}>Approve</button> <button onClick={() => decide(x, "reject")}>Reject</button></>
              : <span className="quiet small">a Model Admin decides</span>}</td></tr>
        ))}</tbody>
      </table>
    </section>
  );
}

function QualitySettings({ model, data }) {
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState(null);
  const [msg, setMsg] = useState("");
  const st = data.settings;
  const admin = data.may_manage;
  const sa = roles().includes("super-admin");
  async function save(path, body, method = "POST") {
    setMsg("");
    try { const r = await apiFetch(`/api/v1/models/${model}/quality/${path}`, { method, body: JSON.stringify(body) }); setMsg(r.message || (r.applied ? `Saved: ${r.summary}` : r.summary)); refreshAll(); return true; } catch (e) { setMsg(e.message); return false; }
  }
  return (
    <section className="q-card q-settings">
      <h3><button className="linkish" onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} Settings, weights and rules</button></h3>
      {!open ? <p className="quiet small">Stale after {st.stale_days} days ({st.stale_from}); score {partsText(st.score_parts)} ({st.score_parts_from});
        green from {st.bands.green}, amber from {st.bands.amber} ({st.bands_from}); {data.rules.length} rule{data.rules.length === 1 ? "" : "s"}
        {data.pending.length ? `; ${data.pending.length} change${data.pending.length === 1 ? "" : "s"} waiting for a Super Admin` : ""}.</p> : <>
        <p className="quiet small">Set on a metamodel and inherited down the hierarchy; a model may change them. {admin && !sa ? "Your changes wait for a Super Admin's approval (you are told)." : ""}</p>
        {msg && <p className="status warn small">{msg}</p>}
        <StaleForm st={st} admin={admin} onSave={(b) => save("settings", b, "PUT")} />
        <h4>Score and colours</h4>
        <ScoreColours admin={admin} parts={st.score_parts} bands={st.bands} own={st.own} from={{ parts: st.score_parts_from, bands: st.bands_from }}
          onSave={(b) => save("settings", b, "PUT")} />
        <h4>Rules</h4>
        <table className="grid-table">
          <thead><tr><th>Code</th><th>Rule</th><th>Kind</th><th>Type</th><th>Severity</th><th>From</th><th /></tr></thead>
          <tbody>
            {data.rules.map((r) => (
              <tr key={r.code} className={r.enabled ? "" : "quiet"}>
                <td className="small">{r.code}</td><td>{r.name}{!r.enabled && " (off)"}</td><td className="small">{r.kind}</td><td className="small">{r.entity_type}</td>
                <td className={r.severity === "error" ? "bad-text small" : "small"}>{r.severity}</td><td className="small">{r.inherited ? r.from : "this model"}</td>
                <td className="small nowrap">{admin && <button className="linkish" onClick={() => setEdit(r)}>{r.inherited ? "Change here" : "Edit"}</button>}
                  {admin && !r.inherited && <>{" · "}<button className="linkish" onClick={() => save(`rules/${r.code}/delete`, {})}>Delete</button></>}</td>
              </tr>
            ))}
            {!data.rules.length && <tr><td colSpan="7" className="quiet">No quality rules yet: only the metamodel's own checks count.</td></tr>}
          </tbody>
        </table>
        {admin && <button onClick={() => setEdit({})}>+ New rule</button>}
        <Weights model={model} data={data} admin={admin} onSave={(w) => save("settings", { weights: w }, "PUT")} />
        {(data.rejected || []).length > 0 && <><h4>Rejected by a Super Admin</h4><ul className="small">{data.rejected.map((r) => <li key={r.id}>{r.summary}
          <span className="quiet"> (rejected by {r.decided_by}, {fmtDateTime(r.decided_at)}{r.decision_note ? `: ${r.decision_note}` : ""})</span>
          {admin && <> <button className="linkish" onClick={() => {
            // eslint-disable-next-line no-alert
            const note = window.prompt("Ask again: a note for the Super Admins (what changed, why it matters)", "");
            if (note !== null) apiFetch(`/api/v1/quality/changes/${r.id}/resubmit`, { method: "POST", body: JSON.stringify({ note }) })
              .then((x) => { setMsg(x.message || x.summary); refreshAll(); }).catch((e) => setMsg(e.message));
          }}>Ask again</button></>}</li>)}</ul></>}
        {data.pending.length > 0 && <><h4>Waiting for a Super Admin</h4><ul className="small">{data.pending.map((p) => <li key={p.id}>{p.summary} <span className="quiet">({p.requested_by}, {fmtDateTime(p.requested_at)})</span></li>)}</ul></>}
      </>}
      {edit && <RuleDialog model={model} data={data} start={edit} onClose={() => setEdit(null)} onSave={async (r) => { if (await save("rules", r)) setEdit(null); }} />}
    </section>
  );
}

function StaleForm({ st, admin, onSave }) {
  const [days, setDays] = useState(st.own.stale_days ?? "");
  const [cron, setCron] = useState(st.own.cron ?? "");
  return (
    <div className="row-gap filters">
      <label className="small">Stale after <input type="number" min="7" max="3650" style={{ width: 80 }} value={days} placeholder={String(st.stale_days)} disabled={!admin} onChange={(e) => setDays(e.target.value)} /> days</label>
      <span className="small">Measured again <Frequency cron={cron || null} disabled={!admin} allowInherit inherited={st.cron} onChange={(c) => setCron(c || "")} /></span>
      <span className="quiet small">empty: inherited ({st.stale_days} days from {st.stale_from}; {cronText(st.cron)} from {st.cron_from})</span>
      {admin && <button onClick={() => onSave({ stale_days: days === "" ? null : Number(days), cron: cron || null })}>Save</button>}
    </div>
  );
}

// the score's weights and the colour thresholds (D244): a model's own (empty: inherited) or, with installation, the
// installation's defaults (Super Admins; nothing to inherit)
const PARTS = [["completeness", "Completeness"], ["rules", "Rules passed"], ["freshness", "Fresh"]];
export function ScoreColours({ admin, parts, bands, own, from, onSave, installation }) {
  const start = (o, eff) => (o ? { ...o } : installation ? { ...eff } : {});
  const [p, setP] = useState(() => start(own?.score_parts, parts));
  const [b, setB] = useState(() => start(own?.bands, bands));
  const ownParts = PARTS.some(([k]) => p[k] !== undefined && p[k] !== "");
  const ownBands = ["green", "amber"].some((k) => b[k] !== undefined && b[k] !== "");
  const num = (v) => (v === "" || v === undefined || v === null ? undefined : Number(v));
  const total = PARTS.reduce((n, [k]) => n + (num(p[k]) ?? parts[k] ?? 0), 0);
  function body() {
    const sp = ownParts ? Object.fromEntries(PARTS.map(([k]) => [k, num(p[k]) ?? parts[k] ?? 0])) : null;
    const bb = ownBands ? { green: num(b.green) ?? bands.green, amber: num(b.amber) ?? bands.amber } : null;
    return { score_parts: sp, bands: bb };
  }
  const g = Number(b.green ?? bands.green); const a = Number(b.amber ?? bands.amber);
  return (
    <div className="q-score-form">
      <div className="row-gap filters">
        <span className="small"><b>Score</b></span>
        {PARTS.map(([k, label]) => <label key={k} className="small">{label} <input type="number" min="0" max="100" style={{ width: 64 }} value={p[k] ?? ""}
          placeholder={String(parts[k])} disabled={!admin} onChange={(e) => setP({ ...p, [k]: e.target.value })} /> %</label>)}
        <span className={`small ${ownParts && total !== 100 ? "bad-text" : "quiet"}`}>{ownParts ? `adds up to ${total}${total !== 100 ? " (must be 100)" : ""}` : `inherited from ${from?.parts || "the installation"}`}</span>
      </div>
      <div className="row-gap filters">
        <span className="small"><b>Colours</b></span>
        <label className="small"><span className="q-swatch good" /> green from <input type="number" min="1" max="100" style={{ width: 64 }} value={b.green ?? ""} placeholder={String(bands.green)} disabled={!admin} onChange={(e) => setB({ ...b, green: e.target.value })} /></label>
        <label className="small"><span className="q-swatch fair" /> amber from <input type="number" min="1" max="99" style={{ width: 64 }} value={b.amber ?? ""} placeholder={String(bands.amber)} disabled={!admin} onChange={(e) => setB({ ...b, amber: e.target.value })} /></label>
        <span className="small"><span className="q-swatch poor" /> red below {a}</span>
        <span className={`small ${ownBands && !(a > 0 && a < g && g <= 100) ? "bad-text" : "quiet"}`}>{ownBands ? (a > 0 && a < g && g <= 100 ? "" : "amber must be below green") : `inherited from ${from?.bands || "the installation"}`}</span>
      </div>
      {admin && <div className="row-gap">
        <button className="primary" disabled={(ownParts && total !== 100) || (ownBands && !(a > 0 && a < g && g <= 100))} onClick={() => onSave(body())}>Save score and colours</button>
        {!installation && (own?.score_parts || own?.bands) && <button onClick={() => { setP({}); setB({}); onSave({ score_parts: null, bands: null }); }}>Inherit again</button>}
      </div>}
    </div>
  );
}

function Weights({ data, admin, onSave }) {
  const types = Object.keys(data.items || {});
  const [type, setType] = useState(types[0] || "");
  const [own, setOwn] = useState(() => JSON.parse(JSON.stringify(data.settings.own.weights || {})));
  if (!types.length) return null;
  const t = data.items[type];
  const set = (item, v) => setOwn((o) => {
    const n = { ...o, [type]: { ...(o[type] || {}) } };
    if (v === "") delete n[type][item]; else n[type][item] = Number(v);
    return n;
  });
  return (
    <>
      <h4>Completeness weights</h4>
      <p className="quiet small">What each item counts for, 0 (left out) to 10. An attribute's weight comes from the metamodel (its default where it is
        defined, or the entity type's override; change it in the Metamodel tab); this model may change it here. Empty: as the metamodel and the parent models say.</p>
      <select value={type} onChange={(e) => setType(e.target.value)}>{types.map((k) => <option key={k} value={k}>{data.items[k].name}</option>)}</select>
      <table className="grid-table q-weights">
        <thead><tr><th>Item</th><th>Metamodel</th><th>Weight now</th><th>This model</th></tr></thead>
        <tbody>{t.items.map((i) => (
          <tr key={i.item}><td className="small">{i.label}</td><td className="small quiet">{i.metamodel}</td>
            <td className="small">{i.weight}{i.from && <span className="quiet"> ({i.from})</span>}</td>
            <td><input type="number" min="0" max="10" style={{ width: 64 }} disabled={!admin} value={own[type]?.[i.item] ?? ""} placeholder="-" onChange={(e) => set(i.item, e.target.value)} /></td></tr>
        ))}</tbody>
      </table>
      {admin && <button onClick={() => onSave(own)}>Save the weights</button>}
    </>
  );
}

const EMPTY = { relationship: { relationship_type: "", direction: "out", other_type: "", min: 1, max: "" },
  attribute: { when: { attribute: "", op: "equals", value: "" }, then: { attribute: "", op: "filled", value: "" } },
  consistency: { when: { attribute: "", op: "equals", value: "" }, via: { relationship_type: "", direction: "any", other_type: "" }, other: { attribute: "Lifecycle", op: "equals", value: "Retired" }, must: "none" },
  naming: { pattern: "", unique: true, scope: "type" } };

function Cond({ c, set, ops, label }) {
  return (
    <div className="row-gap small"><span>{label}</span>
      <input placeholder="Attribute code (or name)" value={c.attribute || ""} onChange={(e) => set({ ...c, attribute: e.target.value })} />
      <select value={c.op || "filled"} onChange={(e) => set({ ...c, op: e.target.value })}>{ops.map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}</select>
      {!["filled", "empty", "before_today", "after_today"].includes(c.op) && <input placeholder="Value (in: a, b, c)" value={c.value || ""} onChange={(e) => set({ ...c, value: e.target.value })} />}
    </div>
  );
}

function RuleDialog({ model, data, start, onClose, onSave }) {
  const [r, setR] = useState(() => ({ code: start.code || "", name: start.name || "", kind: start.kind || "relationship",
    entity_type: start.entity_type || Object.keys(data.items || {})[0] || "", severity: start.severity || "warning",
    enabled: start.enabled !== false, message: start.message || "", spec: start.spec || EMPTY[start.kind || "relationship"] }));
  const [prev, setPrev] = useState(null);
  const [err, setErr] = useState("");
  const set = (k, v) => setR((x) => ({ ...x, [k]: v }));
  const sp = (k, v) => setR((x) => ({ ...x, spec: { ...x.spec, [k]: v } }));
  async function preview() {
    setErr(""); setPrev(null);
    try { setPrev(await apiFetch(`/api/v1/models/${model}/quality/rules/preview`, { method: "POST", body: JSON.stringify(r) })); } catch (e) { setErr(e.message); }
  }
  const types = Object.entries(data.items || {});
  const s = r.spec;
  return (
    <Modal title={start.code ? `Rule ${start.code}` : "New quality rule"} onClose={onClose} wide
      actions={<><button onClick={onClose}>Cancel</button><button onClick={preview}>What would it find?</button><button className="primary" onClick={() => onSave(r)}>Save</button></>}>
      <div className="row-gap">
        <label className="ed-field"><span>Code</span><input value={r.code} onChange={(e) => set("code", e.target.value.toUpperCase())} placeholder="QR-01" style={{ width: 100 }} /></label>
        <label className="ed-field" style={{ flex: 1 }}><span>Name</span><input value={r.name} onChange={(e) => set("name", e.target.value)} placeholder="Every application serves a process" /></label>
      </div>
      <div className="row-gap">
        <label className="ed-field"><span>Kind</span><select value={r.kind} onChange={(e) => setR((x) => ({ ...x, kind: e.target.value, spec: EMPTY[e.target.value] }))}>
          {Object.keys(data.rule_kinds).map((k) => <option key={k} value={k}>{k}</option>)}</select></label>
        <label className="ed-field"><span>Entity type</span><select value={r.entity_type} onChange={(e) => set("entity_type", e.target.value)}>{types.map(([k, t]) => <option key={k} value={k}>{t.name}</option>)}</select></label>
        <label className="ed-field"><span>Severity</span><select value={r.severity} onChange={(e) => set("severity", e.target.value)}><option value="warning">warning (scores, shows, notifies)</option><option value="error">error (blocks the commit)</option></select></label>
        <label className="ed-field radio"><input type="checkbox" checked={r.enabled} onChange={(e) => set("enabled", e.target.checked)} /> <span>On</span></label>
      </div>
      <p className="quiet small">{data.rule_kinds[r.kind]}</p>
      {r.kind === "relationship" && <div className="row-gap small">
        <input placeholder="Relationship type code (empty: any)" value={s.relationship_type || ""} onChange={(e) => sp("relationship_type", e.target.value)} />
        <select value={s.direction || "out"} onChange={(e) => sp("direction", e.target.value)}><option value="out">outgoing</option><option value="in">incoming</option><option value="any">either way</option></select>
        <input placeholder="Other entity type code (empty: any)" value={s.other_type || ""} onChange={(e) => sp("other_type", e.target.value)} />
        at least <input type="number" min="0" style={{ width: 60 }} value={s.min ?? 1} onChange={(e) => sp("min", e.target.value)} />
        at most <input type="number" min="0" style={{ width: 60 }} value={s.max ?? ""} placeholder="-" onChange={(e) => sp("max", e.target.value)} />
      </div>}
      {r.kind === "attribute" && <><Cond label="When (optional)" c={s.when || {}} ops={data.ops} set={(v) => sp("when", v)} /><Cond label="Then" c={s.then || {}} ops={data.ops} set={(v) => sp("then", v)} /></>}
      {r.kind === "consistency" && <>
        <Cond label="When (optional)" c={s.when || {}} ops={data.ops} set={(v) => sp("when", v)} />
        <div className="row-gap small"><span>Related through</span>
          <input placeholder="Relationship type (empty: any)" value={s.via?.relationship_type || ""} onChange={(e) => sp("via", { ...s.via, relationship_type: e.target.value })} />
          <select value={s.via?.direction || "any"} onChange={(e) => sp("via", { ...s.via, direction: e.target.value })}><option value="any">either way</option><option value="out">outgoing</option><option value="in">incoming</option></select>
          <input placeholder="Other type (empty: any)" value={s.via?.other_type || ""} onChange={(e) => sp("via", { ...s.via, other_type: e.target.value })} />
          <select value={s.must || "none"} onChange={(e) => sp("must", e.target.value)}><option value="none">none of them may</option><option value="all">all of them must</option></select></div>
        <Cond label="meet" c={s.other || {}} ops={data.ops} set={(v) => sp("other", v)} />
      </>}
      {r.kind === "naming" && <div className="row-gap small">
        <input placeholder="Pattern (regular expression), e.g. APP-[A-Z].*" value={s.pattern || ""} onChange={(e) => sp("pattern", e.target.value)} />
        <label><input type="checkbox" checked={!!s.unique} onChange={(e) => sp("unique", e.target.checked)} /> unique</label>
        <select value={s.scope || "type"} onChange={(e) => sp("scope", e.target.value)}><option value="type">within its type</option><option value="model">within the model</option></select>
      </div>}
      <label className="ed-field"><span>Message (optional; shown on a failure)</span><input value={r.message} onChange={(e) => set("message", e.target.value)} /></label>
      {err && <p className="status bad">{err}</p>}
      {prev && <div className="status warn small">It checks {prev.checked} entities and {prev.failing} would fail{prev.failing ? ":" : "."}
        {prev.examples.length > 0 && <ul>{prev.examples.slice(0, 8).map((x) => <li key={x.entity}>{x.name}: {x.message}</li>)}</ul>}</div>}
    </Modal>
  );
}

// ---------------------------------------------------------------- Administration > Quality: the estate, every model, approvals
function EstateHead({ estate, every, onPdf, onXlsx }) {
  const e = estate || {};
  const delta = e.month_ago != null && e.score != null ? e.score - e.month_ago : null;
  return (
    <div className="q-head">
      <ScoreRing value={e.score} label="Estate score" />
      <div className="q-parts">
        <p className="quiet small">The overall quality of {every ? "the estate" : "the models you have"}: each model's latest measurement, weighing as many
          entities as it has. {e.measured} of {e.models} models measured, {e.entities} entities.
          {delta != null && <b> {delta >= 0 ? "▲" : "▼"} {Math.abs(Math.round(delta))} since a month ago.</b>}</p>
        <div className="q-tiles">
          <Tile label="Completeness" value={pct(e.completeness)} sub={`${e.incomplete || 0} entities incomplete`} />
          <Tile label="Failing a rule" value={e.failing || 0} sub={`${e.errors || 0} on errors`} bad={e.errors > 0} />
          <Tile label="Stale" value={e.stale || 0} sub="not changed or confirmed" />
          <Tile label="Orphans" value={e.orphans || 0} sub="connected to nothing" />
        </div>
        <div className="row-gap"><button onClick={onPdf}>Download PDF</button><button onClick={onXlsx} title="Every model opens (+) to its entity types">Download Excel</button></div>
        <h4>The estate over time (weekly)</h4>
        <Trend points={e.trend} />
      </div>
    </div>
  );
}

// the installation's defaults (D244): Super Admins set the stale period, schedule, score weights and colours every
// model inherits; a model's own (a Model Admin's waiting for approval) is set on its Quality tab
function Defaults({ d, sa }) {
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState(String(d.stale_days));
  const [cron, setCron] = useState(d.cron);
  const [msg, setMsg] = useState("");
  async function save(body) {
    setMsg("");
    try { const r = await apiFetch("/api/v1/quality/defaults", { method: "PUT", body: JSON.stringify(body) }); setMsg(`Saved: ${r.summary}. Measure again to see the new scores.`); refreshAll(); } catch (e) { setMsg(e.message); }
  }
  return (
    <section className="q-card q-settings">
      <h3><button className="linkish" onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} Score, colours and schedule (the installation's)</button></h3>
      <p className="quiet small">Score: {partsText(d.score_parts)}; green from {d.bands.green}, amber from {d.bands.amber}, red below; stale after {d.stale_days} days; every model measured again {cronText(d.cron)}.
        Every model uses these unless it sets its own on its Quality tab (a Model Admin's waits for a Super Admin's approval). The estate is coloured by these.
        {d.modified_by && d.modified_by !== "system" ? ` Last changed by ${d.modified_by}, ${fmtDateTime(d.modified_at)}.` : ""}</p>
      {open && <>
        {!sa && <p className="quiet small">Only Super Admins change them.</p>}
        <ScoreColours installation admin={sa} parts={d.score_parts} bands={d.bands} own={{ score_parts: d.score_parts, bands: d.bands }} onSave={save} />
        <div className="row-gap filters">
          <label className="small">Stale after <input type="number" min="7" max="3650" style={{ width: 80 }} value={days} disabled={!sa} onChange={(e) => setDays(e.target.value)} /> days</label>
          <span className="small">Every model measured again <Frequency cron={cron} disabled={!sa} onChange={(c) => setCron(c || d.cron)} /></span>
          {sa && <button onClick={() => save({ stale_days: Number(days), cron })}>Save</button>}
        </div>
        {msg && <p className="status warn small">{msg}</p>}
      </>}
    </section>
  );
}

// which models are measured (D242): Super and IT Admins choose; the choice stays
function Scope({ scope, onError, bands }) {
  const [open, setOpen] = useState(true);
  const [busy, setBusy] = useState("");

  async function set(m, measured) {
    setBusy(m.id); onError("");
    try { await apiFetch("/api/v1/quality/scope", { method: "PUT", body: JSON.stringify({ models: [m.id], measured }) }); refreshAll(); } catch (e) { onError(e.message); }
    setBusy("");
  }
  const on = scope.filter((m) => m.measured).length;
  return (
    <section className="q-card">
      <h3><button className="linkish" onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} Which models are measured</button></h3>
      <p className="quiet small">{on} of {scope.length} models are measured. By default project models are, and library models, root metamodels, frozen
        and read-only models are not, so they add no noise; archived models never are. Your choice stays until someone changes it.</p>
      <p className="quiet small q-legend">{Object.values(MODEL_STATES).map(([i, l, h]) => <span key={l} title={h}>{i} {l}</span>)}</p>
      {open && <table className="grid-table">
        <thead><tr><th>Model</th><th>Kind</th><th>State</th><th>Entities</th><th>Latest score</th><th>Measured</th></tr></thead>
        <tbody>{scope.map((m) => (
          <tr key={m.id}><td>{m.name}</td><td className="small nowrap"><KindMark m={m} /> {(MODEL_KINDS[m.kind] || MODEL_KINDS.project).label}
              {(m.kind === "template" || m.kind === "reference") && <span title="In the model library"> 📚</span>}</td>
            <td className="small nowrap"><ModelStateBadge m={m} /></td><td className="small">{m.entities}</td>
            <td className="nowrap" title={m.score == null ? "Not measured yet" : `${exact(m.score)}, measured ${fmtDateTime(m.measured_at)}`}>
              {m.score == null ? <span className="quiet small">-</span> : <><span className="q-mini q-line"><span className={`q-bar-fill ${toneOf(m.score, bands)}`} style={{ width: `${Math.max(2, Number(m.score))}%` }} /></span>{" "}
                <span className="small">{pct(m.score)}</span></>}</td>
            <td><label className="small"><input type="checkbox" checked={m.measured} disabled={busy === m.id || m.lifecycle !== "active"} onChange={(e) => set(m, e.target.checked)} /> {m.lifecycle !== "active" ? "never (archived)" : m.measured ? "yes" : "no"}{m.chosen || m.lifecycle !== "active" ? "" : " (default)"}</label></td></tr>
        ))}</tbody>
      </table>}
    </section>
  );
}

// ---------------------------------------------------------------- Administration > Quality: every model, approvals
export function QualityAdmin() {
  const { data, error } = useApi("/api/v1/quality");
  const sa = roles().includes("super-admin");
  const changes = useApi(sa ? "/api/v1/quality/changes" : null);
  const [msg, setMsg] = useState("");
  const [done, setDone] = useState("");
  const [chosen, setChosen] = useState(new Set());
  const queued = (data?.models || []).filter((x) => x.job).length;
  useEffect(() => {          // measurements run in the background (D245): read again until they are done
    if (!queued) return undefined;
    const tm = setInterval(refreshAll, 3000);
    return () => clearInterval(tm);
  }, [queued]);
  const [was, setWas] = useState(0);
  useEffect(() => { if (was && !queued) setDone("Every measurement asked for is done."); setWas(queued); }, [queued]); // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const running = Object.fromEntries(data.models.filter((x) => x.job).map((x) => [x.id, x.job.status]));
  // measure one model in the background (the Quality tab and the model page have the same button)
  async function measure(m) {
    setMsg(""); setDone("");
    try { await apiFetch(`/api/v1/models/${m.id}/quality/run`, { method: "POST" }); refreshAll(); } catch (e) { setMsg(`${m.name}: ${e.message}`); }
  }
  // every model shown (the models chosen to be measured): one background job each, run side by side
  async function measureAll() {
    setMsg(""); setDone("");
    try { const r = await apiFetch("/api/v1/quality/run", { method: "POST" }); setDone(`${r.requests.length} measurements asked for; they run in the background and the page updates.`); refreshAll(); } catch (e) { setMsg(e.message); }
  }
  async function decide(c, approve) {
    // eslint-disable-next-line no-alert
    const note = window.prompt(approve ? `Approve: ${c.summary}? A note for ${c.requested_by} (optional):` : `Reject: ${c.summary}? Why (for ${c.requested_by}):`, "");
    if (note === null) return;
    setMsg("");
    try { await apiFetch(`/api/v1/quality/changes/${c.id}/${approve ? "approve" : "reject"}`, { method: "POST", body: JSON.stringify({ note }) }); refreshAll(); } catch (e) { setMsg(e.message); }
  }
  const pend = (changes.data?.changes || []).filter((c) => c.status === "pending");
  async function decideAll(approve) {
    // eslint-disable-next-line no-alert
    const note = window.prompt(approve ? `Approve ${chosen.size} changes? A note for the Model Admins (optional):` : `Reject ${chosen.size} changes: why (they can ask again)?`, "");
    if (note === null) return;
    setMsg("");
    try {
      const r = await apiFetch("/api/v1/quality/changes/decide", { method: "POST", body: JSON.stringify({ ids: [...chosen], decision: approve ? "approve" : "reject", note }) });
      setDone(`${r.decided} ${approve ? "approved" : "rejected"}${r.failed.length ? `; ${r.failed.length} not` : ""}.`); setChosen(new Set()); refreshAll();
    } catch (e) { setMsg(e.message); }
  }
  return (
    <div className="quality">
      <Bands.Provider value={data.bands || DEFAULT_BANDS}>
      <EstateHead estate={data.estate} every={data.every} onPdf={() => apiDownload("/api/v1/quality/pdf", "EA Explorer data quality estate.pdf").catch((e) => setMsg(e.message))}
        onXlsx={() => apiDownload("/api/v1/quality/xlsx", "EA Explorer data quality estate.xlsx").catch((e) => setMsg(e.message))} />
      </Bands.Provider>
      {msg && <p className="status bad">{msg}</p>}
      {done && <p className="status ok">{done}</p>}
      <h3>Every model</h3>
      {data.models.length > 0 && <p><button className="primary" onClick={measureAll} disabled={queued > 0}
        title="Measure every model listed here (the models chosen to be measured) in the background and keep the measurements">
        {queued ? "Measuring..." : `Measure all ${data.models.length} now`}</button> {queued > 0 && <span className="small"><span className="spinner" aria-hidden="true" /> {queued} of {data.models.length} still measuring in the background; you can leave this page</span>}</p>}
      <p className="quiet small">{data.every ? "Every project model" : "The project models you have"}, with its latest kept measurement, weakest first; click a model for its Quality tab and the drill-down, or <b>Measure now</b> to measure it and keep the measurement.</p>
      <div className="q-models">
        {data.models.map((m) => (
          <Bands.Provider key={m.id} value={m.summary?.bands || data.bands || DEFAULT_BANDS}><div className="q-model" title={`${m.name}: score ${exact(m.score)}, completeness ${exact(m.completeness)}`}>
            <a href={`#/metamodel/${m.id}/quality`} className="q-model-ring" aria-label={`${m.name}: Quality tab`}><ScoreRing value={m.score} size={86} label="score" /></a>
            <span className="q-model-text"><a href={`#/metamodel/${m.id}/quality`}><ModelIcon m={m} size={16} /> <b>{m.name}</b></a>
              <span className="small">{m.entities} entities · completeness {pct(m.completeness)}{m.summary ? ` · ${m.summary.stale} stale · ${m.summary.failing} failing` : ""}</span>
              <span className="small quiet">{m.measured_at ? `measured ${fmtDateTime(m.measured_at)}` : "not measured yet"}{m.month_ago != null && m.score != null ? ` · ${m.score - m.month_ago >= 0 ? "▲" : "▼"} ${Math.abs(Math.round(m.score - m.month_ago))} in a month` : ""}</span>
              <Trend points={m.trend} small />
              <span><button className="small" onClick={() => measure(m)} disabled={!!running[m.id]} title="Measure this model now and keep the measurement (it joins the trend and the estate)">
                {running[m.id] === "running" ? "Measuring..." : running[m.id] ? "Queued..." : "Measure now"}</button></span></span>
          </div></Bands.Provider>
        ))}
        {!data.models.length && <p className="quiet">No project model yet.</p>}
      </div>
      {data.every && <Scope scope={data.scope} onError={setMsg} bands={data.bands || DEFAULT_BANDS} />}
      {data.defaults && <Defaults d={data.defaults} sa={sa} />}
      {sa && <>
        <h3>Changes waiting for your approval</h3>
        <p className="quiet small">Model Admins' changes to quality settings, weights and rules apply only when a Super Admin approves them (D239). A rejected change can be asked for again.</p>
        {pend.length > 0 && <div className="row-gap"><button className="primary" disabled={!chosen.size} onClick={() => decideAll(true)}>Approve {chosen.size || ""} selected</button>
          <button disabled={!chosen.size} onClick={() => decideAll(false)}>Reject {chosen.size || ""} selected</button></div>}
        <table className="grid-table">
          <thead><tr><th><input type="checkbox" aria-label="Choose all" checked={pend.length > 0 && chosen.size === pend.length} onChange={(e) => setChosen(e.target.checked ? new Set(pend.map((c) => c.id)) : new Set())} /></th>
            <th>Model</th><th>Change</th><th>By</th><th>When</th><th /></tr></thead>
          <tbody>
            {pend.map((c) => <tr key={c.id}><td><input type="checkbox" checked={chosen.has(c.id)} onChange={() => setChosen((s) => { const n = new Set(s); if (n.has(c.id)) n.delete(c.id); else n.add(c.id); return n; })} /></td><td><a href={`#/metamodel/${c.model_id}/quality`}>{c.model}</a></td><td>{c.summary}{c.note && <div className="quiet small">{c.note}</div>}</td>
              <td className="small">{c.requested_by}</td><td className="small">{fmtDateTime(c.requested_at)}</td>
              <td className="nowrap"><button className="primary" onClick={() => decide(c, true)}>Approve</button> <button onClick={() => decide(c, false)}>Reject</button></td></tr>)}
            {!pend.length && <tr><td colSpan="6" className="quiet">Nothing waiting.</td></tr>}
          </tbody>
        </table>
      </>}
    </div>
  );
}
