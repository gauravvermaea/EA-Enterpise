// Phase 8.1 (D84, D209): notifications, requests between people, metamodel push-down, change documents, webhooks.
// Notifications that need action stay open until someone resolves them with a note (once for everyone who got them);
// information ones are read or dismissed by each person. The bell's count is read when a page opens (no live push).
import { useEffect, useState } from "react";
import { apiFetch, can, canOn, currentUser } from "./auth";
import { fmtDateTime } from "./fmt";
import { Modal } from "./ModelOps";
import { refreshAll, useApi } from "./ModelViews";

const CATEGORY = { commit: "Commits", metamodel: "Metamodel", request: "Requests", model: "Model events", system: "System" };
const ICON = { commit: "✔", metamodel: "⬇", request: "✉", model: "◆", system: "⚠" };
const STATUS = { open: "Open", in_progress: "In progress", done: "Done", declined: "Declined" };

// ---------------------------------------------------------------- the bell (top bar)
export function Bell({ route }) {
  const [c, setC] = useState(null);
  useEffect(() => {
    let live = true;
    apiFetch("/api/v1/notifications/counts").then((x) => live && setC(x)).catch(() => {});
    return () => { live = false; };
  }, [route]);   // read again when a page opens (D209: no live push)
  const n = c ? c.unread + c.open_requests : 0;
  const title = c ? `${c.unread} unread notification${c.unread === 1 ? "" : "s"}, ${c.open_actions} waiting for action, `
    + `${c.open_requests} open request${c.open_requests === 1 ? "" : "s"} for you` : "Notifications";
  return (
    <a href="#/notifications" className={`bell${n ? " has" : ""}`} title={title} aria-label={title}>
      <span aria-hidden="true">🔔</span>{n > 0 && <span className="bell-count">{n > 99 ? "99+" : n}</span>}
    </a>
  );
}

// ---------------------------------------------------------------- the notifications page
export default function NotificationsPage({ route }) {
  const parts = route.replace(/^#\/notifications\/?/, "").split(/[/?]/).filter(Boolean);
  const view = parts[0] || "inbox";
  const go = (p) => { window.location.hash = `#/notifications${p ? `/${p}` : ""}`; };
  const { data: counts } = useApi("/api/v1/notifications/counts");
  const { data: reqs } = useApi("/api/v1/requests?box=received&status=active");
  const tabs = [
    ["inbox", `Notifications${counts?.unread ? ` (${counts.unread})` : ""}`],
    ["received", `Requests to me${reqs?.counts?.received_active ? ` (${reqs.counts.received_active})` : ""}`],
    ["sent", "Requests I sent"],
    ["new", "✉ New request"],
  ];
  return (
    <section className="notifications-page">
      <h1>Notifications and requests</h1>
      <p className="quiet">What happened on your models, and requests between people. Notifications that need action
        stay open until someone resolves them with a note of what they did; the others you read or dismiss. A request is
        like a ticket: private to you and the other person.</p>
      <div className="tabs" role="tablist">
        {tabs.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={view === k || (view === "requests" && k === "received")}
            className={view === k ? "tab on" : "tab"} onClick={() => go(k === "inbox" ? "" : k)}>{label}</button>
        ))}
      </div>
      {view === "inbox" ? <Inbox />
        : view === "requests" && parts[1] ? <RequestPage key={parts[1]} id={parts[1]} />
        : view === "received" || view === "sent" ? <RequestList box={view} />
        : view === "new" ? <NewRequest />
        : <Inbox />}
    </section>
  );
}

