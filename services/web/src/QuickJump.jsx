// Quick jump (D481): Ctrl+K (⌘K on a Mac) anywhere: type to go to a group or tab of the page shown, an action of the tab
// shown, a part of EA Explorer, a model or a project. Near spellings work (the same matcher as search, names.js).
import { useEffect, useRef, useState } from "react";
import { apiFetch, partOn } from "./auth";
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
  for (const [l, h, part] of PLACES) if (!part || partOn(part)) out.push({ label: l, where: "Go to", href: h, kind: "place" });
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
  const input = useRef(null);
  const back = useRef(null);
  useEffect(() => {
    const key = (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "k" || e.key === "K")) {
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
  if (!open) return null;
  const all = entries(models, projects);
  const found = (q.trim() ? fuzzyFilter(all, q, (x) => x.label, (x) => x.where) : all.filter((x) => x.kind !== "model" && x.kind !== "project")).slice(0, 12);
  const close = () => { setOpen(false); back.current?.focus?.(); };
  const pick = (x) => { if (!x) return; setOpen(false); window.location.hash = x.href.replace(/^#/, ""); };
  return (
    <div className="ed-backdrop qj-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className="qj" role="dialog" aria-modal="true" aria-label="Quick jump">
        <input ref={input} value={q} placeholder="Go to a tab, action, model or project…" aria-label="Go to"
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
        <p className="quiet small qj-help">↑ ↓ to choose · Enter to go · Esc to close</p>
      </div>
    </div>
  );
}
