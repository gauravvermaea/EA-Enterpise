// The metamodel as an ER diagram, generated from the database every time it opens.
//   #/metamodel/<model>/diagram           chosen layers (Business by default)
//   #/metamodel/<model>/diagram/<typeId>  one entity type and every type it may connect to
// Boxes are entity types with their attributes; lines are the allowed relationships, combined per
// source and target type and labelled with the relationship types. Layout by ELK (elkjs), run in a
// web worker so the screen stays responsive. Which layout:
//   focus on a type with more than RADIAL_MIN types shown   ring around the focused type
//   more than DENSE lines per type (up to RING_MAX types)    every type on a ring, straight lines
//   up to LAYERED_MAX lines                                  ELK layered, right-angled lines
//   otherwise                                                ELK stress, straight lines (layered takes minutes)
// The choice of what to show follows the same rules as services/api/eax/diagram.py (scope).
import { useEffect, useMemo, useRef, useState } from "react";
import ELK from "elkjs/lib/elk-api.js";
import elkWorkerUrl from "elkjs/lib/elk-worker.min.js?url";
import { apiFetch } from "./auth";

const GENERIC = ["Association", "Specialization"];
const REL_COLOURS = {
  Composition: "#1f5fb8", Aggregation: "#5b8fd6", Assignment: "#7a3db8", Realization: "#1e7b3c",
  Serving: "#c26a00", Access: "#8a6d00", Influence: "#b3261e", Association: "#6b7785",
  Triggering: "#00838f", Flow: "#2e9e8f", Specialization: "#4a4a4a",
};
const relColour = (code) => REL_COLOURS[code] || "#6b7785";
const FONT = "12px system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
const BOLD = "600 13px system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
const HEADER = 38, ROW = 18, PAD = 10;
const LAYERED_MAX = 200, RADIAL_MIN = 10, DENSE = 4, RING_MAX = 60;
const elk = new ELK({ workerUrl: elkWorkerUrl });
const go = (path) => { window.location.hash = path; };

let measureCtx;
function textWidth(text, font = FONT) {
  measureCtx ||= document.createElement("canvas").getContext("2d");
  measureCtx.font = font;
  return measureCtx.measureText(text).width;
}

// ---------------------------------------------------------------- what to show (mirrors eax/diagram.py)
export function scopeDiagram(data, { layers, focus, rels, connected }) {
  const keep = new Set(rels);
  let links = data.links
    .map((l) => ({ ...l, relationship_types: l.relationship_types.filter((c) => keep.has(c)) }))
    .filter((l) => l.relationship_types.length);
  let ids;
  if (focus) {
    links = links.filter((l) => l.source === focus || l.target === focus);
    ids = new Set([focus, ...links.map((l) => l.source), ...links.map((l) => l.target)]);
  } else {
    const inside = new Set(data.entity_types.filter((t) => !layers.length || layers.includes(t.layer_id)).map((t) => t.id));
    if (connected) {
      links = links.filter((l) => inside.has(l.source) || inside.has(l.target));
      ids = new Set([...inside, ...links.map((l) => l.source), ...links.map((l) => l.target)]);
    } else {
      links = links.filter((l) => inside.has(l.source) && inside.has(l.target));
      ids = inside;
    }
  }
  return { types: data.entity_types.filter((t) => ids.has(t.id)), links };
}

function nodeSize(t, showAttrs) {
  const attrs = showAttrs ? t.attributes : [];
  let w = Math.max(textWidth(t.name, BOLD), textWidth(`${t.layer} · ${t.entity_count} entities`, FONT));
  for (const a of attrs) w = Math.max(w, textWidth(`${a.name}${a.is_required ? " *" : ""}`) + 16 + textWidth(a.data_type_name));
  return { width: Math.ceil(Math.max(150, w + 2 * PAD)), height: HEADER + (attrs.length ? attrs.length * ROW + 8 : 0) };
}

