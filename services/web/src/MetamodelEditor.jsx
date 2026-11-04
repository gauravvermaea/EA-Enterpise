// Changing a model's metamodel (build phase 3), its history and versions, failing checks and locks.
//   ChangeDialog       one change: a form, "Check impact" (a dry run) and "Save" (publishes a new version)
//   *Button            the + and edit buttons that open a ChangeDialog with the right form
//   MetamodelHistory   versions newest first, what each changed; compare any two versions
//   FailingChecks      every entity failing a check, with filters, CSV and links to fix them
//   LockControl        model locks: metamodel, metamodel and content, maintenance (D67)
// The server decides (and the database enforces) what may be changed; the screens only offer it.
import { useEffect, useMemo, useState } from "react";
import { apiFetch, can, currentUser, canOn } from "./auth";
import { downloadCsv } from "./exporting";
import { refreshAll, Swatch, useApi } from "./ModelViews";

const DATA_TYPES = [
  ["text", "Text"], ["long_text", "Long text"], ["integer", "Whole number"], ["decimal", "Decimal number"],
  ["currency", "Currency amount"], ["percent", "Percentage"], ["date", "Date"], ["boolean", "Yes / no"],
  ["list", "Pick list"], ["url", "Web address"], ["email", "Email address"], ["entity_ref", "Link to an entity"],
];
// [code, name, what it checks, parameters: [label, kind]]; kind: number, date, regex, attr, date_attr, text
const RULE_TYPES = [
  ["mandatory", "Mandatory", "A value is required", []],
  ["min_value", "Minimum", "Number at least", [["Minimum", "number"]]],
  ["max_value", "Maximum", "Number at most", [["Maximum", "number"]]],
  ["range", "Range", "Number from ... to ...", [["From", "number"], ["To", "number"]]],
  ["min_length", "Minimum length", "Text at least ... characters", [["Characters", "number"]]],
  ["max_length", "Maximum length", "Text at most ... characters", [["Characters", "number"]]],
  ["regex", "Pattern", "Text matches a regular expression", [["Regular expression", "regex"]]],
  ["date_range", "Date range", "Date from ... to ...", [["From", "date"], ["To", "date"]]],
  ["date_order", "Date order", "Date after another date attribute", [["Must be after", "date_attr"]]],
  ["required_if", "Required if", "Required when another attribute has a value", [["When attribute", "attr"], ["Has the value", "text"]]],
  ["unique", "Unique", "No other entity of the type has the same value", []],
  ["has_relationship", "Has relationship", "At least one relationship of a type, to or from a type (D113)",
    [["Relationship type (empty: any)", "reltype"], ["Entity type at the other end (empty: any)", "othertype"]]],
];
const REGEX_PRESETS = [
  ["^[A-Z]{3}-\\d{4}$", "Code like ABC-1234"], ["^https?://\\S+$", "Web address"], ["^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", "Email address"],
  ["^\\d+(\\.\\d+){1,3}$", "Version like 4.2 or 4.2.1"], ["^[A-Za-z0-9 _-]+$", "Letters, digits, spaces, _ and - only"],
];

const LOCKS = {
  metamodel: ["Metamodel lock", "The metamodel is read-only; content can still be edited"],
  content: ["Metamodel and content lock", "The whole model is read-only"],
  maintenance: ["Maintenance lock", "Only you can change the model (metamodel and content) until you lift the lock"],
};

const me = () => currentUser().preferred_username || "";

// Can the metamodel of this model be changed by the signed-in user? (The server checks again.)
// Working models and an organisation's own root metamodels (not the shipped, locked ones) can change (D81)
export const changeableModel = (m) => !!m && !m.is_locked && (m.kind === "project" || m.kind === "template");

export function metamodelEditable(m) {
  if (!changeableModel(m)) return false;
  if (m.lock_level === "metamodel" || m.lock_level === "content") return false;
  if (m.lock_level === "maintenance" && m.locked_by !== me()) return false;
  return true;
}

function whyNot(m) {
  if (m.is_locked) return `${m.name} is locked (read-only). Copy it into a project model to change its metamodel (build phase 4).`;
  if (!changeableModel(m)) return "This model is read-only: copy it to change its metamodel.";
  if (m.lock_level !== "none") return `${m.name} is locked (${LOCKS[m.lock_level]?.[0].toLowerCase()}) by ${m.locked_by}.`;
  return "";
}

