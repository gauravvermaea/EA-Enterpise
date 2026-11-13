// The sites (R2.0, D586; R2.2, D634). Connect to a site: each person's own list of remote EA Explorer instances (kept
// by the personal data service); Open goes to the instance's own screens in a new tab, signed in there its own way, with
// the role the person has there. A Super Admin can also open an SSH session to the instance's host, recorded; how they
// prove who they are to the host is EAX_REMOTE_SSH_AUTH (ask each time, a kept key, or this installation's key). Sites
// (R2.1, D646): everyone's shared list in the farm schema, Local first, each with a green, amber or red dot; only Super
// Admins add, change or remove one; a deployed site is added when its deployment finishes.
// (Farm Admin, R2.1) is still to come.
import { lazy, Suspense, useEffect, useState } from "react";
import { apiFetch, can, roles } from "./auth";
import { useApi } from "./ModelViews";
import { fmtDateTime } from "./fmt";
import WebTerminal from "./WebTerminal";

const Deploy = lazy(() => import("./Deploy"));

const AUTH = {
  ask: "asked each time: type the host's password, or paste a private key for this session only (nothing is kept)",
  stored: "your private key, kept with the instance, encrypted (EAX_REMOTE_SECRET_KEY)",
  server_key: "this installation's own SSH key: put its public part on the host",
};

export default function FarmPage({ route }) {
  const connect = route.startsWith("#/farm/connect");
  if (connect) return <ConnectPage />;
  if (route.startsWith("#/farm/deploy")) {        // Deploy, with the other sites (R2.14; was System Admin › Deploy)
    return (
      <section className="page farm-deploy">
        <h1>Sites › Deploy EA Explorer</h1>
        {can("system.operate")
          ? <Suspense fallback={<p>Loading...</p>}><Deploy /></Suspense>
          : <p className="status bad">Deploying is for Super Admins and IT Admins.</p>}
      </section>
    );
  }
  const sa = roles().includes("super-admin");
  return (
    <section className="page farm-page">
      <h1>Sites</h1>
      <p>Every EA Explorer site, the same list for everyone. Open one to sign in there: you work with the role you have on that
        site. The dot is its health from its public heartbeat, every 5 minutes: green working, amber warnings or maintenance,
        red not working or not answering. A site deployed from <a href="#/farm/deploy">Deploy EA Explorer</a> is added when it
        is ready. Your own extra list: <a href="#/farm/connect">My remote instances</a>.</p>
      <SitesTable sa={sa} />
      {sa && <SshSessions />}
    </section>
  );
}

const DOT = { green: "ok", amber: "warn", red: "bad", unknown: "" };

function SitesTable({ sa }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const reload = () => apiFetch("/api/v1/sites").then(setData).catch((e) => setError(e.message));
  useEffect(() => { reload(); }, []);
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const save = async (x) => {
    setErr("");
    try {
      await apiFetch(x.id ? `/api/v1/sites/${x.id}` : "/api/v1/sites", { method: x.id ? "PUT" : "POST",
        body: JSON.stringify({ name: x.name, url: x.url, note: x.note }) });
      setEdit(null); reload();
    } catch (e) { setErr(e.message); }
  };
  const remove = async (x) => {
    if (!window.confirm(`Remove ${x.name} from the list? Nothing happens to the site itself.`)) return;
    try { await apiFetch(`/api/v1/sites/${x.id}`, { method: "DELETE" }); reload(); } catch (e) { setErr(e.message); }
  };
  if (!data) return error ? <p className="status bad">{error}</p> : <p>Loading...</p>;
  return (
    <div className="sites">
      {err && <p className="status bad">{err}</p>}
      {sa && <button onClick={() => setEdit({ name: "", url: "https://", note: "" })}>Add a site</button>}
      <table className="grid-table">
        <thead><tr><th>Health</th><th>Site</th><th>Address</th><th>Version</th><th>Note</th><th>Checked</th><th /></tr></thead>
        <tbody>{data.sites.map((x) => (
          <tr key={x.id}>
            <td><span className={`status ${DOT[x.health]}`} title={x.health_detail}>● {x.health === "unknown" ? "not checked yet" : x.health}</span></td>
            <td>{x.name}{x.source === "local" ? " (this site)" : x.source === "deployed" ? <span className="quiet small"> deployed</span> : ""}</td>
            <td className="small"><code>{x.url}</code></td>
            <td className="small">{x.version}</td>
            <td className="small">{x.note}</td>
            <td className="small nowrap">{x.checked_at ? fmtDateTime(x.checked_at) : ""}</td>
            <td className="nowrap">
              {x.source === "local" ? <a href="#/">Open</a> : <a href={x.url} target="_blank" rel="noopener noreferrer">Open ↗</a>}
              {sa && <> · <button className="linkish" onClick={() => setEdit({ ...x })}>Change</button>
                {x.source !== "local" && <> · <button className="linkish bad-text" onClick={() => remove(x)}>Remove</button></>}</>}
            </td>
          </tr>))}</tbody>
      </table>
      {edit && (
        <div className="card">
          <h3>{edit.id ? `Change ${edit.name}` : "Add a site"}</h3>
          <label>Name <input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></label>{" "}
          {edit.source !== "local" && <label>Address <input value={edit.url} size="40" onChange={(e) => setEdit({ ...edit, url: e.target.value })} /></label>}{" "}
          <label>Note <input value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} /></label>{" "}
          <button onClick={() => save(edit)}>Save</button> <button onClick={() => setEdit(null)}>Cancel</button>
        </div>)}
    </div>
  );
}

