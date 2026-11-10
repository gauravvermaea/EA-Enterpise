// Other views and documents (D358 kept simple by D415, D429): a project tab of sample document templates for views and
// documents outside TOGAF and ArchiMate (SWOT, customer journey, value proposition, decision record and the like), in our
// own wording with no branding, to download and use. It does nothing in the project or the metamodel.
// The project's own uploads (D461): anyone on the project uploads files of any type (several at once) with an optional
// title and description, and downloads them; the person who uploaded one, the Project Admin or Lead Architect, or a
// Super Admin replaces it (the earlier file stays as an earlier version) or deletes it.
import { useState } from "react";
import { apiDownload, apiFetch, apiUpload } from "./auth";
import { Field, Modal } from "./ModelOps";
import { refreshAll, useApi } from "./ModelViews";

const ICON = { docx: "W", pptx: "P", xlsx: "X" };

export function fileSize(n) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(n < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

const when = (v) => (v ? new Date(v).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "");

export default function OtherDocsTab({ p }) {
  const { data, error } = useApi("/api/v1/sample-documents");
  const [msg, setMsg] = useState("");
  async function get(t) {
    setMsg("");
    try { await apiDownload(`/api/v1/sample-documents/${t.code}`, `${t.name}.${t.type}`); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <div className="other-docs">
      {p && <ProjectUploads p={p} />}
      <h3>Sample templates</h3>
      <p className="quiet">Sample templates for views and documents outside TOGAF and ArchiMate, in plain wording and without branding.
        Download one, fill it in, and upload it above (or keep it in the repository). Nothing here changes the project or a model.</p>
      {error && <p className="status bad">{error}</p>}
      {msg && <p className="status bad">{msg}</p>}
      {!data && !error && <p>Loading…</p>}
      <div className="wiz-grid">
        {(data?.templates || []).map((t) => (
          <div key={t.code} className="wiz-card other-doc">
            <div className="other-doc-head"><span className={`file-badge ${t.type}`} aria-hidden="true">{ICON[t.type] || "?"}</span>
              <strong>{t.name}</strong> <span className="quiet small">{t.type_name}</span></div>
            <p className="small">{t.purpose}</p>
            <p className="small quiet">{t.when}</p>
            <button onClick={() => get(t)}>Download</button>
          </div>))}
      </div>
    </div>
  );
}

function ProjectUploads({ p }) {
  const base = `/api/v1/projects/${p.id}/other-uploads`;
  const { data, error } = useApi(base);
  const [msg, setMsg] = useState(null);
  const [dlg, setDlg] = useState(null);
  const uploads = data?.uploads || [];
  const canUpload = data?.may_upload && !p.frozen;
  async function act(fn, quiet) {
    setMsg(null);
    try { const r = await fn(); if (!quiet) refreshAll(); if (r?.message) setMsg({ ok: true, text: r.message }); return r || true; }
    catch (e) { setMsg({ ok: false, text: e.message }); return null; }
  }
  const download = (u, v) => act(() => apiDownload(`${base}/${u.id}/download${v ? `?version=${v}` : ""}`, u.file_name), true);
  return (
    <section className="other-uploads">
      <div className="toolbar">
        <h3>Uploaded by the project</h3>
        {canUpload && <button className="primary" onClick={() => setDlg({ k: "upload" })}>⬆ Upload files</button>}
      </div>
      <p className="quiet small">Anything the project wants to keep beside its work: notes, spreadsheets, slides, pictures. Anyone on the
        project can upload and download; whoever uploaded a file (or the Project Admin, the Lead Architect or a Super Admin) can replace
        or delete it. They are not deliverables: no sign-off, and they do not appear in the repository.</p>
      {error && <p className="status bad">{error}</p>}
      {msg && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      {data && !uploads.length && <p className="quiet">Nothing uploaded yet{canUpload ? ": use Upload files to add the first." : "."}</p>}
      {uploads.length > 0 && (
        <table className="grid-table other-uploads-table">
          <thead><tr><th>Name</th><th>Type</th><th>Size</th><th>Uploaded</th><th>Versions</th><th aria-label="Actions" /></tr></thead>
          <tbody>
            {uploads.map((u) => (
              <tr key={u.id}>
                <td><button className="linkish" onClick={() => download(u)} title={`Download ${u.file_name}`}>{u.title || u.file_name}</button>
                  {u.title && <div className="quiet small">{u.file_name}</div>}
                  {u.description && <div className="small">{u.description}</div>}</td>
                <td><span className="upload-type">{u.type.toUpperCase().slice(0, 4)}</span></td>
                <td className="nowrap">{fileSize(u.file_size)}</td>
                <td className="small nowrap">{u.created_by}<div className="quiet">{when(u.created_at)}</div>
                  {u.versions > 1 && <div className="quiet">replaced by {u.modified_by}, {when(u.modified_at)}</div>}</td>
                <td>{u.versions > 1 ? <button className="linkish" onClick={() => setDlg({ k: "versions", u })}>{u.versions} versions</button> : "1"}</td>
                <td className="nowrap">
                  <button onClick={() => download(u)}>⬇ Download</button>
                  {u.may_change && canUpload && <>
                    {" "}<button onClick={() => setDlg({ k: "replace", u })}>Replace…</button>
                    {" "}<button onClick={() => setDlg({ k: "edit", u })}>Edit…</button>
                    {" "}<button className="danger" onClick={() => setDlg({ k: "delete", u })}>Delete</button></>}
                </td>
              </tr>))}
          </tbody>
        </table>)}
      {dlg?.k === "upload" && <UploadDialog base={base} max={data} onClose={() => setDlg(null)} act={act} />}
      {dlg?.k === "replace" && <ReplaceDialog base={base} u={dlg.u} max={data} onClose={() => setDlg(null)} act={act} />}
      {dlg?.k === "edit" && <EditDialog base={base} u={dlg.u} onClose={() => setDlg(null)} act={act} />}
      {dlg?.k === "versions" && <VersionsDialog base={base} u={dlg.u} onClose={() => setDlg(null)} download={download} />}
      {dlg?.k === "delete" && (
        <Modal title={`Delete ${dlg.u.title || dlg.u.file_name}?`} onClose={() => setDlg(null)}
          actions={<><button onClick={() => setDlg(null)}>Cancel</button>
            <button className="danger" onClick={async () => { if (await act(() => apiFetch(`${base}/${dlg.u.id}`, { method: "DELETE" }))) setDlg(null); }}>Delete</button></>}>
          <p>It goes from the project's list with all its versions.</p>
        </Modal>)}
    </section>
  );
}

function tooBig(files, max) {
  const limit = max?.max_bytes || 50 * 1024 * 1024;
  const big = [...files].filter((f) => f.size > limit).map((f) => f.name);
  return big.length ? `${big.join(", ")} ${big.length === 1 ? "is" : "are"} larger than ${fileSize(limit)}.` : "";
}

function UploadDialog({ base, max, onClose, act }) {
  const [files, setFiles] = useState([]);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const limit = max?.max_files || 20;
  const problem = tooBig(files, max) || (files.length > limit ? `Upload at most ${limit} files at once.` : "");
  async function go() {
    const fd = new FormData();
    files.forEach((f) => fd.append("file", f));
    fd.append("title", title); fd.append("description", desc);
    setBusy(true);
    const r = await act(() => apiUpload(base, fd));
    setBusy(false);
    if (r) onClose();
  }
  return (
    <Modal title="Upload files" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={!files.length || !!problem || busy} onClick={go}>{busy ? "Uploading…" : files.length > 1 ? `Upload ${files.length} files` : "Upload"}</button></>}>
      <div className="drop-zone" onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); setFiles([...e.dataTransfer.files]); }}>
        <input type="file" multiple onChange={(e) => setFiles([...e.target.files])} />
        <p className="quiet small">Any type of file, up to {fileSize(max?.max_bytes || 50 * 1024 * 1024)} each; several at once. Or drop them here.</p>
      </div>
      {files.length > 0 && <ul className="small">{files.map((f) => <li key={f.name}>{f.name} <span className="quiet">({fileSize(f.size)})</span></li>)}</ul>}
      {problem && <p className="status bad">{problem}</p>}
      <Field label="Title" hint={files.length > 1 ? "optional, given to each file" : "optional"}><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What it is" /></Field>
      <Field label="Description" hint="optional"><textarea rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Where it came from, a version, who to ask" /></Field>
    </Modal>
  );
}

