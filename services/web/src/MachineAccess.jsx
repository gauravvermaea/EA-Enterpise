// System admin › Machine access (phase 25, D366, D378): how other systems, scripts and MCP clients sign in.
//   Everyone: my tokens and API keys (made here, the secret shown once), with read or read-write per API area,
//             optionally only some models or projects; revoke; last used.
//   Super Admins and IT Admins: every credential, service accounts (svc-...) and their credentials, client
//             certificates uploaded and trusted one by one (self-signed too).
import { useMemo, useState } from "react";
import { apiFetch, can, currentUser } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { fmtDate, fmtDateTime } from "./fmt";

const STATES = { active: "Active", expiring: "Expires soon", expired: "Expired", revoked: "Revoked" };
const LEVEL = { read: "read", "read-write": "read-write" };

export default function MachineAccess() {
  const meta = useApi("/api/v1/machine-access/areas");
  const all = meta.data?.manage_all;
  const [view, setView] = useState("mine");
  if (meta.error) return <p className="status bad">{meta.error}</p>;
  if (!meta.data) return <p>Loading...</p>;
  return (
    <div className="machine-access">
      <p className="quiet">Other systems, scripts, Excel and Power BI (the OData feed) and MCP clients sign in with a <b>token</b> or an
        {" "}<b>API key</b>{all ? <>, or a <b>client certificate</b> on the machine-access port</> : ""}. Each one works as its owner, never
        with more than the owner may do, and only in the areas it is given. Every call it makes is in the change log.</p>
      <div className="seg" role="tablist">
        <button className={`${view === "mine" ? "on" : ""}`} onClick={() => setView("mine")}>My credentials</button>
        {all && <button className={`${view === "all" ? "on" : ""}`} onClick={() => setView("all")}>Every credential</button>}
        {all && <button className={`${view === "svc" ? "on" : ""}`} onClick={() => setView("svc")}>Service accounts</button>}
        <button className={`${view === "areas" ? "on" : ""}`} onClick={() => setView("areas")}>Areas and addresses</button>
      </div>
      {view === "mine" && <Credentials meta={meta.data} everyone={false} />}
      {view === "all" && all && <Credentials meta={meta.data} everyone />}
      {view === "svc" && all && <ServiceAccounts meta={meta.data} />}
      {view === "areas" && <Areas meta={meta.data} />}
    </div>
  );
}

function scopeText(scopes, meta) {
  const label = Object.fromEntries(meta.areas.map((a) => [a.code, a.label]));
  return Object.entries(scopes || {}).map(([a, l]) => `${label[a] || a}: ${LEVEL[l] || l}`).join(" · ");
}

