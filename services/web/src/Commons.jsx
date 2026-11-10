// Common analyses (phase 13.0.5, D286): what two or more models have in common. Architecture work, a screen.
//   #/compare/common              every common analysis you may see, and + New
//   #/compare/common/new          set up one: the sides, then what counts (all the person's choice)
//   #/compare/common/<analysis>   one: the summary, the elements with a column per side, values that differ, relationships,
//                                 close names to match, notes and decisions; tag the common elements, make a model of them
import { Fragment, useEffect, useMemo, useState } from "react";
import { apiFetch, canOn } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Field, Modal } from "./ModelOps";
import { SidePicker, sideOf } from "./Versions";
import { fmtDateTime } from "./fmt";
import { TaskFiles } from "./TaskDrawer";
import { downloadTask, runTask } from "./tasks";
import { liveModels, useShowRetired } from "./ModelMarks";

const go = (path) => { window.location.hash = path; };
const post = (path, body, method = "POST") => apiFetch(path, { method, body: JSON.stringify(body || {}) });
const show = (v) => (v === null || v === undefined || v === "" ? <span className="quiet">(empty)</span> : String(v));

export default function Commons({ id }) {
  if (id === "new") return <NewCommon />;
  if (id) return <CommonPage id={id} />;
  return <CommonList />;
}

