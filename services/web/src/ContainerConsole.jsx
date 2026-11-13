// Administration > Containers (owner, 6 Nov 2026): every container of the installation; one at a time its state,
// health checks, properties (image, mounts, ports, networks, environment in clear text, restart policy, limits), what
// it uses now, its logs, an interactive terminal (D214) and a command line (IT and Super Admins; EAX_CONTAINER_CONSOLE=off
// switches both off). Every command, and the start and end of every terminal, is in the audit trail.
import FileExplorer from "./FileExplorer";
import PlatformNotice from "./PlatformNotice";
import { useEffect, useRef, useState } from "react";
import { StartupCell, StartupLine, TONE, WORD, containerStartup } from "./StartupStatus";
import { apiFetch, can } from "./auth";
import { fmtDateTime } from "./fmt";
import { useApi } from "./ModelViews";

const mb = (b) => (b == null ? "" : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);

const SUMMARY = "";

// what each container is for (owner, 13 Nov 2026: "add what each container is for in the table"), in plain words
export const PURPOSE = {
  db: "PostgreSQL: the database (models, projects, settings, sign-in, reports, documents' index)",
  "db-standby": "A copy of the database kept in step, ready to take over (scale-out)",
  "dms-broker": "Valkey: the queue Documents uses for its background work",
  keycloak: "Keycloak: sign-in, users and roles",
  api: "The EA Explorer API and its job runner: everything the screens, MCP and eax ask for",
  operations: "The operations service: housekeeping, deployments and updates (/api/v1/operations)",
  personal: "The personal data service: notifications, requests, favourites, settings (/api/v1/me)",
  library: "The reference and enterprise libraries' service",
  views: "The drawn views' service (pictures of a model)",
  reports: "Reports (Superset): dashboards and charts",
  "reports-init": "Sets up Reports once at the start, then stops (a stop here is normal)",
  dms: "Documents (Mayan EDMS): the project documents and their files",
  drawio: "draw.io: the diagram editor for drawn views",
  web: "The screens (the web pages people use)",
  backup: "Backups and restores, on request and on schedule",
  proxy: "The front door (nginx): HTTPS, and which address goes to which service",
  ops: "The operations helper: reaches Docker for Containers, restarts, backups, the terminal and alerts",
  setup: "Makes the certificates and first settings at the start, then stops (a stop here is normal)",
  testrunner: "The self-test, started when a test runs",
  "testrunner-service": "The self-test runner that waits for runs on a managed platform",
};
// only current and relevant containers unless asked (owner, 13 Nov 2026: "Dead are not unless asked for"): running or
// starting ones, and any that stopped with an error (a problem to see); a set-up step that finished, a switched-off
// service and Docker's dead containers only with "Show stopped"
export function isCurrent(c) {
  const st = containerStartup(c);
  if ((c.state || "").toLowerCase() === "dead") return false;
  if (ONE_SHOT_DONE(c)) return false;
  return st !== "off";
}
const ONE_SHOT_DONE = (c) => ["setup", "reports-init"].includes(c.service) && (c.state || "").toLowerCase() === "exited"
  && (c.exit_code ?? 0) === 0;

export const purposeOf = (c) => PURPOSE[c.service] || PURPOSE[String(c.key || "").replace(/-\d+$/, "")] || "";

