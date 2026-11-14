// A container's files in a Windows Explorer style view (R2.18 built it; R2.58 and R2.60 the tree and the File menu;
// R3.5, owner 13 Nov 2026: "make file explorer on containers be read write upload etc with a windows explorer style
// structure"; decided: Details, List, Large icons and a Preview pane; Mounts uses the same explorer, read and write).
//
//   menus          File (New folder, New file, Upload, Open, Download, Rename, Move, Copy, Delete, Properties, Refresh),
//                  Edit (Cut, Copy, Paste, Select all), View (Details, List, Large icons, Preview pane); the same on a
//                  right click
//   keys           Enter opens, F2 renames, Delete deletes, Ctrl+C / Ctrl+X / Ctrl+V / Ctrl+A, Backspace or Alt+Up goes
//                  up, Alt+Left / Alt+Right back and forward, F5 refreshes
//   choosing       click one; Ctrl+click adds or takes away; Shift+click a range; several download as one zip, and are
//                  cut, copied, moved or deleted together
//   drag and drop  files from the computer onto the list or a folder are uploaded there; items dragged onto a folder
//                  (in the list or the tree) are moved there, copied with Ctrl
//   address bar    Back, Forward, Up, the path (type one and press Enter) and a filter
//
// Every write asks first and is in the audit trail; secrets, Docker's socket and the helper's own files are never
// written; a database's data folder warns strongly; a read-only mount is read only here. Off with
// EAX_CONTAINER_CONSOLE=off, as the terminal. The logic without the screen is in fileOps.js.
import { useEffect, useRef, useState } from "react";
import { apiDownload, apiFetch, can } from "./auth";
import { fmtDateTime } from "./fmt";
import { Modal } from "./ModelOps";
import { VIEWS, baseName, choose, crumbs, deleteAsk, dropPlan, iconOf, joinPath, keyAction, parentOf, pasteOps, previewable } from "./fileOps";

export { crumbs, joinPath, parentOf };

