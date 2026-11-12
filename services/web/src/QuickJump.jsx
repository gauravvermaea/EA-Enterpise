// Find (D481, D590): "/" or Ctrl+K (⌘K on a Mac) anywhere outside a text box. Finds functionality (every menu item with
// its path, the tabs and actions of the page shown, the on-screen help's pages) and content (models, projects, and
// entities as you type, from search); the last line searches everything. Near spellings work (names.js).
import { useEffect, useRef, useState } from "react";
import { apiFetch, partOn } from "./auth";
import catalogue from "./help/catalogue.json";
import { menuEntries, runMenuAction } from "./menu";
import { actionsFor, currentNav } from "./navActions";
import { fuzzyFilter } from "./names";

const PLACES = [
  ["Start", "#/"], ["Models", "#/metamodel"], ["Projects", "#/work", "projects"], ["Repository", "#/repository", "repository"],
  ["Library", "#/library"], ["Compare", "#/compare"], ["Gap analysis", "#/compare/gaps"], ["Common analysis", "#/compare/common"],
  ["Change log", "#/change-log"], ["Merge requests", "#/merge-requests"], ["Surveys", "#/surveys"], ["Model admin", "#/model-admin"],
  ["Administration", "#/admin"], ["My profile", "#/my-profile"], ["MCP", "#/mcp"],
];

function entries(models, projects) {
  const out = [];
  const nav = currentNav();
  if (nav) {
    for (const g of nav.groups) for (const t of g.tabs) out.push({ label: t.label, where: `${g.label} · this page`, href: t.href, kind: "tab" });
    const a = actionsFor(nav.page, nav.active, nav.ctx || {});
    for (const x of [...a.own, ...a.page]) if (x.href) out.push({ label: x.label, where: "Action", href: x.href, kind: "action" });
  }
  const seen = new Set();
  for (const e of menuEntries()) {
    const key = `${e.label}|${e.href}|${e.action}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ label: e.label, where: `Menu · ${e.where}`, href: e.href, action: e.action, kind: "place" });
  }
  for (const [l, h, part] of PLACES) if ((!part || partOn(part)) && !out.some((x) => x.href === h)) out.push({ label: l, where: "Go to", href: h, kind: "place" });
  // the on-screen help's pages: a page found by what it does, not only its name
  for (const [key, entry] of Object.entries(catalogue)) {
    if (!key.startsWith("page:") || key.includes("*") || typeof entry !== "object") continue;
    const href = key.slice(5);
    if (/[:]/.test(href.slice(2)) || out.some((x) => x.href === href)) continue;
    out.push({ label: entry.title || href, where: `Help · ${String(entry.what || "").slice(0, 70)}`, href, kind: "help", text: entry.what });
  }
  for (const m of models || []) out.push({ label: m.name, where: `Model · ${m.kind_name || m.kind || ""}`, href: `#/metamodel/${m.id}`, kind: "model" });
  for (const p of projects || []) out.push({ label: p.name, where: "Project", href: `#/projects/${p.id}`, kind: "project" });
  return out;
}

export default function QuickJump() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const [models, setModels] = useState(null);
  const [projects, setProjects] = useState(null);
  const [hits, setHits] = useState(null);
  const input = useRef(null);
  const back = useRef(null);
  useEffect(() => {
    const key = (e) => {
      // "/" outside a text box or a grid
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName || "") || e.target?.isContentEditable || e.target?.closest?.(".grid-box");
      const slash = e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey;
      if (((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "k" || e.key === "K")) || slash) {
        e.preventDefault(); back.current = document.activeElement; setOpen(true); setQ(""); setSel(0);
      }
    };
    window.addEventListener("keydown", key);
    const ask = () => { back.current = document.activeElement; setOpen(true); setQ(""); setSel(0); };
    window.addEventListener("eax-quick-jump", ask);
    return () => { window.removeEventListener("keydown", key); window.removeEventListener("eax-quick-jump", ask); };
  }, []);
  useEffect(() => {
    if (!open) return;
    setTimeout(() => input.current?.focus(), 0);
    if (!models) apiFetch("/api/v1/models").then((r) => setModels(Array.isArray(r) ? r : r.models || [])).catch(() => setModels([]));
    if (!projects && partOn("projects")) apiFetch("/api/v1/projects").then((r) => setProjects(r.projects || [])).catch(() => setProjects([]));
  }, [open]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open || q.trim().length < 2) { setHits(null); return undefined; }
    const t = setTimeout(() => {
      apiFetch(`/api/v1/search?q=${encodeURIComponent(q.trim())}&limit=6`).then((r) => setHits(r.results || [])).catch(() => setHits([]));
    }, 250);
    return () => clearTimeout(t);
  }, [open, q]);
  if (!open) return null;
  const all = entries(models, projects);
  const words = q.trim();
  const fit = (words ? fuzzyFilter(all, q, (x) => x.label, (x) => `${x.where} ${x.text || ""}`) : all.filter((x) => x.kind === "tab" || x.kind === "action")).slice(0, 10);
  const ents = (hits || []).filter(() => words.length >= 2).slice(0, 6)
    .map((r) => ({ label: r.name, where: `${r.entity_type} · ${r.model}`, href: `#/metamodel/${r.model_id}/entity/${r.id}`, kind: "entity" }));
  const found = [...fit, ...ents, ...(words ? [{ label: `Search everything for “${words}”`, where: "Search", href: `#/search?q=${encodeURIComponent(words)}`, kind: "search" }] : [])];
  const close = () => { setOpen(false); back.current?.focus?.(); };
  const pick = (x) => {
    if (!x) return;
    setOpen(false);
    if (x.action) { runMenuAction(x.action); return; }
    if (/^#/.test(x.href)) window.location.hash = x.href.replace(/^#/, "");
    else window.open(x.href, "_blank", "noopener,noreferrer");
  };
  return (
    <div className="ed-backdrop qj-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className="qj" role="dialog" aria-modal="true" aria-label="Find">
        <input ref={input} value={q} placeholder="Find a function or content: a menu item, tab, model, project, entity…" aria-label="Find"
          role="combobox" aria-expanded="true" aria-controls="qj-list" aria-activedescendant={found[sel] ? `qj-${sel}` : undefined}
          onChange={(e) => { setQ(e.target.value); setSel(0); }}
          onKeyDown={(e) => {
            if (e.key === "Escape") { e.preventDefault(); close(); }
            else if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, found.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
            else if (e.key === "Enter") { e.preventDefault(); pick(found[sel]); }
          }} />
        <ul id="qj-list" role="listbox" aria-label="Places">
          {found.map((x, i) => (
            <li key={`${x.href}${i}`} id={`qj-${i}`} role="option" aria-selected={i === sel} className={i === sel ? "on" : ""}
              onMouseEnter={() => setSel(i)} onMouseDown={(e) => { e.preventDefault(); pick(x); }}>
              <span>{x.label}</span><span className="quiet small">{x.where}</span>
            </li>
          ))}
          {!found.length && <li className="quiet">Nothing found.</li>}
        </ul>
        <p className="quiet small qj-help">/ or Ctrl+K opens this · ↑ ↓ to choose · Enter to go · Esc to close</p>
      </div>
    </div>
  );
}
