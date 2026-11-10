// Key questions (owner, 9 Nov 2026): every piece of a project's work answers a stakeholder's question. Each question
// says who asks it and the answer we expect (or how we will answer it); the views that answer it are mapped to it,
// many to many (a question may need several views, a view may answer several questions). Where no view
// fits, a placeholder view stands in: a text, or an empty file (docx, pptx, xlsx...) made in the project's files.
// Placeholders stay in the project (PH-01 ...).
//   KeyQuestionsStep   the wizard's Key questions step
//   QuestionMapping    the top of the wizard's Views step: the views (or placeholders) answering each question
//   KeyQuestionsPanel  the project's Key questions tab: status (open, answered, accepted by the stakeholder), the answer as a
//                      summary linking to the artifacts that hold it, history; kept up by anyone who contributes
import { useState } from "react";
import { apiDownload, apiFetch, apiUpload } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import RichText from "./RichText";

export const FILE_TYPES = { docx: "Word document", pptx: "PowerPoint presentation", xlsx: "Excel workbook", pdf: "PDF",
  drawio: "draw.io diagram", md: "Markdown", txt: "Text" };
export const newKey = () => `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
const EXAMPLES = ["What is the impact of removing an application?", "Which processes depend on the claims system?",
  "Where is customer data held, and who may change it?"];

const phLabel = (ph) => `${ph.code || "new placeholder"} ${ph.name}${ph.kind === "file" ? ` (.${ph.file_type})` : " (text)"}`;

// ---------------------------------------------------------------- the wizard: Key questions
export function KeyQuestionsStep({ d, set, names }) {
  const qs = d.key_questions;
  const upd = (i, k, v) => set("key_questions", qs.map((q, j) => (j === i ? { ...q, [k]: v } : q)));
  const move = (i, by) => {
    const j = i + by;
    if (j < 0 || j >= qs.length) return;
    const next = [...qs];
    [next[i], next[j]] = [next[j], next[i]];
    set("key_questions", next);
  };
  return (
    <div>
      <p className="quiet small">The questions the project's stakeholders need answered: every piece of the project's work answers one of them.
        For each, who asks it and the answer we expect, or how we will answer it. The next step (Views) maps the views that answer
        each question: a question may need more than one view, and a view may answer more than one question. Where no view fits,
        a placeholder (a text, or an empty Word, PowerPoint or other file) stands in.</p>
      {!qs.length && <p className="quiet small">No key questions yet. For example: {EXAMPLES.map((x) => <i key={x}>“{x}” </i>)}</p>}
      <datalist id="kq-askers">{(names || []).map((n) => <option key={n} value={n} />)}</datalist>
      {qs.map((q, i) => (
        <div key={q.id || q.key} className="goal-box kq-box">
          <div className="own-row">
            <b>Q{i + 1}</b>{q.status && q.status !== "open" && <span className="small quiet" title="Answered and accepted on the Key questions tab">{q.status}</span>}
            <input className="wide" placeholder={`The question, e.g. ${EXAMPLES[i % EXAMPLES.length]}`} value={q.question}
              onChange={(e) => upd(i, "question", e.target.value)} aria-label={`Question ${i + 1}`} />
            <button className="linkish" disabled={i === 0} onClick={() => move(i, -1)} title="Up">↑</button>
            <button className="linkish" disabled={i === qs.length - 1} onClick={() => move(i, 1)} title="Down">↓</button>
            <button className="linkish" onClick={() => set("key_questions", qs.filter((_x, j) => j !== i))}>Remove</button>
          </div>
          <div className="own-row">
            <input list="kq-askers" placeholder="Who asks it (stakeholders)" value={q.asked_by} onChange={(e) => upd(i, "asked_by", e.target.value)}
              aria-label={`Question ${i + 1}: who asks it`} />
          </div>
          <textarea className="wide" rows={2} placeholder="The answer we expect, or how we will answer it (the approach)"
            value={q.approach} onChange={(e) => upd(i, "approach", e.target.value)} aria-label={`Question ${i + 1}: expected answer or approach`} />
          {(q.views || []).length > 0 && <p className="small quiet">Answered by {q.views.length} view{q.views.length > 1 ? "s" : ""} (Views step).</p>}
        </div>
      ))}
      <button onClick={() => set("key_questions", [...qs, { key: newKey(), question: "", asked_by: "", approach: "", views: [] }])}>+ Add a key question</button>
    </div>
  );
}

// the views a question can be mapped to in the wizard: refs are a code, "own:<key>" (made in this wizard) or
// "ph:<key>" (a placeholder made in this wizard)
function wizardOptions(d, lib) {
  const name = Object.fromEntries(lib.views.map((v) => [v.code, v.name]));
  const gone = new Set(d.removed_views || []);
  const gonePh = new Set(d.removed_placeholders || []);
  const project = [
    ...d.views.map((c) => ({ ref: c, label: `${c} ${name[c] || ""}` })),
    ...(d.existing_vps || []).filter((v) => !gone.has(v.code)).map((v) => ({ ref: v.code, label: `${v.code} ${v.name}` })),
    ...d.own_views.filter((v) => v.name.trim()).map((v) => ({ ref: `own:${v.key}`, label: `new: ${v.name}` })),
  ];
  const placeholders = d.placeholder_views.filter((p) => p.name.trim() && !gonePh.has(p.code))
    .map((p) => ({ ref: p.code || `ph:${p.key}`, label: phLabel(p) }));
  const chosen = new Set(d.views);
  const library = lib.views.filter((v) => !chosen.has(v.code)).map((v) => ({ ref: v.code, label: `${v.code} ${v.name}` }));
  return { project, placeholders, library };
}

function PlaceholderForm({ onAdd, onCancel, busy }) {
  const [f, setF] = useState({ name: "", kind: "text", file_type: "docx", description: "" });
  return (
    <div className="kq-ph-form">
      <div className="own-row">
        <input placeholder="Name, e.g. Application retirement impact note" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} aria-label="Placeholder name" />
        <label className="small"><input type="radio" checked={f.kind === "text"} onChange={() => setF({ ...f, kind: "text" })} /> a text</label>
        <label className="small"><input type="radio" checked={f.kind === "file"} onChange={() => setF({ ...f, kind: "file" })} /> an empty file</label>
        {f.kind === "file" && <select value={f.file_type} onChange={(e) => setF({ ...f, file_type: e.target.value })} aria-label="Kind of file">
          {Object.entries(FILE_TYPES).map(([k, v]) => <option key={k} value={k}>.{k} {v}</option>)}</select>}
      </div>
      <input className="wide" placeholder="What it will show (optional)" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} aria-label="What it will show" />
      <div className="row-gap">
        <button className="primary" disabled={!f.name.trim() || busy} onClick={() => onAdd(f)}>Add the placeholder</button>
        <button className="linkish" onClick={onCancel}>Cancel</button>
      </div>
      {f.kind === "file" && <p className="small quiet">An empty .{f.file_type} file is made in the project's files (00_Project/Project files), to fill in later.</p>}
    </div>
  );
}

function AddView({ opts, onPick }) {
  return (
    <select value="" onChange={(e) => e.target.value && onPick(e.target.value)} aria-label="Add a view that answers it">
      <option value="">+ A view that answers it…</option>
      {opts.project.length > 0 && <optgroup label="The project's views">{opts.project.map((o) => <option key={o.ref} value={o.ref}>{o.label}</option>)}</optgroup>}
      {opts.placeholders.length > 0 && <optgroup label="Placeholders">{opts.placeholders.map((o) => <option key={o.ref} value={o.ref}>{o.label}</option>)}</optgroup>}
      {opts.library.length > 0 && <optgroup label="The view library (chosen for the project too)">{opts.library.map((o) => <option key={o.ref} value={o.ref}>{o.label}</option>)}</optgroup>}
    </select>
  );
}

// ---------------------------------------------------------------- the wizard: Views step, top
export function QuestionMapping({ d, set, lib }) {
  const [phFor, setPhFor] = useState(null);       // the question index a placeholder is being made for
  const opts = wizardOptions(d, lib);
  const label = Object.fromEntries([...opts.project, ...opts.placeholders, ...opts.library].map((o) => [o.ref, o.label]));
  const qs = d.key_questions.map((q, i) => ({ q, i })).filter(({ q }) => q.question.trim());
  const map = (i, ref) => {
    const q = d.key_questions[i];
    if ((q.views || []).includes(ref)) return;
    set("key_questions", d.key_questions.map((x, j) => (j === i ? { ...x, views: [...(x.views || []), ref] } : x)));
    if (/^VP-|^PV-/.test(ref) && lib.views.some((v) => v.code === ref) && !d.views.includes(ref)
      && !(d.existing_vps || []).some((v) => v.code === ref)) set("views", [...d.views, ref]);
  };
  const unmap = (i, ref) => set("key_questions", d.key_questions.map((x, j) => (j === i ? { ...x, views: (x.views || []).filter((r) => r !== ref) } : x)));
  function addPlaceholder(i, f) {
    const key = newKey();
    set("placeholder_views", [...d.placeholder_views, { ...f, key, name: f.name.trim() }]);
    set("key_questions", d.key_questions.map((x, j) => (j === i ? { ...x, views: [...(x.views || []), `ph:${key}`] } : x)));
    setPhFor(null);
  }
  const updPh = (k, field, v) => set("placeholder_views", d.placeholder_views.map((p) => ((p.code || p.key) === k ? { ...p, [field]: v } : p)));
  function removePh(p) {
    const ref = p.code || `ph:${p.key}`;
    set("key_questions", d.key_questions.map((x) => ({ ...x, views: (x.views || []).filter((r) => r !== ref) })));
    if (p.code && p.existing) set("removed_placeholders", [...(d.removed_placeholders || []), p.code]);
    set("placeholder_views", d.placeholder_views.filter((x) => x !== p));
  }
  const unanswered = qs.filter(({ q }) => !(q.views || []).length).length;
  return (
    <div className="kq-mapping">
      <h3>Answering the key questions</h3>
      {!qs.length && <p className="quiet small">No key questions (the Key questions step): choose the views below as they are.</p>}
      {qs.length > 0 && <p className="quiet small">The views that answer each question. A view from the library is chosen for the project
        too. Where none fits, add a placeholder: a text, or an empty file. {unanswered > 0 && <b>{unanswered} not answered by any view yet.</b>}</p>}
      {qs.map(({ q, i }) => (
        <div key={q.id || q.key} className="goal-box kq-box">
          <div><b>Q{i + 1}</b> {q.question}{q.asked_by && <span className="quiet small"> · asked by {q.asked_by}</span>}</div>
          {q.approach && <div className="small quiet">Expected: {q.approach}</div>}
          <div className="kq-chips">
            {(q.views || []).map((r) => (
              <span key={r} className={`chip kq-chip${/^PH-|^ph:/.test(r) ? " ph" : ""}`}>{label[r] || r}
                <button className="linkish" onClick={() => unmap(i, r)} aria-label={`Unlink ${label[r] || r}`}>×</button></span>
            ))}
            {!(q.views || []).length && <span className="small quiet">not answered yet</span>}
          </div>
          {phFor === i ? <PlaceholderForm onAdd={(f) => addPlaceholder(i, f)} onCancel={() => setPhFor(null)} />
            : <div className="row-gap"><AddView opts={opts} onPick={(r) => map(i, r)} />
              <button className="linkish" onClick={() => setPhFor(i)}>+ No view fits: a placeholder</button></div>}
        </div>
      ))}
      {d.placeholder_views.length > 0 && <>
        <h3>Placeholder views</h3>
        <p className="quiet small">They stay in this project. A file one becomes an empty file in the project's files when the project is saved.</p>
        {d.placeholder_views.map((p) => {
          const ref = p.code || `ph:${p.key}`;
          const answers = d.key_questions.map((q, i) => ((q.views || []).includes(ref) ? `Q${i + 1}` : null)).filter(Boolean);
          return (
            <div key={p.code || p.key} className="own-row small">
              <b>{p.code || "new"}</b>
              <input value={p.name} onChange={(e) => updPh(p.code || p.key, "name", e.target.value)} aria-label="Placeholder name" />
              <input value={p.description || ""} placeholder="What it will show" onChange={(e) => updPh(p.code || p.key, "description", e.target.value)} style={{ flex: 2 }} aria-label="What it will show" />
              <span className="quiet">{p.kind === "file" ? `.${p.file_type}${p.file_name ? " (made)" : ""}` : "text"}</span>
              <span className="quiet">{answers.join(", ") || "answers nothing"}</span>
              <button className="linkish" onClick={() => removePh(p)}>Remove</button>
            </div>
          );
        })}
      </>}
    </div>
  );
}

// ---------------------------------------------------------------- the project's Key questions tab
export const STATUS = { open: ["off", "open"], answered: ["amber", "answered: waiting for acceptance"], accepted: ["green", "accepted"] };
const ACTIONS = { asked: "asked", changed: "changed", answered: "answered", accepted: "accepted", rejected: "not accepted", reopened: "opened again" };
const when = (v) => (v ? new Date(v).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "");

function QuestionForm({ q, names, onSave, onCancel, busy }) {
  const [f, setF] = useState({ question: q?.question || "", asked_by: q?.asked_by || "", approach: q?.approach || "" });
  return (
    <div className="goal-box kq-box">
      <input className="wide" placeholder={`The question, e.g. ${EXAMPLES[0]}`} value={f.question} onChange={(e) => setF({ ...f, question: e.target.value })} aria-label="The question" />
      <div className="own-row"><input list="kq-askers-tab" placeholder="Who asks it (stakeholders)" value={f.asked_by}
        onChange={(e) => setF({ ...f, asked_by: e.target.value })} aria-label="Who asks it" /></div>
      <datalist id="kq-askers-tab">{(names || []).map((n) => <option key={n} value={n} />)}</datalist>
      <textarea className="wide" rows={2} placeholder="The answer we expect, or how we will answer it" value={f.approach}
        onChange={(e) => setF({ ...f, approach: e.target.value })} aria-label="Expected answer or approach" />
      {q?.status === "accepted" && <p className="small status warn">It is accepted: changing the question takes the acceptance away.</p>}
      <div className="row-gap">
        <button className="primary" disabled={!f.question.trim() || busy} onClick={() => onSave(f)}>{q ? "Save" : "Add the question"}</button>
        <button className="linkish" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

const plain = (html) => (html || "").replace(/<[^>]+>|&nbsp;/g, " ").trim();
// an answer saved before it was rich text, or from the seed or an assistant as plain text
const AnswerText = ({ html }) => (/^\s*</.test(html || "")
  // eslint-disable-next-line react/no-danger -- cleaned by the server (eax/project_work.clean_html)
  ? <div className="rich-view" dangerouslySetInnerHTML={{ __html: html }} /> : <div>{html}</div>);

// the answer: a summary (rich text), and what holds it: documents of the project and links (the views mapped to it link too)
function AnswerForm({ p, q, busy, onSave, onCancel }) {
  const [summary, setSummary] = useState(q.answer || "");
  const [docs, setDocs] = useState((q.links || []).filter((l) => l.document).map((l) => l.document));
  const [links, setLinks] = useState((q.links || []).filter((l) => l.url).map((l) => ({ url: l.url, label: l.label })));
  const [find, setFind] = useState("");
  const all = (p.documents || []).filter((d) => d.file_name || d.title);
  const name = (d) => d.title || d.file_name;
  const found = find.trim() ? all.filter((d) => !docs.includes(d.id) && `${name(d)} ${d.folder}`.toLowerCase().includes(find.toLowerCase())).slice(0, 8) : [];
  const updLink = (i, k, v) => setLinks(links.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const points = docs.length + links.filter((l) => l.url.trim()).length + q.views.length;
  return (
    <div className="goal-box kq-box kq-answer-form">
      <label className="small"><b>The answer</b>: a summary, pointing to the artifacts that hold it</label>
      <RichText value={summary} onChange={setSummary}
        placeholder="e.g. Eleven interfaces and four processes use it; seven move to the hub, four retire with it. See the cooperation view and the impact assessment." />
      <div className="small"><b>Documents of the project</b> {docs.map((g) => {
        const d = all.find((x) => x.id === g);
        return <span key={g} className="chip kq-chip">📄 {d ? name(d) : "a document"}<button className="linkish" onClick={() => setDocs(docs.filter((x) => x !== g))} aria-label="Take it out">×</button></span>;
      })}</div>
      <input className="wide" placeholder={all.length ? "Find a document of the project to point to…" : "The project has no documents yet"} value={find}
        disabled={!all.length} onChange={(e) => setFind(e.target.value)} aria-label="Find a document" />
      {found.length > 0 && <ul className="kq-found small">{found.map((d) => (
        <li key={d.id}><button className="linkish" onClick={() => { setDocs([...docs, d.id]); setFind(""); }}>📄 {name(d)}</button> <span className="quiet">{d.folder}</span></li>))}</ul>}
      <div className="small"><b>Links</b> <span className="quiet">(a report, a page, a shared file: https://…, or #/… for a page of EA Explorer)</span></div>
      {links.map((l, i) => (
        <div key={i} className="own-row">
          <input placeholder="https://…" value={l.url} onChange={(e) => updLink(i, "url", e.target.value)} aria-label={`Link ${i + 1}`} style={{ flex: 2 }} />
          <input placeholder="What it is" value={l.label} onChange={(e) => updLink(i, "label", e.target.value)} aria-label={`Link ${i + 1}: what it is`} />
          <button className="linkish" onClick={() => setLinks(links.filter((_x, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button className="linkish small" onClick={() => setLinks([...links, { url: "", label: "" }])}>+ a link</button>
      <p className="small quiet">{q.views.length ? `Its ${q.views.length} view${q.views.length > 1 ? "s" : ""} link too.` : "No view is mapped to it."}
        {!points && <b> Point the answer to at least one document, link or view.</b>}</p>
      <div className="row-gap">
        <button className="primary" disabled={!plain(summary) || !points || busy}
          onClick={() => onSave({ answer: summary, documents: docs, links: links.filter((l) => l.url.trim()) })}>
          {q.status === "open" ? "Answer it" : "Save the answer"}</button>
        <button className="linkish" onClick={onCancel}>Cancel</button>
      </div>
      {q.status === "accepted" && <p className="small status warn">It is accepted: a new answer needs accepting again.</p>}
    </div>
  );
}

// a contributor records the stakeholder's decision given outside the application, with optional evidence
function RecordForm({ q, names, busy, onSave, onCancel }) {
  const [f, setF] = useState({ decision: "accepted", by: q.asked_by || "", on: new Date().toISOString().slice(0, 10), note: "" });
  const [file, setFile] = useState(null);
  return (
    <div className="goal-box kq-box">
      <div className="own-row small">
        <label><input type="radio" checked={f.decision === "accepted"} onChange={() => setF({ ...f, decision: "accepted" })} /> accepted</label>
        <label><input type="radio" checked={f.decision === "rejected"} onChange={() => setF({ ...f, decision: "rejected" })} /> not accepted (opens it again)</label>
      </div>
      <div className="own-row">
        <input list="kq-askers-rec" placeholder="The stakeholder who decided" value={f.by} onChange={(e) => setF({ ...f, by: e.target.value })} aria-label="Who decided" />
        <datalist id="kq-askers-rec">{(names || []).map((n) => <option key={n} value={n} />)}</datalist>
        <input type="date" value={f.on} onChange={(e) => setF({ ...f, on: e.target.value })} aria-label="On" />
      </div>
      <input className="wide" placeholder={f.decision === "rejected" ? "Why not (needed)" : "Note, e.g. by email after the steering committee"} value={f.note}
        onChange={(e) => setF({ ...f, note: e.target.value })} aria-label="Note" />
      <label className="small">Evidence (optional: the email, the minutes) <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} /></label>
      <div className="row-gap">
        <button className="primary" disabled={!f.by.trim() || (f.decision === "rejected" && !f.note.trim()) || busy} onClick={() => onSave(f, file)}>Record it</button>
        <button className="linkish" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

function NoteForm({ label, need, busy, onSave, onCancel, placeholder }) {
  const [note, setNote] = useState("");
  return (
    <div className="own-row">
      <input className="wide" placeholder={placeholder} value={note} onChange={(e) => setNote(e.target.value)} aria-label={label} />
      <button className="primary" disabled={(need && !note.trim()) || busy} onClick={() => onSave(note)}>{label}</button>
      <button className="linkish" onClick={onCancel}>Cancel</button>
    </div>
  );
}

// what the answer points to, as links
function AnswerLinks({ p, q, phs, url, setMsg }) {
  const vp = Object.fromEntries(p.views.map((v) => [v.code, v]));
  return (
    <div className="kq-links small">
      {(q.links || []).map((l, i) => (l.document
        ? <button key={i} className="linkish" title={l.folder} onClick={() => apiDownload(`${url}/documents/${l.document}`, l.file_name).catch((e) => setMsg(e.message))}>📄 {l.title || l.file_name}</button>
        : <a key={i} href={l.url} target={l.url.startsWith("#") ? undefined : "_blank"} rel="noreferrer">🔗 {l.label || l.url}</a>))}
      {q.views.map((c) => {
        const ph = phs.find((x) => x.code === c);
        if (ph) return ph.document
          ? <button key={c} className="linkish" onClick={() => apiDownload(`${url}/documents/${ph.document}`, ph.file_name).catch((e) => setMsg(e.message))}>📄 {c} {ph.name}</button>
          : <span key={c} className="quiet">◇ {c} {ph.name} (placeholder)</span>;
        const v = vp[c];
        return v?.model ? <a key={c} href={`#/metamodel/${v.model}/views/${encodeURIComponent(c)}`}>◧ {c} {v.name}</a> : <span key={c}>◧ {c}</span>;
      })}
    </div>
  );
}

