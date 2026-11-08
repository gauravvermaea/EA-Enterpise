// Links and the Reference area of a project's repository (owner, 8 Nov 2026, D296). A link has no file: an external web
// address, or another project's document or document class (shown as it is there now). The Reference area is TOGAF's
// Reference Library (05_Reference_Library), opened up: folders of any shape, documents and links, added by anyone on the project.
import { EnterprisePicker } from "./ReferenceLibrary";
import { useEffect, useMemo, useState } from "react";
import { apiDownload, apiFetch, apiUpload } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Field, Modal } from "./ModelOps";

export const REFERENCE = "05_Reference_Library";
const rel = (path) => (path === REFERENCE ? "" : path.replace(`${REFERENCE}/`, ""));

// a link's name: opens the web address in a new tab, or the other project's document class or document
export function LinkName({ d }) {
  const t = d.link_target;
  const href = d.link_url || (t?.visible ? t.open : "");
  const external = /^https?:/i.test(href);
  return (
    <span className="link-name">
      {href ? <a href={href} target={external ? "_blank" : undefined} rel={external ? "noopener noreferrer" : undefined}
        title={d.description || href}>🔗 {d.title || d.file_name}</a> : <span title="You cannot see the project it points to">🔗 {d.title || d.file_name}</span>}
      {t && (t.visible ? <span className="small quiet"> → {t.project_name}{t.name ? `: ${t.name}` : ""}{t.state ? ` (${t.state}${t.version ? `, v${t.version}` : ""})` : ""}</span>
        : <span className="small quiet"> → another project you cannot see</span>)}
      {d.description && <div className="small quiet">{d.description}</div>}
    </span>
  );
}

