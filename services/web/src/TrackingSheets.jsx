// Tracking sheets (owner, 8 Nov 2026, phase 13.2, D325): light sheets with no schema rules (an application portfolio,
// vendors, costs), at project level (anyone who contributes) and organisation level (Super Admins and Library Admins).
// Uploaded from Excel (first tab) or CSV, downloaded as Excel (all rows or the filtered ones), edited in place, with a
// filter and a pick of values per column and sorting. Every value is text; sheets never count in data quality.
import { useMemo, useState } from "react";
import { apiDownload, apiFetch, apiUpload } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";

export function TrackingSheets({ scope }) {
  const [open, setOpen] = useState(() => (window.location.hash.match(/[?&]sheet=([^&]+)/) || [])[1] || "");
  const { data, error } = useApi(`/api/v1/tracking-sheets/${scope}`);
  const [dlg, setDlg] = useState(null);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  if (open) return <SheetEditor scope={scope} sid={open} onBack={() => setOpen("")} />;
  return (
    <div>
      <p className="quiet">Tracking sheets: lists kept without the rules of a metamodel, such as an application portfolio, vendors or costs. Every value is
        text, columns are whatever you upload or add, and sheets never count in data quality. {scope === "org"
          ? "Organisation sheets are kept by Super Admins and Library Admins; everyone reads them." : "Anyone who contributes to the project keeps them."}</p>
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      {data.may_write && <div className="row-gap">
        <button className="primary" onClick={() => setDlg("new")}>＋ New sheet</button>
        <button onClick={() => setDlg("upload")}>⬆ From Excel or CSV…</button></div>}
      <table className="grid-table" style={{ marginTop: 8 }}>
        <thead><tr><th>Sheet</th><th>Columns</th><th className="num">Rows</th><th>Changed</th></tr></thead>
        <tbody>
          {data.sheets.map((s) => <tr key={s.id}>
            <td><button className="linkish" onClick={() => setOpen(s.id)}><b>{s.name}</b></button>{s.description && <div className="small quiet">{s.description}</div>}</td>
            <td className="small">{s.columns.slice(0, 8).join(", ")}{s.columns.length > 8 ? ` … (${s.columns.length})` : ""}</td>
            <td className="num">{s.rows}</td><td className="small">{s.modified_by} · {fmtDateTime(s.modified_at)}</td></tr>)}
          {!data.sheets.length && <tr><td colSpan={4} className="quiet">No sheets yet.</td></tr>}
        </tbody>
      </table>
      {dlg && <NewSheet scope={scope} upload={dlg === "upload"} onClose={(r) => { setDlg(null); if (r) { setMsg({ ok: true, text: r.message }); refreshAll(); if (r.id) setOpen(r.id); } }} />}
    </div>
  );
}

