// Entities and the lines between them (relationships, and the parent hierarchy as "Parent").
// Three kinds of picture (prop kind):
//   network  around an entity: the entity in the middle, its neighbours on rings by distance (1 to 3
//            steps); or every entity of chosen types (ELK layered when small, stress when large)
//   domains   the chosen types in horizontal bands by ArchiMate domain (strategy at the top, then
//            business, application, technology...), to read traceability from top to bottom
//   impact   from one entity, follow the lines one way only (out: what it leads to, uses or
//            contains; in: what leads to, uses or contains it), up to 6 steps, in columns by distance
// Click a box to open its entity page (or, by choice, to put it in the middle). Drag a box to move
// it, drag the background to pan, scroll to zoom. Save as a drawn view, open it in draw.io (D585), or download it (SVG, PNG, CSV of the lines) (D407, D408).
// For one entity (its page) there are also:
//   split    both ways at once: what leads to it on the left, what it leads to on the right
//   tree     its family tree: every parent up to the top, its parts down a chosen number of levels
//   domains   its neighbourhood in the bands of the ArchiMate domains
//   path     the shortest chains connecting it to a second entity
//   asof     its relationships at a moment of its history: removed since in red, added since in green
import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "./auth";
import { downloadCsv, downloadPng, downloadSvg } from "./exporting";
import { PictureActions } from "./DrawnView";
import { elk, relColour, straightSection, textWidth } from "./MetamodelDiagram";
import { fmtDateTime } from "./fmt";
import { elementTypes } from "./elements.js";

const go = (path) => { window.location.hash = path; };
const NAME_FONT = "600 12px system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
const H = 44, MIN_W = 110, MAX_W = 220;
const LAYERED_MAX = 50;
const PARENT = "Parent";
const lineColour = (code) => (code === PARENT ? "#8a96a3" : relColour(code));

function boxWidth(n) {
  const sub = textWidth(`${n.entity_type} · ${n.display_id}`, "10px system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif");
  return Math.max(MIN_W, Math.min(MAX_W, Math.ceil(Math.max(textWidth(n.name, NAME_FONT), sub)) + 24));
}

function shorten(text, width) {
  if (textWidth(text, NAME_FONT) <= width) return text;
  let s = text;
  while (s.length > 3 && textWidth(`${s}…`, NAME_FONT) > width) s = s.slice(0, -1);
  return `${s}…`;
}

// focus in the middle, every other entity on the ring of its distance, grouped by type
function rings(nodes, edges, focusId) {
  const near = {};
  for (const e of edges) {
    (near[e.source] ||= []).push(e.target);
    (near[e.target] ||= []).push(e.source);
  }
  const dist = { [focusId]: 0 };
  let frontier = [focusId];
  while (frontier.length) {
    const next = [];
    for (const id of frontier) for (const o of near[id] || []) if (dist[o] === undefined) { dist[o] = dist[id] + 1; next.push(o); }
    frontier = next;
  }
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const angle = { [focusId]: 0 };
  const boxes = {};
  const f = byId[focusId];
  if (f) boxes[focusId] = { x: -boxWidth(f) / 2, y: -H / 2, width: boxWidth(f), height: H };
  const maxD = Math.max(0, ...Object.values(dist));
  let radius = 0;
  for (let d = 1; d <= maxD + 1; d += 1) {
    const ring = nodes.filter((n) => (dist[n.id] ?? maxD + 1) === d && n.id !== focusId);
    if (!ring.length) continue;
    // order: by the angle of the neighbour one ring in, then by type and name
    const inner = (n) => {
      const a = (near[n.id] || []).filter((o) => angle[o] !== undefined && (dist[o] ?? 99) < d).map((o) => angle[o]);
      return a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
    };
    ring.sort((a, b) => (d === 1 ? 0 : inner(a) - inner(b)) || a.entity_type.localeCompare(b.entity_type) || a.name.localeCompare(b.name));
    const widths = ring.map(boxWidth);
    const circumference = widths.reduce((s, w) => s + w + 30, 0);
    radius = Math.max(radius + 200, circumference / (2 * Math.PI), d === 1 ? 220 : 0);
    let at = 0;
    ring.forEach((n, i) => {
      const a = ((at + widths[i] / 2) / circumference) * 2 * Math.PI - Math.PI / 2;
      at += widths[i] + 30;
      angle[n.id] = a;
      boxes[n.id] = { x: radius * Math.cos(a) - widths[i] / 2, y: radius * Math.sin(a) - H / 2, width: widths[i], height: H };
    });
  }
  return boxes;
}

