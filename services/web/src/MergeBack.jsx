// Merging a child model into its parent (phases 19 and 20, D359, D422 to D425): one merge-to-parent wizard.
//   send      the child's Model Admin sends the child (SendForMergeWizard, on the child's Wizards tab)
//   review    the parent's Model Admins and Committers accept or reject each change (#/merge-requests/<id>)
//   merge     everything accepted goes into the parent as one commit; the merge report is kept
//   after     the child's Model Admin freezes the child or refreshes it from the parent
// #/merge-requests lists what waits for me; each model's Model admin > Merge requests tab lists its own.
import { useMemo, useState } from "react";
import { apiDownload, apiFetch } from "./auth";
import { fmtDateTime } from "./fmt";
import { Field, Modal } from "./ModelOps";
import { refreshAll, useApi } from "./ModelViews";
import { runTask } from "./tasks";

const post = (path, body) => apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });
const KIND = { metamodel: "Metamodel", add: "Added", update: "Changed", delete: "Removed", relate: "Related", unrelate: "Unrelated" };
const STATUS = { sent: "Waiting for review", merged: "Merged: waiting for freeze or refresh", closed: "Closed", withdrawn: "Withdrawn" };
const show = (v) => (v === null || v === undefined || v === "" ? <span className="quiet">empty</span> : String(v));

export function StatusBadge({ r }) {
  const cls = r.status === "sent" ? "warn" : r.status === "merged" ? "warn" : r.status === "closed" ? "ok" : "off";
  return <span className={`rag ${cls}`}>{STATUS[r.status]}{r.status === "closed" && r.after ? `: child ${r.after}` : ""}</span>;
}

function Counts({ c }) {
  if (!c) return null;
  const parts = Object.entries(KIND).filter(([k]) => c[k]).map(([k, l]) => `${c[k]} ${l.toLowerCase()}`);
  return <span className="quiet small">{c.total} change{c.total === 1 ? "" : "s"}{parts.length ? ` (${parts.join(", ")})` : ""}
    {c.conflicts ? <> · <b>{c.conflicts} conflict{c.conflicts === 1 ? "" : "s"}</b></> : ""}</span>;
}