function ReplaceDialog({ base, u, max, onClose, act }) {
  const [file, setFile] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const problem = file ? tooBig([file], max) : "";
  async function go() {
    const fd = new FormData(); fd.append("file", file); fd.append("note", note);
    setBusy(true);
    const r = await act(() => apiUpload(`${base}/${u.id}/replace`, fd));
    setBusy(false);
    if (r) onClose();
  }
  return (
    <Modal title={`Replace ${u.title || u.file_name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={!file || !!problem || busy} onClick={go}>{busy ? "Uploading…" : "Replace"}</button></>}>
      <p className="small">The new file becomes version {u.versions + 1}; version {u.versions} stays, downloadable as an earlier version.</p>
      <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} />
      {problem && <p className="status bad">{problem}</p>}
      <Field label="What changed" hint="optional"><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="October figures added" /></Field>
    </Modal>
  );
}

function EditDialog({ base, u, onClose, act }) {
  const [title, setTitle] = useState(u.title || "");
  const [desc, setDesc] = useState(u.description || "");
  async function go() {
    const r = await act(() => apiFetch(`${base}/${u.id}`, { method: "PUT", body: JSON.stringify({ title, description: desc }) }));
    if (r) onClose();
  }
  return (
    <Modal title={`Edit ${u.file_name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={go}>Save</button></>}>
      <Field label="Title"><input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
      <Field label="Description"><textarea rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
    </Modal>
  );
}

function VersionsDialog({ base, u, onClose, download }) {
  const { data, error } = useApi(`${base}/${u.id}/versions`);
  return (
    <Modal wide title={`Versions of ${u.title || u.file_name}`} onClose={onClose} actions={<button onClick={onClose}>Close</button>}>
      {error && <p className="status bad">{error}</p>}
      {!data && !error && <p>Loading…</p>}
      <table className="grid-table small">
        <thead><tr><th>Version</th><th>By</th><th>When</th><th>Note</th><th aria-label="Download" /></tr></thead>
        <tbody>{(data?.versions || []).map((v) => (
          <tr key={v.version}><td className="nowrap">{v.version}{v.version === u.versions ? " (current)" : ""}</td><td>{v.by_user}</td><td className="nowrap">{when(v.at)}</td>
            <td className="small">{v.note}</td>
            <td className="nowrap"><button onClick={() => download(u, v.version === u.versions ? null : v.version)}>⬇ Download</button></td></tr>))}</tbody>
      </table>
    </Modal>
  );
}
