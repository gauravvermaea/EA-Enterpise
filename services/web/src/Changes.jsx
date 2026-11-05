// The Changes tab of a model (build phase 8, D165, D151): uncommitted changes, commit requests, commit history,
// merging another model in, and the live "someone committed" banner (E37).
//   #/metamodel/<model>/changes[/requests|/history|/history/<commit>]
// Content changes in a project model are private to their author until committed. Every screen that changes
// content (data entry, grids, the entity page, merges, and later the draw.io diagrams of phases 28-29 through
// POST /models/<m>/changes/batch) records them here; only committed content reaches history, reports, graphs and MCP.
import { useEffect, useState } from "react";
import { apiFetch, currentUser } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";

const go = (path) => { window.location.hash = path; };
const post = (path, body) => apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });
const me = () => (currentUser()?.preferred_username || "").toLowerCase();
const when = (t) => (t ? fmtDateTime(t) : "");
const show = (v) => (v === null || v === undefined || v === "" ? <span className="quiet">(empty)</span>
  : Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : String(v));

// A link to the entity a change or commit item is about (a relationship: its source entity)
export function EntityLink({ model, id, deleted, label = "Open entity ↗" }) {
  if (!id) return null;
  return <a className="entity-link small" href={`#/metamodel/${model}/entity/${id}`} target="_blank" rel="noreferrer"
    title={deleted ? "The entity is deleted (its page shows its history)" : "Open the entity page in a new tab"}>{label}</a>;
}

const SET_STATUS = {
  open: "Not yet asked for a commit",
  requested: "Commit requested: waiting for a committer",
  returned: "Sent back to you",
};

// The number of my uncommitted changes, for the tab label
export function usePendingCount(model, m) {
  const { data } = useApi(m && m.kind === "project" ? `/api/v1/models/${model}/changes` : null);
  return data ? data.pending_count + (data.may_commit ? data.requests.reduce((n, s) => n + s.changes.length, 0) : 0) : 0;
}

export default function ChangesTab({ model, m, sub, itemId }) {
  const { data: page, error } = useApi(`/api/v1/models/${model}/changes`);
  const view = sub || "mine";
  if (error) return <p className="status bad">{error}</p>;
  if (!page) return <p>Loading...</p>;
  const reqCount = page.requests.reduce((n, s) => n + s.changes.length, 0);
  return (
    <div className="changes">
      {!page.uses_commits ? (
        <p className="quiet">
          {m.name} is not a project model: its changes apply at once and are not committed. Commits are for the content
          of project models (D165).
        </p>
      ) : (
        <p className="quiet">
          Your changes to {m.name} are yours alone until they are committed: only committed content reaches history,
          reports, graphs and MCP. {page.may_commit
            ? "You may commit (Committer, Model Sub Admin or Model Admin): your own changes, and those others ask you to commit."
            : "Ask for a commit when they are ready: the model's committers see them then."}
        </p>
      )}
      <div className="toolbar">
        <div className="seg small" role="tablist">
          <button className={view === "mine" ? "on" : ""} onClick={() => go(`/metamodel/${model}/changes`)}>
            My uncommitted changes ({page.pending_count})</button>
          {page.may_commit && <button className={view === "requests" ? "on" : ""} onClick={() => go(`/metamodel/${model}/changes/requests`)}>
            Waiting for a commit ({reqCount})</button>}
          <button className={view === "history" ? "on" : ""} onClick={() => go(`/metamodel/${model}/changes/history`)}>Commits</button>
        </div>
      </div>
      {view === "requests" && page.may_commit ? <Requests model={model} page={page} />
        : view === "history" ? <History model={model} open={itemId} />
        : <Mine model={model} page={page} />}
    </div>
  );
}

