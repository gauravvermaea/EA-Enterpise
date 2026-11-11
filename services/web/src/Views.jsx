// Model page, tab Views (build phase 8.2, D161):
//   #/metamodel/<model>/views                      every view (VP-01 to VP-26 and the organisation's own),
//                                                        grouped by category, with how many of the model's entities each shows
//   #/metamodel/<model>/views/<code>[/<view>]       the model through one view, as
//        diagram   the elements in bands by domain with the view's relationships (EntityGraph)
//        catalog   one row per element with its key values; CSV
//        heat      tiles grouped by type, coloured by any attribute (a heat map); legend
//        matrix    one type down the side, another across the top, the relationships in the cells
//        rels      every relationship the view shows
//   and a link to the same view in the reporting tool (Superset dashboard VP-xx).
// Library Admins add, change and delete the organisation's own views; the built-in ones are fixed and can be copied.
// A model's own views (D406): copies of a view's definition kept with the model by the views service (MV-<n>), made by
// anyone who may change the model ("Copy as my model's view"), changed or removed there; opened like any view, the
// picture drawn each time and never stored. Every picture offers "Save as a drawn view" and downloads (D407, D408).
import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { apiFetch, can } from "./auth";
import { downloadCsv } from "./exporting";
import { Modal } from "./ModelOps";
import { refreshAll, useApi } from "./ModelViews";
import { DrawnViewsSection, PictureActions, mayDraw } from "./DrawnView";
import { elementTypes } from "./elements.js";

const EntityGraph = lazy(() => import("./EntityGraph"));
const go = (path) => { window.location.hash = path; };
// low to high (owner, 10 Nov 2026): red, then orange, blue in the middle, green at the top; light enough for dark text
export const HEAT = ["ef8a87", "f4a582", "f8bf80", "fbd49c", "b9d7f5", "93c3ef", "a9dca9", "7cc47c"];
const ORDERED = {
  Lifecycle: ["Retired", "Retiring", "Phase Out", "Plan", "Phase In", "Production"],
  Maturity: ["1 - Initial", "2 - Managed", "3 - Defined", "4 - Measured", "5 - Optimised"],
  Priority: ["Won't", "Could", "Should", "Must"],
  "Data Classification": ["Public", "Internal", "Confidential", "Restricted"],
  "Architecture State": ["Baseline", "Transition", "Target"],
  TIME: ["Eliminate", "Migrate", "Tolerate", "Invest"],
};

// a colour for every value of an attribute: numbers low to high, known lists in their order, others by count
export function heatScale(items, attribute, valueOf) {
  const values = items.map((x) => valueOf(x)).filter((v) => v !== undefined && v !== null && v !== "");
  const nums = values.length && values.every((v) => !Number.isNaN(Number(v)));
  if (nums) {
    const n = values.map(Number);
    const lo = Math.min(...n), hi = Math.max(...n);
    const colour = (v) => (v === undefined || v === "" || v === null ? null
      : HEAT[hi === lo ? 3 : Math.round(((Number(v) - lo) / (hi - lo)) * (HEAT.length - 1))]);
    const steps = [...new Set(n)].sort((a, b) => a - b).slice(0, 8);
    return { colour, legend: steps.map((v) => [String(v), colour(v)]) };
  }
  const known = ORDERED[attribute];
  const distinct = known ? known.filter((k) => values.includes(k)).concat([...new Set(values)].filter((v) => !known.includes(v)))
    : [...new Set(values)].sort();
  const map = Object.fromEntries(distinct.map((v, i) => [v, HEAT[distinct.length === 1 ? 3
    : Math.round((i / Math.max(1, distinct.length - 1)) * (HEAT.length - 1))]]));
  return { colour: (v) => map[v] || null, legend: distinct.slice(0, 12).map((v) => [v, map[v]]) };
}

export function Legend({ legend, attribute }) {
  if (!attribute) return null;
  return (
    <div className="heat-legend">
      <strong>{attribute}:</strong>
      {legend.map(([v, c]) => <span key={v} className="legend-chip"><span className="heat-swatch" style={{ background: `#${c}` }} />{v}</span>)}
      <span className="legend-chip"><span className="heat-swatch empty" />not set</span>
    </div>
  );
}

