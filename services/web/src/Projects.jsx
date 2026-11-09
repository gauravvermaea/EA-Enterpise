// Architecture projects (phases 13 and 13.0.1, D258 to D279): #/projects (the list), #/projects/new (the wizard),
// #/projects/<id>/edit (the wizard on a live project, D275), #/projects/<id>/<tab> (a project: its landing page with the
// ADM crop circle, about, repository, steps, sign-off, principles).
// A project starts from its models (one is the project's model: its goals and outcomes are Goal and Outcome entities
// there, D274), then its purpose, scope, sponsor and asks, notes and files, template libraries, viewpoints, principles,
// the ADM steps and deliverables phase by phase (templates chosen from several libraries, or a placeholder to build
// later), its people and who signs off. Documents are edited outside in Office: check out, download, edit, check in.
// Deliverables are signed off (D276); a finished project is frozen, or merged into another (D277).
import PinButton from "./PinButton";
import { Fragment, useEffect, useMemo, useState } from "react";
import AdmWheel from "./AdmWheel";
import { apiDownload, apiFetch, apiUpload, partOn, roles } from "./auth";
import { fmtDate, fmtDateTime } from "./fmt";
import { refreshAll, useApi } from "./ModelViews";
import RichText from "./RichText";
import { Field, Modal } from "./ModelOps";
import { runTask, startDownload } from "./tasks";
import { modelOrigin, ORIGINS } from "./modelOrigin";
import { StakeholderMatrix, StakeholdersStep } from "./Stakeholders";
import { TasksTab } from "./ProjectTasks";
import { ContentFrameworkTab } from "./ContentFramework";
import { AreaChecks, AreaChips, AreaPicker, areaList, areaText } from "./CfAreaPicker";
import { CF_LABEL } from "./cfAreas";
import { RepositoryMap } from "./ArchitectureRepository";
import { ProjectOrgTab } from "./ProjectOrg";
import { BaseBanner, BaseTab, BasesTree, CharterTab, GovernanceTab, StandardsTab } from "./ProjectGovernance";
import { LinkDialog, LinkName, ReferenceStep, ReferenceTab } from "./References";
import { TemplateSetup } from "./TemplateSetup";
import { ProjectQuality } from "./Quality";
import { CalendarView } from "./Calendar";
import { TrackingSheets } from "./TrackingSheets";
import { ComplianceWizard } from "./GuidedWizards";
import { TemplateBrowserDialog } from "./TemplateBrowser";
import { ProjectBackupPanel, ProjectCompare, ProjectGaps, ProjectReports, RestoreProjectFile, ViewpointsByPhase } from "./ProjectTabs";

const ROLE_NAMES = { "project-admin": "Project Admin", "lead-architect": "Lead Architect", architect: "Architect",
  "model-admin": "Model Admin", "model-sub-admin": "Model Sub Admin", stakeholder: "Stakeholder" };
const REPO = { pending: ["amber", "waiting for Documents"], building: ["amber", "being built"], ready: ["green", "ready"], failed: ["red", "not built yet"] };
const STATUS = { active: ["green", "active"], finishing: ["amber", "finishing"], frozen: ["off", "frozen, read only"], merged: ["off", "merged, read only"], closed: ["off", "closed"] };
const PURPOSE_HELP = {
  strategy: "Enterprise-wide direction over several years (TOGAF strategic architecture)",
  portfolio: "A set of initiatives or a segment of the enterprise (segment architecture)",
  project: "One change initiative (capability architecture)",
  solution: "One solution's architecture, within the enterprise architecture",
};
const DEPTHS = [["strategic", "Strategic", "the whole enterprise, long term, summary detail"],
  ["segment", "Segment", "a business unit or portfolio, more detail"], ["capability", "Capability", "one capability or change, full detail"]];
const DOMAINS = [["business", "Business"], ["data", "Data"], ["application", "Application"], ["technology", "Technology"]];
function OriginChip({ m }) {
  const o = modelOrigin(m);
  return o.key ? <span className={`chip origin-${o.key}`} title={o.text}>{o.label}</span> : null;
}
const HOW = { referred: "Referred to (read only)", added: "Added (worked on)", derived: "Derived (a child)", created: "Created (new)" };
const subPhases = (code) => (code === "C" ? ["C", "C-D", "C-A"] : [code]);

// ---------------------------------------------------------------- Project admin (D285): #/project-admin[/library|/<id>]
// New project, edit, finish, save as a template, rebuild the repository: wizards; the project's own page is architecture work
export function ProjectAdmin({ route }) {
  const parts = route.replace(/^#\/project-admin\/?/, "").split("?")[0].split("/").filter(Boolean);
  const tab = parts[0] === "library" ? "library" : parts[0] === "templates" ? "templates" : parts[0] === "libprojects" ? "libprojects"
    : parts[0] === "list" ? "projects" : parts[0] === "bases" ? "bases" : parts[0] === "template-setup" ? "tsetup" : parts[0] === "principles" ? "principles" : parts[0] ? "one" : "wizards";
  return (
    <div className="page">
      <h1>Project admin</h1>
      {tab !== "one" && <div className="tabs" role="tablist">
        <a href="#/project-admin" className={`tab${tab === "wizards" ? " on" : ""}`}>Wizards</a>
        <a href="#/project-admin/list" className={`tab${tab === "projects" ? " on" : ""}`}>Projects</a>
        <a href="#/project-admin/bases" className={`tab${tab === "bases" ? " on" : ""}`}>Project bases</a>
        <a href="#/project-admin/libprojects" className={`tab${tab === "libprojects" ? " on" : ""}`}>Project library</a>
        <a href="#/project-admin/templates" className={`tab${tab === "templates" ? " on" : ""}`}>Project templates</a>
        <a href="#/project-admin/library" className={`tab${tab === "library" ? " on" : ""}`}>Project content template library</a>
        <a href="#/project-admin/template-setup" className={`tab${tab === "tsetup" ? " on" : ""}`}>Template setup</a>
        <a href="#/project-admin/principles" className={`tab${tab === "principles" ? " on" : ""}`}>Principles</a>
      </div>}
      <div className="tab-panel">
        {tab === "wizards" && <ProjectWizards />}
        {tab === "projects" && <AdminProjects />}
        {tab === "library" && <ProjectLibraryAdmin />}
        {tab === "templates" && <TemplatesTab />}
        {tab === "libprojects" && <LibraryProjects />}
        {tab === "bases" && <BasesTree />}
        {tab === "tsetup" && <TemplateSetup />}
        {tab === "principles" && <OrgPrinciples />}
        {tab === "one" && <AdminProject id={parts[0]} />}
      </div>
    </div>
  );
}

// Project admin > Wizards (owner, 7 Nov 2026): every project admin workflow as a wizard. The one-time template library
// set-up first (projects need it), then a new project of each kind (the project templates) or blank, then the wizards
// that run on a project you choose.
const PROJECT_WIZARDS = [
  { k: "edit", title: "✎ Edit a project", text: "The set-up wizard again on a running project: models, scope, goals and outcomes, sponsor, notes, libraries, viewpoints, steps, deliverables, people and sign-off", to: (id) => `#/projects/${id}/edit`, runs: true },
  { k: "finish", title: "Finish a project", text: "Freeze it, or merge it into another project; each of its models kept, merged into its parent, merged and frozen, or frozen", to: (id) => `#/project-admin/${id}?finish=1`, runs: true },
  { k: "derive", title: "Derive a new project", text: "A new project filled in from one you choose: scope, goals, steps, deliverables, viewpoints, libraries; its models referred to or derived from", to: (id) => `#/projects/new?parent=${id}` },
  { k: "library", title: "Make a project a library project", text: "Offer its reference material to every new project, or stop offering it (Super Admins)", to: (id) => `#/project-admin/${id}?library=1`, sup: true },
  { k: "as-template", title: "Save a project as a template", text: "Its decisions as a new kind of project in the gallery (Super Admins)", to: (id) => `#/project-admin/${id}?template=1`, sup: true },
  { k: "compliance", title: "Architecture compliance review", text: "Review a solution against the project's principles and standards: a verdict and note for each, the result and any dispensations in its governance log", to: (id) => `#/project-admin/${id}?compliance=1` },
  { k: "repo", title: "Build a project's repository now", text: "Make its folders and copy its templates in Documents again (missing ones only); see why it is not built", to: (id) => `#/project-admin/${id}`, runs: true },
];

// the organisation-wide architecture charter (owner, 8 Nov 2026, D319): in the Organisation base, filled in from the seed,
// a draft until a Super Admin approves it; each project keeps its own charter page, started from it
// Project admin › Principles (D327): the organisation's principles, kept in the Organisation base by Super Admins
function OrgPrinciples() {
  const { data: sum } = useApi("/api/v1/repository/summary");
  const { data: p, error } = useApi(sum?.org_base ? `/api/v1/projects/${sum.org_base.id}` : null);
  if (error) return <p className="status bad">{error}</p>;
  if (!p) return <p className="quiet">Loading...</p>;
  return (
    <div>
      <p className="small">Kept in the <a href={`#/projects/${p.id}/principles`}>Organisation base</a>; Super Admins change them.</p>
      <PrinciplesTab p={p} />
    </div>
  );
}

function OrgCharterCard() {
  const { data } = useApi("/api/v1/repository/summary");
  if (!data?.org_base) return null;
  const ch = data.charter || {};
  const approved = ch.state === "Approved";
  return (
    <div className={`wiz-card${approved ? "" : " wiz-next"}`}>
      <h4>The organisation's architecture charter</h4>
      <p className="small">One charter for the whole organisation, kept in the Organisation base by Super Admins: purpose, scope, mandate, the
        Architecture Board, principles, roles, method, compliance. Every new project's charter starts from it.</p>
      <p className="small">{approved ? <>✓ Approved by {ch.approved_by}</> : <>{ch.state || "Draft"}: filled in with a starting text to review and approve</>}</p>
      <a className={`button${approved || !data.may_change ? "" : " primary"}`} href={`#/projects/${data.org_base.id}/charter`}>
        {data.may_change ? (approved ? "Open…" : "Review and approve…") : "Read…"}</a>
    </div>
  );
}

function ProjectWizards() {
  const { data: lib, error } = useApi("/api/v1/projects/library");
  const { data: list } = useApi("/api/v1/projects");
  const [pick, setPick] = useState(null);
  const [restoreFile, setRestoreFile] = useState(false);
  if (error) return <p className="status bad">{error}</p>;
  if (!lib) return <p className="quiet">Loading...</p>;
  const done = lib.setup.done;
  const mayCreate = list?.may_create;
  const why = !done ? "No template library is offered to projects: a Super Admin offers one (Project library)" : "Needs a global role (any); ask a User Admin";
  return (
    <div className="wizards">
      {restoreFile && <RestoreProjectFile onClose={() => setRestoreFile(false)} />}
      <p className="quiet">Setting up, changing and finishing projects are wizards. Working in a project (its phases, deliverables, sign-off) is on the
        project's own page in <a href="#/work">Architecture work</a>. A new project's first step is its models: pick existing ones or make new ones with
        the model wizards (Model admin › Wizards).</p>
      <section>
        <h3>1. Optional, before the first project</h3>
        <div className="wiz-grid">
          <div className={`wiz-card${done ? "" : " wiz-next"}`}>
            <h4>Template libraries (optional)</h4>
            <p className="small">Projects start with EA Explorer's own templates. A Super Admin may add TOGAF 10 (The Open Group's, your licensed
              zip) or your organisation's own, and offer them to projects.</p>
            {done ? <a className="button" href="#/project-admin/library">Open…</a>
              : lib.may_manage ? <a className="button primary" href="#/project-admin/library">Start…</a>
              : <p className="small menu-why" style={{ margin: 0 }}>Ask a Super Admin to do it</p>}
          </div>
          <OrgCharterCard />
          <div className="wiz-card">
            <h4>A new model for projects</h4>
            <p className="small">A project works on models: make the current-state and target-state models first if you like, or make them inside the project wizard.</p>
            <a className="button" href="#/model-admin">Model wizards…</a>
          </div>
        </div>
      </section>
      <section>
        <h3>2. A new project</h3>
        <div className="wiz-grid">
          <div className={`wiz-card${mayCreate ? "" : " off"}`}>
            <h4>Restore a project from a backup file</h4><p className="small">A project backup (from a project's About tab, here or on another
              installation) becomes a new project, with its models and documents.</p>
            {mayCreate ? <button onClick={() => setRestoreFile(true)}>Start…</button> : <p className="small menu-why" style={{ margin: 0 }}>{why}</p>}
          </div>
          <div className={`wiz-card${done && mayCreate ? "" : " off"}`}>
            <h4>＋ Blank project</h4><p className="small">The full wizard, every decision yours.</p>
            {done && mayCreate ? <a className="button" href="#/projects/new?template=blank">Start…</a> : <p className="small menu-why" style={{ margin: 0 }}>{why}</p>}
          </div>
          {lib.project_templates.map((t) => (
            <div key={t.code} className={`wiz-card${done && mayCreate ? "" : " off"}`}>
              <h4>{t.icon} {t.name}</h4>
              <p className="small">{t.description}</p>
              <p className="small quiet">{(t.spec.slots || []).map((x) => x.label).join(" · ")}</p>
              {done && mayCreate ? <a className="button" href={`#/projects/new?template=${t.code}`}>Start…</a> : <p className="small menu-why" style={{ margin: 0 }}>{why}</p>}
            </div>
          ))}
        </div>
      </section>
      <section>
        <h3>3. On a project</h3>
        <div className="wiz-grid">
          {PROJECT_WIZARDS.map((w) => (
            <div key={w.k} className="wiz-card"><h4>{w.title}</h4><p className="small">{w.text}</p><button onClick={() => setPick(w)}>Start…</button></div>))}
        </div>
      </section>
      {pick && <PickProject w={pick} projects={list?.projects || []} onClose={() => setPick(null)} />}
    </div>
  );
}

function PickProject({ w, projects, onClose }) {
  const [id, setId] = useState("");
  const runs = (p) => !(p.my_roles || []).length || (p.my_roles || []).some((r) => r === "project-admin" || r === "lead-architect");
  const fit = projects.filter((p) => (!w.runs || runs(p)) && (w.k !== "edit" || !["frozen", "merged", "closed"].includes(p.status))
    && (w.k !== "finish" || p.status === "active"));
  return (
    <Modal title={w.title} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!id} onClick={() => { window.location.hash = w.to(id).slice(1); onClose(); }}>Next</button></>}>
      <ol className="wiz-steps"><li className="on">The project</li><li>The wizard's own steps</li></ol>
      <div className="ed-form">
        <p>{w.text}.</p>
        <Field label="Run it on">
          <select value={id} onChange={(e) => setId(e.target.value)} autoFocus>
            <option value="">Choose a project…</option>
            {fit.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.status})</option>)}
          </select>
        </Field>
        {!fit.length && <p className="quiet">No project this wizard can run on{w.runs ? " (it needs the Project Admin or Lead Architect role on it)" : ""}.</p>}
      </div>
    </Modal>
  );
}

// while a project's repository is still being built, the list looks again every 15 seconds (owner, 8 Nov 2026)
function useWhileBuilding(projects) {
  const building = (projects || []).some((p) => p.repo_state === "pending" || p.repo_state === "building");
  useEffect(() => {
    if (!building) return undefined;
    const t = setInterval(refreshAll, 15000);
    return () => clearInterval(t);
  }, [building]);
}

function AdminProjects() {
  const { data, error } = useApi("/api/v1/projects");
  useWhileBuilding(data?.projects);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const runs = (p) => !(p.my_roles || []).length || (p.my_roles || []).some((r) => r === "project-admin" || r === "lead-architect");
  const mine = data.projects.filter(runs);
  return (
    <div>
      <div className="row-gap">
        {data.may_create && data.setup?.done ? <a className="button primary" href="#/projects/new">+ New project</a>
          : <button className="primary" disabled title={!data.setup?.done ? "No template library is offered to projects (Project library)" : "Needs a global role"}>+ New project</button>}
        <span className="quiet small">Choose a kind of project (a template with the decisions taken) or a blank one; every decision stays editable.</span>
      </div>
      {!data.setup?.done && <SetupNeeded manage={data.may_manage} />}
      <h3>Projects you run</h3>
      {!mine.length && <p className="quiet">None: you are Project Admin or Lead Architect on no project.</p>}
      {mine.length > 0 && <table className="grid-table">
        <thead><tr><th>Project</th><th>Purpose</th><th>Status</th><th>Your roles</th><th className="num">Models</th><th className="num">Documents</th><th>Complete</th><th>Repository</th></tr></thead>
        <tbody>{mine.map((p) => (
          <tr key={p.id}><td><a href={`#/project-admin/${p.id}`}><b>{p.name}</b></a></td><td>{p.purpose}</td><td><StatusChip status={p.status} /></td>
            <td className="small">{(p.my_roles || []).map((r) => ROLE_NAMES[r] || r).join(", ") || <span className="quiet">Super Admin</span>}</td>
            <td className="num">{p.models}</td><td className="num">{p.documents}</td><td><Completion c={p.completion} /></td><td><RepoState state={p.repo_state} /></td></tr>))}</tbody>
      </table>}
    </div>
  );
}

function AdminCard({ title, text, ok, why, href, onClick }) {
  return (
    <div className={`wiz-card${ok ? "" : " off"}`}>
      <h4>{title}</h4><p className="small">{text}</p>
      {!ok ? <p className="small menu-why" style={{ margin: 0 }}>{why}</p> : href ? <a className="button" href={href}>Start…</a> : <button onClick={onClick}>Start…</button>}
    </div>
  );
}

