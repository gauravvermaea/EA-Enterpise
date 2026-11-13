// The top menu bar (R2.0, D586 to D590): nine areas across the top; each opens a drop-down, and an item with "›" opens
// its sub-menu beside it. Click or hover opens; Esc closes; the arrow keys move; Enter follows. Items a person may not
// use are not shown (menu.js). My projects and My models list the person's own when opened.
import { useEffect, useRef, useState } from "react";
import { apiFetch, currentUser, roleName, roles } from "./auth";
import { menuAreaOf, menuEntries, menuTree, runMenuAction, visible } from "./menu";

function follow(it, close) {
  close();
  if (it.action) { runMenuAction(it.action); return; }
  if (!it.href) return;
  if (/^#/.test(it.href)) window.location.hash = it.href.slice(1);
  else window.open(it.href, "_blank", "noopener,noreferrer");
}

// the person's own projects or models, for My projects and My models (the first 15, then "All …")
function useDynamic(kind, open) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    if (!open || !kind || rows) return;
    if (kind === "farm-sites") { // the shared list of sites (R2.1): a health dot, Local here, the others in a new tab
      const dot = { green: "🟢", amber: "🟠", red: "🔴" };
      apiFetch("/api/v1/sites").then((r) => setRows((r.sites || []).map((x) => (x.source === "local"
        ? { label: `${dot[x.health] || "⚪"} ${x.name} (this site)`, href: "#/" }
        : { label: `${dot[x.health] || "⚪"} ${x.name} ↗`, href: x.url })))).catch(() => setRows([]));
      return;
    }
    if (kind === "sites") {      // my remote EA Explorer instances (R2.2): each opens in a new tab, signed in there
      apiFetch("/api/v1/me/remote-instances").then((r) => setRows((r.items || []).map((x) => ({ label: `${x.name} ↗`, href: x.url }))))
        .catch(() => setRows([]));
      return;
    }
    const url = kind === "projects" ? "/api/v1/projects" : "/api/v1/models?archived=false";
    apiFetch(url).then((r) => {
      const list = kind === "projects" ? (r.projects || []).filter((x) => !x.is_library || (x.my_roles || []).length) // a library project is in Project library
        : (Array.isArray(r) ? r : r.models || []);
      setRows(list.map((x) => ({ label: x.name, href: kind === "projects" ? `#/projects/${x.id}` : `#/metamodel/${x.id}` })));
    }).catch(() => setRows([]));
  }, [kind, open, rows]);
  return rows;
}

function Item({ it, close, depth }) {
  const [open, setOpen] = useState(false);
  const rows = useDynamic(it.dynamic, open);
  const kids = it.dynamic
    ? [...(rows || []).slice(0, 15), ...(rows && rows.length > 15 ? [{ label: `All ${rows.length}…`, href: it.href }] : []),
      ...(rows && !rows.length ? [{ label: "None yet: open the list", href: it.href }] : []), ...(rows ? [] : [{ label: "Loading…" }])]
    : it.items;
  if (!kids) {
    return (
      <li role="none">
        <a role="menuitem" href={it.href || "#"} className="tm-item" tabIndex={-1}
          {...(it.href && !/^#/.test(it.href) ? { target: "_blank", rel: "noopener noreferrer" } : {})}
          onClick={(e) => { e.preventDefault(); follow(it, close); }}>{it.label}</a>
      </li>
    );
  }
  return (
    <li role="none" className={open ? "tm-sub open" : "tm-sub"} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <a role="menuitem" href={it.href || "#"} className="tm-item" tabIndex={-1} aria-haspopup="menu" aria-expanded={open}
        onClick={(e) => { e.preventDefault(); if (it.href) follow(it, close); else setOpen(!open); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") { e.preventDefault(); setOpen(true); setTimeout(() => e.currentTarget.parentElement?.querySelector(".tm-drop .tm-item")?.focus(), 0); }
        }}>
        {it.label}<span className="tm-arrow" aria-hidden="true">›</span>
      </a>
      {open && <Drop items={kids} close={close} depth={depth + 1} label={it.label} onBack={() => setOpen(false)} />}
    </li>
  );
}

function Drop({ items, close, depth, label, onBack }) {
  const ref = useRef(null);
  const move = (e) => {
    const all = [...(ref.current?.querySelectorAll(":scope > li > .tm-item") || [])];
    const i = all.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); all[(i + 1) % all.length]?.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); e.stopPropagation(); all[(i - 1 + all.length) % all.length]?.focus(); }
    else if (e.key === "ArrowLeft" && depth > 1) { e.preventDefault(); e.stopPropagation(); onBack?.(); }
    else if (e.key === "Enter" && i >= 0) { e.preventDefault(); e.stopPropagation(); all[i].click(); }
  };
  return (
    <ul ref={ref} className={`tm-drop depth-${depth}`} role="menu" aria-label={label} onKeyDown={move}>
      {items.map((it, i) => <Item key={`${it.label}${i}`} it={it} close={close} depth={depth} />)}
    </ul>
  );
}

// one menu bar: the areas of one place (D586, D591): "left" (the site picker, Farm Admin), the main areas, or "right"
// (? help and documentation, and the person's own menu: their name, User and Profile, Sign out)
export function MenuBar({ route, place = "main", label = "Main menu" }) {
  const [open, setOpen] = useState("");
  const bar = useRef(null);
  const areas = visible(menuTree()).filter((a) => (a.place || "main") === place);
  const on = menuAreaOf(route);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (!bar.current?.contains(e.target)) setOpen(""); };
    const esc = (e) => { if (e.key === "Escape") setOpen(""); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  useEffect(() => { setOpen(""); }, [route]);
  if (!areas.length) return null;
  const close = () => setOpen("");
  const me = currentUser();
  const title = (a) => (a.key === "me"
    ? <span className="tm-me"><span className="tm-me-name">{me?.name || me?.preferred_username}</span>
      <small className="role-chip">{roles().length ? roles().map(roleName).join(", ") : "no role"}</small></span>
    : a.key === "farm" ? <span className="tm-site"><span className="tm-site-dot" aria-hidden="true">●</span> {a.label}</span>
      : a.label);
  return (
    <nav className={`topmenu tm-${place}`} aria-label={label} ref={bar}>
      <ul className="tm-bar" role="menubar">
        {areas.map((a) => (
          <li key={a.key} role="none" className={`tm-area${open === a.key ? " open" : ""}${on === a.key ? " on" : ""}`}
            onMouseEnter={() => { if (open) setOpen(a.key); }}>
            <button role="menuitem" aria-haspopup="menu" aria-expanded={open === a.key} className={`tm-top tm-top-${a.key}`} data-area={a.key}
              title={a.title || undefined} aria-label={a.key === "help" ? "Help and documentation" : undefined}
              onClick={() => setOpen(open === a.key ? "" : a.key)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault(); setOpen(a.key);
                  setTimeout(() => bar.current?.querySelector(".tm-area.open > .tm-drop .tm-item")?.focus(), 0);
                }
              }}>{title(a)}</button>
            {open === a.key && <Drop items={a.items} close={close} depth={1} label={a.title || a.label} />}
          </li>
        ))}
      </ul>
    </nav>
  );
}

export default function TopMenu({ route }) {
  // every page the menu reaches, for the self-test's page sweep (eax/testing/ui_pages.py, R2.0.1)
  useEffect(() => { window.__eaxMenu = menuEntries().map((e) => e.href).filter((h) => h && h.startsWith("#/")); });
  return <MenuBar route={route} place="main" />;
}

