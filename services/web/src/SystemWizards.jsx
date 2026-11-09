// System admin's wizards (D284, D285): System admin > Wizards
//   Give a person access       a person, then the models and the role on each (only models you may give roles on)
//   Take a person's access     a person, then which of their model roles go (leaving, moving team)
//   Back up now                infrastructure or every model, with a tag
//   Restore                    what (one model, every model, the whole installation), then which backup, then confirm
// Global roles are given in Keycloak (D92): the access wizards link there.
import { useEffect, useMemo, useState } from "react";
import { apiFetch, can, canOn, MODEL_ROLES, needsRole, roleName, roles } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Field, Modal } from "./ModelOps";
import { RestoreAll, RestoreInfra, RestoreModel, when } from "./Backups";
import { trackTask } from "./tasks";
import { FirstRunPanel } from "./GuidedWizards";

const post = (path, body) => apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });

function Card({ title, text, ok, why, onClick, href }) {
  return (
    <div className={`wiz-card${ok ? "" : " off"}`}>
      <h4>{title}</h4><p className="small">{text}</p>
      {!ok ? <p className="small menu-why" style={{ margin: 0 }}>{why}</p> : href ? <a className="button" href={href}>Open…</a> : <button onClick={onClick}>Start…</button>}
    </div>
  );
}

export default function SystemWizards() {
  const [open, setOpen] = useState(null);
  const ops = can("system.operate");
  const users = can("users.read");
  const sup = roles().includes("super-admin");
  const close = () => setOpen(null);
  return (
    <div className="wizards">
      <p className="quiet">The system's admin tasks, one wizard each. The settings themselves stay on their tabs.</p>
      <section><h3>People</h3><div className="wiz-grid">
        <Card title="Give a person access" text="Find the person, then give them a role on one or more models at once. Global roles are given in Keycloak"
          ok={users || sup} why={needsRole(["user-admin", "super-admin"])} onClick={() => setOpen("give")} />
        <Card title="Take a person's access away" text="Someone leaving or moving: see every model role they hold and take away those that go"
          ok={users || sup} why={needsRole(["user-admin", "super-admin"])} onClick={() => setOpen("take")} />
        <Card title="Map a Keycloak role" text="Which Keycloak roles give which EA Explorer global role" ok={users} why={needsRole(["user-admin"])} href="#/admin/users/mapping" />
      </div></section>
      <section><h3>Backups and restores</h3><div className="wiz-grid">
        <Card title="Back up now" text="The whole installation (infrastructure) or every model (application), with a tag, in the background"
          ok={ops} why={needsRole(["it-admin", "super-admin"])} onClick={() => setOpen("backup")} />
        <Card title="Restore" text="One model (over itself or as a new model), every model from an application backup, or the whole installation"
          ok={ops} why={needsRole(["it-admin", "super-admin"])} onClick={() => setOpen("restore")} />
        <Card title="When backups run" text="The schedules and how many are kept" ok={ops} why={needsRole(["it-admin", "super-admin"])} href="#/admin/backups" />
      </div></section>
      <section><h3>Set up</h3><div className="wiz-grid">
        <Card title="First-run setup" text="The essentials of a new installation, once: settings, people, the parts in use, template libraries, the charter and principles, backups"
          ok={can("settings.manage")} why={needsRole(["super-admin"])} onClick={() => setOpen("first-run")} />
      </div></section>
      <section><h3>Services</h3><div className="wiz-grid">
        <Card title="Switch an optional service on or off" text="Reports, documents, draw.io, MCP, backups: start or stop them (a copy of the config file is kept first)"
          ok={ops || can("settings.manage")} why={needsRole(["it-admin", "super-admin"])} href="#/admin/system" />
        <Card title="Restart the system" text="Every service, the database first; everyone signs in again" ok={can("settings.manage")} why={needsRole(["super-admin"])} href="#/admin/system" />
      </div></section>
      {open === "give" && <GiveAccess onClose={close} />}
      {open === "take" && <TakeAccess onClose={close} />}
      {open === "backup" && <BackupNow onClose={close} />}
      {open === "restore" && <RestoreWizard onClose={close} />}
      {open === "first-run" && <Modal wide title="First-run setup" onClose={close} actions={<button onClick={close}>Close</button>}><FirstRunPanel always /></Modal>}
    </div>
  );
}

