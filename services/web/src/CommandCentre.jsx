// System admin > Command centre (D554): every eax command from a web page, for IT Admins and Super Admins.
//   Commands  every command grouped as in eaxcli/help.txt; choosing one opens a guided form (what it does, what it keeps
//             or deletes, each option explained), shows the exact command line, and runs it after a confirm; the
//             output streams live. Commands that stop EA Explorer say so; the ones that delete everything need a Super
//             Admin, the installation's name typed and "I understand", and take a backup first; host-only commands show
//             the command to type on the machine itself with a Copy button.
//   Console   a terminal in the browser taking eax commands as typed ("eax status", "backup nightly") and eax console's
//             numbered menu; nothing but eax commands.
//   History   every run and console session: who, when, the command, its exit code, its output or transcript.
//   Schedules scheduled eax commands (D559): a cron in the platform, kept in persist/schedules.json so they survive a
//             reset (D558); presets (every night, every week, every hour, once) or a cron expression, in the
//             installation's time zone; a wipe command needs a Super Admin and the strong confirm once; the one-click
//             demo reset (clean-restart laptop every night at 02:00, with a banner).
import PlatformNotice from "./PlatformNotice";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, can } from "./auth";
import { fmtDateTime } from "./fmt";

const KIND = {
  run: ["", ""],
  offline: ["warn", "Stops or restarts EA Explorer"],
  wipe: ["bad", "Deletes everything"],
  host: ["quiet", "Runs on the machine itself"],
  interactive: ["quiet", "Interactive: in the Console"],
};

export default function CommandCentre({ route }) {
  const sub = (route || "").split("/")[3] || "commands";
  if (!can("system.operate")) return <p className="quiet">The Command centre is for IT Admins and Super Admins.</p>;
  return (
    <div className="cc">
      <PlatformNotice />
      <div className="tabs sub" role="tablist" aria-label="Command centre">
        {[["commands", "Commands"], ["console", "Console"], ["history", "History"], ["schedules", "Schedules"]].map(([k, l]) => (
          <a key={k} href={`#/admin/commands/${k}`} role="tab" aria-selected={sub === k} className={`tab${sub === k ? " on" : ""}`}>{l}</a>
        ))}
      </div>
      {sub === "console" ? <Console /> : sub === "history" ? <History /> : sub === "schedules" ? <Schedules /> : <Commands />}
    </div>
  );
}