function CommonList() {
  const { data, error } = useApi("/api/v1/commons");
  return (
    <div>
      <p className="quiet">What two or more models have in common: the same capabilities, applications, processes or data across business
        units, companies after a merger, or versions of a model. You choose the models, what counts and how many of them an element must
        be in. Each is stored in a project model you choose, whose people can open it.</p>
      <div className="toolbar"><a className="button primary" href="#/compare/common/new">+ New common analysis</a></div>
      {error && <p className="status bad">{error}</p>}
      {data && !data.analyses.length && <p className="quiet">No common analyses yet.</p>}
      {data && data.analyses.length > 0 && (
        <table className="grid-table">
          <thead><tr><th>Common analysis</th><th>Models compared</th><th className="num">Common</th><th className="num">Elements</th><th>Stored in</th><th>Compared</th></tr></thead>
          <tbody>{data.analyses.map((a) => (
            <tr key={a.id}><td><a href={`#/compare/common/${a.id}`}><b>{a.name}</b></a>{a.description && <div className="quiet small">{a.description}</div>}</td>
              <td className="small">{a.sides.join(" · ")}</td><td className="num">{a.totals.common ?? ""}{a.totals.threshold ? <span className="quiet small"> (≥{a.totals.threshold})</span> : ""}</td>
              <td className="num">{a.totals.elements ?? ""}</td><td><a href={`#/metamodel/${a.model_id}`}>{a.model_name}</a></td>
              <td className="small">{fmtDateTime(a.compared_at)} · {a.compared_by}</td></tr>))}</tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- set up
function NewCommon() {
  const [showRetired] = useShowRetired();     // frozen models only when the person shows them (D360)
  const { data: models_ } = useApi("/api/v1/models?kind=project");
  const models = models_ && (showRetired ? models_ : liveModels(models_));
  const [sides, setSides] = useState([{ model: "", tag: "" }, { model: "", tag: "" }]);
  const [info, setInfo] = useState(null);
  const [st, setSt] = useState(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [store, setStore] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const ready = sides.length >= 2 && sides.every((s) => s.model);
  const storable = (models || []).filter((m) => !m.is_locked && canOn(m.id, "model.content"));
  async function read() {
    setBusy("read"); setErr("");
    try { const out = await post("/api/v1/commons/preview", { sides: sides.map(sideOf) }); setInfo(out); setSt(out.defaults); }
    catch (e) { setErr(e.message); }
    setBusy("");
  }
  async function make() {
    setBusy("make"); setErr("");
    try {
      const out = await runTask(post("/api/v1/commons", { store_in: store, name: name.trim(), description, sides: sides.map(sideOf), settings: st }), "#/compare/common");
      refreshAll(); go(`/compare/common/${out.id}`);
    } catch (e) { setErr(e.message); setBusy(""); }
  }
  const setSide = (i, v) => { setSides((x) => x.map((s, j) => (j === i ? v : s))); setInfo(null); };
  return (
    <div>
      <p><a href="#/compare/common">← Common analyses</a></p>
      <div className="merge-step">
        <h3>1. The models</h3>
        <p className="quiet small">Two or more, each as it is now or at one of its tags.</p>
        {sides.map((s, i) => (
          <div key={i} className="row-gap">
            <SidePicker label={`Model ${i + 1}`} value={s} onChange={(v) => setSide(i, v)} />
            {sides.length > 2 && <button className="linkish" onClick={() => { setSides((x) => x.filter((_, j) => j !== i)); setInfo(null); }}>Remove</button>}
          </div>))}
        <div className="toolbar">
          {sides.length < 12 && <button onClick={() => { setSides((x) => [...x, { model: "", tag: "" }]); setInfo(null); }}>+ Another model</button>}
          <button className="primary" disabled={!ready || !!busy} onClick={read}>{busy === "read" ? "Reading…" : "Next: choose what counts"}</button>
        </div>
      </div>
      {info && st && <Setup info={info} st={st} setSt={setSt} />}
      {info && st && (
        <div className="merge-step">
          <h3>3. Name it and where it is stored</h3>
          <div className="ed-form" style={{ padding: 0 }}>
            <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Claims across the three business units" /></Field>
            <Field label="What it is for (optional)"><input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
            <Field label="Stored in" tip="A project model you may change; its people can open the analysis and record decisions.">
              <select value={store} onChange={(e) => setStore(e.target.value)}>
                <option value="">Choose a project model…</option>
                {storable.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select></Field>
          </div>
          <div className="toolbar"><button className="primary" disabled={!!busy || !name.trim() || !store} onClick={make}>{busy === "make" ? "Matching…" : "Find what is common"}</button></div>
          {busy === "make" && <p className="quiet"><span className="spinner" aria-hidden="true" /> Working in the background: the Tasks tab on the right says when it is done.</p>}
        </div>
      )}
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}

// what counts: the threshold, values and relationships, the entity types (each with its fields)
function Setup({ info, st, setSt }) {
  const [open, setOpen] = useState({});
  const n = info.sides.length;
  const types = st.types || {};
  const setType = (code, fields) => setSt((s) => { const t = { ...s.types }; if (fields === null) delete t[code]; else t[code] = fields; return { ...s, types: t }; });
  return (
    <div className="merge-step">
      <h3>2. What counts</h3>
      <div className="toolbar">
        <span>Common means in</span>
        <select value={st.threshold} onChange={(e) => setSt({ ...st, threshold: Number(e.target.value) })}>
          {Array.from({ length: n - 1 }, (_, k) => n - k).map((k) => <option key={k} value={k}>{k === n ? `all ${n}` : `at least ${k} of ${n}`}</option>)}
        </select>
        <label><input type="checkbox" checked={st.values} onChange={(e) => setSt({ ...st, values: e.target.checked })} /> compare values (which fields agree or differ)</label>
        <label><input type="checkbox" checked={st.relationships} onChange={(e) => setSt({ ...st, relationships: e.target.checked })} /> compare relationships</label>
        <label title="Models made apart often reuse display IDs (CAP-001) for different things: leave this off unless the models share their IDs">
          <input type="checkbox" checked={!!st.by_display_id} onChange={(e) => setSt({ ...st, by_display_id: e.target.checked })} /> match by display ID too</label>
      </div>
      <p className="quiet small">Tick the entity types to look at (those at least two models have are ticked); open one with + to choose its fields.</p>
      <table className="grid-table small">
        <thead><tr><th /><th>Entity type</th><th>Domain</th>{info.sides.map((s, i) => <th key={i} className="num" title={s.label}>{i + 1}</th>)}<th /></tr></thead>
        <tbody>{info.types.map((t) => (
          <Fragment key={t.code}>
            <tr className={t.in < 2 ? "quiet" : ""}>
              <td><input type="checkbox" checked={!!types[t.code]} onChange={(e) => setType(t.code, e.target.checked ? t.fields.filter((f) => f.default && !f.code.startsWith("rel:")).map((f) => f.code) : null)} /></td>
              <td>{t.name}</td><td className="quiet">{t.domain}</td>{t.counts.map((c, i) => <td key={i} className="num">{c || ""}</td>)}
              <td>{types[t.code] && <button className="linkish" onClick={() => setOpen((o) => ({ ...o, [t.code]: !o[t.code] }))}>{open[t.code] ? "−" : "+"} fields</button>}</td>
            </tr>
            {open[t.code] && types[t.code] && (
              <tr><td /><td colSpan={3 + n}>
                <div className="field-picks">{t.fields.filter((f) => !f.code.startsWith("rel:")).map((f) => (
                  <label key={f.code} className="wiz-check"><input type="checkbox" checked={types[t.code].includes(f.code)}
                    onChange={(e) => setType(t.code, e.target.checked ? [...types[t.code], f.code] : types[t.code].filter((x) => x !== f.code))} />{f.label}</label>))}
                </div></td></tr>)}
          </Fragment>))}</tbody>
      </table>
      {st.relationships && (
        <details className="small"><summary>Relationship types ({(st.relationship_types || []).length} of {info.relationship_types.length})</summary>
          <div className="field-picks">{info.relationship_types.map((r) => (
            <label key={r.code} className="wiz-check"><input type="checkbox" checked={(st.relationship_types || []).includes(r.code)}
              onChange={(e) => setSt({ ...st, relationship_types: e.target.checked ? [...(st.relationship_types || []), r.code] : st.relationship_types.filter((x) => x !== r.code) })} />{r.name}</label>))}
          </div></details>)}
      <p className="quiet small">Elements are matched as a comparison does: the same element or a copy of it, or the same type and name (case, spaces
        and punctuation ignored); by display ID too when ticked. Close names that did not match are suggested on the result, to confirm or reject.</p>
    </div>
  );
}

// ---------------------------------------------------------------- one common analysis
function CommonPage({ id }) {
  const { data: a, error } = useApi(`/api/v1/commons/${id}`);
  const [tab, setTab] = useState("elements");
  const [filter, setFilter] = useState("");
  const [show_, setShow] = useState("common");
  const [type, setType] = useState("");
  const [picked, setPicked] = useState(() => new Set());
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [dialog, setDialog] = useState(null);
  const live = useMemo(() => (a?.items || []).filter((i) => !i.gone), [a]);
  if (error) return <p className="status bad">{error} <a href="#/compare/common">← Common analyses</a></p>;
  if (!a) return <p>Loading…</p>;
  const n = a.sides.length;
  const may = canOn(a.model.id, "model.content");
  const here = `#/compare/common/${a.id}`;
  const rows = live.filter((i) => (show_ === "all" || (show_ === "common" ? i.is_common : show_ === "differ" ? i.is_common && i.differs.length : !i.is_common))
    && (!type || i.entity_type === type) && (!filter || i.name.toLowerCase().includes(filter.toLowerCase())));
  async function act(what, fn, done) {
    setBusy(what); setErr(""); setMsg("");
    try { const out = await fn(); setMsg(done ? done(out) : out?.message || "Done."); refreshAll(); } catch (e) { setErr(e.message); }
    setBusy("");
  }
  const decide = (ids, body) => act("decide", () => post(`/api/v1/commons/${a.id}/items`, { items: ids, ...body }));
  const sel = picked.size ? [...picked] : null;
  return (
    <div>
      <p><a href="#/compare/common">← Common analyses</a></p>
      <h3 style={{ margin: "4px 0" }}>{a.name}</h3>
      {a.description && <p className="quiet">{a.description}</p>}
      <p className="small">Models: {a.sides.map((s, i) => <span key={i} className="chip">{i + 1}. {s.label}</span>)} · stored in <a href={`#/metamodel/${a.model.id}`}>{a.model.name}</a>
        {" "}· compared {fmtDateTime(a.compared_at)} by {a.compared_by}{a.runs.length > 1 ? ` · ${a.runs.length} results` : ""}</p>
      <div className="q-tiles">
        <div className="q-tile"><span className="q-tile-num">{a.totals.common}</span><span className="q-tile-sub quiet">common (in ≥ {a.totals.threshold} of {n})</span></div>
        <div className="q-tile"><span className="q-tile-num">{a.totals.in_all}</span><span className="q-tile-sub quiet">in all {n}</span></div>
        <div className="q-tile"><span className="q-tile-num">{a.totals.differ}</span><span className="q-tile-sub quiet">common, values differ</span></div>
        <div className="q-tile"><span className="q-tile-num">{a.totals.only_one}</span><span className="q-tile-sub quiet">in only one</span></div>
        <div className="q-tile"><span className="q-tile-num">{(a.relationships || []).filter((r) => r.common).length}</span><span className="q-tile-sub quiet">common relationships</span></div>
      </div>
      <div className="toolbar">
        {may && <button disabled={!!busy} onClick={() => setDialog("settings")}>⚙ What counts…</button>}
        {may && <button disabled={!!busy} onClick={() => act("refresh", () => runTask(post(`/api/v1/commons/${a.id}/refresh`, {}), here), () => "Compared again: notes and decisions kept.")}>
          {busy === "refresh" ? "Comparing…" : "↻ Compare again"}</button>}
        {may && <button disabled={!!busy} onClick={() => act("tag", () => runTask(post(`/api/v1/commons/${a.id}/tag`, { items: sel }), here))}
          title={`Each model's common elements get the tag '${a.tag}' (one commit per model)`}>{busy === "tag" ? "Tagging…" : `🏷 Tag the ${sel ? "ticked" : "common"} elements`}</button>}
        <button disabled={!!busy} onClick={() => setDialog("model")}>Make a model of the {sel ? "ticked" : "common"} elements…</button>
        <button onClick={() => downloadTask(`/api/v1/commons/${a.id}/download?format=xlsx`, undefined, here).catch((e) => setErr(e.message))}>⬇ Excel</button>
        <button onClick={() => downloadTask(`/api/v1/commons/${a.id}/download?format=docx`, undefined, here).catch((e) => setErr(e.message))}>⬇ Word</button>
        {may && <button className="linkish danger-text" onClick={() => setDialog("delete")}>Delete</button>}
      </div>
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
      <TaskFiles kinds={["common.download"]} match={(t) => t.link === here} />
      <div className="tabs" role="tablist">
        {[["elements", `Elements (${live.length})`], ["summary", "By entity type"], ["relationships", `Relationships (${(a.relationships || []).length})`],
          ["suggestions", `Close names (${(a.suggestions || []).length})`], ["runs", `Results (${a.runs.length})`]].map(([k, l]) => (
          <button key={k} role="tab" className={tab === k ? "tab on" : "tab"} aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>))}
      </div>
      <div className="tab-panel">
        {tab === "elements" && <>
          <div className="toolbar">
            <div className="seg small">{[["common", "Common"], ["differ", "Common, values differ"], ["rest", "Not common"], ["all", "All"]].map(([k, l]) => (
              <button key={k} className={show_ === k ? "on" : ""} onClick={() => setShow(k)}>{l}</button>))}</div>
            <select value={type} onChange={(e) => setType(e.target.value)}><option value="">Every entity type</option>
              {a.summary.map((s) => <option key={s.entity_type} value={s.entity_type}>{s.name}</option>)}</select>
            <input className="search" placeholder="Filter" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ maxWidth: 220 }} />
            <span className="quiet small">{rows.length} shown</span>
          </div>
          {may && <div className="toolbar bulk-bar"><span>For {picked.size ? `the ${picked.size} ticked` : "ticked rows"}:</span>
            <select disabled={!picked.size} value="" onChange={(e) => e.target.value && decide([...picked], { decision: e.target.value === "-" ? "" : e.target.value })}>
              <option value="">Decision…</option>{a.decisions.map((d) => <option key={d}>{d}</option>)}<option value="-">(none)</option></select>
            {picked.size > 0 && <button className="linkish" onClick={() => setPicked(new Set())}>Clear the ticks</button>}</div>}
          <div className="scroll">
            <table className="grid-table small common-grid">
              <thead><tr><th><input type="checkbox" aria-label="Tick all shown" checked={rows.length > 0 && rows.every((i) => picked.has(i.id))}
                onChange={(e) => setPicked(e.target.checked ? new Set(rows.map((i) => i.id)) : new Set())} /></th>
                <th>Element</th><th>Type</th><th className="num">In</th>{a.sides.map((s, i) => <th key={i} title={s.label}>{i + 1}</th>)}<th>Values that differ</th><th>Decision</th><th>Note</th></tr></thead>
              <tbody>{rows.slice(0, 1500).map((i) => (
                <Fragment key={i.id}>
                  <tr className={i.is_common ? "row-new" : ""}>
                    <td><input type="checkbox" checked={picked.has(i.id)} onChange={() => setPicked((s) => { const x = new Set(s); if (x.has(i.id)) x.delete(i.id); else x.add(i.id); return x; })} /></td>
                    <td><button className="linkish" onClick={() => setOpen(open === i.id ? null : i.id)}>{i.name}</button></td>
                    <td className="quiet">{i.entity_type_name}</td><td className="num">{i.sides_count}/{n}</td>
                    {a.sides.map((s, k) => { const m = i.members[String(k)]; return (
                      <td key={k} className="nowrap" title={m ? m.name : "not in this model"}>{m ? (s.kind === "model"
                        ? <a href={`#/metamodel/${s.model_id}/entity/${m.guid}`}>✓{m.name !== i.name ? ` ${m.name}` : ""}</a> : `✓${m.name !== i.name ? ` ${m.name}` : ""}`) : <span className="quiet">–</span>}</td>); })}
                    <td className="small">{i.differs.map((d) => d.label).join(", ")}</td>
                    <td>{may ? <select value={i.decision} onChange={(e) => decide([i.id], { decision: e.target.value })}><option value="">–</option>
                      {a.decisions.map((d) => <option key={d}>{d}</option>)}</select> : i.decision}</td>
                    <td>{may ? <NoteCell i={i} onSave={(note) => decide([i.id], { note })} /> : i.note}</td>
                  </tr>
                  {open === i.id && i.differs.length > 0 && (
                    <tr><td /><td colSpan={6 + n}>
                      <table className="grid-table small"><thead><tr><th>Field</th>{a.sides.map((s, k) => <th key={k}>{k + 1}. {s.label}</th>)}</tr></thead>
                        <tbody>{i.differs.map((d) => <tr key={d.field}><td>{d.label}</td>{a.sides.map((s, k) => <td key={k}>{String(k) in d.values ? show(d.values[String(k)]) : <span className="quiet">–</span>}</td>)}</tr>)}</tbody></table>
                    </td></tr>)}
                </Fragment>))}</tbody>
            </table>
            {rows.length > 1500 && <p className="quiet">And {rows.length - 1500} more: filter, or download Excel.</p>}
          </div>
        </>}
        {tab === "summary" && (
          <table className="grid-table">
            <thead><tr><th>Entity type</th><th>Domain</th><th className="num">Elements</th><th className="num">Common</th><th className="num">Values differ</th>
              {Array.from({ length: n }, (_, k) => n - k).map((k) => <th key={k} className="num">In {k}</th>)}</tr></thead>
            <tbody>{a.summary.map((s) => (
              <tr key={s.entity_type}><td><button className="linkish" onClick={() => { setType(s.entity_type); setTab("elements"); }}>{s.name}</button></td><td className="quiet">{s.domain}</td>
                <td className="num">{s.elements}</td><td className="num"><b>{s.common}</b></td><td className="num">{s.differ}</td>
                {Array.from({ length: n }, (_, k) => n - k).map((k) => <td key={k} className="num">{s.by_count[String(k)] || ""}</td>)}</tr>))}</tbody>
          </table>)}
        {tab === "relationships" && (
          !(a.relationships || []).length ? <p className="quiet">{a.settings.relationships ? "No relationships between the elements compared." : "Relationships were not compared (⚙ What counts)."}</p> : (
            <table className="grid-table small">
              <thead><tr><th>Source</th><th>Relationship</th><th>Target</th><th className="num">In</th>{a.sides.map((s, i) => <th key={i} title={s.label}>{i + 1}</th>)}</tr></thead>
              <tbody>{a.relationships.slice(0, 2000).map((r, k) => (
                <tr key={k} className={r.common ? "row-new" : ""}><td>{r.source}</td><td>{r.relationship_type}</td><td>{r.target}</td><td className="num">{r.count}/{n}</td>
                  {a.sides.map((s, i) => <td key={i}>{r.sides.includes(i) ? "✓" : <span className="quiet">–</span>}</td>)}</tr>))}</tbody>
            </table>))}
        {tab === "suggestions" && <Suggestions a={a} may={may} busy={busy} act={act} here={here} />}
        {tab === "runs" && (
          <table className="grid-table small"><thead><tr><th>Result</th><th>Compared</th><th className="num">Common</th><th className="num">In all</th><th className="num">Elements</th></tr></thead>
            <tbody>{a.runs.map((r) => <tr key={r.id}><td>#{r.number}</td><td>{fmtDateTime(r.compared_at)} · {r.compared_by}</td>
              <td className="num">{r.totals.common}</td><td className="num">{r.totals.in_all}</td><td className="num">{r.totals.elements}</td></tr>)}</tbody></table>)}
      </div>
      {dialog === "settings" && <SettingsDialog a={a} onClose={() => setDialog(null)} onRun={(settings) => {
        setDialog(null); act("refresh", () => runTask(post(`/api/v1/commons/${a.id}/refresh`, { settings }), here), () => "Compared again with the new settings: notes and decisions kept.");
      }} />}
      {dialog === "model" && <MakeModelDialog a={a} items={sel} onClose={() => setDialog(null)} />}
      {dialog === "delete" && (
        <Modal title={`Delete ${a.name}`} onClose={() => setDialog(null)}
          actions={<><button onClick={() => setDialog(null)}>Cancel</button><button className="danger" onClick={() => act("delete", () => post(`/api/v1/commons/${a.id}`, {}, "DELETE")).then(() => go("/compare/common"))}>Delete</button></>}>
          <p>The analysis, its results, notes and decisions are deleted. Tags it put on entities stay.</p>
        </Modal>)}
    </div>
  );
}

function NoteCell({ i, onSave }) {
  const [v, setV] = useState(i.note);
  return <input className="small" value={v} placeholder="note" onChange={(e) => setV(e.target.value)} onBlur={() => v !== i.note && onSave(v)} style={{ width: 160 }} />;
}

function Suggestions({ a, may, busy, act, here }) {
  const [ok, setOk] = useState({});     // index -> true (confirm) | false (reject)
  const list = a.suggestions || [];
  if (!list.length) return <p className="quiet">No close names left to look at.</p>;
  const n = Object.keys(ok).length;
  function save() {
    const confirm = list.filter((_, k) => ok[k] === true).map((s) => [s.a, s.b]);
    const reject = list.filter((_, k) => ok[k] === false).map((s) => [s.a, s.b]);
    act("match", () => runTask(post(`/api/v1/commons/${a.id}/suggestions`, { confirm, reject }), here), () => "Saved and compared again.");
  }
  return (
    <div>
      <p className="quiet">Elements of the same type with close names that were not matched. Confirm the ones that are the same thing (kept for the next
        run too) and reject those that are not (not suggested again).</p>
      <table className="grid-table small">
        <thead><tr><th>Type</th><th>One</th><th>In</th><th>The other</th><th>In</th><th className="num">Likeness</th><th>Same thing?</th></tr></thead>
        <tbody>{list.map((s, k) => (
          <tr key={k}><td className="quiet">{s.entity_type_name}</td><td>{s.a_name}</td><td className="small">{s.a_sides.map((x) => x + 1).join(", ")}</td>
            <td>{s.b_name}</td><td className="small">{s.b_sides.map((x) => x + 1).join(", ")}</td><td className="num">{Math.round(s.score * 100)}%</td>
            <td className="nowrap">{may ? <>
              <label><input type="radio" checked={ok[k] === true} onChange={() => setOk((o) => ({ ...o, [k]: true }))} /> yes</label>{" "}
              <label><input type="radio" checked={ok[k] === false} onChange={() => setOk((o) => ({ ...o, [k]: false }))} /> no</label></> : ""}</td></tr>))}</tbody>
      </table>
      {may && <div className="toolbar"><button className="primary" disabled={!n || !!busy} onClick={save}>{busy === "match" ? "Saving…" : `Save ${n || ""} and compare again`}</button></div>}
    </div>
  );
}

function SettingsDialog({ a, onClose, onRun }) {
  const [info, setInfo] = useState(null);
  const [st, setSt] = useState(a.settings);
  const [err, setErr] = useState("");
  useEffect(() => {
    post("/api/v1/commons/preview", { sides: a.sides.map((s) => s.request) }).then(setInfo).catch((e) => setErr(e.message));
  }, [a.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Modal wide title="What counts" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!info} onClick={() => onRun(st)}>Compare again</button></>}>
      {err && <p className="status bad">{err}</p>}
      {!info && !err && <p>Reading the models…</p>}
      {info && <Setup info={info} st={st} setSt={setSt} />}
    </Modal>
  );
}

function MakeModelDialog({ a, items, onClose }) {
  const first = a.sides.findIndex((s) => s.kind === "model");
  const [side, setSide] = useState(first < 0 ? 0 : first);
  const [name, setName] = useState(`Common: ${a.name}`);
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(null);
  async function run() {
    setBusy(true); setErr("");
    try { setDone(await runTask(post(`/api/v1/commons/${a.id}/make-model`, { side, name, description, items }), "#/model-admin")); refreshAll(); }
    catch (e) { setErr(e.message); }
    setBusy(false);
  }
  return (
    <Modal title="Make a model of the common elements" onClose={onClose}
      actions={done ? <><button onClick={onClose}>Close</button><button className="primary" onClick={() => go(`/model-admin/${done.model.id}`)}>Open it</button></>
        : <><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !name.trim() || first < 0} onClick={run}>{busy ? "Making…" : "Make the model"}</button></>}>
      {done ? <p className="status ok">{done.message}</p> : <div className="ed-form">
        <p>A new project model with the {items ? `${items.length} ticked` : "common"} elements and the relationships between them, copied from one of the models
          (its names, values and metamodel). To put it in the library, promote it afterwards (Model admin › Wizards).</p>
        {first < 0 && <p className="status bad">Every side is a tag: one side must be a model as it is now.</p>}
        <Field label="Copy them from">
          <select value={side} onChange={(e) => setSide(Number(e.target.value))}>
            {a.sides.map((s, i) => <option key={i} value={i} disabled={s.kind !== "model"}>{i + 1}. {s.label}{s.kind !== "model" ? " (a tag)" : ""}</option>)}
          </select></Field>
        <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Description (optional)"><input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        {err && <p className="status bad">{err}</p>}
      </div>}
    </Modal>
  );
}
