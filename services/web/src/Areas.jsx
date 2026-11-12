// The five areas (D285): the start page's tiles and the top menu.
//   System admin      #/admin              settings, users, health, backups ... and the platform wizards (D284)
//   Model admin       #/model-admin        pick a model or start one; then every model wizard (ModelAdmin.jsx, D283)
//   Project admin     #/project-admin      new project, edit, finish, save as a template; the project templates and library
//   Architecture work #/work               my projects and my models side by side; one opens the project or model page
//   Everything else   #/more               search, notifications, change log, the model library, MCP, API, the products
// Every tile shows for everyone; one the person may not use is greyed with the reason (as the menus are).
import PinButton from "./PinButton";
import { lazy, Suspense, useState } from "react";
import ProjectTree, { flatten } from "./ProjectTree";
import { can, myInfo, needsRole, partOn } from "./auth";
import { useApi } from "./ModelViews";
import { fmtDateTime } from "./fmt";
import { isRetiredModel, isRetiredProject, KindMark, ShowRetired, useShowRetired } from "./ModelMarks";

const ModelTree = lazy(() => import("./ModelTree"));

// who may use Model admin and Project admin: one definition, with the top menu's (menu.js, D586)
import { mayModelAdmin, mayProjectAdmin } from "./menu";
export { mayModelAdmin, mayProjectAdmin };

export const AREAS = [
  { key: "system", name: "System admin", href: "#/admin", icon: "⚙",
    text: "Settings, users and roles, health, containers, backups and restores, the SQL window, licences and services",
    ok: () => true },
  { key: "model", name: "Model admin", href: "#/model-admin", icon: "🧭",
    text: "Create, copy and derive models; merge into the parent and freeze; propagate; split; extend or upgrade the metamodel; lock, freeze, tag, promote, hand over, download, archive",
    ok: mayModelAdmin, why: () => needsRole(["model-creator", "library-admin", "model-admin"]) },
  { key: "project", name: "Project admin", href: "#/project-admin", icon: "🗂", part: "projects",
    text: "Set up a new architecture project, change one while it runs, finish it, save it as a template; the project templates and the project library",
    ok: mayProjectAdmin, why: () => "Needs a global role (any). Ask a User Admin to give you one." },
  { key: "work", name: "Architecture work", href: "#/work", icon: "✏",
    text: "Your projects and your models: open one to enter data, draw, analyse gaps, report, and deliver and sign off documents",
    ok: () => true },
  { key: "repository", name: "Architecture repository", short: "Repository", href: "#/repository", icon: "🏛", part: "repository",
    text: "The Architecture Repository's parts (framework, landscape, reference library, standards, governance log, capability), each leading to what is held for it",
    ok: () => true },
  { key: "reflib", name: "Reference library", short: "References", href: "#/reference-library", icon: "📚", part: "references",
    text: "The organisation's reference material: standards, regulations, reference architectures, research and links; search inside documents",
    ok: () => true },
  { key: "more", name: "Everything else", href: "#/more", icon: "…",
    text: "Search, notifications and background tasks, the change log, the model library, MCP, the API and the products (reports, documents, draw.io)",
    ok: () => true },
];

