// Model tags, comparison and TOGAF gap analysis (build phase 8.3, D172).
//   #/metamodel/<model>/tags                       tab Tags: frozen snapshots of the model; tag, lock, download, make the latest
//   #/metamodel/<model>/tags/<tag>[/<entity>]      one tag's page: details, actions and its frozen contents (and one entity)
//   #/compare[?left=..&right=..|?model=..]         Compare (top menu, D177): two sides, each any model now or one of its tags
//   #/compare/gaps[?model=..]                      Gap analyses: every one you may see, each stored in a model you choose
//   #/compare/gaps/<analysis>                      one gap analysis
import { Fragment, useEffect, useMemo, useState } from "react";
import { apiDownload, apiFetch, canOn, myInfo } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { EntityLink } from "./Changes";
import { EntityPicker } from "./DataEntry";
import { fmtDate, fmtDateTime } from "./fmt";
import { trackTask } from "./tasks";

const go = (path) => { window.location.hash = path; };
const post = (path, body, method = "POST") => apiFetch(path, { method, body: JSON.stringify(body || {}) });
const when = (t) => (t ? fmtDateTime(t) : "");
const show = (v) => (v === null || v === undefined || v === "" ? <span className="quiet">(empty)</span> : String(v));
const STATUS = { kept: "Kept", changed: "Changed", new: "New", eliminated: "Eliminated" };
const TOGAF = { kept: "Included", changed: "Changed", new: "New", eliminated: "Eliminated" };

// ================================================================ Tags
export function TagsTab({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/tags`);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [lock, setLock] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [restore, setRestore] = useState(null);
  const [edit, setEdit] = useState(null);
  const mayTag = canOn(model, "model.content");
  const admin = canOn(model, "model.lock");
  async function act(fn, done) {
    setBusy(true); setErr(""); setMsg("");
    try { const out = await fn(); setMsg(typeof done === "function" ? done(out) : done); refreshAll(); } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  return (
    <div className="versions">
      <p className="quiet">
        A tag is a frozen copy of {m.name} under a name, for example <em>Baseline 2026</em>: its metamodel and every entity, value and
        relationship as committed at that moment. Compare the model with a tag, or two tags; make a tag the latest to set the whole
        model back to it (the current version is tagged first, so you can always go forward again).
      </p>
      {mayTag ? (
        <div className="toolbar tag-new">
          <input placeholder="Tag name, e.g. Baseline 2026" value={name} onChange={(e) => setName(e.target.value)} style={{ minWidth: 240 }} />
          <input placeholder="What it is (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} style={{ minWidth: 260 }} />
          <label><input type="checkbox" checked={lock} onChange={(e) => setLock(e.target.checked)} /> Lock it (never changed or deleted)</label>
          <button className="primary" disabled={busy || !name.trim()} onClick={() => act(
            () => post(`/api/v1/models/${model}/tags`, { name, description: desc, lock }),
            (t) => {
              setName(""); setDesc(""); setLock(false);
              if (t.task) {   // made in the background (D192): followed in the bar at the top, the list refreshes when done
                trackTask(t.task, `#/metamodel/${model}/tags`);
                return `Tagging '${name.trim()}' in the background: the bar at the top says when it is made. You can carry on working.`;
              }
              return `Tagged '${t.name}': ${t.entities} entities, ${t.relationships} relationships.`;
            })}>
            🏷 Tag the model now</button>
        </div>
      ) : <p className="quiet">Tagging needs a role that changes the content of {m.name}.</p>}
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
      <table className="grid-table">
        <thead><tr><th>Tag</th><th>Made</th><th className="num">Commit</th><th>Metamodel</th><th className="num">Entities</th><th className="num">Relationships</th><th /></tr></thead>
        <tbody>
          <tr className="now-row"><td><strong>{m.name} now</strong> <span className="quiet">(the latest)</span></td><td /><td className="num">{data.now.commit}</td>
            <td>v{data.now.metamodel_version}</td><td className="num">{m.entity_count}</td><td className="num">{m.relationship_count}</td><td /></tr>
          {data.tags.map((t) => (
            <tr key={t.id}>
              <td>
                {t.locked && <span title={`Locked by ${t.locked_by} on ${when(t.locked_at)}`}>🔒 </span>}
                <a href={`#/metamodel/${model}/tags/${t.id}`}><strong>{t.name}</strong></a>{t.kind === "before-restore" && <span className="rchip">automatic</span>}
                {t.description && <div className="quiet small">{t.description}</div>}
                {t.restored_at && <div className="quiet small">Made the latest on {when(t.restored_at)} by {t.restored_by}</div>}
              </td>
              <td className="small">{when(t.created_at)}<br /><span className="quiet">{t.created_by}</span></td>
              <td className="num">{t.commit}</td><td>v{t.metamodel_version}</td><td className="num">{t.entities}</td><td className="num">{t.relationships}</td>
              <td className="nowrap small">
                <button className="linkish" onClick={() => go(`/compare?left=tag:${model}:${t.id}&right=model:${model}`)}>Compare with now</button>{" · "}
                <button className="linkish" onClick={() => apiDownload(`/api/v1/models/${model}/tags/${t.id}/download?format=xlsx`, `${t.name}.xlsx`)}>Excel</button>{" · "}
                <button className="linkish" onClick={() => apiDownload(`/api/v1/models/${model}/tags/${t.id}/download?format=zip`, `${t.name}.zip`)}>zip</button>
                {mayTag && <>{" · "}
                  {!t.locked && <><button className="linkish" onClick={() => setEdit(t)}>Rename</button>{" · "}</>}
                  {(!t.locked || admin) && <button className="linkish" disabled={busy}
                    onClick={() => act(() => post(`/api/v1/models/${model}/tags/${t.id}`, { locked: !t.locked }, "PATCH"),
                      t.locked ? `'${t.name}' unlocked.` : `'${t.name}' locked.`)}>{t.locked ? "Unlock" : "Lock"}</button>}
                  {!t.locked && <>{" · "}<button className="linkish danger-text" disabled={busy} onClick={() => {
                    // eslint-disable-next-line no-alert
                    if (window.confirm(`Delete the tag '${t.name}'? The model is not changed.`)) {
                      act(() => post(`/api/v1/models/${model}/tags/${t.id}`, {}, "DELETE"), `'${t.name}' deleted.`);
                    }
                  }}>Delete</button></>}
                </>}
                {admin && m.kind === "project" && <>{" · "}<button className="linkish" onClick={() => setRestore(t)}>Make this the latest...</button></>}
              </td>
            </tr>
          ))}
          {!data.tags.length && <tr><td colSpan="7" className="quiet">No tags yet.</td></tr>}
        </tbody>
      </table>
      {restore && <RestoreDialog model={model} m={m} t={restore} onClose={() => setRestore(null)} onDone={(out) => { setRestore(null); setMsg(out.note); refreshAll(); }} />}
      {edit && <RenameDialog model={model} t={edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); refreshAll(); }} />}
    </div>
  );
}

