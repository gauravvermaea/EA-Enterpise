// Watching a self-test as it happens (R3.2; owner, 13 Nov 2026: "When running test can we have the name of test being
// executed with what it is testing. There should also be a window where someone can watch what is happening"; decided:
// it watches and can Stop the whole run, no per-step controls). Self-test › a run going on › Watch, and
// `eax test watch` in a terminal. Every two seconds it asks GET /api/v1/admin/tests/<run>/live for what is new: the step
// running now (what it checks), the counts and how many are left, each check as it is recorded, every failure with its
// reason, and the run's log lines.
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "./auth";
import { Modal } from "./ModelOps";

const KEEP = 400;          // the newest checks and log lines kept on screen

export function mergeLive(prev, s) {
  return {
    snap: s,
    results: [...prev.results, ...(s.results || [])].slice(-KEEP),
    log: (prev.log + (s.log || "")).split("\n").slice(-KEEP).join("\n"),
    after: s.after ?? prev.after,
    from: s.log_next ?? prev.from,
  };
}

export default function TestWatch({ runId, onClose }) {
  const [st, setSt] = useState({ snap: null, results: [], log: "", after: 0, from: 0 });
  const [err, setErr] = useState("");
  const [ask, setAsk] = useState(false);
  const [msg, setMsg] = useState("");
  const [follow, setFollow] = useState(true);
  const pos = useRef({ after: 0, from: 0 });
  const logEnd = useRef(null);
  useEffect(() => {
    let alive = true, timer;
    const tick = async () => {
      try {
        const s = await apiFetch(`/api/v1/admin/tests/${runId}/live?after=${pos.current.after}&from=${pos.current.from}`);
        if (!alive) return;
        pos.current = { after: s.after, from: s.log_next };
        setSt((prev) => mergeLive(prev, s));
        setErr("");
        if (s.open) timer = setTimeout(tick, 2000);
      } catch (e) { if (alive) { setErr(e.message); timer = setTimeout(tick, 5000); } }
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [runId]);
  useEffect(() => { if (follow) logEnd.current?.scrollIntoView?.({ block: "end" }); }, [st.log, st.results.length, follow]);
  const s = st.snap, r = s?.run, t = s?.tally || {}, p = s?.progress || {};
  const stop = async () => {
    try { const x = await apiFetch(`/api/v1/admin/tests/${runId}/stop`, { method: "POST" }); setMsg(x.message); } catch (e) { setMsg(e.message); }
    setAsk(false);
  };
  return (
    <Modal wide title={`Watching self-test ${runId}${r ? `: ${r.state}` : ""}`} onClose={onClose}
      actions={<>{s?.open && <button onClick={() => setAsk(true)} disabled={!!r?.stop_asked}>Stop the run</button>}
        <button onClick={onClose}>Close</button></>}>
      {err && <p className="status bad">{err}</p>}
      {!s && !err && <p>Loading…</p>}
      {s && <div className="test-watch" aria-live="polite">
        <p className="test-watch-step">{s.open && <span className="spinner" aria-hidden="true" />}{" "}
          <b>{r.stop_asked ? `Stopping (asked by ${r.stop_asked})…` : r.step || (s.open ? "Starting…" : "Finished")}</b></p>
        <p className="small"><b className="ok-text">{t.passed || 0}</b> passed · <b className={t.failed ? "bad-text" : ""}>{t.failed || 0}</b> failed ·
          {" "}{t.warning || 0} warnings · {t.skipped || 0} skipped{p.total ? ` · about ${p.left} of ${p.total} left` : ""}{msg ? ` · ${msg}` : ""}</p>
        {s.failures?.length > 0 && <details open className="test-watch-failures">
          <summary className="bad-text">Failures so far ({s.failures.length})</summary>
          {s.failures.map((x) => <p key={x.id} className="small"><b>{x.suite} · {x.name}</b>: {x.detail}</p>)}</details>}
        <div className="test-watch-panes">
          <div className="test-watch-checks">
            <h4>Checks as they are recorded</h4>
            <ol className="small">{st.results.map((x) => (
              <li key={x.id} className={`outcome-${x.outcome}`}><span className={`rag ${x.outcome === "passed" ? "ok" : x.outcome === "failed" ? "bad" : "warn"}`}>{x.outcome}</span>
                {" "}{x.suite} · {x.name}{x.outcome !== "passed" && x.detail ? `: ${x.detail}` : ""} <span className="quiet">{x.duration_ms} ms</span></li>))}</ol>
          </div>
          <div className="test-watch-log">
            <h4>Log <label className="small quiet"><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow</label></h4>
            <pre className="small">{st.log || "No log lines yet."}<span ref={logEnd} /></pre>
          </div>
        </div>
        <p className="quiet small">The same in a terminal: <code>eax test watch {runId}</code> (and <code>eax test stop {runId}</code>).</p>
      </div>}
      {ask && <Modal title={`Stop self-test ${runId}?`} onClose={() => setAsk(false)}
        actions={<><button onClick={() => setAsk(false)}>Keep running</button><button className="primary" onClick={stop}>Stop it</button></>}>
        <p>It ends at its next step and keeps what it has found so far.</p></Modal>}
    </Modal>
  );
}