function Credentials({ meta, everyone }) {
  const list = useApi(`/api/v1/machine-access/credentials${everyone ? "?all=1" : ""}`);
  const [show, setShow] = useState("live");
  const [making, setMaking] = useState(null);
  const [made, setMade] = useState(null);
  const [revoking, setRevoking] = useState(null);
  const [editing, setEditing] = useState(null);
  const rows = (list.data || []).filter((c) => show === "all" || ["active", "expiring"].includes(c.state));
  const hidden = (list.data || []).length - rows.length;
  return (
    <>
      <div className="toolbar">
        <button onClick={() => setMaking("token")}>New token</button>
        <button onClick={() => setMaking("api_key")}>New API key</button>
        {meta.manage_all && <button onClick={() => setMaking("certificate")}>Upload a client certificate</button>}
        <label className="quiet" style={{ marginLeft: "auto" }}>
          <input type="checkbox" checked={show === "all"} onChange={(e) => setShow(e.target.checked ? "all" : "live")} />
          {" "}Show revoked and expired{hidden && show !== "all" ? ` (${hidden})` : ""}
        </label>
      </div>
      {list.error && <p className="status bad">{list.error}</p>}
      {list.data && !rows.length && <p className="quiet">{everyone ? "No credentials." : "You have no tokens or API keys yet."}</p>}
      {rows.length > 0 && (
        <div className="table-scroll">
          <table className="grid-table cred-table">
            <thead><tr>
              <th>Name</th>{everyone && <th>Owner</th>}<th>Kind</th><th>May use</th><th>Expires</th><th>Last used</th><th>State</th><th />
            </tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.guid} className={c.state === "revoked" || c.state === "expired" ? "is-retired" : ""}>
                  <td><b>{c.name}</b>
                    <div className="quiet small">{c.kind === "certificate" ? <span title={c.fingerprint}>{c.subject}</span> : <code>{c.prefix}…</code>}</div></td>
                  {everyone && <td>{c.owner}{c.service && <span className="tag">service</span>}</td>}
                  <td>{c.kind_label}</td>
                  <td className="small">{scopeText(c.scopes, meta)}
                    {(c.model_guids.length > 0 || c.project_guids.length > 0) && <div className="quiet">
                      only {c.model_guids.length ? `${c.model_guids.length} model${c.model_guids.length > 1 ? "s" : ""}` : ""}
                      {c.model_guids.length && c.project_guids.length ? " and " : ""}
                      {c.project_guids.length ? `${c.project_guids.length} project${c.project_guids.length > 1 ? "s" : ""}` : ""}</div>}</td>
                  <td>{fmtDate(c.expires_at)}</td>
                  <td className="small">{c.last_used_at ? <>{fmtDateTime(c.last_used_at)}<div className="quiet" title={c.last_used_path}>
                    {c.use_count} call{c.use_count === 1 ? "" : "s"}{c.last_used_from ? ` · from ${c.last_used_from}` : ""}</div></> : <span className="quiet">never</span>}</td>
                  <td><span className={`cred-state cred-${c.state}`}>{STATES[c.state]}</span>
                    {c.revoked_at && <div className="quiet small">{fmtDate(c.revoked_at)} by {c.revoked_by}{c.revoke_reason ? `: ${c.revoke_reason}` : ""}</div>}</td>
                  <td className="nowrap">{!c.revoked_at && c.state !== "expired" && <>
                    <button className="linkish" onClick={() => setEditing(c)}>Change</button>{" "}
                    <button className="linkish bad-text" onClick={() => setRevoking(c)}>Revoke</button></>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {making && <MakeCredential kind={making} meta={meta} onClose={() => setMaking(null)}
        onMade={(c) => { setMaking(null); setMade(c); refreshAll(); }} />}
      {made && <Made c={made} onClose={() => setMade(null)} />}
      {editing && <ChangeCredential c={editing} meta={meta} onClose={() => setEditing(null)} onDone={() => { setEditing(null); refreshAll(); }} />}
      {revoking && <RevokeCredential c={revoking} onClose={() => setRevoking(null)} onDone={() => { setRevoking(null); refreshAll(); }} />}
    </>
  );
}

function AreaPicker({ meta, value, onChange }) {
  return (
    <table className="grid-table area-picker">
      <thead><tr><th>Area</th><th>None</th><th>Read</th><th>Read and write</th></tr></thead>
      <tbody>
        {meta.areas.map((a) => (
          <tr key={a.code}>
            <td><b>{a.label}</b><div className="quiet small">{a.holds}</div></td>
            {["", "read", "read-write"].map((l) => (
              <td key={l} className="center">
                <input type="radio" name={`area-${a.code}`} checked={(value[a.code] || "") === l} aria-label={`${a.label}: ${l || "none"}`}
                  onChange={() => onChange({ ...value, [a.code]: l })} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function LimitPicker({ label, path, value, onChange }) {
  const list = useApi(path);
  const items = useMemo(() => (Array.isArray(list.data) ? list.data : list.data?.items || list.data?.projects || []), [list.data]);
  const [on, setOn] = useState(value.length > 0);
  return (
    <div className="limit-picker">
      <label><input type="checkbox" checked={on} onChange={(e) => { setOn(e.target.checked); if (!e.target.checked) onChange([]); }} />
        {" "}Only some {label}</label>
      {on && (
        <select multiple size={6} value={value} onChange={(e) => onChange([...e.target.selectedOptions].map((o) => o.value))}>
          {items.map((m) => <option key={m.id || m.guid} value={m.id || m.guid}>{m.name}</option>)}
        </select>
      )}
    </div>
  );
}

function MakeCredential({ kind, meta, onClose, onMade }) {
  const me = currentUser()?.username || "";
  const [owner, setOwner] = useState(me);
  const svc = useApi(meta.manage_all ? "/api/v1/machine-access/service-accounts" : null);
  const [name, setName] = useState("");
  const [days, setDays] = useState(meta.default_days[kind]);
  const [scopes, setScopes] = useState(kind === "token" ? { models: "read", reports: "read" } : { models: "read" });
  const [models, setModels] = useState([]);
  const [projects, setProjects] = useState([]);
  const [pem, setPem] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const owners = [me, ...((svc.data || []).filter((s) => !s.disabled_at).map((s) => s.username))];
  const go = async () => {
    setBusy(true); setErr("");
    try {
      const out = await apiFetch("/api/v1/machine-access/credentials", { method: "POST", body: JSON.stringify({
        kind, owner, name, days: Number(days), scopes, model_guids: models, project_guids: projects, pem: kind === "certificate" ? pem : undefined,
      }) });
      onMade(out);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const title = { token: "New token", api_key: "New API key", certificate: "Upload a client certificate" }[kind];
  return (
    <Modal title={title} onClose={onClose} wide actions={<>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={busy || !name.trim() || (kind === "certificate" && !pem.trim())} onClick={go}>
        {kind === "certificate" ? "Upload and trust" : "Make it"}</button></>}>
      <div className="form-grid">
        <label>Name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="What uses it: Excel OData feed, Claude desktop..." autoFocus /></label>
        {(meta.manage_all || kind === "certificate") && owners.length > 1 && (
          <label>Belongs to<select value={owner} onChange={(e) => setOwner(e.target.value)}>
            {owners.map((o) => <option key={o} value={o}>{o === me ? `${o} (me)` : o}</option>)}</select></label>)}
        <label>Lives for (days, at most {meta.max_days[kind]})<input type="number" min={1} max={meta.max_days[kind]} value={days}
          onChange={(e) => setDays(e.target.value)} style={{ width: 100 }} /></label>
      </div>
      {kind === "certificate" && (
        <label className="block">The certificate (PEM; self-signed is fine)
          <textarea rows={6} value={pem} onChange={(e) => setPem(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----" className="mono" />
          <span className="quiet small">Only this very certificate is trusted (by its SHA-256 fingerprint). The system presents it on the
            machine-access port ({meta.certificate_port_note.match(/\d{4}/)?.[0] || "9443"}). It expires when the certificate does, if sooner.</span></label>
      )}
      <h3>May use</h3>
      <p className="quiet small">Read means looking only (GET); read and write also changes. It can never do more than {owner === me ? "you" : owner} may.</p>
      <AreaPicker meta={meta} value={scopes} onChange={setScopes} />
      <div className="form-grid">
        <LimitPicker label="models" path="/api/v1/models" value={models} onChange={setModels} />
        <LimitPicker label="projects" path="/api/v1/projects" value={projects} onChange={setProjects} />
      </div>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

function Made({ c, onClose }) {
  const [copied, setCopied] = useState(false);
  const copy = () => { navigator.clipboard?.writeText(c.secret).then(() => setCopied(true)).catch(() => {}); };
  return (
    <Modal title={`${c.kind_label} made`} onClose={onClose} actions={<button className="primary" onClick={onClose}>I have kept it</button>}>
      {c.secret ? <>
        <p><b>Copy it now: it is shown only this once.</b> EA Explorer keeps only a fingerprint of it, so it cannot show it again.</p>
        <div className="secret-box"><code>{c.secret}</code> <button onClick={copy}>{copied ? "Copied" : "Copy"}</button></div>
        <p className="quiet small">Send it as <code>{c.use.split(":")[0]}: …</code> with every call. For MCP clients and the OData feed use it as
          the bearer token. It expires on {fmtDate(c.expires_at)}.</p>
      </> : <p>The certificate <b>{c.subject}</b> is trusted until {fmtDate(c.expires_at)}. Fingerprint (SHA-256): <code className="small">{c.fingerprint}</code></p>}
    </Modal>
  );
}

function ChangeCredential({ c, meta, onClose, onDone }) {
  const [name, setName] = useState(c.name);
  const [scopes, setScopes] = useState(c.scopes);
  const [models, setModels] = useState(c.model_guids);
  const [projects, setProjects] = useState(c.project_guids);
  const [expires, setExpires] = useState(c.expires_at.slice(0, 10));
  const [err, setErr] = useState("");
  const save = async () => {
    setErr("");
    try {
      const body = { name, scopes, model_guids: models, project_guids: projects };
      if (expires !== c.expires_at.slice(0, 10)) body.expires_at = `${expires}T23:59:00`;
      await apiFetch(`/api/v1/machine-access/credentials/${c.guid}`, { method: "PATCH", body: JSON.stringify(body) });
      onDone();
    } catch (e) { setErr(e.message); }
  };
  return (
    <Modal title={`Change ${c.name}`} onClose={onClose} wide actions={<><button onClick={onClose}>Cancel</button>
      <button className="primary" onClick={save}>Save</button></>}>
      <div className="form-grid">
        <label>Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>Expires (only sooner)<input type="date" value={expires} max={c.expires_at.slice(0, 10)} onChange={(e) => setExpires(e.target.value)} /></label>
      </div>
      <AreaPicker meta={meta} value={scopes} onChange={setScopes} />
      <div className="form-grid">
        <LimitPicker label="models" path="/api/v1/models" value={models} onChange={setModels} />
        <LimitPicker label="projects" path="/api/v1/projects" value={projects} onChange={setProjects} />
      </div>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

function RevokeCredential({ c, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const go = async () => {
    try {
      await apiFetch(`/api/v1/machine-access/credentials/${c.guid}/revoke`, { method: "POST", body: JSON.stringify({ reason }) });
      onDone();
    } catch (e) { setErr(e.message); }
  };
  return (
    <Modal title={`Revoke ${c.name}?`} onClose={onClose} actions={<><button onClick={onClose}>Cancel</button>
      <button className="primary danger" onClick={go}>Revoke now</button></>}>
      <p>It stops working at once, for every call. This cannot be undone: make a new one if it is needed again.</p>
      <label className="block">Why (optional)<input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

function ServiceAccounts({ meta }) {
  const list = useApi("/api/v1/machine-access/service-accounts");
  const [making, setMaking] = useState(false);
  const [err, setErr] = useState("");
  const isSuper = can("settings.manage");
  const patch = async (s, body) => {
    setErr("");
    try { await apiFetch(`/api/v1/machine-access/service-accounts/${s.username}`, { method: "PATCH", body: JSON.stringify(body) }); refreshAll(); }
    catch (e) { setErr(e.message); }
  };
  return (
    <>
      <p className="quiet">A service account is a name another system signs in as. Give it global roles here and model roles on each
        model's People tab, like anyone's; then give it tokens, API keys or a client certificate (Every credential › New...).
        Disabling it stops all its credentials at once.</p>
      <div className="toolbar"><button onClick={() => setMaking(true)}>New service account</button></div>
      {err && <p className="status bad">{err}</p>}
      {list.error && <p className="status bad">{list.error}</p>}
      {list.data && (
        <div className="table-scroll">
          <table className="grid-table">
            <thead><tr><th>Account</th><th>Global roles</th><th>Model roles</th><th>Live credentials</th><th>Last used</th><th>Made</th><th /></tr></thead>
            <tbody>
              {list.data.map((s) => (
                <tr key={s.guid} className={s.disabled_at ? "is-retired" : ""}>
                  <td><b>{s.name}</b><div className="quiet small"><code>{s.username}</code>{s.description ? ` · ${s.description}` : ""}</div></td>
                  <td>{s.roles.join(", ")}</td>
                  <td className="small">{s.model_roles.length ? s.model_roles.map((m) => `${m.model}: ${m.role}`).join("; ") : <span className="quiet">none</span>}</td>
                  <td>{s.live_credentials}</td>
                  <td>{s.last_used_at ? fmtDateTime(s.last_used_at) : <span className="quiet">never</span>}</td>
                  <td className="small">{fmtDate(s.created_at)} by {s.created_by}</td>
                  <td className="nowrap">{s.disabled_at
                    ? <><span className="quiet small">Disabled {fmtDate(s.disabled_at)} </span><button className="linkish" onClick={() => patch(s, { disabled: false })}>Enable</button></>
                    : <button className="linkish bad-text" disabled={s.roles.includes("super-admin") && !isSuper}
                        onClick={() => window.confirm(`Disable ${s.username}? Its credentials stop working at once.`) && patch(s, { disabled: true })}>Disable</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {making && <MakeServiceAccount meta={meta} isSuper={isSuper} onClose={() => setMaking(false)} onDone={() => { setMaking(false); refreshAll(); }} />}
    </>
  );
}

function MakeServiceAccount({ meta, isSuper, onClose, onDone }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [roles, setRoles] = useState(["user"]);
  const [err, setErr] = useState("");
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
  const go = async () => {
    try {
      await apiFetch("/api/v1/machine-access/service-accounts", { method: "POST", body: JSON.stringify({ name, description, roles }) });
      onDone();
    } catch (e) { setErr(e.message); }
  };
  return (
    <Modal title="New service account" onClose={onClose} actions={<><button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={slug.length < 2} onClick={go}>Make it</button></>}>
      <label className="block">Name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Reporting hub" autoFocus />
        <span className="quiet small">Signs in as <code>svc-{slug || "…"}</code></span></label>
      <label className="block">What it is for<input value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <fieldset><legend>Global roles</legend>
        {meta.service_roles.map((r) => (
          <label key={r} className="inline-check"><input type="checkbox" checked={roles.includes(r)} disabled={r === "super-admin" && !isSuper}
            onChange={(e) => setRoles(e.target.checked ? [...roles, r] : roles.filter((x) => x !== r))} /> {r}</label>))}
      </fieldset>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

function Areas({ meta }) {
  const [open, setOpen] = useState("");
  return (
    <>
      <p className="quiet">A credential is given read or read and write on each area; an area it is not given is refused. These are the
        addresses in each. Who am I (<code>/api/v1/me</code>) and the heartbeat always answer.</p>
      <table className="grid-table">
        <thead><tr><th>Area</th><th>Holds</th><th>Addresses</th></tr></thead>
        <tbody>
          {meta.areas.map((a) => (
            <tr key={a.code}>
              <td><b>{a.label}</b></td>
              <td className="small">{a.holds}</td>
              <td className="small">
                <button className="linkish" onClick={() => setOpen(open === a.code ? "" : a.code)}>{a.endpoints.length} address{a.endpoints.length === 1 ? "" : "es"}</button>
                {open === a.code && <ul className="endpoint-list">{a.endpoints.map((e) => (
                  <li key={`${e.path}${e.methods}`}><code>{e.methods.join(" ")}</code> <code>{e.path}</code></li>))}</ul>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
