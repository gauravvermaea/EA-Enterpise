// Model admin (D283, D285): every change to a model's shape, life or access, as wizards.
//   #/model-admin                         start a new model or upload one; pick a model (list, hierarchy, metamodel drafts)
//   #/model-admin/<model>[/wizards]       its wizards, grouped
//   #/model-admin/<model>/<tab>[/...]     metamodel, people, tags, merge, push down, change documents, backups, family
// Entering data and reports stay on the model page (#/metamodel/<model>, Architecture work), one link away.
import { useEffect, useMemo, useState } from "react";
import { apiDownload, apiFetch, can, canOn, needsRole } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { KindMark, liveModels, StatusMarks } from "./ModelMarks";
import { CopyButton, LockBadge } from "./Library";
import { LockBanner, LockControl, changeableModel } from "./MetamodelEditor";
import { ADMIN_VIEWS, ModelAdminPanel, ModelList } from "./Metamodel";
import {
  CopyBanner, DeleteDialog, DownloadDialog, DraftPage, Field, FrameworkMoveDialog, IconDialog, Modal, NewModelDialog, PromoteDialog,
  PublishStepDialog, TagNowDialog, UploadWizard, draftWhy, isTop, libraryAction, mayCreateFrom, ownsDraft,
} from "./ModelOps";
import { runTask } from "./tasks";
import { CollectWizard, LoadDataWizard, MigrationWizard, QualityWizard } from "./GuidedWizards";
import { fmtDateTime } from "./fmt";
import { MergeRequestsTab, SendForMergeWizard } from "./MergeBack";
import PageNav from "./PageNav";

const go = (path) => { window.location.hash = path; };
const post = (path, body) => apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });

