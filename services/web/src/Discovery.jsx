// Data discovery and ingestion (the Release 3 epic, D670; owner, 13 Nov 2026: "what I want for Data ingestion is a
// reverse OData feed: it discovers and then writes to a model"): Import and export › Discovery.
//   sources   an OData feed EA Explorer reads, an endpoint other systems push to, or documents read by the AI engine;
//             each set up by anyone who may change the model, run now or daily or weekly
//   Look      read the source now: its sets, fields, keys and links, and the mapping suggested (set -> entity type,
//             field -> attribute, a field holding another set's key -> a relationship type); change it and save it
//   Run now   what is new or changed since the last delivery becomes a delivery (Deliveries: preview, accept, decline)
//   matches   a found name close to an element of its type: say it is that element, or new
//   AI engine Super Admins choose it: off, a cloud engine with the organisation's own key, or one run locally
//   Python kit a push source's example (D674): push_to_eax.py (push_dataframe(url, df, username, password)), its
//             requirements, a README with the venv steps and sample CSVs made from the model's metamodel; the code shown
//             here to copy, the whole kit downloaded as a zip
import { useState } from "react";
import { apiDownload, apiFetch, can } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Field } from "./ModelOps";
import { fmtDateTime } from "./fmt";
import { trackTask } from "./tasks";

const KINDS = [["odata", "OData feed (EA Explorer reads it)"], ["push", "Push (a system sends to EA Explorer)"], ["ai", "Documents read by the AI engine"]];
const SCHEDULES = [["off", "On demand only"], ["daily", "Daily"], ["weekly", "Weekly"]];
const post = (path, body, method = "POST") => apiFetch(path, { method, body: JSON.stringify(body || {}) });

