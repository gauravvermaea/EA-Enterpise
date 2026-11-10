// Relationship matrix: the entities of one type down the side, of another across the top, and in
// each cell the relationships between the two (either way). For example processes against roles, or
// capabilities against business services. Click a name to open its entity page.
// Saves as CSV (the grid) and opens in draw.io (a table of boxes, D256).
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { downloadCsv } from "./exporting";
import { PictureActions } from "./DrawnView";
import { relColour } from "./MetamodelDiagram";
import { elementTypes } from "./elements.js";

const initial = (r) => r.relationship_type_code === "Parent" ? "P" : (r.relationship_type || "?").slice(0, 2);

export default function RelationMatrix({ model }) {
  const [types, setTypes] = useState(null);
  const [rowType, setRowType] = useState("");
  const [colType, setColType] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [onlyLinked, setOnlyLinked] = useState(true);

  useEffect(() => {
    let live = true;
    apiFetch(`/api/v1/models/${model}/metamodel`).then((mm) => {
      if (!live) return;
      const list = mm.domains.flatMap((l) => elementTypes(l).map((t) => ({ ...t, colour: l.colour })))
        .filter((t) => t.entity_count > 0);
      setTypes(list);
      const by = (code) => list.find((t) => t.code === code);
      const r = by("Process") || list[0], c = by("Role") || list.find((t) => t.id !== r?.id) || r;
      setRowType(r?.id || ""); setColType(c?.id || "");
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model]);

  useEffect(() => {
    if (!rowType || !colType) return undefined;
    let live = true;
    setData(null);
    const q = new URLSearchParams({ limit: "2000" });
    [...new Set([rowType, colType])].forEach((t) => q.append("type", t));
    apiFetch(`/api/v1/models/${model}/graph?${q}`).then((d) => live && setData(d)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model, rowType, colType]);

  const grid = useMemo(() => {
    if (!data) return null;
    let rows = data.nodes.filter((n) => n.entity_type_id === rowType);
    let cols = data.nodes.filter((n) => n.entity_type_id === colType);
    const rowIds = new Set(rows.map((n) => n.id)), colIds = new Set(cols.map((n) => n.id));
    const cells = {};
    for (const e of data.edges) {
      // either way round: row -> column (→) or column -> row (←)
      if (rowIds.has(e.source) && colIds.has(e.target)) (cells[`${e.source}|${e.target}`] ||= []).push({ ...e, way: "→" });
      if (rowIds.has(e.target) && colIds.has(e.source) && e.source !== e.target) (cells[`${e.target}|${e.source}`] ||= []).push({ ...e, way: "←" });
    }
    if (onlyLinked) {
      const usedR = new Set(Object.keys(cells).map((k) => k.split("|")[0]));
      const usedC = new Set(Object.keys(cells).map((k) => k.split("|")[1]));
      rows = rows.filter((n) => usedR.has(n.id)); cols = cols.filter((n) => usedC.has(n.id));
    }
    return { rows, cols, cells, links: Object.values(cells).reduce((s, l) => s + l.length, 0) };
  }, [data, rowType, colType, onlyLinked]);

  if (error) return <p className="status bad">{error}</p>;
  if (!types) return <p className="quiet">Loading...</p>;
  const rt = types.find((t) => t.id === rowType), ct = types.find((t) => t.id === colType);
  const title = `${rt?.name || ""} x ${ct?.name || ""} matrix`;
  const cellText = (list) => (list || []).map((r) => `${r.way} ${r.verb}`).join("; ");

  function exportCsv() {
    downloadCsv([[`${rt.name} \\ ${ct.name}`, ...grid.cols.map((c) => `${c.name} (${c.display_id})`)],
      ...grid.rows.map((r) => [`${r.name} (${r.display_id})`, ...grid.cols.map((c) => cellText(grid.cells[`${r.id}|${c.id}`]))])], title);
  }
  // the matrix as a table of boxes (D407, D408): the row and column heads are the entities (in their notation), the
  // cells say the relationships
  function picture() {
    if (!grid) return null;
    const W = 120, H = 30, HW = 220, HH = 90;
    const cells = [{ id: "corner", label: `${rt.name} \\ ${ct.name}`, x: 0, y: 0, w: HW, h: HH, fill: "f6f7f9", bold: true }];
    grid.cols.forEach((c, j) => cells.push({ id: `c_${c.id}`, label: c.name, x: HW + j * W, y: 0, w: W, h: HH, fill: c.colour,
      align: "center", fontSize: 11, ea_type: c.entity_type, ea_id: c.id, keepSize: true }));
    grid.rows.forEach((r, i) => {
      cells.push({ id: `r_${r.id}`, label: r.name, x: 0, y: HH + i * H, w: HW, h: H, fill: r.colour, fontSize: 11, ea_type: r.entity_type, ea_id: r.id, keepSize: true });
      grid.cols.forEach((c, j) => {
        const list = grid.cells[`${r.id}|${c.id}`];
        cells.push({ id: `x_${i}_${j}`, label: list ? list.map((x) => `${x.way} ${initial(x)}`).join(" ") : "", x: HW + j * W, y: HH + i * H,
          w: W, h: H, fill: list ? "e8f0fb" : "ffffff", stroke: "d9dee5", align: "center", fontSize: 10, keepSize: true });
      });
    });
    return { title, nodes: cells, edges: [] };
  }

  return (
    <div>
      <div className="toolbar">
        <label>Rows
          <select value={rowType} onChange={(e) => setRowType(e.target.value)}>
            {types.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.entity_count})</option>)}
          </select>
        </label>
        <button title="Swap rows and columns" onClick={() => { setRowType(colType); setColType(rowType); }}>⇄</button>
        <label>Columns
          <select value={colType} onChange={(e) => setColType(e.target.value)}>
            {types.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.entity_count})</option>)}
          </select>
        </label>
        <label><input type="checkbox" checked={onlyLinked} onChange={(e) => setOnlyLinked(e.target.checked)} /> Only rows and columns with relationships</label>
        <span className="er-spacer" />
        <PictureActions model={model} picture={picture} disabled={!grid} />
        <button onClick={exportCsv} disabled={!grid}>CSV</button>
      </div>
      {!grid ? <p className="quiet">Loading...</p> : (
        <>
          <p className="quiet er-info">
            {grid.rows.length} rows, {grid.cols.length} columns, {grid.links} relationships
            {data.truncated && " · only the first 2,000 entities"}. A cell shows each relationship and its direction:
            → the row entity is the source, ← the column entity is.
          </p>
          {grid.rows.length && grid.cols.length ? (
            <div className="matrix-frame">
              <table className="matrix">
                <thead>
                  <tr>
                    <th className="corner">{rt?.name} \ {ct?.name}</th>
                    {grid.cols.map((c) => (
                      <th key={c.id} className="col-head" title={`${c.name} (${c.display_id})`}>
                        <a href={`#/metamodel/${model}/entity/${c.id}`}><span>{c.name}</span></a>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grid.rows.map((r) => (
                    <tr key={r.id}>
                      <th className="row-head"><a href={`#/metamodel/${model}/entity/${r.id}`}>{r.name}</a> <span className="quiet">{r.display_id}</span></th>
                      {grid.cols.map((c) => {
                        const list = grid.cells[`${r.id}|${c.id}`];
                        return (
                          <td key={c.id} className={list ? "hit" : ""} title={list ? `${r.name}: ${cellText(list)} ${c.name}` : ""}>
                            {list?.map((x, i) => (
                              <span key={i} className="mx" style={{ color: relColour(x.relationship_type_code), borderColor: relColour(x.relationship_type_code) }}>
                                {x.way}{initial(x)}
                              </span>
                            ))}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="quiet">No relationships between these two types in this model.</p>}
        </>
      )}
    </div>
  );
}
