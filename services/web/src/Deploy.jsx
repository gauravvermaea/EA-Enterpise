// System admin › Deploy (phase 36, D555 to D557): for Super Admins and IT Admins. EA Explorer deploys itself from
// this installation to another place: a server over SSH (Docker installed if missing), or AWS, Azure or DigitalOcean
// (the machine created, or one that exists). The same steps as eax deploy, run by the operations helper, so a reload
// loses nothing.
//   choose the target: the same questions as eax deploy (without the laptop), the SSH key pasted or chosen as a file,
//     the cloud credentials (for this run only unless kept; never shown again)
//   Show the plan (runs nothing) first, then Deploy
//   the run: its steps, Retry / Back / Quit on a failed step, the log
//   the history of targets and of every deployment; kept credentials (names only) can be forgotten
// Several installations managed together (fleets, pushing updates to them) is R2.
import { useEffect, useRef, useState } from "react";
import { apiFetch, can } from "./auth";
import { fmtDateTime } from "./fmt";

const STATUS = {
  running: ["warn", "Running"], failed: ["bad", "Waiting: Retry, Back or Quit"], done: ["ok", "Deployed"],
  planned: ["ok", "Plan shown"], quit: ["bad", "Stopped"], back: ["", "Back to the answers"],
};
const MARK = { waiting: "○", running: "▶", done: "✓", failed: "✕" };

// Always fresh (no cache): a deployment changes from one second to the next.
function useFresh(path) {
  const [state, setState] = useState({ data: null, error: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path || !can("system.operate")) return undefined;
    let live = true;
    apiFetch(path).then((data) => live && setState({ data, error: null })).catch((e) => live && setState((s) => ({ ...s, error: e.message })));
    return () => { live = false; };
  }, [path, tick]);
  return { ...state, reload: () => setTick((t) => t + 1) };
}

