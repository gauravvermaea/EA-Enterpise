// System Admin › Tools › Self-test (phase 36.1, D367, D522 to D529; made simple in R2.0.1, D592): Super Admins and IT
// Admins test this installation, from here or with `eax test smoke|full`: one runner, one results store, so a run started
// in either place shows in both.
//   Run           two choices only: the Smoke test or the Full test (owner, 12 Nov 2026: "Not too many options"); it
//                 asks to confirm, then starts its own test container, tests, writes the report and removes the container;
//                 follow it live, stop it
//   History       every run: its results with each failure explained (what was asked and what came back; a screenshot or
//                 video), its report (HTML or Excel) and its fixtures; Run the failed ones again (R2.36, D605): a new run
//                 of only the checks that failed, whose results show each check then and now
//   Test data     every self_test_<id>_<n> model, project, account and credential of every run; tick and delete them,
//                 or Delete all test data (for good: type DELETE), as a background task with its progress (D593)
// Each run makes the data it needs and tests only inside it; nothing else changes. The test container's image is
// prepared whenever a test starts (D584): nothing to build by hand; its build shows here while it runs.
// Health shows the last run in one line (LastSelfTest).
import { useEffect, useRef, useState } from "react";
import { journey, makeFrame, sweep } from "./selfTestDriver.js";
import { apiBlobUrl, apiDownload, apiFetch, can } from "./auth";
import { Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";
import { trackTask } from "./tasks";

const SUITES = [
  ["api", "API", "every endpoint, with no token and as every role: allowed and refused, never a server error"],
  ["ui", "Browser", "the main journeys through the screens"],
  ["db", "Database", "read-only checks of the database"],
  ["security", "Security", "headers, cookies, the Python dependencies, an OWASP ZAP scan and Trivy image scans"],
  ["backup", "Backups", "the last: an infrastructure and an application backup, each restored into a scratch copy, then removed (R2.45)"],
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
const what = (r) => (r.repeat_of ? `The failed checks of run ${r.repeat_of} again${r.repeat_warnings ? " (and its warnings)" : ""}`
  : r.level === "smoke" ? "Smoke test" : r.suites.length >= 4 ? "Full test" : `Detailed: ${r.suites.join(", ")}`)
  + (r.role ? ` · role ${r.role}` : "") + (r.area ? ` · area ${r.area}` : "") + (r.watch ? " · in a browser" : "");
const repeatable = (r) => r && !open_(r) && (r.failed > 0 || r.skipped > 0);

// Run the failed ones again (R2.36, D605): a new run of only the checks that failed in run `id` (and its warnings if
// asked), in fresh test data (earlier test data is removed first, as before every run)
function RepeatButton({ run, busy, onStarted, small }) {
  const [warnings, setWarnings] = useState(false);
  const [msg, setMsg] = useState("");
  if (!repeatable(run)) return null;
  const go = async () => {
    setMsg("");
    try {
      const x = await apiFetch(`/api/v1/admin/tests/${run.id}/repeat`, { method: "POST", body: JSON.stringify({ warnings }) });
      onStarted(x);
    } catch (e) { setMsg(e.message); }
  };
  return (
    <span className="test-repeat">
      <button className={small ? "linkish" : ""} disabled={busy || (!run.failed && !warnings)} onClick={go}
        title="A new run of only the checks that failed here, in fresh test data; its results show each check then and now">
        Run the failed ones again</button>
      {!small && run.skipped > 0 && <label className="small"><input type="checkbox" checked={warnings}
        onChange={(e) => setWarnings(e.target.checked)} /> and the warnings</label>}
      {msg && <span className="bad-text small"> {msg}</span>}
    </span>
  );
}

// ---------------------------------------------------------------- the page
export default function SelfTest() {
  const [tab, setTab] = useState("run");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(null);
  const load = async () => { try { setData(await apiFetch("/api/v1/admin/tests")); setErr(""); } catch (e) { setErr(e.message); } };
  useEffect(() => { load(); }, []);
  const live = data?.runs?.find(open_);
  const building = !!data?.runner?.build?.busy;
  useEffect(() => {
    if (!live && !building) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [live?.id, building]);
  const built = () => { setTab("run"); load(); };
  const repeated = () => { setOpen(null); setTab("run"); load(); };
  if (!can("system.operate")) return <p className="status bad">The self-test is for Super Admins and IT Admins.</p>;
  return (
    <div className="self-test">
      <p className="quiet small">Tests this installation, in fixtures of its own: each run makes models, a project and test accounts
        named <code>self_test_&lt;id&gt;_&lt;n&gt;</code> and tests only inside them, so nothing else changes and runs can be repeated.
        The same runs come from <code>eax test</code> and CI. Fixtures stay until you purge them (Test fixtures).</p>
      <div className="seg" role="tablist" aria-label="Self-test">
        {[["run", "Run"], ["history", "History"], ["fixtures", "Test data"]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>))}
      </div>
      {err && <p className="status bad">{err}</p>}
      {tab === "run" && data?.runner?.build?.busy && <TestRunner runner={data.runner || {}} onBuilt={built} onChange={load} />}
      {tab === "run" && data && (live ? <LiveRun runId={live.id} onChange={load} onOpen={setOpen} />
        : <Chooser data={data} onStarted={load} />)}
      {tab === "run" && data && !live && data.runs[0] && (
        <p className="small last-run">Last run: <button className="linkish" onClick={() => setOpen(data.runs[0].id)}>
          {data.runs[0].id}</button> <span className={cls(data.runs[0].state)}>{STATE[data.runs[0].state]}</span> · {what(data.runs[0])}
          {" "}· {fmtDateTime(data.runs[0].finished_at || data.runs[0].queued_at)}</p>)}
      {tab === "history" && data && <History runs={data.runs} onOpen={setOpen} busy={!!live} onRepeat={repeated}
        keepDays={data.runner?.keep_days} onChange={load} />}
      {tab === "fixtures" && <FixturesTab runs={data?.runs || []} />}
      {open && <RunDetail id={open} busy={!!live} onRepeat={repeated} onClose={() => { setOpen(null); load(); }} />}
    </div>
  );
}

// ---------------------------------------------------------------- choosing and starting
// Two choices only (owner, 12 Nov 2026, R2.0.1, D592: "Test from UI - Smoke or Full ... Not too many options"): a smoke test
// or the full test (every suite: the API, the database, security, then every page and journey in a headless browser).
// Each run starts its own test container, tests, reports and removes the container; it makes the data it needs itself.
const CHOICES = [
  ["smoke", "Smoke test", "every role signs in, every main area answers, every page opens and the key journeys work once"],
  ["full", "Full test", "everything: every API endpoint for every role, the database, security, then every page and journey in a browser"],
];

function Chooser({ data, onStarted }) {
  const [ask, setAsk] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const runner = data.runner || {};
  const est = (k) => (k === "smoke" ? data.estimates.smoke
    : SUITES.reduce((a, [s]) => [a[0] + data.estimates[s][0] - 1, a[1] + data.estimates[s][1] - 2], [1, 2]));
  const start = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await apiFetch("/api/v1/admin/tests", { method: "POST", body: JSON.stringify(ask === "smoke"
        ? { level: "smoke", suites: [] } : { level: "detailed", suites: SUITES.map(([k]) => k) }) });
      setMsg(r.message); setAsk(""); onStarted();
    } catch (e) { setMsg(e.message); setAsk(""); } finally { setBusy(false); }
  };
  const minutes = (k) => { const [lo, hi] = est(k); return `${Math.max(1, lo)} to ${Math.max(2, hi)} minutes`; };
  return (
    <section className="self-test-choose" aria-label="Choose a self-test">
      {runner.message && runner.image_present !== false && <p className="status warn small">{runner.message}</p>}
      <div className="self-test-choices">
        {CHOICES.map(([k, label, what]) => (
          <div key={k} className="card self-test-choice">
            <h3>{label}</h3>
            <p className="small">{what}.</p>
            <p className="quiet small">About {minutes(k)}.</p>
            <button className={k === "smoke" ? "primary" : ""} disabled={busy || !!runner.build?.busy} onClick={() => setAsk(k)}>
              Start the {label.toLowerCase()}</button>
          </div>))}
      </div>
      {msg && <p className="small">{msg}</p>}
      <p className="quiet small">From the command line: <code>eax test smoke</code> or <code>eax test full</code> (the same runs; they show here too).</p>
      {ask && (
        <Modal title={`Start the ${ask === "smoke" ? "smoke test" : "full test"} now?`} onClose={() => setAsk("")}
          actions={<><button onClick={() => setAsk("")}>Cancel</button>
            <button className="primary" disabled={busy} onClick={start}>{busy ? "Starting..." : "Start now"}</button></>}>
          <p>It starts a test container of its own, tests, writes the report and removes the container. It takes about <b>{minutes(ask)}</b>
            {runner.image_present === false ? <>, plus about {(runner.build_minutes || [5, 15]).join(" to ")} minutes the first time to prepare
              the test container</> : ""}.</p>
          <p className="small">It makes the models, project and test accounts it needs (<code>self_test_&lt;id&gt;_&lt;n&gt;</code>) and tests only
            inside them; nothing else changes.</p>
        </Modal>)}
    </section>
  );
}

