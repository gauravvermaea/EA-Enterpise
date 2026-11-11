// Drawn views (phases 28 and 29, D354, D355, D387 to D398): a view of a model drawn in draw.io, inside EA Explorer.
// The repository is the truth; the view only shows it. draw.io runs in a frame with EA Explorer's plugin
// (deploy/drawio/eax-plugin.js); the messages both ways are in docs/phase-28.md ("As built: the plugin protocol"), the
// API in "As built: API". Here: the Drawn views list on a model's Views tab, the editor page
// (#/metamodel/<m>/drawn-views/<v>[?version=n]), "Save as a drawn view" and downloads for generated pictures
// (PictureActions), an entity's own icon,
// and the project's drawn views as evidence.
import SearchSelect from "./SearchSelect";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiBlobUrl, apiFetch, apiUpload, canOn, currentUser } from "./auth";
import { Modal } from "./ModelOps";
import { refreshAll, useApi } from "./ModelViews";
import { readOnlyWhy } from "./ModelMarks";
import { EntityFormDialog } from "./DataEntry";
import { fuzzyFilter } from "./names";
import { fmtDateTime } from "./fmt";
import { LinkList } from "./Links";
import { RelationshipAttributes as LineAttributes } from "./RelAttributes";
import { downloadDrawio, downloadPicturePng, downloadPictureSvg, drawioXml, saveBlob } from "./exporting";
import { openInDrawio } from "./drawioScratch";

const go = (path) => { window.location.hash = path; };
// the views themselves are the views service's (D405): list, open, save, versions, rename, delete; what needs the model's
// data (setup, resync, relationships, allowed, generate, heat map, icons, evidence) is the main API's
const store = (model) => `/api/views/v1/models/${model}/drawn-views`;
const base = (model) => `/api/v1/models/${model}/drawn-views`;
const viewUrl = (model, v, version) => `#/metamodel/${model}/drawn-views/${encodeURIComponent(v)}${version ? `?version=${version}` : ""}`;
// a drawn view always opens in a tab of its own, full screen (owner, 10 Nov 2026, D411); the address can be bookmarked
const NEW_TAB = { target: "_blank", rel: "noopener" };
export function openDrawnView(model, v, version) { window.open(viewUrl(model, v, version), "_blank", "noopener"); }

// the stencil groups a person hid (D409): remembered in this browser for that person, never saved in a view
const paletteKey = () => `eax.drawn.palettes.${currentUser()?.preferred_username || "me"}`;
function hiddenPalettes() {
  try { return JSON.parse(window.localStorage.getItem(paletteKey()) || "{}") || {}; } catch { return {}; }
}
function keepHiddenPalettes(show) {
  try { window.localStorage.setItem(paletteKey(), JSON.stringify(show)); } catch { /* private window: this time only */ }
}

// who may draw on this model: the content permission on a model that may change (frozen, archived, locked: read only)
export function mayDraw(model, m) {
  return !!m && canOn(model, "model.content") && !readOnlyWhy(m) && !m.frozen_at && m.lifecycle !== "archived"
    && !["content", "maintenance"].includes(m.lock_level);
}