// Ring layout, for a focus with many neighbours (the type in the middle, the neighbours around it)
// and for small but dense diagrams (every type on the ring). Types are grouped by layer; lines are
// straight. Same shape of result as ELK's, so the drawing code is shared.
function radialLayout(part, focus, children, layerOrder) {
  const box = Object.fromEntries(children.map((c) => [c.id, c]));
  const typeOf = Object.fromEntries(part.types.map((t) => [t.id, t]));
  const centre = focus ? box[focus] : { width: 0, height: 0 };
  const ring = children.filter((c) => c.id !== focus).sort((a, b) =>
    (layerOrder[typeOf[a.id].layer_id] - layerOrder[typeOf[b.id].layer_id]) || typeOf[a.id].name.localeCompare(typeOf[b.id].name));
  const need = ring.map((c) => Math.max(c.width, c.height) * 1.15 + 60);  // room along the ring
  const total = need.reduce((s, n) => s + n, 0);
  // ellipse twice as wide as high; perimeter ~ 2*pi*sqrt((a^2+b^2)/2)
  let b = total / (2 * Math.PI * Math.sqrt((4 + 1) / 2));
  b = Math.max(b, centre.height / 2 + 140);
  const a = Math.max(2 * b, centre.width / 2 + 260);
  let run = 0;
  const pos = {};
  ring.forEach((c, i) => {
    const angle = ((run + need[i] / 2) / total) * 2 * Math.PI - Math.PI / 2;
    run += need[i];
    pos[c.id] = { x: a * Math.cos(angle), y: b * Math.sin(angle) };
  });
  if (focus) pos[focus] = { x: 0, y: 0 };
  const placed = children.map((c) => ({ ...c, x: pos[c.id].x - c.width / 2, y: pos[c.id].y - c.height / 2 }));
  const minX = Math.min(...placed.map((c) => c.x)) - 20, minY = Math.min(...placed.map((c) => c.y)) - 20;
  placed.forEach((c) => { c.x -= minX; c.y -= minY; });
  const at = Object.fromEntries(placed.map((c) => [c.id, c]));
  const border = (c, dx, dy) => {  // where the line from the box centre in direction (dx, dy) leaves the box
    const s = Math.min(c.width / 2 / Math.max(Math.abs(dx), 1e-6), c.height / 2 / Math.max(Math.abs(dy), 1e-6));
    return { x: c.x + c.width / 2 + dx * s, y: c.y + c.height / 2 + dy * s };
  };
  const pairs = new Set(part.links.map((l) => `${l.source}|${l.target}`));
  const edges = part.links.map((l, i) => {
    const s = at[l.source], t = at[l.target];
    if (l.source === l.target) {  // a type related to itself: a small loop on the top edge
      const x = s.x + s.width - 30, y = s.y;
      return { id: `e${i}`, sections: [{ startPoint: { x: x - 16, y }, bendPoints: [{ x: x - 16, y: y - 22 }, { x: x + 16, y: y - 22 }], endPoint: { x: x + 16, y } }],
        labels: [{ x: x - 20, y: y - 40 }] };
    }
    let dx = t.x + t.width / 2 - (s.x + s.width / 2), dy = t.y + t.height / 2 - (s.y + s.height / 2);
    const len = Math.hypot(dx, dy) || 1; dx /= len; dy /= len;
    // both directions allowed: shift the two lines apart
    const off = pairs.has(`${l.target}|${l.source}`) ? 7 : 0;
    const ox = -dy * off, oy = dx * off;
    const p1 = border(s, dx, dy), p2 = border(t, -dx, -dy);
    const start = { x: p1.x + ox, y: p1.y + oy }, end = { x: p2.x + ox, y: p2.y + oy };
    // label nearer the neighbour (focus), or nearer the source so the two directions do not overlap
    const away = !focus ? 0.35 : l.source === focus ? 0.62 : 0.38;
    return { id: `e${i}`, sections: [{ startPoint: start, endPoint: end }],
      labels: [{ x: start.x + (end.x - start.x) * away - 24, y: start.y + (end.y - start.y) * away - 7 }] };
  });
  return {
    width: Math.max(...placed.map((c) => c.x + c.width)) + 20,
    height: Math.max(...placed.map((c) => c.y + c.height)) + 20,
    children: placed, edges,
  };
}

