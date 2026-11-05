// The top bar of background tasks (D192): running ones, and those just finished until dismissed (tasks.js follows them).
import { dismissTask, useTasks } from "./tasks";

export function TaskBar() {
  const list = useTasks();
  if (!list.length) return null;
  return (
    <div className="task-bar" role="status" aria-live="polite">
      {list.map((t) => (
        <div key={t.id} className={`task-item ${t.status}`}>
          {t.done ? (t.status === "done" ? "✓ " : "✗ ") : <span className="spinner" aria-hidden="true" />}
          <b>{t.label}</b>{" "}
          {t.done ? <span>{t.message}</span> : <span className="quiet">{t.status === "queued" ? "waiting to start..." : "working..."}</span>}
          {t.done && t.href && t.status === "done" && <> <a href={t.href} onClick={() => dismissTask(t.id)}>Open</a></>}
          {t.done && <button className="linkish" onClick={() => dismissTask(t.id)} aria-label="Dismiss">✕</button>}
        </div>
      ))}
    </div>
  );
}
