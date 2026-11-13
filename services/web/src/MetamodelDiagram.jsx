// The metamodel as an ER diagram, generated from the database every time it opens.
//   #/metamodel/<model>/diagram           chosen domains (Business by default)
//   #/metamodel/<model>/diagram/<typeId>  one entity type and every type it may connect to
// Boxes are entity types with their attributes; lines are the allowed relationships, combined per
// source and target type and labelled with the relationship types. Layout by ELK (elkjs), run in a
// web worker so the screen stays responsive. Which layout:
//   focus on a type with more than RADIAL_MIN types shown   ring around the focused type
//   more than DENSE lines per type (up to RING_MAX types)    every type on a ring, straight lines
//   up to LAYERED_MAX lines                                  ELK layered, right-angled lines
//   otherwise                                                ELK stress, straight lines (layered takes minutes)
// The choice of what to show follows the same rules as services/api/eax/diagram.py (scope).
// Domain view (D124): each domain is a horizontal band, in the metamodel's domain order, with its types
// inside; lines cross between the bands. ELK layered with one partition per domain when the diagram is
// small enough (right-angled lines), otherwise rows of boxes per band with straight lines.
import { useEffect, useMemo, useRef, useState } from "react";
import ELK from "elkjs/lib/elk-api.js";
import elkWorkerUrl from "elkjs/lib/elk-worker.min.js?url";
import { apiFetch } from "./auth";
import { PictureActions } from "./DrawnView";

const GENERIC = ["Association", "Specialization"];
const REL_COLOURS = {
  Composition: "#1f5fb8", Aggregation: "#5b8fd6", Assignment: "#7a3db8", Realization: "#1e7b3c",
  Serving: "#c26a00", Access: "#8a6d00", Influence: "#b3261e", Association: "#6b7785",
  Triggering: "#00838f", Flow: "#2e9e8f", Specialization: "#4a4a4a",
};
export const relColour = (code) => REL_COLOURS[code] || "#6b7785";
const FONT = "12px system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
const BOLD = "600 13px system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
const HEADER = 38, ROW = 18, PAD = 10;
const LAYERED_MAX = 200, RADIAL_MIN = 10, DENSE = 4, RING_MAX = 60;
export const elk = new ELK({ workerUrl: elkWorkerUrl });
const go = (path) => { window.location.hash = path; };

let measureCtx;
export function textWidth(text, font = FONT) {
  measureCtx ||= document.createElement("canvas").getContext("2d");
  measureCtx.font = font;
  return measureCtx.measureText(text).width;
}

// a relationship type on a line with its multiplicity, source end first (D395): "Association 1 : 0..*"
export function multText(l, i) {
  const sm = (l.source_multiplicities || [])[i] || "", tm = (l.target_multiplicities || [])[i] || "";
  return sm || tm ? ` ${sm || "*"} : ${tm || "*"}` : "";
}
// with the attributes of that allowed relationship only (D564): "Association [Connection protocol, Port]"
const mapAttrs = (l, i) => ((l.mapping_attributes || [])[i] ? ` [${l.mapping_attributes[i]}]` : "");
export const linkText = (l) => l.relationship_types.map((c, i) => c + multText(l, i) + mapAttrs(l, i)).join(", ");