async function layout(part, showAttrs, showLabels, focus, layerOrder) {
  const children = part.types.map((t) => ({ id: t.id, ...nodeSize(t, showAttrs) }));
  if (focus && part.types.length > RADIAL_MIN) return radialLayout(part, focus, children, layerOrder);
  if (!focus && part.links.length > DENSE * part.types.length && part.types.length <= RING_MAX) {
    return radialLayout(part, null, children, layerOrder);
  }
  if (part.links.length > LAYERED_MAX) {
    // large: stress layout, then remove overlaps; lines are straight, labels go at their middle
    const edges = part.links.map((l, i) => ({ id: `e${i}`, sources: [l.source], targets: [l.target] }));
    const placed = await elk.layout({
      id: "root", children, edges,
      layoutOptions: { "elk.algorithm": "stress", "elk.stress.desiredEdgeLength": "350" },
    });
    return elk.layout({
      id: "root", edges,
      children: placed.children.map(({ id, x, y, width, height }) => ({ id, x, y, width, height })),
      layoutOptions: { "elk.algorithm": "sporeOverlap", "elk.spacing.nodeNode": "30" },
    });
  }
  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.layered.spacing.nodeNodeBetweenLayers": "80",
      "elk.spacing.nodeNode": "36",
      "elk.spacing.edgeEdge": "10",
      "elk.spacing.edgeNode": "16",
      "elk.spacing.edgeLabel": "3",
      "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
    },
    children,
    edges: part.links.map((l, i) => {
      const text = l.relationship_types.join(", ");
      return {
        id: `e${i}`, sources: [l.source], targets: [l.target],
        labels: showLabels ? [{ id: `e${i}l`, text, width: Math.ceil(textWidth(text, "11px system-ui")) + 6, height: 14 }] : [],
      };
    }),
  };
  return elk.layout(graph);
}

// ---------------------------------------------------------------- drawing
function Node({ t, box, showAttrs, focused, dim, onEnter, onLeave, onClick }) {
  const attrs = showAttrs ? t.attributes : [];
  return (
    <g transform={`translate(${box.x},${box.y})`} opacity={dim ? 0.25 : 1} style={{ cursor: "pointer" }}
      onMouseEnter={onEnter} onMouseLeave={onLeave} onClick={onClick}>
      <title>{`${t.name} (${t.layer})\nClick to focus on this type`}</title>
      <rect width={box.width} height={box.height} rx="6" fill="#ffffff"
        stroke={focused ? "#1f5fb8" : "#8a96a3"} strokeWidth={focused ? 2.5 : 1} />
      <path d={`M0 6 a6 6 0 0 1 6 -6 h${box.width - 12} a6 6 0 0 1 6 6 v${HEADER - 6} h-${box.width} z`}
        fill={`#${t.colour || "eeeeee"}`} stroke="none" />
      <line x1="0" y1={HEADER} x2={box.width} y2={HEADER} stroke="#8a96a3" strokeWidth="0.8" />
      <text x={PAD} y="16" fontSize="13" fontWeight="600" fill="#1d2733" fontFamily="system-ui, sans-serif">{t.name}</text>
      <text x={PAD} y="31" fontSize="11" fill="#5b6775" fontFamily="system-ui, sans-serif">{t.layer} · {t.entity_count} entities</text>
      {attrs.map((a, i) => (
        <g key={a.column_name} transform={`translate(0,${HEADER + 4 + i * ROW})`}>
          <title>{`${a.name}: ${a.data_type_name}${a.pick_list ? ` (${a.pick_list})` : ""}${a.is_required ? ", required" : ""}`}</title>
          <text x={PAD} y="13" fontSize="12" fill="#1d2733" fontFamily="system-ui, sans-serif"
            fontWeight={a.is_required ? 600 : 400}>{a.name}{a.is_required ? " *" : ""}</text>
          <text x={box.width - PAD} y="13" fontSize="12" fill="#5b6775" textAnchor="end"
            fontFamily="system-ui, sans-serif">{a.data_type_name}</text>
        </g>
      ))}
    </g>
  );
}

