// Model page, tab KPIs (phase 24, D365, D430 to D432): the model's KPIs as trends, kept on the 1st of each month and on
// every tag, with the value now worked out live. The standard set (entities by type, applications by TIME and lifecycle,
// total cost, quality score, orphans, end-of-life technology) and the model's own KPIs, which its Model Admins set here:
// a count of the entities of a type, or the sum of a number attribute, with one filter. The same trends are in the
// reporting tool (report KR-01).
import { useState } from "react";
import { apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { fmtDate, fmtNumber, serviceOn } from "./fmt";

const shown = (v, unit) => {
  if (v === null || v === undefined) return "-";
  const n = fmtNumber(v, Number.isInteger(v) ? 0 : 1);
  return unit === "%" ? `${n}%` : unit && unit !== "cost" ? `${n} ${unit}` : n;
};

function Spark({ series, now }) {
  const pts = [...series, now].map((v, i) => [i, v]).filter(([, v]) => v !== null && v !== undefined);
  if (pts.length < 2) return <span className="quiet small">no trend yet</span>;
  const w = 160;
  const h = 34;
  const vals = pts.map(([, v]) => v);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const n = series.length;
  const x = (i) => 3 + (i * (w - 6)) / Math.max(1, n);
  const y = (v) => 3 + ((hi - v) * (h - 6)) / (hi - lo || 1);
  return (
    <svg className="kpi-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Trend">
      <polyline points={pts.map(([i, v]) => `${x(i)},${y(v)}`).join(" ")} className="q-line" />
      <circle cx={x(pts[pts.length - 1][0])} cy={y(pts[pts.length - 1][1])} r="2.5" className="q-dot" />
    </svg>
  );
}

function Chart({ kpi, snapshots }) {
  const dims = kpi.dimensions.slice(0, 6);
  const cols = [...snapshots.map((s) => s), { now: true }];
  const all = dims.flatMap((d) => [...d.series, d.now]).filter((v) => v !== null && v !== undefined);
  if (!all.length) return <p className="quiet">Nothing kept yet.</p>;
  const w = 720;
  const h = 200;
  const lo = Math.min(0, ...all);
  const hi = Math.max(...all) || 1;
  const x = (i) => 56 + (i * (w - 70)) / Math.max(1, cols.length - 1);
  const y = (v) => 10 + ((hi - v) * (h - 40)) / (hi - lo || 1);
  return (
    <div>
      <svg className="kpi-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`${kpi.name} over time`}>
        {[lo, (lo + hi) / 2, hi].map((v) => <g key={v}><line x1="52" x2={w} y1={y(v)} y2={y(v)} className="q-grid" />
          <text x="0" y={y(v) + 4} className="q-axis">{shown(Math.round(v), kpi.unit)}</text></g>)}
        {cols.map((c, i) => (c.now || c.reason === "tag")
          && <line key={`m${i}`} x1={x(i)} x2={x(i)} y1="8" y2={h - 28} className={c.now ? "kpi-now-line" : "kpi-tag-line"}><title>{c.now ? "Now" : `Tag: ${c.tag}`}</title></line>)}
        {dims.map((d, k) => {
          const pts = [...d.series, d.now].map((v, i) => [i, v]).filter(([, v]) => v !== null && v !== undefined);
          return (
            <g key={d.dimension || "one"} className={`kpi-series s${k}`}>
              <polyline points={pts.map(([i, v]) => `${x(i)},${y(v)}`).join(" ")} />
              {pts.map(([i, v]) => <circle key={i} cx={x(i)} cy={y(v)} r="3">
                <title>{`${d.dimension ? `${d.dimension}: ` : ""}${shown(v, kpi.unit)} (${cols[i].now ? "now" : `${fmtDate(cols[i].taken_at)}${cols[i].tag ? `, tag ${cols[i].tag}` : ""}`})`}</title></circle>)}
            </g>
          );
        })}
        {snapshots.length > 0 && <text x={x(0)} y={h - 8} className="q-axis">{fmtDate(snapshots[0].taken_at)}</text>}
        <text x={w} y={h - 8} textAnchor="end" className="q-axis">now</text>
      </svg>
      {dims.length > 1 && (
        <p className="kpi-legend">{dims.map((d, k) => <span key={d.dimension} className={`kpi-key s${k}`}>{d.dimension}</span>)}
          {kpi.dimensions.length > dims.length && <span className="quiet"> and {kpi.dimensions.length - dims.length} more (in the table)</span>}</p>
      )}
    </div>
  );
}

export default function KpisTab({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/kpis`);
  const [open, setOpen] = useState("entities");
  const [editing, setEditing] = useState(null);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading the KPIs...</p>;
  const snaps = data.snapshots;
  const own = data.kpis.filter((k) => k.kind === "own");
  const std = data.kpis.filter((k) => k.kind === "standard");
  const last = snaps[snaps.length - 1];
  const row = (k) => {
    const one = k.dimensions.length === 1 && !k.dimensions[0].dimension;
    const d0 = k.dimensions[0] || { series: [], now: null };
    const before = [...d0.series].reverse().find((v) => v !== null && v !== undefined);
    const change = one && before !== undefined && d0.now !== null ? d0.now - before : null;
    return (
      <tr key={k.code} className={open === k.code ? "on" : ""}>
        <td>
          <button className="linkish" onClick={() => setOpen(open === k.code ? "" : k.code)} title={k.about}>{k.name}</button>
          {k.retired && <span className="rag off" title="No longer kept: its trend so far stays">no longer kept</span>}
          {k.kind === "own" && !k.retired && !d0.series.some((v) => v !== null && v !== undefined)
            && <span className="rag amber" title="Added since the last snapshot: the trend starts at the next one">new</span>}
        </td>
        <td className="num">{one ? shown(d0.now, k.unit) : <span className="quiet">{k.dimensions.length} parts</span>}</td>
        <td className="num">{change === null ? "" : <span className={change > 0 ? "kpi-up" : change < 0 ? "kpi-down" : "quiet"}>
          {change > 0 ? "+" : ""}{shown(change, k.unit)}</span>}</td>
        <td>{one ? <Spark series={d0.series} now={d0.now} /> : <span className="quiet small">{k.dimensions.slice(0, 3).map((d) => `${d.dimension} ${shown(d.now, k.unit)}`).join(" · ")}</span>}</td>
        {data.may_manage && <td>{k.kind === "own" && !k.retired && <button className="linkish" onClick={() => setEditing(k.definition)}>Change</button>}</td>}
      </tr>
    );
  };
  const opened = data.kpis.find((k) => k.code === open);
  return (
    <div className="kpis-tab">
      <h2>KPI trends</h2>
      <p className="quiet">
        Kept on the 1st of each month and whenever the model is tagged ({snaps.length} snapshot{snaps.length === 1 ? "" : "s"} so far
        {last ? `, the last ${fmtDate(last.taken_at)}${last.tag ? ` (tag ${last.tag})` : ""}` : ""}); <em>Now</em> is worked out as you look.
        Committed content only.{serviceOn("reports") && <> The same trends, for several models at once, are in the reporting tool (report KR-01).</>}
      </p>
      {!snaps.length && <p className="status warn">No snapshot kept yet: the first is taken within the hour, and on the next tag.</p>}
      <table className="grid-table kpi-table">
        <thead><tr><th>KPI</th><th className="num">Now</th><th className="num">Since the last snapshot</th><th>Trend</th>{data.may_manage && <th />}</tr></thead>
        <tbody>
          <tr className="kpi-group"><td colSpan={data.may_manage ? 5 : 4}>Standard KPIs</td></tr>
          {std.map(row)}
          <tr className="kpi-group"><td colSpan={data.may_manage ? 5 : 4}>The model's own KPIs
            {data.may_manage && <button className="linkish" onClick={() => setEditing({})}>+ Add a KPI</button>}</td></tr>
          {own.map(row)}
          {!own.length && <tr><td colSpan={5} className="quiet">None yet. {data.may_manage ? "Add one: a count of entities of a type, or a sum of a number attribute, with a filter." : "The model's Model Admins add them."}</td></tr>}
        </tbody>
      </table>
      {opened && (
        <section className="kpi-detail">
          <h3>{opened.name}</h3>
          <p className="quiet">{opened.about}{opened.definition && <> · {describe(opened.definition, data)}</>}</p>
          <Chart kpi={opened} snapshots={snaps} />
          {opened.dimensions.length > 1 && (
            <table className="grid-table">
              <thead><tr><th>{opened.code.includes("type") ? "Entity type" : "Part"}</th><th className="num">Now</th>
                {snaps.slice(-4).map((s, i) => <th key={i} className="num">{fmtDate(s.taken_at)}{s.tag ? ` (${s.tag})` : ""}</th>)}</tr></thead>
              <tbody>{opened.dimensions.map((d) => (
                <tr key={d.dimension}><td>{d.dimension || "-"}</td><td className="num">{shown(d.now, opened.unit)}</td>
                  {d.series.slice(-4).map((v, i) => <td key={i} className="num">{shown(v, opened.unit)}</td>)}</tr>
              ))}</tbody>
            </table>
          )}
        </section>
      )}
      {editing && <KpiEditor model={model} m={m} kpi={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function describe(d, data) {
  const what = d.kind === "sum" ? `the sum of ${d.attribute_code} over ${d.entity_type_code}` : `the number of ${d.entity_type_code}`;
  const filt = d.filter_op ? ` where ${d.filter_attribute} ${data.ops[d.filter_op]}${d.filter_value ? ` ${d.filter_value}` : ""}` : "";
  return `${what}${filt}`;
}

function KpiEditor({ model, kpi, onClose }) {
  const { data: mm } = useApi(`/api/v1/models/${model}/report-designer`);
  const [f, setF] = useState({ name: "", kind: "count", entity_type_code: "", attribute_code: "", filter_attribute: "", filter_op: "",
    filter_value: "", unit: "", description: "", ...kpi });
  const [msg, setMsg] = useState("");
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const type = mm?.types.find((t) => t.code === f.entity_type_code);
  const attrs = (type?.fields || []).filter((a) => a.attribute);
  const numbers = attrs.filter((a) => ["numeric", "bigint", "integer"].includes(a.data_type));
  const save = async () => {
    setMsg("");
    const body = JSON.stringify({ ...f, filter_op: f.filter_attribute ? (f.filter_op || "equals") : "" });
    try {
      if (kpi.id) await apiFetch(`/api/v1/models/${model}/kpis/definitions/${kpi.id}`, { method: "PUT", body });
      else await apiFetch(`/api/v1/models/${model}/kpis/definitions`, { method: "POST", body });
      refreshAll();
      onClose();
    } catch (e) { setMsg(e.message); }
  };
  const remove = async () => {
    try {
      await apiFetch(`/api/v1/models/${model}/kpis/definitions/${kpi.id}/delete`, { method: "POST" });
      refreshAll();
      onClose();
    } catch (e) { setMsg(e.message); }
  };
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="The KPI" onClick={(e) => e.stopPropagation()}>
        <h3>{kpi.id ? "Change the KPI" : "Add a KPI"}</h3>
        <p className="quiet">Kept with the standard KPIs from the next snapshot (the 1st of the month or the next tag); its value now shows at once.</p>
        <div className="form-grid">
          <label>Name <input value={f.name} onChange={set("name")} placeholder="Applications to retire" /></label>
          <label>It is <select value={f.kind} onChange={set("kind")}>{Object.entries(mm?.kinds || { count: "Count of entities", sum: "Sum of a number attribute" }).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label>Entity type <select value={f.entity_type_code} onChange={set("entity_type_code")}>
            <option value="">Choose...</option>
            {(mm?.types || []).map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}</select></label>
          {f.kind === "sum" && <label>Adds up <select value={f.attribute_code} onChange={set("attribute_code")}>
            <option value="">Choose a number attribute...</option>
            {numbers.map((a) => <option key={a.attribute} value={a.attribute}>{a.name}</option>)}</select></label>}
          <label>Filter <select value={f.filter_attribute} onChange={set("filter_attribute")}>
            <option value="">No filter</option>{attrs.map((a) => <option key={a.attribute} value={a.attribute}>{a.name}</option>)}</select></label>
          {f.filter_attribute && <label>Compared <select value={f.filter_op || "equals"} onChange={set("filter_op")}>
            {Object.entries({ equals: "is", "not-equals": "is not", contains: "contains", empty: "is empty", "not-empty": "is not empty", "more-than": "is more than", "less-than": "is less than" })
              .map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>}
          {f.filter_attribute && !["empty", "not-empty"].includes(f.filter_op || "equals") && <label>Value <input value={f.filter_value} onChange={set("filter_value")} /></label>}
          <label>Unit <input value={f.unit} onChange={set("unit")} placeholder="USD, %, people..." /></label>
          <label className="wide">What it tells <input value={f.description} onChange={set("description")} /></label>
        </div>
        {msg && <p className="status bad">{msg}</p>}
        <div className="toolbar">
          <button className="primary" onClick={save}>Save</button>
          {kpi.id && <button className="danger" onClick={remove} title="No longer kept; its trend so far stays">Stop keeping it</button>}
          <button onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