// ---------------------------------------------------------------- what to show (mirrors eax/diagram.py)
export function scopeDiagram(data, { domains, focus, rels, connected }) {
  const keep = new Set(rels);
  let links = data.links
    .map((l) => {
      const at = l.relationship_types.map((c, i) => i).filter((i) => keep.has(l.relationship_types[i]));
      const pick = (arr) => at.map((i) => (arr || [])[i] || "");
      return { ...l, relationship_types: pick(l.relationship_types), source_multiplicities: pick(l.source_multiplicities),
        target_multiplicities: pick(l.target_multiplicities), mapping_attributes: pick(l.mapping_attributes) };
    })
    .filter((l) => l.relationship_types.length);
  // a derived type and its base (R2.9, D629): ArchiMate's Specialization, always shown
  links = links.concat((data.specializations || []).map((x) => ({ source: x.source, target: x.target, specialization: true,
    relationship_types: ["Specialization"], source_multiplicities: [""], target_multiplicities: [""], mapping_attributes: [""] })));
  let ids;
  if (focus) {
    links = links.filter((l) => l.source === focus || l.target === focus);
    ids = new Set([focus, ...links.map((l) => l.source), ...links.map((l) => l.target)]);
  } else {
    const inside = new Set(data.entity_types.filter((t) => !domains.length || domains.includes(t.domain_id)).map((t) => t.id));
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
  let w = Math.max(textWidth(t.name, BOLD), textWidth(`${t.domain} · ${t.entity_count} entities`, FONT));
  for (const a of attrs) w = Math.max(w, textWidth(`${a.name}${a.is_required ? " *" : ""}`) + 16 + textWidth(a.data_type_name));
  return { width: Math.ceil(Math.max(150, w + 2 * PAD)), height: HEADER + (attrs.length ? attrs.length * ROW + 8 : 0) };
}

// Ring layout, for a focus with many neighbours (the type in the middle, the neighbours around it)
// and for small but dense diagrams (every type on the ring). Types are grouped by domain; lines are
// straight. Same shape of result as ELK's, so the drawing code is shared.
function radialLayout(part, focus, children, domainOrder) {
  const box = Object.fromEntries(children.map((c) => [c.id, c]));
  const typeOf = Object.fromEntries(part.types.map((t) => [t.id, t]));
  const centre = focus ? box[focus] : { width: 0, height: 0 };
  const ring = children.filter((c) => c.id !== focus).sort((a, b) =>
    (domainOrder[typeOf[a.id].domain_id] - domainOrder[typeOf[b.id].domain_id]) || typeOf[a.id].name.localeCompare(typeOf[b.id].name));
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

async function layout(part, showAttrs, showLabels, focus, domainOrder) {
  const children = part.types.map((t) => ({ id: t.id, ...nodeSize(t, showAttrs) }));
  if (focus && part.types.length > RADIAL_MIN) return radialLayout(part, focus, children, domainOrder);
  if (!focus && part.links.length > DENSE * part.types.length && part.types.length <= RING_MAX) {
    return radialLayout(part, null, children, domainOrder);
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
      const text = linkText(l);
      return {
        id: `e${i}`, sources: [l.source], targets: [l.target],
        labels: showLabels ? [{ id: `e${i}l`, text, width: Math.ceil(textWidth(text, "11px system-ui")) + 6, height: 14 }] : [],
      };
    }),
  };
  return elk.layout(graph);
}

// ---------------------------------------------------------------- domain view: one band per domain
export const BAND_GUTTER = 150;   // room at the left of each band for the domain's name
const BAND_PAD = 22, BAND_GAP = 26, ROW_GAP = 34, COL_GAP = 40, ROW_MAX = 1700;

async function bandLayout(part, showAttrs, showLabels, domainOrder) {
  const children = part.types.map((t) => ({ id: t.id, ...nodeSize(t, showAttrs) }));
  const typeOf = Object.fromEntries(part.types.map((t) => [t.id, t]));
  if (part.links.length <= LAYERED_MAX) {
    try {
      const g = await elk.layout({
        id: "root",
        layoutOptions: {
          "elk.algorithm": "layered",
          "elk.direction": "DOWN",
          "elk.edgeRouting": "ORTHOGONAL",
          "elk.partitioning.activate": "true",
          "elk.layered.spacing.nodeNodeBetweenLayers": String(2 * BAND_PAD + BAND_GAP + 20),
          "elk.spacing.nodeNode": "36",
          "elk.spacing.edgeEdge": "10",
          "elk.spacing.edgeNode": "16",
          "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
        },
        children: children.map((c) => ({ ...c, layoutOptions: { "elk.partitioning.partition": String(domainOrder[typeOf[c.id].domain_id] ?? 0) } })),
        edges: part.links.map((l, i) => {
          const text = linkText(l);
          return { id: `e${i}`, sources: [l.source], targets: [l.target],
            labels: showLabels ? [{ id: `e${i}l`, text, width: Math.ceil(textWidth(text, "11px system-ui")) + 6, height: 14 }] : [] };
        }),
      });
      return shiftRight(g, BAND_GUTTER);
    } catch { /* fall through to rows */ }
  }
  // rows of boxes per band (large diagrams): straight lines, labels at their middle
  const byDomain = {};
  for (const c of children) (byDomain[typeOf[c.id].domain_id] ||= []).push(c);
  const order = Object.keys(byDomain).sort((a, b) => (domainOrder[a] ?? 0) - (domainOrder[b] ?? 0));
  let y = BAND_PAD;
  const placed = [];
  for (const domain of order) {
    const row = byDomain[domain].sort((a, b) => typeOf[a.id].name.localeCompare(typeOf[b.id].name));
    let x = BAND_GUTTER, rowH = 0;
    for (const c of row) {
      if (x > BAND_GUTTER && x + c.width > BAND_GUTTER + ROW_MAX) { x = BAND_GUTTER; y += rowH + ROW_GAP; rowH = 0; }
      placed.push({ ...c, x, y });
      x += c.width + COL_GAP;
      rowH = Math.max(rowH, c.height);
    }
    y += rowH + 2 * BAND_PAD + BAND_GAP;
  }
  const at = Object.fromEntries(placed.map((c) => [c.id, c]));
  const pairs = new Set(part.links.map((l) => `${l.source}|${l.target}`));
  const edges = part.links.map((l, i) => {
    const sb = at[l.source], tb = at[l.target];
    if (l.source === l.target) {
      const lx = sb.x + sb.width - 30, ly = sb.y;
      return { id: `e${i}`, sections: [{ startPoint: { x: lx - 16, y: ly }, bendPoints: [{ x: lx - 16, y: ly - 18 }, { x: lx + 16, y: ly - 18 }], endPoint: { x: lx + 16, y: ly } }],
        labels: [{ x: lx - 20, y: ly - 34 }] };
    }
    return { id: `e${i}`, sections: [straightSection(sb, tb, pairs.has(`${l.target}|${l.source}`) ? 7 : 0)], labels: [] };
  });
  return {
    width: Math.max(...placed.map((c) => c.x + c.width), 400) + 20,
    height: y,
    children: placed, edges,
  };
}

