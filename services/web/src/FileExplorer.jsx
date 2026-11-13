// A container's files in an Explorer-style view (R2.18 built it; R2.58 and R2.60, owner 13 Nov 2026: "double click on a
// folder at root level, there is no folders inside it ... Fix it with the Windows explorer view").
//
//   File menu      New folder, Upload, Open, Download, Rename, Move, Copy, Delete, Refresh
//   address bar    Back, Forward, Up, the path (type one and press Enter) and a filter
//   left           the folder tree: click a folder to open it, the arrow to expand it without opening it
//   right          the folder's contents: click selects, double click (or Enter) opens a folder or a file
//
// Every write asks first and is in the audit trail; secrets, Docker's socket and the helper's own files are never
// written; a database's data folder warns strongly. Off with EAX_CONTAINER_CONSOLE=off, as the terminal.
import { useEffect, useState } from "react";
import { apiDownload, apiFetch, can } from "./auth";
import { fmtDateTime } from "./fmt";

const size = (b) => (b == null ? "" : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB`
  : b >= 1e3 ? `${Math.round(b / 1e3)} KB` : `${b} B`);
export const parentOf = (p) => p.split("/").slice(0, -1).join("/") || "/";
export const joinPath = (folder, name) => `${folder.replace(/\/$/, "")}/${name}`;

// The folders above a path, root first: "/usr/lib" -> ["/", "/usr", "/usr/lib"].
export function crumbs(p) {
  const parts = p.split("/").filter(Boolean);
  return ["/", ...parts.map((_, i) => `/${parts.slice(0, i + 1).join("/")}`)];
}

function TreeNode({ path, name, tree, current, toggle, open, depth }) {
  const node = tree[path] || {};
  const kids = (node.children || []).filter((e) => e.dir);
  return (
    <li role="treeitem" aria-expanded={!!node.open} aria-selected={current === path}>
      <div className={`fx-node${current === path ? " fx-here" : ""}`} style={{ paddingLeft: `${depth * 14}px` }}>
        <button className="fx-twisty" aria-label={node.open ? `Collapse ${name}` : `Expand ${name}`}
          onClick={() => toggle(path)}>{node.open ? "▾" : "▸"}</button>
        <button className="linkish fx-name" onClick={() => open(path)} title={path}>📁 {name}</button>
      </div>
      {node.open && (node.error ? <div className="quiet small" style={{ paddingLeft: `${(depth + 1) * 14}px` }}>{node.error}</div>
        : !node.children ? <div className="quiet small" style={{ paddingLeft: `${(depth + 1) * 14}px` }}>Loading...</div>
          : kids.length > 0 && <ul role="group">{kids.map((k) => (
            <TreeNode key={k.path} path={k.path} name={k.name} tree={tree} current={current} toggle={toggle} open={open} depth={depth + 1} />))}</ul>)}
    </li>
  );
}

export default function FileExplorer({ service, on }) {
  const [path, setPath] = useState("/");
  const [typed, setTyped] = useState("/");
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [file, setFile] = useState(null);
  const [edit, setEdit] = useState(null);
  const [find, setFind] = useState("");
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState(null);
  const [menu, setMenu] = useState(false);
  const [tree, setTree] = useState({});
  const [back, setBack] = useState([]);
  const [fwd, setFwd] = useState([]);
  const url = (p, what = "") => `/api/v1/admin/containers/${service}/files${what}?path=${encodeURIComponent(p)}`;

  const children = (p) => apiFetch(url(p))
    .then((x) => setTree((t) => ({ ...t, [x.path]: { ...(t[x.path] || {}), open: true, children: x.entries, error: "" } })))
    .catch((e) => setTree((t) => ({ ...t, [p]: { ...(t[p] || {}), open: true, error: e.message } })));
  const load = (p = path, how = "go") => {
    setErr(""); setSel(null);
    return apiFetch(url(p)).then((x) => {
      if (how === "go" && x.path !== path) { setBack((b) => [...b, path]); setFwd([]); }
      setD(x); setPath(x.path); setTyped(x.path);
      setTree((t) => {                      // the tree shows the way down to the open folder, and its folders
        const next = { ...t, [x.path]: { ...(t[x.path] || {}), open: true, children: x.entries, error: "" } };
        for (const c of crumbs(x.path)) if (c !== x.path) next[c] = { ...(next[c] || {}), open: true };
        return next;
      });
      for (const c of crumbs(x.path)) if (c !== x.path) children(c);
    }).catch((e) => setErr(e.message));
  };
  useEffect(() => { setTree({}); setBack([]); setFwd([]); if (on !== false) load("/", "first"); }, [service, on]);
  if (!can("system.operate")) return <p className="quiet">The file explorer is for IT and Super Admins.</p>;
  if (on === false) return <p className="quiet">The file explorer is switched off on this installation (EAX_CONTAINER_CONSOLE=off in the config file).</p>;

  const toggle = (p) => {
    const n = tree[p];
    if (n?.open) setTree((t) => ({ ...t, [p]: { ...n, open: false } }));
    else if (n?.children) setTree((t) => ({ ...t, [p]: { ...n, open: true } }));
    else children(p);
  };
  const goBack = () => { const p = back[back.length - 1]; if (p == null) return; setBack(back.slice(0, -1)); setFwd([path, ...fwd]); load(p, "history"); };
  const goFwd = () => { const p = fwd[0]; if (p == null) return; setFwd(fwd.slice(1)); setBack([...back, path]); load(p, "history"); };

  const change = async (body, sure) => {
    if (sure && !window.confirm(sure)) return null;
    setBusy(true); setErr("");
    try {
      let out;
      try { out = await apiFetch(url(path).split("?")[0], { method: "POST", body: JSON.stringify(body) }); }
      catch (e) {
        if (/database's data folder/.test(e.message) && window.confirm(`${e.message}\n\nGo on anyway?`)) {
          out = await apiFetch(url(path).split("?")[0], { method: "POST", body: JSON.stringify({ ...body, confirm: "database" }) });
        } else throw e;
      }
      load(path, "refresh"); return out;
    } catch (e) { setErr(e.message); return null; } finally { setBusy(false); }
  };
  const view = (f) => apiFetch(url(f.path, "/content")).then((x) => { setFile(x); setEdit(null); }).catch((e) => setErr(e.message));
  const openItem = (f) => (f.dir ? load(f.path) : view(f));
  const download = (f) => apiDownload(url(f.path, "/download"), f.dir ? `${f.name}.zip` : f.name).catch((e) => setErr(e.message));
  const upload = async (list) => {
    const files = await Promise.all([...list].map((f) => new Promise((ok) => { const r = new FileReader(); r.onload = () => ok({ name: f.name, content: String(r.result).split(",")[1] || "" }); r.readAsDataURL(f); })));
    const overwrite = window.confirm(`Upload ${files.length} file(s) into ${path}? OK replaces files of the same name; Cancel keeps them (the upload then stops at a clash).`);
    change({ op: "upload", path, files, overwrite });
  };
  const ask = (what, f) => {
    if (!f) { setErr("Select a file or folder first."); return; }
    if (what === "delete") {
      const typedPath = window.prompt(`Delete ${f.path}${f.dir ? " and everything in it" : ""} for good? Type its full path to confirm:`);
      if (typedPath) change({ op: "delete", path: f.path, confirm_path: typedPath });
      return;
    }
    const to = window.prompt(what === "rename" ? "New name:" : `${what === "copy" ? "Copy" : "Move"} to (full path):`, what === "rename" ? f.name : f.path);
    if (!to) return;
    change({ op: what === "copy" ? "copy" : "move", path: f.path, to: what === "rename" ? joinPath(path, to) : to });
  };
  const ro = d?.read_only_reason;
  const shown = (d?.entries || []).filter((e) => !find || e.name.toLowerCase().includes(find.toLowerCase()));
  const item = (label, fn, disabled) => (
    <li><button role="menuitem" disabled={disabled || busy} onClick={() => { setMenu(false); fn(); }}>{label}</button></li>);

  return (
    <div className="ct-files fx" aria-label={`Files in ${service}`}>
      <div className="fx-menubar" role="menubar">
        <div className="fx-menu">
          <button role="menuitem" aria-haspopup="true" aria-expanded={menu} onClick={() => setMenu(!menu)}>File</button>
          {menu && (
            <ul className="fx-dropdown" role="menu" onMouseLeave={() => setMenu(false)}>
              {item("New folder", () => { const n = window.prompt("New folder name:"); if (n) change({ op: "mkdir", path: joinPath(path, n) }); }, !!ro)}
              <li><label className={`fx-upload${ro ? " disabled" : ""}`}>Upload...
                <input type="file" multiple hidden disabled={!!ro} onChange={(e) => { setMenu(false); if (e.target.files.length) upload(e.target.files); }} /></label></li>
              <li className="fx-sep" role="separator" />
              {item("Open", () => openItem(sel), !sel)}
              {item(sel?.dir ? "Download as zip" : "Download", () => download(sel || { path, name: path.split("/").pop() || "root", dir: true }))}
              <li className="fx-sep" role="separator" />
              {item("Rename", () => ask("rename", sel), !sel || !!ro)}
              {item("Move to...", () => ask("move", sel), !sel || !!ro)}
              {item("Copy to...", () => ask("copy", sel), !sel || !!ro)}
              {item("Delete", () => ask("delete", sel), !sel || !!ro)}
              <li className="fx-sep" role="separator" />
              {item("Refresh", () => load(path, "refresh"))}
            </ul>)}
        </div>
      </div>
      <div className="fx-address">
        <button onClick={goBack} disabled={!back.length} aria-label="Back" title="Back">←</button>
        <button onClick={goFwd} disabled={!fwd.length} aria-label="Forward" title="Forward">→</button>
        <button onClick={() => load(parentOf(path))} disabled={path === "/"} aria-label="Up" title="Up one folder">↑</button>
        <nav className="fx-crumbs" aria-label="Where you are">
          {crumbs(path).map((c) => (
            <button key={c} className="linkish" onClick={() => load(c)}>{c === "/" ? "/" : `${c.split("/").pop()} /`}</button>))}
        </nav>
        <input className="fx-path" value={typed} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(typed)} aria-label="Folder" />
        <button onClick={() => load(path, "refresh")} title="Refresh">⟳</button>
        <input placeholder="Filter this folder" value={find} onChange={(e) => setFind(e.target.value)} aria-label="Filter this folder" />
      </div>
      {ro && <p className="quiet small">Read only here: {ro}</p>}
      {d?.mount && <p className="small">This folder is a mount: <code>{d.mount.source}</code>{d.mount.read_only ? " (read only)" : ""}.</p>}
      {err && <p className="status bad">{err}</p>}
      <div className="fx-panes">
        <ul className="fx-tree" role="tree" aria-label="Folders">
          <TreeNode path="/" name="/" tree={tree} current={path} toggle={toggle} open={(p) => load(p)} depth={0} />
        </ul>
        <div className="fx-list">
          {!d ? !err && <p>Loading...</p> : !shown.length ? <p className="quiet">{find ? "Nothing matches the filter." : "This folder is empty."}</p> : (
            <table className="grid-table">
              <thead><tr><th>Name</th><th>Size</th><th>Changed</th><th>Owner</th><th>Permissions</th></tr></thead>
              <tbody>{shown.map((f) => (
                <tr key={f.path} tabIndex={0} className={sel?.path === f.path ? "fx-selected" : ""} aria-selected={sel?.path === f.path}
                  onClick={() => setSel(f)} onDoubleClick={() => openItem(f)}
                  onKeyDown={(e) => { if (e.key === "Enter") openItem(f); if (e.key === "Delete" && !ro) ask("delete", f); }}>
                  <td title={f.link ? `${f.path} (a link)` : f.path}>{f.dir ? "📁" : "📄"} {f.name}{f.link ? " ↪" : ""}
                    {f.mount && <span className="quiet small"> mount: {f.mount.source}{f.mount.read_only ? " (read only)" : ""}</span>}</td>
                  <td className="small">{f.dir ? "" : size(f.bytes)}</td>
                  <td className="small nowrap">{f.modified ? fmtDateTime(new Date(f.modified * 1000).toISOString()) : ""}</td>
                  <td className="small">{f.owner}</td><td className="small"><code>{f.permissions}</code></td>
                </tr>))}</tbody>
            </table>)}
          <p className="quiet small">{shown.length} item(s){sel ? ` · selected: ${sel.name}` : ""} · double click opens; the File menu does the rest.</p>
        </div>
      </div>
      {file && (
        <div className="card ct-file">
          <h4><code>{file.path}</code> · {file.bytes} bytes <button className="linkish" onClick={() => { setFile(null); setEdit(null); }}>Close</button></h4>
          {file.binary ? <p className="quiet">Not a text file: download it instead.</p>
            : edit == null ? <>
              {!file.read_only_reason && <button onClick={() => setEdit(file.text)}>Edit</button>}
              {file.read_only_reason && <p className="quiet small">Read only: {file.read_only_reason}</p>}
              <pre className="ct-file-text">{file.text}</pre></>
              : <>
                <textarea className="ct-file-edit" value={edit} onChange={(e) => setEdit(e.target.value)} rows={24} aria-label={`Edit ${file.path}`} />
                <button disabled={busy} onClick={async () => { const out = await change({ op: "write", path: file.path, content: edit, sha256: file.sha256 }, `Save your changes to ${file.path}? The file is replaced (the before and after go into the audit trail).`); if (out) view(file); }}>Save</button>
                <button onClick={() => setEdit(null)}>Cancel</button></>}
        </div>)}
    </div>
  );
}
