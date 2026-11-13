// The top menu (R2.0, D586 to D591): the site picker on the left (Farm Admin), the main areas across the top (Architecture
// Work, Model Admin, Project Admin, Repository, System Admin), and on the right ? (help and documentation) and the person's
// own menu (User and Profile in one, with Sign out); each a drop-down with sub-menus where needed. Every
// screen, tab and wizard of EA Explorer is under one of them (tests/test_menu_reachable.py checks nothing is left out).
// An item a person may not use is hidden (D588); an area with nothing left is hidden too.
//
// An item: { label, href?, ok?, part?, items?, action?, dynamic?, note? }
//   href    where it goes (#/... in EA Explorer, or a full address opened in a new tab)
//   ok()    may this person use it (default: yes); part: shown only while that part is switched on (D329)
//   items   a sub-menu; dynamic: "models" | "projects" | "sites" fills it with the person's own when opened
//   action  "sign-out" | "help": done in place
import { can, libraryInfo, myInfo, partOn, roles, signOut } from "./auth";
import { openHelp } from "./help/help";
import { serviceOn } from "./fmt";
import { MODEL_WIZARDS, PROJECT_WIZARDS, SYSTEM_WIZARDS } from "./wizardLists";

// ---------------------------------------------------------------- who may use what
const anyModelAdmin = () => (myInfo()?.models || []).some((m) => (m.permissions || []).includes("model.lock"));
export const mayModelAdmin = () => anyModelAdmin() || can("models.create") || can("library.curate") || can("models.delete");
export const mayProjectAdmin = () => roles().length > 0 || can("library.curate");
const ops = () => can("system.operate");
const sup = () => roles().includes("super-admin");
const creator = () => can("models.create") || can("library.curate");

// the menu style: the menu bar only. Classic (D589) went in two steps: its button (D603), then its screens (owner,
// 12 Nov 2026, R2.25, D606)

// ---------------------------------------------------------------- the wizards as sub-menus (D587)
const modelWizards = () => MODEL_WIZARDS.map(([group, cards]) => ({
  label: group,
  items: cards.map((c) => ({ label: c.title, href: `#/model-admin/wizards?wizard=${c.k}`, ok: c.none && c.k !== "new" ? creator : undefined })),
}));
const projectWizards = () => [
  { label: "New project", items: [
    { label: "Blank project", href: "#/projects/new?template=blank" },
    { label: "From a project template…", href: "#/project-admin" },
    { label: "Restore a project from a backup file", href: "#/project-admin?wizard=restore-file" },
  ] },
  { label: "On a project", items: PROJECT_WIZARDS.map((w) => ({ label: w.title.replace(/^✎ /, ""), href: `#/project-admin?wizard=${w.k}`, ok: w.sup ? sup : undefined })) },
  { label: "Template libraries", href: "#/project-admin/library" },
  { label: "A new model for a project", href: "#/model-admin/wizards?wizard=new" },
];
const systemWizards = () => [
  ...SYSTEM_WIZARDS.map((w) => ({ label: w.title, href: `#/admin/wizards?wizard=${w.k}`,
    ok: w.who === "users" ? () => can("users.read") || sup() : w.who === "ops" ? ops : () => can("settings.manage") })),
  { label: "Map a Keycloak role", href: "#/admin/users/mapping", ok: () => can("users.read") },
  { label: "Switch a service on or off", href: "#/admin/system", ok: () => ops() || can("settings.manage") },
];

