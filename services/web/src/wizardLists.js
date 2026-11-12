// The wizards of Model admin, Project admin and System admin (R2.0, D586): one list each, used by their pages and by the
// top menu's sub-menus (Model Admin › Wizards › …), so a wizard added to a page is in the menu too. A menu item opens
// the page with ?wizard=<k>, and the page opens that wizard.

// Every model wizard in one place: choose the wizard, then the model it runs on (or none, to make or upload one).
// The same wizards are on each model's own Wizards tab, with the model already chosen.
export const MODEL_WIZARDS = [
  ["Start a model", [
    { k: "new", title: "New model", text: "Empty on a root metamodel or a library model, or a copy of a model with or without its data, with or without the parent-child link", none: true },
    { k: "upload", title: "Upload a model", text: "A package from here or another installation, placed where you choose", none: true },
  ]],
  ["Copy and derive", [
    { k: "child", title: "Copy with the parent-child link", text: "A child that merges back later; metamodel changes flow down to it", kinds: ["project"] },
    { k: "copy", title: "Copy without the link", text: "A separate copy, with or without the data" },
    { k: "library", title: "Copy from the library", text: "A new project model from a library (reference) or root model", kinds: ["reference", "template"] },
    { k: "split", title: "Split part of a model into a new one", text: "Chosen types or entities, copied or moved, as a child or separate", kinds: ["project"] },
  ]],
  ["Merge and propagate", [
    { k: "send", title: "Send for merge into the parent", text: "The child's changes, compared with its starting point, reviewed change by change by the parent's people; then freeze or refresh the child", kinds: ["project"] },
    { k: "requests", title: "Review merge requests", text: "Children sent for merge: accept or reject each change, then merge", kinds: ["project"] },
    { k: "down", title: "Propagate changes from the parent", text: "Choose what comes down from the parent into the child", kinds: ["project"] },
    { k: "to-child", title: "Propagate to a child", text: "Choose what goes down from a model into one of its children", kinds: ["project"] },
  ]],
  ["Data and quality", [
    { k: "quality", title: "Improve data quality", text: "Work through what data quality finds, one entity at a time: fill in, not applicable, still correct", kinds: ["project", "reference"] },
    { k: "load", title: "Load data into a model", text: "Download the sheet, fill it in, upload it and check the preview", kinds: ["project", "reference"] },
    { k: "collect", title: "Collect data from people", text: "Ask people to fill in entity types; what they upload comes back as commit requests", kinds: ["project"] },
    { k: "migration", title: "Plan the migration from gaps", text: "Group a gap analysis's gaps into work packages, with a roadmap sheet", kinds: ["project"] },
  ]],
  ["Metamodel", [
    { k: "extend", title: "Extend from another model", text: "Take entity types, relationship types and attributes another model has" },
    { k: "upgrade", title: "Upgrade to another framework", text: "Move a model onto another root metamodel (ArchiMate 5)", kinds: ["project"] },
  ]],
  ["Lifecycle", [
    { k: "lock", title: "Lock or unlock", text: "Temporary: the metamodel, the content, or everything, with a reason" },
    { k: "freeze", title: "Freeze or unfreeze", text: "Final: read only for good (a Super Admin unfreezes)", kinds: ["project"] },
    { k: "tag", title: "Tag a model now", text: "A named point in time to compare with or restore", kinds: ["project", "reference"] },
    { k: "restore", title: "Restore a tag", text: "Make a tag the latest again", kinds: ["project", "reference"] },
    { k: "archive", title: "Archive or reactivate", text: "Hidden from lists; nothing is lost" },
    { k: "delete", title: "Delete a model", text: "For good, after a package of it is saved" },
  ]],
  ["Library and publishing", [
    { k: "promote", title: "Promote to the library", text: "A copy becomes a library model (a draft until published)", kinds: ["project"] },
    { k: "request-publish", title: "Request publishing", text: "Ask for a draft to be published", drafts: true },
    { k: "publish", title: "Approve and publish", text: "Approve, send back or reject a draft", drafts: true },
    { k: "reopen", title: "Open a rejected draft again", text: "Work on it again and request publishing once more", drafts: true },
    { k: "withdraw", title: "Withdraw or restore in the library", text: "Nobody starts new models from it; those built on it keep working", kinds: ["reference", "template"] },
  ]],
  ["People and family", [
    { k: "hand", title: "Hand over a model", text: "Model Admins in and out, and the owner" },
    { k: "family", title: "Detach or reparent", text: "Break the parent-child link, or make it derive from another model", kinds: ["project"] },
  ]],
  ["Packages", [
    { k: "download", title: "Download a model", text: "One package, Excel or zip, with or without data or history" },
    { k: "spec", title: "Download a metamodel", text: "The metamodel as one JSON document" },
  ]],
];


// Project admin > Wizards (owner, 7 Nov 2026): every project admin workflow as a wizard. The one-time template library
// set-up first (projects need it), then a new project of each kind (the project templates) or blank, then the wizards
// that run on a project you choose.
export const PROJECT_WIZARDS = [
  { k: "edit", title: "✎ Edit a project", text: "The set-up wizard again on a running project: models, scope, goals and outcomes, sponsor, notes, libraries, views, steps, deliverables, people and sign-off", to: (id) => `#/projects/${id}/edit`, runs: true },
  { k: "finish", title: "Finish a project", text: "Freeze it, or merge it into another project; each of its models kept, merged into its parent, merged and frozen, or frozen", to: (id) => `#/project-admin/${id}?finish=1`, runs: true },
  { k: "derive", title: "Derive a new project", text: "A new project filled in from one you choose: scope, goals, steps, deliverables, views, libraries; its models referred to or derived from", to: (id) => `#/projects/new?parent=${id}` },
  { k: "library", title: "Make a project a library project", text: "Offer its reference material to every new project, or stop offering it (Super Admins)", to: (id) => `#/project-admin/${id}?library=1`, sup: true },
  { k: "as-template", title: "Save a project as a template", text: "Its decisions as a new kind of project in the gallery (Super Admins)", to: (id) => `#/project-admin/${id}?template=1`, sup: true },
  { k: "compliance", title: "Architecture compliance review", text: "Review a solution against the project's principles and standards: a verdict and note for each, the result and any dispensations in its governance log", to: (id) => `#/project-admin/${id}?compliance=1` },
  { k: "repo", title: "Build a project's repository now", text: "Make its folders and copy its templates in Documents again (missing ones only); see why it is not built", to: (id) => `#/project-admin/${id}`, runs: true },
];


// System admin › Wizards (SystemWizards.jsx): those opened in place; the others there are links to a tab
export const SYSTEM_WIZARDS = [
  { k: "give", title: "Give a person access", who: "users" },
  { k: "take", title: "Take a person's access away", who: "users" },
  { k: "backup", title: "Back up now", who: "ops" },
  { k: "restore", title: "Restore", who: "ops" },
  { k: "first-run", title: "First-run setup", who: "settings" },
];

// the wizard asked for in the address (?wizard=<k>), or ""
export function wizardAsked() {
  const m = /[?&]wizard=([a-z-]+)/.exec(window.location.hash || "");
  return m ? m[1] : "";
}
