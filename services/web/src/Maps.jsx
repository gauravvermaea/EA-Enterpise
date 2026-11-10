// Business maps (build phase 8.2, D161), in the Graph tab:
//   Value stream map   each value stream as a chevron of stages, with the capabilities that enable each stage
//                      under it, coloured by an attribute (maturity, criticality...); or as a value stream x
//                      capability matrix with the same colours (the heat map of the business architecture)
//   Roadmap            plateaus, work packages and deliverables on a timeline from their start and end dates,
//                      coloured by type or by an attribute, with today marked
// Click a capability or a bar to open its entity page. Both save as CSV.
import { useMemo, useState } from "react";
import { downloadCsv } from "./exporting";
import { PictureActions } from "./DrawnView";
import { useApi } from "./ModelViews";
import { Legend, heatScale } from "./Views";

export function ValueStreamMap({ model }) {
  const { data, error } = useApi(`/api/v1/models/${model}/maps/value-streams`);
  const [only, setOnly] = useState("");
  const [attr, setAttr] = useState(null);
  const [as, setAs] = useState("map");
  const streams = useMemo(() => (data ? data.value_streams.filter((v) => !only || v.id === only) : []), [data, only]);
  const caps = useMemo(() => streams.flatMap((v) => v.stages.flatMap((s) => s.capabilities)), [streams]);
  const chosen = attr ?? (data ? (data.attributes.find((a) => a === "Maturity") || data.attributes[0] || "") : "");
  const scale = useMemo(() => heatScale(caps, chosen, (c) => c.values[chosen]), [caps, chosen]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading the value streams...</p>;
  if (!data.value_streams.length) return <p className="quiet">This model has no value streams yet.</p>;
  const capRows = [...new Map(caps.map((c) => [c.id, c])).values()].sort((a, b) => a.name.localeCompare(b.name));
  const stageCols = streams.flatMap((v) => v.stages.map((s) => ({ ...s, stream: v.name })));
  const has = (cap, stage) => stage.capabilities.some((c) => c.id === cap.id);
  const csv = () => downloadCsv([["Value stream", "Stage", "Capability", chosen],
    ...streams.flatMap((v) => v.stages.flatMap((s) => (s.capabilities.length ? s.capabilities : [{}]).map((c) =>
      [v.name, s.name, c.name || "", c.values?.[chosen] || ""])))], "Value stream map");
  return (
    <div className="vs-map">
      <div className="toolbar">
        <div className="seg small" role="tablist">
          <button className={as === "map" ? "on" : ""} onClick={() => setAs("map")}>Map</button>
          <button className={as === "matrix" ? "on" : ""} onClick={() => setAs("matrix")}>Value stream x capability</button>
        </div>
        <label>Value stream <select value={only} onChange={(e) => setOnly(e.target.value)}>
          <option value="">All ({data.value_streams.length})</option>
          {data.value_streams.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>
        <label>Colour by <select value={chosen} onChange={(e) => setAttr(e.target.value)}>
          {data.attributes.map((a) => <option key={a} value={a}>{a}</option>)}</select></label>
        <button onClick={csv}>CSV</button>
        <PictureActions model={model} picture={() => vsPicture(streams, chosen, scale)} />
      </div>
      <Legend legend={scale.legend} attribute={chosen} />
      {as === "map" ? streams.map((v) => (
        <section key={v.id} className="vs-stream">
          <h3><a href={`#/metamodel/${model}/entity/${v.id}`}>{v.name}</a></h3>
          <div className="vs-stages" style={{ gridTemplateColumns: `repeat(${v.stages.length}, minmax(150px, 1fr))` }}>
            {v.stages.map((s, i) => (
              <div key={s.id} className="vs-stage">
                <a className={i === 0 ? "vs-chevron first" : "vs-chevron"} href={`#/metamodel/${model}/entity/${s.id}`}>{s.name}</a>
                <div className="vs-caps">
                  {s.capabilities.map((c) => {
                    const col = scale.colour(c.values[chosen]);
                    return (
                      <a key={c.id} className={col ? "heat-tile" : "heat-tile none"} style={col ? { background: `#${col}` } : undefined}
                        href={`#/metamodel/${model}/entity/${c.id}`} title={`${c.name}\n${chosen}: ${c.values[chosen] ?? "not set"}`}>
                        <span>{c.name}</span><span className="heat-value">{c.values[chosen] ?? ""}</span>
                      </a>
                    );
                  })}
                  {!s.capabilities.length && <span className="quiet">No capabilities linked</span>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )) : (
        <div className="vp-matrix-wrap">
          <table className="grid-table vp-matrix">
            <thead>
              <tr><th />{streams.map((v) => <th key={v.id} colSpan={v.stages.length} className="vs-head">{v.name}</th>)}</tr>
              <tr><th>Capability</th>{stageCols.map((s) => <th key={s.id} className="rot">{s.name}</th>)}</tr>
            </thead>
            <tbody>
              {capRows.map((c) => {
                const col = scale.colour(c.values[chosen]);
                return (
                  <tr key={c.id}>
                    <th><a href={`#/metamodel/${model}/entity/${c.id}`}>{c.name}</a></th>
                    {stageCols.map((s) => (
                      <td key={s.id} className={has(c, s) ? "hit" : ""} style={has(c, s) && col ? { background: `#${col}` } : undefined}
                        title={has(c, s) ? `${c.name} enables ${s.stream}: ${s.name} (${chosen}: ${c.values[chosen] ?? "not set"})` : ""}>
                        {has(c, s) ? (c.values[chosen] ?? "•") : ""}</td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// the value stream map as a picture (D407, D408): each value stream a row of its stages (in the value stream notation),
// the enabling capabilities stacked under each stage, coloured by the chosen attribute
function vsPicture(streams, attr, scale) {
  const nodes = [];
  const SW = 180, SH = 50, CH = 50, GAP = 10, CGAP = 10;
  let y = 0;
  for (const v of streams) {
    nodes.push({ id: `v_${v.id}`, label: v.name, x: 0, y, w: 600, h: 26, shape: "text", fontSize: 15, bold: true });
    y += 32;
    let tallest = 0;
    v.stages.forEach((s, i) => {
      const x = i * (SW + GAP);
      nodes.push({ id: `s_${v.id}_${s.id}`, label: s.name, x, y, w: SW, h: SH, fill: "efbd5d", stroke: "b8862a", bold: true, align: "center",
        ea_type: "ValueStream", ea_id: s.id });
      s.capabilities.forEach((c, k) => {
        const col = scale.colour(c.values[attr]);
        nodes.push({ id: `c_${s.id}_${c.id}`, label: c.name, sub: c.values[attr] || "", x, y: y + SH + 2 * GAP + k * (CH + CGAP),
          w: SW, h: CH, fill: col || "f6f7f9", heatFill: col, fontSize: 11, ea_type: "Capability", ea_id: c.id });
      });
      tallest = Math.max(tallest, s.capabilities.length);
    });
    y += SH + 2 * GAP + tallest * (CH + CGAP) + 30;
  }
  scale.legend.forEach(([val, c], i) => nodes.push({ id: `l_${i}`, label: `${attr}: ${val}`, x: i * 160, y, w: 150, h: 30, fill: c, fontSize: 11, align: "center" }));
  // a capability enabling two stages is one entity: on a drawn view it is drawn once per stage (a second box of it)
  return { title: `Value stream map by ${attr}`, nodes, edges: [] };
}

const TYPE_COLOUR = { Plateau: "#8e7cc3", WorkPackage: "#2f7d9b", Deliverable: "#e69138" };
const DAY = 86400000;

// the roadmap as a picture (D407, D408): year marks and lines, then one bar per item placed by its dates (in its type's
// notation, coloured as the screen colours it)
function roadmapPicture(items, lo, hi, years, colour, by) {
  const LW = 240, TW = 1100, RH = 40;
  const xOf = (ms) => LW + ((ms - lo) / (hi - lo)) * TW;
  const t = (d) => new Date(`${d}T00:00:00Z`).getTime();
  const bottom = 40 + items.length * RH;
  const nodes = years.flatMap((y) => [
    { id: `y_${y}`, label: String(y), x: xOf(Date.UTC(y, 0, 1)) + 4, y: 0, w: 60, h: 24, shape: "text", fontSize: 12, keepSize: true },
    { id: `yl_${y}`, label: "", x: xOf(Date.UTC(y, 0, 1)), y: 24, w: 1, h: bottom - 24, fill: "d9dee5", stroke: "d9dee5", keepSize: true },
  ]);
  items.forEach((i, k) => {
    const y = 40 + k * RH;
    nodes.push({ id: `l_${i.id}`, label: i.name, x: 0, y, w: LW - 20, h: RH - 10, shape: "text", fontSize: 11, keepSize: true });
    nodes.push({ id: i.id, label: i.name, x: xOf(t(i.start_date)), y, w: Math.max(30, xOf(t(i.end_date) + DAY) - xOf(t(i.start_date))), h: RH - 10,
      fill: colour(i).replace("#", ""), heatFill: by === "type" ? null : colour(i).replace("#", ""), fontSize: 10, ea_type: i.type_code || i.entity_type, ea_id: i.id,
      keepSize: true });
  });
  return { title: "Roadmap", nodes, edges: [] };
}

export function Roadmap({ model }) {
  const { data, error } = useApi(`/api/v1/models/${model}/maps/roadmap`);
  const [colourBy, setColourBy] = useState("type");
  const items = useMemo(() => (data ? data.items.filter((i) => i.start_date && i.end_date) : []), [data]);
  const scale = useMemo(() => heatScale(items, colourBy === "priority" ? "Priority" : "Architecture State",
    (i) => (colourBy === "priority" ? i.priority : i.architecture_state)), [items, colourBy]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading the roadmap...</p>;
  if (!data.items.length) return <p className="quiet">This model has no work packages, deliverables or plateaus yet.</p>;
  const undated = data.items.filter((i) => !i.start_date || !i.end_date);
  if (!items.length) return <p className="quiet">None of the {data.items.length} work packages, deliverables or plateaus has a start and an end date yet.</p>;
  const t = (d) => new Date(`${d}T00:00:00Z`).getTime();
  const lo = new Date(Date.UTC(new Date(Math.min(...items.map((i) => t(i.start_date)))).getUTCFullYear(), 0, 1)).getTime();
  const hi = new Date(Date.UTC(new Date(Math.max(...items.map((i) => t(i.end_date)))).getUTCFullYear() + 1, 0, 1)).getTime();
  const pct = (ms) => `${(100 * (ms - lo)) / (hi - lo)}%`;
  const years = [];
  for (let y = new Date(lo).getUTCFullYear(); y < new Date(hi).getUTCFullYear(); y += 1) years.push(y);
  const now = Date.now();
  const groups = [["Plateau", "Plateaus"], ["WorkPackage", "Work packages"], ["Deliverable", "Deliverables"]];
  const colour = (i) => (colourBy === "type" ? TYPE_COLOUR[i.type_code]
    : (() => { const c = scale.colour(colourBy === "priority" ? i.priority : i.architecture_state); return c ? `#${c}` : "#b8c2cc"; })());
  return (
    <div className="roadmap">
      <div className="toolbar">
        <label>Colour by <select value={colourBy} onChange={(e) => setColourBy(e.target.value)}>
          <option value="type">Type</option><option value="priority">Priority</option><option value="state">Architecture state</option>
        </select></label>
        {colourBy === "type" ? Object.entries(TYPE_COLOUR).map(([k, c]) => <span key={k} className="legend-chip"><span className="heat-swatch" style={{ background: c }} />{k.replace("WorkPackage", "Work package")}</span>)
          : <Legend legend={scale.legend} attribute={colourBy === "priority" ? "Priority" : "Architecture state"} />}
        <PictureActions model={model} picture={() => roadmapPicture(items, lo, hi, years, colour, colourBy)} />
        <button onClick={() => downloadCsv([["Type", "ID", "Name", "Start", "End", "Owner", "Priority", "Architecture state", "Delivers"],
          ...data.items.map((i) => [i.entity_type, i.display_id, i.name, i.start_date || "", i.end_date || "", i.owner || "", i.priority || "",
            i.architecture_state || "", i.delivers.map((d) => d.name).join("; ")])], "Roadmap")}>CSV</button>
      </div>
      <div className="rm-grid">
        <div className="rm-row rm-axis"><div className="rm-label" />
          <div className="rm-track">{years.map((y) => <span key={y} className="rm-year" style={{ left: pct(Date.UTC(y, 0, 1)) }}>{y}</span>)}
            {now > lo && now < hi && <span className="rm-today" style={{ left: pct(now) }} title="Today" />}</div></div>
        {groups.map(([code, label]) => {
          const list = items.filter((i) => i.type_code === code);
          if (!list.length) return null;
          return [
            <div key={code} className="rm-group">{label}</div>,
            ...list.map((i) => (
              <div key={i.id} className="rm-row">
                <div className="rm-label"><a href={`#/metamodel/${model}/entity/${i.id}`}>{i.name}</a></div>
                <div className="rm-track">
                  {years.map((y) => <span key={y} className="rm-gridline" style={{ left: pct(Date.UTC(y, 0, 1)) }} />)}
                  {now > lo && now < hi && <span className="rm-today" style={{ left: pct(now) }} />}
                  <a className="rm-bar" href={`#/metamodel/${model}/entity/${i.id}`}
                    style={{ left: pct(t(i.start_date)), width: `calc(${pct(t(i.end_date) + DAY)} - ${pct(t(i.start_date))})`, background: colour(i) }}
                    title={`${i.name}\n${i.start_date} to ${i.end_date}${i.owner ? `\nOwner: ${i.owner}` : ""}${i.delivers.length ? `\nDelivers: ${i.delivers.map((d) => d.name).join(", ")}` : ""}`}>
                    {i.name}</a>
                </div>
              </div>
            )),
          ];
        })}
      </div>
      {undated.length > 0 && <p className="quiet">Not on the roadmap (no start or end date): {undated.map((i) => i.name).join(", ")}.</p>}
    </div>
  );
}
