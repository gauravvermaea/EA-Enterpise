// The enterprise library and the project libraries (owner, 9 Nov 2026, phase 15.2, D346 to D350), served by the library
// service (/api/library/v1). Kept simple: a folder tree of pages (headings, text, lists, tables, links), links and the
// occasional file; one search box; changes show at once, every change is kept and can be undone.
//   #/enterprise-library[/<library>[/<entry>]]     the enterprise library, and the project libraries shown in it
//   #/projects/<p>/library[/<entry>]               a project's library (its Library tab)
// (#/library is the model library: a different thing.)
import { Fragment, useEffect, useState } from "react";
import { apiDownload, apiFetch, apiUpload, libraryInfo } from "./auth";
import { openFile } from "./drawioScratch";
import { refreshAll, useApi } from "./ModelViews";
import { Field, Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";
import { liveModels, liveProjects } from "./ModelMarks";
import { eaHref } from "./Links";

export { eaHref };

const L = "/api/library/v1";
const size = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n > 1024 ? `${Math.round(n / 1024)} kB` : `${n || 0} B`);
const ICON = { page: "📝", link: "🔗", file: "📄" };

// ---------------------------------------------------------------- links inside EA Explorer (ea:...)

function Link({ label, href }) {
  if (/^ea:document:/.test(href)) {
    const [p, d] = href.slice(12).split(":");
    return <button className="linkish lib-a" title="Download the document"
      onClick={() => openFile(`/api/v1/projects/${p}/documents/${d}`, label).catch((e) => window.alert(e.message))}>📄 {label}</button>;
  }
  const inside = eaHref(href);
  if (inside) return <a className="lib-a" href={inside}>{label}</a>;
  return <a className="lib-a" href={href} target="_blank" rel="noreferrer">{label} ↗</a>;
}

// text with [label](href) links in it
function Inline({ text }) {
  const out = [];
  const re = /\[([^\]\n]+)\]\(([^)\s]+)\)/g;
  let at = 0;
  let m;
  while ((m = re.exec(text || ""))) {
    if (m.index > at) out.push(text.slice(at, m.index));
    out.push(<Link key={m.index} label={m[1]} href={m[2]} />);
    at = m.index + m[0].length;
  }
  if (at < (text || "").length) out.push(text.slice(at));
  return <>{out.map((x, i) => (typeof x === "string" ? <Fragment key={`t${i}`}>{x}</Fragment> : x))}</>;
}

export function PageBody({ blocks }) {
  if (!blocks?.length) return <p className="quiet">This page is empty.</p>;
  return (
    <div className="lib-page">
      {blocks.map((b, i) => {
        if (b.type === "heading") return <h3 key={i}><Inline text={b.text} /></h3>;
        if (b.type === "text") return b.text.split(/\n{2,}/).map((para, j) => <p key={`${i}-${j}`}><Inline text={para} /></p>);
        if (b.type === "list") return <ul key={i}>{b.items.map((x, j) => <li key={j}><Inline text={x} /></li>)}</ul>;
        if (b.type === "links") return <ul key={i} className="lib-links">{b.items.map((x, j) => <li key={j}><Link label={x.label} href={x.href} /></li>)}</ul>;
        if (b.type === "table") {
          const [head, ...rest] = b.header ? b.rows : [null, ...b.rows];
          return (
            <table key={i} className="grid-table lib-table">
              {head && <thead><tr>{head.map((c, j) => <th key={j}><Inline text={c} /></th>)}</tr></thead>}
              <tbody>{rest.map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j}><Inline text={c} /></td>)}</tr>)}</tbody>
            </table>
          );
        }
        return null;
      })}
    </div>
  );
}