function TestRunner({ runner, onBuilt, onChange }) {
  const b = runner.build || {};
  const [watching, setWatching] = useState(b.busy ? b.run_id : null);
  const [msg, setMsg] = useState("");
  const [auto, setAuto] = useState(!!runner.auto_build);
  useEffect(() => { setAuto(!!runner.auto_build); }, [runner.auto_build]);
  useEffect(() => { if (b.busy && b.run_id) setWatching(b.run_id); }, [b.busy, b.run_id]);
  if (runner.image_present === null || runner.image_present === undefined) return null;     // the helper is not reachable
  const build = async () => {
    setMsg("");
    try { const r = await apiFetch("/api/v1/admin/tests/build", { method: "POST" }); setWatching(r.run_id); onChange(); } catch (e) { setMsg(e.message); }
  };
  const saveAuto = async (on) => {
    setAuto(on);
    try { await apiFetch("/api/v1/admin/tests/settings", { method: "PUT", body: JSON.stringify({ auto_build: on }) }); onChange(); } catch (e) { setAuto(!on); setMsg(e.message); }
  };
  const autoBox = (
    <label className="check small" title="When the image for the running version is missing, the operations helper builds it in the background after each start and each update">
      <input type="checkbox" checked={auto} onChange={(e) => saveAuto(e.target.checked)} /> Build it automatically after each start or update</label>);
  if (watching) return <RunnerBuild id={watching} onRetry={build} onBuilt={() => { setWatching(null); onBuilt(); }} />;
  // nothing to build by hand (owner, 11 Nov 2026, D584): Start prepares the runner; Advanced keeps a rebuild for when it is needed
  return (
    <details className="small self-test-runner">
      <summary>Advanced: the test runner</summary>
      <p>{runner.image_present ? <>The test runner <code>{runner.image}</code> is built.</>
        : <>The test runner is not built yet: it is built when a test starts (about {runner.size_gb || 1.5} GB,
          {" "}{(runner.build_minutes || [5, 15]).join(" to ")} minutes the first time).</>}
        {b.state === "failed" && <span className="status bad"> The last build failed{b.reason ? `: ${b.reason}` : ""}.</span>}</p>
      <div className="toolbar">
        <button onClick={build}>{b.state === "failed" ? "Retry the build" : "Rebuild the test runner"}</button>
        {autoBox}
      </div>
      {msg && <p className="status bad small">{msg}</p>}
      <p className="quiet small">The same as <code>eax test --build</code>. Never needed before a test: Start and <code>eax test</code> prepare it.</p>
    </details>
  );
}

