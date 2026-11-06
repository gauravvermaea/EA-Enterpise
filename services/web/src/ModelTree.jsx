// The model hierarchy as a drawn tree (Models > Hierarchy): each model a box under the model it merges
// into or, failing that, the one it was created from (D63, D81). Top-down or left-to-right, pan and
// zoom, click a box to open the model; opens in draw.io (D256) and saves as SVG and PNG. Only the models you may read.
import { useEffect, useMemo, useRef, useState } from "react";
import { openDrawio, downloadPng, downloadSvg } from "./exporting";
import usePanZoom from "./usePanZoom";
import { KINDS, lockWhy, marksText, readOnlyWhy } from "./ModelMarks";

const W = 210, H = 64, GAP_X = 28, GAP_Y = 64;
const STYLE = {
  template:  { fill: "#efedfa", stroke: "#5b4bb7", label: KINDS.template.label, glyph: KINDS.template.glyph },
  reference: { fill: "#e6f4f1", stroke: "#1f7a6d", label: KINDS.reference.label, glyph: KINDS.reference.glyph },
  project:   { fill: "#e8f0fb", stroke: "#1f5fb8", label: KINDS.project.label, glyph: KINDS.project.glyph },
};
const upOf = (m) => m.parent_model_id || m.source_model_id || null;
const cut = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

// a tidy tree: leaves side by side, each parent centred over its children
function layout(models, across) {
  const byId = Object.fromEntries(models.map((m) => [m.id, m]));
  const kids = {};
  for (const m of models) {
    const up = upOf(m);
    (kids[up && byId[up] ? up : ""] ||= []).push(m);
  }
  const order = { template: 0, reference: 1, project: 2 };
  Object.values(kids).forEach((l) => l.sort((a, b) => (order[a.kind] ?? 9) - (order[b.kind] ?? 9) || a.name.localeCompare(b.name)));
  const span = across ? H + GAP_X : W + GAP_X;     // room one leaf takes along the breadth
  const step = across ? W + GAP_Y : H + GAP_Y;     // distance between levels
  const nodes = [], edges = [];
  let next = 0, depthMax = 0;
  const place = (m, depth) => {
    depthMax = Math.max(depthMax, depth);
    const children = kids[m.id] || [];
    let at;
    if (!children.length) { at = next; next += span; }
    else {
      const pos = children.map((c) => place(c, depth + 1));
      at = (pos[0] + pos[pos.length - 1]) / 2;
      children.forEach((c) => edges.push({ from: m.id, to: c.id, merges: c.parent_model_id === m.id }));
    }
    const x = across ? depth * step : at, y = across ? at : depth * step;
    nodes.push({ m, x, y });
    return at;
  };
  (kids[""] || []).forEach((m) => { place(m, 0); next += span / 2; });
  const pos = Object.fromEntries(nodes.map((n) => [n.m.id, n]));
  const width = across ? (depthMax + 1) * step - GAP_Y : Math.max(next - GAP_X, W);
  const height = across ? Math.max(next - GAP_X, H) : (depthMax + 1) * step - GAP_Y;
  return { nodes, edges, pos, width, height };
}

