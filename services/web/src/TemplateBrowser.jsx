// Look through a template library (owner, 8 Nov 2026): folder after folder (phases, then their folders) down to the
// files, each with what it is for and a download. Read only; with onPick it also chooses a template, and what was
// picked shows a tick (with `counts`, how many times: the same template may be picked more than once).
import { useEffect, useMemo, useState } from "react";
import { apiDownload } from "./auth";
import { useApi } from "./ModelViews";
import { Modal } from "./ModelOps";

const nice = (seg) => seg.replace(/^\d+[_ -]*/, "").replaceAll("_", " ") || seg;

// the files as a tree: {name, path, folders: Map, files: [...]}
function tree(files) {
  const root = { name: "", path: "", folders: new Map(), files: [] };
  for (const t of files) {
    let node = root;
    for (const seg of (t.folder || "").split("/").filter(Boolean)) {
      const path = node.path ? `${node.path}/${seg}` : seg;
      if (!node.folders.has(seg)) node.folders.set(seg, { name: seg, path, folders: new Map(), files: [] });
      node = node.folders.get(seg);
    }
    node.files.push(t);
  }
  return root;
}
const countFiles = (n) => n.files.length + [...n.folders.values()].reduce((k, f) => k + countFiles(f), 0);
const byName = (a, b) => a.name.localeCompare(b.name);

function FileRow({ t, showFolder, n, counts, onPick, onDownload }) {
  return (
    <div className={`tb-file${n ? " picked" : ""}`}>
      <span className="tb-name">📄 {t.name}{showFolder && <span className="quiet small"> {t.folder}</span>}</span>
      <span className="small quiet tb-for">{t.item ? `${t.phase} · ${t.item}` : ""}</span>
      <span className="small tb-acts">
        {t.has_file ? <button className="linkish" onClick={() => onDownload(t)}>⬇ Download</button>
          : <span className="quiet" title="Its file is not loaded yet (a Super Admin loads it once)">no file yet</span>}
        {onPick && t.has_file && (n
          ? <><span className="tb-tick" title="Picked">✓ added{counts && n > 1 ? ` ×${n}` : ""}</span>
            {counts && <button className="linkish" onClick={() => onPick(t)}>＋ again</button>}</>
          : <button className="linkish" onClick={() => onPick(t)}>＋ Add</button>)}
      </span>
    </div>
  );
}

export function TemplateBrowser({ libraries, start, onPick, picked = [], counts = null }) {
  const [lib, setLib] = useState(start || libraries[0]?.id || "");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(() => new Set());
  const [msg, setMsg] = useState("");
  const { data, error } = useApi(lib ? `/api/v1/projects/library/libraries/${lib}/templates` : null);
  const all = data?.templates || [];
  const root = useMemo(() => tree(all), [all]);
  // one folder at the top (a library in its folder layout): opened at once, so its phases show
  useEffect(() => {
    if (root.folders.size === 1 && !open.size) setOpen(new Set([[...root.folders.values()][0].path]));
  }, [root]); // eslint-disable-line react-hooks/exhaustive-deps
  const found = q.trim() ? all.filter((t) => `${t.name} ${t.item} ${t.path}`.toLowerCase().includes(q.trim().toLowerCase())) : null;
  const toggle = (path) => { const n = new Set(open); if (n.has(path)) n.delete(path); else n.add(path); setOpen(n); };
  const timesPicked = (t) => (counts ? counts[t.id] || 0 : picked.includes(t.id) ? 1 : 0);
  const pick = onPick ? (t) => onPick({ ...t, library: lib, library_name: data.library.name }) : null;
  const download = (t) => apiDownload(`/api/v1/projects/library/templates/${t.id}/file`, t.name).catch((e) => setMsg(e.message));
  const row = (t, showFolder) => <FileRow key={t.id} t={t} showFolder={showFolder} n={timesPicked(t)} counts={counts} onPick={pick} onDownload={download} />;
  const folder = (node, depth) => {
    const isOpen = open.has(node.path);
    const pickedHere = node.files.filter((t) => timesPicked(t)).length;
    return (
      <div key={node.path} className="tb-folder" style={{ marginLeft: depth ? 18 : 0 }}>
        <button className="linkish tb-folder-name" aria-expanded={isOpen} onClick={() => toggle(node.path)}>
          {isOpen ? "▾" : "▸"} 📁 {nice(node.name)} <span className="small quiet">{countFiles(node)}{pickedHere ? ` · ✓ ${pickedHere}` : ""}</span></button>
        {isOpen && <div className="tb-children">
          {[...node.folders.values()].sort(byName).map((f) => folder(f, depth + 1))}
          {node.files.map((t) => <div key={t.id} style={{ marginLeft: 18 }}>{row(t, false)}</div>)}
        </div>}
      </div>
    );
  };
  return (
    <div className="tpl-browser">
      <div className="row-gap">
        <label>Library <select value={lib} onChange={(e) => { setLib(e.target.value); setOpen(new Set()); }}>
          {libraries.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the library" aria-label="Search the library" />
        {data && <span className="small quiet">{all.length} files</span>}
        {data && !found && open.size > 0 && <button className="linkish small" onClick={() => setOpen(new Set())}>Close all folders</button>}
      </div>
      {error && <p className="status bad">{error}</p>}
      {data?.library.description && <p className="small quiet">{data.library.description}</p>}
      {msg && <p className="status bad small">{msg}</p>}
      {!data ? <p className="quiet">Loading...</p> : (
        <div className="tb-tree">
          {found ? (!found.length ? <p className="quiet small">Nothing matches.</p> : found.map((t) => row(t, true))) : <>
            {[...root.folders.values()].sort(byName).map((f) => folder(f, 0))}
            {root.files.map((t) => row(t, false))}
            {!all.length && <p className="quiet small">This library has no files.</p>}
          </>}
        </div>
      )}
    </div>
  );
}

export function TemplateBrowserDialog({ libraries, start, onClose, onPick, picked, counts, title }) {
  return (
    <Modal title={title || "Look through a template library"} onClose={onClose} wide actions={<button className="primary" onClick={onClose}>Done</button>}>
      <TemplateBrowser libraries={libraries} start={start} onPick={onPick} picked={picked} counts={counts} />
    </Modal>
  );
}
