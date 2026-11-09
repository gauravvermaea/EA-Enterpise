// System admin (build phase 10, D183; one of the five areas, D285): #/admin/<tab>
//   wizards      the system's admin tasks as wizards: access, backups and restores, services (SystemWizards.jsx, D284)
//   users        people, their roles, Keycloak role mapping (Users.jsx; User Admins)
//   application  application settings every screen, report and export follows (everyone sees; Super Admins change)
//   system       runtime system settings (Super Admins change), the optional services on or off (D191), start-up
//                settings (shown, secrets masked) and the copies of the config file, restart
//   health       the heartbeat and the containers
//   sql          the SQL window (IT Admins)
//   licences     the products and libraries and their licences
// The old addresses #/users, #/heartbeat and #/sql open the same tabs; #/admin/projects moved to #/project-admin/library.
import { lazy, Suspense, useEffect, useState } from "react";
import { apiFetch, can, needsRole } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { WebhooksPanel } from "./Notifications";
import { config } from "./config";
import { appSettings, fmtDate, fmtDateTime, fmtMoney, fmtNumber, setAppSettings } from "./fmt";

const Users = lazy(() => import("./Users"));
const Heartbeat = lazy(() => import("./Heartbeat"));
const Sql = lazy(() => import("./Sql"));
const ContainerConsole = lazy(() => import("./ContainerConsole"));
const AdminBackups = lazy(() => import("./Backups"));
const RestoresPage = lazy(() => import("./Restores"));
const SystemWizards = lazy(() => import("./SystemWizards"));
const QualityAdmin = lazy(() => import("./Quality").then((x) => ({ default: x.QualityAdmin })));

const TABS = [
  ["wizards", "Wizards", () => true, null],
  ["application", "Application settings", () => true, null],
  ["system", "System settings", () => can("system.operate") || can("settings.manage"), ["it-admin", "super-admin"]],
  ["users", "Users", () => can("users.read"), ["user-admin", "super-admin"]],
  ["health", "Health", () => true, null],
  ["containers", "Containers", () => can("system.operate"), ["it-admin", "super-admin"]],
  ["backups", "Backups", () => can("system.operate"), ["it-admin", "super-admin"]],
  ["restores", "Restores", () => can("system.operate"), ["it-admin", "super-admin"]],
  ["quality", "Quality", () => true, null],
  ["sql", "SQL", () => can("system.operate"), ["it-admin", "super-admin"]],
  ["licences", "Licences", () => true, null],
];

