// The organisation's reference library (owner, 8 Nov 2026, phase 13.0.8, D300): #/reference-library[/<entry>].
// Documents and links in a free folder tree, with title, description, source and tags; search finds words inside the
// documents too; every version of a file is kept. Everyone reads it; Super Admins change it. Projects link to entries
// from their Reference tab (EnterprisePicker).
import { useMemo, useState } from "react";
import { apiDownload, apiFetch, apiUpload } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Field, Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";

const size = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n > 1024 ? `${Math.round(n / 1024)} kB` : `${n || 0} B`);

export default function ReferenceLibraryPage({ route }) {
  const id = route.replace(/^#\/reference-library\/?/, "").split("?")[0];
  return <section className="page">{id ? <EntryPage id={id} /> : <Library />}</section>;
}

function Library() {
  const [folder, setFolder] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");
  const [kind, setKind] = useState("");
  const [deep, setDeep] = useState(false);
  const [dlg, setDlg] = useState(null);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const url = `/api/v1/reference-library?folder=${encodeURIComponent(folder)}&q=${encodeURIComponent(query)}&tag=${encodeURIComponent(tag)}&kind=${kind}&deep=${deep}`;
  const { data, error } = useApi(url);
  const depth = (f) => (f ? f.split("/").length : 0);
  async function act(fn) {
    try { const r = await fn(); setMsg({ ok: true, text: r?.message || "Done." }); refreshAll(); return r; } catch (e) { setMsg({ ok: false, text: e.message }); return null; }
  }
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const can = data.may_write;
  return (
    <div>
      <h1>Reference library</h1>
      <p className="quiet">The organisation's reference material, for everyone: standards, regulations, reference architectures, research, useful web
        pages. Search finds words inside the documents too. Every version of a file is kept. Super Admins add and change it; a project links to an
        entry from its Reference tab. (Each project's own reference material stays on its Reference tab.)</p>
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <form className="row-gap filters" onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }}>
        <input type="search" value={q} onChange={(e) => { setQ(e.target.value); if (!e.target.value) setQuery(""); }} placeholder="Search titles, tags and inside documents" aria-label="Search" style={{ minWidth: 320 }} />
        <button type="submit">Search</button>
        <select value={tag} onChange={(e) => setTag(e.target.value)} aria-label="Tag"><option value="">Any tag</option>
          {data.tags.map((t) => <option key={t.tag} value={t.tag}>{t.tag} ({t.n})</option>)}</select>
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind"><option value="">Documents and links</option>
          <option value="file">Documents</option><option value="link">Links</option></select>
        <label className="small"><input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} /> include sub-folders</label>
        {can && <span className="push-right row-gap">
          <button type="button" className="primary" onClick={() => setDlg({ k: "file" })}>⬆ Add documents</button>
          <button type="button" onClick={() => setDlg({ k: "link" })}>🔗 Add a link</button>
          <button type="button" onClick={() => { const n = window.prompt(`A new folder${folder ? ` in ${folder}` : ""}`, "");
            if (n && n.trim()) act(() => apiFetch("/api/v1/reference-library/folders", { method: "POST", body: JSON.stringify({ path: folder ? `${folder}/${n.trim()}` : n.trim() }) })).then((r) => r && setFolder(r.path)); }}>＋ Folder</button>
        </span>}
      </form>
      <div className="ref-layout">
        <nav className="ref-tree" aria-label="Folders">
          <button className={`linkish ref-folder${!folder ? " on" : ""}`} onClick={() => setFolder("")}>📚 Reference library <span className="small quiet">{data.top_entries || ""}</span></button>
          {data.folders.map((f) => (
            <button key={f.path} className={`linkish ref-folder${folder === f.path ? " on" : ""}`} style={{ paddingLeft: 6 + 14 * depth(f.path) }}
              onClick={() => setFolder(f.path)} title={f.description || f.path}>📁 {f.path.split("/").pop()} <span className="small quiet">{f.entries || ""}</span></button>
          ))}
          {can && folder && <button className="linkish small bad-text" style={{ marginTop: 8 }}
            onClick={() => act(() => apiFetch("/api/v1/reference-library/folders", { method: "POST", body: JSON.stringify({ path: folder, delete: true }) })).then((r) => r && setFolder(""))}>Remove this folder (if empty)</button>}
        </nav>
        <div>
          <p className="small quiet">{data.searching ? `${data.entries.length} found${folder ? ` in ${folder}` : ""}` : (folder || "The top of the library")}</p>
          {!data.entries.length ? <p className="quiet">{data.searching ? "Nothing matches." : "Nothing here yet."}</p> : (
            <table className="grid-table">
              <thead><tr><th>Title</th><th>Tags</th><th>Source</th>{(data.searching || deep) && <th>Folder</th>}<th>Changed</th><th /></tr></thead>
              <tbody>{data.entries.map((e) => (
                <tr key={e.id}>
                  <td>{e.kind === "link" ? "🔗" : "📄"} <a href={`#/reference-library/${e.id}`}><b>{e.title}</b></a>
                    {e.kind === "file" && <span className="small quiet"> v{e.version}{e.has_text ? "" : " · no text to search"}</span>}
                    {e.description && <div className="small quiet">{e.description.slice(0, 160)}</div>}
                    {e.excerpt && <div className="small ref-excerpt">…{e.excerpt}…</div>}</td>
                  <td>{e.tags.map((t) => <button key={t} className="tag-chip" onClick={() => setTag(t)}>{t}</button>)}</td>
                  <td className="small">{e.source}</td>
                  {(data.searching || deep) && <td className="small">{e.folder || "–"}</td>}
                  <td className="small nowrap">{fmtDateTime(e.modified_at)}</td>
                  <td className="nowrap small">{e.kind === "link" ? <a href={e.url} target="_blank" rel="noreferrer">Open ↗</a>
                    : <button className="linkish" onClick={() => act(() => apiDownload(`/api/v1/reference-library/${e.id}/file`, e.file_name))}>⬇ Download</button>}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      </div>
      {dlg && <AddDialog k={dlg.k} folder={folder} folders={data.folders} onClose={(m) => { setDlg(null); if (m) setMsg({ ok: true, text: m }); }} />}
    </div>
  );
}

function AddDialog({ k, folder, folders, onClose }) {
  const [f, setF] = useState({ folder, title: "", url: "", description: "", source: "", tags: "" });
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const set = (key, v) => setF((x) => ({ ...x, [key]: v }));
  async function save() {
    setErr("");
    try {
      if (k === "link") {
        const r = await apiFetch("/api/v1/reference-library/links", { method: "POST", body: JSON.stringify(f) });
        refreshAll(); onClose(r.message); return;
      }
      const failed = [];
      for (const [i, file] of files.entries()) {
        setBusy(`Adding ${i + 1} of ${files.length}…`);
        const fd = new FormData(); fd.append("file", file);
        for (const key of ["folder", "description", "source", "tags"]) if (f[key]) fd.append(key, f[key]);
        if (files.length === 1 && f.title.trim()) fd.append("title", f.title.trim());
        try { await apiUpload("/api/v1/reference-library/files", fd); } catch (e) { failed.push(`${file.name}: ${e.message}`); }
      }
      refreshAll();
      if (failed.length) { setErr(`Not added: ${failed.join("; ")}`); setBusy(""); return; }
      onClose(`${files.length} document${files.length === 1 ? "" : "s"} added.`);
    } catch (e) { setErr(e.message); setBusy(""); }
  }
  const ready = k === "link" ? f.title.trim() && f.url.trim() : files.length > 0;
  return (
    <Modal title={k === "link" ? "Add a link" : "Add documents"} onClose={() => onClose()} wide
      actions={<><button onClick={() => onClose()}>Cancel</button><button className="primary" disabled={!ready || !!busy} onClick={save}>{busy || "Add"}</button></>}>
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        <Field label="Folder"><input list="ref-folders" value={f.folder} onChange={(e) => set("folder", e.target.value)} placeholder="the top of the library" />
          <datalist id="ref-folders">{folders.map((x) => <option key={x.path} value={x.path} />)}</datalist></Field>
        {k === "file" && <Field label="Files" hint="(one or more; the text inside PDF, Word, PowerPoint and Excel files is kept for search)">
          <input type="file" multiple onChange={(e) => { setFiles([...files, ...e.target.files]); e.target.value = ""; }} />
          {files.length > 0 && <ul className="small">{files.map((x, i) => <li key={`${x.name}${i}`}>{x.name}
            <button className="linkish" onClick={() => setFiles(files.filter((_y, j) => j !== i))}> Remove</button></li>)}</ul>}</Field>}
        {(k === "link" || files.length <= 1) && <Field label="Title" hint={k === "file" ? "(empty: from the file's name)" : ""}>
          <input value={f.title} onChange={(e) => set("title", e.target.value)} /></Field>}
        {k === "link" && <Field label="Address"><input value={f.url} onChange={(e) => set("url", e.target.value)} placeholder="https://" /></Field>}
        <Field label="Description"><textarea rows={3} value={f.description} onChange={(e) => set("description", e.target.value)} /></Field>
        <div className="row-gap">
          <Field label="Source"><input value={f.source} onChange={(e) => set("source", e.target.value)} placeholder="e.g. The Open Group, a regulator, a team" /></Field>
          <Field label="Tags" hint="(comma separated)"><input value={f.tags} onChange={(e) => set("tags", e.target.value)} /></Field>
        </div>
      </div>
    </Modal>
  );
}

function EntryPage({ id }) {
  const { data: e, error } = useApi(`/api/v1/reference-library/${id}`);
  const [edit, setEdit] = useState(null);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  async function act(fn) {
    try { const r = await fn(); setMsg({ ok: true, text: r?.message || "Done." }); refreshAll(); return r; } catch (er) { setMsg({ ok: false, text: er.message }); return null; }
  }
  if (error) return <><p><a href="#/reference-library">‹ Reference library</a></p><p className="status bad">{error}</p></>;
  if (!e) return <p className="quiet">Loading...</p>;
  function newVersion() {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.onchange = () => {
      const file = inp.files[0];
      if (!file) return;
      const note = window.prompt("What changed in this version? (optional)", "") || "";
      const fd = new FormData(); fd.append("file", file); fd.append("note", note);
      act(() => apiUpload(`/api/v1/reference-library/${id}/versions`, fd));
    };
    inp.click();
  }
  return (
    <div>
      <p className="small"><a href="#/reference-library">‹ Reference library</a>{e.folder && <> › {e.folder}</>}</p>
      <h1>{e.kind === "link" ? "🔗" : "📄"} {e.title}</h1>
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <div className="row-gap">
        {e.kind === "link" ? <a className="button primary" href={e.url} target="_blank" rel="noreferrer">Open ↗</a>
          : <button className="primary" onClick={() => act(() => apiDownload(`/api/v1/reference-library/${id}/file`, e.file_name))}>⬇ Download (v{e.version})</button>}
        {e.may_write && <>
          {e.kind === "file" && <button onClick={newVersion}>⬆ New version</button>}
          <button onClick={() => setEdit({ title: e.title, description: e.description, source: e.source, tags: e.tags.join(", "), folder: e.folder, url: e.url })}>✎ Change</button>
          <button className="danger" onClick={() => { if (window.confirm(`Delete ${e.title} from the reference library? Its files go to the document store's trash.`))
            act(() => apiFetch(`/api/v1/reference-library/${id}`, { method: "DELETE" })).then((r) => { if (r) window.location.hash = "#/reference-library"; }); }}>Delete</button></>}
      </div>
      <table className="grid-table" style={{ marginTop: 12 }}><tbody>
        {e.kind === "link" && <tr><th>Address</th><td><a href={e.url} target="_blank" rel="noreferrer">{e.url}</a></td></tr>}
        {e.kind === "file" && <tr><th>File</th><td>{e.file_name}{e.has_text ? "" : <span className="quiet"> (no text could be read from it for search)</span>}</td></tr>}
        <tr><th>Description</th><td style={{ whiteSpace: "pre-line" }}>{e.description || <span className="quiet">–</span>}</td></tr>
        <tr><th>Source</th><td>{e.source || <span className="quiet">–</span>}</td></tr>
        <tr><th>Tags</th><td>{e.tags.map((t) => <span key={t} className="chip small">{t}</span>)}</td></tr>
        <tr><th>Added</th><td>{e.created_by}, {fmtDateTime(e.created_at)}</td></tr>
        <tr><th>Changed</th><td>{e.modified_by}, {fmtDateTime(e.modified_at)}</td></tr>
      </tbody></table>
      {e.kind === "file" && <>
        <h3>Versions</h3>
        <table className="grid-table small"><thead><tr><th>Version</th><th>File</th><th>Size</th><th>What changed</th><th>By</th><th /></tr></thead>
          <tbody>{e.versions.map((v) => (
            <tr key={v.version}><td>v{v.version}{v.version === e.version && " (current)"}</td><td>{v.file_name}</td><td>{size(v.size_bytes)}</td>
              <td>{v.note}</td><td>{v.by_user} · {fmtDateTime(v.at)}</td>
              <td><button className="linkish" onClick={() => act(() => apiDownload(`/api/v1/reference-library/${id}/file?version=${v.version}`, v.file_name))}>⬇</button></td></tr>
          ))}</tbody></table></>}
      {edit && (
        <Modal title={`Change ${e.title}`} onClose={() => setEdit(null)} wide
          actions={<><button onClick={() => setEdit(null)}>Cancel</button><button className="primary" disabled={!edit.title.trim()}
            onClick={() => act(() => apiFetch(`/api/v1/reference-library/${id}`, { method: "PUT", body: JSON.stringify(edit) })).then((r) => r && setEdit(null))}>Save</button></>}>
          <div className="ed-form">
            <Field label="Title"><input value={edit.title} onChange={(x) => setEdit({ ...edit, title: x.target.value })} /></Field>
            {e.kind === "link" && <Field label="Address"><input value={edit.url} onChange={(x) => setEdit({ ...edit, url: x.target.value })} /></Field>}
            <Field label="Folder"><input value={edit.folder} onChange={(x) => setEdit({ ...edit, folder: x.target.value })} /></Field>
            <Field label="Description"><textarea rows={3} value={edit.description} onChange={(x) => setEdit({ ...edit, description: x.target.value })} /></Field>
            <Field label="Source"><input value={edit.source} onChange={(x) => setEdit({ ...edit, source: x.target.value })} /></Field>
            <Field label="Tags"><input value={edit.tags} onChange={(x) => setEdit({ ...edit, tags: x.target.value })} /></Field>
          </div>
        </Modal>
      )}
    </div>
  );
}

// a project's Reference tab: link an entry of the organisation's library into the project's Reference area
export function EnterprisePicker({ p, folder, onClose }) {
  const [q, setQ] = useState("");
  const { data } = useApi(`/api/v1/reference-library/pick?q=${encodeURIComponent(q)}`);
  const [err, setErr] = useState("");
  const [done, setDone] = useState([]);
  const list = useMemo(() => data?.entries || [], [data]);
  async function link(e) {
    setErr("");
    try {
      await apiFetch(`/api/v1/projects/${p.id}/links`, { method: "POST", body: JSON.stringify({ title: e.title, url: `#/reference-library/${e.id}`,
        folder, description: `From the enterprise reference library${e.folder ? ` (${e.folder})` : ""}`, kind: "Artifact" }) });
      setDone([...done, e.id]); refreshAll();
    } catch (er) { setErr(er.message); }
  }
  return (
    <Modal title="Link from the enterprise reference library" onClose={onClose} wide actions={<button className="primary" onClick={onClose}>Done</button>}>
      <p className="small quiet">Each entry is linked into this project's Reference area; the link always opens the library's current version.</p>
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the library" aria-label="Search the library" style={{ width: "100%" }} />
      {err && <p className="status bad">{err}</p>}
      {!data ? <p className="quiet">Loading...</p> : !list.length ? <p className="quiet">Nothing found{q ? "" : ": the library is empty"}.</p> : (
        <table className="grid-table small" style={{ marginTop: 8 }}><tbody>{list.map((e) => (
          <tr key={e.id}><td>{e.kind === "link" ? "🔗" : "📄"} <b>{e.title}</b> <span className="quiet">{e.folder}</span></td>
            <td>{(e.tags || []).join(", ")}</td>
            <td className="nowrap">{done.includes(e.id) ? <span className="quiet">linked</span> : <button className="linkish" onClick={() => link(e)}>＋ Link it</button>}</td></tr>
        ))}</tbody></table>
      )}
    </Modal>
  );
}
