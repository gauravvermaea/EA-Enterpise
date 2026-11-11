// System admin › Self-test (phase 36.1, D367, D522 to D529): Super Admins and IT Admins test this installation, from here
// or with `eax test`: one runner, one results store, so a run started in either place shows in both.
//   Run           choose a smoke test or detailed tests (API, browser, database, security; one role, one area), start it
//                 now (it says how long and asks to confirm), follow it live, stop it. With "Watch it in this browser"
//                 the browser journeys run here, in a frame, in this browser (it is recorded with its name and version)
//   History       every run: its results with each failure explained (what was asked and what came back; a screenshot or
//                 video), its report (HTML or Excel) and its fixtures
//   Test fixtures every self_test_<id>_<n> model, project, account and credential of every run; tick and purge them
//                 (for good: type DELETE), as a background task with its progress
// Each run makes its own fixtures and tests only inside them; nothing else changes, and nothing is ever purged by itself.
// Health shows the last run in one line (LastSelfTest).
import { useEffect, useRef, useState } from "react";
import { apiBlobUrl, apiDownload, apiFetch, can } from "./auth";
import { Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";
import { trackTask } from "./tasks";

const SUITES = [
  ["api", "API", "every endpoint, with no token and as every role: allowed and refused, never a server error"],
  ["ui", "Browser", "the main journeys through the screens"],
  ["db", "Database", "read-only checks of the database"],
  ["security", "Security", "headers, cookies, the Python dependencies, an OWASP ZAP scan and Trivy image scans"],
];
const STATE = { queued: "Starting", running: "Running", passed: "Passed", failed: "Failed", error: "Could not finish", stopped: "Stopped" };
const OUTCOME = { passed: "Passed", failed: "Failed", warning: "Warning", skipped: "Skipped" };
const cls = (s) => (s === "passed" ? "ok-text" : s === "failed" || s === "error" ? "bad-text" : s === "warning" || s === "stopped" ? "warn-text" : "quiet");
const short = (g) => String(g || "").replace(/-/g, "").slice(0, 12);
const open_ = (r) => r && (r.state === "queued" || r.state === "running");

function took(r) {
  if (!r.started_at) return "";
  const end = r.finished_at ? new Date(r.finished_at) : new Date();
  const s = Math.max(0, Math.round((end - new Date(r.started_at)) / 1000));
  return s < 90 ? `${s} s` : `${Math.round(s / 60)} min`;
}
const what = (r) => (r.level === "smoke" ? "Smoke test" : `Detailed: ${r.suites.join(", ")}`)
  + (r.role ? ` · role ${r.role}` : "") + (r.area ? ` · area ${r.area}` : "") + (r.watch ? " · in a browser" : "");

// ---------------------------------------------------------------- the page
export default function SelfTest() {
  const [tab, setTab] = useState("run");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(null);
  const load = async () => { try { setData(await apiFetch("/api/v1/admin/tests")); setErr(""); } catch (e) { setErr(e.message); } };
  useEffect(() => { load(); }, []);
  const live = data?.runs?.find(open_);
  useEffect(() => {
    if (!live) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [live?.id]);
  if (!can("system.operate")) return <p className="status bad">The self-test is for Super Admins and IT Admins.</p>;
  return (
    <div className="self-test">
      <p className="quiet small">Tests this installation, in fixtures of its own: each run makes models, a project and test accounts
        named <code>self_test_&lt;id&gt;_&lt;n&gt;</code> and tests only inside them, so nothing else changes and runs can be repeated.
        The same runs come from <code>eax test</code> and CI. Fixtures stay until you purge them (Test fixtures).</p>
      <div className="seg" role="tablist" aria-label="Self-test">
        {[["run", "Run"], ["history", "History"], ["fixtures", "Test fixtures"]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>))}
      </div>
      {err && <p className="status bad">{err}</p>}
      {tab === "run" && data && (live ? <LiveRun runId={live.id} onChange={load} onOpen={setOpen} />
        : <Chooser data={data} onStarted={load} />)}
      {tab === "run" && data && !live && <ResetSurvival />}
      {tab === "run" && data && !live && data.runs[0] && (
        <p className="small last-run">Last run: <button className="linkish" onClick={() => setOpen(data.runs[0].id)}>
          {data.runs[0].id}</button> <span className={cls(data.runs[0].state)}>{STATE[data.runs[0].state]}</span> · {what(data.runs[0])}
          {" "}· {fmtDateTime(data.runs[0].finished_at || data.runs[0].queued_at)}</p>)}
      {tab === "history" && data && <History runs={data.runs} onOpen={setOpen} />}
      {tab === "fixtures" && <FixturesTab runs={data?.runs || []} />}
      {open && <RunDetail id={open} onClose={() => { setOpen(null); load(); }} />}
    </div>
  );
}

// ---------------------------------------------------------------- choosing and starting
function Chooser({ data, onStarted }) {
  const [level, setLevel] = useState("smoke");
  const [pick, setPick] = useState(["api", "ui", "db", "security"]);
  const [role, setRole] = useState("");
  const [area, setArea] = useState("");
  const [watch, setWatch] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const runner = data.runner || {};
  const toggle = (k) => setPick((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const est = level === "smoke" ? data.estimates.smoke : pick.reduce((a, s) => [a[0] + data.estimates[s][0] - 1, a[1] + data.estimates[s][1] - 2], [1, 2]);
  const start = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await apiFetch("/api/v1/admin/tests", { method: "POST", body: JSON.stringify({ level, suites: pick, role, area, watch: watch && level === "detailed" && pick.includes("ui") }) });
      setMsg(r.message); setConfirm(false); onStarted();
    } catch (e) { setMsg(e.message); setConfirm(false); } finally { setBusy(false); }
  };
  return (
    <section className="self-test-choose" aria-label="Choose a self-test">
      {runner.message && <p className="status warn small">{runner.message}</p>}
      <fieldset>
        <legend>What to run</legend>
        <label className="radio"><input type="radio" name="level" checked={level === "smoke"} onChange={() => setLevel("smoke")} />
          {" "}<b>Smoke test</b>: every role signs in, every main area answers, the key journeys work once ({data.estimates.smoke.join(" to ")} minutes)</label>
        <label className="radio"><input type="radio" name="level" checked={level === "detailed"} onChange={() => setLevel("detailed")} />
          {" "}<b>Detailed tests</b>: the suites below</label>
        {level === "detailed" && (
          <div className="self-test-suites">
            <label className="check"><input type="checkbox" checked={pick.length === SUITES.length}
              onChange={(e) => setPick(e.target.checked ? SUITES.map(([k]) => k) : [])} /> <b>All</b></label>
            {SUITES.map(([k, l, help]) => (
              <label key={k} className="check" title={help}><input type="checkbox" checked={pick.includes(k)} onChange={() => toggle(k)} /> {l}
                <span className="quiet small"> {help}</span></label>))}
            <label className="check" title="The browser journeys run here, in a frame of this page, in this browser, while you watch">
              <input type="checkbox" checked={watch} disabled={!pick.includes("ui")} onChange={(e) => setWatch(e.target.checked)} /> Watch it in this browser
              <span className="quiet small"> (the journeys run in this browser instead of headless on the server)</span></label>
          </div>)}
      </fieldset>
      <div className="toolbar">
        <label>Role <select value={role} onChange={(e) => setRole(e.target.value)} title="Test as one role only">
          <option value="">every role</option>{data.roles.map((r) => <option key={r} value={r}>{r}</option>)}</select></label>
        <label>Area <select value={area} onChange={(e) => setArea(e.target.value)} title="Test one API area only">
          <option value="">every area</option>{data.areas.map((a) => <option key={a.code} value={a.code}>{a.label}</option>)}</select></label>
        <button className="primary" disabled={busy || (level === "detailed" && !pick.length) || runner.image_present === false}
          onClick={() => setConfirm(true)}>Start</button>
        {msg && <span className="small">{msg}</span>}
      </div>
      {confirm && (
        <Modal title="Start the self-test now?" onClose={() => setConfirm(false)}
          actions={<><button onClick={() => setConfirm(false)}>Cancel</button>
            <button className="primary" disabled={busy} onClick={start}>{busy ? "Starting..." : "Start now"}</button></>}>
          <p>{level === "smoke" ? "A smoke test" : `Detailed tests: ${pick.join(", ")}`}{role ? `, as ${role} only` : ""}{area ? `, ${area} only` : ""}.
            It takes about <b>{Math.max(1, est[0])} to {Math.max(2, est[1])} minutes</b>{watch && level === "detailed" ? "; keep this page open while the journeys run in it" : ""}.</p>
          <p className="small">It makes its own models, project and test accounts (<code>self_test_&lt;id&gt;_&lt;n&gt;</code>) and tests only inside
            them; nothing else changes. Its test accounts' tokens are revoked when it ends; its fixtures stay until you purge them.</p>
        </Modal>)}
    </section>
  );
}

// ---------------------------------------------------------------- a run going on
function LiveRun({ runId, onChange, onOpen }) {
  const [d, setD] = useState(null);
  const [stopAsk, setStopAsk] = useState(false);
  const [msg, setMsg] = useState("");
  const load = () => apiFetch(`/api/v1/admin/tests/${runId}`).then(setD).catch((e) => setMsg(e.message));
  useEffect(() => { load(); const t = setInterval(load, 2500); return () => clearInterval(t); }, [runId]);
  useEffect(() => { if (d && !open_(d.run)) onChange(); }, [d?.run?.state]);
  if (!d) return <p>Loading...</p>;
  const r = d.run, t = d.tally;
  const stop = async () => {
    try { const x = await apiFetch(`/api/v1/admin/tests/${runId}/stop`, { method: "POST" }); setMsg(x.message); } catch (e) { setMsg(e.message); }
    setStopAsk(false);
  };
  return (
    <section className="self-test-live" aria-live="polite">
      <h2>Self-test {r.id} <span className="quiet small">({short(r.run_guid)})</span>: <span className={cls(r.state)}>{STATE[r.state]}</span></h2>
      <p className="small">{what(r)} · started by {r.started_by} ({r.trigger}) · {took(r)}</p>
      <div className="kpi-row">
        <div className="kpi"><b className="ok-text">{t.passed}</b><span>passed</span></div>
        <div className={`kpi${t.failed ? " bad" : ""}`}><b>{t.failed}</b><span>failed</span></div>
        <div className="kpi"><b>{t.warning}</b><span>warnings</span></div>
        <div className="kpi"><b>{t.skipped}</b><span>skipped</span></div>
      </div>
      <p className="self-test-step"><span className="spinner" aria-hidden="true" /> {r.stop_asked ? `Stopping (asked by ${r.stop_asked})...` : r.step || "Starting..."}</p>
      <div className="toolbar">
        <button onClick={() => setStopAsk(true)} disabled={!!r.stop_asked}>Stop</button>
        <button className="linkish" onClick={() => onOpen(r.id)}>Results so far</button>
        {msg && <span className="small">{msg}</span>}
      </div>
      {d.browser && <BrowserDriver runId={r.id} browser={d.browser} />}
      {d.results.filter((x) => x.outcome === "failed").slice(0, 8).map((x) => (
        <p key={x.id} className="small bad-text">✗ {x.suite} · {x.name}: {x.detail.slice(0, 200)}</p>))}
      {stopAsk && (
        <Modal title={`Stop self-test ${r.id}?`} onClose={() => setStopAsk(false)}
          actions={<><button onClick={() => setStopAsk(false)}>Keep running</button><button className="primary" onClick={stop}>Stop it</button></>}>
          <p>It ends at its next step and keeps what it has found so far; its fixtures stay (purge them later).</p>
        </Modal>)}
    </section>
  );
}

// ---------------------------------------------------------------- the journeys, watched in this browser (D529)
function browserName() {
  const ua = navigator.userAgent;
  const brands = navigator.userAgentData?.brands?.filter((b) => !/Not.?A.?Brand|Chromium/i.test(b.brand)) || [];
  if (brands[0]) return `${brands[0].brand} ${brands[0].version} (watched here)`;
  const m = /(Firefox|Edg|Chrome|Safari)\/([\d.]+)/.exec(ua);
  return m ? `${m[1] === "Edg" ? "Edge" : m[1]} ${m[2]} (watched here)` : `${ua.slice(0, 80)} (watched here)`;
}

async function snapshot(frame) {
  // what the frame shows, drawn without any extension: its page and styles into an SVG, the SVG onto a canvas
  try {
    const doc = frame.contentDocument;
    const w = frame.clientWidth, h = frame.clientHeight;
    const css = [...doc.styleSheets].map((s) => { try { return [...s.cssRules].map((r) => r.cssText).join("\n"); } catch { return ""; } }).join("\n");
    const body = new XMLSerializer().serializeToString(doc.body);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><foreignObject width="100%" height="100%">`
      + `<div xmlns="http://www.w3.org/1999/xhtml" style="width:${w}px;height:${h}px;overflow:hidden;background:#fff"><style>${css.replace(/</g, "\\3c ")}</style>${body}</div></foreignObject></svg>`;
    const img = new Image();
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    c.getContext("2d").drawImage(img, 0, 0);
    return c.toDataURL("image/png");
  } catch { return null; }
}

function BrowserDriver({ runId, browser }) {
  const frame = useRef(null);
  const [rows, setRows] = useState(browser.journeys.map((j) => ({ name: j.name, role: j.role, state: "waiting", detail: "" })));
  const [now, setNow] = useState("");
  const started = useRef(false);
  const set = (i, patch) => setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const waitFor = async (test, ms) => {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      try { if (test()) return true; } catch { /* the frame is loading */ }
      await new Promise((ok) => setTimeout(ok, 300));
    }
    return false;
  };
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      const name = browserName();
      for (const [i, j] of browser.journeys.entries()) {
        const t0 = Date.now();
        set(i, { state: "running" });
        const errors = [];
        let outcome = "passed", detail = "", shot = null;
        for (const step of j.steps) {
          setNow(`${j.name}: ${step.route}`);
          const url = `/?eaxselftest=${encodeURIComponent(browser.ticket)}&eaxrole=${encodeURIComponent(j.role)}${step.route}`;
          await new Promise((ok) => { frame.current.onload = ok; frame.current.src = url; setTimeout(ok, 15000); });
          try { frame.current.contentWindow.addEventListener("error", (e) => errors.push(String(e.message || e))); } catch { /* not ours */ }
          const body = () => frame.current.contentDocument?.body?.innerText || "";
          const ok = await waitFor(() => body().includes("EA Explorer") && (!step.expect || body().includes(step.expect)), 30000);
          if (!ok) { outcome = "failed"; detail = `"${step.expect || "EA Explorer"}" did not show on ${step.route} within 30 s`; break; }
          await new Promise((r) => setTimeout(r, 1200));
        }
        if (outcome === "passed" && errors.length) { outcome = "failed"; detail = errors.slice(0, 10).join("; "); }
        if (outcome === "failed") shot = await snapshot(frame.current);
        if (outcome === "passed") detail = `${j.steps.length} page(s) as ${j.role}`;
        set(i, { state: outcome, detail });
        try {
          await apiFetch(`/api/v1/admin/tests/${runId}/browser`, { method: "POST", body: JSON.stringify({
            results: [{ name: j.name, outcome, detail, ms: Date.now() - t0, browser: name, screenshot: shot }] }) });
        } catch { /* the run may have been stopped */ }
      }
      setNow("done");
      try { await apiFetch(`/api/v1/admin/tests/${runId}/browser`, { method: "POST", body: JSON.stringify({ results: [], done: true }) }); } catch { /* ended */ }
    })();
  }, []);
  return (
    <div className="self-test-watch">
      <ol className="self-test-steps" aria-label="Journeys in this browser">
        {rows.map((r) => <li key={r.name} className={r.state}><span className={cls(r.state)}>{r.state === "running" ? "▶" : r.state === "passed" ? "✓" : r.state === "failed" ? "✗" : "·"}</span>
          {" "}{r.name} <span className="quiet small">as {r.role}</span>{r.detail && r.state === "failed" && <div className="small bad-text">{r.detail}</div>}</li>)}
      </ol>
      <div className="self-test-frame-wrap">
        <p className="quiet small">{now === "done" ? "The journeys have finished in this browser." : `Now: ${now || "starting"}`}</p>
        <iframe ref={frame} title="The self-test's journeys in this browser" className="self-test-frame" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- history and a run's results
function History({ runs, onOpen }) {
  if (!runs.length) return <p className="quiet">No self-test yet.</p>;
  return (
    <table className="grid-table test-run-table">
      <thead><tr><th>Run</th><th>Started</th><th>By</th><th>What</th><th>Result</th><th className="num">Passed</th>
        <th className="num">Failed</th><th className="num">Skipped, warnings</th><th>Took</th><th>Fixtures</th><th /></tr></thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id}>
            <td>{r.id} <span className="quiet small">{short(r.run_guid)}</span></td>
            <td className="nowrap">{fmtDateTime(r.started_at || r.queued_at)}</td>
            <td>{r.started_by}<span className="quiet small"> · {r.trigger}</span></td>
            <td className="small">{what(r)}</td>
            <td><span className={cls(r.state)}>{STATE[r.state] || r.state}</span>
              {r.state === "error" && r.message && <div className="bad-text small">{r.message}</div>}</td>
            <td className="num">{r.passed || ""}</td>
            <td className={`num${r.failed ? " bad-text" : ""}`}>{r.failed || ""}</td>
            <td className="num">{r.skipped || ""}</td>
            <td className="nowrap small">{took(r)}</td>
            <td className="small">{r.purged_at ? <span className="quiet">removed</span> : r.fixtures}</td>
            <td><button className="linkish" onClick={() => onOpen(r.id)}>Results</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RunDetail({ id, onClose }) {
  const [outcome, setOutcome] = useState("");
  const [suite, setSuite] = useState("");
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [shot, setShot] = useState(null);
  useEffect(() => {
    const q = new URLSearchParams({ ...(outcome ? { outcome } : {}), ...(suite ? { suite } : {}) });
    apiFetch(`/api/v1/admin/tests/${id}?${q}`).then(setD).catch((e) => setErr(e.message));
  }, [id, outcome, suite]);
  const showShot = async (r) => { try { setShot({ name: r.name, url: await apiBlobUrl(`/api/v1/admin/tests/${id}/screenshot/${r.id}`) }); } catch (e) { setErr(e.message); } };
  const file = (name) => apiDownload(`/api/v1/admin/tests/${id}/files/${name}`, name.split("/").pop()).catch((e) => setErr(e.message));
  const rep = (fmt) => apiDownload(`/api/v1/admin/tests/${id}/report?format=${fmt}`, `self-test-${id}.${fmt}`).catch((e) => setErr(e.message));
  const run = d?.run;
  return (
    <Modal wide title={`Self-test ${id}${run ? `: ${STATE[run.state] || run.state}` : ""}`} onClose={onClose}
      actions={<><button onClick={() => rep("html")}>Download report (HTML)</button><button onClick={() => rep("xlsx")}>Excel</button>
        <button onClick={onClose}>Close</button></>}>
      {err && <p className="status bad">{err}</p>}
      {run && <p className="small">{what(run)} · {run.message} · version {run.version || "?"} · started by {run.started_by} ({run.trigger})
        {" "}{fmtDateTime(run.started_at || run.queued_at)}{run.purged_at ? ` · fixtures removed by ${run.purged_by}` : ""}</p>}
      <div className="toolbar">
        <label>Show <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="">everything</option>{Object.entries(OUTCOME).map(([k, l]) => <option key={k} value={k}>{l.toLowerCase()} only</option>)}</select></label>
        <label>Suite <select value={suite} onChange={(e) => setSuite(e.target.value)}>
          <option value="">all</option><option value="smoke">Smoke</option>{SUITES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        {d?.files?.filter((f) => !f.startsWith("videos/") && !f.startsWith("report")).map((f) => (
          <button key={f} className="linkish small" onClick={() => file(f)}>{f}</button>))}
      </div>
      {d && (d.results.length === 0 ? <p className="quiet">Nothing to show{outcome ? ` that ${outcome}` : ""}.</p> : (
        <div className="test-results-scroll">
          <table className="grid-table test-results">
            <thead><tr><th>Suite</th><th>Check</th><th>Outcome</th><th>Why</th><th /></tr></thead>
            <tbody>
              {d.results.map((r) => (
                <tr key={r.id}>
                  <td className="small">{r.suite}</td>
                  <td className="small">{r.name}{r.browser && <div className="quiet small">{r.browser}</div>}</td>
                  <td><span className={cls(r.outcome)}>{OUTCOME[r.outcome]}</span></td>
                  <td className="small test-detail">{r.detail}
                    {(r.request || r.response) && <details><summary>What was asked and what came back</summary>
                      <pre className="test-exchange">{r.request}{"\n\n"}{r.response}</pre></details>}</td>
                  <td className="nowrap small">
                    {r.has_screenshot && <button className="linkish small" onClick={() => showShot(r)}>Screenshot</button>}
                    {r.video && <button className="linkish small" onClick={() => file(r.video)}>Video</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {d?.fixtures?.length > 0 && <details className="small"><summary>Its fixtures ({d.fixtures.length})</summary>
        <ul>{d.fixtures.map((f) => <li key={f.id}>{f.kind}: {f.name}{f.purged_at ? " (removed)" : ""}</li>)}</ul></details>}
      {shot && <Modal wide title={shot.name} onClose={() => setShot(null)} actions={<button onClick={() => setShot(null)}>Close</button>}>
        <img className="test-shot" src={shot.url} alt={`What the page looked like when "${shot.name}" failed`} />
      </Modal>}
    </Modal>
  );
}

// ---------------------------------------------------------------- test fixtures and purging them (D529)
function FixturesTab({ runs }) {
  const [rows, setRows] = useState(null);
  const [run, setRun] = useState("");
  const [sel, setSel] = useState(new Set());
  const [ask, setAsk] = useState(false);
  const [typed, setTyped] = useState("");
  const [task, setTask] = useState(null);
  const [err, setErr] = useState("");
  const load = () => apiFetch(`/api/v1/admin/tests/fixtures${run ? `?run=${run}` : ""}`).then((x) => setRows(x.fixtures)).catch((e) => setErr(e.message));
  useEffect(() => { load(); setSel(new Set()); }, [run]);
  useEffect(() => {
    if (!task || task.status === "done" || task.status === "failed") return undefined;
    const t = setInterval(() => apiFetch(`/api/v1/tasks/${task.id}`).then((x) => { setTask(x); if (x.status === "done" || x.status === "failed") load(); }).catch(() => {}), 1500);
    return () => clearInterval(t);
  }, [task?.id, task?.status]);
  if (!rows) return err ? <p className="status bad">{err}</p> : <p>Loading...</p>;
  const runsOf = [...new Set(rows.map((r) => r.run_id))];
  const flip = (id) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const purge = async () => {
    setErr("");
    try {
      const out = await apiFetch("/api/v1/admin/tests/fixtures/purge", { method: "POST", body: JSON.stringify({ fixtures: [...sel], confirm: typed }) });
      trackTask(out.task, "#/admin/self-test"); setTask(out.task); setAsk(false); setTyped(""); setSel(new Set());
    } catch (e) { setErr(e.message); }
  };
  const chosen = rows.filter((r) => sel.has(r.id));
  return (
    <section className="self-test-fixtures" aria-label="Test fixtures">
      <div className="toolbar">
        <label>Run <select value={run} onChange={(e) => setRun(e.target.value)}>
          <option value="">every run</option>{[...new Set([...runsOf, ...runs.filter((r) => r.fixtures > 0).map((r) => r.id)])].sort((a, b) => b - a)
            .map((id) => <option key={id} value={id}>{id}</option>)}</select></label>
        <button onClick={() => setSel(new Set(rows.map((r) => r.id)))} disabled={!rows.length}>{run ? "All of this run" : "All runs"}</button>
        <button onClick={() => setSel(new Set())} disabled={!sel.size}>None</button>
        <button className="danger" disabled={!sel.size} onClick={() => setAsk(true)}>Delete selected ({sel.size})</button>
        {err && <span className="small bad-text">{err}</span>}
      </div>
      {task && <p className={`small ${task.status === "failed" ? "bad-text" : ""}`}>Purging: {task.status}{task.progress != null ? ` ${task.progress}%` : ""}
        {task.note ? ` · ${task.note}` : ""}{task.message ? ` · ${task.message}` : ""}</p>}
      {rows.length === 0 ? <p className="quiet">No self-test fixtures: nothing to remove.</p> : (
        <table className="grid-table">
          <thead><tr><th><span className="sr-only">Choose</span></th><th>Run</th><th>Kind</th><th>Name</th><th>Made</th><th>Size</th></tr></thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id}>
                <td><input type="checkbox" aria-label={`Choose ${f.name}`} checked={sel.has(f.id)} onChange={() => flip(f.id)} /></td>
                <td>{f.run_id} <span className="quiet small">{short(f.run_guid)}</span></td>
                <td className="small">{f.kind.replace("_", " ")}</td>
                <td><code>{f.name}</code></td>
                <td className="nowrap small">{fmtDateTime(f.created_at)}</td>
                <td className="small">{f.kind === "model" ? `${f.entities} entities, ${f.relationships} relationships` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>)}
      {ask && (
        <Modal title={`Delete ${chosen.length} self-test fixture(s) for good?`} onClose={() => setAsk(false)}
          actions={<><button onClick={() => setAsk(false)}>Cancel</button>
            <button className="danger" disabled={typed !== "DELETE"} onClick={purge}>Delete for good</button></>}>
          <p><b>This cannot be undone.</b> The self_test models and everything in them (entities, relationships, history, tags,
            measurements, drawn views), the projects with their documents, and the test accounts and credentials are removed.
            Only fixtures the self-test recorded are touched; the runs' reports stay.</p>
          <p className="small">{[...new Set(chosen.map((f) => f.run_id))].length} run(s): {chosen.slice(0, 6).map((f) => f.name).join(", ")}{chosen.length > 6 ? "…" : ""}</p>
          <label>Type DELETE to confirm <input value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus /></label>
        </Modal>)}
    </section>
  );
}

// ---------------------------------------------------------------- on Health: the last run in one line
export function LastSelfTest() {
  const [r, setR] = useState(null);
  useEffect(() => { if (can("system.operate")) apiFetch("/api/v1/admin/tests?limit=1").then((x) => setR(x.runs[0] || false)).catch(() => {}); }, []);
  if (!can("system.operate") || r === null) return null;
  return (
    <p className="small last-self-test">Self-test: {r ? <><span className={cls(r.state)}>{STATE[r.state]}</span> · {what(r)} · {fmtDateTime(r.finished_at || r.queued_at)}</> : "never run"}
      {" "}· <a href="#/admin/self-test">Self-test</a></p>
  );
}


// ---------------------------------------------------------------- settings survive a reset (D561), opt-in only
function ResetSurvival() {
  const [d, setD] = useState(null);
  const [on, setOn] = useState(false);
  const [typed, setTyped] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { apiFetch("/api/v1/admin/commands/reset-survival").then(setD).catch(() => {}); }, []);
  if (!d) return null;
  const start = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await apiFetch("/api/v1/admin/commands/run", { method: "POST",
        body: JSON.stringify({ argv: ["test", "--reset-survival"], confirm: { typed, understood } }) });
      setMsg(`Started (${r.command}). EA Explorer goes offline now; open this address again in a few minutes and look below.`);
    } catch (e) { setMsg(e.message); }
    setBusy(false);
  };
  return (
    <section className="self-test-reset" aria-label="Settings survive a reset">
      <h3>Settings survive a reset</h3>
      <p className="small quiet">Checks that the schedules, the banner and the safety backups in <code>persist/</code> outlive a real
        <code> eax clean-restart</code>: it writes markers there, resets, waits for EA Explorer to come back and checks them. Never part of
        the smoke or detailed runs. Also <code>eax test --reset-survival</code>.</p>
      {d.you?.super_admin ? <>
        <label className="check"><input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} /> <b>Includes a full reset: deletes all data</b></label>
        {on && <div className="status bad" role="alert">
          <p>This runs a real <code>eax clean-restart</code>: every database, the document files, the config file, the logs and work/backups are deleted,
            and EA Explorer starts again with the sample data. A safety backup is taken first into persist/safety-backups.</p>
          <label>Type the installation's name, <strong>{d.installation}</strong>, to confirm <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" /></label>
          <label className="check"><input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} /> I understand that this deletes all data</label>
          <div className="toolbar"><button className="danger" disabled={busy || !understood || typed.trim() !== d.installation} onClick={start}>Reset and test</button></div>
        </div>}
      </> : <p className="small quiet">Only Super Admins can run it.</p>}
      {msg && <p className="small">{msg}</p>}
      {d.runs.length > 0 && <table className="grid-table">
        <thead><tr><th>Run</th><th>Started</th><th>Result</th><th>Checks</th></tr></thead>
        <tbody>{d.runs.map((r) => <tr key={r.id}><td>{r.id}</td><td>{fmtDateTime(r.started)}</td>
          <td><span className={cls(r.state)}>{r.state}</span></td>
          <td className="small">{(r.checks || []).map((c) => <div key={c.name}>{c.result === "passed" ? "passed" : "FAILED"}: {c.name}{c.note ? ` (${c.note})` : ""}</div>)}</td></tr>)}</tbody>
      </table>}
    </section>
  );
}
