// Administration > Containers (owner, 6 Nov 2026): every container of the installation; one at a time its state,
// health checks, properties (image, mounts, ports, networks, environment in clear text, restart policy, limits), what
// it uses now, its logs, an interactive terminal (D214) and a command line (IT and Super Admins; EAX_CONTAINER_CONSOLE=off
// switches both off). Every command, and the start and end of every terminal, is in the audit trail.
import { useEffect, useRef, useState } from "react";
import { StartupCell, StartupLine, TONE, WORD, containerStartup } from "./StartupStatus";
import { apiFetch, can } from "./auth";
import { fmtDateTime } from "./fmt";
import { useApi } from "./ModelViews";

const mb = (b) => (b == null ? "" : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);

const SUMMARY = "";

export default function ContainerConsole() {
  const { data, error } = useApi("/api/v1/admin/containers");
  const [pick, setPick] = useState(SUMMARY);
  const list = data?.containers || [];
  return (
    <div className="containers">
      <p className="quiet">Every container of this installation. Choose one to see its properties and logs, open a terminal in it
        or run a command (IT and Super Admins; recorded in the audit trail).</p>
      {error && <p className="status bad">{error}</p>}
      <StartupLine />
      <ApiServers />
      <div className="ct-layout">
        <ul className="ct-list" role="listbox" aria-label="Containers">
          <li role="option" aria-selected={pick === SUMMARY} className={`ct-summary-item${pick === SUMMARY ? " on" : ""}`}>
            <button className="linkish" onClick={() => setPick(SUMMARY)}>☰ Summary</button>
          </li>
          {list.map((c) => (
            <li key={c.id} role="option" aria-selected={pick === (c.key || c.service)} className={pick === (c.key || c.service) ? "on" : ""}>
              <button className="linkish" onClick={() => setPick(c.key || c.service)} title={c.name}>
                <span className={`dot ${TONE[containerStartup(c)]}`} />
                {c.key || c.service}<span className="quiet small"> {WORD[containerStartup(c)]}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="ct-main">{pick === SUMMARY ? <Summary onPick={setPick} /> : <ContainerView key={pick} service={pick} />}</div>
      </div>
    </div>
  );
}

function since(iso) {
  const t = Date.parse(iso || "");
  if (!t || t < 1e12) return "";
  const m = Math.round((Date.now() - t) / 60000);
  return m < 60 ? `${m} min` : m < 2880 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} days`;
}

// Summary (owner, 6 Nov 2026): every container in one table, what it uses now, and the total at the bottom
function verdict(c) {
  if (c.oom_killed || c.health === "unhealthy" || (c.state !== "running" && c.exit_code)) return ["red", "Problem"];
  if (c.state !== "running") return ["off", "Not running"];
  if (c.health === "starting" || c.restarts > 0 || c.memory_percent > 90) return ["amber", "Warning"];
  return ["green", "Healthy"];
}

function Summary({ onPick }) {
  const [h, setH] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true); setErr("");
    try { setH(await apiFetch("/api/v1/admin/services/health")); } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  useEffect(() => { load(); }, []);
  const cs = h?.containers || [];
  const run = cs.filter((c) => c.state === "running");
  const sum = (k) => run.reduce((a, c) => a + (c[k] || 0), 0);
  const limit = Math.max(0, ...run.map((c) => c.memory_limit_bytes || 0));   // without limits each one shows the machine's memory
  const n = { green: 0, amber: 0, red: 0, off: 0 };
  cs.forEach((c) => { n[verdict(c)[0]] += 1; });
  return (
    <div>
      <div className="row-gap filters">
        <h3 style={{ margin: 0 }}>All containers</h3>
        <button onClick={load} disabled={busy}>{busy ? "Reading..." : "↻ Check again"}</button>
        {h && <span className="quiet small">Checked {new Date(h.checked_at * 1000).toLocaleTimeString()}</span>}
        {["red", "amber", "green", "off"].filter((k) => n[k]).map((k) => <span key={k} className={`rag ${k}`}>{n[k]} {k === "off" ? "not running" : k === "green" ? "healthy" : k === "amber" ? "warning" : "problem"}</span>)}
      </div>
      {err && <p className="status bad">{err}</p>}
      {h?.helper && <p className="status bad small">{h.helper}</p>}
      {h?.problems?.length > 0 && <p className="status warn small">Not everything could be read: {h.problems.join("; ")}</p>}
      {!h && !err && <p className="quiet">Reading...</p>}
      {h && (
        <div className="table-scroll">
          <table className="grid-table ct-sum">
            <thead><tr><th>Container</th><th title="Start-up (D255): up, starting or down; 1st: starts first (needed to sign in), 2nd: after it, in the background">Start-up</th><th>Health</th><th>State</th><th>Docker health</th><th className="num">CPU</th>
              <th className="num">Memory</th><th className="num">% of limit</th><th className="num">Processes</th>
              <th className="num">Disk (own layer)</th><th className="num">Volumes</th><th>Up for</th><th className="num">Restarts</th></tr></thead>
            <tbody>
              {cs.map((c) => {
                const [lv, txt] = verdict(c);
                const up = c.state === "running";
                return (
                  <tr key={c.id}>
                    <td><button className="linkish" onClick={() => onPick(c.key || c.service)} title={c.name}>{c.key || c.service}</button></td>
                    <td><StartupCell c={c} /></td>
                    <td><span className={`rag ${lv}`}>{txt}</span></td>
                    <td className={up ? "" : "quiet"}>{c.state}{!up && c.exit_code ? ` (exit ${c.exit_code})` : ""}{c.oom_killed ? <span className="bad-text"> · out of memory</span> : null}</td>
                    <td className={c.health === "healthy" ? "ok-text" : c.health === "unhealthy" ? "bad-text" : "quiet"}>{up && c.health !== "none" ? c.health : ""}</td>
                    <td className="num">{up && c.cpu_percent != null ? `${c.cpu_percent.toFixed(1)}%` : ""}</td>
                    <td className="num">{up ? mb(c.memory_bytes) : ""}</td>
                    <td className={`num${c.memory_percent > 90 ? " warn-text" : ""}`}>{up && c.memory_percent != null ? `${c.memory_percent.toFixed(1)}%` : ""}</td>
                    <td className="num">{up ? c.pids ?? "" : ""}</td>
                    <td className="num">{mb(c.layer_bytes)}</td>
                    <td className="num">{c.volume_bytes ? mb(c.volume_bytes) : ""}</td>
                    <td>{up ? since(c.started_at) : ""}</td>
                    <td className={`num${c.restarts > 0 ? " warn-text" : ""}`}>{c.restarts ?? ""}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr>
                <th>Total</th>
                <th colSpan="4">{run.length} of {cs.length} running</th>
                <th className="num">{sum("cpu_percent").toFixed(1)}%</th>
                <th className="num">{mb(sum("memory_bytes"))}</th>
                <th className="num">{limit ? `${((sum("memory_bytes") / limit) * 100).toFixed(1)}%` : ""}</th>
                <th className="num">{sum("pids")}</th>
                <th className="num">{mb(cs.reduce((a, c) => a + (c.layer_bytes || 0), 0))}</th>
                <th className="num">{mb(cs.reduce((a, c) => a + (c.volume_bytes || 0), 0))}</th>
                <th />
                <th className="num">{cs.reduce((a, c) => a + (c.restarts || 0), 0)}</th>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
      <p className="quiet small">CPU is per core: 100% is one core busy, so the total can pass 100% on a machine with several cores. The
        memory total is set against the largest limit, the machine's memory when no container has a limit of its own. Disk counts
        the running and stopped containers; a volume shared by two containers is counted twice.</p>
    </div>
  );
}

function ContainerView({ service }) {
  const [view, setView] = useState("properties");
  const { data: d, error } = useApi(`/api/v1/admin/containers/${service}`);
  return (
    <div>
      <h3>{service} {d && <span className={`ct-state ${d.state.running ? "up" : "down"}`}>{d.state.status}</span>}
        {d && d.health.status !== "none" && <span className={`ct-state ${d.health.status === "healthy" ? "up" : "warn"}`}>{d.health.status}</span>}</h3>
      <div className="tabs small-tabs" role="tablist">
        {[["properties", "Properties"], ["logs", "Logs"], ["terminal", "Terminal"], ["run", "Run a command"]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={view === k} className={view === k ? "tab on" : "tab"} onClick={() => setView(k)}>{l}</button>
        ))}
      </div>
      {error && <p className="status bad">{error}</p>}
      {view === "properties" && (d ? <Properties d={d} /> : !error && <p className="quiet">Loading...</p>)}
      {view === "logs" && <Logs service={service} />}
      {view === "terminal" && <Terminal service={service} on={d?.console} running={d?.state.running} />}
      {view === "run" && <Run service={service} on={d?.console} running={d?.state.running} />}
    </div>
  );
}

function Rows({ rows }) {
  return (
    <table className="grid-table ct-props"><tbody>
      {rows.filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => <tr key={k}><th>{k}</th><td>{v}</td></tr>)}
    </tbody></table>
  );
}

function Properties({ d }) {
  const s = d.state;
  const n = d.now || {};
  return (
    <div className="ct-props-wrap">
      <h4>State</h4>
      <Rows rows={[["Status", s.status], ["Started", fmtDateTime(s.started_at)], ["Finished", s.running ? "" : fmtDateTime(s.finished_at)],
        ["Exit code", s.running ? "" : String(s.exit_code)], ["Out of memory", s.oom_killed ? "yes: it was stopped for using too much memory" : ""],
        ["Restarts", String(s.restarts)], ["Restart policy", d.restart_policy], ["Error", s.error]]} />
      <h4>Health check</h4>
      <Rows rows={[["Status", d.health.status], ["Test", d.health.test && <code>{d.health.test}</code>],
        ["Failing in a row", d.health.failing_streak ? String(d.health.failing_streak) : ""]]} />
      {d.health.log.length > 0 && (
        <table className="grid-table"><thead><tr><th>Checked</th><th>Exit</th><th>Output</th></tr></thead>
          <tbody>{d.health.log.map((x, i) => <tr key={i}><td className="small">{fmtDateTime(x.start)}</td><td>{x.exit_code}</td>
            <td><pre className="ct-pre">{x.output}</pre></td></tr>)}</tbody></table>
      )}
      <h4>Now</h4>
      <Rows rows={[["CPU", n.cpu_percent == null ? "" : `${n.cpu_percent.toFixed(1)}%`],
        ["Memory", n.memory_bytes == null ? "" : `${mb(n.memory_bytes)} of ${mb(n.memory_limit_bytes)} (${(n.memory_percent || 0).toFixed(1)}%)`],
        ["Processes", n.pids == null ? "" : String(n.pids)], ["Network in / out", n.net_io], ["Disk read / written", n.block_io],
        ["Disk: its own layer", mb(n.layer_bytes)], ["Disk: its volumes", n.volume_bytes ? mb(n.volume_bytes) : ""]]} />
      <h4>Container</h4>
      <Rows rows={[["Name", d.name], ["Id", <code key="i">{d.id}</code>], ["Image", <code key="m">{d.image}</code>], ["Image id", d.image_id],
        ["Created", fmtDateTime(d.created)], ["Command", d.command && <code>{d.command}</code>], ["Working folder", d.working_dir],
        ["Runs as", d.user], ["Memory limit", d.limits.memory_bytes ? mb(d.limits.memory_bytes) : "none"],
        ["CPU limit", d.limits.cpus ? `${d.limits.cpus} CPUs` : "none"]]} />
      <h4>Mounts</h4>
      <table className="grid-table"><thead><tr><th>Type</th><th>Source</th><th>Inside the container</th><th>Access</th></tr></thead>
        <tbody>{d.mounts.map((m, i) => <tr key={i}><td>{m.type}</td><td className="small"><code>{m.source}</code></td>
          <td className="small"><code>{m.destination}</code></td><td>{m.read_only ? "read only" : "read and write"}</td></tr>)}
          {!d.mounts.length && <tr><td colSpan="4" className="quiet">None</td></tr>}</tbody></table>
      <h4>Network</h4>
      <Rows rows={[...d.networks.map((x) => [x.name, `${x.ip || ""}${x.aliases.length ? ` · ${x.aliases.join(", ")}` : ""}`]),
        ...d.ports.map((p) => [`Port ${p.container}`, p.host ? `published on ${p.host}` : "inside the network only"])]} />
      <details><summary>Environment ({d.environment.length}, clear text)</summary>
        <pre className="ct-pre">{d.environment.join("\n")}</pre></details>
      <details><summary>Compose labels</summary>
        <pre className="ct-pre">{Object.entries(d.labels).map(([k, v]) => `${k}=${v}`).join("\n")}</pre></details>
    </div>
  );
}

function Logs({ service }) {
  const [tail, setTail] = useState(300);
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef(null);
  async function load() {
    setBusy(true); setErr("");
    try { setData(await apiFetch(`/api/v1/admin/containers/${service}/logs?tail=${tail}`)); } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  useEffect(() => { load(); }, [tail]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [data]);
  const lines = (data?.lines || []).filter((l) => !q || l.toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <div className="row-gap filters">
        <select value={tail} onChange={(e) => setTail(Number(e.target.value))} aria-label="Lines">
          {[100, 300, 1000, 5000].map((n) => <option key={n} value={n}>Last {n} lines</option>)}
        </select>
        <input type="search" placeholder="Filter" value={q} onChange={(e) => setQ(e.target.value)} />
        <button onClick={load} disabled={busy}>{busy ? "Reading..." : "↻ Refresh"}</button>
        <span className="quiet small">{lines.length} line{lines.length === 1 ? "" : "s"}</span>
      </div>
      {err && <p className="status bad">{err}</p>}
      <pre className="ct-log" ref={box}>{lines.join("\n")}</pre>
    </div>
  );
}

function Run({ service, on, running }) {
  const [cmd, setCmd] = useState("");
  const [runs, setRuns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [cwd, setCwd] = useState("");   // the folder the console is in: cd carries over like a terminal
  const [past, setPast] = useState({ list: [], at: -1 });   // commands typed, for the up and down arrows
  const box = useRef(null);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [runs]);
  if (!can("system.operate")) return <p className="quiet">Running commands inside a container is for IT and Super Admins.</p>;
  if (on === false) return <p className="quiet">Running commands is switched off on this installation (EAX_CONTAINER_CONSOLE=off in the config file).</p>;
  async function go() {
    if (!cmd.trim()) return;
    setBusy(true); setErr("");
    try {
      if (cmd.trim() === "clear") { setRuns([]); setCmd(""); setBusy(false); return; }
      const out = await apiFetch(`/api/v1/admin/containers/${service}/exec`, { method: "POST", body: JSON.stringify({ command: cmd, cwd }) });
      setRuns([...runs, { ...out, in: cwd }].slice(-30)); setCmd(""); setCwd(out.cwd || cwd);
      setPast({ list: [...past.list.filter((x) => x !== cmd), cmd].slice(-50), at: -1 });
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  return (
    <div>
      <p className="quiet small">Runs commands inside {service} as its own user, 60 seconds at most each. <code>cd</code> carries over to the
        next command like a terminal; variables set with <code>export</code> do not (each command is its own shell), and programs that
        wait for typing (<code>vi</code>, <code>top</code>, <code>psql</code> without <code>-c</code>) cannot be used. ↑ and ↓ bring back earlier
        commands; <code>clear</code> empties the screen. Recorded in the audit trail.
        {!running && <strong> The container is not running.</strong>}</p>
      <div className="ct-terminal" ref={box}>
        {runs.map((r, i) => (
          <div key={i}>
            <div className="ct-cmd"><span className="ct-cwd">{r.in || "~"}</span> $ {r.command} <span className="quiet">· exit {r.exit_code ?? "timed out"} · {r.ms} ms{r.cut ? " · output cut to the last 200 kB" : ""}</span></div>
            <pre>{r.output}</pre>
          </div>
        ))}
        {!runs.length && <div className="quiet">Try: <code>pwd</code>, <code>ls -la</code>, <code>cd eax</code>, <code>df -h</code>, <code>ps aux</code>, <code>env | sort</code></div>}
      </div>
      <div className="row-gap ct-input">
        <span className="ct-prompt"><span className="ct-cwd">{cwd || "~"}</span> $</span>
        <input value={cmd} onChange={(e) => setCmd(e.target.value)} disabled={busy || !running} placeholder="A command to run inside the container"
          autoFocus onKeyDown={(e) => {
            if (e.key === "Enter") go();
            else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
              e.preventDefault();
              const n = past.list.length;
              if (!n) return;
              const at = e.key === "ArrowUp" ? (past.at < 0 ? n - 1 : Math.max(0, past.at - 1)) : (past.at < 0 ? -1 : past.at + 1);
              if (at < 0 || at >= n) { setPast({ ...past, at: -1 }); setCmd(""); } else { setPast({ ...past, at }); setCmd(past.list[at]); }
            }
          }} />
        <button className="primary" disabled={busy || !running || !cmd.trim()} onClick={go}>{busy ? "Running..." : "Run"}</button>
      </div>
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}

// An interactive terminal in the container (owner, 6 Nov 2026, D214): a real shell (bash where the container has it),
// so vi, top, psql, tab completion and Ctrl+C work. The API checks the person and gives a one-time address; the screen
// connects to it with a WebSocket. It ends with exit, End session or closing the page, or after the idle time without
// typing. Only its start and end are recorded.
function Terminal({ service, on, running }) {
  const box = useRef(null);
  const sess = useRef(null);
  const [state, setState] = useState("idle");   // idle, opening, open, ended
  const [err, setErr] = useState("");
  const [why, setWhy] = useState("");
  const [idle, setIdle] = useState(null);
  useEffect(() => () => end(true), []);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!can("system.operate")) return <p className="quiet">Terminals in containers are for IT and Super Admins.</p>;
  if (on === false) return <p className="quiet">Terminals are switched off on this installation (EAX_CONTAINER_CONSOLE=off in the config file).</p>;

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
      const t = await apiFetch(`/api/v1/admin/containers/${service}/terminal`, { method: "POST", body: JSON.stringify({ cols: term.cols, rows: term.rows }) });
      setIdle(t.idle_minutes);
      const ws = new window.WebSocket(`${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${t.url}`);
      ws.binaryType = "arraybuffer";
      const send = (m) => { if (ws.readyState === 1) ws.send(JSON.stringify(m)); };
      ws.onopen = () => { setState("open"); send({ t: "r", cols: term.cols, rows: term.rows }); term.focus(); };
      ws.onmessage = (e) => {
        if (typeof e.data !== "string") { term.write(new Uint8Array(e.data)); return; }
        try { const m = JSON.parse(e.data); if (m.t === "exit") setWhy(m.reason || "ended"); } catch { /* not ours */ }
      };
      ws.onerror = () => setErr("The terminal could not connect: check that the operations helper runs (Administration > Services).");
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
          ? <button className="danger" onClick={() => end()}>■ End session</button>
          : <button className="primary" onClick={open} disabled={!running || state === "opening"}>
            {state === "opening" ? "Opening..." : state === "ended" ? "▶ Open a new terminal" : "▶ Open a terminal"}</button>}
        <span className="quiet small">
          {state === "open" ? <>Connected to {service}. Ends with <code>exit</code>, End session or leaving this page{idle ? `, or after ${idle} minutes without typing` : ""}.</>
            : state === "ended" ? <>The terminal has ended{why ? `: ${why}` : ""}.</>
              : <>A shell inside {service} as its own user: <code>vi</code>, <code>top</code>, <code>psql</code>, tab completion and Ctrl+C work. The start and end are recorded in the audit trail.</>}
          {!running && <strong> The container is not running.</strong>}
        </span>
      </div>
      {err && <p className="status bad">{err}</p>}
      <div className={`ct-xterm${state === "idle" ? " empty" : ""}`} ref={box} />
    </div>
  );
}


// the API and job servers (D249): copies of the api container; each answers API calls (nginx spreads them across all)
// and runs background jobs. Super and IT Admins add or remove them at once, without a restart.
function ApiServers() {
  const [data, setData] = useState(null);
  const [msg, setMsg] = useState("");
  const [gen, setGen] = useState(0);
  useEffect(() => {
    let live = true;
    apiFetch("/api/v1/admin/servers").then((d) => live && setData(d)).catch((e) => live && setMsg(e.message));
    return () => { live = false; };
  }, [gen]);
  useEffect(() => {          // while servers start or stop, read again every few seconds
    if (!data?.busy) return undefined;
    const t = setTimeout(() => setGen((g) => g + 1), 3000);
    return () => clearTimeout(t);
  }, [data, gen]);
  if (!data) return msg ? <p className="status bad small">{msg}</p> : null;
  const running = data.servers.filter((s) => s.state === "running").length;
  async function set(count) {
    setMsg("");
    try { const r = await apiFetch("/api/v1/admin/servers", { method: "PUT", body: JSON.stringify({ count }) }); setMsg(r.message); setGen((g) => g + 1); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <section className="q-card api-servers">
      <h3>API and job servers</h3>
      <p className="quiet small">Copies of the api container: each answers API calls (nginx spreads them across all of them) and runs background
        jobs such as data quality measurements. Add one when jobs queue up or the screens slow down; removing one lets the jobs it runs finish
        first. The first server is never removed. The number is kept in the config file, so a restart keeps it.</p>
      <div className="row-gap">
        <button onClick={() => set(data.wanted - 1)} disabled={data.busy || data.wanted <= 1} title="Remove a server" aria-label="Remove a server">−</button>
        <b>{data.wanted}</b> wanted · {running} running
        <button onClick={() => set(data.wanted + 1)} disabled={data.busy || data.wanted >= data.max} title="Add a server" aria-label="Add a server">+</button>
        {data.busy && <span className="small"><span className="spinner" aria-hidden="true" /> {data.job?.what}...</span>}
      </div>
      {data.job && !data.busy && (data.job.log?.length > 0 || data.job.error) && <p className={`small ${data.job.error ? "status bad" : "quiet"}`}>{data.job.error || data.job.log.join(" · ")}</p>}
      {msg && <p className="small status warn">{msg}</p>}
      <table className="grid-table">
        <thead><tr><th>#</th><th>Container</th><th>State</th><th>Health</th><th>Started</th></tr></thead>
        <tbody>{data.servers.map((s) => (
          <tr key={s.id}><td>{s.number}{s.number === 1 && <span className="quiet small"> (first)</span>}</td><td className="small"><b>{s.key || `api-${s.number}`}</b> <span className="quiet">{s.name}</span></td>
            <td>{s.state}</td><td>{s.health || "-"}</td><td className="small">{s.started ? fmtDateTime(s.started) : "-"}</td></tr>
        ))}</tbody>
      </table>
    </section>
  );
}