// add or change a link: a web address and/or another project's document or document class
export function LinkDialog({ p, d = null, item = null, folder = null, onClose }) {
  const [title, setTitle] = useState(d?.file_name || "");
  const [url, setUrl] = useState(d?.link_url || "");
  const [desc, setDesc] = useState(d?.description || "");
  const [kind, setKind] = useState(d?.kind || "Artifact");
  const [lp, setLp] = useState(d?.link_project || "");
  const [target, setTarget] = useState(d?.link_document ? `d:${d.link_document}` : d?.link_item ? `i:${d.link_item}` : "");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: plist } = useApi("/api/v1/projects");
  const { data: other } = useApi(lp ? `/api/v1/projects/${lp}` : null);
  const projects = (plist?.projects || []).filter((x) => x.id !== p.id);
  async function save() {
    setBusy(true); setErr("");
    const body = { title, url, description: desc, kind, link_project: lp || null,
      link_document: target.startsWith("d:") ? target.slice(2) : null, link_item: target.startsWith("i:") ? target.slice(2) : null,
      ...(d ? {} : item ? { item } : { folder: folder || REFERENCE }) };
    try {
      const out = await apiFetch(d ? `/api/v1/projects/${p.id}/links/${d.id}` : `/api/v1/projects/${p.id}/links`,
        { method: d ? "PUT" : "POST", body: JSON.stringify(body) });
      refreshAll(); onClose(out.message);
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={d ? `Change the link ${d.file_name}` : "Add a link"} onClose={() => onClose()}
      actions={<><button onClick={() => onClose()}>Cancel</button>
        <button className="primary" disabled={busy || !title.trim() || (!url.trim() && !lp)} onClick={save}>{busy ? "Saving…" : d ? "Save" : "Add the link"}</button></>}>
      <div className="ed-form">
        <p className="small quiet">A link has no file here: it points to a web page, or to another project's document or document class (shown as it is there now).
          It can still be tagged, marked a deliverable, accepted or sent for sign-off.</p>
        <Field label="Title"><input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus placeholder="e.g. Architecture Board minutes, 4 Nov 2026" /></Field>
        <Field label="Web address" hint="(https://…; leave empty for a project link only)"><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" /></Field>
        <Field label="Or another project">
          <select value={lp} onChange={(e) => { setLp(e.target.value); setTarget(""); }}><option value="">–</option>
            {projects.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        {lp && <Field label="Its document or document class" hint="(empty: the project itself)">
          <select value={target} onChange={(e) => setTarget(e.target.value)}><option value="">The project</option>
            {(other?.items || []).filter((i) => i.chosen).map((i) => (
              <optgroup key={i.id} label={`${i.phase} · ${i.name}`}>
                <option value={`i:${i.id}`}>The class: {i.name}</option>
                {(other?.documents || []).filter((x) => x.item_id === i.id).map((x) => <option key={x.id} value={`d:${x.id}`}>{x.file_name}</option>)}
              </optgroup>
            ))}
          </select></Field>}
        <Field label="What it is" hint="(optional)"><textarea rows={2} value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
        {!d && <Field label="Kind"><select value={kind} onChange={(e) => setKind(e.target.value)}><option>Artifact</option><option>Deliverable</option></select></Field>}
        {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- the project's Reference tab
export function ReferenceTab({ p }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/reference`);
  const [sel, setSel] = useState(REFERENCE);
  const [dlg, setDlg] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const can = data.may_edit && !p.frozen;
  const here = data.documents.filter((d) => d.folder === sel);
  const below = (f) => data.documents.filter((d) => d.folder === f || d.folder.startsWith(`${f}/`)).length;
  async function act(fn) {
    setMsg(""); setBusy(true);
    try { const r = await fn(); if (r?.message) setMsg(r.message); refreshAll(); } catch (e) { setMsg(e.message); }
    setBusy(false);
  }
  function upload() {
    const inp = document.createElement("input");
    inp.type = "file"; inp.multiple = true;
    inp.onchange = () => act(async () => {
      const failed = [];
      for (const f of inp.files) {
        const fd = new FormData(); fd.append("file", f); fd.append("folder", sel);
        try { await apiUpload(`/api/v1/projects/${p.id}/reference`, fd); } catch (e) { failed.push(`${f.name}: ${e.message}`); }
      }
      return { message: failed.length ? `Not added: ${failed.join("; ")}` : `${inp.files.length} file${inp.files.length === 1 ? "" : "s"} added to ${rel(sel) || "Reference"}.` };
    });
    inp.click();
  }
  function newFolder() {
    // eslint-disable-next-line no-alert
    const name = window.prompt(`A new folder in ${rel(sel) || "Reference"}`, "");
    if (name && name.trim()) act(() => apiFetch(`/api/v1/projects/${p.id}/reference/folders`, { method: "POST", body: JSON.stringify({ path: `${sel}/${name.trim()}` }) }))
      .then(() => setSel(`${sel}/${name.trim()}`));
  }
  const depth = (f) => (f === REFERENCE ? 0 : rel(f).split("/").length);
  return (
    <div>
      <p className="quiet">Reference material: anything anyone on the project wants to keep to hand (reference models, regulations, patterns, standards,
        earlier work, useful web pages). It is TOGAF's Reference Library, folder {REFERENCE} in Documents; make folders as you like.
        {data.is_library && " This is a library project: its reference material is offered to new projects."}</p>
      {msg && <p className="small status">{msg}</p>}
      <div className="tabs sub" role="tablist">
        <button className="tab on" role="tab" aria-selected="true">This project's reference</button>
        <a className="tab" href="#/reference-library" title="The organisation's reference library, for everyone">📚 Enterprise reference library ↗</a>
      </div>
      <div className="ref-layout">
        <nav className="ref-tree" aria-label="Reference folders">
          {data.folders.map((f) => (
            <button key={f} className={`linkish ref-folder${sel === f ? " on" : ""}`} style={{ paddingLeft: 6 + 14 * depth(f) }} onClick={() => setSel(f)}>
              📁 {f === REFERENCE ? "Reference" : f.split("/").pop().replace(/^\d+_/, "").replaceAll("_", " ")} <span className="small quiet">{below(f) || ""}</span></button>
          ))}
        </nav>
        <div className="ref-main">
          <div className="row-gap">
            <b>{rel(sel) || "Reference"}</b>
            {can && <><button disabled={busy} onClick={upload}>⬆ Add files</button>
              <button disabled={busy} onClick={() => setDlg({ k: "link" })}>🔗 Add a link</button>
              <button disabled={busy} onClick={() => setDlg({ k: "enterprise" })} title="Link an entry of the organisation's reference library">📚 From the enterprise library</button>
              <button disabled={busy} onClick={newFolder}>＋ Folder</button>
              {sel !== REFERENCE && !below(sel) && <button className="linkish" disabled={busy}
                onClick={() => act(() => apiFetch(`/api/v1/projects/${p.id}/reference/folders`, { method: "POST", body: JSON.stringify({ path: sel, delete: true }) })).then(() => setSel(REFERENCE))}>Take the folder away</button>}</>}
          </div>
          {!here.length ? <p className="quiet small">Nothing in this folder yet.</p> : (
            <table className="grid-table">
              <thead><tr><th>Name</th><th>Added by</th><th /></tr></thead>
              <tbody>
                {here.map((d) => (
                  <tr key={d.id}>
                    <td>{d.is_link ? <LinkName d={d} /> : <button className="linkish" onClick={() => apiDownload(`/api/v1/projects/${p.id}/documents/${d.id}`, d.file_name).catch((e) => setMsg(e.message))}>
                      📄 {d.file_name}</button>}{!d.is_link && !d.stored && <span className="small quiet"> (being copied)</span>}</td>
                    <td className="small">{d.created_by}</td>
                    <td className="small nowrap">{can && <>
                      {d.is_link && <button className="linkish" onClick={() => setDlg({ k: "link", d })}>Change</button>}
                      {" "}<button className="linkish bad-text" onClick={() => {
                        // eslint-disable-next-line no-alert
                        if (window.confirm(`Delete ${d.file_name}? It can be restored from the repository with "Show deleted documents".`)) act(() => apiFetch(`/api/v1/projects/${p.id}/documents/${d.id}/delete`, { method: "POST", body: "{}" }));
                      }}>Delete</button></>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      {dlg?.k === "link" && <LinkDialog p={p} d={dlg.d} folder={sel} onClose={(m) => { setDlg(null); if (m) setMsg(m); }} />}
      {dlg?.k === "enterprise" && <EnterprisePicker p={p} folder={sel} onClose={() => setDlg(null)} />}
    </div>
  );
}

// ---------------------------------------------------------------- the wizard's step: reference material to copy into the new project
export function ReferenceStep({ d, set, edit }) {
  const q = new URLSearchParams();
  if (d.parent) q.set("parent", d.parent);
  if (d.template) q.set("template", d.template);
  const { data, error } = useApi(edit ? null : `/api/v1/projects/reference-sources?${q}`);
  const list = useMemo(() => data?.reference || [], [data]);
  useEffect(() => {      // everything offered is ticked to start with; the person unticks what they do not want
    if (data && d.reference === undefined) set("reference", list.map((x) => x.doc));
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  if (edit) return <p className="quiet">The project's reference material is on its <b>Reference</b> tab: add documents, links and folders there at any time.</p>;
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const picked = new Set(d.reference || []);
  const toggle = (k) => set("reference", picked.has(k) ? [...picked].filter((x) => x !== k) : [...picked, k]);
  const groups = [["parent", "From the project it starts from"], ["template", "From the kind of project"], ["library", "From library projects"]];
  return (
    <div>
      <p className="quiet">Reference material to start with: tick what to copy into the new project's Reference area (TOGAF's Reference Library). Files are
        copied once its repository is built; links at once. More can be added on its Reference tab at any time.</p>
      {!list.length && <p className="quiet small">Nothing is offered: no library project has reference material{d.parent ? ", nor the project it starts from" : ""}.</p>}
      {groups.map(([k, label]) => {
        const rows = list.filter((x) => x.source === k);
        if (!rows.length) return null;
        return (
          <div key={k}>
            <h4>{label}</h4>
            <div className="row-gap small"><button className="linkish" onClick={() => set("reference", [...new Set([...picked, ...rows.map((x) => x.doc)])])}>Tick all</button>
              <button className="linkish" onClick={() => set("reference", [...picked].filter((x) => !rows.some((r) => r.doc === x)))}>Untick all</button></div>
            {rows.map((x) => (
              <label key={x.doc} className="ref-pick">
                <input type="checkbox" checked={picked.has(x.doc)} onChange={() => toggle(x.doc)} />
                {x.kind === "link" ? "🔗" : "📄"} <b>{x.title}</b> <span className="small quiet">{x.from}{x.folder ? ` · ${x.folder.replaceAll("_", " ")}` : ""}</span>
                {x.description && <span className="small quiet"> · {x.description}</span>}
              </label>
            ))}
          </div>
        );
      })}
    </div>
  );
}