const own = (model) => `/api/views/v1/models/${model}/own-views`;
const isOwn = (code) => /^MV-\d+$/i.test(code || "");

// the model through a view: a standard one by its code, the model's own by its definition (rendered by the main API)
function useView(model, code) {
  const std = useApi(isOwn(code) ? null : `/api/v1/models/${model}/views/${encodeURIComponent(code)}`);
  const [got, setGot] = useState({ data: null, error: null });
  useEffect(() => {
    if (!isOwn(code)) return undefined;
    let live = true;
    setGot({ data: null, error: null });
    apiFetch(`${own(model)}/${encodeURIComponent(code)}`)
      .then((def) => apiFetch(`/api/v1/models/${model}/views/render`, { method: "POST", body: JSON.stringify(def) })
        .then((d) => live && setGot({ data: { ...d, view: { ...d.view, ...def, own: true } }, error: null })))
      .catch((e) => live && setGot({ data: null, error: e.message }));
    return () => { live = false; };
  }, [model, code]);
  return isOwn(code) ? got : std;
}

// the Views tab's sub-tabs (owner, 10 Nov 2026, D412): #/metamodel/<m>/views/custom|standard. Custom views are the model's
// own, whoever made them: its drawn views and its copies of generated views (MV-n), in one list; standard views are the
// organisation's (VP-n). With no sub-tab named: Custom views when the model has any, else Standard views. A view code opens
// that view; the older drawn and own addresses land on Custom views.
const VIEW_TABS = [["custom", "Custom views"], ["standard", "Standard views"]];
const OLD_TABS = { drawn: "custom", own: "custom" };
export default function ViewsTab({ model, m, code, sub }) {
  const c = code ? decodeURIComponent(code) : "";
  if (c && !VIEW_TABS.some(([k]) => k === c) && !OLD_TABS[c]) return <ViewPage key={c} model={model} m={m} code={c} sub={sub} />;
  return <ViewList model={model} m={m} tab={OLD_TABS[c] || c} />;
}