export function adminTab(route) {
  const r = route.replace(/^#/, "");
  if (r.startsWith("/users")) return ["users", route];
  if (r.startsWith("/heartbeat")) return ["health", route];
  if (r.startsWith("/sql")) return ["sql", route];
  const [, , tab, sub] = r.split("?")[0].split("/");
  return [tab || "wizards", sub ? `#/users/${sub}` : "#/users"];
}

export default function Admin({ route }) {
  const [tab, inner] = adminTab(route);
  if (tab === "projects") { window.location.replace("#/project-admin/library"); return null; }   // moved to Project admin (D285)
  const t = TABS.find(([k]) => k === tab) || TABS[0];
  return (
    <div className="admin">
      <h1>System admin</h1>
      <div className="tabs" role="tablist">
        {TABS.map(([k, l, ok, roles]) => (ok()
          ? <a key={k} href={`#/admin/${k}`} className={`tab${t[0] === k ? " on" : ""}`} role="tab" aria-selected={t[0] === k}>{l}</a>
          : <span key={k} className="tab nav-off" title={needsRole(roles)}>{l}</span>))}
      </div>
      <div className="tab-panel" role="tabpanel">
        <Suspense fallback={<p>Loading...</p>}>
          {!t[2]() ? <p className="status bad">{needsRole(t[3])}</p>
            : t[0] === "wizards" ? <SystemWizards />
            : t[0] === "users" ? <Users route={inner} />
              : t[0] === "health" ? <Heartbeat />
                : t[0] === "containers" ? <ContainerConsole />
                  : t[0] === "backups" ? <AdminBackups />
                    : t[0] === "restores" ? <RestoresPage route={route} />
                    : t[0] === "quality" ? <QualityAdmin />
                  : t[0] === "sql" ? <Sql />
                  : t[0] === "licences" ? <Licences />
                    : <Settings group={t[0]} />}
        </Suspense>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- settings (application and system)
function Field({ s, value, onChange, disabled }) {
  if (s.type === "bool") {
    return <label className="switch-label"><input type="checkbox" checked={!!value} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {" "}{value ? "On" : "Off"}</label>;
  }
  if (s.type === "choice") {
    return (
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        {s.choices.map((c) => <option key={c} value={c}>{c === " " ? "space" : c === "" ? "none" : c}</option>)}
      </select>
    );
  }
  if (s.type === "month") {
    return (
      <select value={value ?? 1} onChange={(e) => onChange(Number(e.target.value))} disabled={disabled}>
        {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
      </select>
    );
  }
  if (s.type === "int") {
    return <input type="number" min={s.range?.[0]} max={s.range?.[1]} value={value ?? ""} disabled={disabled} style={{ width: 120 }}
      onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />;
  }
  if (s.type === "timezone") {
    const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
    return zones.length ? (
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        {!zones.includes(value) && <option value={value}>{value}</option>}
        {zones.map((z) => <option key={z}>{z}</option>)}
      </select>
    ) : <input value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={disabled} />;
  }
  if (s.type === "url") {
    return <input type="url" value={value ?? ""} placeholder="https://" onChange={(e) => onChange(e.target.value)} disabled={disabled} style={{ width: 380 }} />;
  }
  return <input value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={disabled} style={{ width: 200 }} />;
}

// formats a sample with the settings being edited, before they are saved
function withPreview(values, fn) {
  const saved = appSettings();
  setAppSettings(values);
  try { return fn(); } finally { setAppSettings(saved); }
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function Settings({ group }) {
  const { data, error } = useApi("/api/v1/admin/settings");
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [restart, setRestart] = useState(false);
  useEffect(() => { setDraft({}); setMsg(""); setErr(""); }, [group]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const list = data[group] || [];
  const may = data.may_change;
  const value = (s) => (s.key in draft ? draft[s.key] : s.value);
  const changed = Object.keys(draft).filter((k) => list.some((s) => s.key === k && s.value !== draft[k]));
  async function save() {
    setBusy(true); setErr(""); setMsg("");
    try {
      const out = await apiFetch("/api/v1/admin/settings", { method: "PUT", body: JSON.stringify(Object.fromEntries(changed.map((k) => [k, draft[k]]))) });
      if (group === "application") setAppSettings(Object.fromEntries(Object.entries(out.values).filter(([k]) => data.application.some((s) => s.key === k))));
      setDraft({}); setMsg(out.note); refreshAll();
      if (changed.some((k) => k.startsWith("part_"))) setTimeout(() => window.location.reload(), 1500);   // the menus follow (D329)
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  const preview = { ...appSettings(), ...Object.fromEntries(data.application.map((s) => [s.key, value(s)])) };
  return (
    <div className="settings">
      <p className="quiet">
        {group === "application"
          ? "Every screen, report and export follows these, for everyone (D182): times are kept in UTC and shown in this time zone; money is in the base currency."
          : "Settings the running system reads: a change applies at once, without a restart."}
        {!may && " Only a Super Admin changes them."}
      </p>
      <table className="grid-table settings-table">
        <tbody>
          {list.map((s) => (
            <tr key={s.key} className={changed.includes(s.key) ? "changed-here" : ""}>
              <th>{s.label}</th>
              <td><Field s={s} value={value(s)} disabled={!may} onChange={(v) => setDraft((d) => ({ ...d, [s.key]: v }))} /></td>
              <td className="quiet small">{s.help}
                {s.key.startsWith("part_") && s.value && data.parts && !data.parts[s.key.slice(5)] && <div className="bad-text">Off for now: Projects is off.</div>}
                {s.modified_by && <div>Changed {fmtDateTime(s.modified_at)} by {s.modified_by}</div>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {group === "application" && (
        <p className="small settings-preview">Looks like: <b>{withPreview(preview, () => fmtDate("2026-03-31"))}</b> ·{" "}
          <b>{withPreview(preview, () => fmtNumber(1234567.89, 2))}</b> · <b>{withPreview(preview, () => fmtMoney(1250000))}</b>
          {" "}· financial year from {MONTHS[(preview.financial_year_start || 1) - 1]} · weeks start on {preview.first_day_of_week}
          <span className="quiet"> (saved changes show everywhere at once)</span></p>
      )}
      {may && (
        <div className="toolbar">
          <button className="primary" disabled={busy || !changed.length} onClick={save}>{busy ? "Saving..." : `Save ${changed.length || ""} change${changed.length === 1 ? "" : "s"}`}</button>
          {changed.length > 0 && <button className="linkish" onClick={() => setDraft({})}>Undo</button>}
        </div>
      )}
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
      {group === "system" && <Services />}
      {group === "system" && data.startup && <Startup s={data.startup} />}
      {group === "system" && can("system.operate") && <ConfigCopies />}
      {group === "system" && can("system.operate") && <WebhooksPanel />}
      {group === "system" && (
        <div className="merge-step">
          <h3>Restart the system</h3>
          <p className="quiet">Restarts every service of this installation through the operations helper: the database first, the web server last.
            Everyone is signed out for a minute or two; nothing is lost. Recorded in the audit trail and the change log.</p>
          {can("settings.manage") ? <button className="danger" onClick={() => setRestart(true)}>Restart the system...</button>
            : <p className="quiet small">{needsRole(["super-admin"])}</p>}
        </div>
      )}
      {restart && <RestartDialog onClose={() => setRestart(false)} />}
    </div>
  );
}

// The optional services (D191): on or off in the config file; switching one keeps a dated copy of the file first, then
// the operations helper starts or stops its containers (in the background: the table follows it)
// Windows-services style (owner, 5 Nov 2026): every service, the core ones too, with a status icon, its address and the
// same three buttons; a button that cannot apply (a core service cannot stop, a running one cannot start) is greyed out.
// Start on an optional service switches it on in the config file if it is off; Stop switches it off (D191).
const ADDRESS = {
  web: () => window.location.origin + "/",
  api: () => window.location.origin + "/api/docs",
  keycloak: () => `${config.keycloakUrl}/admin/${config.realm}/console/`,
  proxy: () => window.location.origin,
  reports: () => config.reportsUrl + "/",
  documents: () => config.docsUrl + "/",
  drawio: () => window.location.origin + "/drawio/",
  mcp: () => window.location.origin + "/mcp",
  change_log: () => window.location.origin + "/#/change-log",
};
// the MCP address is for language model clients, not a browser: it links to the MCP page (how to connect), with a copy button
const PAGE_OF = { mcp: "#/mcp" };

// the gear of the Windows services console, with a badge: running, stopped, off, busy, unknown
export function SvcIcon({ state }) {
  const badge = { running: "#1a7f37", stopped: "#cf222e", off: "#8c959f", busy: "#bf8700", unknown: "#8c959f" }[state];
  return (
    <svg className="svc-icon" width="22" height="22" viewBox="0 0 24 24" aria-label={state} role="img">
      <path fill="#57606a" d="M19.4 13a7.5 7.5 0 0 0 0-2l2.1-1.6-2-3.5-2.5 1a7.6 7.6 0 0 0-1.7-1L15 3.3h-4l-.4 2.6a7.6 7.6 0 0 0-1.7 1l-2.5-1-2 3.5L6.6 11a7.5 7.5 0 0 0 0 2l-2.1 1.6 2 3.5 2.5-1a7.6 7.6 0 0 0 1.7 1l.4 2.6h4l.4-2.6a7.6 7.6 0 0 0 1.7-1l2.5 1 2-3.5zM13 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7z" transform="translate(-1 0)" />
      <circle cx="18" cy="18" r="5.2" fill="#fff" />
      <circle cx="18" cy="18" r="4.2" fill={badge} />
      {state === "running" && <path d="M16.6 15.8v4.4l3.6-2.2z" fill="#fff" />}
      {state === "stopped" && <rect x="16.3" y="16.3" width="3.4" height="3.4" fill="#fff" />}
      {state === "off" && <rect x="15.6" y="17.4" width="4.8" height="1.3" fill="#fff" />}
      {state === "busy" && <circle cx="18" cy="18" r="1.4" fill="#fff" />}
    </svg>
  );
}

// times for the health columns
function since(iso) {
  const t = Date.parse(iso || "");
  if (!t || t < 1e12) return "";
  const m = Math.round((Date.now() - t) / 60000);
  return m < 60 ? `${m} min` : m < 2880 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} days`;
}
const CHECK_OF = { documents: ["documents", "documents_broker"], api: ["api", "api_jobs"], change_log: ["api_jobs"] };

// health now (owner, 6 Nov 2026): one green, amber or red verdict per service, with what matters for a container in
// columns of their own: the health check's response time, the container's state and Docker health, how long it has
// been up and how often it restarted. Red: a check is down, a container that should run is not, Docker says
// unhealthy, or it was stopped for running out of memory. Amber: a check warns or answers slower than a second, it is
// still starting, or it restarted. Grey: switched off. CPU, memory and disk are on Administration > Containers.
export function rate(s, h) {
  if (!h) return null;
  const checks = (CHECK_OF[s.key] || [s.key]).map((k) => h.checks[k]).filter(Boolean);
  const cs = (h.containers || []).filter((c) => s.containers.includes(c.service) && c.service !== "reports-init");
  const red = []; const amber = [];
  for (const c of checks) {
    if (c.status === "down") red.push(`${c.name}: ${c.detail}`);
    else if (c.status === "warning") amber.push(`${c.name}: ${c.detail}`);
    else if (c.status !== "off" && c.response_ms > 1000) amber.push(`${c.name} answered in ${c.response_ms} ms`);
  }
  for (const c of cs) {
    if (c.oom_killed) red.push(`${c.service} was stopped for running out of memory`);
    if (c.state !== "running" && s.on !== false) red.push(`${c.service} is ${c.state}${c.exit_code ? ` (exit code ${c.exit_code})` : ""}`);
    if (c.state === "running" && c.health === "unhealthy") red.push(`${c.service}: Docker says unhealthy`);
    if (c.health === "starting") amber.push(`${c.service} is still starting`);
    if (c.restarts > 0) amber.push(`${c.service} restarted ${c.restarts} time${c.restarts === 1 ? "" : "s"}`);
  }
  for (const p of h.problems || []) if (cs.some((c) => p.includes(c.service))) amber.push(p);
  const off = s.on === false && !cs.some((c) => c.state === "running");
  const level = off ? "off" : red.length ? "red" : amber.length ? "amber" : checks.length || cs.length ? "green" : "unknown";
  return { level, reasons: [...red, ...amber], checks, cs };
}
const LEVEL = { green: "Healthy", amber: "Warning", red: "Problem", off: "Off", unknown: "Not known" };

function HealthCells({ s, h }) {
  const r = rate(s, h);
  if (!r) return <><td className="quiet small">checking...</td><td /><td /><td /><td /></>;
  const { level, reasons, checks, cs } = r;
  return (
    <>
      <td className="nowrap"><span className={`rag ${level}`} title={reasons.join("\n") || LEVEL[level]}>{LEVEL[level]}</span>
        {reasons.length > 0 && <div className="small svc-reasons">{reasons.slice(0, 3).map((x) => <div key={x}>{x}</div>)}
          {reasons.length > 3 && <div className="quiet">and {reasons.length - 3} more</div>}</div>}</td>
      <td className="small nowrap">{checks.map((c) => (
        <div key={c.name} title={`${c.name}: ${c.detail}${c.target ? ` (${c.target})` : ""}`}>
          {c.status === "off" ? <span className="quiet">off</span>
            : <span className={c.status === "down" ? "bad-text" : c.response_ms > 1000 ? "warn-text" : ""}>{c.status === "down" ? "down" : `${c.response_ms} ms`}</span>}
          {checks.length > 1 && <span className="quiet"> {c.name}</span>}
        </div>))}</td>
      <td className="small nowrap">{cs.map((c) => (
        <div key={c.id} title={c.image}>{cs.length > 1 && <b>{c.service}: </b>}
          <span className={c.state === "running" ? "" : "bad-text"}>{c.state}</span>
          {c.state !== "running" && c.exit_code ? <span className="quiet"> (exit {c.exit_code})</span> : null}
          {c.state === "running" && c.health && c.health !== "none" && <span className={c.health === "healthy" ? "ok-text" : c.health === "starting" ? "warn-text" : "bad-text"}> · {c.health}</span>}
          {c.oom_killed && <span className="bad-text"> · out of memory</span>}
        </div>))}</td>
      <td className="small nowrap">{cs.map((c) => <div key={c.id}>{c.state === "running" ? since(c.started_at) || "?" : ""}</div>)}</td>
      <td className="small">{cs.map((c) => <div key={c.id} className={c.restarts > 0 ? "warn-text" : ""}>{c.restarts ?? ""}</div>)}</td>
    </>
  );
}

function RagSummary({ rows, h }) {
  const n = { green: 0, amber: 0, red: 0 };
  rows.forEach((s) => { const r = rate(s, h); if (r && n[r.level] !== undefined) n[r.level] += 1; });
  return <span className="small">{["red", "amber", "green"].filter((k) => n[k]).map((k) => <span key={k} className={`rag ${k}`}>{n[k]} {LEVEL[k].toLowerCase()}</span>)}</span>;
}

function Services() {
  const { data, error } = useApi("/api/v1/admin/services");
  const [health, setHealth] = useState(null);
  const [checking, setChecking] = useState(false);
  const [hErr, setHErr] = useState("");
  async function check() {
    setChecking(true); setHErr("");
    try { setHealth(await apiFetch("/api/v1/admin/services/health")); } catch (e) { setHErr(e.message); }
    setChecking(false);
  }
  useEffect(() => { if (can("system.operate")) check(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const working = data?.switching?.busy;
  useEffect(() => {
    if (!working) return undefined;
    const t = setInterval(refreshAll, 3000);
    return () => clearInterval(t);
  }, [working]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return null;
  const may = data.may_change;
  async function call(s, what, fn) {
    setBusy(`${s.key}:${what}`); setErr(""); setMsg("");
    try { const out = await fn(); setMsg(out.message); refreshAll(); } catch (e) { setErr(e.message); }
    setBusy("");
  }
  const put = (s, on) => apiFetch(`/api/v1/admin/services/${s.key}`, { method: "PUT", body: JSON.stringify({ on }) });
  const start = (s) => call(s, "start", () => put(s, true));
  const stop = (s) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Stop ${s.name}? It is switched off in the config file (a dated copy is kept first), so it stays off after `
      + `the next eax up too. ${s.when_off}`)) return;
    call(s, "stop", () => put(s, false));
  };
  const restart = (s) => {
    // eslint-disable-next-line no-alert
    if (s.key === "db" && !window.confirm("Restart the database? Every screen pauses for a few seconds.")) return;
    call(s, "restart", async () => {
      await apiFetch("/api/v1/admin/restart", { method: "POST", body: JSON.stringify({ service: s.containers[s.containers.length - 1] }) });
      return { message: `Restarting ${s.name}: it is back in a moment.` };
    });
  };
  // each service is switched on its own (owner, 5 Nov 2026): only its own row waits while it is applied
  const jobs = data.switching?.jobs || {};
  const job = (s) => jobs[s.key];
  const applying = (s) => !!job(s)?.busy || !!jobs.config?.busy;
  function status(s) {
    if (job(s)?.busy) return /\son$/.test(job(s).what) ? ["busy", "Starting..."] : ["busy", "Stopping..."];
    if (jobs.config?.busy && !s.core) return ["busy", "Applying the config file..."];
    if (!s.state) return ["unknown", "Unknown"];
    const main = s.containers.filter((c) => c !== "reports-init");
    const up = main.every((c) => s.state[c] === "running");
    if (!s.on) return ["off", up && s.containers[0] !== "api" ? "Off, still running" : "Stopped (off)"];
    return up ? ["running", "Running"] : ["stopped", "Stopped"];
  }
  const rows = [...(data.core || []), ...data.services];
  const why = !may ? needsRole(["super-admin"]) : "";
  const mine = (s, what) => busy === `${s.key}:${what}`;
  return (
    <div className="merge-step">
      <div className="svc-head"><h3>Services</h3>
        {can("system.operate") && <button onClick={check} disabled={checking}>{checking ? "Checking..." : "↻ Check again"}</button>}
        {health && <span className="quiet small">Checked {new Date(health.checked_at * 1000).toLocaleTimeString()}</span>}
        {hErr && <span className="status bad small">{hErr}</span>}
        {health && <RagSummary rows={[...(data?.core || []), ...(data?.services || [])]} h={health} />}
      </div>
      {health?.helper && <p className="status bad small">{health.helper}</p>}
      {health?.problems?.length > 0 && <p className="status warn small">The operations helper could not read everything: {health.problems.join("; ")}</p>}
      <p className="quiet">Every part of EA Explorer. The core ones always run (restart only). The optional ones start and stop here:
        Stop switches the service off in the config file (a dated copy first) so it stays off; Start switches it back on. The same
        as <code>eax service &lt;name&gt; on|off</code>.</p>
      <div className="table-scroll svc-scroll">
        <table className="grid-table svc-table">
          <thead><tr><th>Name</th><th>Description</th><th>Status</th><th>Health now</th><th>Response</th><th>Container</th><th>Up for</th><th>Restarts</th><th>Startup type</th><th>Address</th><th>Actions</th></tr></thead>
          <tbody>
            {rows.map((s) => {
              const [icon, text] = status(s);
              const running = icon === "running";
              const addr = ADDRESS[s.key]?.();
              const offTip = s.core ? "A core service is always running: use Restart" : "";
              const wait = applying(s) || busy.startsWith(`${s.key}:`);
              const tip = (t) => why || (wait ? "Being applied: a moment" : t);
              return (
                <tr key={s.key} className={s.core ? "svc-core" : ""}>
                  <th className="nowrap"><SvcIcon state={icon} /> {s.name} <div className="quiet small">{s.product}</div></th>
                  <td className="small">{s.core ? s.about : <>While off: {s.when_off}</>}
</td>
                  <td><span className={`svc-state ${icon}`}>{text}</span>
                    {!job(s)?.busy && job(s)?.error && <div className="status bad small">{job(s).error}</div>}
                    {!job(s)?.busy && !job(s)?.error && job(s)?.log?.length > 0 && <div className="quiet small">{job(s).log.join("; ")}</div>}</td>
                  {can("system.operate") ? <HealthCells s={s} h={health} /> : <td colSpan="5" className="quiet small">IT and Super Admins</td>}
                  <td className="small nowrap">{s.core ? "Always on" : s.on ? "On (starts with eax up)" : "Off"}
                    {!s.core && <div className="quiet small"><code>{s.setting}</code></div>}</td>
                  <td className="small">{!addr ? <span className="quiet">none</span>
                    : !running ? <code className="quiet" title="Not running">{addr}</code>
                      : PAGE_OF[s.key] ? <><a href={PAGE_OF[s.key]} title="How to connect a language model">{addr}</a>
                        <button className="linkish small" title="Copy the address for your language model client"
                          onClick={() => { try { navigator.clipboard.writeText(addr); setMsg(`Copied ${addr}`); } catch { /* no clipboard */ } }}>Copy</button></>
                        : <a href={addr} target="_blank" rel="noreferrer">{addr} ↗</a>}</td>
                  <td className="svc-buttons nowrap">
                    <button title={tip(offTip || (running ? "Already running" : ""))} disabled={!!why || wait || s.core || running || !s.state}
                      onClick={() => start(s)}>{mine(s, "start") ? "Starting..." : "▶ Start"}</button>
                    <button title={tip(offTip || (!s.on ? "Already off" : ""))} disabled={!!why || wait || s.core || !s.on}
                      onClick={() => stop(s)}>{mine(s, "stop") ? "Stopping..." : "■ Stop"}</button>
                    <button title={tip(s.key === "ops" ? "The helper that restarts the others: restart it with eax up" : !running ? "Not running: use Start" : "")}
                      disabled={!!why || wait || !running || s.key === "ops"}
                      onClick={() => restart(s)}>{mine(s, "restart") ? "Restarting..." : "↻ Restart"}</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {jobs.config?.busy && <p className="small"><span className="spinner" aria-hidden="true" /> Applying: {jobs.config.what}...</p>}
      {!jobs.config?.busy && jobs.config?.error && <p className="status bad">The config file: {jobs.config.error}</p>}
      {data.helper && <p className="quiet small">{data.helper}</p>}
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}

// The config file and its dated copies (one kept before every change made here or with the eax command): read any of
// them (secrets masked), compare any two setting by setting, and make a copy the config file again (Super Admins): the
// service switches in it apply at once, every other setting at the next eax up
const CURRENT = "";
const label = (n) => (n === CURRENT ? "The config file now" : n);

// One config file in clear text (IT and Super Admins, owner 5 Nov 2026). The file now can be edited: Check shows the
// problems and every setting that would change; Save keeps a dated copy of the file first, then writes it
function ConfigView({ name, edit, onClose }) {
  const { data, error } = useApi(`/api/v1/admin/config-file${name ? `?name=${encodeURIComponent(name)}` : ""}`);
  const [text, setText] = useState(null);       // null: reading; a string: editing
  const [chk, setChk] = useState(null);
  const [why, setWhy] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { if (edit && data?.editable && text === null) setText(data.text); }, [edit, data]);   // eslint-disable-line react-hooks/exhaustive-deps
  const editing = text !== null;
  const dirty = editing && data && text !== data.text;
  const close = () => {
    // eslint-disable-next-line no-alert
    if (dirty && !window.confirm("Close without saving your changes to the config file?")) return;
    onClose();
  };
  async function check() {
    setBusy(true); setErr("");
    try { setChk(await apiFetch("/api/v1/admin/config-file/check", { method: "POST", body: JSON.stringify({ text }) })); }
    catch (e) { setErr(e.message); }
    setBusy(false);
  }
  async function save() {
    setBusy(true); setErr("");
    try {
      const out = await apiFetch("/api/v1/admin/config-file/save", { method: "POST", body: JSON.stringify({ text, why: why || "edited" }) });
      refreshAll();
      onClose(out.message);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  const actions = !editing
    ? <>{data?.editable && <button onClick={() => { setText(data.text); setChk(null); }}>Edit</button>}<button onClick={close}>Close</button></>
    : <>
      <button onClick={() => { setText(null); setChk(null); setErr(""); }} disabled={busy}>Cancel</button>
      <button onClick={check} disabled={busy || !dirty}>Check changes</button>
      <button className="primary" disabled={busy || !dirty || !chk?.ok} title={!chk ? "Check the changes first" : chk.ok ? "" : "Fix the problems first"}
        onClick={save}>{busy ? "Saving..." : "Save"}</button>
    </>;
  return (
    <Modal wide title={`${label(name)}${editing ? ": editing" : ""}`} onClose={close} actions={actions}>
      {error && <p className="status bad">{error}</p>}
      {!data && !error && <p className="quiet">Loading...</p>}
      {data && !editing && <>
        <p className="quiet small"><code>{data.file}</code> · changed {fmtDateTime(data.modified)} · in clear text, passwords and
          secrets too: viewing it is recorded in the audit trail{!data.editable && " · a copy: make it the config file with Restore"}</p>
        <pre className="config-text">{data.text}</pre>
      </>}
      {data && editing && <>
        <p className="quiet small">One setting per line, <code>NAME=value</code>; lines starting with # are comments. Saving keeps the
          file as it is now as a dated copy first. Service switches apply at once; every other setting at the next
          <code> eax up</code> (or <code>eax clean-restart</code>).</p>
        <textarea className="config-edit" spellCheck={false} value={text} onChange={(e) => { setText(e.target.value); setChk(null); }} />
        <div className="row-gap" style={{ marginTop: 8 }}>
          <input placeholder="Why (a few words, kept in the copy's name)" value={why} maxLength={40} onChange={(e) => setWhy(e.target.value)} style={{ minWidth: 320 }} />
        </div>
        {chk && <div style={{ marginTop: 8 }}>
          {chk.errors.map((x) => <p key={x} className="status bad small">{x}</p>)}
          {chk.warnings.map((x) => <p key={x} className="status small" style={{ background: "#fff8c5" }}>{x}</p>)}
          {chk.ok && <p className="small">{chk.rows.length ? `${chk.rows.length} setting${chk.rows.length === 1 ? "" : "s"} will change:` : "Nothing changes."}</p>}
          {chk.rows.length > 0 && <DiffTable rows={chk.rows} headA="Now" headB="After saving" />}
        </div>}
      </>}
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

function DiffTable({ rows, headA, headB }) {
  return (
    <div className="table-scroll">
      <table className="grid-table config-diff">
        <thead><tr><th>Setting</th><th>Change</th><th>{headA}</th><th>{headB}</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.setting} className={`diff-${r.change}`}>
              <td><code>{r.setting}</code></td>
              <td className="small">{r.change}</td>
              <td className="small">{r.a === null || r.a === undefined ? <span className="quiet">not set</span> : <code>{r.a}</code>}</td>
              <td className="small">{r.b === null || r.b === undefined ? <span className="quiet">not set</span> : <code>{r.b}</code>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConfigDiff({ a, b, copies }) {
  const { data, error } = useApi(`/api/v1/admin/config-diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  const at = (n) => copies.find((c) => c.name === n);
  const head = (n) => (n === CURRENT ? "Now" : `${fmtCopyTime(at(n)?.at)} (${(at(n)?.why || "").replace(/-/g, " ")})`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Comparing...</p>;
  return (
    <>
      <p className="small">{data.rows.length ? `${data.rows.length} setting${data.rows.length === 1 ? "" : "s"} differ` : "No setting differs"};
        {" "}{data.same} the same. Comments and the order of lines are not compared.</p>
      {data.rows.length > 0 && <DiffTable rows={data.rows} headA={head(a)} headB={head(b)} />}
    </>
  );
}

const fmtCopyTime = (s) => (/^\d{8}-\d{6}$/.test(s || "")
  ? fmtDateTime(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T${s.slice(9, 11)}:${s.slice(11, 13)}:${s.slice(13, 15)}Z`) : s);

function ConfigCopies() {
  const { data, error } = useApi("/api/v1/admin/config-copies");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [view, setView] = useState(null);       // {name, edit} or null
  const [why, setWhy] = useState("");
  const [pick, setPick] = useState([]);         // the two ticked (names; CURRENT for the file now)
  const [shown, setShown] = useState(null);     // the pair being compared
  if (error) return <div className="merge-step"><h3>The config file and its copies</h3><p className="quiet small">{error}</p></div>;
  if (!data) return null;
  async function restore(c) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Make ${c.name} the config file again? The current one is copied first. The service switches in it apply now; `
      + "every other start-up setting applies at the next eax up.")) return;
    setErr(""); setMsg("");
    try {
      const out = await apiFetch("/api/v1/admin/config-copies/restore", { method: "POST", body: JSON.stringify({ name: c.name }) });
      setMsg(out.message); refreshAll();
    } catch (e) { setErr(e.message); }
  }
  async function keep() {
    setErr(""); setMsg("");
    try {
      const out = await apiFetch("/api/v1/admin/config-copies/new", { method: "POST", body: JSON.stringify({ why: why || "kept-by-hand" }) });
      setMsg(out.message); setWhy(""); refreshAll();
    } catch (e) { setErr(e.message); }
  }
  const order = [CURRENT, ...data.copies.map((c) => c.name)];   // newest first
  const tick = (n) => setPick(pick.includes(n) ? pick.filter((x) => x !== n) : [...pick, n].slice(-2));
  // the older of the two on the left, the newer on the right
  const compare = () => { const [x, y] = [...pick].sort((p, q) => order.indexOf(q) - order.indexOf(p)); setShown({ a: x, b: y }); };
  const box = (n, label) => <input type="checkbox" checked={pick.includes(n)} onChange={() => tick(n)} aria-label={`Compare ${label}`} />;
  return (
    <div className="merge-step">
      <h3>The config file and its copies</h3>
      <p className="quiet"><code>work/eaexplorer.env</code>, and the copies in <code>work/config-history</code>: one kept before every
        change made here or with the eax command, and any you keep by hand. Read any of them and compare two, in clear text, passwords
        too; edit the config file (a copy of it is kept first). Every view and change is in the audit trail.</p>
      <div className="row-gap" style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <button className="primary" onClick={() => setView({ name: CURRENT, edit: true })}>✎ Edit the config file</button>
        <input placeholder="Why (a few words)" value={why} maxLength={40} onChange={(e) => setWhy(e.target.value)} style={{ minWidth: 220 }} />
        <button onClick={keep}>Make a copy now</button>
      </div>
      <div className="table-scroll">
        <table className="grid-table">
          <thead><tr><th title="Tick two to compare">Compare</th><th>Saved</th><th>By</th><th>Before</th><th>Services off in it</th><th /></tr></thead>
          <tbody>
            <tr><td>{box(CURRENT, "the config file now")}</td><td className="small"><strong>The config file now</strong></td><td /><td /><td /><td className="nowrap">
              <button className="linkish" onClick={() => setView({ name: CURRENT })}>View</button>{" · "}
              <button className="linkish" onClick={() => setView({ name: CURRENT, edit: true })}>Edit</button></td></tr>
            {data.copies.map((c) => (
              <tr key={c.name}>
                <td>{box(c.name, c.name)}</td><td className="small">{fmtCopyTime(c.at)}</td><td className="small">{c.by}</td><td className="small">{c.why.replace(/-/g, " ")}</td>
                <td className="small">{Object.entries(c.switches).filter(([, on]) => !on).map(([k]) => k).join(", ") || <span className="quiet">none</span>}</td>
                <td className="nowrap">
                  <button className="linkish" onClick={() => setView({ name: c.name })}>View</button>{" · "}
<button className="linkish" onClick={() => restore(c)}>Restore</button>
                </td>
              </tr>
            ))}
            {!data.copies.length && <tr><td colSpan="6" className="quiet">No copies yet: one is kept before the first change.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="config-compare row-gap">
        <button className="primary" disabled={pick.length !== 2} onClick={compare}
          title={pick.length === 2 ? "" : "Tick two of them in the Compare column"}>Compare the two ticked</button>
        <span className="quiet small">{pick.length === 2 ? "" : `Tick two in the Compare column (${pick.length} ticked).`}</span>
        {shown && <button className="linkish" onClick={() => { setShown(null); setPick([]); }}>Clear</button>}
      </div>
      {shown && <ConfigDiff key={`${shown.a}|${shown.b}`} a={shown.a} b={shown.b} copies={data.copies} />}
      {view && <ConfigView name={view.name} edit={view.edit} onClose={(m) => { setView(null); if (typeof m === "string") setMsg(m); }} />}
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}

function Startup({ s }) {
  return (
    <div className="merge-step">
      <h3>Start-up settings</h3>
      <p className="quiet small">{s.note} File: <code>{s.file}</code>. In clear text, passwords and secrets too.</p>
      {s.groups.map((g) => (
        <details key={g.name} className="startup-group">
          <summary><b>{g.name}</b> <span className="quiet small">{g.settings.length}</span></summary>
          <table className="grid-table"><tbody>
            {g.settings.map((x) => <tr key={x.key}><th><code>{x.key}</code></th><td className={x.secret ? "quiet" : ""}>{x.value || <span className="quiet">(empty)</span>}</td></tr>)}
          </tbody></table>
        </details>
      ))}
    </div>
  );
}

function RestartDialog({ onClose }) {
  const [word, setWord] = useState("");
  const [state, setState] = useState("");
  const [err, setErr] = useState("");
  async function go() {
    setErr(""); setState("asked");
    try {
      await apiFetch("/api/v1/admin/restart", { method: "POST", body: "{}" });
      setState("restarting");
      const started = Date.now();
      await new Promise((r) => { setTimeout(r, 15000); });
      for (;;) {
        try { await apiFetch("/api/v1/heartbeat"); break; } catch (e) { /* still restarting */ }
        if (Date.now() - started > 300000) { setErr("The system has not come back after five minutes: check the containers with .\\eax status."); return; }
        await new Promise((r) => { setTimeout(r, 5000); });
      }
      setState("back");
    } catch (e) { setErr(e.message); setState(""); }
  }
  return (
    <Modal title="Restart the system" onClose={onClose}
      actions={state === "back" ? <button className="primary" onClick={() => window.location.reload()}>Reload the page</button>
        : <><button onClick={onClose} disabled={state === "restarting"}>Cancel</button>
          <button className="danger" disabled={word !== "RESTART" || !!state} onClick={go}>Restart</button></>}>
      {!state && <>
        <p>Every service of this installation restarts. People working now lose what they have not saved and sign in again.</p>
        <label className="ed-field"><span>Type RESTART to confirm</span><input value={word} onChange={(e) => setWord(e.target.value)} autoFocus /></label>
      </>}
      {state === "asked" && <p>Asking the operations helper...</p>}
      {state === "restarting" && <p>Restarting. This page waits for the system to answer again (usually one to three minutes).</p>}
      {state === "back" && <p className="status ok">The system is back.</p>}
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- licences
function Licences() {
  const { data, error } = useApi("/api/v1/admin/licences");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  return (
    <div>
      <p>{data.own}</p>
      <table className="grid-table">
        <thead><tr><th>Product or library</th><th>Image</th><th>Licence</th><th>How it is used</th></tr></thead>
        <tbody>{data.items.map((x) => <tr key={x.product}><td>{x.product}</td><td className="small quiet">{x.image}</td><td>{x.licence}</td><td className="small">{x.kind}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