function Inbox() {
  const [show, setShow] = useState("open");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [resolving, setResolving] = useState(null);
  const [err, setErr] = useState("");
  const path = `/api/v1/notifications?show=${show}&category=${category}&q=${encodeURIComponent(q)}`;
  const { data, error } = useApi(path);
  // seen on screen: mark the unread ones read (the bell goes down when the next page opens)
  useEffect(() => {
    const unread = (data?.items || []).filter((n) => !n.read_at).map((n) => n.id);
    if (unread.length) apiFetch("/api/v1/notifications/read", { method: "POST", body: JSON.stringify({ ids: unread }) }).catch(() => {});
  }, [data]);
  async function act(fn) {
    setErr("");
    try { await fn(); refreshAll(); } catch (e) { setErr(e.message); }
  }
  const dismiss = (n) => act(() => apiFetch(`/api/v1/notifications/${n.id}/dismiss`, { method: "POST" }));
  return (
    <div className="merge-step">
      <div className="row-gap filters">
        <select value={show} onChange={(e) => setShow(e.target.value)} aria-label="Show">
          <option value="open">Open</option><option value="actions">Waiting for action</option>
          <option value="resolved">Resolved and dismissed</option><option value="all">All</option>
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Kind">
          <option value="">Every kind</option>
          {Object.entries(CATEGORY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input type="search" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        {data && <span className="quiet small">{data.total} notification{data.total === 1 ? "" : "s"} · {data.counts.open_actions} waiting for action</span>}
      </div>
      {error && <p className="status bad">{error}</p>}
      {err && <p className="status bad">{err}</p>}
      {data && !data.items.length && <p className="quiet">Nothing here.</p>}
      <ul className="notif-list">
        {(data?.items || []).map((n) => (
          <li key={n.id} className={`notif ${n.needs_action && !n.resolved_at ? "action" : ""} ${n.read_at ? "" : "unread"}`}>
            <span className={`notif-icon ${n.category}`} aria-hidden="true">{ICON[n.category]}</span>
            <div className="notif-main">
              <div>
                {n.link ? <a href={n.link}><strong>{n.title}</strong></a> : <strong>{n.title}</strong>}
                {n.needs_action && !n.resolved_at && <span className="badge action-badge">needs action</span>}
              </div>
              {n.body && <div className="notif-body small">{n.body}</div>}
              <div className="quiet small">{CATEGORY[n.category]} · {n.model_name ? <><a href={`#/metamodel/${n.model_id}`}>{n.model_name}</a> · </> : null}
                {n.actor} · {fmtDateTime(n.created_at)}</div>
              {n.resolved_at && <div className="small resolved-note">Resolved by {n.resolved_by} {fmtDateTime(n.resolved_at)}: {n.resolution}</div>}
            </div>
            <div className="notif-actions">
              {n.needs_action && !n.resolved_at && <button onClick={() => setResolving(n)}>Resolve...</button>}
              {!n.needs_action && !n.dismissed_at && <button className="linkish" onClick={() => dismiss(n)}>Dismiss</button>}
            </div>
          </li>
        ))}
      </ul>
      {resolving && <ResolveDialog n={resolving} onClose={() => setResolving(null)} />}
    </div>
  );
}

function ResolveDialog({ n, onClose }) {
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  async function save() {
    try {
      await apiFetch(`/api/v1/notifications/${n.id}/resolve`, { method: "POST", body: JSON.stringify({ note }) });
      refreshAll(); onClose();
    } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title="Resolve" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!note.trim()} onClick={save}>Resolve</button></>}>
      <p><strong>{n.title}</strong></p>
      <p className="quiet small">Resolved once for everyone who got it: say what you did.</p>
      <textarea rows={4} style={{ width: "100%" }} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What was done" autoFocus />
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- requests
function RequestList({ box }) {
  const [status, setStatus] = useState("active");
  const [q, setQ] = useState("");
  const { data, error } = useApi(`/api/v1/requests?box=${box}&status=${status}&q=${encodeURIComponent(q)}`);
  return (
    <div className="merge-step">
      <div className="row-gap filters">
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="active">Open and in progress</option><option value="closed">Done and declined</option>
          <option value="all">All</option>
        </select>
        <input type="search" placeholder="Search, or a number" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {error && <p className="status bad">{error}</p>}
      {data && !data.items.length && <p className="quiet">No requests here.</p>}
      {data && data.items.length > 0 && (
        <div className="table-scroll">
          <table className="grid-table">
            <thead><tr><th>#</th><th>Subject</th><th>{box === "received" ? "From" : "To"}</th><th>Status</th><th>Comments</th><th>Updated</th></tr></thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id}>
                  <td><a href={`#/notifications/requests/${r.number}`}>{r.number}</a></td>
                  <td><a href={`#/notifications/requests/${r.number}`}>{r.subject}</a></td>
                  <td>{box === "received" ? r.sender : r.receiver}</td>
                  <td><span className={`req-status ${r.status}`}>{r.status_label}</span></td>
                  <td>{r.comment_count || ""}</td>
                  <td className="small">{fmtDateTime(r.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function NewRequest() {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: people } = useApi(`/api/v1/requests/people?q=${encodeURIComponent(to)}`);
  const me = (currentUser()?.preferred_username || "").toLowerCase();
  const note = !!me && to.trim().toLowerCase() === me;
  async function send() {
    setBusy(true); setErr("");
    try {
      const r = await apiFetch("/api/v1/requests", { method: "POST", body: JSON.stringify({ to, subject, body }) });
      refreshAll();
      window.location.hash = `#/notifications/requests/${r.number}`;
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  return (
    <div className="merge-step request-form">
      <h3>New request</h3>
      <p className="quiet small">Ask someone to do something, for example a Model Admin to add an attribute. They are told
        and move it along: in progress, then done or declined with a note. Only the two of you see it. Send it to yourself
        to keep a note or a to-do: only you see it, and you move it along the same way.</p>
      <label>To <input list="request-people" value={to} onChange={(e) => setTo(e.target.value)} placeholder="Their username, or yours for a note" />
        {me && !note && <button className="linkish small" onClick={() => setTo(me)}>Note to myself</button>}</label>
      {note && <p className="quiet small">A note to yourself: nobody else sees it and nobody is notified.</p>}
      <datalist id="request-people">{(people?.people || []).map((p) => <option key={p} value={p} />)}</datalist>
      <label>Subject <input value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} placeholder="What you ask for, in a line" /></label>
      <label>Details <textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Everything they need to know (no attachments)" /></label>
      <div className="row-gap">
        <button className="primary" disabled={busy || !to.trim() || !subject.trim()} onClick={send}>{busy ? "Sending..." : note ? "Keep the note" : "Send the request"}</button>
      </div>
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}

function RequestPage({ id }) {
  const { data: r, error } = useApi(`/api/v1/requests/${id}`);
  const [text, setText] = useState("");
  const [closing, setClosing] = useState(null);   // "done" | "declined" | "open"
  const [err, setErr] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!r) return <p className="quiet">Loading...</p>;
  async function post(path, payload) {
    setErr("");
    try { await apiFetch(`/api/v1/requests/${r.number}/${path}`, { method: "POST", body: JSON.stringify(payload) }); setText(""); refreshAll(); }
    catch (e) { setErr(e.message); }
  }
  const closed = r.status === "done" || r.status === "declined";
  return (
    <div className="merge-step request-page">
      <p><a href="#/notifications/received">← Requests</a></p>
      <h3>#{r.number} {r.subject} <span className={`req-status ${r.status}`}>{r.status_label}</span></h3>
      <p className="quiet small">From <strong>{r.sender}</strong> to <strong>{r.receiver}</strong> · {fmtDateTime(r.created_at)}
        {r.via !== "screen" && ` · sent through ${r.via === "mcp" ? "a language model (MCP)" : "the API"}`}</p>
      {r.body && <div className="request-body">{r.body}</div>}
      {closed && <p className="small resolved-note">{r.status_label} {fmtDateTime(r.closed_at)}: {r.close_note}</p>}
      <h4>Trail</h4>
      <ul className="request-trail">
        {(r.comments || []).map((c, i) => (
          <li key={i} className={c.status ? "trail-status" : ""}>
            <span className="quiet small">{c.author} · {fmtDateTime(c.created_at)}{c.status && ` · ${STATUS[c.status]}`}</span>
            <div>{c.body}</div>
          </li>
        ))}
        {!(r.comments || []).length && <li className="quiet small">No comments yet.</li>}
      </ul>
      <textarea rows={3} style={{ width: "100%" }} value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a comment" />
      <div className="row-gap">
        <button disabled={!text.trim()} onClick={() => post("comments", { body: text })}>Comment</button>
        {r.mine_to_act && r.status === "open" && <button onClick={() => post("status", { status: "in_progress" })}>▶ Start</button>}
        {r.mine_to_act && <button className="primary" onClick={() => setClosing("done")}>✔ Done...</button>}
        {r.mine_to_act && <button onClick={() => setClosing("declined")}>✖ Decline...</button>}
        {closed && <button onClick={() => setClosing("open")}>Open again...</button>}
      </div>
      {err && <p className="status bad">{err}</p>}
      {closing && <CloseDialog what={closing} onClose={() => setClosing(null)}
        onSave={async (note) => { await post("status", { status: closing, note }); setClosing(null); }} />}
    </div>
  );
}

function CloseDialog({ what, onClose, onSave }) {
  const [note, setNote] = useState("");
  const label = { done: "Done", declined: "Decline", open: "Open again" }[what];
  return (
    <Modal title={label} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={what !== "open" && !note.trim()} onClick={() => onSave(note)}>{label}</button></>}>
      <p className="quiet small">{what === "done" ? "Say what was done." : what === "declined" ? "Say why it is declined." : "Say why it is opened again."}</p>
      <textarea rows={4} style={{ width: "100%" }} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
    </Modal>
  );
}

// ---------------------------------------------------------------- metamodel push-down (a model tab)
export function PushDownTab({ model }) {
  const { data, error } = useApi(`/api/v1/models/${model}/pushdown`);
  const [mode, setMode] = useState("offered");
  const [fill, setFill] = useState(true);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [deciding, setDeciding] = useState(null);   // {item, accept}
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const mayEdit = canOn(model, "model.metamodel");
  const writable = data.children.filter((k) => !k.read_only);
  async function push() {
    setBusy(true); setErr(""); setMsg("");
    try {
      const out = await apiFetch(`/api/v1/models/${model}/pushdown`, { method: "POST", body: JSON.stringify({ mode, fill_defaults: fill, note }) });
      setMsg(`${out.message} ${out.targets.map((t) => `${t.model}: ${t.status}${t.error ? ` (${t.error})` : ""}`).join("; ")}`);
      setNote(""); refreshAll();
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  const waiting = data.incoming.filter((x) => x.status === "offered");
  return (
    <div className="pushdown">
      <p className="quiet">Metamodel changes go down the model hierarchy (D84). Changes made in the metamodel editor or the
        grids since the last push go to the models directly under this one as one package: <strong>forced</strong> (made
        in each at once) or <strong>offered</strong> (each model&apos;s Model Admin accepts or rejects it). A model that
        accepts can pass it on to the models under it the same way; one that rejects differs from its parent from then on.</p>

      {data.parent && (
        <div className="merge-step">
          <h3>From the model above: {data.parent.name}</h3>
          {!data.incoming.length && <p className="quiet small">Nothing has arrived from {data.parent.name} yet.</p>}
          {data.incoming.length > 0 && (
            <div className="table-scroll">
              <table className="grid-table">
                <thead><tr><th>Arrived</th><th>Versions</th><th>How</th><th>Changes</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {data.incoming.map((x) => (
                    <tr key={x.id} className={x.status === "offered" ? "row-attention" : ""}>
                      <td className="small">{fmtDateTime(x.pushed_at)}<div className="quiet">by {x.pushed_by}</div></td>
                      <td>{x.versions.join(", ")}</td>
                      <td>{x.mode}</td>
                      <td className="small"><ul className="plain">{(x.changes || []).slice(0, 8).map((c, i) => <li key={i}>{c.note}</li>)}</ul>
                        {(x.changes || []).length > 8 && <span className="quiet">and {x.changes.length - 8} more</span>}
                        {x.note && <div className="quiet">“{x.note}”</div>}</td>
                      <td><span className={`push-status ${x.status}`}>{x.status}</span>
                        {x.decided_by && <div className="quiet small">{x.decided_by} {fmtDateTime(x.decided_at)}</div>}
                        {x.decision_note && <div className="small">{x.decision_note}</div>}
                        {x.error && <div className="status bad small">{x.error}</div>}</td>
                      <td className="nowrap">
                        {x.status === "offered" && mayEdit && <>
                          <button className="primary" onClick={() => setDeciding({ item: x, accept: true })}>Accept...</button>{" "}
                          <button onClick={() => setDeciding({ item: x, accept: false })}>Reject...</button></>}
                        {x.status === "offered" && !mayEdit && <span className="quiet small">its Model Admin decides</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.diverged.length > 0 && <p className="small">This model rejected {data.diverged.length} package{data.diverged.length === 1 ? "" : "s"} from
            {" "}{data.parent.name}: its metamodel differs from its parent&apos;s there.</p>}
          {waiting.length > 0 && <p className="small">{waiting.length} package{waiting.length === 1 ? "" : "s"} waiting for a decision.</p>}
        </div>
      )}

      <div className="merge-step">
        <h3>To the models below</h3>
        {!data.children.length ? <p className="quiet small">No models under this one.</p> : (
          <p className="small">Models directly below: {data.children.map((k) => (
            <span key={k.id} className="chip">{k.name}{k.read_only ? " (read-only, skipped)" : ""}</span>))}</p>
        )}
        {!data.children.length ? null : data.unpushed.length > 0 ? (
          <>
            <p className="small">Metamodel versions since the last push:</p>
            <ul className="plain small">
              {data.unpushed.map((v) => <li key={v.version}>v{v.version} · {v.note || "(no note)"} · {v.changed_by} {fmtDateTime(v.changed_at)}
                {!v.pushable && <span className="quiet"> (made another way: not pushed)</span>}</li>)}
            </ul>
          </>
        ) : <p className="quiet small">Nothing new to push.</p>}
        {mayEdit && writable.length > 0 && data.pushable.length > 0 && (
          <div className="push-form">
            <label><input type="radio" checked={mode === "offered"} onChange={() => setMode("offered")} /> Offer it: each model&apos;s Model Admin accepts or rejects</label>
            <label><input type="radio" checked={mode === "forced"} onChange={() => setMode("forced")} /> Force it: made in every model below at once</label>
            <label><input type="checkbox" checked={fill} onChange={(e) => setFill(e.target.checked)} /> Fill existing entities with the default of new attributes</label>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why (shown to the models below)" style={{ width: "100%" }} />
            <button className="primary" disabled={busy} onClick={push}>{busy ? "Pushing..." : `⬇ Push versions ${data.pushable.join(", ")} ${mode}`}</button>
          </div>
        )}
        {msg && <p className="status ok">{msg}</p>}
        {err && <p className="status bad">{err}</p>}
        {data.pushes.length > 0 && (
          <>
            <h4>Pushed</h4>
            <div className="table-scroll">
              <table className="grid-table">
                <thead><tr><th>When</th><th>Versions</th><th>How</th><th>Models below</th></tr></thead>
                <tbody>
                  {data.pushes.map((p) => (
                    <tr key={p.id}>
                      <td className="small">{fmtDateTime(p.pushed_at)}<div className="quiet">by {p.pushed_by}</div></td>
                      <td>{p.versions.join(", ")}</td><td>{p.mode}</td>
                      <td className="small">{p.targets.map((t) => (
                        <div key={t.model_id}>{t.model}: <span className={`push-status ${t.status}`}>{t.status}</span>
                          {t.note && <span className="quiet"> “{t.note}”</span>}{t.error && <span className="status bad"> {t.error}</span>}</div>))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
      {deciding && <DecideDialog model={model} d={deciding} onClose={() => setDeciding(null)} />}
    </div>
  );
}

function DecideDialog({ model, d, onClose }) {
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true); setErr("");
    try {
      const out = await apiFetch(`/api/v1/models/${model}/pushdown/${d.item.id}/decide`, { method: "POST", body: JSON.stringify({ accept: d.accept, note }) });
      if (out.status === "failed") { setErr(`Could not be made: ${out.error}`); setBusy(false); return; }
      refreshAll(); onClose();
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  return (
    <Modal title={d.accept ? "Accept the metamodel changes" : "Reject the metamodel changes"} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy || (!d.accept && !note.trim())} onClick={save}>{d.accept ? "Accept" : "Reject"}</button></>}>
      <p className="small">{d.accept
        ? "The changes are made in this model at once, as a new metamodel version, and everyone on the model gets the change document."
        : "This model keeps its metamodel as it is and differs from its parent from now on; the note stays in its lineage."}</p>
      <textarea rows={3} style={{ width: "100%" }} value={note} onChange={(e) => setNote(e.target.value)}
        placeholder={d.accept ? "A note (optional)" : "Why it is rejected"} />
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- change documents
export function ChangeDocumentsTab({ model }) {
  const { data, error } = useApi(`/api/v1/models/${model}/change-documents`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  return (
    <div className="merge-step">
      <p className="quiet">A page for every change accepted into this model: metamodel changes from the model above,
        commits and merges, with old and new values.</p>
      {!data.documents.length && <p className="quiet">None yet.</p>}
      <ul className="plain">
        {data.documents.map((d) => (
          <li key={d.id}><a href={`#/change-documents/${d.number}`}>{d.title}</a> <span className="quiet small">· {d.kind} · {d.summary} ·
            {" "}{fmtDateTime(d.created_at)}</span></li>
        ))}
      </ul>
    </div>
  );
}

export function ChangeDocumentPage({ route }) {
  const ref = route.replace(/^#\/change-documents\/?/, "").split(/[/?]/)[0];
  const { data: d, error } = useApi(ref ? `/api/v1/change-documents/${ref}` : null);
  if (error) return <section><p className="status bad">{error}</p></section>;
  if (!d) return <section><p className="quiet">Loading...</p></section>;
  return (
    <section className="change-doc">
      <p><a href={`#/metamodel/${d.model.id}/documents`}>← {d.model.name}: change documents</a></p>
      <h1>{d.title}</h1>
      <p className="quiet">{d.model.name} · {d.summary} · {fmtDateTime(d.created_at)}</p>
      {d.sections.map((s, i) => (
        <div key={i} className="merge-step">
          <h3>{s.title}</h3>
          <div className="table-scroll">
            <table className="grid-table">
              <thead><tr><th>Change</th><th>Item</th><th>Field</th><th>Old</th><th>New</th></tr></thead>
              <tbody>
                {s.rows.map((r, j) => (r.fields && r.fields.length ? r.fields.map((f, k) => (
                  <tr key={`${j}-${k}`}>
                    {k === 0 && <td rowSpan={r.fields.length}>{r.what}{r.by && <div className="quiet small">by {r.by}</div>}</td>}
                    {k === 0 && <td rowSpan={r.fields.length}>{r.item}</td>}
                    <td>{f.field}</td><td className="old">{f.old ?? <span className="quiet">empty</span>}</td>
                    <td className="new">{f.new ?? <span className="quiet">empty</span>}</td>
                  </tr>
                )) : (
                  <tr key={j}><td>{r.what}{r.by && <div className="quiet small">by {r.by}</div>}</td><td>{r.item}</td><td colSpan={3} /></tr>
                )))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}

// ---------------------------------------------------------------- webhooks (Administration, IT and Super Admins)
export function WebhooksPanel() {
  const { data, error } = useApi(can("system.operate") ? "/api/v1/admin/webhooks" : null);
  const [form, setForm] = useState({ name: "", url: "", kinds: [] });
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [log, setLog] = useState(null);
  if (!can("system.operate")) return null;
  if (error) return <div className="merge-step"><h3>Webhooks</h3><p className="status bad">{error}</p></div>;
  if (!data) return null;
  async function call(fn) {
    setErr(""); setMsg("");
    try { const out = await fn(); if (out?.message) setMsg(out.message); refreshAll(); return out; } catch (e) { setErr(e.message); return null; }
  }
  const add = () => call(async () => {
    const out = await apiFetch("/api/v1/admin/webhooks", { method: "POST", body: JSON.stringify(form) });
    setForm({ name: "", url: "", kinds: [] });
    return { message: `Added ${out.name}. Its secret signs every message (X-EAX-Signature: sha256=...).` };
  });
  const toggle = (k) => setForm({ ...form, kinds: form.kinds.includes(k) ? form.kinds.filter((x) => x !== k) : [...form.kinds, k] });
  return (
    <div className="merge-step">
      <h3>Webhooks</h3>
      <p className="quiet">Every notification of the chosen kinds is sent to these addresses as signed JSON (HMAC-SHA256 of
        the body with the webhook&apos;s secret, in the X-EAX-Signature header), retried for about two hours when the
        receiver fails. For chat channels and other systems; EA Explorer never sends email.</p>
      <div className="table-scroll">
        <table className="grid-table">
          <thead><tr><th>Name</th><th>Address</th><th>Kinds</th><th>Secret</th><th>Delivered</th><th /></tr></thead>
          <tbody>
            {data.webhooks.map((w) => (
              <tr key={w.id} className={w.enabled ? "" : "quiet"}>
                <td>{w.name}{!w.enabled && " (off)"}</td>
                <td className="small"><code>{w.url}</code></td>
                <td className="small">{w.kinds.length ? w.kinds.map((k) => CATEGORY[k]).join(", ") : "every kind"}</td>
                <td className="small"><code>{w.secret}</code></td>
                <td className="small">{w.sent} sent{w.pending ? `, ${w.pending} waiting` : ""}{w.failed ? <span className="status bad">, {w.failed} failed</span> : ""}
                  {w.last_sent_at && <div className="quiet">last {fmtDateTime(w.last_sent_at)}</div>}</td>
                <td className="nowrap small">
                  <button className="linkish" onClick={() => call(() => apiFetch(`/api/v1/admin/webhooks/${w.id}/test`, { method: "POST" }))}>Send test</button>{" · "}
                  <button className="linkish" onClick={async () => setLog({ w, rows: (await apiFetch(`/api/v1/admin/webhooks/${w.id}/deliveries`)).deliveries })}>Log</button>{" · "}
                  <button className="linkish" onClick={() => call(() => apiFetch(`/api/v1/admin/webhooks/${w.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !w.enabled }) }))}>{w.enabled ? "Switch off" : "Switch on"}</button>{" · "}
                  <button className="linkish" onClick={() => call(() => apiFetch(`/api/v1/admin/webhooks/${w.id}`, { method: "PATCH", body: JSON.stringify({ new_secret: true }) }))}>New secret</button>{" · "}
                  <button className="linkish" onClick={() => {
                    // eslint-disable-next-line no-alert
                    if (window.confirm(`Delete the webhook ${w.name} and its delivery log?`)) call(() => apiFetch(`/api/v1/admin/webhooks/${w.id}`, { method: "DELETE" }));
                  }}>Delete</button>
                </td>
              </tr>
            ))}
            {!data.webhooks.length && <tr><td colSpan="6" className="quiet">No webhooks yet.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="row-gap webhook-form">
        <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="https://..." value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} style={{ minWidth: 320 }} />
        {data.kinds.map((k) => <label key={k} className="small"><input type="checkbox" checked={form.kinds.includes(k)} onChange={() => toggle(k)} /> {CATEGORY[k]}</label>)}
        <span className="quiet small">{form.kinds.length ? "" : "(none ticked: every kind)"}</span>
        <button className="primary" disabled={!form.name.trim() || !form.url.trim()} onClick={add}>Add webhook</button>
      </div>
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
      {log && (
        <Modal wide title={`Deliveries: ${log.w.name}`} onClose={() => setLog(null)} actions={<button onClick={() => setLog(null)}>Close</button>}>
          <div className="table-scroll">
            <table className="grid-table">
              <thead><tr><th>Made</th><th>Notification</th><th>Status</th><th>Tries</th><th>Answer</th></tr></thead>
              <tbody>
                {log.rows.map((d) => (
                  <tr key={d.id}><td className="small">{fmtDateTime(d.created_at)}</td><td className="small">{d.title}</td>
                    <td>{d.status}</td><td>{d.attempts}</td><td className="small">{d.last_status || ""} {d.last_error}</td></tr>
                ))}
                {!log.rows.length && <tr><td colSpan="5" className="quiet">Nothing sent yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
    </div>
  );
}