// every entity in the band of its domain, grouped by type, wrapping long bands
const BAND_LABEL = 150, BAND_MAX = 1500, GAP = 16;
function bandsLayout(nodes) {
  const groups = [];
  for (const n of [...nodes].sort((a, b) => a.domain_order - b.domain_order || a.entity_type.localeCompare(b.entity_type) || a.name.localeCompare(b.name))) {
    let g = groups[groups.length - 1];
    if (!g || g.domain !== n.domain) groups.push(g = { domain: n.domain, colour: n.colour, items: [] });
    g.items.push(n);
  }
  const boxes = {}, bands = [];
  let y = 0;
  for (const g of groups) {
    let x = BAND_LABEL, rowY = y + GAP, lastType = null;
    for (const n of g.items) {
      const w = boxWidth(n);
      if (lastType && lastType !== n.entity_type) x += 12;  // a little space between types
      if (x + w > BAND_LABEL + BAND_MAX) { x = BAND_LABEL; rowY += H + 14; }
      boxes[n.id] = { x, y: rowY, width: w, height: H };
      x += w + GAP;
      lastType = n.entity_type;
    }
    const h = rowY + H + GAP - y;
    bands.push({ y, height: h, label: g.domain, colour: g.colour });
    y += h + 10;
  }
  return { boxes, bands };
}

// the focus in the first column, then one column per step (to the left when following lines in)
function chainLayout(nodes, focusId, direction) {
  const cols = {};
  for (const n of nodes) (cols[n.id === focusId ? 0 : (n.distance ?? 1)] ||= []).push(n);
  const boxes = {};
  const sign = direction === "in" ? -1 : 1;
  for (const [d, list] of Object.entries(cols)) {
    list.sort((a, b) => a.entity_type.localeCompare(b.entity_type) || a.name.localeCompare(b.name));
    const top = -((list.length - 1) * (H + 18)) / 2;
    list.forEach((n, i) => {
      const w = boxWidth(n);
      boxes[n.id] = { x: sign * Number(d) * 270 - w / 2, y: top + i * (H + 18), width: w, height: H };
    });
  }
  return boxes;
}

async function layout(nodes, edges, focusId, kind, direction) {
  let boxes, bands = [];
  if (kind === "domains") {
    ({ boxes, bands } = bandsLayout(nodes));
  } else if (kind === "impact" && focusId) {
    boxes = chainLayout(nodes, focusId, direction);
  } else if ((kind === "split" || kind === "path") && focusId) {
    boxes = chainLayout(nodes, focusId, "out");   // distances are signed: negative to the left
  } else if (kind === "tree") {
    const placed = await elk.layout({
      id: "root", children: nodes.map((n) => ({ id: n.id, width: boxWidth(n), height: H })),
      edges: edges.filter((e) => e.source !== e.target).map((e, i) => ({ id: `e${i}`, sources: [e.source], targets: [e.target] })),
      layoutOptions: { "elk.algorithm": "mrtree", "elk.direction": "DOWN", "elk.spacing.nodeNode": "24" },
    });
    boxes = Object.fromEntries(placed.children.map((c) => [c.id, { x: c.x, y: c.y, width: c.width, height: c.height }]));
  } else if (focusId) {
    boxes = rings(nodes, edges, focusId);
  } else {
    const children = nodes.map((n) => ({ id: n.id, width: boxWidth(n), height: H }));
    const elkEdges = edges.filter((e) => e.source !== e.target).map((e, i) => ({ id: `e${i}`, sources: [e.source], targets: [e.target] }));
    let placed;
    if (nodes.length <= LAYERED_MAX) {
      placed = await elk.layout({
        id: "root", children, edges: elkEdges,
        layoutOptions: { "elk.algorithm": "layered", "elk.direction": "DOWN", "elk.spacing.nodeNode": "30",
          "elk.layered.spacing.nodeNodeBetweenLayers": "70", "elk.separateConnectedComponents": "true" },
      });
    } else {
      const stress = await elk.layout({ id: "root", children, edges: elkEdges,
        layoutOptions: { "elk.algorithm": "stress", "elk.stress.desiredEdgeLength": "220" } });
      placed = await elk.layout({ id: "root", edges: elkEdges,
        children: stress.children.map(({ id, x, y, width, height }) => ({ id, x, y, width, height })),
        layoutOptions: { "elk.algorithm": "sporeOverlap", "elk.spacing.nodeNode": "24" } });
    }
    boxes = Object.fromEntries(placed.children.map((c) => [c.id, { x: c.x, y: c.y, width: c.width, height: c.height }]));
  }
  // move everything to start at (0, 0)
  const all = Object.values(boxes);
  const minX = Math.min(0, ...all.map((b) => b.x)), minY = Math.min(0, ...all.map((b) => b.y));
  for (const b of all) { b.x -= minX; b.y -= minY; }
  const width = Math.max(1, ...all.map((b) => b.x + b.width));
  for (const band of bands) { band.y -= minY; band.width = width + GAP; }
  return { boxes, bands, width: width + (bands.length ? GAP : 0),
    height: Math.max(1, ...all.map((b) => b.y + b.height), ...bands.map((b) => b.y + b.height)) };
}