// ---------------------------------------------------------------- people
function PersonPick({ person, setPerson }) {
  const [search, setSearch] = useState("");
  const [list, setList] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const t = setTimeout(() => apiFetch(`/api/v1/people${search ? `?search=${encodeURIComponent(search)}` : ""}`)
      .then((x) => { setList(x); setError(""); }).catch((e) => setError(e.message)), 300);
    return () => clearTimeout(t);
  }, [search]);
  return (
    <div>
      <input className="search" placeholder="Find a person by name or user name" value={search} onChange={(e) => setSearch(e.target.value)} autoFocus />
      {error && <p className="status bad">{error}</p>}
      <div className="wiz-scroll" style={{ marginTop: 8 }}>
        {(list || []).map((p) => (
          <label key={p.username} className="wiz-check"><input type="radio" checked={person?.username === p.username} onChange={() => setPerson(p)} />
            <b>{p.name || p.username}</b> <span className="quiet small">{p.username}{p.roles?.length ? ` · ${p.roles.map(roleName).join(", ")}` : ""}
              {p.enabled === false ? " · disabled" : ""}</span></label>))}
        {list && !list.length && <p className="quiet small">Nobody matches.</p>}
      </div>
    </div>
  );
}

function GiveAccess({ onClose }) {
  const { data: models } = useApi("/api/v1/models?archived=false");
  const [step, setStep] = useState(0);
  const [person, setPerson] = useState(null);
  const [role, setRole] = useState("architect");
  const [pick, setPick] = useState({});      // model id -> role
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const mine = (models || []).filter((m) => canOn(m.id, "model.people"));
  const chosen = Object.entries(pick).filter(([, r]) => r);
  async function run() {
    setBusy(true);
    const out = [];
    for (const [id, r] of chosen) {
      const m = mine.find((x) => x.id === id);
      try { await post(`/api/v1/models/${id}/people`, { username: person.username, role: r }); out.push([true, `${m.name}: ${roleName(r)}`]); }
      catch (e) { out.push([false, `${m.name}: ${e.message}`]); }
    }
    setDone(out); setBusy(false); refreshAll();
  }
  return (
    <Modal wide title="Give a person access" onClose={onClose}
      actions={done ? <button className="primary" onClick={onClose}>Close</button> : <>
        <button onClick={onClose}>Cancel</button>{step > 0 && <button onClick={() => setStep(step - 1)}>Back</button>}
        {step < 2 ? <button className="primary" disabled={(step === 0 && !person) || (step === 1 && !chosen.length)} onClick={() => setStep(step + 1)}>Next</button>
          : <button className="primary" disabled={busy} onClick={run}>{busy ? "Giving…" : `Give ${chosen.length} role${chosen.length === 1 ? "" : "s"}`}</button>}</>}>
      <ol className="wiz-steps">{["The person", "Models and roles", "Confirm"].map((s, i) => <li key={s} className={i === step ? "on" : i < step ? "done" : ""}>{s}</li>)}</ol>
      {done ? <ul>{done.map(([ok, t]) => <li key={t} className={ok ? "status ok" : "status bad"}>{t}</li>)}</ul>
        : step === 0 ? <>
          <PersonPick person={person} setPerson={setPerson} />
          {person?.keycloak_url && <p className="small">Global roles (Model Creator, Library Admin…) are given in <a href={person.keycloak_url} target="_blank" rel="noreferrer">Keycloak</a>.</p>}
        </> : step === 1 ? <>
          <div className="toolbar"><span>Role for the ticked models</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>{MODEL_ROLES.map((r) => <option key={r} value={r}>{roleName(r)}</option>)}</select>
            <span className="quiet small">Only models you may give roles on are listed (their Model Admin, or Super Admin).</span></div>
          <div className="wiz-scroll">
            {mine.map((m) => {
              const has = (person.models || []).find((x) => x.id === m.id);
              return (
                <label key={m.id} className="wiz-check"><input type="checkbox" checked={!!pick[m.id]} onChange={() => setPick((x) => ({ ...x, [m.id]: x[m.id] ? "" : role }))} />
                  {m.name} <span className="quiet small">{m.kind_name}{has ? ` · has ${has.roles.map(roleName).join(", ")}` : ""}</span>
                  {pick[m.id] && <select className="small" value={pick[m.id]} onChange={(e) => setPick((x) => ({ ...x, [m.id]: e.target.value }))}>
                    {MODEL_ROLES.map((r) => <option key={r} value={r}>{roleName(r)}</option>)}</select>}
                </label>);
            })}
            {!mine.length && <p className="quiet">There is no model you may give roles on.</p>}
          </div>
        </> : <p>{person.name || person.username} gets: {chosen.map(([id, r]) => `${roleName(r)} on ${mine.find((x) => x.id === id)?.name}`).join("; ")}.</p>}
    </Modal>
  );
}