function Question({ q, value, onChange }) {
  const id = `dq-${q.key}`;
  if (q.choices) {
    return (
      <fieldset className="deploy-q">
        <legend><strong>{q.text}</strong></legend>
        {q.help && <p className="quiet small">{q.help}</p>}
        {Object.entries(q.choices).map(([k, label]) => (
          <label key={k} className="deploy-choice">
            <input type="radio" name={q.key} value={k} checked={value === k} onChange={() => onChange(k)} /> {label}
          </label>
        ))}
      </fieldset>
    );
  }
  if (q.kind === "key") return null;     // the SSH key has its own box below
  return (
    <div className="deploy-q">
      <label htmlFor={id}><strong>{q.text}</strong>{q.required ? "" : <span className="quiet"> (optional)</span>}</label>
      {q.help && <p className="quiet small">{q.help}</p>}
      <input id={id} type={q.secret ? "password" : "text"} autoComplete="off" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function Run({ id, onBack }) {
  const r = useFresh(`/api/v1/operations/deploys/${id}`);
  const [busy, setBusy] = useState("");
  const logRef = useRef(null);
  const live = r.data && ["running", "failed"].includes(r.data.status);
  useEffect(() => {
    if (!live) return undefined;
    const t = setInterval(() => r.reload(), 2000);
    return () => clearInterval(t);
  }, [live]);
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [r.data?.lines?.length]);
  if (r.error) return <p className="status bad">{r.error}</p>;
  if (!r.data) return <p>Loading...</p>;
  const d = r.data;
  async function decide(choice) {
    setBusy(choice);
    try { await apiFetch(`/api/v1/operations/deploys/${id}/decide`, { method: "POST", body: JSON.stringify({ choice }) }); r.reload(); }
    finally { setBusy(""); }
  }
  const [cls, label] = STATUS[d.status] || ["", d.status];
  return (
    <section className="deploy-run" aria-live="polite">
      <h3>{d.plan ? "The plan (nothing is run)" : "Deploying"}: {d.target} <span className={`pill ${cls}`}>{label}</span></h3>
      <p className="quiet small">{d.kind} · version {d.version || "as asked"} · started {fmtDateTime(d.started)} by {d.by}
        {d.keep ? " · credentials kept for this target" : ""}</p>
      <ol className="deploy-steps">
        {(d.steps || []).map((s, i) => (
          <li key={i} className={s.status}><span aria-hidden="true">{MARK[s.status] || ""}</span> {i + 1}. {s.title}</li>
        ))}
      </ol>
      {d.status === "failed" && d.failed && (
        <div className="status bad" role="alert">
          <strong>This step failed: {d.failed.step}</strong><br />{d.failed.why}
          <div className="toolbar">
            <button className="primary" disabled={!!busy} onClick={() => decide("retry")}>Retry this step</button>
            <button disabled={!!busy} onClick={() => decide("back")}>Back to the answers</button>
            <button disabled={!!busy} onClick={() => decide("quit")}>Quit</button>
          </div>
        </div>
      )}
      {d.status === "done" && (
        <p className="status ok">Deployed. {d.result?.public_ip ? `The machine's public address is ${d.result.public_ip}: point the DNS names at it. ` : ""}
          The first sign-in (eaadmin) and its password are in the target's config file, work/eaexplorer.env; they are not shown here.</p>
      )}
      {d.status === "planned" && <p className="status ok">That is the plan. Back to the answers to change them, or Deploy to carry it out.</p>}
      {d.error && <p className="status bad">{d.error}</p>}
      <h4>What it does</h4>
      <pre className="deploy-log" ref={logRef} tabIndex={0} aria-label="The deployment's log">{(d.lines || []).join("\n")}</pre>
      {!live && <button onClick={() => onBack(d)}>Back to the answers</button>}
    </section>
  );
}

export default function Deploy() {
  const ov = useFresh("/api/v1/operations/deploys");
  const [answers, setAnswers] = useState({ kind: "server" });
  const [qs, setQs] = useState([]);
  const [key, setKey] = useState("");
  const [keep, setKeep] = useState(false);
  const [useKept, setUseKept] = useState("");
  const [runId, setRunId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const allowed = can("system.operate");
  useEffect(() => {
    if (!allowed) return;
    let gone = false;
    apiFetch("/api/v1/operations/deploys/questions", { method: "POST", body: JSON.stringify({ answers }) })
      .then((d) => { if (!gone) setQs(d.questions || []); }).catch((e) => setError(e.message));
    return () => { gone = true; };
  }, [JSON.stringify(answers), allowed]);
  if (!allowed) return <p className="status bad">Deploying EA Explorer elsewhere needs the IT Admin or Super Admin role.</p>;
  const set = (k, v) => setAnswers((a) => ({ ...a, [k]: v }));
  function readKey(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => setKey(String(r.result || ""));
    r.readAsText(f);
    e.target.value = "";
  }
  async function start(plan) {
    setError("");
    if (!plan && !window.confirm(`Deploy EA Explorer to ${answers.hostname || answers.ssh_target || answers.kind} now? This creates and changes things as the answers say.`)) return;
    setBusy(true);
    try {
      const full = Object.fromEntries(qs.map((q) => [q.key, answers[q.key] ?? q.default ?? ""]));
      const secretKeys = qs.filter((q) => q.secret).map((q) => q.key);
      const secrets = Object.fromEntries(secretKeys.map((k) => [k, full[k]]).filter(([, v]) => v));
      for (const k of secretKeys) delete full[k];
      const out = await apiFetch("/api/v1/operations/deploys", { method: "POST", body: JSON.stringify({ answers: full, secrets, ssh_key: key, keep,
        use_kept: useKept, plan, confirm: !plan }) });
      setRunId(out.id);
      ov.reload();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function forget(t) {
    if (!window.confirm(`Forget the credentials kept for ${t}?`)) return;
    try { await apiFetch(`/api/v1/operations/deploys/kept/${encodeURIComponent(t)}`, { method: "DELETE" }); ov.reload(); }
    catch (e) { setError(e.message); }
  }
  const data = ov.data || {};
  return (
    <div className="deploy-page">
      <p className="quiet">Deploy EA Explorer from here to <strong>another place</strong>: a server reached over SSH (Docker is installed if
        it is missing), or a machine in AWS, Azure or DigitalOcean, created from your credentials or one you already have. The same
        steps as <code>eax deploy</code>; see the plan first. This installation is not changed. (Managing many installations
        together comes in release 2.)</p>
      {data.helper_down && <p className="status bad">The operations helper is not running: deployments cannot start. The history below is kept.</p>}
      {runId ? <Run id={runId} onBack={() => { setRunId(""); ov.reload(); }} /> : (
        <section className="deploy-form" aria-labelledby="deploy-where">
          <h3 id="deploy-where">Where to deploy</h3>
          {qs.map((q) => <Question key={q.key} q={q} value={answers[q.key] ?? q.default} onChange={(v) => set(q.key, v)} />)}
          <div className="deploy-q">
            <label htmlFor="dq-ssh-key"><strong>SSH private key</strong></label>
            <p className="quiet small">The target is reached over SSH with this key (for a machine created here, its public key is put on it).
              Paste it or choose the file. It goes to the operations helper for this deployment only and is never shown again.</p>
            <textarea id="dq-ssh-key" rows={4} value={key} onChange={(e) => setKey(e.target.value)} spellCheck={false}
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" autoComplete="off" className="deploy-key" />
            <label className="small">Or choose the key file <input type="file" onChange={readKey} aria-label="Choose the SSH private key file" /></label>
          </div>
          {(data.kept || []).length > 0 && (
            <div className="deploy-q">
              <label htmlFor="dq-use-kept"><strong>Use credentials kept for a target</strong> <span className="quiet">(optional)</span></label>
              <select id="dq-use-kept" value={useKept} onChange={(e) => setUseKept(e.target.value)}>
                <option value="">None: the ones given above</option>
                {data.kept.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          )}
          <label className="deploy-choice"><input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} /> Keep the SSH key and
            the cloud credentials for this target, for the next deployment (kept by the operations helper, readable by it only, never shown again)</label>
          {error && <p className="status bad" role="alert">{error}</p>}
          <div className="toolbar">
            <button disabled={busy} onClick={() => start(true)}>Show the plan (runs nothing)</button>
            <button className="primary" disabled={busy} onClick={() => start(false)}>Deploy</button>
          </div>
        </section>
      )}
      <h3>Targets</h3>
      {(data.targets || []).length === 0 ? <p className="quiet">Nothing deployed from here yet.</p> : (
        <table className="grid-table">
          <thead><tr><th>Target</th><th>Kind</th><th>Version</th><th>Last deployed</th><th>By</th><th>Result</th><th>Address</th><th>Deployments</th><th /></tr></thead>
          <tbody>
            {data.targets.map((t) => (
              <tr key={t.target}>
                <td>{t.target}</td><td>{t.kind}</td><td>{t.version}</td><td>{fmtDateTime(t.started_at)}</td><td>{t.started_by}</td>
                <td><span className={`pill ${(STATUS[t.status] || [""])[0]}`}>{(STATUS[t.status] || ["", t.status])[1]}</span>{t.failed_step ? ` at ${t.failed_step}` : ""}</td>
                <td>{t.address}</td><td>{t.deployments}</td>
                <td>{(data.kept || []).includes(t.target) && <button className="tiny" onClick={() => forget(t.target)} title="Forget the credentials kept for this target">Forget credentials</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Every deployment</h3>
      {(data.history || []).length === 0 ? <p className="quiet">None yet.</p> : (
        <table className="grid-table">
          <thead><tr><th>Started</th><th>Target</th><th>Kind</th><th>Plan or deployment</th><th>Version</th><th>By</th><th>Result</th><th /></tr></thead>
          <tbody>
            {data.history.map((h) => (
              <tr key={h.run_id}>
                <td>{fmtDateTime(h.started_at)}</td><td>{h.target}</td><td>{h.kind}</td><td>{h.plan ? "Plan" : "Deployment"}</td><td>{h.version}</td>
                <td>{h.started_by}</td><td><span className={`pill ${(STATUS[h.status] || [""])[0]}`}>{(STATUS[h.status] || ["", h.status])[1]}</span></td>
                <td><button className="tiny" onClick={() => setRunId(h.run_id)}>Open</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
