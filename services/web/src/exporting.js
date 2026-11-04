// Saving what a screen shows: CSV for tables, .drawio for pictures.
// The .drawio files are plain (uncompressed) draw.io XML that opens in the hosted draw.io and the
// desktop app. Every box that stands for an entity carries ea_type (its entity type) and ea_id (its
// guid) as shape data, the same tags as the metamodel ER diagram, so later phases can read files back.

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
  saveBlob(new Blob(["﻿" + toCsv(rows)], { type: "text/csv;charset=utf-8" }), name.endsWith(".csv") ? name : `${name}.csv`);
}

// ---------------------------------------------------------------- draw.io
const xml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const hex = (c, fallback = "eeeeee") => String(c || fallback).replace(/^#/, "");

// nodes: { id, label, sub?, x, y, w, h (absolute), fill?, stroke?, fontColor?, container?, parent? (a node id),
//          ea_type?, ea_id?, ea_layer?, dashed?, bold?, fontSize?, align? ('left'|'center'), shape? ('text') }
// edges: { id?, source, target, label?, colour?, dashed?, arrow? (default true) }
export function drawioXml(title, nodes, edges = []) {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>'];
  const cellId = (id) => `n_${String(id).replace(/[^A-Za-z0-9_-]/g, "_")}`;
  for (const n of nodes) {
    const parent = n.parent && byId[n.parent] ? byId[n.parent] : null;
    const x = Math.round(n.x - (parent ? parent.x : 0)), y = Math.round(n.y - (parent ? parent.y : 0));
    const label = n.sub ? `<b>${xml(n.label)}</b><br><font style="font-size:10px" color="#5b6775">${xml(n.sub)}</font>`
      : n.bold ? `<b>${xml(n.label)}</b>` : xml(n.label);
    const style = n.shape === "text"
      ? `text;html=1;align=${n.align || "left"};verticalAlign=middle;fontSize=${n.fontSize || 12};fontColor=#${hex(n.fontColor, "5b6775")};`
      : [
        "rounded=1", "arcSize=6", "whiteSpace=wrap", "html=1",
        `align=${n.align || "left"}`, `verticalAlign=${n.container ? "top" : "middle"}`, "spacingLeft=6", "spacingTop=2",
        `fillColor=#${hex(n.fill)}`, `strokeColor=#${hex(n.stroke, "8a96a3")}`, `fontSize=${n.fontSize || 12}`,
        n.fontColor ? `fontColor=#${hex(n.fontColor)}` : "", n.dashed ? "dashed=1" : "",
        n.container ? "container=1;collapsible=0" : "",
      ].filter(Boolean).join(";") + ";";
    const geometry = `<mxGeometry x="${x}" y="${y}" width="${Math.round(n.w)}" height="${Math.round(n.h)}" as="geometry"/>`;
    const parentId = parent ? cellId(parent.id) : "1";
    if (n.ea_id) {
      cells.push(`<UserObject id="${cellId(n.id)}" label="${xml(label)}" ea_type="${xml(n.ea_type)}" ea_id="${xml(n.ea_id)}"` +
        `${n.ea_layer ? ` ea_layer="${xml(n.ea_layer)}"` : ""}><mxCell style="${style}" vertex="1" parent="${parentId}">${geometry}</mxCell></UserObject>`);
    } else {
      cells.push(`<mxCell id="${cellId(n.id)}" value="${xml(label)}" style="${style}" vertex="1" parent="${parentId}">${geometry}</mxCell>`);
    }
  }
  edges.forEach((e, i) => {
    if (!byId[e.source] || !byId[e.target]) return;
    const colour = hex(e.colour, "6b7785");
    cells.push(`<mxCell id="e_${i}" value="${xml(e.label || "")}" style="html=1;rounded=0;endArrow=${e.arrow === false ? "none" : "block"};endFill=1;` +
      `strokeColor=#${colour};fontSize=10;fontColor=#${colour};labelBackgroundColor=#ffffff;${e.dashed ? "dashed=1;" : ""}" ` +
      `edge="1" parent="1" source="${cellId(e.source)}" target="${cellId(e.target)}"><mxGeometry relative="1" as="geometry"/></mxCell>`);
  });
  return '<mxfile host="EA Explorer" type="device">' +
    `<diagram id="ea" name="${xml(title)}"><mxGraphModel grid="1" gridSize="10" page="0"><root>` +
    cells.join("") + "</root></mxGraphModel></diagram></mxfile>";
}

export function downloadDrawio(title, nodes, edges) {
  saveBlob(new Blob([drawioXml(title, nodes, edges)], { type: "application/xml" }), `${title}.drawio`);
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
  if (!t) return;
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