// ---------------------------------------------------------------- the enterprise library page
export default function EnterpriseLibraryPage({ route }) {
  const info = libraryInfo();
  const [lib, entry] = route.replace(/^#\/enterprise-library\/?/, "").split("?")[0].split("/").filter(Boolean);
  if (!info.service) return <section className="page"><h1>Enterprise library</h1><p className="status bad">The library service is switched off (System admin › Services).</p></section>;
  if (info.mode === "off" && !lib) return <section className="page"><h1>Enterprise library</h1>
    <p className="quiet">The organisation does not use an enterprise library (System settings › Enterprise library). Each project keeps its own on its Library tab.</p></section>;
  if (info.mode === "link" && !lib) return <section className="page"><ExternalLibrary info={info} /></section>;
  return <section className="page"><OrgLibrary libId={lib} entry={entry} /></section>;
}
// the heading of the library while it loads or cannot be reached, so the page still says what it is (R2.0.1)
const LibHead = () => <h1>Enterprise library</h1>;

function ExternalLibrary({ info }) {
  const [q, setQ] = useState("");
  return (
    <div className="lib-external">
      <h1>Enterprise library</h1>
      <p>The organisation keeps its library in its own system.</p>
      <p><a className="button primary" href={info.link} target="_blank" rel="noreferrer">Open the organisation's library ↗</a></p>
      {info.search_link && (
        <form className="row-gap" onSubmit={(e) => { e.preventDefault(); if (q.trim()) window.open(info.search_link.replace("{q}", encodeURIComponent(q.trim())), "_blank", "noopener"); }}>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the organisation's library" aria-label="Search" style={{ minWidth: 320 }} />
          <button type="submit">Search ↗</button>
        </form>
      )}
      <p className="small quiet">Each project keeps its own library on its Library tab.</p>
    </div>
  );
}

function OrgLibrary({ libId, entry }) {
  const { data: org, error } = useApi(`${L}/libraries/org`);
  const other = org && libId && libId !== org.id ? libId : null;
  const { data: shownLib, error: shownErr } = useApi(other ? `${L}/libraries/${other}` : null);
  if (error) return <><LibHead /><LibraryDown error={error} /></>;
  if (!org) return <><LibHead /><p className="quiet">Loading…</p></>;
  if (other && shownErr) return <p className="status bad">{shownErr} <a href="#/enterprise-library">The enterprise library</a></p>;
  if (other && !shownLib) return <p className="quiet">Loading…</p>;
  const pub = org.published || [];
  const shown = other ? { ...shownLib, id: other, project_name: shownLib.name } : null;
  return (
    <div>
      <h1>{shown ? shown.project_name : "Enterprise library"}</h1>
      {shown ? <p className="small"><a href="#/enterprise-library">Enterprise library</a> › a project's library, shown here by its project (read only).
        {" "}<a href={`#/projects/${shown.project}/library`}>Open it in the project</a></p>
        : <p className="quiet">Our standards, ways of working, reference models and useful links, with the project libraries their projects share. Anyone can add
          and change things here; every change is kept{org.may.admin ? " and you can undo it from Recent changes" : " and Library Admins can undo it"}.</p>}
      <LibraryView lib={shown || org} base={`#/enterprise-library/${shown ? shown.id : org.id}`}
        entry={entry} searchScope="org" side={!shown && pub.length > 0 && (
          <div className="lib-published">
            <h4>Project libraries</h4>
            {pub.map((x) => <a key={x.id} className="lib-folder" href={`#/enterprise-library/${x.id}`}>📚 {x.project_name} <span className="small quiet">{x.entries}</span></a>)}
          </div>
        )} />
    </div>
  );
}

function LibraryDown({ error }) {
  return <div className="status bad">The library is not answering ({error}). It is a service of its own: <code>eax logs library</code> says why.</div>;
}

// ---------------------------------------------------------------- a project's Library tab
export function ProjectLibraryTab({ p, entry }) {
  const info = libraryInfo();
  const { data: lib, error } = useApi(info.service ? `${L}/libraries/project/${p.id}` : null);
  const [settings, setSettings] = useState(false);
  if (!info.service) return <p className="status bad">The library service is switched off (System admin › Services).</p>;
  if (error) return <LibraryDown error={error} />;
  if (!lib) return <p className="quiet">Loading…</p>;
  const head = (
    <div className="row-gap lib-head">
      <span className="small quiet">The project's library: pages, links and the odd file{lib.in_enterprise ? "; shown in the enterprise library (read only there)" : ""}.</span>
      {lib.in_enterprise && <span className="chip on">in the enterprise library</span>}
      {lib.may.admin && <button className="push-right" onClick={() => setSettings(true)}>⚙ Library settings</button>}
    </div>
  );
  return (
    <div>
      {head}
      {lib.external_link ? (
        <div className="lib-external">
          <p>This project keeps its library somewhere else.</p>
          <p><a className="button primary" href={lib.external_link} target="_blank" rel="noreferrer">Open the project's library ↗</a></p>
          <p className="small quiet">{lib.external_link}</p>
        </div>
      ) : <LibraryView lib={lib} base={`#/projects/${p.id}/library`} entry={entry} searchScope={lib.id} />}
      {settings && <ProjectSettings p={p} lib={lib} onClose={() => setSettings(false)} />}
    </div>
  );
}

function ProjectSettings({ p, lib, onClose }) {
  const [f, setF] = useState({ in_enterprise: lib.in_enterprise, own: !!lib.external_link, external_link: lib.external_link || "" });
  const [err, setErr] = useState("");
  const mode = libraryInfo().mode;
  async function save() {
    try {
      await apiFetch(`${L}/libraries/project/${p.id}`, { method: "PUT", body: JSON.stringify({ in_enterprise: f.in_enterprise, external_link: f.own ? f.external_link.trim() : "" }) });
      refreshAll(); onClose();
    } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title="Library settings" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={save} disabled={f.own && !f.external_link.trim()}>Save</button></>}>
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        <label className="small"><input type="checkbox" checked={f.in_enterprise} disabled={mode !== "ours"} onChange={(e) => setF({ ...f, in_enterprise: e.target.checked })} />
          {" "}Show this library in the enterprise library (everyone can read it there; only the project changes it)</label>
        {mode !== "ours" && <p className="small quiet">The organisation uses {mode === "link" ? "its own library elsewhere" : "no enterprise library"}, so it cannot be shown there.</p>}
        <label className="small"><input type="radio" checked={!f.own} onChange={() => setF({ ...f, own: false })} /> Keep the library here, in EA Explorer</label>
        <label className="small"><input type="radio" checked={f.own} onChange={() => setF({ ...f, own: true })} /> The project keeps its library somewhere else: the Library tab opens it</label>
        {f.own && <Field label="Its address"><input type="url" value={f.external_link} placeholder="https://" onChange={(e) => setF({ ...f, external_link: e.target.value })} /></Field>}
        {f.own && <p className="small quiet">What is in the library here is kept, and comes back if you switch back.</p>}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- one library: tree, listing, search, a page
function buildTree(folders) {
  const kids = {};
  for (const f of folders) (kids[f.parent || ""] ||= []).push(f);
  for (const k of Object.keys(kids)) kids[k].sort((a, b) => a.name.localeCompare(b.name));
  return kids;
}

function LibraryView({ lib, base, entry, searchScope, side }) {
  const [folder, setFolder] = useState(null);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [dlg, setDlg] = useState(null);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const { data: listing, error } = useApi(entry ? null : `${L}/libraries/${lib.id}/entries${folder ? `?folder=${folder}` : ""}`);
  const { data: found } = useApi(query ? `${L}/search?q=${encodeURIComponent(query)}&library=${searchScope}` : null);
  const may = lib.may || {};
  const folders = lib.folders || [];
  const kids = buildTree(folders);
  async function act(fn) {
    try { const r = await fn(); setMsg({ ok: true, text: r?.message || "Done." }); refreshAll(); return r; } catch (e) { setMsg({ ok: false, text: e.message }); return null; }
  }
  const open = (id) => { window.location.hash = `${base}/${id}`; };
  function Tree({ parent, depth }) {
    return (kids[parent || ""] || []).map((f) => (
      <Fragment key={f.id}>
        <button className={`linkish lib-folder${folder === f.id && !entry ? " on" : ""}`} style={{ paddingLeft: 6 + 14 * depth }}
          onClick={() => { setFolder(f.id); setQuery(""); if (entry) window.location.hash = base; }}>📁 {f.name} <span className="small quiet">{f.entries || ""}</span></button>
        <Tree parent={f.id} depth={depth + 1} />
      </Fragment>
    ));
  }
  return (
    <div>
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <form className="row-gap filters" onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); if (entry) window.location.hash = base; }}>
        <input type="search" value={q} onChange={(e) => { setQ(e.target.value); if (!e.target.value) setQuery(""); }} aria-label="Search the library"
          placeholder={searchScope === "org" ? "Search the enterprise library and the project libraries in it" : "Search this library"} style={{ minWidth: 340 }} />
        <button type="submit">Search</button>
        <span className="push-right row-gap">
          {may.write && <>
            <button type="button" className="primary" onClick={() => setDlg({ k: "page" })}>＋ Page</button>
            <button type="button" onClick={() => setDlg({ k: "link" })}>🔗 Link</button>
            <button type="button" onClick={() => setDlg({ k: "file" })}>⬆ File</button>
            <button type="button" onClick={() => setDlg({ k: "folder" })}>＋ Folder</button>
          </>}
          <button type="button" onClick={() => setDlg({ k: "history" })}>🕘 Recent changes</button>
        </span>
      </form>
      <div className="ref-layout">
        <nav className="ref-tree" aria-label="Folders">
          <button className={`linkish lib-folder${!folder && !entry && !query ? " on" : ""}`} onClick={() => { setFolder(null); setQuery(""); if (entry) window.location.hash = base; }}>
            📚 {lib.name || "Library"}</button>
          <Tree parent={null} depth={1} />
          {may.write && folder && !entry && <div className="small" style={{ marginTop: 8 }}>
            <button className="linkish" onClick={() => setDlg({ k: "folder", f: folders.find((x) => x.id === folder) })}>Rename or move this folder</button><br />
            <button className="linkish bad-text" onClick={() => window.confirm("Remove this folder and everything in it? (It can be undone from Recent changes.)")
              && act(() => apiFetch(`${L}/libraries/${lib.id}/folders/${folder}`, { method: "DELETE" })).then((r) => r && setFolder(null))}>Remove this folder</button>
          </div>}
          {side}
        </nav>
        <div>
          {query ? <SearchResults found={found} lib={lib} base={base} searchScope={searchScope} />
            : entry ? <EntryView lib={lib} id={entry} base={base} folders={folders} onMsg={setMsg} />
            : error ? <LibraryDown error={error} />
            : !listing ? <p className="quiet">Loading…</p>
            : <Listing listing={listing} lib={lib} open={open} setFolder={setFolder} act={act} />}
        </div>
      </div>
      {dlg?.k === "history" && <History lib={lib} onClose={() => setDlg(null)} />}
      {dlg?.k === "folder" && <FolderDialog lib={lib} folder={dlg.f} parent={folder} folders={folders} onClose={(m) => { setDlg(null); if (m) setMsg({ ok: true, text: m }); }} />}
      {["page", "link", "file"].includes(dlg?.k) && <AddDialog k={dlg.k} lib={lib} folder={folder} onClose={(r) => { setDlg(null); if (r) { setMsg({ ok: true, text: r.message }); if (dlg.k === "page") window.location.hash = `${base}/${r.id}?edit=1`; } }} />}
    </div>
  );
}

