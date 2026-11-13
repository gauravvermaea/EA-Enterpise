// The project page's analysis tabs (owner, 7 Nov 2026):
//   Views   by ADM phase; for each, choose which of the project's models to see it in (the ones that can show it first)
//   Reports      the project's own status report (steps, deliverables, documents, approvals, goals) and each model's reports
//   Gaps         gap analyses between two of the project's models (as the Gap analysis screen does), and the ones already made
//   Compare      two of the project's models (or one of their tags) side by side, and common analyses of its models
import { useMemo, useState } from "react";
import { apiDownload, apiFetch, apiUpload, roles } from "./auth";
import { Field, Modal } from "./ModelOps";
import { runTask } from "./tasks";
import { downloadCsv } from "./exporting";
import { fmtDateTime, fmtStamp } from "./fmt";
import ModelReports from "./ModelReports";
import { refreshAll, useApi } from "./ModelViews";
import { NewGapDialog } from "./Versions";
import { projectPhaseEnabled } from "./iterations";
import { MoveProjectToArchiveDialog } from "./Archive";

const shortPhase = (ph) => ph.name.replace(/^Phase /, "").replace(" Architecture", "").replace(" (repository-wide)", "");

function PhaseTabs({ p, phase, setPhase, count }) {
  return (
    <div className="tabs phase-tabs" role="tablist">
      {p.phases.map((ph) => {
        const n = count(ph.code);
        return (
          <button key={ph.code} role="tab" className={`tab${phase === ph.code ? " on" : ""}${n ? "" : " empty"}`} onClick={() => setPhase(ph.code)}
            title={ph.name}>{shortPhase(ph)} <span className="count">{n}</span></button>
        );
      })}
      <button role="tab" className={`tab${phase === "*" ? " on" : ""}`} onClick={() => setPhase("*")}>All phases</button>
    </div>
  );
}

// the models of the project, the primary working one first
function projectModels(p) {
  return [...p.models].sort((a, b) => (b.home ? 1 : 0) - (a.home ? 1 : 0) || a.name.localeCompare(b.name));
}

