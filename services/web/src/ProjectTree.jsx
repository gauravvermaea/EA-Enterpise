// The project hierarchy as a drawn tree (owner, 8 Nov 2026, D303), drawn as the model hierarchy is: each project a box
// under the base (or library project) it derives from: Empty project > TOGAF 10 project > Organisation base > projects.
// Top-down or left-to-right, pan and zoom, click a box to open it (or onPick); draw.io, SVG and PNG.
import { useEffect, useMemo, useRef, useState } from "react";
import { downloadPng, downloadSvg } from "./exporting";
import { PictureActions } from "./DrawnView";
import usePanZoom from "./usePanZoom";

const W = 210, H = 64, GAP_X = 28, GAP_Y = 64;
const STYLE = {
  empty:   { fill: "#f1f1f1", stroke: "#6b7280", label: "Empty project", glyph: "◻" },
  togaf:   { fill: "#efedfa", stroke: "#5b4bb7", label: "TOGAF 10 project", glyph: "◆" },
  org:     { fill: "#fdf3dc", stroke: "#b7791f", label: "Organisation base", glyph: "🏛" },
  library: { fill: "#e6f4f1", stroke: "#1f7a6d", label: "Library project", glyph: "▣" },
  project: { fill: "#e8f0fb", stroke: "#1f5fb8", label: "Project", glyph: "●" },
};
const cut = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

// the bases tree from /projects/bases as one list of boxes: {id, name, kind, up, status}
export function flatten(nodes, only = null) {
  const out = [];
  for (const n of nodes) {
    out.push({ id: n.id, name: n.name, kind: n.base_kind || "library", up: n.parent, status: n.status });
    for (const p of n.projects || []) {
      if (!only || only.has(p.id)) out.push({ id: p.id, name: p.name, kind: "project", up: n.id, status: p.status });
    }
  }
  return out;
}

function layout(items, across) {
  const byId = Object.fromEntries(items.map((m) => [m.id, m]));
  const kids = {};
  for (const m of items) (kids[m.up && byId[m.up] ? m.up : ""] ||= []).push(m);
  const order = { empty: 0, togaf: 1, org: 2, library: 3, project: 4 };
  Object.values(kids).forEach((l) => l.sort((a, b) => (order[a.kind] ?? 9) - (order[b.kind] ?? 9) || a.name.localeCompare(b.name)));
  const span = across ? H + GAP_X : W + GAP_X;
  const step = across ? W + GAP_Y : H + GAP_Y;
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
      children.forEach((c) => edges.push({ from: m.id, to: c.id }));
    }
    nodes.push({ m, x: across ? depth * step : at, y: across ? at : depth * step });
    return at;
  };
  (kids[""] || []).forEach((m) => { place(m, 0); next += span / 2; });
  const pos = Object.fromEntries(nodes.map((n) => [n.m.id, n]));
  const width = across ? (depthMax + 1) * step - GAP_Y : Math.max(next - GAP_X, W);
  const height = across ? Math.max(next - GAP_X, H) : (depthMax + 1) * step - GAP_Y;
  return { nodes, edges, pos, width, height };
}

export default function ProjectTree({ items, focus, onPick, height }) {
  const [across, setAcross] = useState(() => items.length > 14 || items.length <= 5);
  const [q, setQ] = useState("");
  const svgRef = useRef(null);
  const t = useMemo(() => layout(items, across), [items, across]);
  const { frame, view, fit, zoomCentre, handlers, wasDrag } = usePanZoom([t]);
  useEffect(() => { fit(t.width, t.height, 1); }, [t]); // eslint-disable-line react-hooks/exhaustive-deps
  const title = "EA Explorer project hierarchy";
  const link = (e) => {
    const a = t.pos[e.from], b = t.pos[e.to];
    if (across) {
      const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = x1 + GAP_Y / 2;
      return `M${x1},${y1} H${mx} V${y2} H${x2}`;
    }
    const x1 = a.x + W / 2, y1 = a.y + H, x2 = b.x + W / 2, y2 = b.y, my = y1 + GAP_Y / 2;
    return `M${x1},${y1} V${my} H${x2} V${y2}`;
  };
  // the tree as a picture to download (projects, not one model's: no drawn view, D406)
  function picture() {
    return { title, nodes: t.nodes.map(({ m, x, y }) => ({ id: m.id, label: m.name, sub: STYLE[m.kind]?.label, x, y, w: W, h: H,
      fill: STYLE[m.kind]?.fill, stroke: STYLE[m.kind]?.stroke, align: "center" })),
    edges: t.edges.map((e) => ({ source: e.from, target: e.to, arrow: false, route: "orthogonal" })) };
  }
  const hl = q.trim().toLowerCase();
  return (
    <div>
      <div className="toolbar">
        <div className="seg small" role="tablist">
          <button className={!across ? "on" : ""} onClick={() => setAcross(false)}>Top down</button>
          <button className={across ? "on" : ""} onClick={() => setAcross(true)}>Left to right</button>
        </div>
        <input className="search" style={{ maxWidth: 220 }} placeholder="Highlight projects" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="er-spacer" />
        <button onClick={() => fit(t.width, t.height, 1)}>Fit</button>
        <button onClick={() => zoomCentre(1.25)}>+</button>
        <button onClick={() => zoomCentre(0.8)}>−</button>
        <PictureActions picture={picture} images={false} />
        <button onClick={() => downloadSvg(svgRef.current, t.width, t.height, title)}>SVG</button>
        <button onClick={() => downloadPng(svgRef.current, t.width, t.height, title)}>PNG</button>
      </div>
      <p className="quiet er-info">Each project sits under the base or library project it derives from. {onPick ? "Click a project to open it; click a base to see what it holds (double-click opens it)." : "Click a box to open it."}</p>
      <div className="er-frame graph-frame model-tree-frame" ref={frame} {...handlers} style={height ? { height, minHeight: 0 } : undefined}>
        <svg ref={svgRef} width="100%" height="100%" role="img" aria-label="Project hierarchy">
          <g data-viewport="" transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {t.edges.map((e) => <path key={`${e.from}-${e.to}`} d={link(e)} fill="none" stroke="#7d8996" strokeWidth="1.4" />)}
            {t.nodes.map(({ m, x, y }) => {
              const s = STYLE[m.kind] || STYLE.project;
              const hit = (hl && m.name.toLowerCase().includes(hl)) || m.id === focus;
              return (
                <g key={m.id} transform={`translate(${x},${y})`} className="tree-box"
                  onClick={() => { if (wasDrag()) return; if (onPick) onPick(m.id, m.kind); else window.location.hash = `/projects/${m.id}`; }}
                  onDoubleClick={() => { window.location.hash = `/projects/${m.id}`; }}>
                  <title>{`${m.name}\n${s.label}${m.status ? ` · ${m.status}` : ""}`}</title>
                  <rect width={W} height={H} rx="8" fill={s.fill} stroke={hit ? "#d4351c" : s.stroke} strokeWidth={hit ? 3 : 1.4} />
                  <text x={W / 2} y="25" textAnchor="middle" fontSize="13" fontWeight="600" fill="#1d2733">{s.glyph} {cut(m.name, 24)}</text>
                  <text x={W / 2} y="45" textAnchor="middle" fontSize="11" fill="#5b6775">{s.label}{m.kind === "project" && m.status ? ` · ${m.status}` : ""}
                    {(m.kind === "empty" || m.kind === "togaf") ? " · read-only" : ""}</text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}
