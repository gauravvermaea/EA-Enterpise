// Choosing where something sits in the content framework (D299). One entity type, document type or document may sit
// in several areas (owner, 8 Nov 2026, D309): the areas are ticked by group, and shown as chips.
import { useState } from "react";
import { CF_AREAS, CF_LABEL } from "./cfAreas";

const GROUPS = [...new Set(CF_AREAS.map(([, , , g]) => g))];

// "a,b" or ["a","b"] -> ["a","b"]
export const areaList = (v) => (Array.isArray(v) ? v : String(v || "").split(",")).map((x) => String(x).trim()).filter(Boolean);
export const areaText = (codes) => CF_AREAS.map(([c]) => c).filter((c) => codes.includes(c)).join(",");

// The ticks, grouped. value: a list of codes; onChange(list).
export function AreaChecks({ value, onChange, filter = "" }) {
  const on = new Set(value);
  const q = filter.trim().toLowerCase();
  const toggle = (c) => onChange(CF_AREAS.map(([x]) => x).filter((x) => (x === c ? !on.has(x) : on.has(x))));
  return (
    <div className="cf-checks">
      {GROUPS.map((g) => {
        const rows = CF_AREAS.filter(([, l, , gg]) => gg === g && (!q || l.toLowerCase().includes(q) || g.toLowerCase().includes(q)));
        if (!rows.length) return null;
        return (
          <fieldset key={g} className="cf-check-group">
            <legend>{g}</legend>
            {rows.map(([c, l]) => (
              <label key={c} className={on.has(c) ? "on" : ""}><input type="checkbox" checked={on.has(c)} onChange={() => toggle(c)} /> {l}</label>
            ))}
          </fieldset>
        );
      })}
    </div>
  );
}

// The chips of the areas chosen (or the default ones, shown quieter).
export function AreaChips({ codes, dflt, small }) {
  if (!codes.length) return <span className="quiet small">{dflt ? "not placed" : "none"}</span>;
  return <span className={`cf-chips${small ? " small" : ""}`}>{codes.map((c) => <span key={c} className={`cf-chip${dflt ? " dflt" : ""}`} title={dflt ? "Where it sits by default" : "Chosen"}>{CF_LABEL[c] || c}</span>)}</span>;
}

// A button that opens the ticks in a small panel. value: list; onSave(list) returns a promise (or nothing).
// resetLabel: when given, a button to go back to the default ([] saved).
// dflt: the areas it sits in by default, ticked to start from when none is chosen yet.
export function AreaPicker({ value, dflt = [], onSave, label = "Content framework…", resetLabel = "", disabled }) {
  const [open, setOpen] = useState(false);
  const [cur, setCur] = useState(value);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(list) {
    setBusy(true);
    try { await onSave(list); setOpen(false); } finally { setBusy(false); }
  }
  return (
    <span className="cf-picker">
      <button className="linkish small" disabled={disabled} title="Choose the areas of the content framework where this sits (one or several)"
        onClick={() => { setCur(value.length ? value : dflt); setQ(""); setOpen(!open); }}>▦ {label}</button>
      {open && (
        <div className="cf-picker-pop" role="dialog" aria-label="Content framework areas">
          <div className="row-gap">
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter the areas" aria-label="Filter the areas" autoFocus />
            <span className="small quiet">{cur.length} chosen</span>
          </div>
          <AreaChecks value={cur} onChange={setCur} filter={q} />
          <div className="row-gap cf-picker-actions">
            {resetLabel && <button disabled={busy} onClick={() => save([])}>{resetLabel}</button>}
            <span style={{ flex: 1 }} />
            <button onClick={() => setOpen(false)}>Cancel</button>
            <button className="primary" disabled={busy} onClick={() => save(cur)}>Save</button>
          </div>
        </div>
      )}
    </span>
  );
}