// ------------------------------------------------------------------ Views
// fixed: one phase only (the project's Phases tab, owner, 8 Nov 2026): no phase tabs
export function ViewsByPhase({ p, fixed }) {
  const [phase0, setPhase] = useState(() => p.views.find((v) => v.phase)?.phase || "A");
  const phase = fixed || phase0;
  const [pick, setPick] = useState({});          // view code -> the model chosen to see it in
  const [msg, setMsg] = useState("");
  const qs = p.key_questions || [];
  const answers = (code) => qs.map((q, i) => (q.views.includes(code) ? { n: i + 1, q } : null)).filter(Boolean);
  const list = p.views.filter((v) => phase === "*" || v.phase === phase);
  async function move(v, ph) {
    setMsg("");
    try { const r = await apiFetch(`/api/v1/projects/${p.id}/views/${encodeURIComponent(v.code)}/phase`, { method: "POST", body: JSON.stringify({ phase: ph }) }); setMsg(r.message); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <div>
      <p className="quiet small">The views this project uses, by ADM phase. Choose the model to see a view in: the project's models that
        have every element type it shows come first (✓); the others show what they lack. Views are chosen in the project wizard
        (✎ Edit › Views); a phase can be changed here.</p>
      {!fixed && <PhaseTabs p={p} phase={phase} setPhase={setPhase} count={(c) => p.views.filter((v) => v.phase === c).length} />}
      {fixed && !list.length && <p className="quiet small">No view is placed in this phase.</p>}
      <table className="grid-table vp-table">
        <thead><tr><th>View</th><th>Concerns · stakeholders</th><th>Answers</th><th>See it in</th><th /><th>Phase</th></tr></thead>
        <tbody>
          {list.map((v) => {
            const models = [...(v.models || [])].sort((a, b) => a.missing.length - b.missing.length);
            const chosen = pick[v.code] || v.model || models[0]?.model || "";
            const cm = models.find((x) => x.model === chosen);
            return (
              <tr key={v.code}>
                <td><b>{v.code}</b> {v.name}{v.own && <span className="chip">project's own</span>}</td>
                <td className="small quiet">{v.concerns}{v.stakeholders ? ` · ${v.stakeholders}` : ""}</td>
                <td className="small">{answers(v.code).map((a) => <a key={a.n} className="chip" title={a.q.question} href={`#/projects/${p.id}/questions`}>Q{a.n}</a>)}</td>
                <td>{models.length ? <select value={chosen} onChange={(e) => setPick({ ...pick, [v.code]: e.target.value })}>
                  {models.map((x) => <option key={x.model} value={x.model}>{x.missing.length ? "· " : "✓ "}{x.name}{x.missing.length ? ` (lacks ${x.missing.length})` : ""}</option>)}
                </select> : <span className="quiet small">The project has no model yet.</span>}
                  {cm && cm.missing.length > 0 && <div className="small quiet">lacks {cm.missing.join(", ")}</div>}</td>
                <td className="nowrap">{cm && <a href={`#/metamodel/${cm.model}/views/${encodeURIComponent(v.code)}`}>Open</a>}
                  {cm && cm.missing.length > 0 && <> · <a href={`#/metamodel/${cm.model}/metamodel`}>add the types</a></>}</td>
                <td>{p.may_contribute ? <select value={v.phase || ""} onChange={(e) => move(v, e.target.value)} aria-label={`${v.code}: phase`}>
                  <option value="">usual</option>{p.phases.map((ph) => <option key={ph.code} value={ph.code}>{shortPhase(ph)}</option>)}</select> : v.phase}</td>
              </tr>
            );
          })}
          {!list.length && <tr><td colSpan={6} className="quiet small">{p.views.length ? "No view in this phase." : "No views chosen: ✎ Edit › Views."}</td></tr>}
        </tbody>
      </table>
      {msg && <p className="small status">{msg}</p>}
    </div>
  );
}

// ------------------------------------------------------------------ Reports
// the project's own report (Home › Project report) and its models' reports (the Reports tab) (owner, 8 Nov 2026)
export function ProjectReports({ p, part = "all" }) {
  const models = projectModels(p);
  const [model, setModel] = useState("");
  const rows = useMemo(() => p.phases.map((ph) => {
    const steps = p.steps.filter((s) => s.phase === ph.code && !s.parent && !s.removed);
    const items = p.items.filter((i) => i.phase === ph.code && i.chosen);
    const docs = p.documents.filter((d) => items.some((i) => i.id === d.item_id));
    return {
      phase: ph.name + (projectPhaseEnabled(p, ph.code) ? "" : " (frozen in this iteration)"), steps: steps.length, steps_done: steps.filter((s) => s.done_at).length,
      classes: items.length, classes_with_documents: items.filter((i) => docs.some((d) => d.item_id === i.id)).length,
      documents: docs.length, draft: docs.filter((d) => d.state === "Draft").length, in_review: docs.filter((d) => d.state === "In review").length,
      accepted_or_approved: docs.filter((d) => d.state === "Accepted" || d.state === "Approved").length,
      rejected: docs.filter((d) => d.state === "Rejected").length, checked_out: docs.filter((d) => d.checked_out_by).length,
    };
  }).filter((r) => r.steps || r.classes || r.documents), [p]);
  const tot = (k) => rows.reduce((a, r) => a + r[k], 0);
  const open = (p.signoffs || []).filter((r) => r.state === "open");
  return (
    <div>
      {part !== "models" && <>
      <h3>Project status</h3>
      <p className="quiet small">Where {p.name} stands, phase by phase: its steps, its deliverables and artifacts (document classes), their documents
        and approvals. <button className="linkish" onClick={() => downloadCsv(rows, `${p.name} status`)}>⬇ CSV (opens in Excel)</button></p>
      {p.iteration && <p className="small">ADM cycle {p.cycle}: <b>{p.iteration.label}</b>{p.iteration.chosen ? "" : " (not chosen yet)"}
        {p.iteration.frozen_phases?.length > 0 && <> · frozen (read only): {p.iteration.frozen_phases.map((c) => (c === "P" ? "Preliminary" : c)).join(", ")}</>}</p>}
      <table className="grid-table small">
        <thead><tr><th>Phase</th><th className="num">Steps done</th><th className="num">Classes with documents</th><th className="num">Documents</th>
          <th className="num">Draft</th><th className="num">In review</th><th className="num">Accepted or approved</th><th className="num">Rejected</th><th className="num">Checked out</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.phase}><td>{r.phase}</td><td className="num">{r.steps_done} / {r.steps}</td><td className="num">{r.classes_with_documents} / {r.classes}</td>
              <td className="num">{r.documents}</td><td className="num">{r.draft || ""}</td><td className="num">{r.in_review || ""}</td>
              <td className="num">{r.accepted_or_approved || ""}</td><td className="num">{r.rejected || ""}</td><td className="num">{r.checked_out || ""}</td></tr>
          ))}
          <tr className="total"><td><b>All</b></td><td className="num"><b>{tot("steps_done")} / {tot("steps")}</b></td><td className="num"><b>{tot("classes_with_documents")} / {tot("classes")}</b></td>
            <td className="num"><b>{tot("documents")}</b></td><td className="num">{tot("draft") || ""}</td><td className="num">{tot("in_review") || ""}</td>
            <td className="num">{tot("accepted_or_approved") || ""}</td><td className="num">{tot("rejected") || ""}</td><td className="num">{tot("checked_out") || ""}</td></tr>
        </tbody>
      </table>
      <div className="split-2">
        <div>
          <h4>Waiting for approval ({open.length})</h4>
          {open.length ? <ul className="small">{open.map((r) => <li key={r.id}>{r.file_name} v{r.version}: needs {r.quorum || r.signers.length} of {r.signers.length},
            waiting for {r.waiting_for.join(", ")}</li>)}</ul> : <p className="quiet small">Nothing.</p>}
        </div>
        <div>
          <h4>Goals and outcomes</h4>
          {p.goals?.length ? <ul className="small">{p.goals.map((g) => <li key={g.id || g.name}><b>{g.name}</b>
            {g.outcomes?.length > 0 && <ul>{g.outcomes.map((o) => <li key={o.id || o.name}>{o.name}{o.measure ? ` (${o.measure})` : ""}{o.target_date ? `, by ${o.target_date}` : ""}</li>)}</ul>}</li>)}</ul>
            : <p className="quiet small">None.</p>}
        </div>
      </div>
      </>}
      {part !== "project" && <>
      <h3>Model reports</h3>
      <p className="quiet small">The reports and dashboards of one of the project's models.</p>
      <select value={model} onChange={(e) => setModel(e.target.value)}>
        <option value="">Choose a model…</option>
        {models.map((m) => <option key={m.id} value={m.id}>{m.name}{m.home ? " (primary)" : ""}</option>)}
      </select>
      {model && <ModelReports model={model} m={models.find((m) => m.id === model)} />}
      </>}
    </div>
  );
}

