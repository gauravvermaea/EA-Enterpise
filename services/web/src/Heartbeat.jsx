import { useCallback, useEffect, useState } from "react";
import { apiFetch, can, signedIn } from "./auth";
import { fmtDateTime, fmtTime } from "./fmt";
import { LastSelfTest } from "./TestRuns";

function Status({ ok, children }) {
  return <span className={ok ? "status ok" : "status bad"}>{children}</span>;
}

const STATUS_CLASS = { up: "status ok", ok: "status ok", warning: "status warn", degraded: "status warn", down: "status bad", off: "quiet" };

// Every service in the stack: GET /api/v1/heartbeat/services (signed in)
function Services() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const check = useCallback(async () => {
    setBusy(true);
    try {
      setData(await apiFetch("/api/v1/heartbeat/services"));
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => { check(); }, [check]);
  return (
    <>
      <h2>Services</h2>
      <p>
        <code>GET /api/v1/heartbeat/services</code> checks every service from inside the stack.{" "}
        <button onClick={check} disabled={busy}>{busy ? "Checking..." : "Check again"}</button>
      </p>
      {error && <p className="status bad">{error}</p>}
      {data && (
        <>
          <p>
            Overall: <span className={STATUS_CLASS[data.status]}>{data.status}</span> ·{" "}
            {data.counts.up} up, {data.counts.warning} warning, {data.counts.down} down, {data.counts.off} off ·
            checked in {data.duration_ms} ms at {fmtTime(data.time)}
          </p>
          <table className="grid-table">
            <thead><tr><th>Service</th><th>Product</th><th>Status</th><th>Detail</th><th>ms</th></tr></thead>
            <tbody>
              {data.services.map((s) => (
                <tr key={s.name} title={s.target}>
                  <td>{s.name}</td>
                  <td className="quiet">{s.kind}</td>
                  <td><span className={STATUS_CLASS[s.status]}>{s.status}</span></td>
                  <td>{s.detail}</td>
                  <td className="quiet">{s.response_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}

export default function Heartbeat() {
  const [beat, setBeat] = useState(null);
  const [error, setError] = useState(null);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setBeat(await apiFetch("/api/v1/heartbeat"));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load]);

  async function runJob() {
    setBusy(true);
    try {
      const started = await apiFetch("/api/v1/jobs/heartbeat", {
        method: "POST",
        body: JSON.stringify({ note: "Started from the heartbeat screen" }),
      });
      setJob(started);
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const now = await apiFetch(`/api/v1/jobs/${started.job_id}`);
        setJob(now);
        if (["succeeded", "failed", "cancelled"].includes(now.status)) break;
      }
      load();
    } catch (e) {
      setJob({ status: `error: ${e.message}` });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Heartbeat</h1>
      <p>The API answers <code>GET /api/v1/heartbeat</code>; this screen calls it every 10 seconds.</p>
      {error && <p className="status bad">The API cannot be reached: {error}</p>}
      {beat && (
        <table className="facts">
          <tbody>
            <tr><th>API</th><td><span className={STATUS_CLASS[beat.status] || "status bad"}>{beat.status}</span> version {beat.version} ({beat.deployment})</td></tr>
            <tr><th>Versions</th><td>
              API <strong>{beat.version}</strong> · database <strong>{beat.database.version ?? "unknown"}</strong>{" "}
              {beat.versions_match === true && <span className="status ok">match</span>}
              {beat.versions_match === false && <span className="status warn">do not match</span>}
              {beat.warning && <div className="status warn">{beat.warning}</div>}
            </td></tr>
            <tr><th>Database</th><td><Status ok={beat.database.reachable}>{beat.database.reachable ? "reachable" : "not reachable"}</Status>
              {beat.database.latency_ms != null && ` in ${beat.database.latency_ms} ms`}
              {beat.database.schema_version && `, migration ${beat.database.schema_version}`}
              {beat.database.error && ` (${beat.database.error})`}</td></tr>
            <tr><th>Job queue</th><td>{beat.jobs.waiting ?? "-"} waiting, {beat.jobs.failed ?? "-"} failed</td></tr>
            <tr><th>Checked</th><td>{fmtDateTime(beat.time)}</td></tr>
          </tbody>
        </table>
      )}
      {signedIn() && <Services />}
      <LastSelfTest />
      <Integrate />
      <h2>Background job</h2>
      {signedIn() ? (
        <>
          <p>Runs a sample job in the job runner: it writes a heartbeat row (shown in the Superset sample dashboard) and an audit event.</p>
          <button className="primary" onClick={runJob} disabled={busy}>{busy ? "Running..." : "Run a background job"}</button>
          {job && <p>Job {job.job_id ?? ""}: <strong>{job.status}</strong></p>}
        </>
      ) : (
        <p>Sign in to run a background job.</p>
      )}
    </section>
  );
}

// Where the customer's SOC and monitoring tools read health from (owner, 6 Nov 2026, D213). The addresses that exist
// today; a monitoring-only service-account token, one versioned health API and a security events feed come with
// ADM-088 (phase 35.1)
const FEEDS = [
  ["/api/v1/heartbeat", "Up or not, versions, database and job queue", "None: open to anyone who can reach the server"],
  ["/api/v1/heartbeat/services", "Every service: up, warning, down or off, with its response time", "A signed-in user's token"],
  ["/api/v1/admin/services/health", "Everything on Administration > Services: each check, every container's state, Docker health, exit code, CPU, memory, disk, up time and restarts", "An IT Admin or Super Admin token"],
  ["/api/v1/admin/containers", "Every container and its state", "An IT Admin or Super Admin token"],
  ["/api/v1/admin/containers/<service>", "One container in detail: health check log, mounts, ports, networks, limits, what it uses now", "An IT Admin or Super Admin token"],
];

function Integrate() {
  const [copied, setCopied] = useState("");
  const base = window.location.origin;
  const copy = (u) => { try { navigator.clipboard.writeText(u); setCopied(u); } catch { /* no clipboard */ } };
  return (
    <>
      <h2>Read health from your monitoring or SOC</h2>
      <p>Your security operations centre or monitoring tool can read the same health as JSON over HTTPS, with
        {" "}<code>Authorization: Bearer &lt;token&gt;</code> where a token is needed (a Keycloak access token; ask a User Admin for a
        service account). Every address is described in the <a href="/api/docs" target="_blank" rel="noreferrer">API documentation ↗</a>.</p>
      <table className="grid-table">
        <thead><tr><th>Address</th><th>What it gives</th><th>Sign-in</th></tr></thead>
        <tbody>
          {FEEDS.filter(([, , who]) => !who.includes("IT Admin") || can("system.operate")).map(([path, what, who]) => (
            <tr key={path}>
              <td className="nowrap"><code>{base}{path}</code>{" "}
                <button className="linkish small" onClick={() => copy(`${base}${path}`)}>{copied === `${base}${path}` ? "Copied" : "Copy"}</button></td>
              <td className="small">{what}</td>
              <td className="small">{who}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="quiet small">Coming in phase 35.1 (ADM-081, ADM-088): one versioned health API with a verdict per service, alerts,
        backups and a security events feed, read with a monitoring-only token that sees no model content, and a metrics endpoint for
        monitoring tools.</p>
    </>
  );
}