function ViewList({ model, m, tab: asked }) {
  const { data, error } = useApi(`/api/v1/models/${model}/views`);
  const mine = useApi(own(model));
  const drawn = useApi(`/api/views/v1/models/${model}/drawn-views`);   // the views service (D405)
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const curate = can("library.curate");
  const customCount = mine.data || drawn.data ? (mine.data?.views.length || 0) + (drawn.data?.views.length || 0) : null;
  const tab = asked || (customCount === null && !mine.error && !drawn.error ? "" : customCount ? "custom" : "standard");
  const groups = useMemo(() => {
    if (!data) return [];
    const f = filter.trim().toLowerCase();
    const out = [];
    for (const v of data) {
      if (f && !`${v.code} ${v.name} ${v.concerns} ${v.stakeholders}`.toLowerCase().includes(f)) continue;
      const cat = v.is_builtin ? v.category : `Your own: ${v.category}`;
      let g = out.find((x) => x.name === cat);
      if (!g) out.push(g = { name: cat, items: [] });
      g.items.push(v);
    }
    return out;
  }, [data, filter]);
  const tabs = (
    <div className="tabs sub" role="tablist">
      {VIEW_TABS.map(([k, label]) => (
        <a key={k} role="tab" aria-selected={tab === k} className={`tab${tab === k ? " on" : ""}`} href={`#/metamodel/${model}/views/${k}`}>
          {label}{k === "custom" && customCount !== null ? ` (${customCount})` : k === "standard" && data ? ` (${data.length})` : ""}</a>))}
    </div>);
  if (!tab) return <div className="views">{tabs}<p>Loading...</p></div>;
  if (tab === "custom") {
    const f = filter.trim().toLowerCase();
    const generated = (mine.data?.views || []).filter((v) => !f || `${v.code} ${v.name} ${v.concerns} ${v.stakeholders}`.toLowerCase().includes(f));
    return (
      <div className="views">
        {tabs}
        <p className="quiet">This model's own views, whoever made them: <b>drawn</b> views, drawn in draw.io from the model's entities and
          relationships, and <b>generated</b> views, copies of a standard view's definition changed for {m.name} (open a standard view
          and choose <em>Copy as my model's view</em>). They travel with the model when it is copied or packaged.</p>
        <div className="toolbar">
          <input type="search" placeholder="Filter the custom views" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        {mine.error && <p className="status warn">{mine.error}</p>}
        <DrawnViewsSection model={model} m={m} generated={generated} filter={f} />
      </div>);
  }
  if (error) return <div className="views">{tabs}<p className="status bad">{error}</p></div>;
  if (!data) return <div className="views">{tabs}<p>Loading...</p></div>;
  return (
    <div className="views">
      {tabs}
      <p className="quiet">
        A view shows <strong>{m.name}</strong> for one set of concerns: the element and relationship types that matter to
        them, as a diagram, a catalog, a heat map, a matrix or a list of relationships. VP-01 to VP-25 are the example
        views of the ArchiMate 4 Specification, VP-26 shows the gaps of gap analyses; each is also a dashboard in the reporting tool (Reports tab).
        Open one and choose <em>Copy as my model's view</em> to keep a changed copy under <a href={`#/metamodel/${model}/views/custom`}>Custom views</a>.
      </p>
      <div className="toolbar">
        <input type="search" placeholder="Filter views, concerns or stakeholders" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <span className="er-spacer" />
        <button disabled={!curate} title={curate ? "Make a view of your own for the whole organisation: choose its element and relationship types"
          : "Needs the Library Admin role"} onClick={() => setEditing({})}>+ New standard view</button>
      </div>
      {groups.map((g) => (
        <section key={g.name}>
          <h3 className="vp-group">{g.name}</h3>
          <div className="report-cards">
            {g.items.map((v) => (
              <a key={v.code} className={v.entities ? "report-card" : "report-card empty-card"} href={`#/metamodel/${model}/views/${encodeURIComponent(v.code)}`}
                title={`${v.purpose}. Stakeholders: ${v.stakeholders}`}>
                <span className="report-code">{v.code}</span>
                <strong>{v.name}</strong>
                {v.source && <span className="vp-source" title={v.source}>ArchiMate 4</span>}
                <span className="quiet">{v.concerns}</span>
                <span className="vp-count">{v.entities ? `${v.entities} entities in ${v.types_present.length} of ${v.element_types.length} types`
                  : "Nothing in this model yet"}</span>
              </a>
            ))}
          </div>
        </section>
      ))}
      {!groups.length && <p className="quiet">No views match.</p>}
      {editing && <ViewDialog model={model} start={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

const SUBS = [
  ["diagram", "Diagram", "The elements in bands by domain, with the relationships the view shows"],
  ["catalog", "Catalog", "One row per element with its key values"],
  ["heat", "Heat map", "The elements as tiles grouped by type, coloured by an attribute you choose"],
  ["matrix", "Matrix", "One type against another, with the relationships between their elements"],
  ["rels", "Relationships", "Every relationship the view shows"],
];

function ViewPage({ model, m, code, sub }) {
  const { data, error } = useView(model, code);
  const reports = useApi(`/api/v1/models/${model}/reports`);
  const [editing, setEditing] = useState(null);
  const [owning, setOwning] = useState(null);           // the model's own view being made or changed
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading the view...</p>;
  const vp = data.view;
  // the form it opens in: the one asked for, else the view's own (a TOGAF catalogue opens as a catalog, D345)
  const s = SUBS.some(([k]) => k === sub) ? sub : SUBS.some(([k]) => k === vp.default_view) ? vp.default_view : "diagram";
  const dash = reports.data?.reports.find((r) => r.code === vp.code);
  const curate = can("library.curate");
  const may = mayDraw(model, m);
  return (
    <div className="view">
      <p className="crumbs"><a href={`#/metamodel/${model}/views/${vp.own ? "custom" : "standard"}`}>{vp.own ? "Custom views" : "Standard views"}</a> › {vp.code}</p>
      <div className="vp-head">
        <div>
          <h2>{vp.code} {vp.name} <span className="quiet vp-cat">{vp.category}</span></h2>
          {vp.source && <p className="vp-source-line"><span className="vp-source">ArchiMate 4</span> From the {vp.source}: its name, purpose,
            stakeholders and elements are the specification's; the concerns are described in our own words.</p>}
          {vp.togaf_artifact && <p className="vp-source-line"><span className="vp-source togaf">TOGAF</span> Gives the TOGAF business architecture
            artifact <b>{vp.togaf_artifact}</b>{vp.code > "VP-26" ? " (EA Explorer's view for it)" : ""}.</p>}
          <p><strong>Concerns:</strong> {vp.concerns}</p>
          <p className="quiet"><strong>Stakeholders:</strong> {vp.stakeholders} · <strong>Purpose:</strong> {vp.purpose}</p>
          <p className="quiet"><strong>Elements:</strong> {vp.element_types.map(spaced).join(", ")}
            {" · "}<strong>Relationships:</strong> {vp.relationship_types.length ? vp.relationship_types.join(", ") : "every type"}</p>
        </div>
        <div className="vp-actions">
          {dash && <a className="button" href={dash.url} target="_blank" rel="noreferrer" title="The same view as a dashboard in the reporting tool">Open in the reporting tool</a>}
          <button disabled={!may} title={may ? "A copy of this view's definition kept with this model, to change for it (D406)"
            : "Needs a role that may change this model's content"}
            onClick={() => setOwning({ ...vp, name: `${vp.name} (${m.name})`, copied_from: vp.copied_from && vp.own ? vp.copied_from : vp.code, _new: true })}>
            Copy as my model's view</button>
          {vp.own && may && <button onClick={() => setOwning({ ...vp })}>Edit</button>}
          {!vp.own && <button disabled={!curate} title={curate ? "Make an organisation-wide view starting from this one" : "Needs the Library Admin role"}
            onClick={() => setEditing({ ...vp, code: "", name: `${vp.name} (copy)` })}>Copy for everyone</button>}
          {!vp.own && !vp.is_builtin && <button disabled={!curate} onClick={() => setEditing({ ...vp, _code: vp.code })}>Edit</button>}
        </div>
      </div>
      <p className="quiet">{data.entities.length} elements and {data.relationships.length} relationships of {m.name} in this view
        {data.types.length ? `: ${data.types.map((t) => `${t.count} ${t.name}`).join(", ")}` : "."}</p>
      <div className="seg" role="tablist" aria-label="Show the view as">
        {SUBS.map(([k, label, help]) => (
          <button key={k} role="tab" aria-selected={s === k} className={s === k ? "on" : ""} title={help}
            onClick={() => go(`/metamodel/${model}/views/${encodeURIComponent(vp.code)}/${k}`)}>{label}</button>
        ))}
      </div>
      {!data.entities.length ? <p className="quiet">This model has no entities of the view's types yet.</p>
        : s === "diagram" ? (
          <Suspense fallback={<p>Loading the picture...</p>}>
            <EntityGraph model={model} kind="domains" presetTypeCodes={vp.element_types} onlyRels={vp.relationship_types} />
          </Suspense>)
        : s === "catalog" ? <Catalog data={data} model={model} />
        : s === "heat" ? <HeatMap data={data} model={model} />
        : s === "matrix" ? <Matrix data={data} model={model} />
        : <Relationships data={data} model={model} />}
      {editing && <ViewDialog model={model} start={editing} onClose={() => setEditing(null)} />}
      {owning && <ViewDialog model={model} start={owning} ownView onClose={() => setOwning(null)} />}
    </div>
  );
}

const KEY_ATTRS = ["Owner", "Lifecycle", "Criticality", "Maturity", "Priority", "Data Classification", "Architecture State"];

function Catalog({ data, model }) {
  const [filter, setFilter] = useState("");
  const cols = KEY_ATTRS.filter((a) => data.attributes.includes(a));
  const rows = data.entities.filter((e) => !filter || `${e.name} ${e.display_id} ${e.entity_type} ${Object.values(e.values).join(" ")}`
    .toLowerCase().includes(filter.toLowerCase()));
  return (
    <div>
      <div className="toolbar">
        <input type="search" placeholder="Filter" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button onClick={() => downloadCsv([["Domain", "Type", "ID", "Name", "Description", "Part of", ...data.attributes],
          ...rows.map((e) => [e.domain, e.entity_type, e.display_id, e.name, e.description, e.parent || "",
            ...data.attributes.map((a) => e.values[a] || "")])], `${data.model.name} ${data.view.code} catalog`)}
          title="Every element with every attribute, as CSV (opens in Excel)">CSV</button>
      </div>
      <table className="grid-table">
        <thead><tr><th>Domain</th><th>Type</th><th>ID</th><th>Name</th><th>Part of</th>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td><span className="heat-swatch" style={{ background: `#${e.colour}` }} /> {e.domain}</td>
              <td>{e.entity_type}</td><td className="quiet">{e.display_id}</td>
              <td><a href={`#/metamodel/${model}/entity/${e.id}`}>{e.name}</a></td>
              <td className="quiet">{e.parent || ""}</td>
              {cols.map((c) => <td key={c}>{e.values[c] || ""}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HeatMap({ data, model }) {
  const [attr, setAttr] = useState(data.heat_attribute || data.attributes[0] || "");
  const scale = useMemo(() => heatScale(data.entities, attr, (e) => e.values[attr]), [data, attr]);
  return (
    <div>
      <div className="toolbar">
        <label>Colour by <select value={attr} onChange={(e) => setAttr(e.target.value)}>
          {data.attributes.map((a) => <option key={a} value={a}>{a}</option>)}
        </select></label>
        <Legend legend={scale.legend} attribute={attr} />
        <PictureActions model={model} picture={() => heatPicture(data, attr, scale)} />
      </div>
      <div className="heat-groups">
        {data.types.map((t) => (
          <section key={t.code} className="heat-group">
            <h4><span className="heat-swatch" style={{ background: `#${t.colour}` }} /> {t.name} <span className="quiet">({t.count})</span></h4>
            <Tiles items={data.entities.filter((e) => e.type_code === t.code)} model={model} attr={attr} scale={scale} />
          </section>
        ))}
      </div>
    </div>
  );
}

// the heat map as a picture (D407, D408): per type a title and its entities as boxes in their notation, coloured by the
// chosen attribute; a parent holds its parts; the legend under it
function heatPicture(data, attr, scale) {
  const nodes = [];
  const TW = 170, TH = 50, GAP = 10, PER_ROW = 6;
  let y = 0;
  const fill = (e) => scale.colour(e.values[attr]) || "eeeeee";
  const ea = (e) => ({ ea_type: e.type_code || e.entity_type, ea_id: e.id, ea_domain: e.domain });
  for (const t of data.types) {
    nodes.push({ id: `h_${t.code}`, label: `${t.name} (${t.count})`, x: 0, y, w: 400, h: 30, shape: "text", fontSize: 14, bold: true });
    y += 40;
    const items = data.entities.filter((e) => e.type_code === t.code);
    const names = new Set(items.map((e) => e.name));
    const kids = {};
    for (const e of items) if (e.parent && names.has(e.parent)) (kids[e.parent] ||= []).push(e);
    const tops = items.filter((e) => !e.parent || !names.has(e.parent));
    let x = 0, rowH = 0;
    const place = (w, h) => {
      if (x + w > PER_ROW * (TW + GAP)) { x = 0; y += rowH + GAP; rowH = 0; }
      const at = { x, y }; x += w + GAP; rowH = Math.max(rowH, h); return at;
    };
    for (const e of tops) {
      const children = kids[e.name] || [];
      if (!children.length) {
        const at = place(TW, TH);
        nodes.push({ id: e.id, label: e.name, sub: e.values[attr] || "", ...at, w: TW, h: TH, fill: fill(e), heatFill: fill(e), ...ea(e) });
        continue;
      }
      const cols = 2, cw = 140, ch = 50;
      const w = 10 + cols * (cw + 10), h = 40 + Math.ceil(children.length / cols) * (ch + 10);
      const at = place(w, h);
      nodes.push({ id: e.id, label: `${e.name}${e.values[attr] ? ` (${e.values[attr]})` : ""}`, ...at, w, h, fill: fill(e), heatFill: fill(e),
        container: true, bold: true, ...ea(e) });
      children.forEach((k, i) => nodes.push({ id: k.id, label: k.name, sub: k.values[attr] || "", parent: e.id,
        x: at.x + 10 + (i % cols) * (cw + 10), y: at.y + 40 + Math.floor(i / cols) * (ch + 10), w: cw, h: ch, fill: fill(k), heatFill: fill(k),
        fontSize: 11, ...ea(k) }));
    }
    y += rowH + 30;
  }
  scale.legend.forEach(([v, c], i) => nodes.push({ id: `l_${i}`, label: v, x: i * 130, y, w: 120, h: 30, fill: c, fontSize: 11, align: "center" }));
  return { title: `${data.model.name} ${data.view.code} heat map by ${attr}`, nodes, edges: [] };
}

// the matrix as a picture (D407, D408): a table of boxes, the row and column heads the entities in their notation
function matrixPicture(data, rows, cols, cell) {
  const W = 120, H = 30, HW = 220, HH = 110;
  const nodes = [{ id: "corner", label: `${data.view.code} ${data.view.name}`, x: 0, y: 0, w: HW, h: HH, fill: "f6f7f9", bold: true, keepSize: true }];
  cols.forEach((c, j) => nodes.push({ id: `c_${c.id}`, label: c.name, x: HW + j * W, y: 0, w: W, h: HH, fill: c.colour, align: "center",
    fontSize: 11, ea_type: c.type_code || c.entity_type, ea_id: c.id, keepSize: true }));
  rows.forEach((r, i) => {
    nodes.push({ id: `r_${r.id}`, label: r.name, x: 0, y: HH + i * H, w: HW, h: H, fill: r.colour, fontSize: 11, ea_type: r.type_code || r.entity_type,
      ea_id: r.id, keepSize: true });
    cols.forEach((c, j) => {
      const v = cell[`${r.id}|${c.id}`];
      nodes.push({ id: `x_${i}_${j}`, label: v ? v.join(", ") : "", x: HW + j * W, y: HH + i * H, w: W, h: H, fill: v ? "e8f0fb" : "ffffff",
        stroke: "d9dee5", align: "center", fontSize: 9, keepSize: true });
    });
  });
  return { title: `${data.model.name} ${data.view.code} matrix`, nodes, edges: [] };
}

// tiles of one type; parents with parts in the same type hold their parts (a capability map by level)
function Tiles({ items, model, attr, scale }) {
  const names = new Set(items.map((e) => e.name));
  const kids = {};
  for (const e of items) if (e.parent && names.has(e.parent)) (kids[e.parent] ||= []).push(e);
  const tops = items.filter((e) => !e.parent || !names.has(e.parent));
  const tile = (e) => {
    const c = scale.colour(e.values[attr]);
    return (
      <a key={e.id} className={c ? "heat-tile" : "heat-tile none"} style={c ? { background: `#${c}` } : undefined}
        href={`#/metamodel/${model}/entity/${e.id}`} title={`${e.name}\n${attr}: ${e.values[attr] ?? "not set"}`}>
        <span>{e.name}</span><span className="heat-value">{e.values[attr] ?? ""}</span>
      </a>
    );
  };
  const box = (e) => (
    <div key={e.id} className="heat-box">
      {tile(e)}
      <div className="heat-box-kids">{kids[e.name].map((k) => (kids[k.name] ? box(k) : tile(k)))}</div>
    </div>
  );
  const nested = tops.filter((e) => kids[e.name]);
  const flat = tops.filter((e) => !kids[e.name]);
  return (
    <>
      {nested.length > 0 && <div className="heat-boxes">{nested.map(box)}</div>}
      {flat.length > 0 && <div className="heat-tiles">{flat.map(tile)}</div>}
    </>
  );
}

const spaced = (code) => code.replace(/([a-z])([A-Z])/g, "$1 $2");

function Matrix({ data, model }) {
  const types = data.types;
  const counts = useMemo(() => {
    const n = {};
    const typeOf = Object.fromEntries(data.entities.map((e) => [e.id, e.type_code]));
    for (const r of data.relationships) {
      const k = `${typeOf[r.source]}|${typeOf[r.target]}`;
      n[k] = (n[k] || 0) + 1;
    }
    return n;
  }, [data]);
  const best = useMemo(() => Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0]?.split("|") || [], [counts]);
  const [rowType, setRowType] = useState(best[0] || types[0]?.code || "");
  const [colType, setColType] = useState(best[1] || types[1]?.code || types[0]?.code || "");
  const rows = data.entities.filter((e) => e.type_code === rowType);
  const cols = data.entities.filter((e) => e.type_code === colType);
  const cell = useMemo(() => {
    const out = {};
    for (const r of data.relationships) {
      for (const [a, b, dir] of [[r.source, r.target, "→"], [r.target, r.source, "←"]]) {
        (out[`${a}|${b}`] ||= []).push(`${dir} ${r.verb || r.relationship_type}`);
      }
    }
    return out;
  }, [data]);
  const linkedCols = cols.filter((c) => rows.some((r) => cell[`${r.id}|${c.id}`]));
  const linkedRows = rows.filter((r) => cols.some((c) => cell[`${r.id}|${c.id}`]));
  return (
    <div>
      <div className="toolbar">
        <label>Down the side <select value={rowType} onChange={(e) => setRowType(e.target.value)}>
          {types.map((t) => <option key={t.code} value={t.code}>{t.name} ({t.count})</option>)}</select></label>
        <label>Across the top <select value={colType} onChange={(e) => setColType(e.target.value)}>
          {types.map((t) => <option key={t.code} value={t.code}>{t.name} ({t.count})</option>)}</select></label>
        <PictureActions model={model} disabled={!linkedRows.length} picture={() => matrixPicture(data, linkedRows, linkedCols, cell)} />
        <button onClick={() => downloadCsv([["", ...linkedCols.map((c) => c.name)],
          ...linkedRows.map((r) => [r.name, ...linkedCols.map((c) => (cell[`${r.id}|${c.id}`] || []).join("; "))])],
        `${data.model.name} ${data.view.code} matrix`)}>CSV</button>
      </div>
      {!linkedRows.length ? <p className="quiet">No relationships between these two types in this view.</p> : (
        <div className="vp-matrix-wrap">
          <table className="grid-table vp-matrix">
            <thead><tr><th />{linkedCols.map((c) => <th key={c.id} className="rot"><a href={`#/metamodel/${model}/entity/${c.id}`}>{c.name}</a></th>)}</tr></thead>
            <tbody>
              {linkedRows.map((r) => (
                <tr key={r.id}>
                  <th><a href={`#/metamodel/${model}/entity/${r.id}`}>{r.name}</a></th>
                  {linkedCols.map((c) => {
                    const v = cell[`${r.id}|${c.id}`];
                    return <td key={c.id} className={v ? "hit" : ""} title={v ? `${r.name} ${v.join(", ")} ${c.name}` : ""}>{v ? v.length : ""}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Relationships({ data, model }) {
  const byId = Object.fromEntries(data.entities.map((e) => [e.id, e]));
  return (
    <div>
      <div className="toolbar">
        <button onClick={() => downloadCsv([["Source type", "Source", "Relationship", "Target type", "Target", "Name"],
          ...data.relationships.map((r) => [byId[r.source]?.entity_type, byId[r.source]?.name, r.relationship_type,
            byId[r.target]?.entity_type, byId[r.target]?.name, r.name || ""])], `${data.model.name} ${data.view.code} relationships`)}>CSV</button>
      </div>
      <table className="grid-table">
        <thead><tr><th>Source</th><th>Relationship</th><th>Target</th><th>Name</th></tr></thead>
        <tbody>
          {data.relationships.map((r) => (
            <tr key={r.id}>
              <td><a href={`#/metamodel/${model}/entity/${r.source}`}>{byId[r.source]?.name}</a> <span className="quiet">{byId[r.source]?.entity_type}</span></td>
              <td>{r.verb || r.relationship_type}</td>
              <td><a href={`#/metamodel/${model}/entity/${r.target}`}>{byId[r.target]?.name}</a> <span className="quiet">{byId[r.target]?.entity_type}</span></td>
              <td className="quiet">{r.name || ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Add, change, copy or delete one of the organisation's own views (Library Admins), or, with ownView, a view of the
// model's own (D406: anyone who may change the model; kept by the views service)
function ViewDialog({ model, start, onClose, ownView = false }) {
  const [mm, setMm] = useState(null);
  const [v, setV] = useState({
    code: start.code || "", name: start.name || "", category: ownView ? (start.own ? start.category || "Model" : "Model") : start.is_builtin ? "Organisation" : start.category || "Organisation",
    purpose: start.purpose || "", concerns: start.concerns || "", stakeholders: start.stakeholders || "",
    element_types: start.element_types || [], relationship_types: start.relationship_types || [],
    heat_attribute: start.heat_attribute || "Lifecycle", audiences: start.audiences || [],
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const editing = ownView ? !start._new : !!start._code;
  useEffect(() => { apiFetch(`/api/v1/models/${model}/metamodel`).then(setMm).catch((e) => setError(e.message)); }, [model]);
  const set = (k, val) => setV((x) => ({ ...x, [k]: val }));
  const toggle = (k, code) => set(k, v[k].includes(code) ? v[k].filter((c) => c !== code) : [...v[k], code]);
  const save = async () => {
    setBusy(true); setError(null);
    try {
      const out = ownView
        ? await apiFetch(editing ? `${own(model)}/${encodeURIComponent(start.code)}` : own(model),
          { method: editing ? "PUT" : "POST", body: JSON.stringify({ ...v, copied_from: start.copied_from || "" }) })
        : await apiFetch(editing ? `/api/v1/views/${encodeURIComponent(start._code)}` : "/api/v1/views",
          { method: editing ? "PUT" : "POST", body: JSON.stringify(v) });
      refreshAll();
      onClose();
      go(`/metamodel/${model}/views/${encodeURIComponent(out.code)}`);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try {
      await apiFetch(ownView ? `${own(model)}/${encodeURIComponent(start.code)}` : `/api/v1/views/${encodeURIComponent(start._code)}`, { method: "DELETE" });
      refreshAll(); onClose(); go(`/metamodel/${model}/views/${ownView ? "custom" : "standard"}`);
    }
    catch (e) { setError(e.message); setBusy(false); }
  };
  return (
    <Modal wide title={ownView ? (editing ? `Change ${start.code}, this model's view` : "Copy as my model's view")
      : editing ? `Change ${start._code}` : "New view"} onClose={onClose} actions={<>
      {editing && <button className="danger" disabled={busy} onClick={remove}>Delete</button>}
      <span className="er-spacer" />
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={busy || (!ownView && !v.code) || !v.name || !v.element_types.length} onClick={save}>Save</button>
    </>}>
      <div className="ed-form">
        {error && <p className="status bad">{error}</p>}
        <div className="vp-form-row">
          {ownView ? <p className="quiet">{start.copied_from ? `A copy of ${start.copied_from}'s definition, ` : ""}kept with this model: it travels with it
            when the model is copied or packaged.</p>
            : <label className="ed-field"><span>Code <span className="quiet">for example OVP-01 (VP-numbers are the built-in ones)</span></span>
              <input value={v.code} onChange={(e) => set("code", e.target.value.toUpperCase())} /></label>}
          <label className="ed-field"><span>Name</span><input value={v.name} onChange={(e) => set("name", e.target.value)} /></label>
          <label className="ed-field"><span>Category</span><input value={v.category} onChange={(e) => set("category", e.target.value)} /></label>
        </div>
        <label className="ed-field"><span>Concerns <span className="quiet">what it answers</span></span>
          <textarea value={v.concerns} onChange={(e) => set("concerns", e.target.value)} /></label>
        <div className="vp-form-row">
          <label className="ed-field"><span>Stakeholders</span><input value={v.stakeholders} onChange={(e) => set("stakeholders", e.target.value)} /></label>
          <label className="ed-field"><span>Purpose</span><input value={v.purpose} onChange={(e) => set("purpose", e.target.value)} /></label>
          <label className="ed-field"><span>Heat map colours by <span className="quiet">attribute code</span></span>
            <input value={v.heat_attribute} onChange={(e) => set("heat_attribute", e.target.value)} /></label>
        </div>
        {!mm ? <p className="quiet">Loading the types...</p> : <>
          <div className="ed-field"><span>Element types ({v.element_types.length})</span>
            <div className="vp-checks">
              {mm.domains.map((l) => (
                <div key={l.id} className="vp-domain"><strong>{l.name}</strong>
                  {elementTypes(l).map((t) => (
                    <label key={t.id}><input type="checkbox" checked={v.element_types.includes(t.code)} onChange={() => toggle("element_types", t.code)} /> {t.name}</label>
                  ))}
                </div>
              ))}
            </div>
          </div>
          <div className="ed-field"><span>Relationship types <span className="quiet">none ticked: every type</span></span>
            <div className="vp-checks inline">
              {mm.relationship_types.map((r) => (
                <label key={r.id}><input type="checkbox" checked={v.relationship_types.includes(r.code)} onChange={() => toggle("relationship_types", r.code)} /> {r.name}</label>
              ))}
            </div>
          </div>
        </>}
      </div>
    </Modal>
  );
}
