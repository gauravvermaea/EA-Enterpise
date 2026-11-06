// Model page, tab Viewpoints (build phase 8.2, D161):
//   #/metamodel/<model>/viewpoints                      every viewpoint (VP-01 to VP-26 and the organisation's own),
//                                                        grouped by category, with how many of the model's entities each shows
//   #/metamodel/<model>/viewpoints/<code>[/<view>]       the model through one viewpoint, as
//        diagram   the elements in bands by layer with the viewpoint's relationships (EntityGraph)
//        catalog   one row per element with its key values; CSV
//        heat      tiles grouped by type, coloured by any attribute (a heat map); legend
//        matrix    one type down the side, another across the top, the relationships in the cells
//        rels      every relationship the viewpoint shows
//   and a link to the same viewpoint in the reporting tool (Superset dashboard VP-xx).
// Library Admins add, change and delete the organisation's own viewpoints; the built-in ones are fixed and can be copied.
import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { apiFetch, can } from "./auth";
import { downloadCsv, downloadDrawio } from "./exporting";
import { Modal } from "./ModelOps";
import { refreshAll, useApi } from "./ModelViews";

const EntityGraph = lazy(() => import("./EntityGraph"));
const go = (path) => { window.location.hash = path; };
// light to strong: pick lists of up to 8 values; numbers are spread over it
export const HEAT = ["e8f5e9", "c8e6c9", "fff3c4", "ffe0a3", "ffc48a", "ff9e80", "f28b82", "d96b6b"];
const ORDERED = {
  Lifecycle: ["Plan", "Phase In", "Production", "Phase Out", "Retiring", "Retired"],
  Maturity: ["5 - Optimised", "4 - Measured", "3 - Defined", "2 - Managed", "1 - Initial"],
  Priority: ["Won't", "Could", "Should", "Must"],
  "Data Classification": ["Public", "Internal", "Confidential", "Restricted"],
  "Architecture State": ["Baseline", "Transition", "Target"],
  TIME: ["Invest", "Tolerate", "Migrate", "Eliminate"],
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

export default function ViewpointsTab({ model, m, code, sub }) {
  return code ? <ViewpointPage key={code} model={model} m={m} code={decodeURIComponent(code)} sub={sub} />
    : <ViewpointList model={model} m={m} />;
}

function ViewpointList({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/viewpoints`);
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const curate = can("library.curate");
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
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  return (
    <div className="viewpoints">
      <p className="quiet">
        A viewpoint shows <strong>{m.name}</strong> for one set of concerns: the element and relationship types that matter to
        them, as a diagram, a catalog, a heat map, a matrix or a list of relationships. VP-01 to VP-25 are the example
        viewpoints of the ArchiMate 4 Specification, VP-26 shows the gaps of gap analyses; each is also a dashboard in the reporting tool (Reports tab).
      </p>
      <div className="toolbar">
        <input type="search" placeholder="Filter viewpoints, concerns or stakeholders" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <span className="er-spacer" />
        <button disabled={!curate} title={curate ? "Make a viewpoint of your own: choose its element and relationship types"
          : "Needs the Library Admin role"} onClick={() => setEditing({})}>+ New viewpoint</button>
      </div>
      {groups.map((g) => (
        <section key={g.name}>
          <h3 className="vp-group">{g.name}</h3>
          <div className="report-cards">
            {g.items.map((v) => (
              <a key={v.code} className={v.entities ? "report-card" : "report-card empty-card"} href={`#/metamodel/${model}/viewpoints/${encodeURIComponent(v.code)}`}
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
      {!groups.length && <p className="quiet">No viewpoints match.</p>}
      {editing && <ViewpointDialog model={model} start={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

const SUBS = [
  ["diagram", "Diagram", "The elements in bands by layer, with the relationships the viewpoint shows"],
  ["catalog", "Catalog", "One row per element with its key values"],
  ["heat", "Heat map", "The elements as tiles grouped by type, coloured by an attribute you choose"],
  ["matrix", "Matrix", "One type against another, with the relationships between their elements"],
  ["rels", "Relationships", "Every relationship the viewpoint shows"],
];

function ViewpointPage({ model, m, code, sub }) {
  const { data, error } = useApi(`/api/v1/models/${model}/viewpoints/${encodeURIComponent(code)}`);
  const reports = useApi(`/api/v1/models/${model}/reports`);
  const [editing, setEditing] = useState(null);
  const s = SUBS.some(([k]) => k === sub) ? sub : "diagram";
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading the viewpoint...</p>;
  const vp = data.viewpoint;
  const dash = reports.data?.reports.find((r) => r.code === vp.code);
  const curate = can("library.curate");
  return (
    <div className="viewpoint">
      <p className="crumbs"><a href={`#/metamodel/${model}/viewpoints`}>Viewpoints</a> › {vp.code}</p>
      <div className="vp-head">
        <div>
          <h2>{vp.code} {vp.name} <span className="quiet vp-cat">{vp.category}</span></h2>
          {vp.source && <p className="vp-source-line"><span className="vp-source">ArchiMate 4</span> From the {vp.source}: its name, purpose,
            stakeholders and elements are the specification's; the concerns are described in our own words.</p>}
          <p><strong>Concerns:</strong> {vp.concerns}</p>
          <p className="quiet"><strong>Stakeholders:</strong> {vp.stakeholders} · <strong>Purpose:</strong> {vp.purpose}</p>
          <p className="quiet"><strong>Elements:</strong> {vp.element_types.map(spaced).join(", ")}
            {" · "}<strong>Relationships:</strong> {vp.relationship_types.length ? vp.relationship_types.join(", ") : "every type"}</p>
        </div>
        <div className="vp-actions">
          {dash && <a className="button" href={dash.url} target="_blank" rel="noreferrer" title="The same viewpoint as a dashboard in the reporting tool">Open in the reporting tool</a>}
          <button disabled={!curate} title={curate ? "Make your own viewpoint starting from this one" : "Needs the Library Admin role"}
            onClick={() => setEditing({ ...vp, code: "", name: `${vp.name} (copy)` })}>Copy</button>
          {!vp.is_builtin && <button disabled={!curate} onClick={() => setEditing({ ...vp, _code: vp.code })}>Edit</button>}
        </div>
      </div>
      <p className="quiet">{data.entities.length} elements and {data.relationships.length} relationships of {m.name} in this viewpoint
        {data.types.length ? `: ${data.types.map((t) => `${t.count} ${t.name}`).join(", ")}` : "."}</p>
      <div className="seg" role="tablist" aria-label="Show the viewpoint as">
        {SUBS.map(([k, label, help]) => (
          <button key={k} role="tab" aria-selected={s === k} className={s === k ? "on" : ""} title={help}
            onClick={() => go(`/metamodel/${model}/viewpoints/${encodeURIComponent(vp.code)}/${k}`)}>{label}</button>
        ))}
      </div>
      {!data.entities.length ? <p className="quiet">This model has no entities of the viewpoint's types yet.</p>
        : s === "diagram" ? (
          <Suspense fallback={<p>Loading the picture...</p>}>
            <EntityGraph model={model} kind="layers" presetTypeCodes={vp.element_types} onlyRels={vp.relationship_types} />
          </Suspense>)
        : s === "catalog" ? <Catalog data={data} model={model} />
        : s === "heat" ? <HeatMap data={data} model={model} />
        : s === "matrix" ? <Matrix data={data} model={model} />
        : <Relationships data={data} model={model} />}
      {editing && <ViewpointDialog model={model} start={editing} onClose={() => setEditing(null)} />}
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
        <button onClick={() => downloadCsv([["Layer", "Type", "ID", "Name", "Description", "Part of", ...data.attributes],
          ...rows.map((e) => [e.layer, e.entity_type, e.display_id, e.name, e.description, e.parent || "",
            ...data.attributes.map((a) => e.values[a] || "")])], `${data.model.name} ${data.viewpoint.code} catalog`)}
          title="Every element with every attribute, as CSV (opens in Excel)">CSV</button>
      </div>
      <table className="grid-table">
        <thead><tr><th>Layer</th><th>Type</th><th>ID</th><th>Name</th><th>Part of</th>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td><span className="heat-swatch" style={{ background: `#${e.colour}` }} /> {e.layer}</td>
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
        <button onClick={() => heatDrawio(data, attr, scale)} title="The heat map as a draw.io diagram, each box linked to its entity">.drawio</button>
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

// draw.io: the heat map as boxes (parents as containers holding their parts), each linked to its entity
function heatDrawio(data, attr, scale) {
  const nodes = [];
  const TW = 170, TH = 40, GAP = 8, PER_ROW = 6;
  let y = 0;
  const fill = (e) => scale.colour(e.values[attr]) || "f6f7f9";
  const ea = (e) => ({ ea_type: e.entity_type, ea_id: e.id, ea_layer: e.layer });
  for (const t of data.types) {
    nodes.push({ id: `h_${t.code}`, label: `${t.name} (${t.count})`, x: 0, y, w: 400, h: 24, shape: "text", fontSize: 14, bold: true });
    y += 30;
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
        nodes.push({ id: e.id, label: e.name, sub: e.values[attr] || "", ...at, w: TW, h: TH, fill: fill(e), ...ea(e) });
        continue;
      }
      const cols = 2, cw = 130, ch = 34;
      const w = cols * (cw + 6) + 10, h = 34 + Math.ceil(children.length / cols) * (ch + 6) + 6;
      const at = place(w, h);
      nodes.push({ id: e.id, label: `${e.name}${e.values[attr] ? ` (${e.values[attr]})` : ""}`, ...at, w, h, fill: fill(e), container: true, bold: true, ...ea(e) });
      children.forEach((k, i) => nodes.push({ id: k.id, label: k.name, sub: k.values[attr] || "", parent: e.id,
        x: at.x + 5 + (i % cols) * (cw + 6), y: at.y + 30 + Math.floor(i / cols) * (ch + 6), w: cw, h: ch, fill: fill(k), fontSize: 11, ...ea(k) }));
    }
    y += rowH + 24;
  }
  scale.legend.forEach(([v, c], i) => nodes.push({ id: `l_${i}`, label: v, x: i * 130, y, w: 120, h: 24, fill: c, fontSize: 11, align: "center" }));
  downloadDrawio(`${data.model.name} ${data.viewpoint.code} heat map by ${attr}`, nodes, []);
}

// draw.io: the matrix as a table of boxes, the row and column heads linked to their entities
function matrixDrawio(data, rows, cols, cell) {
  const W = 110, H = 28, HW = 220, HH = 110;
  const nodes = [{ id: "corner", label: `${data.viewpoint.code} ${data.viewpoint.name}`, x: 0, y: 0, w: HW, h: HH, fill: "f6f7f9", bold: true }];
  cols.forEach((c, j) => nodes.push({ id: `c_${c.id}`, label: c.name, x: HW + j * W, y: 0, w: W, h: HH, fill: c.colour, align: "center",
    fontSize: 11, ea_type: c.entity_type, ea_id: c.id }));
  rows.forEach((r, i) => {
    nodes.push({ id: `r_${r.id}`, label: r.name, x: 0, y: HH + i * H, w: HW, h: H, fill: r.colour, fontSize: 11, ea_type: r.entity_type, ea_id: r.id });
    cols.forEach((c, j) => {
      const v = cell[`${r.id}|${c.id}`];
      nodes.push({ id: `x_${i}_${j}`, label: v ? v.join(", ") : "", x: HW + j * W, y: HH + i * H, w: W, h: H, fill: v ? "e8f0fb" : "ffffff",
        stroke: "d9dee5", align: "center", fontSize: 9 });
    });
  });
  downloadDrawio(`${data.model.name} ${data.viewpoint.code} matrix`, nodes, []);
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
        <button disabled={!linkedRows.length} onClick={() => matrixDrawio(data, linkedRows, linkedCols, cell)}
          title="The matrix as a draw.io diagram">.drawio</button>
        <button onClick={() => downloadCsv([["", ...linkedCols.map((c) => c.name)],
          ...linkedRows.map((r) => [r.name, ...linkedCols.map((c) => (cell[`${r.id}|${c.id}`] || []).join("; "))])],
        `${data.model.name} ${data.viewpoint.code} matrix`)}>CSV</button>
      </div>
      {!linkedRows.length ? <p className="quiet">No relationships between these two types in this viewpoint.</p> : (
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
            byId[r.target]?.entity_type, byId[r.target]?.name, r.name || ""])], `${data.model.name} ${data.viewpoint.code} relationships`)}>CSV</button>
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

// Add, change, copy or delete one of the organisation's own viewpoints (Library Admins)
function ViewpointDialog({ model, start, onClose }) {
  const [mm, setMm] = useState(null);
  const [v, setV] = useState({
    code: start.code || "", name: start.name || "", category: start.is_builtin ? "Organisation" : start.category || "Organisation",
    purpose: start.purpose || "", concerns: start.concerns || "", stakeholders: start.stakeholders || "",
    element_types: start.element_types || [], relationship_types: start.relationship_types || [],
    heat_attribute: start.heat_attribute || "Lifecycle", audiences: start.audiences || [],
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const editing = !!start._code;
  useEffect(() => { apiFetch(`/api/v1/models/${model}/metamodel`).then(setMm).catch((e) => setError(e.message)); }, [model]);
  const set = (k, val) => setV((x) => ({ ...x, [k]: val }));
  const toggle = (k, code) => set(k, v[k].includes(code) ? v[k].filter((c) => c !== code) : [...v[k], code]);
  const save = async () => {
    setBusy(true); setError(null);
    try {
      const out = await apiFetch(editing ? `/api/v1/viewpoints/${encodeURIComponent(start._code)}` : "/api/v1/viewpoints",
        { method: editing ? "PUT" : "POST", body: JSON.stringify(v) });
      refreshAll();
      onClose();
      go(`/metamodel/${model}/viewpoints/${encodeURIComponent(out.code)}`);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await apiFetch(`/api/v1/viewpoints/${encodeURIComponent(start._code)}`, { method: "DELETE" }); refreshAll(); onClose(); go(`/metamodel/${model}/viewpoints`); }
    catch (e) { setError(e.message); setBusy(false); }
  };
  return (
    <Modal wide title={editing ? `Change ${start._code}` : "New viewpoint"} onClose={onClose} actions={<>
      {editing && <button className="danger" disabled={busy} onClick={remove}>Delete</button>}
      <span className="er-spacer" />
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={busy || !v.code || !v.name || !v.element_types.length} onClick={save}>Save</button>
    </>}>
      <div className="ed-form">
        {error && <p className="status bad">{error}</p>}
        <div className="vp-form-row">
          <label className="ed-field"><span>Code <span className="quiet">for example OVP-01 (VP-numbers are the built-in ones)</span></span>
            <input value={v.code} onChange={(e) => set("code", e.target.value.toUpperCase())} /></label>
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
              {mm.layers.map((l) => (
                <div key={l.id} className="vp-layer"><strong>{l.name}</strong>
                  {l.entity_types.map((t) => (
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