// ---------------------------------------------------------------- one change
// A regular expression with a live check, ready-made patterns and a box to try a value against it.
// The server checks the pattern again (Python's rules, which match JavaScript's for ordinary patterns).
function RegexInput({ id, value, set }) {
  const [sample, setSample] = useState("");
  let error = "";
  let re = null;
  try { if (value) re = new RegExp(value); } catch (e) { error = e.message; }
  return (
    <div className="regex">
      <input type="text" id={id} className={`mono${error ? " bad-input" : ""}`} value={value ?? ""} onChange={(e) => set(e.target.value)}
        placeholder="for example ^[A-Z]{3}-\d{4}$" spellCheck={false} />
      <select value="" onChange={(e) => e.target.value && set(e.target.value)} aria-label="Ready-made patterns">
        <option value="">Ready-made patterns...</option>
        {REGEX_PRESETS.map(([p, l]) => <option key={p} value={p}>{l}: {p}</option>)}
      </select>
      {error ? <small className="status bad">Not a valid pattern: {error}</small>
        : value ? <small className="quiet">Valid pattern. ^ and $ anchor the start and end; without them it matches anywhere in the value.</small> : null}
      <div className="regex-try">
        <input type="text" placeholder="Try a value" value={sample} onChange={(e) => setSample(e.target.value)} aria-label="Try a value" />
        {re && sample !== "" && (re.test(sample)
          ? <span className="all-pass">✓ matches</span> : <span className="status bad">✗ does not match</span>)}
      </div>
    </div>
  );
}

