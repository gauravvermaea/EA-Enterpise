// Data entry (build phase 6): forms generated from the metamodel, entity actions (edit, retire, restore,
// delete, roll back), relationships (add from what the metamodel allows, or outside it with D49, remove),
// and the data entry page by entity type (D79). Every save is visible to everyone at once (D61); rules warn,
// never block (D48). Controls a person may not use are greyed out with the role they need (D125).
import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, canOn, currentUser, needsRole } from "./auth";
import { Modal as BaseModal } from "./ModelOps";

// the dialogs' content sits in the usual padded, scrolling form area
function Modal({ children, ...props }) {
  return <BaseModal {...props}><div className="ed-form">{children}</div></BaseModal>;
}
import { refreshAll, Swatch, useApi } from "./ModelViews";
import { PendingBanner, PendingMark } from "./ModelMarks";
import { EntityChanges, useEntityChanges, WasValue } from "./Changes";

const CONTENT_ROLES = ["architect", "model-sub-admin", "model-admin"];
const me = () => currentUser().preferred_username || "";

// Can the signed-in person change this model's content? { ok, why } (the server checks again)
export function contentAccess(model, m, retiredType = false) {
  if (!m) return { ok: false, why: "" };
  if (m.kind === "template") return { ok: false, why: "A root metamodel holds no entities: create a model from it (Actions)." };
  if (m.is_locked) return { ok: false, why: `${m.name} is locked (read-only). Create a model from it (Actions) to work on a copy.` };
  if (m.kind === "reference") return { ok: false, why: `${m.name} is a library model (read-only). Create a model from it to work on a copy.` };
  if (m.lock_level === "content") return { ok: false, why: `${m.name}'s content is locked by ${m.locked_by}.` };
  if (m.lock_level === "maintenance" && m.locked_by !== me()) return { ok: false, why: `${m.name} is locked for maintenance by ${m.locked_by}.` };
  if (retiredType) return { ok: false, why: "This entity type is retired: its entities are read-only until a Model Admin restores the type (D87)." };
  if (!canOn(model, "model.content")) return { ok: false, why: `Changing content: ${needsRole(CONTENT_ROLES, m.name)}` };
  return { ok: true, why: "" };
}

function Gate({ access, label, onClick, className = "", title, danger }) {
  return (
    <button className={`${access.ok ? (danger ? "danger" : "ed-btn") : "later"} ${className}`} disabled={!access.ok}
      title={access.ok ? title : access.why} onClick={onClick}>{label}</button>
  );
}

// ---------------------------------------------------------------- one field of a form
export function EntityPicker({ model, value, label, types, onChange, placeholder = "Search by name or ID", autoFocus }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [found, setFound] = useState([]);
  const timer = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const params = new URLSearchParams({ q, limit: "30" });
      (types || []).forEach((t) => params.append("type", t));
      apiFetch(`/api/v1/models/${model}/entity-picker?${params}`).then(setFound).catch(() => setFound([]));
    }, 200);
    return () => clearTimeout(timer.current);
  }, [q, open, model, (types || []).join(",")]);
  return (
    <div className="picker">
      {value && !open
        ? <span className="picked">{label || value} <button type="button" className="linkish" onClick={() => onChange(null, "")} title="Clear">✕</button>
            <button type="button" className="linkish" onClick={() => setOpen(true)}>change</button></span>
        : <input type="search" autoFocus={autoFocus} placeholder={placeholder} value={q} onFocus={() => setOpen(true)}
            onChange={(e) => { setQ(e.target.value); setOpen(true); }} />}
      {open && (
        <ul className="picker-list" onMouseDown={(e) => e.preventDefault()}>
          {found.map((x) => (
            <li key={x.id}><button type="button" className="linkish" onClick={() => { onChange(x.id, x.name, x); setOpen(false); setQ(""); }}>
              <Swatch colour={x.colour} /> {x.name} <span className="quiet">{x.display_id} · {x.entity_type}{x.status === "retired" ? " · retired" : ""}</span>
            </button></li>
          ))}
          {!found.length && <li className="quiet">No entities match.</li>}
          <li><button type="button" className="linkish quiet" onClick={() => setOpen(false)}>close</button></li>
        </ul>
      )}
    </div>
  );
}