function RunnerBuild({ id, onRetry, onBuilt }) {
  const [d, setD] = useState(null);
  const [log, setLog] = useState("");
  const [err, setErr] = useState("");
  const from = useRef(0);
  const pre = useRef(null);
  useEffect(() => {
    let stop = false;
    from.current = 0; setLog("");
    const tick = async () => {
      try {
        const r = await apiFetch(`/api/v1/admin/tests/build/${encodeURIComponent(id)}?from=${from.current}`);
        if (stop) return;
        from.current = r.next; if (r.text) setLog((l) => (l + r.text).slice(-60000)); setD(r); setErr("");
        if (r.finished) { stop = true; if (r.ok) setTimeout(onBuilt, 2500); }
      } catch (e) { setErr(e.message); }
    };
    tick();
    const t = setInterval(() => { if (!stop) tick(); }, 2000);
    return () => { stop = true; clearInterval(t); };
  }, [id]);
  useEffect(() => { if (pre.current) pre.current.scrollTop = pre.current.scrollHeight; }, [log]);
  const steps = d?.steps || [];
  const done = steps.filter((s) => s.state === "done").length;
  return (
    <section className="self-test-runner panel-soft" aria-live="polite" aria-label="Building the test runner">
      <h3>{!d?.finished ? "Building the test runner..." : d.ok ? "The test runner is built" : "The build failed"}</h3>
      <div className="runner-meter" role="progressbar" aria-valuemin={0} aria-valuemax={steps.length || 5} aria-valuenow={done}>
        <span style={{ width: `${steps.length ? (100 * done) / steps.length : 3}%` }} /></div>
      <ol className="build-steps">
        {steps.map((s) => <li key={s.key} className={s.state}>
          <span className={cls(s.state === "done" ? "passed" : s.state)}>{s.state === "done" ? "✓" : s.state === "failed" ? "✗" : s.state === "running" ? "▶" : "·"}</span> {s.label}</li>)}
      </ol>
      {d?.finished && d.ok && <p className="status good small">Ready: the Run tab opens in a moment.</p>}
      {d?.finished && !d.ok && <>
        <p className="status bad small">Why: {d.reason || "see the log below"}</p>
        <button className="primary" onClick={onRetry}>Retry</button></>}
      {err && <p className="status warn small">{err}</p>}
      <details open><summary>The build's log</summary>
        <pre ref={pre} className="build-log">{log || "Starting..."}</pre></details>
      <p className="quiet small">Started by {d?.status?.by || "?"} · {d?.status?.command || "eax test --build"}. You can leave this page; the build goes on.</p>
    </section>
  );
}

