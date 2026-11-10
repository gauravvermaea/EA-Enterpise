// The help panel and the tooltips (D497), from the one help catalogue (help/catalogue.json).
//  - ? Help in the top bar, F1 anywhere, or ? on a pop-up opens the panel beside the page: help for the pop-up open,
//    the wizard step, the sub-tab, the tab and the page, most specific first, and a search over all the help.
//  - Every button, tab, label and field without its own title gets one from the catalogue when the mouse or the
//    keyboard reaches it (elements that already have a title keep it).
import { useEffect, useState } from "react";
import { currentNav } from "../navActions";
import { lookup, norm, openHelp, pageHelp, searchHelp, tipOf } from "./help";

const NAV_TABS = ".nav-classic, .nav-groups, .nav-tabs, .nav-menu";
const FORM = new Set(["INPUT", "SELECT", "TEXTAREA"]);

// a label's own words: its first text, skipping the field inside it (a select's options are not its words)
function labelWords(el) {
  for (const n of el.childNodes) {
    if (n.nodeType === 3 && n.textContent.trim()) return n.textContent;
    if (n.nodeType === 1 && !FORM.has(n.tagName) && n.textContent.trim()) return labelWords(n) || n.textContent;
  }
  return "";
}

function fieldWords(el) {
  if (el.tagName === "LABEL") return labelWords(el);
  const lab = el.closest("label") || (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`));
  return (lab && labelWords(lab)) || el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name
    || el.previousElementSibling?.textContent || "";
}

// the tooltip for an element without a title, from the catalogue
export function tooltipFor(el) {
  if (el.matches('[role="tab"]')) return tipOf(lookup("tab", el.textContent)?.entry);
  if (el.tagName === "BUTTON") {
    const words = el.textContent || "";
    const aria = el.getAttribute("aria-label") || "";
    return tipOf(lookup("button", words)?.entry || lookup("button", aria)?.entry || lookup("tab", words)?.entry);
  }
  if (el.tagName === "LABEL" || FORM.has(el.tagName)) return tipOf(lookup("field", fieldWords(el))?.entry);
  return "";
}

function useTooltips() {
  useEffect(() => {
    const give = (e) => {
      const el = e.target?.closest?.('button, [role="tab"], label, input, select, textarea');
      if (!el || el.dataset.helpTip !== undefined) return;
      el.dataset.helpTip = "";
      if (el.getAttribute("title")) return;            // its own tooltip stays
      if (FORM.has(el.tagName) && el.closest("label[title]")) return;
      const tip = tooltipFor(el);
      if (tip) el.setAttribute("title", tip);
    };
    document.addEventListener("mouseover", give, true);
    document.addEventListener("focusin", give, true);
    return () => { document.removeEventListener("mouseover", give, true); document.removeEventListener("focusin", give, true); };
  }, []);
}

// what is on the screen now, most specific first: the pop-up, the wizard step, sub-tabs, the tab, the page
function helpHere(popupTitle) {
  const out = [];
  const add = (label, hit) => { if (hit && !out.some((x) => x.key === hit.key)) out.push({ label, ...hit }); };
  const dialogs = [...document.querySelectorAll('[role="dialog"]')].filter((d) => !d.closest(".help-panel"));
  const top = dialogs[dialogs.length - 1];
  const title = popupTitle || top?.getAttribute("aria-label") || top?.querySelector("h2")?.textContent || "";
  if (title) add("This pop-up", lookup("popup", title));
  const step = document.querySelector(".wizard-steps li.on button, .wiz-steps li.on");
  if (step) add("This step", lookup("step", step.textContent.replace(/^\s*\d+\.\s*/, "").replace(/\s*•\s*$/, "")));
  const subs = [...document.querySelectorAll('main [role="tab"][aria-selected="true"]')].filter((t) => !t.closest(NAV_TABS));
  subs.forEach((t) => add("This sub-tab", lookup("tab", t.textContent)));
  const nav = currentNav();
  if (nav?.active) {
    const tab = nav.groups?.flatMap((g) => g.tabs).find((t) => t.k === nav.active);
    if (tab) add("This tab", lookup("tab", tab.label));
  }
  add("This page", pageHelp(window.location.hash || "#/"));
  return out;
}

function Entry({ label, entry }) {
  if (!entry || typeof entry === "string") return null;
  return (
    <section className="help-entry">
      {label && <p className="help-label">{label}</p>}
      {entry.title && <h3>{entry.title}</h3>}
      <p>{entry.what}</p>
      {entry.how?.length ? <ul>{entry.how.map((h) => <li key={h}>{h}</li>)}</ul> : null}
      {entry.example && <p className="help-example"><b>Example:</b> {entry.example}</p>}
    </section>
  );
}

export function HelpButton() {
  return (
    <button className="linkish help-open" title="Help for this page (F1)" aria-keyshortcuts="F1" onClick={() => openHelp()}>? Help</button>
  );
}

export default function HelpPanel() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [words, setWords] = useState("");
  useTooltips();
  useEffect(() => {
    const show = (e) => { setItems(helpHere(e.detail?.popup)); setWords(""); setOpen(true); };
    const key = (e) => {
      if (e.key === "F1") { e.preventDefault(); show({ detail: {} }); }
      else if (e.key === "Escape" && open && !document.querySelector('[role="dialog"]:not(.help-panel)')) setOpen(false);
    };
    const moved = () => { if (open) setItems(helpHere()); };
    window.addEventListener("eax-help", show);
    window.addEventListener("keydown", key);
    window.addEventListener("hashchange", moved);
    return () => { window.removeEventListener("eax-help", show); window.removeEventListener("keydown", key); window.removeEventListener("hashchange", moved); };
  }, [open]);
  useEffect(() => {        // pop-ups and the page make room for the panel instead of hiding under it
    document.body.classList.toggle("with-help", open);
    return () => document.body.classList.remove("with-help");
  }, [open]);
  if (!open) return null;
  const found = searchHelp(words);
  return (
    <aside className="help-panel" role="complementary" aria-label="Help">
      <div className="help-head">
        <h2>Help</h2>
        <button className="linkish" onClick={() => setOpen(false)} aria-label="Close the help">✕</button>
      </div>
      <input type="search" className="help-search" aria-label="Search the help" placeholder="Search the help, e.g. merge, tag, KPI"
        value={words} onChange={(e) => setWords(e.target.value)} />
      {norm(words).length >= 2
        ? (found.length ? found.map((f) => <Entry key={f.key} label={f.key.split(":")[0]} entry={f.entry} />)
          : <p className="quiet">Nothing found for "{words}".</p>)
        : (items.length ? items.map((it) => <Entry key={it.key} label={it.label} entry={it.entry} />)
          : <p className="quiet">No help for this screen yet.</p>)}
      <p className="quiet small help-foot">Rest the mouse on any button or field for a short tip. F1 opens this panel anywhere.</p>
    </aside>
  );
}