export default function DiscoveryTab({ model }) {
  const { data, error } = useApi(`/api/v1/models/${model}/import-sources`);
  const [adding, setAdding] = useState(null);
  const [open, setOpen] = useState(null);
  const [err, setErr] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const sources = (data.sources || []).filter((s) => s.kind && s.kind !== "folder");
  async function add() {
    setErr("");
    try { const s = await post(`/api/v1/models/${model}/discovery-sources`, adding); setAdding(null); refreshAll(); setOpen(s.id); }
    catch (e) { setErr(e.message); }
  }
  return (
    <section className="discovery" aria-label="Discovery">
      <p className="quiet">Point EA Explorer at what your organisation already has: an OData feed it reads, an endpoint a system sends to, or
        documents the AI engine reads. Each run finds what is new or changed and sends it to <a href={`#/metamodel/${model}/import/deliveries`}>Deliveries</a> as
        a delivery to preview, then accept or decline. Anyone who may change this model sets sources up; accepting needs a Committer.</p>
      {err && <p className="status bad">{err}</p>}
      <table className="grid-table">
        <thead><tr><th>Source</th><th>Kind</th><th>Runs</th><th>Last run</th><th /></tr></thead>
        <tbody>{sources.length ? sources.map((s) => (
          <tr key={s.id}><td>{s.name}</td><td>{(KINDS.find((k) => k[0] === s.kind) || [, s.kind])[1]}</td>
            <td>{(SCHEDULES.find((k) => k[0] === s.schedule) || [, s.schedule])[1]}</td>
            <td className="small">{s.last_run?.at ? `${fmtDateTime(s.last_run.at)}: ${s.last_run.error || s.last_run.message || ""}` : "never"}</td>
            <td><button onClick={() => setOpen(open === s.id ? null : s.id)}>{open === s.id ? "Close" : "Open"}</button></td></tr>))
          : <tr><td colSpan={5} className="quiet">No discovery sources yet.</td></tr>}</tbody>
      </table>
      {!adding ? <p><button className="primary" onClick={() => setAdding({ kind: "odata", schedule: "off" })}>Add a discovery source</button></p> : (
        <div className="card">
          <h3>A new discovery source</h3>
          <Field label="Name"><input value={adding.name || ""} onChange={(e) => setAdding({ ...adding, name: e.target.value })} placeholder="Cloud inventory" /></Field>
          <Field label="Kind"><select value={adding.kind} onChange={(e) => setAdding({ ...adding, kind: e.target.value })}>
            {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
          {adding.kind !== "push" && <Field label="Address" hint={adding.kind === "odata" ? "the feed's service document or one entity set (JSON)" : "a page to read (or leave it empty and drop documents in the source's folder)"}>
            <input value={adding.url || ""} onChange={(e) => setAdding({ ...adding, url: e.target.value })} placeholder="https://" /></Field>}
          <Field label="Sign-in setting" hint="the name of a setting in the config file whose value is sent as the Authorization header; never the secret itself">
            <input value={adding.auth_ref || ""} onChange={(e) => setAdding({ ...adding, auth_ref: e.target.value.toUpperCase() })} placeholder="EAX_SOURCE_INVENTORY" /></Field>
          <Field label="Runs"><select value={adding.schedule} onChange={(e) => setAdding({ ...adding, schedule: e.target.value })}>
            {SCHEDULES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
          <button className="primary" onClick={add} disabled={!adding.name}>Add it</button> <button onClick={() => setAdding(null)}>Cancel</button>
        </div>)}
      {open && <SourcePanel key={open} id={open} model={model} />}
      {can("settings.manage") && <AiEngine />}
    </section>
  );
}

function SourcePanel({ id, model }) {
  const { data: src, error } = useApi(`/api/v1/discovery-sources/${id}`);
  const [found, setFound] = useState(null);
  const [mapping, setMapping] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!src) return <p>Loading...</p>;
  const map = mapping || src.mapping || {};
  const set = (name, patch) => setMapping({ ...map, [name]: { ...(map[name] || {}), ...patch } });
  const act = async (what, fn) => {
    setBusy(what); setErr(""); setMsg("");
    try { await fn(); } catch (e) { setErr(e.message); }
    setBusy("");
  };
  const look = () => act("look", async () => { const x = await post(`/api/v1/discovery-sources/${id}/look`); setFound(x); setMapping({ ...x.mapping, ...(src.mapping || {}) }); });
  const save = () => act("save", async () => { await post(`/api/v1/discovery-sources/${id}`, { mapping: map }, "PATCH"); setMsg("The mapping is saved."); setMapping(null); refreshAll(); });
  const run = (full) => act("run", async () => {
    const x = await post(`/api/v1/discovery-sources/${id}/run`, { full });
    if (x.task) trackTask(x.task, `#/metamodel/${model}/import/deliveries`);
    setMsg(x.message); refreshAll();
  });
  const decide = (s, entity) => act("match", async () => {
    await post(`/api/v1/discovery-sources/${id}/matches`, { entity_type: s.entity_type, found: s.found, entity });
    refreshAll();
  });
  const types = found?.types || [];
  const last = src.last_run || {};
  return (
    <div className="card discovery-source">
      <h3>{src.name}</h3>
      <p className="small">{(KINDS.find((k) => k[0] === src.kind) || [, src.kind])[1]}{src.url ? ` · ${src.url}` : ""}
        {src.auth_ref ? ` · signs in with the setting ${src.auth_ref}` : ""} · {(SCHEDULES.find((k) => k[0] === src.schedule) || [, ""])[1]}
        {src.next_run_at ? ` · next run ${fmtDateTime(src.next_run_at)}` : ""}</p>
      {src.push && <p className="small">Systems send JSON to <code>POST {src.push}</code>: <code>{'{"<set>": [records]}'}</code>, as this
        model's service account or anyone who may load into it.</p>}
      {src.kind === "push" && <PythonKit id={id} />}
      {err && <p className="status bad">{err}</p>}
      {msg && <p className="status ok">{msg}</p>}
      <div className="toolbar">
        {src.kind !== "push" && <button onClick={look} disabled={!!busy}>{busy === "look" ? "Reading..." : "Look"}</button>}
        {src.kind !== "push" && <button className="primary" onClick={() => run(false)} disabled={!!busy}>{busy === "run" ? "Running..." : "Run now"}</button>}
        {src.kind !== "push" && <button onClick={() => run(true)} disabled={!!busy} title="Send everything found, not only what changed">Run in full</button>}
      </div>
      {last.at && <p className="small">Last run {fmtDateTime(last.at)} by {last.by}: {last.error || last.message}
        {last.counts ? ` (found ${last.counts.found}, new or changed ${last.counts.changed}, relationships ${last.counts.relationships ?? 0})` : ""}</p>}
      {(last.renamed || []).length > 0 && <div className="small">
        <p><b>Renamed at the source</b> (each arrives as a new element; the old one stays, as a delivery never deletes: merge or retire it):</p>
        <ul>{last.renamed.map((r) => <li key={`${r.entity_type}${r.key}`}>{r.old} → {r.new} <span className="quiet">({r.entity_type})</span></li>)}</ul></div>}
      {(last.suggestions || []).length > 0 && <>
        <h4>Is this the same element?</h4>
        <table className="grid-table"><thead><tr><th>Found</th><th>In the model</th><th>How alike</th><th /></tr></thead>
          <tbody>{last.suggestions.map((s) => (
            <tr key={`${s.entity_type}${s.found}`}><td>{s.found} <span className="quiet small">({s.entity_type})</span></td><td>{s.candidate}</td>
              <td>{s.confidence}%</td>
              <td className="nowrap"><button onClick={() => decide(s, s.candidate_id)} disabled={!!busy}>Same element</button>{" "}
                <button onClick={() => decide(s, null)} disabled={!!busy}>It is new</button></td></tr>))}</tbody></table></>}
      {found && <>
        <h4>What is in it, and where it goes</h4>
        {found.sets.map((f) => {
          const mp = map[f.set] || {};
          const t = types.find((x) => x.code === mp.entity_type);
          return (
            <details key={f.set} open className="discovery-set">
              <summary><b>{f.set}</b> · {f.count} records · {mp.entity_type ? `as ${t?.name || mp.entity_type}` : "not mapped yet"}
                {mp.confidence ? <span className="quiet small"> (suggested {mp.confidence}%)</span> : null}</summary>
              <Field label="Entity type"><select value={mp.entity_type || ""} onChange={(e) => set(f.set, { entity_type: e.target.value })}>
                <option value="">(not taken)</option>{types.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}</select></Field>
              {["key", "name", "description"].map((k) => (
                <Field key={k} label={{ key: "Its key", name: "Its name", description: "Its description" }[k]}>
                  <select value={mp[k] || ""} onChange={(e) => set(f.set, { [k]: e.target.value })}>
                    <option value="">(none)</option>{f.fields.map((x) => <option key={x} value={x}>{x}</option>)}</select></Field>))}
              <table className="grid-table small"><thead><tr><th>Field</th><th>Example</th><th>Goes to</th></tr></thead>
                <tbody>{f.fields.filter((x) => ![mp.key, mp.name, mp.description].includes(x)).map((x) => (
                  <tr key={x}><td>{x}</td><td className="quiet">{String(f.sample?.[x] ?? "")}</td>
                    <td>{f.links?.[x] ? <select value={mp.links?.[x] || ""} onChange={(e) => set(f.set, { links: { ...(mp.links || {}), [x]: e.target.value } })}
                      aria-label={`Relationship for ${x}`}>
                      <option value="">(no relationship)</option>{(found.relationship_types || []).map((r) => <option key={r.code} value={r.code}>{r.name} to {f.links[x]}</option>)}</select>
                      : <select value={mp.attributes?.[x] || ""} onChange={(e) => set(f.set, { attributes: { ...(mp.attributes || {}), [x]: e.target.value } })}
                        aria-label={`Attribute for ${x}`}>
                        <option value="">(left out)</option>{(t?.attributes || []).map((a) => <option key={a.code} value={a.code}>{a.name}</option>)}</select>}</td></tr>))}</tbody></table>
            </details>);
        })}
        <button className="primary" onClick={save} disabled={!!busy}>Save the mapping</button>
      </>}
    </div>
  );
}

export function copyText(text, done) {
  try { navigator.clipboard.writeText(text).then(() => done("Copied."), () => done("Select it and copy it by hand.")); }
  catch { done("Select it and copy it by hand."); }
}

// A push source's Python kit (D674): read the code here, copy it, or download everything as a zip.
function PythonKit({ id }) {
  const { data: k, error } = useApi(`/api/v1/discovery-sources/${id}/kit/code`);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!k) return null;
  const download = () => apiDownload(`/api/v1/discovery-sources/${id}/kit`, k.zip).catch((e) => setNote(e.message));
  return (
    <div className="discovery-kit">
      <h4>Push with Python</h4>
      <p className="small">An example to read and adapt: <code>push_to_eax.py</code> reads the CSV files in a folder and sends them here
        in one call with <code>push_dataframes</code> (or one DataFrame with <code>push_dataframe(url, df, username, password)</code>),
        signed in with your user name and password (an Active Directory account too), a personal token (for single sign-on), a service account's API key or a client certificate. The kit holds the script, <code>requirements.txt</code>, a README with the
        steps to set up Python (a venv) and sample CSV files made from this model's types. What it sends becomes a delivery to review.</p>
      <div className="toolbar">
        <button className="primary" onClick={download}>Download the Python kit (zip)</button>
        <button onClick={() => setOpen(!open)}>{open ? "Hide the code" : "Show the code"}</button>
        <button onClick={() => copyText(k.script, setNote)}>Copy the code</button>
        <button onClick={() => copyText(k.command, setNote)}>Copy the command</button>
      </div>
      {note && <p className="status ok small">{note}</p>}
      <p className="small">Run it: <code>{k.command}</code></p>
      {open && <>
        <h5>push_to_eax.py</h5>
        <pre className="code-block">{k.script}</pre>
        <h5>requirements.txt</h5>
        <pre className="code-block">{k.requirements}</pre>
        {Object.entries(k.samples || {}).map(([name, body]) => <div key={name}><h5>samples/{name}</h5><pre className="code-block">{body}</pre></div>)}
      </>}
    </div>
  );
}

function AiEngine() {
  const { data, error } = useApi("/api/v1/admin/ai-engine");
  const [form, setForm] = useState(null);
  const [msg, setMsg] = useState("");
  if (error || !data) return null;
  const f = form || data;
  const save = async () => {
    try { await post("/api/v1/admin/ai-engine", f, "PUT"); setMsg("Saved."); setForm(null); refreshAll(); } catch (e) { setMsg(e.message); }
  };
  return (
    <div className="card">
      <h3>AI engine (Super Admins)</h3>
      <p className="quiet small">The engine that reads documents for discovery: off until you choose one. A cloud engine uses your organisation's own key;
        a local one runs on your own servers. Any engine with the common chat-completions interface. The key is never stored here: name the setting in the
        config file that holds it.</p>
      <Field label="Engine"><select value={f.mode} onChange={(e) => setForm({ ...f, mode: e.target.value })}>
        <option value="off">Off</option><option value="cloud">Cloud (our own key)</option><option value="local">Local</option></select></Field>
      {f.mode !== "off" && <>
        <Field label="Its address"><input value={f.url || ""} onChange={(e) => setForm({ ...f, url: e.target.value })} placeholder="https://.../v1" /></Field>
        <Field label="Model name"><input value={f.model || ""} onChange={(e) => setForm({ ...f, model: e.target.value })} /></Field>
        <Field label="Key setting"><input value={f.key_ref || ""} onChange={(e) => setForm({ ...f, key_ref: e.target.value.toUpperCase() })} placeholder="EAX_AI_KEY" /></Field>
      </>}
      <button onClick={save} disabled={!form}>Save the AI engine</button> {msg && <span className="small">{msg}</span>}
    </div>
  );
}