function shiftRight(g, dx) {
  const mv = (p) => ({ ...p, x: p.x + dx });
  return {
    ...g, width: g.width + dx,
    children: g.children.map(mv),
    edges: (g.edges || []).map((e) => ({ ...e,
      sections: (e.sections || []).map((sec) => ({ ...sec, startPoint: mv(sec.startPoint), endPoint: mv(sec.endPoint), bendPoints: (sec.bendPoints || []).map(mv) })),
      labels: (e.labels || []).map((lb) => (lb.x !== undefined ? mv(lb) : lb)) })),
  };
}

// The bands to draw behind the boxes: one per domain, from its highest box to its lowest, the full width
export function bandsOf(boxes, types, domains, width) {
  const typeOf = Object.fromEntries(types.map((t) => [t.id, t]));
  const out = [];
  for (const l of domains) {
    const inside = boxes.filter((b) => typeOf[b.id]?.domain_id === l.id);
    if (!inside.length) continue;
    const top = Math.min(...inside.map((b) => b.y)) - BAND_PAD;
    const bottom = Math.max(...inside.map((b) => b.y + b.height)) + BAND_PAD;
    out.push({ id: l.id, name: l.name, colour: l.colour || "eeeeee", x: 0, y: top, width, height: bottom - top, count: inside.length });
  }
  return out;
}

// A straight line between two boxes, leaving each box at its border (used after a box is dragged)
export function straightSection(s, t, offset = 0) {
  const sc = { x: s.x + s.width / 2, y: s.y + s.height / 2 }, tc = { x: t.x + t.width / 2, y: t.y + t.height / 2 };
  let dx = tc.x - sc.x, dy = tc.y - sc.y;
  const len = Math.hypot(dx, dy) || 1; dx /= len; dy /= len;
  const border = (c, b, ux, uy) => {
    const k = Math.min(b.width / 2 / Math.max(Math.abs(ux), 1e-6), b.height / 2 / Math.max(Math.abs(uy), 1e-6));
    return { x: c.x + ux * k - dy * offset, y: c.y + uy * k + dx * offset };
  };
  return { startPoint: border(sc, s, dx, dy), endPoint: border(tc, t, -dx, -dy) };
}

