// Architecture projects (phase 13, D258 to D264): #/projects (the list), #/projects/new (the wizard),
// #/projects/<id>/<tab> (a project: overview, repository, steps, principles).
// A project has a purpose, its models, viewpoints, principles, the ADM steps (accepted, or removed and shown crossed out
// with the reason), its deliverables and artifacts (chosen, or not_for_use in the same folders), its people and who signs
// off. Its repository is built in Documents (Mayan); documents are edited outside in Office: check out, download, edit,
// check in the new file. Templates come from template libraries (D264): EA Explorer's own, TOGAF 10 (loaded once by a
// Super Admin) and the organisation's own (a zip in the library layout); a Super Admin finishes the template library
// setup before the first project.
import { useEffect, useMemo, useState } from "react";
import { apiDownload, apiFetch, apiUpload } from "./auth";
import { fmtDateTime } from "./fmt";
import { refreshAll, useApi } from "./ModelViews";

const ROLE_NAMES = { "project-admin": "Project Admin", "lead-architect": "Lead Architect", architect: "Architect",
  "model-admin": "Model Admin", "model-sub-admin": "Model Sub Admin", stakeholder: "Stakeholder" };
const REPO = { pending: ["amber", "waiting for Documents"], building: ["amber", "being built"], ready: ["green", "ready"], failed: ["red", "not built yet"] };
const PURPOSE_HELP = {
  strategy: "Enterprise-wide direction over several years (TOGAF strategic architecture)",
  portfolio: "A set of initiatives or a segment of the enterprise (segment architecture)",
  project: "One change initiative (capability architecture)",
  solution: "One solution's architecture, within the enterprise architecture",
};