function ConnectPage() {
  const [tick, setTick] = useState(0);
  const { data, error } = useApi(`/api/v1/me/remote-instances?t=${tick}`);
  const [edit, setEdit] = useState(null);
  const [ssh, setSsh] = useState(null);
  const [msg, setMsg] = useState("");
  const sa = roles().includes("super-admin");
  async function remove(x) {
    if (!window.confirm(`Take ${x.name} off your list?`)) return;   // eslint-disable-line no-alert
    try { await apiFetch(`/api/v1/me/remote-instances/${x.id}`, { method: "DELETE" }); setTick((t) => t + 1); } catch (e) { setMsg(e.message); }
  }
  return (
    <section className="page farm-page">
      <h1>Connect to a site</h1>
      <p className="quiet">Your own list of EA Explorer instances. Open one: its own screens open in a new tab, where you sign in its own way
        (its single sign-on, a key, or a user name and password) and work with the role you have there. They are also in the site picker
        at the top left.</p>
      {error && <p className="status bad">{error}</p>}
      {msg && <p className="status">{msg}</p>}
      <button className="primary" onClick={() => setEdit({})}>+ Add an instance</button>
      {!data ? <p>Loading...</p> : !data.items.length ? <p className="quiet">None yet.</p> : (
        <table className="grid-table">
          <thead><tr><th>Instance</th><th>Address</th>{sa && <th>SSH</th>}<th /></tr></thead>
          <tbody>{data.items.map((x) => (
            <tr key={x.id}>
              <td><b>{x.name}</b>{x.note && <div className="quiet small">{x.note}</div>}</td>
              <td className="small"><a href={x.url} target="_blank" rel="noopener noreferrer">{x.url}</a></td>
              {sa && <td className="small">{x.ssh_host ? `${x.ssh_user}@${x.ssh_host}:${x.ssh_port}` : <span className="quiet">not set</span>}
                {data.ssh_auth === "stored" && x.ssh_host && <div className="quiet">{x.has_key ? "key kept" : "no key kept yet"}</div>}</td>}
              <td className="row-gap">
                <a className="button" href={x.url} target="_blank" rel="noopener noreferrer">Open ↗</a>
                {sa && x.ssh_host && <button onClick={() => setSsh(x)}>SSH</button>}
                <button onClick={() => setEdit(x)}>Change</button>
                <button className="danger" onClick={() => remove(x)}>Remove</button>
              </td>
            </tr>))}</tbody>
        </table>)}
      {edit && <InstanceForm x={edit} sa={sa} mode={data?.ssh_auth} onDone={() => { setEdit(null); setTick((t) => t + 1); }} />}
      {ssh && <SshPanel x={ssh} mode={data?.ssh_auth} onClose={() => setSsh(null)} />}
      {sa && <p className="quiet small">SSH sign-in on this installation: {AUTH[data?.ssh_auth] || AUTH.ask} (EAX_REMOTE_SSH_AUTH). Every SSH
        session is recorded: <a href="#/farm">Farm Admin › Sites</a>.</p>}
    </section>
  );
}