const xml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// The diagram as a .drawio file (uncompressed XML): opens in the hosted draw.io and the desktop app.
// Each box carries ea_type (the entity type's code) and ea_id (its guid) as shape data, the same tags
// our diagrams use, so later phases can read the file back.
export function drawioXml(title, boxes, links, types, showAttrs, bands = []) {
  const byId = Object.fromEntries(types.map((t) => [t.id, t]));
  const cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>'];
  // domain view: the domain bands first, so they sit behind the boxes
  bands.forEach((b, i) => cells.push(
    `<mxCell id="band_${i}" value="${xml(b.name)}" style="rounded=0;whiteSpace=wrap;html=1;fillColor=#${b.colour};opacity=35;strokeColor=#${b.colour};` +
    `align=left;verticalAlign=top;spacingLeft=12;spacingTop=8;fontStyle=1;fontSize=14;" vertex="1" parent="1">` +
    `<mxGeometry x="${Math.round(b.x)}" y="${Math.round(b.y)}" width="${Math.round(b.width)}" height="${Math.round(b.height)}" as="geometry"/></mxCell>`));
  for (const b of boxes) {
    const t = byId[b.id];
    if (!t) continue;
    const attrs = showAttrs ? t.attributes.map((a) => `${xml(a.name)}${a.is_required ? " *" : ""}: <i>${xml(a.data_type_name)}</i>`).join("<br>") : "";
    const label = `<b>${xml(t.name)}</b><br><font style="font-size:10px">${xml(t.domain)}</font>` + (attrs ? `<hr>${attrs}` : "");
    cells.push(
      `<UserObject id="t_${b.id}" label="${xml(label)}" ea_type="${xml(t.code)}" ea_id="${b.id}" ea_domain="${xml(t.domain)}">` +
      `<mxCell style="rounded=1;arcSize=4;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacingLeft=8;spacingTop=4;` +
      `fillColor=#${t.colour || "eeeeee"};strokeColor=#8a96a3;fontSize=12;" vertex="1" parent="1">` +
      `<mxGeometry x="${Math.round(b.x)}" y="${Math.round(b.y)}" width="${Math.round(b.width)}" height="${Math.round(b.height)}" as="geometry"/>` +
      "</mxCell></UserObject>");
  }
  links.forEach((l, i) => {
    const single = l.relationship_types.length === 1;
    const colour = (single ? relColour(l.relationship_types[0]) : "#6b7785").slice(1);
    const arrow = l.relationship_types.some((c) => c !== "Association") ? "block" : "none";
    cells.push(
      `<mxCell id="r_${i}" value="${xml(linkText(l))}" ` +
      `style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=${arrow};endFill=1;strokeColor=#${colour};fontSize=10;fontColor=#${colour};labelBackgroundColor=#ffffff;" ` +
      `edge="1" parent="1" source="t_${l.source}" target="t_${l.target}"><mxGeometry relative="1" as="geometry"/></mxCell>`);
  });
  return '<mxfile host="EA Explorer" type="device">' +
    `<diagram id="metamodel" name="${xml(title)}"><mxGraphModel grid="1" gridSize="10" page="0"><root>` +
    cells.join("") + "</root></mxGraphModel></diagram></mxfile>";
}