// how many checks are left (R2.40; owner, 12 Nov 2026: "please tell how many tests are left as well when in the screen"):
// as many as the newest finished run of the same kind had (a repeat: as many as it repeats)
function Progress({ p }) {
  if (!p) return null;
  if (p.total == null) return <p className="small quiet test-progress">{p.done} checks so far; how many are left is not known ({p.how}).</p>;
  return (
    <div className="test-progress" title={`About ${p.total} checks in all: ${p.how}`}>
      <div className="test-progress-bar"><span style={{ width: `${p.percent}%` }} /></div>
      <p className="small"><b>{p.done}</b> of about {p.total} checks done · <b>{p.left}</b> left ({p.percent}%)</p>
    </div>
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
      <Progress p={d.progress} />
      <HealthPanel h={d.health} />
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

// ---------------------------------------------------------------- the same from the command line (D578)

function BrowserDriver({ runId, browser }) {
  // the page sweep, then the journeys, in a frame of this page (selfTestDriver.js: the same rules as the headless runner)
  const frame = useRef(null);
  const js = browser.journeys || [];
  const [rows, setRows] = useState(js.map((j) => ({ name: j.name, role: j.role, state: "waiting", detail: "" })));
  const [pages, setPages] = useState({ done: 0, of: (browser.pages || []).length, failed: 0 });
  const [now, setNow] = useState("");
  const started = useRef(false);
  const set = (i, patch) => setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      const name = browserName();
      const errors = [];
      const f = makeFrame(frame.current, browser.ticket, (e) => errors.push(e));
      const post = async (results, done) => {
        try { await apiFetch(`/api/v1/admin/tests/${runId}/browser`, { method: "POST", body: JSON.stringify({ results, done }) }); }
        catch { /* the run may have been stopped */ }
      };
      if ((browser.pages || []).length) {
        await sweep(f, browser, errors, async (nm, outcome, detail, ms, wantShot) => {
          const shot = wantShot ? await snapshot(frame.current) : null;
          if (nm.startsWith("page: ") && outcome !== "skipped") {
            setPages((p) => ({ ...p, done: p.done + 1, failed: p.failed + (outcome === "failed" ? 1 : 0) }));
          }
          await post([{ name: nm, outcome, detail, ms, browser: name, screenshot: shot }]);
        }, (route, n, of) => { setNow(`page ${n + 1} of ${of}: ${route}`); setPages((p) => ({ ...p, of })); });
      }
      for (const [i, j] of js.entries()) {
        const t0 = Date.now();
        set(i, { state: "running" });
        setNow(`${j.name} as ${j.role}`);
        errors.length = 0;
        let [outcome, detail] = await journey(f, j);
        if (outcome === "passed" && errors.length) { outcome = "failed"; detail = errors.slice(0, 10).join("; "); }
        const shot = outcome === "failed" ? await snapshot(frame.current) : null;
        set(i, { state: outcome, detail });
        await post([{ name: j.name, outcome, detail, ms: Date.now() - t0, browser: name, screenshot: shot }]);
      }
      setNow("done");
      await post([], true);
    })();
  }, []);
  return (
    <div className="self-test-watch">
      <div>
        {pages.of > 0 && <p className="small">Pages opened <b>{pages.done}</b> of {pages.of}{pages.failed ? <span className="bad-text"> · {pages.failed} failed</span> : ""}</p>}
        <ol className="self-test-steps" aria-label="Journeys in this browser">
          {rows.map((r) => <li key={r.name} className={r.state}><span className={cls(r.state)}>{r.state === "running" ? "▶" : r.state === "passed" ? "✓" : r.state === "failed" ? "✗" : "·"}</span>
            {" "}{r.name} <span className="quiet small">as {r.role}</span>{r.detail && r.state === "failed" && <div className="small bad-text">{r.detail}</div>}</li>)}
        </ol>
      </div>
      <div className="self-test-frame-wrap">
        <p className="quiet small">{now === "done" ? "The pages and journeys have finished in this browser." : `Now: ${now || "starting"}`}</p>
        <iframe ref={frame} title="The self-test's pages and journeys in this browser" className="self-test-frame" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- history and a run's results
// deleting test results (R2.43; owner, 12 Nov 2026: "delete test logs both on web and UI so that all the captured images,
// logs videos all are deleted"): a run, every finished one, or those older than N days; and how long they are kept
function DeleteResults({ keepDays, onChange }) {
  const [ask, setAsk] = useState(null);       // {runs, label}
  const [typed, setTyped] = useState("");
  const [days, setDays] = useState(keepDays ?? 30);
  const [msg, setMsg] = useState("");
  useEffect(() => { setDays(keepDays ?? 30); }, [keepDays]);
  const go = async () => {
    try {
      const x = await apiFetch("/api/v1/admin/tests/delete", { method: "POST", body: JSON.stringify(ask.body) });
      setMsg(x.message); setAsk(null); setTyped(""); onChange();
    } catch (e) { setMsg(e.message); }
  };
  const saveDays = async () => {
    try { await apiFetch("/api/v1/admin/tests/settings", { method: "PUT", body: JSON.stringify({ keep_days: Number(days) || 0 }) }); setMsg(Number(days) ? `Test results are kept ${days} days.` : "Test results are kept until deleted."); onChange(); }
    catch (e) { setMsg(e.message); }
  };
  return (
    <div className="row-gap filters test-delete">
      <button onClick={() => setAsk({ body: { runs: "all" }, label: "every finished test run" })}>Delete all test results...</button>
      <label className="small">Keep test results <input type="number" min="0" max="3650" value={days} onChange={(e) => setDays(e.target.value)} style={{ width: 70 }} /> days
        (0: until deleted)</label>
      <button className="linkish" onClick={saveDays}>Save</button>
      {msg && <span className="small">{msg}</span>}
      {ask && (
        <Modal title="Delete test results for good?" onClose={() => setAsk(null)}
          actions={<><button onClick={() => setAsk(null)}>Keep them</button>
            <button className="danger" disabled={typed !== "DELETE"} onClick={go}>Delete</button></>}>
          <p>This deletes {ask.label} for good: its test data, its results and screenshots, and its reports, logs and videos
            in work/tests. It cannot be undone. A run still going is left.</p>
          <label>Type DELETE <input value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus /></label>
        </Modal>)}
    </div>
  );
}

function History({ runs, onOpen, busy, onRepeat, keepDays, onChange }) {
  const [msg, setMsg] = useState("");
  if (!runs.length) return <><DeleteResults keepDays={keepDays} onChange={onChange} /><p className="quiet">No self-test yet.</p></>;
  const del = async (r) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete self-test ${r.id} for good: its test data, results, screenshots, report, log and videos?`)) return;
    try { const x = await apiFetch("/api/v1/admin/tests/delete", { method: "POST", body: JSON.stringify({ runs: [r.id] }) }); setMsg(x.message); onChange(); }
    catch (e) { setMsg(e.message); }
  };
  return (
    <>
    <DeleteResults keepDays={keepDays} onChange={onChange} />
    {msg && <p className="small status">{msg}</p>}
    <table className="grid-table test-run-table">
      <thead><tr><th>Run</th><th>Started</th><th>By</th><th>What</th><th>Result</th><th className="num">Passed</th>
        <th className="num">Failed</th><th className="num">Skipped, warnings</th><th>Took</th><th>Fixtures</th><th /></tr></thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id}>
            <td>{r.id} <span className="quiet small">{short(r.run_guid)}</span></td>
            <td className="nowrap">{fmtDateTime(r.started_at || r.queued_at)}</td>
            <td>{r.started_by}<span className="quiet small"> · {r.trigger}</span></td>
            <td className="small">{what(r)}{r.command && <div><code className="quiet" title="The same run from the command line">{r.command}</code></div>}</td>
            <td><span className={cls(r.state)}>{STATE[r.state] || r.state}</span>
              {r.state === "error" && r.message && <div className="bad-text small">{r.message}</div>}
              {r.followed_up_by && <div className="ok-text small">followed up by run {r.followed_up_by}</div>}</td>
            <td className="num">{r.passed || ""}</td>
            <td className={`num${r.failed ? " bad-text" : ""}`}>{r.failed || ""}</td>
            <td className="num">{r.skipped || ""}</td>
            <td className="nowrap small">{took(r)}</td>
            <td className="small">{r.purged_at ? <span className="quiet">removed</span> : r.fixtures}</td>
            <td className="nowrap"><button className="linkish" onClick={() => onOpen(r.id)}>Results</button>
              {r.failed > 0 && !r.followed_up_by && <> · <RepeatButton run={r} busy={busy} onStarted={onRepeat} small /></>}
              {!open_(r) && <> · <button className="linkish" onClick={() => del(r)}>Delete</button></>}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </>
  );
}

// the functional health of a run and its ring (R2.35, owner, 12 Nov 2026): every check is critical or not
// (eax/testing/health.py); Not healthy when a critical one failed, Degraded when many non-critical ones failed or a
// critical one warns, else Healthy. Security findings are shown beside it, never counted against it.
const RING_COLOURS = { "critical failed": "#b42318", "non-critical failed": "#e8833a", warning: "#d4a72c", skipped: "#9aa3af", passed: "#2e7d4f" };
const HEALTH_CLASS = { Healthy: "ok", Degraded: "amber", "Not healthy": "bad", "Not known": "off" };
function Ring({ parts, size = 120, label }) {
  const total = parts.reduce((a, [, n]) => a + n, 0) || 1;
  const r = size / 2 - 10, c = 2 * Math.PI * r, cx = size / 2;
  let at = 0;
  const failed = parts.filter(([k]) => k.endsWith("failed")).reduce((a, [, n]) => a + n, 0);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${failed} failed of ${total}`}>
      <circle cx={cx} cy={cx} r={r} fill="none" stroke="#e5e7eb" strokeWidth="16" />
      {parts.filter(([, n]) => n > 0).map(([k, n]) => {
        const f = n / total;
        const el = <circle key={k} cx={cx} cy={cx} r={r} fill="none" stroke={RING_COLOURS[k]} strokeWidth="16"
          strokeDasharray={`${f * c} ${c}`} strokeDashoffset={-at * c} transform={`rotate(-90 ${cx} ${cx})`}><title>{`${k}: ${n}`}</title></circle>;
        at += f;
        return el;
      })}
      <text x={cx} y={cx - 2} textAnchor="middle" fontSize="20" fontWeight="700" fill="currentColor">{failed}</text>
      <text x={cx} y={cx + 15} textAnchor="middle" fontSize="11" fill="currentColor">failed</text>
    </svg>
  );
}
export function HealthPanel({ h }) {
  if (!h) return null;
  const c = h.critical, nc = h.non_critical;
  const parts = [["critical failed", c.failed], ["non-critical failed", nc.failed], ["warning", c.warning + nc.warning],
    ["skipped", c.skipped + nc.skipped], ["passed", c.passed + nc.passed]];
  return (
    <div className="test-health">
      <Ring parts={parts} label="Every check" />
      <div>
        <p><span className={`rag ${HEALTH_CLASS[h.health] || "off"}`}>Functional health: {h.health}</span></p>
        <p className="small">{h.reason}</p>
        <p className="small quiet">Critical: {c.passed} passed, {c.failed} failed, {c.warning} warnings, {c.skipped} skipped ·
          Non-critical: {nc.passed} passed, {nc.failed} failed, {nc.warning} warnings · Security (not counted in the health):
          {" "}{h.security.failed} failed, {h.security.warning} warnings</p>
        <p className="small test-legend">{Object.entries(RING_COLOURS).map(([k, col]) => <span key={k}><i style={{ background: col }} />{k}</span>)}</p>
      </div>
    </div>
  );
}