function Edge({ edge, link, names, dim, hot, showLabel }) {
  const s = edge.sections?.[0];
  if (!s) return null;
  const pts = [s.startPoint, ...(s.bendPoints || []), s.endPoint];
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ");
  const single = link.relationship_types.length === 1;
  const colour = single ? relColour(link.relationship_types[0]) : "#6b7785";
  const directed = link.relationship_types.some((c) => c !== "Association");
  // layered layouts place the label; straight lines get it at their middle
  const mid = { x: (s.startPoint.x + s.endPoint.x) / 2 - 20, y: (s.startPoint.y + s.endPoint.y) / 2 - 7 };
  const label = showLabel ? (edge.labels?.[0]?.x !== undefined ? edge.labels[0] : mid) : null;
  return (
    <g opacity={dim ? 0.12 : 1}>
      <title>{`${names[link.source]} → ${names[link.target]}: ${link.relationship_types.join(", ")}`}</title>
      <path d={d} fill="none" stroke="transparent" strokeWidth="10" />
      <path d={d} fill="none" stroke={colour} strokeWidth={hot ? 2.2 : 1.2}
        markerEnd={directed ? `url(#arrow-${single ? link.relationship_types[0] : "mixed"})` : undefined} />
      {label && (
        <text x={label.x + 3} y={label.y + 11} fontSize="11" fontFamily="system-ui, sans-serif"
          paintOrder="stroke" stroke="#ffffff" strokeWidth="3" strokeLinejoin="round">
          {link.relationship_types.map((c, i) => (
            <tspan key={c} fill={relColour(c)}>{i ? ", " : ""}{c}</tspan>
          ))}
        </text>
      )}
    </g>
  );
}