function Field({ f: field, value, set, values }) {
  const f = typeof field.type === "function" ? { ...field, ...field.type(values || {}) } : field;
  const common = { id: `f-${f.name}`, value: value ?? "", onChange: (e) => set(f.name, e.target.value) };
  let input;
  if (f.type === "regex") {
    input = <RegexInput id={`f-${f.name}`} value={value} set={(v) => set(f.name, v)} />;
  } else if (f.type === "date") {
    input = <input type="date" {...common} />;
  } else if (f.type === "number") {
    input = <input type="number" step="any" {...common} />;
  } else if (f.type === "select") {
    input = (
      <select {...common}>
        {f.blank !== false && <option value="">{f.blank || "Choose..."}</option>}
        {f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    );
  } else if (f.type === "check") {
    input = <input type="checkbox" checked={!!value} onChange={(e) => set(f.name, e.target.checked)} />;
  } else if (f.type === "lines") {
    input = <textarea {...common} rows={f.rows || 5} placeholder={f.placeholder} />;
  } else if (f.type === "textarea") {
    input = <textarea {...common} rows={3} />;
  } else {
    input = <input type="text" {...common} placeholder={f.placeholder} />;
  }
  return (
    <label className={`ed-field${f.type === "check" ? " check" : ""}`} htmlFor={`f-${f.name}`}>
      <span>{f.label}{f.required && <span className="req">*</span>}</span>
      {input}
      {f.help && <small className="quiet">{f.help}</small>}
    </label>
  );
}

function Impact({ impact }) {
  if (!impact) return null;
  return (
    <div className="impact">
      <strong>Impact</strong>
      <ul>{impact.summary.map((l, i) => <li key={i}>{l}</li>)}</ul>
      {impact.newly_failing.length > 0 && (
        <details>
          <summary>{impact.newly_failing_count} new failure{impact.newly_failing_count > 1 ? "s" : ""}</summary>
          <ul className="impact-list">{impact.newly_failing.map((r, i) => (
            <li key={i}><span className={`sev ${r.severity}`}>{r.severity}</span> {r.display_id} {r.name}: {r.field} ({r.rule})</li>))}</ul>
        </details>
      )}
      {impact.now_passing.length > 0 && (
        <details>
          <summary>{impact.now_passing_count} fixed</summary>
          <ul className="impact-list">{impact.now_passing.map((r, i) => <li key={i}>{r.display_id} {r.name}: {r.field} ({r.rule})</li>)}</ul>
        </details>
      )}
    </div>
  );
}

const n = (k, one, many) => `${k} ${k === 1 ? one : many}`;
// What a change removes or leaves outside the rules (from its result), said before and after saving
function Removals({ result, saved }) {
  if (!result) return null;
  const lines = [];
  if (result.values_removed) lines.push(`${n(result.values_removed, "value", "values")} ${saved ? "removed" : "will be removed"} (kept in history)`);
  if (result.relationships_removed) lines.push(`${n(result.relationships_removed, "relationship", "relationships")} ${saved ? "removed" : "will be removed"} (kept in history)`);
  if (result.relationships_now_outside_the_rules) lines.push(`${n(result.relationships_now_outside_the_rules, "relationship", "relationships")} ${saved ? "are" : "will be"} outside the metamodel (kept, shown on Failing checks)`);
  return lines.length ? <div className="removals">{lines.map((l) => <div key={l}>{l}</div>)}</div> : null;
}

// spec: { title, op, fields: [...], fixed: {...}, intro, toPayload(values) }
export function ChangeDialog({ model, m, spec, onClose }) {
  const [values, setValues] = useState(() => Object.fromEntries((spec.fields || []).map((f) => [f.name, f.initial ?? (f.type === "check" ? false : "")])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);
  const [saved, setSaved] = useState(null);
  const set = (k, v) => { setValues((x) => ({ ...x, [k]: v })); setPreview(null); };
  const shown = (spec.fields || []).filter((f) => !f.when || f.when(values));

  function payload() {
    const p = { ...(spec.fixed || {}) };
    for (const f of shown) {
      const v = values[f.name];
      if (f.type === "lines") p[f.name] = String(v || "").split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
      else if (v !== "" && v !== undefined) p[f.name] = v;
      else if (f.sendEmpty) p[f.name] = "";
    }
    return spec.toPayload ? spec.toPayload(p, values) : p;
  }
  async function send(dry) {
    setBusy(true); setError("");
    try {
      const out = await apiFetch(`/api/v1/models/${model}/metamodel/changes`, {
        method: "POST", body: JSON.stringify({ op: spec.op, dry_run: dry, ...payload() }),
      });
      if (dry) setPreview(out);
      else { setSaved(out); refreshAll(); }
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  const missing = shown.filter((f) => f.required && (values[f.name] === "" || values[f.name] === undefined));

  return (
    <div className="ed-backdrop" role="dialog" aria-modal="true" aria-label={spec.title} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ed-dialog">
        <div className="ed-head">
          <h2>{spec.title}</h2>
          <button className="linkish" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {saved ? (
          <div>
            <p className="all-pass">✓ Saved as metamodel version {saved.version}: {saved.note}.</p>
            {saved.result?.filled_with_default > 0 && <p>{saved.result.filled_with_default === 1 ? "1 existing entity was" : `${saved.result.filled_with_default} existing entities were`} given the default value.</p>}
            <Removals result={saved.result} saved />
            <Impact impact={saved.impact} />
            <div className="ed-actions"><span className="er-spacer" /><button className="primary" onClick={onClose}>Close</button></div>
          </div>
        ) : (
          <>
            {spec.intro && <p className="quiet">{spec.intro}</p>}
            {shown.length > 0 && <div className="ed-form">{shown.map((f) => <Field key={f.name} f={f} value={values[f.name]} set={set} values={values} />)}</div>}
            {error && <p className="status bad">{error}</p>}
            {preview && (
              <>
                <p className="quiet">Saving publishes metamodel version {preview.version}: <em>{preview.note}</em>.</p>
                <Removals result={preview.result} />
                <Impact impact={preview.impact} />
              </>
            )}
            <div className="ed-actions">
              <span className="quiet">{m && `Now at metamodel version ${m.metamodel_version}.`}</span>
              <span className="er-spacer" />
              <button onClick={onClose}>Cancel</button>
              <button disabled={busy || missing.length > 0} onClick={() => send(true)} title="What would this change do? Nothing is saved">Check impact</button>
              <button className={spec.danger ? "danger" : "primary"} disabled={busy || missing.length > 0} onClick={() => send(false)}>
                {spec.saveLabel || "Save"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// A button that opens a ChangeDialog, or shows why it cannot (a locked or read-only model)
export function EditButton({ model, m, label, spec, className = "", title }) {
  const [open, setOpen] = useState(false);
  if (!canOn(model, "model.metamodel")) return null;   // only the model's Model Admins (and Super Admins) change its metamodel (D89)
  const ok = metamodelEditable(m);
  return (
    <>
      <button className={`${ok ? "ed-btn" : "later"} ${className}`} disabled={!ok} title={ok ? title || spec?.title : whyNot(m)}
        onClick={() => setOpen(true)}>{label}</button>
      {open && <ChangeDialog model={model} m={m} spec={typeof spec === "function" ? spec() : spec} onClose={() => setOpen(false)} />}
    </>
  );
}

// ---------------------------------------------------------------- the forms
export function entityTypeSpec(layers, t = null) {
  const layerOptions = layers.map((l) => [l.id, l.name]);
  if (t) {
    return {
      title: `Change entity type ${t.name}`, op: "entity_type.update", fixed: { id: t.id },
      fields: [
        { name: "name", label: "Name", required: true, initial: t.name },
        { name: "layer", label: "Layer", type: "select", options: layerOptions, initial: t.layer_id, blank: false },
        { name: "id_prefix", label: "Display ID prefix", initial: t.id_prefix, help: "New entities get IDs like PREFIX-0001" },
        { name: "aspect", label: "Aspect", initial: t.aspect },
        { name: "description", label: "Description", type: "textarea", initial: t.description, sendEmpty: true },
      ],
    };
  }
  return {
    title: "New entity type", op: "entity_type.create",
    intro: "A new kind of thing the model can hold. Its attributes, rules and allowed relationships are added on its page.",
    fields: [
      { name: "name", label: "Name", required: true, placeholder: "for example Integration Platform" },
      { name: "layer", label: "Layer", type: "select", options: layerOptions, required: true },
      { name: "id_prefix", label: "Display ID prefix", placeholder: "3 letters, for example INT", help: "Made from the name when left empty" },
      { name: "aspect", label: "Aspect", placeholder: "for example Active Structure" },
      { name: "description", label: "Description", type: "textarea" },
    ],
  };
}

// The input for a default value, by the attribute's data type: a date picker for dates, numbers for
// numbers, yes or no, or the pick list's values.
function defaultInput(dataType, listValues) {
  if (dataType === "date") return { type: "date" };
  if (["integer", "decimal", "currency", "percent"].includes(dataType)) return { type: "number" };
  if (dataType === "boolean") return { type: "select", options: [["yes", "Yes"], ["no", "No"]], blank: "(no default)" };
  if (dataType === "list" && listValues?.length) return { type: "select", options: listValues.map((x) => [x, x]), blank: "(no default)" };
  return { type: "text" };
}

export function attributeSpec(t, pickLists, hasEntities, a = null) {
  const defaultHelp = "Given to new entities. Empty means no default.";
  const applyField = { name: "apply_default_to_existing", label: `Put the default on the existing ${t.name} entities that have no value`, type: "check",
    when: (v) => hasEntities && String(v.default_value || "").trim() !== "" };
  if (a) {
    return {
      title: `Change attribute ${a.name} on ${t.name}`, op: "attribute.update", fixed: { item: a.item_id },
      intro: hasEntities ? "Making an attribute mandatory is never blocked: entities without a value show on the failing-checks screen, unless you give them the default." : "",
      fields: [
        { name: "name", label: "Name", required: true, initial: a.name },
        { name: "is_required", label: "Mandatory", type: "check", initial: a.is_required },
        { name: "default_value", label: "Default value", initial: a.default_value ?? "", help: defaultHelp, sendEmpty: true,
          ...defaultInput(a.data_type, a.pick_list_values) },
        applyField,
        { name: "section", label: "Section on the form", initial: a.section },
        { name: "unit", label: "Unit", initial: a.unit, sendEmpty: true },
        { name: "help_text", label: "Help text", initial: a.help_text, sendEmpty: true },
        { name: "description", label: "Description", type: "textarea", initial: a.description, sendEmpty: true },
      ],
    };
  }
  return {
    title: `New attribute on ${t.name}`, op: "attribute.create", fixed: { entity_type: t.id },
    intro: hasEntities ? `${t.name} already has entities. A mandatory attribute is never blocked: give a default (or leave it empty) and choose whether the existing entities get it.` : "",
    fields: [
      { name: "name", label: "Name", required: true, placeholder: "for example Data Classification" },
      { name: "data_type", label: "Data type", type: "select", options: DATA_TYPES, required: true },
      { name: "pick_list", label: "Pick list", type: "select", blank: "(new pick list from the values below)",
        options: pickLists.map((p) => [p.id, `${p.name} (${p.values.filter((v) => v.status !== "retired").map((v) => v.value).join(", ")})`]),
        when: (v) => v.data_type === "list" },
      { name: "values", label: "Values, one per line", type: "lines", when: (v) => v.data_type === "list" && !v.pick_list },
      { name: "is_required", label: "Mandatory", type: "check" },
      { name: "default_value", label: "Default value", help: defaultHelp, when: (v) => v.data_type && v.data_type !== "entity_ref",
        type: (v) => defaultInput(v.data_type, v.data_type !== "list" ? null : v.pick_list
          ? (pickLists.find((p) => p.id === v.pick_list)?.values || []).filter((x) => x.status !== "retired").map((x) => x.value)
          : String(v.values || "").split(/\r?\n/).map((x) => x.trim()).filter(Boolean)) },
      applyField,
      { name: "section", label: "Section on the form", initial: "General" },
      { name: "unit", label: "Unit", placeholder: "for example ZAR or days", when: (v) => ["integer", "decimal", "currency", "percent"].includes(v.data_type) },
      { name: "help_text", label: "Help text" },
      { name: "description", label: "Description", type: "textarea" },
    ],
  };
}

export function removeAttributeSpec(t, a) {
  return { title: `Remove ${a.name} from ${t.name}`, op: "attribute.remove", fixed: { item: a.item_id }, danger: true, saveLabel: "Remove",
    intro: `The attribute leaves ${t.name} and its value is removed from every ${t.name}. Each removed value stays in the entity's history. Check impact shows how many.`, fields: [] };
}

export function lifecycleSpec(t) {
  return {
    title: `New lifecycle on ${t.name}`, op: "lifecycle.create", fixed: { entity_type: t.id },
    intro: "A lifecycle is a set of ordered phases, each with a date: it adds a phase pick list and a date per phase in its own section.",
    fields: [
      { name: "name", label: "Name", required: true, initial: "Lifecycle" },
      { name: "phases", label: "Phases in order, one per line", type: "lines", required: true, initial: "Plan\nPhase in\nActive\nPhase out\nEnd of life" },
    ],
  };
}

export function relationshipTypeSpec(r = null) {
  const fields = [
    { name: "name", label: "Name", required: true, initial: r?.name, placeholder: "for example Feeds" },
    { name: "verb", label: "Reads as (source ... target)", required: true, initial: r?.verb, placeholder: "for example feeds" },
    { name: "category", label: "Category", type: "select", options: [["Structural", "Structural"], ["Dependency", "Dependency"], ["Dynamic", "Dynamic"], ["Other", "Other"]], initial: r?.category || "" },
    { name: "is_directed", label: "Directed (has a source and a target)", type: "check", initial: r ? r.is_directed : true },
    { name: "description", label: "Description", type: "textarea", initial: r?.description, sendEmpty: !!r },
  ];
  return r ? { title: `Change relationship type ${r.name}`, op: "relationship_type.update", fixed: { id: r.id }, fields }
    : { title: "New relationship type", op: "relationship_type.create", fields,
      intro: "Add mappings afterwards to say which entity types it may connect (without one, relationships of the type show as outside the metamodel)." };
}

export function mappingSpec(types, relTypes, source = null) {
  const typeOptions = types.map((t) => [t.id, t.name]);
  return {
    title: "New mapping (allowed relationship)", op: "mapping.add",
    intro: "Which relationship type may connect which source type to which target type.",
    fields: [
      { name: "source_type", label: "Source entity type", type: "select", options: typeOptions, required: true, initial: source || "" },
      { name: "relationship_type", label: "Relationship type", type: "select", options: relTypes.filter((r) => r.status !== "retired").map((r) => [r.id, `${r.name} (${r.verb})`]), required: true },
      { name: "target_type", label: "Target entity type", type: "select", options: typeOptions, required: true },
      { name: "note", label: "Note" },
    ],
  };
}

function paramField(t, [label, kind], i, initial) {
  const attrs = (t.attributes || []);
  const f = { name: `param${i + 1}`, label, initial, required: kind === "regex" || kind === "attr" || kind === "date_attr" };
  if (kind === "regex") return { ...f, type: "regex" };
  if (kind === "date") return { ...f, type: "date", help: "Leave one empty for no limit on that side" };
  if (kind === "number") return { ...f, type: "number", required: true };
  if (kind === "attr") return { ...f, type: "select", options: attrs.map((a) => [a.code, a.name]) };
  if (kind === "date_attr") return { ...f, type: "select", options: attrs.filter((a) => a.data_type === "date").map((a) => [a.code, a.name]) };
  // relationship rules (D113): what the metamodel allows this type to be linked by, and to
  const allowed = [...(t.outgoing || []), ...(t.incoming || [])];
  const uniq = (xs) => [...new Set(xs)].sort().map((x) => [x, x]);
  if (kind === "reltype") return { ...f, type: "select", options: uniq(allowed.map((a) => a.relationship_type)) };
  if (kind === "othertype") return { ...f, type: "select", options: uniq(allowed.map((a) => a.other_type)) };
  return f;
}

export function ruleSpec(t, r = null) {
  if (r) {
    const rt = RULE_TYPES.find((x) => x[0] === r.rule_type_code) || [r.rule_type_code, r.rule, "", [["Parameter 1", "text"], ["Parameter 2", "text"]]];
    return {
      title: `Change rule on ${r.field}`, op: "rule.update", fixed: { id: r.id },
      fields: [
        ...rt[3].map((p, i) => paramField(t, p, i, r[`param${i + 1}`])),
        { name: "severity", label: "Severity", type: "select", options: [["error", "Error"], ["warning", "Warning"]], initial: r.severity, blank: false },
        { name: "message", label: "Message shown when it fails", initial: r.message, required: true },
      ],
    };
  }
  const targets = [["field:name", "Name (built-in)"], ["field:description", "Description (built-in)"], ["field:relationships", "Relationships (use the rule Has relationship)"],
    ...t.attributes.map((a) => [`attr:${a.attribute_id}`, a.name])];
  return {
    title: `New rule on ${t.name}`, op: "rule.create",
    intro: "Rules warn, they never block a save: a value that fails is kept and shows as an error or warning until fixed.",
    fields: [
      { name: "target", label: "Checks", type: "select", options: targets, required: true },
      { name: "rule_type", label: "Rule", type: "select", options: RULE_TYPES.map(([c, n, d]) => [c, `${n}: ${d}`]), required: true },
      ...RULE_TYPES.flatMap(([code, , , params]) => params.map((p, i) => ({
        ...paramField(t, p, i), name: `${code}__param${i + 1}`, when: (v) => v.rule_type === code }))),
      { name: "scope", label: "Applies to", type: "select", options: [["type", `${t.name} only`], ["all", "Every entity type with this attribute or field"]], initial: "type", blank: false },
      { name: "severity", label: "Severity", type: "select", options: [["error", "Error"], ["warning", "Warning"]], initial: "error", blank: false },
      { name: "message", label: "Message shown when it fails", placeholder: "for example Owner is required" },
    ],
    toPayload: (p) => {
      const out = {};
      for (const [k, v] of Object.entries(p)) {
        const m = k.match(/^(\w+)__(param\d)$/);
        if (!m) out[k] = v; else if (m[1] === p.rule_type) out[m[2]] = v;
      }
      const [kind, ref] = String(p.target || "").split(":");
      delete out.target; delete out.scope;
      if (p.rule_type === "has_relationship") { /* about relationships: no field or attribute */ }
      else if (kind === "field") out.field_name = ref; else out.attribute = ref;
      if (p.scope !== "all") out.entity_type = t.id;
      return out;
    },
  };
}

export function simpleSpec(title, op, fixed, intro, danger = false, saveLabel = "Save") {
  return { title, op, fixed, intro, fields: [], danger, saveLabel };
}

export function pickListSpec() {
  return { title: "New pick list", op: "pick_list.create",
    fields: [{ name: "name", label: "Name", required: true }, { name: "values", label: "Values, one per line", type: "lines", required: true }] };
}

// ---------------------------------------------------------------- pick lists
export function PickLists({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/metamodel/pick-lists`);
  if (!data) return error ? <p className="status bad">{error}</p> : <p className="quiet">Loading...</p>;
  return (
    <div>
      <div className="toolbar">
        <span className="quiet">{data.length} pick lists, shared by the attributes that use them.</span>
        <span className="er-spacer" />
        <EditButton model={model} m={m} label="+ Pick list" spec={pickListSpec()} />
      </div>
      <table className="grid-table">
        <thead><tr><th>Pick list</th><th>Values</th><th /></tr></thead>
        <tbody>
          {data.map((p) => (
            <tr key={p.id}>
              <td><strong>{p.name}</strong><br /><code className="quiet">{p.code}</code></td>
              <td className="pick-values">
                {p.values.map((v) => (
                  <span key={v.id} className={`pick-value${v.status === "retired" ? " retired" : ""}`}>
                    {v.value}
                    {v.status !== "retired" && (
                      <EditButton model={model} m={m} label="×" className="tiny" title={`Retire ${v.value}`}
                        spec={simpleSpec(`Retire ${v.value} in ${p.name}`, "pick_list.retire_value", { value_id: v.id },
                          "Retired values are no longer offered; entities that use them keep the value and show a warning.", true, "Retire")} />
                    )}
                  </span>
                ))}
              </td>
              <td>
                <EditButton model={model} m={m} label="+ Value" className="small"
                  spec={{ title: `New value in ${p.name}`, op: "pick_list.add_value", fixed: { pick_list: p.id },
                    fields: [{ name: "value", label: "Value", required: true }] }} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- history and versions
function ChangeRow({ c }) {
  return (
    <tr>
      <td><span className={`chg ${c.change}`}>{c.change}</span></td>
      <td className="quiet nowrap">{c.kind}</td>
      <td>{c.item}</td>
      <td>
        {c.fields.slice(0, 6).map((f, i) => (
          <div key={i} className="chg-field"><strong>{f.field}</strong>: {f.old !== null && f.old !== undefined && <><del>{f.old}</del> → </>}{f.new ?? <em className="quiet">(none)</em>}</div>
        ))}
        {c.fields.length > 6 && <span className="quiet">and {c.fields.length - 6} more</span>}
      </td>
    </tr>
  );
}

function Compare({ model, m, from, to, setFrom, setTo }) {
  const path = from ? `/api/v1/models/${model}/metamodel/compare?from=${from}${to ? `&to=${to}` : ""}` : null;
  const { data, error } = useApi(path);
  const versions = Array.from({ length: m.metamodel_version }, (_, i) => m.metamodel_version - i);
  return (
    <div className="compare">
      <div className="toolbar">
        <strong>Compare</strong>
        <label>from version <select value={from || ""} onChange={(e) => setFrom(Number(e.target.value) || null)}>
          <option value="">choose...</option>{versions.map((v) => <option key={v} value={v}>v{v}</option>)}</select></label>
        <label>to <select value={to || ""} onChange={(e) => setTo(Number(e.target.value) || null)}>
          <option value="">the current version (v{m.metamodel_version})</option>{versions.map((v) => <option key={v} value={v}>v{v}</option>)}</select></label>
        {data && <button onClick={() => downloadCsv([["Change", "Kind", "Item", "Field", "Old", "New"],
          ...data.items.flatMap((c) => (c.fields.length ? c.fields : [{}]).map((f) => [c.change, c.kind, c.item, f.field, f.old, f.new]))],
          `${m.name} - metamodel v${data.from_version} to v${data.to_version}`)}>CSV</button>}
      </div>
      {error && <p className="status bad">{error}</p>}
      {from && !data && !error && <p className="quiet">Comparing...</p>}
      {data && (
        <>
          <p>{data.items.length ? `${data.items.length} differences from v${data.from_version} to v${data.to_version}: ` : `No differences between v${data.from_version} and v${data.to_version}.`}
            {data.summary.map((s, i) => <span key={i} className="quiet">{i > 0 && " · "}{s.kind}: {Object.entries(s).filter(([k]) => k !== "kind").map(([k, n]) => `${n} ${k}`).join(", ")}</span>)}</p>
          {data.items.length > 0 && (
            <table className="grid-table history"><thead><tr><th>Change</th><th>Kind</th><th>Item</th><th>What</th></tr></thead>
              <tbody>{data.items.map((c, i) => <ChangeRow key={i} c={c} />)}</tbody></table>
          )}
        </>
      )}
    </div>
  );
}

export function MetamodelHistory({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/metamodel/history`);
  const [open, setOpen] = useState({});
  const [from, setFrom] = useState(null);
  const [to, setTo] = useState(null);
  if (!data) return error ? <p className="status bad">{error}</p> : <p className="quiet">Loading...</p>;
  return (
    <div>
      <p className="quiet">The metamodel is at <strong>version {data.current_version}</strong>. Every change publishes a new version
        (newest first); click one to see what it changed, or compare any two versions.</p>
      <Compare model={model} m={m} from={from} to={to} setFrom={setFrom} setTo={setTo} />
      <ol className="mm-versions">
        {data.versions.map((v) => {
          const isOpen = open[v.version] ?? v.version === data.current_version;
          return (
            <li key={v.version} className={isOpen ? "open" : ""}>
              <button className="linkish mm-version-head" onClick={() => setOpen((o) => ({ ...o, [v.version]: !isOpen }))}>
                <span className="vtag">v{v.version}</span> <strong>{v.note || (v.version === 1 ? "Initial metamodel" : "")}</strong>{" "}
                <span className="quiet">{new Date(v.changed_at).toLocaleString()} · {v.changed_by}</span>
              </button>
              {v.version > 1 && <button className="linkish small-link" onClick={() => { setFrom(v.version - 1); setTo(v.version); }}>compare with v{v.version - 1}</button>}
              {v.version < data.current_version && <button className="linkish small-link" onClick={() => { setFrom(v.version); setTo(null); }}>what changed since</button>}
              {isOpen && (v.items.length ? (
                <table className="grid-table history"><tbody>{v.items.map((c, i) => <ChangeRow key={i} c={c} />)}</tbody></table>
              ) : (
                <p className="quiet">{v.counts.map((c) => `${c.count} ${c.kind}${c.count > 1 ? "s" : ""}`).join(", ") || "No recorded changes."}</p>
              ))}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------- failing checks
export function FailingChecks({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/checks`);
  const [type, setType] = useState("");
  const [rule, setRule] = useState("");
  const [severity, setSeverity] = useState("");
  const [older, setOlder] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [type, rule, severity, older, q]);
  const rows = useMemo(() => {
    if (!data) return [];
    const f = q.trim().toLowerCase();
    return data.rows.filter((r) => (!type || r.entity_type === type) && (!rule || r.rule === rule) && (!severity || r.severity === severity)
      && (!older || (r.modified_mm_version ?? 0) < Number(older))
      && (!f || `${r.display_id} ${r.name} ${r.message}`.toLowerCase().includes(f)));
  }, [data, type, rule, severity, older, q]);
  if (!data) return error ? <p className="status bad">{error}</p> : <p className="quiet">Checking every entity...</p>;
  const versions = Array.from({ length: data.metamodel_version }, (_, i) => i + 2).filter((v) => v <= data.metamodel_version);
  const PAGE = 100;
  return (
    <div>
      <p>{data.failures ? <><strong>{data.entities}</strong> entities fail <strong>{data.failures}</strong> checks.</> : <span className="all-pass">✓ Every entity passes every check.</span>}
        <span className="quiet"> Checks never block a save: fix these on each entity's page (editing values arrives in build phase 6).</span></p>
      {data.failures > 0 && (
        <>
          <div className="er-chips">
            <span className="quiet">Failures by entity type:</span>
            {data.by_type.map((c) => <button key={c.name} className={`chip${type === c.name ? " on" : ""}`} onClick={() => setType(type === c.name ? "" : c.name)}>{c.name} <span className="count">{c.count}</span></button>)}
          </div>
          <div className="toolbar">
            <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Entity type">
              <option value="">Every entity type</option>
              {data.by_type.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.count})</option>)}
            </select>
            <input className="search" style={{ maxWidth: 240 }} placeholder="Search entity or message" value={q} onChange={(e) => setQ(e.target.value)} />
            <select value={rule} onChange={(e) => setRule(e.target.value)}><option value="">Every rule</option>{data.by_rule.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.count})</option>)}</select>
            <select value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="">Errors and warnings</option>{data.by_severity.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.count})</option>)}</select>
            {versions.length > 0 && (
              <select value={older} onChange={(e) => setOlder(e.target.value)} title="Entities not changed since a metamodel version">
                <option value="">Any metamodel version</option>
                {versions.map((v) => <option key={v} value={v}>last changed before v{v}</option>)}
              </select>
            )}
            <button onClick={() => downloadCsv([["Display ID", "Name", "Entity type", "Field", "Rule", "Severity", "Message", "Created in", "Last changed in"],
              ...rows.map((r) => [r.display_id, r.name, r.entity_type, r.field, r.rule, r.severity, r.message, r.created_mm_version, r.modified_mm_version])],
            `${m.name} - failing checks`)}>CSV</button>
            <span className="er-spacer" />
            <span className="quiet">{rows.length} shown</span>
            {rows.length > PAGE && <span className="pager"><button disabled={!page} onClick={() => setPage(page - 1)}>‹</button><button disabled={(page + 1) * PAGE >= rows.length} onClick={() => setPage(page + 1)}>›</button></span>}
          </div>
          <table className="grid-table">
            <thead><tr><th>Entity</th><th>Type</th><th>Field</th><th>Check</th><th>Metamodel v</th></tr></thead>
            <tbody>
              {rows.slice(page * PAGE, (page + 1) * PAGE).map((r, i) => (
                <tr key={i}>
                  <td><Swatch colour={r.colour} /> <a href={`#/metamodel/${model}/entity/${r.entity_id}`}>{r.name}</a> <span className="quiet">{r.display_id}</span></td>
                  <td className="quiet">{r.entity_type}</td>
                  <td>{r.field}</td>
                  <td><span className={`sev ${r.severity}`}>{r.severity}</span> {r.message}</td>
                  <td className="quiet nowrap">{r.created_mm_version != null ? `created v${r.created_mm_version} · changed v${r.modified_mm_version}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- locks
export function LockControl({ model, m }) {
  const [open, setOpen] = useState(false);
  const [level, setLevel] = useState("metamodel");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  if (!changeableModel(m)) return null;
  if (!canOn(model, "model.lock")) {
    return m.lock_level && m.lock_level !== "none"
      ? <span className={`model-lock ${m.lock_level}`}>🔒 {LOCKS[m.lock_level][0]} · {m.locked_by}</span> : null;
  }
  async function call(method, body) {
    setError("");
    try {
      await apiFetch(`/api/v1/models/${model}/lock`, { method, body: body ? JSON.stringify(body) : undefined });
      setOpen(false); setReason(""); refreshAll();
    } catch (e) { setError(e.message); }
  }
  if (m.lock_level && m.lock_level !== "none") {
    return (
      <span className={`model-lock ${m.lock_level}`} title={`${LOCKS[m.lock_level][1]}. Locked by ${m.locked_by} on ${new Date(m.locked_at).toLocaleString()}${m.lock_reason ? `: ${m.lock_reason}` : ""}`}>
        🔒 {LOCKS[m.lock_level][0]} · {m.locked_by}
        <button className="linkish" onClick={() => call("DELETE")}>Unlock</button>
        {error && <span className="status bad"> {error}</span>}
      </span>
    );
  }
  return (
    <span className="lock-ctl">
      <button onClick={() => setOpen(!open)} title="Lock this model (Model Admins from build phase 3.1)">Lock...</button>
      {open && (
        <div className="lock-pop">
          {Object.entries(LOCKS).map(([k, [name, help]]) => (
            <label key={k} className="lock-opt"><input type="radio" name="lock" checked={level === k} onChange={() => setLevel(k)} />
              <span><strong>{name}</strong><br /><small className="quiet">{help}</small></span></label>
          ))}
          <input className="search" placeholder="Why (shown to everyone)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="ed-actions"><span className="er-spacer" /><button onClick={() => setOpen(false)}>Cancel</button>
            <button className="primary" onClick={() => call("PUT", { level, reason })}>Lock</button></div>
          {error && <p className="status bad">{error}</p>}
        </div>
      )}
    </span>
  );
}

export function LockBanner({ m }) {
  if (!m.lock_level || m.lock_level === "none") return null;
  const [name, help] = LOCKS[m.lock_level];
  return (
    <div className={`lock-banner ${m.lock_level}`}>
      <strong>🔒 {name}</strong> by {m.locked_by} since {new Date(m.locked_at).toLocaleString()}: {help.toLowerCase()}.
      {m.lock_reason && <> Reason: <em>{m.lock_reason}</em>.</>}
    </div>
  );
}