export function ValueInput({ model, a, value, onChange, id }) {
  const v = value ?? "";
  switch (a.data_type) {
    case "long_text":
      return <textarea id={id} rows={3} value={v} onChange={(e) => onChange(e.target.value)} />;
    case "list":
      return (
        <select id={id} value={v} onChange={(e) => onChange(e.target.value)}>
          <option value="">(not set)</option>
          {a.pick_list_values.map((p) => <option key={p} value={p}>{p}</option>)}
          {v && !a.pick_list_values.includes(v) && <option value={v}>{v} (not in the list)</option>}
        </select>
      );
    case "boolean":
      return (
        <select id={id} value={v === true || v === "Yes" ? "Yes" : v === false || v === "No" ? "No" : ""} onChange={(e) => onChange(e.target.value)}>
          <option value="">(not set)</option><option>Yes</option><option>No</option>
        </select>
      );
    case "date":
      return <input id={id} type="date" value={String(v).slice(0, 10)} onChange={(e) => onChange(e.target.value)} />;
    case "integer": case "decimal": case "currency": case "percent":
      return <input id={id} type="text" inputMode="decimal" value={v} onChange={(e) => onChange(e.target.value)}
        placeholder={a.data_type === "integer" ? "whole number" : "number"} />;
    case "entity_ref":
      return <EntityPicker model={model} value={value?.id || null} label={value?.name} onChange={(i, n) => onChange(i ? { id: i, name: n } : null)} />;
    default:
      return <input id={id} type={a.data_type === "email" ? "email" : a.data_type === "url" ? "url" : "text"} value={v}
        onChange={(e) => onChange(e.target.value)} />;
  }
}

// ---------------------------------------------------------------- the form (create or edit)
function initialValues(e, form) {
  const out = {};
  for (const a of form.attributes) {
    const cur = e?.attributes?.find((x) => x.code === a.code);
    if (!cur || cur.value === null || cur.value === undefined) continue;
    out[a.code] = a.data_type === "entity_ref" ? { id: cur.ref_id, name: cur.value }
      : a.data_type === "date" ? String(cur.typed || cur.value).slice(0, 10) : cur.value;
  }
  return out;
}

