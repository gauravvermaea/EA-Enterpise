// Page navigation helpers (D478–D481): the person's navigation style, each group's last tab, the page shown now
// (for quick jump, Ctrl+K) and one registry of the actions each tab offers (the "⋯ Actions" menu).
import { can, canOn, myInfo } from "./auth";

// ---------------------------------------------------------------- page tabs: grouped (groups, then tabs, then sub-tabs)
// the only style since the Classic screens went (owner, 12 Nov 2026, R2.25, D606)
const who = () => (myInfo() || {}).username || "anyone";

// each group remembers the tab last used in it, per page kind (model, project, model admin)
const lastKey = (page) => `eax.navLast.${who()}.${page}`;
export function readLastTabs(page) {
  try { return JSON.parse(window.localStorage.getItem(lastKey(page)) || "{}") || {}; } catch { return {}; }
}
export function saveLastTab(page, group, tab) {
  try { const all = readLastTabs(page); all[group] = tab; window.localStorage.setItem(lastKey(page), JSON.stringify(all)); }
  catch { /* only a convenience */ }
}


// ---------------------------------------------------------------- the page shown now (read by quick jump)
let current = null;
export function setCurrentNav(nav) {
  current = nav;
  try { window.__eaxNav = nav; } catch { /* no window */ }    // the self-test's page sweep reads every tab of the page shown (D575)
}
export function clearCurrentNav(nav) { if (current === nav) current = null; }
export function currentNav() { return current; }

// ---------------------------------------------------------------- the actions registry
// registerActions(page, tab, (ctx) => [{ label, href | run, ok, danger, title }]); tab "*" = every tab of that page.
// ctx: { page, tab, id, m (a model), p (a project) }. Items with ok === false are left out: only what the person may do.
const REG = {};
export function registerActions(page, tab, fn) { (REG[`${page}:${tab}`] = REG[`${page}:${tab}`] || []).push(fn); }

function collect(key, ctx) {
  const out = [];
  for (const fn of REG[key] || []) {
    try { for (const a of fn(ctx) || []) if (a && a.ok !== false) out.push(a); } catch { /* one bad entry never hides the rest */ }
  }
  return out;
}
// the tab's own actions, then the page's (shown after a line)
export function actionsFor(page, tab, ctx) {
  const c = { ...ctx, page, tab };
  return { own: collect(`${page}:${tab}`, c), page: collect(`${page}:*`, c) };
}

// ---------------------------------------------------------------- the starting set
const M = (ctx, rest) => `#/metamodel/${ctx.id}/${rest}`;
const P = (ctx, rest) => `#/projects/${ctx.id}/${rest}`;
const edits = (ctx) => canOn(ctx.id, "model.content") && !(ctx.m && (ctx.m.frozen_at || ctx.m.is_locked));
const isProject = (ctx) => ctx.m?.kind === "project";

registerActions("model", "grid", (ctx) => [
  { label: "Add an entity (data entry)", href: M(ctx, "entry"), ok: edits(ctx) },
  { label: "Load from Excel or CSV", href: M(ctx, "import"), ok: edits(ctx) },
  { label: "Download sheets to fill in", href: M(ctx, "import") },
  { label: "Find duplicates", href: M(ctx, "duplicates"), ok: isProject(ctx) },
  { label: "Uncommitted changes", href: M(ctx, "changes"), ok: isProject(ctx) },
  { label: "Report designer", href: M(ctx, "designer") },
]);
registerActions("model", "entry", (ctx) => [
  { label: "Edit in the grid", href: M(ctx, "grid") },
  { label: "Load from Excel or CSV", href: M(ctx, "import"), ok: edits(ctx) },
  { label: "Uncommitted changes", href: M(ctx, "changes"), ok: isProject(ctx) },
  { label: "Find duplicates", href: M(ctx, "duplicates"), ok: isProject(ctx) },
]);
registerActions("model", "views", (ctx) => [
  { label: "Custom views (drawn and saved)", href: M(ctx, "views/custom") },
  { label: "Standard views", href: M(ctx, "views/standard") },
  { label: "Business views", href: M(ctx, "business") },
  { label: "Graph of the model", href: M(ctx, "graph") },
]);
registerActions("model", "quality", (ctx) => [
  { label: "Find duplicates", href: M(ctx, "duplicates") },
  { label: "Failing checks", href: M(ctx, "checks") },
  { label: "KPI trends", href: M(ctx, "kpis") },
]);
registerActions("model", "checks", (ctx) => [
  { label: "Quality", href: M(ctx, "quality"), ok: isProject(ctx) },
]);
registerActions("model", "reports", (ctx) => [
  { label: "Report designer", href: M(ctx, "designer") },
  { label: "OData feed for Power BI and Excel", href: M(ctx, "odata") },
  { label: "KPI trends", href: M(ctx, "kpis"), ok: ctx.m?.kind === "project" || ctx.m?.kind === "reference" },
]);
registerActions("model", "kpis", (ctx) => [
  { label: "Reports", href: M(ctx, "reports") },
  { label: "Report designer", href: M(ctx, "designer") },
]);
registerActions("model", "tags", (ctx) => [
  { label: "Compare two models or tags", href: "#/compare" },
  { label: "Gap analysis", href: "#/compare/gaps" },
  { label: "History of changes", href: M(ctx, "changes/history"), ok: isProject(ctx) },
]);
registerActions("model", "*", (ctx) => [
  { label: "Model wizards", href: `#/model-admin/${ctx.id}`, ok: canOn(ctx.id, "model.lock") || can("models.delete") },
  { label: "All models", href: "#/metamodel" },
]);

registerActions("project", "models", (ctx) => [
  { label: "Add or make a model", href: P(ctx, "edit?step=Models"), ok: !!ctx.p?.may_admin && !ctx.p?.frozen },
  { label: "Gaps and comparison", href: P(ctx, "analysis") },
  { label: "Model reports", href: P(ctx, "reports") },
]);
registerActions("project", "tasks", (ctx) => [
  { label: "Calendar", href: P(ctx, "calendar") },
  { label: "Sign-off", href: P(ctx, "signoff") },
  { label: "Tracking sheets", href: P(ctx, "sheets") },
]);
registerActions("project", "governance", (ctx) => [
  { label: "Record a compliance assessment", href: P(ctx, "governance?kind=Compliance%20assessment"), ok: !ctx.p?.frozen },
  { label: "Principles", href: P(ctx, "principles") },
  { label: "Standards", href: P(ctx, "standards") },
]);
registerActions("project", "otherdocs", (ctx) => [
  { label: "Library", href: P(ctx, "library") },
  { label: "Tracking sheets", href: P(ctx, "sheets") },
]);
registerActions("project", "views", (ctx) => [
  { label: "Models", href: P(ctx, "models") },
  { label: "Model reports", href: P(ctx, "reports") },
]);
registerActions("project", "*", (ctx) => [
  { label: "Edit the project", href: P(ctx, "edit"), ok: !!ctx.p?.may_admin && !ctx.p?.frozen },
  { label: "Project wizards", href: `#/project-admin/${ctx.id}`, ok: !!ctx.p?.may_admin || (ctx.p?.my_roles || []).includes("super-admin") },
  { label: "All projects", href: "#/work" },
]);

registerActions("admin", "*", (ctx) => [
  { label: "Open the model", href: `#/metamodel/${ctx.id}` },
  { label: "Merge requests waiting for me", href: "#/merge-requests" },
]);