// ---------------------------------------------------------------- Commands: the catalogue and the guided form
function Commands() {
  const [cat, setCat] = useState(null);
  const [err, setErr] = useState("");
  const [find, setFind] = useState("");
  const [pick, setPick] = useState(null);
  const [run, setRun] = useState(null);
  useEffect(() => { apiFetch("/api/v1/admin/commands").then(setCat).catch((e) => setErr(e.message)); }, []);
  const groups = useMemo(() => {
    if (!cat) return [];
    const q = find.trim().toLowerCase();
    return cat.groups.map((g) => ({ ...g, commands: g.commands.filter((c) => !q
      || c.names.some((n) => n.includes(q)) || c.summary.toLowerCase().includes(q)) })).filter((g) => g.commands.length);
  }, [cat, find]);
  if (err) return <p className="status bad">{err}</p>;
  if (!cat) return <p><span className="spinner" aria-hidden="true" /> Reading the commands…</p>;
  if (run) return <RunView run={run} onBack={() => { setRun(null); setPick(null); }} />;
  if (pick) return <Guided cmd={pick} cat={cat} onBack={() => setPick(null)} onStarted={setRun} />;
  return (
    <div>
      <p className="quiet">Every <code>eax</code> command, as in <code>eax help</code>. Choose one: a short form asks for its options,
        shows the exact command and runs it on {cat.installation ? <strong>{cat.installation}</strong> : "this installation"}.
        Prefer typing? Use the <a href="#/admin/commands/console">Console</a>.</p>
      <label className="cc-find">Find a command <input type="search" value={find} onChange={(e) => setFind(e.target.value)} placeholder="backup, restore, logs…" /></label>
      {groups.map((g) => (
        <section key={g.title} className="cc-group">
          <h3>{g.title}</h3>
          {g.notes.map((n) => <p key={n} className="quiet small">{n}</p>)}
          <div className="cc-cards">
            {g.commands.map((c) => {
              const [tone, label] = KIND[c.kind] || KIND.run;
              const mayNot = c.role === "super-admin" && !cat.you?.super_admin;
              return (
                <button key={c.name} className={`cc-card ${tone}`} onClick={() => setPick(c)} disabled={mayNot}
                  title={mayNot ? "Super Admins only" : c.summary}>
                  <code>eax {c.names.join(" | ")}</code>
                  <span>{c.summary}</span>
                  {label && <span className={`cc-kind ${tone}`}>{label}{mayNot ? " · Super Admins only" : ""}</span>}
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

function commandLine(cmd, values) {
  const argv = [cmd.name];
  for (const p of cmd.params) {
    const v = values[p.key];
    if (v === undefined || v === "" || v === false) continue;
    if (p.type === "flag") argv.push(p.key);
    else if (p.type === "flags") argv.push(v);
    else if (p.type === "flag-value") argv.push(values[`${p.key}:flag`] || p.flags[0], v);
    else if (p.type === "words") argv.push(...String(v).split(/\s+/).filter(Boolean));
    else argv.push(v);
  }
  return argv;
}

function Guided({ cmd, cat, onBack, onStarted }) {
  const [values, setValues] = useState({});
  const [typed, setTyped] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const argv = commandLine(cmd, values);
  const line = `eax ${argv.join(" ")}`;
  const set = (k, v) => setValues((x) => ({ ...x, [k]: v }));
  const wipe = cmd.kind === "wipe";
  const ready = !wipe || (understood && typed.trim() === cat.installation);

  async function go() {
    setBusy(true); setErr("");
    try {
      const out = await apiFetch("/api/v1/admin/commands/run", { method: "POST",
        body: JSON.stringify({ argv, confirm: wipe ? { typed, understood } : undefined }) });
      onStarted({ ...out, cmd });
    } catch (e) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className="cc-guided">
      <p><button className="linkish" onClick={onBack}>← All commands</button></p>
      <h2><code>eax {cmd.names.join(" | ")}</code></h2>
      <p><strong>{cmd.summary}</strong></p>
      {cmd.detail.length > 0 && <details open={cmd.kind !== "run"}><summary>What it does</summary><pre className="cc-help">{cmd.detail.join("\n")}</pre></details>}
      {cmd.examples.length > 0 && <p className="small quiet">Examples: {cmd.examples.map((e) => <code key={e} className="cc-ex">{e}</code>)}</p>}

      {cmd.kind === "host" ? (
        <div className="status warn cc-host">
          <p><strong>This command runs on the machine itself, not from this page.</strong> {cmd.host_why}</p>
          <p>Type it in a terminal in the installation folder:</p>
          <div className="toolbar"><code className="cc-line">{line}</code>
            <button onClick={() => { navigator.clipboard?.writeText(line).then(() => setCopied(true)).catch(() => setCopied(false)); }}>{copied ? "Copied" : "Copy"}</button></div>
        </div>
      ) : cmd.kind === "interactive" ? (
        <p className="status warn">eax {cmd.name} asks questions as it goes: <a href="#/admin/commands/console">open the Console</a> and type <code>{cmd.name}</code>.</p>
      ) : (
        <>
          {cmd.params.length > 0 && <fieldset className="cc-form"><legend>Options</legend>
            {cmd.params.map((p) => <Param key={p.key} p={p} values={values} set={set} />)}
          </fieldset>}
          <p className="small">It runs: <code className="cc-line">{line}</code></p>
          {cmd.kind === "offline" && <p className="status warn">This stops or restarts EA Explorer: this page stops answering while it runs and
            comes back when EA Explorer is up again. {cmd.name === "stop" ? "After stop, start it again on the machine with eax up." : ""}</p>}
          {wipe && <WipeConfirm argv={argv} cat={cat} typed={typed} setTyped={setTyped} understood={understood} setUnderstood={setUnderstood} />}
          {err && <p className="status bad">{err}</p>}
          <div className="toolbar">
            <button className={wipe ? "danger" : "primary"} disabled={busy || !ready} onClick={go}>
              {busy ? "Starting…" : wipe ? "Back up, then delete everything" : `Run ${cmd.name}`}</button>
            <button onClick={onBack}>Cancel</button>
          </div>
        </>
      )}
    </div>
  );
}

function Param({ p, values, set }) {
  const label = p.type === "flag" ? p.key : p.type === "flags" ? p.choices.join(" or ") : p.type === "flag-value" ? p.flags.join(" / ") : p.placeholder || "value";
  if (p.type === "flag") {
    return <label className="cc-param"><input type="checkbox" checked={!!values[p.key]} onChange={(e) => set(p.key, e.target.checked)} /> <code>{p.key}</code></label>;
  }
  if (p.type === "flags") {
    return (
      <label className="cc-param">{label}
        <select value={values[p.key] || ""} onChange={(e) => set(p.key, e.target.value)}>
          <option value="">(none)</option>{p.choices.map((c) => <option key={c} value={c}>{c}</option>)}
        </select></label>
    );
  }
  const choices = p.type === "choice" || (p.type === "flag-value" && p.choices);
  return (
    <label className="cc-param">
      {p.type === "flag-value" && p.flags.length > 1
        ? <select aria-label="Which option" value={values[`${p.key}:flag`] || p.flags[0]} onChange={(e) => set(`${p.key}:flag`, e.target.value)}>
          {p.flags.map((f) => <option key={f}>{f}</option>)}</select>
        : <span>{p.type === "flag-value" ? <code>{label}</code> : label}{p.required ? " (needed)" : ""}</span>}
      {choices
        ? <select value={values[p.key] || ""} onChange={(e) => set(p.key, e.target.value)}>
          <option value="">{p.required ? "Choose…" : "(not given)"}</option>{p.choices.map((c) => <option key={c} value={c}>{c}</option>)}</select>
        : <input value={values[p.key] || ""} onChange={(e) => set(p.key, e.target.value)}
          placeholder={p.type === "words" ? `${p.placeholder} (several: separate with spaces)` : (p.choices || []).includes("latest") ? `${p.placeholder} (e.g. latest)` : p.placeholder} />}
    </label>
  );
}

function WipeConfirm({ argv, cat, typed, setTyped, understood, setUnderstood }) {
  const all = argv[0] !== "cleanup" || argv.includes("--all");
  return (
    <div className="status bad cc-wipe" role="alert">
      <p><strong>eax {argv.join(" ")} deletes everything:</strong></p>
      <ul>
        {all && <li>every database: the models, projects, people, settings, reports and the documents' records</li>}
        {all && <li>the document files and every Docker volume</li>}
        <li>the config file (work/eaexplorer.env), every log and the laptop data folders</li>
        <li><strong>every backup and restore log in work/backups</strong></li>
        {argv.includes("--certificate") && <li>the local certificate</li>}
      </ul>
      <p>First a fresh infrastructure backup is taken and copied to <code>persist/safety-backups/</code> beside the work folder, which no cleanup
        deletes. Copy it elsewhere afterwards if you want it off this machine. EA Explorer goes offline: open this address again in a few minutes.</p>
      <label>Type the installation's name, <strong>{cat.installation}</strong>, to confirm
        <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" /></label>
      <label className="cc-param"><input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} /> I understand that this deletes everything</label>
    </div>
  );
}

// ---------------------------------------------------------------- a run, live
function RunView({ run, onBack }) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState(null);
  const [offline, setOffline] = useState(false);
  const pos = useRef(0);
  const misses = useRef(0);
  useEffect(() => {
    let live = true;
    let timer;
    const tick = async () => {
      try {
        const d = await apiFetch(`/api/v1/admin/commands/runs/${run.id}?from=${pos.current}`);
        if (!live) return;
        misses.current = 0;
        setOffline(false);
        if (d.text) { pos.current = d.next; setText((t) => t + d.text); }
        setStatus(d.status);
        if (d.status?.state === "running" || d.running) timer = setTimeout(tick, 1000);
      } catch {
        if (!live) return;
        misses.current += 1;                 // the first answers may come before the run's record is written
        if (misses.current > 3) setOffline(true);
        timer = setTimeout(tick, misses.current > 3 ? 5000 : 1000);    // going down or coming back: keep asking
      }
    };
    tick();
    return () => { live = false; clearTimeout(timer); };
  }, [run.id]);
  const done = status && status.state !== "running";
  async function stop() {
    try { setStatus(await apiFetch(`/api/v1/admin/commands/runs/${run.id}/stop`, { method: "POST", body: "{}" })); } catch (e) { setText((t) => `${t}\n${e.message}\n`); }
  }
  return (
    <div className="cc-run">
      <p><button className="linkish" onClick={onBack}>← All commands</button></p>
      <h2><code>{run.command}</code></h2>
      <p className={`status ${!done ? "" : status.exit_code === 0 ? "ok" : "bad"}`}>
        {!done ? <><span className="spinner" aria-hidden="true" /> Running…</> : status.state === "stopped" ? "Stopped." : status.exit_code === 0 ? "Finished." : `Failed (exit code ${status.exit_code}).`}
        {status?.by && <span className="quiet small"> · {status.by}, {fmtDateTime(status.started)}</span>}
      </p>
      {offline && <p className="status warn">EA Explorer is not answering{run.goes_offline ? " (this command stops or restarts it)" : ""}: this page keeps
        asking every few seconds and carries on when it is back.{run.kind === "wipe" ? " After a delete-everything command, sign in again once it is back." : ""}</p>}
      {!done && run.cmd?.stoppable && <button onClick={stop}>■ Stop</button>}
      <pre className="cc-output" aria-live="polite">{text || "…"}</pre>
    </div>
  );
}

// ---------------------------------------------------------------- Console: eax commands as typed, and eax console's menu
function Console() {
  const box = useRef(null);
  const sess = useRef(null);
  const [state, setState] = useState("idle");
  const [err, setErr] = useState("");
  const [why, setWhy] = useState("");
  useEffect(() => () => end(true), []);   // eslint-disable-line react-hooks/exhaustive-deps

  function end(leaving = false) {
    const s = sess.current;
    if (!s) return;
    try { s.send({ t: "end" }); s.ws.close(1000); } catch { /* already closed */ }
    s.ro.disconnect();
    if (leaving) s.term.dispose();
  }

  async function open() {
    setErr(""); setWhy(""); setState("opening");
    try {
      if (sess.current) { end(); sess.current.term.dispose(); sess.current = null; }
      const [{ Terminal: XTerm }, { FitAddon }] = await Promise.all([import("@xterm/xterm"), import("@xterm/addon-fit")]);
      await import("@xterm/xterm/css/xterm.css");
      const term = new XTerm({ cursorBlink: true, scrollback: 5000, fontSize: 13,
        fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace", theme: { background: "#0d1117", foreground: "#e6edf3" } });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(box.current);
      fit.fit();
      const t = await apiFetch("/api/v1/admin/commands/console", { method: "POST", body: JSON.stringify({ cols: term.cols, rows: term.rows }) });
      const ws = new window.WebSocket(`${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${t.url}`);
      ws.binaryType = "arraybuffer";
      const send = (m) => { if (ws.readyState === 1) ws.send(JSON.stringify(m)); };
      ws.onopen = () => { setState("open"); send({ t: "r", cols: term.cols, rows: term.rows }); term.focus(); };
      ws.onmessage = (e) => {
        if (typeof e.data !== "string") { term.write(new Uint8Array(e.data)); return; }
        try { const m = JSON.parse(e.data); if (m.t === "exit") setWhy(m.reason || "ended"); } catch { /* not ours */ }
      };
      ws.onerror = () => setErr("The Console could not connect: check that the operations helper runs (System admin > Health).");
      ws.onclose = () => setState("ended");
      term.onData((d) => send({ t: "i", d }));
      term.onResize(({ cols, rows }) => send({ t: "r", cols, rows }));
      const ro = new ResizeObserver(() => { try { fit.fit(); } catch { /* hidden */ } });
      ro.observe(box.current);
      sess.current = { ws, term, ro, send };
    } catch (e) { setErr(e.message); setState("idle"); }
  }

  return (
    <div>
      <div className="row-gap filters">
        {state === "open"
          ? <button className="danger" onClick={() => end()}>■ End the Console</button>
          : <button className="primary" onClick={open} disabled={state === "opening"}>
            {state === "opening" ? "Opening…" : state === "ended" ? "▶ Open the Console again" : "▶ Open the Console"}</button>}
        <span className="quiet small">
          {state === "open" ? <>Type eax commands as on the machine (<code>status</code>, <code>backup nightly</code>, <code>help restore</code>); <code>console</code> opens the numbered menu; <code>exit</code> ends.</>
            : state === "ended" ? <>The Console has ended{why ? `: ${why}` : ""}. Its transcript is in <a href="#/admin/commands/history">History</a>.</>
              : <>Only eax commands run here, never a shell. Everything typed is kept with the session. Commands that delete everything ask for the installation's name and take a backup first.</>}
        </span>
      </div>
      {err && <p className="status bad">{err}</p>}
      <div className={`ct-xterm${state === "idle" ? " empty" : ""}`} ref={box} />
    </div>
  );
}

// ---------------------------------------------------------------- History
function History() {
  const [runs, setRuns] = useState(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(null);
  useEffect(() => { apiFetch("/api/v1/admin/commands/runs").then((d) => setRuns(d.runs)).catch((e) => setErr(e.message)); }, []);
  if (err) return <p className="status bad">{err}</p>;
  if (!runs) return <p><span className="spinner" aria-hidden="true" /> Reading the history…</p>;
  if (open) return <HistoryDetail id={open} onBack={() => setOpen(null)} />;
  if (!runs.length) return <p className="quiet">No commands have been run from this page or the Console yet.</p>;
  return (
    <table className="grid-table">
      <thead><tr><th>When</th><th>Who</th><th>Command</th><th>Where</th><th>Result</th><th /></tr></thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id}>
            <td className="nowrap">{fmtDateTime(r.started)}</td>
            <td>{r.by}</td>
            <td><code>{r.command}</code></td>
            <td>{r.source === "console" ? "Console" : "Command centre"}</td>
            <td className={r.state === "failed" ? "bad" : r.state === "done" ? "ok" : ""}>
              {r.state === "running" ? "running" : r.state === "stopped" ? "stopped" : r.exit_code === 0 ? "done" : r.exit_code == null ? r.state : `exit code ${r.exit_code}`}</td>
            <td><button className="linkish" onClick={() => setOpen(r.id)}>{r.source === "console" ? "Transcript" : "Output"}</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function HistoryDetail({ id, onBack }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { apiFetch(`/api/v1/admin/commands/runs/${id}`).then(setD).catch((e) => setErr(e.message)); }, [id]);
  return (
    <div>
      <p><button className="linkish" onClick={onBack}>← History</button></p>
      {err && <p className="status bad">{err}</p>}
      {d && <>
        <h3><code>{d.status.command}</code></h3>
        <p className="quiet small">{d.status.by} · {fmtDateTime(d.status.started)}{d.status.ended ? ` to ${fmtDateTime(d.status.ended)}` : ""}</p>
        {d.commands?.length > 0 && <table className="grid-table small"><thead><tr><th>When</th><th>Typed</th><th>Result</th></tr></thead><tbody>
          {d.commands.map((c, i) => <tr key={i}><td className="nowrap">{fmtDateTime(c.at)}</td><td><code>{c.command || "(refused)"}</code></td>
            <td>{c.refused ? `refused: ${c.refused}` : c.exit_code === 0 ? "done" : `exit code ${c.exit_code}`}</td></tr>)}
        </tbody></table>}
        <pre className="cc-output">{(d.text || "").replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "")}</pre>
      </>}
    </div>
  );
}


// ---------------------------------------------------------------- Schedules (D559)
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const NOT_SCHEDULED = new Set(["logs", "debug"]);

function Schedules() {
  const [data, setData] = useState(null);
  const [cat, setCat] = useState(null);
  const [err, setErr] = useState("");
  const [adding, setAdding] = useState(null);       // null | "new" | "demo"
  const [msg, setMsg] = useState("");
  const load = () => apiFetch("/api/v1/admin/commands/schedules").then(setData).catch((e) => setErr(e.message));
  useEffect(() => { load(); apiFetch("/api/v1/admin/commands").then(setCat).catch(() => {}); }, []);
  async function change(s, what) {
    if (what === "remove" && !window.confirm(`Remove the schedule ${s.name}?`)) return;
    setErr(""); setMsg("");
    try {
      const out = await apiFetch(`/api/v1/admin/commands/schedules/${s.id}/${what}`, { method: "POST", body: "{}" });
      setMsg(what === "run" ? `Started: ${out.command}. See the History.` : `${s.name}: ${what === "remove" ? "removed" : what}.`);
      load();
    } catch (e) { setErr(e.message); }
  }
  if (err && !data) return <p className="status bad">{err}</p>;
  if (!data || !cat) return <p><span className="spinner" aria-hidden="true" /> Reading the schedules…</p>;
  if (adding) return <ScheduleForm cat={cat} demo={adding === "demo"} superAdmin={data.you?.super_admin}
    onDone={(text) => { setAdding(null); setMsg(text || ""); load(); }} />;
  return (
    <div className="cc-schedules">
      <p className="quiet">eax commands that run by themselves, in the installation's time zone (<strong>{data.time_zone}</strong>). They are kept in
        <code> persist/schedules.json</code>, which no reset deletes, so a demo can reset itself every night and still keep its schedule.
        Each run is in the <a href="#/admin/commands/history">History</a>.</p>
      {data.warning && <p className="status warn" role="alert">{data.warning}</p>}
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
      <div className="toolbar">
        <button className="primary" onClick={() => setAdding("new")}>+ New schedule</button>
        {data.you?.super_admin && <button onClick={() => setAdding("demo")} title="eax clean-restart laptop every night at 02:00, with a banner saying so">Demo reset every night…</button>}
      </div>
      {data.schedules.length === 0 ? <p className="quiet">No schedules yet.</p> : (
        <table className="grid-table cc-table">
          <thead><tr><th>Name</th><th>Command</th><th>When</th><th>On</th><th>Next run</th><th>Last run</th><th /></tr></thead>
          <tbody>
            {data.schedules.map((s) => {
              const last = s.last || {};
              return (
                <tr key={s.id} className={s.enabled ? "" : "is-retired"}>
                  <td><strong>{s.name}</strong>{s.wipe && <span className="pill bad" title="Deletes everything every time it runs"> deletes everything</span>}
                    <div className="small quiet">by {s.created_by}</div></td>
                  <td><code>{s.command}</code>{s.wipe && <div className="small quiet">{s.backup_first ? `backup first, newest ${s.keep} kept` : "no backup first"}</div>}</td>
                  <td>{s.when}</td>
                  <td>{s.enabled ? "On" : "Off"}</td>
                  <td>{s.next ? fmtDateTime(s.next) : "—"}</td>
                  <td>{last.state ? <><span className={`pill ${last.state === "done" ? "ok" : last.state === "failed" ? "bad" : "warn"}`}>{last.state}</span>
                    <span className="small"> {last.at ? fmtDateTime(last.at) : ""}</span>{last.note && <div className="small quiet">{last.note}</div>}
                    {last.run && <div className="small quiet">its output: History, run {last.run}</div>}</> : "—"}</td>
                  <td className="nowrap">
                    <button onClick={() => change(s, s.enabled ? "off" : "on")}>{s.enabled ? "Turn off" : "Turn on"}</button>{" "}
                    <button onClick={() => change(s, "run")} title="Run it now (asks nothing more: it was confirmed when made)">Run now</button>{" "}
                    <button className="linkish" onClick={() => change(s, "remove")}>Remove</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ScheduleForm({ cat, demo, superAdmin, onDone }) {
  const cmds = useMemo(() => cat.groups.flatMap((g) => g.commands)
    .filter((c) => !["host", "interactive"].includes(c.kind) && !NOT_SCHEDULED.has(c.name) && (c.kind !== "wipe" || superAdmin)), [cat, superAdmin]);
  const [name, setName] = useState(demo ? "Demo reset every night" : "");
  const [cmdName, setCmdName] = useState(demo ? "clean-restart" : "backup");
  const [values, setValues] = useState(demo ? { "laptop|server": "laptop" } : {});
  const [kind, setKind] = useState("nightly");
  const [time, setTime] = useState("02:00");
  const [day, setDay] = useState(1);
  const [minute, setMinute] = useState(0);
  const [at, setAt] = useState("");
  const [cron, setCron] = useState("");
  const [backup, setBackup] = useState(!demo);
  const [keep, setKeep] = useState(3);
  const [banner, setBanner] = useState(true);
  const [typed, setTyped] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const cmd = cmds.find((c) => c.name === cmdName) || cmds[0];
  const argv = demo ? ["clean-restart", "laptop"] : cmd ? commandLine(cmd, values) : [];
  const wipe = demo || cmd?.kind === "wipe";
  const ready = (!wipe || (understood && typed.trim() === cat.installation)) && argv.length;
  const words = kind === "nightly" ? `every day at ${time}` : kind === "weekly" ? `every ${DAYS[day]} at ${time}`
    : kind === "hourly" ? `every hour at :${String(minute).padStart(2, "0")}` : kind === "once" ? `once at ${at.replace("T", " ")}` : `cron ${cron}`;

  async function save() {
    setBusy(true); setErr("");
    const when = kind === "cron" ? { cron } : { preset: { kind, time_: time, day: Number(day), minute: Number(minute), at } };
    const body = demo ? { demo: true, at: time, confirm: { typed, understood } }
      : { name: name || undefined, argv, ...when, backup_first: backup, keep: Number(keep), banner: wipe && banner,
        confirm: wipe ? { typed, understood } : undefined };
    try {
      const out = await apiFetch("/api/v1/admin/commands/schedules", { method: "POST", body: JSON.stringify(body) });
      onDone(`Schedule made: ${out.name}, ${out.when}.`);
    } catch (e) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className="cc-guided">
      <p><button className="linkish" onClick={() => onDone("")}>← All schedules</button></p>
      <h2>{demo ? "Demo reset every night" : "New schedule"}</h2>
      {demo && <p>For a demonstration installation: every night <code>eax clean-restart laptop</code> deletes everything entered that day and
        starts again with the sample data. A banner tells everyone when it resets. No backup is taken first (there is nothing to keep).</p>}
      {!demo && <fieldset className="cc-form"><legend>What to run</legend>
        <label className="cc-param">Name <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Nightly backup" /></label>
        <label className="cc-param">Command <select value={cmd?.name || ""} onChange={(e) => { setCmdName(e.target.value); setValues({}); }}>
          {cmds.map((c) => <option key={c.name} value={c.name}>{c.name}: {c.summary}</option>)}</select></label>
        {cmd?.params.map((p) => <Param key={p.key} p={p} values={values} set={(k, v) => setValues((x) => ({ ...x, [k]: v }))} />)}
      </fieldset>}
      <fieldset className="cc-form"><legend>When</legend>
        {!demo && <label className="cc-param">Repeat <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="nightly">Every night at…</option><option value="weekly">Every week on…</option>
          <option value="hourly">Every hour</option><option value="once">Once at…</option><option value="cron">A cron expression</option></select></label>}
        {kind === "weekly" && !demo && <label className="cc-param">Day <select value={day} onChange={(e) => setDay(e.target.value)}>
          {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></label>}
        {(kind === "nightly" || kind === "weekly" || demo) && <label className="cc-param">At <input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></label>}
        {kind === "hourly" && !demo && <label className="cc-param">At minute <input type="number" min="0" max="59" value={minute} onChange={(e) => setMinute(e.target.value)} /></label>}
        {kind === "once" && !demo && <label className="cc-param">Date and time <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} /></label>}
        {kind === "cron" && !demo && <label className="cc-param">Cron <input value={cron} onChange={(e) => setCron(e.target.value)} placeholder="minute hour day month weekday, e.g. 0 2 * * *" /></label>}
        <p className="small">Runs <strong>{demo ? `every day at ${time}` : words}</strong> ({cat.installation ? "this installation's time zone" : "the time zone in the config file"}):
          <code className="cc-line"> eax {argv.join(" ")}</code></p>
      </fieldset>
      {wipe && <>
        <div className="status bad cc-wipe" role="alert">
          <p><strong>This deletes everything every time it runs</strong>: every database (models, projects, people, settings), the document files,
            the config file, the logs and every backup in work/backups. The schedule itself, the banner and the safety backups are in
            <code> persist/</code> and stay.</p>
          <label>Type the installation's name, <strong>{cat.installation}</strong>, to confirm (asked once, now)
            <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" /></label>
          <label className="cc-param"><input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} /> I understand that this deletes everything, every time</label>
        </div>
        {!demo && <fieldset className="cc-form"><legend>Safety</legend>
          <label className="cc-param"><input type="checkbox" checked={backup} onChange={(e) => setBackup(e.target.checked)} /> Take a safety backup first (into persist/safety-backups)</label>
          {backup && <label className="cc-param">Keep the newest <input type="number" min="1" max="20" value={keep} onChange={(e) => setKeep(e.target.value)} /> backups of this schedule</label>}
          <label className="cc-param"><input type="checkbox" checked={banner} onChange={(e) => setBanner(e.target.checked)} /> Show a banner saying when it resets</label>
        </fieldset>}
      </>}
      {err && <p className="status bad">{err}</p>}
      <div className="toolbar">
        <button className={wipe ? "danger" : "primary"} disabled={busy || !ready} onClick={save}>{busy ? "Saving…" : "Make the schedule"}</button>
        <button onClick={() => onDone("")}>Cancel</button>
      </div>
    </div>
  );
}