// ---------------------------------------------------------------- the nine areas (D586)
export function menuTree() {
  const enterpriseLibrary = () => {
    const lib = libraryInfo();
    if (!partOn("projects") || lib.mode === "off") return null;
    return lib.mode === "link" ? { label: "Enterprise library ↗", href: lib.link } : { label: "Enterprise library", href: "#/enterprise-library" };
  };
  return [
    { key: "me", label: "Me", place: "right", items: [
      { label: "Home", href: "#/" },
      { label: "My tasks", items: [
        { label: "Requests to me", href: "#/notifications/received" },
        { label: "Requests I sent", href: "#/notifications/sent" },
        { label: "New request", href: "#/notifications/new" },
        { label: "Background tasks", href: "#/notifications/tasks" },
        { label: "Merge requests", href: "#/merge-requests" },
      ] },
      { label: "Surveys to answer", href: "#/surveys" },
      { label: "Notifications", href: "#/notifications" },
      { label: "Recent and pinned", href: "#/work" },
      { label: "Search everything", href: "#/search" },
      { label: "My profile and skills", href: "#/my-profile" },
      { label: "My tokens and keys", href: "#/admin/machine-access" },
      { label: "Sign out", action: "sign-out" },
    ] },
    { key: "work", label: "Architecture Work", items: [
      { label: "My projects", href: "#/work?tab=projects", part: "projects", dynamic: "projects" },
      { label: "My models", href: "#/work?tab=models", dynamic: "models" },
      { label: "Compare and analyse", items: [
        { label: "Compare models", href: "#/compare" },
        { label: "Gap analysis", href: "#/compare/gaps" },
        { label: "Common analysis", href: "#/compare/common" },
      ] },
      { label: "Merge requests", href: "#/merge-requests" },
      { label: "Change log", href: "#/change-log" },
      // for everyone, admin or not (owner, 12 Nov 2026): the libraries to start from
      { label: "Model library", href: "#/library" },
      { label: "Project library", href: "#/project-library", part: "projects" },
    ] },
    { key: "model", label: "Model Admin", ok: mayModelAdmin, items: [
      { label: "Wizards", href: "#/model-admin", items: modelWizards() },
      { label: "Models", href: "#/model-admin/list" },
      { label: "Model hierarchy", href: "#/model-admin/hierarchy" },
      { label: "Archive", href: "#/archive" },
      { label: "Metamodel drafts", href: "#/model-admin/drafts" },
      { label: "Model library", items: [
        { label: "Every library model", href: "#/library" },
        { label: "External reference models", href: "#/library?kind=reference" },
      ] },
    ] },
    { key: "project", label: "Project Admin", part: "projects", ok: mayProjectAdmin, items: [
      { label: "Wizards", href: "#/project-admin", items: projectWizards() },
      { label: "Projects", href: "#/project-admin/list" },
      { label: "Project bases", href: "#/project-admin/bases" },
      { label: "Templates and libraries", items: [
        { label: "Project library", href: "#/project-admin/libprojects" },
        { label: "Project templates", href: "#/project-admin/templates" },
        { label: "Project content template library", href: "#/project-admin/library" },
        { label: "Template setup", href: "#/project-admin/template-setup" },
      ] },
      { label: "Principles", href: "#/project-admin/principles" },
      { label: "Surveys and maturity", items: [
        { label: "Surveys", href: "#/surveys" },
        { label: "EA capability maturity", href: "#/maturity", ok: () => can("maturity.manage") },
      ] },
    ] },
    { key: "repository", label: "Repository & Content Framework", items: [
      { label: "Architecture Repository", href: "#/repository", part: "repository", items: [
        { label: "The Architecture Repository", href: "#/repository" },
        // the organisation's principles for everyone, as cards by area (R2.48, D607)
        { label: "Architecture principles", href: "#/principles" },
        { label: "Architecture landscape", items: [
          { label: "Strategic architectures", href: "#/work?tab=models&view=tiles&level=strategic" },
          { label: "Segment architectures", href: "#/work?tab=models&view=tiles&level=segment" },
          { label: "Capability architectures", href: "#/work?tab=models&view=tiles&level=capability" },
          { label: "Transition architectures", href: "#/work?tab=models&view=tiles&level=transition" },
        ] },
        { label: "Reference architectures", items: [
          { label: "Foundation architectures", href: "#/repository/reference/foundation" },
          { label: "Common systems architectures", href: "#/repository/reference/common" },
          { label: "Industry architectures", href: "#/repository/reference/industry" },
          { label: "Organisation's own architectures", href: "#/repository/reference/own" },
        ] },
        { label: "Governance log", items: [
          { label: "Decision log", href: "#/repository/decisions" },
          { label: "Compliance assessments", href: "#/repository/compliance" },
          { label: "Capability assessments", href: "#/repository/capability" },
          { label: "Calendar", href: "#/repository/calendar" },
          { label: "Project portfolio", href: "#/work?tab=projects", part: "projects" },
          { label: "Performance measurement", href: "#/repository/measures" },
          { label: "Tracking sheets", href: "#/repository/sheets" },
        ] },
        { label: "Architecture capability", items: [
          { label: "Skills repository", href: "#/repository/skills" },
          { label: "EA capability maturity", href: "#/maturity" },
          { label: "Organisation structure", href: "#/repository/people" },
          { label: "Architecture board", href: "#/repository/board" },
        ] },
      ] },
      { label: "Content framework", href: "#/metamodel", items: [
        { label: "Content metamodel (every model)", href: "#/metamodel" },
        { label: "Model hierarchy", href: "#/metamodel/hierarchy" },
        { label: "Metamodel drafts", href: "#/metamodel/drafts" },
      ] },
      { label: "Libraries", items: [
        { label: "Reference library", href: "#/reference-library", part: "references" },
        enterpriseLibrary(),
        { label: "Model library", href: "#/library" },
        { label: "External reference models", href: "#/library?kind=reference" },
        { label: "Project library", href: "#/project-library", part: "projects" },
      ].filter(Boolean) },
    ] },
    { key: "help", label: "?", title: "Help and documentation", place: "right", items: [
      { label: "Help for this page (F1)", action: "help" },
      { label: "Documentation: every document", href: "#/documentation" },
      { label: "Getting started", href: "#/documentation/readme" },
      { label: "What EA Explorer does", href: "#/documentation/capabilities" },
      { label: "Release notes", href: "#/documentation?group=Release%20notes" },
      { label: "Command line (eax)", href: "#/documentation/command-line-help" },
      { label: "Connect your AI assistant (MCP)", href: "#/mcp", ok: () => serviceOn("mcp") },
      { label: "API (Swagger) ↗", href: "/api/docs" },
    ] },
    { key: "system", label: "System Admin", ok: () => ops() || can("settings.manage") || can("users.read"), items: [
      { label: "Wizards", href: "#/admin/wizards", items: systemWizards() },
      { label: "Settings", items: [
        { label: "Application settings", href: "#/admin/application" },
        { label: "System settings", href: "#/admin/system", ok: () => ops() || can("settings.manage") },
        { label: "Banner", href: "#/admin/banner", ok: ops },
        { label: "Licences", href: "#/admin/licences" },
      ] },
      { label: "Users and roles", href: "#/admin/users", ok: () => can("users.read") },
      { label: "Running", ok: ops, items: [
        { label: "Health", href: "#/admin/health" },
        { label: "Containers", href: "#/admin/containers" },
        { label: "Hosts", href: "#/admin/hosts" },          // the Docker engine (R2.16)
        { label: "Mounts", href: "#/admin/mounts" },        // volumes and bind mounts (R2.17)
        { label: "Databases", href: "#/admin/databases" },
        { label: "Persist", href: "#/admin/persist" },
        { label: "Footprint", href: "#/admin/footprint" },
        { label: "Estate", href: "#/admin/estate" },
        { label: "Scaling", href: "#/admin/scaling" },
        { label: "Operations", href: "#/admin/operations" },
        { label: "Data quality", href: "#/admin/quality" },
      ] },
      { label: "Backups and restores", ok: ops, items: [
        { label: "Backups", href: "#/admin/backups" },
        { label: "Restores", href: "#/admin/restores" },
      ] },
      { label: "Updates", href: "#/admin/updates", ok: ops },   // Deploy moved to the site picker (R2.14)
      { label: "Tools", ok: ops, items: [
        { label: "Command centre", href: "#/admin/commands" },
        { label: "SQL", href: "#/admin/sql" },
        { label: "Self-test", href: "#/admin/self-test" },
      ] },
      { label: "Machine access", href: "#/admin/machine-access" },
      { label: "AI activity (MCP)", href: "#/mcp", ok: () => serviceOn("mcp") },
    ] },
    // the site picker (R2.0, R2.2): this site, my remote instances (each opens in a new tab, signed in there), my list
    { key: "farm", label: "Local", title: "The EA Explorer sites: this one is Local; yours open in a new tab", place: "left", items: [
      { label: "Sites", href: "#/farm", dynamic: "farm-sites" },   // everyone's list, with a health dot (R2.1)
      { label: "My remote instances", href: "#/farm/connect", dynamic: "sites" },
      { label: "Connect to a site", href: "#/farm/connect" },
      { label: "Manage sites", href: "#/farm" },
      // putting EA Explorer on another laptop, server or cloud belongs with the other sites (R2.14; owner, 11 Nov 2026)
      { label: "Deploy EA Explorer", href: "#/farm/deploy", ok: ops },
    ] },
  ];
}

