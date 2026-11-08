// The task drawer (D273): a slim tab on the right edge of every page, with how many tasks are running; it opens into
// the list of your background tasks with their progress, and when one ends it says completed or failed, with the
// link back to the screen that asked and the file it made (kept 24 hours). tasks.js follows them.
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "./auth";
import { fmtDateTime } from "./fmt";
import { clearFinished, dismissTask, downloadTaskFile, useAllTasks, useTasks } from "./tasks";

function Bar({ t }) {
  if (t.done) return null;
  const known = typeof t.progress === "number";
  return (
    <div className={`task-progress${known ? "" : " unknown"}`} role="progressbar" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={known ? t.progress : undefined} aria-label={t.label}>
      <span style={known ? { width: `${Math.max(3, t.progress)}%` } : undefined} />
    </div>
  );
}

export function TaskRow({ t, onOpen, hideDismiss = false }) {
  const state = !t.done ? (t.status === "queued" ? "Waiting to start" : "Running") : t.status === "done" ? "Completed" : "Failed";
  return (
    <li className={`task-row ${t.done ? t.status : "running"}`}>
      <div className="task-head">
        <span className="task-icon" aria-hidden="true">{!t.done ? <span className="spinner" /> : t.status === "done" ? "✓" : "✗"}</span>
        <b className="task-label">{t.label}</b>
        {t.done && !hideDismiss && <button className="linkish task-x" onClick={() => dismissTask(t.id)} aria-label={`Dismiss ${t.label}`} title="Dismiss">✕</button>}
      </div>
      <Bar t={t} />
      <div className="task-state quiet small">
        {state}{!t.done && t.progress_note ? `: ${t.progress_note}` : ""}
        {!t.done && typeof t.progress === "number" ? ` (${t.progress}%)` : ""}
        {t.done && t.finished_at ? ` · ${fmtDateTime(t.finished_at)}` : ""}
      </div>
      {t.done && t.message && <div className={`task-message small${t.status === "failed" ? " bad" : ""}`}>{t.message}</div>}
      {t.done && (
        <div className="task-actions small">
          {t.status === "done" && t.file && <button className="linkish" onClick={() => downloadTaskFile(t).catch(() => {})}>⬇ Download</button>}
          {t.href && <a href={t.href} onClick={onOpen}>Open</a>}
        </div>
      )}
    </li>
  );
}

const PIN = "eax-tasks-pinned";
const pinnedAtStart = () => { try { return localStorage.getItem(PIN) === "1"; } catch { return false; } };