export function saveBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename.replace(/[\\/:*?"<>|]/g, "_");
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ---------------------------------------------------------------- drawing
function Node({ t, box, showAttrs, focused, dim, onEnter, onLeave, onClick, onGrab }) {
  const attrs = showAttrs ? t.attributes : [];
  return (
    <g transform={`translate(${box.x},${box.y})`} opacity={dim ? 0.25 : 1} style={{ cursor: "move" }}
      onMouseEnter={onEnter} onMouseLeave={onLeave} onClick={onClick} onMouseDown={onGrab}>
      <title>{`${t.name} (${t.domain})\nDrag to move; click to focus on this type`}</title>
      <rect width={box.width} height={box.height} rx="6" fill="#ffffff"
        stroke={focused ? "#1f5fb8" : "#8a96a3"} strokeWidth={focused ? 2.5 : 1} />
      <path d={`M0 6 a6 6 0 0 1 6 -6 h${box.width - 12} a6 6 0 0 1 6 6 v${HEADER - 6} h-${box.width} z`}
        fill={`#${t.colour || "eeeeee"}`} stroke="none" />
      <line x1="0" y1={HEADER} x2={box.width} y2={HEADER} stroke="#8a96a3" strokeWidth="0.8" />
      <text x={PAD} y="16" fontSize="13" fontWeight="600" fill="#1d2733" fontFamily="system-ui, sans-serif">{t.name}</text>
      <text x={PAD} y="31" fontSize="11" fill="#5b6775" fontFamily="system-ui, sans-serif">{t.domain} · {t.entity_count} entities</text>
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
      <title>{`${names[link.source]} → ${names[link.target]}: ${linkText(link)}`}</title>
      <path d={d} fill="none" stroke="transparent" strokeWidth="10" />
      <path d={d} fill="none" stroke={colour} strokeWidth={hot ? 2.2 : 1.2}
        markerEnd={directed ? `url(#arrow-${single ? link.relationship_types[0] : "mixed"})` : undefined} />
      {label && (
        <text x={label.x + 3} y={label.y + 11} fontSize="11" fontFamily="system-ui, sans-serif"
          paintOrder="stroke" stroke="#ffffff" strokeWidth="3" strokeLinejoin="round">
          {link.relationship_types.map((c, i) => (
            <tspan key={c} fill={relColour(c)}>{i ? ", " : ""}{c}{multText(link, i)}</tspan>
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
  const [domains, setDomains] = useState(null);          // chosen domain ids
  const [rels, setRels] = useState(null);              // chosen relationship type codes
  const [showAttrs, setShowAttrs] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [connected, setConnected] = useState(false);
  const [arrange, setArrange] = useState(() => { try { return localStorage.getItem("eax-er-arrange") || "free"; } catch { return "free"; } });
  const [graph, setGraph] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hover, setHover] = useState(null);
  const [view, setView] = useState({ x: 20, y: 20, k: 1 });
  const [note, setNote] = useState("");
  const [moved, setMoved] = useState({});            // boxes dragged by hand: id -> {x, y} offset
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
        const business = d.domains.find((l) => l.code === "business") || d.domains[0];
        setDomains(business ? [business.id] : []);
        setRels(d.relationship_types.map((r) => r.code).filter((c) => !GENERIC.includes(c)));
      })
      .catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model]);

  const part = useMemo(
    () => (data && domains && rels ? scopeDiagram(data, { domains, focus, rels, connected }) : null),
    [data, domains, focus, rels, connected]);

  useEffect(() => {
    if (!part) return;
    let live = true;
    setBusy(true);
    const domainOrder = Object.fromEntries(data.domains.map((l, i) => [l.id, i]));
    (arrange === "domains" ? bandLayout(part, showAttrs, showLabels, domainOrder) : layout(part, showAttrs, showLabels, focus, domainOrder))
      .then((g) => { if (live) { setGraph({ ...g, part }); setMoved({}); fit(g); } })
      .catch((e) => live && setError(`Layout failed: ${e.message}`))
      .finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [part, showAttrs, showLabels, arrange]); // eslint-disable-line react-hooks/exhaustive-deps

  function chooseArrange(a) {
    setArrange(a);
    // a domain view of one domain says little: show them all (the chips still narrow it)
    if (a === "domains" && !focus && data && domains && domains.length <= 1) setDomains(data.domains.map((l) => l.id));
    try { localStorage.setItem("eax-er-arrange", a); } catch { /* the choice is only for this visit */ }
  }

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

  const onDown = (e) => { if (e.button === 0 && !drag.current) drag.current = { x: e.clientX, y: e.clientY, moved: false }; };
  const grab = (id) => (e) => {   // a box: dragging moves the box, not the picture
    if (e.button !== 0) return;
    e.stopPropagation();
    drag.current = { x: e.clientX, y: e.clientY, moved: false, node: id };
  };
  const onMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) d.moved = true;
    d.x = e.clientX; d.y = e.clientY;
    if (d.node) {
      const k = view.k;
      setMoved((m) => ({ ...m, [d.node]: { x: (m[d.node]?.x || 0) + dx / k, y: (m[d.node]?.y || 0) + dy / k } }));
    } else {
      setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
    }
  };
  const onUp = () => { setTimeout(() => { drag.current = null; }, 0); };

  function toggle(list, setList, value) {
    setList(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);
  }

  function chooseDomain(id) {
    if (focus) { setDomains([id]); go(`/metamodel/${model}/diagram`); return; }
    toggle(domains, setDomains, id);
  }

  function fileName(ext) {
    const focusName = focus && data.entity_types.find((t) => t.id === focus)?.name;
    return `${data.model.name} - ${focusName || "metamodel"}.${ext}`;
  }

  function svgText() {
    const svg = svgRef.current;
    if (!svg || !graph) return null;
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
    return new XMLSerializer().serializeToString(copy);
  }

  function downloadSvg() {
    const text = svgText();
    if (text) saveBlob(new Blob([text], { type: "image/svg+xml" }), fileName("svg"));
  }

  function downloadPng() {
    const text = svgText();
    if (!text) return;
    const scale = 2, w = (graph.width + 40) * scale, h = (graph.height + 40) * scale;
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      canvas.toBlob((blob) => blob && saveBlob(blob, fileName("png")), "image/png");
    };
    img.onerror = () => setNote("Could not draw the PNG; use SVG instead.");
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(text);
  }

  // the diagram's own draw.io file: saved as a drawn view of the model (its boxes are types, not entities, so they stay
  // plain shapes there) or opened in our draw.io (D407, D408, D585)
  function picture() {
    if (!graph) return null;
    const t = fileName("drawio").replace(/\.drawio$/, "");
    return { title: t, plain: true, xml: drawioXml(t, boxes, links, data.entity_types, showAttrs, bands) };
  }

  async function copyMermaid() {
    const q = new URLSearchParams();
    if (focus) q.set("type", focus); else domains.forEach((l) => q.append("domain", l));
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
  if (!data || !domains || !rels) return <p>Loading the metamodel...</p>;

  const names = Object.fromEntries(data.entity_types.map((t) => [t.id, t.name]));
  const focusType = focus && data.entity_types.find((t) => t.id === focus);
  // draw what was laid out (graph.part); the counts above it describe the current choice
  const links = graph?.part.links || [];
  const linkOf = Object.fromEntries((graph?.edges || []).map((e, i) => [e.id, links[i]]));
  const boxes = (graph?.children || []).map((b) => (moved[b.id] ? { ...b, x: b.x + moved[b.id].x, y: b.y + moved[b.id].y } : b));
  const boxOf = Object.fromEntries(boxes.map((b) => [b.id, b]));
  const pairs = new Set(links.map((l) => `${l.source}|${l.target}`));
  const edgeFor = (e, l) => {
    if (!moved[l.source] && !moved[l.target]) return e;
    const s = boxOf[l.source], t = boxOf[l.target];
    if (!s || !t) return e;
    if (l.source === l.target) {  // a loop on one box moves with the box
      const { x: dx, y: dy } = moved[l.source];
      const shift = (pt) => ({ ...pt, x: pt.x + dx, y: pt.y + dy });
      return { ...e, sections: (e.sections || []).map((sec) => ({ ...sec, startPoint: shift(sec.startPoint),
        endPoint: shift(sec.endPoint), bendPoints: (sec.bendPoints || []).map(shift) })),
        labels: (e.labels || []).map((lb) => (lb.x !== undefined ? shift(lb) : lb)) };
    }
    const offset = pairs.has(`${l.target}|${l.source}`) ? 7 : 0;
    return { ...e, sections: [straightSection(s, t, offset)], labels: [] };
  };
  const near = hover ? new Set([hover, ...links.filter((l) => l.source === hover || l.target === hover)
    .flatMap((l) => [l.source, l.target])]) : null;
  const big = part && (part.types.length > 45 || part.links.length > 250);
  const bands = arrange === "domains" && graph ? bandsOf(boxes, data.entity_types, data.domains, graph.width) : [];

  return (
    <div className="er">
      <div className="er-bar">
        <label>Focus on
          <select value={focus || ""} onChange={(e) => go(`/metamodel/${model}/diagram${e.target.value ? `/${e.target.value}` : ""}`)}>
            <option value="">(domains below)</option>
            {data.domains.map((l) => (
              <optgroup key={l.id} label={l.name}>
                {data.entity_types.filter((t) => t.domain_id === l.id).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        {focusType && <>
          <a href={`#/metamodel/${model}/type/${focus}`}>{focusType.name} details</a>
          <button onClick={() => go(`/metamodel/${model}/diagram`)}>Clear focus</button>
        </>}
        <span className="er-spacer" />
        <div className="seg small" role="group" aria-label="Arrangement">
          <button className={arrange === "free" ? "on" : ""} onClick={() => chooseArrange("free")}
            title="Boxes placed to keep lines short and tidy">Free layout</button>
          <button className={arrange === "domains" ? "on" : ""} onClick={() => chooseArrange("domains")}
            title="One band per domain, top to bottom in the metamodel's domain order (Strategy, Business, Application, Technology...), with lines crossing between the bands">By domain</button>
        </div>
        <label><input type="checkbox" checked={showAttrs} onChange={(e) => setShowAttrs(e.target.checked)} /> Attributes</label>
        <label><input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /> Line labels</label>
        <button onClick={() => fit()}>Fit</button>
        <button onClick={() => zoomAt(1.25, frame.current.clientWidth / 2, frame.current.clientHeight / 2)}>+</button>
        <button onClick={() => zoomAt(0.8, frame.current.clientWidth / 2, frame.current.clientHeight / 2)}>−</button>
        {Object.keys(moved).length > 0 && <button onClick={() => setMoved({})} title="Put dragged boxes back">Reset layout</button>}
        <button onClick={downloadSvg}>SVG</button>
        <button onClick={downloadPng}>PNG</button>
        <PictureActions model={model} picture={picture} images={false} disabled={!graph} />
        <button onClick={copyMermaid}>Copy as Mermaid</button>
      </div>

      <div className={`er-chips${focus ? " off" : ""}`}>
        <span className="quiet">Domains{focus ? " (choose one to leave the focus)" : ""}:</span>
        {data.domains.map((l) => (
          <button key={l.id} className={`chip${!focus && domains.includes(l.id) ? " on" : ""}`} onClick={() => chooseDomain(l.id)}>
            <span className="swatch" style={{ background: `#${l.colour}` }} /> {l.name}
          </button>
        ))}
        {!focus && <>
          <button className="chip" onClick={() => setDomains(data.domains.map((l) => l.id))}>All</button>
          <label className="quiet"><input type="checkbox" checked={connected} onChange={(e) => setConnected(e.target.checked)} /> plus connected types from other domains</label>
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
        {arrange === "domains" && part && ` · by domain: ${new Set(part.types.map((t) => t.domain_id)).size} domains${part.links.length > LAYERED_MAX ? " (straight lines: a large diagram)" : ""}`}
        {busy && " · laying out..."}

        {big && " · a large diagram: choose a domain, fewer relationship types, or focus on one type"}
        {note && <strong> · {note}</strong>}
      </p>

      <div className="er-frame" ref={frame} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
        {part && !part.types.length && <p className="quiet er-empty">Nothing to show: choose a domain or a type.</p>}
        <svg ref={svgRef} width="100%" height="100%">
          <defs>
            {[...Object.keys(REL_COLOURS), "mixed"].map((c) => (
              <marker key={c} id={`arrow-${c}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill={c === "mixed" ? "#6b7785" : relColour(c)} />
              </marker>
            ))}
          </defs>
          <g data-viewport="" transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {bands.map((b) => (
              <g key={b.id}>
                <title>{`${b.name}: ${b.count} entity types`}</title>
                <rect x={b.x} y={b.y} width={b.width} height={b.height} rx="8" fill={`#${b.colour}`} fillOpacity="0.28"
                  stroke={`#${b.colour}`} strokeOpacity="0.9" />
                <text x={b.x + 14} y={b.y + 24} fontSize="15" fontWeight="700" fill="#1d2733" fontFamily="system-ui, sans-serif">{b.name}</text>
                <text x={b.x + 14} y={b.y + 42} fontSize="11" fill="#5b6775" fontFamily="system-ui, sans-serif">{b.count} types</text>
              </g>
            ))}
            {graph?.edges.map((e) => {
              const l = linkOf[e.id];
              if (!l) return null;
              const touches = hover && (l.source === hover || l.target === hover);
              return <Edge key={e.id} edge={edgeFor(e, l)} link={l} names={names} dim={hover && !touches} hot={touches} showLabel={showLabels} />;
            })}
            {boxes.map((box) => {
              const t = data.entity_types.find((x) => x.id === box.id);
              return t && (
                <Node key={box.id} t={t} box={box} showAttrs={showAttrs} focused={box.id === focus}
                  dim={near && !near.has(box.id)}
                  onEnter={() => setHover(box.id)} onLeave={() => setHover(null)} onGrab={grab(box.id)}
                  onClick={() => { if (!drag.current?.moved) go(`/metamodel/${model}/diagram/${box.id}`); }} />
              );
            })}
          </g>
        </svg>
      </div>
      <p className="quiet er-info">
        Boxes are entity types with their attributes (* required; every entity also has a display ID, name,
        description, parent, status and history). Lines are the relationships the metamodel allows, from source to
        target, combined per pair of types. Drag a box to move it, click it to focus on it; drag the background to
        move around; scroll to zoom. SVG and PNG save what you see; Save as a drawn view keeps it, with this layout, as a
        drawn view of the model; Open in draw.io shows it in our draw.io, to export it (.drawio, PNG, SVG, PDF) or save it there.
      </p>
    </div>
  );
}
