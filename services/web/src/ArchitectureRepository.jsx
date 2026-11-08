// The Architecture Repository (owner, 8 Nov 2026, D301): its parts as TOGAF gives them, drawn as a map, each part
// leading to what EA Explorer holds for it today. For the whole organisation (#/repository) and for one project (its
// Architecture repository tab). Its own design and build is phase 13.0.9: parts not built yet say so.
const SOON = "phase 13.0.9";

function parts(p) {
  const pj = p ? `#/projects/${p.id}` : null;
  const cf = (area) => (p ? `${pj}/content?area=${area}` : null);
  return {
    framework: { title: "Architecture framework", colour: "#1f7a3a", items: [
      { label: "Architecture method", href: p ? `${pj}/home` : "#/project-admin/library", note: p ? "the project's phases and steps" : "the project library: phases, steps, document types" },
      { label: "Content metamodel", href: p ? `${pj}/content` : "#/metamodel", note: p ? "the content framework of the project" : "the models' metamodels" },
    ] },
    landscape: { title: "Architecture landscape", colour: "#2d3f8f", items: [
      { label: "Strategic architectures", href: p ? `${pj}/models` : "#/work", note: p ? "the project's models" : "projects of kind strategy" },
      { label: "Segment architectures", href: p ? `${pj}/models` : "#/work", note: p ? "the project's models" : "projects and their models" },
      { label: "Transition architectures", href: p ? cf("real.capabilities") : "#/work", note: "transition models and plateaus" },
    ] },
    reference: { title: "Reference library", colour: "#2d3f8f", items: [
      { label: "Foundation architectures", href: "#/library", note: "root metamodels in the model library" },
      { label: "Common systems architectures", href: "#/library", note: "reference models" },
      { label: "Industry architectures", href: "#/library", note: "industry reference models" },
      { label: "Organisation's own architectures", href: p ? `${pj}/reference` : null, note: p ? "the project's Reference area" : "the organisation's reference library: phase 13.0.8" },
    ] },
    standards: { title: "Standards information base", colour: "#2d3f8f", items: [
      { label: "Business standards", href: cf("gov.standards"), note: p ? "standards in the content framework" : SOON },
      { label: "Data standards", href: cf("gov.standards"), note: p ? "standards in the content framework" : SOON },
      { label: "Application standards", href: cf("gov.standards"), note: p ? "standards in the content framework" : SOON },
      { label: "Technology standards", href: cf("gov.standards"), note: p ? "standards in the content framework" : SOON },
    ] },
    governance: { title: "Governance log", colour: "#8f1d1d", items: [
      { label: "Decision log", href: p ? `${pj}/signoff` : "#/change-log", note: p ? "sign-off decisions" : "the change log" },
      { label: "Compliance assessments", href: cf("gov.standards"), note: p ? "governance documents" : SOON },
      { label: "Capability assessments", href: cf("vision.business_strategy"), note: p ? "capability assessment documents" : SOON },
      { label: "Calendar", href: null, note: SOON },
      { label: "Project portfolio", href: "#/work", note: "Architecture work" },
      { label: "Performance measurement", href: p ? `${pj}/home` : "#/admin/quality", note: p ? "the project's completion" : "data quality" },
    ] },
    capability: { title: "Architecture capability", colour: "#1f7a3a", items: [
      { label: "Skills repository", href: null, note: SOON },
      { label: "Organisation structure", href: p ? `${pj}/organisation` : "#/admin/users", note: p ? "who works on the project, by role" : "users and roles" },
      { label: "Architecture charter", href: cf("prelim.principles"), note: p ? "Preliminary: principles, terms of reference" : SOON },
    ] },
  };
}

// at project level the structure is empty for now (owner, 8 Nov 2026): its content is designed in phase 13.0.9
function emptied(x) {
  return Object.fromEntries(Object.entries(x).map(([k, part]) => [k, { ...part, items: part.items.map((i) => ({ label: i.label, href: null, note: "empty: phase 13.0.9" })) }]));
}

function Part({ part, cols }) {
  return (
    <div className="ar-part" style={{ borderColor: part.colour }}>
      <div className="ar-title" style={{ background: part.colour }}>{part.title}</div>
      <div className="ar-items" style={{ gridTemplateColumns: `repeat(${cols || 1}, minmax(0, 1fr))` }}>
        {part.items.map((i) => (i.href
          ? <a key={i.label} className="ar-item" href={i.href} title={i.note}><b>{i.label}</b><span>{i.note}</span></a>
          : <div key={i.label} className="ar-item off" title={i.note}><b>{i.label}</b><span>{i.note}</span></div>))}
      </div>
    </div>
  );
}

export function RepositoryMap({ p }) {
  const x = p ? emptied(parts(p)) : parts();
  return (
    <div>
      {p ? <p className="quiet">This project's own enterprise repository, for this project only, in the shape TOGAF gives the Architecture Repository.
        Its parts are empty for now: what each holds for a project is designed and built in phase 13.0.9.</p>
        : <p className="quiet">The Architecture Repository in the shape TOGAF gives it. Each part leads to what EA Explorer holds for it today;
        a part shown grey is still to come (the repository's own design and build is phase 13.0.9).</p>}
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
          <div className="ar-ext"><b>External reference models</b><span>adopted by the enterprise into the reference library</span></div>
          <div className="ar-ext"><b>External standards</b><span>adopted by the enterprise into the standards information base</span></div>
          <div className="ar-ext tall"><b>Architecture board</b><span>steers the capability; visibility and escalation</span></div>
        </div>
      </div>
    </div>
  );
}

export default function ArchitectureRepositoryPage() {
  return (
    <section className="page">
      <h1>Architecture repository</h1>
      <RepositoryMap />
    </section>
  );
}