export function EntityFormDialog({ model, m, typeId, e, onClose, onSaved }) {
  const { data: form, error } = useApi(`/api/v1/models/${model}/forms/${typeId || e?.entity_type_id}`);
  const [name, setName] = useState(e?.name || "");
  const [description, setDescription] = useState(e?.description || "");
  const [parent, setParent] = useState(e?.parent_id ? { id: e.parent_id, name: e.parent_name } : null);
  const [tags, setTags] = useState((e?.tags || []).join(", "));
  const [values, setValues] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [saved, setSaved] = useState(null);
  const ec = useEntityChanges(model, m, e?.id);   // my uncommitted changes to it, highlighted (phase 8)
  const f = (code) => ec.fields[String(code).toLowerCase()];
  useEffect(() => { if (form && values === null) setValues(initialValues(e, form)); }, [form]);
  if (!form || values === null) return <Modal title="Loading..." onClose={onClose}><p className="quiet">{error || "Loading the form..."}</p></Modal>;
  const sections = [];
  for (const a of form.attributes) {
    let s = sections.find((x) => x.name === a.section);
    if (!s) sections.push(s = { name: a.section, items: [] });
    s.items.push(a);
  }
  const before = e ? initialValues(e, form) : {};
  const changedValues = () => {
    const out = {};
    for (const a of form.attributes) {
      const now = values[a.code];
      const was = before[a.code];
      const norm = (x) => (x && typeof x === "object" ? x.id : x ?? "");
      if (String(norm(now)) !== String(norm(was))) out[a.code] = a.data_type === "entity_ref" ? (now?.id || "") : now ?? "";
    }
    return out;
  };
  const missing = form.attributes.filter((a) => a.is_required && (values[a.code] === undefined || values[a.code] === "" || values[a.code] === null));
  async function save(another = false) {
    setBusy(true); setMsg("");
    const body = { values: changedValues() };
    if (!e) Object.assign(body, { entity_type: form.entity_type.id, name, description, parent: parent?.id || "", tags });
    else {
      if (name !== e.name) body.name = name;
      if (description !== (e.description || "")) body.description = description;
      if ((parent?.id || null) !== (e.parent_id || null)) body.parent = parent?.id || "";
      if (tags !== (e.tags || []).join(", ")) body.tags = tags;
      body.row_version = e.row_version;
    }
    try {
      const out = await apiFetch(e ? `/api/v1/models/${model}/content/entities/${e.id}` : `/api/v1/models/${model}/content/entities`,
        { method: e ? "PATCH" : "POST", body: JSON.stringify(body) });
      refreshAll();
      if (out.saved_warnings?.length) { setSaved(out); setBusy(false); return; }
      if (another) {
        setName(""); setDescription(""); setTags(""); setValues({}); setParent(null);
        setMsg(`Saved ${out.display_id} ${out.name}. Enter the next one.`); setBusy(false); return;
      }
      onSaved?.(out); onClose();
    } catch (err) { setMsg(err.message); setBusy(false); }
  }
  if (saved) {
    return (
      <Modal title={`Saved ${saved.display_id} ${saved.name}, with warnings`} onClose={() => { onSaved?.(saved); onClose(); }}
        actions={<button className="ed-btn" onClick={() => { onSaved?.(saved); onClose(); }}>OK</button>}>
        <p>It is saved. These rules fail; the values are kept with a flag and these details, and the warnings show until fixed (D48):</p>
        <ul>{saved.saved_warnings.map((w, i) => <li key={i}><span className={`sev ${w.severity}`}>{w.severity}</span> {w.field}: {w.message}</li>)}</ul>
      </Modal>
    );
  }
  return (
    <Modal wide title={e ? `Edit ${e.display_id} ${e.name}` : `New ${form.entity_type.name}`} onClose={onClose}
      actions={<>
        {!e && <button className="ed-btn secondary" disabled={busy || !name.trim()} onClick={() => save(true)} title="Save and start the next one">Save and new</button>}
        <button className="ed-btn" disabled={busy || !name.trim()} onClick={() => save(false)}>{busy ? "Saving..." : "Save"}</button>
      </>}>
      {msg && <p className={msg.startsWith("Saved") ? "status ok" : "status bad"}>{msg}</p>}
      {e && <EntityChanges model={model} entity={e} ec={ec} compact />}
      <div className="form-grid">
        <label className={`ed-field${f("name") ? " pending-field" : ""}`}><span>Name <span className="req">*</span> <WasValue f={f("name")} /></span>
          <input autoFocus value={name} onChange={(ev) => setName(ev.target.value)} /></label>
        <label className="ed-field"><span>Display ID</span>
          <input value={e?.display_id || ""} disabled placeholder={`${form.entity_type.id_prefix}-next number`} title="Given when saved" /></label>
        <label className={`ed-field wide${f("description") ? " pending-field" : ""}`}><span>Description <WasValue f={f("description")} /></span>
          <textarea rows={2} value={description} onChange={(ev) => setDescription(ev.target.value)} /></label>
        <div className="ed-field"><span title="The entity this one is part of (for hierarchies such as capability levels)">Part of (parent) <span className="tip">ⓘ</span></span>
          <EntityPicker model={model} value={parent?.id} label={parent?.name} types={[form.entity_type.id]}
            onChange={(i, n) => setParent(i ? { id: i, name: n } : null)} /></div>
        <label className="ed-field"><span title="Words to group and find entities by, separated by commas">Tags <span className="tip">ⓘ</span></span>
          <input value={tags} onChange={(ev) => setTags(ev.target.value)} placeholder="for example cloud, critical" /></label>
      </div>
      {sections.map((s) => (
        <fieldset key={s.name} className="form-section">
          <legend>{s.name}</legend>
          <div className="form-grid">
            {s.items.map((a) => {
              const cur = e?.attributes?.find((x) => x.code === a.code);
              const warn = cur?.warnings?.length ? cur.warnings.map((w) => w.message).join("; ") : "";
              return (
                <div key={a.code} className={`ed-field${a.data_type === "long_text" ? " wide" : ""}${f(`value:${a.code}`) ? " pending-field" : ""}`}>
                  <label htmlFor={`f-${a.code}`} title={[a.description, a.data_type_name, a.pick_list_values.length ? `One of: ${a.pick_list_values.join(", ")}` : ""].filter(Boolean).join(" · ")}>
                    {a.name}{a.is_required && <span className="req" title="Required">*</span>}{a.unit && <span className="quiet"> ({a.unit})</span>} <span className="tip">ⓘ</span> <WasValue f={f(`value:${a.code}`)} />
                  </label>
                  <ValueInput model={model} a={a} id={`f-${a.code}`} value={values[a.code]} onChange={(v) => setValues((x) => ({ ...x, [a.code]: v }))} />
                  {warn && <span className="sev warning small" title={cur?.override ? `Saved anyway by ${cur.override.by} on ${new Date(cur.override.at).toLocaleString()}` : undefined}>{warn}</span>}
                </div>
              );
            })}
          </div>
        </fieldset>
      ))}
      {missing.length > 0 && <p className="quiet">Required and still empty: {missing.map((a) => a.name).join(", ")}. You can save anyway; it shows as a warning (D48).</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- buttons on the entity page and type table
export function NewEntityButton({ model, m, typeId, typeName, retired, onSaved, label }) {
  const [open, setOpen] = useState(false);
  const access = contentAccess(model, m, retired);
  return (
    <>
      <Gate access={access} label={label || `+ New ${typeName || "entity"}`} onClick={() => setOpen(true)} title={`Enter a new ${typeName || "entity"} in a form`} />
      {open && <EntityFormDialog model={model} m={m} typeId={typeId} onClose={() => setOpen(false)}
        onSaved={(out) => (onSaved ? onSaved(out) : (window.location.hash = `/metamodel/${model}/entity/${out.id}`))} />}
    </>
  );
}

export function EntityActions({ model, m, e }) {
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState("");
  const access = contentAccess(model, m, e.entity_type_status === "retired");
  async function act(path, method = "POST") {
    setMsg("");
    try {
      const out = await apiFetch(`/api/v1/models/${model}/content/entities/${e.id}${path}`, { method });
      refreshAll();
      return out;
    } catch (err) { setMsg(err.message); return null; }
  }
  return (
    <span className="entity-actions">
      <Gate access={access} label="✎ Edit" onClick={() => setEditing(true)} title="Change the name, description, parent, tags and values" />
      {e.status === "retired"
        ? <Gate access={access} label="Restore" onClick={() => act("/restore")} title="Make it current again" />
        : <Gate access={access} label="Retire" onClick={() => act("/retire")} title="No longer in use: kept, shown as retired" />}
      <Gate access={access} label="Delete..." danger onClick={() => setConfirm(true)} title="Delete it with its values and relationships (kept in history)" />
      {msg && <span className="status bad">{msg}</span>}
      {editing && <EntityFormDialog model={model} m={m} e={e} onClose={() => setEditing(false)} />}
      {confirm && (
        <Modal title={`Delete ${e.display_id} ${e.name}?`} onClose={() => setConfirm(false)}
          actions={<button className="danger" onClick={async () => { const out = await act("", "DELETE"); setConfirm(false);
            if (out) window.location.hash = `/metamodel/${model}/types/${e.entity_type_id}`; }}>Delete</button>}>
          <p>{e.name} and its {e.relationships.length} relationship{e.relationships.length === 1 ? "" : "s"} are removed from the model.
            Its history is kept. Retire it instead if it is only no longer in use.</p>
        </Modal>
      )}
    </span>
  );
}

// ---------------------------------------------------------------- relationships
export function AddRelationshipButton({ model, m, e, label = "+ Relationship", className = "" }) {
  const [open, setOpen] = useState(false);
  const access = contentAccess(model, m, e.entity_type_status === "retired");
  return (
    <>
      <Gate access={access} className={className} label={label} onClick={() => setOpen(true)} title={`Relate ${e.name} to an existing entity`} />
      {open && <AddRelationshipDialog model={model} m={m} e={e} onClose={() => setOpen(false)} />}
    </>
  );
}

function AddRelationshipDialog({ model, m, e, onClose }) {
  const { data: opts, error } = useApi(`/api/v1/models/${model}/content/entities/${e.id}/relationship-options`);
  const [mode, setMode] = useState("allowed");
  const [choice, setChoice] = useState("");
  const [relType, setRelType] = useState("");
  const [direction, setDirection] = useState("outgoing");
  const [other, setOther] = useState(null);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const [outside, setOutside] = useState(false);
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState([]);
  const allowed = opts?.allowed || [];
  const pick = mode === "allowed" ? allowed[Number(choice)] : null;
  const groups = useMemo(() => {
    const g = [];
    allowed.forEach((a, i) => {
      const key = `${a.direction}|${a.relationship_type}`;
      let x = g.find((y) => y.key === key);
      if (!x) g.push(x = { key, a, items: [] });
      x.items.push([i, a]);
    });
    return g;
  }, [opts]);
  if (!opts) return <Modal title="Loading..." onClose={onClose}><p className="quiet">{error || "Loading what the metamodel allows..."}</p></Modal>;
  const dir = pick ? pick.direction : direction;
  const typeName = pick ? pick.relationship_type : opts.relationship_types.find((r) => r.id === relType)?.name;
  async function add(allowOutside = false) {
    if (!other || !(pick || relType)) return;
    setBusy(true); setMsg("");
    const body = {
      source: dir === "outgoing" ? e.id : other.id, target: dir === "outgoing" ? other.id : e.id,
      relationship_type: pick ? pick.relationship_type_id : relType, name, allow_outside: allowOutside,
    };
    try {
      const out = await apiFetch(`/api/v1/models/${model}/content/relationships`, { method: "POST", body: JSON.stringify(body) });
      refreshAll();
      setAdded((x) => [...x, `${typeName} ${dir === "outgoing" ? "→" : "←"} ${other.name}${out.outside_metamodel ? " (added to the metamodel, flagged)" : ""}`]);
      setOther(null); setName(""); setOutside(false);
    } catch (err) {
      if (/does not allow/.test(err.message)) setOutside(true);
      setMsg(err.message);
    }
    setBusy(false);
  }
  return (
    <Modal wide title={`Relate ${e.name} to...`} onClose={onClose}
      actions={<>
        {outside && <button className="ed-btn secondary" disabled={busy} onClick={() => add(true)}
          title="Adds this relationship type between these entity types to the model's metamodel, flagged for a Model Admin to review (D49)">Add anyway (outside the metamodel)</button>}
        <button className="ed-btn" disabled={busy || !other || !(pick || relType)} onClick={() => add(false)}>Add</button>
        <button className="ed-btn secondary" onClick={onClose}>Done</button>
      </>}>
      <div className="seg">
        <button className={mode === "allowed" ? "on" : ""} onClick={() => { setMode("allowed"); setOther(null); setOutside(false); setMsg(""); }}>
          What the metamodel allows ({allowed.length})</button>
        <button className={mode === "any" ? "on" : ""} onClick={() => { setMode("any"); setOther(null); setOutside(false); setMsg(""); }}
          title="Any relationship type to any entity; if the metamodel does not allow it you can still add it, which adds it to the metamodel, flagged (D49)">
          Any relationship</button>
      </div>
      {mode === "allowed" ? (
        <label className="ed-field"><span>Relationship and the type at the other end</span>
          <select value={choice} onChange={(ev) => { setChoice(ev.target.value); setOther(null); }}>
            <option value="">Choose...</option>
            {groups.map((g) => (
              <optgroup key={g.key} label={g.a.direction === "outgoing" ? `${e.name} ${g.a.verb} →` : `→ ${g.a.verb} ${e.name}`}>
                {g.items.map(([i, a]) => <option key={i} value={i}>{a.relationship_type}: {a.other_type}{a.from_content ? " (added from data entry)" : ""}</option>)}
              </optgroup>
            ))}
          </select></label>
      ) : (
        <div className="form-grid">
          <label className="ed-field"><span>Relationship type</span>
            <select value={relType} onChange={(ev) => setRelType(ev.target.value)}>
              <option value="">Choose...</option>
              {opts.relationship_types.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.verb})</option>)}
            </select></label>
          <label className="ed-field"><span>Direction</span>
            <select value={direction} onChange={(ev) => setDirection(ev.target.value)}>
              <option value="outgoing">{e.name} → the other</option><option value="incoming">the other → {e.name}</option>
            </select></label>
        </div>
      )}
      {(pick || (mode === "any" && relType)) && (
        <div className="ed-field"><span>{pick ? `The ${pick.other_type}` : "The other entity"} (existing entities only; save a new one first)</span>
          <EntityPicker model={model} autoFocus value={other?.id} label={other?.name} types={pick ? [pick.other_type_id] : []}
            onChange={(i, n) => { setOther(i ? { id: i, name: n } : null); setOutside(false); setMsg(""); }} />
        </div>
      )}
      <label className="ed-field"><span>Label (optional)</span><input value={name} onChange={(ev) => setName(ev.target.value)} placeholder="for example nightly file" /></label>
      {msg && <p className="status bad">{msg}</p>}
      {added.length > 0 && <div className="status ok">Added: <ul>{added.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
    </Modal>
  );
}

export function RemoveRelationshipButton({ model, m, e, r }) {
  const access = contentAccess(model, m);
  const [msg, setMsg] = useState("");
  return (
    <>
      <button className={access.ok ? "linkish danger-text" : "linkish later-text"} disabled={!access.ok}
        title={access.ok ? `Remove: ${e.name} ${r.verb} ${r.other_name} (kept in history)` : access.why}
        onClick={async () => {
          try { await apiFetch(`/api/v1/models/${model}/content/relationships/${r.id}`, { method: "DELETE" }); refreshAll(); } catch (err) { setMsg(err.message); }
        }}>✕</button>
      {msg && <span className="status bad">{msg}</span>}
    </>
  );
}

// ---------------------------------------------------------------- roll back (history tab)
export function RollBackButton({ model, m, e, eventId, at }) {
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState("");
  const access = contentAccess(model, m, e.entity_type_status === "retired");
  return (
    <>
      <Gate access={access} className="small" label="↶ Roll back to here" onClick={() => setConfirm(true)}
        title="Set the entity back to how it was just after this moment (saved as a new version; nothing is lost)" />
      {confirm && (
        <Modal title={`Roll ${e.name} back?`} onClose={() => setConfirm(false)}
          actions={<button className="ed-btn" onClick={async () => {
            try {
              await apiFetch(`/api/v1/models/${model}/content/entities/${e.id}/roll-back`, { method: "POST", body: JSON.stringify({ event: eventId }) });
              refreshAll(); setConfirm(false);
            } catch (err) { setMsg(err.message); }
          }}>Roll back</button>}>
          <p>Its name, description, parent, status, tags, values and relationships go back to how they were on {new Date(at).toLocaleString()}.
            This is saved as a new version: the history keeps everything in between, so you can roll forward again.</p>
          {msg && <p className="status bad">{msg}</p>}
        </Modal>
      )}
    </>
  );
}

// ---------------------------------------------------------------- the data entry page (D79)
function cellValue(row, a) {
  return row.values[a.code] ?? "";
}

function EntryRow({ model, m, form, row, cols, access, onRelate }) {
  const [edit, setEdit] = useState(null);   // { name, description, values } while editing
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const isNew = !row.id;
  const start = () => setEdit({ name: row.name || "", description: row.description || "", tags: (row.tags || []).join(", "),
    values: Object.fromEntries(cols.map((a) => [a.code, a.data_type === "entity_ref" ? (row.values[a.code] ? { id: row.values[a.code], name: row.values[a.code] } : null) : cellValue(row, a)])) });
  useEffect(() => { if (isNew) start(); }, []);
  async function save() {
    setBusy(true); setMsg("");
    const values = {};
    for (const a of cols) {
      const now = edit.values[a.code];
      const was = isNew ? "" : cellValue(row, a);
      const n = now && typeof now === "object" ? now.id : now ?? "";
      if (String(n) !== String(was) && !(a.data_type === "entity_ref" && now && now.name === was)) values[a.code] = n;
    }
    const body = isNew ? { entity_type: form.entity_type.id, name: edit.name, description: edit.description, tags: edit.tags, values }
      : { values, row_version: row.row_version,
        ...(edit.name !== row.name ? { name: edit.name } : {}), ...(edit.description !== (row.description || "") ? { description: edit.description } : {}),
        ...(edit.tags !== (row.tags || []).join(", ") ? { tags: edit.tags } : {}) };
    try {
      const out = await apiFetch(isNew ? `/api/v1/models/${model}/content/entities` : `/api/v1/models/${model}/content/entities/${row.id}`,
        { method: isNew ? "POST" : "PATCH", body: JSON.stringify(body) });
      setEdit(null);
      if (out.saved_warnings?.length) setMsg(`Saved with ${out.saved_warnings.length} warning(s): ${out.saved_warnings.map((w) => w.message).join("; ")}`);
      refreshAll();
    } catch (err) { setMsg(err.message); }
    setBusy(false);
  }
  const warn = row.messages?.length ? row.messages.join("\n") : "";
  if (edit) {
    return (
      <tr className="entry-editing">
        <td>{row.display_id || <span className="quiet">new</span>}</td>
        <td><input autoFocus value={edit.name} placeholder="Name *" onChange={(ev) => setEdit({ ...edit, name: ev.target.value })}
          onKeyDown={(ev) => { if (ev.key === "Enter") save(); if (ev.key === "Escape") setEdit(null); }} /></td>
        <td><input value={edit.description} onChange={(ev) => setEdit({ ...edit, description: ev.target.value })} /></td>
        {cols.map((a) => (
          <td key={a.code}><ValueInput model={model} a={a} value={edit.values[a.code]} onChange={(v) => setEdit({ ...edit, values: { ...edit.values, [a.code]: v } })} /></td>
        ))}
        <td><input value={edit.tags} placeholder="tags" onChange={(ev) => setEdit({ ...edit, tags: ev.target.value })} /></td>
        <td className="nowrap">
          <button className="ed-btn small" disabled={busy || !edit.name.trim()} onClick={save}>{busy ? "..." : "Save"}</button>
          {!isNew && <button className="linkish" onClick={() => setEdit(null)}>cancel</button>}
          {msg && <div className="status bad small">{msg}</div>}
        </td>
      </tr>
    );
  }
  return (
    <tr className={warn ? "has-warning" : ""}>
      <td><a href={`#/metamodel/${model}/entity/${row.id}`}>{row.display_id}</a></td>
      <td>{row.name}{row.status === "retired" && <span className="quiet"> (retired)</span>} <PendingMark kind={row.pending} model={model} /></td>
      <td className="quiet clip">{row.description}</td>
      {cols.map((a) => {
        const ov = row.overrides?.[a.code];
        return <td key={a.code} className={ov ? "override" : ""} title={ov ? `Saved although it fails: ${ov.rules.map((r) => r.message).join("; ")} (by ${ov.by})` : undefined}>{cellValue(row, a)}</td>;
      })}
      <td className="quiet">{(row.tags || []).join(", ")}</td>
      <td className="nowrap">
        <button className={access.ok ? "linkish" : "linkish later-text"} disabled={!access.ok} title={access.ok ? "Edit this row" : access.why} onClick={start}>✎</button>
        <button className={access.ok ? "linkish" : "linkish later-text"} disabled={!access.ok}
          title={access.ok ? `Relate ${row.name} to existing entities (${row.relationship_count} now)` : access.why} onClick={() => onRelate(row)}>+ rel ({row.relationship_count})</button>
        {warn && <span className="sev warning" title={warn}>⚠ {row.errors + row.warnings}</span>}
        {msg && <div className="status ok small">{msg}</div>}
      </td>
    </tr>
  );
}

export function DataEntryTab({ model, m, typeFromUrl }) {
  const { data: mm } = useApi(`/api/v1/models/${model}/metamodel`);
  const [type, setType] = useState(typeFromUrl || "");
  const { data, error } = useApi(type ? `/api/v1/models/${model}/entry/${type}` : null);
  const [filter, setFilter] = useState("");
  const [newRows, setNewRows] = useState(0);
  const [relateTo, setRelateTo] = useState(null);
  const [hidden, setHidden] = useState([]);
  useEffect(() => { setNewRows(0); setHidden([]); }, [type]);
  const types = mm ? mm.layers.flatMap((l) => l.entity_types.map((t) => ({ ...t, layer: l.name }))) : [];
  const access = contentAccess(model, m, data?.retired);
  const cols = data ? data.attributes.filter((a) => !hidden.includes(a.code)) : [];
  const f = filter.trim().toLowerCase();
  const rows = data ? data.rows.filter((r) => !f || `${r.display_id} ${r.name} ${r.description} ${Object.values(r.values).join(" ")} ${(r.tags || []).join(" ")}`.toLowerCase().includes(f)) : [];
  return (
    <div className="data-entry">
      <div className="toolbar">
        <label title="Choose an entity type: its fields become the columns">Entity type{" "}
          <select value={type} onChange={(ev) => { setType(ev.target.value); window.location.hash = `/metamodel/${model}/entry${ev.target.value ? `/${ev.target.value}` : ""}`; }}>
            <option value="">Choose...</option>
            {mm?.layers.map((l) => (
              <optgroup key={l.id} label={l.name}>
                {l.entity_types.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.entity_count ?? 0})</option>)}
              </optgroup>
            ))}
          </select></label>
        {data && <input className="search" style={{ maxWidth: 240 }} placeholder={`Filter ${data.rows.length} rows`} value={filter} onChange={(ev) => setFilter(ev.target.value)} />}
        {data && <Gate access={access} label="+ Row" onClick={() => setNewRows((n) => n + 1)} title="Add a row for a new entity (saved when you press Save)" />}
        {data && <NewEntityButton model={model} m={m} typeId={type} typeName={data.entity_type.name} retired={data.retired} label="+ In a form" onSaved={() => refreshAll()} />}
        {data && data.attributes.length > 0 && (
          <details className="col-chooser">
            <summary>Columns ({cols.length}/{data.attributes.length})</summary>
            <div className="col-list">
              {data.attributes.map((a) => (
                <label key={a.code}><input type="checkbox" checked={!hidden.includes(a.code)}
                  onChange={(ev) => setHidden((h) => (ev.target.checked ? h.filter((x) => x !== a.code) : [...h, a.code]))} /> {a.name}</label>
              ))}
            </div>
          </details>
        )}
      </div>
      {!type && <p className="quiet">Choose an entity type: its fields appear as columns. Add rows, type values and save each row; once a row is
        saved, + rel relates it to existing entities (a new entity is saved first, D79). In a project model a save is your uncommitted change until it is committed (Changes tab); elsewhere everyone sees it at once.</p>}
      {type && !data && <p className="quiet">{error || "Loading..."}</p>}
      {!access.ok && data && <p className="quiet">{access.why}</p>}
      {data && <PendingBanner count={data.pending_changes} model={model} />}
      {data && (
        <div className="table-scroll">
          <table className="grid-table entry-table">
            <thead><tr>
              <th>ID</th><th>Name <span className="req">*</span></th><th>Description</th>
              {cols.map((a) => <th key={a.code} title={[a.data_type_name, a.unit, a.pick_list_values.length ? `One of: ${a.pick_list_values.join(", ")}` : ""].filter(Boolean).join(" · ")}>
                {a.name}{a.is_required && <span className="req">*</span>}</th>)}
              <th>Tags</th><th />
            </tr></thead>
            <tbody>
              {Array.from({ length: newRows }, (_, i) => (
                <EntryRow key={`new-${i}-${data.rows.length}`} model={model} m={m} form={data} cols={cols} access={access}
                  row={{ values: {}, tags: [] }} onRelate={() => {}} />
              ))}
              {rows.map((r) => <EntryRow key={`${r.id}-${r.row_version}`} model={model} m={m} form={data} row={r} cols={cols} access={access}
                onRelate={(row) => setRelateTo(row)} />)}
              {!rows.length && !newRows && <tr><td colSpan={cols.length + 5} className="quiet">No {data.entity_type.name} entities yet. Press + Row.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {relateTo && <RelateFromRow model={model} m={m} row={relateTo} onClose={() => setRelateTo(null)} />}
    </div>
  );
}

function RelateFromRow({ model, m, row, onClose }) {
  const { data: e } = useApi(`/api/v1/models/${model}/entities/${row.id}`);
  if (!e) return <Modal title="Loading..." onClose={onClose}><p className="quiet">Loading...</p></Modal>;
  return <AddRelationshipDialog model={model} m={m} e={e} onClose={onClose} />;
}


// ---------------------------------------------------------------- row actions wherever entities are listed
// (type tables, relationship lists, failing checks): ✎ edit and + rel, loading the entity when pressed
function EntityLoader({ model, entityId, children, onClose }) {
  const { data: e, error } = useApi(`/api/v1/models/${model}/entities/${entityId}`);
  if (!e) return <Modal title="Loading..." onClose={onClose}><p className="quiet">{error || "Loading..."}</p></Modal>;
  return children(e);
}

export function RowActions({ model, m, entityId, name, retiredType }) {
  const [open, setOpen] = useState("");
  const access = contentAccess(model, m, retiredType);
  const btn = (key, label, title) => (
    <button className={access.ok ? "linkish row-act" : "linkish later-text row-act"} disabled={!access.ok}
      title={access.ok ? title : access.why} onClick={(ev) => { ev.stopPropagation(); setOpen(key); }}>{label}</button>
  );
  return (
    <span className="row-actions nowrap">
      {btn("edit", "✎", `Edit ${name || "this entity"}`)}
      {btn("rel", "+ rel", `Relate ${name || "this entity"} to existing entities`)}
      {open && (
        <EntityLoader model={model} entityId={entityId} onClose={() => setOpen("")}>
          {(e) => (open === "edit"
            ? <EntityFormDialog model={model} m={m} e={e} onClose={() => setOpen("")} />
            : <AddRelationshipDialog model={model} m={m} e={e} onClose={() => setOpen("")} />)}
        </EntityLoader>
      )}
    </span>
  );
}

// A relationship between any two existing entities, of a chosen type (relationship lists)
export function NewRelationshipButton({ model, m, relType, label = "+ Relationship" }) {
  const [open, setOpen] = useState(false);
  const access = contentAccess(model, m);
  return (
    <>
      <Gate access={access} label={label} onClick={() => setOpen(true)} title="Relate two existing entities" />
      {open && <NewRelationshipDialog model={model} m={m} relType={relType} onClose={() => setOpen(false)} />}
    </>
  );
}

function NewRelationshipDialog({ model, m, relType, onClose }) {
  const { data: types } = useApi(`/api/v1/models/${model}/relationship-types`);
  const [type, setType] = useState(relType?.id || "");
  const [source, setSource] = useState(null);
  const [target, setTarget] = useState(null);
  const [msg, setMsg] = useState("");
  const [outside, setOutside] = useState(false);
  const [added, setAdded] = useState([]);
  const [busy, setBusy] = useState(false);
  const t = types?.find((x) => x.id === type);
  async function add(allowOutside) {
    setBusy(true); setMsg("");
    try {
      const out = await apiFetch(`/api/v1/models/${model}/content/relationships`, { method: "POST",
        body: JSON.stringify({ source: source.id, target: target.id, relationship_type: type, allow_outside: allowOutside }) });
      refreshAll();
      setAdded((x) => [...x, `${source.name} ${t?.verb || ""} ${target.name}${out.outside_metamodel ? " (added to the metamodel, flagged)" : ""}`]);
      setTarget(null); setOutside(false);
    } catch (err) { if (/does not allow/.test(err.message)) setOutside(true); setMsg(err.message); }
    setBusy(false);
  }
  return (
    <Modal wide title="New relationship" onClose={onClose}
      actions={<>
        {outside && <button className="ed-btn secondary" disabled={busy} onClick={() => add(true)}
          title="Adds this relationship type between these entity types to the model's metamodel, flagged (D49)">Add anyway (outside the metamodel)</button>}
        <button className="ed-btn" disabled={busy || !source || !target || !type} onClick={() => add(false)}>Add</button>
        <button className="ed-btn secondary" onClick={onClose}>Done</button>
      </>}>
      <label className="ed-field"><span>Relationship type</span>
        <select value={type} onChange={(ev) => setType(ev.target.value)}>
          <option value="">Choose...</option>
          {(types || []).map((r) => <option key={r.id} value={r.id}>{r.name} ({r.verb})</option>)}
        </select></label>
      <div className="form-grid">
        <div className="ed-field"><span>From (source)</span>
          <EntityPicker model={model} value={source?.id} label={source?.name} onChange={(i, n) => { setSource(i ? { id: i, name: n } : null); setOutside(false); }} /></div>
        <div className="ed-field"><span>To (target){t ? `: ${t.verb}` : ""}</span>
          <EntityPicker model={model} value={target?.id} label={target?.name} onChange={(i, n) => { setTarget(i ? { id: i, name: n } : null); setOutside(false); }} /></div>
      </div>
      <p className="quiet">Existing entities only. The source stays chosen after each Add, so you can relate it to several targets in a row.</p>
      {msg && <p className="status bad">{msg}</p>}
      {added.length > 0 && <div className="status ok">Added: <ul>{added.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
    </Modal>
  );
}