// model: guid; focus: entity guid (fixed when the entity page shows it); lockFocus hides the type
// choice; kind: network, domains or impact
const FIRST_DEPTH = { impact: 3, split: 2, tree: 4, path: 6 };
const ALL_NODES = ["impact", "split", "tree", "path", "asof"];   // kinds that show every entity they fetch
const FOCUS_KINDS = ["impact", "split", "tree", "path", "asof"];  // kinds that need an entity to start from

// the as-of answer of one entity as a graph: lines then, removed since and added since
function asOfGraph(a, colour) {
  const me = a.entity;
  const nodes = [{ id: me.id, name: me.name, display_id: me.display_id, entity_type: me.entity_type, colour, domain: "", focus: true, distance: 0 }];
  const seen = new Set([me.id]);
  const edges = [];
  const add = (r, status) => {
    if (!r.other_id) return;
    if (!seen.has(r.other_id)) {
      seen.add(r.other_id);
      nodes.push({ id: r.other_id, name: r.other_name, display_id: r.other_display_id || "", entity_type: r.other_type || "", colour: r.other_colour, domain: "", distance: 1 });
    }
    const out = r.direction === "outgoing";
    edges.push({ id: `${r.id}-${status}`, source: out ? me.id : r.other_id, target: out ? r.other_id : me.id,
      relationship_type_code: r.relationship_type_code || r.relationship_type, relationship_type: r.relationship_type, verb: r.verb, allowed: true, status });
  };
  a.relationships.forEach((r) => add(r, r.still_there ? "then" : "removed"));
  a.added_since.forEach((r) => add(r, "added"));
  return { model: "", nodes, edges, truncated: false, as_of: a.as_of };
}