const size = (b) => (b == null ? "" : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB`
  : b >= 1e3 ? `${Math.round(b / 1e3)} KB` : `${b} B`);
const when = (t) => (t ? fmtDateTime(new Date(t * 1000).toISOString()) : "");
const DRAG = "application/x-eax-paths";

function TreeNode({ path, name, tree, current, toggle, open, depth, onDropTo }) {
  const node = tree[path] || {};
  const kids = (node.children || []).filter((e) => e.dir);
  const [over, setOver] = useState(false);
  return (
    <li role="treeitem" aria-expanded={!!node.open} aria-selected={current === path}>
      <div className={`fx-node${current === path ? " fx-here" : ""}${over ? " fx-drop" : ""}`} style={{ paddingLeft: `${depth * 14}px` }}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { setOver(false); onDropTo(e, path); }}>
        <button className="fx-twisty" aria-label={node.open ? `Collapse ${name}` : `Expand ${name}`}
          onClick={() => toggle(path)}>{node.open ? "▾" : "▸"}</button>
        <button className="linkish fx-name" onClick={() => open(path)} title={path}>📁 {name}</button>
      </div>
      {node.open && (node.error ? <div className="quiet small" style={{ paddingLeft: `${(depth + 1) * 14}px` }}>{node.error}</div>
        : !node.children ? <div className="quiet small" style={{ paddingLeft: `${(depth + 1) * 14}px` }}>Loading...</div>
          : kids.length > 0 && <ul role="group">{kids.map((k) => (
            <TreeNode key={k.path} path={k.path} name={k.name} tree={tree} current={current} toggle={toggle} open={open}
              depth={depth + 1} onDropTo={onDropTo} />))}</ul>)}
    </li>
  );
}

export default function FileExplorer({ service, on, start = "/" }) {
  const [path, setPath] = useState(start);
  const [typed, setTyped] = useState(start);
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [file, setFile] = useState(null);
  const [edit, setEdit] = useState(null);
  const [find, setFind] = useState("");
  const [busy, setBusy] = useState(false);
  const [chosen, setChosen] = useState([]);
  const [anchor, setAnchor] = useState(null);
  const [menu, setMenu] = useState("");            // "file" | "edit" | "view" | ""
  const [ctx, setCtx] = useState(null);            // a right click: {x, y}
  const [view, setView] = useState(() => { try { return localStorage.getItem("eax.fx.view") || "details"; } catch { return "details"; } });
  const [preview, setPreview] = useState(false);
  const [peek, setPeek] = useState(null);          // what the preview pane shows
  const [props, setProps] = useState(null);
  const [clip, setClip] = useState(null);          // {mode: "cut" | "copy", paths, service}
  const [tree, setTree] = useState({});
  const [back, setBack] = useState([]);
  const [fwd, setFwd] = useState([]);
  const [dropOn, setDropOn] = useState(null);
  const listRef = useRef(null);
  const url = (p, what = "") => `/api/v1/admin/containers/${service}/files${what}?path=${encodeURIComponent(p)}`;

  const children = (p) => apiFetch(url(p))
    .then((x) => setTree((t) => ({ ...t, [x.path]: { ...(t[x.path] || {}), open: true, children: x.entries, error: "" } })))
    .catch((e) => setTree((t) => ({ ...t, [p]: { ...(t[p] || {}), open: true, error: e.message } })));
  const load = (p = path, how = "go") => {
    setErr(""); setChosen([]); setAnchor(null); setPeek(null);
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
  useEffect(() => { setTree({}); setBack([]); setFwd([]); if (on !== false) load(start, "first"); }, [service, on, start]);
  useEffect(() => { try { localStorage.setItem("eax.fx.view", view); } catch { /* a convenience only */ } }, [view]);
  const shown = (d?.entries || []).filter((e) => !find || e.name.toLowerCase().includes(find.toLowerCase()));
  const items = shown.filter((e) => chosen.includes(e.path));
  const one = items.length === 1 ? items[0] : null;
  useEffect(() => {                                 // the preview pane: the one item chosen
    if (!preview || !one) { setPeek(null); return; }
    if (one.dir || !previewable(one)) { setPeek({ item: one }); return; }
    apiFetch(url(one.path, "/content")).then((x) => setPeek({ item: one, ...x })).catch((e) => setPeek({ item: one, error: e.message }));
  }, [preview, one?.path]);
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

  const send = async (body) => {
    try { return await apiFetch(url(path).split("?")[0], { method: "POST", body: JSON.stringify(body) }); }
    catch (e) {
      if (/database's data folder/.test(e.message) && window.confirm(`${e.message}\n\nGo on anyway?`)) {
        return apiFetch(url(path).split("?")[0], { method: "POST", body: JSON.stringify({ ...body, confirm: "database" }) });
      }
      throw e;
    }
  };
  const change = async (body, sure) => {
    if (sure && !window.confirm(sure)) return null;
    setBusy(true); setErr("");
    try { const out = await send(body); load(path, "refresh"); return out; }
    catch (e) { setErr(e.message); return null; } finally { setBusy(false); }
  };
  const changeAll = async (bodies, done) => {        // several changes, one after another; stops at the first refused
    setBusy(true); setErr(""); let n = 0;
    try { for (const b of bodies) { await send(b); n += 1; } setMsg(done(n)); }
    catch (e) { setErr(`${e.message}${n ? ` (${n} done before this)` : ""}`); }
    finally { setBusy(false); load(path, "refresh"); }
  };
  const viewFile = (f) => apiFetch(url(f.path, "/content")).then((x) => { setFile(x); setEdit(null); }).catch((e) => setErr(e.message));
  const openItem = (f) => (f?.dir ? load(f.path) : f && viewFile(f));
  const download = (list) => {
    if (list.length > 1) {
      const q = list.map((f) => `path=${encodeURIComponent(f.path)}`).join("&");
      return apiDownload(`/api/v1/admin/containers/${service}/files/download?${q}`, "files.zip").catch((e) => setErr(e.message));
    }
    const f = list[0] || { path, name: baseName(path) === "/" ? "root" : baseName(path), dir: true };
    return apiDownload(url(f.path, "/download"), f.dir ? `${f.name}.zip` : f.name).catch((e) => setErr(e.message));
  };
  const upload = async (list, into = path) => {
    const files = await Promise.all([...list].map((f) => new Promise((ok) => { const r = new FileReader(); r.onload = () => ok({ name: f.name, content: String(r.result).split(",")[1] || "" }); r.readAsDataURL(f); })));
    const overwrite = window.confirm(`Upload ${files.length} file(s) into ${into}? OK replaces files of the same name; Cancel keeps them (the upload then stops at a clash).`);
    change({ op: "upload", path: into, files, overwrite });
  };
  const newFile = () => {
    const n = window.prompt("New file name:");
    if (n) change({ op: "upload", path, files: [{ name: n, content: "" }], overwrite: false });
  };
  const newFolder = () => { const n = window.prompt("New folder name:"); if (n) change({ op: "mkdir", path: joinPath(path, n) }); };
  const rename = (f) => {
    if (!f) { setErr("Choose one item to rename."); return; }
    const to = window.prompt("New name:", f.name);
    if (to && to !== f.name) change({ op: "move", path: f.path, to: joinPath(parentOf(f.path), to) });
  };
  const moveOrCopy = (what, list) => {
    if (!list.length) { setErr("Choose a file or folder first."); return; }
    const to = window.prompt(`${what === "copy" ? "Copy" : "Move"} ${list.length > 1 ? `these ${list.length} items` : list[0].name} to which folder (full path)?`, path);
    if (!to) return;
    const { ops, skipped } = pasteOps({ mode: what === "copy" ? "copy" : "cut", paths: list.map((f) => f.path) }, to);
    changeAll(ops, (n) => `${n} ${what === "copy" ? "copied" : "moved"}${skipped.length ? `; left out: ${skipped.join(", ")}` : ""}.`);
  };
  const remove = (list) => {
    const a = deleteAsk(list.map((f) => f.path));
    if (!a) { setErr("Choose a file or folder first."); return; }
    const typedIn = window.prompt(a.prompt);
    if (typedIn !== a.expect) { if (typedIn != null) setErr("Not deleted: what you typed does not match."); return; }
    changeAll(list.map((f) => ({ op: "delete", path: f.path, confirm_path: f.path })), (n) => `${n} deleted.`);
  };
  const paste = () => {
    if (!clip || clip.service !== service) { setErr("Nothing to paste: cut or copy something in this container first."); return; }
    const { ops, skipped } = pasteOps(clip, path);
    if (!ops.length) { setErr(skipped.join("; ") || "Nothing to paste."); return; }
    if (!window.confirm(`${clip.mode === "cut" ? "Move" : "Copy"} ${ops.length} item(s) into ${path}?`)) return;
    changeAll(ops, (n) => `${n} ${clip.mode === "cut" ? "moved" : "copied"} into ${path}${skipped.length ? `; left out: ${skipped.join(", ")}` : ""}.`);
    if (clip.mode === "cut") setClip(null);
  };
  const showProps = (f) => apiFetch(url((f || { path }).path, "/properties")).then(setProps).catch((e) => setErr(e.message));
  const selectAll = () => setChosen(shown.map((e) => e.path));
  const ro = d?.read_only_reason;

  const act = (name) => {
    setMenu(""); setCtx(null); setMsg("");
    switch (name) {
      case "open": return openItem(one);
      case "rename": return !ro && rename(one);
      case "delete": return !ro && remove(items);
      case "copy": return items.length && setClip({ mode: "copy", paths: items.map((f) => f.path), service });
      case "cut": return !ro && items.length && setClip({ mode: "cut", paths: items.map((f) => f.path), service });
      case "paste": return !ro && paste();
      case "all": return selectAll();
      case "up": return path !== "/" && load(parentOf(path));
      case "back": return goBack();
      case "forward": return goFwd();
      case "refresh": return load(path, "refresh");
      default: return null;
    }
  };
  const onKey = (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    const a = keyAction(e);
    if (a === "none") { setCtx(null); setMenu(""); return; }
    if (!a) return;
    e.preventDefault();
    act(a);
  };
  const onDropTo = (e, folder) => {
    e.preventDefault(); setDropOn(null);
    let dragged = [];
    try { dragged = JSON.parse(e.dataTransfer.getData(DRAG) || "[]"); } catch { dragged = []; }
    const copy = e.ctrlKey || e.altKey;
    const plan = dropPlan({ files: [...(e.dataTransfer.files || [])], dragged, copy }, folder);
    if (!plan) return;
    if (ro) { setErr(`Read only here: ${ro}`); return; }
    if (plan.upload) { upload(e.dataTransfer.files, folder); return; }
    if (!plan.ops.length) { setErr(plan.skipped.join("; ")); return; }
    if (!window.confirm(`${copy ? "Copy" : "Move"} ${plan.ops.length} item(s) into ${folder}?`)) return;
    changeAll(plan.ops, (n) => `${n} ${copy ? "copied" : "moved"} into ${folder}.`);
  };
  const click = (e, f) => {
    const out = choose(shown, chosen, anchor, f.path, { ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey });
    setChosen(out.chosen); setAnchor(out.anchor);
  };
  const rightClick = (e, f) => {
    e.preventDefault();
    if (f && !chosen.includes(f.path)) { setChosen([f.path]); setAnchor(f.path); }
    if (!f) setChosen([]);
    setMenu(""); setCtx({ x: e.clientX, y: e.clientY });
  };
  const dragStart = (e, f) => {
    e.dataTransfer.setData(DRAG, JSON.stringify(chosen.includes(f.path) ? chosen : [f.path]));
    e.dataTransfer.effectAllowed = "copyMove";
  };
  const rowProps = (f) => ({
    tabIndex: 0, draggable: !ro, "aria-selected": chosen.includes(f.path),
    className: `${chosen.includes(f.path) ? "fx-selected" : ""}${clip?.mode === "cut" && clip.paths.includes(f.path) ? " fx-cut" : ""}${dropOn === f.path ? " fx-drop" : ""}`,
    onClick: (e) => click(e, f), onDoubleClick: () => openItem(f), onContextMenu: (e) => rightClick(e, f),
    onDragStart: (e) => dragStart(e, f),
    onDragOver: f.dir ? (e) => { e.preventDefault(); e.stopPropagation(); setDropOn(f.path); } : undefined,
    onDragLeave: f.dir ? () => setDropOn(null) : undefined,
    onDrop: f.dir ? (e) => { e.stopPropagation(); onDropTo(e, f.path); } : undefined,
    title: f.link ? `${f.path} (a link)` : f.path,
  });

  const item = (label, fn, disabled, keys = "") => (
    <li key={label}><button role="menuitem" disabled={disabled || busy} onClick={() => { setMenu(""); setCtx(null); fn(); }}>
      {label}{keys && <span className="fx-keys">{keys}</span>}</button></li>);
  const sep = (k) => <li key={k} className="fx-sep" role="separator" />;
  const fileItems = () => [
    item("New folder", newFolder, !!ro),
    item("New file", newFile, !!ro),
    <li key="upload"><label className={`fx-upload${ro ? " disabled" : ""}`}>Upload...
      <input type="file" multiple hidden disabled={!!ro} onChange={(e) => { setMenu(""); setCtx(null); if (e.target.files.length) upload(e.target.files); }} /></label></li>,
    sep("s1"),
    item("Open", () => openItem(one), !one, "Enter"),
    item(items.length > 1 ? `Download ${items.length} as one zip` : one?.dir ? "Download as zip" : "Download", () => download(items)),
    sep("s2"),
    item("Rename", () => rename(one), !one || !!ro, "F2"),
    item("Move to...", () => moveOrCopy("move", items), !items.length || !!ro),
    item("Copy to...", () => moveOrCopy("copy", items), !items.length || !!ro),
    item("Delete", () => remove(items), !items.length || !!ro, "Del"),
    sep("s3"),
    item("Properties", () => showProps(one), items.length > 1),
    item("Refresh", () => load(path, "refresh"), false, "F5"),
  ];
  const editItems = () => [
    item("Cut", () => act("cut"), !items.length || !!ro, "Ctrl+X"),
    item("Copy", () => act("copy"), !items.length, "Ctrl+C"),
    item("Paste", () => act("paste"), !clip || clip.service !== service || !!ro, "Ctrl+V"),
    sep("s4"),
    item("Select all", selectAll, !shown.length, "Ctrl+A"),
  ];
  const viewItems = () => [
    ...VIEWS.map(([k, l]) => item(`${view === k ? "● " : ""}${l}`, () => setView(k))),
    sep("s5"),
    item(`${preview ? "● " : ""}Preview pane`, () => setPreview(!preview)),
  ];
  const menuButton = (k, label, list) => (
    <div className="fx-menu" key={k}>
      <button role="menuitem" aria-haspopup="true" aria-expanded={menu === k} onClick={() => { setCtx(null); setMenu(menu === k ? "" : k); }}>{label}</button>
      {menu === k && <ul className="fx-dropdown" role="menu" onMouseLeave={() => setMenu("")}>{list()}</ul>}
    </div>);

  return (
    <div className="ct-files fx" aria-label={`Files in ${service}`} onKeyDown={onKey} onClick={() => ctx && setCtx(null)}>
      <div className="fx-menubar" role="menubar">
        {menuButton("file", "File", fileItems)}
        {menuButton("edit", "Edit", editItems)}
        {menuButton("view", "View", viewItems)}
      </div>
      <div className="fx-address">
        <button onClick={goBack} disabled={!back.length} aria-label="Back" title="Back (Alt+Left)">←</button>
        <button onClick={goFwd} disabled={!fwd.length} aria-label="Forward" title="Forward (Alt+Right)">→</button>
        <button onClick={() => load(parentOf(path))} disabled={path === "/"} aria-label="Up" title="Up one folder (Backspace)">↑</button>
        <nav className="fx-crumbs" aria-label="Where you are">
          {crumbs(path).map((c) => (
            <button key={c} className="linkish" onClick={() => load(c)}>{c === "/" ? "/" : `${c.split("/").pop()} /`}</button>))}
        </nav>
        <input className="fx-path" value={typed} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(typed)} aria-label="Folder" />
        <button onClick={() => load(path, "refresh")} title="Refresh (F5)">⟳</button>
        <input placeholder="Filter this folder" value={find} onChange={(e) => setFind(e.target.value)} aria-label="Filter this folder" />
      </div>
      {ro && <p className="quiet small">Read only here: {ro}</p>}
      {d?.mount && <p className="small">This folder is a mount: <code>{d.mount.source}</code>{d.mount.read_only ? " (read only)" : ""}.</p>}
      {!d?.mount && d?.inside_mount && <p className="small quiet">In the mount of <code>{d.inside_mount.source}</code> at <code>{d.inside_mount.at}</code>{d.inside_mount.read_only ? " (read only)" : ""}.</p>}
      {err && <p className="status bad">{err}</p>}
      {msg && <p className="status ok small">{msg}</p>}
      <div className={`fx-panes${preview ? " fx-with-preview" : ""}`}>
        <ul className="fx-tree" role="tree" aria-label="Folders">
          <TreeNode path="/" name="/" tree={tree} current={path} toggle={toggle} open={(p) => load(p)} depth={0} onDropTo={onDropTo} />
        </ul>
        <div className={`fx-list fx-view-${view}${dropOn === path ? " fx-drop" : ""}`} ref={listRef} tabIndex={-1}
          onContextMenu={(e) => e.target === listRef.current && rightClick(e, null)}
          onDragOver={(e) => { e.preventDefault(); setDropOn(path); }} onDragLeave={(e) => e.target === listRef.current && setDropOn(null)}
          onDrop={(e) => onDropTo(e, path)}>
          {!d ? !err && <p>Loading...</p> : !shown.length ? <p className="quiet">{find ? "Nothing matches the filter." : "This folder is empty. Drop files here to upload them."}</p>
            : view === "details" ? (
              <table className="grid-table">
                <thead><tr><th>Name</th><th>Size</th><th>Changed</th><th>Owner</th><th>Permissions</th></tr></thead>
                <tbody>{shown.map((f) => (
                  <tr key={f.path} {...rowProps(f)}>
                    <td>{iconOf(f)} {f.name}{f.link ? " ↪" : ""}
                      {f.mount && <span className="quiet small"> mount: {f.mount.source}{f.mount.read_only ? " (read only)" : ""}</span>}</td>
                    <td className="small">{f.dir ? "" : size(f.bytes)}</td>
                    <td className="small nowrap">{when(f.modified)}</td>
                    <td className="small">{f.owner}</td><td className="small"><code>{f.permissions}</code></td>
                  </tr>))}</tbody>
              </table>)
              : <ul className={view === "icons" ? "fx-icons" : "fx-compact"} role="listbox" aria-multiselectable="true" aria-label={`${path} contents`}>
                {shown.map((f) => (
                  <li key={f.path} role="option" {...rowProps(f)}>
                    <span className="fx-icon" aria-hidden="true">{iconOf(f)}</span><span className="fx-label">{f.name}</span></li>))}
              </ul>}
          <p className="quiet small">{shown.length} item(s){items.length ? ` · ${items.length} chosen` : ""}{clip ? ` · ${clip.paths.length} ${clip.mode === "cut" ? "cut" : "copied"}` : ""} · double click opens; right click for the menu; Ctrl+click or Shift+click chooses several; drop files to upload.</p>
        </div>
        {preview && (
          <aside className="fx-preview" aria-label="Preview">
            {!peek ? <p className="quiet small">Choose one file to see it here.</p> : <>
              <h4>{iconOf(peek.item)} {peek.item.name}</h4>
              <p className="small quiet">{peek.item.dir ? "folder" : size(peek.item.bytes)} · {when(peek.item.modified)} · {peek.item.owner} · <code>{peek.item.permissions}</code></p>
              {peek.error ? <p className="small bad-text">{peek.error}</p>
                : peek.item.dir ? <button onClick={() => showProps(peek.item)}>Properties (size of everything in it)</button>
                  : !previewable(peek.item) ? <p className="quiet small">Too large to show here: download it.</p>
                    : peek.binary ? <p className="quiet small">Not a text file: download it.</p>
                      : peek.text != null ? <pre className="fx-preview-text">{peek.text.slice(0, 20000)}</pre> : <p className="quiet small">Loading...</p>}
            </>}
          </aside>)}
      </div>
      {ctx && (
        <ul className="fx-dropdown fx-context" role="menu" style={{ position: "fixed", left: ctx.x, top: ctx.y }} onMouseLeave={() => setCtx(null)}>
          {items.length > 0 && item("Open", () => openItem(one), !one, "Enter")}
          {items.length > 0 && item(items.length > 1 ? `Download ${items.length} as one zip` : "Download", () => download(items))}
          {editItems()}
          {sep("s6")}
          {items.length > 0 && item("Rename", () => rename(one), !one || !!ro, "F2")}
          {items.length > 0 && item("Delete", () => remove(items), !!ro, "Del")}
          {items.length === 0 && item("New folder", newFolder, !!ro)}
          {items.length === 0 && item("New file", newFile, !!ro)}
          {item("Properties", () => showProps(one || null), items.length > 1)}
        </ul>)}
      {props && (
        <Modal title={`Properties: ${props.name}`} onClose={() => setProps(null)} actions={<button onClick={() => setProps(null)}>Close</button>}>
          <table className="grid-table fx-props"><tbody>
            <tr><th>Where</th><td><code>{props.path}</code></td></tr>
            <tr><th>Kind</th><td>{props.kind}</td></tr>
            <tr><th>Size</th><td>{size(props.bytes)}{props.folder ? ` (${props.files} file(s) in ${props.folders} folder(s))` : ""}</td></tr>
            <tr><th>Owner</th><td>{props.owner} (group {props.group})</td></tr>
            <tr><th>Permissions</th><td><code>{props.permissions}</code></td></tr>
            <tr><th>Changed</th><td>{when(props.modified)}</td></tr>
            <tr><th>Last read</th><td>{when(props.accessed)}</td></tr>
            {props.read_only_reason && <tr><th>Writes</th><td className="small">{props.read_only_reason}</td></tr>}
          </tbody></table>
        </Modal>)}
      {file && (
        <div className="card ct-file">
          <h4><code>{file.path}</code> · {file.bytes} bytes <button className="linkish" onClick={() => { setFile(null); setEdit(null); }}>Close</button></h4>
          {file.binary ? <p className="quiet">Not a text file: download it instead.</p>
            : edit == null ? <>
              {!file.read_only_reason && !ro && <button onClick={() => setEdit(file.text)}>Edit</button>}
              {(file.read_only_reason || ro) && <p className="quiet small">Read only: {file.read_only_reason || ro}</p>}
              <pre className="ct-file-text">{file.text}</pre></>
              : <>
                <textarea className="ct-file-edit" value={edit} onChange={(e) => setEdit(e.target.value)} rows={24} aria-label={`Edit ${file.path}`} />
                <button disabled={busy} onClick={async () => { const out = await change({ op: "write", path: file.path, content: edit, sha256: file.sha256 }, `Save your changes to ${file.path}? The file is replaced (the before and after go into the audit trail).`); if (out) viewFile(file); }}>Save</button>
                <button onClick={() => setEdit(null)}>Cancel</button></>}
        </div>)}
    </div>
  );
}
