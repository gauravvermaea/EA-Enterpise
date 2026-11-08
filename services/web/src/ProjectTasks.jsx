// A project's Tasks tab (owner, 8 Nov 2026, D298): a scratchpad of what people are doing. Not project management: no
// dates, no deadlines. A task may belong to a step or a sub step; finishing it never finishes the step. Everyone on the
// project sees every task; contributors add and change them and assign them to anyone on the project; the person a
// task is assigned to changes its status and notes. A project adds statuses of its own.
import { useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import RichText from "./RichText";
import { Field, Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";

const stepLabel = (s) => (s ? `${s.phase} · ${s.parent ? `${s.parent} › ` : ""}${s.name}` : "");

export function TasksTab({ p }) {
  const url = `/api/v1/projects/${p.id}/tasks`;
  const { data, error } = useApi(url);
  const [who, setWho] = useState("everyone");
  const [status, setStatus] = useState("");
  const [step, setStep] = useState("");
  const [q, setQ] = useState("");
  const [showFinished, setShowFinished] = useState(false);
  const [open, setOpen] = useState(null);
  const [statusesOpen, setStatusesOpen] = useState(false);
  const [quick, setQuick] = useState({ title: "", assigned_to: "", step_id: "" });
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const list = data?.tasks || [];
  const me = data?.me || "";
  const shown = useMemo(() => list.filter((t) =>
    (who === "everyone" || (who === "mine" ? t.assigned_to === me : who === "made" ? t.created_by.toLowerCase() === me : !t.assigned_to))
    && (status ? t.status === status : showFinished || !t.finished)
    && (!step || String(t.step?.id || "") === step)
    && (!q.trim() || `${t.title} ${t.assigned_to} ${t.step?.name || ""}`.toLowerCase().includes(q.trim().toLowerCase()))), [list, who, status, step, q, showFinished, me]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const readOnly = ["finishing", "frozen", "merged", "closed"].includes(p.status);
  const canAdd = data.may_add && !readOnly;
  const mayChange = (t) => !readOnly && (data.may_add || t.assigned_to === me);
  const finished = list.filter((t) => t.finished).length;
  async function act(fn) {
    try { const r = await fn(); setMsg({ ok: true, text: r?.message || "Done." }); refreshAll(); return true; } catch (e) { setMsg({ ok: false, text: e.message }); return false; }
  }
  const put = (t, body) => act(() => apiFetch(`${url}/${t.id}`, { method: "PUT", body: JSON.stringify(body) }));
  async function quickAdd(e) {
    e.preventDefault();
    if (!quick.title.trim()) return;
    if (await act(() => apiFetch(url, { method: "POST", body: JSON.stringify({ ...quick, step_id: quick.step_id || null }) }))) {
      setQuick({ ...quick, title: "" });
    }
  }
  return (
    <div>
      <p className="quiet">What people on the project are doing: a scratchpad, not a plan. No dates. A task may belong to a step or a sub step;
        finishing a task does not finish its step (mark the step done on Home). Everyone on the project sees every task.</p>
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      {canAdd && (
        <form className="row-gap task-quick" onSubmit={quickAdd}>
          <input value={quick.title} onChange={(e) => setQuick({ ...quick, title: e.target.value })} placeholder="A new task" aria-label="A new task" />
          <select value={quick.assigned_to} onChange={(e) => setQuick({ ...quick, assigned_to: e.target.value })} aria-label="Assigned to">
            <option value="">Nobody yet</option>
            <option value={me}>Me</option>
            {data.people.filter((u) => u !== me).map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
          <StepSelect steps={data.steps} value={quick.step_id} onChange={(v) => setQuick({ ...quick, step_id: v })} none="No step" />
          <button className="primary" type="submit" disabled={!quick.title.trim()}>＋ Add</button>
          <button type="button" className="linkish" onClick={() => setOpen({})}>more…</button>
        </form>
      )}
      <div className="row-gap filters">
        <span className="view-toggle" role="group" aria-label="Whose tasks">
          {[["everyone", "Everyone's"], ["mine", "Mine"], ["made", "I made"], ["nobody", "Not assigned"]].map(([k, l]) => (
            <button key={k} className={who === k ? "on" : ""} onClick={() => setWho(k)}>{l}</button>))}
        </span>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">Any status</option>
          {data.statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select>
        <StepSelect steps={data.steps} value={step} onChange={setStep} none="Any step" />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search tasks" aria-label="Search tasks" />
        {!status && <label className="small"><input type="checkbox" checked={showFinished} onChange={(e) => setShowFinished(e.target.checked)} /> show finished ({finished})</label>}
        {canAdd && <button className="push-right linkish" onClick={() => setStatusesOpen(true)}>Statuses…</button>}
      </div>
      {!shown.length ? <p className="quiet">{list.length ? "No task matches." : "No tasks yet."}</p> : (
        <table className="grid-table tasks-table">
          <thead><tr><th>Status</th><th>Task</th><th>Assigned to</th><th>Step</th><th>Made by</th><th /></tr></thead>
          <tbody>
            {shown.map((t) => (
              <tr key={t.id} className={t.finished ? "task-finished" : ""}>
                <td>{mayChange(t) ? (
                  <select value={t.status} onChange={(e) => put(t, { status: e.target.value })} aria-label={`Status of ${t.title}`}>
                    {data.statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select>
                ) : <span className="chip">{t.status}</span>}</td>
                <td><button className="linkish task-title" onClick={() => setOpen(t)}>{t.title}</button>
                  {t.notes_html && <span className="quiet small" title="Has notes"> 📝</span>}</td>
                <td>{t.assigned_to ? (t.assigned_to === me ? <b>me</b> : t.assigned_to) : <span className="quiet">nobody</span>}</td>
                <td className="small">{t.step ? <>{stepLabel(t.step)}{t.step.done && <span className="quiet"> (step done)</span>}</> : <span className="quiet">–</span>}</td>
                <td className="small quiet" title={`changed by ${t.modified_by}, ${fmtDateTime(t.modified_at)}`}>{t.created_by}</td>
                <td>{!readOnly && data.may_add && (t.created_by.toLowerCase() === me || data.may_admin) && (
                  <button className="linkish" aria-label={`Delete ${t.title}`} title="Delete"
                    onClick={() => act(() => apiFetch(`${url}/${t.id}`, { method: "DELETE" }))}>🗑</button>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {open && <TaskDialog url={url} data={data} task={open} full={data.may_add && !readOnly} may={open.id ? mayChange(open) : canAdd}
        onClose={() => setOpen(null)} onDone={(text) => { setMsg({ ok: true, text }); setOpen(null); refreshAll(); }} />}
      {statusesOpen && <StatusesDialog url={`/api/v1/projects/${p.id}/task-statuses`} data={data} onClose={() => setStatusesOpen(false)} />}
    </div>
  );
}

function StepSelect({ steps, value, onChange, none }) {
  const phases = [...new Set(steps.map((s) => s.phase))];
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Step">
      <option value="">{none}</option>
      {phases.map((ph) => (
        <optgroup key={ph} label={`Phase ${ph}`}>
          {steps.filter((s) => s.phase === ph).map((s) => <option key={s.id} value={String(s.id)}>{s.parent ? `  › ${s.name}` : s.name}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

function TaskDialog({ url, data, task, full, may, onClose, onDone }) {
  const [f, setF] = useState({ title: task.title || "", notes_html: task.notes_html || "", status: task.status || "Created",
    assigned_to: task.assigned_to || "", step_id: task.step ? String(task.step.id) : "" });
  const [err, setErr] = useState("");
  const set = (k, v) => setF({ ...f, [k]: v });
  async function save() {
    try {
      const body = full ? { ...f, step_id: f.step_id || null } : { status: f.status, notes_html: f.notes_html };
      const r = await apiFetch(task.id ? `${url}/${task.id}` : url, { method: task.id ? "PUT" : "POST", body: JSON.stringify(body) });
      onDone(r.message);
    } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={task.id ? "Task" : "A new task"} onClose={onClose} wide
      actions={<>{may && <button className="primary" onClick={save} disabled={!f.title.trim()}>Save</button>}<button onClick={onClose}>{may ? "Cancel" : "Close"}</button></>}>
      {err && <p className="status bad">{err}</p>}
      <Field label="Task"><input value={f.title} onChange={(e) => set("title", e.target.value)} disabled={!full} /></Field>
      <div className="row-gap">
        <Field label="Status"><select value={f.status} onChange={(e) => set("status", e.target.value)} disabled={!may}>
          {data.statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select></Field>
        <Field label="Assigned to"><select value={f.assigned_to} onChange={(e) => set("assigned_to", e.target.value)} disabled={!full}>
          <option value="">Nobody yet</option>{data.people.map((u) => <option key={u} value={u}>{u === data.me ? `${u} (me)` : u}</option>)}</select></Field>
        <Field label="Step or sub step"><StepSelect steps={data.steps} value={f.step_id} onChange={(v) => full && set("step_id", v)} none="No step" /></Field>
      </div>
      <Field label="Notes">{may ? <RichText value={f.notes_html} onChange={(v) => set("notes_html", v)} placeholder="What it is about, where it stands" />
        : <div className="rich-view" dangerouslySetInnerHTML={{ __html: f.notes_html || "<p class='quiet'>No notes.</p>" }} />}</Field>
      {task.id && <p className="small quiet">Made by {task.created_by} on {fmtDateTime(task.created_at)}; last changed by {task.modified_by} on {fmtDateTime(task.modified_at)}.
        {!full && may && " You may change its status and notes (it is assigned to you)."}</p>}
    </Modal>
  );
}

function StatusesDialog({ url, data, onClose }) {
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const own = data.statuses.filter((s) => !data.standard.includes(s));
  async function go(fn) {
    try { await fn(); setErr(""); refreshAll(); } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title="Task statuses" onClose={onClose} actions={<button className="primary" onClick={onClose}>Done</button>}>
      <p className="small quiet">Standard: {data.standard.join(", ")}. Add statuses of this project's own; one in use stays until its tasks change.</p>
      {err && <p className="status bad">{err}</p>}
      {own.length ? <ul>{own.map((s) => <li key={s}>{s} <button className="linkish" aria-label={`Remove ${s}`}
        onClick={() => go(() => apiFetch(`${url}?name=${encodeURIComponent(s)}`, { method: "DELETE" }))}>✕</button></li>)}</ul>
        : <p className="quiet small">None of its own yet.</p>}
      <form className="row-gap" onSubmit={(e) => { e.preventDefault(); if (name.trim()) go(() => apiFetch(url, { method: "POST", body: JSON.stringify({ name }) }).then(() => setName(""))); }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="A new status, e.g. Waiting for input" aria-label="New status" maxLength={40} />
        <button type="submit" disabled={!name.trim()}>＋ Add</button>
      </form>
    </Modal>
  );
}