function NewSheet({ scope, upload, onClose }) {
  const [name, setName] = useState("");
  const [cols, setCols] = useState("Name, Owner, Status");
  const [file, setFile] = useState(null);
  const [err, setErr] = useState("");
  async function go() {
    setErr("");
    try {
      if (upload) {
        const fd = new FormData(); fd.append("file", file); fd.append("name", name);
        onClose(await apiUpload(`/api/v1/tracking-sheets/${scope}`, fd));
      } else {
        onClose(await apiFetch(`/api/v1/tracking-sheets/${scope}`, { method: "POST", body: JSON.stringify({ name, columns: cols.split(",") }) }));
      }
    } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={upload ? "A sheet from Excel or CSV" : "A new sheet"} onClose={() => onClose()}
      actions={<><button onClick={() => onClose()}>Cancel</button><button className="primary" disabled={upload ? !file : !name.trim()} onClick={go}>{upload ? "Upload" : "Make it"}</button></>}>
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        <label className="ed-field"><span>Name {upload && <span className="quiet">(empty: the file's name)</span>}</span><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
        {upload ? <label className="ed-field"><span>File <span className="quiet">(the first tab; its first row gives the columns)</span></span>
          <input type="file" accept=".xlsx,.xlsm,.csv" onChange={(e) => setFile(e.target.files[0] || null)} /></label>
          : <label className="ed-field"><span>Columns <span className="quiet">(comma separated; add more any time)</span></span><input value={cols} onChange={(e) => setCols(e.target.value)} /></label>}
      </div>
    </Modal>
  );
}

function SheetEditor({ scope, sid, onBack }) {
  const url = `/api/v1/tracking-sheets/${scope}/${sid}`;
  const { data, error } = useApi(url);
  const [filters, setFilters] = useState({});
  const [picks, setPicks] = useState({});
  const [q, setQ] = useState("");
  const [sort, setSort] = useState({ col: "", dir: 1 });
  const [ticked, setTicked] = useState(() => new Set());
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const [dlg, setDlg] = useState("");
  const rows = useMemo(() => {
    if (!data) return [];
    const ql = q.trim().toLowerCase();
    let out = data.rows.filter((r) => (!ql || Object.values(r.cells).join(" ").toLowerCase().includes(ql))
      && data.columns.every((c) => (!filters[c] || (r.cells[c] || "").toLowerCase().includes(filters[c].toLowerCase()))
        && (!picks[c] || (r.cells[c] || "") === picks[c])));
    if (sort.col) {
      const num = (v) => (v !== "" && !Number.isNaN(Number(String(v).replace(/[ ,]/g, ""))) ? Number(String(v).replace(/[ ,]/g, "")) : null);
      out = [...out].sort((a, b) => {
        const x = a.cells[sort.col] || ""; const y = b.cells[sort.col] || "";
        const nx = num(x); const ny = num(y);
        return (nx !== null && ny !== null ? nx - ny : x.localeCompare(y)) * sort.dir;
      });
    }
    return out;
  }, [data, q, filters, picks, sort]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const can = data.may_write;
  async function put(body, quiet) {
    try { const r = await apiFetch(url, { method: "PUT", body: JSON.stringify(body) }); if (!quiet) setMsg({ ok: true, text: r.message }); refreshAll(); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
  }
  const values = (c) => [...new Set(data.rows.map((r) => r.cells[c] || ""))].filter(Boolean).sort().slice(0, 200);
  const filtered = rows.length !== data.rows.length;
  const tickAll = () => setTicked(rows.every((r) => ticked.has(r.id)) && rows.length ? new Set() : new Set(rows.map((r) => r.id)));
  return (
    <div className="tsheet">
      <div className="row-gap">
        <button className="linkish" onClick={onBack}>‹ All sheets</button>
        <h3 style={{ margin: 0 }}>{data.name}</h3>
        {can && <button className="linkish small" onClick={() => setDlg("name")}>✎ Rename</button>}
        <span className="small quiet">{data.rows.length} rows · {data.columns.length} columns · changed by {data.modified_by}</span>
      </div>
      {data.description && <p className="small quiet">{data.description}</p>}
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <div className="row-gap cf-tag-tools">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find in any column" aria-label="Find" />
        {filtered && <><span className="small">{rows.length} of {data.rows.length} shown</span>
          <button className="linkish small" onClick={() => { setFilters({}); setPicks({}); setQ(""); }}>Clear the filters</button></>}
        <span style={{ flex: 1 }} />
        {can && <>
          <button onClick={() => put({ add: [{}] })}>＋ Row</button>
          <button onClick={() => setDlg("column")}>＋ Column</button>
          <button disabled={!ticked.size} className="danger" onClick={() => put({ delete: [...ticked] }).then(() => setTicked(new Set()))}>Delete {ticked.size || ""} ticked</button>
          <button onClick={() => setDlg("upload")}>⬆ Upload…</button>
        </>}
        <button onClick={() => apiDownload(`${url}/xlsx`, `${data.name}.xlsx`).catch((e) => setMsg({ ok: false, text: e.message }))}>⬇ Excel</button>
        {filtered && <button onClick={() => apiDownload(`${url}/xlsx?rows=${rows.map((r) => r.id).join(",")}`, `${data.name} (filtered).xlsx`).catch((e) => setMsg({ ok: false, text: e.message }))}>⬇ Filtered rows</button>}
      </div>
      <div className="table-wrap tsheet-wrap">
        <table className="grid-table tsheet-table">
          <thead>
            <tr>
              {can && <th style={{ width: 24 }}><input type="checkbox" aria-label="Tick every row shown" checked={rows.length > 0 && rows.every((r) => ticked.has(r.id))} onChange={tickAll} /></th>}
              {data.columns.map((c) => (
                <th key={c}>
                  <button className="linkish" title="Sort" onClick={() => setSort({ col: c, dir: sort.col === c ? -sort.dir : 1 })}>
                    {c} {sort.col === c ? (sort.dir > 0 ? "▲" : "▼") : ""}</button>
                  {can && <button className="linkish small" title="Rename or remove the column" onClick={() => setDlg(`col:${c}`)}>⋯</button>}
                </th>
              ))}
            </tr>
            <tr className="tsheet-filters">
              {can && <th />}
              {data.columns.map((c) => (
                <th key={c}>
                  <input value={filters[c] || ""} onChange={(e) => setFilters({ ...filters, [c]: e.target.value })} placeholder="filter" aria-label={`Filter ${c}`} />
                  <select value={picks[c] || ""} onChange={(e) => setPicks({ ...picks, [c]: e.target.value })} aria-label={`Pick a value of ${c}`}>
                    <option value="">all</option>{values(c).map((v) => <option key={v} value={v}>{v}</option>)}</select>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={ticked.has(r.id) ? "ticked" : ""}>
                {can && <td><input type="checkbox" checked={ticked.has(r.id)} onChange={() => { const n = new Set(ticked); if (n.has(r.id)) n.delete(r.id); else n.add(r.id); setTicked(n); }} aria-label="Tick the row" /></td>}
                {data.columns.map((c) => (
                  <td key={c}>{can ? <Cell value={r.cells[c] || ""} onSave={(v) => put({ rows: [{ id: r.id, cells: { [c]: v } }] }, true)} /> : (r.cells[c] || "")}</td>
                ))}
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={data.columns.length + 1} className="quiet">{data.rows.length ? "Nothing matches the filters." : "No rows yet."}</td></tr>}
          </tbody>
        </table>
      </div>
      {dlg === "upload" && <UploadInto url={url} columns={data.columns} onClose={(m) => { setDlg(""); if (m) { setMsg({ ok: true, text: m }); refreshAll(); } }} />}
      {dlg === "column" && <Ask title="A new column" label="Its name" onClose={(v) => { setDlg(""); if (v) put({ columns: [...data.columns, v] }); }} />}
      {dlg === "name" && <Ask title="Rename the sheet" label="Name" value={data.name} onClose={(v) => { setDlg(""); if (v) put({ name: v }); }} />}
      {dlg.startsWith("col:") && <ColumnDialog col={dlg.slice(4)} columns={data.columns} onClose={(body) => { setDlg(""); if (body) put(body); }} />}
    </div>
  );
}

// a cell edited in place: saved when you leave it, if it changed
function Cell({ value, onSave }) {
  const [v, setV] = useState(value);
  const [was, setWas] = useState(value);
  if (value !== was) { setWas(value); setV(value); }
  return <input className="tsheet-cell" value={v} onChange={(e) => setV(e.target.value)} onBlur={() => v !== value && onSave(v)}
    onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") setV(value); }} />;
}

function Ask({ title, label, value = "", onClose }) {
  const [v, setV] = useState(value);
  return (
    <Modal title={title} onClose={() => onClose()} actions={<><button onClick={() => onClose()}>Cancel</button><button className="primary" disabled={!v.trim()} onClick={() => onClose(v.trim())}>OK</button></>}>
      <label className="ed-field"><span>{label}</span><input value={v} onChange={(e) => setV(e.target.value)} autoFocus onKeyDown={(e) => e.key === "Enter" && v.trim() && onClose(v.trim())} /></label>
    </Modal>
  );
}

function ColumnDialog({ col, columns, onClose }) {
  const [name, setName] = useState(col);
  const i = columns.indexOf(col);
  const moved = (d) => { const c = [...columns]; const j = i + d; [c[i], c[j]] = [c[j], c[i]]; return c; };
  return (
    <Modal title={`Column ${col}`} onClose={() => onClose()}
      actions={<><button className="danger" onClick={() => onClose({ columns: columns.filter((c) => c !== col) })}>Remove the column</button>
        <button onClick={() => onClose()}>Cancel</button>
        <button className="primary" disabled={!name.trim() || name.trim() === col} onClick={() => onClose({ renames: { [col]: name.trim() } })}>Rename</button></>}>
      <label className="ed-field"><span>Name</span><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <p className="row-gap"><button disabled={i <= 0} onClick={() => onClose({ columns: moved(-1) })}>◀ Move left</button>
        <button disabled={i >= columns.length - 1} onClick={() => onClose({ columns: moved(1) })}>Move right ▶</button></p>
      <p className="small quiet">Removing a column removes its values from every row.</p>
    </Modal>
  );
}

function UploadInto({ url, columns, onClose }) {
  const [file, setFile] = useState(null);
  const [how, setHow] = useState("add");
  const [key, setKey] = useState(columns[0] || "");
  const [err, setErr] = useState("");
  async function go() {
    setErr("");
    const fd = new FormData(); fd.append("file", file); fd.append("how", how); fd.append("key", key);
    try { onClose((await apiUpload(`${url}/upload`, fd)).message); } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title="Upload into the sheet" onClose={() => onClose()}
      actions={<><button onClick={() => onClose()}>Cancel</button><button className="primary" disabled={!file} onClick={go}>Upload</button></>}>
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        <label className="ed-field"><span>File <span className="quiet">(Excel's first tab or CSV; its first row gives the columns)</span></span>
          <input type="file" accept=".xlsx,.xlsm,.csv" onChange={(e) => setFile(e.target.files[0] || null)} /></label>
        <fieldset className="ed-field"><legend>What to do with the rows</legend>
          <label><input type="radio" checked={how === "add"} onChange={() => setHow("add")} /> Add them</label><br />
          <label><input type="radio" checked={how === "update"} onChange={() => setHow("update")} /> Update the rows matched on a key column, add the others</label>
          {how === "update" && <select value={key} onChange={(e) => setKey(e.target.value)} aria-label="Key column" style={{ marginLeft: 8 }}>
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}</select>}<br />
          <label><input type="radio" checked={how === "replace"} onChange={() => setHow("replace")} /> Replace every row (the sheet becomes the file)</label>
        </fieldset>
        <p className="small quiet">Columns in the file that the sheet does not have are added. Only the latest version is kept.</p>
      </div>
    </Modal>
  );
}
