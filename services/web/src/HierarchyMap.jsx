// Hierarchy map: the entities of one type as nested boxes, parents holding their parts, for example
// the capability map from level 1 down to level 4. Colour the boxes by domain colour or by one
// attribute (a heat map: maturity, criticality, lifecycle...). Click a box to open its entity page.
// Opens in draw.io (nested containers, D256); saves as SVG, PNG and CSV (one row per entity with its path).
import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "./auth";
import { downloadCsv, downloadPng, downloadSvg } from "./exporting";
import { PictureActions } from "./DrawnView";
import { textWidth } from "./MetamodelDiagram";
import usePanZoom from "./usePanZoom";
import { elementTypes } from "./elements.js";

const go = (path) => { window.location.hash = path; };
const LEAF_W = 168, LEAF_H = 30, HEAD = 28, PAD = 8, GAP = 6, ROOT_GAP = 16, ROW_MAX = 2200;
const FONT = "12px system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
const BOLD = "600 12px system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
// light to strong; enough for pick lists of up to 8 values, numbers are spread over it
const SCALE = ["ef8a87", "f4a582", "f8bf80", "fbd49c", "b9d7f5", "93c3ef", "a9dca9", "7cc47c"];   // low to high: red, orange, blue, green (owner, 10 Nov 2026; as Views.jsx HEAT)
const NUMERIC = new Set(["integer", "decimal", "currency", "percent"]);

function shorten(text, width, font) {
  if (textWidth(text, font) <= width) return text;
  let s = text;
  while (s.length > 3 && textWidth(`${s}…`, font) > width) s = s.slice(0, -1);
  return `${s}…`;
}

// sizes first (bottom up), then positions (top down); levels below `levels` are counted, not drawn
function layoutTree(roots, levels) {
  const size = (n, level) => {
    const kids = level < levels ? n.children : [];
    n.drawKids = kids;
    if (!kids.length) { n.w = LEAF_W; n.h = LEAF_H; return; }
    kids.forEach((c) => size(c, level + 1));
    n.w = Math.max(LEAF_W + 2 * PAD, ...kids.map((c) => c.w + 2 * PAD));
    n.h = HEAD + kids.reduce((s, c) => s + c.h + GAP, 0) + PAD - GAP;
    kids.forEach((c) => { if (!c.drawKids.length) c.w = n.w - 2 * PAD; });   // leaves fill their parent
  };
  const place = (n, x, y) => {
    n.x = x; n.y = y;
    let cy = y + HEAD;
    for (const c of n.drawKids) { place(c, x + PAD, cy); cy += c.h + GAP; }
  };
  roots.forEach((r) => size(r, 1));
  let x = 0, y = 0, rowH = 0;
  for (const r of roots) {
    if (x > 0 && x + r.w > ROW_MAX) { x = 0; y += rowH + ROOT_GAP; rowH = 0; }
    place(r, x, y);
    x += r.w + ROOT_GAP; rowH = Math.max(rowH, r.h);
  }
  const all = [];
  const walk = (n) => { all.push(n); n.drawKids.forEach(walk); };
  roots.forEach(walk);
  return { all, width: Math.max(1, ...all.map((n) => n.x + n.w)), height: Math.max(1, ...all.map((n) => n.y + n.h)) };
}

