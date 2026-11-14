// Saving what a screen shows: CSV for tables; a generated picture is saved as a drawn view of the model or downloaded
// (PNG, SVG, .drawio) (D408: every view in the system is a draw.io file; nothing is edited outside a drawn view; a
// download is the person's own and goes stale). The picture's file is plain draw.io XML: every box that stands for an
// entity carries ea_id (its guid) and ea_type (its type's code), the drawn-view plugin's own attributes, so a drawn view
// made from it is bound to the model's entities, in the ArchiMate notation of their types (setup.types).

export function saveBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename.replace(/[\\/:*?"<>|]/g, "_");
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ---------------------------------------------------------------- CSV
function cell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows) {
  return rows.map((r) => r.map(cell).join(",")).join("\r\n");
}

// rows: an array of arrays, the first one the column headings. A BOM so Excel reads UTF-8.
export function downloadCsv(rows, name) {
  saveBlob(new Blob(["\ufeff" + toCsv(rows)], { type: "text/csv;charset=utf-8" }), name.endsWith(".csv") ? name : `${name}.csv`);
}

// ---------------------------------------------------------------- draw.io
const xml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const hex = (c, fallback = "eeeeee") => String(c || fallback).replace(/^#/, "");
const GRID = 10;
const snap = (v) => Math.round((Number(v) || 0) / GRID) * GRID;

// Tidy (owner, 6 Nov 2026 todo): boxes on the 10 px grid, no box smaller than its kind needs, a container at least as
// large as what it holds (with room for its title), parts kept inside their container; lines as the picture draws them.
export function tidy(nodes) {
  const out = nodes.map((n) => (n.keepSize ? { ...n, x: Math.round(n.x), y: Math.round(n.y), w: Math.round(n.w), h: Math.round(n.h) }
    : { ...n, x: snap(n.x), y: snap(n.y),
      w: Math.max(snap(n.w), n.shape === "text" ? 40 : n.ea_id ? 120 : 40), h: Math.max(snap(n.h), n.shape === "text" ? 20 : n.ea_id ? 40 : 20) }));
  const byId = Object.fromEntries(out.map((n) => [n.id, n]));
  for (const n of out) {                       // parts inside their container, below its title
    const p = n.parent && byId[n.parent];
    if (!p) continue;
    n.x = Math.max(n.x, p.x + GRID); n.y = Math.max(n.y, p.y + 3 * GRID);
  }
  for (const n of [...out].reverse()) {          // containers grow to hold their parts (deepest first)
    const kids = out.filter((k) => k.parent === n.id);
    if (!kids.length) continue;
    n.w = Math.max(n.w, Math.max(...kids.map((k) => k.x + k.w)) - n.x + GRID);
    n.h = Math.max(n.h, Math.max(...kids.map((k) => k.y + k.h)) - n.y + GRID);
  }
  return out;
}

// the type's code for a node's ea_type (a code or a type's name) in the model's drawn-view setup
const codeOf = (look, t) => (!look || !t ? null : look.types[t] ? t
  : Object.keys(look.types).find((c) => look.types[c].name === t || c.toLowerCase() === String(t).replace(/\s+/g, "").toLowerCase()) || null);

// nodes: { id, label, sub?, x, y, w, h (absolute), fill?, stroke?, fontColor?, container?, parent? (a node id),
//          ea_type? (a type's code or name), ea_id?, dashed?, bold?, fontSize?, align? ('left'|'center'), shape? ('text') }
//          heatFill? (an entity coloured by a value: kept on a drawn view; otherwise its type's colour),
//          keepSize? (a table cell or a timeline bar: its size and place exactly as given, not snapped)
// edges: { source, target, label?, colour?, dashed?, arrow? (default true), rel? (a relationship type's code), rel_id?,
//          route? ('orthogonal' for a tree's elbows; else straight, as the graphs draw them) }
// look: the model's drawn-view setup (types and relationship types with their ArchiMate looks); without it, plain boxes
export function drawioXml(title, nodes, edges = [], look = null) {
  const all = tidy(nodes);
  const byId = Object.fromEntries(all.map((n) => [n.id, n]));
  const cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>'];
  const cellId = (id) => `n_${String(id).replace(/[^A-Za-z0-9_-]/g, "_")}`;
  for (const n of all) {
    const parent = n.parent && byId[n.parent] ? byId[n.parent] : null;
    const x = n.x - (parent ? parent.x : 0), y = n.y - (parent ? parent.y : 0);
    const code = n.ea_id ? codeOf(look, n.ea_type) : null;
    const t = code ? look.types[code] : null;
    const label = n.sub ? `<b>${xml(n.label)}</b><br><font style="font-size:10px" color="#5b6775">${xml(n.sub)}</font>`
      : n.bold ? `<b>${xml(n.label)}</b>` : xml(n.label);
    const style = t      // an entity: its type's ArchiMate notation, coloured as the picture colours it
      ? `${t.box}fillColor=#${hex(n.heatFill || t.colour)};fontSize=${n.fontSize || 12};` +
        (n.container ? "container=1;collapsible=0;recursiveResize=0;verticalAlign=top;align=left;spacingLeft=8;spacingTop=6;" : "verticalAlign=middle;align=center;")
      : n.shape === "text"
        ? `text;html=1;align=${n.align || "left"};verticalAlign=middle;fontSize=${n.fontSize || 12};fontColor=#${hex(n.fontColor, "5b6775")};`
        : [
          "rounded=1", "arcSize=6", "whiteSpace=wrap", "html=1",
          `align=${n.align || "left"}`, `verticalAlign=${n.container ? "top" : "middle"}`, "spacingLeft=6", "spacingTop=2",
          `fillColor=#${hex(n.fill)}`, `strokeColor=#${hex(n.stroke, "8a96a3")}`, `fontSize=${n.fontSize || 12}`,
          n.fontColor ? `fontColor=#${hex(n.fontColor)}` : "", n.dashed ? "dashed=1" : "",
          n.container ? "container=1;collapsible=0" : "",
        ].filter(Boolean).join(";") + ";";
    const geometry = `<mxGeometry x="${x}" y="${y}" width="${n.w}" height="${n.h}" as="geometry"/>`;
    const parentId = parent ? cellId(parent.id) : "1";
    if (n.ea_id) {
      const type = code || n.ea_type || "";
      cells.push(`<object id="${cellId(n.id)}" label="${xml(t ? n.label : label)}" ea_id="${xml(n.ea_id)}" ea_type="${xml(type)}">` +
        `<mxCell style="${xml(style)}" vertex="1" parent="${parentId}">${geometry}</mxCell></object>`);
    } else {
      cells.push(`<mxCell id="${cellId(n.id)}" value="${xml(label)}" style="${xml(style)}" vertex="1" parent="${parentId}">${geometry}</mxCell>`);
    }
  }
  edges.forEach((e, i) => {
    if (!byId[e.source] || !byId[e.target]) return;
    const colour = hex(e.colour, "6b7785");
    // as the picture draws it: straight from box to box (the graphs), or at right angles (the trees)
    const route = e.route === "orthogonal" ? "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;" : "edgeStyle=none;";
    const own = e.rel && look?.relationshipTypes?.[e.rel]?.style;
    if (e.rel && e.rel_id && own) {             // a relationship of the model: its ArchiMate line, bound to it
      cells.push(`<object id="e_${i}" label="${xml(e.label || "")}" ea_rel="${xml(e.rel)}" ea_rel_id="${xml(e.rel_id)}">` +
        `<mxCell style="${xml(own + route)}" edge="1" parent="1" source="${cellId(e.source)}" target="${cellId(e.target)}">` +
        '<mxGeometry relative="1" as="geometry"/></mxCell></object>');
      return;
    }
    const routed = e.points?.length > 1 ? waypoints(e, byId) : null;     // the picture's own route (R3.4)
    cells.push(`<mxCell id="e_${i}" value="${xml(e.short || e.label || "")}" style="html=1;${routed ? routed.style : route}endArrow=${e.arrow === false ? "none" : "block"};endFill=1;` +
      `strokeColor=#${colour};fontSize=10;fontColor=#${colour};labelBackgroundColor=#ffffff;${e.dashed ? "dashed=1;" : ""}" ` +
      `edge="1" parent="1" source="${cellId(e.source)}" target="${cellId(e.target)}"><mxGeometry relative="1" as="geometry">${routed ? routed.points : ""}</mxGeometry></mxCell>`);
  });
  return '<mxfile host="EA Explorer" type="device">' +
    `<diagram id="ea" name="${xml(title)}"><mxGraphModel grid="1" gridSize="10" page="0"><root>` +
    cells.join("") + "</root></mxGraphModel></diagram></mxfile>";
}

// a routed line in draw.io: leaves and enters each box where the picture does, through the picture's bends
function waypoints(e, byId) {
  const a = byId[e.source], b = byId[e.target], p = e.points;
  const fx = (n, x) => Math.max(0, Math.min(1, (x - n.x) / n.w)).toFixed(3);
  const style = `edgeStyle=none;exitX=${fx(a, p[0][0])};exitY=${e.exit === "top" ? 0 : 1};exitPerimeter=0;` +
    `entryX=${fx(b, p[p.length - 1][0])};entryY=${e.entry === "top" ? 0 : 1};entryPerimeter=0;`;
  const inner = p.slice(1, -1).map(([x, y]) => `<mxPoint x="${x}" y="${y}"/>`).join("");
  return { style, points: inner ? `<Array as="points">${inner}</Array>` : "" };
}

// the picture as a .drawio file to keep (a download: the person's own; it goes stale, D408)
export function downloadDrawio(title, nodes, edges, look = null) {
  saveBlob(new Blob([drawioXml(title, nodes, edges, look)], { type: "application/xml" }), `${title}.drawio`);
}

// the picture (nodes and edges) as an SVG text, for screens drawn in HTML (heat maps, matrices, maps)
export function pictureSvg(nodes, edges = []) {
  const all = tidy(nodes);
  const pts = edges.flatMap((e) => [...(e.points || []), ...(e.label_at && e.short ? [[e.label_at[0] + e.short.length * 5.2 + 6, e.label_at[1]]] : [])]);
  const W = Math.max(100, ...all.map((n) => n.x + n.w), ...pts.map((p) => p[0])), H = Math.max(60, ...all.map((n) => n.y + n.h), ...pts.map((p) => p[1]));
  const byId = Object.fromEntries(all.map((n) => [n.id, n]));
  const parts = [`<svg xmlns="http://www.w3.org/2000/svg" width="${W + 40}" height="${H + 40}" viewBox="-20 -20 ${W + 40} ${H + 40}" font-family="system-ui, sans-serif">`,
    `<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#6b7785"/></marker></defs>`,
    `<rect x="-20" y="-20" width="${W + 40}" height="${H + 40}" fill="#ffffff"/>`];
  const boxes = [], lines = [], labels = [];
  for (const n of all) {
    const tip = n.title ? `<title>${xml(n.title)}</title>` : "";
    if (n.shape !== "text") {
      boxes.push(`<rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="4" fill="#${hex(n.fill)}" stroke="#${hex(n.stroke, "8a96a3")}"${n.dashed ? ' stroke-dasharray="4 3"' : ""}>${tip}</rect>`);
    }
    const centre = n.align === "center" || (!n.container && n.shape !== "text" && n.align !== "left" && !n.lines);
    const tx = centre ? n.x + n.w / 2 : n.x + 6, anchor = centre ? "middle" : "start";
    const size = n.fontSize || 12, weight = n.bold || n.lines ? 700 : 400;
    if (n.lines) {                 // wrapped to the box (R3.4): the label's lines, then the line(s) under it
      const rows = [...n.lines.map((t) => [t, size, weight, "1f2328"]), ...(n.sublines || []).map((t) => [t, 10, 400, "5b6775"])];
      const tall = 14 * n.lines.length + 13 * (n.sublines || []).length;
      let y = n.container ? n.y + 16 : n.y + Math.max(14, (n.h - tall) / 2 + 11);
      for (const [t, sz, wt, col] of rows) {
        boxes.push(`<text x="${tx}" y="${y}" text-anchor="${anchor}" font-size="${sz}" font-weight="${wt}" fill="#${col}">${xml(t)}${tip}</text>`);
        y += sz >= 11 ? 14 : 13;
      }
      continue;
    }
    const ty = n.container ? n.y + 16 : n.y + n.h / 2 + (n.sub ? -2 : 4);
    boxes.push(`<text x="${tx}" y="${ty}" text-anchor="${anchor}" font-size="${size}" font-weight="${n.bold ? 700 : 400}" fill="#${hex(n.fontColor, "1f2328")}">${xml(n.label)}</text>`);
    if (n.sub) boxes.push(`<text x="${tx}" y="${ty + 13}" text-anchor="${anchor}" font-size="10" fill="#5b6775">${xml(n.sub)}</text>`);
  }
  for (const e of edges) {
    const a = byId[e.source], b = byId[e.target];
    if (!a || !b) continue;
    const stroke = `stroke="#${hex(e.colour, "6b7785")}"${e.dashed ? ' stroke-dasharray="4 3"' : ""}`;
    const end = e.arrow === false ? "" : ' marker-end="url(#arrow)"';
    if (e.points?.length > 1) {    // routed at right angles between the boxes (R3.4)
      lines.push(`<polyline points="${e.points.map((p) => p.join(",")).join(" ")}" fill="none" ${stroke}${end}>${e.label ? `<title>${xml(e.label)}</title>` : ""}</polyline>`);
      if (e.short && e.label_at) {
        labels.push(`<text x="${e.label_at[0]}" y="${e.label_at[1]}" font-size="9" fill="#4a5562" paint-order="stroke" stroke="#ffffff" stroke-width="3">${xml(e.short)}<title>${xml(e.label)}</title></text>`);
      }
      continue;
    }
    lines.push(`<line x1="${a.x + a.w / 2}" y1="${a.y + a.h / 2}" x2="${b.x + b.w / 2}" y2="${b.y + b.h / 2}" ${stroke}/>`);
  }
  parts.push(...boxes, ...lines, ...labels, "</svg>");
  return { text: parts.join(""), width: W, height: H };
}

export function downloadPictureSvg(title, nodes, edges) {
  saveBlob(new Blob([pictureSvg(nodes, edges).text], { type: "image/svg+xml" }), `${title}.svg`);
}

export function downloadPicturePng(title, nodes, edges) {
  const { text, width, height } = pictureSvg(nodes, edges);
  svgToPng(text, width, height, title);
}

function svgToPng(t, width, height, name) {
  const w = (width + 40) * 2, h = (height + 40) * 2;
  const img = new Image();
  img.onload = () => {
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, w, h); ctx.drawImage(img, 0, 0, w, h);
    c.toBlob((b) => b && saveBlob(b, `${name}.png`), "image/png");
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(t);
}

// An <svg> on screen as a stand-alone SVG text (white background, the pan and zoom removed)
export function svgText(svg, width, height) {
  if (!svg) return null;
  const copy = svg.cloneNode(true);
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  copy.setAttribute("width", width + 40);
  copy.setAttribute("height", height + 40);
  copy.setAttribute("viewBox", `-20 -20 ${width + 40} ${height + 40}`);
  copy.querySelector("[data-viewport]")?.setAttribute("transform", "");
  const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  Object.entries({ x: -20, y: -20, width: width + 40, height: height + 40, fill: "#ffffff" }).forEach(([k, v]) => bg.setAttribute(k, v));
  copy.insertBefore(bg, copy.firstChild);
  return new XMLSerializer().serializeToString(copy);
}

export function downloadSvg(svg, width, height, name) {
  const t = svgText(svg, width, height);
  if (t) saveBlob(new Blob([t], { type: "image/svg+xml" }), `${name}.svg`);
}

export function downloadPng(svg, width, height, name) {
  const t = svgText(svg, width, height);
  if (t) svgToPng(t, width, height, name);
}