export default function ModelAdmin({ route }) {
  const [, , model, tab, itemId, sub] = route.replace(/^#/, "").split("?")[0].split("/");
  if (!model || model === "wizards") return <WizardsHome />;
  if (model === "list") return <ModelList admin />;
  if (model === "hierarchy") return <ModelList view="hierarchy" admin />;
  if (model === "drafts") return tab ? <DraftPage id={tab} /> : <ModelList view="drafts" admin />;
  return <AdminModelPage key={model} model={model} tab={tab || "wizards"} itemId={itemId} sub={sub} />;
}

const TABS = [
  ["wizards", "Wizards", () => true],
  ["metamodel", "Metamodel", () => true],
  ["people", "People", (m) => changeableModel(m)],
  ["tags", "Tags", (m) => m.kind !== "template"],
  ["merge", "Merge", (m) => m.kind === "project"],
  ["merge-requests", "Merge requests", (m) => m.kind === "project"],
  ["send", "Send for merge", (m) => m.kind === "project" && !!m.parent_model_id && !m.frozen_at],
  ["pushdown", "Push down", (m) => m.kind === "project" || m.kind === "template"],
  ["documents", "Change documents", () => true],
  ["backups", "Backups", (m) => m.kind !== "template" && canOn(m.id, "model.metamodel")],
  ["family", "Family", () => true],
];

// Model admin's groups (D478)
const ADMIN_GROUPS = [
  ["wizards", "Wizards", "✦", ["wizards"]],
  ["changes", "Changes", "⇄", ["merge", "merge-requests", "send", "pushdown", "documents"]],
  ["admin", "Admin", "⚙", ["metamodel", "people", "tags", "backups", "family"]],
];

function AdminModelPage({ model, tab, itemId, sub }) {
  const { data: m, error } = useApi(`/api/v1/models/${model}`);
  const [icon, setIcon] = useState(false);
  if (error) return <section><p className="status bad">{error}</p><a href="#/model-admin">Model admin</a></section>;
  if (!m) return <section><p>Loading...</p></section>;
  const tabs = TABS.filter(([, , ok]) => ok(m));
  const t = tabs.some(([k]) => k === tab) ? tab : "wizards";
  return (
    <section className="model-page model-admin">
      <p className="quiet breadcrumb"><a href="#/model-admin">Model admin</a> / {m.name}</p>
      <div className="model-head">
        {canOn(model, "model.lock") || can("models.delete")
          ? <button className="linkish icon-edit" onClick={() => setIcon(true)} title="Change the model's icon"><KindMark m={m} big />
            <span className="icon-pencil" aria-hidden="true">✎</span></button>
          : <KindMark m={m} big />}
        {icon && <IconDialog m={m} onClose={() => setIcon(false)} />}
        <h1>{m.name} {m.version_label && <span className="quiet">{m.version_label}</span>}</h1>
        <StatusMarks m={m} />
        <LockBadge model={m} />
        {m.frozen_at ? <span className="rag off" title={m.frozen_note || ""}>❄ frozen {fmtDateTime(m.frozen_at)} by {m.frozen_by}</span>
          : <LockControl model={model} m={m} />}
        {m.is_locked && <CopyButton m={m} />}
        <a className="button" href={`#/metamodel/${model}`} title="The model's own page: data entry, grids, views, reports">✏ Open the model</a>
      </div>
      <p className="quiet">{m.kind_name} · {m.metamodel_name} · {m.entity_type_count} entity types
        {m.kind !== "template" && ` · ${m.entity_count} entities · ${m.relationship_count} relationships`}
        {m.parent_model_id && <> · merges into <a href={`#/model-admin/${m.parent_model_id}`}>{m.parent_model_name}</a></>}
        {m.source_model_id && m.source_model_id !== m.parent_model_id && <> · created from <a href={`#/model-admin/${m.source_model_id}`}>{m.source_model_name}</a></>}</p>
      {m.frozen_at && <div className="lock-banner">❄ Frozen{m.frozen_note ? `: ${m.frozen_note}` : ""}. Read only for good: it can still be copied,
        compared and reported on. Only a Super Admin unfreezes it.</div>}
      {!m.frozen_at && <LockBanner m={m} />}
      <CopyBanner m={m} />
      <PageNav page="admin" tabs={tabs.map(([k, l]) => [k, l, null])} groups={ADMIN_GROUPS} active={t} href={(k) => `#/model-admin/${model}/${k}`}
        ctx={{ id: model, m }} crumbs={[{ label: "Model admin", href: "#/model-admin" }, { label: m.name, href: `#/model-admin/${model}` }]}>
      <div className="tab-panel" role="tabpanel">
        {t === "wizards" ? <Wizards m={m} />
          : t === "family" ? <Family m={m} />
          : t === "merge-requests" ? <MergeRequestsTab m={m} />
          : t === "send" ? <SendForMergeTab m={m} />
          : ADMIN_VIEWS.includes(t) ? <ModelAdminPanel model={model} m={m} tab={t} itemId={itemId} sub={sub} /> : null}
      </div>
      </PageNav>
    </section>
  );
}

// Model admin > Changes > Send for merge: the wizard's own tab (owner, 10 Nov 2026, D542); also a tile on Wizards
function SendForMergeTab({ m }) {
  const [open, setOpen] = useState(false);
  const parent = { id: m.parent_model_id, name: m.parent_model_name };
  return (
    <div>
      <h3>Send {m.name} for merge into {m.parent_model_name}</h3>
      <p className="quiet">What changed in {m.name} since its starting point goes to {m.parent_model_name} as a merge request: its people review it change
        by change (a change only {m.name} made is accepted already; one both made differently is a conflict to decide), then merge it. Afterwards you
        freeze {m.name} or refresh it from its parent. Requests sent so far are on <a href={`#/model-admin/${m.id}/merge-requests`}>Merge requests</a>.</p>
      <button className="primary" onClick={() => setOpen(true)}>Preview and send…</button>
      {open && <SendForMergeWizard m={m} parent={parent} onClose={() => setOpen(false)} />}
    </div>
  );
}

// ---------------------------------------------------------------- Model admin > Wizards (the first tab, owner 7 Nov 2026)
// Every model wizard in one place: choose the wizard, then the model it runs on (or none, to make or upload one).
// The same wizards are on each model's own Wizards tab, with the model already chosen.
const ALL = [
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

export function AdminTabs({ on }) {
  return (
    <div className="tabs" role="tablist">
      {[["wizards", "Wizards", "/model-admin"], ["list", "Models", "/model-admin/list"], ["hierarchy", "Hierarchy", "/model-admin/hierarchy"],
        ["drafts", "Metamodel drafts", "/model-admin/drafts"]].map(([k, l, h]) => (
        <button key={k} role="tab" aria-selected={on === k} className={on === k ? "tab on" : "tab"} onClick={() => go(h)}>{l}</button>))}
    </div>
  );
}

function WizardsHome() {
  const [open, setOpen] = useState(null);
  const close = () => setOpen(null);
  const creator = can("models.create") || can("library.curate");
  return (
    <section>
      <h1>Model admin</h1>
      <p className="quiet">Every change to a model's shape, life or access is a wizard: choose one, then the model it runs on. Each wizard says
        what it will do before it does it; merging, splitting and extending run in the background. Entering data and reports are on the
        model's own page (<a href="#/work">Architecture work</a>).</p>
      <AdminTabs on="wizards" />
      <div className="wizards">
        {ALL.map(([g, cards]) => (
          <section key={g}>
            <h3>{g}</h3>
            <div className="wiz-grid">
              {cards.map((c) => <Card key={c.k} title={c.title} text={c.text} ok={!c.none || creator || c.k === "new"}
                why={needsRole(["model-creator", "library-admin"])} onClick={() => setOpen(c)} />)}
            </div>
          </section>
        ))}
      </div>
      {open?.k === "new" && <NewModelDialog admin onClose={close} />}
      {open?.k === "upload" && <UploadWizard onClose={close} />}
      {open && !open.none && <PickModel wizard={open} onClose={close} />}
    </section>
  );
}

// step 1 of a wizard started from Model admin > Wizards: the model it runs on
function PickModel({ wizard, onClose }) {
  const { data: models } = useApi(wizard.k === "archive" ? "/api/v1/models" : "/api/v1/models?archived=false");   // archived ones only to reactivate
  const [id, setId] = useState("");
  const [go2, setGo2] = useState(false);
  const { data: m } = useApi(go2 && id ? `/api/v1/models/${id}` : null);
  const fit = (models || []).filter((x) => (!wizard.kinds || wizard.kinds.includes(x.kind)) && (!wizard.drafts || x.is_draft));
  if (go2 && m) return <Wizards m={m} only={wizard.k} onDone={onClose} />;
  return (
    <Modal title={wizard.title} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!id || go2} onClick={() => setGo2(true)}>{go2 ? "Reading…" : "Next"}</button></>}>
      <ol className="wiz-steps"><li className="on">The model</li><li>The wizard's own steps</li></ol>
      <div className="ed-form">
        <p>{wizard.text}.</p>
        <Field label="Run it on">
          <select value={id} onChange={(e) => setId(e.target.value)} autoFocus>
            <option value="">Choose a model…</option>
            {fit.map((x) => <option key={x.id} value={x.id}>{x.name}{x.version_label ? ` ${x.version_label}` : ""} ({x.kind_name}{x.lifecycle === "archived" ? ", archived" : ""}{x.frozen_at ? ", frozen" : ""})</option>)}
          </select>
        </Field>
        {models && !fit.length && <p className="quiet">No model this wizard can run on.</p>}
        <p className="quiet small">If you may not run it on the model you choose, the next step says why.</p>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- the wizards, grouped
function Card({ title, text, ok, why, onClick, children }) {
  return (
    <div className={`wiz-card${ok ? "" : " off"}`}>
      <h4>{title}</h4>
      <p className="small">{text}</p>
      {children || (ok ? <button onClick={onClick}>Start…</button>
        : <p className="small menu-why" style={{ margin: 0 }}>{why}</p>)}
    </div>
  );
}

function Wizards({ m, only = null, onDone = null }) {
  const [open, setOpen] = useState(null);
  const [started, setStarted] = useState(false);
  const { data: fam } = useApi(`/api/v1/models/${m.id}/wizards/family`);
  const close = () => { setOpen(null); if (onDone) onDone(); };
  const admin = canOn(m.id, "model.lock");
  const superAdmin = can("models.delete");
  const curator = can("library.curate");
  const library = m.kind === "reference" || m.kind === "template";
  const project = m.kind === "project";
  const frozen = !!m.frozen_at;
  const locked = m.lock_level && m.lock_level !== "none";
  const adminWhy = needsRole("model-admin", m.name);
  const parent = fam?.parent;
  const kids = fam?.children || [];
  const fromWhy = m.is_draft && !ownsDraft(m) ? draftWhy(m) : needsRole(["model-creator", "library-admin"]) + (project ? ` (or Model Admin of ${m.name}, for a child)` : "");
  const notFrozen = frozen ? `${m.name} is frozen` : null;

  const groups = [
    ["Copy and derive", [
      { k: "child", title: "Copy with the parent-child link", text: `A child of ${m.name}: its work merges back, and the metamodel changes flow down to it`,
        ok: project && mayCreateFrom(m) && canOn(m.id, "model.derive"), why: !project ? "Only a project model has children" : fromWhy },
      { k: "copy", title: "Copy without the link", text: "A separate copy, with or without the data: never merges back, can still be compared",
        ok: mayCreateFrom(m), why: fromWhy },
      { k: "library", title: library ? "Start a model from this library model" : "Copy a model from the library",
        text: library ? `A new project model on ${m.name}, with its content or the metamodel only` : "Pick a library or root model and start a new project model from it",
        ok: library ? mayCreateFrom(m) : can("models.create") || curator, why: fromWhy },
      { k: "split", title: "Split part of it into a new model", text: "Chosen entity types or entities, with the relationships between them, copied or moved into a new model (a child or separate)",
        ok: project && !frozen && (admin || mayCreateFrom(m)), why: !project ? "Only a project model is split" : notFrozen || fromWhy },
    ]],
    ["Merge and propagate", [
      { k: "send", title: "Send for merge into the parent", text: `What changed since its starting point, reviewed change by change in ${parent ? parent.name : "the parent"}; then frozen or refreshed`,
        ok: !!parent && admin && !frozen, why: !parent ? `${m.name} has no parent model` : notFrozen || adminWhy },
      { k: "requests", title: "Merge requests", text: kids.length ? `Requests from ${kids.map((c) => c.name).join(", ")} to review, and ${m.name}'s own` : `${m.name}'s merge requests`,
        ok: project, why: "Only project models merge", go: `/model-admin/${m.id}/merge-requests` },
      { k: "down", title: "Propagate changes from the parent", text: `Choose what comes down from ${parent ? parent.name : "the parent"} into ${m.name}`,
        ok: !!parent && admin && !frozen && !locked, why: !parent ? `${m.name} has no parent model` : notFrozen || (locked ? `${m.name} is locked` : adminWhy) },
      { k: "to-child", title: "Propagate to a child", text: kids.length ? `Choose what goes down into ${kids.map((c) => c.name).join(", ")}` : "Choose what goes down into one of its children",
        ok: kids.length > 0 && kids.some((c) => canOn(c.id, "model.lock")), why: kids.length ? "Needs the Model Admin role on a child" : `${m.name} has no child models` },
    ]],
    ["Data and quality", [
      { k: "quality", title: "Improve data quality", text: "Work through what data quality finds, one entity at a time: fill in, not applicable, still correct",
        ok: m.kind !== "template" && canOn(m.id, "model.content") && !frozen, why: m.kind === "template" ? "A root metamodel holds no data" : notFrozen || needsRole(["architect", "committer", "model-sub-admin", "model-admin"], m.name) },
      { k: "load", title: "Load data", text: "Download the sheet, fill it in, upload it and check the preview: the rows become your changes",
        ok: m.kind !== "template" && canOn(m.id, "model.content") && !frozen, why: m.kind === "template" ? "A root metamodel holds no data" : notFrozen || needsRole(["architect", "committer", "model-sub-admin", "model-admin"], m.name) },
      { k: "collect", title: "Collect data from people", text: "Ask people to fill in entity types; what they upload comes back as commit requests you review",
        ok: project && admin && !frozen, why: !project ? "Only project models collect data" : notFrozen || adminWhy },
      { k: "migration", title: "Plan the migration from gaps", text: "Group the gaps of a gap analysis into work packages (Work Package entities) and a roadmap sheet",
        ok: project && admin && !frozen && !locked, why: !project ? "Gap analyses are kept in project models" : notFrozen || (locked ? `${m.name} is locked` : adminWhy) },
    ]],
    ["Metamodel", [
      { k: "extend", title: "Extend from another model", text: "Take entity types, relationship types and attributes another model's metamodel has (one new metamodel version)",
        ok: admin && !frozen && changeableModel(m), why: notFrozen || adminWhy },
      { k: "upgrade", title: "Upgrade to another framework", text: "Put the model on another root metamodel, for example when ArchiMate 5 comes; types are mapped first",
        ok: admin && project && !m.is_locked && !frozen, why: !project ? "Only project models move to another framework" : notFrozen || adminWhy },
    ]],
    ["Lifecycle", [
      { k: "lock", title: "Lock or unlock", text: "Temporary: the metamodel, the content, or everything for maintenance, with a reason everyone sees", custom: true },
      { k: "freeze", title: frozen ? "Unfreeze" : "Freeze", text: frozen ? "Make the frozen model open again (Super Admins)" : "Final: read only for good. It can still be copied, compared and reported on",
        ok: frozen ? superAdmin : admin && project, why: frozen ? needsRole(["super-admin"]) : !project ? "Root and library models are read only already" : adminWhy },
      { k: "tag", title: "Tag it now", text: "A frozen copy under a name (for example Baseline 2026) to compare with or restore. Every wizard that changes a model tags it first",
        ok: m.kind !== "template" && canOn(m.id, "model.content"), why: m.kind === "template" ? "A root metamodel has no content to tag" : needsRole(["architect", "committer", "model-sub-admin", "model-admin"], m.name) },
      { k: "restore", title: "Restore a tag", text: "Make a tag the latest again (its Tags tab)", ok: m.kind !== "template", why: "A root metamodel has no tags", go: `/model-admin/${m.id}/tags` },
      { k: "archive", title: m.lifecycle === "archived" ? "Reactivate" : "Archive", text: m.lifecycle === "archived" ? "Back in the lists" : "Hidden from lists; nothing is lost and it can be reactivated",
        ok: admin && !m.is_locked && !isTop(m), why: isTop(m) ? "Root always stays" : adminWhy },
      { k: "delete", title: "Delete", text: "For good, after a package of it is saved", ok: superAdmin && !isTop(m), why: isTop(m) ? "Root always stays" : needsRole(["super-admin"]) },
    ]],
    ["Library and publishing", [
      { k: "promote", title: "Promote to the library", text: "A copy becomes a library model, a draft until a Library Admin publishes it",
        ok: curator && project && !m.is_draft, why: !project ? "Only project models are promoted" : m.is_draft ? "Publish the model first" : needsRole(["library-admin"]) },
      { k: "request-publish", title: "Request publishing", text: "Ask for this draft to be published",
        ok: m.is_draft && ["editing", "returned"].includes(m.approval_state) && (admin || (library && curator)), why: !m.is_draft ? "Already published" : adminWhy },
      { k: "publish", title: "Approve and publish", text: "Approve the draft (or send it back, or reject it)",
        ok: m.is_draft && m.approval_state === "requested" && (library ? curator : admin), why: !m.is_draft ? "Already published" : "Publishing has not been requested yet" },
      { k: "reopen", title: "Open the rejected draft again", text: "Work on a rejected draft again and request publishing once more",
        ok: m.is_draft && m.approval_state === "rejected" && admin, why: m.approval_state !== "rejected" ? "Only a rejected draft is opened again" : adminWhy },
      { k: "withdraw", title: m.library_state === "withdrawn" ? "Restore to the library" : "Withdraw from the library",
        text: m.library_state === "withdrawn" ? "Back in the library for everyone" : "Nobody starts new models from it; those built on it keep working",
        ok: curator && library && !isTop(m) && ["published", "withdrawn"].includes(m.library_state), why: !library ? "Only library models" : needsRole(["library-admin"]) },
    ]],
    ["People and family", [
      { k: "hand", title: "Hand over", text: "New Model Admins in, old ones out (it keeps at least one), and the owner", ok: admin, why: adminWhy },
      { k: "family", title: "Detach or reparent", text: parent ? `Break the link to ${parent.name}, or make it derive from another model` : "Make it derive from a project model (it then merges back into it)",
        ok: admin && project, why: !project ? "Only project models have parents" : adminWhy },
    ]],
    ["Packages", [
      { k: "download", title: "Download", text: "One package, Excel or zip: without data, with data, or deep with its history", ok: true },
      { k: "spec", title: "Download the metamodel", text: "The metamodel as one JSON document, to give an AI assistant or upload as a metamodel draft", ok: true },
      { k: "upload", title: "Upload a model", text: "A package from here or another installation, placed where you choose", ok: can("models.create") || curator, why: needsRole(["model-creator", "library-admin"]) },
    ]],
  ];

  async function act(path) {
    try { await post(`/api/v1/models/${m.id}/${path}`, {}); refreshAll(); if (onDone) onDone(); }
    catch (e) { setOpen({ error: e.message }); }   // shown above the cards
  }
  function start(c) {
    if (c.go) { go(c.go); if (onDone) onDone(); return; }
    if (c.k === "spec") { apiDownload(`/api/v1/models/${m.id}/metamodel-spec`, `${m.name} metamodel.json`).then(() => onDone && onDone()).catch((e) => setOpen({ error: e.message })); return; }
    if (c.k === "archive") { act(m.lifecycle === "archived" ? "reactivate" : "archive"); return; }
    if (c.k === "withdraw") { libraryAction(m, m.library_state === "withdrawn" ? "restore" : "withdraw").then(() => onDone && onDone()).catch((e) => setOpen({ error: e.message })); return; }
    setOpen(c.k);
  }

  // started from Model admin > Wizards with a model chosen: run that one wizard (or say why it can't run on it)
  const card = only ? groups.flatMap(([, cs]) => cs).find((c) => c.k === only) : null;
  useEffect(() => {
    if (!card || started || !fam || card.custom || !card.ok) return;
    setStarted(true);
    start(card);
  });   // eslint-disable-line react-hooks/exhaustive-deps
  if (only) {
    if (!fam) return <Modal title="Reading the model…" onClose={onDone}><p>Loading…</p></Modal>;
    if (open?.error) return <Modal title={card?.title || "Wizard"} onClose={onDone} actions={<button onClick={onDone}>Close</button>}><p className="status bad">{open.error}</p></Modal>;
    if (card?.custom) {
      return (
        <Modal title={`Lock or unlock ${m.name}`} onClose={onDone} actions={<button onClick={onDone}>Close</button>}>
          <p>{card.text}</p>{frozen ? <p className="quiet">{m.name} is frozen: there is no lock to change.</p> : <LockControl model={m.id} m={m} />}
        </Modal>);
    }
    if (card && !card.ok) {
      return (
        <Modal title={card.title} onClose={onDone} actions={<button onClick={onDone}>Choose another model</button>}>
          <p>This wizard can't run on <b>{m.name}</b>: {card.why || "not allowed"}.</p>
        </Modal>);
    }
  }

  return (
    <div className={only ? "" : "wizards"}>
      {!only && <>
      <p className="quiet">Each wizard says what it will do before it does it. Merging, splitting and extending run in the background:
        the Tasks tab on the right shows them, and you are told when they are done.</p>
      {open?.error && <p className="status bad">{open.error}</p>}
      {groups.map(([g, cards]) => (
        <section key={g}>
          <h3>{g}</h3>
          <div className="wiz-grid">
            {cards.map((c) => (c.custom
              ? <Card key={c.k} title={c.title} text={c.text} ok>{frozen ? <p className="small quiet">Frozen: no lock to change</p> : <LockControl model={m.id} m={m} />}</Card>
              : <Card key={c.k} {...c} onClick={() => start(c)} />))}
          </div>
        </section>
      ))}
      </>}
      {open === "child" && <NewModelDialog from={m} preset={{ link: "child" }} admin onClose={close} />}
      {open === "copy" && <NewModelDialog from={m} preset={{ link: "independent" }} admin onClose={close} />}
      {open === "library" && <NewModelDialog from={library ? m : undefined} admin onClose={close} />}
      {open === "split" && <SplitWizard m={m} onClose={close} />}
      {open === "send" && parent && <SendForMergeWizard m={m} parent={parent} onClose={close} />}
      {open === "down" && parent && <MergeWizard target={m} source={parent} onClose={close} />}
      {open === "to-child" && <ChildPick m={m} kids={kids} onClose={close} />}
      {open === "extend" && <ExtendWizard m={m} onClose={close} />}
      {open === "upgrade" && <FrameworkMoveDialog m={m} onClose={close} />}
      {open === "freeze" && <FreezeDialog m={m} onClose={close} />}
      {open === "tag" && <TagNowDialog m={m} onClose={close} />}
      {open === "delete" && <DeleteDialog m={m} onClose={close} />}
      {open === "promote" && <PromoteDialog m={m} onClose={close} />}
      {open === "request-publish" && <PublishStepDialog m={m} step="request-publish" onClose={close} />}
      {open === "publish" && <PublishChoice m={m} onClose={close} />}
      {open === "reopen" && <PublishStepDialog m={m} step="reopen" onClose={close} />}
      {open === "hand" && <HandOverWizard m={m} onClose={close} />}
      {open === "family" && <ReparentWizard m={m} parent={parent} onClose={close} />}
      {open === "download" && <DownloadDialog m={m} onClose={close} />}
      {open === "upload" && <UploadWizard onClose={close} />}
      {open === "quality" && <QualityWizard m={m} onClose={close} />}
      {open === "load" && <LoadDataWizard m={m} onClose={close} />}
      {open === "collect" && <CollectWizard m={m} onClose={close} />}
      {open === "migration" && <MigrationWizard m={m} onClose={close} />}
    </div>
  );
}

function PublishChoice({ m, onClose }) {
  const [step, setStep] = useState(null);
  if (step) return <PublishStepDialog m={m} step={step} onClose={onClose} />;
  return (
    <Modal title={`Publishing ${m.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button onClick={() => setStep("send-back-publish")}>Send back…</button>
        <button className="danger" onClick={() => setStep("reject-publish")}>Reject…</button>
        <button className="primary" onClick={() => setStep("publish")}>Approve and publish…</button></>}>
      <p>Approve the draft and publish it, send it back with what to change, or reject it.</p>
    </Modal>
  );
}

function ChildPick({ m, kids, onClose }) {
  const ok = kids.filter((c) => canOn(c.id, "model.lock"));
  const [child, setChild] = useState(ok[0]?.id || "");
  const [go2, setGo2] = useState(false);
  if (go2) return <MergeWizard target={kids.find((c) => c.id === child)} source={m} onClose={onClose} />;
  return (
    <Modal title={`Propagate from ${m.name} to a child`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!child} onClick={() => setGo2(true)}>Next</button></>}>
      <div className="ed-form">
        <Field label="Into which child">
          <select value={child} onChange={(e) => setChild(e.target.value)}>
            {kids.map((c) => <option key={c.id} value={c.id} disabled={!canOn(c.id, "model.lock")}>{c.name}{canOn(c.id, "model.lock") ? "" : " (needs Model Admin on it)"}</option>)}
          </select>
        </Field>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- merge with what goes in (by type, then by item)
// Merge `source` into `target`: plan it (in the background), choose by type then by item, decide the conflicts,
// then merge (in the background: tagged first, the source frozen after when asked). D283.
const STEPS = ["What and how", "By type", "By item", "Conflicts", "Confirm"];

function MergeWizard({ target, source, freeze = false, onClose }) {
  const [step, setStep] = useState(0);
  const [tagFirst, setTagFirst] = useState(true);
  const [doFreeze, setDoFreeze] = useState(freeze);
  const [note, setNote] = useState(freeze ? `Merged into ${target.name}` : "");
  const [plan, setPlan] = useState(null);
  const [offTypes, setOffTypes] = useState(() => new Set());     // entity types left out
  const [offRelTypes, setOffRelTypes] = useState(() => new Set());
  const [offMeta, setOffMeta] = useState(() => new Set());       // metamodel parts left out
  const [offItems, setOffItems] = useState(() => new Set());     // entity keys left out
  const [offRels, setOffRels] = useState(() => new Set());       // r<n>
  const [winner, setWinner] = useState("theirs");
  const [decisions, setDecisions] = useState({});
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);

  // what changes the target: new entities, and those in both whose empty fields it fills ("same" ones change nothing)
  const withConflict = new Set((plan?.conflicts || []).map((c) => c.id.split("|")[0]));
  const ents = (plan?.entities || []).filter((e) => e.action === "create" || (e.fills || []).length || withConflict.has(e.key));
  const rels = plan?.relationships || [];
  const types = useMemo(() => {
    const c = {};
    ents.forEach((e) => { const t = c[e.entity_type] ||= { name: e.entity_type, create: 0, update: 0 }; t[e.action === "create" ? "create" : "update"] += 1; });
    return Object.values(c).sort((a, b) => a.name.localeCompare(b.name));
  }, [ents]);
  const relTypes = useMemo(() => [...new Set(rels.map((r) => r.type))].sort(), [rels]);
  const meta = useMemo(() => Object.entries(plan?.metamodel_gaps || {}).flatMap(([k, v]) => (Array.isArray(v) ? v : [])
    .filter((x) => x.code).map((x) => ({ section: k, code: x.code, name: x.name || x.code }))), [plan]);
  const inType = (e) => !offTypes.has(e.entity_type);
  const keptEnts = ents.filter((e) => inType(e) && !offItems.has(e.key));
  const keptKeys = new Set(keptEnts.map((e) => e.key));
  const leftKeys = new Set(ents.filter((e) => !keptKeys.has(e.key)).map((e) => e.key));
  const relOk = (r, n) => !offRelTypes.has(r.type) && !offRels.has(`r${n}`) && !leftKeys.has(r.source) && !leftKeys.has(r.target);
  const keptRels = rels.filter(relOk);
  const conflicts = (plan?.conflicts || []).filter((c) => keptKeys.has(c.id.split("|")[0]));
  const toggle = (set, setter, k) => setter(() => { const n = new Set(set); if (n.has(k)) n.delete(k); else n.add(k); return n; });

  async function makePlan() {
    setBusy(true); setError("");
    try {
      setPlan(await runTask(post(`/api/v1/models/${target.id}/merges`, { source_model: source.id, with_data: true }), `#/model-admin/${target.id}`));
      setStep(1);
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  async function merge() {
    setBusy(true); setError("");
    const exclude = { entity_types: [...offTypes], relationship_types: [...offRelTypes], entities: [...offItems], relationships: [...offRels], metamodel: [...offMeta] };
    try {
      const out = await runTask(post(`/api/v1/models/${target.id}/wizards/merge`, {
        merge: plan.id, source: source.id, decisions, all_conflicts: winner, exclude, tag_first: tagFirst,
        freeze_source: doFreeze, freeze_note: note, why: `merging ${source.name}`, label: `Merge ${source.name} into ${target.name}`,
      }), `#/model-admin/${target.id}`);
      setDone(out); refreshAll();
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  async function cancel() {
    if (plan && !done) await post(`/api/v1/models/${target.id}/merges/${plan.id}/cancel`).catch(() => {});
    onClose();
  }
  const freezeOk = canOn(source.id, "model.lock") && source.kind === "project";
  const actions = done ? <button className="primary" onClick={onClose}>Close</button> : (
    <>
      <button onClick={cancel}>Cancel</button>
      {step > 0 && <button disabled={busy} onClick={() => setStep(step - 1)}>Back</button>}
      {step === 0 && <button className="primary" disabled={busy} onClick={makePlan}>{busy ? "Reading both models…" : "Read and compare"}</button>}
      {step > 0 && step < 4 && <button className="primary" onClick={() => setStep(step + 1)}>Next</button>}
      {step === 4 && <button className="primary" disabled={busy || (!keptEnts.length && !keptRels.length && meta.length === offMeta.size)} onClick={merge}>
        {busy ? "Merging…" : doFreeze ? "Merge and freeze" : "Merge"}</button>}
    </>
  );
  return (
    <Modal wide title={`Merge ${source.name} into ${target.name}`} onClose={cancel} actions={actions}>
      <ol className="wiz-steps">{STEPS.map((s, i) => <li key={s} className={i === step ? "on" : i < step ? "done" : ""}>{s}</li>)}</ol>
      {done ? (
        <div>
          <p className="status ok">{done.note || "Merged."} {done.tag && <>Tagged first as <b>{done.tag.name}</b>. </>}{done.frozen && <>{source.name} is frozen.</>}</p>
          {done.commit && <p><a href={`#/metamodel/${target.id}/changes/history/${done.commit}`} onClick={onClose}>Open the commit</a> (to look at it, or roll it back)</p>}
        </div>
      ) : step === 0 ? (
        <div className="ed-form">
          <p>Both models are read and compared in the background. Nothing changes in {target.name} until the last step.</p>
          <label><input type="checkbox" checked={tagFirst} onChange={(e) => setTagFirst(e.target.checked)} /> Tag {target.name} first, so it can be restored</label>
          <label title={freezeOk ? "" : needsRole("model-admin", source.name)}>
            <input type="checkbox" checked={doFreeze} disabled={!freezeOk} onChange={(e) => setDoFreeze(e.target.checked)} /> Freeze {source.name} after merging (final: read only for good)</label>
          {doFreeze && <Field label="Why it is frozen (shown on it)"><input value={note} onChange={(e) => setNote(e.target.value)} /></Field>}
        </div>
      ) : step > 0 && step < 4 && !ents.length && !rels.length && !meta.length ? (
        <div><p className="status ok">Nothing to merge: {source.name} has nothing {target.name} lacks, and no value differs.</p></div>
      ) : step === 1 ? (
        <div>
          <p className="quiet">Untick a type to leave everything of it out. Relationships to entities left out are left out too.</p>
          <div className="wiz-cols">
            <div><h4>Entity types</h4>
              {!types.length && <p className="quiet small">No entities to add or fill.</p>}
              {types.map((t) => <label key={t.name} className="wiz-check"><input type="checkbox" checked={!offTypes.has(t.name)} onChange={() => toggle(offTypes, setOffTypes, t.name)} />
                {t.name} <span className="quiet small">{t.create} new{t.update ? ` · ${t.update} filled` : ""}</span></label>)}
            </div>
            <div><h4>Relationship types</h4>
              {!relTypes.length && <p className="quiet small">No new relationships.</p>}
              {relTypes.map((t) => <label key={t} className="wiz-check"><input type="checkbox" checked={!offRelTypes.has(t)} onChange={() => toggle(offRelTypes, setOffRelTypes, t)} />
                {t} <span className="quiet small">{rels.filter((r) => r.type === t).length}</span></label>)}
            </div>
            <div><h4>Metamodel parts {target.name} lacks</h4>
              {!meta.length && <p className="quiet small">None: the metamodels match.</p>}
              {meta.map((x) => <label key={`${x.section}:${x.code}`} className="wiz-check"><input type="checkbox" checked={!offMeta.has(String(x.code).toLowerCase())}
                onChange={() => toggle(offMeta, setOffMeta, String(x.code).toLowerCase())} />{x.name} <span className="quiet small">{x.section.replace(/_/g, " ")}</span></label>)}
            </div>
          </div>
        </div>
      ) : step === 2 ? (
        <div>
          <div className="toolbar"><input className="search" placeholder="Filter" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ maxWidth: 280 }} />
            <span className="quiet small">{keptEnts.length} entities and {keptRels.length} relationships go in</span></div>
          <div className="wiz-cols">
            <div className="wiz-scroll"><h4>Entities</h4>
              {ents.filter(inType).filter((e) => !filter || `${e.name} ${e.entity_type}`.toLowerCase().includes(filter.toLowerCase())).slice(0, 1000).map((e) => (
                <label key={e.key} className="wiz-check"><input type="checkbox" checked={!offItems.has(e.key)} onChange={() => toggle(offItems, setOffItems, e.key)} />
                  {e.name} <span className="quiet small">{e.entity_type} · {e.action === "create" ? "new" : (e.fills || []).length ? "fills empty fields" : "differs"}</span></label>))}
            </div>
            <div className="wiz-scroll"><h4>Relationships</h4>
              {rels.map((r, n) => [r, n]).filter(([r]) => !offRelTypes.has(r.type) && !leftKeys.has(r.source) && !leftKeys.has(r.target))
                .filter(([r]) => !filter || `${r.source_name} ${r.type} ${r.target_name}`.toLowerCase().includes(filter.toLowerCase())).slice(0, 1000).map(([r, n]) => (
                  <label key={n} className="wiz-check"><input type="checkbox" checked={!offRels.has(`r${n}`)} onChange={() => toggle(offRels, setOffRels, `r${n}`)} />
                    {r.source_name} <span className="quiet">{r.type}</span> {r.target_name}</label>))}
            </div>
          </div>
        </div>
      ) : step === 3 ? (
        <div>
          {!conflicts.length ? <p className="quiet">No conflicts in what goes in: nothing to decide.</p> : <>
            <div className="toolbar"><span>Where both have a different value, by default keep</span>
              <div className="seg small"><button className={winner === "theirs" ? "on" : ""} onClick={() => setWinner("theirs")}>{source.name}'s</button>
                <button className={winner === "mine" ? "on" : ""} onClick={() => setWinner("mine")}>{target.name}'s</button></div>
              <span className="quiet small">or decide one by one below</span></div>
            <div className="wiz-scroll"><table className="grid-table"><thead><tr><th>Entity</th><th>Field</th><th>{target.name}</th><th>{source.name}</th><th>Keep</th></tr></thead>
              <tbody>{conflicts.slice(0, 500).map((c) => {
                const d = decisions[c.id] || winner;
                return <tr key={c.id}><td>{c.entity} <span className="quiet small">{c.entity_type}</span></td><td>{c.field}</td>
                  <td className={d === "mine" ? "chosen" : ""}>{String(c.mine ?? "")}</td><td className={d === "theirs" ? "chosen" : ""}>{String(c.theirs ?? "")}</td>
                  <td className="small nowrap"><label><input type="radio" checked={d === "mine"} onChange={() => setDecisions((x) => ({ ...x, [c.id]: "mine" }))} /> {target.name}</label>{" "}
                    <label><input type="radio" checked={d === "theirs"} onChange={() => setDecisions((x) => ({ ...x, [c.id]: "theirs" }))} /> {source.name}</label></td></tr>;
              })}</tbody></table></div></>}
        </div>
      ) : (
        <div>
          <p>Into <b>{target.name}</b>, as one commit (it can be rolled back from its Changes tab):</p>
          <ul>
            <li>{keptEnts.filter((e) => e.action === "create").length} new entities, {keptEnts.filter((e) => e.action !== "create").length} with empty fields filled</li>
            <li>{keptRels.length} new relationships</li>
            <li>{meta.length - offMeta.size} metamodel parts added (a new metamodel version)</li>
            <li>{conflicts.length} conflicts: {Object.keys(decisions).length} decided one by one, the rest keep {winner === "theirs" ? source.name : target.name}'s value</li>
            {tagFirst && <li>{target.name} is tagged first</li>}
            {doFreeze && <li><b>{source.name} is frozen afterwards</b>: read only for good</li>}
          </ul>
        </div>
      )}
      {busy && <p className="quiet"><span className="spinner" aria-hidden="true" /> Working in the background: close this if you like; the Tasks tab says when it is done.</p>}
      {error && <p className="status bad">{error}</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- split
function SplitWizard({ m, onClose }) {
  const { data: list, error: le } = useApi(`/api/v1/models/${m.id}/entity-list?limit=5000`);
  const [step, setStep] = useState(0);
  const [name, setName] = useState(`${m.name} part`);
  const [description, setDescription] = useState("");
  const [child, setChild] = useState(true);
  const [move, setMove] = useState(false);
  const [on, setOn] = useState(() => new Set());
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);
  const ents = list || [];
  const types = useMemo(() => [...new Set(ents.map((e) => e.entity_type))], [ents]);
  const ofType = (t) => ents.filter((e) => e.entity_type === t);
  const typeState = (t) => { const k = ofType(t).filter((e) => on.has(String(e.id))).length; return k === 0 ? 0 : k === ofType(t).length ? 2 : 1; };
  const setType = (t, v) => setOn((s) => { const n = new Set(s); ofType(t).forEach((e) => (v ? n.add(String(e.id)) : n.delete(String(e.id)))); return n; });
  const flip = (id) => setOn((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const admin = canOn(m.id, "model.lock");
  async function run() {
    setBusy(true); setError("");
    try {
      const out = await runTask(post(`/api/v1/models/${m.id}/split`, { name: name.trim(), description, child, move, entities: [...on] }), `#/model-admin/${m.id}`);
      setDone(out); refreshAll();
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  return (
    <Modal wide title={`Split part of ${m.name} into a new model`} onClose={onClose}
      actions={done ? <><button onClick={onClose}>Close</button><button className="primary" onClick={() => { onClose(); go(`/model-admin/${done.model.id}`); }}>Open {done.model.name}</button></>
        : <><button onClick={onClose}>Cancel</button>{step > 0 && <button onClick={() => setStep(step - 1)}>Back</button>}
          {step < 2 ? <button className="primary" disabled={step === 1 && !on.size} onClick={() => setStep(step + 1)}>Next</button>
            : <button className="primary" disabled={busy || !name.trim() || !on.size} onClick={run}>{busy ? "Splitting…" : "Split"}</button>}</>}>
      <ol className="wiz-steps">{["The new model", "What goes in", "Confirm"].map((s, i) => <li key={s} className={i === step ? "on" : i < step ? "done" : ""}>{s}</li>)}</ol>
      {done ? <p className="status ok">{done.message}</p> : step === 0 ? (
        <div className="ed-form">
          <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
          <Field label="Description"><textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <label><input type="radio" checked={child} onChange={() => setChild(true)} /> <b>A child of {m.name}</b>: it merges back later</label>
          <label><input type="radio" checked={!child} onChange={() => setChild(false)} /> <b>A separate model</b> on the same metamodel</label>
          <label title={admin ? "" : needsRole("model-admin", m.name)}><input type="checkbox" checked={move} disabled={!admin} onChange={(e) => setMove(e.target.checked)} />
            {" "}<b>Move</b> them: take them out of {m.name} (one commit, which can be rolled back). Otherwise they are copied</label>
        </div>
      ) : step === 1 ? (
        <div>
          {le && <p className="status bad">{le}</p>}
          <div className="toolbar"><input className="search" placeholder="Filter entities" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ maxWidth: 280 }} />
            <span className="quiet small">{on.size} chosen. Tick a type for all of it, then add or take out single entities.</span></div>
          <div className="wiz-cols">
            <div className="wiz-scroll"><h4>By type</h4>
              {types.map((t) => { const st = typeState(t); return (
                <label key={t} className="wiz-check"><input type="checkbox" checked={st === 2} ref={(el) => { if (el) el.indeterminate = st === 1; }} onChange={() => setType(t, st !== 2)} />
                  {t} <span className="quiet small">{ofType(t).length}</span></label>); })}
            </div>
            <div className="wiz-scroll"><h4>By item</h4>
              {ents.filter((e) => !filter || `${e.name} ${e.entity_type}`.toLowerCase().includes(filter.toLowerCase())).slice(0, 1500).map((e) => (
                <label key={e.id} className="wiz-check"><input type="checkbox" checked={on.has(String(e.id))} onChange={() => flip(String(e.id))} />
                  {e.name} <span className="quiet small">{e.entity_type}</span></label>))}
            </div>
          </div>
        </div>
      ) : (
        <p>A new model <b>{name}</b>{child ? `, a child of ${m.name},` : ""} on {m.name}'s metamodel, with {on.size} entities and the relationships
          between them. {move ? <b>They are taken out of {m.name} (one commit).</b> : `${m.name} keeps them.`} It runs in the background.</p>
      )}
      {error && <p className="status bad">{error}</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- extend the metamodel from another model
function ExtendWizard({ m, onClose }) {
  const { data: models_ } = useApi("/api/v1/models?archived=false");
  const models = models_ && liveModels(models_);
  const [source, setSource] = useState("");
  const [prev, setPrev] = useState(null);
  const [pick, setPick] = useState({ entity_types: new Set(), relationship_types: new Set(), attributes: new Set() });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);
  async function look(s) {
    setSource(s); setPrev(null); setError("");
    if (!s) return;
    try { setPrev(await apiFetch(`/api/v1/models/${m.id}/extend-preview?source=${s}`)); } catch (e) { setError(e.message); }
  }
  const flip = (k, c) => setPick((p) => { const n = new Set(p[k]); if (n.has(c)) n.delete(c); else n.add(c); return { ...p, [k]: n }; });
  const count = pick.entity_types.size + pick.relationship_types.size + pick.attributes.size;
  async function run() {
    setBusy(true); setError("");
    try {
      setDone(await runTask(post(`/api/v1/models/${m.id}/extend`, { source, entity_types: [...pick.entity_types], relationship_types: [...pick.relationship_types],
        attributes: [...pick.attributes] }), `#/model-admin/${m.id}/metamodel`));
      refreshAll();
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  const SECTIONS = [["entity_types", "Entity types"], ["relationship_types", "Relationship types"], ["attributes", "Attributes"]];
  return (
    <Modal wide title={`Extend ${m.name}'s metamodel`} onClose={onClose}
      actions={done ? <button className="primary" onClick={onClose}>Close</button>
        : <><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !count} onClick={run}>{busy ? "Adding…" : `Add ${count || ""}`}</button></>}>
      {done ? <p className="status ok">{done.message}</p> : <>
        <div className="ed-form"><Field label="Take from the metamodel of">
          <select value={source} onChange={(e) => look(e.target.value)}>
            <option value="">Choose a model…</option>
            {(models || []).filter((x) => x.id !== m.id).map((x) => <option key={x.id} value={x.id}>{x.name}{x.version_label ? ` ${x.version_label}` : ""} ({x.kind_name})</option>)}
          </select></Field></div>
        <p className="quiet small">An entity type brings its attributes, domain and pick lists; the allowed relationships between types {m.name} then has come too. One new metamodel version.</p>
        {prev && <div className="wiz-cols">{SECTIONS.map(([k, l]) => (
          <div key={k} className="wiz-scroll"><h4>{l} <span className="quiet small">{prev[k].length}</span></h4>
            {!prev[k].length && <p className="quiet small">None that {m.name} lacks.</p>}
            {prev[k].map((x) => <label key={x.code} className="wiz-check"><input type="checkbox" checked={pick[k].has(x.code)} onChange={() => flip(k, x.code)} />
              {x.name} <span className="quiet small">{x.domain || x.data_type || ""}</span></label>)}
          </div>))}</div>}
      </>}
      {error && <p className="status bad">{error}</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- freeze, hand over, detach or reparent
function FreezeDialog({ m, onClose }) {
  const [note, setNote] = useState("");
  const [typed, setTyped] = useState("");
  const [tag, setTag] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const frozen = !!m.frozen_at;
  async function run() {
    setBusy(true); setError("");
    try {
      if (!frozen && tag) await post(`/api/v1/models/${m.id}/wizards/tag-first`, { why: "freezing" });
      await post(`/api/v1/models/${m.id}/${frozen ? "unfreeze" : "freeze"}`, { note });
      refreshAll(); onClose();
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`${frozen ? "Unfreeze" : "Freeze"} ${m.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className={frozen ? "primary" : "danger"} disabled={busy || (!frozen && typed !== m.name)} onClick={run}>
        {busy ? "Working…" : frozen ? "Unfreeze" : "Freeze for good"}</button></>}>
      <div className="ed-form">
        {frozen ? <p>{m.name} opens again for changes, as before it was frozen.</p> : <>
          <p>Freezing is <b>final</b>: nobody changes {m.name} again, its metamodel or its content (only a Super Admin unfreezes it).
            It can still be opened, copied, compared, tagged-from and reported on. To stop changes for a while, lock it instead.</p>
          <Field label="Why (shown on the model)"><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Baseline signed off" /></Field>
          <label><input type="checkbox" checked={tag} onChange={(e) => setTag(e.target.checked)} /> Tag it first</label>
          <Field label={`Type the model's name (${m.name}) to confirm`}><input value={typed} onChange={(e) => setTyped(e.target.value)} /></Field>
        </>}
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

function HandOverWizard({ m, onClose }) {
  const { data: people } = useApi(`/api/v1/models/${m.id}/people`);
  const admins = (people || []).filter((p) => (p.roles || [p.role]).includes("model-admin")).map((p) => p.username);
  const [add, setAdd] = useState("");
  const [remove, setRemove] = useState(() => new Set());
  const [owner, setOwner] = useState(m.owner || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  async function run() {
    setBusy(true); setError("");
    try {
      const out = await post(`/api/v1/models/${m.id}/hand-over`, { add: add.split(/[\s,;]+/).filter(Boolean), remove: [...remove], owner });
      setMsg(out.message); refreshAll();
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  return (
    <Modal title={`Hand over ${m.name}`} onClose={onClose}
      actions={msg ? <button className="primary" onClick={onClose}>Close</button>
        : <><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy} onClick={run}>{busy ? "Saving…" : "Hand over"}</button></>}>
      {msg ? <p className="status ok">{msg}</p> : <div className="ed-form">
        <Field label="Model Admins now" hint="(tick to take out)">
          <div>{admins.map((u) => <label key={u} className="wiz-check"><input type="checkbox" checked={remove.has(u)}
            onChange={() => setRemove((s) => { const n = new Set(s); if (n.has(u)) n.delete(u); else n.add(u); return n; })} /> {u}</label>)}
            {!admins.length && <span className="quiet">None listed</span>}</div>
        </Field>
        <Field label="New Model Admins" hint="(user names, separated by commas)"><input value={add} onChange={(e) => setAdd(e.target.value)} /></Field>
        <Field label="Owner" hint="(named on the model)"><input value={owner} onChange={(e) => setOwner(e.target.value)} /></Field>
        <p className="quiet small">A model keeps at least one Model Admin. Other roles stay on its People tab.</p>
        {error && <p className="status bad">{error}</p>}
      </div>}
    </Modal>
  );
}

function ReparentWizard({ m, parent, onClose }) {
  const { data: models_ } = useApi("/api/v1/models?kind=project&archived=false");
  const models = models_ && liveModels(models_);
  const [how, setHow] = useState(parent ? "detach" : "reparent");
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run() {
    setBusy(true); setError("");
    try {
      await post(`/api/v1/models/${m.id}/${how}`, how === "reparent" ? { parent: to } : {});
      refreshAll(); onClose();
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Detach or reparent ${m.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || (how === "reparent" && !to)} onClick={run}>{busy ? "Saving…" : "Save"}</button></>}>
      <div className="ed-form">
        {parent && <label><input type="radio" checked={how === "detach"} onChange={() => setHow("detach")} /> <b>Detach</b> from {parent.name}: a model of its own, never merges back</label>}
        <label><input type="radio" checked={how === "reparent"} onChange={() => setHow("reparent")} /> <b>Derive from</b>{" "}
          <select value={to} onChange={(e) => { setTo(e.target.value); setHow("reparent"); }}>
            <option value="">Choose a project model…</option>
            {(models || []).filter((x) => x.id !== m.id && x.id !== parent?.id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>: it then merges back into that model</label>
        <p className="quiet small">Merging back compares by type and name, so it works between any two models; the link says where it goes.</p>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- family
function Family({ m }) {
  const { data: f, error } = useApi(`/api/v1/models/${m.id}/wizards/family`);
  if (error) return <p className="status bad">{error}</p>;
  if (!f) return <p>Loading…</p>;
  return (
    <div className="family">
      <p>{f.source ? <>Built from <a href={`#/model-admin/${f.source.id}`}>{f.source.name}</a> {f.source.version_label || ""} ({f.source.kind}). </> : "Built from nothing above it. "}
        {f.parent ? <>Merges into <a href={`#/model-admin/${f.parent.id}`}><b>{f.parent.name}</b></a>.</> : "Has no parent model."}</p>
      <p>{f.children.length ? <>Children (they merge back into it): {f.children.map((c, i) => <span key={c.id}>{i > 0 && ", "}<a href={`#/model-admin/${c.id}`}>{c.name}</a></span>)}</> : "No child models."}</p>
      <p className="quiet">{f.frozen ? `Frozen ${fmtDateTime(f.frozen_at)} by ${f.frozen_by}.` : f.lock_level && f.lock_level !== "none" ? `Locked (${f.lock_level}).` : "Open."}</p>
      <p className="small"><a href={`#/metamodel/${m.id}/hierarchy`}>See it in the model tree</a></p>
    </div>
  );
}