export default function HierarchyMap({ model }) {
  const [types, setTypes] = useState(null);
  const [typeId, setTypeId] = useState("");
  const [table, setTable] = useState(null);
  const [error, setError] = useState(null);
  const [levels, setLevels] = useState(3);
  const [colourBy, setColourBy] = useState("");
  const svgRef = useRef(null);
  const { frame, view, fit, zoomCentre, handlers, wasDrag } = usePanZoom([table]);

  useEffect(() => {
    let live = true;
    apiFetch(`/api/v1/models/${model}/metamodel`).then((mm) => {
      if (!live) return;
      const list = mm.domains.flatMap((l) => elementTypes(l).map((t) => ({ ...t, colour: l.colour })))
        .filter((t) => t.entity_count > 0).sort((a, b) => b.entity_count - a.entity_count);
      setTypes(list);
      setTypeId((list.find((t) => t.code === "Capability") || list[0])?.id || "");
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model]);

  useEffect(() => {
    if (!typeId) return undefined;
    let live = true;
    setTable(null);
    apiFetch(`/api/v1/models/${model}/entity-types/${typeId}/table`).then((t) => {
      if (!live) return;
      setTable(t);
      const preferred = t.columns.find((c) => /maturity/i.test(c.name)) || null;
      setColourBy(preferred ? preferred.code : "");
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model, typeId]);

  const tree = useMemo(() => {
    if (!table) return null;
    const byId = Object.fromEntries(table.rows.map((r) => [r.id, { ...r, children: [] }]));
    const roots = [];
    for (const n of Object.values(byId)) (n.parent_id && byId[n.parent_id] ? byId[n.parent_id].children : roots).push(n);
    const sortRec = (list) => { list.sort((a, b) => String(a.display_id).localeCompare(String(b.display_id), undefined, { numeric: true })); list.forEach((n) => sortRec(n.children)); };
    sortRec(roots);
    const depthOf = (n) => 1 + Math.max(0, ...n.children.map(depthOf));
    const maxDepth = Math.max(1, ...roots.map(depthOf));
    const count = (n) => n.children.reduce((s, c) => s + 1 + count(c), 0);
    Object.values(byId).forEach((n) => { n.below = count(n); });
    return { roots, maxDepth };
  }, [table]);

  const placed = useMemo(() => (tree ? layoutTree(tree.roots, Math.min(levels, tree.maxDepth)) : null), [tree, levels]);
  useEffect(() => { if (placed) fit(placed.width, placed.height, 1); }, [placed]); // eslint-disable-line react-hooks/exhaustive-deps

  // colours: the type's domain colour, or one per value of the chosen attribute
  const colouring = useMemo(() => {
    if (!table || !colourBy) return null;
    const col = table.columns.find((c) => c.code === colourBy);
    const values = [...new Set(table.rows.map((r) => r.values[colourBy]).filter((v) => v !== undefined && v !== ""))];
    const numeric = col && NUMERIC.has(col.data_type);
    values.sort((a, b) => (numeric ? Number(a) - Number(b) : String(a).localeCompare(String(b), undefined, { numeric: true })));
    const map = {};
    values.forEach((v, i) => { map[v] = SCALE[values.length === 1 ? 0 : Math.round((i * (SCALE.length - 1)) / (values.length - 1))]; });
    return { name: col?.name, values, map };
  }, [table, colourBy]);

  if (error) return <p className="status bad">{error}</p>;
  if (!types) return <p className="quiet">Loading...</p>;
  const type = types.find((t) => t.id === typeId);
  const fill = (n) => {
    if (!colouring) return type?.colour || "eeeeee";
    const v = n.values[colourBy];
    return v === undefined || v === "" ? "f1f3f5" : colouring.map[v];
  };
  const title = `${table?.entity_type.name || "hierarchy"} map${colouring ? ` by ${colouring.name}` : ""}`;

  // nested boxes: each entity holds its parts (D407, D408)
  function picture() {
    if (!placed) return null;
    return { title, nodes: placed.all.map((n) => ({
      id: n.id, label: n.name, x: n.x, y: n.y, w: n.w, h: n.h,
      fill: fill(n), heatFill: colouring ? fill(n) : null, container: n.drawKids.length > 0, bold: n.drawKids.length > 0,
      parent: n.parent_id && placed.all.some((p) => p.id === n.parent_id) ? n.parent_id : null,
      ea_type: table.entity_type.name, ea_id: n.id, ea_domain: table.entity_type.domain,
      keepSize: true,                 // the nesting is laid out already: sizes and places as drawn
    })), edges: [] };
  }
  function exportCsv() {
    const rows = [["Level", "Path", "Display ID", "Name", colouring?.name || "Colour"]];
    const walk = (n, path, level) => {
      rows.push([level, [...path, n.name].join(" > "), n.display_id, n.name, colouring ? n.values[colourBy] ?? "" : ""]);
      n.children.forEach((c) => walk(c, [...path, n.name], level + 1));
    };
    tree.roots.forEach((r) => walk(r, [], 1));
    downloadCsv(rows, title);
  }

  return (
    <div className="er">
      <div className="er-bar">
        <label>Entity type
          <select value={typeId} onChange={(e) => setTypeId(e.target.value)}>
            {types.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.entity_count})</option>)}
          </select>
        </label>
        {tree && (
          <label>Levels
            <select value={Math.min(levels, tree.maxDepth)} onChange={(e) => setLevels(Number(e.target.value))}>
              {Array.from({ length: tree.maxDepth }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </label>
        )}
        {table && (
          <label>Colour by
            <select value={colourBy} onChange={(e) => setColourBy(e.target.value)}>
              <option value="">domain colour</option>
              {table.columns.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
            </select>
          </label>
        )}
        <span className="er-spacer" />
        <button onClick={() => placed && fit(placed.width, placed.height, 1)}>Fit</button>
        <button onClick={() => zoomCentre(1.25)}>+</button>
        <button onClick={() => zoomCentre(0.8)}>−</button>
        <PictureActions model={model} picture={picture} images={false} disabled={!placed} />
        <button onClick={() => placed && downloadSvg(svgRef.current, placed.width, placed.height, title)}>SVG</button>
        <button onClick={() => placed && downloadPng(svgRef.current, placed.width, placed.height, title)}>PNG</button>
        <button onClick={exportCsv} disabled={!tree}>CSV</button>
      </div>
      {colouring && (
        <div className="er-chips">
          <span className="quiet">{colouring.name}:</span>
          {colouring.values.map((v) => <span key={v} className="legend-chip"><span className="swatch" style={{ background: `#${colouring.map[v]}` }} /> {v}</span>)}
          <span className="legend-chip"><span className="swatch" style={{ background: "#f1f3f5" }} /> not set</span>
        </div>
      )}
      <p className="quiet er-info">
        {!table ? "Loading..." : `${table.rows.length} ${table.entity_type.name} entities, ${tree.roots.length} at the top, ${tree.maxDepth} levels`}
        {tree && tree.maxDepth === 1 && " · this type has no parent hierarchy in this model"}
      </p>
      <div className="er-frame graph-frame" ref={frame} {...handlers}>
        <svg ref={svgRef} width="100%" height="100%">
          <g data-viewport="" transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {placed?.all.map((n) => {
              const container = n.drawKids.length > 0;
              const hidden = !container && n.below > 0 ? ` +${n.below}` : "";
              return (
                <g key={n.id} transform={`translate(${n.x},${n.y})`} style={{ cursor: "pointer" }}
                  onClick={(e) => { e.stopPropagation(); if (!wasDrag()) go(`/metamodel/${model}/entity/${n.id}`); }}>
                  <title>{`${n.name} (${n.display_id})${colouring ? `\n${colouring.name}: ${n.values[colourBy] ?? "not set"}` : ""}${n.below ? `\n${n.below} parts below` : ""}\nClick: open its page`}</title>
                  <rect width={n.w} height={n.h} rx="5" fill={`#${fill(n)}`} stroke={container ? "#8a96a3" : "#b4bec9"} strokeWidth={container ? 1.2 : 0.8} />
                  <text x="8" y={container ? 18 : 19} fontSize="12" fontWeight={container ? 600 : 400} fill="#1d2733">
                    {shorten(n.name, n.w - 16 - textWidth(hidden, FONT), container ? BOLD : FONT)}
                    {hidden && <tspan fill="#5b6775" fontSize="10">{hidden}</tspan>}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <p className="quiet er-info">
        Parents hold their parts; +n counts the parts on levels not shown. Click a box to open its entity page. In draw.io the picture keeps
        the nesting (move a parent and its parts move with it).
      </p>
    </div>
  );
}
