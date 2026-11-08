// The SQL window's database diagram (owner, 8 Nov 2026): the tables behind models (schema core) or behind projects (schema
// proj), each with its columns (key ⚷, join ↗), and lines for the joins between them. Laid out by ELK, drawn as SVG.
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { elk } from "./MetamodelDiagram";

const ROW = 16;
const HEAD = 24;
const W = 300;
const cut = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export default function SchemaDiagram() {
  const [schema, setSchema] = useState("proj");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [keysOnly, setKeysOnly] = useState(true);
  const [focus, setFocus] = useState("");
  const [layout, setLayout] = useState(null);
  useEffect(() => {
    setData(null); setErr(""); setFocus(""); setLayout(null);   // the other schema's drawing goes (its tables are not in this one)
    apiFetch(`/api/v1/sql/schema?schema=${schema}`).then(setData).catch((e) => setErr(e.message));
  }, [schema]);
  // the tables shown: all, or one and the tables it joins with
  const shown = useMemo(() => {
    if (!data) return [];
    if (!focus) return data.tables;
    const near = new Set([focus]);
    data.joins.forEach((j) => { if (j.from === focus) near.add(j.to); if (j.to === focus) near.add(j.from); });
    return data.tables.filter((t) => near.has(t.name));
  }, [data, focus]);
  const colsOf = (t) => (keysOnly ? t.columns.filter((c) => c.pk || c.fk || ["name", "guid", "code"].includes(c.name)) : t.columns);
  useEffect(() => {
    if (!data) return;
    const names = new Set(shown.map((t) => t.name));
    const graph = {
      id: "root",
      layoutOptions: { "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.spacing.nodeNode": "28", "elk.layered.spacing.nodeNodeBetweenLayers": "60",
        "elk.edgeRouting": "ORTHOGONAL" },
      children: shown.map((t) => ({ id: t.name, width: W, height: HEAD + ROW * colsOf(t).length + 6 })),
      edges: data.joins.filter((j) => !j.outside && names.has(j.from) && names.has(j.to) && j.from !== j.to)
        .map((j, i) => ({ id: `e${i}`, sources: [j.from], targets: [j.to] })),
    };
    let live = true;
    elk.layout(graph).then((g) => { if (live) setLayout(g); }).catch((e) => setErr(String(e)));
    return () => { live = false; };
  }, [data, shown, keysOnly]); // eslint-disable-line react-hooks/exhaustive-deps
  function downloadSvg() {
    const svg = document.getElementById("schema-svg");
    if (!svg) return;
    const blob = new Blob([svg.outerHTML], { type: "image/svg+xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `EA Explorer ${schema} tables.svg`; a.click();
  }
  const byName = Object.fromEntries((data?.tables || []).map((t) => [t.name, t]));
  return (
    <div className="schema-diagram">
      <div className="row-gap">
        <label>Tables of <select value={schema} onChange={(e) => setSchema(e.target.value)}>
          <option value="proj">projects (schema proj)</option><option value="core">models (schema core)</option></select></label>
        <label className="small"><input type="checkbox" checked={keysOnly} onChange={(e) => setKeysOnly(e.target.checked)} /> keys and joins only</label>
        <label className="small">Focus on <select value={focus} onChange={(e) => setFocus(e.target.value)}><option value="">every table</option>
          {(data?.tables || []).map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}</select></label>
        <button className="push-right" onClick={downloadSvg} disabled={!layout}>⬇ SVG</button>
      </div>
      <p className="small quiet">Each box is a table of schema <code>{schema}</code>: ⚷ its key, ↗ a column that joins another table (the line). Click a table to focus on it
        and the tables it joins with. {schema === "core" && "Every core table also has model_id → models.id."}</p>
      {err && <p className="status bad">{err}</p>}
      {!layout ? <p className="quiet">Drawing…</p> : (
        <div className="schema-scroll">
          <svg id="schema-svg" xmlns="http://www.w3.org/2000/svg" width={layout.width + 20} height={layout.height + 20} fontFamily="system-ui, sans-serif" fontSize="11">
            <defs><marker id="sch-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#8a94a6" /></marker></defs>
            <rect width="100%" height="100%" fill="#ffffff" />
            {(layout.edges || []).map((e) => (e.sections || []).map((s, i) => {
              const pts = [s.startPoint, ...(s.bendPoints || []), s.endPoint];
              return <polyline key={`${e.id}${i}`} points={pts.map((q) => `${q.x + 10},${q.y + 10}`).join(" ")} fill="none" stroke="#8a94a6" strokeWidth="1.2" markerEnd="url(#sch-arrow)" />;
            }))}
            {(layout.children || []).map((n) => {
              const t = byName[n.id];
              if (!t) return null;        // a drawing of tables no longer loaded (owner, 8 Nov 2026: the screen went blank)
              const cols = colsOf(t);
              return (
                <g key={n.id} transform={`translate(${n.x + 10},${n.y + 10})`} style={{ cursor: "pointer" }} onClick={() => setFocus(focus === n.id ? "" : n.id)}>
                  <rect width={W} height={n.height} rx="5" fill="#fff" stroke={focus === n.id ? "#0969da" : "#9aa4b2"} strokeWidth={focus === n.id ? 2 : 1} />
                  <rect width={W} height={HEAD} rx="5" fill="#eef3fb" />
                  <text x="8" y="16" fontWeight="700" fontSize="12" fill="#1f2328">{n.id}</text>
                  {cols.map((c, i) => (
                    <text key={c.name} x="8" y={HEAD + ROW * i + 12} fill={c.pk ? "#1f2328" : "#424a53"} fontWeight={c.pk ? 700 : 400}>
                      {c.pk ? "⚷ " : c.fk ? "↗ " : "  "}{cut(c.name, 26)}<tspan fill="#8a94a6"> {cut(`${c.type}${c.fk ? ` → ${c.fk}` : ""}`, Math.max(8, 44 - Math.min(c.name.length, 26)))}</tspan>
                      <title>{`${c.name} ${c.type}${c.nullable ? "" : " not null"}${c.fk ? ` → ${c.fk}` : ""}`}</title>
                    </text>
                  ))}
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </div>
  );
}