// which area a page belongs to, for the top menu
export function areaOf(route) {
  const r = route || "#/";
  if (/^#\/(admin|users|heartbeat|sql)/.test(r)) return "system";
  if (r.startsWith("#/model-admin")) return "model";
  if (r.startsWith("#/repository")) return "repository";
  if (r.startsWith("#/reference-library")) return "reflib";
  if (r.startsWith("#/project-admin") || /^#\/projects\/(new|[^/]+\/edit)/.test(r)) return "project";
  if (r.startsWith("#/work") || r.startsWith("#/metamodel") || r.startsWith("#/projects") || r.startsWith("#/compare")) return "work";
  if (r === "#/" || r === "#") return "";
  return "more";
}

// the areas of the parts switched on (D329): a part switched off is not shown at all
const shown = () => AREAS.filter((a) => !a.part || partOn(a.part));

export function AreaTiles() {
  return (
    <div className="area-grid">
      {shown().map((a) => (a.ok()
        ? <a key={a.key} className={`area-tile area-${a.key}`} href={a.href}>
          <span className="area-icon" aria-hidden="true">{a.icon}</span><h2>{a.name}</h2><p>{a.text}</p></a>
        : <div key={a.key} className={`area-tile area-${a.key} off`} aria-disabled="true" title={a.why ? a.why() : ""}>
          <span className="area-icon" aria-hidden="true">{a.icon}</span><h2>{a.name}</h2><p>{a.text}</p>
          <span className="badge">{a.why ? a.why() : ""}</span></div>))}
    </div>
  );
}

// ---------------------------------------------------------------- Architecture work (#/work)
// My projects and my models side by side: the ones I have a role on (a Super Admin sees all), most recently changed first
const PROJECT_STATUS = { active: "active", finishing: "finishing", frozen: "frozen", merged: "merged", closed: "closed" };

export function ArchitectureWork() {
  // two tabs, a list or tiles, filters and pins (owner, 8 Nov 2026); the pins are favourites, kept per person on the server
  const route = window.location.hash;
  const projectsOn = partOn("projects");
  const [tabWanted, setTab] = useState(() => (/[?&]tab=models/.test(route) ? "models" : "projects"));
  const tab = projectsOn ? tabWanted : "models";
  const [view, setView] = useState(() => (route.match(/[?&]view=(tiles|list|tree|levels)/) || [])[1]
    || (() => { try { return localStorage.getItem("eax-work-view") || "tiles"; } catch { return "tiles"; } })());
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [purpose, setPurpose] = useState("");
  const [kind, setKind] = useState("");
  const [onlyPinned, setOnlyPinned] = useState(false);
  // the landscape level of a model comes from its project's depth (owner, 8 Nov 2026, D318); transition: its role there
  const [level, setLevel] = useState(() => (route.match(/[?&]level=(strategic|segment|capability|transition)/) || [])[1] || "");
  const { data: lv } = useApi(tab === "models" && partOn("repository") ? "/api/v1/repository/model-levels" : null);
  const { data: pd, error: pe } = useApi(projectsOn ? "/api/v1/projects" : null);
  const { data: models, error: me } = useApi("/api/v1/models");
  const [showRetired, setShowRetired] = useShowRetired();     // frozen and archived out of the way (D360)
  const { data: favs } = useApi("/api/v1/favourites");
  const pinned = new Set((favs || []).filter((f) => f.kind === "project" || f.kind === "model").map((f) => `${f.kind}:${f.id}`));
  const mine = new Set((myInfo()?.models || []).map((m) => String(m.id)));
  const super_ = can("models.delete");
  const setV = (v) => { setView(v); try { localStorage.setItem("eax-work-view", v); } catch { /* the view is a convenience */ } };
  const text = (x) => !q.trim() || `${x.name} ${x.description || ""} ${x.purpose || ""}`.toLowerCase().includes(q.trim().toLowerCase());
  const byPin = (k) => (a, b) => (pinned.has(`${k}:${b.id}`) ? 1 : 0) - (pinned.has(`${k}:${a.id}`) ? 1 : 0);
  const ps = (pd?.projects || []).filter((p) => text(p) && (!status || p.status === status) && (!purpose || p.purpose === purpose)
      && (showRetired || status || !isRetiredProject(p))
      && (!onlyPinned || pinned.has(`project:${p.id}`)))
    .sort((a, b) => byPin("project")(a, b) || (a.status === "active" ? 0 : 1) - (b.status === "active" ? 0 : 1)
      || String(b.modified_at || b.created_at || "").localeCompare(String(a.modified_at || a.created_at || "")));
  const allModels = (models || []).filter((m) => super_ || mine.has(String(m.id)));
  const inLevel = (m, l) => (lv?.models || []).some((x) => x.model_id === String(m.id) && (l === "transition" ? x.role === "transition" : x.level === l));
  const ms = allModels.filter((m) => (!level || inLevel(m, level)) && text(m) && (!kind || (kind === "project" ? m.kind === "project" : m.kind !== "project"))
      && (!status || (status === "frozen" ? m.frozen_at : !m.frozen_at)) && (!onlyPinned || pinned.has(`model:${m.id}`))
      && (showRetired || status === "frozen" || !isRetiredModel(m)))
    .sort((a, b) => byPin("model")(a, b) || (a.kind === "project" ? 0 : 1) - (b.kind === "project" ? 0 : 1)
      || String(b.modified_at || "").localeCompare(String(a.modified_at || "")));
  const purposes = [...new Set((pd?.projects || []).map((p) => p.purpose).filter(Boolean))].sort();
  const Pin = ({ k, x }) => <PinButton k={k} x={x} pins={pinned} small />;
  return (
    <section className="work-home">
      <h1>Architecture work</h1>
      <p className="quiet">Your projects and your models. Open one to work in it: data entry, grids, diagrams, views, gap analysis,
        reports, and the project's deliverables and sign-off. Setting up and changing models and projects is in Model admin and Project admin.</p>
      <div className="tabs" role="tablist">
        {projectsOn && <button role="tab" aria-selected={tab === "projects"} className={`tab${tab === "projects" ? " on" : ""}`} onClick={() => { setTab("projects"); setStatus(""); }}>
          Projects <span className="small quiet">{(pd?.projects || []).filter((p) => showRetired || !isRetiredProject(p)).length || ""}</span></button>}
        <button role="tab" aria-selected={tab === "models"} className={`tab${tab === "models" ? " on" : ""}`} onClick={() => { setTab("models"); setStatus(""); }}>
          Models <span className="small quiet">{allModels.filter((m) => showRetired || !isRetiredModel(m)).length || ""}</span></button>
      </div>
      <div className="row-gap filters">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={tab === "projects" ? "Search projects" : "Search models"} aria-label="Search" />
        {tab === "projects" ? <>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">Any status</option>
            {Object.keys(PROJECT_STATUS).map((k) => <option key={k} value={k}>{PROJECT_STATUS[k]}</option>)}</select>
          <select value={purpose} onChange={(e) => setPurpose(e.target.value)} aria-label="Purpose"><option value="">Any purpose</option>
            {purposes.map((x) => <option key={x} value={x}>{x}</option>)}</select>
        </> : <>
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind"><option value="">Every kind</option>
            <option value="project">Project models</option><option value="other">Library and root models</option></select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">Any state</option>
            <option value="open">Open</option><option value="frozen">Frozen</option></select>
          <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Landscape level" title="From the depth of the project the model is in">
            <option value="">Any level</option>{Object.entries(LEVEL_NAMES).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select>
        </>}
        <label className="small"><input type="checkbox" checked={onlyPinned} onChange={(e) => setOnlyPinned(e.target.checked)} /> pinned only</label>
        <ShowRetired count={tab === "projects" ? (pd?.projects || []).filter(isRetiredProject).length : allModels.filter(isRetiredModel).length}
          show={showRetired} setShow={setShowRetired} />
        <span className="push-right view-toggle" role="group" aria-label="View">
          <button className={view === "tiles" ? "on" : ""} onClick={() => setV("tiles")} title="Tiles">▦ Tiles</button>
          <button className={view === "list" ? "on" : ""} onClick={() => setV("list")} title="List">☰ List</button>
          <button className={view === "tree" ? "on" : ""} onClick={() => setV("tree")} title="Hierarchy">🌳 Hierarchy</button>
          {tab === "projects" && <button className={view === "repo" ? "on" : ""} onClick={() => setV("repo")} title="Repository">🏛 Repository</button>}
          {tab === "models" && <button className={view === "levels" ? "on" : ""} onClick={() => setV("levels")} title="By landscape level">🗺 By level</button>}
        </span>
      </div>
      {tab === "projects" && <>
        {pe && <p className="status bad">{pe}</p>}
        {pd && !ps.length && <p className="quiet">{(pd.projects || []).length ? "No project matches." : "You are on no project yet."}
          {!(pd.projects || []).length && mayProjectAdmin() && <> Start one in <a href="#/project-admin">Project admin</a>.</>}</p>}
        {view === "tree" ? <ProjectHierarchy projects={ps} Pin={Pin} />
          : view === "repo" ? <div className="repo-placeholder"><h3>Repository view</h3>
            <p className="quiet">The projects seen through the Architecture Repository: designed in phase 13.0.9. Empty for now.</p></div>
          : view === "tiles" || view === "levels" ? <div className="work-tiles">
          {ps.map((p) => (
            <a key={p.id} className={`work-tile${isRetiredProject(p) ? " is-retired" : ""}`} href={`#/projects/${p.id}`}>
              <div className="tile-head"><b>{p.name}</b><Pin k="project" x={p} /></div>
              <div className="small"><span className={`rag ${p.status === "active" ? "green" : "off"} small`}>{PROJECT_STATUS[p.status] || p.status}</span> {p.purpose}
                {p.is_library && <span className="chip">library project</span>}</div>
              {p.description && <p className="small quiet tile-desc">{p.description}</p>}
              <div className="small quiet">{p.models} model{p.models === 1 ? "" : "s"} · {p.documents} document{p.documents === 1 ? "" : "s"}</div>
              {p.completion && <div className="small"><span className="completion-bar" aria-hidden="true"><span style={{ width: `${p.completion.percent}%` }} /></span> {p.completion.percent}% complete</div>}
            </a>
          ))}
        </div> : <table className="grid-table">
          <thead><tr><th /><th>Project</th><th>Status</th><th>Purpose</th><th className="num">Models</th><th className="num">Documents</th><th>Complete</th></tr></thead>
          <tbody>{ps.map((p) => (
            <tr key={p.id} className={isRetiredProject(p) ? "is-retired" : undefined}><td><Pin k="project" x={p} /></td><td><a href={`#/projects/${p.id}`}><b>{p.name}</b></a></td>
              <td><span className={`rag ${p.status === "active" ? "green" : "off"} small`}>{PROJECT_STATUS[p.status] || p.status}</span></td>
              <td>{p.purpose}</td><td className="num">{p.models}</td><td className="num">{p.documents}</td>
              <td className="small">{p.completion ? `${p.completion.percent}%` : ""}</td></tr>
          ))}</tbody>
        </table>}
      </>}
      {tab === "models" && <>
        {me && <p className="status bad">{me}</p>}
        {models && !ms.length && <p className="quiet">{allModels.length ? "No model matches." : "You have no role on a model yet. A model's Model Admin gives you one."}</p>}
        {view === "levels" ? <ModelsByLevel models={ms} lv={lv} Pin={Pin} only={level} />
          : view === "tree" ? <ModelHierarchy models={models || []} shown={ms} Pin={Pin} />
          : view === "tiles" || view === "repo" ? <div className="work-tiles">
          {ms.map((m) => (
            <a key={m.id} className={`work-tile${isRetiredModel(m) ? " is-retired" : ""}`} href={`#/metamodel/${m.id}`}>
              <div className="tile-head"><span><KindMark m={m} /> <b>{m.name}</b></span><Pin k="model" x={m} /></div>
              {m.frozen_at && <span className="rag off small">frozen</span>}
              {m.description && <p className="small quiet tile-desc">{m.description}</p>}
              <div className="small quiet">{m.entity_count ?? 0} entities · {m.relationship_count ?? 0} relationships
                {m.parent_model_name ? ` · merges into ${m.parent_model_name}` : ""}</div>
              {m.modified_at && <div className="small quiet">changed {fmtDateTime(m.modified_at)}</div>}
            </a>
          ))}
        </div> : <table className="grid-table">
          <thead><tr><th /><th>Model</th><th className="num">Entities</th><th className="num">Relationships</th><th>Merges into</th><th>Changed</th></tr></thead>
          <tbody>{ms.map((m) => (
            <tr key={m.id} className={isRetiredModel(m) ? "is-retired" : undefined}><td><Pin k="model" x={m} /></td><td><KindMark m={m} /> <a href={`#/metamodel/${m.id}`}><b>{m.name}</b></a>{m.frozen_at && <span className="rag off small"> frozen</span>}</td>
              <td className="num">{m.entity_count ?? 0}</td><td className="num">{m.relationship_count ?? 0}</td><td className="small">{m.parent_model_name || ""}</td>
              <td className="small">{m.modified_at ? fmtDateTime(m.modified_at) : ""}</td></tr>
          ))}</tbody>
        </table>}
        <p className="small"><a href="#/metamodel">All the models you may open</a> · <a href="#/compare">Compare and gap analysis</a></p>
      </>}
    </section>
  );
}

// Models by landscape level (owner, 8 Nov 2026, D318): Strategic, Segment and Capability architectures from the depth of
// each project a model is in, and Transition architectures from its role; a model in several projects shows in each
const LEVEL_NAMES = { strategic: "Strategic", segment: "Segment", capability: "Capability", transition: "Transition" };
function ModelsByLevel({ models, lv, Pin, only }) {
  if (!lv) return <p className="quiet">Loading...</p>;
  const byId = Object.fromEntries(models.map((m) => [String(m.id), m]));
  const col = (l) => {
    const seen = new Map();
    for (const x of lv.models) {
      if (!byId[x.model_id] || (l === "transition" ? x.role !== "transition" : x.level !== l)) continue;
      if (!seen.has(x.model_id)) seen.set(x.model_id, []);
      seen.get(x.model_id).push(x);
    }
    return [...seen.entries()];
  };
  const none = models.filter((m) => !lv.models.some((x) => x.model_id === String(m.id) && x.level));
  return (
    <div>
      <p className="small quiet">A model's level comes from the depth of the project it is in (the project wizard's Scope step); Transition from its
        role in a project. A model in several projects shows under each.</p>
      <div className="level-cols">
        {Object.entries(LEVEL_NAMES).filter(([l]) => !only || l === only).map(([l, n]) => {
          const rows = col(l);
          return (
            <div key={l} className="level-col">
              <h3>{n} <span className="small quiet">{rows.length}</span></h3>
              {!rows.length && <p className="small quiet">None.</p>}
              {rows.map(([id, xs]) => (
                <div key={id} className="level-item">
                  <span><KindMark m={byId[id]} /> <a href={`#/metamodel/${id}`}><b>{byId[id].name}</b></a> <Pin k="model" x={byId[id]} /></span>
                  <div className="small quiet">{xs.map((x) => <span key={x.project_id}><a href={`#/projects/${x.project_id}/models`}>{x.project}</a>{x.role ? ` (${x.role})` : ""} </span>)}</div>
                </div>
              ))}
            </div>
          );
        })}
      </div>
      {none.length > 0 && <p className="small quiet">Not in a project with a depth: {none.map((m) => m.name).join(", ")}.</p>}
    </div>
  );
}

// the project hierarchy (phase 13.1, D303): the bases and library projects, and your projects below the one each derives from
function ProjectHierarchy({ projects, Pin }) {
  const { data } = useApi("/api/v1/projects/bases");
  const [graph, setGraph] = useState(true);
  if (!data) return <p className="quiet">Loading...</p>;
  const toggle = (
    <div className="view-toggle" role="group" aria-label="Hierarchy view" style={{ margin: "8px 0" }}>
      <button className={graph ? "on" : ""} onClick={() => setGraph(true)}>🌳 Graph</button>
      <button className={!graph ? "on" : ""} onClick={() => setGraph(false)}>☰ Indented</button>
    </div>
  );
  if (graph) {
    return <div className="work-tree">{toggle}<Suspense fallback={<p className="quiet">Loading the tree...</p>}>
      <ProjectTree items={flatten(data.nodes, new Set(projects.map((p) => p.id)))} /></Suspense></div>;
  }
  const mine = new Set(projects.map((p) => p.id));
  const byBase = (id) => projects.filter((p) => p.base_id === id);
  const kids = (id) => data.nodes.filter((n) => n.parent === id);
  const LABEL = { empty: "Empty project", togaf: "TOGAF 10 project", org: "Organisation base" };
  const Node = ({ n }) => (
    <li>
      <a href={`#/projects/${n.id}`}><b>{n.name}</b></a> <span className="chip small">{n.base_kind ? LABEL[n.base_kind] : "library project"}</span>
      <ul className="tree-list">
        {kids(n.id).map((c) => <Node key={c.id} n={c} />)}
        {byBase(n.id).filter((p) => !p.is_library).map((p) => <li key={p.id}><Pin k="project" x={p} /> <a href={`#/projects/${p.id}`}>{p.name}</a>
          <span className="small quiet"> {PROJECT_STATUS[p.status] || p.status} · {p.purpose}{p.completion ? ` · ${p.completion.percent}%` : ""}</span></li>)}
      </ul>
    </li>
  );
  const orphans = projects.filter((p) => !p.base_id || !data.nodes.some((n) => n.id === p.base_id));
  return (
    <div className="work-tree">
      {toggle}
      <ul className="tree-list root">{data.nodes.filter((n) => !n.parent).map((n) => <Node key={n.id} n={n} />)}</ul>
      {orphans.filter((p) => mine.has(p.id) && !p.is_library).length > 0 && <>
        <h4>Not under a base</h4>
        <ul className="tree-list">{orphans.filter((p) => !p.is_library).map((p) => <li key={p.id}><a href={`#/projects/${p.id}`}>{p.name}</a></li>)}</ul></>}
    </div>
  );
}

// the model hierarchy: each model under its parent (derived) or, failing that, the model it was created from
function ModelHierarchy({ models, shown, Pin }) {
  const [graph, setGraph] = useState(true);
  const toggle = (
    <div className="view-toggle" role="group" aria-label="Hierarchy view" style={{ margin: "8px 0" }}>
      <button className={graph ? "on" : ""} onClick={() => setGraph(true)}>🌳 Graph</button>
      <button className={!graph ? "on" : ""} onClick={() => setGraph(false)}>☰ Indented</button>
    </div>
  );
  const ids = new Set(models.map((m) => String(m.id)));
  const show = new Set(shown.map((m) => String(m.id)));
  const up = (m) => (m.parent_model_id && ids.has(String(m.parent_model_id)) ? String(m.parent_model_id)
    : m.source_model_id && ids.has(String(m.source_model_id)) ? String(m.source_model_id) : null);
  const kids = (id) => models.filter((m) => up(m) === id);
  const has = (m) => show.has(String(m.id)) || kids(String(m.id)).some(has);   // a branch shows when it leads to a model shown
  const Node = ({ m }) => (
    <li>
      <KindMark m={m} /> {show.has(String(m.id)) && <Pin k="model" x={m} />}<a href={`#/metamodel/${m.id}`}>{show.has(String(m.id)) ? <b>{m.name}</b> : m.name}</a>
      <span className="small quiet"> {m.kind_name || m.kind}{m.parent_model_id && up(m) === String(m.parent_model_id) ? " · derived" : ""}{m.frozen_at ? " · frozen" : ""}</span>
      <ul className="tree-list">{kids(String(m.id)).filter(has).map((c) => <Node key={c.id} m={c} />)}</ul>
    </li>
  );
  if (graph) {     // the same drawn tree as Models > Hierarchy, of the models shown and those above them
    const keep = models.filter(has);
    return <div className="work-tree">{toggle}<Suspense fallback={<p className="quiet">Loading the tree...</p>}>
      <ModelTree models={keep} /></Suspense></div>;
  }
  return (
    <div className="work-tree">
      {toggle}
      <p className="small quiet">Each model sits under the model it derives from (merges into), or else the one it was created from. Bold: the models you work on.</p>
      <ul className="tree-list root">{models.filter((m) => !up(m) && has(m)).map((m) => <Node key={m.id} m={m} />)}</ul>
    </div>
  );
}
