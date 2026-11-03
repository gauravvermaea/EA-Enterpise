import { useCallback, useEffect, useState } from "react";
import { apiFetch, keycloak } from "./auth";

function Status({ ok, children }) {
  return <span className={ok ? "status ok" : "status bad"}>{children}</span>;
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
            <tr><th>API</th><td><Status ok={beat.status === "ok"}>{beat.status}</Status> version {beat.version} ({beat.deployment})</td></tr>
            <tr><th>Database</th><td><Status ok={beat.database.reachable}>{beat.database.reachable ? "reachable" : "not reachable"}</Status>
              {beat.database.latency_ms != null && ` in ${beat.database.latency_ms} ms`}
              {beat.database.schema_version && `, schema ${beat.database.schema_version}`}
              {beat.database.error && ` (${beat.database.error})`}</td></tr>
            <tr><th>Job queue</th><td>{beat.jobs.waiting ?? "-"} waiting, {beat.jobs.failed ?? "-"} failed</td></tr>
            <tr><th>Checked</th><td>{new Date(beat.time).toLocaleString()}</td></tr>
          </tbody>
        </table>
      )}
      <h2>Background job</h2>
      {keycloak.authenticated ? (
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
