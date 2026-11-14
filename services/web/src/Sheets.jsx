// The Import and export tab (build phase 10.1, D197) of every model that holds content:
//   #/metamodel/<model>/import                  choose entity types, build and download; upload a sheet (one screen)
//   #/metamodel/<model>/import/load/<id>        a load: preview (new, changed, unchanged, delete, problems), map columns,
//                                               correct rows, add them to your uncommitted changes, undo
//   #/metamodel/<model>/import/loads            every load of the model you may see
//   #/metamodel/<model>/import/deliveries       other systems' deliveries in the published formats (phase 34, Deliveries.jsx)
//   #/metamodel/<model>/import/discovery        OData feeds read, pushes taken, documents read by AI (R3 epic, Discovery.jsx)
//   (collection sets, feeds and scheduled exports: a phase of their own, D198)
import { useEffect, useMemo, useState } from "react";
import { apiDownload, apiFetch, apiUpload, canOn } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";
import { trackTask, useTask } from "./tasks";
import DeliveriesTab, { DeliveryActions } from "./Deliveries";
import DiscoveryTab from "./Discovery";

const go = (path) => { window.location.hash = path; };
const post = (path, body, method = "POST") => apiFetch(path, { method, body: JSON.stringify(body || {}) });
const ACTIONS = { new: "New", changed: "Changed", unchanged: "Unchanged", delete: "To delete", problem: "Problems" };
const FORMATS = [["xlsx", "Excel (.xlsx)", "Drop-downs and provisional IDs for new rows; no macros."],
  ["xlsm", "Excel with macro (.xlsm)", "The same, and a macro writes a GUID into each new row (allow macros when Excel asks)."],
  ["zip", "CSV set (.zip)", "One CSV per type and one of relationships, for feeds and other tools."]];

export default function SheetsTab({ model, m, sub, itemId }) {
  const may = canOn(model, "model.content");
  const nav = [["", "Download and upload"], ["loads", "Loads"], ["deliveries", "Deliveries"], ["discovery", "Discovery"]];
  const cur = sub === "load" ? "loads" : sub || "";
  return (
    <div className="sheets">
      <div className="seg small" role="tablist">
        {nav.map(([k, l]) => <button key={k} className={cur === k ? "on" : ""} onClick={() => go(`/metamodel/${model}/import${k ? `/${k}` : ""}`)}>{l}</button>)}
      </div>
      {sub === "load" && itemId ? <LoadPage key={itemId} model={model} m={m} id={itemId} />
        : sub === "loads" ? <><LoadList model={model} /><SavedMappings model={model} /></>
          : sub === "deliveries" ? <DeliveriesTab model={model} m={m} />
          : sub === "discovery" ? <DiscoveryTab model={model} />
          : <><Download model={model} m={m} /><Upload model={model} m={m} may={may} /></>}
    </div>
  );
}

// ---------------------------------------------------------------- download: choose the types, built now
function TypePicker({ model, value, onChange }) {
  const { data, error } = useApi(`/api/v1/models/${model}/sheets`);
  const [q, setQ] = useState("");
  if (error) return <p className="error">Could not load the entity types: {error}</p>;
  if (!data) return <p className="quiet">Loading the entity types...</p>;
  const domains = [...new Set(data.types.map((t) => t.domain))];
  const shown = data.types.filter((t) => !q || `${t.name} ${t.code}`.toLowerCase().includes(q.toLowerCase()));
  const toggle = (codes, on) => onChange(on ? [...new Set([...value, ...codes])] : value.filter((c) => !codes.includes(c)));
  return (
    <div className="type-picker">
      <div className="toolbar">
        <input className="search" placeholder="Filter types" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 220 }} />
        <button className="linkish" onClick={() => onChange(data.types.filter((t) => t.entities).map((t) => t.code))}>Every type with entities</button>
        <button className="linkish" onClick={() => onChange([])}>None</button>
        <span className="quiet small">{value.length} chosen</span>
      </div>
      <div className="type-domains">
        {domains.map((l) => {
          const ts = shown.filter((t) => t.domain === l);
          if (!ts.length) return null;
          const all = ts.every((t) => value.includes(t.code));
          return (
            <fieldset key={l} className="form-section">
              <legend><label><input type="checkbox" checked={all} onChange={(e) => toggle(ts.map((t) => t.code), e.target.checked)} /> {l}</label></legend>
              {ts.map((t) => (
                <label key={t.code} className="type-choice" title={`${t.attributes} attributes`}>
                  <input type="checkbox" checked={value.includes(t.code)} onChange={(e) => toggle([t.code], e.target.checked)} />
                  {" "}{t.name} <span className="quiet small">{t.entities}</span>
                </label>
              ))}
            </fieldset>
          );
        })}
      </div>
    </div>
  );
}

