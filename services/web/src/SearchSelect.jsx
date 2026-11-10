// A drop-down you can type in (owner, 10 Nov 2026, D540): the list of types (or any options) filtered as you type, with
// near spellings ("aplication comp" finds Application Component), grouped like the drop-down it replaces. Clicking it or
// pressing Down shows the whole list; Up and Down move, Enter chooses, Esc closes the list and keeps the choice (a second Esc
// reaches the pop-up around it). Used for every
// type drop-down of the drawn view and for the entity type pickers of Duplicates.
// options: [{ value, label, group?, note? }]; value: the chosen value ("" for none); onChange(value).
import { useEffect, useMemo, useRef, useState } from "react";
import { fuzzyFilter } from "./names";

let seq = 0;

export default function SearchSelect({ value, onChange, options, ariaLabel, placeholder = "Type to search", className = "", disabled = false }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [at, setAt] = useState(0);
  const box = useRef(null);
  const input = useRef(null);
  const id = useMemo(() => `ss-${(seq += 1)}`, []);
  const chosen = options.find((o) => o.value === value);
  const shown = useMemo(() => (q.trim() ? fuzzyFilter(options, q, (o) => o.label, (o) => `${o.group || ""} ${o.value}`) : options), [q, options]);
  useEffect(() => { setAt(0); }, [q]);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (box.current && !box.current.contains(e.target)) { setOpen(false); setQ(""); } };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  const pick = (o) => { onChange(o.value); setOpen(false); setQ(""); };
  const key = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (!open) setOpen(true); else setAt((i) => Math.min(i + 1, shown.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter") { if (open && shown[at]) { e.preventDefault(); pick(shown[at]); } }
    else if (e.key === "Escape") { if (open) { e.preventDefault(); e.stopPropagation(); e.nativeEvent.stopPropagation(); setOpen(false); setQ(""); } }
    else if (e.key === "Tab") { setOpen(false); setQ(""); }
  };
  useEffect(() => {
    if (!open) return;
    const el = box.current?.querySelector(`#${id}-o${at}`);
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }, [at, open, id]);
  let lastGroup = null;
  return (
    <span className={`search-select ${className}`} ref={box}>
      <input ref={input} role="combobox" aria-expanded={open} aria-controls={`${id}-list`} aria-autocomplete="list" aria-label={ariaLabel}
        aria-activedescendant={open && shown[at] ? `${id}-o${at}` : undefined} disabled={disabled}
        value={open ? q : (chosen ? chosen.label : "")} placeholder={open ? placeholder : (chosen ? "" : placeholder)}
        onFocus={() => { setOpen(true); setQ(""); }} onClick={() => setOpen(true)}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }} onKeyDown={key} />
      <span className="search-select-caret" aria-hidden="true" onMouseDown={(e) => { e.preventDefault(); if (open) { setOpen(false); setQ(""); } else input.current?.focus(); }}>▾</span>
      {open && (
        <ul className="search-select-list" role="listbox" id={`${id}-list`} aria-label={ariaLabel}>
          {!shown.length && <li className="quiet small search-select-none">Nothing matches "{q}"</li>}
          {shown.map((o, i) => {
            const head = !q.trim() && o.group && o.group !== lastGroup ? o.group : null;
            lastGroup = o.group;
            return [
              head && <li key={`g-${head}`} className="search-select-group" role="presentation">{head}</li>,
              <li key={`${o.value}`} id={`${id}-o${i}`} role="option" aria-selected={o.value === value}
                className={`search-select-opt${i === at ? " at" : ""}${o.value === value ? " on" : ""}`}
                onMouseDown={(e) => { e.preventDefault(); pick(o); }} onMouseEnter={() => setAt(i)}>
                {o.label}{q.trim() && o.group ? <span className="quiet small"> · {o.group}</span> : null}{o.note ? <span className="quiet small"> {o.note}</span> : null}
              </li>,
            ];
          })}
        </ul>
      )}
    </span>
  );
}
