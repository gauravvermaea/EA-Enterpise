// Model page, Reports > Report designer (phase 24, D365, D433, D434): choose an entity type, its columns, related types
// (through a relationship, either way) with their columns, and filters; see the first rows; save it; Open makes the
// dataset in the reporting tool and opens its chart builder (charts and dashboards are made there). Also the model's
// OData feed address, for Power BI and Excel (Get data > OData feed), signed in with your own user name and password.
import { useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { fmtDate } from "./fmt";

const EMPTY = { entity_type: "", columns: ["display_id", "name"], related: [], filters: [] };

export function ODataPanel({ url }) {
  const [copied, setCopied] = useState(false);
  const copy = () => { navigator.clipboard?.writeText(url).then(() => setCopied(true)).catch(() => setCopied(false)); };
  return (
    <div className="odata-panel">
      <h3>OData feed</h3>
      <p className="quiet">For Power BI, Excel and other OData tools: <em>Get data</em> &gt; <em>OData feed</em>, paste this address and sign
        in with <strong>Basic</strong>: your EA Explorer user name and password. You get one table per entity type (plus Entities and
        Relationships), read only, with what you may read. Committed content only.</p>
      <div className="toolbar"><code className="odata-url">{url}</code>
        <button onClick={copy}>{copied ? "Copied" : "Copy the address"}</button></div>
    </div>
  );
}

// the model's OData feed as its own tab (owner, 10 Nov 2026, D542): Reports > Power BI and Excel
export function ODataTab({ model }) {
  const { data, error } = useApi(`/api/v1/models/${model}/report-designer`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading the feed's address...</p>;
  return <ODataPanel url={data.odata_url} />;
}

export default function ReportDesigner({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/report-designer`);
  const [spec, setSpec] = useState(EMPTY);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(null);
  const [preview, setPreview] = useState(null);
  const [msg, setMsg] = useState("");
  const types = useMemo(() => Object.fromEntries((data?.types || []).map((t) => [t.code, t])), [data]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading the report designer...</p>;
  const type = types[spec.entity_type];
  const change = (patch) => { setSpec((s) => ({ ...s, ...patch })); setPreview(null); };
  const toggle = (list, c) => (list.includes(c) ? list.filter((x) => x !== c) : [...list, c]);
  const fieldsOf = (code) => (types[code]?.fields || []);
  const allFields = [
    ...fieldsOf(spec.entity_type).map((f) => ({ value: f.column, label: `${type?.name}: ${f.name}` })),
    ...spec.related.flatMap((r, i) => fieldsOf(r.other_type).map((f) => ({ value: `related:${i + 1}:${f.column}`, label: `${types[r.other_type]?.name}: ${f.name}` }))),
  ];
  const run = async () => {
    setMsg("");
    try { setPreview(await apiFetch(`/api/v1/models/${model}/report-designs/preview`, { method: "POST", body: JSON.stringify({ spec }) })); }
    catch (e) { setMsg(e.message); setPreview(null); }
  };
  const save = async (open) => {
    setMsg("");
    try {
      const body = JSON.stringify({ name, spec });
      const d = editing
        ? await apiFetch(`/api/v1/models/${model}/report-designs/${editing}`, { method: "PUT", body })
        : await apiFetch(`/api/v1/models/${model}/report-designs`, { method: "POST", body });
      setEditing(d.id);
      refreshAll();
      if (open) window.open(d.open_url, "_blank", "noopener");
      else setMsg(`Saved ${d.name}.`);
    } catch (e) { setMsg(e.message); }
  };
  const load = (d) => { setEditing(d.id); setName(d.name); setSpec({ ...EMPTY, ...d.spec }); setPreview(null); setMsg(""); };
  const remove = async (d) => {
    try { await apiFetch(`/api/v1/models/${model}/report-designs/${d.id}/delete`, { method: "POST" }); refreshAll(); if (editing === d.id) { setEditing(null); setSpec(EMPTY); setName(""); } }
    catch (e) { setMsg(e.message); }
  };
  return (
    <div className="designer">
      <p><a href={`#/metamodel/${model}/reports`}>← Reports</a></p>
      <h2>Report designer</h2>
      <p className="quiet">Build the data for a report on <strong>{m.name}</strong>: a type, the columns you want, related types and filters.
        <em> Save and open</em> makes it a dataset in the reporting tool and opens its chart builder, where you make the chart (and add
        it to a dashboard). Everyone sees only the models they may read.</p>

      {data.designs.length > 0 && (
        <table className="grid-table">
          <thead><tr><th>Saved designs</th><th>About</th><th>By</th><th>Changed</th><th /></tr></thead>
          <tbody>{data.designs.map((d) => (
            <tr key={d.id} className={editing === d.id ? "on" : ""}>
              <td><button className="linkish" onClick={() => load(d)}>{d.name}</button></td>
              <td>{types[d.spec.entity_type]?.name || d.spec.entity_type}{d.spec.related.length ? ` with ${d.spec.related.map((r) => types[r.other_type]?.name || r.other_type).join(", ")}` : ""}
                {d.spec.filters.length ? ` · ${d.spec.filters.length} filter${d.spec.filters.length === 1 ? "" : "s"}` : ""}</td>
              <td>{d.created_by}</td><td>{fmtDate(d.modified_at)}</td>
              <td><a className="button" href={d.open_url} target="_blank" rel="noreferrer" title="Make or refresh its dataset and open the chart builder">Open</a>
                <button className="linkish" onClick={() => remove(d)}>Delete</button></td>
            </tr>))}</tbody>
        </table>
      )}

      <section className="designer-steps">
        <h3>{editing ? "Change the design" : "A new design"} {editing && <button className="linkish" onClick={() => { setEditing(null); setSpec(EMPTY); setName(""); setPreview(null); }}>start a new one</button>}</h3>
        <label className="designer-row">1. About <select value={spec.entity_type} onChange={(e) => change({ ...EMPTY, entity_type: e.target.value })}>
          <option value="">Choose the entity type...</option>
          {data.types.map((t) => <option key={t.code} value={t.code} disabled={!t.has_view}>{t.domain}: {t.name}{t.has_view ? "" : " (no report view yet)"}</option>)}
        </select></label>
        {type && (
          <>
            <div className="designer-row"><span>2. Columns</span>
              <div className="chips">{type.fields.map((f) => (
                <label key={f.column} className={spec.columns.includes(f.column) ? "chip on" : "chip"}>
                  <input type="checkbox" checked={spec.columns.includes(f.column)} onChange={() => change({ columns: toggle(spec.columns, f.column) })} /> {f.name}
                </label>))}</div>
            </div>
            <div className="designer-row"><span>3. Related</span>
              <div>
                {spec.related.map((r, i) => (
                  <div key={i} className="designer-related">
                    <strong>{type.related.find((x) => x.relationship_type === r.relationship_type && x.direction === r.direction && x.other_type === r.other_type)?.label}</strong>
                    <div className="chips">{fieldsOf(r.other_type).map((f) => (
                      <label key={f.column} className={r.columns.includes(f.column) ? "chip on" : "chip"}>
                        <input type="checkbox" checked={r.columns.includes(f.column)}
                          onChange={() => change({ related: spec.related.map((x, k) => (k === i ? { ...x, columns: toggle(x.columns, f.column) } : x)) })} /> {f.name}
                      </label>))}</div>
                    <button className="linkish" onClick={() => change({ related: spec.related.filter((_x, k) => k !== i), filters: spec.filters.filter((f) => !f.field.startsWith("related:")) })}>remove</button>
                  </div>
                ))}
                {spec.related.length < 4 && (
                  <select value="" onChange={(e) => { const r = type.related[Number(e.target.value)]; if (r) change({ related: [...spec.related, { relationship_type: r.relationship_type, direction: r.direction, other_type: r.other_type, columns: ["name"] }] }); }}>
                    <option value="">+ Add a related type...</option>
                    {type.related.map((r, i) => <option key={i} value={i} disabled={!types[r.other_type]?.has_view}>{r.label}</option>)}
                  </select>
                )}
              </div>
            </div>
            <div className="designer-row"><span>4. Filters</span>
              <div>
                {spec.filters.map((f, i) => (
                  <div key={i} className="toolbar">
                    <select value={f.field} onChange={(e) => change({ filters: spec.filters.map((x, k) => (k === i ? { ...x, field: e.target.value } : x)) })}>
                      {allFields.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
                    <select value={f.op} onChange={(e) => change({ filters: spec.filters.map((x, k) => (k === i ? { ...x, op: e.target.value } : x)) })}>
                      {Object.entries(data.ops).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
                    {!["empty", "not-empty"].includes(f.op) && <input value={f.value} placeholder="value"
                      onChange={(e) => change({ filters: spec.filters.map((x, k) => (k === i ? { ...x, value: e.target.value } : x)) })} />}
                    <button className="linkish" onClick={() => change({ filters: spec.filters.filter((_x, k) => k !== i) })}>remove</button>
                  </div>
                ))}
                <button className="linkish" onClick={() => change({ filters: [...spec.filters, { field: allFields[0]?.value || "name", op: "equals", value: "" }] })}>+ Add a filter</button>
              </div>
            </div>
            <div className="toolbar">
              <button onClick={run}>Show the first rows</button>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name it, e.g. Costly applications and their capabilities" className="designer-name" />
              <button onClick={() => save(false)}>Save</button>
              <button className="primary" onClick={() => save(true)} title="Save, make its dataset in the reporting tool and open the chart builder">Save and open</button>
            </div>
          </>
        )}
        {msg && <p className={msg.startsWith("Saved") ? "status ok" : "status bad"}>{msg}</p>}
        {preview && (
          <div className="designer-preview">
            <p className="quiet">{preview.count} row{preview.count === 1 ? "" : "s"} now (the first {preview.rows.length} shown); a type related several times gives a row per related entity.</p>
            <div className="table-scroll"><table className="grid-table">
              <thead><tr>{preview.columns.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
              <tbody>{preview.rows.map((r, i) => <tr key={i}>{r.map((v, k) => <td key={k}>{v ?? ""}</td>)}</tr>)}</tbody>
            </table></div>
            <details><summary className="quiet">The query (over the report views)</summary><pre className="designer-sql">{preview.sql}</pre></details>
          </div>
        )}
      </section>
      <ODataPanel url={data.odata_url} />
    </div>
  );
}