function TakeAccess({ onClose }) {
  const [step, setStep] = useState(0);
  const [person, setPerson] = useState(null);
  const [off, setOff] = useState({});      // "model|role" -> true
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const held = useMemo(() => (person?.models || []).flatMap((m) => m.roles.map((r) => ({ m, r, k: `${m.id}|${r}` }))), [person]);
  const chosen = held.filter((h) => off[h.k]);
  async function run() {
    setBusy(true);
    const out = [];
    for (const h of chosen) {
      try {
        await apiFetch(`/api/v1/models/${h.m.id}/people/${encodeURIComponent(person.username)}?role=${h.r}`, { method: "DELETE" });
        out.push([true, `${h.m.name}: ${roleName(h.r)} taken away`]);
      } catch (e) { out.push([false, `${h.m.name}: ${e.message}`]); }
    }
    setDone(out); setBusy(false); refreshAll();
  }
  return (
    <Modal wide title="Take a person's access away" onClose={onClose}
      actions={done ? <button className="primary" onClick={onClose}>Close</button> : <>
        <button onClick={onClose}>Cancel</button>{step > 0 && <button onClick={() => setStep(step - 1)}>Back</button>}
        {step < 2 ? <button className="primary" disabled={(step === 0 && !person) || (step === 1 && !chosen.length)} onClick={() => setStep(step + 1)}>Next</button>
          : <button className="danger" disabled={busy} onClick={run}>{busy ? "Taking away…" : `Take ${chosen.length} away`}</button>}</>}>
      <ol className="wiz-steps">{["The person", "What goes", "Confirm"].map((s, i) => <li key={s} className={i === step ? "on" : i < step ? "done" : ""}>{s}</li>)}</ol>
      {done ? <ul>{done.map(([ok, t]) => <li key={t} className={ok ? "status ok" : "status bad"}>{t}</li>)}</ul>
        : step === 0 ? <PersonPick person={person} setPerson={(p) => { setPerson(p); setOff({}); }} />
        : step === 1 ? <>
          <div className="toolbar"><button onClick={() => setOff(Object.fromEntries(held.map((h) => [h.k, true])))}>Tick all</button>
            <button className="linkish" onClick={() => setOff({})}>Untick all</button>
            <span className="quiet small">A model keeps at least one Model Admin: hand it over first (Model admin &gt; Hand over).</span></div>
          <div className="wiz-scroll">{held.map((h) => (
            <label key={h.k} className="wiz-check"><input type="checkbox" checked={!!off[h.k]} onChange={() => setOff((x) => ({ ...x, [h.k]: !x[h.k] }))} />
              {h.m.name} <span className="quiet small">{roleName(h.r)}</span></label>))}
            {!held.length && <p className="quiet">{person.name || person.username} has no role on a model.</p>}</div>
          {person.keycloak_url && <p className="small">Their global roles, and switching the account off, are in <a href={person.keycloak_url} target="_blank" rel="noreferrer">Keycloak</a>.</p>}
        </> : <p>Take away from {person.name || person.username}: {chosen.map((h) => `${roleName(h.r)} on ${h.m.name}`).join("; ")}.</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- backups
function BackupNow({ onClose }) {
  const [kind, setKind] = useState("application");
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  async function run() {
    setBusy(true); setError("");
    try {
      const t = await post(`/api/v1/admin/backups/${kind}`, { tag });
      trackTask(t, "#/admin/backups");
      setMsg(kind === "application" ? "Backing up every model in the background: the Tasks tab says when it is done." : "Backing up the installation in the background.");
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  return (
    <Modal title="Back up now" onClose={onClose}
      actions={msg ? <button className="primary" onClick={onClose}>Close</button> : <><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy} onClick={run}>{busy ? "Starting…" : "Back up"}</button></>}>
      {msg ? <p className="status ok">{msg}</p> : <div className="ed-form">
        <label><input type="radio" checked={kind === "application"} onChange={() => setKind("application")} /> <b>Every model</b> (application backup): each model
          as a file to download, restore over itself or as a new model, or take to another installation</label>
        <label><input type="radio" checked={kind === "infrastructure"} onChange={() => setKind("infrastructure")} /> <b>The whole installation</b> (infrastructure backup):
          every database, the document files, the certificate, the config file and the versions</label>
        <Field label="Tag" hint="(optional)"><input value={tag} onChange={(e) => setTag(e.target.value)} placeholder="e.g. Before the upgrade" /></Field>
        {error && <p className="status bad">{error}</p>}
      </div>}
    </Modal>
  );
}

function RestoreWizard({ onClose }) {
  const { data, error } = useApi("/api/v1/admin/backups");
  const [what, setWhat] = useState("model");
  const [step, setStep] = useState(0);
  const [pick, setPick] = useState(null);
  const [final, setFinal] = useState(null);
  const infra = data?.infrastructure?.infrastructure || [];
  const runs = data?.application?.runs || [];
  const modelRows = runs.flatMap((r) => (r.models || []).filter((m) => m.status === "ok").map((m) => ({ r, m, k: `${r.name}|${m.file}` })));
  if (final === "model") return <RestoreModel b={{ where: "application", name: pick.r.name, file: pick.m.file, model: pick.m.id, modelName: pick.m.name, kind: pick.m.kind }} onClose={onClose} />;
  if (final === "all") return <RestoreAll r={pick} onClose={onClose} />;
  if (final === "infra") return <RestoreInfra b={pick} choices={data?.infrastructure?.restore_choices || {}} onClose={onClose} />;
  return (
    <Modal wide title="Restore" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>{step > 0 && <button onClick={() => { setStep(0); setPick(null); }}>Back</button>}
        {step === 0 ? <button className="primary" onClick={() => setStep(1)}>Next</button>
          : <button className="primary" disabled={!pick} onClick={() => setFinal(what === "model" ? "model" : what === "all" ? "all" : "infra")}>Next</button>}</>}>
      <ol className="wiz-steps">{["What comes back", "Which backup", "Confirm"].map((s, i) => <li key={s} className={i === step ? "on" : i < step ? "done" : ""}>{s}</li>)}</ol>
      {error && <p className="status bad">{error}</p>}
      {step === 0 ? <div className="ed-form">
        <label><input type="radio" checked={what === "model"} onChange={() => setWhat("model")} /> <b>One model</b>: over itself (what it is now is kept first) or as a new model</label>
        <label><input type="radio" checked={what === "all"} onChange={() => setWhat("all")} /> <b>Every model</b> of an application backup, as one commit each</label>
        <label><input type="radio" checked={what === "infra"} onChange={() => setWhat("infra")} /> <b>The whole installation</b> from an infrastructure backup (everyone is locked out until it is done)</label>
      </div> : !data ? <p>Loading the backups…</p> : (
        <div className="wiz-scroll">
          {what === "model" && modelRows.map((x) => (
            <label key={x.k} className="wiz-check"><input type="radio" checked={pick?.k === x.k} onChange={() => setPick(x)} />
              <b>{x.m.name}</b> <span className="quiet small">{x.r.tag || x.r.name} · {when(x.r.created)}</span></label>))}
          {what === "all" && runs.map((r) => (
            <label key={r.name} className="wiz-check"><input type="radio" checked={pick?.name === r.name} onChange={() => setPick(r)} />
              <b>{r.tag || r.name}</b> <span className="quiet small">{when(r.created)} · {(r.models || []).length} models</span></label>))}
          {what === "infra" && infra.filter((b) => b.status === "ok").map((b) => (
            <label key={b.name} className="wiz-check"><input type="radio" checked={pick?.name === b.name} onChange={() => setPick(b)} />
              <b>{b.tag || b.name}</b> <span className="quiet small">{when(b.created)}{b.version ? ` · version ${b.version}` : ""}</span></label>))}
          {((what === "model" && !modelRows.length) || (what === "all" && !runs.length) || (what === "infra" && !infra.length)) && <p className="quiet">No backups of this kind yet.</p>}
        </div>)}
    </Modal>
  );
}