export function KeyQuestionsPanel({ p }) {
  const may = p.may_contribute;
  const isStakeholder = (p.my_roles || []).includes("stakeholder") && !p.frozen;
  const { data: lib } = useApi(may ? "/api/v1/projects/library" : null);
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState(null);         // [question id, what]: edit | answer | record | reject | reopen | map | placeholder
  const [hist, setHist] = useState({});
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const qs = p.key_questions || [];
  const phs = p.placeholder_views || [];
  const names = [...new Set([...(p.stakeholders || []).map((s) => s.name), ...qs.map((q) => q.asked_by)].filter(Boolean))];
  const vpName = Object.fromEntries([...(lib?.views || []).map((v) => [v.code, `${v.code} ${v.name}`]),
    ...p.views.map((v) => [v.code, `${v.code} ${v.name}`]), ...phs.map((x) => [x.code, phLabel(x)])]);
  const have = new Set(p.views.map((v) => v.code));
  const opts = {
    project: p.views.map((v) => ({ ref: v.code, label: `${v.code} ${v.name}` })),
    placeholders: phs.map((x) => ({ ref: x.code, label: phLabel(x) })),
    library: (lib?.views || []).filter((v) => !have.has(v.code)).map((v) => ({ ref: v.code, label: `${v.code} ${v.name}` })),
  };
  const url = `/api/v1/projects/${p.id}`;
  async function act(fn) {
    setBusy(true); setMsg("");
    try { const r = await fn(); setMsg(r?.message || ""); setOpen(null); setAdding(false); refreshAll(); return true; }
    catch (e) { setMsg(e.message); return false; } finally { setBusy(false); }
  }
  const post = (q, what, body) => act(() => apiFetch(`${url}/key-questions/${q.id}/${what}`, { method: "POST", body: JSON.stringify(body) }));
  const save = (q, f) => act(() => (q ? apiFetch(`${url}/key-questions/${q.id}`, { method: "PUT", body: JSON.stringify(f) })
    : apiFetch(`${url}/key-questions`, { method: "POST", body: JSON.stringify(f) })));
  const setVps = (q, list) => act(() => apiFetch(`${url}/key-questions/${q.id}`, { method: "PUT", body: JSON.stringify({ views: list }) }));
  const addPh = (q, f) => act(() => apiFetch(`${url}/placeholder-views`, { method: "POST", body: JSON.stringify({ ...f, questions: [q.id] }) }));
  const record = (q, f, file) => act(() => {
    const fd = new FormData();   // multipart: the evidence file goes with it
    Object.entries(f).forEach(([k, v]) => fd.append(k, v));
    if (file) fd.append("file", file);
    return apiUpload(`${url}/key-questions/${q.id}/record`, fd);
  });
  const is = (q, what) => open && open[0] === q.id && open[1] === what;
  const counts = Object.fromEntries(Object.keys(STATUS).map((k) => [k, qs.filter((q) => q.status === k).length]));
  const shown = qs.map((q, i) => ({ q, n: i + 1 })).filter(({ q }) => filter === "all" || q.status === filter);
  const noFile = phs.filter((x) => x.kind === "file" && !x.document);
  const unlinked = p.views.filter((v) => !qs.some((q) => q.views.includes(v.code)));
  return (
    <div className="kq-panel">
      <p className="quiet small">The questions this project's work answers. Each says who asks it and the answer we expect; the views mapped to it
        show the work. When it is answered, the answer is a summary pointing to the artifacts that hold it; the stakeholder then accepts it
        (in the application, or a contributor records an acceptance given outside, with evidence). A rejection opens it again.</p>
      <div className="row-gap kq-filters" role="tablist">
        <button role="tab" className={`tab${filter === "all" ? " on" : ""}`} onClick={() => setFilter("all")}>All <span className="count">{qs.length}</span></button>
        {Object.entries(STATUS).map(([k, [, label]]) => (
          <button key={k} role="tab" className={`tab${filter === k ? " on" : ""}`} onClick={() => setFilter(k)}>
            <span className={`dot ${STATUS[k][0]}`} /> {label} <span className="count">{counts[k]}</span></button>))}
      </div>
      {isStakeholder && counts.answered > 0 && <p className="status warn small">{counts.answered} answer{counts.answered > 1 ? "s wait" : " waits"} for you to accept or reject.</p>}
      {!qs.length && <p className="quiet small">No key questions yet.{may ? " Add the first below." : ""}</p>}
      {shown.map(({ q, n }) => (
        <div key={q.id} className={`goal-box kq-card ${q.status}`}>
          {is(q, "edit") ? <QuestionForm q={q} names={names} busy={busy} onSave={(f) => save(q, f)} onCancel={() => setOpen(null)} /> : <>
            <div className="kq-head">
              <b>Q{n}</b> <span className="kq-q">{q.question}</span>
              <span className={`kq-status ${q.status}`}><span className={`dot ${STATUS[q.status][0]}`} /> {STATUS[q.status][1]}</span>
            </div>
            <div className="small quiet">{q.asked_by && <>asked by {q.asked_by} · </>}{q.approach ? <>expected: {q.approach}</> : "no expected answer written"}</div>
          </>}
          {q.status !== "open" || q.answer ? (
            <div className="kq-answer">
              <div className="small"><b>{q.status === "open" ? "Last answer (not accepted)" : "Answer"}</b>
                {q.answered_by && <span className="quiet"> · {q.answered_by}, {when(q.answered_at)}</span>}</div>
              <AnswerText html={q.answer} />
              <AnswerLinks p={p} q={q} phs={phs} url={url} setMsg={setMsg} />
            </div>
          ) : <AnswerLinks p={p} q={{ ...q, links: [] }} phs={phs} url={url} setMsg={setMsg} />}
          {q.status === "accepted" && (
            <div className="small kq-accepted">✓ Accepted by <b>{q.accepted_by}</b>, {when(q.accepted_at)}
              {q.accept_recorded_by && <span className="quiet"> (recorded by {q.accept_recorded_by})</span>}
              {q.accept_note && <> · {q.accept_note}</>}
              {q.evidence && <> · <button className="linkish" onClick={() => apiDownload(`${url}/documents/${q.evidence}`, q.evidence_name).catch((e) => setMsg(e.message))}>📎 {q.evidence_name}</button></>}
            </div>)}
          {is(q, "answer") && <AnswerForm p={p} q={q} busy={busy} onSave={(b) => post(q, "answer", b)} onCancel={() => setOpen(null)} />}
          {is(q, "record") && <RecordForm q={q} names={names} busy={busy} onSave={(f, file) => record(q, f, file)} onCancel={() => setOpen(null)} />}
          {is(q, "reject") && <NoteForm label="Not accepted" need busy={busy} placeholder="Why not: what the answer still needs"
            onSave={(note) => post(q, "decide", { decision: "rejected", note })} onCancel={() => setOpen(null)} />}
          {is(q, "accept") && <NoteForm label="Accept" busy={busy} placeholder="A note (optional)"
            onSave={(note) => post(q, "decide", { decision: "accepted", note })} onCancel={() => setOpen(null)} />}
          {is(q, "reopen") && <NoteForm label="Open it again" need busy={busy} placeholder="Why it is opened again"
            onSave={(note) => post(q, "reopen", { note })} onCancel={() => setOpen(null)} />}
          {is(q, "map") && (
            <div className="kq-map">
              <div className="kq-chips">{q.views.map((c) => (
                <span key={c} className={`chip kq-chip${/^PH-/.test(c) ? " ph" : ""}`}>{vpName[c] || c}
                  <button className="linkish" aria-label={`Unlink ${c}`} disabled={busy} onClick={() => setVps(q, q.views.filter((x) => x !== c))}>×</button></span>))}
                {!q.views.length && <span className="small quiet">no view yet</span>}</div>
              <div className="row-gap small"><AddView opts={opts} onPick={(r) => setVps(q, [...q.views, r])} />
                <button className="linkish" onClick={() => setOpen([q.id, "placeholder"])}>+ No view fits: a placeholder</button>
                <button className="linkish" onClick={() => setOpen(null)}>Done</button></div>
            </div>)}
          {is(q, "placeholder") && <PlaceholderForm busy={busy} onAdd={(f) => addPh(q, f)} onCancel={() => setOpen([q.id, "map"])} />}
          {!open || open[0] !== q.id ? (
            <div className="row-gap small kq-actions">
              {may && <button className="linkish" onClick={() => setOpen([q.id, "answer"])}>{q.status === "open" && !q.answer ? "✎ Answer it" : "✎ Change the answer"}</button>}
              {isStakeholder && q.status === "answered" && <>
                <button className="primary small" onClick={() => setOpen([q.id, "accept"])}>✓ Accept</button>
                <button className="linkish" onClick={() => setOpen([q.id, "reject"])}>Not accepted…</button></>}
              {may && q.status === "answered" && <button className="linkish" onClick={() => setOpen([q.id, "record"])}>Record the stakeholder's decision…</button>}
              {may && q.status !== "open" && <button className="linkish" onClick={() => setOpen([q.id, "reopen"])}>Open it again…</button>}
              {may && <button className="linkish" onClick={() => setOpen([q.id, "map"])}>Views ({q.views.length})</button>}
              {may && <button className="linkish" onClick={() => setOpen([q.id, "edit"])}>Edit the question</button>}
              {may && <button className="linkish" disabled={busy} onClick={() => act(() => apiFetch(`${url}/key-questions/${q.id}`, { method: "DELETE" }))}>Remove</button>}
              <button className="linkish" onClick={() => setHist({ ...hist, [q.id]: !hist[q.id] })}>History ({(q.history || []).length})</button>
            </div>) : null}
          {hist[q.id] && <ul className="small kq-history">{(q.history || []).map((h, i) => (
            <li key={i}><span className="quiet">{when(h.at)}</span> {h.username} {ACTIONS[h.action] || h.action}{h.note ? `: ${h.note}` : ""}</li>))}</ul>}
        </div>
      ))}
      {may && (adding ? <QuestionForm names={names} busy={busy} onSave={(f) => save(null, f)} onCancel={() => setAdding(false)} />
        : <button onClick={() => setAdding(true)}>+ Add a key question</button>)}
      {phs.length > 0 && <>
        <h4>Placeholder views</h4>
        <table className="grid-table small">
          <thead><tr><th>Code</th><th>Name</th><th>What it will show</th><th>Kind</th><th>Answers</th>{may && <th />}</tr></thead>
          <tbody>
            {phs.map((x) => (
              <tr key={x.code}>
                <td><b>{x.code}</b></td><td>{x.name}</td><td className="quiet">{x.description}</td>
                <td>{x.kind === "file" ? (x.document
                  ? <button className="linkish" onClick={() => apiDownload(`${url}/documents/${x.document}`, x.file_name).catch((e) => setMsg(e.message))}>📄 {x.file_name}</button>
                  : <span className="quiet">.{x.file_type}: file not made yet</span>) : "text"}</td>
                <td>{x.answers.map((id) => `Q${qs.findIndex((q) => q.id === id) + 1}`).join(", ") || <span className="quiet">nothing</span>}</td>
                {may && <td><button className="linkish" disabled={busy} onClick={() => act(() => apiFetch(`${url}/placeholder-views/${x.code}`, { method: "DELETE" }))}>Remove</button></td>}
              </tr>
            ))}
          </tbody>
        </table>
        {may && noFile.length > 0 && <button disabled={busy} onClick={() => act(() => apiFetch(`${url}/placeholder-views/files`, { method: "POST" }))}>
          Make the {noFile.length} missing file{noFile.length > 1 ? "s" : ""}</button>}
      </>}
      {qs.length > 0 && unlinked.length > 0 && <p className="small quiet">Views of the project that answer no key question yet: {unlinked.map((v) => v.code).join(", ")}.</p>}
      {msg && <p className="small status">{msg}</p>}
    </div>
  );
}

// after a save: the empty files of the file placeholders, once Documents takes them (the repository may still be being built)
export async function makePlaceholderFiles(projectId) {
  for (let k = 0; k < 20; k += 1) {
    try {
      const r = await apiFetch(`/api/v1/projects/${projectId}/placeholder-views/files`, { method: "POST" });
      if (!r.left?.length) return "";
    } catch (e) { if (!/not built yet|being built|try again|Documents/i.test(e.message)) return e.message; }
    await new Promise((res) => setTimeout(res, 3000));
  }
  return "Some placeholder files are not made yet: make them on the project's Views tab.";
}
