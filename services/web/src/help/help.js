// On-screen help (D497): one catalogue (catalogue.json) for the help panel and the tooltips. Keys:
//   page:#/route  tab:Label  popup:Title (* = a dynamic part)  step:Label  field:Label  button:Text
// tools/help_inventory.py finds every key the screens need; services/api/tests/test_help_catalogue.py fails the
// build when one has no entry. How to add help for a new screen: docs/help-catalogue.md.
import catalogue from "./catalogue.json";

export const norm = (t) => String(t || "").replace(/\s+/g, " ").trim().replace(/(\s*[:…]|\.\.\.)$/, "").trim();

const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
// the keys with dynamic parts, by kind, as patterns; the one with the most fixed text wins
const PATTERNS = {};
for (const key of Object.keys(catalogue)) {
  const i = key.indexOf(":");
  if (i < 0 || key.startsWith("_")) continue;
  const kind = key.slice(0, i), text = key.slice(i + 1);
  if (!text.includes("*")) continue;
  (PATTERNS[kind] ||= []).push({ key, re: new RegExp("^" + text.split("*").map(esc).join(".+?") + "$", "i"), fixed: text.replace(/\*/g, "").length });
}
Object.values(PATTERNS).forEach((list) => list.sort((a, b) => b.fixed - a.fixed));

// buttons and labels are keyed by their leading words (what comes before a count or a name): match by prefix too
const PREFIXES = {};
for (const key of Object.keys(catalogue)) {
  const i = key.indexOf(":");
  if (i < 0 || key.startsWith("_")) continue;
  const kind = key.slice(0, i);
  if (kind === "button" || kind === "field" || kind === "tab") (PREFIXES[kind] ||= []).push(key.slice(i + 1));
}
Object.values(PREFIXES).forEach((list) => list.sort((a, b) => b.length - a.length));

export function lookup(kind, text) {
  const t = norm(text);
  if (!t) return null;
  const exact = catalogue[`${kind}:${t}`];
  if (exact) return { key: `${kind}:${t}`, entry: exact };
  for (const p of PATTERNS[kind] || []) if (p.re.test(t)) return { key: p.key, entry: catalogue[p.key] };
  for (const pre of PREFIXES[kind] || []) {
    if (pre.length >= 3 && !pre.includes("*") && t.toLowerCase().startsWith(pre.toLowerCase())) return { key: `${kind}:${pre}`, entry: catalogue[`${kind}:${pre}`] };
  }
  return null;
}

export const tipOf = (entry) => (!entry ? "" : typeof entry === "string" ? entry : entry.tip || entry.what || "");

// the page's help: the longest page key the route starts with
export function pageHelp(route) {
  const path = String(route || "#/").split("?")[0];
  let best = null;
  for (const key of Object.keys(catalogue)) {
    if (!key.startsWith("page:")) continue;
    const r = key.slice(5);
    if ((path === r || path.startsWith(r.endsWith("/") ? r : r + "/") || (r === "#/" && path === "#")) && (!best || r.length > best.length)) best = r;
  }
  return best ? { key: `page:${best}`, entry: catalogue[`page:${best}`] } : null;
}

// every entry with a panel (pages, tabs, pop-ups, steps), for the panel's search
export function searchHelp(words) {
  const w = norm(words).toLowerCase();
  if (w.length < 2) return [];
  const out = [];
  for (const [key, entry] of Object.entries(catalogue)) {
    if (key.startsWith("_") || typeof entry === "string") continue;
    const text = `${key} ${entry.title || ""} ${entry.what} ${(entry.how || []).join(" ")}`.toLowerCase();
    if (text.includes(w)) out.push({ key, entry });
    if (out.length >= 12) break;
  }
  return out;
}

export function openHelp(detail = {}) {
  window.dispatchEvent(new CustomEvent("eax-help", { detail }));
}

export default catalogue;