function InstanceForm({ x, sa, mode, onDone }) {
  const [f, setF] = useState({ name: x.name || "", url: x.url || "", note: x.note || "", ssh_host: x.ssh_host || "", ssh_port: x.ssh_port || 22,
    ssh_user: x.ssh_user || "", ssh_key: "" });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function save() {
    setErr("");
    const body = { ...f };
    if (!(sa && mode === "stored" && f.ssh_key)) delete body.ssh_key;
    try {
      await apiFetch(x.id ? `/api/v1/me/remote-instances/${x.id}` : "/api/v1/me/remote-instances",
        { method: x.id ? "PATCH" : "POST", body: JSON.stringify(body) });
      onDone();
    } catch (e) { setErr(e.message); }
  }
  return (
    <div className="card ed-form">
      <h2>{x.id ? `Change ${x.name}` : "Add an instance"}</h2>
      <label>Name<input value={f.name} onChange={set("name")} placeholder="e.g. Staging" /></label>
      <label>Address<input value={f.url} onChange={set("url")} placeholder="https://ea.example.com" /></label>
      <label>Note<input value={f.note} onChange={set("note")} /></label>
      {sa && <>
        <label>SSH host<input value={f.ssh_host} onChange={set("ssh_host")} placeholder="ea-host.example.com" /></label>
        <label>SSH port<input type="number" value={f.ssh_port} onChange={set("ssh_port")} /></label>
        <label>SSH user<input value={f.ssh_user} onChange={set("ssh_user")} placeholder="e.g. eaxadmin" /></label>
        {mode === "stored" && <label>Private key to keep (encrypted){x.has_key ? " - one is kept; paste a new one to replace it" : ""}
          <textarea rows={4} value={f.ssh_key} onChange={set("ssh_key")} placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" /></label>}
      </>}
      {err && <p className="status bad">{err}</p>}
      <div className="row-gap"><button className="primary" onClick={save}>Save</button><button onClick={onDone}>Cancel</button></div>
    </div>
  );
}

function SshPanel({ x, mode, onClose }) {
  const [key, setKey] = useState("");
  const { data: server } = useApi(mode === "server_key" ? "/api/v1/admin/ssh-key" : null);
  return (
    <div className="card">
      <div className="row-gap"><h2>SSH to {x.name}: {x.ssh_user}@{x.ssh_host}:{x.ssh_port}</h2><button onClick={onClose}>Close</button></div>
      {mode === "ask" && <label className="small">Private key for this session only (optional: leave empty to type the host's password)
        <textarea rows={3} value={key} onChange={(e) => setKey(e.target.value)} placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" /></label>}
      {mode === "server_key" && server && <p className="small">This installation's public key, to put in the host's
        <code> ~/.ssh/authorized_keys</code>: <code className="wrap">{server.public_key}</code></p>}
      <WebTerminal what={`${x.ssh_host} (recorded)`} openLabel="▶ Connect"
        note={<>An SSH session to the host, from this installation. Everything the host shows is recorded (Farm Admin › Sites).</>}
        ticket={(size) => apiFetch(`/api/v1/remote-instances/${x.id}/ssh`, { method: "POST", body: JSON.stringify({ ...size, ...(key ? { ssh_key: key } : {}) }) })} />
    </div>
  );
}

function SshSessions() {
  const { data, error } = useApi("/api/v1/admin/ssh-sessions");
  const [open, setOpen] = useState(null);
  const { data: t } = useApi(open ? `/api/v1/admin/ssh-sessions/${open}` : null);
  if (error) return null;
  return (
    <div>
      <h2>SSH sessions (recorded)</h2>
      {!data ? <p>Loading...</p> : !data.items.length ? <p className="quiet">None yet.</p> : (
        <table className="grid-table small">
          <thead><tr><th>Started</th><th>By</th><th>Instance</th><th>Host</th><th>Sign-in</th><th>Ended</th><th /></tr></thead>
          <tbody>{data.items.map((s) => (
            <tr key={s.session}>
              <td>{fmtDateTime(s.started_at)}</td><td>{s.username}</td><td>{s.instance}</td>
              <td>{s.ssh_user}@{s.host}:{s.port}</td><td>{s.auth}</td>
              <td>{s.ended_at ? `${fmtDateTime(s.ended_at)} (${s.reason})` : "open"}</td>
              <td><button className="linkish" onClick={() => setOpen(open === s.session ? null : s.session)}>{open === s.session ? "Hide" : "Transcript"}</button></td>
            </tr>))}</tbody>
        </table>)}
      {open && t && <pre className="log-box small">{t.text}</pre>}
    </div>
  );
}