function Crumbs({ path, setFolder }) {
  return (
    <p className="small lib-crumbs">
      <button className="linkish" onClick={() => setFolder(null)}>Top</button>
      {path.map((f) => <span key={f.id}> › <button className="linkish" onClick={() => setFolder(f.id)}>{f.name}</button></span>)}
    </p>
  );
}

function Listing({ listing, lib, open, setFolder, act }) {
  return (
    <div>
      <Crumbs path={listing.path} setFolder={setFolder} />
      {!listing.entries.length ? <p className="quiet">Nothing here yet.{lib.may?.write ? " Add a page, a link or a file." : ""}</p> : (
        <table className="grid-table">
          <thead><tr><th>Title</th><th>Tags</th><th>Changed</th><th /></tr></thead>
          <tbody>{listing.entries.map((e) => (
            <tr key={e.id}>
              <td>{ICON[e.kind]} <button className="linkish" onClick={() => open(e.id)}><b>{e.title}</b></button>
                {e.kind === "file" && <span className="small quiet"> {e.file_name} · {size(e.file_size)}</span>}
                {e.description && <div className="small quiet">{e.description.slice(0, 160)}</div>}</td>
              <td>{(e.tags || []).map((t) => <span key={t} className="tag-chip">{t}</span>)}</td>
              <td className="small nowrap">{e.changed_by} · {fmtDateTime(e.changed_at)}</td>
              <td className="small nowrap">{e.kind === "link" ? <Link label="Open" href={e.href} />
                : e.kind === "file" ? <button className="linkish" onClick={() => act(() => apiDownload(`${L}/libraries/${lib.id}/entries/${e.id}/file`, e.file_name))}>⬇ Download</button>
                : <button className="linkish" onClick={() => open(e.id)}>Read</button>}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}

function SearchResults({ found, lib, base, searchScope }) {
  if (!found) return <p className="quiet">Searching…</p>;
  const href = (r) => (r.library === lib.id ? `${base}/${r.id}` : `#/enterprise-library/${r.library}/${r.id}`);
  const groups = {};
  for (const r of found.results) (groups[r.library_name] ||= []).push(r);
  const mark = (s) => (s || "").split(/(<<|>>)/).reduce((acc, part, i, all) => {
    if (part === "<<" || part === ">>") return acc;
    acc.push(all[i - 1] === "<<" ? <mark key={i}>{part}</mark> : <Fragment key={i}>{part}</Fragment>);
    return acc;
  }, []);
  return (
    <div className="lib-results">
      <p className="small quiet">{found.results.length} found for “{found.q}”{searchScope === "org" ? " in the enterprise library and the project libraries in it" : ""}.</p>
      {found.folders.length > 0 && <p className="small">Folders: {found.folders.map((f) => <span key={f.id} className="chip">📁 {f.name}{searchScope === "org" ? ` (${f.library_name})` : ""}</span>)}</p>}
      {Object.entries(groups).map(([name, rs]) => (
        <section key={name}>
          {searchScope === "org" && <h4>{name}</h4>}
          {rs.map((r) => (
            <div key={r.id} className="lib-hit">
              {ICON[r.kind]} <a href={href(r)}><b>{r.title}</b></a>{r.folder_name && <span className="small quiet"> in {r.folder_name}</span>}
              {r.kind === "link" && <> · <Link label="open" href={r.href} /></>}
              {r.excerpt && <div className="small ref-excerpt">…{mark(r.excerpt)}…</div>}
            </div>
          ))}
        </section>
      ))}
      {!found.results.length && !found.folders.length && <p className="quiet">Nothing matches. Search finds whole words and the start of words in titles, tags, pages and files.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- one entry
function EntryView({ lib, id, base, folders, onMsg }) {
  const { data: e, error } = useApi(`${L}/libraries/${lib.id}/entries/${id}`);
  const [editing, setEditing] = useState(false);
  const [history, setHistory] = useState(false);
  const wantEdit = /[?&]edit=1/.test(window.location.hash);
  useEffect(() => { if (wantEdit && e && lib.may?.write) setEditing(true); }, [wantEdit, e, lib.may?.write]);
  if (error) return <p className="status bad">{error}</p>;
  if (!e) return <p className="quiet">Loading…</p>;
  async function act(fn) {
    try { const r = await fn(); onMsg({ ok: true, text: r?.message || "Done." }); refreshAll(); return r; } catch (x) { onMsg({ ok: false, text: x.message }); return null; }
  }
  if (editing) return <EntryEditor lib={lib} e={e} folders={folders} onDone={(m) => { setEditing(false); if (m) onMsg({ ok: true, text: m }); window.location.hash = `${base}/${id}`; }} />;
  return (
    <article className="lib-entry">
      <p className="small lib-crumbs"><a href={base}>Top</a>{e.path.map((f) => <span key={f.id}> › {f.name}</span>)}</p>
      <div className="row-gap">
        <h2 style={{ margin: 0 }}>{ICON[e.kind]} {e.title}</h2>
        {(e.tags || []).map((t) => <span key={t} className="tag-chip">{t}</span>)}
        <span className="push-right row-gap">
          {lib.may?.write && <button className="primary" disabled={!!e.editing_by && e.kind === "page"} title={e.editing_by ? `${e.editing_by} is editing it` : ""} onClick={() => setEditing(true)}>✎ Edit</button>}
          <button onClick={() => setHistory(true)}>🕘 History</button>
          {lib.may?.write && <button className="bad-text" onClick={() => window.confirm(`Remove ${e.title}? (It can be undone from Recent changes.)`)
            && act(() => apiFetch(`${L}/libraries/${lib.id}/entries/${id}`, { method: "DELETE" })).then((r) => { if (r) window.location.hash = base; })}>Remove</button>}
        </span>
      </div>
      {e.editing_by && <p className="small lock-banner">{e.editing_by} is editing this page.</p>}
      {e.description && <p className="quiet">{e.description}</p>}
      {e.kind === "page" && <PageBody blocks={e.blocks} />}
      {e.kind === "link" && <p><Link label={e.href.startsWith("ea:") ? "Open it in EA Explorer" : e.href} href={e.href} /></p>}
      {e.kind === "file" && <p><button onClick={() => act(() => apiDownload(`${L}/libraries/${lib.id}/entries/${id}/file`, e.file_name))}>⬇ Download {e.file_name}</button>
        <span className="small quiet"> {size(e.file_size)}</span></p>}
      <p className="small quiet">Added by {e.created_by} on {fmtDateTime(e.created_at)}; last changed by {e.changed_by} on {fmtDateTime(e.changed_at)}.</p>
      {history && <History lib={lib} entry={id} onClose={() => setHistory(false)} />}
    </article>
  );
}

function EntryEditor({ lib, e, folders, onDone }) {
  const [f, setF] = useState({ title: e.title, description: e.description || "", tags: (e.tags || []).join(", "), href: e.href || "", folder: e.folder || "",
    blocks: e.blocks?.length ? e.blocks : [{ type: "text", text: "" }] });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const url = `${L}/libraries/${lib.id}/entries/${e.id}`;
  useEffect(() => {
    if (e.kind !== "page") return undefined;
    apiFetch(`${url}/hold`, { method: "POST" }).catch((x) => setErr(x.message));
    return () => { apiFetch(`${url}/hold`, { method: "DELETE" }).catch(() => {}); };
  }, [url, e.kind]);
  async function save() {
    setBusy(true); setErr("");
    try {
      const body = { title: f.title, description: f.description, tags: f.tags, folder: f.folder || null };
      if (e.kind === "page") body.blocks = f.blocks;
      if (e.kind === "link") body.href = f.href;
      const r = await apiFetch(url, { method: "PUT", body: JSON.stringify(body) });
      refreshAll(); onDone(r.message);
    } catch (x) { setErr(x.message); setBusy(false); }
  }
  return (
    <div className="lib-editor">
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        <Field label="Title"><input value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} /></Field>
        <div className="row-gap">
          <Field label="Folder"><select value={f.folder} onChange={(x) => setF({ ...f, folder: x.target.value })}>
            <option value="">(the top)</option>{folders.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
          <Field label="Tags" hint="(commas between)"><input value={f.tags} onChange={(x) => setF({ ...f, tags: x.target.value })} /></Field>
        </div>
        <Field label="Description" hint="(a line, shown in lists and found by search)"><input value={f.description} onChange={(x) => setF({ ...f, description: x.target.value })} /></Field>
        {e.kind === "link" && <Field label="Goes to"><LinkInput value={f.href} onChange={(v) => setF({ ...f, href: v })} lib={lib} /></Field>}
      </div>
      {e.kind === "page" && <BlocksEditor blocks={f.blocks} onChange={(blocks) => setF({ ...f, blocks })} lib={lib} />}
      <div className="row-gap" style={{ marginTop: 12 }}>
        <button className="primary" disabled={busy || !f.title.trim()} onClick={save}>{busy ? "Saving…" : "Save"}</button>
        <button onClick={() => onDone("")}>Cancel</button>
        <span className="small quiet">Saved changes show at once; the history keeps what was there before.</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the page editor: simple blocks
const NEW = { heading: { type: "heading", text: "" }, text: { type: "text", text: "" }, list: { type: "list", items: [""] },
  table: { type: "table", header: true, rows: [["", ""], ["", ""]] }, links: { type: "links", items: [{ label: "", href: "" }] } };
const NAMES = { heading: "Heading", text: "Text", list: "List", table: "Table", links: "Links" };

function BlocksEditor({ blocks, onChange, lib }) {
  const [pick, setPick] = useState(null);      // {i, put(text)}: the link picker for a block
  const set = (i, b) => onChange(blocks.map((x, j) => (j === i ? b : x)));
  const move = (i, d) => { const out = [...blocks]; [out[i], out[i + d]] = [out[i + d], out[i]]; onChange(out); };
  const add = (t, at) => { const out = [...blocks]; out.splice(at, 0, structuredClone(NEW[t])); onChange(out); };
  const Adder = ({ at }) => (
    <div className="lib-adder small">＋ {Object.keys(NEW).map((t) => <button key={t} className="linkish" onClick={() => add(t, at)}>{NAMES[t]}</button>)}</div>
  );
  return (
    <div className="lib-blocks">
      <p className="small quiet">Write links as [words](address): an address on the web, or one from <b>🔗 Insert a link</b> (a model, project, document, canvas, view, reference entry or page).</p>
      <Adder at={0} />
      {blocks.map((b, i) => (
        <div key={i} className={`lib-block lib-${b.type}`}>
          <div className="lib-block-bar small">
            <b>{NAMES[b.type]}</b>
            {b.type !== "links" && <button className="linkish" onClick={() => setPick({ i, put: (t) => {
              if (b.type === "list") set(i, { ...b, items: [...b.items.filter(Boolean), t] });
              else if (b.type === "table") set(i, { ...b, rows: [...b.rows, [t, ...Array(Math.max(0, b.rows[0].length - 1)).fill("")]] });
              else set(i, { ...b, text: `${b.text}${b.text ? " " : ""}${t}` });
            } })}>🔗 Insert a link</button>}
            <span className="push-right" />
            <button className="linkish" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Up">↑</button>
            <button className="linkish" disabled={i === blocks.length - 1} onClick={() => move(i, 1)} aria-label="Down">↓</button>
            <button className="linkish bad-text" onClick={() => onChange(blocks.filter((_x, j) => j !== i))}>Remove</button>
          </div>
          {b.type === "heading" && <input value={b.text} onChange={(e) => set(i, { ...b, text: e.target.value })} placeholder="A heading" className="lib-h-input" />}
          {b.type === "text" && <textarea rows={Math.max(3, b.text.split("\n").length + 1)} value={b.text} onChange={(e) => set(i, { ...b, text: e.target.value })}
            placeholder="Text. A blank line starts a new paragraph." />}
          {b.type === "list" && <textarea rows={Math.max(3, b.items.length + 1)} value={b.items.join("\n")} onChange={(e) => set(i, { ...b, items: e.target.value.split("\n") })}
            placeholder="One point per line" />}
          {b.type === "table" && <TableEditor b={b} onChange={(x) => set(i, x)} />}
          {b.type === "links" && <LinksEditor b={b} onChange={(x) => set(i, x)} lib={lib} />}
          <Adder at={i + 1} />
        </div>
      ))}
      {pick && <LinkPicker lib={lib} onClose={() => setPick(null)} onPick={(label, href) => { pick.put(`[${label}](${href})`); setPick(null); }} />}
    </div>
  );
}

function TableEditor({ b, onChange }) {
  const width = b.rows[0]?.length || 1;
  const cell = (r, c, v) => onChange({ ...b, rows: b.rows.map((row, i) => (i === r ? row.map((x, j) => (j === c ? v : x)) : row)) });
  return (
    <div className="lib-table-ed">
      <table>
        <tbody>{b.rows.map((row, r) => (
          <tr key={r} className={b.header && r === 0 ? "head" : ""}>
            {row.map((x, c) => <td key={c}><input value={x} onChange={(e) => cell(r, c, e.target.value)} aria-label={`Row ${r + 1}, column ${c + 1}`} /></td>)}
            <td><button className="linkish small" disabled={b.rows.length < 2} onClick={() => onChange({ ...b, rows: b.rows.filter((_y, i) => i !== r) })} aria-label="Remove the row">✕</button></td>
          </tr>
        ))}
          <tr>{Array.from({ length: width }, (_x, c) => <td key={c}><button className="linkish small" disabled={width < 2}
            onClick={() => onChange({ ...b, rows: b.rows.map((row) => row.filter((_y, j) => j !== c)) })}>✕ column</button></td>)}<td /></tr>
        </tbody>
      </table>
      <div className="row-gap small">
        <button className="linkish" onClick={() => onChange({ ...b, rows: [...b.rows, Array(width).fill("")] })}>＋ Row</button>
        <button className="linkish" onClick={() => onChange({ ...b, rows: b.rows.map((row) => [...row, ""]) })}>＋ Column</button>
        <label><input type="checkbox" checked={!!b.header} onChange={(e) => onChange({ ...b, header: e.target.checked })} /> First row is the header</label>
      </div>
    </div>
  );
}

function LinksEditor({ b, onChange, lib }) {
  const set = (i, x) => onChange({ ...b, items: b.items.map((y, j) => (j === i ? x : y)) });
  return (
    <div>
      {b.items.map((x, i) => (
        <div key={i} className="row-gap lib-link-row">
          <input value={x.label} placeholder="Words to show" onChange={(e) => set(i, { ...x, label: e.target.value })} style={{ minWidth: 220 }} />
          <LinkInput value={x.href} onChange={(v, label) => set(i, { label: x.label || label || "", href: v })} lib={lib} />
          <button className="linkish bad-text small" onClick={() => onChange({ ...b, items: b.items.filter((_y, j) => j !== i) })}>✕</button>
        </div>
      ))}
      <button className="linkish small" onClick={() => onChange({ ...b, items: [...b.items, { label: "", href: "" }] })}>＋ Link</button>
    </div>
  );
}

function LinkInput({ value, onChange, lib }) {
  const [pick, setPick] = useState(false);
  return (
    <span className="row-gap">
      <input value={value} placeholder="https://… or 🔗 Choose" onChange={(e) => onChange(e.target.value)} style={{ minWidth: 300 }} />
      <button type="button" onClick={() => setPick(true)}>🔗 Choose</button>
      {pick && <LinkPicker lib={lib} onClose={() => setPick(false)} onPick={(label, href) => { onChange(href, label); setPick(false); }} />}
    </span>
  );
}

// a link to something in EA Explorer (or on the web)
function LinkPicker({ lib, onClose, onPick }) {
  const [kind, setKind] = useState("model");
  const [project, setProject] = useState("");
  const [model, setModel] = useState("");
  const [web, setWeb] = useState({ label: "", href: "https://" });
  const [pq, setPq] = useState("");
  const { data: models_ } = useApi(["model", "view"].includes(kind) ? "/api/v1/models?archived=false" : null);
  const { data: projects_ } = useApi(["project", "document", "canvas"].includes(kind) ? "/api/v1/projects" : null);
  // the picker never offers a frozen or archived model or project (D360)
  const models = models_ && liveModels(models_);
  const projects = projects_ && { ...projects_, projects: liveProjects(projects_.projects) };
  const { data: proj } = useApi(kind === "document" && project ? `/api/v1/projects/${project}` : null);
  const { data: canv } = useApi(kind === "canvas" && project ? `/api/v1/projects/${project}/canvases` : null);
  const { data: vps } = useApi(kind === "view" && model ? `/api/v1/models/${model}/views` : null);
  const { data: refs } = useApi(kind === "reference" ? "/api/v1/reference-library?deep=true" : null);
  const { data: pages } = useApi(kind === "page" && pq.trim().length > 1 ? `${L}/search?q=${encodeURIComponent(pq.trim())}&library=${lib.scope === "org" ? "org" : lib.id}` : null);
  const list = (xs, label, href) => (xs || []).map((x) => <button key={href(x)} className="linkish lib-pick" onClick={() => onPick(label(x), href(x))}>{label(x)}</button>);
  const mlist = Array.isArray(models) ? models : models?.models;
  const plist = Array.isArray(projects) ? projects : projects?.projects;
  return (
    <Modal title="Insert a link" onClose={onClose} wide actions={<button onClick={onClose}>Cancel</button>}>
      <div className="row-gap" role="tablist">
        {[["model", "Model"], ["project", "Project"], ["document", "Document"], ["canvas", "Canvas"], ["view", "View"], ["reference", "Reference library"], ["page", "Library page"], ["web", "Web address"]]
          .map(([k, l]) => <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{l}</button>)}
      </div>
      <div className="lib-pick-list">
        {kind === "model" && list(mlist, (m) => m.name, (m) => `ea:model:${m.id}`)}
        {kind === "project" && list(plist, (p) => p.name, (p) => `ea:project:${p.id}`)}
        {["document", "canvas"].includes(kind) && <select value={project} onChange={(e) => setProject(e.target.value)}><option value="">Choose the project…</option>
          {(plist || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>}
        {kind === "document" && proj && list(proj.documents, (d) => d.title || d.file_name, (d) => `ea:document:${project}:${d.id}`)}
        {kind === "canvas" && canv && list(canv.canvases, (c) => c.name, (c) => `ea:canvas:${project}:${c.id}`)}
        {kind === "view" && <select value={model} onChange={(e) => setModel(e.target.value)}><option value="">Choose the model…</option>
          {(mlist || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>}
        {kind === "view" && vps && list(vps.views || vps, (v) => `${v.code} ${v.name}`, (v) => `ea:view:${model}:${v.code}`)}
        {kind === "reference" && list(refs?.entries, (r) => r.title, (r) => `ea:reference:${r.id}`)}
        {kind === "page" && <><input type="search" value={pq} onChange={(e) => setPq(e.target.value)} placeholder="Words from the page's title" autoFocus />
          {list((pages?.results || []).filter((r) => r.kind === "page"), (r) => r.title, (r) => `ea:page:${r.library}:${r.id}`)}</>}
        {kind === "web" && <div className="ed-form">
          <Field label="Words to show"><input value={web.label} onChange={(e) => setWeb({ ...web, label: e.target.value })} /></Field>
          <Field label="Address"><input type="url" value={web.href} onChange={(e) => setWeb({ ...web, href: e.target.value })} /></Field>
          <button className="primary" disabled={!/^(https?:\/\/\S+|mailto:\S+)$/.test(web.href)} onClick={() => onPick(web.label || web.href, web.href)}>Insert</button>
        </div>}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- adding, folders, history
function AddDialog({ k, lib, folder, onClose }) {
  const [f, setF] = useState({ title: "", description: "", tags: "", href: "" });
  const [file, setFile] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true); setErr("");
    try {
      let r;
      if (k === "file") {
        const fd = new FormData();
        fd.append("file", file); fd.append("kind", "file");
        for (const key of ["title", "description", "tags"]) if (f[key]) fd.append(key, f[key]);
        if (folder) fd.append("folder", folder);
        r = await apiUpload(`${L}/libraries/${lib.id}/entries`, fd);
      } else {
        r = await apiFetch(`${L}/libraries/${lib.id}/entries`, { method: "POST", body: JSON.stringify({ ...f, kind: k, folder, blocks: k === "page" ? [{ type: "text", text: "" }] : undefined }) });
      }
      refreshAll(); onClose(r);
    } catch (x) { setErr(x.message); setBusy(false); }
  }
  const ready = k === "file" ? !!file : f.title.trim() && (k !== "link" || f.href.trim());
  return (
    <Modal title={{ page: "A new page", link: "Add a link", file: "Add a file" }[k]} onClose={() => onClose()}
      actions={<><button onClick={() => onClose()}>Cancel</button><button className="primary" disabled={!ready || busy} onClick={save}>{busy ? "Adding…" : k === "page" ? "Make it and write" : "Add"}</button></>}>
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        {k === "file" && <Field label="File" hint="(the text inside PDF, Word, PowerPoint, Excel and text files is kept for search; a link suits large documents better)">
          <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} /></Field>}
        <Field label="Title" hint={k === "file" ? "(empty: the file's name)" : ""}><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} autoFocus={k !== "file"} /></Field>
        {k === "link" && <Field label="Goes to"><LinkInput value={f.href} lib={lib} onChange={(v, label) => setF({ ...f, href: v, title: f.title || label || "" })} /></Field>}
        <Field label="Description"><input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="Tags" hint="(commas between)"><input value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}

function FolderDialog({ lib, folder, parent, folders, onClose }) {
  const [f, setF] = useState({ name: folder?.name || "", parent: folder ? folder.parent || "" : parent || "" });
  const [err, setErr] = useState("");
  async function save() {
    try {
      const r = folder
        ? await apiFetch(`${L}/libraries/${lib.id}/folders/${folder.id}`, { method: "PUT", body: JSON.stringify({ name: f.name, parent: f.parent || null }) })
        : await apiFetch(`${L}/libraries/${lib.id}/folders`, { method: "POST", body: JSON.stringify({ name: f.name, parent: f.parent || null }) });
      refreshAll(); onClose(r.message);
    } catch (x) { setErr(x.message); }
  }
  return (
    <Modal title={folder ? "Rename or move the folder" : "A new folder"} onClose={() => onClose()}
      actions={<><button onClick={() => onClose()}>Cancel</button><button className="primary" disabled={!f.name.trim()} onClick={save}>Save</button></>}>
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoFocus /></Field>
        <Field label="Inside"><select value={f.parent} onChange={(e) => setF({ ...f, parent: e.target.value })}>
          <option value="">(the top)</option>{folders.filter((x) => x.id !== folder?.id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
      </div>
    </Modal>
  );
}

const ACTION = { added: "added", changed: "changed", removed: "removed", moved: "moved", undone: "undid" };

function History({ lib, entry, onClose }) {
  const { data, error } = useApi(`${L}/libraries/${lib.id}/history${entry ? `?entry=${entry}` : ""}`);
  const [open, setOpen] = useState(null);
  const [msg, setMsg] = useState("");
  async function undo(c) {
    try { const r = await apiFetch(`${L}/libraries/${lib.id}/changes/${c.id}/undo`, { method: "POST" }); setMsg(r.message); refreshAll(); } catch (x) { setMsg(x.message); }
  }
  return (
    <Modal title={entry ? "History" : "Recent changes"} onClose={onClose} wide actions={<button onClick={onClose}>Close</button>}>
      {msg && <p className="status ok">{msg}</p>}
      {error && <p className="status bad">{error}</p>}
      {!data ? <p className="quiet">Loading…</p> : !data.changes.length ? <p className="quiet">No changes yet.</p> : (
        <table className="grid-table">
          <thead><tr><th>When</th><th>Who</th><th>What</th><th /></tr></thead>
          <tbody>{data.changes.map((c) => (
            <Fragment key={c.id}>
              <tr className={c.undone_by ? "lib-undone" : ""}>
                <td className="small nowrap">{fmtDateTime(c.at)}</td>
                <td className="small">{c.username}</td>
                <td>{ACTION[c.action] || c.action} <b>{c.title}</b>{c.undone_by && <span className="small quiet"> (undone by {c.undone_by})</span>}</td>
                <td className="nowrap small">
                  {c.has_before && ["changed", "moved"].includes(c.action) && <button className="linkish" onClick={() => setOpen(open === c.id ? null : c.id)}>{open === c.id ? "Hide" : "Before and after"}</button>}
                  {c.has_before && ["changed", "moved"].includes(c.action) && lib.may?.admin && !c.undone_by && " · "}
                  {lib.may?.admin && !c.undone_by && c.action !== "undone" && <button className="linkish" onClick={() => undo(c)}>↶ Undo</button>}
                </td>
              </tr>
              {open === c.id && <tr><td colSpan={4}><ChangeDetail lib={lib} id={c.id} /></td></tr>}
            </Fragment>
          ))}</tbody>
        </table>
      )}
      {!lib.may?.admin && <p className="small quiet">{lib.scope === "org" ? "Library Admins and Super Admins" : "The project's admins"} can undo changes.</p>}
    </Modal>
  );
}

function ChangeDetail({ lib, id }) {
  const { data } = useApi(`${L}/libraries/${lib.id}/changes/${id}`);
  if (!data) return <p className="quiet small">Loading…</p>;
  const b = data.before || {};
  const a = data.after || {};
  const keys = ["title", "description", "tags", "href", "folder", "in_enterprise", "external_link"].filter((k) => JSON.stringify(b[k] ?? "") !== JSON.stringify(a[k] ?? "") && (k in b || k in a));
  const pageChanged = JSON.stringify(b.blocks || []) !== JSON.stringify(a.blocks || []) && (b.blocks || a.blocks);
  return (
    <div className="lib-diff">
      {keys.map((k) => <div key={k} className="small"><b>{k.replace("_", " ")}</b>: <del>{String(b[k] ?? "")}</del> → <ins>{String(a[k] ?? "")}</ins></div>)}
      {(b.folder_id ?? null) !== (a.folder_id ?? null) && "folder_id" in a && <div className="small"><b>folder</b>: moved to another folder</div>}
      {pageChanged && <div className="lib-diff-page">
        <div><p className="small quiet">Before</p><PageBody blocks={b.blocks || []} /></div>
        <div><p className="small quiet">After</p><PageBody blocks={a.blocks || []} /></div>
      </div>}
      {!keys.length && !pageChanged && <p className="small quiet">Nothing to compare.</p>}
    </div>
  );
}