// ---------------------------------------------------------------- the list, on the model's Views tab
// the Views tab's Custom views (D412): this model's drawn views and its copies of generated views (MV-n), in one list,
// whoever made them; Kind says which, and each has its own actions
export function DrawnViewsSection({ model, m, generated = [], filter = "" }) {
  const { data, error } = useApi(store(model));
  const [dialog, setDialog] = useState(null);       // {kind: "new" | "copy" | "rename" | "delete" | "versions", view}
  const may = mayDraw(model, m);
  const drawn = (data?.views || []).filter((v) => !filter || `${v.name} ${v.description || ""}`.toLowerCase().includes(filter));
  const none = data && !drawn.length && !generated.length;
  return (
    <section className="drawn-views">
      <div className="toolbar">
        <h3 className="vp-group" style={{ margin: 0 }}>Custom views</h3>
        <span className="er-spacer" />
        {may && <button className="primary" onClick={() => setDialog({ kind: "new" })}>+ New drawn view</button>}
      </div>
      {error && <p className="status bad">{error}</p>}
      {none && <p className="quiet">{filter ? "No custom views match." : `No custom views yet.${may ? " Start one with + New drawn view, open a generated picture and choose Save as a drawn view, or copy a standard view." : ""}`}</p>}
      {(drawn.length > 0 || generated.length > 0) && (
        <table className="grid-table drawn-list">
          <thead><tr><th>Name</th><th>Kind</th><th>Version</th><th>Saved</th><th>Shows</th><th /></tr></thead>
          <tbody>
            {drawn.map((v) => (
              <tr key={v.id}>
                <td><a href={viewUrl(model, v.id)} {...NEW_TAB}><b>{v.name}</b></a>
                  {v.model_changed_since && <span className="rag amber" title="The model changed since this version was saved: open it and Resync"> model changed since</span>}
                  {v.placeholders > 0 && <span className="rag off" title="Placeholders on the view still to be realised"> {v.placeholders} placeholder{v.placeholders === 1 ? "" : "s"}</span>}
                  {v.description && <div className="small quiet">{v.description}</div>}</td>
                <td><span className="kind-tag">Drawn</span></td>
                <td>v{v.version}</td>
                <td className="small">{v.saved_by} · {fmtDateTime(v.saved_at)}</td>
                <td>{v.objects} objects</td>
                <td className="row-gap">
                  <a className="button" href={viewUrl(model, v.id)} {...NEW_TAB} title="Opens in a tab of its own, full screen">{may ? "Open ↗" : "Open (read only) ↗"}</a>
                  <button onClick={() => setDialog({ kind: "versions", view: v })}>Versions</button>
                  {may && <button onClick={() => setDialog({ kind: "copy", view: v })}>Copy</button>}
                  {may && <button onClick={() => setDialog({ kind: "rename", view: v })}>Rename</button>}
                  {may && <button onClick={() => setDialog({ kind: "delete", view: v })}>Delete</button>}
                </td>
              </tr>
            ))}
            {generated.map((v) => (
              <tr key={v.id || v.code}>
                <td><a href={`#/metamodel/${model}/views/${encodeURIComponent(v.code)}`}><b>{v.name}</b></a> <span className="quiet small">{v.code}</span>
                  {v.copied_from && <span className="vp-source" title={`Copied from ${v.copied_from}`}> from {v.copied_from}</span>}
                  {(v.concerns || v.purpose) && <div className="small quiet">{v.concerns || v.purpose}</div>}</td>
                <td><span className="kind-tag">Generated</span></td>
                <td>—</td>
                <td className="small">{v.modified_by || v.created_by || ""}{v.modified_at || v.created_at ? ` · ${fmtDateTime(v.modified_at || v.created_at)}` : ""}</td>
                <td>{(v.element_types || []).length} element types</td>
                <td className="row-gap">
                  <a className="button" href={`#/metamodel/${model}/views/${encodeURIComponent(v.code)}`} title="Diagram, catalog, heat map, matrix or relationships; change or delete it there">Open</a>
                  <a className="button" href={`#/metamodel/${model}/views/${encodeURIComponent(v.code)}/diagram`}>Diagram</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {dialog && ["new", "copy"].includes(dialog.kind) && <NewDrawnView model={model} views={data?.views || []} copy={dialog.view} onClose={() => setDialog(null)} />}
      {dialog?.kind === "rename" && <RenameDrawnView model={model} v={dialog.view} onClose={() => setDialog(null)} />}
      {dialog?.kind === "delete" && <DeleteDrawnView model={model} v={dialog.view} onClose={() => setDialog(null)} />}
      {dialog?.kind === "versions" && <VersionsDialog model={model} v={dialog.view} may={may} onClose={() => setDialog(null)} />}
    </section>
  );
}

export function NewDrawnView({ model, views, copy, onClose, xml, source, sourceNote, sameTab = false, onSaved }) {
  const [name, setName] = useState(copy ? `${copy.name} (copy)` : sourceNote || "");
  const [description, setDescription] = useState(copy?.description || "");
  const [from, setFrom] = useState(copy?.id || "");
  const [version, setVersion] = useState("");
  const vers = useApi(from && !xml ? `${store(model)}/${from}/versions` : null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  async function create() {
    setBusy(true); setMsg("");
    const tab = sameTab ? null : window.open("about:blank", "_blank");     // sameTab: from a scratch view (D585)
    try {
      const body = { name: name.trim(), description };
      if (xml) Object.assign(body, { xml, source: source || "generated", source_note: sourceNote || "" });
      else if (from) Object.assign(body, { copy_from: from, ...(version ? { copy_version: Number(version) } : {}) });
      const out = await apiFetch(store(model), { method: "POST", body: JSON.stringify(body) });
      refreshAll();
      onSaved?.(out);
      onClose();
      if (tab) tab.location.href = new URL(viewUrl(model, out.id), window.location.href).href;
      else go(viewUrl(model, out.id).slice(1));
    } catch (e) { if (tab) tab.close(); setMsg(e.message); setBusy(false); }
  }
  return (
    <Modal title={xml ? "Save as a drawn view" : copy ? `Copy ${copy.name}` : "New drawn view"} onClose={onClose}
      actions={<><button className="ed-btn" disabled={busy || !name.trim()} onClick={create}>{xml ? "Save and open" : "Create and open"}</button>
        <button className="ed-btn secondary" onClick={onClose}>Cancel</button></>}>
      {xml && <p className="quiet">The picture becomes a drawn view, keeping its layout: its objects are bound to the model's entities and its lines to their relationships.</p>}
      <label className="ed-field">Name<input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <label className="ed-field">Description<textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} /></label>
      {!xml && <>
        <label className="ed-field">Start from
          <select value={from} onChange={(e) => { setFrom(e.target.value); setVersion(""); }}>
            <option value="">An empty view</option>
            {views.map((v) => <option key={v.id} value={v.id}>A copy of {v.name}</option>)}
          </select></label>
        {from && <label className="ed-field">Version
          <select value={version} onChange={(e) => setVersion(e.target.value)}>
            <option value="">The latest</option>
            {(vers.data?.versions || []).map((x) => <option key={x.version} value={x.version}>v{x.version} · {x.saved_by} · {fmtDateTime(x.saved_at)}{x.note ? ` · ${x.note}` : ""}</option>)}
          </select></label>}
      </>}
      {msg && <p className="status bad">{msg}</p>}
    </Modal>
  );
}

function RenameDrawnView({ model, v, onClose }) {
  const [name, setName] = useState(v.name);
  const [description, setDescription] = useState(v.description || "");
  const [msg, setMsg] = useState("");
  async function save() {
    try { await apiFetch(`${store(model)}/${v.id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim(), description }) }); refreshAll(); onClose(); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <Modal title={`Rename ${v.name}`} onClose={onClose}
      actions={<><button className="ed-btn" disabled={!name.trim()} onClick={save}>Save</button><button className="ed-btn secondary" onClick={onClose}>Cancel</button></>}>
      <label className="ed-field">Name<input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <label className="ed-field">Description<textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} /></label>
      {msg && <p className="status bad">{msg}</p>}
    </Modal>
  );
}

function DeleteDrawnView({ model, v, onClose }) {
  const [msg, setMsg] = useState("");
  async function del() {
    try { await apiFetch(`${store(model)}/${v.id}`, { method: "DELETE" }); refreshAll(); onClose(); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <Modal title={`Delete ${v.name}?`} onClose={onClose}
      actions={<><button className="ed-btn danger" onClick={del}>Delete the view</button><button className="ed-btn secondary" onClick={onClose}>Cancel</button></>}>
      <p>The drawn view goes from the list. Its versions are kept, and nothing in the model changes: entities and
        relationships are never deleted from a view.</p>
      {msg && <p className="status bad">{msg}</p>}
    </Modal>
  );
}

function VersionsDialog({ model, v, may, onClose, current }) {
  const { data, error } = useApi(`${store(model)}/${v.id}/versions`);
  return (
    <Modal wide title={`Versions of ${v.name}`} onClose={onClose} actions={<button className="ed-btn secondary" onClick={onClose}>Close</button>}>
      <p className="quiet">Each save is kept. An older version opens read only; {may ? "from there, Restore as a new version saves it as the latest." : "you may not change this view."}</p>
      {error && <p className="status bad">{error}</p>}
      {data && (
        <table className="grid-table">
          <thead><tr><th>Version</th><th>Saved by</th><th>When</th><th>Note</th><th /></tr></thead>
          <tbody>{data.versions.map((x, i) => (
            <tr key={x.version} className={x.version === current ? "skill-me" : undefined}>
              <td>v{x.version}{i === 0 ? " (latest)" : ""}</td><td>{x.saved_by}</td><td className="small">{fmtDateTime(x.saved_at)}</td><td className="small">{x.note}</td>
              <td><a className="button" href={viewUrl(model, v.id, i === 0 ? null : x.version)} {...NEW_TAB} onClick={onClose}>Open ↗</a></td>
            </tr>))}</tbody>
        </table>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- the editor
const EMPTY = '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>';
const STRUCTURAL = ["Composition", "Aggregation", "Assignment", "Realization"];
const stencilKey = () => `eax.drawn.stencilSize.${currentUser()?.preferred_username || "me"}`;
const STENCIL_SIZES = [["small", "Small"], ["medium", "Medium"], ["large", "Large"]];
function stencilSize() {
  try { const v = window.localStorage.getItem(stencilKey()); return STENCIL_SIZES.some(([k]) => k === v) ? v : "medium"; } catch { return "medium"; }
}
function keepStencilSize(v) {
  try { window.localStorage.setItem(stencilKey(), v); } catch { /* private window: this time only */ }
}
// the search panel's types by domain, in the stencil's order (D412): the setup's domains and its type order, extensions last
function typeGroups(setup) {
  const ts = Object.entries(setup?.types || {});
  const ds = setup?.domains?.length ? setup.domains : [...new Set(ts.map(([, t]) => t.domain || "Other"))];
  return ds.map((d) => [d, ts.filter(([, t]) => (t.domain || "Other") === d).sort((a, b) => (a[1].extension ? 1 : 0) - (b[1].extension ? 1 : 0))])
    .filter(([, x]) => x.length);
}
// the stencil dialog's groups matching a search (D540): a group by its own name, or by the names of the types in it
function paletteMatches(groups, setup, q) {
  if (!q.trim()) return groups.map((g) => [g, []]);
  const ts = Object.values(setup?.types || {});
  return groups.map((g) => {
    const hits = fuzzyFilter(ts.filter((t) => (t.domain || "Other") === g), q, (t) => t.name, () => "").map((t) => t.name);
    return [g, hits, fuzzyFilter([g], q, (x) => x, () => "").length > 0];
  }).filter(([, hits, self]) => self || hits.length).map(([g, hits]) => [g, hits]);
}

// the types as SearchSelect options (D540): by domain, extensions marked; codes limits them (a placeholder's family)
function typeOptions(setup, codes = null) {
  const out = typeGroups(setup).flatMap(([d, ts]) => ts.map(([c, t]) => ({ value: c, label: `${t.name}${t.extension ? " (extension)" : ""}`, group: d })));
  if (!codes) return out;
  const known = out.filter((o) => codes.includes(o.value));
  return [...known, ...codes.filter((c) => !known.some((o) => o.value === c)).map((c) => ({ value: c, label: setup?.types?.[c]?.name || c }))];
}
const boundIds = (xml) => [...new Set([...String(xml || "").matchAll(/\bea_id="([^"]+)"/g)].map((x) => x[1]))];

// the working space (owner, 10 Nov 2026, D420): the stencil on the left, a bottom panel of tabs, each pinned or unpinned;
// three preset layouts; the person's preset, pins and sizes are remembered in this browser for that person
const PRESETS = { drawing: { stencil: true, bottom: false }, editing: { stencil: true, bottom: true }, canvas: { stencil: false, bottom: false } };
const PRESET_NAMES = [["drawing", "Drawing"], ["editing", "Editing"], ["canvas", "Canvas only"]];
const BOTTOM_MIN = 120;
const LAYOUT_DEFAULT = { preset: "editing", ...PRESETS.editing, height: 260, stencilWidth: 0, lineAttrs: true };
const layoutKey = () => `eax.drawn.layout.${currentUser()?.preferred_username || "me"}`;
function savedLayout() {
  try {
    const v = JSON.parse(window.localStorage.getItem(layoutKey()) || "null");
    if (v && PRESETS[v.preset]) return { ...LAYOUT_DEFAULT, ...v, height: Math.max(BOTTOM_MIN, Number(v.height) || LAYOUT_DEFAULT.height) };
  } catch { /* private window: the default */ }
  return LAYOUT_DEFAULT;
}
function keepLayout(l) {
  try { window.localStorage.setItem(layoutKey(), JSON.stringify(l)); } catch { /* private window: this time only */ }
}
const BOTTOM_TABS = [["find", "Find in the model"], ["props", "Properties"], ["rels", "Relationships"], ["allowed", "Allowed relationships"], ["unc", "Uncommitted changes"]];

// the drawn view in its own tab, full screen: no EA Explorer header or menus (D411)
export function DrawnViewFullScreen({ model, view, route }) {
  const { data: m, error } = useApi(`/api/v1/models/${model}`);
  useEffect(() => { document.body.classList.add("drawn-full-body"); return () => document.body.classList.remove("drawn-full-body"); }, []);
  if (error) return <div className="drawn-full"><p className="status bad">{error}</p></div>;
  if (!m) return <div className="drawn-full"><p className="quiet">Opening the drawn view...</p></div>;
  return (
    <div className="drawn-full">
      <DrawnViewPage key={`${view}${route.split("?")[1] || ""}`} model={model} m={m} view={view} full />
    </div>
  );
}

export function DrawnViewPage({ model, m, view, full = false }) {
  const askedVersion = Number((/[?&]version=(\d+)/.exec(window.location.hash) || [])[1] || 0) || null;
  const [info, setInfo] = useState(null);
  useEffect(() => { if (full && info?.name) document.title = `${info.name} · ${m?.name || "drawn view"} · EA Explorer`; }, [full, info?.name, m?.name]);
  const [error, setError] = useState("");
  const [setup, setSetup] = useState(null);
  const frame = useRef(null);
  const st = useRef({ ready: false, loaded: false, setupSent: false, xml: "", pending: null });
  const [phase, setPhase] = useState("starting");           // starting, ready
  const [dirty, setDirty] = useState(false);
  const [placeholders, setPlaceholders] = useState(0);
  const [phList, setPhList] = useState(null);
  const [toast, setToast] = useState(null);                 // {ok, text}
  const [conflict, setConflict] = useState(null);
  const [changedBanner, setChangedBanner] = useState(false);
  const [dlg, setDlg] = useState(null);                     // a dialog: {kind, ...}
  const [selected, setSelected] = useState(null);           // what the plugin says is selected: entity, placeholder or line
  const [details, setDetails] = useState({});               // entity id -> its detail (attributes, relationships), while open
  const [hiddenList, setHiddenList] = useState(null);
  const [heat, setHeat] = useState(null);                   // {attribute, legend, colours}
  const [panel, setPanel] = useState({ q: "", type: "", bindTo: null });
  const [dragging, setDragging] = useState(null);           // the entity being dragged from the search panel
  const [saving, setSaving] = useState(false);
  const [groups, setGroups] = useState([]);                 // the stencil's groups (D409)
  const [palQ, setPalQ] = useState("");                     // the stencil dialog's search (D540)
  const [shown, setShown] = useState(hiddenPalettes);       // {group: false} for each hidden one
  const [size, setSize] = useState(stencilSize);            // the stencil's item size (D412)
  const [pend, setPend] = useState(null);                   // the person's uncommitted changes in the model: {changes, count, may_commit} (D413)
  const [note, setNote] = useState(null);                   // "Updated since last saved: ..." when opened (D413)
  const [layout, setLayout] = useState(savedLayout);        // preset, pins and sizes (D420)
  const [stencilOver, setStencilOver] = useState(false);    // an unpinned stencil opened for a while
  const [bottomOver, setBottomOver] = useState(false);      // an unpinned bottom panel opened over the drawing
  const [tab, setTab] = useState("find");
  const old = !!(info && askedVersion && askedVersion < info.latest_version);
  const readOnly = !setup || setup.readOnly || old;
  const committer = !!pend?.may_commit;                     // makes and changes entities from the drawing (D413)

  const say = (text, ok = true) => setToast({ text, ok, at: Date.now() });
  const post = useCallback((msg) => { frame.current?.contentWindow?.postMessage(JSON.stringify(msg), "*"); }, []);

  // the view and the plugin's setup
  useEffect(() => {
    let live = true;
    apiFetch(`${store(model)}/${encodeURIComponent(view)}${askedVersion ? `?version=${askedVersion}` : ""}`)
      .then((v) => { if (live) { setInfo(v); setChangedBanner(!!v.model_changed_since); } }).catch((e) => live && setError(e.message));
    apiFetch(`${base(model)}/setup?view=${encodeURIComponent(view)}`).then((s) => live && setSetup(s)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model, view, askedVersion]);

  const { data: entities } = useApi(`/api/v1/models/${model}/entity-list`);
  const typeByName = useMemo(() => Object.fromEntries(Object.entries(setup?.types || {}).map(([code, t]) => [t.name, code])), [setup]);

  const trySetup = useCallback(() => {
    const s = st.current;
    if (!s.ready || !s.loaded || s.setupSent || !setup || !info) return;
    s.setupSent = true;
    post({ ...setup, readOnly: setup.readOnly || old, title: info.name });
    setPhase("ready");
  }, [setup, info, old, post]);
  useEffect(() => { trySetup(); }, [trySetup]);

  // leaving with unsaved changes
  useEffect(() => {
    const before = (e) => { if (st.current.dirty) { e.preventDefault(); e.returnValue = ""; } };
    const here = window.location.hash;
    const onHash = () => {
      if (st.current.dirty && !st.current.leaving && !window.confirm("The drawn view has changes that are not saved. Leave anyway?")) {
        st.current.leaving = true; window.location.hash = here; setTimeout(() => { st.current.leaving = false; }, 0);
      }
    };
    window.addEventListener("beforeunload", before);
    window.addEventListener("hashchange", onHash);
    return () => { window.removeEventListener("beforeunload", before); window.removeEventListener("hashchange", onHash); };
  }, []);
  useEffect(() => { st.current.dirty = dirty; }, [dirty]);

  async function saveXml(xml, force = false, note = "") {
    if (readOnly) return;
    setSaving(true);
    try {
      const out = await apiFetch(`${store(model)}/${encodeURIComponent(view)}`, { method: "PUT",
        body: JSON.stringify({ xml, base_version: info.version, note, force }) });
      setInfo((i) => ({ ...i, version: out.version, latest_version: out.version, summary: out.summary }));
      setDirty(false); setConflict(null);
      say(out.warning ? `${out.message} ${out.warning}` : out.message || `Saved as version ${out.version}.`, !out.warning);
      refreshAll();
      return out;
    } catch (e) {
      if (e.status === 409 && e.body?.errors?.conflict) setConflict({ ...e.body.errors.conflict, xml, note });
      else say(e.message, false);
    } finally { setSaving(false); }
  }

  // ---------------------------------------------------------------- what the plugin and draw.io say
  useEffect(() => {
    async function handle(ev) {
      if (!frame.current || ev.source !== frame.current.contentWindow) return;
      let msg; try { msg = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data; } catch { return; }
      if (!msg || !msg.event) return;
      const s = st.current;
      switch (msg.event) {
        case "configure": post({ action: "configure", config: { defaultLibraries: "", enabledLibraries: [], compressXml: false } }); break;
        case "init": s.initWaiting = true; sendLoad(); break;
        case "load": s.loaded = true; trySetup(); break;
        case "eax-ready": s.ready = true; trySetup(); break;
        case "autosave": s.xml = msg.xml; break;
        case "save": s.xml = msg.xml; saveXml(msg.xml); break;
        case "export": if (s.exportWaiting) { const f = s.exportWaiting; s.exportWaiting = null; f(msg.data); } break;
        case "eax-setup-done": {
          s.settleUntil = Date.now() + 2000; setDirty(false);
          setGroups(msg.groups || []);
          const show = hiddenPalettes();
          if (Object.keys(show).length) post({ eax: "palettes", show });
          post({ eax: "stencil-size", size: stencilSize() });
          post({ eax: "line-labels", attrs: layout.lineAttrs !== false });
          checkPending();
          if (!old) resync(true);         // the model as it is now (D413): names, new relationships, deletions, commits
          break;
        }
        case "eax-changed":           // restyling what the file holds, just after setup, is not a change of the person's
          setPlaceholders(msg.placeholders || 0);
          if (!s.settleUntil || Date.now() > s.settleUntil) setDirty(!!msg.dirty);
          clearTimeout(s.pendTimer); s.pendTimer = setTimeout(checkPending, 800);
          break;
        case "eax-refused": say(msg.reason, false); break;
        case "eax-placed": setDirty(true); break;
        case "eax-bound": setDirty(true); setPanel((p) => ({ ...p, bindTo: null })); setDetails((d) => { const n = { ...d }; delete n[msg.entity]; return n; }); break;
        case "eax-relationship": relationshipDrawn(msg); break;
        case "eax-undo-note": say(msg.text); break;
        case "eax-undo-back": resync(false, true); break;      // an object back by redo or undo: its lines drawn again
        case "eax-add-relationship": setDlg({ kind: "add-rel", ...msg }); break;
        case "eax-junction-new": makeJunction(msg); break;
        case "eax-nest": nest(msg); break;
        case "eax-choose":            // right-click Choose instance / Change instance: the properties panel's chooser
          setSelected((x) => ({ ...(x && x.cell === msg.cell ? x : { cell: msg.cell, type: msg.type, placeholder: true }), choosing: Date.now() }));
          break;
        case "eax-open": window.open(`#/metamodel/${model}/entity/${msg.entity}`, "_blank"); break;
        case "eax-selected": setSelected(msg.cell && (msg.entity || msg.relationship || msg.placeholder || msg.relType) ? msg : null); break;
        case "eax-hidden": case "eax-shown": post({ eax: "hidden" }); break;
        case "eax-hidden-list": setHiddenList(msg.hidden || []); showTab("props"); break;
        case "eax-placeholders": setPhList(msg.list || []); showTab("props"); break;
        case "eax-resynced": {
          setDetails({});
          const parts = [msg.renamed && `${msg.renamed} renamed`, msg.added && `${msg.added} relationship${msg.added === 1 ? "" : "s"} drawn`,
            msg.deleted && `${msg.deleted} marked as deleted in the model`, msg.committed && `${msg.committed} now committed`].filter(Boolean);
          if (msg.auto) {                 // on opening: a note, and the view is changed only if something changed (D413)
            if (parts.length) { setNote(`Updated since last saved: ${parts.join(", ")}.`); setDirty(true); }
          } else if (msg.quiet) { if (msg.added) setDirty(true); }
          else say(parts.length ? `Brought up to date: ${parts.join(", ")}.` : "The view was up to date with the model.");
          break;
        }
        case "eax-line-deleted": setDlg({ kind: "line-del", rel: msg.relationship }); break;
        case "eax-rel-rename": renameLine(msg); break;
        case "eax-dropped": setDlg({ kind: "drop", ...msg }); break;
        case "eax-waiting-line": makeWaiting(msg); break;
        case "eax-related-added": if (!msg.already) setDirty(true); break;
        case "eax-stencil-width": changeLayout({ stencilWidth: msg.width }); break;
        case "eax-canvas-click": setStencilOver(false); setBottomOver(false); break;
        default: break;
      }
    }
    function sendLoad() {
      const s = st.current;
      if (!info || !s.initWaiting) return;
      s.initWaiting = false;
      s.xml = info.xml || "";
      post({ action: "load", xml: info.xml || EMPTY, autosave: 1, title: info.name });
    }
    st.current.sendLoad = sendLoad;
    window.addEventListener("message", handle);
    return () => window.removeEventListener("message", handle);
  });
  useEffect(() => { st.current.sendLoad?.(); }, [info]);
  // the stencil (draw.io's left sidebar) pinned, opened for a while, or folded away (D420)
  useEffect(() => {
    if (phase !== "ready") return;
    post({ eax: "stencil-panel", open: !readOnly && (layout.stencil || stencilOver), width: layout.stencilWidth || 0 });
  }, [phase, layout.stencil, stencilOver, readOnly, post]);

  // Ctrl+Z, Ctrl+Y and Ctrl+Shift+Z pressed in this page (after a pop-up or a panel had the focus): the drawing's undo
  // and redo, as if pressed on the canvas (owner, 10 Nov 2026); never while typing in a field or with a pop-up open
  useEffect(() => {
    if (phase !== "ready" || readOnly) return undefined;
    function key(e) {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      const k = (e.key || "").toLowerCase();
      if (k !== "z" && k !== "y") return;
      const t = e.target;
      if (t && (t.isContentEditable || (t.closest && t.closest("input, textarea, select, [contenteditable='true']")))) return;
      if (document.querySelector(".ed-backdrop")) return;
      e.preventDefault();
      post({ eax: k === "y" || e.shiftKey ? "redo" : "undo" });
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [phase, readOnly, post]);

  // ---------------------------------------------------------------- answers the plugin waits for
  async function makeJunction(msg) {
    const kind = msg.kind === "and" ? "And" : "Or";
    try {
      const out = await changeNow(model, "entity.create", { data: { entity_type: "Junction", name: `${kind} junction`, values: { JunctionKind: kind } } }, info?.name);
      const id = out.id || out.entity?.id;
      post({ eax: "junction-bound", cell: msg.cell, id });
      say(`An ${kind} junction is in the model now (committed).`);
    } catch (e) { say(`The junction could not be made: ${e.message}`, false); }
  }
  // a line drawn between two objects (owner, 10 Nov 2026): the relationship the model already has between these two
  // entities is shown, never a second one; with one type possible and it there, the line simply shows it
  async function relationshipDrawn(msg) {
    if (!msg.junction) {
      try {
        const r = await apiFetch(`${base(model)}/relationships-of`, { method: "POST", body: JSON.stringify({ entity: msg.source, others: [msg.target] }) });
        const existing = (r.relationships || []).filter((y) => y.source === msg.source && y.target === msg.target && (msg.options || []).includes(y.type));
        if (existing.length && (msg.options || []).length === 1) {
          const x = existing[0];
          post({ eax: "rel", cell: msg.cell, type: x.type, id: x.id, name: x.name || "", pending: !x.committed });
          setDirty(true);
          say("Shown the existing relationship.");
          return;
        }
        if (existing.length) { setDlg({ kind: "rel", ...msg, existing }); return; }
      } catch { /* asked as usual */ }
    }
    setDlg({ kind: "rel", ...msg });
  }
  async function nest(msg) {
    try {
      const r = await apiFetch(`${base(model)}/relationships-of`, { method: "POST", body: JSON.stringify({ entity: msg.entity, others: [msg.parent] }) });
      const has = (r.relationships || []).some((x) => STRUCTURAL.includes(x.type)
        && ((x.source === msg.parent && x.target === msg.entity) || (x.source === msg.entity && x.target === msg.parent)));
      const child = r.entity || {};
      if (has || (child.parent && child.parent === msg.parent)) { post({ eax: "nest-ok", cell: msg.cell }); return; }
      const a = await apiFetch(`${base(model)}/allowed?source=${msg.parent}&target=${msg.entity}`);
      const options = (a.allowed || []).filter((x) => STRUCTURAL.includes(x.code));
      if (!options.length) {
        post({ eax: "nest-refused", cell: msg.cell, reason: `Nothing in the metamodel lets ${a.source_type} contain ${a.target_type}.` });
        return;
      }
      setDlg({ kind: "nest", ...msg, options, view: info?.name });
    } catch (e) { post({ eax: "nest-refused", cell: msg.cell, reason: e.message }); }
  }

  // the Uncommitted changes button (D413): all the person's uncommitted changes in this model, to edit, discard or commit
  async function checkPending() {
    if (readOnly) return;
    try {
      const c = await apiFetch(`/api/v1/models/${model}/changes`);
      const changes = (c.mine || []).flatMap((x) => x.changes || []);
      setPend({ changes, count: changes.length, may_commit: !!c.may_commit, uses_commits: c.uses_commits });
    } catch { setPend(null); }
  }

  // while open (D413): the model's last change, every 30 seconds and when the tab comes back; changed, the banner and Resync
  useEffect(() => {
    if (old) return undefined;
    let live = true;
    const look = (mine = false) => apiFetch(`${base(model)}/access`).then((a) => {
      if (!live) return;
      const s = st.current;
      if (!mine && s.mark && a.marker && a.marker !== s.mark) setChangedBanner(true);
      s.mark = a.marker || s.mark;
    }).catch(() => {});
    st.current.mineChanged = () => look(true);     // the person's own changes from the view are no news to them
    look(true);
    const t = setInterval(() => look(), 30000);
    const onFocus = () => look();
    window.addEventListener("focus", onFocus);
    return () => { live = false; clearInterval(t); window.removeEventListener("focus", onFocus); };
  }, [model, old]);

  // a line renamed in place on the canvas (D565): the name only, in the model at once as the person (D413); refused,
  // the line gets the model's name back
  async function renameLine(msg) {
    try {
      await changeNow(model, "relationship.rename", { relationship: msg.relationship, name: msg.name || "" }, info?.name);
      setDetails({});
      say(`Renamed: ${msg.name || "(no name)"}. The relationship's type stays.`);
    } catch (err) {
      post({ eax: "rel-name", id: msg.relationship, name: msg.previous || "" });
      say(err.message, false);
    }
  }
  // a line's name and attribute values saved from the Properties panel (D563): the label follows at once
  async function saveLine(id, data) {
    const out = await changeNow(model, "relationship.rename", { relationship: id, ...data }, info?.name);
    const r = out?.result || out || {};
    if ("name" in data) post({ eax: "rel-name", id, name: data.name || "" });
    if (r.values) post({ eax: "rel-values", values: { [id]: r.values } });
    else resync(false, true);
    setDirty(true);
    return r;
  }
  async function resync(auto = false, quietly = false) {
    try {
      const r = await apiFetch(`${base(model)}/resync`, { method: "POST", body: JSON.stringify(st.current.xml ? { xml: st.current.xml } : { view }) });
      const ents = Object.fromEntries(Object.entries(r.entities || {}).map(([id, e]) => [id, { name: e.name, type: e.type, icon: e.icon || null }]));
      const rels = [...(r.relationships || []), ...(r.new_relationships || [])];
      const seen = new Set();
      post({ eax: "resync", auto: auto === true, quiet: quietly === true, entities: ents, deleted: [...(r.deleted_entities || []), ...(r.missing_entities || [])],
        relationships: rels.filter((x) => !seen.has(x.id) && seen.add(x.id)).map((x) => ({ id: x.id, type: x.type, source: x.source, target: x.target, name: x.name || "", values: x.values || {}, pending: !x.committed })),
        deletedRelationships: r.gone_relationships || [] });
      setChangedBanner(false);
      st.current.mineChanged?.();
      setTimeout(checkPending, 300);
    } catch (e) { say(e.message, false); }
  }

  async function place(entity, at) {
    const others = boundIds(st.current.xml).filter((x) => x !== entity.id);
    let relationships = [];
    try {
      const r = await apiFetch(`${base(model)}/relationships-of`, { method: "POST", body: JSON.stringify({ entity: entity.id, others }) });
      relationships = (r.relationships || []).map((x) => ({ id: x.id, type: x.type, source: x.source, target: x.target, name: x.name || "", pending: !x.committed }));
      if (r.entity?.icon) entity = { ...entity, icon: r.entity.icon };
    } catch { /* placed without its lines; Resync draws them */ }
    if (at) post({ eax: "place-at-pointer", entity, clientX: at.x, clientY: at.y, relationships });
    else post({ eax: "place", entity, at: { x: 40 + Math.random() * 200, y: 40 + Math.random() * 120 }, relationships });
  }
  // a placeholder realised (or a shape shown as another entity of its type): bound, and the model's relationships with
  // what is on the view drawn, as when placing
  async function realise(cell, entity) {
    const others = boundIds(st.current.xml).filter((x) => x !== entity.id);
    let relationships = [];
    try {
      const r = await apiFetch(`${base(model)}/relationships-of`, { method: "POST", body: JSON.stringify({ entity: entity.id, others }) });
      relationships = (r.relationships || []).map((x) => ({ id: x.id, type: x.type, source: x.source, target: x.target, name: x.name || "", pending: !x.committed }));
      if (r.entity?.icon) entity = { ...entity, icon: r.entity.icon };
    } catch { /* bound without its lines; Resync draws them */ }
    post({ eax: "bind", cell, entity, relationships });
  }
  function pick(e) {
    const code = typeByName[e.entity_type];
    if (!code) { say(`${e.entity_type} has no look on drawn views in this metamodel.`, false); return; }
    const entity = { id: e.id, name: e.name, type: code };
    if (panel.bindTo) {
      if (panel.type && code !== panel.type) { say(`The placeholder is a ${setup.types[panel.type]?.name}; choose one of those.`, false); return; }
      realise(panel.bindTo, entity);
    } else place(entity);
  }

  async function exportAs(format, asShown) {
    const heatOn = heat && !asShown;
    if (heatOn) post({ eax: "heat-off" });
    const data = await new Promise((resolve) => { st.current.exportWaiting = resolve; post({ action: "export", format: format === "pdf" ? "png" : format }); });
    if (heatOn) post({ eax: "heat", colours: heat.colours });
    return data;
  }
  async function download(format, asShown = false) {
    const name = (info?.name || "drawn view").replace(/[\\/:*?"<>|]+/g, "-");
    if (format === "drawio") { saveBlob(new Blob([st.current.xml || info.xml || ""], { type: "application/xml" }), `${name}.drawio`); return; }
    const data = await exportAs(format, asShown);
    const blob = format === "pdf" ? await pngToPdf(data) : dataUriToBlob(data);
    saveBlob(blob, `${name}.${format}`);
  }

  // ---------------------------------------------------------------- the working space (D420)
  function showTab(k) { setTab(k); if (!layout.bottom) setBottomOver(true); }
  function changeLayout(ch) {
    setLayout((l) => { const n = { ...l, ...ch }; keepLayout(n); return n; });
  }
  function choosePreset(p) {
    setStencilOver(false); setBottomOver(false);
    changeLayout({ preset: p, ...PRESETS[p] });
  }
  function startResize(e) {
    e.preventDefault();
    const el = e.currentTarget;
    try { el.setPointerCapture(e.pointerId); } catch { /* an old browser */ }
    const y0 = e.clientY, h0 = layout.height;
    const max = Math.max(160, Math.round(window.innerHeight * 0.7));
    const move = (ev) => setLayout((l) => ({ ...l, height: Math.min(max, Math.max(BOTTOM_MIN, h0 + (y0 - ev.clientY))) }));
    const up = () => {
      el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up);
      setLayout((l) => { keepLayout(l); return l; });
    };
    el.addEventListener("pointermove", move); el.addEventListener("pointerup", up);
  }
  const tabShown = (k) => k !== "unc" || !readOnly;
  function tabLabel(k, l) {
    if (k === "unc") return uncommittedLabel(pend);
    if (k === "rels" && selected?.entity && details[selected.entity]?.relationships) return `${l} (${details[selected.entity].relationships.length})`;
    return l;
  }
  // the Relationships tab: the related entity next to the selected object, with the relationship's line (D420)
  async function addRelated(r) {
    if (!selected?.cell || !selected.entity) return;
    const type = typeByName[r.other_type];
    if (!type) { say(`${r.other_type} has no look on drawn views in this metamodel.`, false); return; }
    const out = r.direction === "outgoing";
    const rel = { id: r.id, type: r.relationship_type_code, source: out ? selected.entity : r.other_id, target: out ? r.other_id : selected.entity,
      name: r.name || "", pending: false };
    let entity = { id: r.other_id, name: r.other_name, type };
    let relationships = [];
    try {
      const others = boundIds(st.current.xml).filter((x) => x !== r.other_id);
      const x = await apiFetch(`${base(model)}/relationships-of`, { method: "POST", body: JSON.stringify({ entity: r.other_id, others }) });
      relationships = (x.relationships || []).map((y) => ({ id: y.id, type: y.type, source: y.source, target: y.target, name: y.name || "", pending: !y.committed }));
      const me = relationships.find((y) => y.id === r.id);
      if (me) rel.pending = me.pending;
      if (x.entity?.icon) entity = { ...entity, icon: x.entity.icon };
    } catch { /* drawn without its other lines; Resync draws them */ }
    post({ eax: "add-related", cell: selected.cell, near: selected.entity, entity, relationship: rel, relationships });
  }
  // the Allowed relationships tab: a placeholder of the other type, joined by a line waiting for it; then the drop pop-up
  function addAllowed(rel, types, outgoing) {
    if (!selected?.cell || !types.length) return;
    post({ eax: "add-allowed", cell: selected.cell, near: selected.entity, type: types[0], types, rel, outgoing });
  }
  // a waiting line whose placeholder is bound or created: the relationship, in the model at once (D413)
  async function makeWaiting(msg) {
    const label = setup?.relationshipTypes?.[msg.type]?.name || msg.type;
    try {
      const out = await changeNow(model, "relationship.create", { data: { source: msg.source, target: msg.target, relationship_type: msg.type, name: "" } }, info?.name);
      post({ eax: "rel", cell: msg.cell, type: msg.type, id: out.id || out.relationship?.id, name: out.name ?? out.relationship?.name ?? "", pending: false });
      setDirty(true); refreshAll(); setDetails({}); st.current.mineChanged?.();
      say(`The ${label} relationship is in the model now (committed).`);
    } catch (e) {
      if (e.status === 409 && /already have/.test(e.message)) {
        const r = await apiFetch(`${base(model)}/relationships-of`, { method: "POST", body: JSON.stringify({ entity: msg.source, others: [msg.target] }) }).catch(() => null);
        const x = (r?.relationships || []).find((y) => y.type === msg.type && y.source === msg.source && y.target === msg.target);
        if (x) { post({ eax: "rel", cell: msg.cell, type: msg.type, id: x.id, name: x.name || "", pending: !x.committed }); setDirty(true); say("Shown the existing relationship."); return; }
      }
      post({ eax: "waiting-cancel", cell: msg.cell });
      say(`The ${label} relationship could not be made: ${e.message}`, false);
    }
  }
  function bottomPanel(over) {
    const sel = selected;
    return (
      <section className={`drawn-bottom${over ? " over" : ""}`} style={{ height: layout.height }} aria-label="Find, properties and changes">
        <div className="drawn-tabs" role="tablist">
          {BOTTOM_TABS.filter(([k]) => tabShown(k)).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : undefined}
              onClick={() => { setTab(k); if (k === "unc") checkPending(); }}>{tabLabel(k, l)}</button>))}
          <span className="er-spacer" />
          <button className={`drawn-pin${layout.bottom ? "" : " off"}`} aria-label={layout.bottom ? "Unpin the panel" : "Pin the panel"}
            title={layout.bottom ? "Unpin: fold the panel away to give the drawing the space" : "Pin: keep the panel open below the drawing"}
            onClick={() => { setBottomOver(false); changeLayout({ bottom: !layout.bottom }); }}>📌</button>
          {over && <button className="linkish" aria-label="Fold the panel away" onClick={() => setBottomOver(false)}>✕</button>}
        </div>
        <div className="drawn-tabbody">
          {tab === "find" && (readOnly ? <p className="small quiet">Finding and placing entities needs a role that may change the model.</p> : (
            <div className="drawn-find">
              <div>
                <input type="search" placeholder="Name or ID" value={panel.q} onChange={(e) => setPanel({ ...panel, q: e.target.value })} aria-label="Find an entity" />
                <SearchSelect ariaLabel="Type" value={panel.type} onChange={(v) => setPanel({ ...panel, type: v })}
                  placeholder="Any type: type to search" options={[{ value: "", label: "Any type" }, ...typeOptions(setup)]} />
                {panel.bindTo && <button className="linkish small" onClick={() => setPanel({ q: "", type: "", bindTo: null })}>Cancel choosing</button>}
                <p className="small quiet">{panel.bindTo ? "Pick the entity the placeholder shows." : "Drag one onto the drawing (onto a placeholder of its type to realise it), or press Place."}</p>
              </div>
              <ul className="drawn-results">
                {found.map((e) => {
                  const t = setup.types[typeByName[e.entity_type]];
                  return (
                    <li key={e.id} draggable={!panel.bindTo} onDragStart={(ev) => { ev.dataTransfer.setData("text/plain", e.id); setDragging(e); }}
                      onDragEnd={() => setDragging(null)} style={{ borderLeftColor: `#${t.colour}` }} title={`${e.entity_type} · ${e.display_id}`}>
                      <span className="drawn-swatch" style={{ background: `#${t.colour}` }} />
                      <span className="drawn-name">{e.name}<span className="small quiet"> {t.name}</span></span>
                      <button className="linkish small" onClick={() => pick(e)}>{panel.bindTo ? "Choose" : "Place"}</button>
                    </li>);
                })}
                {entities && !found.length && <li className="quiet small">Nothing matches.</li>}
              </ul>
            </div>))}
          {tab === "props" && <div className="drawn-propsbody">
            {sel ? <Properties model={model} sel={sel} setup={setup} entities={entities} readOnly={readOnly} details={details}
              setDetails={setDetails} onView={boundIds(st.current.xml)} committer={committer} onChoose={(e) => {
                const code = typeByName[e.entity_type];
                realise(sel.cell, { id: e.id, name: e.name, type: code });
              }} onSelectEntity={(id) => post({ eax: "select", entity: id })} onTab={setTab}
              onType={(code) => { post({ eax: "placeholder-type", cell: sel.cell, type: code }); setSelected((x) => ({ ...x, type: code })); }}
              onEdit={(e) => setDlg({ kind: "edit", e })} onCreate={(code) => setDlg({ kind: "create", code, cell: sel.cell })}
              onSaveLine={saveLine} />
              : <p className="small quiet">Select an object or a line to see all its attributes. Select a placeholder to choose the entity it shows.</p>}
            {phList && <div><h4>Placeholders</h4>{!phList.length ? <p className="small quiet">None.</p> : <ul className="small">{phList.map((p) => (
              <li key={p.cell}>{setup.types[p.type]?.name || p.type} <button className="linkish" onClick={() => setSelected({ cell: p.cell, type: p.type, placeholder: true, choosing: Date.now() })}>choose</button></li>))}</ul>}</div>}
            {hiddenList && <div><h4>Hidden relationships</h4>{!hiddenList.length ? <p className="small quiet">None hidden in this view.</p> : <ul className="small">{hiddenList.map((h) => (
              <li key={h.id}>{h.rel}: {nameOf(entities, h.source)} → {nameOf(entities, h.target)}</li>))}</ul>}
              <p className="small quiet">Right-click an object › Show hidden relationships brings its lines back.</p></div>}
          </div>}
          {tab === "rels" && <RelatedTab model={model} sel={sel} details={details} setDetails={setDetails} readOnly={readOnly}
            xml={st.current.xml} onAdd={addRelated} onSelectEntity={(id) => post({ eax: "select", entity: id })} />}
          {tab === "allowed" && <AllowedTab sel={sel} setup={setup} readOnly={readOnly} onAdd={addAllowed} />}
          {tab === "unc" && !readOnly && <UncommittedPanel model={model} m={m} pend={pend} say={say} view={info.name} refresh={checkPending}
            onCommitted={() => { refreshAll(); resync(); }} />}
        </div>
      </section>
    );
  }

  if (error) return <div><p className="status bad">{error}</p><a href={`#/metamodel/${model}/views/custom`}>Back to the views</a></div>;
  if (!info || !setup) return <p className="quiet">Opening the drawn view...</p>;
  if (!st.current.v) st.current.v = Date.now();     // a fresh draw.io page (a browser keeps index.html)
  const src = `/drawio/index.html?embed=1&proto=json&configure=1&eax=1&spin=1&libraries=1&noExitBtn=1&saveAndExit=0&eaxv=${st.current.v}`;
  const q = panel.q.trim().toLowerCase();
  const found = fuzzyFilter((entities || []).filter((e) => typeByName[e.entity_type] && (!panel.type || typeByName[e.entity_type] === panel.type)), q)
    .slice(0, 60);
  return (
    <div className={`drawn-page${full ? " full" : ""}`}>
      {!full && <p className="crumbs"><a href={`#/metamodel/${model}/views/custom`}>Views</a> › Custom views › {info.name}</p>}
      <div className="drawn-head">
        {full && <span className="drawn-crumb small"><a href={`#/metamodel/${model}/views/custom`} target="_blank" rel="noopener" title="The model's Views tab, in a new tab">{m?.name || "Model"}</a> › Custom views ›</span>}
        <h2>{info.name} <span className="quiet">v{info.version}{old ? ` of ${info.latest_version}` : ""}</span></h2>
        {readOnly && <span className="rag off" title={old ? "An older version: read only" : "You may look and export, not change"}>read only</span>}
        {dirty && <span className="rag amber">not saved</span>}
        {placeholders > 0 && <button className="linkish small" onClick={() => post({ eax: "placeholders" })}
          title="Placeholders are on the view only, never in the model, until realised">{placeholders} placeholder{placeholders === 1 ? "" : "s"} not realised</button>}
        <span className="er-spacer" />
        {!readOnly && <button className="primary" disabled={saving || phase !== "ready"} onClick={() => saveXml(st.current.xml)}>{saving ? "Saving..." : "Save"}</button>}
        {!readOnly && <button className="drawn-commit" disabled={phase !== "ready"} onClick={() => { checkPending(); showTab("unc"); }}
          title={pend?.count ? "Your uncommitted changes in this model: edit, discard or commit them" : "Nothing of yours is waiting to be committed in this model"}>
          {uncommittedLabel(pend)}</button>}
        {old && mayDraw(model, m) && <button className="primary" onClick={async () => {
          const latest = await apiFetch(`${store(model)}/${encodeURIComponent(view)}?xml=0`);
          const out = await apiFetch(`${store(model)}/${encodeURIComponent(view)}`, { method: "PUT",
            body: JSON.stringify({ xml: info.xml, base_version: latest.version, note: `Restored version ${info.version}` }) }).catch((e) => { say(e.message, false); });
          if (out) { refreshAll(); go(viewUrl(model, view).slice(1)); }
        }}>Restore as a new version</button>}
        {!old && <button disabled={phase !== "ready"} onClick={() => resync()} title="Bring the view up to date with the model: names, new relationships between objects on it, deleted entities and relationships marked">Resync</button>}
        <button disabled={phase !== "ready"} onClick={() => setDlg({ kind: "heat" })}>{heat ? `Heat map: ${heat.attribute.name}` : "Heat map"}</button>
        <button disabled={phase !== "ready"} onClick={() => post({ eax: "hidden" })}>Hidden relationships</button>
        {!readOnly && <button disabled={phase !== "ready" || !groups.length} onClick={() => setDlg({ kind: "palettes" })}
          title="Show or hide the stencil's groups: each domain's types, Relationships, Junctions">Stencil</button>}
        {!readOnly && <label className="drawn-size small" title="The size of the stencil's items; this browser remembers it for you">Stencil size
          <select value={size} disabled={phase !== "ready"} onChange={(e) => { setSize(e.target.value); keepStencilSize(e.target.value); post({ eax: "stencil-size", size: e.target.value }); }}>
            {STENCIL_SIZES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>}
        <label className="drawn-size small" title="What a relationship's line shows: its name and type, or also its attribute values in [key:value]; this browser remembers it for you">Line labels
          <select value={layout.lineAttrs === false ? "type" : "attrs"} aria-label="Line labels"
            onChange={(e) => { const on = e.target.value === "attrs"; changeLayout({ lineAttrs: on }); post({ eax: "line-labels", attrs: on }); }}>
            <option value="type">Name and type</option><option value="attrs">With attributes</option></select></label>
        <label className="drawn-size small" title="Drawing: the stencil pinned, the panel folded away. Editing: both pinned. Canvas only: everything folded away. Within any of them, pin, unpin and resize as you like; this browser remembers it for you">Layout
          <select value={layout.preset} onChange={(e) => choosePreset(e.target.value)} aria-label="Layout">
            {PRESET_NAMES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <button disabled={phase !== "ready"} onClick={() => setDlg({ kind: "export" })}>Export</button>
        <button onClick={() => setDlg({ kind: "versions" })}>Versions</button>
        {!old && <button disabled={phase !== "ready" || dirty} title={dirty ? "Save first: evidence links to a saved view" : "A link from a deliverable or a key question to this view"}
          onClick={() => setDlg({ kind: "evidence" })}>Use as project evidence…</button>}
        {full && <button title="Close this tab (asks first when there are changes not saved)" onClick={() => {
          if (st.current.dirty && !window.confirm("The drawn view has changes that are not saved. Close anyway?")) return;
          st.current.dirty = false; window.close();
          setTimeout(() => { window.location.hash = `#/metamodel/${model}/views/custom`; }, 300);   // a tab the browser will not close
        }}>Close</button>}
      </div>
      {changedBanner && !old && <div className="status warn drawn-banner">The model has changed since this view was opened or saved.
        <button className="linkish" onClick={() => { setChangedBanner(false); resync(); }}>Resync</button> brings the view up to date.</div>}
      {note && <div className="status info drawn-banner drawn-note">{note} <span className="quiet">Save to keep it.</span>
        <button className="linkish" onClick={() => setNote(null)} aria-label="Dismiss">✕</button></div>}
      {conflict && <div className="status bad drawn-banner">{conflict.saved_by} saved version {conflict.version} at {fmtDateTime(conflict.saved_at)}, after you opened this view.
        <button className="linkish" onClick={() => saveXml(conflict.xml, true, conflict.note)}>Save anyway</button> (theirs stays in the versions) ·
        <button className="linkish" onClick={() => { setDirty(false); st.current.dirty = false; window.location.reload(); }}>Reload theirs</button></div>}
      {toast && <p className={`status ${toast.ok ? "ok" : "bad"} drawn-toast`} key={toast.at}>{toast.text} <button className="linkish" onClick={() => setToast(null)}>✕</button></p>}
      {heat && <div className="drawn-legend"><b>{heat.attribute.name}</b>{heat.legend.map((l) => <span key={l.label}><i style={{ background: `#${l.colour}` }} />{l.label}</span>)}
        <span><i style={{ background: "#EEEEEE" }} />no value</span><button className="linkish" onClick={() => { post({ eax: "heat-off" }); setHeat(null); }}>Off</button></div>}
      <div className={`drawn-body${layout.bottom ? " bottom-pinned" : ""}`}>
        <div className="drawn-row">
          {!readOnly && (
            <div className={`drawn-strip left${layout.stencil ? " pinned" : ""}${stencilOver ? " open" : ""}`}
              onClick={() => { if (!layout.stencil) setStencilOver((o) => !o); }}
              title={layout.stencil ? "The stencil is pinned" : stencilOver ? "Click the drawing to fold the stencil away" : "Open the stencil"}>
              <button className={`drawn-pin${layout.stencil ? "" : " off"}`} aria-label={layout.stencil ? "Unpin the stencil" : "Pin the stencil"}
                title={layout.stencil ? "Unpin: fold the stencil away to give the drawing the space" : "Pin: keep the stencil open"}
                onClick={(e) => { e.stopPropagation(); setStencilOver(false); changeLayout({ stencil: !layout.stencil }); }}>📌</button>
              <span className="drawn-strip-label">Stencil</span>
            </div>)}
          <div className="drawn-frame">
            <iframe ref={frame} title="The drawn view" src={src} />
            {dragging && <div className="drawn-drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => {
              e.preventDefault();
              const r = frame.current.getBoundingClientRect();
              const ent = dragging; setDragging(null);
              const code = typeByName[ent.entity_type];
              place({ id: ent.id, name: ent.name, type: code }, { x: e.clientX - r.left, y: e.clientY - r.top });
            }} />}
            {phase !== "ready" && <div className="drawn-wait">Starting draw.io…</div>}
            {!layout.bottom && bottomOver && bottomPanel(true)}
          </div>
        </div>
        {layout.bottom ? <>
          <div className="drawn-resizer" role="separator" aria-orientation="horizontal" aria-label="Resize the panel" title="Drag to resize"
            onPointerDown={startResize} />
          {bottomPanel(false)}
        </> : !bottomOver && (
          <div className="drawn-strip bottom" onClick={() => setBottomOver(true)} title="Open the panel over the drawing">
            {BOTTOM_TABS.filter(([k]) => tabShown(k)).map(([k, l]) => <button key={k} className="linkish small" onClick={(e) => { e.stopPropagation(); setTab(k); setBottomOver(true); }}>{tabLabel(k, l)}</button>)}
            <span className="er-spacer" />
            <button className="drawn-pin off" aria-label="Pin the panel" title="Pin: keep the panel open below the drawing"
              onClick={(e) => { e.stopPropagation(); changeLayout({ bottom: true }); }}>📌</button>
          </div>)}
      </div>
      {dlg?.kind === "edit" && <EntityFormDialog model={model} m={m} e={dlg.e} commit={{ view: info.name }} onClose={() => setDlg(null)}
        onSaved={(out) => { say(`Saved and committed ${out.name || dlg.e.name}.`); setDetails({}); refreshAll(); resync(); checkPending(); st.current.mineChanged?.(); }} />}
      {dlg?.kind === "create" && <EntityFormDialog model={model} m={m} typeId={dlg.code} commit={{ view: info.name }} onClose={() => setDlg(null)}
        onUseExisting={(x) => { realise(dlg.cell, { id: x.id, name: x.name, type: dlg.code }); say(`The shape shows ${x.name} (${x.display_id}), already in the model: nothing new was made.`); }}
        onSaved={(out) => {
          const id = out.id || out.entity?.id;
          if (id) realise(dlg.cell, { id, name: out.name, type: dlg.code });
          say(`${out.name} is in the model now (committed), and the placeholder shows it.`); refreshAll(); checkPending(); st.current.mineChanged?.();
        }} />}
      {dlg?.kind === "line-del" && <LineDeleteDialog model={model} rel={dlg.rel} view={info.name} may={!readOnly} say={say} post={post}
        onDone={() => { setDlg(null); setSelected(null); checkPending(); }} />}
      {dlg?.kind === "drop" && <DropDialog msg={dlg} setup={setup} entities={entities} committer={committer} onView={boundIds(st.current.xml)}
        onType={(code) => { post({ eax: "placeholder-type", cell: dlg.cell, type: code }); setDlg((d) => ({ ...d, type: code })); }}
        onBind={(e, code) => { setDlg(null); realise(dlg.cell, { id: e.id, name: e.name, type: code }); }}
        onCreate={(code) => setDlg({ kind: "create", code, cell: dlg.cell })}
        onLeave={() => setDlg(null)} />}
      {dlg?.kind === "rel" && <RelationshipDialog model={model} setup={setup} msg={dlg} entities={entities} view={info.name}
        onDone={(answer) => { const { note, okNote, ...a } = answer; post(a); setDlg(null); if (a.eax === "rel") setDirty(true); if (note) say(note, false); if (okNote) say(okNote); }} />}
      {dlg?.kind === "add-rel" && <AddRelationshipDialog model={model} setup={setup} msg={dlg} view={info.name} onDone={(answer) => { if (answer) { post(answer); setDirty(true); } setDlg(null); }} />}
      {dlg?.kind === "nest" && <NestDialog model={model} setup={setup} msg={dlg} entities={entities} onDone={(answer) => { post(answer); setDlg(null); }} />}
      {dlg?.kind === "heat" && <HeatDialog model={model} onClose={() => setDlg(null)} onHeat={(h) => { setHeat(h); post({ eax: "heat", colours: h.colours }); setDlg(null); }} />}
      {dlg?.kind === "export" && <Modal title="Export the drawn view" onClose={() => setDlg(null)} actions={<button className="ed-btn secondary" onClick={() => setDlg(null)}>Close</button>}>
        <p className="quiet">As drawn, in the model's colours{heat ? " (the heat map is switched off for the export unless you choose as shown)" : ""}.</p>
        <div className="row-gap">
          <button onClick={() => download("png")}>PNG</button><button onClick={() => download("svg")}>SVG</button>
          <button onClick={() => download("pdf")}>PDF</button><button onClick={() => download("drawio")}>.drawio file</button>
          {heat && <button onClick={() => download("png", true)}>PNG as shown (with the heat map)</button>}
        </div></Modal>}
      {dlg?.kind === "palettes" && <Modal title="The stencil" onClose={() => setDlg(null)} actions={<button className="ed-btn secondary" onClick={() => setDlg(null)}>Close</button>}>
        <p className="quiet">Every type of the model's metamodel, by domain, with the relationship types and the junctions; then draw.io's
          General, Misc and Basic shapes for decoration (text, notes, comments, callouts, arrows, containers: never bound to the model, and
          their arrows never become relationships). Show what you use; this browser remembers it for you. Nothing of it is saved in the view.</p>
        <input type="search" className="search" placeholder="Find a group or a type" aria-label="Find a stencil group or type" value={palQ}
          onChange={(e) => setPalQ(e.target.value)} style={{ maxWidth: 320 }} />
        <div className="drawn-palettes">{paletteMatches(groups, setup, palQ).map(([g, hits]) => (
          <label key={g}><input type="checkbox" checked={shown[g] !== false} onChange={(e) => {
            const next = { ...shown, [g]: e.target.checked };
            if (e.target.checked) delete next[g];
            setShown(next); keepHiddenPalettes(next);
            post({ eax: "palettes", show: { [g]: e.target.checked } });
          }} /> {g}{hits.length ? <span className="quiet small"> · {hits.slice(0, 4).join(", ")}{hits.length > 4 ? "…" : ""}</span> : null}</label>))}
          {palQ.trim() && !paletteMatches(groups, setup, palQ).length && <p className="quiet small">No group or type matches "{palQ}".</p>}</div>
        <div className="row-gap"><button className="linkish" onClick={() => {
          const all = Object.fromEntries(groups.map((g) => [g, true]));
          setShown({}); keepHiddenPalettes({}); post({ eax: "palettes", show: all });
        }}>Show all</button></div></Modal>}
      {dlg?.kind === "versions" && <VersionsDialog model={model} v={{ id: info.id, name: info.name }} may={mayDraw(model, m)} current={info.version} onClose={() => setDlg(null)} />}
      {dlg?.kind === "evidence" && <EvidenceDialog model={model} info={info} onClose={() => setDlg(null)} say={say} />}
    </div>
  );
}

const nameOf = (entities, id) => (entities || []).find((e) => e.id === id)?.name || id;

// the properties panel (D411): everything about what is selected, right here. An entity: every attribute of its type (in
// the type's order, an empty one as —) and every relationship, by type and direction. A line: its type, both ends,
// committed or pending. A placeholder: the model's entities of its type to choose from; a realised object may be
// shown as another entity of its type (Change instance).
function useEntityDetail(model, id, details, setDetails) {
  useEffect(() => {
    if (!id || details[id]) return;
    let live = true;
    apiFetch(`/api/v1/models/${model}/entities/${id}`).then((e) => live && setDetails((d) => ({ ...d, [id]: e })))
      .catch((err) => live && setDetails((d) => ({ ...d, [id]: { error: err.message } })));
    return () => { live = false; };
  }, [model, id, details, setDetails]);
  return id ? details[id] : null;
}

function Properties({ model, sel, setup, entities, readOnly, details, setDetails, onView, onChoose, onSelectEntity, committer, onType, onEdit, onCreate, onTab, onSaveLine }) {
  const [changing, setChanging] = useState(false);
  const e = useEntityDetail(model, sel.entity || (sel.relationship ? sel.source : null), details, setDetails);
  useEffect(() => { setChanging(false); }, [sel.cell]);
  const typeName = setup?.types?.[sel.type]?.name || sel.type;
  if (sel.placeholder || (changing && sel.entity) || (sel.choosing && sel.entity)) {
    return <ChooseInstance key={`${sel.cell}${sel.choosing || ""}`} sel={sel} typeName={typeName} setup={setup} entities={entities} readOnly={readOnly}
      onView={onView} onChoose={(x) => { setChanging(false); onChoose(x); }} onCancel={sel.entity ? () => setChanging(false) : null}
      committer={committer} onType={sel.placeholder ? onType : null} onCreate={sel.placeholder ? onCreate : null} />;
  }
  if (sel.relationship || sel.relType) {
    const r = e && !e.error ? (e.relationships || []).find((x) => x.id === sel.relationship) : null;
    const nm = (id) => nameOf(entities, id);
    return (
      <div className="small drawn-prop">
        <p><b>{r?.relationship_type || sel.relType || "A line"}</b>{sel.pending || !r ? <span className="rag amber"> pending</span> : <span className="rag ok"> committed</span>}</p>
        <table className="facts"><tbody>
          <tr><th>From</th><td>{sel.source ? <button className="linkish" onClick={() => onSelectEntity(sel.source)}>{nm(sel.source)}</button> : "—"}</td></tr>
          <tr><th>To</th><td>{sel.target ? <button className="linkish" onClick={() => onSelectEntity(sel.target)}>{nm(sel.target)}</button> : "—"}</td></tr>
          {r && <tr><th>Status</th><td>{r.status || "—"}</td></tr>}
          {r && <tr><th>Changed</th><td>{r.modified_by || "—"}{r.modified_at ? ` · ${fmtDateTime(r.modified_at)}` : ""}</td></tr>}
          {r && r.allowed === false && <tr><th>Rules</th><td className="status bad">Outside the metamodel's rules</td></tr>}
        </tbody></table>
        {r && sel.relationship && <LineAttributes model={model} id={sel.relationship} readOnly={readOnly || sel.pending} onSave={onSaveLine}
          note={"A relationship's change is in the model at once, as you (\"Drawn on view …\")."} />}
        {!r && sel.relationship && <p className="quiet">Not committed yet: an uncommitted change from before relationships were committed at once
          (Uncommitted changes commits it).</p>}
        {!readOnly && sel.relationship && <p className="quiet">Delete the line to hide it in this view or delete it from the model (you are asked).</p>}
      </div>
    );
  }
  if (!sel.entity) return null;
  if (!e) return <p className="small quiet">Loading…</p>;
  if (e.error) return <p className="small status bad">{e.error}</p>;
  const shown = (v) => (v === null || v === undefined || v === "" || (Array.isArray(v) && !v.length) ? "—" : Array.isArray(v) ? v.join(", ") : String(v));
  return (
    <div className="small drawn-prop">
      <p><b>{e.name}</b><br /><span className="quiet">{e.entity_type} · {e.display_id}</span></p>
      {e.description && <p>{e.description}</p>}
      <h5>Attributes</h5>
      <table className="facts"><tbody>
        {(e.attributes || []).map((a) => <tr key={a.code || a.name}><th>{a.name}</th><td className={shown(a.value) === "—" ? "quiet" : undefined}>{a.data_type === "url" && a.value ? <LinkList value={a.value} /> : shown(a.value)}</td></tr>)}
        {!(e.attributes || []).length && <tr><td className="quiet">Its type has no attributes.</td></tr>}
      </tbody></table>
      <p className="quiet">{(e.relationships || []).length} relationship{(e.relationships || []).length === 1 ? "" : "s"} in the model:{" "}
        <button className="linkish" onClick={() => onTab?.("rels")}>Relationships</button> · <button className="linkish" onClick={() => onTab?.("allowed")}>Allowed relationships</button></p>
      {!readOnly && !sel.junction && <p className="row-gap">
        {committer ? <button className="ed-btn small" onClick={() => onEdit(e)} title="Edit the entity in its form; Save and commit puts it in the model at once">Edit</button>
          : <span className="quiet" title="Only the model's committers change entities from a drawn view (D413)">Editing the entity needs a committer.</span>}
        <button className="linkish" onClick={() => setChanging(true)}>Change instance…</button></p>}
      <a href={`#/metamodel/${model}/entity/${e.id}`} target="_blank" rel="noreferrer">Open the entity ↗</a>
    </div>
  );
}

// the entities of the placeholder's type (and the types specialising it), to choose the one it shows
// the dropped type and the types specialising it (D413): a placeholder's type dropdown
function typeFamily(setup, code) {
  const types = setup?.types || {};
  let top = code;
  const seen = new Set();
  while (types[top]?.specialises && types[types[top].specialises] && !seen.has(top)) { seen.add(top); top = types[top].specialises; }
  const out = [top];
  for (let i = 0; i < out.length; i++) for (const [c, t] of Object.entries(types)) if (t.specialises === out[i] && !out.includes(c)) out.push(c);
  return out;
}

function ChooseInstance({ sel, typeName, setup, entities, readOnly, onView, onChoose, onCancel, committer, onType, onCreate }) {
  const [q, setQ] = useState("");
  const input = useRef(null);
  useEffect(() => { input.current?.focus(); }, []);
  const family = useMemo(() => typeFamily(setup, sel.type), [setup, sel.cell]);
  const names = new Set([typeName]);
  if (!onType) for (const t of Object.values(setup?.types || {})) if (t.specialises && names.has(setup.types[t.specialises]?.name)) names.add(t.name);
  // near spellings too (D454): "Claims Platfrom" finds Claims Platform
  const list = fuzzyFilter((entities || []).filter((x) => names.has(x.entity_type) && x.entity_type !== "Junction"), q);
  if (readOnly) return <p className="small quiet">A placeholder for a {typeName}, not realised yet.</p>;
  return (
    <div className="small drawn-prop">
      <p><b>{sel.entity ? `Show another ${typeName}` : `Realise this ${typeName}`}</b></p>
      <p className="quiet">{sel.entity ? "The object will show the entity you choose, with its relationships to what is on the view."
        : "Choose the entity it shows: it is then bound to it, as if dragged from the search, and its relationships to what is on the view are drawn."}</p>
      {onType && family.length > 1 && <label className="ed-field">Type
        <SearchSelect ariaLabel="The placeholder's type" value={sel.type} onChange={onType} options={typeOptions(setup, family)} /></label>}
      <input ref={input} type="search" placeholder={`Find a ${typeName}`} value={q} onChange={(e) => setQ(e.target.value)} aria-label={`Find a ${typeName}`} />
      <ul className="drawn-choose" role="listbox" aria-label={`${typeName} entities`}>
        {list.slice(0, 200).map((x) => (
          <li key={x.id}><button className="linkish" role="option" aria-selected="false" onClick={() => onChoose(x)}>{x.name}</button>
            <span className="quiet"> {x.display_id}{onView.includes(x.id) ? " · on the view" : ""}</span></li>))}
        {entities && !list.length && <li className="quiet">{q ? "Nothing matches." : `The model has no ${typeName} yet.`}</li>}
        {!entities && <li className="quiet">Loading…</li>}
      </ul>
      {list.length > 200 && <p className="quiet">The first 200; type to narrow.</p>}
      {onCreate && (committer
        ? <p><button className="ed-btn small" onClick={() => onCreate(sel.type)} title="Its form; Save and commit puts it in the model at once and binds the placeholder to it">Create a new {typeName}…</button></p>
        : <p className="quiet">Only the model's committers create entities from a drawn view: choose one that exists.</p>)}
      {onCancel && <button className="linkish" onClick={onCancel}>Cancel</button>}
    </div>
  );
}

// a change made on the view, in the model at once and committed as the person (D413)
function changeNow(model, op, args, view, message = "") {
  return apiFetch(`/api/v1/models/${model}/drawn-views/change`, { method: "POST", body: JSON.stringify({ op, args, view_name: view || "", message }) });
}

function uncommittedLabel(p) {
  const n = p?.count || 0;
  return n ? `Uncommitted changes (${n})` : "Uncommitted changes";
}

// the person's uncommitted changes in this model (D413): each to edit (an entity's, in its form), discard, or commit with a
// message. Relationships and junctions need no committer; anything else does
const FREE_OPS = /^relationship\./;
function UncommittedPanel({ model, m, pend, say, view, refresh, onCommitted }) {
  const [chosen, setChosen] = useState({});
  const [message, setMessage] = useState(`Committed from drawn view ${view || ""}`.trim());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [edit, setEdit] = useState(null);
  const changes = pend?.changes || [];
  const may = (c) => pend?.may_commit || FREE_OPS.test(c.op) || /junction/i.test(c.label || "");
  const ids = changes.filter((c) => chosen[c.id]).map((c) => c.id);
  async function commit(list) {
    setBusy(true); setErr("");
    try {
      const out = await apiFetch(`/api/v1/models/${model}/drawn-views/commit`, { method: "POST", body: JSON.stringify({ changes: list, message }) });
      say(`Committed ${out.committed} change${out.committed === 1 ? "" : "s"} (commit ${out.number}).`);
      setChosen({}); await refresh(); onCommitted();
    } catch (e) {
      const c = e.body?.errors?.conflicts;
      setErr(c?.length ? `${e.message} Open the model's Changes tab to resolve them.` : e.message);
    } finally { setBusy(false); }
  }
  async function discard(c) {
    if (!window.confirm(`Discard "${c.label}"? It cannot be undone.`)) return;
    setErr("");
    try { await apiFetch(`/api/v1/models/${model}/changes/discard`, { method: "POST", body: JSON.stringify({ changes: [c.id] }) }); await refresh(); onCommitted(); }
    catch (e) { setErr(e.message); }
  }
  async function openEdit(c) {
    try { setEdit(await apiFetch(`/api/v1/models/${model}/entities/${c.target}`)); } catch (e) { setErr(e.message); }
  }
  const all = changes.filter(may).map((c) => c.id);
  return (
    <div className="drawn-uncpanel">
      <p className="small quiet">Everything of yours in {m?.name || "this model"} not committed yet, made here or anywhere else. Relationships drawn on a view are committed
        at once now; these are older ones and entity changes.{pend?.may_commit ? "" : " You may commit relationships and junctions; other changes need one of the model's committers (the Changes tab asks them)."}</p>
      {!changes.length ? <p className="quiet">Nothing waiting.</p> : <table className="small drawn-unc"><thead><tr><th /><th>Change</th><th>When</th><th /></tr></thead><tbody>
        {changes.map((c) => (
          <tr key={c.id}>
            <td><input type="checkbox" disabled={!may(c)} checked={!!chosen[c.id]} onChange={(e) => setChosen({ ...chosen, [c.id]: e.target.checked })} aria-label={`Choose ${c.label}`} /></td>
            <td>{c.label}{c.warnings?.length ? <span className="sev warning small"> {c.warnings.length} rule{c.warnings.length === 1 ? "" : "s"}</span> : null}
              {!may(c) && <span className="quiet"> (needs a committer)</span>}</td>
            <td className="quiet">{c.created_at ? fmtDateTime(c.created_at) : ""}</td>
            <td className="row-gap">{c.target_kind === "entity" && c.op !== "entity.delete" && <button className="linkish" onClick={() => openEdit(c)}>Edit</button>}
              <button className="linkish drawn-discard" onClick={() => discard(c)}>Discard</button></td>
          </tr>))}
      </tbody></table>}
      {changes.length > 0 && <div className="drawn-uncact">
        <label className="ed-field">Commit message<input value={message} onChange={(e) => setMessage(e.target.value)} aria-label="Commit message" /></label>
        <button className="ed-btn" disabled={busy || !ids.length || !message.trim() || ids.some((x) => !may(changes.find((c) => c.id === x)))} onClick={() => commit(ids)}>Commit selected ({ids.length})</button>
        <button className="ed-btn secondary" disabled={busy || !all.length || !message.trim()} onClick={() => commit(all)}>Commit all{all.length < changes.length ? ` you may (${all.length})` : ""}</button>
      </div>}
      {err && <p className="status bad">{err}</p>}
      {edit && <EntityFormDialog model={model} m={m} e={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); refresh(); }} />}
    </div>
  );
}

// a shape dropped from the stencil, or a placeholder added from Allowed relationships (D420): what is it? Bind it to an
// existing entity of its type, create a new one (committers only), or leave it as a placeholder (Esc) to decide later
function DropDialog({ msg, setup, entities, committer, onView, onType, onBind, onCreate, onLeave }) {
  const [q, setQ] = useState("");
  const input = useRef(null);
  useEffect(() => { input.current?.focus(); }, [msg.type]);
  const fromAllowed = msg.via === "allowed";
  const types = useMemo(() => (fromAllowed ? (msg.types || [msg.type]) : typeFamily(setup, msg.type)), [setup, msg.cell]);
  const typeName = setup?.types?.[msg.type]?.name || msg.type;
  const relName = msg.rel ? (setup?.relationshipTypes?.[msg.rel]?.name || msg.rel) : "";
  // near spellings and word order too (D454): "Claims Platfrom" finds Claims Platform
  const list = fuzzyFilter((entities || []).filter((x) => x.entity_type === typeName), q);
  return (
    <Modal title={`What is this ${typeName}?`} onClose={onLeave}
      actions={<>
        {committer && <button className="ed-btn" onClick={() => onCreate(msg.type)} title="Its form; Save and commit puts it in the model at once and the shape shows it">Create a new {typeName}…</button>}
        <button className="ed-btn secondary" onClick={onLeave} title="It stays a dashed placeholder; choose its entity later in Properties (Esc)">Leave as a placeholder</button></>}>
      {fromAllowed && <p className="quiet small">Joined to the selected object by {relName}: the relationship is made (committed at once) when you choose or create the entity.</p>}
      {types.length > 1 && <label className="ed-field">{fromAllowed ? "The other end is a" : "Type"}
        <SearchSelect ariaLabel="The placeholder's type" value={msg.type} onChange={onType} options={typeOptions(setup, types)} /></label>}
      <label className="ed-field">Bind it to an existing {typeName}
        <input ref={input} type="search" placeholder={`Find a ${typeName}`} value={q} onChange={(e) => setQ(e.target.value)} aria-label={`Find a ${typeName}`} /></label>
      <ul className="drawn-choose" role="listbox" aria-label={`${typeName} entities`}>
        {list.slice(0, 200).map((x) => (
          <li key={x.id}><button className="linkish" role="option" aria-selected="false" onClick={() => onBind(x, msg.type)}>{x.name}</button>
            <span className="quiet"> {x.display_id}{onView.includes(x.id) ? " · on the view" : ""}</span></li>))}
        {entities && !list.length && <li className="quiet">{q ? "Nothing matches." : `The model has no ${typeName} yet.`}</li>}
        {!entities && <li className="quiet">Loading…</li>}
      </ul>
      {list.length > 200 && <p className="quiet small">The first 200; type to narrow.</p>}
      {!committer && <p className="quiet small">Only the model's committers create entities from a drawn view: bind it to one that exists, or leave it as a placeholder.</p>}
    </Modal>
  );
}

// the Relationships tab (D420): the selected entity's relationships in the model, both ways, by type. Clicking one puts the
// related entity next to it with the relationship's line; on the view already, only the line; both there, the line is selected
function RelatedTab({ model, sel, details, setDetails, readOnly, xml, onAdd, onSelectEntity }) {
  const e = useEntityDetail(model, sel?.entity || null, details, setDetails);
  if (!sel || !sel.entity) return <p className="small quiet">{sel?.placeholder ? "Choose the placeholder's entity first (Properties); its relationships are then here." : "Select an object to see its relationships in the model."}</p>;
  if (!e) return <p className="small quiet">Loading…</p>;
  if (e.error) return <p className="small status bad">{e.error}</p>;
  const rels = e.relationships || [];
  if (!rels.length) return <p className="small quiet">{e.name} has no relationships in the model. Allowed relationships adds one.</p>;
  const groups = {};
  for (const r of rels) {
    const k = `${r.direction === "outgoing" ? "" : "← "}${r.relationship_type}${r.direction === "outgoing" ? " →" : ""}`;
    (groups[k] = groups[k] || []).push(r);
  }
  const text = String(xml || "");
  return (
    <div className="small drawn-relcols">
      <p className="quiet drawn-relintro"><b>{e.name}</b> · {readOnly ? "the ones on this view can be selected." : "click one to put it on the view next to it, with its line."}</p>
      {Object.entries(groups).map(([k, rs]) => (
        <div key={k} className="drawn-relgroup"><div className="drawn-relhead">{k}</div>
          <ul>{rs.map((r) => {
            const lineOn = text.includes(`ea_rel_id="${r.id}"`), entOn = text.includes(`ea_id="${r.other_id}"`);
            const mark = lineOn ? "on the view" : entOn ? "on the view, line not drawn" : "";
            return (
              <li key={r.id} className={lineOn ? "on-view" : undefined}>
                {readOnly ? (entOn ? <button className="linkish" onClick={() => onSelectEntity(r.other_id)}>{r.other_name}</button> : r.other_name)
                  : <button className="linkish" onClick={() => onAdd(r)} title={lineOn ? "Select it on the view" : entOn ? "Draw the line" : "Put it on the view next to the selected object, with the line"}>{r.other_name}</button>}
                <span className="quiet"> {r.other_type}{r.name ? ` · ${r.name}` : ""}</span>
                {mark && <span className="drawn-onview"> ✓ {mark}</span>}
              </li>);
          })}</ul></div>))}
    </div>
  );
}

// the Allowed relationships tab (D420): what the metamodel allows for the selected object's type, both ways, with the other
// types and multiplicity. Clicking puts a placeholder of the other type next to it, joined by that relationship
function AllowedTab({ sel, setup, readOnly, onAdd }) {
  if (!sel || (!sel.entity && !sel.placeholder) || sel.junction) return <p className="small quiet">Select an object to see the relationships the metamodel allows for its type.</p>;
  const T = sel.type;
  const tn = (c) => setup?.types?.[c]?.name || c;
  const rn = (c) => setup?.relationshipTypes?.[c]?.name || c;
  const rows = [];
  for (const out of [true, false]) {
    const by = {};
    for (const a of setup?.allowed || []) {
      if ((out ? a[0] : a[2]) !== T) continue;
      const other = out ? a[2] : a[0];
      if (!setup.types[other]) continue;
      (by[a[1]] = by[a[1]] || []).push({ code: other, mult: out ? (a[4] || "") : (a[3] || "") });
    }
    const order = Object.keys(setup?.relationshipTypes || {});
    Object.keys(by).sort((x, y) => order.indexOf(x) - order.indexOf(y)).forEach((r) => rows.push({ out, rel: r, others: by[r] }));
  }
  if (!rows.length) return <p className="small quiet">The metamodel allows no relationships for {tn(T)}.</p>;
  return (
    <div className="small drawn-allowed">
      <p className="quiet drawn-relintro"><b>{tn(T)}</b> · {readOnly ? "what the metamodel allows." : "click a type to put a placeholder of it next to the selected object, joined by that relationship; the row's name asks which type."}</p>
      <table><tbody>{rows.map((r) => (
        <tr key={`${r.out}${r.rel}`}>
          <th>{readOnly ? <span>{r.out ? "" : "← "}{rn(r.rel)}{r.out ? " →" : ""}</span>
            : <button className="linkish" onClick={() => onAdd(r.rel, r.others.map((o) => o.code), r.out)} title={r.others.length > 1 ? "Add one; the pop-up asks which type" : "Add one"}>
              {r.out ? "" : "← "}{rn(r.rel)}{r.out ? " →" : ""}</button>}</th>
          <td>{r.others.map((o) => (
            <span key={o.code} className="drawn-chip" style={{ borderLeftColor: `#${setup.types[o.code]?.colour || "ccc"}` }}>
              {readOnly ? tn(o.code) : <button className="linkish" onClick={() => onAdd(r.rel, [o.code], r.out)}>{tn(o.code)}</button>}
              {o.mult && <span className="quiet" title="Multiplicity at that end"> {o.mult}</span>}</span>))}</td>
        </tr>))}</tbody></table>
    </div>
  );
}

// a relationship's line deleted on the view (D413): asked each time. Hide it in this view (the hidden list), or delete it from
// the model (anyone who may change the model; committed at once, other views show it red when next opened)
function LineDeleteDialog({ model, rel, view, may, say, post, onDone }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const keep = () => { post({ eax: "line-restore", id: rel.id }); onDone(); };
  async function fromModel() {
    setBusy(true); setErr("");
    try {
      if (rel.pending) {           // never committed: the person's uncommitted change is discarded instead
        const c = await apiFetch(`/api/v1/models/${model}/changes`);
        const ch = (c.mine || []).flatMap((x) => x.changes || []).find((x) => x.target === rel.id && x.op === "relationship.create");
        if (ch) await apiFetch(`/api/v1/models/${model}/changes/discard`, { method: "POST", body: JSON.stringify({ changes: [ch.id] }) });
        else await changeNow(model, "relationship.delete", { relationship: rel.id }, view);
      } else await changeNow(model, "relationship.delete", { relationship: rel.id }, view);
      post({ eax: "line-removed", id: rel.id });
      refreshAll();
      say("Deleted from the model (committed). Other views show it red when next opened.");
      onDone();
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title="Delete this relationship?" onClose={keep}
      actions={<>
        <button className="ed-btn" disabled={busy} onClick={() => { post({ eax: "line-hide", id: rel.id }); onDone(); }}>Hide in this view</button>
        {may && <button className="danger" disabled={busy} onClick={fromModel}>{busy ? "Deleting..." : "Delete from the model"}</button>}
        <button className="ed-btn secondary" disabled={busy} onClick={keep}>Cancel</button></>}>
      <p>The {rel.rel} relationship{rel.name ? ` "${rel.name}"` : ""}: hide its line in this view only (it stays in the model and on other views), or
        delete it from the model{may ? "" : " (needs a role that may change the model)"}.</p>
      <p className="small quiet">Deleting from the model is committed at once as you, with the message "Deleted on drawn view {view}".</p>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// a line drawn between two objects: which relationship (only the allowed ones), and its name
function RelationshipDialog({ model, setup, msg, entities, onDone, view }) {
  const existing = msg.existing || [];
  // the types already between these two come first (owner, 10 Nov 2026)
  const options = [...(msg.options || [])].sort((a, b) => (existing.some((x) => x.type === b) ? 1 : 0) - (existing.some((x) => x.type === a) ? 1 : 0));
  const [type, setType] = useState(existing[0]?.type || options[0] || "");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const label = (c) => setup.relationshipTypes?.[c]?.name || c;
  const show = (x) => onDone({ eax: "rel", cell: msg.cell, type: x.type, id: x.id, name: x.name || "", pending: !x.committed, okNote: "Shown the existing relationship." });
  const there = existing.find((x) => x.type === type);
  async function add() {
    if (there) { show(there); return; }
    setBusy(true); setErr("");
    try {
      const out = await changeNow(model, "relationship.create", { data: { source: msg.source, target: msg.target, relationship_type: type, name } }, view);
      refreshAll();
      onDone({ eax: "rel", cell: msg.cell, type, id: out.id || out.relationship?.id, name: out.name ?? out.relationship?.name ?? name, pending: false });
    } catch (e) {
      // the model has it already: the line shows that relationship (often one hidden on this view)
      if (e.status === 409 && /already have/.test(e.message)) {
        const r = await apiFetch(`${base(model)}/relationships-of`, { method: "POST", body: JSON.stringify({ entity: msg.source, others: [msg.target] }) }).catch(() => null);
        const x = (r?.relationships || []).find((y) => y.type === type && y.source === msg.source && y.target === msg.target);
        if (x) { show(x); return; }
      }
      setErr(e.message); setBusy(false);
    }
  }
  return (
    <Modal title="A new relationship" onClose={() => onDone({ eax: "rel-cancel", cell: msg.cell })}
      actions={<><button className="ed-btn" disabled={busy || !type} onClick={add}>{there ? "Show the existing relationship" : "Add the relationship"}</button>
        <button className="ed-btn secondary" onClick={() => onDone({ eax: "rel-cancel", cell: msg.cell })}>Cancel</button></>}>
      <p>From <b>{nameOf(entities, msg.source)}</b> to <b>{nameOf(entities, msg.target)}</b>{msg.junction ? " (through a junction)" : ""}.</p>
      {existing.length > 0 && <div className="status ok small">Already in the model between these two:{" "}
        {existing.map((x) => <span key={x.id}><b>{label(x.type)}</b>{x.name ? ` "${x.name}"` : ""}{" "}
          <button className="linkish" onClick={() => show(x)}>show it</button>{" "}</span>)}</div>}
      <label className="ed-field">Relationship type
        <SearchSelect ariaLabel="Relationship type" value={type} onChange={setType}
          options={options.map((c) => ({ value: c, label: label(c), note: existing.some((x) => x.type === c) ? "(already in the model)" : "" }))} /></label>
      {!there && <label className="ed-field">Name (optional)<input value={name} onChange={(e) => setName(e.target.value)} /></label>}
      <p className="small quiet">Only the types the metamodel allows between these two are offered. It goes into the model at once, committed as you
        ("Drawn on view {view}"), and shows solid.</p>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// Add a relationship...: the other object on the view, the direction and an allowed type
function AddRelationshipDialog({ model, setup, msg, onDone, view }) {
  const [other, setOther] = useState("");
  const [outgoing, setOutgoing] = useState(true);
  const [options, setOptions] = useState(null);
  const [type, setType] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const cand = (msg.candidates || []).find((c) => c.cell === other);
  useEffect(() => {
    if (!cand) { setOptions(null); return; }
    const [s, t] = outgoing ? [msg.entity, cand.entity] : [cand.entity, msg.entity];
    apiFetch(`${base(model)}/allowed?source=${s}&target=${t}`).then((a) => { setOptions(a.allowed || []); setType(a.allowed?.[0]?.code || ""); })
      .catch((e) => setErr(e.message));
  }, [other, outgoing]);
  async function add() {
    setErr("");
    const [s, t] = outgoing ? [msg.entity, cand.entity] : [cand.entity, msg.entity];
    try {
      const out = await changeNow(model, "relationship.create", { data: { source: s, target: t, relationship_type: type, name } }, view);
      refreshAll();
      onDone({ eax: "rel-create", source: outgoing ? msg.cell : cand.cell, target: outgoing ? cand.cell : msg.cell, type, id: out.id || out.relationship?.id, name: out.name ?? out.relationship?.name ?? name, pending: false });
    } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title="Add a relationship" onClose={() => onDone(null)}
      actions={<><button className="ed-btn" disabled={!cand || !type} onClick={add}>Add</button><button className="ed-btn secondary" onClick={() => onDone(null)}>Cancel</button></>}>
      <label className="ed-field">With
        <select value={other} onChange={(e) => setOther(e.target.value)}>
          <option value="">Choose an object on the view</option>
          {(msg.candidates || []).map((c) => <option key={c.cell} value={c.cell}>{c.name} ({setup.types[c.type]?.name || c.type})</option>)}
        </select></label>
      <label><input type="radio" checked={outgoing} onChange={() => setOutgoing(true)} /> from this object to it</label>{" "}
      <label><input type="radio" checked={!outgoing} onChange={() => setOutgoing(false)} /> from it to this object</label>
      {options && (options.length
        ? <label className="ed-field">Relationship type<SearchSelect ariaLabel="Relationship type" value={type} onChange={setType}
          options={options.map((o) => ({ value: o.code, label: o.name, note: o.source_multiplicity || o.target_multiplicity ? `(${o.source_multiplicity || "*"} : ${o.target_multiplicity || "*"})` : "" }))} /></label>
        : <p className="status bad">The metamodel allows nothing this way between these two.</p>)}
      <label className="ed-field">Name (optional)<input value={name} onChange={(e) => setName(e.target.value)} /></label>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// an object dropped into another: nesting needs a relationship (D354 rule 6)
function NestDialog({ model, setup, msg, entities, onDone }) {
  const [type, setType] = useState(msg.options[0]?.code || "");
  const [err, setErr] = useState("");
  async function make() {
    try {
      await changeNow(model, "relationship.create", { data: { source: msg.parent, target: msg.entity, relationship_type: type } }, msg.view);
      refreshAll();
      onDone({ eax: "nest-ok", cell: msg.cell });
    } catch (e) { setErr(e.message); }
  }
  const refuse = () => onDone({ eax: "nest-refused", cell: msg.cell, reason: "Nesting needs a relationship between the two; none was made." });
  return (
    <Modal title="Nesting needs a relationship" onClose={refuse}
      actions={<><button className="ed-btn" disabled={!type} onClick={make}>Make it and nest</button><button className="ed-btn secondary" onClick={refuse}>Move it back out</button></>}>
      <p><b>{nameOf(entities, msg.entity)}</b> placed inside <b>{nameOf(entities, msg.parent)}</b>: the model has no composition, aggregation,
        assignment or realization between them. Choose one to make (in the model at once, committed), or move it back out.</p>
      <label className="ed-field">Relationship<SearchSelect ariaLabel="Relationship" value={type} onChange={setType}
        options={msg.options.map((o) => ({ value: o.code, label: o.name }))} /></label>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

function HeatDialog({ model, onClose, onHeat }) {
  const { data: mm } = useApi(`/api/v1/models/${model}/metamodel/diagram`);
  const attrs = useMemo(() => {
    const seen = new Map();
    for (const t of mm?.entity_types || []) for (const a of t.attributes || []) {
      if (!["date", "boolean", "datetime"].includes(a.data_type) && !seen.has(a.name)) seen.set(a.name, a);
    }
    return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [mm]);
  const [attr, setAttr] = useState("");
  const [ranges, setRanges] = useState("");
  const [err, setErr] = useState("");
  const a = attrs.find((x) => x.name === attr);
  const numeric = a && /int|dec|num|money|percent/i.test(a.data_type || "");
  async function show() {
    setErr("");
    try {
      const h = await apiFetch(`/api/v1/models/${model}/heat-map?attribute=${encodeURIComponent(attr)}${numeric && ranges.trim() ? `&ranges=${encodeURIComponent(ranges.trim())}` : ""}`);
      onHeat(h);
    } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title="Heat map" onClose={onClose}
      actions={<><button className="ed-btn" disabled={!attr} onClick={show}>Show</button><button className="ed-btn secondary" onClick={onClose}>Cancel</button></>}>
      <p className="quiet">Colours the objects by one attribute, on screen only: the saved view keeps the model's colours.</p>
      <label className="ed-field">Attribute<select value={attr} onChange={(e) => setAttr(e.target.value)}>
        <option value="">Choose…</option>{attrs.map((x) => <option key={x.name} value={x.name}>{x.name}{x.pick_list ? " (pick list)" : ""}</option>)}</select></label>
      {numeric && <label className="ed-field">Ranges (optional)<input value={ranges} onChange={(e) => setRanges(e.target.value)} placeholder="e.g. 0:10,10:50,50:100 (default: five equal bands)" /></label>}
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// the view as a project deliverable's artifact or a key question's answer: a link only (D408), to the live view or to the
// version open now (read only); no picture of it is stored anywhere
function EvidenceDialog({ model, info, onClose, say }) {
  const { data: plist } = useApi("/api/v1/projects");
  const [project, setProject] = useState("");
  const { data: p } = useApi(project ? `/api/v1/projects/${project}` : null);
  const { data: kq } = useApi(project ? `/api/v1/projects/${project}/key-questions` : null);
  const [kind, setKind] = useState("item");
  const [item, setItem] = useState("");
  const [question, setQuestion] = useState("");
  const [which, setWhich] = useState("live");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const items = (p?.items || []).filter((i) => i.kind !== "folder");
  async function add() {
    setBusy(true); setErr("");
    try {
      const body = { model, view: info.id, note, ...(which === "version" ? { version: info.version } : {}),
        ...(kind === "item" ? { item } : { question }) };
      const out = await apiFetch(`/api/v1/projects/${project}/view-evidence`, { method: "POST", body: JSON.stringify(body) });
      say(out.message || "Added as evidence."); onClose();
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  const ok = project && (kind === "item" ? item : question);
  return (
    <Modal title="Use as project evidence" onClose={onClose}
      actions={<><button className="ed-btn" disabled={!ok || busy} onClick={add}>{busy ? "Adding…" : "Add as evidence"}</button><button className="ed-btn secondary" onClick={onClose}>Cancel</button></>}>
      <p className="quiet">A link to {info.name}: opening the evidence opens the view itself. No picture is kept; a download stays yours.</p>
      <label><input type="radio" name="ev-which" checked={which === "live"} onChange={() => setWhich("live")} /> the live view (always as it is now)</label>{" "}
      <label><input type="radio" name="ev-which" checked={which === "version"} onChange={() => setWhich("version")} /> version {info.version} (read only)</label>
      <label className="ed-field">Project<select value={project} onChange={(e) => { setProject(e.target.value); setItem(""); setQuestion(""); }}>
        <option value="">Choose…</option>{(plist?.projects || []).filter((x) => !x.frozen).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      {project && <>
        <label><input type="radio" checked={kind === "item"} onChange={() => setKind("item")} /> a deliverable's artifact</label>{" "}
        <label><input type="radio" checked={kind === "question"} onChange={() => setKind("question")} /> a key question's answer</label>
        {kind === "item" ? <label className="ed-field">Deliverable<select value={item} onChange={(e) => setItem(e.target.value)}>
          <option value="">Choose…</option>{items.map((i) => <option key={i.id} value={i.id}>{i.phase} · {i.name}</option>)}</select></label>
          : <label className="ed-field">Key question<select value={question} onChange={(e) => setQuestion(e.target.value)}>
            <option value="">Choose…</option>{(kq?.questions || []).map((q) => <option key={q.id} value={q.id_guid || q.id}>{q.question}</option>)}</select></label>}
        <label className="ed-field">Note (optional)<input value={note} onChange={(e) => setNote(e.target.value)} /></label>
      </>}
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- the project's drawn views as evidence (its Views tab)
export function ViewEvidenceList({ p }) {
  const { data } = useApi(`/api/v1/projects/${p.id}/view-evidence`);
  if (!data || !data.evidence.length) return null;
  return (
    <section className="drawn-evidence">
      <h3>Drawn views as evidence</h3>
      <table className="grid-table">
        <thead><tr><th>For</th><th>Drawn view</th><th>Added</th></tr></thead>
        <tbody>{data.evidence.map((x) => (
          <tr key={x.id}>
            <td>{x.item_name ? <>Deliverable: {x.item_name}</> : <>Key question: {x.question_text}</>}{x.note && <div className="small quiet">{x.note}</div>}</td>
            <td>{x.view_removed ? <span className="quiet">{x.view_name || "a drawn view"} (removed)</span>
              : <a href={x.link} {...NEW_TAB}>{x.view_name} {x.version ? `v${x.version} (read only)` : "(live)"} ↗</a>}<div className="small quiet">{x.model_name}</div></td>
            <td className="small">{x.added_by} · {fmtDateTime(x.added_at)}</td>
          </tr>))}</tbody>
      </table>
    </section>
  );
}

// ---------------------------------------------------------------- a generated picture: save as a drawn view, or download
// Every generated picture (D407, D408) offers "Save as a drawn view" (a drawn view of the model keeping the picture's
// layout, tidied, its boxes in the ArchiMate notation of their types and bound to the entities, its lines to the
// relationships), "Open in draw.io" (our own draw.io in a tab of its own, as a scratch view kept nowhere: look, export,
// or save it as a drawn view there; D585) and downloads (PNG, SVG). Nothing else is stored.
// picture(): {title, nodes, edges} in exporting.js's drawioXml shape, read when pressed. images: PNG and SVG from the
// nodes (screens drawn in HTML); screens with their own SVG keep their own buttons for those. model: none for a picture
// that is not of one model (the model tree): downloads only (.drawio, PNG, SVG). A picture with its own file (the metamodel diagram) gives
// {title, xml} instead of nodes.
export function PictureActions({ model, picture, images = true, disabled = false }) {
  const { data: m } = useApi(model ? `/api/v1/models/${model}` : null);
  const [xml, setXml] = useState(null);
  const [title, setTitle] = useState("");
  const [err, setErr] = useState("");
  const may = !!model && !!m && mayDraw(model, m);
  async function look() {
    try { return model ? await apiFetch(`${base(model)}/setup`) : null; } catch { return null; }
  }
  async function save() {
    setErr("");
    try {
      const p = picture();
      if (!p || (!p.xml && !p.nodes.length)) throw new Error("Nothing on the picture to keep.");
      setTitle(p.title); setXml(p.xml || drawioXml(p.title, p.nodes, p.edges || [], await look()));
    } catch (e) { setErr(e.message); }
  }
  async function file() {
    const p = picture();
    if (p?.xml) saveBlob(new Blob([p.xml], { type: "application/xml" }), `${p.title}.drawio`);
    else if (p) downloadDrawio(p.title, p.nodes, p.edges || [], await look());
  }
  async function open() {
    setErr("");
    try {
      const p = picture();
      if (!p || (!p.xml && !p.nodes.length)) throw new Error("Nothing on the picture to open.");
      openInDrawio({ model, title: p.title, plain: !!p.plain, xml: p.xml || drawioXml(p.title, p.nodes, p.edges || [], await look()) });
    } catch (e) { setErr(e.message); }
  }
  return (
    <>
      {may && <button disabled={disabled} onClick={save} title="Keep this picture, with its layout, as a drawn view of the model: change it there and save versions">Save as a drawn view</button>}
      {model ? <button disabled={disabled} onClick={open}
        title="Open the picture in draw.io, in a tab of its own: look, export (.drawio, PNG, SVG, PDF) or save it as a drawn view there. It is kept nowhere until saved">Open in draw.io</button>
        : <button disabled={disabled} onClick={file} title="Download the picture as a draw.io file (yours to keep: it does not follow the model)">.drawio</button>}
      {images && <button disabled={disabled} onClick={() => { const p = picture(); if (p) downloadPicturePng(p.title, p.nodes, p.edges || []); }}>PNG</button>}
      {images && <button disabled={disabled} onClick={() => { const p = picture(); if (p) downloadPictureSvg(p.title, p.nodes, p.edges || []); }}>SVG</button>}
      {err && <span className="status bad small">{err}</span>}
      {xml && <NewDrawnView model={model} views={[]} xml={xml} source="generated" sourceNote={title} onClose={() => setXml(null)} />}
    </>
  );
}

// ---------------------------------------------------------------- an entity's own icon (part 2)
export function EntityIcon({ model, m, e }) {
  const [url, setUrl] = useState(null);
  const [tick, setTick] = useState(0);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const may = mayDraw(model, m);
  useEffect(() => {
    let live = true, made = null;
    apiBlobUrl(`/api/v1/models/${model}/entities/${e.id}/icon?t=${tick}`).then((u) => { made = u; if (live) setUrl(u); }).catch(() => live && setUrl(null));
    return () => { live = false; if (made) URL.revokeObjectURL(made); };
  }, [model, e.id, tick]);
  async function upload(file) {
    if (!file) return;
    if (file.size > 64 * 1024) { setMsg({ ok: false, text: "At most 64 KB." }); return; }
    const f = new FormData(); f.append("file", file, file.name);
    try { const out = await apiUpload(`/api/v1/models/${model}/entities/${e.id}/icon`, f); setMsg({ ok: true, text: out.message || "Saved." }); setTick((t) => t + 1); }
    catch (err) { setMsg({ ok: false, text: err.message }); }
  }
  async function remove() {
    try { const out = await apiFetch(`/api/v1/models/${model}/entities/${e.id}/icon`, { method: "DELETE" }); setMsg({ ok: true, text: out.message || "Removed." }); setTick((t) => t + 1); }
    catch (err) { setMsg({ ok: false, text: err.message }); }
  }
  if (!url && !may) return null;
  return (
    <div className="entity-icon-row small">
      <span className="quiet">Icon on drawn views:</span>
      {url ? <img src={url} alt="" className="entity-icon" /> : <span className="quiet"> its type's</span>}
      {may && <label className="linkish"> {url ? "Replace" : "Upload one"}<input type="file" accept=".svg,.png,image/svg+xml,image/png" hidden
        onChange={(ev) => { upload(ev.target.files[0]); ev.target.value = ""; }} /></label>}
      {may && url && <button className="linkish" onClick={remove}>Remove</button>}
      <span className="quiet"> (SVG or PNG, at most 64 KB)</span>
      {msg.text && <span className={`status ${msg.ok ? "ok" : "bad"}`}> {msg.text}</span>}
    </div>
  );
}

// ---------------------------------------------------------------- files
export function dataUriToBlob(uri) {
  const [head, body] = String(uri).split(",");
  const mime = (/data:([^;,]+)/.exec(head) || [])[1] || "application/octet-stream";
  const bin = head.includes(";base64") ? atob(body) : decodeURIComponent(body);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

// a one-page PDF holding the picture (as JPEG), written by hand: no PDF library is needed for that
export async function pngToPdf(pngUri) {
  const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = pngUri; });
  const c = document.createElement("canvas");
  c.width = img.width; c.height = img.height;
  const g = c.getContext("2d");
  g.fillStyle = "#ffffff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0);
  const jpeg = atob(c.toDataURL("image/jpeg", 0.92).split(",")[1]);
  const pw = Math.min(1190, Math.max(200, img.width * 0.75)), ph = img.height * (pw / img.width);
  const parts = []; const offsets = []; let len = 0;
  const add = (s) => { parts.push(s); len += s.length; };
  add("%PDF-1.4\n");
  const obj = (n, body) => { offsets[n] = len; add(`${n} 0 obj\n${body}\nendobj\n`); };
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  obj(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pw.toFixed(2)} ${ph.toFixed(2)}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`);
  offsets[4] = len;
  add(`4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${img.width} /Height ${img.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`);
  add(jpeg); add("\nendstream\nendobj\n");
  const content = `q ${pw.toFixed(2)} 0 0 ${ph.toFixed(2)} 0 0 cm /Im0 Do Q`;
  obj(5, `<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
  const xref = len;
  add(`xref\n0 6\n0000000000 65535 f \n${[1, 2, 3, 4, 5].map((n) => `${String(offsets[n]).padStart(10, "0")} 00000 n \n`).join("")}`);
  add(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`);
  const s = parts.join("");
  const bytes = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) bytes[i] = s.charCodeAt(i) & 0xff;
  return new Blob([bytes], { type: "application/pdf" });
}