// ---------------------------------------------------------------- the changes, three-way
function ChangeTable({ changes, decide, busy, may }) {
  const [filter, setFilter] = useState("all");
  const [why, setWhy] = useState({});
  const rows = changes.filter((c) => filter === "all" || (filter === "conflicts" ? c.conflict : filter === "rejected"
    ? c.decision?.accept === false : c.kind === filter));
  const kinds = [...new Set(changes.map((c) => c.kind))];
  const state = (c) => (c.decision ? (c.decision.accept ? "accepted" : "rejected") : c.conflict ? "to decide" : "pre-accepted");
  return (
    <div>
      <div className="toolbar">
        <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Show">
          <option value="all">Every change ({changes.length})</option>
          <option value="conflicts">Conflicts ({changes.filter((c) => c.conflict).length})</option>
          <option value="rejected">Rejected ({changes.filter((c) => c.decision?.accept === false).length})</option>
          {kinds.map((k) => <option key={k} value={k}>{KIND[k]} ({changes.filter((c) => c.kind === k).length})</option>)}
        </select>
        <span className="quiet small">A change only the child made is pre-accepted; a conflict (both changed it) is decided here. Accepting a conflict
          takes the child's value; rejecting keeps the parent's and needs a reason.</span>
      </div>
      <div className="grid-scroll"><table className="grid-table merge-changes">
        <thead><tr><th>Change</th><th>Type</th><th>Item</th><th>Field</th><th>At the start</th><th>Child</th><th>Parent now</th><th>Why</th><th>Decision</th></tr></thead>
        <tbody>{rows.map((c) => (
          <tr key={c.id} className={c.conflict ? "conflict-row" : ""}>
            <td>{KIND[c.kind]}{c.conflict && <span className="rag warn small" title="Changed in both, or no starting point to tell"> conflict</span>}</td>
            <td className="quiet">{c.entity_type || c.relationship_type || (c.section || "").replace(/_/g, " ")}</td>
            <td>{c.name}</td><td>{c.field || ""}</td>
            <td className="quiet">{c.kind === "update" ? show(c.base) : ""}</td>
            <td>{c.kind === "update" ? show(c.child) : ""}</td>
            <td>{c.kind === "update" ? show(c.parent) : ""}</td>
            <td className="quiet small">{c.why}</td>
            <td className="nowrap">
              <span className={`rag small ${state(c) === "rejected" ? "bad" : state(c) === "to decide" ? "warn" : "ok"}`}>{state(c)}</span>
              {c.decision?.reason && <div className="quiet small">“{c.decision.reason}” ({c.decision.by})</div>}
              {may && (
                <div className="merge-decide">
                  <button className="small" disabled={busy || c.decision?.accept === true || (c.kind === "metamodel" && !may.admin)}
                    onClick={() => decide({ [c.id]: { accept: true } })}>Accept</button>
                  <input className="small" placeholder="why rejected" value={why[c.id] || ""} onChange={(e) => setWhy({ ...why, [c.id]: e.target.value })} />
                  <button className="small" disabled={busy || !(why[c.id] || "").trim() || (c.kind === "metamodel" && !may.admin)}
                    title={(why[c.id] || "").trim() ? "" : "Say why first"} onClick={() => decide({ [c.id]: { accept: false, reason: why[c.id] } })}>Reject</button>
                  {c.decision && <button className="linkish small" disabled={busy} onClick={() => decide({ [c.id]: { accept: null } })}>undo</button>}
                </div>)}
            </td>
          </tr>))}</tbody>
      </table></div>
      {!rows.length && <p className="quiet">Nothing to show.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- send (the child's Model Admin)
export function SendForMergeWizard({ m, parent, onClose }) {
  const { data: p, error } = useApi(`/api/v1/models/${m.id}/merge-requests/preview`);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [done, setDone] = useState(null);
  async function send() {
    setBusy(true); setMsg("");
    try {
      const out = await runTask(post(`/api/v1/models/${m.id}/merge-requests`, { note }), `#/model-admin/${m.id}/merge-requests`);
      setDone(out); refreshAll();
    } catch (e) { setMsg(e.message); }
    setBusy(false);
  }
  return (
    <Modal wide title={`Send ${m.name} for merge into ${parent?.name || "its parent"}`} onClose={onClose}
      actions={done ? <><button onClick={onClose}>Close</button><a className="button primary" href={`#/merge-requests/${done.id}`} onClick={onClose}>Open the request</a></>
        : <><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !p || !p.changes?.length} onClick={send}>{busy ? "Sending…" : "Send for merge"}</button></>}>
      <div className="ed-form">
      {done ? <p className="status ok">Merge request {done.number} sent. {parent?.name}'s Model Admins and Committers review it; you are told when it is merged,
        and then choose to freeze {m.name} or refresh it from {parent?.name}.</p> : <>
        <p>Compared three ways: {m.name} now, {m.name} at its starting point{p?.base ? <> (<b>{p.base.name}</b>)</> : ""}, and {parent?.name} now.
          Only what {m.name} changed is sent; where both changed the same thing, the reviewers decide.</p>
        {p && !p.base && <p className="status warn small">{m.name} has no starting point (it was made before this was kept, or moved under its parent later):
          every difference is sent as a conflict for the reviewers to decide.</p>}
        {error && <p className="status bad">{error}</p>}
        {!p && !error && <p><span className="spinner" aria-hidden="true" /> Comparing {m.name} with {parent?.name}…</p>}
        {p && <><p><Counts c={p.counts} /></p>
          {p.changes.length ? <ChangeTable changes={p.changes} /> : <p className="status ok">Nothing to merge: {m.name} changed nothing since its starting point.</p>}
          <Field label="A note for the reviewers"><textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed and why" /></Field></>}
        {msg && <p className="status bad">{msg}</p>}
      </>}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- lists
function RequestRows({ rows, side }) {
  if (!rows?.length) return <p className="quiet">None.</p>;
  return (
    <table className="grid-table"><thead><tr><th>#</th><th>{side === "sent" ? "Into" : "From"}</th><th>Status</th><th>Changes</th><th>Sent</th><th /></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.id}><td>{r.number}</td><td>{side === "sent" ? r.parent?.name : r.child?.name}</td><td><StatusBadge r={r} />{r.waiting && <div className="small quiet">waiting for you: {r.waiting}</div>}</td>
          <td><Counts c={r.counts} />{r.status === "sent" && r.undecided ? <div className="small">{r.undecided} conflict{r.undecided === 1 ? "" : "s"} undecided</div> : null}</td>
          <td className="quiet small">{r.sent_by}, {fmtDateTime(r.sent_at)}</td>
          <td><a href={`#/merge-requests/${r.id}`}>Open</a></td></tr>))}</tbody></table>
  );
}

export function MergeRequestsTab({ m }) {
  const { data, error } = useApi(`/api/v1/models/${m.id}/merge-requests`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading…</p>;
  return (
    <div>
      <p className="quiet">A child is sent for merge by its Model Admin; the parent's Model Admins and Committers review each change, then merge it as one commit.
        Afterwards the child is frozen or refreshed from the parent.</p>
      {data.parent && <><h3>Sent to {data.parent.name}</h3><RequestRows rows={data.sent} side="sent" /></>}
      <h3>Sent to {m.name} by its children</h3><RequestRows rows={data.received} side="received" />
    </div>
  );
}

// ---------------------------------------------------------------- #/merge-requests and #/merge-requests/<id>
export default function MergeRequestsPage({ route }) {
  const id = route.replace(/^#\/merge-requests\/?/, "").split("?")[0];
  if (id) return <MergeRequest key={id} id={id} />;
  return <Waiting />;
}

function Waiting() {
  const { data, error } = useApi("/api/v1/merge-requests/waiting");
  return (
    <section>
      <h1>Merge requests waiting for you</h1>
      <p className="quiet">Children sent for merge into a model you review, and merged children you choose to freeze or refresh.
        Every model's own requests are on its Model admin › Merge requests tab.</p>
      {error && <p className="status bad">{error}</p>}
      {!data && !error && <p>Loading…</p>}
      {data && <RequestRows rows={data.requests} side="received" />}
    </section>
  );
}

function MergeRequest({ id }) {
  const { data: r, error } = useApi(`/api/v1/merge-requests/${id}`);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [live, setLive] = useState(null);
  const [choice, setChoice] = useState("refresh");
  const [note, setNote] = useState("");
  const req = live || r;
  const may = req && req.status === "sent" && req.you?.reviewer ? { admin: req.you.parent_admin } : null;
  const left = useMemo(() => (req?.changes || []).filter((c) => c.conflict && !c.decision).length, [req]);
  if (error) return <section><p className="status bad">{error}</p></section>;
  if (!req) return <section><p>Loading…</p></section>;
  async function act(fn, ok) {
    setBusy(true); setMsg(null);
    try { const out = await fn(); if (out?.changes) setLive(out); setMsg([true, out?.message || ok]); refreshAll(); }
    catch (e) { setMsg([false, e.message]); }
    setBusy(false);
  }
  const decide = (d) => act(() => post(`/api/v1/merge-requests/${id}/decisions`, { decisions: d }), "Saved.");
  const accepted = (req.changes || []).filter((c) => (c.decision ? c.decision.accept : !c.conflict)).length;
  return (
    <section className="merge-request">
      <p className="quiet breadcrumb"><a href="#/merge-requests">Merge requests</a> / {req.child?.name} into {req.parent?.name}</p>
      <h1>Merge request {req.number}: <a href={`#/model-admin/${req.child?.id}`}>{req.child?.name}</a> into <a href={`#/model-admin/${req.parent?.id}`}>{req.parent?.name}</a></h1>
      <p><StatusBadge r={req} /> <Counts c={req.counts} /></p>
      <p className="quiet">Sent by {req.sent_by}, {fmtDateTime(req.sent_at)}. Compared with {req.base ? <b>{req.base.name}</b> : "no starting point (every difference is a conflict)"}.
        {req.merged_at && <> Merged by {req.merged_by}, {fmtDateTime(req.merged_at)}.</>}{req.closed_at && <> Closed by {req.closed_by}, {fmtDateTime(req.closed_at)}.</>}</p>
      {req.note && <blockquote className="merge-note">{req.note}</blockquote>}
      {msg && <p className={`status ${msg[0] ? "ok" : "bad"}`}>{msg[1]}</p>}

      {req.status === "sent" && (
        <div className="toolbar">
          {req.you?.reviewer && <button className="primary" disabled={busy || left > 0} title={left ? `Decide the ${left} conflict${left === 1 ? "" : "s"} first` : ""}
            onClick={() => act(() => runTask(post(`/api/v1/merge-requests/${id}/merge`), `#/merge-requests/${id}`), "Merged.")}>
            {busy ? "Merging…" : `Merge ${accepted} accepted change${accepted === 1 ? "" : "s"} into ${req.parent?.name}`}</button>}
          {req.you?.reviewer && <span className="quiet small">{left ? `${left} conflict${left === 1 ? "" : "s"} to decide. ` : ""}{req.parent?.name} is tagged first;
            everything accepted is one commit (roll it back from Changes › Commits).</span>}
          {!req.you?.reviewer && <span className="quiet small">Waiting for {req.parent?.name}'s Model Admins and Committers.</span>}
          {req.you?.child_admin && <button disabled={busy} onClick={() => act(() => post(`/api/v1/merge-requests/${id}/withdraw`, {}), "Withdrawn.")}>Withdraw</button>}
        </div>)}

      {req.status === "merged" && req.you?.child_admin && (
        <div className="merge-step">
          <h3>What happens to {req.child?.name} now?</h3>
          <label className="wiz-check"><input type="radio" checked={choice === "refresh"} onChange={() => setChoice("refresh")} />
            <span><b>Refresh it from {req.parent?.name} and carry on</b>: it becomes what {req.parent?.name} holds now (rejected changes go), tagged first,
              with a new starting point for the next merge.</span></label>
          <label className="wiz-check"><input type="radio" checked={choice === "freeze"} onChange={() => setChoice("freeze")} />
            <span><b>Freeze it</b>: read only for good. It can still be copied, compared and reported on.</span></label>
          {choice === "freeze" && <Field label="Why it is frozen (shown on it)"><input value={note} onChange={(e) => setNote(e.target.value)} placeholder={`Merged into ${req.parent?.name}`} /></Field>}
          <button className="primary" disabled={busy} onClick={() => act(() => runTask(post(`/api/v1/merge-requests/${id}/finish`, { choice, note }), `#/merge-requests/${id}`), "Done.")}>
            {busy ? "Working…" : choice === "freeze" ? `Freeze ${req.child?.name}` : `Refresh ${req.child?.name}`}</button>
        </div>)}
      {req.status === "merged" && !req.you?.child_admin && <p className="quiet">Waiting for {req.child?.name}'s Model Admin to freeze it or refresh it.</p>}

      {req.report && (
        <div className="merge-step">
          <h3>Merge report</h3>
          <p>{req.report.accepted.length} accepted, {req.report.rejected.length} rejected
            {(req.report.failed?.length || req.report.left_out?.length) ? `, ${req.report.failed.length + req.report.left_out.length} not applied` : ""}.
            {req.report.commit && <> Commit <a href={`#/metamodel/${req.parent?.id}/changes/history/${req.report.commit}`}>{req.report.commit}</a> in {req.parent?.name}.</>}
            {req.report.tag && <> Tagged first as <b>{req.report.tag.name}</b>.</>}
            {" "}<button className="linkish" onClick={() => apiDownload(`/api/v1/merge-requests/${id}/report`, `Merge report ${req.number}.docx`)}>Download the report (Word)</button></p>
          {req.report.rejected.length > 0 && <table className="grid-table"><thead><tr><th>Rejected</th><th>Item</th><th>Field</th><th>Reason</th><th>By</th></tr></thead>
            <tbody>{req.report.rejected.map((x) => <tr key={x.id}><td>{KIND[x.kind]}</td><td>{x.name}</td><td>{x.field || ""}</td><td>{x.reason}</td><td className="quiet">{x.by}</td></tr>)}</tbody></table>}
          {[...(req.report.failed || []), ...(req.report.left_out || [])].length > 0 && <p className="status warn small">Not applied: {[...(req.report.failed || []).map((f) => `${f.what}: ${f.error}`),
            ...(req.report.left_out || []).map((f) => `${f.what}: ${f.why}`)].join("; ")}</p>}
        </div>)}

      <h3>Changes</h3>
      <ChangeTable changes={req.changes || []} decide={decide} busy={busy} may={may} />
    </section>
  );
}