export default function Projects({ route }) {
  const parts = route.replace(/^#\/projects\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "new") return <Wizard parent={new URLSearchParams(route.split("?")[1] || "").get("parent")} />;
  if (parts[0]) return <ProjectPage id={parts[0].split("?")[0]} tab={parts[1] || "overview"} />;
  return <ProjectList />;
}

// ---------------------------------------------------------------- the list
function ProjectList() {
  const { data, error } = useApi("/api/v1/projects");
  return (
    <div className="page">
      <div className="row-gap">
        <h2 style={{ margin: 0 }}>Architecture projects</h2>
        {data?.may_create && data.setup?.done && <a className="button primary" href="#/projects/new">+ New project</a>}
      </div>
      {data && !data.setup?.done && <SetupNeeded manage={data.may_manage} />}
      <p className="quiet">Architecture work for a purpose (strategy, portfolio, project or solution): its models, the ADM steps it
        follows, the deliverables and artifacts it produces, its people and its repository in Documents.</p>
      {error && <p className="status bad">{error}</p>}
      {data && !data.projects.length && <p className="quiet">You are on no project yet{data.may_create ? ": start one with + New project." : "."}</p>}
      {data && data.projects.length > 0 && (
        <table className="grid-table">
          <thead><tr><th>Project</th><th>Purpose</th><th>Cycle</th><th>Your roles</th><th className="num">People</th>
            <th className="num">Models</th><th className="num">Items in use</th><th className="num">Documents</th><th>Repository</th><th>Created</th></tr></thead>
          <tbody>
            {data.projects.map((p) => (
              <tr key={p.id}>
                <td><a href={`#/projects/${p.id}`}><b>{p.name}</b></a>{p.parent_name && <div className="small quiet">rerun of {p.parent_name}</div>}</td>
                <td>{p.purpose}</td><td>{p.cycle}</td>
                <td className="small">{(p.my_roles || []).map((r) => ROLE_NAMES[r] || r).join(", ") || <span className="quiet">Super Admin</span>}</td>
                <td className="num">{p.people}</td><td className="num">{p.models}</td><td className="num">{p.items}</td><td className="num">{p.documents}</td>
                <td><RepoState state={p.repo_state} /></td>
                <td className="small">{fmtDateTime(p.created_at)} · {p.created_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SetupNeeded({ manage }) {
  return (
    <div className="notice-box">
      <b>Projects start after the template library setup</b>
      <p className="small">Before the first project a Super Admin chooses the template libraries projects take their starting documents from:
        EA Explorer's own (ready to use as it is), TOGAF 10 (The Open Group's, loaded once) and your organisation's own (download one, rebrand it,
        add documents and upload it back).</p>
      {manage ? <a className="button primary" href="#/admin/projects">Set up the template libraries →</a>
        : <p className="small quiet">Ask a Super Admin to finish it (Administration › Project library).</p>}
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

// ---------------------------------------------------------------- the wizard
const STEPS = ["Basics", "Template libraries", "Models", "Viewpoints and artifacts", "Principles", "Phase by phase", "People and sign-off", "Review"];

function Wizard({ parent }) {
  const { data: lib, error } = useApi("/api/v1/projects/library");
  const { data: me } = useApi("/api/v1/me");
  const { data: mlist } = useApi("/api/v1/models");
  const { data: plist } = useApi("/api/v1/projects");
  const [step, setStep] = useState(0);
  const [d, setD] = useState({ name: "", purpose: "", own_purpose: "", description: "", parent: parent || "", models: [], viewpoints: [],
    principles: [], own_principles: [], removed: {}, own_steps: [], picks: null, kinds: {}, own_items: [], members: [], signoff: { "": [] },
    libraries: null });
  const [phase, setPhase] = useState("P");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setD((x) => ({ ...x, [k]: v }));
  useEffect(() => {   // the library's defaults: every item offered ticked unless the library marks it not for use
    if (lib && d.picks === null) set("picks", Object.fromEntries(lib.items.map((i) => [i.id, i.default_pick])));
    if (lib && d.libraries === null) set("libraries", lib.libraries.filter((l) => l.shared && l.usable).map((l) => l.id));
  }, [lib]); // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <div className="page"><p className="status bad">{error}</p></div>;
  if (!lib || d.picks === null || d.libraries === null) return <div className="page"><p className="quiet">Loading the project library...</p></div>;
  if (!lib.setup.done) return <div className="page"><h2>New architecture project</h2><SetupNeeded manage={lib.may_manage} /></div>;
  const models = (mlist?.models || mlist || []).filter((m) => !m.is_deleted);
  const purpose = d.purpose === "own" ? d.own_purpose.trim() : d.purpose;
  const problems = [
    !d.name.trim() && "Give the project a name (Basics).",
    !purpose && "Choose its purpose (Basics).",
    !d.libraries.length && "Pick at least one template library (Template libraries).",
    d.models.some((m) => (m.how !== "added" && !m.name.trim()) || !(m.model || m.from)) && "Each model needs a model to start from and, when new, a name (Models).",
    Object.entries(d.removed).some(([, why]) => !why.trim()) && "Say why each removed step is removed (Phase by phase).",
  ].filter(Boolean);

  async function create() {
    setBusy(true); setMsg("");
    const body = {
      name: d.name.trim(), purpose, description: d.description, parent: d.parent || undefined, viewpoints: d.viewpoints,
      libraries: d.libraries,
      models: d.models.map((m) => (m.how === "added" ? { how: "added", model: m.model } : { how: m.how, from: m.from, name: m.name, copy: m.copy })),
      principles: [...d.principles.map((id) => ({ library_id: id })), ...d.own_principles.filter((p) => p.name.trim())],
      removed_steps: Object.entries(d.removed).map(([id, reason]) => ({ library_id: Number(id), reason })),
      own_steps: d.own_steps.filter((s) => s.name.trim()),
      items: Object.entries(d.picks).filter(([, on]) => on).map(([id]) => id), kinds: d.kinds,
      own_items: d.own_items.filter((i) => i.name.trim()),
      members: d.members.filter((m) => m.username.trim()), signoff: d.signoff,
    };
    try {
      const out = await apiFetch("/api/v1/projects", { method: "POST", body: JSON.stringify(body) });
      refreshAll();
      window.location.hash = `#/projects/${out.project.id}`;
    } catch (e) { setMsg(e.message); }
    setBusy(false);
  }

  return (
    <div className="page wizard">
      <h2>New architecture project</h2>
      <ol className="wizard-steps">
        {STEPS.map((s, i) => <li key={s} className={i === step ? "on" : i < step ? "done" : ""}><button className="linkish" onClick={() => setStep(i)}>{i + 1}. {s}</button></li>)}
      </ol>
      <div className="wizard-body">
        {step === 0 && <Basics d={d} set={set} lib={lib} projects={plist?.projects || []} />}
        {step === 1 && <Libraries d={d} set={set} lib={lib} />}
        {step === 2 && <Models d={d} set={set} models={models} />}
        {step === 3 && <ViewpointsAndItems d={d} set={set} lib={lib} />}
        {step === 4 && <Principles d={d} set={set} lib={lib} parentName={(plist?.projects || []).find((p) => p.id === d.parent)?.name} />}
        {step === 5 && <PhaseByPhase d={d} set={set} lib={lib} phase={phase} setPhase={setPhase} />}
        {step === 6 && <People d={d} set={set} lib={lib} me={me?.username || me?.preferred_username} />}
        {step === 7 && <Review d={d} lib={lib} purpose={purpose} problems={problems} />}
      </div>
      <div className="row-gap wizard-nav">
        <button disabled={step === 0} onClick={() => setStep(step - 1)}>← Back</button>
        {step < STEPS.length - 1 && <button className="primary" onClick={() => setStep(step + 1)}>Next: {STEPS[step + 1]} →</button>}
        {step === STEPS.length - 1 && <button className="primary" disabled={busy || problems.length > 0} onClick={create}>
          {busy ? "Creating..." : "Create the project"}</button>}
        <a href="#/projects">Cancel</a>
        {msg && <span className="status bad">{msg}</span>}
      </div>
    </div>
  );
}

function Basics({ d, set, lib, projects }) {
  return (
    <div className="basics">
      <label className="field">Name
        <input value={d.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Claims Transformation 2027" autoFocus />
      </label>
      <label className="field">Description
        <textarea rows={3} value={d.description} onChange={(e) => set("description", e.target.value)}
          placeholder="What the project is for, its scope and sponsor" />
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
      <label className="field">Start
        <select value={d.parent} onChange={(e) => set("parent", e.target.value)}>
          <option value="">From scratch</option>
          {projects.map((p) => <option key={p.id} value={p.id}>Rerun the ADM on {p.name} (a child project)</option>)}
        </select>
        <span className="small quiet">A child project inherits its parent's principles; the parent stays open (copying its artifacts and
          merging back come in phase 13.3).</span>
      </label>
    </div>
  );
}

function Libraries({ d, set, lib }) {
  const toggle = (id) => set("libraries", d.libraries.includes(id) ? d.libraries.filter((x) => x !== id) : [...d.libraries, id]);
  const offered = lib.libraries.filter((l) => l.state !== "failed");
  return (
    <div>
      <p className="quiet">Where the project's starting documents come from. Pick one or more: every template the picked libraries have for a
        deliverable or artifact is copied into its folder, named <code>library-document</code> (two libraries with a template for the
        Architecture Vision give two files).</p>
      <table className="grid-table">
        <thead><tr><th /><th>Template library</th><th>Kind</th><th>Files</th><th>Offered to</th></tr></thead>
        <tbody>
          {offered.map((l) => (
            <tr key={l.id} className={l.usable || l.state === "loading" ? "" : "quiet"}>
              <td><input type="checkbox" checked={d.libraries.includes(l.id)} disabled={!l.usable && l.state !== "loading"} onChange={() => toggle(l.id)} /></td>
              <td><b>{l.name}</b><div className="small quiet">{l.description}</div></td>
              <td className="small">{LIB_KIND[l.kind]}</td>
              <td><LibState l={l} />{l.may_download && <> <button className="linkish small" onClick={() => apiDownload(`/api/v1/projects/library/libraries/${l.id}/zip`)}>⬇ zip</button></>}</td>
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

function Models({ d, set, models }) {
  const projectModels = models.filter((m) => m.kind === "project");
  const starts = models.filter((m) => ["template", "reference", "project"].includes(m.kind));
  const upd = (i, k, v) => set("models", d.models.map((m, j) => (j === i ? { ...m, [k]: v } : m)));
  return (
    <div>
      <p className="quiet">The models this project works on: add existing ones (models are shared: any project can use a model its
        people may use), derive a child from a project model (it merges back into it), or create a new one from a root
        metamodel or a library model. The project's people get roles on the models it derives or creates; on added models
        they keep the roles they have.</p>
      <table className="grid-table">
        <thead><tr><th>How</th><th>Model</th><th>New model's name</th><th>Copy</th><th /></tr></thead>
        <tbody>
          {d.models.map((m, i) => (
            <tr key={i}>
              <td><select value={m.how} onChange={(e) => upd(i, "how", e.target.value)}>
                <option value="added">Add an existing model</option><option value="derived">Derive a child from</option><option value="created">Create a new model from</option>
              </select></td>
              <td><select value={m.how === "added" ? m.model : m.from} onChange={(e) => upd(i, m.how === "added" ? "model" : "from", e.target.value)}>
                <option value="">Choose...</option>
                {(m.how === "derived" ? projectModels : m.how === "created" ? starts : models).map((x) => <option key={x.id} value={x.id}>{x.name} ({x.kind})</option>)}
              </select></td>
              <td>{m.how !== "added" ? <input value={m.name} onChange={(e) => upd(i, "name", e.target.value)} placeholder="Name of the new model" /> : <span className="quiet">-</span>}</td>
              <td>{m.how !== "added" ? <select value={m.copy} onChange={(e) => upd(i, "copy", e.target.value)}>
                <option value="metamodel">Metamodel only</option><option value="content">Metamodel and content</option>
              </select> : <span className="quiet">-</span>}</td>
              <td><button className="linkish" onClick={() => set("models", d.models.filter((_x, j) => j !== i))}>Remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row-gap">
        <button onClick={() => set("models", [...d.models, { how: "added", model: "", from: "", name: "", copy: "metamodel" }])}>+ Add an existing model</button>
        <button onClick={() => set("models", [...d.models, { how: "derived", model: "", from: "", name: `${d.name || "Project"} model`, copy: "content" }])}>+ Derive a child</button>
        <button onClick={() => set("models", [...d.models, { how: "created", model: "", from: "", name: `${d.name || "Project"} model`, copy: "metamodel" }])}>+ Create a new model</button>
      </div>
    </div>
  );
}

function ViewpointsAndItems({ d, set, lib }) {
  const [filter, setFilter] = useState("");
  const toggleVp = (c) => set("viewpoints", d.viewpoints.includes(c) ? d.viewpoints.filter((x) => x !== c) : [...d.viewpoints, c]);
  const items = lib.items.filter((i) => !filter || `${i.name} ${i.type} ${i.kind}`.toLowerCase().includes(filter.toLowerCase()));
  const on = Object.values(d.picks).filter(Boolean).length;
  const setAll = (val, kind) => set("picks", { ...d.picks, ...Object.fromEntries(items.filter((i) => !kind || kindOf(d, i) === kind).map((i) => [i.id, val])) });
  return (
    <div>
      <h3>Viewpoints</h3>
      <p className="quiet small">The views this project's stakeholders need; chosen here for the whole project.
        Chosen: <b>{d.viewpoints.length}</b> of {lib.viewpoints.length}.</p>
      <div className="row-gap">
        <button onClick={() => set("viewpoints", lib.viewpoints.map((v) => v.code))}>Select all</button>
        <button onClick={() => set("viewpoints", [])}>Clear all</button>
      </div>
      <div className="vp-choices">
        {lib.viewpoints.map((v) => (
          <label key={v.code} className={`choice small${d.viewpoints.includes(v.code) ? " on" : ""}`} title={v.purpose}>
            <input type="checkbox" checked={d.viewpoints.includes(v.code)} onChange={() => toggleVp(v.code)} /> {v.code} {v.name}
          </label>
        ))}
      </div>
      <h3>Deliverables and artifacts for the whole project</h3>
      <p className="quiet small">Everything the library offers ({lib.items.length}), from TOGAF, the Meridian framework and repository and the
        phase-wise list. Chosen: <b>{on}</b>. What is not chosen still goes into the repository, in the same folder, as not_for_use, and
        can be brought in later. The next step shows them phase by phase.</p>
      <div className="row-gap filters">
        <input placeholder="Filter" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button onClick={() => setAll(true)}>Choose all shown</button><button onClick={() => setAll(false)}>Clear all shown</button>
        <button onClick={() => setAll(true, "Deliverable")}>All deliverables</button><button onClick={() => setAll(true, "Artifact")}>All artifacts</button>
        <button onClick={() => set("picks", Object.fromEntries(lib.items.map((i) => [i.id, i.default_pick])))}>Library defaults</button>
      </div>
      <div className="item-columns">
        {lib.phases.map((ph) => {
          const list = items.filter((i) => i.phase === ph.code);
          if (!list.length) return null;
          return (
            <div key={ph.code} className="item-col">
              <h4>{ph.code} · {ph.name.replace(/^Phase [A-H]: /, "")} <span className="quiet small">{list.filter((i) => d.picks[i.id]).length}/{list.length}</span></h4>
              {list.map((i) => <ItemPick key={i.id} d={d} set={set} i={i} />)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const kindOf = (d, i) => d.kinds[i.id] || i.kind;

function ItemPick({ d, set, i }) {
  const k = kindOf(d, i);
  return (
    <div className={`item-pick${d.picks[i.id] ? "" : " off"}`} title={(i.sources || []).map((s) => `${s.source}: ${s.name}${s.files ? ` (${s.files})` : ""}`).join("\n")}>
      <label><input type="checkbox" checked={!!d.picks[i.id]} onChange={(e) => set("picks", { ...d.picks, [i.id]: e.target.checked })} /> {i.name}</label>
      <button className={`kind-toggle ${k === "Deliverable" ? "del" : "art"}`} title="Deliverable or artifact: click to change"
        onClick={() => set("kinds", { ...d.kinds, [i.id]: k === "Deliverable" ? "Artifact" : "Deliverable" })}>{k === "Deliverable" ? "D" : "A"}</button>
      {i.type && <span className="small quiet"> {i.type}</span>}
      {!d.picks[i.id] && <span className="small quiet"> · not_for_use</span>}
    </div>
  );
}

function Principles({ d, set, lib, parentName }) {
  const sets = [...new Set(lib.principles.map((p) => p.set_name || "Principles"))];
  const toggle = (id) => set("principles", d.principles.includes(id) ? d.principles.filter((x) => x !== id) : [...d.principles, id]);
  const upd = (i, k, v) => set("own_principles", d.own_principles.map((p, j) => (j === i ? { ...p, [k]: v } : p)));
  return (
    <div>
      {parentName && <p className="status ok small">As a child of {parentName}, the project inherits its principles; add more here.</p>}
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
  const steps = lib.steps.filter((s) => s.phase === phase);
  const items = lib.items.filter((i) => i.phase === phase);
  const own = d.own_steps.filter((s) => s.phase === phase);
  const ownItems = d.own_items.filter((i) => i.phase === phase);
  const ph = lib.phases.find((p) => p.code === phase);
  const removeStep = (s, on) => { const r = { ...d.removed }; if (on) r[s.id] = r[s.id] || ""; else delete r[s.id]; set("removed", r); };
  return (
    <div>
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
        <div className="phase-cols">
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
                  {off && <input className="why" placeholder="Why it is removed (required)" value={d.removed[s.id]}
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
          <div>
            <h4>Deliverables and artifacts <span className="quiet small">D deliverable, A artifact: click to change</span></h4>
            {items.map((i) => <ItemPick key={i.id} d={d} set={set} i={i} />)}
            {ownItems.map((it) => {
              const i = d.own_items.indexOf(it);
              const upd = (k, v) => set("own_items", d.own_items.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
              return (
                <div key={`own${i}`} className="item-pick own">
                  <input value={it.name} placeholder="Your own deliverable or artifact" onChange={(e) => upd("name", e.target.value)} />
                  <select value={it.kind} onChange={(e) => upd("kind", e.target.value)}><option>Deliverable</option><option>Artifact</option></select>
                  <button className="linkish" onClick={() => set("own_items", d.own_items.filter((_x, j) => j !== i))}>Remove</button>
                </div>
              );
            })}
            <button onClick={() => set("own_items", [...d.own_items, { phase, name: "", kind: "Deliverable" }])}>+ Add your own</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function People({ d, set, lib, me }) {
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
      <p className="quiet">You become the project's Project Admin. Project Admin and Lead Architect run the setup and the people;
        Architects, Model Admins and Model Sub Admins contribute too; Stakeholders read, and comment on, approve or reject documents.</p>
      <datalist id="people-list">{(people || []).map((p) => <option key={p.username} value={p.username}>{p.name || p.username}</option>)}</datalist>
      <table className="grid-table">
        <thead><tr><th>Person</th><th>Project role</th><th /></tr></thead>
        <tbody>
          <tr><td><b>{me}</b> (you)</td><td>Project Admin</td><td /></tr>
          {d.members.map((m, i) => (
            <tr key={i}>
              <td><input list="people-list" value={m.username} onChange={(e) => { upd(i, "username", e.target.value); setSearch(e.target.value); }} placeholder="user name" /></td>
              <td><select value={m.role} onChange={(e) => upd(i, "role", e.target.value)}>{lib.roles.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}</select></td>
              <td><button className="linkish" onClick={() => set("members", d.members.filter((_x, j) => j !== i))}>Remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={() => set("members", [...d.members, { username: "", role: "architect" }])}>+ Add a person</button>
      <h3>Who signs off documents</h3>
      <p className="quiet small">One set for the whole project; add a set for a phase where it differs. The workflow that asks them comes in 13.1.</p>
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
    </div>
  );
}

function Review({ d, lib, purpose, problems }) {
  const chosen = lib.items.filter((i) => d.picks[i.id]);
  const removed = lib.steps.filter((s) => s.id in d.removed);
  return (
    <div>
      {problems.length > 0 && <ul className="status bad">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
      <table className="grid-table review">
        <tbody>
          <tr><th>Name</th><td>{d.name}</td></tr>
          <tr><th>Purpose</th><td>{purpose}</td></tr>
          <tr><th>Template libraries</th><td>{d.libraries.map((id) => lib.libraries.find((l) => l.id === id)?.name).filter(Boolean).join(", ") || <span className="quiet">none</span>}</td></tr>
          <tr><th>Models</th><td>{d.models.map((m, i) => <div key={i}>{m.how === "added" ? "Add" : m.how === "derived" ? `Derive "${m.name}" from` : `Create "${m.name}" from`} a model</div>)}{!d.models.length && <span className="quiet">none yet</span>}</td></tr>
          <tr><th>Viewpoints</th><td>{d.viewpoints.join(", ") || <span className="quiet">none</span>}</td></tr>
          <tr><th>Principles</th><td>{d.principles.length} from the library, {d.own_principles.filter((p) => p.name.trim()).length} of its own</td></tr>
          <tr><th>Steps</th><td>{lib.steps.length - removed.length} kept, {removed.length} removed (crossed out), {d.own_steps.filter((s) => s.name.trim()).length} of its own</td></tr>
          <tr><th>Deliverables and artifacts</th><td>{chosen.length} chosen ({chosen.filter((i) => kindOf(d, i) === "Deliverable").length} deliverables,{" "}
            {chosen.filter((i) => kindOf(d, i) === "Artifact").length} artifacts), {lib.items.length - chosen.length} as not_for_use, {d.own_items.filter((i) => i.name.trim()).length} of its own</td></tr>
          <tr><th>People</th><td>you (Project Admin){d.members.filter((m) => m.username.trim()).map((m) => `, ${m.username} (${ROLE_NAMES[m.role]})`).join("")}</td></tr>
          <tr><th>Sign-off</th><td>{Object.entries(d.signoff).map(([ph, us]) => <div key={ph}>{ph || "Whole project"}: {us.join(", ") || <span className="quiet">nobody yet</span>}</div>)}</td></tr>
        </tbody>
      </table>
      <p className="quiet small">Creating the project builds its repository in Documents in the background: the master folders, a folder for every
        deliverable and artifact (not_for_use ones marked so), and a copy of every template the picked libraries have for each chosen item.</p>
    </div>
  );
}

// ---------------------------------------------------------------- one project
const TABS = [["overview", "Overview"], ["repository", "Repository"], ["steps", "Steps"], ["principles", "Principles"]];

function ProjectPage({ id, tab }) {
  const { data: p, error } = useApi(`/api/v1/projects/${id}`);
  const [msg, setMsg] = useState("");
  if (error) return <div className="page"><p className="status bad">{error}</p><a href="#/projects">All projects</a></div>;
  if (!p) return <div className="page"><p className="quiet">Loading...</p></div>;
  async function rebuild() {
    try { const r = await apiFetch(`/api/v1/projects/${id}/repository`, { method: "POST" }); setMsg(r.message); setTimeout(refreshAll, 4000); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <div className="page">
      <div className="small"><a href="#/projects">Architecture projects</a> ›</div>
      <div className="row-gap">
        <h2 style={{ margin: 0 }}>{p.name}</h2>
        <span className="chip on">{p.purpose}</span><span className="chip">ADM cycle {p.cycle}</span>
        {p.parent_name && <span className="small quiet">rerun of <a href={`#/projects/${p.parent_id}`}>{p.parent_name}</a></span>}
        <span className="small">Repository: <RepoState state={p.repo_state} note={p.repo_note} /></span>
        {p.may_admin && p.repo_state !== "ready" && <button onClick={rebuild}>Build it now</button>}
        {msg && <span className="small quiet">{msg}</span>}
      </div>
      {p.repo_state !== "ready" && p.repo_note && <p className="small quiet">{p.repo_note}</p>}
      <div className="tabs" role="tablist">
        {TABS.map(([k, l]) => <a key={k} href={`#/projects/${id}/${k}`} className={`tab${tab === k ? " on" : ""}`}>{l}</a>)}
      </div>
      <div className="tab-panel">
        {tab === "overview" && <Overview p={p} />}
        {tab === "repository" && <RepositoryTab p={p} />}
        {tab === "steps" && <StepsTab p={p} />}
        {tab === "principles" && <PrinciplesTab p={p} />}
      </div>
    </div>
  );
}

function Overview({ p }) {
  const [edit, setEdit] = useState(false);
  const chosen = p.items.filter((i) => i.chosen);
  return (
    <div className="overview-grid">
      <section>
        <h3>About</h3>
        <p>{p.description || <span className="quiet">No description.</span>}</p>
        <p className="small quiet">Created {fmtDateTime(p.created_at)} by {p.created_by}. Your roles: {p.my_roles.map((r) => ROLE_NAMES[r] || r).join(", ")}.</p>
        <h3>Models</h3>
        {p.models.map((m) => <div key={m.id}><a href={`#/metamodel/${m.id}`}>{m.name}</a> <span className="small quiet">{m.how}{m.copy_state ? ` · ${m.copy_state}` : ""}</span></div>)}
        {!p.models.length && <p className="quiet small">No models yet.</p>}
        <h3>Template libraries</h3>
        <p>{p.libraries.map((l) => <span key={l.id} className="chip">{l.name}</span>)}{!p.libraries.length && <span className="quiet small">None.</span>}</p>
        <h3>Viewpoints</h3>
        <p>{p.viewpoints.map((v) => <span key={v.code} className="chip" title={v.name}>{v.code} {v.name}</span>)}{!p.viewpoints.length && <span className="quiet small">None chosen.</span>}</p>
        <h3>In the repository</h3>
        <p className="small">{chosen.length} deliverables and artifacts in use ({chosen.filter((i) => i.kind === "Deliverable").length} deliverables), {p.items.length - chosen.length} not_for_use,
          {" "}{p.documents.length} documents. Steps: {p.steps.filter((s) => !s.removed).length}, {p.steps.filter((s) => s.removed).length} removed.</p>
      </section>
      <section>
        <div className="row-gap"><h3 style={{ margin: 0 }}>People</h3>{p.may_admin && <button className="linkish" onClick={() => setEdit(!edit)}>{edit ? "Close" : "Change"}</button>}</div>
        {edit ? <PeopleEdit p={p} onDone={() => setEdit(false)} /> : (
          <>
            <table className="grid-table small"><tbody>
              {p.members.map((m) => <tr key={`${m.username}${m.role}`}><td>{m.username}</td><td>{ROLE_NAMES[m.role] || m.role}</td></tr>)}
            </tbody></table>
            <h3>Who signs off</h3>
            {[...new Set(p.signoff.map((s) => s.phase))].map((ph) => (
              <div key={ph} className="small"><b>{ph || "Whole project"}:</b> {p.signoff.filter((s) => s.phase === ph).map((s) => s.username).join(", ")}</div>
            ))}
            {!p.signoff.length && <p className="quiet small">Nobody yet.</p>}
          </>
        )}
      </section>
    </div>
  );
}

function PeopleEdit({ p, onDone }) {
  const [members, setMembers] = useState(p.members.map((m) => ({ username: m.username, role: m.role })));
  const [sign, setSign] = useState(() => { const s = {}; p.signoff.forEach((x) => { (s[x.phase] = s[x.phase] || []).push(x.username); }); if (!s[""]) s[""] = []; return s; });
  const [msg, setMsg] = useState("");
  const users = [...new Set(members.map((m) => m.username.trim().toLowerCase()).filter(Boolean))];
  async function save() {
    try { await apiFetch(`/api/v1/projects/${p.id}/people`, { method: "PUT", body: JSON.stringify({ members, signoff: sign }) }); refreshAll(); onDone(); }
    catch (e) { setMsg(e.message); }
  }
  return (
    <div>
      {members.map((m, i) => (
        <div key={i} className="own-row">
          <input value={m.username} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, username: e.target.value } : x)))} />
          <select value={m.role} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, role: e.target.value } : x)))}>
            {Object.entries(ROLE_NAMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button className="linkish" onClick={() => setMembers(members.filter((_x, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button onClick={() => setMembers([...members, { username: "", role: "architect" }])}>+ Add a person</button>
      <h4>Signs off (whole project)</h4>
      {users.map((u) => <label key={u} className="choice small"><input type="checkbox" checked={(sign[""] || []).includes(u)}
        onChange={() => setSign({ ...sign, "": (sign[""] || []).includes(u) ? sign[""].filter((x) => x !== u) : [...(sign[""] || []), u] })} /> {u}</label>)}
      <div className="row-gap"><button className="primary" onClick={save}>Save</button><button onClick={onDone}>Cancel</button>{msg && <span className="status bad">{msg}</span>}</div>
    </div>
  );
}

function RepositoryTab({ p }) {
  const [phase, setPhase] = useState(() => p.phases.find((ph) => p.items.some((i) => i.phase === ph.code && i.chosen))?.code || p.phases[0]?.code);
  const [showOff, setShowOff] = useState(false);
  const docsBy = useMemo(() => {
    const o = {};
    p.documents.forEach((d) => { (o[d.item_id] = o[d.item_id] || []).push(d); });
    return o;
  }, [p.documents]);
  const items = p.items.filter((i) => i.phase === phase && (showOff || i.chosen));
  const current = p.phases.find((ph) => ph.code === phase);
  const loose = p.documents.filter((d) => !d.item_id && current && d.folder.startsWith(current.workspace));
  return (
    <div>
      <div className="tabs phase-tabs" role="tablist">
        {p.phases.map((ph) => {
          const n = p.items.filter((i) => i.phase === ph.code && i.chosen).length;
          return (
            <button key={ph.code} role="tab" className={`tab${phase === ph.code ? " on" : ""}${n ? "" : " empty"}`} onClick={() => setPhase(ph.code)}
              title={`${ph.name} · ${ph.workspace}`}>{ph.name.replace(/^Phase /, "").replace(" Architecture", "").replace(" (repository-wide)", "")} <span className="count">{n}</span></button>
          );
        })}
      </div>
      <div className="row-gap filters">
        <label className="small"><input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} /> Show not_for_use items</label>
        <span className="small quiet">⬇ a template to start from it. Edit in Office: upload, <b>Check out</b>, download, edit, then <b>Check in</b> the
          new file. Stored in Documents with every version.</span>
      </div>
      {current && <p className="small quiet">📁 {current.workspace}</p>}
      {!items.length && <p className="quiet">Nothing {showOff ? "" : "in use "}in this phase.</p>}
      {items.map((i) => <RepoItem key={i.id} p={p} i={i} docs={docsBy[i.id] || []} />)}
      {loose.map((d) => <div key={d.id} className="repo-doc small"><button className="linkish" onClick={() => apiDownload(`/api/v1/projects/${p.id}/documents/${d.id}`, d.file_name)}>📄 {d.file_name}</button> <span className="quiet">{d.folder}</span></div>)}
    </div>
  );
}

function RepoItem({ p, i, docs }) {
  const [msg, setMsg] = useState("");
  async function act(fn) { setMsg(""); try { const r = await fn(); if (r?.message) setMsg(r.message); refreshAll(); } catch (e) { setMsg(e.message); } }
  function pick(onFile) {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.onchange = () => inp.files[0] && onFile(inp.files[0]);
    inp.click();
  }
  const upload = () => pick((f) => act(() => { const fd = new FormData(); fd.append("file", f); return apiUpload(`/api/v1/projects/${p.id}/items/${i.id}/documents`, fd); }));
  const checkIn = (d) => pick((f) => act(() => {
    const fd = new FormData(); fd.append("file", f);
    // eslint-disable-next-line no-alert
    fd.append("comment", window.prompt("What changed in this version? (optional)", "") || "");
    return apiUpload(`/api/v1/projects/${p.id}/documents/${d.id}/checkin`, fd);
  }));
  const post = (path, body) => apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });
  return (
    <div className={`repo-item${i.chosen ? "" : " off"}`}>
      <div className="row-gap">
        <span className={`kind-toggle ${i.kind === "Deliverable" ? "del" : "art"}`} title={i.kind}>{i.kind === "Deliverable" ? "D" : "A"}</span>
        <b>{i.name}</b>{i.type && <span className="small quiet">{i.type}</span>}
        {i.chosen && p.may_contribute && <button className="linkish" onClick={upload}>⬆ Upload</button>}
        {p.may_admin && <button className="linkish small" onClick={() => act(() => post(`/api/v1/projects/${p.id}/items/${i.id}/choose`, { chosen: !i.chosen }))}>
          {i.chosen ? "Mark not_for_use" : "Bring into use"}</button>}
        {msg && <span className="small status warn">{msg}</span>}
        <span className="small quiet folder" title={`Approved ones move to ${i.approved_folder || "-"}`}>📁 {i.folder}{i.chosen ? "" : " (not_for_use)"}</span>
      </div>
      {(p.templates?.[i.library_id] || []).length > 0 && (
        <div className="repo-templates small">
          <span className="quiet">Templates:</span>
          {p.templates[i.library_id].map((t) => (
            <button key={t.id} className="linkish" title={`From the ${t.library} library`}
              onClick={() => act(() => apiDownload(`/api/v1/projects/${p.id}/templates/${t.id}`, `${t.library}-${t.name}`))}>⬇ {t.library}-{t.name}</button>
          ))}
        </div>
      )}
      {docs.map((d) => {
        const mine = d.checked_out_by && d.checked_out_by.toLowerCase() === (p.me || "").toLowerCase();
        return (
          <div key={d.id} className="repo-doc">
            <button className="linkish" onClick={() => act(() => apiDownload(`/api/v1/projects/${p.id}/documents/${d.id}`, d.file_name))}>📄 {d.file_name}</button>
            <span className="small quiet"> v{d.versions} · {d.state} · {d.origin === "template" ? "from the template" : d.modified_by} · {fmtDateTime(d.modified_at)}</span>
            {d.checked_out_by ? <span className="rag amber" title={`since ${fmtDateTime(d.checked_out_at)}`}>checked out: {d.checked_out_by}</span> : null}
            {p.may_contribute && !d.checked_out_by && <button className="linkish" onClick={() => act(() => post(`/api/v1/projects/${p.id}/documents/${d.id}/checkout`))}>Check out</button>}
            {d.checked_out_by && <button className="linkish" onClick={() => checkIn(d)} title="Only the person who checked it out">Check in…</button>}
            {d.checked_out_by && (mine || p.may_undo) && <button className="linkish" onClick={() => act(() => post(`/api/v1/projects/${p.id}/documents/${d.id}/undo-checkout`))}>Undo check-out</button>}
          </div>
        );
      })}
    </div>
  );
}

function StepsTab({ p }) {
  const [msg, setMsg] = useState("");
  async function mark(st, done) {
    setMsg("");
    try { const r = await apiFetch(`/api/v1/projects/${p.id}/steps/${st.id}/done`, { method: "POST", body: JSON.stringify({ done }) }); setMsg(r.message); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  const live = p.steps.filter((x) => !x.removed);
  return (
    <div>
      <p className="quiet small">The ADM steps this project follows: tick a step when it is done (anyone who contributes); the Lead Architect or the
        Project Admin can reopen it. Removed standard steps stay, crossed out, with the reason. Done: <b>{live.filter((x) => x.done_at).length}</b> of {live.length}.</p>
      {msg && <p className="small status">{msg}</p>}
      {p.phases.map((ph) => {
        const list = p.steps.filter((x) => x.phase === ph.code);
        if (!list.length) return null;
        const open = list.filter((x) => !x.removed);
        return (
          <details key={ph.code} open>
            <summary><b>{ph.name}</b> <span className="small quiet">{open.filter((x) => x.done_at).length} of {open.length} done
              {list.some((x) => x.removed) ? `, ${list.filter((x) => x.removed).length} removed` : ""}</span></summary>
            <ol className="steps-list">
              {list.map((x) => (
                <li key={x.id} className={`${x.removed ? "removed" : ""}${x.done_at ? " done" : ""}`} value={x.seq}>
                  {!x.removed && (
                    <input type="checkbox" checked={!!x.done_at} disabled={!p.may_contribute || (x.done_at && !p.may_admin)}
                      title={x.done_at ? (p.may_admin ? "Reopen" : "Only the Lead Architect or the Project Admin reopens a step") : "Mark done"}
                      onChange={(e) => mark(x, e.target.checked)} />
                  )}
                  <span className="step-name">{x.name}</span>{x.own && <span className="chip">own</span>}
                  {x.done_at && <span className="small quiet"> done by {x.done_by}, {fmtDateTime(x.done_at)}</span>}
                  {x.removed && <span className="small quiet"> removed: {x.removed_reason}</span>}
                </li>
              ))}
            </ol>
          </details>
        );
      })}
    </div>
  );
}

function PrinciplesTab({ p }) {
  if (!p.principles.length) return <p className="quiet">No principles on this project yet.</p>;
  return (
    <table className="grid-table">
      <thead><tr><th>Code</th><th>Principle</th><th>Statement</th><th>Rationale</th><th>Implications</th><th>From</th></tr></thead>
      <tbody>
        {p.principles.map((r) => (
          <tr key={r.id}><td>{r.code}</td><td><b>{r.name}</b></td><td className="small">{r.statement}</td><td className="small">{r.rationale}</td>
            <td className="small" style={{ whiteSpace: "pre-line" }}>{r.implications}</td><td className="small">{r.inherited_from ? `inherited from ${r.inherited_from}` : ""}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------- Administration > Project library (Super Admins)
export function ProjectLibraryAdmin() {
  const { data: lib, error } = useApi("/api/v1/projects/library");
  const [msg, setMsg] = useState("");
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
      {!lib.setup.done && (
        <div className="notice-box">
          <b>Template library setup: needed before the first project</b>
          <p className="small">Choose where projects take their starting documents from. Any mix of:</p>
          <ol className="small">
            <li><b>Load TOGAF 10</b>: The Open Group's template deliverables, your licensed copy: <b>⬆ zip</b> on its row, the zip as you downloaded it.</li>
            <li><b>Download ours and upload it back as your own</b>: <i>⬇ zip</i> on EA Explorer's library, rebrand the files, keep them in
              their folders, and upload the zip as a new library.</li>
            <li><b>Add more documents</b> to any folder of that zip before you upload it: each becomes a template of that deliverable, artifact or folder.</li>
            <li><b>Use ours as it is</b>: EA Explorer's own library is ready (the worked samples rebranded to [Organisation], and a starter file for the rest).</li>
          </ol>
          <p className="small">Tick the libraries to offer to projects and press <b>Finish the setup</b>. You can add, offer or withdraw libraries later.</p>
        </div>
      )}
      {lib.setup.done && <p className="small quiet">Template library setup finished by {lib.setup.done_by} on {fmtDateTime(lib.setup.done_at)}.</p>}
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
              <td>{l.may_download && <button className="linkish" onClick={() => apiDownload(`/api/v1/projects/library/libraries/${l.id}/zip`)}>⬇ zip</button>}
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
