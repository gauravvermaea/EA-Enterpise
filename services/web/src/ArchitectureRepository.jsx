// The Architecture Repository (owner, 8 Nov 2026, D301, D318): its parts as TOGAF gives them, drawn as a map, each
// item opening the screen that holds it today. For the organisation (#/repository) and for one project (its
// Enterprise Repository (Project Scope) tab). Within a project everything is limited to the project, except the
// reference library and the model library: those offer both the project's and the organisation's, in a small menu.
// The organisation's read-only views across projects (decisions, compliance and capability assessments, people and
// skills) show only the projects the person is on (a Super Admin: all); records are changed inside each project.
import { useEffect, useRef, useState } from "react";
import { useApi } from "./ModelViews";
import { fmtDateTime } from "./fmt";

const LATER = "to be designed (phase 13.0.9)";
const REF_LATER = "the reference library's structure is discussed when it is built";

function orgParts(base) {
  const ob = base ? `#/projects/${base.id}` : null;
  return {
    framework: { title: "Architecture framework", colour: "#1f7a3a", items: [
      { label: "Architecture method", href: ob && `${ob}/phases`, note: "the Organisation base's phases, steps and document classes" },
      { label: "Content metamodel", href: "#/metamodel", note: "every metamodel you may open", also: [["Architecture work › Models", "#/work?tab=models"]] },
    ] },
    landscape: { title: "Architecture landscape", colour: "#2d3f8f", items: [
      { label: "Strategic architectures", href: "#/work?tab=models&view=tiles&level=strategic", note: "models in strategic projects" },
      { label: "Segment architectures", href: "#/work?tab=models&view=tiles&level=segment", note: "models in segment projects" },
      { label: "Capability architectures", href: "#/work?tab=models&view=tiles&level=capability", note: "models in capability projects" },
      { label: "Transition architectures", href: "#/work?tab=models&view=tiles&level=transition", note: "models with the transition role" },
    ] },
    reference: { title: "Reference library", colour: "#2d3f8f", items: [
      { label: "Foundation architectures", href: "#/reference-library", note: REF_LATER },
      { label: "Common systems architectures", href: "#/reference-library", note: REF_LATER },
      { label: "Industry architectures", href: "#/reference-library", note: REF_LATER },
      { label: "Organisation's own architectures", href: "#/reference-library", note: REF_LATER },
    ] },
    standards: { title: "Standards information base", colour: "#2d3f8f", items: [
      { label: "Business standards", href: "#/reference-library", note: "the reference library, for now" },
      { label: "Data standards", href: "#/reference-library", note: "the reference library, for now" },
      { label: "Application standards", href: "#/reference-library", note: "the reference library, for now" },
      { label: "Technology standards", href: "#/reference-library", note: "the reference library, for now" },
    ] },
    governance: { title: "Governance log", colour: "#8f1d1d", items: [
      { label: "Decision log", href: "#/repository/decisions", note: "every project's decisions, read only" },
      { label: "Compliance assessments", href: "#/repository/compliance", note: "every project's, read only" },
      { label: "Capability assessments", href: "#/repository/capability", note: "every project's, read only" },
      { label: "Calendar", href: null, note: LATER },
      { label: "Project portfolio", href: "#/work?tab=projects", note: "all the projects" },
      { label: "Performance measurement", href: "#/admin/quality", note: "data quality; each project's completion" },
    ] },
    capability: { title: "Architecture capability", colour: "#1f7a3a", items: [
      { label: "Skills repository", href: "#/repository/skills", note: "people on the projects, by skill" },
      { label: "Organisation structure", href: "#/repository/people", note: "who works on each project, by role" },
      { label: "Architecture charter", href: ob && `${ob}/charter`, note: "the Organisation base's charter" },
    ] },
    outside: [
      { label: "External reference models", href: "#/library?kind=reference", note: "the model library, reference models" },
      { label: "External standards", href: "#/reference-library", note: "the reference library (an external standards folder: to be discussed)" },
      { label: "Architecture board", href: "#/admin/users", note: "users and their roles", tall: true },
    ],
  };
}