function AdminProject({ id }) {
  const { data: p, error } = useApi(`/api/v1/projects/${id}`);
  const [msg, setMsg] = useState("");
  const qs = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const [finish, setFinish] = useState(qs.get("finish") === "1");
  const [libDlg, setLibDlg] = useState(qs.get("library") === "1");
  const [review, setReview] = useState(qs.get("compliance") === "1");
  const [asked, setAsked] = useState(false);
  useEffect(() => {      // ?template=1: asked once, after the page is shown
    if (p && !asked && qs.get("template") === "1" && p.my_roles.includes("super-admin")) { setAsked(true); setTimeout(asTemplate, 0); }
  }, [p, asked]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <p className="status bad">{error}</p>;
  if (!p) return <p className="quiet">Loading...</p>;
  const sup = p.my_roles.includes("super-admin");
  const runs = p.may_admin || sup;
  const why = "Needs the Project Admin or Lead Architect role on this project";
  const frozen = p.frozen ? "The project is finished: read only" : null;
  async function rebuild() {
    try { const r = await apiFetch(`/api/v1/projects/${id}/repository`, { method: "POST" }); setMsg(r.message); setTimeout(refreshAll, 4000); }
    catch (e) { setMsg(e.message); }
  }
  async function asTemplate() {
    // eslint-disable-next-line no-alert
    const name = window.prompt("Save this project's decisions as a project template named", `${p.name} (template)`);
    if (!name) return;
    try { const t = await apiFetch(`/api/v1/projects/${p.id}/as-template`, { method: "POST", body: JSON.stringify({ name }) }); setMsg(`Saved as the project template ${t.name}.`); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <div>
      <p className="quiet breadcrumb"><a href="#/project-admin">Project admin</a> / {p.name}</p>
      <div className="row-gap project-head">
        <h2 style={{ margin: 0 }}>{p.name}</h2><span className="chip on">{p.purpose}</span><StatusChip status={p.status} />
        <span className="small">Repository: <RepoState state={p.repo_state} note={p.repo_note} /></span>
        <a className="button" style={{ marginLeft: "auto" }} href={`#/projects/${id}`}>✏ Open the project</a>
      </div>
      {p.frozen && <div className="lock-banner">{p.status === "merged" ? <>Merged into <a href={`#/project-admin/${p.merged_into?.id}`}>{p.merged_into?.name}</a></> : "Frozen"}
        {" "}on {fmtDateTime(p.finished_at)} by {p.finished_by}: read only. {p.finish_note}</div>}
      <RepoHelp p={p} onRebuild={runs && !p.frozen ? rebuild : null} />
      <div className="wiz-grid">
        <AdminCard title="✎ Edit the project" text="The set-up wizard again on the project as it is: models, scope, goals and outcomes, sponsor, notes, libraries, viewpoints, steps, deliverables, people and sign-off"
          ok={runs && !p.frozen} why={frozen || why} href={`#/projects/${id}/edit`} />
        <AdminCard title="Finish the project" text="Freeze it, or merge it into another project; each of its models kept or merged into its parent"
          ok={p.may_finish} why={frozen || why} onClick={() => setFinish(true)} />
        <AdminCard title="Derive a new project" text="A new project filled in from this one: scope, goals, steps, deliverables, viewpoints and libraries; its models to refer to or derive from"
          ok href={`#/projects/new?parent=${id}`} />
        <AdminCard title="Save as a project template" text="Its decisions as a new kind of project in the gallery (Super Admins)" ok={sup} why="Needs the Super Admin role" onClick={asTemplate} />
        <AdminCard title={p.is_library ? "No longer a library project" : "Make it a library project"}
          text={p.is_library ? "Stop offering its reference material to new projects (the material stays in the project)"
            : "Offer its reference material (reference models, regulations, patterns, standards, links) to every new project"}
          ok={sup} why="Needs the Super Admin role" onClick={() => setLibDlg(true)} />
        <AdminCard title="Architecture compliance review" text="Review a solution against the project's principles and standards; the result and any dispensations go into its governance log"
          ok={p.may_contribute && !p.frozen} why={frozen || "Needs a contributing role on this project"} onClick={() => setReview(true)} />
        <AdminCard title="Build the repository now" text="Make the folders and copy the templates in Documents again (missing ones only; documents stay)"
          ok={runs && p.repo_state !== "ready" && !p.frozen} why={p.repo_state === "ready" ? "The repository is ready" : frozen || why} onClick={rebuild} />
      </div>
      {msg && <p className="small quiet">{msg}</p>}
      {finish && <FinishDialog p={p} onClose={() => setFinish(false)} />}
      {libDlg && sup && <LibraryProjectDialog project={p} onClose={() => setLibDlg(false)} onDone={setMsg} />}
      {review && <ComplianceWizard p={p} onClose={() => setReview(false)} />}
    </div>
  );
}

// Making a project a library project, or no longer one (owner, 8 Nov 2026: an action, not a tick box). Super Admins.
// project: the project (from its page), or none: choose one of `projects` first.
function LibraryProjectDialog({ project, projects = [], onClose, onDone }) {
  const [pick, setPick] = useState(project?.id || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const p = project || projects.find((x) => x.id === pick);
  const on = !p?.is_library;
  async function run() {
    setBusy(true); setErr("");
    try {
      const r = await apiFetch(`/api/v1/projects/${p.id}/library`, { method: "POST", body: JSON.stringify({ on }) });
      onDone?.(r.message); refreshAll(); onClose();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  return (
    <Modal title={p && !on ? `${p.name}: no longer a library project` : "Make a project a library project"} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={!p || busy} onClick={run}>{busy ? "Working..." : on ? "Make it a library project" : "No longer a library project"}</button></>}>
      <div className="ed-form">
        {!project && <Field label="Project"><select value={pick} onChange={(e) => setPick(e.target.value)} autoFocus>
          <option value="">Choose a project…</option>
          {projects.filter((x) => !x.is_library).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>}
        {p && (on ? <>
          <p>A library project keeps reference material for every project: reference models, regulations, patterns, standards and useful links.</p>
          <ul className="small">
            <li>Its Reference area is offered to every new project (New project › Reference), to copy from.</li>
            <li>It shows under Library projects in Project admin, and in the project hierarchy as a library project new projects may derive from.</li>
            <li>The project itself does not change: its documents, models and people stay as they are.</li>
          </ul>
          {p.reference_items !== undefined && <p className="small quiet">It has {p.reference_items} reference item{p.reference_items === 1 ? "" : "s"} now.</p>}
        </> : <>
          <p>Its reference material is no longer offered to new projects. The material stays in the project, and projects that copied from it keep their copies.</p>
        </>)}
        <DialogError e={err} />
      </div>
    </Modal>
  );
}

export default function Projects({ route }) {
  const parts = route.replace(/^#\/projects\/?/, "").split("/").filter(Boolean);
  const qs = new URLSearchParams(route.split("?")[1] || "");
  if (parts[0] === "new" || parts[0]?.startsWith("new?")) {
    if (!qs.get("template") && !qs.get("parent")) return <Gallery />;      // D282: the project templates first
    return <Wizard key={`new-${qs.get("parent") || ""}-${qs.get("template") || ""}`} parent={qs.get("parent")} template={qs.get("template") === "blank" ? "" : qs.get("template")} />;
  }
  if (parts[0] && (parts[1] || "").split("?")[0] === "edit") return <Wizard key={`edit-${parts[0]}`} editId={parts[0]} startAt={qs.get("step")} />;
  if (parts[0]) return <ProjectPage key={parts[0].split("?")[0]} id={parts[0].split("?")[0]} tab={(parts[1] || "home").split("?")[0]} />;
  window.location.replace("#/work");   // the list of projects is on Architecture work (D285)
  return null;
}

// ---------------------------------------------------------------- the project templates (D282): choose one, or a blank project
const ROLE_NAMES_M = { current: "Current state", target: "Target state", transition: "Transition state", scenario: "Scenario",
  reference: "Reference", "working-copy": "Working copy" };

function Gallery() {
  const { data: lib, error } = useApi("/api/v1/projects/library");
  if (error) return <div className="page"><p className="status bad">{error}</p></div>;
  if (!lib) return <div className="page"><p className="quiet">Loading...</p></div>;
  if (!lib.setup.done) return <div className="page"><h2>New architecture project</h2><SetupNeeded manage={lib.may_manage} /></div>;
  return (
    <div className="page">
      <div className="small"><a href="#/project-admin">Project admin</a> ›</div>
      <h2>New architecture project</h2>
      <p className="quiet">Choose the kind of project: its wizard comes with the decisions already taken (the models and their roles, the
        purpose and scope, the phases, deliverables and viewpoints) and asks only the rest. Everything can still be changed, here or later with ✎ Edit.</p>
      <div className="template-grid">
        {lib.project_templates.map((t) => (
          <a key={t.code} className="template-card" href={`#/projects/new?template=${t.code}`}>
            <span className="template-icon" aria-hidden="true">{t.icon}</span>
            <b>{t.name}</b>
            <span className="small">{t.description}</span>
            <span className="small quiet">{(t.spec.slots || []).map((x) => x.label).join(" · ")}</span>
          </a>
        ))}
        <a className="template-card blank" href="#/projects/new?template=blank">
          <span className="template-icon" aria-hidden="true">＋</span><b>Blank project</b>
          <span className="small">The full wizard, every decision yours.</span>
        </a>
      </div>
    </div>
  );
}

// a template's decisions applied to the wizard's state (the full wizard can change them all, D282)
function applyTemplate(x, t, lib) {
  const s = t.spec || {};
  const inScope = (i) => (s.items ? s.items.includes(i.id) : (!s.phases || s.phases.includes(i.phase)) && i.default_pick);
  return {
    ...x, template: t.code,
    purpose: s.purpose || x.purpose,
    scope: { ...x.scope, depth: s.depth || x.scope.depth, domains: s.domains?.length ? s.domains : x.scope.domains },
    picks: Object.fromEntries(lib.items.map((i) => [i.id, inScope(i)])),
    removed: Object.fromEntries(Object.entries(s.removed_steps || {}).map(([k, v]) => [Number(k), v || "Not needed in this kind of project"])),
    viewpoints: s.viewpoints || x.viewpoints,
    goals: s.goals === false ? [] : x.goals,
    stakeholders: (s.stakeholders || []).map((r) => ({ ...r })),     // the kind of project's suggested stakeholders (D294)
  };
}

// how complete a project is (owner, 8 Nov 2026): steps done and deliverables approved or accepted, each counting once
export function Completion({ c, wide = false }) {
  if (!c) return null;
  // phases marked complete count, nothing else (owner, 8 Nov 2026); a project marked complete is 100%
  const t = c.completed_at ? `marked complete by ${c.completed_by}, ${fmtDateTime(c.completed_at)}`
    : `${c.phases_done ?? c.done} of ${c.phases ?? c.total} phases marked complete`;
  return (
    <span className="completion" title={t}>
      <span className="completion-bar" aria-hidden="true"><span style={{ width: `${c.percent}%` }} /></span>
      <b>{c.percent}%</b>{wide && <span className="small quiet"> {t}</span>}
    </span>
  );
}

// ---------------------------------------------------------------- the list
function StatusChip({ status }) {
  const [tone, word] = STATUS[status] || ["off", status];
  return <span className={`rag ${tone}`}>{word}</span>;
}

function SetupNeeded({ manage }) {
  return (
    <div className="notice-box">
      <b>No template library is offered to projects</b>
      <p className="small">Projects take their starting documents from a template library. EA Explorer's own is normally offered from the start;
        here every library has been withdrawn, so a Super Admin ticks one as Offered again.</p>
      {manage ? <a className="button primary" href="#/project-admin/library">Project library →</a>
        : <p className="small quiet">Ask a Super Admin (Project admin › Project library).</p>}
    </div>
  );
}

const LIB_KIND = { "ea-explorer": "EA Explorer's own", togaf: "TOGAF 10", own: "Your own" };

// A new template library from a zip (in the project wizard, private to you until a Super Admin shares it; or on
// Administration › Project library)
function AddLibrary({ onAdded, inWizard }) {
  const [name, setName] = useState("");
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  async function add() {
    setBusy(true); setMsg("");
    const fd = new FormData(); fd.append("name", name.trim()); fd.append("file", file);
    try { const r = await apiUpload("/api/v1/projects/library/libraries", fd); setMsg(r.message); setName(""); setFile(null); onAdded?.(r.id); refreshAll(); }
    catch (e) { setMsg(e.message); }
    setBusy(false);
  }
  return (
    <div className="add-library">
      <b>Add a template library</b>
      <p className="small quiet">Download a library's zip (⬇ zip: a folder for every deliverable and artifact), rebrand or replace its files, add more
        documents to any folder, zip it again and upload it here under a name of its own.
        {inWizard ? " It is yours and this project's until a Super Admin offers it to every project." : ""}</p>
      <div className="row-gap">
        <input className="lib-name" placeholder="Library name, e.g. Thotnr 2027" value={name} onChange={(e) => setName(e.target.value)} />
        <input type="file" accept=".zip" onChange={(e) => setFile(e.target.files[0] || null)} />
        <button className="primary" disabled={busy || !name.trim() || !file} onClick={add}>{busy ? "Uploading..." : "Upload"}</button>
      </div>
      {msg && <p className="small">{msg}</p>}
    </div>
  );
}

function LibState({ l }) {
  if (l.state === "loading") return <span className="rag amber" title={l.note}>loading</span>;
  if (l.state === "failed") return <span className="rag red" title={l.note}>failed</span>;
  if (!l.files) return <span className="rag off" title={l.note}>no files yet</span>;
  return <span className="rag green" title={l.note}>{l.files} files</span>;
}

function RepoState({ state, note }) {
  const [tone, word] = REPO[state] || ["off", state];
  return <span className={`rag ${tone}`} title={note || ""}>{word}</span>;
}

// Documents' own messages (HTTP codes and JSON) in plain words; the original stays one click away
function plainMayan(msg) {
  const m = /Mayan refused (\w+) (\S+): HTTP (\d+)/.exec(msg || "");
  if (!m) return msg;
  const [, , path, code] = m;
  const what = path.includes("cabinet") ? "make a folder" : path.includes("checkout") ? "check the document out or in"
    : path.includes("documents") ? "store a document" : "do what was asked";
  if (code === "400") return `Documents refused to ${what}: it expected something else (EA Explorer and this version of Documents disagree). Build it again; if it fails the same way, send the message below to your IT Admin.`;
  if (code === "401" || code === "403") return `Documents refused to ${what}: EA Explorer's access to Documents was not accepted. It is set up again by itself; build it again in a minute.`;
  if (code === "404") return `Documents could not find what EA Explorer asked for (to ${what}). Build it again: what is missing is made again.`;
  return `Documents could not ${what} (error ${code}). Build it again in a minute.`;
}

// Why a project's repository (its folders and starting documents in Documents) is not ready, and what to do about it
export function RepoHelp({ p, onRebuild }) {
  if (!p || p.repo_state === "ready") return null;
  const reason = (p.repo_note || "").replace(/^Not built yet: /, "").replace(/ It is tried again every minute\.?$/, "");
  // Documents not up yet (it starts last), as opposed to Documents answering but refusing (an HTTP 4xx: needs looking at)
  const docsDown = !/HTTP 4\d\d/.test(reason) && /connect|connection refused|timed? ?out|502|503|504|unavailable|name or service|resolve|not up|starting/i.test(reason);
  // only waiting (or being built): one line, the rest a click away; a failure stays open
  if (p.repo_state !== "failed") {
    return (
      <details className="notice-line small">
        <summary><span className="spinner" aria-hidden="true" /> The project's repository (its folders in Documents) is {p.repo_state === "building" ? "being built" : "waiting to be built"}:
          everything else works meanwhile. <span className="quiet">More…</span></summary>
        <p>It is built by itself in the background within a minute or two of Documents being up; only uploading documents waits for it.
          A build cut off by a restart is taken up again within 15 minutes.{reason ? <> Last attempt: {plainMayan(reason)}</> : null}</p>
        {onRebuild && <button onClick={onRebuild}>Build the repository now</button>}
      </details>
    );
  }
  return (
    <div className="notice-box">
      <b>The project's repository is {p.repo_state === "failed" ? "not built yet" : p.repo_state === "building" ? "being built" : "waiting for Documents"}</b>
      <p className="small">The repository is the project's folders and starting documents in Documents (the document store). It is built by itself
        in the background, and tried again every minute until it works. Everything else in the project works meanwhile; only the deliverables'
        documents wait for it.</p>
      {reason && <p className="small"><b>Last attempt:</b> {plainMayan(reason)}</p>}
      {reason && plainMayan(reason) !== reason && <details className="small"><summary>The message from Documents</summary><code>{reason}</code></details>}
      <p className="small"><b>What to do:</b>{" "}
        {p.repo_state !== "failed" ? "nothing: wait a minute or two (a build cut off by a restart is taken up again by itself within 15 minutes; Build now starts it at once)."
          : docsDown ? <>nothing yet: Documents is not answering (it starts after the rest, and the top right shows it as starting). The repository is
            built when it is up. If Documents stays down, look at it in <a href="#/admin/containers">System admin › Containers</a>.</>
          : <>this needs looking at: the reason above is not Documents starting. Try building it now; if it fails the same way, send the reason
            to your IT Admin (System admin › Containers › dms has the Documents log).</>}</p>
      {onRebuild && <button onClick={onRebuild}>Build the repository now</button>}
    </div>
  );
}

// ---------------------------------------------------------------- the wizard (new, and the edit workflow)
// the models first (owner, 7 Nov 2026); a new model's suggested name follows the project's name once it is given in Basics
const STEPS = ["Models", "Primary working model", "Basics", "Scope", "Goals and outcomes", "Sponsor", "Stakeholders", "Notes and files", "Reference", "Template libraries", "Viewpoints",
  "Principles", "Charter", "Phase by phase", "People and sign-off", "Review"];
const EMPTY = {
  name: "", purpose: "", own_purpose: "", description: "", parent: "", models: [],
  scope: { breadth: "", depth: "", domains: [], start: "", end: "", horizon: "", notes: "" },
  sponsor: { name: "", role: "", contact: "", asks: [], notes_html: "" }, notes_html: "", goals_notes_html: "", files: [], goals: [],
  viewpoints: [], own_viewpoints: [], existing_vps: [], removed_viewpoints: [],
  principles: [], own_principles: [], existing_principles: [], removed_principles: [],
  removed: {}, own_steps: [], picks: null, kinds: {}, templates: {}, placeholders: {}, notes: {}, areas: {}, own_items: [], members: [], signoff: { "": [] }, signoff_quorum: "",
  libraries: null, template: "", stakeholders: [],
};

// the wizard's state from a live project (edit) or from the project a new one derives from (D274: derive)
function fromProject(p, lib, derive) {
  const purposes = lib.purposes.map((x) => x.code);
  const picks = Object.fromEntries(lib.items.map((i) => [i.id, false]));
  const kinds = {}, templates = {}, placeholders = {}, notes = {}, areas = {};
  p.items.filter((i) => i.library_id).forEach((i) => {
    picks[i.library_id] = i.chosen; kinds[i.library_id] = i.kind;
    if (i.templates) templates[i.library_id] = i.templates;
    if (i.placeholder) placeholders[i.library_id] = true;
    if (i.note) notes[i.library_id] = i.note;
    if (i.content_area) areas[i.library_id] = i.content_area;
  });
  const removed = Object.fromEntries(p.steps.filter((s) => s.library_id && s.removed).map((s) => [s.library_id, s.removed_reason || ""]));
  const ownSteps = p.steps.filter((s) => !s.library_id && !s.parent).map((s) => ({ ...(derive ? {} : { id: s.id }), phase: s.phase, name: s.name }));
  const ownItems = p.items.filter((i) => !i.library_id).map((i) => ({ ...(derive ? {} : { id: i.id }), phase: i.phase, name: i.name, kind: i.kind,
    placeholder: i.placeholder, removed: !i.chosen, templates: i.templates || [], note: i.note || "", areas: i.content_area || "" }));
  const signoff = { "": [] };
  p.signoff.forEach((x) => { (signoff[x.phase] = signoff[x.phase] || []).push(x.username); });
  const goals = (p.goals || []).filter((g) => g.id).map((g) => ({ ...(derive ? {} : { id: g.id }), name: g.name, description: g.description,
    outcomes: g.outcomes.map((o) => ({ ...(derive ? {} : { id: o.id }), name: o.name, description: o.description, measure: o.measure, target_date: o.target_date })) }));
  const base = {
    scope: { ...EMPTY.scope, ...p.scope }, removed, own_steps: ownSteps, own_steps_seen: ownSteps.filter((s) => s.id).map((s) => s.id), picks, kinds, templates, placeholders, notes, areas, own_items: ownItems,
    viewpoints: p.viewpoints.filter((v) => !v.own).map((v) => v.code), libraries: p.libraries.map((l) => l.id),
  };
  if (derive) {
    const keep = ["name", "organisation", "role_title", "category", "email", "phone", "concerns", "power", "interest", "disrupt", "understanding_now",
      "understanding_needed", "commitment_now", "commitment_needed", "support_needed", "frequency", "channel", "owner", "notes_html", "viewpoints"];
    return { ...base, parent: p.id, goals: [],
      // its stakeholders come too (their ratings and notes, not the discussions; D294)
      stakeholders: (p.stakeholders || []).map((s) => ({ ...Object.fromEntries(keep.map((k) => [k, s[k]])),
        ...(s.class_set ? { class: s.class } : {}), ...(s.approach_set ? { approach: s.approach } : {}) })),
      models: p.models.map((m) => ({ how: "referred", model: m.id, from: m.id, name: "", copy: "content", home: false, label: m.name, role: m.role || "reference" })),
      derived_goals: goals };
  }
  return {
    ...EMPTY, ...base, name: p.name, purpose: purposes.includes(p.purpose) ? p.purpose : "own", own_purpose: purposes.includes(p.purpose) ? "" : p.purpose,
    description: p.description || "", parent: p.parent_id || "",
    models: p.models.map((m) => ({ id: m.id, how: m.how, model: m.id, from: "", name: m.name, copy: "", home: m.id === p.home_model, label: m.name,
      role: m.role || "", seq: m.role_seq || null })),
    template: p.template?.code || "",
    sponsor: { ...EMPTY.sponsor, ...p.sponsor }, notes_html: p.notes_html || "", goals_notes_html: p.goals_notes_html || "", goals,
    existing_vps: p.viewpoints.filter((v) => v.own),
    principles: p.principles.filter((r) => r.library_id && !r.inherited_from).map((r) => r.library_id),
    existing_principles: p.principles.filter((r) => !r.library_id && !r.inherited_from),
    members: p.members.filter((m) => !(m.role === "project-admin" && m.username === p.me)).map((m) => ({ username: m.username, role: m.role })),
    signoff, signoff_quorum: p.signoff_quorum ?? "",
  };
}

function Wizard({ parent, editId, template, startAt }) {
  const { data: lib, error } = useApi("/api/v1/projects/library");
  const { data: me } = useApi("/api/v1/me");
  const { data: mlist } = useApi("/api/v1/models");
  const { data: plist } = useApi("/api/v1/projects");
  const { data: live, error: liveErr } = useApi(editId ? `/api/v1/projects/${editId}` : null);
  // ?step=Models opens the edit wizard on that step: add or make a model at any time in a project (owner, 7 Nov 2026)
  const [step, setStep] = useState(() => Math.max(0, STEPS.indexOf(startAt || "")));
  const [d, setD] = useState(EMPTY);
  const [phase, setPhase] = useState("P");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setD((x) => {
    if (k !== "name") return { ...x, [k]: v };
    // a new model still carrying its suggested name follows the project's name
    const models = x.models.map((m) => (m.auto_suffix && !m.id ? { ...m, name: `${v.trim() || "Project"} ${m.auto_suffix}` } : m));
    return { ...x, name: v, models };
  });
  useEffect(() => {
    if (!lib) return;
    if (editId) { if (live && d.picks === null) setD(fromProject(live, lib, false)); return; }
    if (d.picks === null) {
      const t = lib.project_templates.find((x) => x.code === template);
      setD((x) => {
        const base = { ...x, picks: Object.fromEntries(lib.items.map((i) => [i.id, i.default_pick])),
          libraries: lib.libraries.filter((l) => l.shared && l.usable).map((l) => l.id) };
        return t ? applyTemplate(base, t, lib) : base;
      });
      if (parent) deriveFrom(parent);
    }
  }, [lib, live]); // eslint-disable-line react-hooks/exhaustive-deps
  async function deriveFrom(id) {
    if (!id) { set("parent", ""); return; }
    try {
      const p = await apiFetch(`/api/v1/projects/${id}`);
      setD((x) => {
        const got = fromProject(p, lib, true);
        const have = new Set(x.models.map((m) => m.model || m.from));
        return { ...x, ...got, models: [...x.models, ...got.models.filter((m) => !have.has(m.model))],
          goals: x.goals.length ? x.goals : got.derived_goals, stakeholders: got.stakeholders.length ? got.stakeholders : x.stakeholders,
          reference: undefined };      // offered again, with the parent's reference material
      });
      setMsg(`Started from ${p.name}: its scope, steps, deliverables, viewpoints and libraries are filled in, and its models are listed as referred to (change each to add, derive or create). Its principles are inherited.`);
    } catch (e) { setMsg(e.message); }
  }
  if (error || liveErr) return <div className="page"><p className="status bad">{error || liveErr}</p></div>;
  if (!lib || d.picks === null || d.libraries === null) return <div className="page"><p className="quiet">Loading the project library...</p></div>;
  if (!editId && !lib.setup.done) return <div className="page"><h2>New architecture project</h2><SetupNeeded manage={lib.may_manage} /></div>;
  if (editId && live && !live.may_admin) return <div className="page"><p className="status bad">Changing {live.name} needs the Project Admin or the Lead Architect{live.frozen ? " (and it is read only now)" : ""}.</p></div>;
  const models = (mlist?.models || mlist || []).filter((m) => !m.is_deleted);
  const tpl = lib.project_templates.find((x) => x.code === d.template) || null;
  const steps = STEPS.filter((x) => !(tpl?.spec.skip || []).includes(x));
  const at = steps[Math.min(step, steps.length - 1)];
  const chooseKind = (code) => {
    const t = lib.project_templates.find((x) => x.code === code);
    setD((x) => (t ? applyTemplate(x, t, lib) : { ...x, template: "" }));
  };
  const purpose = d.purpose === "own" ? d.own_purpose.trim() : d.purpose;
  const goalsGiven = d.goals.some((g) => g.name.trim());
  const problems = [
    !d.models.length && "Select or make at least one model (Models).",
    ...(tpl?.spec.slots || []).filter((sl) => d.models.filter((m) => m.role === sl.role).length < sl.min)
      .map((sl) => `${sl.label}: at least ${sl.min} model${sl.min > 1 ? "s" : ""} (Models).`),
    d.models.some((m) => !m.id && ((["derived", "created"].includes(m.how) && !m.name.trim()) || !(m.model || m.from))) && "Each model needs a model to start from and, when new, a name (Models).",
    goalsGiven && !d.models.some((m) => m.home) && "Goals and outcomes need a primary working model: choose one under Primary working model, or remove the goals (Goals and outcomes).",
    !d.name.trim() && "Give the project a name (Basics).",
    !purpose && "Choose its purpose (Basics).",
    d.scope.start && d.scope.end && d.scope.end < d.scope.start && "The project ends before it starts (Scope).",
    !d.libraries.length && "Pick at least one template library (Template libraries).",
    Object.entries(d.removed).some(([, why]) => !String(why).trim()) && "Say why each removed step is removed (Phase by phase).",
  ].filter(Boolean);
  // the required fields of a step (owner, 7 Nov 2026): you cannot go past a step until they are filled in
  const problemsOf = (name) => problems.filter((p) => p.endsWith(`(${name}).`) || p.includes(`(${name})`));
  const blockedAt = steps.findIndex((x) => x !== "Review" && problemsOf(x).length > 0);   // the first step still missing something
  const go = (i) => setStep(blockedAt >= 0 && i > blockedAt ? blockedAt : i);
  const here = problemsOf(at);

  function body() {
    return {
      name: d.name.trim(), purpose, description: d.description, parent: d.parent || undefined, template: d.template || undefined,
      scope: d.scope, sponsor: d.sponsor, notes_html: d.notes_html, goals_notes_html: d.goals_notes_html,
      goals: d.goals.filter((g) => g.name.trim()),
      viewpoints: d.viewpoints, own_viewpoints: d.own_viewpoints.filter((v) => v.name.trim()), removed_viewpoints: d.removed_viewpoints,
      libraries: d.libraries,
      models: d.models.map((m) => ({ ...(m.id ? { id: m.id, how: m.how, home: m.home }
        : ["added", "referred"].includes(m.how) ? { how: m.how, model: m.model, home: m.home }
          : { how: m.how, start: startOf(m), from: m.from, name: m.name, description: m.description || "", copy: m.copy, home: m.home, tag: m.tag || undefined }),
        role: m.role || null, seq: m.seq || null })),
      principles: editId ? d.principles : [...d.principles.map((id) => ({ library_id: id })), ...d.own_principles.filter((p) => p.name.trim())],
      own_principles: d.own_principles.filter((p) => p.name.trim()), removed_principles: d.removed_principles,
      removed_steps: Object.entries(d.removed).map(([id, reason]) => ({ library_id: Number(id), reason })), removed: d.removed,
      own_steps: d.own_steps.filter((s) => s.name.trim()), own_steps_seen: d.own_steps_seen || [],
      stakeholders: editId ? undefined : (d.stakeholders || []).filter((s) => (s.name || "").trim()),
      reference: editId ? undefined : d.reference || [],
      items: Object.entries(d.picks).filter(([, on]) => on).map(([id]) => id), picks: d.picks, kinds: d.kinds,
      templates: d.templates, placeholders: d.placeholders, notes: d.notes, areas: d.areas,
      charter: Object.keys(d.charter || {}).length ? d.charter : undefined,
      own_items: d.own_items.filter((i) => i.name.trim()),
      members: d.members.filter((m) => m.username.trim()), signoff: d.signoff, signoff_quorum: d.signoff_quorum ?? "",
    };
  }
  async function uploadFiles(projectId) {
    const left = [];
    for (const f of d.files) {
      let done = false;
      for (let k = 0; k < 40 && !done; k += 1) {     // the new project's repository is built within moments: wait for it
        try {
          const fd = new FormData(); fd.append("file", f);
          await apiUpload(`/api/v1/projects/${projectId}/files`, fd);
          done = true;
        } catch (e) {
          if (!/not built yet|being built|try again/i.test(e.message)) break;
          await new Promise((r) => setTimeout(r, 3000));
        }
      }
      if (!done) left.push(f.name);
    }
    return left;
  }
  async function save() {
    setBusy(true); setMsg("");
    try {
      const from = window.location.hash;
      // D273, D275: made (or changed) in the background: its model copies, goals and repository
      const out = editId
        ? await runTask(apiFetch(`/api/v1/projects/${editId}`, { method: "PUT", body: JSON.stringify(body()) }), `#/projects/${editId}`)
        : await runTask(apiFetch("/api/v1/projects", { method: "POST", body: JSON.stringify(body()) }), "#/project-admin");
      const id = out.project.id;
      const left = d.files.length ? await uploadFiles(id) : [];
      refreshAll();
      if (left.length) setMsg(`Not uploaded: ${left.join(", ")}. Add them on the project's About tab.`);
      if (window.location.hash === from && !left.length) window.location.hash = `#/projects/${id}`;
    } catch (e) { setMsg(e.message); }
    setBusy(false);
  }

  return (
    <div className="page wizard">
      <h2>{editId ? `Change ${live?.name}` : `New architecture project${tpl ? `: ${tpl.name}` : ""}`}</h2>
      {!editId && <div className="small"><a href="#/projects/new">← All kinds of project</a></div>}
      {editId && <p className="small quiet">The project as it should be: add or remove models, viewpoints, steps, deliverables and artifacts, people and
        libraries. Documents already in the repository stay; new folders and templates are added in the background.</p>}
      {!editId && (
        <div className="row-gap small kind-row">
          <label>Kind of project <select value={d.template || ""} onChange={(e) => chooseKind(e.target.value)}>
            <option value="">Blank project (every decision yours)</option>
            {lib.project_templates.map((t) => <option key={t.code} value={t.code}>{t.icon} {t.name}</option>)}
          </select></label>
          {tpl && <span className="quiet">{tpl.description} Its decisions are filled in; change any of them.</span>}
        </div>
      )}
      <ol className="wizard-steps">
        {steps.map((s, i) => <li key={s} className={`${s === at ? "on" : i < steps.indexOf(at) ? "done" : ""}${problemsOf(s).length ? " missing" : ""}`}>
          <button className="linkish" disabled={blockedAt >= 0 && i > blockedAt} title={blockedAt >= 0 && i > blockedAt ? `Fill in ${steps[blockedAt]} first` : problemsOf(s).join(" ")}
            onClick={() => go(i)}>{i + 1}. {s}{problemsOf(s).length ? " •" : ""}</button></li>)}
      </ol>
      <div className="wizard-body">
        {at === "Models" && (tpl?.spec.slots?.length ? <RoleSlots d={d} set={set} models={models} tpl={tpl} />
          : <Models d={d} set={set} models={models} edit={!!editId} />)}
        {at === "Primary working model" && <PrimaryModel d={d} set={set} models={models} />}
        {at === "Basics" && <Basics d={d} set={set} lib={lib} projects={(plist?.projects || []).filter((p) => p.id !== editId)} onDerive={deriveFrom} edit={!!editId} />}
        {at === "Scope" && <Scope d={d} set={set} />}
        {at === "Goals and outcomes" && <Goals d={d} set={set} />}
        {at === "Sponsor" && <Sponsor d={d} set={set} />}
        {at === "Stakeholders" && <StakeholdersStep d={d} set={set} edit={!!editId} projectId={editId} />}
        {at === "Notes and files" && <NotesFiles d={d} set={set} live={live} />}
        {at === "Reference" && <ReferenceStep d={d} set={set} edit={!!editId} />}
        {at === "Template libraries" && <Libraries d={d} set={set} lib={lib} />}
        {at === "Viewpoints" && <ViewpointsStep d={d} set={set} lib={lib} />}
        {at === "Charter" && <CharterStep d={d} set={set} lib={lib} editId={editId} />}
        {at === "Principles" && <Principles d={d} set={set} lib={lib} parentName={(plist?.projects || []).find((p) => p.id === d.parent)?.name} />}
        {at === "Phase by phase" && <PhaseByPhase d={d} set={set} lib={lib} phase={phase} setPhase={setPhase} />}
        {at === "People and sign-off" && <People d={d} set={set} lib={lib} me={me?.username || me?.preferred_username} live={editId ? live : null} />}
        {at === "Review" && <Review d={d} lib={lib} purpose={purpose} problems={problems} />}
      </div>
      {here.length > 0 && at !== "Review" && <ul className="status bad small wizard-missing">{here.map((p) => <li key={p}>{p}</li>)}</ul>}
      <div className="row-gap wizard-nav">
        <button disabled={step === 0} onClick={() => setStep(step - 1)}>← Back</button>
        {step < steps.length - 1 && <button className="primary" disabled={here.length > 0} title={here.length ? "Fill in what is missing first" : ""}
          onClick={() => go(step + 1)}>Next: {steps[step + 1]} →</button>}
        {step >= steps.length - 1 && <button className="primary" disabled={busy || problems.length > 0} onClick={save}>
          {busy ? "Saving..." : editId ? "Save the changes" : "Create the project"}</button>}
        <a href={editId ? `#/project-admin/${editId}` : "#/project-admin"}>Cancel</a>
        {busy && <span className="small quiet"><span className="spinner" aria-hidden="true" /> In the background{d.files.length
          ? <b>: stay on this page until it is done, so the {d.files.length} file{d.files.length > 1 ? "s" : ""} you added can be uploaded</b>
          : ": you can leave this page"}; the Tasks tab on the right says when it is done.</span>}
        {msg && <span className={`status ${/Not |needs|No |not /.test(msg) ? "bad" : "ok"} small`}>{msg}</span>}
      </div>
    </div>
  );
}

// Step 1 (owner, 7 Nov 2026): the models. Select one or more existing models (worked on, or referred to: read only for
// everyone on the project), and make one or more new ones with the new-model wizard.
const START = {
  empty: ["Create empty", "A new model with a metamodel and no content: from a root metamodel (ArchiMate 4...) or a library model's metamodel."],
  copy: ["Derive from an existing model", "A separate copy of a model as it is now or at one of its tags: its metamodel, or its metamodel and content. It does not merge back."],
  library: ["Copy from the library", "A new model from a library (reference) model, with its ready-made content or its metamodel only (D283)."],
  child: ["Derive and keep the parent-child link", "A child of a project model, copied from it, that can merge back into it later (when the project finishes, or any time)."],
};
const startOf = (m) => m.start || (m.how === "derived" ? "child" : m.copy === "content" ? "copy" : "empty");

function Models({ d, set, models, edit }) {
  const [picking, setPicking] = useState(false);
  const [making, setMaking] = useState(null);     // null, or the index of the new model being changed (-1: a new one)
  const existing = d.models.map((m, i) => [m, i]).filter(([m]) => m.id || ["added", "referred"].includes(m.how));
  const fresh = d.models.map((m, i) => [m, i]).filter(([m]) => !m.id && ["derived", "created"].includes(m.how));
  const upd = (i, k, v) => set("models", d.models.map((m, j) => (j === i ? { ...m, [k]: v } : m)));
  const name = (id) => models.find((x) => x.id === id)?.name || id;
  return (
    <div>
      <p className="quiet">The models the project works on. Select existing models, and make new ones: most projects have two, one for the
        <b> current state</b> and one for the <b>target state</b>. Next you choose the primary working model, where the project's goals and outcomes go.</p>
      <h3>Existing models</h3>
      {!existing.length && <p className="quiet small">None selected.</p>}
      {existing.length > 0 && (
        <table className="grid-table">
          <thead><tr><th>Model</th><th>In this project</th><th>Role</th><th /></tr></thead>
          <tbody>
            {existing.map(([m, i]) => (
              <tr key={m.id || m.model || i}>
                <td>{m.id ? <a href={`#/metamodel/${m.id}`}>{m.label || m.name}</a> : <b>{m.label || name(m.model)}</b>} <OriginChip m={models.find((x) => x.id === (m.id || m.model))} />
                  {m.id && !["added", "referred"].includes(m.how) && <span className="small quiet"> · {HOW[m.how]}</span>}</td>
                <td>{["added", "referred"].includes(m.how) ? (
                  <select value={m.how} onChange={(e) => upd(i, "how", e.target.value)}>
                    <option value="added">Worked on</option><option value="referred">Referred to (read only)</option>
                  </select>) : <span className="small">{HOW[m.how]}</span>}</td>
                <td><RoleSelect m={m} onChange={(r) => upd(i, "role", r)} /></td>
                <td><button className="linkish" onClick={() => set("models", d.models.filter((_x, j) => j !== i))}>{m.id ? "Take out" : "Remove"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="small quiet">Everyone on the project can read a model it refers to: they get Report Viewer where they have no role yet (its
        Model Admins are asked when you are not one of them).</p>
      <button onClick={() => setPicking(true)}>+ Select existing models</button>
      <h3>New models</h3>
      {!fresh.length && <p className="quiet small">None yet.</p>}
      {fresh.map(([m, i]) => (
        <div key={i} className="goal-box">
          <div className="row-gap">
            <b>{m.name || "New model"}</b><span className="chip">{START[startOf(m)][0]}</span><RoleSelect m={m} onChange={(r) => upd(i, "role", r)} />
            <span className="small quiet">from {name(m.from)}{startOf(m) !== "empty" ? (m.copy === "content" ? ", metamodel and content" : ", metamodel only") : ""}</span>
            <button className="linkish" onClick={() => setMaking(i)}>Change</button>
            <button className="linkish" onClick={() => set("models", d.models.filter((_x, j) => j !== i))}>Remove</button>
          </div>
          {m.description && <div className="small">{m.description}</div>}
        </div>
      ))}
      <button className="primary" onClick={() => setMaking(-1)}>+ New model…</button>
      {edit && <p className="small quiet">Taking a model out of the project leaves the model as it is.</p>}
      {picking && <PickModels d={d} set={set} models={models} onClose={() => setPicking(false)} />}
      {making !== null && <NewModel models={models} start={making >= 0 ? d.models[making] : null} projectName={d.name}
        onClose={() => setMaking(null)}
        onDone={(m) => { set("models", making >= 0 ? d.models.map((x, j) => (j === making ? m : x)) : [...d.models, m]); setMaking(null); }} />}
    </div>
  );
}

function RoleSelect({ m, onChange }) {
  return (
    <select className="small" value={m.role || ""} onChange={(e) => onChange(e.target.value)} aria-label="Its role in the project">
      <option value="">no role</option>{Object.entries(ROLE_NAMES_M).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
    </select>
  );
}

// the Models step of a project template (D281, D282): one section per role it asks for
function RoleSlots({ d, set, models, tpl }) {
  const [picking, setPicking] = useState(null);     // the slot picking existing models
  const [making, setMaking] = useState(null);       // {slot, index}
  const name = (id) => models.find((x) => x.id === id)?.name || id;
  const current = d.models.find((m) => m.role === "current");
  const sourceDefault = current ? (current.model || current.id || "") : "";
  const place = (list) => {
    const out = [...list];
    const prim = tpl.spec.primary;
    if (prim && !out.some((m) => m.home)) { const k = out.findIndex((m) => m.role === prim && m.how !== "referred"); if (k >= 0) out[k] = { ...out[k], home: true }; }
    const seq = {};
    return out.map((m) => (["transition", "scenario"].includes(m.role) ? { ...m, seq: (seq[m.role] = (seq[m.role] || 0) + 1) } : m));
  };
  return (
    <div>
      <p className="quiet">{tpl.description} The models it works with, by their role.{tpl.spec.finish ? ` When it finishes: ${tpl.spec.finish}` : ""}</p>
      {tpl.spec.slots.map((sl) => {
        const mine = d.models.map((m, i) => [m, i]).filter(([m]) => m.role === sl.role);
        const full = !sl.many && mine.length >= 1;
        return (
          <section key={sl.role} className="goal-box">
            <div className="row-gap"><h3 style={{ margin: 0 }}>{sl.label}</h3>
              <span className="small quiet">{sl.min ? `at least ${sl.min}` : "optional"}{sl.many ? ", one or more" : ""}</span></div>
            {sl.help && <p className="small quiet">{sl.help}</p>}
            {mine.map(([m, i]) => (
              <div key={i} className="row-gap">
                <b>{m.label || m.name || name(m.model)}</b>
                <span className="chip">{m.id || ["added", "referred"].includes(m.how) ? (m.how === "referred" ? "existing, read only" : "existing") : START[startOf(m)][0]}</span>
                {m.seq && ["transition", "scenario"].includes(m.role) && <span className="small quiet">{m.role === "transition" ? `transition ${m.seq}` : `scenario ${String.fromCharCode(64 + m.seq)}`}</span>}
                {!m.id && !["added", "referred"].includes(m.how) && <button className="linkish" onClick={() => setMaking({ slot: sl, index: i })}>Change</button>}
                <button className="linkish" onClick={() => set("models", place(d.models.filter((_x, j) => j !== i)))}>Remove</button>
              </div>
            ))}
            {!full && (
              <div className="row-gap">
                {sl.starts.includes("existing") && <button onClick={() => setPicking(sl)}>+ Select existing</button>}
                {sl.starts.some((x) => x !== "existing") && <button className={sl.default_start !== "existing" ? "primary" : ""} onClick={() => setMaking({ slot: sl, index: -1 })}>+ New model…</button>}
              </div>
            )}
          </section>
        );
      })}
      {picking && <PickModels d={d} set={(k, v) => set(k, place(v.map((m) => (m.role || !d.models.includes(m) ? m : m))))} models={models}
        role={picking.role} how={picking.how} single={!picking.many} onClose={() => setPicking(null)} />}
      {making && <NewModel models={models} projectName={d.name} allowed={making.slot.starts.filter((x) => x !== "existing")}
        defaultStart={making.slot.default_start !== "existing" ? making.slot.default_start : null} defaultSource={sourceDefault}
        roleLabel={making.slot.label} start={making.index >= 0 ? d.models[making.index] : null}
        onClose={() => setMaking(null)}
        onDone={(m) => {
          const nm = { ...m, role: making.slot.role };
          set("models", place(making.index >= 0 ? d.models.map((x, j) => (j === making.index ? nm : x)) : [...d.models, nm]));
          setMaking(null);
        }} />}
    </div>
  );
}

// select existing models, with filters (owner, 7 Nov 2026): kind of model, metamodel, industry, owner, status
function PickModels({ d, set, models, onClose, role, how, single }) {
  const [q, setQ] = useState("");
  const [f, setF] = useState({ origin: "", metamodel: "", industry: "", owner: "", status: "", archived: false });
  const have = new Set(d.models.map((m) => m.id || m.model));
  const [chosen, setChosen] = useState({});
  const pool = models.filter((m) => !have.has(m.id));
  const opts = (k) => [...new Set(pool.map((m) => m[k]).filter(Boolean))].sort();
  const statusOf = (m) => (m.frozen_at ? "frozen" : m.lifecycle === "archived" ? "archived" : m.is_draft ? "draft" : m.lock_level && m.lock_level !== "none" ? `locked (${m.lock_level})` : "active");
  const list = pool.filter((m) => (!q || `${m.name} ${m.description || ""}`.toLowerCase().includes(q.toLowerCase()))
    && (!f.origin || modelOrigin(m).key === f.origin) && (!f.metamodel || m.metamodel_name === f.metamodel)
    && (!f.industry || m.industry === f.industry) && (!f.owner || m.owner === f.owner)
    && (!f.status || statusOf(m) === f.status) && (f.archived || f.status === "archived" || statusOf(m) !== "archived"));
  const groups = [["project", "Project models"], ["reference", "Library models"], ["template", "Root metamodels"]];
  const n = Object.values(chosen).filter(Boolean).length;
  const sel = (k, label, values) => values.length > 1 && (
    <label className="small">{label} <select value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}>
      <option value="">any</option>{values.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>);
  function add() {
    set("models", [...d.models, ...Object.entries(chosen).filter(([, h]) => h).map(([id, h]) => ({ how: h, model: id, from: "", name: "",
      label: models.find((x) => x.id === id)?.name, role: role || (h === "referred" ? "reference" : "") }))]);
    onClose();
  }
  return (
    <Modal wide title="Select existing models" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!n} onClick={add}>Add {n || ""}</button></>}>
      <div className="pick-filters">
        <input placeholder="Name or description" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
        {sel("origin", "Kind of model", Object.entries(ORIGINS).filter(([k]) => pool.some((m) => modelOrigin(m).key === k)))}
        {sel("metamodel", "Metamodel", opts("metamodel_name").map((v) => [v, v]))}
        {sel("industry", "Industry", opts("industry").map((v) => [v, v]))}
        {sel("owner", "Owner", opts("owner").map((v) => [v, v]))}
        {sel("status", "Status", [...new Set(pool.map(statusOf))].sort().map((v) => [v, v]))}
        <label className="small"><input type="checkbox" checked={f.archived} onChange={(e) => setF({ ...f, archived: e.target.checked })} /> archived too</label>
        <span className="small quiet">{list.length} of {pool.length}</span>
      </div>
      <div className="pick-list">
        {groups.map(([k, label]) => {
          const g = list.filter((m) => m.kind === k);
          if (!g.length) return null;
          return (
            <div key={k}><h4>{label}</h4>
              <table className="grid-table small pick-table"><tbody>
                {g.map((m) => {
                  const o = modelOrigin(m);
                  return (
                    <tr key={m.id} className={chosen[m.id] ? "on" : ""}>
                      <td><label><input type={single ? "radio" : "checkbox"} name="pick-model" checked={!!chosen[m.id]}
                        onChange={(e) => setChosen({ ...(single ? {} : chosen), [m.id]: e.target.checked ? (how || (k === "project" ? "added" : "referred")) : "" })} /> <b>{m.name}</b></label>
                        {m.description && <div className="quiet">{m.description}</div>}</td>
                      <td><span className={`chip origin-${o.key}`} title={o.text}>{o.label}</span><div className="quiet">{o.text}</div></td>
                      <td className="quiet">{m.metamodel_name}{m.industry ? ` · ${m.industry}` : ""}{m.owner ? ` · ${m.owner}` : ""}</td>
                      <td className="num quiet">{m.entity_count ?? ""} entities</td>
                      <td>{statusOf(m) !== "active" && <span className="chip">{statusOf(m)}</span>}
                        {chosen[m.id] && <select value={chosen[m.id]} onChange={(e) => setChosen({ ...chosen, [m.id]: e.target.value })}>
                          <option value="added">worked on</option><option value="referred">referred to (read only)</option></select>}</td>
                    </tr>
                  );
                })}
              </tbody></table>
            </div>
          );
        })}
        {!list.length && <p className="quiet small">No model matches{pool.length ? ": change the filters" : ""}.</p>}
      </div>
    </Modal>
  );
}

// the new-model wizard: how it starts, then its details
function NewModel({ models, start, projectName, onClose, onDone, allowed, defaultStart, defaultSource, roleLabel }) {
  const [step, setStep] = useState(start || (allowed?.length === 1) ? 1 : 0);
  const [m, setM] = useState(() => {
    if (start) return { ...start, start: startOf(start) };
    const k = allowed?.length === 1 ? allowed[0] : null;
    if (!k) return { start: "", how: "created", from: "", name: "", description: "", copy: "metamodel" };
    return { start: k, how: k === "child" ? "derived" : "created", copy: k === "empty" ? "metamodel" : "content",
      from: k === "empty" ? "" : defaultSource || "", name: `${projectName || "Project"} ${(roleLabel || "model").toLowerCase()}`,
      auto_suffix: (roleLabel || "model").toLowerCase(), description: "" };
  });
  const up = (k, v) => setM((x) => ({ ...x, [k]: v }));
  const sources = m.start === "empty" ? models.filter((x) => ["template", "reference"].includes(x.kind))
    : m.start === "child" ? models.filter((x) => x.kind === "project")
    : m.start === "library" ? models.filter((x) => x.kind === "reference") : models;
  function choose(k) {
    setM((x) => ({ ...x, start: k, how: k === "child" ? "derived" : "created", copy: k === "empty" ? "metamodel" : "content",
      from: k === "empty" ? "" : defaultSource || "",
      name: x.name || `${projectName || "Project"} ${(roleLabel || (k === "empty" ? "target state" : "model")).toLowerCase()}`,
      auto_suffix: x.name ? x.auto_suffix : (roleLabel || (k === "empty" ? "target state" : "model")).toLowerCase() }));
    setStep(1);
  }
  const ok = m.from && m.name.trim();
  // a separate copy can start from the model as it was at one of its tags (owner, 7 Nov 2026); a child cannot
  const src = models.find((x) => x.id === m.from);
  const tagsOk = m.start === "copy" && src?.kind === "project";
  const { data: tagList } = useApi(tagsOk ? `/api/v1/models/${m.from}/tags` : null);
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="New model">
      <div className="modal">
        <h3>New model{roleLabel ? ` (${roleLabel.toLowerCase()})` : ""}{step === 1 ? `: ${START[m.start][0].toLowerCase()}` : ""}</h3>
        {step === 0 && Object.entries(START).filter(([k]) => !allowed || allowed.includes(k) || (k === "library" && allowed.includes("copy"))).map(([k, [title, help]]) => (
          <button key={k} className="start-choice" onClick={() => choose(k)}><b>{title}</b><span className="small quiet">{help}</span></button>
        ))}
        {step === 1 && (
          <div className="basics">
            <label className="field">{m.start === "empty" ? "Its metamodel comes from" : m.start === "child" ? "The parent model (a project model)" : m.start === "library" ? "The library model" : "Copy from"}
              <select value={m.from} onChange={(e) => setM((x) => ({ ...x, from: e.target.value, tag: "", tag_name: "" }))}>
                <option value="">Choose...</option>
                {sources.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.kind === "template" ? "root metamodel" : x.kind === "reference" ? "library model" : "project model"})</option>)}
              </select>
            </label>
            {tagsOk && (
              <div className="field">As it is
                <div className="radio-row">
                  <label><input type="radio" checked={!m.tag} onChange={() => setM((x) => ({ ...x, tag: "", tag_name: "" }))} /> now</label>
                  <label><input type="radio" checked={!!m.tag} disabled={!tagList?.tags?.length}
                    onChange={() => setM((x) => ({ ...x, tag: tagList.tags[0].id, tag_name: tagList.tags[0].name, copy: "content" }))} /> at a tag
                    {tagList && !tagList.tags.length && <span className="small quiet"> (it has no tags)</span>}</label>
                  {m.tag && <select value={m.tag} onChange={(e) => setM((x) => ({ ...x, tag: e.target.value, tag_name: tagList.tags.find((t) => t.id === e.target.value)?.name || "" }))}>
                    {tagList.tags.map((t) => <option key={t.id} value={t.id}>{t.name} ({fmtDateTime(t.created_at)}, {t.entities} entities)</option>)}
                  </select>}
                </div>
              </div>
            )}
            {m.start !== "empty" && !m.tag && (
              <div className="field">What is copied
                <div className="radio-row">
                  <label><input type="radio" checked={m.copy === "content"} onChange={() => up("copy", "content")} /> Metamodel and content</label>
                  <label><input type="radio" checked={m.copy === "metamodel"} onChange={() => up("copy", "metamodel")} /> Metamodel only</label>
                </div>
              </div>
            )}
            {m.tag && <p className="small quiet">Its metamodel and content as they were at the tag. A model made from a tag is always a separate copy: it has no parent and does not merge back.</p>}
            <label className="field">Name{m.auto_suffix ? <span className="small quiet"> (follows the project's name, given in Basics, until you change it)</span> : ""} <input value={m.name} onChange={(e) => setM((x) => ({ ...x, name: e.target.value, auto_suffix: "" }))} placeholder="e.g. Claims target state 2030" /></label>
            <label className="field">Description <textarea rows={2} value={m.description || ""} onChange={(e) => up("description", e.target.value)}
              placeholder="e.g. The target state of claims after the transformation" /></label>
            {m.start === "child" && <p className="small quiet">It stays linked to its parent: when the project finishes you can merge it back (or keep it).</p>}
          </div>
        )}
        <div className="row-gap">
          {step === 1 && !start && (!allowed || allowed.length > 1) && <button onClick={() => setStep(0)}>← Back</button>}
          {step === 1 && <button className="primary" disabled={!ok} onClick={() => onDone({ ...m, name: m.name.trim() })}>{start ? "Save" : "Add the model"}</button>}
          <button onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

// Step 2: the primary working model, where the project's goals and outcomes go (optional: a project may have none)
function PrimaryModel({ d, set, models }) {
  const cands = d.models.map((m, i) => [m, i]).filter(([m]) => m.how !== "referred");
  const name = (m) => m.label || m.name || models.find((x) => x.id === (m.model || m.from))?.name || "a model";
  const pick = (i) => set("models", d.models.map((m, j) => ({ ...m, home: j === i })));
  return (
    <div>
      <p className="quiet">Which model is the project's primary working model? Its goals and outcomes are Goal and Outcome entities there
        (usually the target state). A project needs none when it has no goals: a library, documenting the current state, reports.</p>
      {cands.map(([m, i]) => (
        <label key={i} className={`choice${m.home ? " on" : ""}`}><input type="radio" name="primary" checked={!!m.home} onChange={() => pick(i)} /> <b>{name(m)}</b>
          <span className="small quiet">{m.id ? HOW[m.how] : ["derived", "created"].includes(m.how) ? `new: ${START[startOf(m)][0].toLowerCase()}` : "worked on"}</span></label>
      ))}
      <label className={`choice${!d.models.some((m) => m.home) ? " on" : ""}`}><input type="radio" name="primary" checked={!d.models.some((m) => m.home)}
        onChange={() => set("models", d.models.map((m) => ({ ...m, home: false })))} /> <b>None</b><span className="small quiet">the project has no goals and outcomes</span></label>
      {!cands.length && <p className="quiet small">Only models referred to (read only): goals need a model the project works on.</p>}
    </div>
  );
}

function Basics({ d, set, lib, projects, onDerive, edit }) {
  return (
    <div className="basics">
      <label className="field">Name
        <input value={d.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Claims Transformation 2027" autoFocus />
      </label>
      <label className="field">Description
        <textarea rows={3} value={d.description} onChange={(e) => set("description", e.target.value)} placeholder="What the project is for" />
      </label>
      <div className="field">Purpose
        <div className="purpose-choices">
          {lib.purposes.map((p) => (
            <label key={p.code} className={`choice${d.purpose === p.code ? " on" : ""}`} title={PURPOSE_HELP[p.code] || ""}>
              <input type="radio" name="purpose" checked={d.purpose === p.code} onChange={() => set("purpose", p.code)} /> {p.name}
              <span className="small quiet">{PURPOSE_HELP[p.code] || ""}</span>
            </label>
          ))}
          <label className={`choice${d.purpose === "own" ? " on" : ""}`}>
            <input type="radio" name="purpose" checked={d.purpose === "own"} onChange={() => set("purpose", "own")} /> Your own:
            <input value={d.own_purpose} onChange={(e) => { set("own_purpose", e.target.value); set("purpose", "own"); }} placeholder="e.g. Regulatory change" />
          </label>
        </div>
      </div>
      {!edit && (
        <label className="field">Start
          <select value={d.parent} onChange={(e) => onDerive(e.target.value)}>
            <option value="">From scratch</option>
            {projects.map((p) => <option key={p.id} value={p.id}>Derive from {p.name}{p.status !== "active" ? ` (${p.status})` : ""}</option>)}
          </select>
          <span className="small quiet">A derived project starts with its parent's scope, goals, steps, deliverables and artifacts, viewpoints and libraries
            (change any of them), inherits its principles, and lists its models as referred to: choose for each to refer to it, add it, derive a child
            or create a separate one. A frozen project can be a parent too.</span>
        </label>
      )}
    </div>
  );
}

function Scope({ d, set }) {
  const s = d.scope;
  const up = (k, v) => set("scope", { ...s, [k]: v });
  const toggle = (c) => up("domains", s.domains.includes(c) ? s.domains.filter((x) => x !== c) : [...s.domains, c]);
  return (
    <div className="basics">
      <p className="quiet">TOGAF scopes an architecture in four ways: how much of the enterprise (breadth), how much detail (depth), the time it
        covers, and which architecture domains.</p>
      <label className="field">Breadth: what part of the enterprise
        <input value={s.breadth} onChange={(e) => up("breadth", e.target.value)} placeholder="e.g. the whole group; or Claims and Underwriting" />
      </label>
      <div className="field">Depth: the level of detail
        <div className="purpose-choices">
          {DEPTHS.map(([k, n, help]) => (
            <label key={k} className={`choice${s.depth === k ? " on" : ""}`}>
              <input type="radio" name="depth" checked={s.depth === k} onChange={() => up("depth", k)} /> {n}<span className="small quiet">{help}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="field">Time
        <div className="row-gap">
          <label className="small">Starts <input type="date" value={s.start} onChange={(e) => up("start", e.target.value)} /></label>
          <label className="small">Ends <input type="date" value={s.end} onChange={(e) => up("end", e.target.value)} /></label>
          <label className="small">Target horizon <input value={s.horizon} onChange={(e) => up("horizon", e.target.value)} placeholder="e.g. 3 years, 2030" /></label>
        </div>
      </div>
      <div className="field">Architecture domains
        <div className="row-gap">{DOMAINS.map(([k, n]) => <label key={k} className={`choice small${s.domains.includes(k) ? " on" : ""}`}>
          <input type="checkbox" checked={s.domains.includes(k)} onChange={() => toggle(k)} /> {n}</label>)}</div>
      </div>
      <label className="field">Anything else about the scope
        <textarea rows={2} value={s.notes} onChange={(e) => up("notes", e.target.value)} placeholder="Out of scope, constraints, assumptions" />
      </label>
    </div>
  );
}

// goals and outcomes as two grids (owner, 7 Nov 2026): the goals, then the outcomes, each saying which goal it shows is reached
function Goals({ d, set }) {
  const home = d.models.find((m) => m.home);
  const goalsGiven = d.goals.some((g) => g.name.trim());
  const upd = (i, k, v) => set("goals", d.goals.map((g, j) => (j === i ? { ...g, [k]: v } : g)));
  // the outcomes, flat: [goal index, outcome index, outcome]
  const outs = d.goals.flatMap((g, i) => g.outcomes.map((o, n) => [i, n, o]));
  const updO = (i, n, k, v) => upd(i, "outcomes", d.goals[i].outcomes.map((o, j) => (j === n ? { ...o, [k]: v } : o)));
  const moveO = (i, n, to) => {
    if (to === i) return;
    const o = d.goals[i].outcomes[n];
    set("goals", d.goals.map((g, j) => (j === i ? { ...g, outcomes: g.outcomes.filter((_x, k) => k !== n) } : j === to ? { ...g, outcomes: [...g.outcomes, o] } : g)));
  };
  const goalName = (g, i) => g.name.trim() || `Goal ${i + 1}`;
  return (
    <div>
      <p className="quiet">What the project is for: its goals, and the outcomes that show each is reached (how it is measured and by when). They are
        {" "}<b>Goal</b> and <b>Outcome</b> entities in the project's model{home ? <> (<b>{home.label || home.name || "the chosen model"}</b>)</> : ""};
        each outcome realises its goal, so they can be traced to drivers, requirements and the architecture.</p>
      {!home && <p className="small quiet">No primary working model is chosen, so this project has no goals and outcomes: that is fine for a library,
        documenting the current state or reports. To add goals, choose one first (Primary working model; only a model the project adds, derives or
        creates can be one: change a referred model on the Models step).</p>}
      {!home && goalsGiven && <p className="small status bad">{d.goals.filter((g) => g.name.trim()).length} goals are listed (from the project you started from).
        {" "}<button className="linkish" onClick={() => set("goals", [])}>Remove these goals</button>, or choose a primary working model to keep them.</p>}
      {home && <>
        <h4>Goals</h4>
        <table className="grid-table edit-grid">
          <thead><tr><th style={{ width: "30%" }}>Goal</th><th>Description</th><th className="num">Outcomes</th><th /></tr></thead>
          <tbody>
            {d.goals.map((g, i) => (
              <tr key={i}>
                <td><input aria-label="Goal" placeholder="e.g. Pay claims faster" value={g.name} onChange={(e) => upd(i, "name", e.target.value)} /></td>
                <td><input aria-label="Goal description" placeholder="Description" value={g.description || ""} onChange={(e) => upd(i, "description", e.target.value)} /></td>
                <td className="num">{g.outcomes.length}</td>
                <td><button className="linkish" title={g.outcomes.length ? "Its outcomes go too" : ""} onClick={() => set("goals", d.goals.filter((_x, j) => j !== i))}>Remove</button></td>
              </tr>
            ))}
            {!d.goals.length && <tr><td colSpan={4} className="quiet small">No goals yet.</td></tr>}
          </tbody>
        </table>
        <button onClick={() => set("goals", [...d.goals, { name: "", description: "", outcomes: [] }])}>+ Add a goal</button>
        <h4>Outcomes</h4>
        <table className="grid-table edit-grid">
          <thead><tr><th style={{ width: "22%" }}>For the goal</th><th>Outcome</th><th>Measure</th><th>Target date</th><th /></tr></thead>
          <tbody>
            {outs.map(([i, n, o]) => (
              <tr key={`${i}-${n}`}>
                <td><select value={i} onChange={(e) => moveO(i, n, Number(e.target.value))}>
                  {d.goals.map((g, k) => <option key={k} value={k}>{goalName(g, k)}</option>)}</select></td>
                <td><input aria-label="Outcome" placeholder="e.g. Claims paid within 5 days" value={o.name} onChange={(e) => updO(i, n, "name", e.target.value)} /></td>
                <td><input aria-label="How it is measured" placeholder="e.g. median days" value={o.measure || ""} onChange={(e) => updO(i, n, "measure", e.target.value)} /></td>
                <td><input type="date" aria-label="Target date" value={o.target_date || ""} onChange={(e) => updO(i, n, "target_date", e.target.value)} /></td>
                <td><button className="linkish" onClick={() => upd(i, "outcomes", d.goals[i].outcomes.filter((_x, k) => k !== n))}>Remove</button></td>
              </tr>
            ))}
            {!outs.length && <tr><td colSpan={5} className="quiet small">{d.goals.length ? "No outcomes yet." : "Add a goal first."}</td></tr>}
          </tbody>
        </table>
        <button disabled={!d.goals.length} onClick={() => upd(d.goals.length - 1, "outcomes", [...d.goals[d.goals.length - 1].outcomes, { name: "", measure: "", target_date: "" }])}>+ Add an outcome</button>
      </>}
      <h4>More about the goals</h4>
      <RichText value={d.goals_notes_html || ""} onChange={(v) => set("goals_notes_html", v)} placeholder="Background, priorities, what is out of scope, links" />
    </div>
  );
}

function Sponsor({ d, set }) {
  const s = d.sponsor;
  const up = (k, v) => set("sponsor", { ...s, [k]: v });
  const updA = (i, k, v) => up("asks", s.asks.map((a, j) => (j === i ? { ...a, [k]: v } : a)));
  return (
    <div className="basics">
      <div className="row-gap">
        <label className="field">Sponsor <input value={s.name} onChange={(e) => up("name", e.target.value)} placeholder="Name" /></label>
        <label className="field">Role <input value={s.role} onChange={(e) => up("role", e.target.value)} placeholder="e.g. Chief Financial Officer" /></label>
        <label className="field">Contact <input value={s.contact} onChange={(e) => up("contact", e.target.value)} placeholder="Phone or office (optional)" /></label>
      </div>
      <h4>What the sponsor asks for</h4>
      {s.asks.map((a, i) => (
        <div key={i} className="own-row">
          <input placeholder="The ask, e.g. a roadmap for the claims platform" value={a.ask} onChange={(e) => updA(i, "ask", e.target.value)} style={{ flex: 3 }} />
          <input type="date" aria-label="By" value={a.by} onChange={(e) => updA(i, "by", e.target.value)} />
          <input placeholder="How success is judged" value={a.measure} onChange={(e) => updA(i, "measure", e.target.value)} style={{ flex: 2 }} />
          <button className="linkish" onClick={() => up("asks", s.asks.filter((_x, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button onClick={() => up("asks", [...s.asks, { ask: "", by: "", measure: "" }])}>+ Add an ask</button>
      <h4>More about the sponsor</h4>
      <RichText value={s.notes_html || ""} onChange={(v) => up("notes_html", v)} placeholder="Background, expectations, how they like to be kept informed, other sponsors" />
    </div>
  );
}

function NotesFiles({ d, set, live }) {
  return (
    <div>
      <p className="quiet">Anything about the project that does not belong in a model: background, decisions so far, contacts, links. Kept with the
        project, not in the metamodel.</p>
      <RichText value={d.notes_html} onChange={(v) => set("notes_html", v)} placeholder="Notes about the project" />
      <h4>Files of the project</h4>
      <p className="small quiet">Contracts, statements of work, letters: kept in the project's repository (00_Project/Project files), with versions.
        {live ? "" : " They are uploaded as soon as the project is made: stay on the page until it is."}</p>
      {live?.project_files?.length > 0 && <ul className="small">{live.project_files.map((f) => <li key={f.id}>📄 {f.file_name}</li>)}</ul>}
      <input type="file" multiple aria-label="Add files of the project" onChange={(e) => { set("files", [...d.files, ...e.target.files]); e.target.value = ""; }} />
      {d.files.length > 0 && (
        <ul className="small">{d.files.map((f, i) => <li key={`${f.name}${i}`}>{f.name} <button className="linkish" onClick={() => set("files", d.files.filter((_x, j) => j !== i))}>Remove</button></li>)}</ul>
      )}
    </div>
  );
}

function Libraries({ d, set, lib }) {
  const toggle = (id) => set("libraries", d.libraries.includes(id) ? d.libraries.filter((x) => x !== id) : [...d.libraries, id]);
  const offered = lib.libraries.filter((l) => l.state !== "failed");
  return (
    <div>
      <p className="quiet">Where the project's starting documents come from. Pick one or more; then, phase by phase, choose for each deliverable and
        artifact which of their templates to copy (copies are named <code>library-document</code>), or none: a placeholder, built later.</p>
      <table className="grid-table">
        <thead><tr><th /><th>Template library</th><th>Kind</th><th>Files</th><th>Offered to</th></tr></thead>
        <tbody>
          {offered.map((l) => (
            <tr key={l.id} className={l.usable || l.state === "loading" ? "" : "quiet"}>
              <td><input type="checkbox" checked={d.libraries.includes(l.id)} disabled={!l.usable && l.state !== "loading"} onChange={() => toggle(l.id)} /></td>
              <td><b>{l.name}</b><div className="small quiet">{l.description}</div></td>
              <td className="small">{LIB_KIND[l.kind]}</td>
              <td><LibState l={l} />{l.may_download && <> <button className="linkish small" onClick={() => startDownload(`/api/v1/projects/library/libraries/${l.id}/zip`, undefined, window.location.hash).catch(() => {})}>⬇ zip</button></>}</td>
              <td className="small">{l.shared ? "every project" : `you${l.project ? ` and ${l.project}` : ""} (not shared yet)`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {d.libraries.length > 0 && <p className="small">Picked, in this order: {d.libraries.map((id) => offered.find((l) => l.id === id)?.name).filter(Boolean).join(", ")}.</p>}
      <AddLibrary inWizard onAdded={(id) => set("libraries", [...d.libraries, id])} />
    </div>
  );
}

function ViewpointsStep({ d, set, lib }) {
  const toggleVp = (c) => set("viewpoints", d.viewpoints.includes(c) ? d.viewpoints.filter((x) => x !== c) : [...d.viewpoints, c]);
  const upd = (i, k, v) => set("own_viewpoints", d.own_viewpoints.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  return (
    <div>
      <p className="quiet small">The views this project's stakeholders need, from the viewpoint library. On the project's page each shows whether its
        element types are in one of the project's models' metamodels (open it there) or still to build. Chosen: <b>{d.viewpoints.length}</b> of {lib.viewpoints.length}.</p>
      <div className="row-gap">
        <button onClick={() => set("viewpoints", lib.viewpoints.map((v) => v.code))}>Select all</button>
        <button onClick={() => set("viewpoints", [])}>Clear all</button>
      </div>
      <div className="vp-choices">
        {lib.viewpoints.map((v) => (
          <label key={v.code} className={`choice small${d.viewpoints.includes(v.code) ? " on" : ""}`} title={`${v.purpose}\n\nShows: ${(v.element_types || []).join(", ")}`}>
            <input type="checkbox" checked={d.viewpoints.includes(v.code)} onChange={() => toggleVp(v.code)} /> {v.code} {v.name}
          </label>
        ))}
      </div>
      <h3>The project's own viewpoints</h3>
      {d.existing_vps.map((v) => (
        <div key={v.code} className="own-row small"><b>{v.code}</b> {v.name} <span className="quiet">{v.state}</span>
          <label><input type="checkbox" checked={d.removed_viewpoints.includes(v.code)}
            onChange={(e) => set("removed_viewpoints", e.target.checked ? [...d.removed_viewpoints, v.code] : d.removed_viewpoints.filter((x) => x !== v.code))} /> take out</label></div>
      ))}
      {d.own_viewpoints.map((v, i) => (
        <div key={i} className="goal-box">
          <div className="own-row">
            <input placeholder="Name, e.g. Claims journey" value={v.name} onChange={(e) => upd(i, "name", e.target.value)} />
            <input placeholder="Concerns it answers" value={v.concerns} onChange={(e) => upd(i, "concerns", e.target.value)} style={{ flex: 2 }} />
            <input placeholder="Stakeholders" value={v.stakeholders} onChange={(e) => upd(i, "stakeholders", e.target.value)} />
            <button className="linkish" onClick={() => set("own_viewpoints", d.own_viewpoints.filter((_x, j) => j !== i))}>Remove</button>
          </div>
          <input className="wide" placeholder="Element types it shows, separated by commas, e.g. BusinessProcess, BusinessActor, Journey step"
            value={v.types_text} onChange={(e) => set("own_viewpoints", d.own_viewpoints.map((x, j) => (j === i ? { ...x, types_text: e.target.value,
              element_types: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) } : x)))} />
          <p className="small quiet">Types the project's models' metamodels have make it ready to use; others make it a viewpoint to build.</p>
        </div>
      ))}
      <button onClick={() => set("own_viewpoints", [...d.own_viewpoints, { name: "", concerns: "", stakeholders: "", element_types: [], types_text: "" }])}>+ Make a viewpoint for the project</button>
    </div>
  );
}

const kindOf = (d, i) => d.kinds[i.id] || i.kind;

// The templates of a library document type in the wizard: the ones chosen (none chosen: every one its libraries offer),
// or none at all when it is a blank one (a placeholder: its document is made later).
const offeredTpl = (d, lib, i) => (lib.item_templates[i.id] || []).filter((t) => d.libraries.includes(t.library));
function chosenTpl(d, lib, i) {
  if (d.placeholders[i.id]) return [];
  const offered = offeredTpl(d, lib, i);
  const ids = d.templates[i.id];
  if (!ids) return offered;
  const idx = lib.template_index || {};
  return ids.map((id) => offered.find((t) => t.id === id) || idx[String(id)] || { id, name: `template ${id}`, library_name: "" });
}

// The templates cell (owner, 8 Nov 2026): each template with the library it is from; remove one; add one by looking
// through the libraries (a library not yet in the project comes in with it); none: a blank document, its description
// said in the Description column.
function TemplatesCell({ tpls, offered, onRemove, onAdd, libs }) {
  const [browse, setBrowse] = useState(false);
  const picked = tpls.map((t) => t.id);
  const notChosen = offered.filter((t) => !picked.includes(t.id));
  return (
    <div className="wz-tpls">
      {tpls.length ? tpls.map((t) => (
        <span key={t.id} className="tpl-chip" title={`From the library ${t.library_name || "?"}`}>
          <span className="quiet">{t.library_name || "?"} ›</span> {t.name}
          <button className="linkish" aria-label={`Take out ${t.name}`} title="Take this template out" onClick={() => onRemove(t)}>×</button></span>
      )) : <span className="tpl-chip blank" title="No template: the document is made later; its description says what it holds">Blank</span>}
      {notChosen.map((t) => <button key={t.id} className="linkish small quiet" title={`Offered by ${t.library_name}: add it`} onClick={() => onAdd(t)}>＋ {t.library_name} › {t.name}</button>)}
      <button className="linkish small" onClick={() => setBrowse(true)} disabled={!libs.length}>📚 Browse the libraries…</button>
      {browse && <TemplateBrowserDialog libraries={libs} picked={picked} title="Add a template from a library"
        onClose={() => setBrowse(false)} onPick={(t) => onAdd(t)} />}
    </div>
  );
}

function Principles({ d, set, lib, parentName }) {
  const sets = [...new Set(lib.principles.map((p) => p.set_name || "Principles"))];
  const toggle = (id) => set("principles", d.principles.includes(id) ? d.principles.filter((x) => x !== id) : [...d.principles, id]);
  const upd = (i, k, v) => set("own_principles", d.own_principles.map((p, j) => (j === i ? { ...p, [k]: v } : p)));
  return (
    <div>
      {parentName && <p className="status ok small">As derived from {parentName}, the project inherits its principles; add more here.</p>}
      {!lib.principles.length && <p className="quiet">The principles library is empty: add the project's own below (a Super Admin can fill the library).</p>}
      {lib.principles.length > 0 && (
        <div className="row-gap">
          <button onClick={() => set("principles", lib.principles.map((p) => p.id))}>Select all</button>
          <button onClick={() => set("principles", [])}>Clear all</button>
          <span className="small quiet">Chosen: <b>{d.principles.length}</b> of {lib.principles.length}</span>
        </div>
      )}
      {sets.map((s) => (
        <details key={s} open>
          <summary><b>{s}</b> <span className="quiet small">{lib.principles.filter((p) => (p.set_name || "Principles") === s && d.principles.includes(p.id)).length} chosen</span>{" "}
            <button className="linkish small" onClick={(e) => { e.preventDefault(); set("principles", [...new Set([...d.principles, ...lib.principles.filter((p) => (p.set_name || "Principles") === s).map((p) => p.id)])]); }}>select all in {s}</button></summary>
          <div className="principle-list">
            {lib.principles.filter((p) => (p.set_name || "Principles") === s).map((p) => (
              <label key={p.id} className={`choice small${d.principles.includes(p.id) ? " on" : ""}`} title={`${p.statement}\n\nRationale: ${p.rationale}`}>
                <input type="checkbox" checked={d.principles.includes(p.id)} onChange={() => toggle(p.id)} /> <b>{p.code}</b> {p.name}
                {p.tier && <span className="small quiet"> · {p.tier}</span>}
              </label>
            ))}
          </div>
        </details>
      ))}
      <h4>The project's own principles</h4>
      {d.existing_principles.map((p) => (
        <div key={p.id} className="own-row small"><b>{p.name}</b> <span className="quiet">{p.statement}</span>
          <label><input type="checkbox" checked={d.removed_principles.includes(p.id)}
            onChange={(e) => set("removed_principles", e.target.checked ? [...d.removed_principles, p.id] : d.removed_principles.filter((x) => x !== p.id))} /> remove</label></div>
      ))}
      {d.own_principles.map((p, i) => (
        <div key={i} className="own-row">
          <input placeholder="Name" value={p.name} onChange={(e) => upd(i, "name", e.target.value)} />
          <input placeholder="Statement" value={p.statement} onChange={(e) => upd(i, "statement", e.target.value)} style={{ flex: 2 }} />
          <input placeholder="Rationale" value={p.rationale} onChange={(e) => upd(i, "rationale", e.target.value)} style={{ flex: 2 }} />
          <button className="linkish" onClick={() => set("own_principles", d.own_principles.filter((_x, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button onClick={() => set("own_principles", [...d.own_principles, { name: "", statement: "", rationale: "", implications: "" }])}>+ Add a principle</button>
    </div>
  );
}

function PhaseByPhase({ d, set, lib, phase, setPhase }) {
  const [part, setPart] = useState("docs");       // Steps and Documents are tabs of their own (owner, 8 Nov 2026)
  const steps = lib.steps.filter((s) => s.phase === phase);
  const items = lib.items.filter((i) => i.phase === phase);
  const own = d.own_steps.filter((s) => s.phase === phase);
  const ownItems = d.own_items.filter((i) => i.phase === phase);
  const ph = lib.phases.find((p) => p.code === phase);
  const removeStep = (s, on) => { const r = { ...d.removed }; if (on) r[s.id] = r[s.id] || ""; else delete r[s.id]; set("removed", r); };
  // the ADM cycle to choose a phase from (owner, 7 Nov 2026): steps kept and documents chosen per phase (C holds C-D and C-A)
  const wheelStats = {};
  lib.phases.forEach((p) => {
    const k = p.code.startsWith("C") ? "C" : p.code;
    const w = wheelStats[k] || (wheelStats[k] = { steps: 0, done: 0, items: 0, docs: 0 });
    const st = lib.steps.filter((x) => x.phase === p.code);
    w.steps += st.length; w.done += st.filter((x) => !(x.id in d.removed)).length + d.own_steps.filter((x) => x.phase === p.code).length;
    const its = lib.items.filter((i) => i.phase === p.code);
    w.items += its.length; w.docs += its.filter((i) => d.picks[i.id]).length + d.own_items.filter((i) => i.phase === p.code && i.name.trim()).length;
  });
  return (
    <div>
      <div className="phase-wheel-layout">
      <div className="phase-wheel-side">
        <AdmWheel choosing stats={wheelStats} selected={subPhases("C").includes(phase) ? "C" : phase === "X" ? "" : phase} onSelect={setPhase} />
        <p className="small quiet">Click a phase on the cycle (or use the tabs). The ring shows the steps kept; the count, the documents chosen.</p>
      </div>
      <div className="phase-wheel-main">
      <div className="tabs sub" role="tablist">
        {lib.phases.map((p) => {
          const n = lib.items.filter((i) => i.phase === p.code && d.picks[i.id]).length;
          const r = lib.steps.filter((s) => s.phase === p.code && s.id in d.removed).length;
          return <button key={p.code} className={`tab${p.code === phase ? " on" : ""}`} onClick={() => setPhase(p.code)} title={p.name}>
            {p.code}<span className="small quiet"> {n}{r ? ` · −${r}` : ""}</span></button>;
        })}
      </div>
      <div className="tab-panel">
        <h3 style={{ marginTop: 0 }}>{ph?.name}</h3>
        {ph?.objectives && <p className="small quiet" style={{ whiteSpace: "pre-line" }}>{ph.objectives}</p>}
        <div className="tabs sub wz-part" role="tablist">
          <button className={`tab${part === "steps" ? " on" : ""}`} onClick={() => setPart("steps")}>Steps <span className="small quiet">{steps.length - steps.filter((s) => s.id in d.removed).length + own.length}</span></button>
          <button className={`tab${part === "docs" ? " on" : ""}`} onClick={() => setPart("docs")}>Documents <span className="small quiet">{items.filter((i) => d.picks[i.id]).length + ownItems.filter((i) => !i.removed).length}</span></button>
        </div>
        {part === "steps" ? (
          <div>
            <h4>Steps <span className="quiet small">keep, remove (it stays crossed out with your reason) or add your own</span></h4>
            {!steps.length && !own.length && <p className="quiet small">No steps in the library for this part of the cycle.</p>}
            {steps.map((s) => {
              const off = s.id in d.removed;
              return (
                <div key={s.id} className={`step-row${off ? " removed" : ""}`} title={s.note || ""}>
                  <span className="step-name">{s.seq}. {s.name}</span>
                  <span className="small quiet"> {s.source === "TOGAF 10" ? "TOGAF" : s.source}{s.marking && s.marking !== "Kept" ? ` · ${s.marking}` : ""}</span>
                  <button className="linkish" onClick={() => removeStep(s, !off)}>{off ? "Keep" : "Remove"}</button>
                  {off && <input className="why" aria-label="Why it is removed" placeholder="Why it is removed (required)" value={d.removed[s.id]}
                    onChange={(e) => set("removed", { ...d.removed, [s.id]: e.target.value })} />}
                </div>
              );
            })}
            {own.map((s) => {
              const i = d.own_steps.indexOf(s);
              return (
                <div key={i} className="step-row own">
                  <input value={s.name} placeholder="Your own step" onChange={(e) => set("own_steps", d.own_steps.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                  <button className="linkish" onClick={() => set("own_steps", d.own_steps.filter((_x, j) => j !== i))}>Remove</button>
                </div>
              );
            })}
            <button onClick={() => set("own_steps", [...d.own_steps, { phase, name: "" }])}>+ Add your own step</button>
          </div>
        ) : <PhaseDocuments d={d} set={set} lib={lib} phase={phase} items={items} ownItems={ownItems} />}
      </div>
      </div>
      </div>
    </div>
  );
}

function KindBtn({ k, onChange }) {
  return (
    <button className={`kind-toggle ${k === "Deliverable" ? "del" : "art"}`} title={`${k}: click to change (a deliverable is signed off)`}
      onClick={() => onChange(k === "Deliverable" ? "Artifact" : "Deliverable")}>{k === "Deliverable" ? "D" : "A"}</button>
  );
}

// where a document type sits in the content framework: its chosen areas, or (quieter) its default ones
function WzAreas({ value, dflt, onSave }) {
  return (
    <div className="wz-areas">
      <AreaChips codes={value.length ? value : dflt} dflt={!value.length} small />
      <AreaPicker value={value} dflt={dflt} label="Change…" resetLabel={value.length ? "Back to its default" : ""} onSave={onSave} />
    </div>
  );
}

// A phase's documents in the wizard (owner, 8 Nov 2026): a table of the document types added to the project, each with
// D or A, a description, its templates (each showing the library it is from; none: a blank one) and where it sits in
// the content framework (one area or several); below, the document types not added, to add later.
function PhaseDocuments({ d, set, lib, phase, items, ownItems }) {
  const [ftype, setFtype] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => { setFtype(""); setQ(""); }, [phase]);     // a filter chosen in one phase is not carried to the next
  const tType = (t) => fileType(t.file_name || t.name);
  const phaseTypes = [...new Set(items.flatMap((i) => offeredTpl(d, lib, i).map(tType)).filter(Boolean))].sort();
  const hit = (i) => (!q.trim() || `${i.name} ${i.type || ""}`.toLowerCase().includes(q.trim().toLowerCase()))
    && (!ftype || offeredTpl(d, lib, i).some((t) => tType(t) === ftype));
  const added = items.filter((i) => d.picks[i.id] && hit(i));
  const notAdded = items.filter((i) => !d.picks[i.id] && hit(i));
  const libs = lib.libraries.filter((l) => l.usable || d.libraries.includes(l.id));
  const useLib = (t) => { if (t.library && !d.libraries.includes(t.library)) set("libraries", [...d.libraries, t.library]); };
  // a library document type
  const tplsOf = (i) => chosenTpl(d, lib, i);
  function setTpls(i, list) {
    set("templates", { ...d.templates, [i.id]: list.map((t) => t.id) });
    set("placeholders", { ...d.placeholders, [i.id]: list.length === 0 });
  }
  const addTpl = (i, t) => { useLib(t); if (!tplsOf(i).some((x) => x.id === t.id)) setTpls(i, [...tplsOf(i), t]); };
  const pick = (ids, on) => set("picks", { ...d.picks, ...Object.fromEntries(ids.map((id) => [id, on])) });
  function chooseType() {      // with a file type chosen: add these, with only their templates of that type
    pick(notAdded.map((i) => i.id).concat(added.map((i) => i.id)), true);
    set("templates", { ...d.templates, ...Object.fromEntries([...added, ...notAdded].map((i) => [i.id, offeredTpl(d, lib, i).filter((t) => tType(t) === ftype).map((t) => t.id)])) });
    set("placeholders", { ...d.placeholders, ...Object.fromEntries([...added, ...notAdded].map((i) => [i.id, false])) });
  }
  // the project's own document types
  const updOwn = (it, k, v) => set("own_items", d.own_items.map((x) => (x === it ? { ...x, [k]: v } : x)));
  const ownTpls = (it) => (it.templates || []).map((id) => (lib.template_index || {})[String(id)] || { id, name: `template ${id}`, library_name: "" });
  const shownOwn = ownItems.filter((it) => !q.trim() || (it.name || "").toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <div>
      <div className="row-gap small wz-doc-tools">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a document type" aria-label="Find a document type" />
        {(phaseTypes.length > 0 || ftype) && <label>File type <select value={ftype} onChange={(e) => setFtype(e.target.value)}>
          <option value="">all</option>{phaseTypes.map((t) => <option key={t} value={t}>{t}</option>)}</select></label>}
        {ftype ? <button className="linkish" onClick={chooseType}>Add these ({added.length + notAdded.length}, only their .{ftype} templates)</button>
          : <><button className="linkish" onClick={() => pick(notAdded.map((i) => i.id), true)} disabled={!notAdded.length}>Add all</button>
            <button className="linkish" onClick={() => pick(added.map((i) => i.id), false)} disabled={!added.length}>Take all out</button></>}
        <span className="quiet">D deliverable (signed off), A artifact: click to change.</span>
      </div>
      <table className="grid-table wz-docs">
        <thead><tr><th>Document type</th><th title="Deliverable or artifact">D/A</th><th>Description</th><th>Templates (library › file)</th><th>Content framework</th><th /></tr></thead>
        <tbody>
          {!added.length && !shownOwn.length && <tr><td colSpan={6} className="quiet small">No document type added{q || ftype ? " matches" : " in this phase yet"}: add one from <i>Templates/documents not in use</i> below, or one of your own.</td></tr>}
          {added.map((i) => (
            <tr key={i.id}>
              <td title={(i.sources || []).map((x) => `${x.source}: ${x.name}${x.files ? ` (${x.files})` : ""}`).join("\n")}><b>{i.name}</b>
                {i.type && <div className="small quiet">{i.type}</div>}</td>
              <td><KindBtn k={kindOf(d, i)} onChange={(k) => set("kinds", { ...d.kinds, [i.id]: k })} /></td>
              <td><textarea rows={2} className="wz-desc" value={d.notes?.[i.id] ?? ""} placeholder={i.description || "What this document holds"}
                onChange={(e) => set("notes", { ...(d.notes || {}), [i.id]: e.target.value })} aria-label={`Description of ${i.name}`} /></td>
              <td><TemplatesCell tpls={tplsOf(i)} offered={offeredTpl(d, lib, i)} libs={libs}
                onRemove={(t) => setTpls(i, tplsOf(i).filter((x) => x.id !== t.id))} onAdd={(t) => addTpl(i, t)} /></td>
              <td><WzAreas value={areaList(d.areas?.[i.id])} dflt={i.areas || []} onSave={(list) => set("areas", { ...(d.areas || {}), [i.id]: areaText(list) })} /></td>
              <td><button className="linkish small" title="Take it out of the project: it moves to Templates/documents not in use (in as not_for_use)" onClick={() => pick([i.id], false)}>Take out</button></td>
            </tr>
          ))}
          {shownOwn.map((it) => (
            <tr key={`own${d.own_items.indexOf(it)}`} className={`wz-own${it.removed ? " off" : ""}`}>
              <td><input value={it.name} placeholder="Your own document type" onChange={(e) => updOwn(it, "name", e.target.value)} aria-label="Name of your own document type" />
                <div className="small quiet">of the project's own</div>
                {!it.id && <input className="small" value={it.documents || ""} placeholder="Documents in it, file later (comma separated)" title="Each name becomes a document with no file yet; add its file later"
                  onChange={(e) => updOwn(it, "documents", e.target.value)} />}</td>
              <td><KindBtn k={it.kind} onChange={(k) => updOwn(it, "kind", k)} /></td>
              <td><textarea rows={2} className="wz-desc" value={it.note || ""} placeholder="What this document holds" onChange={(e) => updOwn(it, "note", e.target.value)} aria-label="Description" /></td>
              <td><TemplatesCell tpls={ownTpls(it)} offered={[]} libs={libs}
                onRemove={(t) => updOwn(it, "templates", (it.templates || []).filter((x) => x !== t.id))}
                onAdd={(t) => { useLib(t); if (!(it.templates || []).includes(t.id)) updOwn(it, "templates", [...(it.templates || []), t.id]); }} /></td>
              <td><WzAreas value={areaList(it.areas)} dflt={[]} onSave={(list) => updOwn(it, "areas", areaText(list))} /></td>
              <td>{it.id ? <label className="small" title="Kept, but not used: wizards take nothing away"><input type="checkbox" checked={!!it.removed} onChange={(e) => updOwn(it, "removed", e.target.checked)} /> not_for_use</label>
                : <button className="linkish small" onClick={() => set("own_items", d.own_items.filter((x) => x !== it))}>Remove</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={() => set("own_items", [...d.own_items, { phase, name: "", kind: "Deliverable", placeholder: true, documents: "", templates: [], note: "", areas: "" }])}>
        + Add a document type of your own</button>
      <details className="wz-not-added" open={notAdded.length > 0 && notAdded.length <= 8}>
        <summary><b>Templates/documents not in use</b> <span className="quiet small">{notAdded.length} document type{notAdded.length === 1 ? "" : "s"} of the library for this phase:
          they come in as not_for_use, and can be added at any time</span></summary>
        {!notAdded.length ? <p className="quiet small">Every document type of this phase is added{q || ftype ? " (of those that match)" : ""}.</p> : (
          <table className="grid-table small">
            <tbody>
              {notAdded.map((i) => (
                <tr key={i.id}>
                  <td>{i.name}{i.type && <span className="quiet"> · {i.type}</span>}</td>
                  <td><span className={`kind-toggle ${kindOf(d, i) === "Deliverable" ? "del" : "art"}`}>{kindOf(d, i) === "Deliverable" ? "D" : "A"}</span></td>
                  <td className="quiet">{i.description}</td>
                  <td className="quiet">{offeredTpl(d, lib, i).length ? `${offeredTpl(d, lib, i).length} template${offeredTpl(d, lib, i).length === 1 ? "" : "s"}` : "no template"}</td>
                  <td><button className="linkish" onClick={() => pick([i.id], true)}>＋ Add</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </details>
    </div>
  );
}

// The wizard's Charter step (owner, 8 Nov 2026): the architecture charter, starting from the Organisation base's (a
// new project) or the project's own (editing); each section changed here is kept, a draft until it is approved on the
// project's Charter tab.
function CharterStep({ d, set, lib, editId }) {
  const { data, error } = useApi(`/api/v1/projects/${editId || lib.org_base}/charter`);
  const [open, setOpen] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading the charter…</p>;
  const mine = d.charter || {};
  const val = (s) => (s.key in mine ? mine[s.key] : s.html);
  return (
    <div>
      <p className="quiet">The project's architecture charter: why it does architecture, its scope and authority, how it is governed, the
        principles and standards it applies, its roles, method and how compliance is checked. It starts from {editId ? "the project's charter" : "the Organisation base's charter"};
        change any section here. It is a draft until a Project Admin or Lead Architect approves it on the project's Charter tab.</p>
      {data.sections.map((s) => (
        <section key={s.key} className="charter-section">
          <h4>{s.title} {s.key in mine && <span className="chip small">changed</span>}{" "}
            <button className="linkish small" onClick={() => setOpen(open === s.key ? "" : s.key)}>{open === s.key ? "Done" : "✎ Change"}</button>
            {s.key in mine && <button className="linkish small" onClick={() => { const n = { ...mine }; delete n[s.key]; set("charter", n); }}>Undo</button>}</h4>
          {open === s.key ? <RichText value={val(s)} onChange={(v) => set("charter", { ...mine, [s.key]: v })} />
            : (val(s) ? <div className="rich-view" dangerouslySetInnerHTML={{ __html: val(s) }} /> : <p className="quiet small">Empty.</p>)}
        </section>
      ))}
    </div>
  );
}

function People({ d, set, lib, me, live }) {
  // editing as the Lead Architect (not the Project Admin): their own rows are in the list, as they are
  const admin = !live || (live.my_roles || []).includes("project-admin");
  const [people, setPeople] = useState([]);
  const [search, setSearch] = useState("");
  useEffect(() => {
    const t = setTimeout(() => apiFetch(`/api/v1/people${search ? `?search=${encodeURIComponent(search)}` : ""}`).then(setPeople).catch(() => setPeople([])), 250);
    return () => clearTimeout(t);
  }, [search]);
  const upd = (i, k, v) => set("members", d.members.map((m, j) => (j === i ? { ...m, [k]: v } : m)));
  const everyone = [...new Set([me, ...d.members.map((m) => m.username.trim().toLowerCase())].filter(Boolean))];
  const phases = Object.keys(d.signoff);
  const toggleSign = (ph, u) => {
    const cur = d.signoff[ph] || [];
    set("signoff", { ...d.signoff, [ph]: cur.includes(u) ? cur.filter((x) => x !== u) : [...cur, u] });
  };
  return (
    <div>
      <p className="quiet">{admin ? "You are the project's Project Admin. " : `You change this project as its ${(live.my_roles || []).map((r) => lib.roles.find((x) => x.code === r)?.name || r).join(" and ")}. `}Project Admin and Lead Architect run the setup and the people;
        Architects, Model Admins and Model Sub Admins contribute too; Stakeholders read, and approve or reject what they sign off.</p>
      <datalist id="people-list">{(people || []).map((p) => <option key={p.username} value={p.username}>{p.name || p.username}</option>)}</datalist>
      <table className="grid-table">
        <thead><tr><th>Person</th><th>Project role</th><th /></tr></thead>
        <tbody>
          {admin && <tr><td><b>{me}</b> (you)</td><td>Project Admin</td><td /></tr>}
          {d.members.map((m, i) => (
            <tr key={i}>
              <td><input list="people-list" aria-label="Person's user name" value={m.username} onChange={(e) => { upd(i, "username", e.target.value); setSearch(e.target.value); }} placeholder="user name" /></td>
              <td><select aria-label="Project role" value={m.role} onChange={(e) => upd(i, "role", e.target.value)}>{lib.roles.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}</select></td>
              <td><button className="linkish" onClick={() => set("members", d.members.filter((_x, j) => j !== i))}>Remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={() => set("members", [...d.members, { username: "", role: "architect" }])}>+ Add a person</button>
      <h3>Who approves documents</h3>
      <p className="quiet small">One set for the whole project; add a set for a phase where it differs. When a document is sent for approval they are
        told in the application, and approve or reject it (with comments). Anyone on the project can also accept a document directly, with evidence.</p>
      <table className="grid-table">
        <thead><tr><th>Applies to</th>{everyone.map((u) => <th key={u}>{u}</th>)}<th /></tr></thead>
        <tbody>
          {phases.map((ph) => (
            <tr key={ph || "all"}>
              <td>{ph ? lib.phases.find((p) => p.code === ph)?.name || ph : "The whole project"}</td>
              {everyone.map((u) => <td key={u}><input type="checkbox" checked={(d.signoff[ph] || []).includes(u)} onChange={() => toggleSign(ph, u)} /></td>)}
              <td>{ph && <button className="linkish" onClick={() => { const s = { ...d.signoff }; delete s[ph]; set("signoff", s); }}>Remove</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <select value="" onChange={(e) => e.target.value && set("signoff", { ...d.signoff, [e.target.value]: [...(d.signoff[""] || [])] })}>
        <option value="">+ A different set for a phase...</option>
        {lib.phases.filter((p) => !(p.code in d.signoff)).map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
      </select>
      <Quorum value={d.signoff_quorum ?? ""} onChange={(v) => set("signoff_quorum", v)} />
    </div>
  );
}

function Review({ d, lib, purpose, problems }) {
  const chosen = lib.items.filter((i) => d.picks[i.id]);
  const removed = lib.steps.filter((s) => s.id in d.removed);
  const places = chosen.filter((i) => !chosenTpl(d, lib, i).length).length;
  const s = d.scope;
  return (
    <div>
      {problems.length > 0 && <ul className="status bad">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
      <table className="grid-table review">
        <tbody>
          <tr><th>Models</th><td>{d.models.map((m, i) => <div key={i}>{HOW[m.how]}: {m.label || m.name || "a model"}{m.home ? <b> (the project's model)</b> : ""}</div>)}</td></tr>
          <tr><th>Name</th><td>{d.name}</td></tr>
          <tr><th>Purpose</th><td>{purpose}</td></tr>
          <tr><th>Scope</th><td>{[s.breadth, DEPTHS.find(([k]) => k === s.depth)?.[1], s.start && `${s.start} to ${s.end || "?"}`, s.horizon, s.domains.join(", ")].filter(Boolean).join(" · ") || <span className="quiet">not set</span>}</td></tr>
          <tr><th>Goals and outcomes</th><td>{d.goals.filter((g) => g.name.trim()).map((g) => <div key={g.name}>{g.name}: {g.outcomes.filter((o) => o.name.trim()).map((o) => o.name).join("; ") || <span className="quiet">no outcome</span>}</div>)}{!d.goals.length && <span className="quiet">none</span>}</td></tr>
          <tr><th>Sponsor</th><td>{d.sponsor.name ? `${d.sponsor.name}${d.sponsor.role ? `, ${d.sponsor.role}` : ""}` : <span className="quiet">not named</span>}{d.sponsor.asks.length ? ` · ${d.sponsor.asks.length} asks` : ""}</td></tr>
          <tr><th>Notes and files</th><td>{d.notes_html ? "notes written" : <span className="quiet">no notes</span>}{d.files.length ? ` · ${d.files.length} files to upload` : ""}</td></tr>
          <tr><th>Template libraries</th><td>{d.libraries.map((id) => lib.libraries.find((l) => l.id === id)?.name).filter(Boolean).join(", ") || <span className="quiet">none</span>}</td></tr>
          <tr><th>Viewpoints</th><td>{d.viewpoints.join(", ") || <span className="quiet">none</span>}{d.own_viewpoints.filter((v) => v.name.trim()).length ? ` + ${d.own_viewpoints.filter((v) => v.name.trim()).length} of its own` : ""}</td></tr>
          <tr><th>Charter</th><td>{Object.keys(d.charter || {}).length ? `${Object.keys(d.charter).length} section${Object.keys(d.charter).length === 1 ? "" : "s"} changed` : <span className="quiet">as the base's</span>} (a draft until approved)</td></tr>
          <tr><th>Principles</th><td>{d.principles.length} from the library, {d.own_principles.filter((p) => p.name.trim()).length + d.existing_principles.length} of its own</td></tr>
          <tr><th>Steps</th><td>{lib.steps.length - removed.length} kept, {removed.length} removed (crossed out), {d.own_steps.filter((x) => x.name.trim()).length} of its own</td></tr>
          <tr><th>Deliverables and artifacts</th><td>{chosen.length} chosen ({chosen.filter((i) => kindOf(d, i) === "Deliverable").length} deliverables,{" "}
            {chosen.filter((i) => kindOf(d, i) === "Artifact").length} artifacts; {places} blank, with no template), {lib.items.length - chosen.length} as not_for_use, {d.own_items.filter((i) => i.name.trim()).length} of its own</td></tr>
          <tr><th>People</th><td>you (Project Admin){d.members.filter((m) => m.username.trim()).map((m) => `, ${m.username} (${ROLE_NAMES[m.role]})`).join("")}</td></tr>
          <tr><th>Sign-off</th><td>{Object.entries(d.signoff).map(([ph, us]) => <div key={ph}>{ph || "Whole project"}: {us.join(", ") || <span className="quiet">nobody yet</span>}</div>)}</td></tr>
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- one project: its landing page (D279) and tabs
// gap analysis, comparison and common analysis on one tab (owner, 8 Nov 2026); the stakeholder matrix (D294)
// the steps and the repository are on Home, phase by phase or for all phases (owner, 8 Nov 2026); Tasks, a scratchpad (D298)
// phase 13.1 (D303 to D307): Base, Charter, Standards, Governance log
const TABS = [["home", "Home"], ["phases", "Phases"], ["report", "Project report"], ["base", "Base"], ["charter", "Charter"], ["archrepo", "Enterprise Repository (Project Scope)"], ["content", "Content framework"],
  ["tasks", "Tasks"], ["models", "Models"], ["organisation", "Organisation"], ["stakeholders", "Stakeholders"], ["principles", "Principles"],
  ["standards", "Standards"], ["governance", "Governance log"], ["reference", "Reference"], ["viewpoints", "Viewpoints"], ["reports", "Model reports"], ["quality", "Quality"], ["calendar", "Calendar"], ["sheets", "Sheets"],
  ["analysis", "Gaps and comparison"], ["signoff", "Sign-off"]];

function ProjectPage({ id, tab }) {
  const { data: p, error } = useApi(`/api/v1/projects/${id}`);
  const [msg, setMsg] = useState("");
  const [finish, setFinish] = useState(false);
  useWhileBuilding(p ? [p] : []);
  if (error) return <div className="page"><p className="status bad">{error}</p><a href="#/work">Architecture work</a></div>;
  if (!p) return <div className="page"><p className="quiet">Loading...</p></div>;
  const mine = p.signoffs.filter((s) => s.mine).length;
  return (
    <div className="page">
      <div className="row-gap project-head">
        <div className="small"><a href="#/work">Architecture work</a> ›</div>
        <h2 style={{ margin: 0 }}>{p.name}</h2>
        <PinButton k="project" x={p} />
        <span className="chip on">{p.purpose}</span>{p.template && <span className="chip" title="The kind of project it was made as">{p.template.icon} {p.template.name}</span>}
        <span className="chip">ADM cycle {p.cycle}</span><StatusChip status={p.status} />
        {p.parent_name && <span className="small quiet">derived from <a href={`#/projects/${p.parent_id}`}>{p.parent_name}</a></span>}
        <span className="small">Repository: <RepoState state={p.repo_state} note={p.repo_note} /></span>
        <span className="small">Complete: <Completion c={p.completion} /></span>
        {p.is_library && <span className="chip on" title="Its reference material is offered to new projects">library project</span>}
        <span style={{ marginLeft: "auto" }} />
        {p.may_admin && !p.frozen && <a className="button" href={`#/projects/${id}/edit`} title="Change the project: the set-up wizard again">✎ Edit</a>}
        {p.may_admin && !p.frozen && <button title={p.completion?.completed_at ? "Open it again: completion goes back to its phases" : "Mark the whole project complete (it can be opened again at any time)"}
          onClick={async () => { try { const r = await apiFetch(`/api/v1/projects/${id}/complete`, { method: "POST", body: JSON.stringify({ complete: !p.completion?.completed_at }) });
            setMsg(r.message); refreshAll(); } catch (e) { setMsg(e.message); } }}>{p.completion?.completed_at ? "↺ Reopen the project" : "✔ Mark the project complete"}</button>}
        {p.may_finish && <button onClick={() => setFinish(true)}>Finish the project…</button>}
        {(p.may_admin || p.my_roles.includes("super-admin")) && <a className="button" href={`#/project-admin/${id}`}
          title="Project admin: every project wizard for this project">⚙ Project wizards</a>}
      </div>
      {msg && <p className="small quiet">{msg}</p>}
      {p.frozen && <div className="lock-banner">{p.status === "merged" ? <>Merged into <a href={`#/projects/${p.merged_into?.id}`}>{p.merged_into?.name}</a></> : "Frozen"}
        {" "}on {fmtDateTime(p.finished_at)} by {p.finished_by}: read only. {p.finish_note}</div>}
      <BaseBanner p={p} />
      <RepoHelp p={p} onRebuild={p.may_admin && !p.frozen ? async () => {
        try { const r = await apiFetch(`/api/v1/projects/${id}/repository`, { method: "POST" }); setMsg(r.message); setTimeout(refreshAll, 4000); }
        catch (e) { setMsg(e.message); }
      } : null} />
      <div className="tabs" role="tablist">
        {TABS.filter(([k]) => (k !== "archrepo" || partOn("repository")) && (k !== "reference" || partOn("references"))).map(([k, l]) => <a key={k} href={`#/projects/${id}/${k}`} className={`tab${tab === k ? " on" : ""}`}>{l}{k === "signoff" && mine ? ` (${mine})` : ""}</a>)}
      </div>
      <div className="tab-panel">
        {["home", "about", "overview"].includes(tab) && <Landing p={p} />}
        {["phases", "repository", "steps"].includes(tab) && <PhasesTab key={tab} p={p} start={tab === "steps" ? "steps" : "documents"} />}
        {tab === "steps" && <StepsTab p={p} />}
        {tab === "signoff" && <SignoffTab p={p} />}
        {tab === "principles" && <PrinciplesTab p={p} />}
        {tab === "viewpoints" && <ViewpointsByPhase p={p} />}
        {tab === "reports" && <ProjectReports p={p} part="models" />}
        {tab === "reference" && <ReferenceTab p={p} />}
        {tab === "stakeholders" && <StakeholderMatrix p={p} />}
        {tab === "tasks" && <TasksTab p={p} />}
        {tab === "content" && <ContentFrameworkTab p={p} />}
        {tab === "archrepo" && <RepositoryMap p={p} />}
        {tab === "organisation" && <ProjectOrgTab p={p} />}
        {tab === "base" && <BaseTab p={p} />}
        {tab === "report" && <ProjectReports p={p} part="project" />}
        {tab === "charter" && <CharterTab p={p} />}
        {tab === "standards" && <StandardsTab p={p} />}
        {tab === "governance" && <GovernanceTab p={p} />}
        {tab === "quality" && <ProjectQuality p={p} />}
        {tab === "calendar" && <CalendarView cal={p.id} />}
        {tab === "sheets" && <TrackingSheets scope={p.id} />}
        {tab === "models" && <ProjectModels p={p} />}
        {["analysis", "gaps", "compare"].includes(tab) && <AnalysisTab p={p} start={tab} />}
      </div>
      {finish && <FinishDialog p={p} onClose={() => setFinish(false)} />}
    </div>
  );
}

function phaseStats(p) {
  const out = {};
  const ring = (code) => (code === "C-D" || code === "C-A" ? "C" : code);
  p.steps.filter((s) => !s.removed && !s.parent).forEach((s) => { const k = ring(s.phase); out[k] = out[k] || { steps: 0, done: 0, items: 0, docs: 0 }; out[k].steps += 1; if (s.done_at) out[k].done += 1; });
  const itemPhase = {};
  p.items.filter((i) => i.chosen).forEach((i) => { const k = ring(i.phase); itemPhase[i.id] = k; out[k] = out[k] || { steps: 0, done: 0, items: 0, docs: 0 }; out[k].items += 1; });
  p.documents.forEach((d) => { const k = itemPhase[d.item_id]; if (k) out[k].docs += 1; });
  return out;
}

// gap analyses, comparison and common analyses on one tab, each a sub-tab (owner, 8 Nov 2026)
function AnalysisTab({ p, start }) {
  const [part, setPart] = useState(start === "compare" ? "compare" : "gaps");
  const parts = [["gaps", "Gap analyses"], ["compare", "Compare two models"], ["common", "Common analyses"]];
  return (
    <div>
      <div className="tabs sub" role="tablist">
        {parts.map(([k, l]) => <button key={k} role="tab" aria-selected={part === k} className={`tab${part === k ? " on" : ""}`} onClick={() => setPart(k)}>{l}</button>)}
      </div>
      {part === "gaps" && <ProjectGaps p={p} />}
      {part !== "gaps" && <ProjectCompare p={p} part={part} />}
    </div>
  );
}

// the project's models on a tab of their own (owner, 8 Nov 2026)
function ProjectModels({ p }) {
  return (
    <div>
      <p className="quiet">The models this project works on or refers to: each one's role in the project, what kind of model it is and how it joined.
        Open one to work in it (data entry, grids, diagrams, viewpoints, reports).</p>
      {p.may_admin && !p.frozen && <p><a className="button primary" href={`#/projects/${p.id}/edit?step=Models`}>＋ Add or make a model</a></p>}
      {!p.models.length ? <p className="quiet">No models yet.</p> : (
        <table className="grid-table">
          <thead><tr><th>Model</th><th>Role in the project</th><th>Kind of model</th><th>How it joined</th><th /></tr></thead>
          <tbody>
            {p.models.map((m) => (
              <tr key={m.id}>
                <td><a href={`#/metamodel/${m.id}`}><b>{m.name}</b></a>{m.id === p.home_model && <div className="small"><span className="chip on">primary working model</span> its goals and outcomes live here</div>}</td>
                <td>{m.role ? <span className="chip">{ROLE_NAMES_M[m.role]}{m.role_seq ? ` ${m.role_seq}` : ""}</span> : <span className="quiet">–</span>}</td>
                <td><OriginChip m={m} /></td>
                <td className="small">{HOW[m.how] || m.how}</td>
                <td className="small nowrap"><a href={`#/metamodel/${m.id}`}>Open</a>{" · "}<a href={`#/model-admin/${m.id}`}>Model admin</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// Home (owner, 8 Nov 2026): the ADM cycle and About. A phase clicked on the cycle shows how far it is, with a button to
// open it on the Phases tab, where its documents, steps and viewpoints are.
function Landing({ p }) {
  const stats = useMemo(() => phaseStats(p), [p]);
  const [sel, setSel] = useState(() => (p.phases.find((ph) => ph.code === "A") ? "A" : p.phases[0]?.code));
  const ph = p.phases.find((x) => x.code === sel);
  const codes = subPhases(sel);
  const steps = p.steps.filter((s) => codes.includes(s.phase) && !s.removed && !s.parent);
  const classes = p.items.filter((i) => i.chosen && codes.includes(i.phase));
  const docs = p.documents.filter((d) => classes.some((i) => i.id === d.item_id));
  const empty = classes.filter((i) => !docs.some((d) => d.item_id === i.id)).length;
  return (
    <div className="landing">
      <div className="landing-wheel">
        <AdmWheel stats={stats} selected={sel} onSelect={setSel} />
        <div className="phase-card">
          <h3>{sel === "C" ? "Phase C: Information Systems Architecture (data and application)" : sel === "X" ? "Across the cycle (repository-wide)" : ph?.name}</h3>
          {sel !== "X" && <PhaseDone p={p} codes={codes} />}
          <p className="small">{steps.filter((s) => s.done_at).length} of {steps.length} steps done · {classes.length} document classes ·
            {" "}{docs.length} documents{empty ? ` · ${empty} class${empty === 1 ? "" : "es"} with no document yet` : ""}</p>
          <div className="row-gap">
            <a className="button primary" href={`#/projects/${p.id}/phases?phase=${sel}`}>Open {sel === "X" ? "across the cycle" : `phase ${sel}`} →</a>
            <button className="linkish small" onClick={() => setSel("X")}>Across the cycle</button>
          </div>
        </div>
        <p className="small">The whole project: <Completion c={p.completion} wide /></p>
        <p className="small"><a href={`#/projects/${p.id}/models`}>{p.models.length} model{p.models.length === 1 ? "" : "s"} →</a></p>
      </div>
      <div className="landing-phase"><About p={p} /></div>
    </div>
  );
}

// The Phases tab (owner, 8 Nov 2026): a tab for each phase (and across the cycle); in each, its Documents, the document
// classes Not added to the project, its Steps and its Viewpoints.
function PhasesTab({ p, start = "documents" }) {
  const qs = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const pick = qs.get("phase");
  const [sel, setSelState] = useState(() => (pick && pick !== "*" ? pick : (p.phases.find((ph) => ph.code === "A") ? "A" : p.phases[0]?.code)));
  const [part, setPart] = useState(start === "steps" ? "steps" : "documents");
  const setSel = (c) => { setSelState(c); window.history.replaceState(null, "", `#/projects/${p.id}/phases?phase=${c}`); };
  const ph = p.phases.find((x) => x.code === sel);
  const codes = subPhases(sel);
  const steps = p.steps.filter((s) => codes.includes(s.phase));
  const notAdded = p.items.filter((i) => !i.chosen && codes.includes(i.phase));
  const nDocs = p.documents.filter((d) => p.items.some((i) => i.id === d.item_id && i.chosen && codes.includes(i.phase))).length;
  const vps = p.viewpoints.filter((v) => codes.includes(v.phase)).length;
  const loose = p.documents.filter((d) => !d.item_id && !d.folder.startsWith("00_Project") && !d.folder.startsWith("05_Reference_Library")
    && ph && d.folder.startsWith(ph.workspace));
  // the phase tabs: C's two parts sit under one C tab
  const tabs = p.phases.filter((x) => x.code !== "C-A" && x.code !== "C-D").map((x) => x.code);
  if (p.phases.some((x) => x.code === "C-D" || x.code === "C-A") && !tabs.includes("C")) {
    const at = p.phases.findIndex((x) => x.code === "C-D" || x.code === "C-A");
    tabs.splice(Math.min(at, tabs.length), 0, "C");
  }
  const shortName = (n) => (n || "").replace(/^(Phase [^:]+|[^:]+ Phase|Preliminary[^:]*):\s*/i, "").replace(/ Architecture$| Management$/, "");
  const label = (c) => (c === "X" ? "Across the cycle" : c === "C" ? "C · Information Systems"
    : `${c} · ${shortName(p.phases.find((x) => x.code === c)?.name) || c}`);
  const nameOf = (c) => (c === "C" ? "Phase C: Information Systems Architecture" : p.phases.find((x) => x.code === c)?.name || c);
  return (
    <div>
      <div className="tabs phase-tabs" role="tablist">
        {tabs.map((c) => {
          const n = p.items.filter((i) => i.chosen && subPhases(c).includes(i.phase)).length;
          return <button key={c} role="tab" aria-selected={sel === c} className={`tab${sel === c ? " on" : ""}`} title={nameOf(c)} onClick={() => setSel(c)}>
            {label(c)} <span className="small quiet">{n}</span></button>;
        })}
      </div>
      <div className="tab-panel">
        <h3 style={{ marginTop: 0 }}>{sel === "C" ? "Phase C: Information Systems Architecture (data and application)" : sel === "X" ? "Across the cycle (repository-wide)" : ph?.name}
          {sel !== "X" && <PhaseDone p={p} codes={codes} />}</h3>
        <div className="tabs sub" role="tablist">
          <button role="tab" aria-selected={part === "documents"} className={`tab${part === "documents" ? " on" : ""}`} onClick={() => setPart("documents")}>
            Documents <span className="small quiet">{nDocs}</span></button>
          <button role="tab" aria-selected={part === "notadded"} className={`tab${part === "notadded" ? " on" : ""}`} onClick={() => setPart("notadded")}>
            Templates/documents not in use <span className="small quiet">{notAdded.length}</span></button>
          <button role="tab" aria-selected={part === "steps"} className={`tab${part === "steps" ? " on" : ""}`} onClick={() => setPart("steps")}>
            Steps <span className="small quiet">{steps.filter((s) => !s.removed && !s.parent && s.done_at).length} of {steps.filter((s) => !s.removed && !s.parent).length} done</span></button>
          <button role="tab" aria-selected={part === "viewpoints"} className={`tab${part === "viewpoints" ? " on" : ""}`} onClick={() => setPart("viewpoints")}>
            Viewpoints <span className="small quiet">{vps}</span></button>
        </div>
        {part === "documents" && <section>
          <RepoTable key={sel} p={p} codes={codes} phase={sel} />
          {loose.length > 0 && <>
            <h4>Other documents in this phase's folders</h4>
            {loose.map((d) => <div key={d.id} className="repo-doc small">{d.is_link ? <LinkName d={d} /> : d.no_file ? <span>📝 {d.title} <span className="chip small">no file yet</span></span>
              : <button className="linkish" onClick={() => apiDownload(`/api/v1/projects/${p.id}/documents/${d.id}`, d.file_name).catch(() => {})}>📄 {d.title || d.file_name}</button>} <span className="quiet">{d.folder}</span></div>)}
          </>}
        </section>}
        {part === "notadded" && <NotAddedClasses p={p} list={notAdded} />}
        {part === "steps" && <section>
          <StepList p={p} list={steps} phase={sel === "X" ? "" : sel} />
          {!steps.length && <p className="quiet small">No steps in this part of the cycle.</p>}
        </section>}
        {part === "viewpoints" && <section>{sel === "X" ? <ViewpointList p={p} /> : <ViewpointsByPhase p={p} fixed={codes[0]} />}</section>}
      </div>
    </div>
  );
}

// the document classes of a phase not added to the project (owner, 8 Nov 2026): each can be added at any time
function NotAddedClasses({ p, list }) {
  const [msg, setMsg] = useState("");
  const can = p.may_contribute && !p.frozen;
  async function add(i) {
    setMsg("");
    try { const r = await apiFetch(`/api/v1/projects/${p.id}/items/${i.id}/not-needed`, { method: "POST", body: JSON.stringify({ undo: true }) }); setMsg(r.message); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  if (!list.length) return <p className="quiet">Every document class of this phase is in the project.</p>;
  return (
    <div>
      <p className="small quiet">Document classes of this phase that are not in the project: left out when it was set up, or marked "won't need"
        (their documents are kept). Bring one back at any time; adding a document to it brings it back too.</p>
      {msg && <p className="small status">{msg}</p>}
      <table className="grid-table repo-classes">
        <thead><tr><th>Document class</th><th>Type</th><th>Why it is not in</th><th>Documents</th><th /></tr></thead>
        <tbody>{list.map((i) => (
          <tr key={i.id}><td><b>{i.name}</b>{i.type && <span className="small quiet"> {i.type}</span>}</td>
            <td><span className={`kind-toggle ${kindClass(i.kind)}`} title={i.kind}>{kindLetter(i.kind)}</span></td>
            <td className="small">{i.not_needed_reason ? <>{i.not_needed_reason}<div className="quiet">{i.not_needed_by} · {fmtDateTime(i.not_needed_at)}</div></> : <span className="quiet">not chosen when the project was set up</span>}</td>
            <td className="small">{i.documents ? <>{i.documents} kept<div className="quiet">bring the class back to work in them</div></> : <span className="quiet">none</span>}</td>
            <td>{can && <button className="linkish" onClick={() => add(i)}>{i.not_needed_by ? "↺ Bring it back" : "＋ Add it to the project"}</button>}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

// a phase marked complete, or open again, by anyone who contributes (owner, 8 Nov 2026); phase C is C-D and C-A
function PhaseDone({ p, codes }) {
  const [msg, setMsg] = useState("");
  const have = codes.filter((c) => p.steps.some((s) => s.phase === c));
  const list = have.length ? have : codes;
  const done = list.length > 0 && list.every((c) => p.phases_done?.[c]);
  const can = p.may_contribute && !p.frozen;
  async function go() {
    try {
      let r;
      for (const c of list) r = await apiFetch(`/api/v1/projects/${p.id}/phases/${c}`, { method: "POST", body: JSON.stringify({ complete: !done }) });
      setMsg(r?.message || ""); refreshAll();
    } catch (e) { setMsg(e.message); }
  }
  const by = list.map((c) => p.phases_done?.[c]).find(Boolean);
  return (
    <span className="phase-done small">
      {done ? <span className="rag green" title={by ? `by ${by.by}, ${fmtDateTime(by.at)}` : ""}>✔ phase complete</span> : <span className="rag off">open</span>}
      {can && <button className="linkish" onClick={go}>{done ? "Reopen the phase" : "Mark the phase complete"}</button>}
      {msg && <span className="quiet"> {msg}</span>}
    </span>
  );
}

function ViewpointList({ p }) {
  const [adding, setAdding] = useState(false);
  const [v, setV] = useState({ name: "", concerns: "", stakeholders: "", types: [] });
  const [msg, setMsg] = useState("");
  async function add() {
    setMsg("");
    try { const r = await apiFetch(`/api/v1/projects/${p.id}/viewpoints`, { method: "POST", body: JSON.stringify({ ...v, element_types: v.types }) }); setMsg(r.message); setAdding(false); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <div>
      {!p.viewpoints.length && <p className="quiet small">No viewpoints chosen.</p>}
      <ul className="vp-status">
        {p.viewpoints.map((x) => (
          <li key={x.code} className={x.state === "ready" ? "ready" : "build"}>
            <b>{x.code}</b> {x.name}{x.own && <span className="chip">project's own</span>}{" "}
            {x.state === "ready"
              ? <a href={`#/metamodel/${x.model}/viewpoints/${encodeURIComponent(x.code)}`}>Open in {x.model_name}</a>
              : <span className="small">to build: {x.missing.length ? `${x.missing.join(", ")} not in the models' metamodels` : "no model yet"}
                {x.model && <> · <a href={`#/metamodel/${x.model}/metamodel`}>add the types in {x.model_name}</a></>}</span>}
          </li>
        ))}
      </ul>
      {p.may_contribute && !adding && <button className="linkish small" onClick={() => setAdding(true)}>+ Make a viewpoint for the project</button>}
      {adding && (
        <div className="goal-box">
          <div className="own-row">
            <input placeholder="Name" value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} />
            <input placeholder="Concerns" value={v.concerns} onChange={(e) => setV({ ...v, concerns: e.target.value })} style={{ flex: 2 }} />
            <input placeholder="Stakeholders" value={v.stakeholders} onChange={(e) => setV({ ...v, stakeholders: e.target.value })} />
          </div>
          <div className="vp-checks inline small">{p.model_types.map((t) => <label key={t}><input type="checkbox" checked={v.types.includes(t)}
            onChange={() => setV({ ...v, types: v.types.includes(t) ? v.types.filter((x) => x !== t) : [...v.types, t] })} /> {t}</label>)}</div>
          <input className="wide" placeholder="Other element types to build, separated by commas" onChange={(e) => setV({ ...v,
            types: [...v.types.filter((t) => p.model_types.includes(t)), ...e.target.value.split(",").map((t) => t.trim()).filter(Boolean)] })} />
          <div className="row-gap"><button className="primary" disabled={!v.name.trim() || !v.types.length} onClick={add}>Make it</button><button onClick={() => setAdding(false)}>Cancel</button></div>
        </div>
      )}
      {msg && <p className="small">{msg}</p>}
    </div>
  );
}

function About({ p }) {
  const [edit, setEdit] = useState(false);
  const s = p.scope;
  const chosen = p.items.filter((i) => i.chosen);
  return (
    <div className="overview-grid">
      <section>
        <h3>About</h3>
        <p>{p.description || <span className="quiet">No description.</span>}</p>
        <p className="small quiet">Created {fmtDateTime(p.created_at)} by {p.created_by}. Your roles: {p.my_roles.map((r) => ROLE_NAMES[r] || r).join(", ")}.
          {p.children.length > 0 && <> Derived from it: {p.children.map((c) => <a key={c.id} href={`#/projects/${c.id}`}>{c.name} </a>)}</>}</p>
        <h3>Scope</h3>
        <table className="grid-table small"><tbody>
          <tr><th>Breadth</th><td>{s.breadth || <span className="quiet">-</span>}</td></tr>
          <tr><th>Depth</th><td>{DEPTHS.find(([k]) => k === s.depth)?.[1] || <span className="quiet">-</span>}</td></tr>
          <tr><th>Time</th><td>{s.start || "?"} to {s.end || "?"}{s.horizon ? ` · target horizon ${s.horizon}` : ""}</td></tr>
          <tr><th>Domains</th><td>{(s.domains || []).map((x) => DOMAINS.find(([k]) => k === x)?.[1]).join(", ") || <span className="quiet">-</span>}</td></tr>
          {s.notes && <tr><th>Notes</th><td style={{ whiteSpace: "pre-line" }}>{s.notes}</td></tr>}
        </tbody></table>
        <h3>Goals and outcomes</h3>
        {p.goals.map((g) => (
          <div key={g.id || g.name} className="goal-view">
            <b>{g.id && p.home_model ? <a href={`#/metamodel/${p.home_model}/entity/${g.id}`}>{g.name}</a> : g.name}</b> {g.description && <span className="small quiet">{g.description}</span>}
            <ul className="small">{g.outcomes.map((o) => <li key={o.id}><a href={`#/metamodel/${p.home_model}/entity/${o.id}`}>{o.name}</a>
              {o.measure && <span className="quiet"> · measure: {o.measure}</span>}{o.target_date && <span className="quiet"> · by {o.target_date}</span>}</li>)}</ul>
          </div>
        ))}
        {!p.goals.length && <p className="quiet small">{p.pending_goals.length ? "Being written into the project's model (its metamodel copy is still running)." : "None yet."}</p>}
        <h3>Sponsor</h3>
        {p.sponsor.name ? <p>{p.sponsor.name}{p.sponsor.role ? `, ${p.sponsor.role}` : ""}{p.sponsor.contact ? <span className="small quiet"> · {p.sponsor.contact}</span> : ""}</p> : <p className="quiet small">Not named.</p>}
        {(p.sponsor?.asks || []).length > 0 && <ul className="small">{p.sponsor.asks.map((a) => <li key={a.ask}>{a.ask}{a.by ? ` (by ${a.by})` : ""}{a.measure ? <span className="quiet"> · {a.measure}</span> : ""}</li>)}</ul>}
        {p.sponsor.notes_html && <RichText readOnly value={p.sponsor.notes_html} />}
        {p.goals_notes_html && <><h3>More about the goals</h3><RichText readOnly value={p.goals_notes_html} /></>}
        <h3>Notes</h3>
        {p.notes_html ? <RichText readOnly value={p.notes_html} /> : <p className="quiet small">None.</p>}
        <ProjectFiles p={p} />
        <h3>Template libraries</h3>
        <p>{p.libraries.map((l) => <span key={l.id} className="chip">{l.name}</span>)}{!p.libraries.length && <span className="quiet small">None.</span>}</p>
        <h3>In the repository</h3>
        <p className="small">{chosen.length} deliverables and artifacts in use ({chosen.filter((i) => i.kind === "Deliverable").length} deliverables,
          {" "}{chosen.filter((i) => i.placeholder).length} placeholders), {p.items.length - chosen.length} not_for_use, {p.documents.length} documents.</p>
      </section>
      <section>
        <div className="row-gap"><h3 style={{ margin: 0 }}>People</h3>{p.may_admin && <button className="linkish" onClick={() => setEdit(!edit)}>{edit ? "Close" : "Change"}</button>}</div>
        {edit ? <PeopleEdit p={p} onDone={() => setEdit(false)} /> : (
          <>
            <table className="grid-table small"><tbody>
              {p.members.map((m) => <tr key={`${m.username}${m.role}`}><td>{m.username}</td><td>{ROLE_NAMES[m.role] || m.role}</td></tr>)}
            </tbody></table>
            <h3>Who signs off</h3>
            {[...new Set(p.signoff.map((x) => x.phase))].map((ph) => (
              <div key={ph} className="small"><b>{ph || "Whole project"}:</b> {p.signoff.filter((x) => x.phase === ph).map((x) => x.username).join(", ")}</div>
            ))}
            {!p.signoff.length && <p className="quiet small">Nobody yet.</p>}
            {p.signoff.length > 0 && <p className="small quiet">Approved when {p.signoff_quorum ? `${p.signoff_quorum} of them` : "a majority of them"} approve; any rejection rejects it.</p>}
          </>
        )}
        <div className="row-gap"><h3 style={{ margin: 0 }}>Models</h3>{p.may_admin && <a className="small" href={`#/projects/${p.id}/edit?step=Models`}>＋ Add or make a model</a>}</div>
        {p.models.map((m) => <div key={m.id}><a href={`#/metamodel/${m.id}`}>{m.name}</a> {m.role && <span className="chip">{ROLE_NAMES_M[m.role]}{m.role_seq ? ` ${m.role_seq}` : ""}</span>} <OriginChip m={m} /> <span className="small quiet">{HOW[m.how] || m.how}{m.id === p.home_model ? " · primary working model" : ""}{m.copy_state ? ` · ${m.copy_state}` : ""}</span></div>)}
        {p.models.some((m) => m.role === "current") && p.models.some((m) => ["target", "transition", "scenario"].includes(m.role)) && (
          <p className="small"><a href={`#/projects/${p.id}/gaps`}>Gap analysis</a>: compare the current state with a target, transition or scenario (the Gaps tab).</p>)}
        <ProjectBackupPanel p={p} />
      </section>
    </div>
  );
}

function ProjectFiles({ p }) {
  const [msg, setMsg] = useState("");
  function upload() {
    const inp = document.createElement("input");
    inp.type = "file"; inp.multiple = true;
    inp.onchange = async () => {
      setMsg("");
      for (const f of inp.files) {
        const fd = new FormData(); fd.append("file", f);
        try { await apiUpload(`/api/v1/projects/${p.id}/files`, fd); } catch (e) { setMsg(e.message); }
      }
      refreshAll();
    };
    inp.click();
  }
  return (
    <>
      <div className="row-gap"><h3 style={{ margin: 0 }}>Files of the project</h3>{p.may_contribute && <button className="linkish" onClick={upload}>⬆ Add files</button>}</div>
      {p.project_files.map((f) => <div key={f.id} className="small"><button className="linkish" onClick={() => apiDownload(`/api/v1/projects/${p.id}/documents/${f.id}`, f.file_name)}>📄 {f.file_name}</button> <span className="quiet">v{f.versions} · {f.modified_by} · {fmtDateTime(f.modified_at)}</span></div>)}
      {!p.project_files.length && <p className="quiet small">None: contracts, statements of work and the like go here.</p>}
      {msg && <p className="small status bad">{msg}</p>}
    </>
  );
}

// the project's quorum (D290): how many of a phase's sign-off people must approve; empty is a majority
function Quorum({ value, onChange }) {
  return (
    <p className="small">Approved when <input type="number" aria-label="Quorum" min="1" max="50" style={{ width: 64 }} value={value} placeholder="most"
      onChange={(e) => onChange(e.target.value)} /> of the people approve <span className="quiet">(empty: a majority; never more than there are).
      Any rejection rejects it.</span></p>
  );
}

function PeopleEdit({ p, onDone }) {
  const [members, setMembers] = useState(p.members.map((m) => ({ username: m.username, role: m.role })));
  const [sign, setSign] = useState(() => { const s = {}; p.signoff.forEach((x) => { (s[x.phase] = s[x.phase] || []).push(x.username); }); if (!s[""]) s[""] = []; return s; });
  const [quorum, setQuorum] = useState(p.signoff_quorum ?? "");
  const [msg, setMsg] = useState("");
  const users = [...new Set(members.map((m) => m.username.trim().toLowerCase()).filter(Boolean))];
  async function save() {
    try { await apiFetch(`/api/v1/projects/${p.id}/people`, { method: "PUT", body: JSON.stringify({ members, signoff: sign, signoff_quorum: quorum }) }); refreshAll(); onDone(); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <div>
      {members.map((m, i) => (
        <div key={i} className="own-row">
          <input aria-label="Person's user name" value={m.username} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, username: e.target.value } : x)))} />
          <select aria-label="Project role" value={m.role} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, role: e.target.value } : x)))}>
            {Object.entries(ROLE_NAMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button className="linkish" onClick={() => setMembers(members.filter((_x, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button onClick={() => setMembers([...members, { username: "", role: "architect" }])}>+ Add a person</button>
      <h4>Signs off (whole project)</h4>
      {users.map((u) => <label key={u} className="choice small"><input type="checkbox" checked={(sign[""] || []).includes(u)}
        onChange={() => setSign({ ...sign, "": (sign[""] || []).includes(u) ? sign[""].filter((x) => x !== u) : [...(sign[""] || []), u] })} /> {u}</label>)}
      <Quorum value={quorum} onChange={setQuorum} />
      <div className="row-gap"><button className="primary" onClick={save}>Save</button><button onClick={onDone}>Cancel</button>{msg && <span className="status bad">{msg}</span>}</div>
    </div>
  );
}

// The repository as a table (D290): one row per document class (a deliverable or artifact) with its documents under it:
// state, your version, the system version, checked out by whom (and the version being worked on), the last check-in,
// sign-off; check out, check in, history; add documents to any class, add a class, mark a class "won't need this".
// The project's documents (owner, 8 Nov 2026, D312): a table of document classes; a class opens to tabs of its
// documents and its templates; a document opens to its versions (only the versions, each to download). People check a
// document out, work in it and check it in; documents are added as files, from templates, or with no file yet. The whole
// repository is tagged, downloaded as at a tag, or brought back to a tag.
const kindLetter = (k) => (k === "Deliverable" ? "D" : k === "None" ? "–" : "A");
const kindClass = (k) => (k === "Deliverable" ? "del" : k === "None" ? "none" : "art");

function RepoTable({ p, codes, phase, compact = false }) {
  // opened from the content framework (D299): the document type or document asked for is highlighted and scrolled to
  const asked = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const hlItem = asked.get("item");
  const hlDoc = asked.get("doc");
  useEffect(() => {
    if (!hlItem && !hlDoc) return undefined;
    const t = setTimeout(() => document.querySelector(".repo-hl")?.scrollIntoView({ block: "center", behavior: "smooth" }), 300);
    return () => clearTimeout(t);
  }, [hlItem, hlDoc]);
  const [dlg, setDlg] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [tag, setTag] = useState("");
  // the ⋯ menus close on a click anywhere else, on Escape, and once one of their items is chosen (owner, 8 Nov 2026)
  useEffect(() => {
    const shut = (e) => document.querySelectorAll("details.more-menu[open]").forEach((m) => {
      if (e.type === "keydown" ? e.key === "Escape" : !m.contains(e.target) || e.target.closest(".more-menu > div button")) m.open = false;
    });
    document.addEventListener("click", shut);
    document.addEventListener("keydown", shut);
    return () => { document.removeEventListener("click", shut); document.removeEventListener("keydown", shut); };
  }, []);
  const [ftype, setFtype] = useState("");
  const [showArc, setShowArc] = useState(false);
  const [showDel, setShowDel] = useState(false);
  const [open, setOpen] = useState(null);           // the classes opened (null: those with documents, and the one asked for)
  const [tab, setTab] = useState({});               // class -> "docs" | "templates"
  const [openDoc, setOpenDoc] = useState(() => new Set(hlDoc ? [hlDoc] : []));
  // archived and deleted documents are not loaded with the project: only when asked for (D290)
  const show = [showArc && "archived", showDel && "deleted"].filter(Boolean).join(",");
  const { data: extra } = useApi(show ? `/api/v1/projects/${p.id}/documents?show=${show}` : null);
  const allDocs = useMemo(() => {
    if (!show || !extra) return p.documents;
    const byId = Object.fromEntries(p.documents.map((d) => [d.id, d]));
    const kindOf = Object.fromEntries(p.items.map((i) => [i.id, i.kind]));
    return extra.documents.map((d) => ({ ...d, kind: byId[d.id]?.kind || d.kind || kindOf[d.item_id] || "Artifact", signoff: byId[d.id]?.signoff }));
  }, [p.documents, p.items, extra, show]);
  const types = useMemo(() => [...new Set([...allDocs.map((d) => fileType(d.file_name)).filter(Boolean), ...(ftype ? [ftype] : [])])].sort(), [allDocs, ftype]);
  const tagList = useMemo(() => [...new Set([...allDocs.flatMap((d) => d.tags || []), ...(tag ? [tag] : [])])]
    .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())), [allDocs, tag]);
  const filtering = Boolean(tag || ftype);
  const docsBy = useMemo(() => {
    const o = {};
    allDocs.filter((d) => (!tag || (d.tags || []).some((t) => t.toLowerCase() === tag.toLowerCase())) && (!ftype || fileType(d.file_name) === ftype))
      .forEach((d) => { (o[d.item_id] = o[d.item_id] || []).push(d); });
    return o;
  }, [allDocs, tag, ftype]);
  const inPhase = p.items.filter((i) => codes.includes(i.phase));
  // classes not in use (left out, or marked won't need) are on the phase's Not added tab, to bring back (owner, 8 Nov 2026)
  const items = inPhase.filter((i) => i.chosen && (!filtering || (docsBy[i.id] || []).length));
  const can = p.may_contribute;
  const close = () => setDlg(null);
  const tplsOf = (i) => p.class_templates?.[i.id] || [];
  const docOf = allDocs.find((d) => d.id === hlDoc);
  const opened = open || new Set([...items.filter((i) => (docsBy[i.id] || []).length).map((i) => i.id), ...(hlItem ? [hlItem] : []), ...(docOf ? [docOf.item_id] : [])]);
  const toggle = (id) => { const n = new Set(opened); if (n.has(id)) n.delete(id); else n.add(id); setOpen(n); };
  // a document just added shows where it is: its class open, on its Documents tab (owner, 8 Nov 2026: it showed under
  // Templates first)
  const showDocs = (id) => { if (!id) return; setOpen(new Set([...opened, id])); setTab((x) => ({ ...x, [id]: "docs" })); };
  const toggleDoc = (id) => { const n = new Set(openDoc); if (n.has(id)) n.delete(id); else n.add(id); setOpenDoc(n); };
  async function act(fn) {
    setMsg(""); setBusy(true);
    try { const r = await fn(); if (r?.message) setMsg(r.message); refreshAll(); return r; } catch (e) { setMsg(e.message); return null; }
    finally { setBusy(false); }
  }
  function addFile(d) {          // the first file of a planned document (owner, 8 Nov 2026)
    const inp = document.createElement("input");
    inp.type = "file";
    inp.onchange = () => {
      const f = inp.files[0];
      if (!f) return;
      const fd = new FormData(); fd.append("file", f);
      act(() => apiUpload(`/api/v1/projects/${p.id}/documents/${d.id}/file`, fd));
    };
    inp.click();
  }
  const post = (path, body) => apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });
  const zip = (q) => act(async () => { await startDownload(`/api/v1/projects/${p.id}/repo-zip${q ? `?${q}` : ""}`, undefined, window.location.hash);
    return { message: "The zip is being made: it downloads when ready (see the task drawer)." }; });
  const nDocs = items.reduce((n, i) => n + (docsBy[i.id] || []).length, 0);
  return (
    <div className="repo-table-wrap">
      <div className="toolbar">
        {can && <button className="primary" onClick={() => setDlg({ k: "upload" })}>⬆ Add a document</button>}
        {can && <button onClick={() => setDlg({ k: "class" })}>＋ Add a document class</button>}
        <button onClick={() => setDlg({ k: "repotags" })} title="Tag the whole repository; download it as at a tag, or bring it back to a tag">🏷 Repository tags…</button>
        <button onClick={() => zip("")} title="Every document as it is now, a folder per class">⬇ Download all</button>
        <span className="small quiet">{items.filter((i) => i.chosen).length} classes · {nDocs} documents</span>
        <button className="linkish small" onClick={() => setOpen(new Set(items.map((i) => i.id)))}>Open all</button>
        <button className="linkish small" onClick={() => setOpen(new Set())}>Close all</button>
      </div>
      <div className="toolbar small">
        {tagList.length > 0 && <label>Tag <select value={tag} onChange={(e) => setTag(e.target.value)}>
          <option value="">any</option>{tagList.map((t) => <option key={t} value={t}>{t}</option>)}</select></label>}
        {(types.length > 1 || ftype) && <label>File type <select value={ftype} onChange={(e) => setFtype(e.target.value)}>
          <option value="">any</option>{types.map((t) => <option key={t} value={t}>{t}</option>)}</select></label>}
        {(p.hidden_documents?.archived > 0 || showArc) && <label><input type="checkbox" checked={showArc} onChange={(e) => setShowArc(e.target.checked)} />
          {" "}Show archived ({p.hidden_documents?.archived || 0})</label>}
        {(p.hidden_documents?.deleted > 0 || showDel) && <label><input type="checkbox" checked={showDel} onChange={(e) => setShowDel(e.target.checked)} />
          {" "}Show deleted ({p.hidden_documents?.deleted || 0})</label>}
      </div>
      {!compact && <p className="small quiet">Open a class (▸) for its <b>Documents</b> and <b>Templates</b>. To work in a document: <b>Check out</b> (it downloads),
        edit it, then <b>Check in</b> the new file, saying what changed. <b>🕘 History</b> on a document shows its versions, each to download.</p>}
      {msg && <p className="small status warn">{msg}</p>}
      {!items.length && filtering ? <p className="quiet">No documents match the filters. <button className="linkish" onClick={() => { setTag(""); setFtype(""); }}>Clear the filters</button></p>
        : !items.length ? <p className="quiet">No document classes in use here (see Templates/documents not in use).{can ? " Add one, or add a document and make its class as you go." : ""}</p> : (
        <div className="scroll">
          <table className="grid-table repo-classes">
            <colgroup><col className="c-twisty" /><col className="c-name" /><col className="c-kind" /><col className="c-docs" /><col className="c-tpl" /><col className="c-when" /><col className="c-act" /></colgroup>
            <thead><tr><th /><th>Document class</th><th title="Deliverable or artifact">Type</th><th>Documents</th><th>Templates</th><th>Last updated</th><th /></tr></thead>
            <tbody>
              {items.map((i) => {
                const docs = docsBy[i.id] || [];
                const temps = tplsOf(i);
                const isOpen = opened.has(i.id);
                const t = tab[i.id] || "docs";       // a class opens on its documents (templates: their own tab)
                const last = docs.map((d) => d.checked_in_at || d.modified_at).filter(Boolean).sort().pop();
                const outN = docs.filter((d) => d.checked_out_by).length;
                return (
                  <Fragment key={i.id}>
                    <tr className={`repo-class${i.chosen ? "" : " off"}${hlItem === i.id ? " repo-hl" : ""}${isOpen ? " open" : ""}`}>
                      <td><button className="linkish repo-twisty" aria-expanded={isOpen} aria-label={`${isOpen ? "Close" : "Open"} ${i.name}`} onClick={() => toggle(i.id)}>{isOpen ? "▾" : "▸"}</button></td>
                      <td><button className="linkish repo-classname" onClick={() => toggle(i.id)}><b>{i.name}</b></button>
                        {codes.length > 1 && <span className="chip small">{i.phase}</span>}{i.type && <span className="small quiet"> {i.type}</span>}
                        {!i.chosen && <span className="rag off" title={`${i.not_needed_by || ""} ${i.not_needed_at ? fmtDateTime(i.not_needed_at) : ""}`}>
                          won't need{i.not_needed_reason ? `: ${i.not_needed_reason}` : ""}</span>}</td>
                      <td><span className={`kind-toggle ${kindClass(i.kind)}`} title={i.kind}>{kindLetter(i.kind)}</span></td>
                      <td>{docs.length ? <>{docs.length} document{docs.length === 1 ? "" : "s"}{outN ? <div className="small rag amber">{outN} checked out</div> : null}</>
                        : i.chosen ? <span className="rag amber" title="In use, with no document yet: add one">none yet</span> : <span className="quiet">–</span>}</td>
                      <td>{temps.length ? <button className="linkish" onClick={() => { setTab({ ...tab, [i.id]: "templates" }); if (!isOpen) toggle(i.id); }}>{temps.length} template{temps.length === 1 ? "" : "s"}</button>
                        : <span className="quiet small">none</span>}</td>
                      <td className="small">{last ? fmtDateTime(last) : <span className="quiet">–</span>}</td>
                      <td className="repo-actions small">
                        {can && i.chosen && <button className="linkish" onClick={() => setDlg({ k: "upload", item: i.id })}>⬆ Add a document</button>}
                        {can && i.chosen && <button className="linkish" title="A web address or another project's document, filed in this class" onClick={() => setDlg({ k: "link", item: i.id })}>🔗 Link</button>}
                        {docs.some((d) => !d.no_file && !d.is_link) && <button className="linkish" title="Its documents as they are now, in one zip" onClick={() => zip(`item=${i.id}`)}>⬇ Download</button>}
                        {can && (i.chosen
                          ? <button className="linkish quiet" onClick={() => setDlg({ k: "notneeded", item: i })}>Won't need</button>
                          : <button className="linkish" onClick={() => act(() => post(`/api/v1/projects/${p.id}/items/${i.id}/not-needed`, { undo: true }))}>Needed again</button>)}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="repo-open"><td /><td colSpan={6}>
                        <div className="tabs sub repo-tabs" role="tablist">
                          <button className={`tab${t === "docs" ? " on" : ""}`} onClick={() => setTab({ ...tab, [i.id]: "docs" })}>Documents <span className="small quiet">{docs.length}</span></button>
                          <button className={`tab${t === "templates" ? " on" : ""}`} onClick={() => setTab({ ...tab, [i.id]: "templates" })}>Templates <span className="small quiet">{temps.length}</span></button>
                        </div>
                        {t === "docs" ? (
                          <ClassDocs p={p} i={i} docs={docs} can={can} busy={busy} act={act} post={post} addFile={addFile} setDlg={setDlg} setTag={setTag}
                            openDoc={openDoc} toggleDoc={toggleDoc} hlDoc={hlDoc} />
                        ) : (
                          <ClassTemplates p={p} i={i} temps={temps} can={can} act={act} onMade={() => showDocs(i.id)} />
                        )}
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {dlg?.k === "upload" && <AddDocDialog p={p} items={inPhase} phase={phase} item={dlg.item} onClose={(itemId) => { close(); showDocs(typeof itemId === "string" ? itemId : dlg.item); }} />}
      {dlg?.k === "class" && <AddClassDialog p={p} phase={phase} onClose={close} />}
      {dlg?.k === "notneeded" && <NotNeededDialog p={p} i={dlg.item} onClose={close} />}
      {dlg?.k === "tags" && <TagsDialog p={p} d={dlg.d} onClose={close} />}
      {dlg?.k === "accept" && <AcceptDialog p={p} d={dlg.d} onClose={close} />}
      {dlg?.k === "in" && <CheckInDialog p={p} d={dlg.d} onClose={close} />}
      {dlg?.k === "history" && <DocHistory p={p} d={dlg.d} onClose={close} />}
      {dlg?.k === "signlink" && <SignoffLink p={p} r={dlg.r} onClose={close} sent />}
      {dlg?.k === "link" && <LinkDialog p={p} d={dlg.d} item={dlg.item} onClose={(m) => { close(); if (m) setMsg(m); }} />}
      {dlg?.k === "repotags" && <RepoTagsDialog p={p} onClose={close} onMsg={setMsg} />}
    </div>
  );
}

// a class's documents: each with its type, state, versions, check-out, sign-off; opened, its versions
function ClassDocs({ p, i, docs, can, busy, act, post, addFile, setDlg, setTag, openDoc, toggleDoc, hlDoc }) {
  if (!docs.length) {
    return <p className="small quiet repo-empty">No document yet.{can && i.chosen ? <> <button className="linkish" onClick={() => setDlg({ k: "upload", item: i.id })}>Add one</button>
      {" "}(a file, from a template, or its name now and its file later).</> : ""}</p>;
  }
  return (
    <table className="grid-table repo-docs">
      <colgroup><col className="c-twisty" /><col className="c-name" /><col className="c-kind" /><col className="c-state" /><col className="c-uv" /><col className="c-ver" />
        <col className="c-out" /><col className="c-when" /><col className="c-sign" /><col className="c-act" /></colgroup>
      <thead><tr><th /><th>Document</th><th>Type</th><th>State</th><th title="Your version: free text">Yours</th><th className="num" title="The system's version: counts the files">Version</th><th>Checked out</th><th>Last updated</th><th>Sign-off</th><th /></tr></thead>
      <tbody>
        {docs.map((d) => {
          const mine = d.checked_out_by && d.checked_out_by.toLowerCase() === (p.me || "").toLowerCase();
          const gone = d.deleted_at ? "deleted" : d.archived_at ? "archived" : "";
          const done = d.state === "Approved" || d.state === "Accepted";
          const isOpen = openDoc.has(d.id);
          const hasVersions = !d.is_link && !d.no_file;
          return (
            <Fragment key={d.id}>
              <tr className={`repo-docrow${gone ? " gone" : ""}${hlDoc === d.id ? " repo-hl" : ""}`}>
                <td>{hasVersions && <button className="linkish repo-twisty" aria-expanded={isOpen} aria-label="Its versions" title="Its versions" onClick={() => toggleDoc(d.id)}>{isOpen ? "▾" : "▸"}</button>}</td>
                <td><div className="repo-docname">{d.is_link ? <LinkName d={d} /> : d.no_file
                  ? <span title="No file yet: add its file when you have it">📝 <b>{d.title}</b> <span className="chip small">no file yet</span></span>
                  : <button className="linkish" onClick={() => act(() => apiDownload(`/api/v1/projects/${p.id}/documents/${d.id}`, d.file_name))}
                    title="Download the latest version">📄 {d.title || d.file_name}</button>}</div>
                  {d.title && !d.no_file && !d.is_link && <div className="small quiet">file: {d.file_name}</div>}
                  <div className="doc-tags">{(d.tags || []).map((t) => <button key={t} className="tag-chip" title="Show only documents with this tag" onClick={() => setTag(t)}>{t}</button>)}
                    {areaList(d.content_area).map((a) => <a key={a} className="cf-chip" href={`#/projects/${p.id}/content?area=${a}`} title="Placed in this area of the content framework: open it">▦ {CF_LABEL[a] || a}</a>)}
                    {can && <button className="linkish small" title="Tag this document and place it in the content framework" onClick={() => setDlg({ k: "tags", d })}>#{d.tags?.length || d.content_area ? "" : " tag"}</button>}</div></td>
                <td>{can && !gone ? <button className={`kind-toggle small ${kindClass(d.kind)}`} title="Deliverable (signed off), artifact, or neither (no approval): click to change"
                  onClick={() => act(() => post(`/api/v1/projects/${p.id}/documents/${d.id}/kind`, { kind: d.kind === "Deliverable" ? "Artifact" : d.kind === "Artifact" ? "None" : "Deliverable" }))}>
                  {kindLetter(d.kind)}</button> : <span className={`kind-toggle small ${kindClass(d.kind)}`}>{kindLetter(d.kind)}</span>}</td>
                <td><span className={`small doc-state ${String(d.state).replace(/\s+/g, "-").toLowerCase()}`}>{d.state}</span>
                  {gone && <div className="small bad-text">{gone} by {d[`${gone}_by`]}</div>}
                  {d.state === "Accepted" && d.accepted_by && <div className="small quiet" title={d.accepted_note}>by {d.accepted_by}</div>}</td>
                <td>{d.user_version || <span className="quiet">–</span>}</td>
                <td className="num">{d.is_link ? <span className="quiet small">link</span> : d.no_file ? <span className="quiet">0</span>
                  : <>{d.versions}{d.signed_version ? <div className="small quiet">v{d.signed_version} signed</div> : ""}</>}</td>
                <td>{d.is_link || d.no_file ? <span className="quiet small">–</span> : d.checked_out_by ? <span className="rag amber" title={`since ${fmtDateTime(d.checked_out_at)}`}>
                  {mine ? "you" : d.checked_out_by}{d.out_version ? ` · ${d.out_version}` : ""}</span> : <span className="quiet small">in</span>}</td>
                <td className="small">{d.checked_in_by ? <><span className="nowrap">{fmtDateTime(d.checked_in_at)}</span><div className="quiet">{d.checked_in_by}</div></>
                  : <span className="quiet">{d.origin === "template" ? "from its template" : d.no_file ? "no file yet" : `added by ${d.created_by}`}</span>}</td>
                <td className="small">{d.signoff ? <a href={`#/projects/${p.id}/signoff`}>needs {d.signoff.quorum || d.signoff.signers.length} of {d.signoff.signers.length};
                  waiting for {d.signoff.waiting_for.join(", ")}</a>
                  : d.state === "Approved" ? "approved" : d.state === "Accepted" ? <span title={d.accepted_note}>accepted</span> : d.kind === "None" ? <span className="quiet">not needed</span> : ""}</td>
                <td className="repo-actions small">
                  {gone ? <>{can && <button className="linkish" onClick={() => act(() => post(`/api/v1/projects/${p.id}/documents/${d.id}/${gone === "deleted" ? "delete" : "archive"}`, { undo: true }))}>Restore</button>}
                    {hasVersions && <button className="linkish" onClick={() => toggleDoc(d.id)}>🕘 {isOpen ? "Hide history" : "History"}</button>}</> : <>
                    {hasVersions && <button className="linkish" aria-expanded={isOpen} title="Its versions, each to download"
                      onClick={() => toggleDoc(d.id)}>🕘 {isOpen ? "Hide history" : `History (${d.versions})`}</button>}
                    {can && d.is_link && <button className="linkish" onClick={() => setDlg({ k: "link", d })}>Change link</button>}
                    {can && d.no_file && <button className="linkish" onClick={() => addFile(d)} title="Choose its file: it becomes version 1">⬆ Add the file…</button>}
                    {can && !d.checked_out_by && hasVersions && <button className="linkish" disabled={busy} title="It is yours until you check it in; it downloads now"
                      onClick={() => act(async () => { const r = await post(`/api/v1/projects/${p.id}/documents/${d.id}/checkout`);
                        await apiDownload(`/api/v1/projects/${p.id}/documents/${d.id}`, d.file_name).catch(() => {}); return r; })}>Check out</button>}
                    {d.checked_out_by && mine && <button className="linkish" onClick={() => setDlg({ k: "in", d })}>Check in…</button>}
                    {d.checked_out_by && (mine || p.may_undo) && <button className="linkish" onClick={() => act(() => post(`/api/v1/projects/${p.id}/documents/${d.id}/undo-checkout`))}>Undo check-out</button>}
                    {can && !d.checked_out_by && !d.signoff && !done && hasVersions && d.kind !== "None" && (p.signoff.some((x) => x.phase === i.phase || x.phase === "")
                      ? <button className="linkish" title="Ask the phase's sign-off people: approved when the quorum approves, any rejection rejects it"
                        onClick={async () => { const r = await act(() => post(`/api/v1/projects/${p.id}/documents/${d.id}/signoff`, {}));
                          if (r?.id) setDlg({ k: "signlink", r: { id: r.id, file_name: d.file_name, version: d.versions } }); }}>Send for approval</button>
                      : <span className="quiet" title="Nobody approves documents in this project yet: the Project Admin sets who in About › People › Change (or in the project wizard).">no approvers set</span>)}
                  </>}
                  {can && !d.checked_out_by && <details className="more-menu"><summary title="More" aria-label="More">⋯</summary><div>
                    {!gone && !done && hasVersions && d.kind !== "None" && <button className="linkish" title="Mark it accepted now, with the evidence" onClick={() => setDlg({ k: "accept", d })}>Accept…</button>}
                    {!gone && <button className="linkish" onClick={() => { const t = window.prompt("The document's name (its file keeps its own name)", d.title || d.file_name);
                      if (t !== null) act(() => apiFetch(`/api/v1/projects/${p.id}/documents/${d.id}/title`, { method: "PUT", body: JSON.stringify({ title: t }) })); }}>Rename…</button>}
                    <button className="linkish" onClick={() => setDlg({ k: "history", d })}>Everything that happened to it…</button>
                    {!gone && <button className="linkish" onClick={() => act(() => post(`/api/v1/projects/${p.id}/documents/${d.id}/archive`))}>Archive (hide; restore any time)</button>}
                    {!gone && <button className="linkish bad-text" onClick={() => { if (window.confirm(`Delete ${d.title || d.file_name} with all its versions? It is then shown only with "Show deleted" and can be restored there.`)) act(() => post(`/api/v1/projects/${p.id}/documents/${d.id}/delete`)); }}>Delete with all versions</button>}
                  </div></details>}
                </td>
              </tr>
              {isOpen && hasVersions && <tr className="repo-versions-row"><td /><td colSpan={9}><DocVersions p={p} d={d} /></td></tr>}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

// a document's versions only (owner, 8 Nov 2026): newest first, each to download
function DocVersions({ p, d }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/documents/${d.id}/versions?v=${d.versions}`);
  const [err, setErr] = useState("");
  if (error) return <p className="status bad small">{error}</p>;
  if (!data) return <p className="quiet small">Loading the versions…</p>;
  return (
    <div className="repo-versions">
      <table className="grid-table small">
        <thead><tr><th className="num">Version</th><th>Your version</th><th>When</th><th>Who</th><th>What changed</th><th /></tr></thead>
        <tbody>{data.versions.map((v) => (
          <tr key={v.version}><td className="num"><b>{v.version}</b>{v.version === d.versions ? <span className="chip small">latest</span> : null}</td>
            <td>{v.user_version || <span className="quiet">–</span>}</td><td className="nowrap">{fmtDateTime(v.at)}</td><td>{v.by_user}</td>
            <td>{v.action === "checked in" ? v.note : <><span className="quiet">{v.action}</span>{v.note ? `: ${v.note}` : ""}</>}</td>
            <td><button className="linkish" onClick={() => apiDownload(`/api/v1/projects/${p.id}/documents/${d.id}/versions/${v.version}`, d.file_name).catch((e) => setErr(e.message))}>⬇ Download</button></td></tr>
        ))}</tbody>
      </table>
      {err && <p className="status bad small">{err}</p>}
    </div>
  );
}

// a class's templates (owner, 8 Nov 2026): to download, to make a document from, and more added from any library
function ClassTemplates({ p, i, temps, can, act, onMade }) {
  const [browse, setBrowse] = useState(false);
  const { data: libData } = useApi(browse ? "/api/v1/projects/library" : null);
  const libs = (libData?.libraries || []).filter((l) => l.usable);
  const make = (t) => {
    const title = window.prompt(`The new document's name (made from ${t.name})`, t.name.replace(/\.[^.]+$/, ""));
    if (title === null) return;
    act(() => apiFetch(`/api/v1/projects/${p.id}/items/${i.id}/documents/from-templates`, { method: "POST",
      body: JSON.stringify({ documents: [{ template: t.id, title: title.trim() }] }) })).then((r) => { if (r) onMade?.(); });
  };
  return (
    <div>
      {!temps.length ? <p className="small quiet repo-empty">No template for this class yet.</p> : (
        <table className="grid-table repo-docs small">
          <thead><tr><th>Template</th><th>Library</th><th /></tr></thead>
          <tbody>{temps.map((t) => (
            <tr key={t.id}><td>📄 {t.name}{t.added && <span className="chip small" title="Added to this class">added</span>}</td><td>{t.library}</td>
              <td className="repo-actions">
                <button className="linkish" onClick={() => act(() => apiDownload(`/api/v1/projects/${p.id}/templates/${t.id}`, `${t.library}-${t.name}`))}>⬇ Download</button>
                {can && i.chosen && <button className="linkish" title="A new document of this class, a copy of the template" onClick={() => make(t)}>＋ New document from it</button>}
                {can && t.added && <button className="linkish quiet" onClick={() => act(() => apiFetch(`/api/v1/projects/${p.id}/items/${i.id}/templates`, { method: "POST", body: JSON.stringify({ template: t.id, remove: true }) }))}>Take off</button>}
              </td></tr>
          ))}</tbody>
        </table>
      )}
      {can && <button className="linkish small" onClick={() => setBrowse(true)}>📚 Add a template from a library…</button>}
      {browse && libData && !libs.length && <p className="small quiet">No template library with files is offered to you. <button className="linkish" onClick={() => setBrowse(false)}>Close</button></p>}
      {browse && libData && libs.length > 0 && <TemplateBrowserDialog libraries={libs} picked={temps.map((t) => t.id)} title={`Add a template to ${i.name}`} onClose={() => setBrowse(false)}
        onPick={(t) => act(() => apiFetch(`/api/v1/projects/${p.id}/items/${i.id}/templates`, { method: "POST", body: JSON.stringify({ template: t.id }) }))} />}
    </div>
  );
}

// tags on the whole repository (owner, 8 Nov 2026, D312): the version of every document at a moment, to download
// everything as it was, or to bring the repository back (a tag "before application of tag <name>" is made first)
function RepoTagsDialog({ p, onClose, onMsg }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/repo-tags`);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [ask, setAsk] = useState(null);          // the tag to bring the repository back to
  async function run(label, fn) {
    setBusy(label); setErr("");
    try { const r = await fn(); if (r?.message) onMsg(r.message); refreshAll(); return r; } catch (e) { setErr(e.message); return null; } finally { setBusy(""); }
  }
  return (
    <Modal wide title="Repository tags" onClose={onClose} actions={<button onClick={onClose}>Close</button>}>
      <p className="small quiet">A tag keeps the version of every document in the repository at that moment. Download everything as it was at a tag,
        or bring the repository back to a tag: a tag "before application of tag …" is made first, so nothing is lost.</p>
      {error && <p className="status bad">{error}</p>}
      {data?.may_tag && <div className="row-gap repo-tag-new">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Tag name, e.g. Phase B sign-off" aria-label="Tag name" />
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" aria-label="Note" style={{ flex: 2 }} />
        <button className="primary" disabled={!name.trim() || !!busy} onClick={async () => { if (await run("Tagging…", () => apiFetch(`/api/v1/projects/${p.id}/repo-tags`,
          { method: "POST", body: JSON.stringify({ name: name.trim(), note }) }))) { setName(""); setNote(""); } }}>🏷 Tag the repository now</button>
      </div>}
      {err && <p className="status bad small">{err}</p>}
      {!data ? <p className="quiet">Loading…</p> : !data.tags.length ? <p className="quiet">No tag yet.</p> : (
        <table className="grid-table small">
          <thead><tr><th>Tag</th><th className="num">Documents</th><th>By</th><th>When</th><th /></tr></thead>
          <tbody>{data.tags.map((t) => (
            <tr key={t.id}><td><b>{t.name}</b>{t.auto && <span className="chip small" title="Made when the repository was brought back to a tag">automatic</span>}
              {t.note && <div className="quiet">{t.note}</div>}</td>
              <td className="num">{t.documents}</td><td>{t.created_by}</td><td className="nowrap">{fmtDateTime(t.created_at)}</td>
              <td className="repo-actions">
                <button className="linkish" onClick={() => run("", async () => { await startDownload(`/api/v1/projects/${p.id}/repo-zip?tag=${t.id}`, undefined, window.location.hash);
                  return { message: `The documents as at ${t.name} are being zipped: the zip downloads when ready.` }; })}>⬇ Download as at this tag</button>
                {data.may_revert && <button className="linkish" onClick={() => setAsk(t)}>↺ Bring the repository back to it…</button>}
                {data.may_revert && <button className="linkish quiet" onClick={() => { if (window.confirm(`Remove the tag ${t.name}? The documents are not changed.`))
                  run("", () => apiFetch(`/api/v1/projects/${p.id}/repo-tags/${t.id}`, { method: "DELETE" })); }}>Remove</button>}
              </td></tr>
          ))}</tbody>
        </table>
      )}
      {ask && <RevertDialog p={p} t={ask} onClose={() => setAsk(null)} onDone={(m) => { setAsk(null); onMsg(m); onClose(); }} />}
    </Modal>
  );
}

function RevertDialog({ p, t, onClose, onDone }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/repo-tags/${t.id}`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const changed = (data?.documents || []).filter((d) => d.version !== d.now_version);
  async function go() {
    setBusy(true); setErr("");
    try {
      const r = await runTask(apiFetch(`/api/v1/projects/${p.id}/repo-tags/${t.id}/revert`, { method: "POST" }), window.location.hash);
      refreshAll(); onDone(r?.message || `The repository is back at ${t.name}.`);
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Bring the repository back to ${t.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !data} onClick={go}>{busy ? "Working… (in the task drawer)" : "Bring it back"}</button></>}>
      {error && <p className="status bad">{error}</p>}
      {!data ? <p className="quiet">Loading…</p> : <>
        <ol className="small">
          <li>A tag <b>before application of tag {t.name}</b> is made, keeping the repository as it is now.</li>
          <li>{changed.length} document{changed.length === 1 ? "" : "s"} changed since the tag get a new version, a copy of their version at the tag.</li>
          <li>{data.added_since.length} document{data.added_since.length === 1 ? "" : "s"} added after the tag {data.added_since.length === 1 ? "is" : "are"} archived (restore any time).</li>
        </ol>
        {changed.length > 0 && <details className="small"><summary>The documents that go back</summary><ul>{changed.map((d) => <li key={d.id}>{d.name}: version {d.now_version} → copy of {d.version}</li>)}</ul></details>}
        {data.added_since.length > 0 && <details className="small"><summary>The documents archived</summary><ul>{data.added_since.map((d) => <li key={d.id}>{d.name}</li>)}</ul></details>}
        <p className="small quiet">Nothing is lost: every version stays, and the automatic tag brings it all back. Documents checked out stop it: check them in first.</p>
      </>}
      <DialogError e={err} />
    </Modal>
  );
}

const phaseChoices = (p) => p.phases.map((ph) => <option key={ph.code} value={ph.code}>{ph.name}</option>);
const KIND_HELP = "A deliverable is signed off; an artifact supports one (a catalog, matrix or diagram)";

function DialogError({ e }) { return e ? <p className="status bad">{e}</p> : null; }

// a document into any class, or a new class made on the way (D290)
// Add a document (owner, 8 Nov 2026): its name apart from its file's name; no file yet is fine (its file is added later);
// each document is a deliverable, an artifact or neither (neither needs no approval), whatever its class is.
function AddDocDialog({ p, items, phase, item, onClose }) {
  const [cls, setCls] = useState(item || (items.find((i) => i.chosen)?.id || "new"));
  const [name, setName] = useState("");
  const [kind, setKind] = useState("Artifact");
  const [ph, setPh] = useState(phase === "X" || phase === "*" ? "X" : phase);
  const [files, setFiles] = useState([]);
  const [title, setTitle] = useState("");
  const [docKind, setDocKind] = useState("");
  const [ver, setVer] = useState("0.1");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  // documents made from templates (owner, 8 Nov 2026): several, from any library, the same template more than once
  const [how, setHow] = useState("files");          // files | templates
  const [tpls, setTpls] = useState([]);             // [{key, template, name, library_name, title}]
  const [browse, setBrowse] = useState(false);
  const { data: libData } = useApi(how === "templates" ? "/api/v1/projects/library" : null);
  const libs = (libData?.libraries || []).filter((l) => l.usable);
  const addTpl = (t) => setTpls((x) => [...x, { key: `${t.id}-${Date.now()}-${x.length}`, template: t.id, name: t.name, library_name: t.library_name, title: "" }]);
  const all = p.items.filter((i) => i.chosen || i.id === item);
  const clsKind = cls === "new" ? kind : (p.items.find((i) => i.id === cls)?.kind || "Artifact");
  async function send(itemId, file, docTitle) {
    for (let k = 0; k < 20; k += 1) {      // a new class's folder is made in Documents within moments
      try {
        const fd = new FormData();
        if (file) { fd.append("file", file); fd.append("user_version", ver); }
        if (docTitle) fd.append("title", docTitle);
        if (docKind) fd.append("kind", docKind);
        return await apiUpload(`/api/v1/projects/${p.id}/items/${itemId}/documents`, fd);
      } catch (e) {
        if (!/not built yet/i.test(e.message) || k === 19 || !file) throw e;
        setBusy("Making the class's folder in Documents…");
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
    return null;
  }
  async function run() {
    setErr(""); setBusy(files.length ? "Uploading…" : "Adding…");
    try {
      let itemId = cls;
      if (cls === "new") {
        const r = await apiFetch(`/api/v1/projects/${p.id}/items`, { method: "POST", body: JSON.stringify({ name: name.trim(), kind, phase: ph }) });
        itemId = r.item;
        setCls(itemId);               // tried again, the class made now is used (not made twice)
      }
      if (how === "templates") {
        for (let k = 0; k < 20; k += 1) {           // a new class's folder is made in Documents within moments
          try {
            setBusy(`Making ${tpls.length} document${tpls.length === 1 ? "" : "s"} from templates…`);
            await apiFetch(`/api/v1/projects/${p.id}/items/${itemId}/documents/from-templates`, { method: "POST",
              body: JSON.stringify({ documents: tpls.map((t) => ({ template: t.template, title: t.title.trim() })), kind: docKind || undefined }) });
            break;
          } catch (e) {
            if (!/not built yet/i.test(e.message) || k === 19) throw e;
            setBusy("Making the class's folder in Documents…");
            await new Promise((r) => setTimeout(r, 3000));
          }
        }
        refreshAll(); onClose(itemId); return;
      }
      if (!files.length) {                           // planned: the name now, the file later
        await send(itemId, null, title.trim());
        refreshAll(); onClose(itemId); return;
      }
      const failed = [];
      for (const [i, f] of files.entries()) {      // several files: each becomes a document of the class
        setBusy(`Uploading ${i + 1} of ${files.length}…`);
        try { await send(itemId, f, files.length === 1 ? title.trim() : ""); } catch (e) { failed.push(`${f.name}: ${e.message}`); }
      }
      refreshAll();
      if (failed.length) { setErr(`Not added: ${failed.join("; ")}`); setBusy(""); setFiles(files.filter((f) => failed.some((x) => x.startsWith(`${f.name}:`)))); return; }
      onClose(itemId);
    } catch (e) { setErr(e.message); setBusy(""); }
  }
  const ready = (how === "templates" ? tpls.length > 0 : (files.length || title.trim()) && (!files.length || ver.trim())) && (cls !== "new" || name.trim());
  return (
    <Modal title="Add a document" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!!busy || !ready} onClick={run}>
        {busy || (how === "templates" ? `Make ${tpls.length || ""} document${tpls.length === 1 ? "" : "s"} from templates`
          : files.length > 1 ? `Add these ${files.length}` : files.length ? "Add it" : "Add it, file later")}</button></>}>
      <div className="ed-form">
        <Field label="Document class">
          <select value={cls} onChange={(e) => setCls(e.target.value)}>
            <option value="new">＋ A new class…</option>
            {p.phases.map((x) => {
              const list = all.filter((i) => i.phase === x.code);
              return list.length ? <optgroup key={x.code} label={x.name}>{list.map((i) => <option key={i.id} value={i.id}>{i.name} ({i.kind === "Deliverable" ? "D" : "A"})</option>)}</optgroup> : null;
            })}
          </select>
        </Field>
        {cls === "new" && <>
          <Field label="New class name" hint="(e.g. Capability Heat Map)"><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
          <Field label="Phase"><select value={ph} onChange={(e) => setPh(e.target.value)}>{phaseChoices(p)}</select></Field>
          <Field label="The class's kind" hint={`(${KIND_HELP})`}>
            <select value={kind} onChange={(e) => setKind(e.target.value)}><option>Artifact</option><option>Deliverable</option></select></Field>
        </>}
        <div className="row-gap small" role="radiogroup" aria-label="How">
          <label><input type="radio" checked={how === "files"} onChange={() => setHow("files")} /> My own files, or no file yet</label>
          <label><input type="radio" checked={how === "templates"} onChange={() => setHow("templates")} /> From templates (one or several)</label>
        </div>
        {how === "templates" ? <>
          <p className="small quiet">Each template picked becomes a document of the class, a copy of the template's file. Pick as many as you need,
            from any library you may use; the same template more than once gives several documents (name each).</p>
          {tpls.length > 0 && <table className="grid-table small"><thead><tr><th>Template (library › file)</th><th>Document name (optional)</th><th /></tr></thead>
            <tbody>{tpls.map((t) => (
              <tr key={t.key}><td><span className="quiet">{t.library_name} ›</span> {t.name}</td>
                <td><input value={t.title} placeholder={t.name.replace(/\.[^.]+$/, "")} aria-label={`Name of the document from ${t.name}`}
                  onChange={(e) => setTpls(tpls.map((x) => (x.key === t.key ? { ...x, title: e.target.value } : x)))} /></td>
                <td className="nowrap"><button className="linkish" onClick={() => addTpl({ id: t.template, name: t.name, library_name: t.library_name })} title="Another document from the same template">＋ again</button>
                  {" "}<button className="linkish" onClick={() => setTpls(tpls.filter((x) => x.key !== t.key))}>Remove</button></td></tr>
            ))}</tbody></table>}
          <button onClick={() => setBrowse(true)} disabled={!libs.length}>📚 {tpls.length ? "Pick more templates…" : "Pick templates…"}</button>
          {libData && !libs.length && <span className="small quiet"> No template library with files is offered to you.</span>}
          {browse && <TemplateBrowserDialog libraries={libs} title="Pick templates: each becomes a document"
            counts={tpls.reduce((o, t) => ({ ...o, [t.template]: (o[t.template] || 0) + 1 }), {})}
            onClose={() => setBrowse(false)} onPick={addTpl} />}
          <Field label="These documents are" hint="(a deliverable is signed off; an artifact may be; neither needs no approval)">
            <select value={docKind} onChange={(e) => setDocKind(e.target.value)}>
              <option value="">as their class: {clsKind}</option><option value="Deliverable">Deliverables</option>
              <option value="Artifact">Artifacts</option><option value="None">neither (no approval)</option></select></Field>
        </> : <>
        <Field label="Document name" hint={files.length > 1 ? "(several files: each keeps its file's name)" : "(e.g. Business Model Canvas; its file may be called anything)"}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} disabled={files.length > 1} placeholder={files.length === 1 ? files[0].name : "Business Model Canvas"} /></Field>
        <Field label="This document is" hint="(a deliverable is signed off; an artifact may be; neither needs no approval)">
          <select value={docKind} onChange={(e) => setDocKind(e.target.value)}>
            <option value="">as its class: {clsKind}</option><option value="Deliverable">a Deliverable</option>
            <option value="Artifact">an Artifact</option><option value="None">neither (no approval)</option></select></Field>
        <Field label="Files" hint="(optional: leave empty to add the file later; several: each becomes a document)">
          <input type="file" multiple onChange={(e) => { setFiles([...files, ...e.target.files]); e.target.value = ""; }} /></Field>
        {files.length > 0 && <ul className="small">{files.map((f, i) => <li key={`${f.name}${i}`}>{f.name} <button className="linkish" aria-label={`Remove ${f.name}`}
          onClick={() => setFiles(files.filter((_x, j) => j !== i))}>Remove</button></li>)}</ul>}
        {files.length > 0 && <Field label="Your version" hint="(free text, e.g. 0.1 draft; the same for each file)"><input value={ver} onChange={(e) => setVer(e.target.value)} /></Field>}
        {!files.length && title.trim() && <p className="small quiet">{title.trim()} is added with no file yet: add its file from its row when you have it.</p>}
        </>}
        <DialogError e={err} />
      </div>
    </Modal>
  );
}

function AddClassDialog({ p, phase, onClose }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState("Artifact");
  const [ph, setPh] = useState(phase === "X" || phase === "*" ? "X" : phase);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true); setErr("");
    try { await apiFetch(`/api/v1/projects/${p.id}/items`, { method: "POST", body: JSON.stringify({ name: name.trim(), kind, phase: ph, note }) }); refreshAll(); onClose(); }
    catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title="Add a document class" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !name.trim()} onClick={run}>{busy ? "Adding…" : "Add the class"}</button></>}>
      <div className="ed-form">
        <p className="small quiet">A new kind of document this project delivers, for example Architecture Maturity Assessment or Organisation
          Decomposition Diagram. Its folder is made in Documents; add as many documents to it as you need.</p>
        <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
        <Field label="Phase"><select value={ph} onChange={(e) => setPh(e.target.value)}>{phaseChoices(p)}</select></Field>
        <Field label="Kind" hint={`(${KIND_HELP})`}><select value={kind} onChange={(e) => setKind(e.target.value)}><option>Artifact</option><option>Deliverable</option></select></Field>
        <Field label="Note (optional)"><input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <DialogError e={err} />
      </div>
    </Modal>
  );
}

function NotNeededDialog({ p, i, onClose }) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  async function run() {
    try { await apiFetch(`/api/v1/projects/${p.id}/items/${i.id}/not-needed`, { method: "POST", body: JSON.stringify({ reason }) }); refreshAll(); onClose(); }
    catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={`Won't need ${i.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!reason.trim()} onClick={run}>Mark it not needed</button></>}>
      <div className="ed-form">
        <p className="small">It moves to the phase's <b>Templates/documents not in use</b> tab with your reason, and its documents are kept. You, the Project Admin or
          the Lead Architect bring it back from there. A class with a document checked out cannot be set aside until it is checked in.</p>
        <Field label="Why"><input value={reason} onChange={(e) => setReason(e.target.value)} autoFocus placeholder="e.g. covered by the capability assessment" /></Field>
        <DialogError e={err} />
      </div>
    </Modal>
  );
}

// the next version put in when none is given at check-in (as the server does): 0.3 draft -> 0.4, nothing -> 0.1
export const fileType = (name) => { const m = /\.([a-z0-9]{1,6})$/i.exec(name || ""); return m ? m[1].toLowerCase() : ""; };

function AcceptDialog({ p, d, onClose }) {
  const [note, setNote] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function run() {
    setBusy(true); setErr("");
    try {
      const fd = new FormData(); fd.append("note", note); if (file) fd.append("evidence", file);
      await apiUpload(`/api/v1/projects/${p.id}/documents/${d.id}/accept`, fd); refreshAll(); onClose();
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Accept ${d.title || d.file_name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !note.trim()} onClick={run}>{busy ? "Accepting…" : "Accept it"}</button></>}>
      <div className="ed-form">
        <p className="small">Version {d.versions}{d.user_version ? ` (${d.user_version})` : ""} becomes <b>Accepted</b> now, without asking the sign-off people{d.signoff ? "; the open request to them is withdrawn" : ""}.
          The evidence and your name are kept in its history.</p>
        <Field label="Evidence: why it is accepted" hint="(required, e.g. agreed at the architecture forum on 6 Nov)"><textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} autoFocus /></Field>
        <Field label="Evidence file" hint="(optional: the email, the minutes)"><input type="file" onChange={(e) => setFile(e.target.files[0] || null)} /></Field>
        <DialogError e={err} />
      </div>
    </Modal>
  );
}

export function nextVersion(v) {
  const m = String(v || "").match(/\d+(?:\.\d+)*/);
  if (!m) return "0.1";
  const parts = m[0].split(".");
  parts[parts.length - 1] = String(Number(parts[parts.length - 1]) + 1);
  return String(v).slice(0, m.index).trim() + parts.join(".");
}

function TagsDialog({ p, d, onClose }) {
  const [tags, setTags] = useState(d.tags || []);
  const [areas, setAreas] = useState(areaList(d.content_area));       // the content framework areas it is placed in (D309)
  const [q, setQ] = useState("");
  const [add, setAdd] = useState("");
  const [err, setErr] = useState("");
  const known = (p.document_tags || []).filter((t) => !tags.some((x) => x.toLowerCase() === t.toLowerCase()));
  function plus(t) {
    const v = t.trim().replace(/\s+/g, " ");
    if (v && !tags.some((x) => x.toLowerCase() === v.toLowerCase())) setTags([...tags, v]);
    setAdd("");
  }
  async function save() {
    const typed = add.trim().replace(/\s+/g, " ");      // a tag typed but not yet added with Enter is kept too
    const all = typed && !tags.some((x) => x.toLowerCase() === typed.toLowerCase()) ? [...tags, typed] : tags;
    try {
      await apiFetch(`/api/v1/projects/${p.id}/documents/${d.id}/tags`, { method: "POST", body: JSON.stringify({ tags: all }) });
      if (areas.join(",") !== areaList(d.content_area).join(",")) {
        await apiFetch(`/api/v1/projects/${p.id}/documents/${d.id}/content-area`, { method: "PUT", body: JSON.stringify({ areas }) });
      }
      refreshAll(); onClose();
    } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={`Tags and content framework: ${d.title || d.file_name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={save}>Save</button></>}>
      <div className="ed-form">
        <div className="doc-tags">{tags.length ? tags.map((t) => <span key={t} className="tag-chip">{t}
          <button className="linkish" title="Remove" aria-label={`Remove the tag ${t}`} onClick={() => setTags(tags.filter((x) => x !== t))}>×</button></span>)
          : <span className="quiet small">No tags yet.</span>}</div>
        <Field label="Add a tag" hint="(Enter adds it)"><input value={add} list="eax-doc-tags" autoFocus onChange={(e) => setAdd(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); plus(add); } }} /></Field>
        <datalist id="eax-doc-tags">{known.map((t) => <option key={t} value={t} />)}</datalist>
        {known.length > 0 && <p className="small">In use on this project: {known.slice(0, 20).map((t) => <button key={t} className="tag-chip" onClick={() => plus(t)}>{t}</button>)}</p>}
        <h4>Content framework</h4>
        <p className="small quiet">The document always shows under its document type's areas. Tick more areas to show it there too: one or several.
          {areas.length ? <> Chosen: {areas.map((a) => CF_LABEL[a]).join(", ")}.</> : null}</p>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter the areas" aria-label="Filter the areas" />
        <AreaChecks value={areas} onChange={setAreas} filter={q} />
        <DialogError e={err} />
      </div>
    </Modal>
  );
}

function CheckInDialog({ p, d, onClose }) {
  const [file, setFile] = useState(null);
  const [ver, setVer] = useState(d.out_version || "");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function run() {
    setBusy(true); setErr("");
    try {
      const fd = new FormData(); fd.append("file", file); fd.append("user_version", ver); fd.append("comment", comment);
      await apiUpload(`/api/v1/projects/${p.id}/documents/${d.id}/checkin`, fd); refreshAll(); onClose();
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Check in ${d.title || d.file_name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !file || !comment.trim()} onClick={run}>{busy ? "Checking in…" : "Check in"}</button></>}>
      <div className="ed-form">
        <p className="small">The new file becomes system version {d.versions + 1}; the check-out ends{d.signoff ? ", and the open sign-off is withdrawn" : ""}.</p>
        <Field label="The new file"><input type="file" onChange={(e) => setFile(e.target.files[0] || null)} /></Field>
        <Field label="Your version" hint={`(left empty, it becomes ${nextVersion(d.user_version)})`}><input value={ver} placeholder={nextVersion(d.user_version)}
          onChange={(e) => setVer(e.target.value)} autoFocus /></Field>
        <Field label="What changed" hint="(required)"><input value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
        <DialogError e={err} />
      </div>
    </Modal>
  );
}

function DocHistory({ p, d, onClose }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/documents/${d.id}/history`);
  return (
    <Modal wide title={`Everything that happened to ${d.title || d.file_name}`} onClose={onClose} actions={<button onClick={onClose}>Close</button>}>
      {error && <p className="status bad">{error}</p>}
      {!data ? <p>Loading…</p> : (
        <table className="grid-table small"><thead><tr><th>When</th><th>Who</th><th>What</th><th>Your version</th><th className="num">System version</th><th>Note</th></tr></thead>
          <tbody>{data.events.map((e, k) => <tr key={k}><td className="nowrap">{fmtDateTime(e.at)}</td><td>{e.by_user}</td><td>{e.action}</td>
            <td>{e.user_version}</td><td className="num">{e.version ?? ""}</td><td>{e.note}</td></tr>)}</tbody></table>)}
    </Modal>
  );
}

// the steps of a phase (owner, 7 Nov 2026): completing a step records who did it and when, as a sub step of the same name
// under it; "+ sub step" opens it again, to complete later (with a date it is due by); steps are added at any time.
// Completing a sub step never completes its step: someone ticks the step itself (owner, 8 Nov 2026)
function StepList({ p, list, phase }) {
  const [msg, setMsg] = useState("");
  const [adding, setAdding] = useState(null);       // {parent?: step} the add form
  const top = list.filter((x) => !x.parent);
  const subsOf = (x) => list.filter((y) => y.parent === x.id);
  const can = p.may_contribute;
  async function call(path, body, method = "POST") {
    setMsg("");
    try { const r = await apiFetch(path, { method, body: body ? JSON.stringify(body) : undefined }); setMsg(r.message); refreshAll(); return true; }
    catch (e) { setMsg(e.message); return false; }
  }
  const mark = (st, done) => call(`/api/v1/projects/${p.id}/steps/${st.id}/done`, { done });
  return (
    <>
      <ol className="steps-list">
        {top.map((x) => {
          const subs = subsOf(x);
          const open = subs.filter((y) => !y.done_at);
          return (
            <li key={x.id} className={`${x.removed ? "removed" : ""}${x.done_at ? " done" : ""}`} value={x.seq}>
              {!x.removed && <input type="checkbox" checked={!!x.done_at} disabled={!can} title={x.done_at ? "Mark not done (the last completion is taken back)" : "Mark done"}
                onChange={(e) => mark(x, e.target.checked)} aria-label={`${x.name}: done`} />}
              <span className="step-name">{x.name}</span>{x.own && <span className="chip">own</span>}
              <span className="small quiet"> opened {fmtDate(x.added_at)}</span>
              {x.done_at && <span className="small quiet"> · closed {fmtDate(x.done_at)} by {x.done_by}</span>}
              <StepHistory events={x.events} />
              {subs.length > 1 && <span className="small quiet"> · done {subs.filter((y) => y.done_at).length} times</span>}
              {open.length > 0 && <span className="rag amber small"> {open.length} open</span>}
              {x.due_date && !x.done_at && <span className="small quiet"> · due {x.due_date}</span>}
              {x.removed && <span className="small quiet"> removed: {x.removed_reason}</span>}
              {can && !x.removed && <button className="linkish small" title="Do this step again: open a sub step, to complete later"
                onClick={() => setAdding({ parent: x })}>＋ sub step</button>}
              {subs.length > 0 && (
                <ul className="sub-steps">
                  {subs.map((y) => (
                    <li key={y.id} className={y.done_at ? "done" : "open"}>
                      <input type="checkbox" checked={!!y.done_at} disabled={!can} onChange={(e) => mark(y, e.target.checked)} aria-label={`${y.name} (${y.seq}): done`} />
                      <span>{y.name} <span className="quiet">#{y.seq}</span></span>
                      <span className="small quiet"> opened {fmtDate(y.added_at)}{y.added_by ? ` by ${y.added_by}` : ""}</span>
                      {y.done_at ? <span className="small quiet"> · closed {fmtDate(y.done_at)} by {y.done_by}</span>
                        : <span className="small quiet"> · open{y.due_date ? `, due ${y.due_date}` : ""}</span>}
                      <StepHistory events={y.events} />
                      {y.done_note && <span className="small"> · {y.done_note}</span>}
                      {can && !y.done_at && <button className="linkish small" onClick={() => call(`/api/v1/projects/${p.id}/steps/${y.id}/sub`, null, "DELETE")}>Take away</button>}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
      {can && phase && <button className="linkish small" onClick={() => setAdding({})}>＋ Add a step</button>}
      {msg && <p className="small status">{msg}</p>}
      {adding && <StepDialog p={p} phase={phase} parent={adding.parent} onClose={() => setAdding(null)} call={call} />}
    </>
  );
}

// a step's history (owner, 8 Nov 2026): when it was opened, closed and reopened, and by whom
function StepHistory({ events }) {
  const list = typeof events === "string" ? JSON.parse(events || "[]") : events || [];
  if (!list.length) return null;
  return (
    <details className="step-history small"><summary title="When it was opened, closed and reopened">🕘 {list.length}</summary>
      <ul>{list.map((e, i) => <li key={i}>{fmtDateTime(e.at)} · {e.action} by {e.by}{e.note ? `: ${e.note}` : ""}</li>)}</ul>
    </details>
  );
}

function StepDialog({ p, phase, parent, onClose, call }) {
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const [opened, setOpened] = useState(() => new Date().toISOString().slice(0, 10));   // a sub step's open date (owner, 8 Nov 2026)
  const [note, setNote] = useState("");
  const [ph, setPh] = useState(phase || p.phases[0]?.code);
  async function save() {
    const ok = parent
      ? await call(`/api/v1/projects/${p.id}/steps/${parent.id}/sub`, { open_date: opened || null, due_date: due || null, note })
      : await call(`/api/v1/projects/${p.id}/steps`, { phase: ph, name, due_date: due || null });
    if (ok) onClose();
  }
  return (
    <Modal title={parent ? `Do "${parent.name}" again` : "Add a step"} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!parent && !name.trim()} onClick={save}>{parent ? "Open the sub step" : "Add the step"}</button></>}>
      <div className="ed-form">
        {parent ? <p className="small">A sub step of the same name is opened under the step, and the step is open again. Tick the sub step when it is done
          (who and when are kept); the step itself is ticked on its own when the whole step is done.</p> : <>
          <Field label="Phase"><select value={ph} onChange={(e) => setPh(e.target.value)}>{p.phases.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}</select></Field>
          <Field label="Step"><input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="e.g. Review the target with the Executive Committee" /></Field>
        </>}
        {parent && <Field label="Opened on"><input type="date" value={opened} onChange={(e) => setOpened(e.target.value)} /></Field>}
        <Field label="Due by" hint="(optional)"><input type="date" value={due} min={parent ? opened : undefined} onChange={(e) => setDue(e.target.value)} /></Field>
        {parent && <Field label="Note" hint="(optional)"><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. quarterly review" /></Field>}
      </div>
    </Modal>
  );
}

function StepsTab({ p }) {
  const live = p.steps.filter((x) => !x.removed && !x.parent);
  return (
    <div>
      <p className="quiet small">The ADM steps this project follows: tick a step when it is done (who and when are kept as a sub step under it), untick
        it if it is not. <b>＋ sub step</b> opens it again, to do later: ticking the sub step does not tick the step, someone ticks the step when it is
        all done; <b>＋ Add a step</b> adds one of the project's own at any time (anyone who
        contributes). Removed standard steps stay, crossed out, with the reason. Done: <b>{live.filter((x) => x.done_at).length}</b> of {live.length}.</p>
      {p.phases.map((ph) => {
        const list = p.steps.filter((x) => x.phase === ph.code);
        const open = list.filter((x) => !x.removed && !x.parent);
        return (
          <details key={ph.code} open>
            <summary><b>{ph.name}</b> <span className="small quiet">{open.filter((x) => x.done_at).length} of {open.length} done
              {list.some((x) => x.removed) ? `, ${list.filter((x) => x.removed).length} removed` : ""}</span></summary>
            <StepList p={p} list={list} phase={ph.code} />
          </details>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- sign-off (D276)
// a link to a sign-off request, to send by email yourself (owner, 8 Nov 2026): it opens the Sign-off tab on that request
export function SignoffLink({ p, r, onClose, sent = false }) {
  const [copied, setCopied] = useState(false);
  const url = `${window.location.origin}${window.location.pathname}#/projects/${p.id}/signoff?request=${r.id}`;
  const subject = `Please approve: ${r.file_name}${r.version ? ` v${r.version}` : ""} (${p.name})`;
  const body = `Please review and approve or reject ${r.file_name}${r.version ? ` version ${r.version}` : ""} for ${p.name}:\n\n${url}\n\nSign in to EA Explorer to give your decision.`;
  async function copy() {
    try { await navigator.clipboard.writeText(url); setCopied(true); } catch { setCopied(false); }
  }
  return (
    <Modal title={sent ? "Sent for approval" : "Link to this sign-off"} onClose={onClose}
      actions={<button className="primary" onClick={onClose}>Done</button>}>
      <div className="ed-form">
        {sent && <p className="small">The signers are told in EA Explorer. To ask them by email as well, send them this link: it opens the request
          for their decision once they sign in.</p>}
        <Field label="Link"><input readOnly value={url} onFocus={(e) => e.target.select()} aria-label="Link to the sign-off request" /></Field>
        <div className="row-gap">
          <button onClick={copy}>{copied ? "Copied ✓" : "Copy the link"}</button>
          <a className="button" href={`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`}>Write an email…</a>
          <span className="small quiet">opens your own mail program with the link in it</span>
        </div>
      </div>
    </Modal>
  );
}

// what still needs signing off (owner, 8 Nov 2026): deliverables neither approved nor accepted, with no request open, and
// deliverable classes with no document yet
function NotSignedOff({ p, onSent }) {
  const [msg, setMsg] = useState("");
  const itemOf = Object.fromEntries(p.items.map((i) => [i.id, i]));
  const docs = p.documents.filter((d) => d.kind === "Deliverable" && !["Approved", "Accepted"].includes(d.state) && !d.signoff
    && (!d.item_id || itemOf[d.item_id]?.chosen));
  const empty = p.items.filter((i) => i.chosen && i.kind === "Deliverable" && !p.documents.some((d) => d.item_id === i.id));
  const can = p.may_contribute && !p.frozen;
  async function send(d) {
    setMsg("");
    try {
      const r = await apiFetch(`/api/v1/projects/${p.id}/documents/${d.id}/signoff`, { method: "POST", body: "{}" });
      refreshAll(); onSent({ id: r.id, file_name: d.file_name, version: d.versions });
    } catch (e) { setMsg(e.message); }
  }
  return (
    <div>
      <h3>Not signed off yet <span className="small quiet">{docs.length + empty.length}</span></h3>
      {msg && <p className="status bad small">{msg}</p>}
      {!docs.length && !empty.length ? <p className="quiet small">Every deliverable is approved, accepted or waiting for its signers.</p> : (
        <table className="grid-table small">
          <thead><tr><th>Phase</th><th>Deliverable</th><th>Document</th><th>State</th><th /></tr></thead>
          <tbody>
            {docs.map((d) => {
              const i = itemOf[d.item_id];
              return (
                <tr key={d.id}><td>{i?.phase || ""}</td><td>{i?.name || d.folder}</td><td>{d.is_link ? "🔗 " : "📄 "}{d.file_name}</td><td>{d.state}</td>
                  <td>{can && !d.checked_out_by && <button className="linkish" onClick={() => send(d)}>Send for approval</button>}
                    {d.checked_out_by && <span className="quiet">checked out by {d.checked_out_by}</span>}</td></tr>
              );
            })}
            {empty.map((i) => (
              <tr key={i.id}><td>{i.phase}</td><td>{i.name}</td><td className="quiet">no document yet</td><td /><td>
                <a href={`#/projects/${p.id}/phases?phase=${i.phase}`}>Add it in Phases</a></td></tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SignoffTab({ p }) {
  const [msg, setMsg] = useState("");
  const [rec, setRec] = useState(null);
  const [link, setLink] = useState(null);
  const asked = new URLSearchParams(window.location.hash.split("?")[1] || "").get("request");
  useEffect(() => {      // opened from a link: the request is shown and scrolled to
    if (asked) document.getElementById(`signoff-${asked}`)?.scrollIntoView({ block: "center" });
  }, [asked]);
  async function decide(r, decision) {
    // eslint-disable-next-line no-alert
    const comment = window.prompt(decision === "approved" ? "A comment (optional)" : "Why is it rejected? (required)", "");
    if (comment === null) return;
    setMsg("");
    try { const out = await apiFetch(`/api/v1/projects/${p.id}/signoffs/${r.id}/decide`, { method: "POST", body: JSON.stringify({ decision, comment }) }); setMsg(out.message); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  const mayRecord = (r) => r.state === "open" && p.may_contribute && (p.may_admin || r.raised_by.toLowerCase() === (p.me || "").toLowerCase());
  return (
    <div>
      <p className="quiet small">Documents sent for approval to the phase's sign-off people. Each is told in the application and approves, or
        rejects with comments; the person who sent it approves their own part as self approved. A decision given outside (an email, a signed page)
        is recorded with the evidence. <b>Approved when {p.signoff_quorum ? `${p.signoff_quorum} of them` : "a majority of them"} approve; any
        rejection rejects it.</b> A new version checked in ends the request for the old one. Email alerts come in a later phase.</p>
      {msg && <p className="small status">{msg}</p>}
      <NotSignedOff p={p} onSent={setLink} />
      <h3>Sent for approval</h3>
      {!p.signoffs.length && <p className="quiet">Nothing sent for approval yet.</p>}
      <table className="grid-table">
        <thead><tr><th>Document</th><th>Version</th><th>State</th><th>Raised</th><th>Decisions</th><th /></tr></thead>
        <tbody>
          {p.signoffs.map((r) => (
            <tr key={r.id} id={`signoff-${r.id}`} className={`${r.mine ? "mine" : ""}${asked === r.id ? " asked" : ""}`}>
              <td><b>{r.file_name}</b><div className="small quiet">{r.item || ""}{r.phase ? ` · ${r.phase}` : ""}</div>{r.note && <div className="small">{r.note}</div>}</td>
              <td>v{r.version}</td>
              <td><span className={`rag ${r.state === "approved" ? "green" : r.state === "rejected" ? "red" : r.state === "open" ? "amber" : "off"}`}>{r.state}</span>
                {r.state === "open" && <div className="small">needs {r.quorum || r.signers.length} of {r.signers.length} · {r.decisions.filter((x) => x.decision === "approved").length} so far</div>}
                {r.waiting_for.length > 0 && <div className="small quiet">waiting for {r.waiting_for.join(", ")}</div>}</td>
              <td className="small">{r.raised_by}<div className="quiet">{fmtDateTime(r.raised_at)}</div></td>
              <td className="small">{r.decisions.map((x) => <div key={x.signer}><b>{x.signer}</b> {x.decision}{x.how !== "in-app" ? ` (${x.how === "self" ? "self approved" : `recorded by ${x.recorded_by}, evidence ${x.evidence_name}`})` : ""}
                {x.comment && <span className="quiet">: {x.comment}</span>}</div>)}</td>
              <td>{r.mine && <><button className="primary" onClick={() => decide(r, "approved")}>Approve</button> <button onClick={() => decide(r, "rejected")}>Reject</button></>}
                {mayRecord(r) && <div><button className="linkish small" onClick={() => setRec(r)}>Record a decision with evidence…</button></div>}
                {r.state === "open" && <div><button className="linkish small" onClick={() => setLink(r)}>🔗 Link for an email</button></div>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rec && <RecordDialog p={p} r={rec} onClose={() => setRec(null)} />}
      {link && <SignoffLink p={p} r={link} onClose={() => setLink(null)} />}
    </div>
  );
}

function RecordDialog({ p, r, onClose }) {
  const [signer, setSigner] = useState(r.waiting_for[0] || "");
  const [decision, setDecision] = useState("approved");
  const [comment, setComment] = useState("");
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState("");
  async function save() {
    const fd = new FormData();
    fd.append("signer", signer); fd.append("decision", decision); fd.append("comment", comment); fd.append("file", file);
    try { await apiUpload(`/api/v1/projects/${p.id}/signoffs/${r.id}/record`, fd); refreshAll(); onClose(); } catch (e) { setMsg(e.message); }
  }
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Record a sign-off decision">
      <div className="modal">
        <h3>Record a decision on {r.file_name} v{r.version}</h3>
        <label className="field">Signer <select value={signer} onChange={(e) => setSigner(e.target.value)}>{r.waiting_for.map((u) => <option key={u}>{u}</option>)}</select></label>
        <div className="row-gap"><label><input type="radio" checked={decision === "approved"} onChange={() => setDecision("approved")} /> Approved</label>
          <label><input type="radio" checked={decision === "rejected"} onChange={() => setDecision("rejected")} /> Rejected</label></div>
        <label className="field">Comment <input value={comment} onChange={(e) => setComment(e.target.value)} /></label>
        <label className="field">Evidence: the email or signed document <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} /></label>
        <div className="row-gap"><button className="primary" disabled={!signer || !file} onClick={save}>Record it</button><button onClick={onClose}>Cancel</button></div>
        {msg && <p className="status bad small">{msg}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- finishing the project (D277)
function FinishDialog({ p, onClose }) {
  const { data: plist } = useApi("/api/v1/projects");
  const [mode, setMode] = useState("freeze");
  const [target, setTarget] = useState("");
  const [models, setModels] = useState(() => Object.fromEntries(p.models.map((m) => [m.id, "keep"])));
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const targets = (plist?.projects || []).filter((x) => x.id !== p.id && x.status === "active");
  async function go() {
    setBusy(true); setMsg("");
    try {
      await runTask(apiFetch(`/api/v1/projects/${p.id}/finish`, { method: "POST", body: JSON.stringify({ mode, target: mode === "merge" ? target : undefined, models, note }) }), `#/projects/${p.id}`);
      refreshAll(); onClose();
    } catch (e) { setMsg(e.message); }
    setBusy(false);
  }
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Finish the project">
      <div className="modal">
        <h3>Finish {p.name}</h3>
        <p className="small quiet">A finished project is read only. Done in the background: the Tasks tab on the right says when it is.</p>
        <label className="choice"><input type="radio" checked={mode === "freeze"} onChange={() => setMode("freeze")} /> <b>Freeze it</b>
          <span className="small quiet">read only, as it is; other projects can still derive from it</span></label>
        <label className="choice"><input type="radio" checked={mode === "merge"} onChange={() => setMode("merge")} /> <b>Merge it into another project</b>
          <span className="small quiet">its documents are copied into that project's repository (same phase and deliverable where it has it, else a folder
            "From {p.name}" in that phase), then it is frozen</span></label>
        {mode === "merge" && <label className="field">Into <select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Choose a project...</option>{targets.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>}
        <h4>Its models</h4>
        <table className="grid-table small"><tbody>
          {p.models.map((m) => (
            <tr key={m.id}><td>{m.name}<div className="quiet">{HOW[m.how] || m.how}</div></td>
              <td><label><input type="radio" checked={models[m.id] === "keep"} onChange={() => setModels({ ...models, [m.id]: "keep" })} /> keep as it is</label>{" "}
                <label title={m.has_parent ? `Merged into ${m.parent_name} (its changes win)` : "It has no parent model"}><input type="radio" disabled={!m.has_parent || ["added", "referred"].includes(m.how)}
                  checked={models[m.id] === "merge"} onChange={() => setModels({ ...models, [m.id]: "merge" })} /> merge into its parent{m.parent_name ? ` (${m.parent_name})` : ""}</label>{" "}
                <label title={m.has_parent ? "" : "It has no parent model"}><input type="radio" disabled={!m.has_parent || ["added", "referred"].includes(m.how)}
                  checked={models[m.id] === "merge-freeze"} onChange={() => setModels({ ...models, [m.id]: "merge-freeze" })} /> merge into its parent and freeze it</label>{" "}
                <label><input type="radio" disabled={m.how === "referred"}
                  checked={models[m.id] === "freeze"} onChange={() => setModels({ ...models, [m.id]: "freeze" })} /> freeze it (final)</label></td></tr>
          ))}
        </tbody></table>
        <label className="field">Note <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why, what was delivered (optional)" /></label>
        <div className="row-gap"><button className="primary" disabled={busy || (mode === "merge" && !target)} onClick={go}>{busy ? "Working..." : mode === "merge" ? "Merge and freeze" : "Freeze"}</button>
          <button onClick={onClose}>Cancel</button></div>
        {msg && <p className="status bad small">{msg}</p>}
      </div>
    </div>
  );
}

// the project's principles by area (owner, 8 Nov 2026): a grid per area with the statement, rationale and implications;
// anyone who contributes adds principles of the project's own at any time (the name plain, the rest rich text)
const richOrPlain = (v) => (/^\s*</.test(v || "") ? <div className="rich-view" dangerouslySetInnerHTML={{ __html: v }} />
  : <div style={{ whiteSpace: "pre-line" }}>{v}</div>);

// A project's principles (owner, 8 Nov 2026, D327): a grid by area (Business, Security, Data...), each principle with its
// statement, rationale and implications; one that refines a higher-level principle is nested under it. The
// organisation's set lives in the Organisation base: enforced ones (🔒) are in every project and cannot be taken out;
// optional ones come too and a project may take them out; a project adds its own. In a base, a Super Admin sets each
// principle enforced or optional and adds areas.
export function PrinciplesTab({ p }) {
  const [dlg, setDlg] = useState(null);
  const [msg, setMsg] = useState("");
  const [shut, setShut] = useState(() => new Set());
  const can = p.may_contribute && !p.frozen;
  const isBase = !!p.base_kind;
  const all = p.principles;
  const byKey = {};
  for (const r of all) { if (r.guid) byKey[r.guid] = r; if (r.origin_guid) byKey[r.origin_guid] = r; }
  const parentOf = (r) => (r.refines && byKey[r.refines] && byKey[r.refines] !== r ? byKey[r.refines] : null);
  const areas = [...new Set([...(p.principle_area_list || []), ...all.map((r) => r.area || "")])].filter((a) => a !== undefined);
  const ordered = areas.sort((x, y) => (x || "~").localeCompare(y || "~"));
  async function call(url, opts) {
    try { const out = await apiFetch(url, opts); setMsg(out.message); refreshAll(); } catch (e) { setMsg(e.message); }
  }
  function remove(r) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Take the principle ${r.name} out of the ${isBase ? "base" : "project"}?`)) return;
    call(`/api/v1/projects/${p.id}/principles/${r.id}`, { method: "DELETE" });
  }
  const addArea = () => {
    // eslint-disable-next-line no-alert
    const n = window.prompt("The new area's name (e.g. Business, Security, Data, AI)");
    if (n && n.trim()) call(`/api/v1/projects/${p.id}/principle-areas`, { method: "POST", body: JSON.stringify({ name: n }) });
  };
  const from = (r) => (isBase ? (r.mandatory ? "🔒 enforced in every project below" : "optional below")
    : r.from_base && r.mandatory ? "🔒 enforced by the organisation" : r.from_base ? "optional, from the organisation"
      : r.inherited_from ? `inherited from ${r.inherited_from}` : r.library_id ? "library" : `the project's own (${r.created_by})`);
  const locked = (r) => r.inherited_from || (!isBase && r.from_base && r.mandatory);
  const row = (r, depth) => {
    const kids = all.filter((k) => parentOf(k) === r && (k.area || "") === (r.area || ""));
    const open = !shut.has(r.id);
    return [
      <tr key={r.id} className={depth ? "principle-child" : ""}>
        <td style={{ paddingLeft: 8 + depth * 22 }}>
          {kids.length > 0 && <button className="linkish small" aria-expanded={open} onClick={() => { const n = new Set(shut); if (open) n.add(r.id); else n.delete(r.id); setShut(n); }}>{open ? "▾" : "▸"}</button>}
          {depth > 0 && <span className="quiet">↳ </span>}<b>{r.name}</b>{r.code && <div className="small quiet">{r.code}</div>}
          {parentOf(r) && (parentOf(r).area || "") !== (r.area || "") && <div className="small quiet">refines {parentOf(r).name} ({parentOf(r).area || "Other"})</div>}</td>
        <td className="small">{richOrPlain(r.statement)}</td><td className="small">{richOrPlain(r.rationale)}</td>
        <td className="small">{richOrPlain(r.implications)}</td>
        <td className="small">{from(r)}</td>
        {can && <td className="small nowrap">{!locked(r) && <>
          <button className="linkish" onClick={() => setDlg(r)}>Change</button>{" · "}
          {isBase && p.is_super && <><button className="linkish" onClick={() => call(`/api/v1/projects/${p.id}/principles/${r.id}`, { method: "PUT", body: JSON.stringify({ mandatory: !r.mandatory }) })}>
            {r.mandatory ? "Make optional" : "Enforce"}</button>{" · "}</>}
          <button className="linkish" onClick={() => remove(r)}>Take out</button></>}
          {can && <>{!locked(r) && " · "}<button className="linkish" onClick={() => setDlg({ area: r.area, refines: r.guid })}>＋ Refine it</button></>}</td>}
      </tr>,
      ...(open ? kids.flatMap((k) => row(k, depth + 1)) : []),
    ];
  };
  return (
    <div>
      <p className="quiet">{isBase
        ? "The organisation's principles, by area. Enforced ones (🔒) are in every project below and cannot be taken out there; optional ones come to every new project, which may take them out. A principle may refine a higher-level one: it is shown under it."
        : "The principles this project works to, by area. Those the organisation enforces are locked (🔒; ask for a dispensation in the governance log); optional ones from the organisation may be taken out; the project adds its own, and may refine any of them."}</p>
      {msg && <p className="small status">{msg}</p>}
      {can && <div className="row-gap"><button className="primary" onClick={() => setDlg({})}>＋ Add a principle</button>
        <button onClick={addArea}>＋ Add an area</button></div>}
      {!all.length && !ordered.length && <p className="quiet">No principles yet.</p>}
      {ordered.map((area) => {
        const here = all.filter((r) => (r.area || "") === area);
        const tops = here.filter((r) => !parentOf(r) || (parentOf(r).area || "") !== area);
        return (
          <section key={area || "~"} className="principle-area">
            <h3>{area || "Other"} <span className="small quiet">{here.length}</span>
              {can && <button className="linkish small" onClick={() => setDlg({ area })}>＋ add here</button>}
              {can && !here.length && area && <button className="linkish small" onClick={() => call(`/api/v1/projects/${p.id}/principle-areas`, { method: "POST", body: JSON.stringify({ name: area, remove: true }) })}>remove the area</button>}</h3>
            {here.length ? <table className="grid-table principle-grid">
              <thead><tr><th>Principle</th><th>Statement</th><th>Rationale</th><th>Implications</th><th>{isBase ? "Below" : "From"}</th>{can && <th />}</tr></thead>
              <tbody>{tops.flatMap((r) => row(r, 0))}</tbody>
            </table> : <p className="small quiet">No principles in this area yet.</p>}
          </section>
        );
      })}
      {dlg && <PrincipleDialog p={p} r={dlg} onClose={(m) => { setDlg(null); if (m) setMsg(m); }} />}
    </div>
  );
}

function PrincipleDialog({ p, r, onClose }) {
  const lib = !!r.library_id;
  const [f, setF] = useState({ name: r.name || "", area: r.area || "", code: r.code || "", statement: r.statement || "", rationale: r.rationale || "",
    implications: r.implications || "", refines: r.refines || "", ...(p.base_kind && !r.id ? { mandatory: true } : {}) });
  const others = p.principles.filter((x) => x.id !== r.id);
  const [err, setErr] = useState("");
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const asHtml = (v) => (/^\s*</.test(v) ? v : v ? `<p>${v.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>")}</p>` : "");
  async function save() {
    setErr("");
    try {
      const out = await apiFetch(r.id ? `/api/v1/projects/${p.id}/principles/${r.id}` : `/api/v1/projects/${p.id}/principles`,
        { method: r.id ? "PUT" : "POST", body: JSON.stringify(lib ? { area: f.area, refines: f.refines } : f) });
      refreshAll(); onClose(out.message);
    } catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={r.id ? `Change ${r.name}` : r.refines ? "A principle that refines another" : "Add a principle"} onClose={() => onClose()} wide
      actions={<><button onClick={() => onClose()}>Cancel</button><button className="primary" disabled={!f.name.trim()} onClick={save}>Save</button></>}>
      <div className="ed-form">
        {lib && <p className="small quiet">A principle from the library keeps its words: only its area can be changed here.</p>}
        <Field label="Area" hint="(e.g. Business, Data, Application, Technology, Security)">
          <input list="principle-areas" value={f.area} onChange={(e) => set("area", e.target.value)} />
          <datalist id="principle-areas">{(p.principle_areas || []).map((a) => <option key={a} value={a} />)}</datalist></Field>
        <Field label="Name"><input value={f.name} disabled={lib} onChange={(e) => set("name", e.target.value)} autoFocus /></Field>
        <Field label="Refines" hint="(optional: the higher-level principle this one makes more specific)">
          <select value={f.refines} onChange={(e) => set("refines", e.target.value)}>
            <option value="">nothing: a top-level principle</option>
            {others.map((x) => <option key={x.id} value={x.origin_guid || x.guid}>{x.area ? `${x.area}: ` : ""}{x.name}</option>)}</select></Field>
        {p.base_kind && !r.id && <label className="small"><input type="checkbox" checked={!!f.mandatory} onChange={(e) => set("mandatory", e.target.checked)} /> Enforced in every
          project below (otherwise optional: a project may take it out)</label>}
        <Field label="Code" hint="(optional)"><input value={f.code} disabled={lib} onChange={(e) => set("code", e.target.value)} /></Field>
        {lib ? <>{richOrPlain(f.statement)}</> : <>
          <Field label="Statement"><RichText value={asHtml(f.statement)} onChange={(v) => set("statement", v)} placeholder="What the principle says" /></Field>
          <Field label="Rationale"><RichText value={asHtml(f.rationale)} onChange={(v) => set("rationale", v)} placeholder="Why it matters" /></Field>
          <Field label="Implications"><RichText value={asHtml(f.implications)} onChange={(v) => set("implications", v)} placeholder="What it means in practice" /></Field>
        </>}
        {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- Administration > Project library (Super Admins)
// the project library (owner, 8 Nov 2026), as library models are for models: projects a Super Admin marks as library
// projects; their reference material is offered to every new project (New project › Reference)
function LibraryProjects() {
  const { data, error } = useApi("/api/v1/projects");
  const [msg, setMsg] = useState("");
  const [dlg, setDlg] = useState(null);      // {project} to stop one, {} to make one
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const sup = roles().includes("super-admin");
  const libs = data.projects.filter((p) => p.is_library);
  return (
    <div>
      <p className="quiet">Library projects keep reference material for every project: reference models, regulations, patterns, standards, useful links.
        A new project can copy any of it into its own Reference area (New project › Reference). A Super Admin makes a project a library project here, or from the project's admin page.</p>
      {msg && <p className="small status">{msg}</p>}
      {!libs.length ? <p className="quiet">No library project yet.</p> : (
        <table className="grid-table">
          <thead><tr><th>Library project</th><th className="num">Reference items</th><th>Status</th><th /></tr></thead>
          <tbody>{libs.map((p) => (
            <tr key={p.id}><td><a href={`#/projects/${p.id}/reference`}><b>{p.name}</b></a><div className="small quiet">{p.description}</div></td>
              <td className="num">{p.reference_items}</td><td><StatusChip status={p.status} /></td>
              <td className="small">{sup ? <button className="linkish" onClick={() => setDlg({ project: p })}>No longer a library project…</button> : null}</td></tr>
          ))}</tbody>
        </table>
      )}
      {sup ? <button className="primary" onClick={() => setDlg({})}>＋ Make a project a library project…</button> : null}
      {dlg && <LibraryProjectDialog project={dlg.project} projects={data.projects} onClose={() => setDlg(null)} onDone={setMsg} />}
    </div>
  );
}

// the kinds of project on a tab of their own, apart from the library of steps, deliverables and template files (owner, 8 Nov 2026)
function TemplatesTab() {
  const { data: lib, error } = useApi("/api/v1/projects/library");
  if (error) return <p className="status bad">{error}</p>;
  if (!lib) return <p className="quiet">Loading...</p>;
  return <ProjectTemplatesAdmin may={lib.may_manage} />;
}

export function ProjectLibraryAdmin() {
  const { data: lib, error } = useApi("/api/v1/projects/library");
  const [msg, setMsg] = useState("");
  const [browse, setBrowse] = useState(null);
  const [busy, setBusy] = useState(false);
  const [offer, setOffer] = useState(null);
  useEffect(() => { if (lib && offer === null) setOffer(lib.libraries.filter((l) => l.shared).map((l) => l.id)); }, [lib]); // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <p className="status bad">{error}</p>;
  if (!lib || offer === null) return <p className="quiet">Loading...</p>;
  const togaf = lib.templates;
  const missing = togaf.filter((t) => !t.has_file).length;
  async function act(fn) {
    setBusy(true); setMsg("");
    try { const r = await fn(); setMsg(`${r.message}${r.skipped?.length ? ` Not matched: ${r.skipped.join("; ")}` : ""}`); refreshAll(); }
    catch (e) { setMsg(e.message); }
    setBusy(false);
  }
  const post = (url, body) => apiFetch(url, { method: "POST", body: JSON.stringify(body || {}) });
  function upload(t) {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.onchange = () => {
      const f = inp.files[0];
      if (!f) return;
      const fd = new FormData(); fd.append("file", f);
      act(() => apiUpload(`/api/v1/projects/library/templates/${t.id}/file`, fd));
    };
    inp.click();
  }
  const togafLib = lib.libraries.find((l) => l.kind === "togaf");
  function uploadTogaf() {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = ".zip";
    inp.onchange = () => {
      const f = inp.files[0];
      if (!f) return;
      const fd = new FormData(); fd.append("file", f);
      act(() => apiUpload(`/api/v1/projects/library/libraries/${togafLib.id}/zip`, fd));
    };
    inp.click();
  }
  const toggleOffer = (id) => setOffer(offer.includes(id) ? offer.filter((x) => x !== id) : [...offer, id]);
  return (
    <div>
      <p className="quiet">What every architecture project chooses from: {lib.phases.length} phases, {lib.steps.length} steps, {lib.items.length} deliverables
        and artifacts, {lib.folders.length} folders, {lib.principles.length} principles, and the template libraries below. Kept by Super Admins;
        built from the master template repository workbook (docs/requirements).</p>
      <div className="notice-box">
        <b>{lib.setup.done ? "Projects can start now" : "Offer a template library to projects"}</b>
        <p className="small">Projects take their starting documents from the template libraries ticked <b>Offered</b> below.
          {" "}<b>EA Explorer's own</b> is ready and offered from the start, so nothing has to be set up first.</p>
        <p className="small"><b>Optional</b>, any time:</p>
        <ul className="small">
          <li><b>TOGAF 10</b>: if you have The Open Group's template deliverables, press <b>⬆ zip</b> on its row and choose the zip as you downloaded
            it. When it shows its templates, tick <b>Offered</b> and it is in every new project's choice.</li>
          <li><b>Your own</b>: <b>⬇ zip</b> on EA Explorer's library, rebrand the files (add documents to any folder), and upload it back as your own library.</li>
        </ul>
        <p className="small"><b>Next:</b> <a href="#/project-admin">Project admin › Wizards</a>: pick a kind of project (or a blank one) and the wizard
          takes you through its models, scope, goals, people and deliverables.</p>
      </div>
      <h3>Template libraries</h3>
      <table className="grid-table">
        <thead><tr><th>{lib.setup.done ? "Offered" : "Offer"}</th><th>Library</th><th>Kind</th><th>Templates</th><th>Added by</th><th /></tr></thead>
        <tbody>
          {lib.libraries.map((l) => (
            <tr key={l.id}>
              <td>{lib.setup.done
                ? (lib.may_manage ? <input type="checkbox" checked={l.shared} disabled={busy || (!l.shared && l.state !== "ready")}
                    onChange={() => act(() => post(`/api/v1/projects/library/libraries/${l.id}/share`, { shared: !l.shared }))} /> : (l.shared ? "yes" : "no"))
                : <input type="checkbox" checked={offer.includes(l.id)} disabled={l.state !== "ready"} onChange={() => toggleOffer(l.id)} />}</td>
              <td><b>{l.name}</b><div className="small quiet">{l.description || l.note}</div>
                {!l.shared && l.kind === "own" && <div className="small">private to {l.created_by}{l.project ? ` and ${l.project}` : ""}</div>}</td>
              <td className="small">{LIB_KIND[l.kind]}</td>
              <td><LibState l={l} />{l.kind === "togaf" && <span className="small quiet"> of {l.templates}</span>}</td>
              <td className="small">{l.created_by}{l.created_at ? ` · ${fmtDateTime(l.created_at)}` : ""}</td>
              <td><button className="linkish" title="Look through its folders and files (read only)" onClick={() => setBrowse(l.id)}>Open</button>{" "}
                {l.may_download && <button className="linkish" onClick={() => startDownload(`/api/v1/projects/library/libraries/${l.id}/zip`, undefined, window.location.hash).catch(() => {})}>⬇ zip</button>}
                {l.kind === "togaf" && lib.may_manage && <button className="linkish" disabled={busy || l.state === "loading"} onClick={uploadTogaf}>⬆ zip</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!lib.setup.done && lib.may_manage && (
        <div className="row-gap">
          <button className="primary" disabled={busy || !offer.length} onClick={() => act(() => post("/api/v1/projects/library/setup", { shared: offer }))}>
            Finish the setup</button>
          <span className="small quiet">{offer.length} offered to projects</span>
        </div>
      )}
      {msg && <p className="small">{msg}</p>}
      <AddLibrary />
      {browse && <TemplateBrowserDialog libraries={lib.libraries} start={browse} onClose={() => setBrowse(null)} />}
      <p className="small quiet">The kinds of project (project templates) are on their own tab: <a href="#/project-admin/templates">Project templates →</a></p>
      <p className="small quiet">Where each deliverable, artifact and template sits in the content framework (the defaults every project starts from):
        <a href="#/project-admin/template-setup"> Template setup →</a></p>
      <h3>TOGAF 10 template deliverables</h3>
      {missing > 0 && (
        <div className="notice-box">
          <b>One-time admin task: the TOGAF template deliverables ({missing} of {togaf.length} not loaded yet)</b>
          <ol>
            <li>Download <i>{lib.download.togaf_title}</i>: <a href={lib.download.togaf} target="_blank" rel="noreferrer">{lib.download.togaf}</a></li>
            <li>Press <b>⬆ Upload the TOGAF zip</b> below and choose the zip exactly as you downloaded it. Each template is stored in Documents
              unchanged, in the background (the library shows <i>loading</i>, then how many are loaded).</li>
          </ol>
          <p className="small quiet">Or unzip it into <code>library/templates/togaf</code> in the EA Explorer folder (git ignores the files: they are
            The Open Group's and may not be redistributed) and press <b>Load templates from the folder</b>; or upload a file against a template
            one at a time.</p>
          <p className="small quiet">Files in the folder now: {lib.folder_files.length ? lib.folder_files.length : "none"}.</p>
        </div>
      )}
      <div className="row-gap">
        {lib.may_manage && togafLib && <button className="primary" disabled={busy || togafLib.state === "loading"} onClick={uploadTogaf}>
          {togafLib.state === "loading" ? "Loading the TOGAF zip..." : "⬆ Upload the TOGAF zip"}</button>}
        {lib.may_manage && <button disabled={busy} onClick={() => act(() => post("/api/v1/projects/library/templates/load"))}>
          {busy ? "Working..." : "Load templates from the folder"}</button>}
        {togafLib?.note && <span className="small quiet">{togafLib.note}</span>}
      </div>
      <table className="grid-table">
        <thead><tr><th>ID</th><th>Template</th><th>Phase</th><th>Folder</th><th>File</th><th /></tr></thead>
        <tbody>
          {togaf.map((t) => (
            <tr key={t.id}>
              <td>{t.code}</td><td>{t.name}</td><td>{t.phase}</td><td className="small quiet">{t.folder}</td>
              <td className="small">{t.has_file ? <span className="rag green" title={`${t.uploaded_by} ${fmtDateTime(t.uploaded_at)}`}>{t.file_name}</span> : <span className="quiet">none</span>}</td>
              <td>{lib.may_manage && <button className="linkish" onClick={() => upload(t)}>{t.has_file ? "Replace" : "Upload"}</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Administration › Project library: the project templates (D282), kept by Super Admins and Library Admins
// a project template to read (owner, 8 Nov 2026): what it decides, laid out; and a project made from it in one click
const START_LABEL = { existing: "an existing model", empty: "a new empty model", copy: "a separate copy", child: "a child (derived, merges back)", tag: "a copy at a tag" };
function TemplateView({ t, roles, may, onClose, onChange }) {
  const s = t.spec || {};
  const Row = ({ label, children }) => <tr><th style={{ width: 190, verticalAlign: "top" }}>{label}</th><td>{children}</td></tr>;
  const list = (xs) => (xs && xs.length ? xs.join(", ") : <span className="quiet">none</span>);
  return (
    <Modal title={`${t.icon || ""} ${t.name}`} onClose={onClose} wide
      actions={<>{may && <button onClick={onChange}>Change</button>}<button onClick={onClose}>Close</button>
        {!t.retired && <a className="button primary" href={`#/projects/new?template=${t.code}`}>＋ Make a project from it</a>}</>}>
      <p>{t.description}</p>
      {t.retired && <p className="status warn small">Retired: not offered on + New project.</p>}
      <table className="grid-table small">
        <tbody>
          <Row label="Purpose">{s.purpose || <span className="quiet">–</span>}</Row>
          <Row label="Depth">{s.depth || <span className="quiet">–</span>}</Row>
          <Row label="Domains">{list(s.domains)}</Row>
          <Row label="Phases">{s.phases ? list(s.phases) : "every phase"}</Row>
          <Row label="Models by role">
            {(s.slots || []).map((x) => (
              <div key={x.role} style={{ marginBottom: 6 }}><b>{x.label}</b>{x.min ? " (needed)" : " (optional)"}{x.many ? ", one or more" : ""}
                {x.how === "referred" ? ", read only" : ""}
                <div className="quiet">starts as {(x.starts || []).map((k) => START_LABEL[k] || k).join(" or ")}{x.default_start ? `; usually ${START_LABEL[x.default_start] || x.default_start}` : ""}</div>
                {x.help && <div className="quiet">{x.help}</div>}</div>
            ))}
          </Row>
          <Row label="Goals and outcomes">{s.goals ? `yes, into the ${roles?.[s.primary] || s.primary || "project's"} model` : "no"}</Row>
          <Row label="Viewpoints">{list(s.viewpoints)}</Row>
          <Row label="Steps left out">{list(s.skip)}</Row>
          <Row label="Suggested stakeholders">{(s.stakeholders || []).length ? (s.stakeholders || []).map((x) => `${x.name}${x.role_title ? ` (${x.role_title})` : ""}`).join(", ") : <span className="quiet">none</span>}</Row>
          <Row label="Reference links">{(s.reference || []).length ? (s.reference || []).map((r, i) => <div key={i}>{r.title || r.url} <span className="quiet">{r.url}</span></div>) : <span className="quiet">none</span>}</Row>
          <Row label="When finished">{s.finish || <span className="quiet">–</span>}</Row>
          <Row label="Changed">{t.modified_by} · {fmtDateTime(t.modified_at)}</Row>
        </tbody>
      </table>
    </Modal>
  );
}

function ProjectTemplatesAdmin({ may }) {
  const { data } = useApi("/api/v1/projects/templates?all=true");
  const [edit, setEdit] = useState(null);
  const [view, setView] = useState(null);
  const [msg, setMsg] = useState("");
  async function save(t, patch) {
    setMsg("");
    try {
      const out = t.code ? await apiFetch(`/api/v1/projects/templates/${t.code}`, { method: "PUT", body: JSON.stringify({ ...t, ...patch }) })
        : await apiFetch("/api/v1/projects/templates", { method: "POST", body: JSON.stringify({ ...t, ...patch }) });
      setMsg(`Saved ${out.name}.`); setEdit(null); refreshAll();
    } catch (e) { setMsg(e.message); }
  }
  if (!data) return null;
  return (
    <div>
      <h3>Project templates</h3>
      <p className="small quiet">The kinds of project offered on + New project: each a wizard with its decisions taken (models by role, purpose,
        scope, phases, viewpoints, goals, suggested stakeholders, reference links). Make a new one, change one, retire one, or save a project as a new
        one (on the project: Save as a project template).</p>
      {may && <p><button className="primary" onClick={() => setEdit({ name: "", icon: "📁", description: "", text: JSON.stringify({
        purpose: "project", depth: "", domains: [], phases: null, viewpoints: [], goals: true, primary: null, skip: [], finish: "",
        slots: [{ role: "current", label: "Current state", starts: ["existing"], min: 1 }], stakeholders: [], reference: [] }, null, 1) })}>＋ New template</button></p>}
      <table className="grid-table small">
        <thead><tr><th>Template</th><th>Models by role</th><th>Goals into</th><th>Changed</th><th /></tr></thead>
        <tbody>
          {data.templates.map((t) => (
            <tr key={t.code} className={t.retired ? "quiet" : ""}>
              <td>{t.icon} <button className="linkish" onClick={() => setView(t)} title="Open it to read"><b>{t.name}</b></button>{t.retired && " (retired)"}
                <div className="quiet">{t.description}</div></td>
              <td>{(t.spec.slots || []).map((x) => `${x.label} (${x.starts.join("/")})`).join(", ")}</td>
              <td>{t.spec.primary ? data.roles[t.spec.primary] : "none"}</td>
              <td>{t.modified_by} · {fmtDateTime(t.modified_at)}</td>
              <td className="nowrap"><button className="linkish" onClick={() => setView(t)}>Open</button>
                {!t.retired && <> · <a href={`#/projects/new?template=${t.code}`}>＋ New project</a></>}
                {may && <> · <button className="linkish" onClick={() => setEdit({ ...t, text: JSON.stringify(t.spec, null, 1) })}>Change</button>{" "}
                <button className="linkish" onClick={() => save(t, { retired: !t.retired })}>{t.retired ? "Offer again" : "Retire"}</button></>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {msg && <p className="small">{msg}</p>}
      {view && <TemplateView t={view} roles={data.roles} may={may} onClose={() => setView(null)}
        onChange={() => { setEdit({ ...view, text: JSON.stringify(view.spec, null, 1) }); setView(null); }} />}
      {edit && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Change a project template">
          <div className="modal">
            <h3>{edit.code ? `Change ${edit.name}` : "A new project template"}</h3>
            <label className="field">Name <input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></label>
            <label className="field">Icon <input value={edit.icon} onChange={(e) => setEdit({ ...edit, icon: e.target.value })} /></label>
            <label className="field">Description <textarea rows={2} value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></label>
            <label className="field">Its decisions (JSON: slots, purpose, depth, domains, phases or items, viewpoints, goals, primary, skip, finish)
              <textarea rows={14} className="mono" value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })} /></label>
            <div className="row-gap"><button className="primary" onClick={() => { try { save(edit, { spec: JSON.parse(edit.text) }); } catch (e) { setMsg(`Not JSON: ${e.message}`); } }}>Save</button>
              <button onClick={() => setEdit(null)}>Cancel</button></div>
          </div>
        </div>
      )}
    </div>
  );
}