// ---------------------------------------------------------------- the screen
export default function MetamodelDiagram({ model, focus }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [layers, setLayers] = useState(null);          // chosen layer ids
  const [rels, setRels] = useState(null);              // chosen relationship type codes
  const [showAttrs, setShowAttrs] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [connected, setConnected] = useState(false);
  const [graph, setGraph] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hover, setHover] = useState(null);
  const [view, setView] = useState({ x: 20, y: 20, k: 1 });
  const [note, setNote] = useState("");
  const frame = useRef(null);
  const svgRef = useRef(null);
  const drag = useRef(null);

  useEffect(() => {
    let live = true;
    setData(null); setError(null);
    apiFetch(`/api/v1/models/${model}/metamodel/diagram`)
      .then((d) => {
        if (!live) return;
        setData(d);
        const business = d.layers.find((l) => l.code === "business") || d.layers[0];
        setLayers(business ? [business.id] : []);
        setRels(d.relationship_types.map((r) => r.code).filter((c) => !GENERIC.includes(c)));
      })
      .catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model]);

  const part = useMemo(
    () => (data && layers && rels ? scopeDiagram(data, { layers, focus, rels, connected }) : null),
    [data, layers, focus, rels, connected]);

  useEffect(() => {
    if (!part) return;
    let live = true;
    setBusy(true);
    const layerOrder = Object.fromEntries(data.layers.map((l, i) => [l.id, i]));
    layout(part, showAttrs, showLabels, focus, layerOrder)
      .then((g) => { if (live) { setGraph({ ...g, part }); fit(g); } })
      .catch((e) => live && setError(`Layout failed: ${e.message}`))
      .finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [part, showAttrs, showLabels]); // eslint-disable-line react-hooks/exhaustive-deps

  function fit(g = graph) {
    const el = frame.current;
    if (!g || !el) return;
    const w = el.clientWidth, h = el.clientHeight;
    const k = Math.min(1, (w - 40) / Math.max(g.width, 1), (h - 40) / Math.max(g.height, 1));
    setView({ k, x: (w - g.width * k) / 2, y: Math.max(20, (h - g.height * k) / 2) });
  }

  function zoomAt(factor, cx, cy) {
    setView((v) => {
      const k = Math.min(3, Math.max(0.1, v.k * factor));
      const f = k / v.k;
      return { k, x: cx - (cx - v.x) * f, y: cy - (cy - v.y) * f };
    });
  }

  // wheel zoom needs a non-passive listener so the page does not scroll
  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const onWheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [data]);

  const onDown = (e) => { if (e.button === 0) drag.current = { x: e.clientX, y: e.clientY, moved: false }; };
  const onMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) d.moved = true;
    d.x = e.clientX; d.y = e.clientY;
    setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  };
  const onUp = () => { setTimeout(() => { drag.current = null; }, 0); };

  function toggle(list, setList, value) {
    setList(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);
  }

  function chooseLayer(id) {
    if (focus) { setLayers([id]); go(`/metamodel/${model}/diagram`); return; }
    toggle(layers, setLayers, id);
  }

  function downloadSvg() {
    const svg = svgRef.current;
    if (!svg || !graph) return;
    const copy = svg.cloneNode(true);
    copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    copy.setAttribute("width", graph.width + 40);
    copy.setAttribute("height", graph.height + 40);
    copy.setAttribute("viewBox", `-20 -20 ${graph.width + 40} ${graph.height + 40}`);
    copy.querySelector("[data-viewport]").setAttribute("transform", "");
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    Object.entries({ x: -20, y: -20, width: graph.width + 40, height: graph.height + 40, fill: "#ffffff" })
      .forEach(([k, v]) => bg.setAttribute(k, v));
    copy.insertBefore(bg, copy.firstChild);
    const blob = new Blob([new XMLSerializer().serializeToString(copy)], { type: "image/svg+xml" });
    const a = document.createElement("a");
    const focusName = focus && data.entity_types.find((t) => t.id === focus)?.name;
    a.href = URL.createObjectURL(blob);
    a.download = `${data.model.name} - ${focusName || "metamodel"}.svg`.replace(/[\\/:*?"<>|]/g, "_");
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function copyMermaid() {
    const q = new URLSearchParams();
    if (focus) q.set("type", focus); else layers.forEach((l) => q.append("layer", l));
    rels.forEach((r) => q.append("rel", r));
    if (connected) q.set("connected", "true");
    if (!showAttrs) q.set("attributes", "false");
    try {
      const out = await apiFetch(`/api/v1/models/${model}/metamodel/mermaid?${q}`);
      await navigator.clipboard.writeText(out.mermaid);
      setNote("Mermaid ER diagram copied: paste it into mermaid.live, GitHub, Confluence or draw.io (Arrange > Insert > Mermaid).");
    } catch (e) {
      setNote(`Could not copy: ${e.message}`);
    }
    setTimeout(() => setNote(""), 6000);
  }

  if (error) return <p className="status bad">{error}</p>;
  if (!data || !layers || !rels) return <p>Loading the metamodel...</p>;

  const names = Object.fromEntries(data.entity_types.map((t) => [t.id, t.name]));
  const focusType = focus && data.entity_types.find((t) => t.id === focus);
  // draw what was laid out (graph.part); the counts above it describe the current choice
  const links = graph?.part.links || [];
  const linkOf = Object.fromEntries((graph?.edges || []).map((e, i) => [e.id, links[i]]));
  const near = hover ? new Set([hover, ...links.filter((l) => l.source === hover || l.target === hover)
    .flatMap((l) => [l.source, l.target])]) : null;
  const big = part && (part.types.length > 45 || part.links.length > 250);

  return (
    <div className="er">
      <div className="er-bar">
        <label>Focus on
          <select value={focus || ""} onChange={(e) => go(`/metamodel/${model}/diagram${e.target.value ? `/${e.target.value}` : ""}`)}>
            <option value="">(layers below)</option>
            {data.layers.map((l) => (
              <optgroup key={l.id} label={l.name}>
                {data.entity_types.filter((t) => t.layer_id === l.id).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        {focusType && <>
          <a href={`#/metamodel/${model}/type/${focus}`}>{focusType.name} details</a>
          <button onClick={() => go(`/metamodel/${model}/diagram`)}>Clear focus</button>
        </>}
        <span className="er-spacer" />
        <label><input type="checkbox" checked={showAttrs} onChange={(e) => setShowAttrs(e.target.checked)} /> Attributes</label>
        <label><input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /> Line labels</label>
        <button onClick={() => fit()}>Fit</button>
        <button onClick={() => zoomAt(1.25, frame.current.clientWidth / 2, frame.current.clientHeight / 2)}>+</button>
        <button onClick={() => zoomAt(0.8, frame.current.clientWidth / 2, frame.current.clientHeight / 2)}>−</button>
        <button onClick={downloadSvg}>Download SVG</button>
        <button onClick={copyMermaid}>Copy as Mermaid</button>
      </div>

      <div className={`er-chips${focus ? " off" : ""}`}>
        <span className="quiet">Layers{focus ? " (choose one to leave the focus)" : ""}:</span>
        {data.layers.map((l) => (
          <button key={l.id} className={`chip${!focus && layers.includes(l.id) ? " on" : ""}`} onClick={() => chooseLayer(l.id)}>
            <span className="swatch" style={{ background: `#${l.colour}` }} /> {l.name}
          </button>
        ))}
        {!focus && <>
          <button className="chip" onClick={() => setLayers(data.layers.map((l) => l.id))}>All</button>
          <label className="quiet"><input type="checkbox" checked={connected} onChange={(e) => setConnected(e.target.checked)} /> plus connected types from other layers</label>
        </>}
      </div>
      <div className="er-chips">
        <span className="quiet">Relationships:</span>
        {data.relationship_types.map((r) => (
          <button key={r.code} title={`${r.name}: ${r.verb}`} className={`chip${rels.includes(r.code) ? " on" : ""}`}
            style={rels.includes(r.code) ? { borderColor: relColour(r.code), color: relColour(r.code) } : undefined}
            onClick={() => toggle(rels, setRels, r.code)}>
            <span className="er-line" style={{ background: relColour(r.code) }} /> {r.name}
          </button>
        ))}
      </div>

      <p className="quiet er-info">
        {part && `${part.types.length} entity types, ${part.links.length} lines`}
        {busy && " · laying out..."}

        {big && " · a large diagram: choose a layer, fewer relationship types, or focus on one type"}
        {note && <strong> · {note}</strong>}
      </p>

      <div className="er-frame" ref={frame} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
        {part && !part.types.length && <p className="quiet er-empty">Nothing to show: choose a layer or a type.</p>}
        <svg ref={svgRef} width="100%" height="100%">
          <defs>
            {[...Object.keys(REL_COLOURS), "mixed"].map((c) => (
              <marker key={c} id={`arrow-${c}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill={c === "mixed" ? "#6b7785" : relColour(c)} />
              </marker>
            ))}
          </defs>
          <g data-viewport="" transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {graph?.edges.map((e) => {
              const l = linkOf[e.id];
              if (!l) return null;
              const touches = hover && (l.source === hover || l.target === hover);
              return <Edge key={e.id} edge={e} link={l} names={names} dim={hover && !touches} hot={touches} showLabel={showLabels} />;
            })}
            {graph?.children.map((box) => {
              const t = data.entity_types.find((x) => x.id === box.id);
              return t && (
                <Node key={box.id} t={t} box={box} showAttrs={showAttrs} focused={box.id === focus}
                  dim={near && !near.has(box.id)}
                  onEnter={() => setHover(box.id)} onLeave={() => setHover(null)}
                  onClick={() => { if (!drag.current?.moved) go(`/metamodel/${model}/diagram/${box.id}`); }} />
              );
            })}
          </g>
        </svg>
      </div>
      <p className="quiet er-info">
        Boxes are entity types with their attributes (* required; every entity also has a display ID, name,
        description, parent, status and history). Lines are the relationships the metamodel allows, from source to
        target, combined per pair of types. Click a box to focus on it; drag to move; scroll to zoom.
      </p>
    </div>
  );
}