// within a project: the project only, but the libraries offer the project's and the organisation's
function projectParts(p) {
  const pj = `#/projects/${p.id}`;
  const depth = (p.scope?.depth || "").toLowerCase();
  const level = (l, n) => ({ label: `${n} architectures`, href: depth === l ? `${pj}/models` : null,
    note: depth === l ? "the project's models" : depth ? `this project is ${depth}` : "the project's depth is not set (Edit › Scope)" });
  const refBoth = { choose: [["The project's Reference area", `${pj}/reference`], ["The organisation's reference library", "#/reference-library"]],
    note: "the project's or the organisation's" };
  const gov = (kind) => `${pj}/governance?kind=${encodeURIComponent(kind)}`;
  const transition = (p.models || []).some((m) => m.role === "transition");
  return {
    framework: { title: "Architecture framework", colour: "#1f7a3a", items: [
      { label: "Architecture method", href: `${pj}/phases`, note: "the project's phases, steps and document classes" },
      { label: "Content metamodel", href: `${pj}/models`, note: "the project's models and their metamodels", also: [["Content framework", `${pj}/content`]] },
    ] },
    landscape: { title: "Architecture landscape", colour: "#2d3f8f", items: [
      level("strategic", "Strategic"), level("segment", "Segment"), level("capability", "Capability"),
      { label: "Transition architectures", href: transition ? `${pj}/models` : null,
        note: transition ? "the project's transition models" : "no transition model in the project" },
    ] },
    reference: { title: "Reference library", colour: "#2d3f8f", items: [
      { label: "Foundation architectures", ...refBoth },
      { label: "Common systems architectures", ...refBoth },
      { label: "Industry architectures", ...refBoth },
      { label: "Organisation's own architectures", ...refBoth },
    ] },
    standards: { title: "Standards information base", colour: "#2d3f8f", items: [
      { label: "Business standards", href: `${pj}/standards`, note: "the project's standards" },
      { label: "Data standards", href: `${pj}/standards`, note: "the project's standards" },
      { label: "Application standards", href: `${pj}/standards`, note: "the project's standards" },
      { label: "Technology standards", href: `${pj}/standards`, note: "the project's standards" },
    ] },
    governance: { title: "Governance log", colour: "#8f1d1d", items: [
      { label: "Decision log", href: gov("Decision"), note: "the project's decisions" },
      { label: "Compliance assessments", href: gov("Compliance assessment"), note: "the project's" },
      { label: "Capability assessments", href: gov("Capability assessment"), note: "the project's" },
      { label: "Calendar", href: null, note: LATER },
      { label: "Project portfolio", href: `${pj}/home`, note: "this project" },
      { label: "Performance measurement", href: `${pj}/quality`, note: "the data quality of the project's models", also: [["Project report", `${pj}/report`]] },
    ] },
    capability: { title: "Architecture capability", colour: "#1f7a3a", items: [
      { label: "Skills repository", href: `${pj}/organisation`, note: "the project's people and their skills" },
      { label: "Organisation structure", href: `${pj}/organisation`, note: "who works on the project, by role" },
      { label: "Architecture charter", href: `${pj}/charter`, note: "the project's charter" },
    ] },
    outside: [
      { label: "External reference models", choose: [["The project's models", `${pj}/models`], ["The model library, reference models", "#/library?kind=reference"]],
        note: "the project's or the model library" },
      { label: "External standards", choose: [["The project's Reference area", `${pj}/reference`], ["The organisation's reference library", "#/reference-library"]],
        note: "the project's or the organisation's" },
      { label: "Architecture board", href: `${pj}/signoff`, note: "the project's sign-off people", tall: true },
    ],
  };
}