// a repeat beside the run it repeats (R2.36): each check then and now
function RepeatPanel({ rp }) {
  if (!rp) return null;
  return (
    <div className="test-repeat-panel">
      <p><b>Repeat of self-test {rp.of}</b>{rp.with_warnings ? " (with its warnings)" : ""}: {rp.fixed} of {rp.checks.length} now pass
        {rp.all_passed ? `; self-test ${rp.of} is marked as followed up.` : "."}</p>
      <table className="grid-table test-results"><thead><tr><th>Suite</th><th>Check</th><th>Then</th><th>Now</th></tr></thead>
        <tbody>{rp.checks.map((c) => (
          <tr key={`${c.suite} ${c.name}`}><td className="small">{c.suite}</td><td className="small">{c.name}</td>
            <td><span className={cls(c.then)}>{OUTCOME[c.then] || c.then}</span></td>
            <td><span className={cls(c.now)}>{OUTCOME[c.now] || c.now}</span></td></tr>))}</tbody></table>
    </div>
  );
}

function RunDetail({ id, onClose, busy, onRepeat }) {
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
      actions={<>{run && <RepeatButton run={run} busy={busy} onStarted={onRepeat} />}
        <button onClick={() => rep("html")}>Download report (HTML)</button><button onClick={() => rep("xlsx")}>Excel</button>
        <button onClick={onClose}>Close</button></>}>
      {err && <p className="status bad">{err}</p>}
      {run && <p className="small">{what(run)} · {run.message} · version {run.version || "?"} · started by {run.started_by} ({run.trigger})
        {" "}{fmtDateTime(run.started_at || run.queued_at)}{run.purged_at ? ` · fixtures removed by ${run.purged_by}` : ""}</p>}
      {run?.followed_up_by && <p className="status ok small">Followed up: every check that failed here passes in run {run.followed_up_by}.</p>}
      {d?.health && <HealthPanel h={d.health} />}
      <RepeatPanel rp={d?.repeat} />
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
        {/* one click for all of it, as `eax test clean` (R2.0.1, D593); each run also removes what earlier runs left */}
        {!run && <button className="danger" disabled={!rows.length} onClick={() => { setSel(new Set(rows.map((r) => r.id))); setAsk(true); }}>
          Delete all test data</button>}
        {err && <span className="small bad-text">{err}</span>}
      </div>
      {task && <p className={`small ${task.status === "failed" ? "bad-text" : ""}`}>Purging: {task.status}{task.progress != null ? ` ${task.progress}%` : ""}
        {task.note ? ` · ${task.note}` : ""}{task.message ? ` · ${task.message}` : ""}</p>}
      <p className="quiet small">Every test run removes the test data earlier runs left before it starts; delete it here at any time
        (the same as <code>eax test clean</code>).</p>
      {rows.length === 0 ? <p className="quiet">No test data: nothing to remove.</p> : (
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
        <Modal title={`Delete ${chosen.length} item(s) of test data for good?`} onClose={() => setAsk(false)}
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