// ------------------------------------------------------------------ Gaps
const byRole = (p, ...roles) => roles.map((r) => p.models.find((m) => m.role === r)).find(Boolean);

export function ProjectGaps({ p }) {
  const { data, error } = useApi("/api/v1/gaps");
  const models = projectModels(p);
  const ids = new Set(models.map((m) => m.id));
  const [base, setBase] = useState(() => (byRole(p, "current", "reference") || models[0])?.id || "");
  const [target, setTarget] = useState(() => (byRole(p, "target", "transition", "scenario", "working-copy") || models[1] || models[0])?.id || "");
  const [making, setMaking] = useState(false);
  const mine = (data?.analyses || []).filter((a) => ids.has(a.baseline_model) || ids.has(a.target_model) || ids.has(a.model_id));
  return (
    <div>
      <p className="quiet small">A gap analysis compares a source (baseline) with a target the TOGAF way: each element is included, changed, new or
        eliminated, with resolutions and work packages. Choose two of the project's models (a tag can be chosen in the next step).</p>
      <div className="toolbar">
        <label className="small">Source (baseline) <select value={base} onChange={(e) => setBase(e.target.value)}>
          {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <label className="small">Target <select value={target} onChange={(e) => setTarget(e.target.value)}>
          {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <button className="primary" disabled={!base || !target || models.length < 1} onClick={() => setMaking(true)}>+ New gap analysis</button>
        <a className="small" href={`#/compare?left=model:${base}&right=model:${target}`}>or compare them first</a>
      </div>
      {error && <p className="status bad">{error}</p>}
      <table className="grid-table">
        <thead><tr><th>Gap analysis</th><th>Source (baseline)</th><th>Target</th><th>Stored in</th><th>Compared</th><th className="num">Gaps</th><th className="num">Undecided</th></tr></thead>
        <tbody>
          {mine.map((a) => (
            <tr key={a.id}>
              <td><a href={`#/compare/gaps/${a.id}`}><b>{a.name}</b></a>{a.description && <div className="quiet small">{a.description}</div>}</td>
              <td className="small">{a.baseline}</td><td className="small">{a.target}</td><td className="small">{a.model_name}</td>
              <td className="small">{a.compared_at ? fmtDateTime(a.compared_at) : ""}<br /><span className="quiet">{a.compared_by}</span></td>
              <td className="num">{a.gaps}</td><td className="num">{a.undecided || ""}</td>
            </tr>
          ))}
          {data && !mine.length && <tr><td colSpan={7} className="quiet small">No gap analysis of this project's models yet.</td></tr>}
        </tbody>
      </table>
      {making && <NewGapDialog baseline={{ model: base, tag: "" }} target={{ model: target, tag: "" }} onClose={() => { setMaking(false); refreshAll(); }} />}
    </div>
  );
}

// ------------------------------------------------------------------ Compare
export function ProjectCompare({ p, part = "all" }) {
  const models = projectModels(p);
  const ids = new Set(models.map((m) => m.id));
  const [left, setLeft] = useState(() => (byRole(p, "current", "reference") || models[0])?.id || "");
  const [right, setRight] = useState(() => (byRole(p, "target", "transition", "scenario", "working-copy") || models[1] || models[0])?.id || "");
  const { data: commons } = useApi("/api/v1/commons");
  const names = models.map((m) => m.name);
  const mine = (commons?.analyses || []).filter((a) => ids.has(a.model_id) || (a.sides || []).some((l) => names.some((n) => String(l).startsWith(n))));
  return (
    <div>
      {part !== "common" && <>
      <h3>Compare two models</h3>
      <p className="quiet small">Side by side: what is only in one, only in the other, and what differs. On the Compare screen each side can also be
        one of the model's tags, and the result can be kept as a gap analysis.</p>
      <div className="toolbar">
        <label className="small">Baseline (left) <select value={left} onChange={(e) => setLeft(e.target.value)}>
          {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <label className="small">Target (right) <select value={right} onChange={(e) => setRight(e.target.value)}>
          {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <a className="button primary" href={`#/compare?left=model:${left}&right=model:${right}`}>Compare</a>
      </div>
      </>}
      {part !== "compare" && <>
      <h3>What the project's models have in common</h3>
      <p className="quiet small">A common analysis finds what two or more models share (capabilities, applications, processes…).
        {" "}<a href="#/compare/common">+ New common analysis</a></p>
      {mine.length ? <ul className="small">{mine.map((a) => <li key={a.id}><a href={`#/compare/common/${a.id}`}>{a.name}</a></li>)}</ul>
        : <p className="quiet small">None of this project's models yet.</p>}
      </>}
    </div>
  );
}

// ------------------------------------------------------------------ Back up and restore (owner, 7 Nov 2026)
export function ProjectBackupPanel({ p }) {
  const { data } = useApi(`/api/v1/projects/${p.id}/backups`);
  const superAdmin = roles().includes("super-admin");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [restoring, setRestoring] = useState(null);
  const [archiving, setArchiving] = useState(false);
  async function backUp() {
    setBusy("backup"); setMsg("");
    try { const r = await runTask(apiFetch(`/api/v1/projects/${p.id}/backups`, { method: "POST", body: JSON.stringify({ why: "" }) }), `#/projects/${p.id}/about`); setMsg(r?.message || "Backed up."); refreshAll(); }
    catch (e) { setMsg(e.message); }
    setBusy("");
  }
  async function del(b) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete the backup of ${fmtStamp(b.created)}? This cannot be undone.`)) return;
    try { await apiFetch(`/api/v1/projects/${p.id}/backups/${encodeURIComponent(b.file)}`, { method: "DELETE" }); refreshAll(); } catch (e) { setMsg(e.message); }
  }
  const list = data?.backups || [];
  if (!data?.may_manage) return null;
  return (
    <div className="backup-panel">
      <h3>Back up and restore</h3>
      <p className="small quiet">A backup holds the project (its people, steps, document classes, approvals and history), the models it works on and
        the latest version of each document. Restoring makes a <b>new</b> project from it: the old one is not touched. It runs in the background.
        {p.frozen && " A finished project can still be backed up."}</p>
      <div className="row-gap"><button disabled={!!busy} onClick={backUp}>{busy === "backup" ? "Backing up…" : "Back up now"}</button>
        <button className="danger" onClick={() => setArchiving(true)}>Move to the archive</button></div>
      {msg && <p className="small status">{msg}</p>}
      {list.length > 0 && <table className="grid-table small">
        <thead><tr><th>Backed up</th><th>By</th><th className="num">Documents</th><th>Models</th><th /></tr></thead>
        <tbody>{list.map((b) => (
          <tr key={b.file}>
            <td>{b.created ? fmtStamp(b.created) : b.file}
              {b.documents_missing?.length > 0 && <div className="bad-text">{b.documents_missing.length} document files missing</div>}
              {b.upgrade?.length > 0 && <div className="small quiet" title="Restoring it runs the upgrade steps, as the database's migrations do">
                from EA Explorer {b.version}: upgraded to {b.upgrade[b.upgrade.length - 1]} on restore</div>}</td>
            <td>{b.by}</td><td className="num">{b.counts?.documents ?? ""}</td>
            <td>{(b.models || []).filter((m) => !m.error).map((m) => m.name).join(", ")}</td>
            <td className="nowrap">
              <button className="linkish" onClick={() => apiDownload(`/api/v1/projects/${p.id}/backups/${encodeURIComponent(b.file)}`, b.file)}>⬇ Download</button>{" · "}
              {data.may_restore && <><button className="linkish" onClick={() => setRestoring({ b, over: false })}>Restore as a new project</button>{" · "}</>}
              {superAdmin && <><button className="linkish" onClick={() => setRestoring({ b, over: true })}>Put back over itself</button>{" · "}</>}
              <button className="linkish bad-text" onClick={() => del(b)}>Delete</button></td>
          </tr>))}</tbody>
      </table>}
      {restoring && <RestoreDialog p={p} b={restoring.b} over={restoring.over} onClose={() => setRestoring(null)} />}
      {archiving && <MoveProjectToArchiveDialog p={p} superAdmin={superAdmin} onClose={() => setArchiving(false)} />}
    </div>
  );
}

// restore one of a project's backups: as a new project, or (Super Admins) over itself; the About tab and Administration › Backups
export function RestoreDialog({ p, b, over = false, onClose }) {
  const [name, setName] = useState("");
  const [word, setWord] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function run() {
    setBusy(true); setErr("");
    try {
      const r = await runTask(apiFetch(`/api/v1/projects/${p.id}/backups/${encodeURIComponent(b.file)}/restore`,
        { method: "POST", body: JSON.stringify(over ? { over: true } : { name }) }), over ? `#/projects/${p.id}` : "#/work");
      refreshAll(); onClose();
      if (r?.project) window.location.hash = `#/projects/${r.project}`;
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={over ? `Put ${p.name} back as it was` : "Restore as a new project"} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className={over ? "danger" : "primary"} disabled={busy || (over && word !== "RESTORE")} onClick={run}>{busy ? "Restoring…" : over ? "Put it back" : "Restore"}</button></>}>
      <div className="ed-form">
        <p className="small">Backup of {fmtStamp(b.created)} by {b.by}: {b.counts?.documents || 0} documents.</p>
        {over ? <>
          <ul className="small">
            <li>The project goes back to how it was in this backup: its steps, people, sign-off, document classes and documents. What was added since is gone (documents added since go to the trash in Documents).</li>
            <li>The models it made go back as they were (each is backed up and kept as a tag first). The organisation's models it only uses stay as they are.</li>
            <li>Its repository is built again in Documents within a minute or two: a document still there gets the backed-up file as its newest version when it differs (its history kept); one that is gone is put back.</li>
          </ul>
          <Field label="Type RESTORE to go on"><input value={word} onChange={(e) => setWord(e.target.value)} autoFocus /></Field>
        </> : <>
          <p className="small">A new project is made from the backup; {p.name} itself is not changed. You are its Project Admin.</p>
          <ul className="small">
            <li>The models the project made (derived or created) come back as new models; a model it worked on in place, or only refers to, is linked again when it is still here.</li>
            <li>The repository is built again in Documents within a minute or two and the latest version of each document is put back.</li>
          </ul>
          <Field label="Name" hint="(empty: the old name with “restored” and the date)"><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
        </>}
        {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}

// a project backup file from this installation or another, restored as a new project (Project admin › Wizards)
export function RestoreProjectFile({ onClose }) {
  const [file, setFile] = useState(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function run() {
    setBusy(true); setErr("");
    try {
      const fd = new FormData(); fd.append("file", file); fd.append("name", name);
      const r = await runTask(apiUpload("/api/v1/projects/restore", fd), "#/work");
      refreshAll(); onClose();
      if (r?.project) window.location.hash = `#/projects/${r.project}`;
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title="Restore a project from a backup file" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !file} onClick={run}>{busy ? "Restoring…" : "Restore"}</button></>}>
      <div className="ed-form">
        <p className="small">A project backup file (<code>.eaxproject.zip</code>, from Back up now on a project's About tab, here or on another
          installation) becomes a new project, with its models and documents.</p>
        <Field label="Backup file"><input type="file" accept=".eaxproject.zip,.zip" onChange={(e) => setFile(e.target.files[0] || null)} /></Field>
        <Field label="Name" hint="(optional)"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}