export default function ModelTree({ models, focus }) {
  const [across, setAcross] = useState(false);
  const [mine, setMine] = useState("");
  const svgRef = useRef(null);
  const t = useMemo(() => layout(models, across), [models, across]);
  const { frame, view, fit, zoomCentre, handlers, wasDrag } = usePanZoom([t]);
  useEffect(() => { fit(t.width, t.height, 1); }, [t]); // eslint-disable-line react-hooks/exhaustive-deps
  const title = "EA Explorer model hierarchy";

  // the elbow line from a parent box to a child box
  const link = (e) => {
    const a = t.pos[e.from], b = t.pos[e.to];
    if (across) {
      const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = x1 + GAP_Y / 2;
      return `M${x1},${y1} H${mx} V${y2} H${x2}`;
    }
    const x1 = a.x + W / 2, y1 = a.y + H, x2 = b.x + W / 2, y2 = b.y, my = y1 + GAP_Y / 2;
    return `M${x1},${y1} V${my} H${x2} V${y2}`;
  };
  function exportDrawio() {
    openDrawio(title, t.nodes.map(({ m, x, y }) => ({
      id: m.id, label: m.name, sub: `${STYLE[m.kind]?.label || m.kind}${m.kind !== "template" ? ` · ${m.entity_count} entities` : ""}`,
      x, y, w: W, h: H, fill: STYLE[m.kind]?.fill, stroke: STYLE[m.kind]?.stroke, ea_type: "Model", ea_id: m.id, align: "center",
    })), t.edges.map((e) => ({ source: e.from, target: e.to, dashed: !e.merges, arrow: false })));
  }
  const q = mine.trim().toLowerCase();

  return (
    <div>
      <div className="toolbar">
        <div className="seg small" role="tablist">
          <button className={!across ? "on" : ""} onClick={() => setAcross(false)}>Top down</button>
          <button className={across ? "on" : ""} onClick={() => setAcross(true)}>Left to right</button>
        </div>
        <input className="search" style={{ maxWidth: 220 }} placeholder="Highlight models" value={mine} onChange={(e) => setMine(e.target.value)} />
        <span className="er-spacer" />
        <button onClick={() => fit(t.width, t.height, 1)}>Fit</button>
        <button onClick={() => zoomCentre(1.25)}>+</button>
        <button onClick={() => zoomCentre(0.8)}>−</button>
        <button onClick={exportDrawio} title="Boxes and lines, opened in draw.io in a new tab; save or export it there">Open in draw.io</button>
        <button onClick={() => downloadSvg(svgRef.current, t.width, t.height, title)}>SVG</button>
        <button onClick={() => downloadPng(svgRef.current, t.width, t.height, title)}>PNG</button>
      </div>
      <p className="quiet er-info">
        {models.length} models. A solid line: the child merges back into its parent; a dashed line: it was created
        (copied) from it. Click a box to open the model. Models you may not read are left out.
      </p>
      <div className="er-frame graph-frame model-tree-frame" ref={frame} {...handlers}>
        <svg ref={svgRef} width="100%" height="100%" role="img" aria-label="Model hierarchy">
          <g data-viewport="" transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {t.edges.map((e) => (
              <path key={`${e.from}-${e.to}`} d={link(e)} fill="none" stroke="#7d8996" strokeWidth="1.4" strokeDasharray={e.merges ? "" : "5 4"} />
            ))}
            {t.nodes.map(({ m, x, y }) => {
              const s = STYLE[m.kind] || STYLE.project;
              const hit = (q && (m.name.toLowerCase().includes(q) || (m.industry || "").toLowerCase().includes(q))) || m.id === focus;
              return (
                <g key={m.id} transform={`translate(${x},${y})`} className="tree-box"
                  onClick={() => { if (!wasDrag()) window.location.hash = `/metamodel/${m.id}`; }}>
                  <title>{[`${m.name}${m.version_label ? ` ${m.version_label}` : ""}`, s.label, m.metamodel_name, readOnlyWhy(m), lockWhy(m)].filter(Boolean).join("\n")}</title>
                  <rect width={W} height={H} rx="8" fill={s.fill} stroke={hit ? "#d4351c" : s.stroke} strokeWidth={hit ? 3 : 1.4} />
                  <text x={W / 2} y="25" textAnchor="middle" fontSize="13" fontWeight="600" fill="#1d2733">
                    {s.glyph} {cut(m.name, 24)}{m.version_label ? ` ${m.version_label}` : ""}
                  </text>
                  <text x={W / 2} y="45" textAnchor="middle" fontSize="11" fill="#5b6775">
                    {s.label}{m.kind !== "template" ? ` · ${m.entity_count} entities` : ""}{marksText(m) ? `  ${marksText(m)}` : ""}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}