// what this person sees: parts switched off and items they may not use taken out, empty sub-menus and areas too
export function visible(items) {
  const out = [];
  for (const it of items || []) {
    if (!it) continue;
    if (it.part && !partOn(it.part)) continue;
    if (it.ok && !it.ok()) continue;
    if (it.items) {
      const kids = visible(it.items);
      if (!kids.length && !it.href && !it.dynamic) continue;
      out.push({ ...it, items: kids });
    } else out.push(it);
  }
  return out;
}

// every item this person may use, flat, with its path ("System Admin › Running › Health"), for the "/" search
export function menuEntries() {
  const out = [];
  const walk = (items, path) => {
    for (const it of items) {
      const where = path.join(" › ");
      if (it.href || it.action) out.push({ label: it.label, where, href: it.href || "", action: it.action || "" });
      if (it.items) walk(it.items, [...path, it.label]);
    }
  };
  walk(visible(menuTree()), []);
  return out;
}

// which area a page is in (the area shown as on)
export function menuAreaOf(route) {
  const r = route || "#/";
  if (r.startsWith("#/admin")) return "system";
  if (r.startsWith("#/model-admin") || (r.startsWith("#/library") && mayModelAdmin())) return "model";
  if (r.startsWith("#/project-admin") || /^#\/projects\/(new|[^/]+\/edit)/.test(r)) return "project";
  if (/^#\/(repository|reference-library|enterprise-library|maturity|principles)/.test(r)) return "repository";
  if (r.startsWith("#/documentation") || r.startsWith("#/mcp")) return "help";
  if (r.startsWith("#/my-profile")) return "me";
  if (r.startsWith("#/farm")) return "farm";
  if (/^#\/(work|metamodel|projects|project-library|library|compare|change-log|merge-requests|change-documents)/.test(r)) return "work";
  return "me";
}

// a menu item that does something in place (sign out, the help panel, the menu style)
export function runMenuAction(action) {
  if (action === "sign-out") signOut();
  else if (action === "help") openHelp();
}