export function Download({ model, m }) {
  // a request to fill in data (WIZ-018) links here with the types chosen: ?types=A,B
  const [types, setTypes] = useState(() => (window.location.hash.match(/[?&]types=([^&]+)/) || [])[1]?.split(",").map(decodeURIComponent) || []);
  const [fmt, setFmt] = useState("xlsx");
  const [blank, setBlank] = useState(false);     // the published format's empty template (phase 34)
  const [taskId, setTaskId] = useState(null);
  const [fetched, setFetched] = useState(null);
  const [err, setErr] = useState("");
  const task = useTask(taskId);
  useEffect(() => {   // built: download it at once
    if (task?.done && task.status === "done" && fetched !== task.id) {
      setFetched(task.id);
      apiDownload(`/api/v1/tasks/${task.id}/file`, task.result?.file || "sheets").catch((e) => setErr(e.message));
    }
  }, [task?.done]);
  async function build() {
    setErr("");
    try {
      const out = await post(`/api/v1/models/${model}/sheets`, { types, format: fmt, blank });
      trackTask(out.task, `#/metamodel/${model}/import`);
      setTaskId(out.task.id);
    } catch (e) { setErr(e.message); }
  }
  return (
    <div className="merge-step">
      <h3>Download sheets</h3>
      <p className="quiet">Choose the entity types: the workbook is built now from the metamodel, with one sheet per type holding
        every entity and its values, and a Relationships sheet with the relationships between them. Change values, add rows,
        mark rows to delete, and load it back below. A new row needs no ID: it gets one as soon as it has a name.</p>
      <TypePicker model={model} value={types} onChange={setTypes} />
      <div className="toolbar">
        {FORMATS.map(([k, l, help]) => (
          <label key={k} title={help}><input type="radio" name="fmt" checked={fmt === k} onChange={() => setFmt(k)} /> {l}</label>
        ))}
        <label title="The same columns and drop-downs with no rows: the published format for another system to fill (docs/import-formats.md)">
          <input type="checkbox" checked={blank} onChange={(e) => setBlank(e.target.checked)} /> Empty template</label>
        <button className="primary" disabled={!types.length || (task && !task.done)} onClick={build}>
          {task && !task.done ? "Building..." : `⬇ Build and download (${types.length} type${types.length === 1 ? "" : "s"})`}</button>
      </div>
      {task?.done && <p className={`status ${task.status === "done" ? "ok" : "bad"}`}>{task.message}
        {task.status === "done" && <> <button className="linkish" onClick={() => apiDownload(`/api/v1/tasks/${task.id}/file`, task.result?.file)}>Download again</button></>}</p>}
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- upload
export function Upload({ model, m, may }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function upload() {
    setBusy(true); setErr("");
    const form = new FormData();
    form.append("file", file);
    try {
      const out = await apiUpload(`/api/v1/models/${model}/loads`, form);
      trackTask(out.task, `#/metamodel/${model}/import/load/${out.load.id}`);
      go(`/metamodel/${model}/import/load/${out.load.id}`);
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <div className="merge-step">
      <h3>Upload a sheet</h3>
      <p className="quiet">A workbook made here (.xlsx or .xlsm), a CSV set (.zip), or a CSV or workbook from another system (you
        map its columns). You see a preview first; the rows then become <b>your uncommitted changes</b>, which you commit (or ask a
        committer to) on the Changes tab, as with any edit.</p>
      {!may ? <p className="quiet small">Loading needs a role that changes the content of {m.name}.</p> : (
        <div className="toolbar">
          <input type="file" accept=".xlsx,.xlsm,.csv,.txt,.zip" onChange={(e) => setFile(e.target.files[0] || null)} />
          <button className="primary" disabled={!file || busy} onClick={upload}>{busy ? "Uploading..." : "⬆ Upload and preview"}</button>
        </div>
      )}
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- a load: preview, mapping, rows, add, undo
function LoadPage({ model, m, id }) {
  const [filter, setFilter] = useState("todo");   // first what the load would do; "all" adds the unchanged rows
  const { data: l, error } = useApi(`/api/v1/loads/${id}${filter && filter !== "todo" && filter !== "all" ? `?action=${filter}` : ""}`);
  const [taskId, setTaskId] = useState(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [editing, setEditing] = useState(null);
  const task = useTask(taskId);
  const working = l && ["uploaded"].includes(l.status);
  useEffect(() => {
    if (!working && !(task && !task.done)) return undefined;
    const t = setInterval(refreshAll, 2500);
    return () => clearInterval(t);
  }, [working, task?.done]);
  if (error) return <p className="status bad">{error}</p>;
  if (!l) return <p>Loading...</p>;
  async function act(fn, done) {
    setErr(""); setMsg("");
    try { const out = await fn(); setMsg(typeof done === "function" ? done(out) : done); refreshAll(); } catch (e) { setErr(e.message); }
  }
  const s = l.summary || {};
  const toAdd = (s.new || 0) + (s.changed || 0) + (s.delete || 0);
  const delivery = !!l.source;
  const rows = (l.rows || []).filter((r) => filter !== "todo" || r.action !== "unchanged" || (r.kept || []).length);
  return (
    <div>
      <p><a href={`#/metamodel/${model}/import/${delivery ? "deliveries" : "loads"}`}>← {delivery ? "Deliveries" : "Loads"}</a></p>
      <div className="merge-step">
        <h3>{l.file_name} <span className="quiet small">· uploaded by {l.created_by} on {fmtDateTime(l.created_at)}{l.owner !== l.created_by ? ` · becomes ${l.owner}'s changes` : ""}</span></h3>
        {delivery && <p className="quiet small">A delivery from <b>{l.source.name}</b> ({{ folder: "dropped in its folder", api: "sent to the API", upload: "uploaded" }[l.delivery]}):
          matched by type and name, never deletes{l.source.values_win ? "; its values win" : "; values already in EA Explorer are kept (only empty fields are filled)"}.
          {l.accepted_by && <> Accepted by {l.accepted_by} on {fmtDateTime(l.accepted_at)}.</>}{l.declined_by && <> Declined by {l.declined_by} on {fmtDateTime(l.declined_at)}.</>}</p>}
        <p className={`status ${l.status === "failed" || l.status === "declined" ? "bad" : l.status === "added" ? "ok" : ""}`}>
          {l.status === "uploaded" ? <><span className="spinner" aria-hidden="true" /> Working out what each row does...</> : l.message}</p>
        {l.status === "previewed" || l.status === "added" || l.status === "undone" ? (
          <div className="merge-stats">
            <button className={filter === "todo" ? "on" : ""} onClick={() => setFilter("todo")}><b>{toAdd + (s.problem || 0)}</b> to look at</button>
            <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}><b>{l.rows_total ?? ""}</b> all</button>
            {Object.entries(ACTIONS).map(([k, label]) => (
              <button key={k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}><b>{s[k] || 0}</b> {label.toLowerCase()}</button>
            ))}
          </div>
        ) : null}
        <div className="toolbar">
          {delivery && <DeliveryActions model={model} load={l} onMessage={setMsg} />}
          {l.status === "previewed" && !delivery && <button className="primary" disabled={!toAdd || (task && !task.done)}
            onClick={() => act(async () => { const out = await post(`/api/v1/loads/${id}/add`); trackTask(out.task, `#/metamodel/${model}/changes`); setTaskId(out.task.id); return out; },
              "Adding in the background: the bar at the top says when it is done.")}>
            {task && !task.done ? "Adding..." : `Add ${toAdd} change${toAdd === 1 ? "" : "s"} to my uncommitted changes`}</button>}
          {l.status === "added" && !delivery && <a href={`#/metamodel/${model}/changes`}>Commit them on the Changes tab →</a>}
          {l.status === "added" && <button className="linkish danger-text" onClick={() => {
            // eslint-disable-next-line no-alert
            if (window.confirm("Undo this load? Its uncommitted changes are discarded; committed ones are rolled back as a new commit.")) {
              act(() => post(`/api/v1/loads/${id}/undo`, {}), (o) => o.message);
            }
          }}>Undo the load</button>}
          {!["added", "declined"].includes(l.status) && !(delivery && l.status === "previewed") && <button className="linkish danger-text" onClick={() => act(() => post(`/api/v1/loads/${id}`, {}, "DELETE"), "")
            .then(() => go(`/metamodel/${model}/import/loads`))}>Forget it</button>}
        </div>
        {msg && <p className="status ok">{msg}</p>}
        {err && <p className="status bad">{err}</p>}
        {(s.failed || []).length > 0 && <details><summary className="status warn">{s.failed.length} rows could not be added</summary>
          <ul className="small">{s.failed.map((f, i) => <li key={i}>Row {f.n}: {f.error}</li>)}</ul></details>}
      </div>
      {l.status === "mapping" && <MapColumns model={model} load={l} onDone={(t) => { trackTask(t, `#/metamodel/${model}/import/load/${id}`); setTaskId(t.id); refreshAll(); }} />}
      {l.sheets?.length > 0 && (
        <table className="grid-table small">
          <thead><tr><th>Sheet</th><th>Holds</th><th className="num">Rows</th><th className="num">New</th><th className="num">Changed</th>
            <th className="num">Delete</th><th className="num">Unchanged</th><th className="num">Problems</th></tr></thead>
          <tbody>{l.sheets.map((x) => (
            <tr key={x.sheet}><td>{x.sheet}</td><td>{x.kind === "relationships" ? "Relationships" : x.entity_type_name}</td><td className="num">{x.rows}</td>
              <td className="num">{x.new}</td><td className="num">{x.changed}</td><td className="num">{x.delete}</td><td className="num">{x.unchanged}</td>
              <td className="num">{x.problem || ""}</td></tr>))}</tbody>
        </table>
      )}
      {rows.length > 0 && (<div className="table-scroll">
        <table className="grid-table load-rows">
          <thead><tr><th>What</th><th>Sheet · row</th><th>Item</th><th>Changes</th><th>Problems and warnings</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.n} className={`la-${r.action}`}>
                <td><b>{ACTIONS[r.action]}</b>{r.matched_by === "name" && <div className="quiet small" title="No GUID or ID: found by its type and name">by name</div>}</td>
                <td className="small">{r.sheet} · {r.row}</td>
                <td>{r.kind === "entity" ? <>{r.id && <span className="quiet">{r.id} </span>}<b>{r.name}</b><div className="quiet small">{r.entity_type_name}</div></>
                  : <>{r.source} <b>{r.relationship_type}</b> {r.target}{r.name && <div className="quiet small">{r.name}</div>}</>}</td>
                <td className="small">{r.changes.slice(0, 8).map((c, i) => (
                  <div key={i}><b>{c.field}</b>: {c.old ? <><del>{c.old}</del> → </> : ""}{c.new || <span className="quiet">(empty)</span>}</div>))}
                  {r.changes.length > 8 && <span className="quiet">+{r.changes.length - 8} more</span>}
                  {(r.kept || []).map((c, i) => (
                    <div key={`k${i}`} className="quiet" title="EA Explorer's value stays: this source's values do not win">
                      <b>{c.field}</b>: kept {c.old} <span className="small">(delivered: {c.new})</span></div>))}</td>
                <td className="small">{r.problems.map((p, i) => <div key={i} className="sev error">{p}</div>)}
                  {r.warnings.map((w, i) => <div key={`w${i}`} className="sev warning">{w}</div>)}</td>
                <td>{l.status === "previewed" && !delivery && <button className="linkish" onClick={() => setEditing(r)}>Correct</button>}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
      {l.rows_total > (l.rows || []).length && <p className="quiet small">The first {l.rows.length} of {l.rows_total} rows; filter by what they do.</p>}
      {editing && <EditRow load={l} row={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refreshAll(); }} />}
    </div>
  );
}

function EditRow({ load, row, onClose, onSaved }) {
  const [values, setValues] = useState({ ...row.data });
  const [err, setErr] = useState("");
  const keys = Object.keys(values).filter((k) => !k.startsWith("_"));
  async function save() {
    setErr("");
    try { await post(`/api/v1/loads/${load.id}/rows/${row.n}`, { values }, "PATCH"); onSaved(); } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={`Correct ${row.sheet}, row ${row.row}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={save}>Save and check again</button></>}>
      <p className="quiet small">The row as it will be loaded; the preview is worked out again when you save. The file is not changed.</p>
      <div className="form-grid">
        {keys.map((k) => (
          <label key={k} className="ed-field"><span>{k}</span>
            <input value={values[k] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))} /></label>
        ))}
      </div>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// sheets EA Explorer does not know: each header to a field or attribute (or ignored), saved for the next file if wanted
function MapColumns({ model, load, onDone }) {
  const { data: types } = useApi(`/api/v1/models/${model}/sheets`);
  const { data: saved } = useApi(`/api/v1/models/${model}/column-mappings`);
  const [maps, setMaps] = useState(() => Object.fromEntries(load.needs_mapping.map((n) => [n.sheet, { entity_type: n.type_guess || "", columns: {} }])));
  const [saveAs, setSaveAs] = useState("");
  const [err, setErr] = useState("");
  const fieldsFor = useFields(model, Object.values(maps).map((x) => x.entity_type).filter(Boolean));
  async function send(body) {
    setErr("");
    try { const out = await post(`/api/v1/loads/${load.id}/mapping`, body); onDone(out.task); } catch (e) { setErr(e.message); }
  }
  return (
    <div className="merge-step">
      <h3>Map the columns</h3>
      <p className="quiet">These sheets are not EA Explorer sheets: say which entity type each holds and what each column is. A
        column you leave on "ignore" is not loaded. Rows are matched by ID if there is an ID column, otherwise by type and name.</p>
      {load.needs_mapping.map((n) => {
        const mp = maps[n.sheet];
        const fields = fieldsFor(mp.entity_type);
        return (
          <fieldset key={n.sheet} className="form-section">
            <legend>{n.sheet} <span className="quiet small">· {n.rows} rows</span></legend>
            <div className="toolbar">
              <label>Entity type{" "}
                <select value={mp.entity_type} onChange={(e) => setMaps((x) => ({ ...x, [n.sheet]: { ...mp, entity_type: e.target.value } }))}>
                  <option value="">Choose...</option>
                  {(types?.types || []).map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
                </select></label>
              {(saved?.mappings || []).length > 0 && <label>or a saved mapping{" "}
                <select defaultValue="" onChange={(e) => e.target.value && send({ saved: e.target.value, sheet: n.sheet })}>
                  <option value="">Choose...</option>
                  {saved.mappings.map((s) => <option key={s.id} value={s.id}>{s.name}{s.entity_type_name ? ` (${s.entity_type_name})` : ""}</option>)}
                </select></label>}
            </div>
            {mp.entity_type && (
              <table className="grid-table small">
                <thead><tr><th>Column in the file</th><th>Example</th><th>Is</th></tr></thead>
                <tbody>{n.headers.filter(Boolean).map((h) => (
                  <tr key={h}><td>{h}</td><td className="quiet">{n.sample.map((x) => x[h]).filter(Boolean).slice(0, 2).join(", ")}</td>
                    <td><select value={mp.columns[h] ?? guess(h, fields)} onChange={(e) => setMaps((x) => ({ ...x, [n.sheet]: { ...mp, columns: { ...mp.columns, [h]: e.target.value } } }))}>
                      <option value="">ignore</option>
                      {fields.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
                    </select></td></tr>))}</tbody>
              </table>
            )}
          </fieldset>
        );
      })}
      <div className="toolbar">
        <input placeholder="Save the mapping as (optional)" value={saveAs} onChange={(e) => setSaveAs(e.target.value)} style={{ minWidth: 260 }} />
        <button className="primary" disabled={load.needs_mapping.some((n) => !maps[n.sheet].entity_type)} onClick={() => send({
          mapping: Object.fromEntries(load.needs_mapping.map((n) => {
            const mp = maps[n.sheet];
            const fields = fieldsFor(mp.entity_type);
            return [n.sheet, { entity_type: mp.entity_type, columns: Object.fromEntries(n.headers.filter(Boolean).map((h) => [h, mp.columns[h] ?? guess(h, fields)])) }];
          })), save_as: saveAs || null })}>Use this mapping and preview</button>
      </div>
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}

// the fields of the chosen types: fixed fields and attributes, [code, label]
function useFields(model, codes) {
  const key = [...new Set(codes)].sort().join(",");
  const { data } = useApi(key ? `/api/v1/models/${model}/sheets/fields?types=${encodeURIComponent(key)}` : null);
  return useMemo(() => (code) => {
    const fixed = [["guid", "GUID"], ["display_id", "ID"], ["name", "Name"], ["description", "Description"], ["parent", "Parent ID"], ["tags", "Tags"], ["delete", "Delete"]];
    const t = (data?.types || []).find((x) => x.code === code);
    return [...fixed, ...((t?.attributes || []).map((a) => [a.code, a.name]))];
  }, [data]);
}

function guess(header, fields) {
  const h = header.toLowerCase().replace(/[^a-z0-9]/g, "");
  const hit = fields.find(([code, label]) => code.toLowerCase().replace(/[^a-z0-9]/g, "") === h || label.toLowerCase().replace(/[^a-z0-9]/g, "") === h);
  return hit ? hit[0] : "";
}

// ---------------------------------------------------------------- the loads of a model
function LoadList({ model }) {
  const { data, error } = useApi(`/api/v1/models/${model}/loads`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  return (
    <table className="grid-table">
      <thead><tr><th>File</th><th>By</th><th>When</th><th>Status</th><th className="num">New</th><th className="num">Changed</th>
        <th className="num">Delete</th><th className="num">Problems</th></tr></thead>
      <tbody>
        {data.loads.map((l) => (
          <tr key={l.id}>
            <td><a href={`#/metamodel/${model}/import/load/${l.id}`}>{l.file_name}</a></td>
            <td className="small">{l.created_by}{l.owner !== l.created_by ? ` → ${l.owner}` : ""}</td>
            <td className="small">{fmtDateTime(l.created_at)}</td><td className="small">{l.status}</td>
            <td className="num">{l.summary.new ?? ""}</td><td className="num">{l.summary.changed ?? ""}</td>
            <td className="num">{l.summary.delete ?? ""}</td><td className="num">{l.summary.problem || ""}</td>
          </tr>
        ))}
        {!data.loads.length && <tr><td colSpan="8" className="quiet">No loads yet.</td></tr>}
      </tbody>
    </table>
  );
}

// saved column mappings (made when mapping a sheet from another system), shown under the loads
function SavedMappings({ model }) {
  const { data } = useApi(`/api/v1/models/${model}/column-mappings`);
  const [err, setErr] = useState("");
  const maps = data?.mappings || [];
  return (
    <div className="merge-step">
      <h3>Saved column mappings</h3>
      <p className="quiet small">Made when you map the columns of a sheet from another system; pick one next time instead of mapping again.</p>
      <div className="table-scroll">
        <table className="grid-table small">
          <thead><tr><th>Mapping</th><th>Type</th><th>Columns</th><th>By</th><th /></tr></thead>
          <tbody>{maps.map((x) => (
            <tr key={x.id}><td>{x.name}</td><td>{x.entity_type_name || ""}</td>
              <td>{Object.entries(x.columns).filter(([, v]) => v).map(([h, v]) => `${h} → ${v}`).join("; ")}</td><td>{x.created_by}</td>
              <td><button className="linkish danger-text" onClick={() => post(`/api/v1/models/${model}/column-mappings/${x.id}`, {}, "DELETE")
                .then(refreshAll).catch((e) => setErr(e.message))}>Delete</button></td></tr>))}
            {!maps.length && <tr><td colSpan="5" className="quiet">None yet.</td></tr>}</tbody>
        </table>
      </div>
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}