// ---------------------------------------------------------------- one change set, with chosen rows
function ChangeRows({ model, changes, chosen, setChosen, showConflicts }) {
  const all = changes.every((c) => chosen.has(c.id));
  const flip = (id) => setChosen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  return (
    <table className="grid-table changes-table">
      <thead>
        <tr>
          <th><input type="checkbox" checked={all} aria-label="Choose all"
            onChange={() => setChosen(all ? new Set() : new Set(changes.map((c) => c.id)))} /></th>
          <th>Change</th><th>What changes</th><th>Made</th>
        </tr>
      </thead>
      <tbody>
        {changes.map((c) => (
          <tr key={c.id} className={c.conflict ? "row-conflict" : ""}>
            <td><input type="checkbox" checked={chosen.has(c.id)} onChange={() => flip(c.id)} aria-label={c.label} /></td>
            <td>
              <strong>{c.label}</strong> <EntityLink model={model} id={c.entity} deleted={c.op === "entity.delete"} />
              {c.source && <span className="source-chip" title="Where this change came from">{c.source}</span>}
              {showConflicts && c.conflict && <div className="status bad small">⚠ {c.conflict.message}</div>}
              <RuleWarnings list={c.warnings} />
            </td>
            <td className="small">
              {c.rows.length ? c.rows.map((r) => (
                <div key={r.code}><span className="quiet">{r.field}:</span> {r.before !== null && r.before !== undefined
                  ? <><s>{show(r.before)}</s> → </> : null}{show(r.after)}</div>
              )) : <span className="quiet">{c.op.replace(".", " ")}</span>}
            </td>
            <td className="quiet small">{when(c.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// The rules a change leaves its entity failing (D48: saved and committed anyway, flagged until fixed)
export function RuleWarnings({ list, title }) {
  if (!list?.length) return null;
  const errors = list.filter((w) => w.severity === "error").length;
  return (
    <div className="rule-fails small">
      <span className={`sev ${errors ? "error" : "warning"}`}>⚠ {title || `fails ${list.length} rule${list.length === 1 ? "" : "s"}`}</span>
      <ul>{list.map((w, i) => <li key={i}>{w.field ? <b>{w.field}: </b> : null}{w.message}</li>)}</ul>
    </div>
  );
}

function useCommit(model, onDone) {
  const [conflicts, setConflicts] = useState(null);
  const [pending, setPending] = useState(null);   // what to send again once the conflicts are settled
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function commit(body) {
    setBusy(true); setError("");
    try {
      const out = await post(`/api/v1/models/${model}/changes/commit`, body);
      setConflicts(null); setPending(null); refreshAll(); onDone?.(out);
    } catch (e) {
      const list = e.body?.errors?.conflicts;
      if (e.status === 409 && list) { setConflicts(list); setPending(body); } else setError(e.message);
    }
    setBusy(false);
  }
  const dialog = conflicts && (
    <ConflictDialog model={model} conflicts={conflicts} onClose={() => setConflicts(null)}
      onResolve={(resolutions) => commit({ ...pending, resolutions: { ...(pending.resolutions || {}), ...resolutions } })} />
  );
  return { commit, busy, error, dialog };
}

// ---------------------------------------------------------------- my uncommitted changes
function Mine({ model, page }) {
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const [info, setInfo] = useState("");
  const [err, setErr] = useState("");
  const { commit, busy, error, dialog } = useCommit(model, (o) => setInfo(`Committed as commit ${o.number}: ${o.committed} changes${o.skipped ? `, ${o.skipped} skipped` : ""}.`));
  async function step(path, body, done) {
    setErr(""); setInfo("");
    try { await post(`/api/v1/models/${model}/changes/${path}`, body); refreshAll(); setInfo(done); } catch (e) { setErr(e.message); }
  }
  return (
    <div>
      {info && <p className="status ok">{info}</p>}
      {(err || error) && <p className="status bad">{err || error}</p>}
      {!page.mine.length && <p className="quiet">You have no uncommitted changes in this model.</p>}
      {page.mine.map((s) => (
        <MySet key={s.id} model={model} s={s} page={page} busy={busy} note={note} setNote={setNote} message={message} setMessage={setMessage}
          commit={commit} step={step} />
      ))}
      {dialog}
      {page.decided?.length > 0 && (
        <details className="decided">
          <summary>Decided in the last 30 days ({page.decided.length})</summary>
          <table className="grid-table">
            <thead><tr><th>Change</th><th>Decision</th><th>By</th><th>When</th></tr></thead>
            <tbody>
              {page.decided.map((d) => (
                <tr key={d.id}>
                  <td>{d.label}</td>
                  <td>{d.status === "committed" ? <>Committed{d.commit ? ` (commit ${d.commit})` : ""}</>
                    : <span className="status bad">Rejected{d.note ? `: ${d.note}` : ""}</span>}</td>
                  <td>{d.decided_by}</td><td className="quiet">{when(d.decided_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

function MySet({ model, s, page, busy, note, setNote, message, setMessage, commit, step }) {
  const [chosen, setChosen] = useState(() => new Set(s.changes.map((c) => c.id)));
  const ids = s.changes.filter((c) => chosen.has(c.id)).map((c) => c.id);
  const some = ids.length > 0;
  const partial = ids.length < s.changes.length ? ids : null;
  return (
    <div className="change-set">
      <h3>{SET_STATUS[s.status] || s.status} · {s.changes.length} change{s.changes.length === 1 ? "" : "s"}</h3>
      {s.status === "returned" && s.reply_note && <p className="status bad">Sent back by {s.replied_by}: {s.reply_note}</p>}
      {s.status === "requested" && s.request_note && <p className="quiet">Your note: {s.request_note}</p>}
      <ChangeRows model={model} changes={s.changes} chosen={chosen} setChosen={setChosen} />
      <div className="toolbar">
        {page.may_commit && <>
          <input placeholder="Commit message (optional)" value={message} onChange={(e) => setMessage(e.target.value)} style={{ minWidth: 240 }} />
          <button className="primary" disabled={busy || !some} onClick={() => commit({ set: s.id, changes: partial, message })}>
            {partial ? `Commit the ${ids.length} chosen` : "Commit all"}</button>
        </>}
        {s.status !== "requested" ? <>
          <input placeholder="A note for the committers (optional)" value={note} onChange={(e) => setNote(e.target.value)} style={{ minWidth: 240 }} />
          <button className={page.may_commit ? "" : "primary"} disabled={busy}
            onClick={() => step("request", { set: s.id, note }, "Asked for a commit: the model's committers see your changes now.")}>
            Ask for a commit</button>
        </> : <button disabled={busy} onClick={() => step("withdraw", { set: s.id }, "Request withdrawn: the changes stay yours, uncommitted.")}>
          Withdraw the request</button>}
        <button className="danger" disabled={busy || !some} onClick={() => {
          // eslint-disable-next-line no-alert
          if (window.confirm(`Discard ${partial ? `the ${ids.length} chosen changes` : "all these changes"}? They are gone for good.`)) {
            step("discard", { set: s.id, changes: partial }, "Discarded.");
          }
        }}>{partial ? "Discard the chosen" : "Discard all"}</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- requests (committers)
function Requests({ model, page }) {
  const [info, setInfo] = useState("");
  const { commit, busy, error, dialog } = useCommit(model, (o) => setInfo(`Committed as commit ${o.number}: ${o.committed} changes${o.skipped ? `, ${o.skipped} skipped` : ""}.`));
  return (
    <div>
      {info && <p className="status ok">{info}</p>}
      {error && <p className="status bad">{error}</p>}
      {!page.requests.length && <p className="quiet">Nobody is waiting for a commit in this model.</p>}
      {page.requests.map((s) => <RequestSet key={s.id} model={model} s={s} busy={busy} commit={commit} setInfo={setInfo} />)}
      {dialog}
    </div>
  );
}

function RequestSet({ model, s, busy, commit, setInfo }) {
  const [chosen, setChosen] = useState(() => new Set(s.changes.map((c) => c.id)));
  const [message, setMessage] = useState("");
  const [ask, setAsk] = useState(null);   // "reject" | "send-back"
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const ids = s.changes.filter((c) => chosen.has(c.id)).map((c) => c.id);
  const partial = ids.length < s.changes.length ? ids : null;
  const clashes = s.changes.filter((c) => c.conflict).length;
  async function decide() {
    setErr("");
    try {
      await post(`/api/v1/models/${model}/changes/${ask}`, { set: s.id, changes: ask === "reject" ? partial : null, note });
      setInfo(ask === "reject" ? "Rejected: the author sees why." : "Sent back to the author with your note.");
      setAsk(null); setNote(""); refreshAll();
    } catch (e) { setErr(e.message); }
  }
  return (
    <div className="change-set">
      <h3>{s.author} · {s.changes.length} change{s.changes.length === 1 ? "" : "s"} · asked {when(s.requested_at)}</h3>
      {s.request_note && <p>“{s.request_note}”</p>}
      {clashes > 0 && <p className="status bad">⚠ {clashes} clash with content committed since: you choose how when you commit.</p>}
      {s.changes.some((c) => c.warnings?.length) && <p className="status bad small">⚠ {s.changes.filter((c) => c.warnings?.length).length} change(s) leave
        an entity failing rules (listed under each). Committing keeps them flagged until fixed; or send back to fix first.</p>}
      <ChangeRows model={model} changes={s.changes} chosen={chosen} setChosen={setChosen} showConflicts />
      <div className="toolbar">
        <input placeholder="Commit message (optional)" value={message} onChange={(e) => setMessage(e.target.value)} style={{ minWidth: 240 }} />
        <button className="primary" disabled={busy || !ids.length} onClick={() => commit({ set: s.id, changes: partial, message })}>
          {partial ? `Commit the ${ids.length} chosen` : "Commit all"}</button>
        <button disabled={busy || !ids.length} className="danger" onClick={() => setAsk("reject")}>
          {partial ? "Reject the chosen..." : "Reject all..."}</button>
        <button disabled={busy} onClick={() => setAsk("send-back")}>Send back...</button>
      </div>
      {err && <p className="status bad">{err}</p>}
      {ask && (
        <Modal title={ask === "reject" ? `Reject ${partial ? `${ids.length} changes` : "these changes"} of ${s.author}` : `Send back to ${s.author}`}
          onClose={() => setAsk(null)}
          actions={<><button onClick={() => setAsk(null)}>Cancel</button>
            <button className="danger" disabled={ask === "send-back" && !note.trim()} onClick={decide}>
              {ask === "reject" ? "Reject" : "Send back"}</button></>}>
          <div className="ed-form">
            <label className="ed-field"><span>{ask === "reject" ? "Why (the author sees it)" : "What to change"}</span>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} autoFocus /></label>
            {err && <p className="status bad">{err}</p>}
          </div>
        </Modal>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- conflicts at commit
function ConflictDialog({ model, conflicts, onResolve, onClose }) {
  // decisions: change id -> "skip" | "mine" | {fields: {code: "mine" | "theirs" | {value}}}
  const [d, setD] = useState({});
  const setField = (c, code, how) => setD((x) => ({ ...x, [c.change]: { fields: { ...((x[c.change] || {}).fields || {}), [code]: how } } }));
  const fieldOf = (c, code) => ((d[c.change] || {}).fields || {})[code];
  function all(how) {
    const out = {};
    for (const c of conflicts) {
      if (c.kind === "fields") out[c.change] = how === "mine" ? "mine" : { fields: Object.fromEntries(c.fields.map((f) => [f.code, "theirs"])) };
      else out[c.change] = how === "mine" && c.choices.includes("mine") ? "mine" : "skip";
    }
    setD(out);
  }
  const settled = conflicts.every((c) => {
    const x = d[c.change];
    if (x === "mine" || x === "skip") return true;
    return c.kind === "fields" && c.fields.every((f) => (x?.fields || {})[f.code] !== undefined);
  });
  return (
    <Modal wide title={`${conflicts.length} change${conflicts.length === 1 ? "" : "s"} clash with content committed since`} onClose={onClose}
      actions={<>
        <button onClick={() => all("mine")}>All mine</button>
        <button onClick={() => all("theirs")}>All theirs</button>
        <span style={{ flex: 1 }} />
        <button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={!settled} onClick={() => onResolve(d)}>Commit with these choices</button>
      </>}>
      <p className="quiet">Mine: the change as it was made. Theirs: keep what was committed since. Skip: leave the change out.</p>
      {conflicts.map((c) => (
        <div key={c.change} className="change-set">
          <h3>{c.label} <span className="quiet">({c.author})</span> <EntityLink model={model} id={c.entity} />
            {c.source && <span className="source-chip">{c.source}</span>}</h3>
          <p className="small">{c.message}</p>
          {c.kind === "fields" ? (
            <table className="grid-table">
              <thead><tr><th>Field</th><th>Was</th><th>Theirs (committed since)</th><th>Mine</th><th>Keep</th></tr></thead>
              <tbody>
                {c.fields.map((f) => {
                  const v = fieldOf(c, f.code);
                  const own = v && typeof v === "object";
                  return (
                    <tr key={f.code}>
                      <td>{f.field}</td><td className="quiet">{show(f.base)}</td><td>{show(f.theirs)}</td><td>{show(f.mine)}</td>
                      <td className="small">
                        <label><input type="radio" checked={v === "mine" || d[c.change] === "mine"} onChange={() => setField(c, f.code, "mine")} /> mine</label>{" "}
                        <label><input type="radio" checked={v === "theirs"} onChange={() => setField(c, f.code, "theirs")} /> theirs</label>{" "}
                        <label><input type="radio" checked={own} onChange={() => setField(c, f.code, { value: f.mine ?? "" })} /> another value</label>
                        {own && <input value={v.value ?? ""} onChange={(e) => setField(c, f.code, { value: e.target.value })} style={{ width: 160 }} />}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <>
              {(c.fields || []).length > 0 && <ul className="small">{c.fields.map((f) => <li key={f.code}>{f.field}: {show(f.base)} → {show(f.theirs)}</li>)}</ul>}
              {c.choices.map((ch) => (
                <label key={ch} style={{ marginRight: 12 }}><input type="radio" checked={d[c.change] === ch}
                  onChange={() => setD((x) => ({ ...x, [c.change]: ch }))} /> {ch === "mine" ? "Mine anyway" : "Skip this change"}</label>
              ))}
            </>
          )}
        </div>
      ))}
    </Modal>
  );
}

// ---------------------------------------------------------------- commit history (D151)
function History({ model, open }) {
  const [person, setPerson] = useState("");
  const { data, error } = useApi(`/api/v1/models/${model}/commits${person ? `?person=${encodeURIComponent(person)}` : ""}`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  return (
    <div>
      <div className="toolbar">
        <span className="quiet">{data.everyone ? "Every commit of this model (History Viewer or Model Admin)." : "Your commits: those you made or committed. Everyone's need the History Viewer role (D151)."}</span>
        {data.everyone && (
          <select value={person} onChange={(e) => setPerson(e.target.value)}>
            <option value="">Everyone</option>
            {data.people.map((p) => <option key={p} value={p}>{p}{p === me() ? " (me)" : ""}</option>)}
          </select>
        )}
        {data.everyone && <button className="linkish" onClick={() => setPerson(me())}>My changes</button>}
      </div>
      <table className="grid-table">
        <thead><tr><th>#</th><th>Message</th><th>Committed by</th><th>Changes by</th><th>Items</th><th>When</th></tr></thead>
        <tbody>
          {data.commits.map((c) => (
            <tr key={c.id} className={open === c.id ? "on" : ""}>
              <td><a href={`#/metamodel/${model}/changes/history/${c.id}`}>{c.number}</a></td>
              <td>{c.kind === "rollback" && <span className="rchip">roll back of {c.rolls_back}</span>} {c.message}</td>
              <td>{c.committed_by}</td><td>{(c.authors || []).join(", ")}</td>
              <td className="num">{c.items}{c.rolled_back > 0 && <span className="quiet"> ({c.rolled_back} rolled back)</span>}</td>
              <td className="quiet">{when(c.committed_at)}</td>
            </tr>
          ))}
          {!data.commits.length && <tr><td colSpan="6" className="quiet">No commits yet.</td></tr>}
        </tbody>
      </table>
      {open && <CommitDetail key={open} model={model} id={open} />}
    </div>
  );
}

function CommitDetail({ model, id }) {
  const { data: c, error } = useApi(`/api/v1/models/${model}/commits/${id}`);
  const [chosen, setChosen] = useState(new Set());
  const [changed, setChanged] = useState(null);
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!c) return <p>Loading...</p>;
  const open = c.items.filter((i) => !i.rolled_back_by);
  async function rollBack(force) {
    setErr(""); setInfo("");
    try {
      const out = await post(`/api/v1/models/${model}/commits/${id}/roll-back`, { items: chosen.size ? [...chosen] : null, force });
      setChanged(null); setChosen(new Set()); setInfo(`Rolled back as commit ${out.number}.`); refreshAll();
    } catch (e) {
      if (e.status === 409 && e.body?.errors?.conflicts) setChanged(e.body.errors.conflicts); else setErr(e.message);
    }
  }
  return (
    <div className="change-set">
      <h3>Commit {c.number}: {c.message} <span className="quiet">· {c.committed_by} · {when(c.committed_at)}</span></h3>
      {c.rolls_back && <p className="quiet">Rolls back commit {c.rolls_back}.</p>}
      <table className="grid-table">
        <thead><tr><th />{/* choose */}<th>Item</th><th>By</th><th>What changed</th></tr></thead>
        <tbody>
          {c.items.map((i) => (
            <tr key={i.id}>
              <td>{!i.rolled_back_by && c.may_roll_back && <input type="checkbox" checked={chosen.has(i.id)} aria-label={i.label}
                onChange={() => setChosen((s) => { const n = new Set(s); if (n.has(i.id)) n.delete(i.id); else n.add(i.id); return n; })} />}</td>
              <td>{i.label} <EntityLink model={model} id={i.entity} deleted={i.entity_deleted} />
                {i.rolled_back_by && <span className="rchip">rolled back in {i.rolled_back_by}</span>}</td>
              <td>{i.author}</td>
              <td className="small">{!i.changes.length && <span className="quiet">No change: what was committed before was kept</span>}{i.changes.map((x, k) => (
                <div key={k}><span className="quiet">{x.field}:</span> {x.before !== null && x.before !== undefined ? <><s>{show(x.before)}</s> → </> : null}{show(x.after)}</div>
              ))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {c.may_roll_back && open.length > 0 && (
        <div className="toolbar">
          <button className="danger" onClick={() => rollBack(false)}>{chosen.size ? `Roll back the ${chosen.size} chosen` : "Roll back the whole commit"}</button>
          <span className="quiet small">A roll back is a new commit: each item goes back to how it was before this commit.</span>
        </div>
      )}
      {info && <p className="status ok">{info}</p>}
      {err && <p className="status bad">{err}</p>}
      {changed && (
        <Modal title="Changed since this commit" onClose={() => setChanged(null)}
          actions={<><button onClick={() => setChanged(null)}>Cancel</button><button className="danger" onClick={() => rollBack(true)}>Roll back anyway</button></>}>
          <p>These were changed by later commits. Rolling back puts them back as they were before commit {c.number}, undoing the later changes too.</p>
          <ul>{changed.map((x) => <li key={x.item}><strong>{x.label}</strong>{(x.fields || []).length > 0 && `: ${x.fields.map((f) => f.field).join(", ")}`}</li>)}</ul>
        </Modal>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- live updates (E37)
// Polls the model's last commit; when someone else commits, offers to reload what is on the page.
export function LiveCommits({ model, m }) {
  const [seen, setSeen] = useState(null);
  const [news, setNews] = useState(null);
  useEffect(() => {
    if (!m || m.kind !== "project") return undefined;
    let live = true;
    let first = null;
    const look = () => apiFetch(`/api/v1/models/${model}/commits/latest`).then((c) => {
      if (!live) return;
      if (first === null) { first = c.number; setSeen(c.number); return; }
      if (c.number > first && (c.committed_by || "") !== me()) setNews(c);
    }).catch(() => {});
    look();
    const t = setInterval(look, 20000);
    return () => { live = false; clearInterval(t); };
  }, [model, m?.kind, seen]);
  if (!news) return null;
  return (
    <div className="lock-banner live-banner">
      {news.committed_by} committed changes (commit {news.number}{news.message ? `: ${news.message}` : ""}).{" "}
      <button className="primary" onClick={() => { setNews(null); setSeen(news.number); refreshAll(); }}>Reload</button>{" "}
      <button className="linkish" onClick={() => { setNews(null); setSeen(news.number); }}>Later</button>
    </div>
  );
}

// ---------------------------------------------------------------- one entity's uncommitted changes (the entity page and its edit form)
// What I changed in this entity and its relationships, field by field, so pages can highlight it; committed from there too.
export function useEntityChanges(model, m, entityId) {
  const { data } = useApi(m?.kind === "project" && entityId ? `/api/v1/models/${model}/changes?entity=${entityId}` : null);
  const mine = (data?.mine || []).flatMap((s) => s.changes);
  const fields = {};   // field code (lower case) -> {before: committed value, after: my value}
  for (const c of mine) {
    for (const r of c.rows) {
      const k = String(r.code).toLowerCase();
      fields[k] = { before: fields[k] ? fields[k].before : r.before, after: r.after, created: c.op === "entity.create" };
    }
  }
  const others = (data?.requests || []).flatMap((s) => s.changes);
  return { data, mine, fields, others, mayCommit: !!data?.may_commit };
}

// The committed value under a field I changed (the entity page and the edit form)
export function WasValue({ f }) {
  if (!f) return null;
  return (
    <span className="was-value" title="Your uncommitted change: nobody else sees it until it is committed">
      ✎ {f.created ? "new, uncommitted" : <>was <s>{show(f.before)}</s>, uncommitted</>}
    </span>
  );
}

export function EntityChanges({ model, entity, ec, compact }) {
  const fails = (entity.warnings || []).map((w) => ({ field: w.field || w.code, message: w.message, severity: w.severity }));
  const [note, setNote] = useState("");
  const [info, setInfo] = useState("");
  const [err, setErr] = useState("");
  const { commit, busy, error, dialog } = useCommit(model, (o) => setInfo(`Committed as commit ${o.number}.`));
  if (!ec.mine.length && !ec.others.length) return info ? <p className="status ok">{info}</p> : null;
  const ids = ec.mine.map((c) => c.id);
  const requested = ec.mine.length > 0 && (ec.data.mine || []).filter((s) => s.changes.length).every((s) => s.status === "requested");
  async function step(path, body, done) {
    setErr(""); setInfo("");
    try { await post(`/api/v1/models/${model}/changes/${path}`, body); refreshAll(); setInfo(done); } catch (e) { setErr(e.message); }
  }
  return (
    <div className="lock-banner pending-banner entity-changes">
      {ec.mine.length > 0 && <>
        <strong>Your uncommitted changes to {entity.name} ({ec.mine.length})</strong>
        {requested ? <span className="quiet"> · commit requested</span> : null}
        {!compact && (
          <ul className="small">
            {ec.mine.map((c) => (
              <li key={c.id}>{c.label}{c.source && <span className="source-chip">{c.source}</span>}{c.rows.length > 0 && <span className="quiet"> · {c.rows.map((r) => r.field).join(", ")}</span>}</li>
            ))}
          </ul>
        )}
        <RuleWarnings list={fails} title={`With your changes ${entity.name} fails ${fails.length} rule${fails.length === 1 ? "" : "s"}: it can still be committed, flagged until fixed`} />
        <div className="toolbar">
          {ec.mayCommit && <button className="primary" disabled={busy} onClick={() => commit({ changes: ids, message: `${entity.name}` })}>
            Commit {ec.mine.length === 1 ? "it" : `these ${ec.mine.length}`}</button>}
          {!requested && <>
            <input placeholder="A note for the committers (optional)" value={note} onChange={(e) => setNote(e.target.value)} style={{ minWidth: 220 }} />
            <button className={ec.mayCommit ? "" : "primary"} disabled={busy}
              onClick={() => step("request", { changes: ids, note }, "Asked for a commit of these changes.")}>Ask for a commit</button>
          </>}
          <button className="danger" disabled={busy} onClick={() => {
            // eslint-disable-next-line no-alert
            if (window.confirm(`Discard your ${ec.mine.length} uncommitted change(s) to ${entity.name}?`)) step("discard", { changes: ids }, "Discarded.");
          }}>Discard</button>
          <a href={`#/metamodel/${model}/changes`}>All my changes</a>
        </div>
      </>}
      {ec.others.length > 0 && (
        <p className="small">{ec.others.length} change{ec.others.length === 1 ? "" : "s"} by others to {entity.name} wait for a commit:{" "}
          <a href={`#/metamodel/${model}/changes/requests`}>Waiting for a commit</a>.</p>
      )}
      {info && <p className="status ok">{info}</p>}
      {(err || error) && <p className="status bad">{err || error}</p>}
      {dialog}
    </div>
  );
}
