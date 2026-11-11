// System admin › Scaling (phase 36.3, D378, D520, D526): how many API and job servers run, for Super Admins and IT
// Admins. Fixed (the number you set, as Containers and `eax servers` do, D249) or by rules: the fewest and most servers,
// one server per so many people active, and one more or fewer when the servers' CPU stays high or low for some minutes,
// with a cool-down between changes. The operations helper looks every minute and applies them; each change is listed.
// The rest of scaling out (a database standby, shared storage, more hosts, the library on its own server) is set up
// in the config file: docs/phase-36.3.md.
import { useEffect, useState } from "react";
import { apiFetch } from "./auth";
import { fmtDateTime } from "./fmt";

const FIELDS = [
  ["EAX_SCALE_MIN", "Fewest servers", "Never fewer than this."],
  ["EAX_SCALE_MAX", "Most servers", "Never more than this (up to 16; each server needs about 1 GB of memory)."],
  ["EAX_SCALE_USERS_PER_SERVER", "People per server", "One server for every this many people active in the last 15 minutes."],
  ["EAX_SCALE_CPU_UP", "Add a server above CPU (%)", "When the servers' average CPU stays above this ..."],
  ["EAX_SCALE_CPU_DOWN", "Remove a server below CPU (%)", "... or below this ..."],
  ["EAX_SCALE_MINUTES", "For (minutes)", "... for this many minutes, one server is added or removed."],
  ["EAX_SCALE_COOLDOWN", "Then wait (minutes)", "Nothing changes again within this many minutes of a change."],
];

export default function Scaling() {
  const [d, setD] = useState(null);
  const [form, setForm] = useState(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try { const x = await apiFetch("/api/v1/admin/scaling"); setD(x); setForm((f) => f || { ...x.settings }); setErr(""); } catch (e) { setErr(e.message); }
  };
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);
  if (err && !d) return <p className="status bad">{err}</p>;
  if (!d || !form) return <p>Loading...</p>;
  const changed = Object.keys(form).some((k) => String(form[k]) !== String(d.settings[k]));
  const save = async () => {
    setBusy(true); setMsg("");
    try {
      const x = await apiFetch("/api/v1/admin/scaling", { method: "PUT", body: JSON.stringify({ settings: form }) });
      setD(x); setForm({ ...x.settings }); setMsg("Saved in the config file (a dated copy was kept first).");
    } catch (e) { setMsg(e.message); } finally { setBusy(false); }
  };
  const auto = form.EAX_SCALE_MODE === "auto";
  const last = d.last_sample;
  return (
    <div className="scaling">
      <h2>API and job servers</h2>
      <div className="kpi-row">
        <div className="kpi"><b>{d.running}</b><span>running now</span></div>
        <div className="kpi"><b>{d.servers}</b><span>wanted (EAX_API_SERVERS)</span></div>
        <div className="kpi"><b>{last?.cpu ?? "-"}{last ? "%" : ""}</b><span>average CPU</span></div>
        <div className="kpi"><b>{last?.people ?? "-"}</b><span>people active (15 min)</span></div>
      </div>
      {d.error && <p className="status warn small">The last look at the load had a problem: {d.error}</p>}
      <fieldset className="scaling-mode">
        <legend>How the number is decided</legend>
        <label className="radio"><input type="radio" checked={!auto} onChange={() => setForm({ ...form, EAX_SCALE_MODE: "fixed" })} />
          {" "}<b>Fixed</b>: the number set on <a href="#/admin/containers">Containers</a> or with <code>eax servers &lt;n&gt;</code></label>
        <label className="radio"><input type="radio" checked={auto} onChange={() => setForm({ ...form, EAX_SCALE_MODE: "auto" })} />
          {" "}<b>By rules</b>: the operations helper looks every minute and adds or removes one server at a time</label>
      </fieldset>
      <table className="grid-table scaling-rules">
        <tbody>
          {FIELDS.map(([k, label, help]) => (
            <tr key={k}>
              <th scope="row"><label htmlFor={k}>{label}</label></th>
              <td><input id={k} type="number" min="0" value={form[k]} disabled={!auto && k !== "EAX_SCALE_MIN" && k !== "EAX_SCALE_MAX"}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></td>
              <td className="quiet small">{help}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="toolbar">
        <button className="primary" disabled={!changed || busy} onClick={save}>{busy ? "Saving..." : "Save"}</button>
        {changed && <button onClick={() => setForm({ ...d.settings })}>Undo changes</button>}
        {msg && <span className="small">{msg}</span>}
      </div>
      <h2>Changes made by the rules</h2>
      {d.events.length === 0 ? <p className="quiet">None yet.</p> : (
        <table className="grid-table">
          <thead><tr><th>When</th><th>What</th><th>Why</th><th>CPU</th><th>People</th></tr></thead>
          <tbody>
            {d.events.map((e, i) => (
              <tr key={i}>
                <td className="nowrap">{fmtDateTime(e.at)}</td>
                <td>{e.settings ? `Rules saved by ${e.by}` : `${e.from} → ${e.to} servers`}</td>
                <td className="small">{e.settings ? Object.entries(e.settings).map(([k, v]) => `${k.replace("EAX_SCALE_", "").toLowerCase()} ${v}`).join(", ") : e.why}</td>
                <td>{e.cpu != null ? `${e.cpu}%` : ""}</td>
                <td>{e.people ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h2>More hosts, a database standby, shared storage</h2>
      <p className="small">These are set up in the config file with <code>EAX_COMPOSE_EXTRA</code> (standby, shared-storage,
        primary, api-host, library-host, library-elsewhere) and the settings each one names; <code>eax standby</code> shows
        how far the standby is behind and promotes it. See docs/phase-36.3.md.</p>
    </div>
  );
}