// ---------------------------------------------------------------- one tag's page
export function TagPage({ model, m, tagId, entityId }) {
  const { data: t, error } = useApi(`/api/v1/models/${model}/tags/${tagId}`);
  const [view, setView] = useState("entities");
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [restore, setRestore] = useState(null);
  const [edit, setEdit] = useState(null);
  const mayTag = canOn(model, "model.content");
  const admin = canOn(model, "model.lock");
  if (error) return <p className="status bad">{error}</p>;
  if (!t) return <p>Loading...</p>;
  if (entityId) return <TagEntity model={model} t={t} entityId={entityId} />;
  async function act(fn, done) {
    setBusy(true); setErr(""); setMsg("");
    try { await fn(); setMsg(done); refreshAll(); } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  const ql = q.toLowerCase();
  const ents = t.entity_list.filter((e) => (!type || e.type_code === type) && (!q || `${e.name} ${e.display_id}`.toLowerCase().includes(ql)));
  const rels = t.relationship_list.filter((r) => !q || `${r.source_name} ${r.target_name} ${r.relationship_type}`.toLowerCase().includes(ql));
  const mm = t.metamodel;
  return (
    <div className="versions">
      <p><a href={`#/metamodel/${model}/tags`}>← Tags of {t.model.name}</a></p>
      <div className="merge-step">
        <h3>{t.locked && <span title={`Locked by ${t.locked_by} on ${when(t.locked_at)}`}>🔒 </span>}🏷 {t.name}
          {t.kind === "before-restore" && <span className="rchip">automatic</span>}</h3>
        {t.description && <p>{t.description}</p>}
        <table className="kv small"><tbody>
          <tr><th>Model</th><td>{t.model.name}</td></tr>
          <tr><th>Made</th><td>{when(t.created_at)} by {t.created_by}</td></tr>
          <tr><th>Holds</th><td>commit {t.commit} · metamodel v{t.metamodel_version} · {t.entities} entities · {t.relationships} relationships</td></tr>
          <tr><th>Metamodel</th><td>{mm.entity_types} entity types · {mm.attributes} attributes · {mm.relationship_types} relationship types ·
            {" "}{mm.pick_lists} pick lists · {mm.rules} rules · {mm.layers} layers</td></tr>
          {t.locked && <tr><th>Locked</th><td>{when(t.locked_at)} by {t.locked_by}: never changed or deleted</td></tr>}
          {t.restored_at && <tr><th>Made the latest</th><td>{when(t.restored_at)} by {t.restored_by}</td></tr>}
        </tbody></table>
        <div className="toolbar">
          <button onClick={() => go(`/compare?left=tag:${model}:${t.id}&right=model:${model}`)}>Compare with now</button>
          <button onClick={() => apiDownload(`/api/v1/models/${model}/tags/${t.id}/download?format=xlsx`, `${t.name}.xlsx`)}>⬇ Excel</button>
          <button onClick={() => apiDownload(`/api/v1/models/${model}/tags/${t.id}/download?format=zip`, `${t.name}.zip`)}>⬇ zip</button>
          {mayTag && !t.locked && <button onClick={() => setEdit(t)}>Rename</button>}
          {mayTag && (!t.locked || admin) && <button disabled={busy}
            onClick={() => act(() => post(`/api/v1/models/${model}/tags/${t.id}`, { locked: !t.locked }, "PATCH"), t.locked ? "Unlocked." : "Locked.")}>
            {t.locked ? "Unlock" : "Lock"}</button>}
          {admin && m.kind === "project" && <button onClick={() => setRestore(t)}>Make this the latest...</button>}
          {mayTag && !t.locked && <button className="linkish danger-text" disabled={busy} onClick={() => {
            // eslint-disable-next-line no-alert
            if (window.confirm(`Delete the tag '${t.name}'? The model is not changed.`)) {
              act(() => post(`/api/v1/models/${model}/tags/${t.id}`, {}, "DELETE"), "").then(() => go(`/metamodel/${model}/tags`));
            }
          }}>Delete</button>}
        </div>
        {msg && <p className="status ok">{msg}</p>}
        {err && <p className="status bad">{err}</p>}
      </div>
      <div className="toolbar">
        <div className="seg small">
          <button className={view === "entities" ? "on" : ""} onClick={() => setView("entities")}>Entities ({t.entities})</button>
          <button className={view === "types" ? "on" : ""} onClick={() => setView("types")}>By type ({t.types.length})</button>
          <button className={view === "rels" ? "on" : ""} onClick={() => setView("rels")}>Relationships ({t.relationships})</button>
        </div>
        {view === "entities" && <select value={type} onChange={(e) => setType(e.target.value)}><option value="">Every type</option>
          {t.types.map((x) => <option key={x.code} value={x.code}>{x.name} ({x.count})</option>)}</select>}
        {view !== "types" && <input className="search" placeholder="Filter by name" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 220 }} />}
        <span className="quiet small">As frozen in the tag; it never changes.</span>
      </div>
      {view === "types" && (
        <table className="grid-table"><thead><tr><th>Layer</th><th>Entity type</th><th className="num">Entities</th></tr></thead>
          <tbody>{t.types.map((x) => (
            <tr key={x.code}><td className="small">{x.layer}</td>
              <td><button className="linkish" onClick={() => { setType(x.code); setView("entities"); }}>{x.name}</button></td><td className="num">{x.count}</td></tr>
          ))}</tbody></table>
      )}
      {view === "entities" && (
        <table className="grid-table"><thead><tr><th>Entity</th><th>Type</th><th>Display ID</th><th>Status</th><th>Parent</th><th>Values</th></tr></thead>
          <tbody>
            {ents.slice(0, 500).map((e) => (
              <tr key={e.id}><td><a href={`#/metamodel/${model}/tags/${t.id}/${e.id}`}>{e.name}</a></td>
                <td className="small">{e.entity_type} <span className="quiet">· {e.layer}</span></td><td className="small">{e.display_id}</td>
                <td className="small">{e.status}</td><td className="small">{e.parent}</td><td className="num">{e.values}</td></tr>
            ))}
            {ents.length > 500 && <tr><td colSpan="6" className="quiet">The first 500 of {ents.length}: filter, or download the tag as Excel.</td></tr>}
            {!ents.length && <tr><td colSpan="6" className="quiet">Nothing to show.</td></tr>}
          </tbody></table>
      )}
      {view === "rels" && (
        <table className="grid-table"><thead><tr><th>Source</th><th>Relationship</th><th>Target</th></tr></thead>
          <tbody>
            {rels.slice(0, 500).map((r) => (
              <tr key={r.id}><td><a href={`#/metamodel/${model}/tags/${t.id}/${r.source}`}>{r.source_name}</a></td>
                <td className="small">{r.relationship_type}{r.name && <span className="quiet"> · {r.name}</span>}</td>
                <td><a href={`#/metamodel/${model}/tags/${t.id}/${r.target}`}>{r.target_name}</a></td></tr>
            ))}
            {rels.length > 500 && <tr><td colSpan="3" className="quiet">The first 500 of {rels.length}: filter, or download the tag as Excel.</td></tr>}
            {!rels.length && <tr><td colSpan="3" className="quiet">Nothing to show.</td></tr>}
          </tbody></table>
      )}
      {restore && <RestoreDialog model={model} m={m} t={restore} onClose={() => setRestore(null)} onDone={(out) => { setRestore(null); setMsg(out.note); refreshAll(); }} />}
      {edit && <RenameDialog model={model} t={edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); refreshAll(); }} />}
    </div>
  );
}

function TagEntity({ model, t, entityId }) {
  const { data: e, error } = useApi(`/api/v1/models/${model}/tags/${t.id}/entities/${entityId}`);
  if (error) return <p className="status bad">{error}</p>;
  if (!e) return <p>Loading...</p>;
  const link = (id, name) => <a href={`#/metamodel/${model}/tags/${t.id}/${id}`}>{name}</a>;
  return (
    <div className="versions">
      <p><a href={`#/metamodel/${model}/tags/${t.id}`}>← 🏷 {t.name}</a> · <a href={`#/metamodel/${model}/tags`}>Tags of {t.model.name}</a></p>
      <div className="merge-step">
        <h3>{e.name} <span className="quiet">· {e.entity_type} · {e.layer}</span></h3>
        <p className="quiet small">As it was in the tag <b>{t.name}</b> ({when(t.created_at)}).{" "}
          {e.exists_now ? <a href={`#/metamodel/${model}/entity/${e.id}`}>Open it as it is now ↗</a> : <span className="status bad">It is no longer in {t.model.name}.</span>}
          {" · "}<a href={`#/compare?left=tag:${model}:${t.id}&right=model:${model}`}>Compare the tag with now</a></p>
        <table className="kv small"><tbody>
          {e.display_id && <tr><th>Display ID</th><td>{e.display_id}</td></tr>}
          <tr><th>Description</th><td>{show(e.description)}</td></tr>
          <tr><th>Status</th><td>{show(e.status)}</td></tr>
          {e.parent && <tr><th>Parent</th><td>{link(e.parent.id, e.parent.name || e.parent.id)}</td></tr>}
          {e.tags.length > 0 && <tr><th>Tags</th><td>{e.tags.join(", ")}</td></tr>}
          {e.values.map((v) => <tr key={v.code}><th>{v.label}</th><td>{show(v.value)}</td></tr>)}
        </tbody></table>
      </div>
      <h4>Relationships ({e.relationships.length})</h4>
      <table className="grid-table"><tbody>
        {e.relationships.map((r) => (
          <tr key={r.id}><td className="small">{r.direction === "out" ? `${r.verb || r.relationship_type} →` : `← ${r.verb || r.relationship_type}`}</td>
            <td>{r.in_tag ? link(r.other, r.other_name) : r.other_name}</td><td className="quiet small">{r.relationship_type}</td></tr>
        ))}
        {!e.relationships.length && <tr><td className="quiet">No relationships.</td></tr>}
      </tbody></table>
    </div>
  );
}