// an item that offers two places: a small menu, closed by a click elsewhere or Escape
function Choose({ i, className }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const off = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", off); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", off); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={ref} className={className} role="button" tabIndex={0} title={i.note} aria-haspopup="menu" aria-expanded={open}
      onClick={() => setOpen(!open)} onKeyDown={(e) => { if (e.key === "Enter") setOpen(!open); }} style={{ cursor: "pointer", position: "relative" }}>
      <b>{i.label} ▾</b><span>{i.note}</span>
      {open && <div className="ar-choose" role="menu" onClick={(e) => e.stopPropagation()}>
        {i.choose.map(([l, h]) => <a key={h} role="menuitem" href={h} onClick={() => setOpen(false)}>{l}</a>)}
      </div>}
    </div>
  );
}

function Item({ i }) {
  if (i.choose) return <Choose i={i} className="ar-item" />;
  if (!i.href) return <div className="ar-item off" title={i.note}><b>{i.label}</b><span>{i.note}</span></div>;
  return (
    <a className="ar-item" href={i.href} title={i.note}><b>{i.label}</b><span>{i.note}</span>
      {(i.also || []).map(([l, h]) => <span key={h}>also <span role="link" tabIndex={0} className="ar-also"
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); window.location.hash = h; }}>{l}</span></span>)}</a>
  );
}

function Part({ part, cols }) {
  return (
    <div className="ar-part" style={{ borderColor: part.colour }}>
      <div className="ar-title" style={{ background: part.colour }}>{part.title}</div>
      <div className="ar-items" style={{ gridTemplateColumns: `repeat(${cols || 1}, minmax(0, 1fr))` }}>
        {part.items.map((i) => <Item key={i.label} i={i} />)}
      </div>
    </div>
  );
}

function Outside({ i }) {
  const cls = `ar-ext${i.tall ? " tall" : ""}`;
  if (i.choose) return <Choose i={i} className={cls} />;
  return <a className={cls} href={i.href} title={i.note}><b>{i.label}</b><span>{i.note}</span></a>;
}

