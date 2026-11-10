// The "⋯ Actions" button at the right of a tab (D479): only the actions that make sense on that tab and that the person
// may do, from one registry (navActions.js). Keyboard: Enter or Down opens, arrows move, Esc closes.
import { useEffect, useRef, useState } from "react";
import { actionsFor } from "./navActions";

export function MenuList({ items, onDone, label }) {
  const ref = useRef(null);
  useEffect(() => { ref.current?.querySelector("[role=menuitem]")?.focus(); }, []);
  const key = (e) => {
    const all = [...(ref.current?.querySelectorAll("[role=menuitem]") || [])];
    const i = all.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); all[(i + 1) % all.length]?.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); all[(i - 1 + all.length) % all.length]?.focus(); }
    else if (e.key === "Home") { e.preventDefault(); all[0]?.focus(); }
    else if (e.key === "End") { e.preventDefault(); all[all.length - 1]?.focus(); }
    else if (e.key === "Escape" || e.key === "Tab") { onDone(e.key === "Escape"); }
  };
  return (
    <div className="nav-pop" role="menu" aria-label={label} ref={ref} onKeyDown={key}>
      {items.map((a, n) => (a === "-"
        ? <div key={`s${n}`} className="nav-pop-sep" role="separator" />
        : a.href
          ? <a key={n} role="menuitem" tabIndex={-1} href={a.href} className={a.danger ? "danger" : ""} title={a.title || ""} onClick={() => onDone(false)}>{a.label}</a>
          : <button key={n} role="menuitem" tabIndex={-1} className={a.danger ? "danger" : ""} title={a.title || ""}
            onClick={() => { onDone(false); a.run?.(); }}>{a.label}</button>))}
    </div>
  );
}

export default function ActionsMenu({ page, tab, ctx }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  const btn = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const out = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", out);
    return () => document.removeEventListener("mousedown", out);
  }, [open]);
  const { own, page: general } = actionsFor(page, tab, ctx);
  const items = [...own, ...(own.length && general.length ? ["-"] : []), ...general];
  if (!items.length) return null;
  return (
    <span className="nav-actions" ref={box}>
      <button ref={btn} className="nav-actions-btn" aria-haspopup="menu" aria-expanded={open} title="What you can do here"
        onClick={() => setOpen((x) => !x)} onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); } }}>⋯ Actions</button>
      {open && <MenuList label="Actions" items={items} onDone={(refocus) => { setOpen(false); if (refocus) btn.current?.focus(); }} />}
    </span>
  );
}
