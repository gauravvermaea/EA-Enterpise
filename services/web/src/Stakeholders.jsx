// The project's stakeholder matrix (owner, 8 Nov 2026, D294): TOGAF's stakeholder management. Each stakeholder is typed in;
// power and interest (High/Medium/Low) place it on the grid and give its class (changeable); its position, concerns and the
// viewpoints and document classes that answer them, how it is engaged, contact details, notes and dated discussion notes.
import { Fragment, useMemo, useState } from "react";
import { apiDownload, apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import RichText from "./RichText";
import { Field, Modal } from "./ModelOps";

export const CATEGORIES = { corporate: "Corporate functions", "end-user": "End-user organisation", operations: "Systems operations",
  project: "Project organisation", outside: "Outside services" };
export const CLASSES = { key: "Key players", satisfied: "Keep satisfied", informed: "Keep informed", minimal: "Minimal effort" };
const CLASS_HELP = { key: "High power and interest: engage closely, involve in decisions", satisfied: "High power, less interest: consult, keep content",
  informed: "Interested, less power: keep them informed", minimal: "Little power or interest: monitor" };
const LEVELS = { H: "High", M: "Medium", L: "Low" };
// power -> interest -> class (owner, 8 Nov 2026), as the server works it out
const CLASS_OF = { H: { H: "key", M: "key", L: "satisfied" }, M: { H: "key", M: "informed", L: "satisfied" }, L: { H: "informed", M: "informed", L: "minimal" } };
export const autoClass = (p, i) => CLASS_OF[p]?.[i] || "";
const POSITION = [["disrupt", "Ability to disrupt"], ["understanding_now", "Understanding now"], ["understanding_needed", "Understanding needed"],
  ["commitment_now", "Commitment now"], ["commitment_needed", "Commitment needed"], ["support_needed", "Support needed"]];
const APPROACHES = ["Engage closely", "Consult", "Inform", "Monitor"];

function LevelSelect({ value, onChange, label, disabled }) {
  return (
    <select aria-label={label} value={value || ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      <option value="">–</option>{Object.entries(LEVELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
    </select>
  );
}

const lv = (v) => (v ? LEVELS[v] : "");

// the power/interest grid: High at the top and right; each stakeholder a chip in its cell, the cell coloured by its class
export function PowerGrid({ list, onOpen }) {
  const order = ["H", "M", "L"];
  const unplaced = list.filter((s) => !s.power || !s.interest);
  return (
    <div className="sh-grid-wrap">
      <div className="sh-grid" role="table" aria-label="Power and interest grid">
        <div className="sh-axis-y">Power / influence ↑</div>
        {order.map((pw) => (
          <div key={pw} className="sh-row" role="row">
            <div className="sh-lab" role="rowheader">{LEVELS[pw]}</div>
            {[...order].reverse().map((it) => {
              const cls = autoClass(pw, it);
              const here = list.filter((s) => s.power === pw && s.interest === it);
              return (
                <div key={it} role="cell" className={`sh-cell sh-${cls}`} title={`${CLASSES[cls]}: ${CLASS_HELP[cls]}`}>
                  {here.map((s) => (
                    <button key={s.id} className={`sh-chip${s.class !== cls ? " moved" : ""}`} onClick={() => onOpen?.(s)}
                      title={`${s.name}${s.class !== cls ? ` (set to ${CLASSES[s.class]})` : ""}`}>{s.name}</button>
                  ))}
                </div>
              );
            })}
          </div>
        ))}
        <div className="sh-row sh-foot"><div className="sh-lab" />{["Low", "Medium", "High"].map((x) => <div key={x} className="sh-lab">{x}</div>)}</div>
        <div className="sh-axis-x">Interest →</div>
      </div>
      <ul className="sh-legend small">
        {Object.entries(CLASSES).map(([k, v]) => <li key={k}><span className={`sh-swatch sh-${k}`} /> <b>{v}</b>: {CLASS_HELP[k]}</li>)}
        {unplaced.length > 0 && <li className="quiet">Not placed yet (power or interest missing): {unplaced.map((s) => s.name).join(", ")}</li>}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- the project's Stakeholders tab
export function StakeholderMatrix({ p }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/stakeholders`);
  const [open, setOpen] = useState(null);           // a stakeholder (or {} for a new one)
  const [fcls, setFcls] = useState("");
  const [fcat, setFcat] = useState("");
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");
  const list = data?.stakeholders || [];
  const shown = useMemo(() => list.filter((s) => (!fcls || s.class === fcls) && (!fcat || s.category === fcat)
    && (!q.trim() || `${s.name} ${s.organisation} ${s.role_title} ${s.concerns}`.toLowerCase().includes(q.trim().toLowerCase()))), [list, fcls, fcat, q]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const can = data.may_edit && !p.frozen;
  const overdue = list.filter((s) => s.overdue).length;
  const gaps = list.filter((s) => s.gaps.length).length;
  const uncovered = list.filter((s) => s.uncovered).length;
  return (
    <div>
      <p className="quiet">The project's stakeholders, as TOGAF's stakeholder management has them: who they are, their power and interest (which
        decides how they are engaged), their position on the change, their concerns and the viewpoints and documents that answer them.
        The sponsor is on the About tab.</p>
      {msg && <p className="status ok">{msg}</p>}
      <div className="row-gap small">
        {Object.entries(CLASSES).map(([k, v]) => <span key={k} className={`sh-count sh-${k}`}>{v}: <b>{data.counts[k] || 0}</b></span>)}
        {overdue > 0 && <span className="status bad">{overdue} overdue for contact</span>}
        {gaps > 0 && <span className="status warn">{gaps} with a commitment or understanding gap</span>}
        {uncovered > 0 && <span className="quiet">{uncovered} with no viewpoint or document answering their concerns</span>}
      </div>
      <PowerGrid list={list} onOpen={setOpen} />
      <div className="row-gap filters">
        {can && <button className="primary" onClick={() => setOpen({})}>+ Add a stakeholder</button>}
        {can && list.length > 0 && <ToArchitecture p={p} onDone={setMsg} />}
        <label className="small">Class <select value={fcls} onChange={(e) => setFcls(e.target.value)}><option value="">all</option>
          {Object.entries(CLASSES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="small">Category <select value={fcat} onChange={(e) => setFcat(e.target.value)}><option value="">all</option>
          {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search stakeholders" aria-label="Search stakeholders" />
        <button className="push-right" onClick={() => apiDownload(`/api/v1/projects/${p.id}/stakeholders?format=csv`, `${p.name} - stakeholders.csv`)
          .catch((e) => setMsg(e.message))}>⬇ CSV for Excel</button>
      </div>
      {!list.length ? <p className="quiet">No stakeholders yet.{can ? " Add the people and groups the work affects, who can influence it or care how it turns out." : ""}</p> : (
        <div className="table-scroll">
          <table className="grid-table sh-table">
            <thead><tr>
              <th>Stakeholder</th><th>Category</th><th title="Power or influence">Power</th><th>Interest</th><th>Class</th>
              <th title="Ability to disrupt">Disrupt</th><th>Understanding<br /><span className="quiet">now → needed</span></th>
              <th>Commitment<br /><span className="quiet">now → needed</span></th><th>Support needed</th><th>Concerns</th>
              <th>Approach</th><th>Looked after by</th><th>Last / next contact</th>
            </tr></thead>
            <tbody>
              {shown.map((s) => (
                <tr key={s.id}>
                  <td><button className="linkish" onClick={() => setOpen(s)}><b>{s.name}</b></button>
                    {(s.role_title || s.organisation) && <div className="small quiet">{[s.role_title, s.organisation].filter(Boolean).join(", ")}</div>}</td>
                  <td className="small">{CATEGORIES[s.category] || ""}</td>
                  <td>{lv(s.power)}</td><td>{lv(s.interest)}</td>
                  <td>{s.class ? <span className={`sh-count sh-${s.class}`} title={s.class_set ? `Set by hand (the grid says ${CLASSES[s.class_auto] || "nothing yet"})` : "From power and interest"}>
                    {CLASSES[s.class]}{s.class_set ? " ✎" : ""}</span> : <span className="quiet">–</span>}</td>
                  <td>{lv(s.disrupt)}</td>
                  <td className={s.gaps.includes("understanding") ? "sh-gap" : ""}>{lv(s.understanding_now) || "–"} → {lv(s.understanding_needed) || "–"}</td>
                  <td className={s.gaps.includes("commitment") ? "sh-gap" : ""}>{lv(s.commitment_now) || "–"} → {lv(s.commitment_needed) || "–"}</td>
                  <td>{lv(s.support_needed)}</td>
                  <td className="small">{s.concerns}{s.uncovered && s.concerns && <div className="quiet">no viewpoint or document yet</div>}</td>
                  <td className="small">{s.approach}{s.frequency ? `, ${s.frequency}` : ""}{s.channel ? ` (${s.channel})` : ""}</td>
                  <td className="small">{s.owner}</td>
                  <td className="small nowrap">{s.last_contact || "–"} / <span className={s.overdue ? "bad-text" : ""}>{s.next_contact || "–"}</span></td>
                </tr>
              ))}
              {!shown.length && <tr><td colSpan="13" className="quiet">No stakeholder matches the filters.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {open && <StakeholderDialog p={p} s={open} can={can} onClose={(m) => { setOpen(null); if (m) setMsg(m); refreshAll(); }} />}
    </div>
  );
}

const BLANK = { name: "", organisation: "", role_title: "", category: "", email: "", phone: "", concerns: "", power: "", interest: "", class: "",
  disrupt: "", understanding_now: "", understanding_needed: "", commitment_now: "", commitment_needed: "", support_needed: "", approach: "",
  frequency: "", channel: "", owner: "", next_contact: "", notes_html: "", viewpoints: [], items: [] };

function StakeholderDialog({ p, s, can, onClose }) {
  const isNew = !s.id;
  const [f, setF] = useState(() => ({ ...BLANK, ...s, class: s.class_set ? s.class : "", approach: s.approach_set ? s.approach : "",
    items: (s.items || []).map((i) => i.id) }));
  const [tab, setTab] = useState("who");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const auto = autoClass(f.power, f.interest);
  const vps = p.viewpoints || [];
  const items = (p.items || []).filter((i) => i.chosen);
  async function save() {
    setBusy(true); setErr("");
    try {
      const out = await apiFetch(isNew ? `/api/v1/projects/${p.id}/stakeholders` : `/api/v1/projects/${p.id}/stakeholders/${s.id}`,
        { method: isNew ? "POST" : "PUT", body: JSON.stringify(f) });
      onClose(out.message);
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  async function remove() {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Take ${s.name} out of the stakeholders, with its discussion notes?`)) return;
    try { const out = await apiFetch(`/api/v1/projects/${p.id}/stakeholders/${s.id}`, { method: "DELETE" }); onClose(out.message); }
    catch (e) { setErr(e.message); }
  }
  const tabs = [["who", "Who"], ["position", "Position"], ["concerns", "Concerns"], ["engage", "Engagement"], ["notes", "Notes"],
    ...(isNew ? [] : [["talks", "Discussions"]])];
  return (
    <Modal title={isNew ? "Add a stakeholder" : s.name} onClose={() => onClose()} wide
      actions={<>{!isNew && can && <button className="danger" onClick={remove}>Take out…</button>}<button onClick={() => onClose()}>{can ? "Cancel" : "Close"}</button>
        {can && tab !== "talks" && <button className="primary" disabled={busy || !f.name.trim()} onClick={save}>{busy ? "Saving…" : "Save"}</button>}</>}>
      <div className="tabs sub" role="tablist">
        {tabs.map(([k, v]) => <button key={k} role="tab" aria-selected={tab === k} className={`tab${tab === k ? " on" : ""}`} onClick={() => setTab(k)}>{v}</button>)}
      </div>
      <fieldset className="ed-form" disabled={!can}>
        {tab === "who" && <>
          <Field label="Name" hint="(a person or a group)"><input value={f.name} onChange={(e) => set("name", e.target.value)} autoFocus /></Field>
          <Field label="Role"><input value={f.role_title} onChange={(e) => set("role_title", e.target.value)} placeholder="e.g. CIO" /></Field>
          <Field label="Organisation"><input value={f.organisation} onChange={(e) => set("organisation", e.target.value)} /></Field>
          <Field label="Category" hint="(TOGAF's groups of stakeholders)">
            <select value={f.category} onChange={(e) => set("category", e.target.value)}><option value="">–</option>
              {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Email"><input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
          <Field label="Phone"><input value={f.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
        </>}
        {tab === "position" && <>
          <div className="row-gap">
            <Field label="Power / influence"><LevelSelect label="Power" value={f.power} onChange={(v) => set("power", v)} /></Field>
            <Field label="Interest"><LevelSelect label="Interest" value={f.interest} onChange={(v) => set("interest", v)} /></Field>
          </div>
          <Field label="Class" hint={auto ? `(the grid says ${CLASSES[auto]})` : "(give power and interest)"}>
            <select value={f.class} onChange={(e) => set("class", e.target.value)}>
              <option value="">{auto ? `From the grid: ${CLASSES[auto]}` : "From the grid"}</option>
              {Object.entries(CLASSES).map(([k, v]) => <option key={k} value={k}>{v} (set by hand)</option>)}</select></Field>
          <div className="sh-position">
            {POSITION.map(([k, label]) => <Field key={k} label={label}><LevelSelect label={label} value={f[k]} onChange={(v) => set(k, v)} /></Field>)}
          </div>
        </>}
        {tab === "concerns" && <>
          <Field label="Key concerns"><textarea rows={3} value={f.concerns} onChange={(e) => set("concerns", e.target.value)} /></Field>
          <h4>What answers them</h4>
          <p className="small quiet">The viewpoints and documents to produce and go through with them.</p>
          <div className="sh-picks">
            <div><b className="small">Viewpoints</b>
              {vps.length ? vps.map((v) => <label key={v.code} className="small"><input type="checkbox" checked={f.viewpoints.includes(v.code)}
                onChange={(e) => set("viewpoints", e.target.checked ? [...f.viewpoints, v.code] : f.viewpoints.filter((x) => x !== v.code))} /> {v.code} {v.name}</label>)
                : <p className="small quiet">The project has no viewpoints yet.</p>}</div>
            <div><b className="small">Document classes</b>
              {items.map((i) => <label key={i.id} className="small"><input type="checkbox" checked={f.items.includes(i.id)}
                onChange={(e) => set("items", e.target.checked ? [...f.items, i.id] : f.items.filter((x) => x !== i.id))} /> {i.phase} · {i.name}</label>)}</div>
          </div>
        </>}
        {tab === "engage" && <>
          <Field label="Approach" hint={auto || f.class ? `(empty: ${["Engage closely", "Consult", "Inform", "Monitor"][["key", "satisfied", "informed", "minimal"].indexOf(f.class || auto)]})` : ""}>
            <input list="sh-approaches" value={f.approach} onChange={(e) => set("approach", e.target.value)} />
            <datalist id="sh-approaches">{APPROACHES.map((a) => <option key={a} value={a} />)}</datalist></Field>
          <Field label="How often"><input value={f.frequency} onChange={(e) => set("frequency", e.target.value)} placeholder="e.g. monthly, at each phase gate" /></Field>
          <Field label="Channel"><input value={f.channel} onChange={(e) => set("channel", e.target.value)} placeholder="e.g. steering committee, email update" /></Field>
          <Field label="Looked after by"><input value={f.owner} onChange={(e) => set("owner", e.target.value)} placeholder="who on the project keeps in touch" /></Field>
          <Field label="Next contact"><input type="date" value={f.next_contact || ""} onChange={(e) => set("next_contact", e.target.value)} /></Field>
          {!isNew && <p className="small quiet">Last contact: {s.last_contact || "none noted yet"} (the latest discussion note).</p>}
        </>}
        {tab === "notes" && <RichText value={f.notes_html} onChange={(v) => set("notes_html", v)} placeholder="Anything about them: history, sensitivities, what matters to them" />}
      </fieldset>
      {tab === "talks" && <Discussions p={p} s={s} can={can} />}
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

function Discussions({ p, s, can }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/stakeholders/${s.id}/notes`);
  const [edit, setEdit] = useState(null);          // a note being written or changed
  const [err, setErr] = useState("");
  async function save() {
    setErr("");
    try {
      await apiFetch(edit.id ? `/api/v1/projects/${p.id}/stakeholder-notes/${edit.id}` : `/api/v1/projects/${p.id}/stakeholders/${s.id}/notes`,
        { method: edit.id ? "PUT" : "POST", body: JSON.stringify(edit) });
      setEdit(null); refreshAll();
    } catch (e) { setErr(e.message); }
  }
  async function remove(n) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete the note of ${n.held_on}?`)) return;
    try { await apiFetch(`/api/v1/projects/${p.id}/stakeholder-notes/${n.id}`, { method: "DELETE" }); refreshAll(); } catch (e) { setErr(e.message); }
  }
  if (error) return <p className="status bad">{error}</p>;
  return (
    <div className="sh-talks">
      {can && !edit && <button onClick={() => setEdit({ held_on: new Date().toISOString().slice(0, 10), title: "", html: "" })}>+ Note a discussion</button>}
      {edit && (
        <div className="ed-form sh-note-edit">
          <div className="row-gap">
            <Field label="When"><input type="date" value={edit.held_on} onChange={(e) => setEdit({ ...edit, held_on: e.target.value })} /></Field>
            <Field label="Subject"><input value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} placeholder="e.g. Phase B review" /></Field>
          </div>
          <RichText value={edit.html} onChange={(v) => setEdit({ ...edit, html: v })} placeholder="What was discussed, agreed, asked" />
          <div className="row-gap"><button className="primary" onClick={save}>Save the note</button><button onClick={() => setEdit(null)}>Cancel</button></div>
        </div>
      )}
      {!data ? <p className="quiet">Loading...</p> : !data.notes.length ? <p className="quiet small">No discussions noted yet.</p> : data.notes.map((n) => (
        <Fragment key={n.id}>
          <div className="sh-note">
            <div className="row-gap small"><b>{n.held_on}</b>{n.title && <span>{n.title}</span>}<span className="quiet">by {n.by}</span>
              {can && <span className="push-right"><button className="linkish" onClick={() => setEdit({ id: n.id, held_on: n.held_on, title: n.title, html: n.html })}>Change</button>
                {" · "}<button className="linkish" onClick={() => remove(n)}>Delete</button></span>}</div>
            <div className="rich-view" dangerouslySetInnerHTML={{ __html: n.html }} />
          </div>
        </Fragment>
      ))}
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- the wizard's step: the template's suggestions to keep, change or add to
export function StakeholdersStep({ d, set, edit, projectId }) {
  if (edit) {
    return (
      <div>
        <p className="quiet">The project's stakeholders are kept on its <a href={`#/projects/${projectId}/stakeholders`}>Stakeholders tab</a>: their position, concerns,
          engagement and discussions. Change them there.</p>
      </div>
    );
  }
  const rows = d.stakeholders || [];
  const upd = (i, k, v) => set("stakeholders", rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div>
      <p className="quiet">Who the work affects, who can influence it and who cares how it turns out. Power and interest place each one on TOGAF's grid
        and decide how they are engaged. {d.template ? "The kind of project suggests these: keep, change or remove them." : ""} Their position,
        concerns, engagement and discussions go on the project's Stakeholders tab once it is made.</p>
      <div className="table-scroll">
        <table className="grid-table sh-table">
          <thead><tr><th>Stakeholder</th><th>Role</th><th>Category</th><th>Power</th><th>Interest</th><th>Class</th><th>Key concerns</th><th /></tr></thead>
          <tbody>
            {rows.map((r, i) => {
              const cls = autoClass(r.power, r.interest);
              return (
                <tr key={i}>
                  <td><input aria-label="Stakeholder" value={r.name} onChange={(e) => upd(i, "name", e.target.value)} placeholder="a person or a group" /></td>
                  <td><input aria-label="Role" value={r.role_title || ""} onChange={(e) => upd(i, "role_title", e.target.value)} /></td>
                  <td><select aria-label="Category" value={r.category || ""} onChange={(e) => upd(i, "category", e.target.value)}><option value="">–</option>
                    {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
                  <td><LevelSelect label="Power" value={r.power} onChange={(v) => upd(i, "power", v)} /></td>
                  <td><LevelSelect label="Interest" value={r.interest} onChange={(v) => upd(i, "interest", v)} /></td>
                  <td>{cls ? <span className={`sh-count sh-${cls}`}>{CLASSES[cls]}</span> : <span className="quiet">–</span>}</td>
                  <td><input aria-label="Key concerns" value={r.concerns || ""} onChange={(e) => upd(i, "concerns", e.target.value)} /></td>
                  <td><button className="linkish" aria-label={`Remove ${r.name}`} onClick={() => set("stakeholders", rows.filter((_x, j) => j !== i))}>Remove</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <button onClick={() => set("stakeholders", [...rows, { name: "", role_title: "", category: "", power: "", interest: "", concerns: "" }])}>+ Add a stakeholder</button>
      {rows.some((r) => r.name.trim()) && <PowerGrid list={rows.filter((r) => r.name.trim()).map((r, i) => ({ ...r, id: `w${i}`, class: autoClass(r.power, r.interest) }))} />}
    </div>
  );
}

// the stakeholders into the project's organisation and into one of its models as Stakeholder entities (D302)
function ToArchitecture({ p, onDone }) {
  const [model, setModel] = useState(() => (p.models || []).find((m) => m.home)?.id || p.models?.[0]?.id || "");
  const [busy, setBusy] = useState(false);
  async function go(url, body) {
    setBusy(true);
    try { const r = await apiFetch(url, { method: "POST", body: JSON.stringify(body) }); onDone(r.message); refreshAll(); }
    catch (e) { onDone(e.message); }
    setBusy(false);
  }
  return (
    <span className="row-gap small">
      <button disabled={busy} title="List every stakeholder not listed yet in the project's Organisation tab, with their role"
        onClick={() => go(`/api/v1/projects/${p.id}/organisation`, { stakeholders: true })}>⇢ Organisation</button>
      {(p.models || []).length > 0 && <>
        <select value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model for the stakeholders">
          {p.models.map((m) => <option key={m.id} value={m.id}>{m.name}{m.home ? " (project's model)" : ""}</option>)}</select>
        <button disabled={busy || !model} title="Make each stakeholder a Stakeholder entity in the model (ones made before are brought up to date)"
          onClick={() => go(`/api/v1/projects/${p.id}/stakeholders/to-model`, { model })}>⇢ Into the model</button>
      </>}
    </span>
  );
}