// presetTypeCodes (a view, phase 8.2): start with these entity types chosen; onlyRels: show only these relationship types
export default function EntityGraph({ model, focus: fixedFocus = null, lockFocus = false, kind = "network", focusColour = null,
  presetTypeCodes = null, onlyRels = null }) {
  const [pathTo, setPathTo] = useState(null);           // paths: the second entity
  const [moments, setMoments] = useState(null);         // as of: the moments of the entity's history
  const [asOf, setAsOf] = useState(null);               // as of: the chosen history event
  const [direction, setDirection] = useState("out");    // impact chains: out or in
  const [onClick, setOnClick] = useState("open");       // a click on a box: open its page, or put it in the middle
  const [relKnown, setRelKnown] = useState({});          // relationship types seen: code -> name
  const [meta, setMeta] = useState(null);         // entity types that hold entities
  const [types, setTypes] = useState(null);       // chosen type ids (when not focused)
  const [focus, setFocus] = useState(fixedFocus);
  const [depth, setDepth] = useState(FIRST_DEPTH[kind] || 1);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [hidden, setHidden] = useState([]);       // relationship type codes switched off
  const [graph, setGraph] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hover, setHover] = useState(null);
  const [view, setView] = useState({ x: 20, y: 20, k: 1 });
  const [moved, setMoved] = useState({});
  const [labels, setLabels] = useState(false);
  const [loners, setLoners] = useState(kind === "domains");   // show entities without lines
  const [find, setFind] = useState("");
  const [entities, setEntities] = useState(null);
  const frame = useRef(null);
  const svgRef = useRef(null);
  const drag = useRef(null);

  useEffect(() => { setFocus(fixedFocus); }, [fixedFocus]);

  // the types to choose from; by default the smallest types, up to 80 entities in all
  useEffect(() => {
    if (lockFocus) return;
    let live = true;
    apiFetch(`/api/v1/models/${model}/metamodel`).then((mm) => {
      if (!live) return;
      const list = mm.domains.flatMap((l) => elementTypes(l).map((t) => ({ ...t, colour: l.colour, domain: l.name })))
        .filter((t) => t.entity_count > 0);
      setMeta(list);
      if (presetTypeCodes) {
        const chosen = list.filter((t) => presetTypeCodes.includes(t.code)).map((t) => t.id);
        setTypes(chosen.length ? chosen : list.slice(0, 1).map((t) => t.id));
        return;
      }
      let total = 0;
      const chosen = [];
      for (const t of [...list].sort((a, b) => a.entity_count - b.entity_count)) {
        if (total + t.entity_count <= 80) { chosen.push(t.id); total += t.entity_count; }
      }
      setTypes(chosen.length ? chosen : list.slice(0, 1).map((t) => t.id));
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model, lockFocus, presetTypeCodes]);

  useEffect(() => { setDepth(FIRST_DEPTH[kind] || 1); setLoners(kind === "domains"); setHidden([]); }, [kind]);

  // as of: the moments of the entity's history (one per person per second), newest first
  useEffect(() => {
    if (kind !== "asof" || !focus) return undefined;
    let live = true;
    apiFetch(`/api/v1/models/${model}/entities/${focus}/history`).then((h) => {
      if (!live) return;
      const list = [];
      for (const ev of h.events) {
        const key = `${Math.floor(new Date(ev.at).getTime() / 1000)}|${ev.by}`;
        if (!list.length || list[list.length - 1].key !== key) list.push({ key, id: ev.id, at: ev.at, by: ev.by, n: 0 });
        list[list.length - 1].n += 1;
      }
      setMoments(list);
      setAsOf((list[1] || list[0])?.id ?? null);
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model, focus, kind]);

  // chains and paths follow only the relationship types switched on, so ask the server for those
  const relParam = ["impact", "split", "path"].includes(kind) && hidden.length ? Object.keys(relKnown).filter((c) => !hidden.includes(c)).join("|") : "";

  useEffect(() => {
    const q = new URLSearchParams();
    const useFocus = focus && (kind !== "domains" || lockFocus);
    let url = `/api/v1/models/${model}/graph`;
    if (kind === "path") {
      if (!focus || !pathTo) { setData(null); return undefined; }
      url = `/api/v1/models/${model}/entities/${focus}/paths`;
      q.set("to", pathTo); q.set("steps", Math.min(depth, 8));
      if (relParam) relParam.split("|").forEach((r) => q.append("rel", r));
    } else if (kind === "asof") {
      if (!focus || !asOf) { setData(null); return undefined; }
      let live = true;
      apiFetch(`/api/v1/models/${model}/entities/${focus}/as-of?event=${asOf}`)
        .then((a) => live && setData(asOfGraph(a, focusColour)))
        .catch((e) => live && setError(e.message));
      return () => { live = false; };
    } else if (useFocus) {
      q.set("focus", focus);
      q.set("depth", Math.min(depth, kind === "tree" ? 10 : ["impact", "split"].includes(kind) ? 6 : 3));
      if (kind === "impact") q.set("direction", direction);
      if (kind === "split" || kind === "tree") q.set("direction", kind);
      if (relParam) relParam.split("|").forEach((r) => q.append("rel", r));
    } else if (FOCUS_KINDS.includes(kind)) { setData(null); return undefined; }
    else if (types && types.length) types.forEach((t) => q.append("type", t));
    else { setData(null); return; }
    q.set("limit", "400");
    let live = true;
    setError(null);
    apiFetch(`${url}?${q}`)
      .then((d) => {
        if (!live) return;
        setData(d);
        setRelKnown((k) => ({ ...k, ...Object.fromEntries(d.edges.map((e) => [e.relationship_type_code, e.relationship_type])) }));
      })
      .catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model, focus, depth, types, kind, direction, relParam, lockFocus, pathTo, asOf, focusColour]);

  const shown = useMemo(() => {
    if (!data) return null;
    const edges = data.edges.filter((e) => !hidden.includes(e.relationship_type_code)
      && (!onlyRels || !onlyRels.length || onlyRels.includes(e.relationship_type_code)));
    const linked = new Set(edges.flatMap((e) => [e.source, e.target]));
    const nodes = loners || ALL_NODES.includes(kind) ? data.nodes : data.nodes.filter((n) => linked.has(n.id) || n.id === focus);
    return { nodes, edges, alone: data.nodes.length - nodes.length };
  }, [data, hidden, loners, focus, kind, onlyRels]);

  useEffect(() => {
    if (!shown) return;
    let live = true;
    setBusy(true);
    const centre = kind !== "domains" && focus && shown.nodes.some((n) => n.id === focus) ? focus : null;
    layout(shown.nodes, shown.edges, centre, kind, direction)
      .then((g) => { if (live) { setGraph(g); setMoved({}); fit(g); } })
      .catch((e) => live && setError(`Layout failed: ${e.message}`))
      .finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [shown]); // eslint-disable-line react-hooks/exhaustive-deps

  function fit(g = graph) {
    const el = frame.current;
    if (!g || !el) return;
    const w = el.clientWidth, h = el.clientHeight;
    const k = Math.min(1.2, (w - 40) / g.width, (h - 40) / g.height);
    setView({ k, x: (w - g.width * k) / 2, y: Math.max(20, (h - g.height * k) / 2) });
  }
  function zoomAt(factor, cx, cy) {
    setView((v) => {
      const k = Math.min(3, Math.max(0.05, v.k * factor));
      const f = k / v.k;
      return { k, x: cx - (cx - v.x) * f, y: cy - (cy - v.y) * f };
    });
  }
  useEffect(() => {
    const el = frame.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [graph]);

  const onDown = (e) => { if (e.button === 0 && !drag.current) drag.current = { x: e.clientX, y: e.clientY, moved: false }; };
  const grab = (id) => (e) => {
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
    if (d.node) setMoved((m) => ({ ...m, [d.node]: { x: (m[d.node]?.x || 0) + dx / view.k, y: (m[d.node]?.y || 0) + dy / view.k } }));
    else setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  };
  const onUp = () => { setTimeout(() => { drag.current = null; }, 0); };

  async function startFind() {
    if (entities) return;
    try { setEntities(await apiFetch(`/api/v1/models/${model}/entity-list`)); } catch (e) { setError(e.message); }
  }
  const matches = useMemo(() => {
    const f = find.trim().toLowerCase();
    if (!f || !entities) return [];
    return entities.filter((e) => `${e.name} ${e.display_id}`.toLowerCase().includes(f)).slice(0, 12);
  }, [find, entities]);

  const title = () => `${data?.model || "model"} - ${focusNode?.name || "entities"} (${{
    network: "network", domains: "by domain", impact: `impact ${direction}`, split: "both ways", tree: "family tree",
    path: `paths to ${data?.target?.name || ""}`, asof: `as of ${String(data?.as_of?.at || "").slice(0, 16).replace("T", " ")}`,
  }[kind]})`;

  // the picture for a drawn view or a download (D407, D408): bands, the entities in their places, the lines bound to the
  // relationships they show
  function picture() {
    if (!graph) return null;
    const cells = (graph.bands || []).map((b, i) => ({
      id: `band${i}`, label: b.label, x: 0, y: b.y, w: b.width, h: b.height, fill: "f6f7f9", stroke: "d9dee5",
      dashed: true, fontColor: "5b6775", bold: true, align: "left",
    }));
    for (const n of nodes) {
      const b = box(n.id);
      if (b) cells.push({ id: n.id, label: n.name, sub: `${n.entity_type} · ${n.display_id}`, x: b.x, y: b.y, w: b.width, h: b.height,
        fill: n.colour, stroke: n.id === focus ? "1f5fb8" : "8a96a3", ea_type: n.entity_type, ea_id: n.id, ea_domain: n.domain });
    }
    return { title: title(), nodes: cells, edges: edges.filter((e) => e.source !== e.target).map((e) => ({
      rel: e.relationship_type_code !== PARENT && e.status !== "removed" && /^[0-9a-f-]{36}$/i.test(e.id) ? e.relationship_type_code : null,
      rel_id: /^[0-9a-f-]{36}$/i.test(e.id) ? e.id : null,
      source: e.source, target: e.target, label: labels || e.status === "removed" || e.status === "added" ? `${e.verb}${e.status === "removed" ? " (removed since)" : e.status === "added" ? " (added since)" : ""}` : "",
      colour: e.status === "removed" ? "b3261e" : e.status === "added" ? "1e7b3c" : lineColour(e.relationship_type_code),
      dashed: e.relationship_type_code === PARENT || !e.allowed || e.status === "removed",
    })) };
  }

  function exportCsv() {
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const rows = [["Source ID", "Source", "Source type", "Relationship", "Reads as", "Target ID", "Target", "Target type", "In the metamodel"]];
    for (const e of edges) {
      const s2 = byId[e.source], t = byId[e.target];
      if (s2 && t) rows.push([s2.display_id, s2.name, s2.entity_type, e.relationship_type, e.verb, t.display_id, t.name, t.entity_type, e.allowed ? "yes" : "no"]);
    }
    const linked = new Set(edges.flatMap((e) => [e.source, e.target]));
    for (const n of nodes) if (!linked.has(n.id)) rows.push([n.display_id, n.name, n.entity_type, "", "", "", "", "", ""]);
    downloadCsv(rows, title());
  }

  function clickBox(n) {
    if (drag.current?.moved) return;
    if (lockFocus || onClick === "open" || kind === "domains") go(`/metamodel/${model}/entity/${n.id}`);
    else setFocus(n.id);
  }

  if (error) return <p className="status bad">{error}</p>;
  const nodes = shown?.nodes || [];
  const edges = shown?.edges || [];
  const focusNode = data?.nodes.find((n) => n.id === focus);
  const box = (id) => {
    const b = graph?.boxes[id];
    if (!b) return null;
    return moved[id] ? { ...b, x: b.x + moved[id].x, y: b.y + moved[id].y } : b;
  };
  const near = hover ? new Set([hover, ...edges.filter((e) => e.source === hover || e.target === hover).flatMap((e) => [e.source, e.target])]) : null;
  const relTypes = data ? [...new Map(data.edges.map((e) => [e.relationship_type_code, e.relationship_type])).entries()] : [];
  const pairs = new Set(edges.map((e) => `${e.source}|${e.target}`));
  const names = Object.fromEntries((data?.nodes || []).map((n) => [n.id, n.name]));

  return (
    <div className="er">
      <div className="er-bar">
        {!lockFocus && (
          <span className="graph-find">
            <input className="search" placeholder={kind === "impact" ? "Start from an entity..." : "Put an entity in the middle..."} value={find}
              onFocus={startFind} onChange={(e) => setFind(e.target.value)} />
            {matches.length > 0 && (
              <ul className="graph-matches">
                {matches.map((m) => (
                  <li key={m.id}><button className="linkish" onClick={() => { setFocus(m.id); setFind(""); }}>
                    {m.name} <span className="quiet">{m.display_id} · {m.entity_type}</span></button></li>
                ))}
              </ul>
            )}
          </span>
        )}
        {kind === "impact" && (
          <label>Follow
            <select value={direction} onChange={(e) => setDirection(e.target.value)}>
              <option value="out">lines going out (impact: what it leads to, uses, contains)</option>
              <option value="in">lines coming in (dependencies: what leads to, uses, contains it)</option>
            </select>
          </label>
        )}
        {kind === "path" && focus && (
          <span className="graph-find">
            <input className="search" placeholder={pathTo ? "Path to another entity..." : "Path to which entity? Type a name..."} value={find}
              onFocus={startFind} onChange={(e) => setFind(e.target.value)} />
            {matches.length > 0 && (
              <ul className="graph-matches">
                {matches.filter((m) => m.id !== focus).map((m) => (
                  <li key={m.id}><button className="linkish" onClick={() => { setPathTo(m.id); setFind(""); }}>
                    {m.name} <span className="quiet">{m.display_id} · {m.entity_type}</span></button></li>
                ))}
              </ul>
            )}
          </span>
        )}
        {kind === "asof" && moments && (
          <label>As it was after
            <select value={asOf || ""} onChange={(e) => setAsOf(Number(e.target.value))}>
              {moments.map((m, i) => <option key={m.id} value={m.id}>{fmtDateTime(m.at)} · {m.by} ({m.n} change{m.n > 1 ? "s" : ""}){i === 0 ? " · latest" : ""}</option>)}
            </select>
          </label>
        )}
        {focus && kind !== "asof" && (kind !== "domains" || lockFocus) && (
          <>
            <label>{kind === "tree" ? "Levels down" : kind === "path" ? "At most steps" : "Steps"}
              <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
                {(kind === "tree" ? [1, 2, 3, 4, 5, 6, 8, 10] : kind === "path" ? [1, 2, 3, 4, 5, 6, 7, 8]
                  : ["impact", "split"].includes(kind) ? [1, 2, 3, 4, 5, 6] : [1, 2, 3]).map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
            {!lockFocus && kind === "network" && <button onClick={() => setFocus(null)}>Back to chosen types</button>}
          </>
        )}
        {!lockFocus && kind === "network" && (
          <label>Click a box to
            <select value={onClick} onChange={(e) => setOnClick(e.target.value)}>
              <option value="open">open its entity page</option>
              <option value="middle">put it in the middle</option>
            </select>
          </label>
        )}
        <span className="er-spacer" />
        {!ALL_NODES.includes(kind) && <label><input type="checkbox" checked={loners} onChange={(e) => setLoners(e.target.checked)} /> Entities without lines</label>}
        <label><input type="checkbox" checked={labels} onChange={(e) => setLabels(e.target.checked)} /> Line labels</label>
        <button onClick={() => fit()}>Fit</button>
        <button onClick={() => zoomAt(1.25, frame.current.clientWidth / 2, frame.current.clientHeight / 2)}>+</button>
        <button onClick={() => zoomAt(0.8, frame.current.clientWidth / 2, frame.current.clientHeight / 2)}>−</button>
        {Object.keys(moved).length > 0 && <button onClick={() => setMoved({})}>Reset layout</button>}
        <button onClick={() => graph && downloadSvg(svgRef.current, graph.width, graph.height, title())}>SVG</button>
        <button onClick={() => graph && downloadPng(svgRef.current, graph.width, graph.height, title())}>PNG</button>
        <button onClick={exportCsv} title="The lines (and entities without lines) as a table">CSV</button>
        <PictureActions model={model} picture={picture} images={false} disabled={!graph} />
      </div>

      {!lockFocus && (!focus || kind === "domains") && !FOCUS_KINDS.includes(kind) && meta && (
        <div className="er-chips">
          <span className="quiet">Entity types:</span>
          {meta.map((t) => (
            <button key={t.id} className={`chip${types?.includes(t.id) ? " on" : ""}`}
              onClick={() => setTypes((l) => (l.includes(t.id) ? l.filter((x) => x !== t.id) : [...l, t.id]))}>
              <span className="swatch" style={{ background: `#${t.colour}` }} /> {t.name} <span className="count">{t.entity_count}</span>
            </button>
          ))}
          <button className="chip" onClick={() => setTypes([])}>None</button>
        </div>
      )}
      {relTypes.length > 0 && (
        <div className="er-chips">
          <span className="quiet">Lines:</span>
          {relTypes.map(([code, name]) => {
            const on = !hidden.includes(code);
            return (
              <button key={code} className={`chip${on ? " on" : ""}`}
                style={on ? { borderColor: lineColour(code), color: lineColour(code) } : undefined}
                onClick={() => setHidden((h) => (on ? [...h, code] : h.filter((x) => x !== code)))}>
                <span className="er-line" style={{ background: lineColour(code) }} /> {code === PARENT ? "Parent (part of)" : name}
              </button>
            );
          })}
        </div>
      )}
      <p className="quiet er-info">
        {data && `${nodes.length} entities, ${edges.length} lines`}
        {shown?.alone > 0 && ` (${shown.alone} without lines hidden)`}
        {data?.truncated && ` · only the first ${data.limit} entities: choose fewer types or fewer steps`}
        {busy && " · laying out..."}
        {kind === "path" && data && (data.found
          ? <> · {data.paths.length}{data.truncated ? "+" : ""} shortest path{data.paths.length > 1 ? "s" : ""} of {data.steps} step{data.steps > 1 ? "s" : ""} to <strong>{data.target.name}</strong></>
          : <> · <strong>no path</strong> to {data.target?.name} within {depth} steps: allow more steps or more line types</>)}
        {kind === "path" && !pathTo && " · choose the entity to find paths to"}
        {kind === "asof" && data?.as_of && <> · as it was on {fmtDateTime(data.as_of.at)}:{" "}
          {edges.filter((e) => e.status === "removed").length} removed since (red), {edges.filter((e) => e.status === "added").length} added since (green)</>}
        {kind === "asof" && moments && !moments.length && " · no recorded history"}
        {focusNode && !["domains", "path", "asof"].includes(kind) && <> · {["impact", "split", "tree"].includes(kind) ? "start" : "middle"}: <a href={`#/metamodel/${model}/entity/${focusNode.id}`}>{focusNode.name}</a> ({focusNode.entity_type})</>}
        {kind !== "impact" && !focus && types && !types.length && " · choose one or more entity types, or put an entity in the middle"}
        {kind === "impact" && !focus && " · choose an entity to start from in the search box"}
      </p>

      <div className="er-frame graph-frame" ref={frame} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
        <svg ref={svgRef} width="100%" height="100%">
          <defs>
            {[...new Set(edges.map((e) => e.relationship_type_code))].map((c) => (
              <marker key={c} id={`garrow-${c}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill={lineColour(c)} />
              </marker>
            ))}
          </defs>
          <g data-viewport="" transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {(graph?.bands || []).map((b) => (
              <g key={b.label}>
                <rect x="0" y={b.y} width={b.width} height={b.height} rx="8" fill="#f6f7f9" stroke="#d9dee5" strokeDasharray="4 3" />
                <rect x="0" y={b.y} width="8" height={b.height} rx="3" fill={`#${b.colour || "ccc"}`} />
                <text x="18" y={b.y + 24} fontSize="14" fontWeight="700" fill="#5b6775">{b.label}</text>
              </g>
            ))}
            {edges.map((e) => {
              const s = box(e.source), t = box(e.target);
              if (!s || !t || e.source === e.target) return null;
              const sec = straightSection(s, t, pairs.has(`${e.target}|${e.source}`) ? 5 : 0);
              const touches = hover && (e.source === hover || e.target === hover);
              const colour = e.status === "removed" ? "#b3261e" : e.status === "added" ? "#1e7b3c" : lineColour(e.relationship_type_code);
              const mx = (sec.startPoint.x + sec.endPoint.x) / 2, my = (sec.startPoint.y + sec.endPoint.y) / 2;
              return (
                <g key={`${e.id}-${e.relationship_type_code}`} opacity={hover && !touches ? 0.12 : 1}>
                  <title>{`${names[e.source]} ${e.verb} ${names[e.target]} (${e.relationship_type}${e.allowed ? "" : ", not in the metamodel"}${e.status === "removed" ? ", removed since" : e.status === "added" ? ", added since" : ""})`}</title>
                  <line x1={sec.startPoint.x} y1={sec.startPoint.y} x2={sec.endPoint.x} y2={sec.endPoint.y}
                    stroke={colour} strokeWidth={touches || e.status === "added" || kind === "path" ? 2.4 : 1.4}
                    strokeDasharray={e.status === "removed" ? "6 4" : e.relationship_type_code === PARENT ? "2 3" : e.allowed ? undefined : "6 4"}
                    markerEnd={`url(#garrow-${e.relationship_type_code})`} />
                  {(labels || touches || e.status === "removed" || e.status === "added" || kind === "path") && (
                    <text x={mx} y={my - 3} textAnchor="middle" fontSize="10" fill={colour} stroke="#fff" strokeWidth="3" paintOrder="stroke">
                      {e.verb}{e.status === "removed" ? " (removed since)" : e.status === "added" ? " (added since)" : ""}</text>
                  )}
                </g>
              );
            })}
            {nodes.map((n) => {
              const b = box(n.id);
              if (!b) return null;
              const isFocus = n.id === focus;
              return (
                <g key={n.id} transform={`translate(${b.x},${b.y})`} opacity={near && !near.has(n.id) ? 0.25 : 1}
                  style={{ cursor: "pointer" }} onMouseDown={grab(n.id)}
                  onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                  onClick={() => clickBox(n)}
                  onDoubleClick={() => go(`/metamodel/${model}/entity/${n.id}`)}>
                  <title>{`${n.name} (${n.display_id}, ${n.entity_type}). ${!lockFocus && kind === "network" && onClick === "middle" ? "Click: put in the middle. Double-click: open." : "Click: open its page."}`}</title>
                  <rect width={b.width} height={b.height} rx="6" fill={`#${n.colour || "eeeeee"}`}
                    stroke={isFocus || n.target ? "#1f5fb8" : "#8a96a3"} strokeWidth={isFocus || n.target ? 3 : 1} />
                  <text x="10" y="18" fontSize="12" fontWeight="600" fill="#1d2733">{shorten(n.name, b.width - 20)}</text>
                  <text x="10" y="34" fontSize="10" fill="#5b6775">{n.entity_type} · {n.display_id}</text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <p className="quiet er-info">
        Boxes are entities, coloured by domain. Lines are relationships from source to target (dashed: not allowed by the
        metamodel; dotted grey: part of a parent). {kind === "domains" ? "Bands are the ArchiMate domains, top to bottom. " : ""}
        {kind === "impact" ? "Columns are steps from the starting entity. " : ""}
        {kind === "split" ? "Left: what leads to it (dependencies); right: what it leads to (impact). " : ""}
        {kind === "tree" ? "Parents above, parts below. " : ""}
        {kind === "path" ? "Columns are steps from this entity to the other one (outlined). " : ""}
        {kind === "asof" ? "Red dashed: relationships it had then and has no longer; green: relationships added since. " : ""}Click a box to open its entity page.
        Drag a box to move it, drag the background to move around, scroll to zoom. Save as a drawn view keeps it, with this layout, as a drawn view of the model.
      </p>
    </div>
  );
}