export function RepositoryMap({ p }) {
  const { data } = useApi(p ? null : "/api/v1/repository/summary");
  const x = p ? projectParts(p) : orgParts(data?.org_base);
  return (
    <div>
      {p ? <p className="quiet">This project's part of the Enterprise Repository, in the shape TOGAF gives the Architecture Repository. Every link stays
        within the project, except the reference library and the model library, which offer the project's and the organisation's.</p>
        : <p className="quiet">The organisation's Architecture Repository in the shape TOGAF gives it. Each item opens the screen that holds it, showing
        everything you may see (admins: every project and every user); the decision log, the assessments and the people are read only here (changed
        inside each project).</p>}
      <div className="ar-wrap">
        <div className="ar-main">
          <Part part={x.framework} cols={2} />
          <div className="ar-mid">
            <Part part={x.landscape} />
            <div className="ar-right">
              <Part part={x.reference} />
              <Part part={x.standards} />
            </div>
          </div>
          <Part part={x.governance} cols={3} />
          <Part part={x.capability} cols={3} />
        </div>
        <div className="ar-outside">
          {x.outside.map((i) => <Outside key={i.label} i={i} />)}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the organisation's read-only views (D318)
const GOV = { decisions: "Decision log", compliance: "Compliance assessments", capability: "Capability assessments" };

function GovAcross({ kind }) {
  const { data, error } = useApi(`/api/v1/repository/governance/${kind}`);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [appr, setAppr] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const rows = data.records.filter((r) => (!status || r.status === status) && (!appr || r.approval === appr)
    && (!q.trim() || `${r.ref} ${r.title} ${r.owner} ${r.project}`.toLowerCase().includes(q.trim().toLowerCase())));
  const statuses = [...new Set(data.records.map((r) => r.status))];
  return (
    <div>
      <p className="quiet">Every {data.kind.toLowerCase()} of the {data.projects} project{data.projects === 1 ? "" : "s"} {data.all ? "(every project: you are an admin)" : "you are on"},
        read only: open one to change it in its project's Governance log.</p>
      <div className="row-gap">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find" aria-label="Find" />
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">Any status</option>
          {statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select>
        <select value={appr} onChange={(e) => setAppr(e.target.value)} aria-label="Approval"><option value="">Any approval</option>
          {["Draft", "Waiting for approval", "Approved", "Rejected"].map((s) => <option key={s} value={s}>{s}</option>)}</select>
        <span className="small quiet">{rows.length} of {data.records.length}</span>
      </div>
      <table className="grid-table">
        <thead><tr><th>Ref</th><th>Title</th><th>Project</th><th>Status</th><th>Approval</th><th>Owner</th><th>Raised</th><th>Changed</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}><td>{r.ref}</td>
              <td><a href={`#/projects/${r.project_id}/governance?kind=${encodeURIComponent(data.kind)}`}>{r.title}</a></td>
              <td>{r.project}</td><td>{r.status}</td>
              <td><span className={`rag ${{ Approved: "green", Rejected: "red", "Waiting for approval": "amber" }[r.approval] || "off"} small`}
                title={r.approved_by ? `by ${r.approved_by}` : ""}>{r.approval}</span></td><td>{r.owner}</td><td className="small">{r.raised_on}</td>
              <td className="small">{r.modified_at ? fmtDateTime(r.modified_at) : ""}</td></tr>
          ))}
          {!rows.length && <tr><td colSpan={8} className="quiet">{data.records.length ? "Nothing matches." : "None yet."}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// admins (Super Admins, User Admins) see every user of EA Explorer: their global roles, projects and models (owner, 8 Nov 2026)
function AllUsers({ members }) {
  const { data, error } = useApi("/api/v1/people");
  const [q, setQ] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Reading the users...</p>;
  const ql = q.trim().toLowerCase();
  const on = (u) => (members || []).filter((m) => m.username === String(u).toLowerCase());
  const rows = data.filter((u) => !ql || `${u.username} ${u.name || ""} ${u.email || ""} ${u.roles.join(" ")} ${on(u.username).map((m) => m.project).join(" ")}`.toLowerCase().includes(ql));
  return (
    <div>
      <div className="row-gap">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a user, role or project" aria-label="Find" />
        <span className="small quiet">{rows.length} of {data.length}{data.length >= 100 ? " (the first 100: find to narrow)" : ""}</span>
        <a className="small" href="#/admin/users">Users (Administration) →</a>
      </div>
      <table className="grid-table">
        <thead><tr><th>User</th><th>Global roles</th><th>Projects (role)</th><th>Models (role)</th></tr></thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.id} className={u.enabled === false ? "retired" : ""}>
              <td><b>{u.username}</b>{u.name && <div className="small quiet">{u.name}</div>}{u.email && <div className="small quiet">{u.email}</div>}</td>
              <td className="small">{u.roles.length ? u.roles.join(", ") : <span className="quiet">none</span>}</td>
              <td className="small">{on(u.username).map((m, i) => <span key={m.project_id + m.role}>{i > 0 && ", "}<a href={`#/projects/${m.project_id}/organisation`}>{m.project}</a> <span className="quiet">({m.role})</span></span>)}
                {!on(u.username).length && <span className="quiet">none</span>}</td>
              <td className="small">{(u.models || []).map((m, i) => <span key={m.id}>{i > 0 && ", "}<a href={`#/metamodel/${m.id}`}>{m.name}</a> <span className="quiet">({(m.roles || [m.role]).join(", ")})</span></span>)}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={4} className="quiet">Nothing matches.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function PeopleAcross({ bySkill }) {
  const { data, error } = useApi("/api/v1/repository/people");
  const [q, setQ] = useState("");
  const [skill, setSkill] = useState("");
  const [view, setView] = useState("users");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  if (!bySkill && data.all_users) {
    return (
      <div>
        <div className="cf-views" role="tablist">
          <button role="tab" aria-selected={view === "users"} className={`cf-view${view === "users" ? " on" : ""}`} onClick={() => setView("users")}>Every user</button>
          <button role="tab" aria-selected={view === "org"} className={`cf-view${view === "org" ? " on" : ""}`} onClick={() => setView("org")}>On the projects' Organisation tabs</button>
        </div>
        {view === "users" ? <AllUsers members={data.members} /> : <PeopleList data={data} q={q} setQ={setQ} skill={skill} setSkill={setSkill} />}
      </div>
    );
  }
  return <PeopleList data={data} q={q} setQ={setQ} skill={skill} setSkill={setSkill} bySkill={bySkill} />;
}

function PeopleList({ data, q, setQ, skill, setSkill, bySkill }) {
  const ql = q.trim().toLowerCase();
  const rows = data.people.filter((r) => (!skill || r.skills.includes(skill))
    && (!ql || `${r.name} ${r.role} ${r.username} ${r.project} ${r.skills.join(" ")}`.toLowerCase().includes(ql)));
  return (
    <div>
      <p className="quiet">Everyone on the Organisation tab of the {data.projects} project{data.projects === 1 ? "" : "s"} {data.all_users ? "(every project: you are an admin)" : "you are on"},
        read only: change them in each project.</p>
      <div className="row-gap">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a person, role or skill" aria-label="Find" />
        <select value={skill} onChange={(e) => setSkill(e.target.value)} aria-label="Skill"><option value="">Any skill</option>
          {data.skills.map((s) => <option key={s} value={s}>{s}</option>)}</select>
        <span className="small quiet">{rows.length} of {data.people.length}</span>
      </div>
      {bySkill ? (
        <div className="level-cols">
          {(skill ? [skill] : data.skills).map((s) => {
            const ps = rows.filter((r) => r.skills.includes(s));
            return ps.length ? <div key={s} className="level-col"><h3>{s} <span className="small quiet">{ps.length}</span></h3>
              {ps.map((r) => <div key={r.id} className="level-item">{r.name} <span className="small quiet">{r.role} · <a href={`#/projects/${r.project_id}/organisation`}>{r.project}</a></span></div>)}
            </div> : null;
          })}
          {!data.skills.length && <p className="quiet">No skills recorded yet (skills are tags on each project's Organisation tab).</p>}
        </div>
      ) : (
        <table className="grid-table">
          <thead><tr><th>Person</th><th>Role</th><th>Project</th><th>Skills</th></tr></thead>
          <tbody>
            {rows.map((r) => <tr key={r.id}><td>{r.name}{r.username ? <span className="small quiet"> {r.username}</span> : null}</td><td>{r.role}</td>
              <td><a href={`#/projects/${r.project_id}/organisation`}>{r.project}</a></td><td className="small">{r.skills.join(", ")}</td></tr>)}
            {!rows.length && <tr><td colSpan={4} className="quiet">{data.people.length ? "Nothing matches." : "None yet."}</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}

const VIEWS = { ...GOV, people: "Organisation structure", skills: "Skills repository" };

// the top-level map is always the organisation's (owner, 8 Nov 2026): everything an admin may see, or what the person
// may see; inside a project (its Enterprise Repository tab) everything is the project's. A link takes you there.
const lastProject = () => { try { return localStorage.getItem("eax.lastProject"); } catch { return null; } };
function ScopedMap() {
  const pid = lastProject();
  const { data: p } = useApi(pid ? `/api/v1/projects/${pid}` : null);
  return (
    <div>
      {p && <p className="small">This is the organisation's view. For one project only, open it inside the project:{" "}
        <a href={`#/projects/${p.id}/archrepo`}>{p.name} › Enterprise Repository (Project Scope) →</a></p>}
      <RepositoryMap />
    </div>
  );
}

export default function ArchitectureRepositoryPage() {
  const [route, setRoute] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setRoute(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const sub = route.replace(/^#\/repository\/?/, "").split("?")[0];
  const title = VIEWS[sub];
  return (
    <section className="page">
      <h1>{title ? <><a href="#/repository">Architecture repository</a> › {title}</> : "Architecture repository"}</h1>
      {GOV[sub] ? <GovAcross kind={sub} /> : sub === "people" ? <PeopleAcross /> : sub === "skills" ? <PeopleAcross bySkill /> : <ScopedMap />}
    </section>
  );
}