// The task drawer: a permanent tab on the right of every page. "Now" lists what is running and what ended in the last
// 24 hours; "History" every task you ran, kept until you delete it. Pin it to keep it open beside the page.
export function TaskDrawer() {
  const list = useTasks();
  const [pinned, setPinned] = useState(pinnedAtStart);
  const [open, setOpen] = useState(pinnedAtStart);
  const [view, setView] = useState("now");
  const [unseen, setUnseen] = useState(0);
  const seen = useRef(new Set());
  const since = useRef(Date.now() - 5000);   // only tasks that end while this page is open light the tab
  const running = list.filter((t) => !t.done).length;
  useEffect(() => {    // a task that ends while the drawer is closed lights the tab
    const ended = list.filter((t) => t.done && !seen.current.has(t.id) && new Date(t.finished_at).getTime() > since.current);
    if (open) { ended.forEach((t) => seen.current.add(t.id)); setUnseen(0); }
    else if (ended.length) setUnseen(ended.length);
  }, [list, open]);
  useEffect(() => {
    const esc = (e) => { if (e.key === "Escape" && !pinned) setOpen(false); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [pinned]);
  useEffect(() => {    // pinned: the page makes room for the drawer instead of being covered
    document.body.classList.toggle("tasks-pinned", pinned && open);
    return () => document.body.classList.remove("tasks-pinned");
  }, [pinned, open]);
  function pin(on) {
    setPinned(on);
    if (on) setOpen(true);
    try { localStorage.setItem(PIN, on ? "1" : "0"); } catch { /* storage blocked: pinned until the page reloads */ }
  }
  const close = () => { setOpen(false); if (pinned) pin(false); };
  const leave = () => { if (!pinned) setOpen(false); };
  const title = running ? `${running} background task${running === 1 ? "" : "s"} running` : unseen ? `${unseen} finished` : "Background tasks";
  return (
    <>
      {!(open && pinned) && (
        <button className={`task-tab${running ? " busy" : ""}${unseen ? " news" : ""}`} onClick={() => setOpen(!open)}
          aria-expanded={open} aria-controls="task-drawer" title={title} aria-label={title}>
          <span className="task-tab-icon" aria-hidden="true">{running ? <span className="spinner" /> : unseen ? "✓" : "⏱"}</span>
          <span className="task-tab-text">Tasks</span>
          {(running > 0 || unseen > 0) && <span className="task-tab-count">{running || unseen}</span>}
        </button>
      )}
      {open && (
        <aside id="task-drawer" className={`task-drawer${pinned ? " pinned" : ""}`} aria-label="Background tasks">
          <header>
            <h2>Background tasks</h2>
            <span className="row-gap">
              <button className={`linkish task-pin${pinned ? " on" : ""}`} onClick={() => pin(!pinned)} aria-pressed={pinned}
                title={pinned ? "Unpin: the drawer closes when you click away" : "Pin: keep the drawer open beside the page"}>📌 {pinned ? "Pinned" : "Pin"}</button>
              <button className="linkish" onClick={close} aria-label="Close">✕</button>
            </span>
          </header>
          <div className="seg small task-views" role="tablist">
            <button role="tab" aria-selected={view === "now"} className={view === "now" ? "on" : ""} onClick={() => setView("now")}>
              Now{running ? ` (${running} running)` : ""}</button>
            <button role="tab" aria-selected={view === "history"} className={view === "history" ? "on" : ""} onClick={() => setView("history")}>History</button>
          </div>
          {view === "now" ? <>
            <p className="quiet small">They carry on when you leave the page. A file a task makes is kept 24 hours.
              {" "}<a href="#/notifications/tasks" onClick={leave}>All task notifications</a></p>
            {!list.length ? <p className="quiet">Nothing running and nothing finished in the last 24 hours. Earlier ones are in History.</p> : (
              <ul className="task-list">{list.map((t) => <TaskRow key={t.id} t={t} onOpen={leave} />)}</ul>
            )}
            {list.some((t) => t.done) && <p><button className="linkish small" onClick={clearFinished}>Clear the finished ones from Now</button>
              <span className="quiet small"> (they stay in History)</span></p>}
          </> : <TaskHistory onOpen={leave} />}
        </aside>
      )}
    </>
  );
}

// every task you ran, newest first, kept until you delete it
function TaskHistory({ onOpen }) {
  const [rows, setRows] = useState(null);
  const [total, setTotal] = useState(0);
  const [pick, setPick] = useState(() => new Set());
  const [msg, setMsg] = useState("");
  const [sure, setSure] = useState(false);
  const [filter, setFilter] = useState("");
  async function load(more = false) {
    try {
      const r = await apiFetch(`/api/v1/tasks?history=true&limit=50&offset=${more ? (rows || []).length : 0}`);
      setRows(more ? [...(rows || []), ...r.tasks] : r.tasks); setTotal(r.total);
    } catch (e) { setMsg(e.message); setRows([]); }
  }
  useEffect(() => { load(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  async function del(body) {
    setMsg("");
    try {
      const r = await apiFetch("/api/v1/tasks", { method: "DELETE", body: JSON.stringify(body) });
      setMsg(r.message); setPick(new Set()); setSure(false); load();
    } catch (e) { setMsg(e.message); }
  }
  if (!rows) return <p className="quiet">Loading…</p>;
  const shown = rows.filter((t) => !filter || `${t.label} ${t.message}`.toLowerCase().includes(filter.toLowerCase()));
  return (
    <div>
      <p className="quiet small">Every background task you ran, kept until you delete it. {total} in all.</p>
      <div className="toolbar">
        <input className="search" placeholder="Filter" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ maxWidth: 160 }} />
        <button disabled={!pick.size} onClick={() => del({ ids: [...pick] })}>Delete {pick.size || ""} ticked</button>
        {!sure ? <button className="linkish danger-text" disabled={!total} onClick={() => setSure(true)}>Delete all…</button>
          : <span className="small">Delete all {total}? <button className="danger" onClick={() => del({ all: true })}>Yes, delete</button>{" "}
            <button className="linkish" onClick={() => setSure(false)}>No</button></span>}
      </div>
      {msg && <p className="small">{msg}</p>}
      {!shown.length ? <p className="quiet">No finished tasks{filter ? " match" : " yet"}.</p> : (
        <ul className="task-list">{shown.map((t) => (
          <li key={t.id} className="task-hist">
            <input type="checkbox" aria-label={`Tick ${t.label}`} checked={pick.has(t.id)}
              onChange={() => setPick((s) => { const n = new Set(s); if (n.has(t.id)) n.delete(t.id); else n.add(t.id); return n; })} />
            <div style={{ flex: 1 }}><TaskRow t={{ ...t, href: t.link }} onOpen={onOpen} hideDismiss /></div>
          </li>))}</ul>
      )}
      {rows.length < total && <p><button className="linkish small" onClick={() => load(true)}>Show more ({total - rows.length} older)</button></p>}
    </div>
  );
}

// on a page that offers downloads: the files its background tasks made recently (24 hours), to download again
export function TaskFiles({ kinds, model, match }) {
  const list = useAllTasks().filter((t) => kinds.includes(t.kind) && (!model || t.model_id === model)
    && (!match || match(t)) && (!t.done || t.file || t.status === "failed")).slice(0, 5);
  if (!list.length) return null;
  return (
    <ul className="task-files small" aria-label="Files made in the background">
      {list.map((t) => (
        <li key={t.id}>
          {!t.done ? <><span className="spinner" aria-hidden="true" /> {t.label}: making it...</>
            : t.status === "failed" ? <span className="bad">✗ {t.label}: {t.message}</span>
            : <>✓ <button className="linkish" onClick={() => downloadTaskFile(t).catch(() => {})}>⬇ {t.file}</button>
              <span className="quiet"> ({fmtDateTime(t.finished_at)}, kept 24 hours)</span></>}
        </li>
      ))}
    </ul>
  );
}