export default function ContainerConsole() {
  const { data, error } = useApi("/api/v1/admin/containers");
  const [pick, setPick] = useState(SUMMARY);
  const [showAll, setShowAll] = useState(false);
  const every = data?.containers || [];
  const list = showAll ? every : every.filter(isCurrent);
  const hidden = every.length - every.filter(isCurrent).length;
  return (
    <div className="containers">
      <PlatformNotice />
      <p className="quiet">Every container of this installation. Choose one to see its properties and logs, open a terminal in it
        or run a command (IT and Super Admins; recorded in the audit trail).</p>
      {error && <p className="status bad">{error}</p>}
      <StartupLine />
      <ApiServers />
      <label className="small" title="Set-up steps that finished, switched-off services and Docker's dead containers">
        <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Show stopped
        {hidden > 0 ? ` (${hidden} hidden)` : ""}</label>
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
        <div className="ct-main">{pick === SUMMARY ? <Summary onPick={setPick} showAll={showAll} /> : <ContainerView key={pick} service={pick} />}</div>
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

// the file systems (owner, 8 Nov 2026): the disk under Docker, the work folder and the backups folder: size, used, free;
// and what Docker keeps on its disk. Over 80% used: amber; over 90%: red.
const gb = (b) => (b == null ? "" : b >= 1e12 ? `${(b / 1e12).toFixed(2)} TB` : `${(b / 1e9).toFixed(1)} GB`);
function FileSystems({ h }) {
  const fs = h.filesystems || [];
  if (!fs.length) return null;
  return (
    <div className="fs-wrap">
      <h3>File systems</h3>
      <table className="grid-table fs-table">
        <thead><tr><th>File system</th><th>Holds</th><th className="num">Size</th><th className="num">Used</th><th className="num">Free</th><th style={{ width: "28%" }}>Used</th></tr></thead>
        <tbody>{fs.map((f) => (
          <tr key={f.path}>
            <td><b>{f.label}</b><div className="small quiet mono">{f.path}</div></td>
            <td className="small">{f.holds}{f.same_as && <div className="quiet">on the same disk as {f.same_as}</div>}</td>
            {f.error ? <td colSpan={4} className="bad-text small">Not readable: {f.error}</td> : <>
              <td className="num">{gb(f.total_bytes)}</td><td className="num">{gb(f.used_bytes)}</td><td className="num">{gb(f.free_bytes)}</td>
              <td><div className={`fs-bar ${f.level}`} title={`${f.used_percent}% used${f.inodes_used_percent != null ? ` · ${f.inodes_used_percent}% of its file entries used` : ""}`}>
                <span style={{ width: `${Math.min(100, f.used_percent)}%` }} /></div>
                <span className={`small rag ${f.level}`}>{f.used_percent}%</span></td></>}
          </tr>
        ))}</tbody>
      </table>
      {(h.docker_disk || []).length > 0 && (
        <details className="small"><summary>What Docker keeps on its disk</summary>
          <table className="grid-table small"><thead><tr><th>Kind</th><th className="num">How many</th><th className="num">In use</th><th className="num">Size</th><th>Could be freed</th></tr></thead>
            <tbody>{h.docker_disk.map((k) => <tr key={k.kind}><td>{k.kind}</td><td className="num">{k.count}</td><td className="num">{k.active}</td><td className="num">{gb(k.bytes)}</td><td>{k.reclaimable}</td></tr>)}</tbody></table>
        </details>
      )}
    </div>
  );
}

function Summary({ onPick, showAll = false }) {
  const [h, setH] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true); setErr("");
    try { setH(await apiFetch("/api/v1/admin/services/health")); } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  useEffect(() => { load(); }, []);
  const cs = (h?.containers || []).filter((c) => showAll || isCurrent(c));
  const run = cs.filter((c) => c.state === "running");
  const sum = (k) => run.reduce((a, c) => a + (c[k] || 0), 0);
  const limit = Math.max(0, ...run.map((c) => c.memory_limit_bytes || 0));   // without limits each one shows the machine's memory
  const n = { green: 0, amber: 0, red: 0, off: 0 };
  cs.forEach((c) => { n[verdict(c)[0]] += 1; });
  const fsBad = (h?.filesystems || []).filter((f) => !f.same_as && (f.level === "red" || f.level === "amber"));
  return (
    <div>
      <div className="row-gap filters">
        <h3 style={{ margin: 0 }}>Containers and file systems</h3>
        <button onClick={load} disabled={busy}>{busy ? "Reading..." : "↻ Check again"}</button>
        {h && <span className="quiet small">Checked {new Date(h.checked_at * 1000).toLocaleTimeString()}</span>}
        {["red", "amber", "green", "off"].filter((k) => n[k]).map((k) => <span key={k} className={`rag ${k}`}>{n[k]} {k === "off" ? "not running" : k === "green" ? "healthy" : k === "amber" ? "warning" : "problem"}</span>)}
        {fsBad.map((f) => <span key={f.path} className={`rag ${f.level}`}>{f.label} {f.used_percent}% full</span>)}
      </div>
      {err && <p className="status bad">{err}</p>}
      {h?.helper && <p className="status bad small">{h.helper}</p>}
      {h?.problems?.length > 0 && <p className="status warn small">Not everything could be read: {h.problems.join("; ")}</p>}
      {!h && !err && <p className="quiet">Reading...</p>}
      {h && <FileSystems h={h} />}
      {h && (
        <div className="table-scroll">
          <h3>Containers</h3>
          <table className="grid-table ct-sum">
            <thead><tr><th>Container</th><th>What it is for</th><th title="Start-up (D255): up, starting or down; 1st: starts first (needed to sign in), 2nd: after it, in the background">Start-up</th><th>Health</th><th>State</th><th>Docker health</th><th className="num">CPU</th>
              <th className="num">Memory</th><th className="num">% of limit</th><th className="num">Processes</th>
              <th className="num">Disk (own layer)</th><th className="num">Volumes</th><th>Up for</th><th className="num">Restarts</th></tr></thead>
            <tbody>
              {cs.map((c) => {
                const [lv, txt] = verdict(c);
                const up = c.state === "running";
                return (
                  <tr key={c.id}>
                    <td><button className="linkish" onClick={() => onPick(c.key || c.service)} title={c.name}>{c.key || c.service}</button></td>
                    <td className="small ct-purpose">{purposeOf(c)}</td>
                    <td><StartupCell c={c} /></td>
                    <td><span className={`rag ${lv}`}>{txt}</span></td>
                    <td className={up ? "" : "quiet"}>{c.state}{!up && c.exit_code ? ` (exit ${c.exit_code})` : ""}{c.oom_killed ? <span className="bad-text"> · out of memory</span> : null}</td>
                    <td className={c.health === "healthy" ? "ok-text" : c.health === "unhealthy" ? "bad-text" : "quiet"}>{up && c.health !== "none" ? c.health : ""}</td>
                    <td className="num" title={c.cpu_cores != null ? `${c.cpu_cores} of ${h.host_cpus || "?"} cores` : ""}>{up && c.cpu_percent != null ? `${c.cpu_percent.toFixed(1)}%` : ""}</td>
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
                <th colSpan="5">{run.length} of {cs.length} running</th>
                <th className="num" title={h.host_cpus ? `${sum("cpu_cores").toFixed(2)} of ${h.host_cpus} cores in use` : ""}>{sum("cpu_percent").toFixed(1)}%{h.host_cpus ? <div className="small quiet">{sum("cpu_cores").toFixed(1)} of {h.host_cpus} cores</div> : null}</th>
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
      <p className="quiet small">CPU is a share of the whole machine{h?.host_cpus ? ` (${h.host_cpus} cores)` : ""}: 100% is every core busy, so the total stays
        between 0% and 100%; hover a figure for the cores in use (R2.21). The
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
      {purposeOf({ service, key: service }) && <p className="quiet small">{purposeOf({ service, key: service })}</p>}
      <div className="tabs small-tabs" role="tablist">
        {[["properties", "Properties"], ["logs", "Logs"], ["terminal", "Terminal"], ["files", "Files"]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={view === k} className={view === k ? "tab on" : "tab"} onClick={() => setView(k)}>{l}</button>
        ))}
      </div>
      {error && <p className="status bad">{error}</p>}
      {view === "properties" && (d ? <Properties d={d} /> : !error && <p className="quiet">Loading...</p>)}
      {view === "logs" && <Logs service={service} />}
      {view === "terminal" && <Terminal service={service} on={d?.console} running={d?.state.running} />}
      {view === "files" && (d?.state.running === false ? <p className="quiet">The container is not running: start it to see its files.</p>
        : <FileExplorer service={service} on={d?.console} />)}
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
      <Rows rows={[["CPU", n.cpu_percent == null ? "" : `${n.cpu_percent.toFixed(1)}% of the machine${n.cpu_cores != null ? ` (${n.cpu_cores} of ${d.host_cpus || "?"} cores)` : ""}`],
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
  const [mode, setMode] = useState("now");     // now: Docker's last lines; kept: the daily files on disk (R2.31, R2.32)
  return (
    <div>
      <div className="row-gap small-tabs" role="tablist" aria-label="Which logs">
        <button role="tab" aria-selected={mode === "now"} className={mode === "now" ? "tab on" : "tab"} onClick={() => setMode("now")}>Last lines</button>
        <button role="tab" aria-selected={mode === "kept"} className={mode === "kept" ? "tab on" : "tab"} onClick={() => setMode("kept")}>Kept by day</button>
        <button role="tab" aria-selected={mode === "own"} className={mode === "own" ? "tab on" : "tab"} onClick={() => setMode("own")}>eax and log backups</button>
      </div>
      {mode === "now" ? <LastLines service={service} /> : mode === "kept" ? <KeptLogs service={service} /> : <OwnLogs />}
    </div>
  );
}

function LastLines({ service }) {
  const [tail, setTail] = useState(300);
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const box = useRef(null);
  async function load() {
    setBusy(true); setErr("");
    try { setData(await apiFetch(`/api/v1/admin/containers/${service}/logs?tail=${tail}`)); } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  useEffect(() => { load(); }, [tail]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {                        // live: new lines every 5 seconds, until paused (R2.31)
    if (!live) return undefined;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [live, tail]);                        // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [data]);
  const lines = (data?.lines || []).filter((l) => !q || l.toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <div className="row-gap filters">
        <select value={tail} onChange={(e) => setTail(Number(e.target.value))} aria-label="Lines">
          {[100, 300, 1000, 5000].map((n) => <option key={n} value={n}>Last {n} lines</option>)}
        </select>
        <input type="search" placeholder="Filter (words or a request id)" value={q} onChange={(e) => setQ(e.target.value)} />
        <button onClick={load} disabled={busy}>{busy ? "Reading..." : "↻ Refresh"}</button>
        <label className="small"><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> Live</label>
        <button onClick={() => download(`${service}-last-${tail}.log`, lines)} disabled={!lines.length}>Download</button>
        <span className="quiet small">{lines.length} line{lines.length === 1 ? "" : "s"}</span>
      </div>
      {err && <p className="status bad">{err}</p>}
      <pre className="ct-log" ref={box}>{lines.map((l, i) => <LogLine key={i} line={l} q={q} />)}</pre>
    </div>
  );
}

function download(name, lines) {
  const url = URL.createObjectURL(new Blob([lines.join("\n") + "\n"], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const LEVEL_CLASS = { error: "log-error", warning: "log-warning", debug: "log-debug", info: "" };
function levelOf(line) {
  const l = line.toLowerCase();
  if (/\b(error|exception|traceback|critical|fatal|failed)\b/.test(l)) return "error";
  if (/\b(warn|warning)\b/.test(l)) return "warning";
  if (/\bdebug\b/.test(l)) return "debug";
  return "info";
}

// one line, coloured by its level, the words searched for highlighted
function LogLine({ line, q, level, service }) {
  const lv = level || levelOf(line);
  const text = service ? `${service.padEnd(10)} ${line}` : line;
  if (!q) return <div className={LEVEL_CLASS[lv]}>{text}</div>;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return <div className={LEVEL_CLASS[lv]}>{text}</div>;
  return <div className={LEVEL_CLASS[lv]}>{text.slice(0, i)}<mark>{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</div>;
}

// eax's own logs (work/logs) and the log backups (work/backups/logs), opened the same way (R2.31)
function OwnLogs() {
  const { data: list, error } = useApi("/api/v1/admin/logs/own");
  const [pick, setPick] = useState("");            // "own:<name>" or "zip:<name>"
  const [member, setMember] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [asked, setAsked] = useState(0);            // Enter in the search: read again with the words
  useEffect(() => {
    if (!pick) return;
    setErr("");
    const [kind, name] = [pick.slice(0, 3), pick.slice(4)];
    const url = kind === "own" ? `/api/v1/admin/logs/own?name=${encodeURIComponent(name)}`
      : `/api/v1/admin/logs/own?backup=${encodeURIComponent(name)}${member ? `&member=${encodeURIComponent(member)}` : ""}`;
    apiFetch(`${url}&q=${encodeURIComponent(q)}&page=${page}`).then(setData).catch((e) => setErr(e.message));
  }, [pick, member, page, asked]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <p className="status bad">{error}</p>;
  if (!list) return <p>Loading...</p>;
  const lines = data?.lines || [];
  return (
    <div>
      <div className="row-gap filters">
        <select aria-label="Log" value={pick} onChange={(e) => { setPick(e.target.value); setMember(""); setPage(0); setData(null); }}>
          <option value="">Choose a log…</option>
          <optgroup label="eax's own logs (work/logs)">{list.own.map((f) => <option key={f.name} value={`own:${f.name}`}>{f.name}</option>)}</optgroup>
          <optgroup label="Log backups (work/backups/logs)">{list.backups.map((f) => <option key={f.name} value={`zip:${f.name}`}>{f.name}</option>)}</optgroup>
        </select>
        {data?.members && <select aria-label="File in the backup" value={member} onChange={(e) => { setMember(e.target.value); setPage(0); }}>
          <option value="">Choose a file…</option>{data.members.map((m) => <option key={m} value={m}>{m}</option>)}</select>}
        <input type="search" placeholder="Words or a request id" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { setPage(0); setAsked((n) => n + 1); } }} />
        <button onClick={() => download(`${(pick || "log").slice(4)}${member ? `-${member.replace(/\//g, "_")}` : ""}.log`, lines.map((l) => l.line))} disabled={!lines.length}>Download</button>
      </div>
      {err && <p className="status bad">{err}</p>}
      {data && data.total !== undefined && <p className="quiet small">{data.total} line(s){data.pages > 1 && <> · page {data.page + 1} of {data.pages}{" "}
        <button className="small" disabled={data.page === 0} onClick={() => setPage(data.page - 1)}>‹ Earlier</button>{" "}
        <button className="small" disabled={data.page >= data.pages - 1} onClick={() => setPage(data.page + 1)}>Later ›</button></>}</p>}
      <pre className="ct-log">{lines.map((l, i) => <LogLine key={i} line={l.line} level={l.level} q={q} />)}</pre>
    </div>
  );
}

// the logs kept on disk, one file a day per container (R2.31, R2.32): one or several containers merged by time, by level
// and time of day, the words searched for highlighted, a page of 1,000 lines at a time, live, downloaded; and the logs
// backed up or cleaned (R2.30)
function KeptLogs({ service }) {
  const { data: files } = useApi("/api/v1/admin/logs/files");
  const all = [...new Set((files?.files || []).map((f) => f.service))].sort();
  const days = [...new Set((files?.files || []).map((f) => f.day))].sort().reverse();
  const [pick, setPick] = useState([service]);
  const [day, setDay] = useState("");
  const [level, setLevel] = useState("");
  const [q, setQ] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [page, setPage] = useState(null);       // null: the last page
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [live, setLive] = useState(false);
  const [note, setNote] = useState("");
  const theDay = day || days[0] || "";
  async function load(p = page) {
    if (!theDay || !pick.length) return;
    setErr("");
    const ask = (n) => apiFetch(`/api/v1/admin/logs/read?services=${encodeURIComponent(pick.join(","))}&day=${theDay}`
      + `&level=${level}&q=${encodeURIComponent(q)}&since=${since}&until=${until}&page=${n}`);
    try {
      let d = await ask(p === null ? 0 : p);
      if (p === null && d.pages > 1) d = await ask(d.pages - 1);
      setData(d);
    } catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, [theDay, pick.join(","), level, since, until, page]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!live) return undefined;
    const t = setInterval(() => load(null), 5000);
    return () => clearInterval(t);
  }, [live, theDay, pick.join(","), level, q, since, until]);   // eslint-disable-line react-hooks/exhaustive-deps
  async function keep(what) {
    setNote("");
    if (what === "clean") {
      const d = window.prompt("Delete the logs and log backups older than how many days? (cannot be undone)", "30");
      if (!d) return;
      try { const o = await apiFetch("/api/v1/admin/logs/clean", { method: "POST", body: JSON.stringify({ days: Number(d) }) });
        setNote(`Deleted ${o.deleted.length} file(s) older than ${o.kept_days} days.`); } catch (e) { setNote(e.message); }
      return;
    }
    try { const o = await apiFetch("/api/v1/admin/logs/backup", { method: "POST", body: "{}" });
      setNote(`Backed up ${o.files} file(s) to work/backups/logs/${o.file}.`); } catch (e) { setNote(e.message); }
  }
  const lines = data?.lines || [];
  if (files && !(files.files || []).length) {
    return <p className="quiet">No logs kept on disk yet: the operations helper writes every container's log here once a minute (logs/, or EAX_LOGS_DIR).</p>;
  }
  return (
    <div>
      <div className="row-gap filters">
        <select multiple value={pick} onChange={(e) => setPick([...e.target.selectedOptions].map((o) => o.value))}
          aria-label="Containers" size={Math.min(4, Math.max(2, all.length))}>
          {all.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={theDay} onChange={(e) => { setDay(e.target.value); setPage(null); }} aria-label="Day">
          {days.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select value={level} onChange={(e) => { setLevel(e.target.value); setPage(null); }} aria-label="Level">
          <option value="">Every level</option><option value="info">Info and worse</option>
          <option value="warning">Warnings and errors</option><option value="error">Errors only</option>
        </select>
        <input type="time" value={since} onChange={(e) => setSince(e.target.value)} aria-label="Since" title="Since" />
        <input type="time" value={until} onChange={(e) => setUntil(e.target.value)} aria-label="Until" title="Until" />
        <input type="search" placeholder="Words or a request id" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { setPage(null); load(null); } }} />
        <label className="small"><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> Live</label>
        <button onClick={() => download(`${pick.join("+")}-${theDay}.log`, lines.map((l) => `${l.service} ${l.line}`))} disabled={!lines.length}>Download</button>
        <button onClick={() => keep("backup")}>Back up logs</button>
        <button onClick={() => keep("clean")}>Clean logs…</button>
      </div>
      {note && <p className="status">{note}</p>}
      {err && <p className="status bad">{err}</p>}
      {data && <p className="quiet small">{data.total} line(s){data.pages > 1 && <> · page {data.page + 1} of {data.pages}{" "}
        <button className="small" disabled={data.page === 0} onClick={() => setPage(data.page - 1)}>‹ Earlier</button>{" "}
        <button className="small" disabled={data.page >= data.pages - 1} onClick={() => setPage(data.page + 1)}>Later ›</button></>}</p>}
      <pre className="ct-log">{lines.map((l, i) => <LogLine key={i} line={l.line} level={l.level} q={q} service={pick.length > 1 ? l.service : ""} />)}</pre>
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

// Files: an Explorer-style view, in FileExplorer.jsx (R2.18, R2.58, R2.60).