function RenameDialog({ model, t, onClose, onDone }) {
  const [name, setName] = useState(t.name);
  const [desc, setDesc] = useState(t.description || "");
  const [err, setErr] = useState("");
  async function save() {
    try { await post(`/api/v1/models/${model}/tags/${t.id}`, { name, description: desc }, "PATCH"); onDone(); } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={`Rename the tag '${t.name}'`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!name.trim()} onClick={save}>Save</button></>}>
      <div className="ed-form">
        <label className="ed-field"><span>Name</span><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
        <label className="ed-field"><span>What it is</span><textarea value={desc} onChange={(e) => setDesc(e.target.value)} /></label>
        {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}

function RestoreDialog({ model, m, t, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [typed, setTyped] = useState("");
  async function go2() {
    setBusy(true); setErr("");
    try { onDone(await post(`/api/v1/models/${model}/tags/${t.id}/restore`, {})); } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Make '${t.name}' the latest version of ${m.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="danger" disabled={busy || typed.trim() !== t.name} onClick={go2}>{busy ? "Restoring..." : "Overwrite the model"}</button></>}>
      <p>This is a complete override, like restoring an old backup on top of the model:</p>
      <ol>
        <li>The model as it is now is tagged first (an automatic tag, <em>Before restore</em> with the date and time): nothing is lost.</li>
        <li>The metamodel becomes the tag's: entity types, attributes, relationship types and pick lists added since are removed.</li>
        <li>The content becomes the tag's: entities and relationships added since are deleted, the others set back as they were.
          Everyone sees it at once (one commit).</li>
      </ol>
      <p>To go back, make the automatic tag the latest again. Uncommitted changes people have in {m.name} may no longer fit.</p>
      <label className="ed-field"><span>Type the tag's name to confirm: <b>{t.name}</b></span>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus /></label>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// ================================================================ Compare
// Compare and Gap analyses: first-class screens of the top menu (D177), not inside a model
export default function CompareScreen({ route }) {
  const [, , sub, id] = (route || "").replace(/^#/, "").split("?")[0].split("/");
  return (
    <div className="versions">
      <h2>{sub === "gaps" ? "Gap analyses" : "Compare"}</h2>
      <div className="toolbar">
        <div className="seg small" role="tablist">
          <button className={sub !== "gaps" ? "on" : ""} onClick={() => go("/compare")}>Compare</button>
          <button className={sub === "gaps" ? "on" : ""} onClick={() => go("/compare/gaps")}>Gap analyses</button>
        </div>
      </div>
      {sub === "gaps" ? (id === "results" ? <GapResultsCompared key={route} /> : id ? <GapAnalysis key={id} id={id} /> : <GapList key={route} />) : <Comparison key={route} />}
    </div>
  );
}

// one side: a model (any the person may open) as it is now, or one of its tags
function SidePicker({ label, value, onChange }) {
  const { data: models } = useApi("/api/v1/models?archived=false");
  const { data: tags } = useApi(value.model ? `/api/v1/models/${value.model}/tags` : null);
  const list = (models || []).filter((x) => x.kind !== "template");
  return (
    <div className="side-picker">
      <b>{label}</b>
      <select value={value.model || ""} onChange={(e) => onChange({ model: e.target.value, tag: "" })}>
        <option value="">Choose a model...</option>
        {list.map((x) => <option key={x.id} value={x.id}>{x.name}{x.version_label ? ` ${x.version_label}` : ""}</option>)}
      </select>
      <select value={value.tag || ""} onChange={(e) => onChange({ ...value, tag: e.target.value })} disabled={!value.model}>
        <option value="">as it is now</option>
        {(tags?.tags || []).map((t) => <option key={t.id} value={t.id}>🏷 {t.name} ({fmtDate(t.created_at)})</option>)}
      </select>
    </div>
  );
}

const sideOf = (v) => (v.tag ? { kind: "tag", id: v.tag } : { kind: "model", id: v.model });
// a side in the address: model:<model> (as it is now) or tag:<model>:<tag>
function parseSide(s) {
  if (!s) return null;
  const [kind, a, b] = s.split(":");
  return kind === "tag" ? { model: a, tag: b || "" } : { model: a, tag: "" };
}

function Comparison() {
  const params = new URLSearchParams((window.location.hash.split("?")[1]) || "");
  const start = params.get("model") || "";   // from a model's Actions menu: its latest tag against it now
  const { data: mine } = useApi(start ? `/api/v1/models/${start}/tags` : null);
  const [left, setLeft] = useState(() => parseSide(params.get("left")) || { model: start, tag: "" });
  const [right, setRight] = useState(() => parseSide(params.get("right")) || { model: start, tag: "" });
  useEffect(() => {
    if (start && mine?.tags?.length && !left.tag && left.model === start) setLeft({ model: start, tag: mine.tags[0].id });
  }, [mine]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [info, setInfo] = useState(null);
  const [settings, setSettings] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [saveGap, setSaveGap] = useState(false);
  const ready = left.model && right.model;
  async function filters() {
    setBusy("fields"); setErr(""); setResult(null);
    try {
      const out = await post("/api/v1/compare/fields", { left: sideOf(left), right: sideOf(right) });
      setInfo(out); setSettings(out.defaults);
    } catch (e) { setErr(e.message); }
    setBusy("");
  }
  async function run() {
    setBusy("compare"); setErr("");
    try { setResult(await post("/api/v1/compare", { left: sideOf(left), right: sideOf(right), settings })); } catch (e) { setErr(e.message); }
    setBusy("");
  }
  return (
    <div>
      <div className="merge-step">
        <h3>1. What to compare</h3>
        <SidePicker label="Baseline (left)" value={left} onChange={(v) => { setLeft(v); setInfo(null); setResult(null); }} />
        <SidePicker label="Target (right)" value={right} onChange={(v) => { setRight(v); setInfo(null); setResult(null); }} />
        <div className="toolbar">
          <button className="primary" disabled={!ready || !!busy} onClick={filters}>{busy === "fields" ? "Reading..." : "Next: choose what counts"}</button>
          <button disabled={!ready || !!busy} onClick={async () => { setSettings(null); await run(); }} title="Compare with the tool's defaults">Compare with the defaults</button>
        </div>
      </div>
      {info && settings && <FilterScreen info={info} settings={settings} setSettings={setSettings} onCompare={run} busy={busy === "compare"} />}
      {err && <p className="status bad">{err}</p>}
      {result && (
        <CompareResult result={result} actions={<>
          <button onClick={() => apiDownload("/api/v1/compare/download", "comparison.xlsx", { left: sideOf(left), right: sideOf(right), settings })}>⬇ Excel</button>
          <button className="primary" onClick={() => setSaveGap(true)}>Save as a gap analysis...</button>
        </>} />
      )}
      {saveGap && <NewGapDialog baseline={left} target={right} settings={settings} onClose={() => setSaveGap(false)} />}
    </div>
  );
}

// the filter screen: per entity type the fields to compare (the tool's defaults ticked), relationship types, metamodel
function FilterScreen({ info, settings, setSettings, onCompare, busy }) {
  const { data: profiles } = useApi("/api/v1/compare-profiles");
  const [open, setOpen] = useState({});
  const [pname, setPname] = useState("");
  const [loaded, setLoaded] = useState(null);
  const me = (myInfo()?.username || "").toLowerCase();
  const [msg, setMsg] = useState("");
  const types = settings.types || {};
  const setType = (code, fields) => setSettings((s) => {
    const t = { ...(s.types || {}) };
    if (fields === null) delete t[code]; else t[code] = fields;
    return { ...s, types: t };
  });
  const flip = (code, f) => {
    const cur = types[code] || [];
    setType(code, cur.includes(f) ? cur.filter((x) => x !== f) : [...cur, f]);
  };
  const byLayer = useMemo(() => {
    const out = {};
    info.types.forEach((t) => { (out[t.layer || "Other"] = out[t.layer || "Other"] || []).push(t); });
    return out;
  }, [info]);
  async function saveProfile() {
    setMsg("");
    try { await post("/api/v1/compare-profiles", { name: pname, settings }); setMsg(`Saved as '${pname}' for everyone.`); setPname(""); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  async function dropProfile(p) {
    setMsg("");
    try { await post(`/api/v1/compare-profiles/${p.id}`, {}, "DELETE"); setMsg(`Profile '${p.name}' deleted.`); setLoaded(null); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <div className="merge-step">
      <h3>2. Choose what counts</h3>
      <p className="quiet small">
        Ticked types are compared on their ticked fields and relationships: press + on a type to choose them. The tool proposes name,
        description, parent, every attribute and every relationship; status, tags and display ID are left out; system fields (ids, dates,
        who changed it) never count. A relationship counts under the type at either end that has it ticked. The two sides need not have the
        same types or attributes: a type only one side has shows its entities as new or eliminated, and an attribute only one side has is
        marked and left out unless you tick it. <b>{info.left.label}</b> against <b>{info.right.label}</b>.
      </p>
      <div className="toolbar">
        <select value="" onChange={(e) => { const p = (profiles || []).find((x) => x.id === e.target.value); if (p) { setSettings(p.settings); setLoaded(p); setMsg(`Profile '${p.name}' loaded.`); } }}>
          <option value="">Load a saved profile...</option>
          {(profiles || []).map((p) => <option key={p.id} value={p.id}>{p.name} (by {p.created_by})</option>)}
        </select>
        {loaded && loaded.created_by === me && <button className="linkish danger-text" onClick={() => dropProfile(loaded)}>Delete '{loaded.name}'</button>}
        <button onClick={() => setSettings(info.defaults)}>The tool's defaults</button>
        <button onClick={() => setSettings({ ...settings, types: {} })}>Untick all types</button>
        <span className="tabs-right">
          <input placeholder="Save as profile..." value={pname} onChange={(e) => setPname(e.target.value)} style={{ width: 180 }} />
          <button disabled={!pname.trim()} onClick={saveProfile}>Save</button>
        </span>
      </div>
      {msg && <p className="quiet">{msg}</p>}
      <div className="filter-grid">
        {Object.entries(byLayer).map(([layer, list]) => (
          <div key={layer} className="filter-layer">
            <h4>{layer}</h4>
            {list.map((t) => {
              const on = !!types[t.code];
              const chosen = types[t.code] || [];
              const fieldsOf = t.fields.filter((f) => f.section !== "Relationships");
              const relsOf = t.fields.filter((f) => f.section === "Relationships");
              const group = (fs, all) => setType(t.code, all ? [...new Set([...chosen, ...fs.map((f) => f.code)])]
                : chosen.filter((c) => !fs.some((f) => f.code === c)));
              const nF = fieldsOf.filter((f) => chosen.includes(f.code)).length;
              const nR = relsOf.filter((f) => chosen.includes(f.code)).length;
              return (
                <div key={t.code} className={`filter-type${on ? " on" : ""}`}>
                  <button className="linkish plus" aria-expanded={!!open[t.code]} title="Choose its fields and relationships"
                    onClick={() => setOpen((o) => ({ ...o, [t.code]: !o[t.code] }))}>{open[t.code] ? "−" : "+"}</button>
                  <label><input type="checkbox" checked={on} onChange={() => setType(t.code, on ? null : t.fields.filter((f) => f.default).map((f) => f.code))} />
                    {" "}{t.name} <span className="quiet small">{t.left} / {t.right}</span>
                    {!t.in_left && <span className="only-badge" title="This entity type is only in the target's metamodel">target only</span>}
                    {!t.in_right && <span className="only-badge" title="This entity type is only in the baseline's metamodel">baseline only</span>}</label>
                  {on && <span className="quiet small"> · {nF} fields, {nR} relationships</span>}
                  {open[t.code] && (
                    <div className="filter-fields-box">
                      <div className="filter-group"><b>Fields</b> <button className="linkish small" onClick={() => group(fieldsOf, true)}>all</button>{" "}
                        <button className="linkish small" onClick={() => group(fieldsOf, false)}>none</button></div>
                      <div className="filter-fields">
                        {fieldsOf.map((f) => (
                          <label key={f.code} title={f.only ? `Only the ${f.only === "left" ? "baseline" : "target"}'s ${t.name} has this attribute` : undefined}>
                            <input type="checkbox" checked={chosen.includes(f.code)} onChange={() => flip(t.code, f.code)} /> {f.label}
                            {f.only && <span className="only-badge">{f.only === "left" ? "baseline only" : "target only"}</span>}</label>
                        ))}
                      </div>
                      <div className="filter-group"><b>Relationships</b> <button className="linkish small" onClick={() => group(relsOf, true)}>all</button>{" "}
                        <button className="linkish small" onClick={() => group(relsOf, false)}>none</button></div>
                      <div className="filter-fields">
                        {relsOf.map((f) => (
                          <label key={f.code} title={`${f.label}: ${f.others.join(", ")}`} className={f.used ? "" : "quiet"}>
                            <input type="checkbox" checked={chosen.includes(f.code)} onChange={() => flip(t.code, f.code)} /> {f.label}
                            <span className="quiet small"> {f.others.slice(0, 3).join(", ")}{f.others.length > 3 ? ` +${f.others.length - 3}` : ""}</span></label>
                        ))}
                        {!relsOf.length && <span className="quiet small">No relationships.</span>}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <label><input type="checkbox" checked={settings.metamodel !== false} onChange={(e) => setSettings({ ...settings, metamodel: e.target.checked })} />
        {" "}Compare the metamodels too{info.metamodel_differs ? " (they differ)" : " (they are the same)"}</label>
      <div className="toolbar"><button className="primary" disabled={busy || !Object.keys(types).length} onClick={onCompare}>{busy ? "Comparing..." : "3. Compare"}</button></div>
    </div>
  );
}

function sideLink(side, guid) {
  if (!side || !guid) return null;
  if (side.kind === "tag" && side.tag_id) return `#/metamodel/${side.model_id}/tags/${side.tag_id}/${guid}`;   // as frozen in the tag
  return side.kind === "model" ? `#/metamodel/${side.model_id}/entity/${guid}` : null;
}

const specOf = (l) => (l.kind === "tag" ? { kind: "tag", id: l.tag_id } : { kind: "model", id: l.model_id });

// one element side by side: its two versions (baseline and target), every field, value and relationship, differences marked
function SideBySide({ path, body, title, onClose }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [only, setOnly] = useState(false);
  useEffect(() => {
    (body ? post(path, body) : apiFetch(path)).then(setD).catch((e) => setErr(e.message));
  }, [path]);
  const L = d?.left, R = d?.right;
  const fields = d ? d.fields.filter((f) => !only || f.differs || f.only) : [];
  const rels = d ? d.relationships.filter((r) => !only || !(r.left && r.right)) : [];
  return (
    <Modal wide title={title} onClose={onClose} actions={<button onClick={onClose}>Close</button>}>
      {err && <p className="status bad">{err}</p>}
      {!d && !err && <p>Loading...</p>}
      {d && <>
        <p className="quiet small">
          {d.gap && <><b>{d.gap.togaf_cell}</b>{d.gap.resolution && <> · resolution <b>{d.gap.resolution}</b></>}{d.gap.note && <> · {d.gap.note}</>}<br /></>}
          {d.status === "new" ? "Only in the target: a new element." : d.status === "eliminated" ? "Only in the baseline: an eliminated element."
            : d.differences ? `${d.differences} difference${d.differences > 1 ? "s" : ""}, highlighted.` : "The two versions are the same."}
          {" "}A model side shows the model as it is now; a tag as frozen.
        </p>
        <label className="small"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} /> Only the differences</label>
        <table className="grid-table attr-table side-by-side">
          <thead><tr><th>Field</th>
            <th>Baseline: {L.label}{L.entity && sideLink(L, L.entity.id) && <> <a className="small" href={sideLink(L, L.entity.id)} target="_blank" rel="noreferrer">↗</a></>}</th>
            <th>Target: {R.label}{R.entity && sideLink(R, R.entity.id) && <> <a className="small" href={sideLink(R, R.entity.id)} target="_blank" rel="noreferrer">↗</a></>}</th></tr></thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f.field} className={f.differs ? "sbs-differs" : ""}>
                <th>{f.label}{f.only && <span className="only-badge">{f.only === "left" ? "baseline only" : "target only"}</span>}</th>
                <td className={f.differs ? "sbs-old" : ""}>{L.entity ? show(f.left) : <span className="quiet">not in the baseline</span>}</td>
                <td className={f.differs ? "sbs-new" : ""}>{R.entity ? show(f.right) : <span className="quiet">not in the target</span>}</td>
              </tr>
            ))}
            {!fields.length && <tr><td colSpan="3" className="quiet">No field differs.</td></tr>}
            <tr className="sbs-section"><th colSpan="3">Relationships</th></tr>
            {rels.map((r, k) => {
              const text = r.direction === "out" ? <>{r.verb || r.relationship_type} → <b>{r.other}</b></> : <>← {r.verb || r.relationship_type} <b>{r.other}</b></>;
              return (
                <tr key={k} className={r.left && r.right ? "" : "sbs-differs"}>
                  <th className="quiet small">{r.relationship_type}</th>
                  <td className={r.left && !r.right ? "sbs-old" : ""}>{r.left ? text : <span className="quiet">-</span>}</td>
                  <td className={r.right && !r.left ? "sbs-new" : ""}>{r.right ? text : <span className="quiet">-</span>}</td>
                </tr>
              );
            })}
            {!rels.length && <tr><td colSpan="3" className="quiet">{only ? "No relationship differs." : "No relationships."}</td></tr>}
          </tbody>
        </table>
      </>}
    </Modal>
  );
}

export function CompareResult({ result, actions }) {
  const [detail, setDetail] = useState(null);
  const [status, setStatus] = useState("changes");
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState({});
  const [view, setView] = useState("entities");
  const t = result.totals;
  const items = result.items.filter((i) => (status === "changes" ? i.status !== "kept" : status === "all" || i.status === status)
    && (!type || i.entity_type === type) && (!q || i.name.toLowerCase().includes(q.toLowerCase())));
  return (
    <div className="merge-step">
      <h3>{result.left.label} → {result.right.label}</h3>
      <div className="merge-stats">
        {["changed", "new", "eliminated", "kept"].map((s) => (
          <button key={s} className={status === s ? "on" : ""} onClick={() => { setStatus(s); setView("entities"); }}><b>{t[s]}</b> {STATUS[s].toLowerCase()}</button>
        ))}
        <button className={view === "relationships" ? "on" : ""} onClick={() => setView("relationships")}>
          <b>{result.relationship_totals.new + result.relationship_totals.eliminated + result.relationship_totals.changed}</b> relationship differences</button>
        <button className={view === "metamodel" ? "on" : ""} onClick={() => setView("metamodel")}><b>{result.metamodel.length}</b> metamodel differences</button>
      </div>
      <div className="toolbar">{actions}</div>
      {view === "entities" && <>
        <table className="grid-table compare-summary">
          <colgroup><col style={{ width: "18%" }} /><col style={{ width: "34%" }} /><col /><col /><col /><col /></colgroup>
          <thead><tr><th>Layer</th><th>Entity type</th><th className="num">Kept</th><th className="num">Changed</th><th className="num">New</th><th className="num">Eliminated</th></tr></thead>
          <tbody>
            {result.summary.filter((s) => s.changed + s.new + s.eliminated + s.kept).map((s) => (
              <tr key={s.entity_type} className={type === s.entity_type ? "on" : ""} onClick={() => setType(type === s.entity_type ? "" : s.entity_type)} style={{ cursor: "pointer" }}>
                <td className="quiet">{s.layer}</td><td>{s.name}</td><td className="num">{s.kept || ""}</td><td className="num">{s.changed || ""}</td>
                <td className="num">{s.new || ""}</td><td className="num">{s.eliminated || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="toolbar">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="changes">Every difference</option><option value="all">Everything</option>
            {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          {type && <button className="linkish" onClick={() => setType("")}>All types</button>}
          <input className="search" placeholder="Filter by name" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
          <span className="quiet">{items.length} shown</span>
        </div>
        <table className="grid-table">
          <thead><tr><th>Status</th><th>Entity type</th><th>Baseline</th><th>Target</th><th>What changed</th></tr></thead>
          <tbody>
            {items.slice(0, 500).map((i, k) => (
              <Fragment key={k}>
                <tr className={`cmp-${i.status}`}>
                  <td>{STATUS[i.status]}{i.renamed && <span className="rchip">renamed</span>}</td>
                  <td className="quiet">{i.entity_type_name}</td>
                  <td>{i.left ? <>{i.left.name} <span className="quiet small">{i.left.display_id}</span> {sideLink(result.left, i.left.guid) && <a className="small" href={sideLink(result.left, i.left.guid)} target="_blank" rel="noreferrer">↗</a>}</> : <span className="quiet">-</span>}</td>
                  <td>{i.right ? <>{i.right.name} <span className="quiet small">{i.right.display_id}</span> {sideLink(result.right, i.right.guid) && <a className="small" href={sideLink(result.right, i.right.guid)} target="_blank" rel="noreferrer">↗</a>}</> : <span className="quiet">-</span>}</td>
                  <td className="small">{i.changes.length > 0 && (
                    <button className="linkish" onClick={() => setOpen((o) => ({ ...o, [k]: !o[k] }))}>{i.changes.map((c) => c.label).join(", ")}</button>)}
                    <button className="linkish sbs-btn" title="Both versions side by side: every field, value and relationship"
                      onClick={() => setDetail(i)}>⇆ details</button></td>
                </tr>
                {open[k] && i.changes.map((c) => (
                  <tr key={`${k}-${c.field}`} className="cmp-detail"><td /><td className="quiet small">{c.label}</td>
                    <td className="small"><s>{show(c.left)}</s></td><td className="small">{show(c.right)}</td><td /></tr>
                ))}
              </Fragment>
            ))}
            {items.length > 500 && <tr><td colSpan="5" className="quiet">And {items.length - 500} more: download the Excel workbook for every row.</td></tr>}
            {!items.length && <tr><td colSpan="5" className="quiet">Nothing to show.</td></tr>}
          </tbody>
        </table>
      </>}
      {detail && <SideBySide path="/api/v1/compare/detail" title={`${detail.name}: baseline and target side by side`} onClose={() => setDetail(null)}
        body={{ left: specOf(result.left), right: specOf(result.right), left_entity: detail.left?.guid || null, right_entity: detail.right?.guid || null }} />}
      {view === "relationships" && (
        <table className="grid-table">
          <thead><tr><th>Status</th><th>Relationship</th><th>Source</th><th>Target</th></tr></thead>
          <tbody>
            {result.relationships.filter((r) => r.status !== "kept").slice(0, 500).map((r, k) => (
              <tr key={k} className={`cmp-${r.status}`}><td>{STATUS[r.status]}</td><td>{r.relationship_type}</td><td>{r.source}</td><td>{r.target}</td></tr>
            ))}
            {!result.relationships.some((r) => r.status !== "kept") && <tr><td colSpan="4" className="quiet">The relationships are the same.</td></tr>}
          </tbody>
        </table>
      )}
      {view === "metamodel" && (
        <table className="grid-table">
          <thead><tr><th>Part</th><th>Code</th><th>Name</th><th>Change</th><th>Fields</th></tr></thead>
          <tbody>
            {result.metamodel.map((d, k) => (
              <tr key={k} className={`cmp-${d.change === "added" ? "new" : d.change === "removed" ? "eliminated" : "changed"}`}>
                <td>{d.section.replace("_", " ")}</td><td>{d.code}</td><td>{d.name}</td><td>{d.change}</td>
                <td className="small">{d.fields.map((f) => `${f.field}: ${f.old ?? ""} → ${f.new ?? ""}`).join("; ")}</td>
              </tr>
            ))}
            {!result.metamodel.length && <tr><td colSpan="5" className="quiet">The metamodels are the same (or were not compared).</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ================================================================ gap analyses
function NewGapDialog({ baseline, target, settings, onClose }) {
  const { data } = useApi("/api/v1/gaps");
  const { data: models } = useApi("/api/v1/models?archived=false");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [template, setTemplate] = useState("all");
  const [left, setLeft] = useState(baseline || { model: "", tag: "" });
  const [right, setRight] = useState(target || { model: "", tag: "" });
  const [store, setStore] = useState("");
  const [own, setOwn] = useState(!!settings);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const tpl = (data?.templates || []).find((t) => t.code === template);
  // the gaps are stored in a project model that is not locked, where you may change content (it may be the baseline's or target's)
  const stores = (models || []).filter((x) => x.kind === "project" && !x.is_locked && canOn(x.id, "model.content"));
  const storeId = store || [right.model, left.model].find((x) => stores.some((y) => y.id === x)) || "";
  async function save() {
    setBusy(true); setErr("");
    try {
      const out = await post("/api/v1/gaps", {
        store_in: storeId, name, description: desc, template, baseline: sideOf(left), target: sideOf(right),
        settings: own && settings ? settings : null,
      });
      refreshAll(); onClose(); go(`/compare/gaps/${out.id}`);
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal wide title="New gap analysis" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy || !name.trim() || !storeId || !(left.model && right.model)} onClick={save}>{busy ? "Comparing..." : "Compare and keep"}</button></>}>
      <div className="ed-form">
        <label className="ed-field"><span>Name</span><input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="e.g. Applications 2026 to 2028" /></label>
        <SidePicker label="Source (baseline)" value={left} onChange={setLeft} />
        <SidePicker label="Target" value={right} onChange={setRight} />
        <label className="ed-field"><span>Store the gaps in</span>
          <select value={storeId} onChange={(e) => setStore(e.target.value)}>
            <option value="">Choose a model...</option>
            {stores.map((x) => <option key={x.id} value={x.id}>{x.name}{x.id === left.model ? " (the baseline's model)" : x.id === right.model ? " (the target's model)" : ""}</option>)}
          </select></label>
        <p className="quiet small">The analysis, its decisions and any Gap entities live in this model: its readers see the analysis, its Architects
          and above decide the gaps, its Model Admins add Gap entities. A project model that is not locked, where you may change content.
          {!stores.length && " You have no such model: ask a Model Admin for a role on one."}</p>
        <label className="ed-field"><span>TOGAF template</span>
          <select value={template} onChange={(e) => setTemplate(e.target.value)}>
            {(data?.templates || []).map((t) => <option key={t.code} value={t.code}>{t.name} (phase {t.phase})</option>)}
          </select></label>
        {tpl && <p className="quiet small">{tpl.purpose}{tpl.types ? ` Compares: ${tpl.types.join(", ")}.` : ""}</p>}
        {settings && <label><input type="checkbox" checked={own} onChange={(e) => setOwn(e.target.checked)} /> Use the types and fields I chose instead of the template's</label>}
        <label className="ed-field"><span>What it is for (optional)</span><textarea value={desc} onChange={(e) => setDesc(e.target.value)} /></label>
        {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}

function GapList() {
  const params = new URLSearchParams((window.location.hash.split("?")[1]) || "");
  const { data, error } = useApi("/api/v1/gaps");
  const [creating, setCreating] = useState(false);
  const [store, setStore] = useState(params.get("model") || "");
  const [q, setQ] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const stores = [...new Map(data.analyses.map((a) => [a.model_id, a.model_name])).entries()].sort((x, y) => x[1].localeCompare(y[1]));
  const rows = data.analyses.filter((a) => (!store || a.model_id === store || a.baseline_model === store || a.target_model === store)
    && (!q || `${a.name} ${a.baseline} ${a.target} ${a.model_name}`.toLowerCase().includes(q.toLowerCase())));
  return (
    <div>
      <p className="quiet">
        A gap analysis compares a source (baseline) with a target the TOGAF way, each any model as it is now or one of its tags: each element
        is included, changed, new (to build or buy) or eliminated (to retire, replace, or add back if omitted by accident). It is stored in a
        model you choose, with its notes, resolutions and work packages; its gaps can be added to that model as Gap entities, and appear in
        the reports GR-01 to GR-05.
      </p>
      <div className="toolbar">
        <button className="primary" onClick={() => setCreating(true)}>+ New gap analysis</button>
        <select value={store} onChange={(e) => setStore(e.target.value)}><option value="">Every model</option>
          {stores.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select>
        <input className="search" placeholder="Filter by name" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
        <span className="quiet small">{rows.length} of {data.analyses.length}</span>
      </div>
      <table className="grid-table">
        <thead><tr><th>Gap analysis</th><th>Stored in</th><th>Template</th><th>Source (baseline)</th><th>Target</th><th>Compared</th><th className="num">Gaps</th><th className="num">Undecided</th></tr></thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <td><a href={`#/compare/gaps/${a.id}`}><strong>{a.name}</strong></a>{a.description && <div className="quiet small">{a.description}</div>}</td>
              <td className="small"><a href={`#/metamodel/${a.model_id}`}>{a.model_name}</a></td>
              <td className="small">{a.template_name}</td><td className="small">{a.baseline}</td><td className="small">{a.target}</td>
              <td className="small">{when(a.compared_at)}<br /><span className="quiet">{a.compared_by}</span></td>
              <td className="num">{a.gaps}</td><td className="num">{a.undecided || ""}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan="8" className="quiet">{data.analyses.length ? "No gap analysis matches." : "No gap analyses yet."}</td></tr>}
        </tbody>
      </table>
      <GapResults />
      {creating && <NewGapDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

// every result of every gap analysis (each time one was made or compared again): filter by name, delete, or tick two to compare
function GapResults() {
  const [q, setQ] = useState("");
  const [store, setStore] = useState("");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [limit, setLimit] = useState(50);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const { data } = useApi("/api/v1/gap-runs");
  const runs = data ? data.runs : [];
  const stores = [...new Map(runs.map((r) => [r.model_id, r.model_name])).entries()].sort((x, y) => x[1].localeCompare(y[1]));
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const rows = runs.filter((r) => (!store || r.model_id === store)
    && words.every((w) => `${r.analysis} #${r.number} ${r.baseline} ${r.target} ${r.model_name} ${r.compared_by}`.toLowerCase().includes(w)));
  async function remove(r) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete the result '${r.analysis} #${r.number}' now, with the Gap entities made from it in ${r.model_name}? `
      + "This is not a draft: it happens at once. Gap entities a later result brought up to date stay and only lose this result's tag. "
      + "The gap analysis, its gaps, notes and other results stay.")) return;
    setErr(""); setMsg("");
    try {
      const out = await post(`/api/v1/gap-runs/${r.id}`, {}, "DELETE");
      setMsg(out.note);
      if (a === r.id) setA("");
      if (b === r.id) setB("");
      refreshAll();
    } catch (e) { setErr(e.message); }
  }
  const pick = (id) => {   // the first tick is A (earlier), the second B (later); a third replaces B
    if (a === id) { setA(""); return; }
    if (b === id) { setB(""); return; }
    if (!a) setA(id); else setB(id);
  };
  const label = (id) => (runs.find((r) => r.id === id) || {}).label;
  return (
    <div className="merge-step gap-runs-box">
      <h4>Gap analysis results</h4>
      <p className="quiet small">
        Each time a gap analysis is made or compared again its result is kept (#1, #2...); Gap entities made from it carry the
        result's tag. Tick two results, of one analysis or of two, and compare them to see which gaps closed, which are new and
        which changed status or resolution; the comparison shows here and downloads as Excel or CSV. Nothing is saved.
      </p>
      <div className="toolbar">
        <input className="search" placeholder="Filter results by name" value={q} onChange={(e) => { setQ(e.target.value); setLimit(50); }} style={{ maxWidth: 260 }} />
        <select value={store} onChange={(e) => setStore(e.target.value)}><option value="">Every model</option>
          {stores.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select>
        <span className="quiet small">{rows.length} of {runs.length}</span>
        <span className="tabs-right">
          <span className="small">{a ? <>A: <b>{label(a)}</b></> : "Tick A (earlier)"} · {b ? <>B: <b>{label(b)}</b></> : "then B (later)"}</span>{" "}
          <button className="primary" disabled={!a || !b} onClick={() => go(`/compare/gaps/results?a=${a}&b=${b}`)}>Compare</button>
          {(a || b) && <button className="linkish" onClick={() => { setA(""); setB(""); }}>Clear</button>}
        </span>
      </div>
      {err && <p className="status bad">{err}</p>}
      {msg && <p className="status ok">{msg}</p>}
      <table className="grid-table">
        <thead><tr><th>A / B</th><th>Result</th><th>Stored in</th><th>Source (baseline)</th><th>Target</th><th>Compared</th>
          <th className="num">New</th><th className="num">Eliminated</th><th className="num">Changed</th><th /></tr></thead>
        <tbody>
          {rows.slice(0, limit).map((r) => (
            <tr key={r.id} className={r.id === a || r.id === b ? "picked" : ""}>
              <td><button className={`linkish pick-ab${r.id === a || r.id === b ? " on" : ""}`} onClick={() => pick(r.id)}
                title="Tick to compare: the first tick is A (earlier), the second B (later)">{r.id === a ? "A" : r.id === b ? "B" : "☐"}</button></td>
              <td><a href={`#/compare/gaps/${r.analysis_id}`}><strong>{r.analysis}</strong></a> #{r.number}{r.is_latest && <span className="quiet small"> (latest)</span>}</td>
              <td className="small">{r.model_name}</td><td className="small">{r.baseline}</td><td className="small">{r.target}</td>
              <td className="small">{when(r.compared_at)}<br /><span className="quiet">{r.compared_by}</span></td>
              <td className="num">{r.totals.new || 0}</td><td className="num">{r.totals.eliminated || 0}</td><td className="num">{r.totals.changed || 0}</td>
              <td>{canOn(r.model_id, "model.content") && <button className="linkish danger-text" onClick={() => remove(r)}
                title="Delete this result and its Gap entities at once; the analysis and its other results stay">Delete</button>}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan="10" className="quiet">{runs.length ? "No result matches." : "No results yet: make a gap analysis."}</td></tr>}
        </tbody>
      </table>
      {rows.length > limit && <p><button className="linkish" onClick={() => setLimit(limit + 100)}>Show more ({rows.length - limit} not shown)</button></p>}
    </div>
  );
}

const RUN_CHANGES = ["New gap", "Gap closed", "Status changed", "Resolution changed", "Unchanged gap", "Not a gap in either"];
const RUN_CLASS = { "New gap": "row-new", "Gap closed": "row-closed", "Status changed": "row-moved", "Resolution changed": "row-moved" };

// two gap results compared, on screen, with downloads (Excel, CSV)
function GapResultsCompared() {
  const params = new URLSearchParams((window.location.hash.split("?")[1]) || "");
  const a = params.get("a");
  const b = params.get("b");
  const { data, error } = useApi(a && b ? `/api/v1/gap-runs/compare?a=${a}&b=${b}&format=json` : null);
  const [picked, setChange] = useState(null);   // null: what moved, or everything when nothing moved
  const [layer, setLayer] = useState("");
  const [q, setQ] = useState("");
  if (!a || !b) return <p className="status bad">Choose two results to compare. <a href="#/compare/gaps">← Gap analyses</a></p>;
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Comparing...</p>;
  const moved = data.rows.filter((r) => !["Unchanged gap", "Not a gap in either"].includes(r.change)).length;
  const change = picked || (moved ? "changes" : "all");
  const layers = [...new Set(data.rows.map((r) => r.layer))].filter(Boolean).sort();
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const rows = data.rows.filter((r) => (change === "all" || (change === "changes" ? !["Unchanged gap", "Not a gap in either"].includes(r.change) : r.change === change))
    && (!layer || r.layer === layer) && words.every((w) => `${r.name} ${r.entity_type_name}`.toLowerCase().includes(w)));
  const file = `${data.a.label} vs ${data.b.label}`.replace(/[^\w .#()-]+/g, "-").slice(0, 120);
  const side = (k) => (<tr><th>{k.toUpperCase()}</th><td><b>{data[k].label}</b> <span className="quiet">· {data[k].baseline} → {data[k].target}</span></td>
    <td className="small">{["new", "eliminated", "changed", "kept"].map((s) => `${(data[k].totals || {})[s] || 0} ${TOGAF[s].toLowerCase()}`).join(" · ")}</td></tr>);
  return (
    <div>
      <p><a href="#/compare/gaps">← Gap analyses</a></p>
      <div className="merge-step">
        <h3>Two gap results compared</h3>
        <table className="kv small"><tbody>{side("a")}{side("b")}</tbody></table>
        <div className="merge-stats">
          <button className={change === "changes" ? "on" : ""} onClick={() => setChange("changes")}>
            <b>{moved}</b> what moved</button>
          {RUN_CHANGES.map((c) => (
            <button key={c} className={change === c ? "on" : ""} onClick={() => setChange(c)}><b>{data.counts[c] || 0}</b> {c.toLowerCase()}</button>
          ))}
          <button className={change === "all" ? "on" : ""} onClick={() => setChange("all")}><b>{data.rows.length}</b> all</button>
        </div>
        {!moved && <p className="quiet small">Nothing moved between these two results: every gap has the same status and resolution in both.</p>}
        <div className="toolbar">
          <select value={layer} onChange={(e) => setLayer(e.target.value)}><option value="">Every layer</option>{layers.map((l) => <option key={l}>{l}</option>)}</select>
          <input className="search" placeholder="Filter by element or type" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
          <span className="quiet small">{rows.length} shown</span>
          <span className="tabs-right">
            <button onClick={() => apiDownload(`/api/v1/gap-runs/compare?a=${a}&b=${b}`, `${file}.xlsx`)}>⬇ Excel</button>
            <button onClick={() => apiDownload(`/api/v1/gap-runs/compare?a=${a}&b=${b}&format=csv`, `${file}.csv`)}>⬇ CSV</button>
          </span>
        </div>
      </div>
      <table className="grid-table gap-compare">
        <thead><tr><th>What happened</th><th>Layer</th><th>Entity type</th><th>Element</th><th>Status A</th><th>Status B</th>
          <th>Resolution A</th><th>Resolution B</th><th>Fields changed A</th><th>Fields changed B</th></tr></thead>
        <tbody>
          {rows.map((r, n) => (
            <tr key={`${r.entity_type_name}|${r.name}|${n}`} className={RUN_CLASS[r.change] || ""}>
              <td><b>{r.change}</b></td><td className="small">{r.layer}</td><td className="small">{r.entity_type_name}</td><td>{r.name}</td>
              <td className="small">{TOGAF[r.status_a] || r.status_a || <span className="quiet">not in A</span>}</td>
              <td className="small">{TOGAF[r.status_b] || r.status_b || <span className="quiet">not in B</span>}</td>
              <td className="small">{r.resolution_a}</td><td className="small">{r.resolution_b}</td>
              <td className="small">{r.fields_a}</td><td className="small">{r.fields_b}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan="10" className="quiet">Nothing here; choose another count above.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function GapAnalysis({ id }) {
  const { data: a, error } = useApi(`/api/v1/gaps/${id}`);
  const [view, setView] = useState("gaps");
  const [status, setStatus] = useState("gaps");
  const [layer, setLayer] = useState("");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState(() => new Set());
  const [bulkRes, setBulkRes] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [wpFor, setWpFor] = useState(null);
  const [detail, setDetail] = useState(null);
  if (error) return <p className="status bad">{error}</p>;
  if (!a) return <p>Loading...</p>;
  const model = a.model.id;   // the model the gaps are stored in: its roles decide what you may do here
  const m = a.model;
  const admin = canOn(model, "model.lock") && !m.is_locked;
  const mayEdit = canOn(model, "model.content");
  const live = a.items.filter((i) => !i.gone);
  const layers = [...new Set(live.map((i) => i.layer))].sort();
  const items = live.filter((i) => (status === "gaps" ? i.status !== "kept" : status === "undecided" ? i.status !== "kept" && !i.resolution
    : status === "all" || i.status === status) && (!layer || i.layer === layer) && (!q || i.name.toLowerCase().includes(q.toLowerCase())));
  async function act(what, fn, done) {
    setBusy(what); setErr(""); setMsg("");
    try { const out = await fn(); setMsg(typeof done === "function" ? done(out) : done); refreshAll(); } catch (e) { setErr(e.message); }
    setBusy("");
  }
  const patch = (i, body) => act("item", () => post(`/api/v1/gaps/${a.id}/items/${i.id}`, body, "PATCH"), "");
  const side = (s) => `${s.label} · commit ${s.commit} · metamodel v${s.metamodel_version}`;
  return (
    <div>
      <p><a href="#/compare/gaps">← Gap analyses</a></p>
      <div className="merge-step">
        <h3>{a.name} <span className="quiet">· {a.template.name}</span></h3>
        {a.description && <p>{a.description}</p>}
        <table className="kv small"><tbody>
          <tr><th>Stored in</th><td><a href={`#/metamodel/${model}`}>{m.name}</a> <span className="quiet">(its roles decide who sees and works on this analysis; Gap entities go here)</span></td></tr>
          <tr><th>Source (baseline)</th><td>{side(a.baseline)}</td></tr>
          <tr><th>Target</th><td>{side(a.target)}</td></tr>
          <tr><th>Compared</th><td>{when(a.compared_at)} by {a.compared_by}</td></tr>
          {a.run && <tr><th>Result</th><td>#{a.run} (latest; {a.runs.length} kept, see the results list) · Gap entities are tagged {a.tags.map((t) => <code key={t} className="tag-code">{t}</code>)}
            {a.runs.length > 1 && <> · <a href={`#/compare/gaps/results?a=${a.runs[1].id}&b=${a.runs[0].id}`}>compare with #{a.runs[1].number}</a></>}</td></tr>}
        </tbody></table>
        <div className="merge-stats">
          {["new", "eliminated", "changed", "kept"].map((s) => (
            <button key={s} className={status === s ? "on" : ""} onClick={() => { setStatus(s); setView("gaps"); }}><b>{a.totals[s]}</b> {TOGAF[s].toLowerCase()}</button>
          ))}
          <button className={status === "undecided" ? "on" : ""} onClick={() => { setStatus("undecided"); setView("gaps"); }}><b>{a.undecided}</b> without a resolution</button>
        </div>
        <div className="toolbar">
            {mayEdit && <button disabled={!!busy} onClick={() => act("refresh", () => post(`/api/v1/gaps/${a.id}/refresh`), "Compared again: notes and resolutions kept.")}>{busy === "refresh" ? "Comparing..." : "↻ Compare again"}</button>}
            <button onClick={() => apiDownload(`/api/v1/gaps/${a.id}/download?format=xlsx`, `${a.name}.xlsx`)}>⬇ Excel</button>
            <button onClick={() => apiDownload(`/api/v1/gaps/${a.id}/download?format=docx`, `${a.name}.docx`)}>⬇ Word</button>
        </div>
      </div>
      <div className="toolbar">
        <div className="seg small">
          <button className={view === "gaps" ? "on" : ""} onClick={() => setView("gaps")}>Gaps</button>
          <button className={view === "matrix" ? "on" : ""} onClick={() => setView("matrix")}>TOGAF gap matrix</button>
          <button className={view === "summary" ? "on" : ""} onClick={() => setView("summary")}>By layer and type</button>
        </div>
        <select value={layer} onChange={(e) => setLayer(e.target.value)}><option value="">Every layer</option>{layers.map((l) => <option key={l}>{l}</option>)}</select>
        <input className="search" placeholder="Filter by name" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 220 }} />
        <span className="tabs-right">
          {admin && <button disabled={!!busy} title="Each gap becomes a Gap entity of this model, associated with its elements and work packages (committed at once)"
            onClick={() => act("entities", () => post(`/api/v1/gaps/${a.id}/gap-entities`, { items: picked.size ? [...picked] : null }), (o) => o.note)}>
            {busy === "entities" ? "Adding..." : picked.size ? `Add the ${picked.size} ticked as Gap entities` : "Add the gaps as Gap entities"}</button>}
          <button className="linkish danger-text" onClick={() => {
            // eslint-disable-next-line no-alert
            if (window.confirm(`Delete the gap analysis '${a.name}' now, with its results, notes and decisions, and the Gap entities `
              + `made from it in ${m.name}? This is not a draft: it happens at once (the history keeps a record).`)) {
              act("delete", () => post(`/api/v1/gaps/${a.id}`, {}, "DELETE"), "").then(() => go("/compare/gaps"));
            }
          }}>Delete</button>
        </span>
      </div>
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
      {view === "gaps" && <>
        {mayEdit && (
          <div className="toolbar bulk-bar">
            <span>For the {picked.size ? `${picked.size} ticked` : `${items.length} shown`}:</span>
            <select value={bulkRes} onChange={(e) => setBulkRes(e.target.value)}>
              <option value="">Resolution...</option>{a.resolutions.map((r) => <option key={r}>{r}</option>)}
            </select>
            <button disabled={!bulkRes || !!busy} onClick={() => act("bulk", () => post(`/api/v1/gaps/${a.id}/items`,
              { items: picked.size ? [...picked] : items.map((i) => i.id), resolution: bulkRes }), (o) => `${o.updated} gaps: ${bulkRes}.`)}>Set</button>
            {picked.size > 0 && <button className="linkish" onClick={() => setPicked(new Set())}>Clear the ticks</button>}
          </div>
        )}
        <table className="grid-table gap-table">
          <thead><tr>
            <th><input type="checkbox" checked={items.length > 0 && items.every((i) => picked.has(i.id))}
              onChange={(e) => setPicked(e.target.checked ? new Set(items.map((i) => i.id)) : new Set())} aria-label="Tick all shown" /></th>
            <th>TOGAF</th><th>Element</th><th>What changed</th><th>Resolution</th><th>Work packages</th><th>Note</th>
          </tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id} className={`cmp-${i.status}`}>
                <td><input type="checkbox" checked={picked.has(i.id)} onChange={() => setPicked((x) => { const n = new Set(x); if (n.has(i.id)) n.delete(i.id); else n.add(i.id); return n; })} /></td>
                <td className="small">{TOGAF[i.status]}</td>
                <td><strong>{i.name}</strong> <span className="quiet small">{i.entity_type_name} · {i.layer}</span>
                  {(i.target_here || i.baseline_here) && <EntityLink model={model} id={i.target_here ? i.target_guid : i.baseline_guid} />}
                  {i.gap_entity && <EntityLink model={model} id={i.gap_entity} label="Gap entity ↗" />}
                  {i.baseline_name && i.target_name && i.baseline_name !== i.target_name && <div className="quiet small">was {i.baseline_name}</div>}</td>
                <td className="small">{i.changes.slice(0, 6).map((c) => <div key={c.field}><span className="quiet">{c.label}:</span> <s>{show(c.left)}</s> → {show(c.right)}</div>)}
                  {i.changes.length > 6 && <div className="quiet">+{i.changes.length - 6} more</div>}
                  <button className="linkish sbs-btn" title="The element in the baseline and in the target side by side" onClick={() => setDetail(i)}>⇆ details</button></td>
                <td>{mayEdit ? <select value={i.resolution} onChange={(e) => patch(i, { resolution: e.target.value })}>
                  <option value="">-</option>{a.resolutions.map((r) => <option key={r}>{r}</option>)}</select> : i.resolution}</td>
                <td className="small">{i.work_packages.map((w) => <div key={w.id}><a href={`#/metamodel/${model}/entity/${w.id}`}>{w.name}</a>
                  {mayEdit && <button className="linkish" title="Remove" onClick={() => patch(i, { work_packages: i.work_packages.filter((x) => x.id !== w.id).map((x) => x.id) })}> ✕</button>}</div>)}
                  {mayEdit && <button className="linkish" onClick={() => setWpFor(i)}>+ work package</button>}</td>
                <td>{mayEdit ? <input defaultValue={i.note} onBlur={(e) => e.target.value !== i.note && patch(i, { note: e.target.value })} placeholder="Note" /> : i.note}</td>
              </tr>
            ))}
            {!items.length && <tr><td colSpan="7" className="quiet">Nothing to show.</td></tr>}
          </tbody>
        </table>
      </>}
      {view === "matrix" && <GapMatrix items={live.filter((i) => (!layer || i.layer === layer))} />}
      {view === "summary" && <GapSummary items={live} />}
      {detail && <SideBySide path={`/api/v1/gaps/${a.id}/items/${detail.id}/detail`} title={`${detail.name}: baseline and target side by side`}
        onClose={() => setDetail(null)} />}
      {wpFor && (
        <Modal title={`Work package for '${wpFor.name}'`} onClose={() => setWpFor(null)} actions={<button onClick={() => setWpFor(null)}>Close</button>}>
          <p className="quiet">Choose the work package (or any entity of {m.name}) that closes this gap.</p>
          <EntityPicker model={model} types={["WorkPackage", "Deliverable", "Plateau"]} autoFocus
            onChange={(wid) => { if (wid) { patch(wpFor, { work_packages: [...wpFor.work_packages.map((w) => w.id), wid] }); setWpFor(null); } }} />
        </Modal>
      )}
    </div>
  );
}

// the TOGAF gap matrix, per entity type: baseline elements down, target elements across
function GapMatrix({ items }) {
  const [all, setAll] = useState(false);
  const groups = {};
  items.forEach((i) => { (groups[i.entity_type] = groups[i.entity_type] || []).push(i); });
  const list = Object.values(groups).filter((g) => all || g.some((i) => i.status !== "kept"))
    .sort((x, y) => (x[0].layer + x[0].entity_type_name).localeCompare(y[0].layer + y[0].entity_type_name));
  return (
    <div>
      <label><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show the types without gaps too</label>
      <p className="quiet small">TOGAF gap matrix: each baseline element down the side, each target element across the top. Included where the same element is in
        both; the last column holds eliminated elements, the last row new ones. Large types show their first 40 rows and columns (the Excel download has all).</p>
      {list.map((g) => {
        const base = g.filter((i) => i.baseline_name).slice(0, 40);
        const tgt = g.filter((i) => i.target_name).slice(0, 40);
        return (
          <div key={g[0].entity_type} className="gap-matrix">
            <h4>{g[0].entity_type_name} <span className="quiet small">{g[0].layer}</span></h4>
            <div className="scroll">
              <table className="grid-table matrix">
                <thead><tr><th>Baseline \ Target</th>{tgt.map((j) => <th key={j.id} className="vert" title={j.target_name}><span>{j.target_name}</span></th>)}<th className="vert"><span>Eliminated</span></th></tr></thead>
                <tbody>
                  {base.map((i) => (
                    <tr key={i.id}><th>{i.baseline_name}</th>
                      {tgt.map((j) => <td key={j.id} className={j === i ? `cmp-${i.status}` : ""}>{j === i ? (i.status === "kept" ? "Included" : "Changed") : ""}</td>)}
                      <td className={i.status === "eliminated" ? "cmp-eliminated" : ""}>{i.status === "eliminated" ? (i.resolution || "Eliminated") : ""}</td></tr>
                  ))}
                  <tr><th>New</th>{tgt.map((j) => <td key={j.id} className={j.status === "new" ? "cmp-new" : ""}>{j.status === "new" ? (j.resolution || "New") : ""}</td>)}<td /></tr>
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function GapSummary({ items }) {
  const rows = {};
  items.forEach((i) => {
    const k = `${i.layer}|${i.entity_type_name}`;
    rows[k] = rows[k] || { layer: i.layer, name: i.entity_type_name, kept: 0, changed: 0, new: 0, eliminated: 0 };
    rows[k][i.status] += 1;
  });
  const list = Object.values(rows).sort((x, y) => (x.layer + x.name).localeCompare(y.layer + y.name));
  const max = Math.max(1, ...list.map((r) => r.kept + r.changed + r.new + r.eliminated));
  return (
    <table className="grid-table">
      <thead><tr><th>Layer</th><th>Entity type</th><th>Included</th><th>Changed</th><th>New</th><th>Eliminated</th><th style={{ width: "35%" }} /></tr></thead>
      <tbody>
        {list.map((r) => (
          <tr key={r.layer + r.name}>
            <td className="quiet">{r.layer}</td><td>{r.name}</td><td className="num">{r.kept}</td><td className="num">{r.changed || ""}</td>
            <td className="num">{r.new || ""}</td><td className="num">{r.eliminated || ""}</td>
            <td><div className="gap-bar">{["kept", "changed", "new", "eliminated"].map((s) => r[s] > 0 &&
              <span key={s} className={`gb-${s}`} style={{ width: `${(100 * r[s]) / max}%` }} title={`${TOGAF[s]}: ${r[s]}`} />)}</div></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
