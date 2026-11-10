// Surveys (owner, 9 Nov 2026, phase 38.1, D375, D446 to D449) and EA capability maturity (phase 40, D377, D450 to D453).
// #/surveys                     to answer, answered, mine (and all for a Super Admin); a new survey
// #/surveys/<id>                the designer while a draft (sections, questions, conditions, recipients), then running it
// #/surveys/<id>/answer         answering (saved as you go; an anonymous survey's draft stays in this browser)
// #/surveys/<id>/results        results by question, progress, who has answered (not anonymous), Excel
// #/maturity                    assessments, the trend and the evidence EA Explorer measures (Super Admins)
// #/maturity/<id>               an assessment's scores by element, gaps against targets, the evidence and the one before
// Delivered through the task list (a notification needing action) and a link, never email. Answers never change a model.
import { useEffect, useMemo, useState } from "react";
import { apiDownload, apiFetch, can } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { fmtDate, fmtDateTime } from "./fmt";
import { LinkEditor, LinkList } from "./Links";

const KINDS = { single: "One choice", multi: "Several choices", yes_no: "Yes or no", rating: "Rating", number: "Number",
  date: "Date", text: "Short text", long_text: "Long text", links: "Links (evidence)" };
const OPS = { equals: "is", not_equals: "is not", includes: "includes", answered: "is answered" };
const STATUS = { draft: "Draft", open: "Open", closed: "Closed" };
const RKINDS = { user: "A person", role: "Everyone with a global role", model: "Everyone on a model", project: "Everyone on a project" };
const ROLE_NAMES = { "super-admin": "Super Admin", "it-admin": "IT Admin", "user-admin": "User Admin", "keycloak-admin": "Keycloak Admin",
  "model-creator": "Model Creator", "library-admin": "Library Admin", user: "User", "model-admin": "Model Admin", "model-sub-admin": "Model Sub Admin",
  committer: "Committer", architect: "Architect", "history-viewer": "History Viewer", "report-viewer": "Report Viewer" };

const go = (h) => { window.location.hash = h; };
const Status = ({ s }) => <span className={`badge survey-${s}`}>{STATUS[s] || s}</span>;
const Msg = ({ m }) => (m?.text ? <p className={`status ${m.ok ? "ok" : "bad"}`}>{m.text}</p> : null);

// the same rule as the API's surveys.visible(): which questions show for these answers
function fits(c, answers, shown) {
  if (!c) return true;
  if (!shown.has(c.question)) return false;
  const a = answers[c.question];
  const empty = a === undefined || a === null || a === "" || (Array.isArray(a) && !a.length);
  if (c.op === "answered") return !empty;
  if (empty) return c.op === "not_equals";
  const vals = Array.isArray(a) ? a.map(String) : [typeof a === "boolean" ? String(a) : String(a)];
  if (c.op === "includes") return vals.includes(String(c.value ?? ""));
  const exactly = vals.length === 1 && vals[0] === String(c.value ?? "");
  return c.op === "equals" ? exactly : !exactly;
}
export function visibleKeys(spec, answers) {
  const shown = new Set();
  for (const s of spec?.sections || []) {
    if (!fits(s.condition, answers, shown)) continue;
    for (const q of s.questions || []) if (fits(q.condition, answers, shown)) shown.add(q.key);
  }
  return shown;
}
const allQuestions = (spec) => (spec?.sections || []).flatMap((s) => (s.questions || []).map((q) => ({ ...q, section: s.title })));

export default function SurveysPage({ route }) {
  if (route.startsWith("#/maturity")) {
    const id = (route.match(/^#\/maturity\/([^/?]+)/) || [])[1];
    return id ? <MaturityResult id={id} /> : <MaturityPage />;
  }
  const m = route.match(/^#\/surveys\/([^/?]+)(?:\/(answer|results))?/);
  if (m && m[1] !== "new") {
    if (m[2] === "answer") return <AnswerPage id={m[1]} />;
    if (m[2] === "results") return <ResultsPage id={m[1]} />;
    return <SurveyPage id={m[1]} />;
  }
  return <SurveyList />;
}

// ---------------------------------------------------------------- the list
function SurveyList() {
  const { data, error } = useApi("/api/v1/surveys");
  const [tab, setTab] = useState(null);
  const [title, setTitle] = useState("");
  const [msg, setMsg] = useState(null);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const tabs = [["to_answer", "To answer"], ["answered", "Answered"], ...(data.may_create || data.mine.length ? [["mine", "I run"]] : []),
    ...(data.all.length ? [["all", "Every survey"]] : [])];
  const on = tab || (data.to_answer.length || !data.mine.length ? "to_answer" : "mine");
  const rows = data[on] || [];
  async function make() {
    try {
      const s = await apiFetch("/api/v1/surveys", { method: "POST", body: JSON.stringify({ title }) });
      refreshAll(); go(`#/surveys/${s.id}`);
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  }
  return (
    <section>
      <h1>Surveys</h1>
      <p className="quiet">Ask people questions and look at the answers. A survey reaches people through their task list (Notifications,
        needing action) and a link; nothing is emailed. Answers never change any model.</p>
      {can("maturity.manage") && <p className="small"><a href="#/maturity">EA capability maturity assessments ›</a></p>}
      <Msg m={msg} />
      {data.may_create && <div className="row-gap">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="A new survey's title" aria-label="New survey title" style={{ minWidth: 320 }} />
        <button className="primary" disabled={!title.trim()} onClick={make}>＋ New survey</button></div>}
      <div className="tabs" role="tablist">
        {tabs.map(([k, n]) => <button key={k} role="tab" aria-selected={on === k} className={`tab${on === k ? " on" : ""}`} onClick={() => setTab(k)}>
          {n} <span className="small quiet">{(data[k] || []).length || ""}</span></button>)}
      </div>
      <div className="tab-panel">
        <table className="grid-table">
          <thead><tr><th>Survey</th><th>Status</th><th>From</th><th>Closes</th>{["mine", "all"].includes(on) && <th>Answered</th>}<th /></tr></thead>
          <tbody>
            {rows.map((s) => <tr key={s.id}>
              <td><b>{s.title}</b>{s.kind === "maturity" && <span className="badge"> · maturity assessment</span>}
                {s.anonymous && <span className="badge"> · anonymous</span>}{s.description && <div className="small quiet">{s.description.slice(0, 160)}</div>}</td>
              <td><Status s={s.status} /></td><td className="small">{s.owner}</td>
              <td className="small">{s.closes_at ? fmtDate(s.closes_at) : ""}</td>
              {["mine", "all"].includes(on) && <td className="small">{s.progress ? `${s.progress.answered_of_asked} of ${s.progress.asked}${s.progress.by_link ? ` (+${s.progress.by_link} by link)` : ""}` : ""}</td>}
              <td><div className="row-gap">
                {s.may_answer && <a className="button primary" href={`#/surveys/${s.id}/answer`}>{s.answered ? "Change my answers" : "Answer"}</a>}
                {s.answered && !s.may_answer && <span className="small quiet">answered</span>}
                {s.runs && <a href={`#/surveys/${s.id}`}>{s.status === "draft" ? "Edit" : "Run"}</a>}
                {s.runs && s.status !== "draft" && <a href={s.kind === "maturity" ? `#/maturity/${s.id}` : `#/surveys/${s.id}/results`}>Results</a>}
              </div></td></tr>)}
            {!rows.length && <tr><td colSpan={6} className="quiet">{on === "to_answer" ? "Nothing to answer." : "None."}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- one survey: design it, then run it
function SurveyPage({ id }) {
  const url = `/api/v1/surveys/${id}`;
  const { data, error } = useApi(url);
  const [msg, setMsg] = useState(null);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  if (!data.runs) { go(`#/surveys/${id}/answer`); return null; }
  async function act(what, body, ask) {
    if (ask && !window.confirm(ask)) return;
    try {
      const r = await apiFetch(`${url}${what ? `/${what}` : ""}`, { method: what ? "POST" : "DELETE", body: body ? JSON.stringify(body) : undefined });
      refreshAll();
      if (what === "copy") { go(`#/surveys/${r.id}`); return; }
      if (!what) { go("#/surveys"); return; }
      setMsg({ ok: true, text: what === "send" ? `Sent: ${r.asked_now} people asked.` : what === "remind" ? `${r.reminded} people reminded.`
        : what === "recipients" ? `${r.asked_now} more people asked.` : what === "close" ? "Closed." : what === "reopen" ? "Open again." : "Done." });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  }
  const link = `${window.location.origin}${window.location.pathname}#/surveys/${id}/answer`;
  return (
    <section className="survey-page">
      <p><a href="#/surveys">‹ Surveys</a>{data.kind === "maturity" && <> · <a href="#/maturity">Maturity assessments</a></>}</p>
      <h1>{data.title} <Status s={data.status} /></h1>
      <Msg m={msg} />
      <div className="row-gap">
        {data.status === "draft" && <button className="primary" onClick={() => act("send", null, "Send it now? Everyone it is for gets it in their task list; the questions can no longer change.")}>Send</button>}
        {data.status === "open" && <button onClick={() => act("remind")}>Remind those who have not answered</button>}
        {data.status === "open" && <button onClick={() => act("close", null, "Close it now? Nobody can answer after that.")}>Close</button>}
        {data.status === "closed" && <button onClick={() => act("reopen")}>Reopen</button>}
        {data.status !== "draft" && <a className="button" href={data.kind === "maturity" ? `#/maturity/${id}` : `#/surveys/${id}/results`}>Results</a>}
        <a className="button" href={`#/surveys/${id}/answer`}>{data.status === "draft" ? "Preview" : "Answer it myself"}</a>
        <button onClick={() => act("copy")}>Copy</button>
        {data.status === "draft" && <button onClick={() => act(null, null, "Delete this draft?")}>Delete</button>}
      </div>
      {data.status !== "draft" && <div className="survey-run">
        <Progress p={data.progress} />
        <p className="small">The link to answer: <code>{link}</code> <button className="linkish small" onClick={() => navigator.clipboard?.writeText(link)}>Copy link</button>
          {data.open_link ? " Anyone signed in who has it may answer." : " Only the people asked may answer."}</p>
        <p className="small quiet">Sent {fmtDateTime(data.opened_at)}{data.closed_at ? ` · closed ${fmtDateTime(data.closed_at)}` : ""}
          {data.last_reminded_at ? ` · last reminder ${fmtDateTime(data.last_reminded_at)}` : ""}</p>
      </div>}
      <Settings data={data} url={url} onMsg={setMsg} />
      <h2>Who it is for</h2>
      <Recipients data={data} url={url} onMsg={setMsg} onAdd={(r) => act("recipients", { recipients: r })} />
      <h2>Questions</h2>
      {data.status === "draft" ? <Designer spec={data.spec} url={url} onMsg={setMsg} maturity={data.kind === "maturity"} />
        : <><p className="small quiet">The questions were fixed when the survey was sent. Copy it to make a changed version.</p><SpecView spec={data.spec} /></>}
    </section>
  );
}

function Progress({ p }) {
  if (!p) return null;
  return (
    <div className="survey-progress" aria-label="Progress">
      <div className="survey-meter"><span style={{ width: `${p.percent}%` }} /></div>
      <span className="small"><b>{p.answered_of_asked}</b> of {p.asked} asked have answered ({p.percent}%)
        {p.by_link ? ` · ${p.by_link} more by the link` : ""}{p.in_progress ? ` · ${p.in_progress} started` : ""}</span>
    </div>
  );
}

function Settings({ data, url, onMsg }) {
  const [d, setD] = useState({ title: data.title, description: data.description, closes_at: data.closes_at ? String(data.closes_at).slice(0, 10) : "",
    remind_every_days: data.remind_every_days || "", anonymous: data.anonymous, open_link: data.open_link });
  const draft = data.status === "draft";
  async function save() {
    const body = { title: d.title, description: d.description, closes_at: d.closes_at || null, remind_every_days: d.remind_every_days || null, open_link: d.open_link };
    if (draft) body.anonymous = d.anonymous;
    try { await apiFetch(url, { method: "PATCH", body: JSON.stringify(body) }); refreshAll(); onMsg({ ok: true, text: "Saved." }); }
    catch (e) { onMsg({ ok: false, text: e.message }); }
  }
  const set = (k) => (e) => setD({ ...d, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  return (
    <div className="ed-form survey-settings">
      <label className="ed-field"><span>Title</span><input value={d.title} onChange={set("title")} /></label>
      <label className="ed-field"><span>What it is about <span className="quiet">(shown to the people answering)</span></span><textarea value={d.description} onChange={set("description")} /></label>
      <div className="row-gap">
        <label className="ed-field"><span>Closes on <span className="quiet">(empty: when you close it)</span></span><input type="date" value={d.closes_at} onChange={set("closes_at")} /></label>
        <label className="ed-field"><span>Remind every <span className="quiet">(days; empty: no automatic reminders)</span></span><input type="number" min="1" max="60" value={d.remind_every_days} onChange={set("remind_every_days")} /></label>
      </div>
      <label className="ed-field check"><input type="checkbox" checked={d.anonymous} disabled={!draft} onChange={set("anonymous")} />
        <span>Anonymous: answers carry no name; each person answers once; results show once 3 have answered {!draft && <span className="quiet">(fixed when sent)</span>}</span></label>
      <label className="ed-field check"><input type="checkbox" checked={d.open_link} onChange={set("open_link")} />
        <span>Anyone signed in who has the link may answer too</span></label>
      <div><button className="primary" onClick={save}>Save settings</button></div>
    </div>
  );
}

// ---------------------------------------------------------------- who it is for
function Recipients({ data, url, onMsg, onAdd }) {
  const [list, setList] = useState(data.recipients || []);
  const [adding, setAdding] = useState([]);
  useEffect(() => { setList(data.recipients || []); }, [data]);
  const draft = data.status === "draft";
  async function save(next) {
    setList(next);
    try { await apiFetch(url, { method: "PATCH", body: JSON.stringify({ recipients: next }) }); refreshAll(); }
    catch (e) { onMsg({ ok: false, text: e.message }); }
  }
  return (
    <div className="survey-recipients">
      <div>{list.map((r, i) => <span key={`${r.kind}${r.value}${r.role || ""}`} className="chip">{label(r)}
        {draft && <button className="linkish" aria-label="Remove" onClick={() => save(list.filter((_x, j) => j !== i))}>✕</button>}</span>)}
        {!list.length && <span className="quiet small">Nobody chosen yet.</span>}</div>
      {draft ? <RecipientPicker onPick={(r) => save([...list, r])} />
        : data.status === "open" && <>
          <p className="small quiet">Add more people (nobody is taken off). They are asked at once.</p>
          <div>{adding.map((r) => <span key={`${r.kind}${r.value}${r.role || ""}`} className="chip">{label(r)}</span>)}</div>
          <RecipientPicker onPick={(r) => setAdding([...adding, r])} />
          {adding.length > 0 && <button className="primary" onClick={() => { onAdd(adding); setAdding([]); }}>Ask them</button>}
        </>}
    </div>
  );
}
const label = (r) => r.label || (r.kind === "user" ? r.value : r.kind === "role" ? `Everyone: ${ROLE_NAMES[r.value] || r.value}`
  : `${r.kind === "model" ? "Model" : "Project"} ${r.value}${r.role ? ` (${ROLE_NAMES[r.role] || r.role})` : ""}`);

export function RecipientPicker({ onPick }) {
  const { data } = useApi("/api/v1/surveys/people");
  const [kind, setKind] = useState("user");
  const [value, setValue] = useState("");
  const [role, setRole] = useState("");
  if (!data) return null;
  function add() {
    if (!value) return;
    const r = { kind, value };
    if (kind === "model") { const m = data.models.find((x) => x.id === value); r.label = `Everyone on ${m?.name || value}${role ? ` (${ROLE_NAMES[role]})` : ""}`; if (role) r.role = role; }
    if (kind === "project") { const p = data.projects.find((x) => x.id === value); r.label = `Everyone on the project ${p?.name || value}`; }
    if (kind === "role") r.label = `Everyone who is ${ROLE_NAMES[value] || value}`;
    onPick(r); setValue(""); setRole("");
  }
  return (
    <div className="row-gap recipient-picker">
      <select value={kind} onChange={(e) => { setKind(e.target.value); setValue(""); }} aria-label="Who">
        {Object.entries(RKINDS).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select>
      {kind === "user" && <><input list="survey-people" value={value} onChange={(e) => setValue(e.target.value.trim().toLowerCase())} placeholder="user name" aria-label="Person" />
        <datalist id="survey-people">{data.users.map((u) => <option key={u} value={u} />)}</datalist></>}
      {kind === "role" && <select value={value} onChange={(e) => setValue(e.target.value)} aria-label="Global role"><option value="">Choose a role</option>
        {data.roles.map((r) => <option key={r} value={r}>{ROLE_NAMES[r] || r}</option>)}</select>}
      {kind === "model" && <><select value={value} onChange={(e) => setValue(e.target.value)} aria-label="Model"><option value="">Choose a model</option>
        {data.models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>
        <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Model role"><option value="">any role</option>
          {data.model_roles.map((r) => <option key={r} value={r}>{ROLE_NAMES[r] || r}</option>)}</select></>}
      {kind === "project" && <select value={value} onChange={(e) => setValue(e.target.value)} aria-label="Project"><option value="">Choose a project</option>
        {data.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>}
      <button onClick={add} disabled={!value}>Add</button>
    </div>
  );
}

// ---------------------------------------------------------------- the designer (a draft's sections and questions)
let seq = 0;
const newKey = (p) => `${p}${Date.now().toString(36)}${(seq += 1)}`;

function Designer({ spec, url, onMsg, maturity }) {
  const [sections, setSections] = useState(() => JSON.parse(JSON.stringify(spec?.sections || [])));
  const [dirty, setDirty] = useState(false);
  const change = (next) => { setSections(next); setDirty(true); };
  const earlierOf = (si, qi) => sections.flatMap((s, i) => (s.questions || []).filter((_q, j) => i < si || (i === si && j < qi)));
  async function save() {
    try {
      const r = await apiFetch(url, { method: "PATCH", body: JSON.stringify({ spec: { sections } }) });
      setSections(r.spec.sections); setDirty(false); refreshAll(); onMsg({ ok: true, text: "Questions saved." });
    } catch (e) { onMsg({ ok: false, text: e.message }); }
  }
  const setS = (i, s) => change(sections.map((x, j) => (j === i ? s : x)));
  const move = (arr, i, d) => { const a = [...arr]; const [x] = a.splice(i, 1); a.splice(i + d, 0, x); return a; };
  return (
    <div className="survey-designer">
      {maturity && <p className="small quiet">The starting questions follow the nine elements and six levels of the assessment. Each level question
        is scored by its options' scores; you may change the wording, add questions or remove comments.</p>}
      {sections.map((s, si) => (
        <fieldset key={s.key} className="survey-section">
          <legend>Section {si + 1}</legend>
          <div className="row-gap">
            <label className="ed-field" style={{ flex: 1 }}><span>Title</span><input value={s.title} onChange={(e) => setS(si, { ...s, title: e.target.value })} /></label>
            <button className="linkish" disabled={!si} onClick={() => change(move(sections, si, -1))} aria-label="Move up">▲</button>
            <button className="linkish" disabled={si === sections.length - 1} onClick={() => change(move(sections, si, 1))} aria-label="Move down">▼</button>
            <button className="linkish" onClick={() => change(sections.filter((_x, j) => j !== si))}>Remove section</button>
          </div>
          <label className="ed-field"><span>Introduction <span className="quiet">(optional)</span></span><input value={s.text || ""} onChange={(e) => setS(si, { ...s, text: e.target.value })} /></label>
          <ConditionEdit c={s.condition} earlier={earlierOf(si, 0)} onChange={(c) => setS(si, { ...s, condition: c })} what="Show this section only when" />
          {(s.questions || []).map((q, qi) => (
            <QuestionEdit key={q.key} q={q} n={qi + 1} earlier={earlierOf(si, qi)}
              onChange={(nq) => setS(si, { ...s, questions: s.questions.map((x, j) => (j === qi ? nq : x)) })}
              onRemove={() => setS(si, { ...s, questions: s.questions.filter((_x, j) => j !== qi) })}
              onMove={(d) => setS(si, { ...s, questions: move(s.questions, qi, d) })} last={qi === s.questions.length - 1} />))}
          <button onClick={() => setS(si, { ...s, questions: [...(s.questions || []), { key: newKey("q"), kind: "single", text: "", required: false,
            options: [{ value: "1", label: "" }, { value: "2", label: "" }] }] })}>＋ Question</button>
        </fieldset>))}
      <div className="row-gap">
        <button onClick={() => change([...sections, { key: newKey("s"), title: `Section ${sections.length + 1}`, questions: [] }])}>＋ Section</button>
        <button className="primary" disabled={!dirty} onClick={save}>Save questions</button>
        {dirty && <span className="small quiet">Not saved yet.</span>}
      </div>
    </div>
  );
}

function ConditionEdit({ c, earlier, onChange, what }) {
  if (!earlier.length) return null;
  const q = earlier.find((x) => x.key === c?.question);
  return (
    <div className="row-gap small survey-condition">
      <label className="row-gap"><input type="checkbox" checked={!!c} onChange={(e) => onChange(e.target.checked ? { question: earlier[earlier.length - 1].key, op: "equals", value: "" } : null)} />{what}</label>
      {c && <>
        <select value={c.question} onChange={(e) => onChange({ ...c, question: e.target.value, value: "" })} aria-label="Question">
          {earlier.map((x) => <option key={x.key} value={x.key}>{(x.text || x.key).slice(0, 60)}</option>)}</select>
        <select value={c.op} onChange={(e) => onChange({ ...c, op: e.target.value })} aria-label="Condition">
          {Object.entries(OPS).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select>
        {c.op !== "answered" && (q?.options ? <select value={c.value || ""} onChange={(e) => onChange({ ...c, value: e.target.value })} aria-label="Value">
          <option value="">choose</option>{q.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          : q?.kind === "yes_no" ? <select value={c.value || ""} onChange={(e) => onChange({ ...c, value: e.target.value })} aria-label="Value">
            <option value="">choose</option><option value="true">Yes</option><option value="false">No</option></select>
            : <input value={c.value || ""} onChange={(e) => onChange({ ...c, value: e.target.value })} aria-label="Value" />)}
      </>}
    </div>
  );
}

function QuestionEdit({ q, n, earlier, onChange, onRemove, onMove, last }) {
  const set = (k, v) => onChange({ ...q, [k]: v });
  const choice = q.kind === "single" || q.kind === "multi";
  const opts = q.options || [];
  return (
    <div className="survey-question-edit">
      <div className="row-gap">
        <b className="small">{n}.</b>
        <select value={q.kind} onChange={(e) => onChange({ ...q, kind: e.target.value, options: ["single", "multi"].includes(e.target.value)
          ? (opts.length ? opts : [{ value: "1", label: "" }, { value: "2", label: "" }]) : undefined })} aria-label="Kind">
          {Object.entries(KINDS).map(([k, x]) => <option key={k} value={k}>{x}</option>)}</select>
        <label className="row-gap small"><input type="checkbox" checked={!!q.required} onChange={(e) => set("required", e.target.checked)} />required</label>
        {q.element && <span className="badge">scores: {q.element.replaceAll("_", " ")}</span>}
        <span style={{ marginLeft: "auto" }} />
        <button className="linkish" disabled={n === 1} onClick={() => onMove(-1)} aria-label="Move up">▲</button>
        <button className="linkish" disabled={last} onClick={() => onMove(1)} aria-label="Move down">▼</button>
        <button className="linkish" onClick={onRemove}>Remove</button>
      </div>
      <label className="ed-field"><span>Question</span><input value={q.text} onChange={(e) => set("text", e.target.value)} placeholder="What do you want to ask?" /></label>
      <label className="ed-field"><span>Help <span className="quiet">(optional)</span></span><input value={q.help || ""} onChange={(e) => set("help", e.target.value)} /></label>
      {choice && <div className="survey-options">
        {opts.map((o, i) => <div key={o.value} className="row-gap">
          <input value={o.label} onChange={(e) => set("options", opts.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} placeholder={`Option ${i + 1}`} aria-label={`Option ${i + 1}`} style={{ flex: 1 }} />
          <input type="number" value={o.score ?? ""} onChange={(e) => set("options", opts.map((x, j) => (j === i ? { ...x, score: e.target.value === "" ? undefined : Number(e.target.value) } : x)))}
            placeholder="score" aria-label="Score" style={{ width: 70 }} title="Optional: a number for scoring" />
          <button className="linkish" onClick={() => set("options", opts.filter((_x, j) => j !== i))} aria-label="Remove option">✕</button>
          {q.element && <div className="maturity-level-edit">
            <label className="ed-field"><span>Description</span><textarea rows={2} value={o.description || ""}
              onChange={(e) => set("options", opts.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} /></label>
            <label className="ed-field"><span>Examples <span className="quiet">(one a line: what you typically see at this level)</span></span><textarea rows={2}
              value={Array.isArray(o.examples) ? o.examples.join("\n") : (o.examples || "")}
              onChange={(e) => set("options", opts.map((x, j) => (j === i ? { ...x, examples: e.target.value.split("\n") } : x)))} /></label>
          </div>}</div>)}
        <button className="linkish small" onClick={() => set("options", [...opts, { value: newKey("o"), label: "" }])}>＋ Option</button>
        {q.kind === "single" && <label className="row-gap small"><input type="checkbox" checked={!!q.other} onChange={(e) => set("other", e.target.checked)} />allow "Other" with its own text</label>}
      </div>}
      {(q.kind === "rating" || q.kind === "number") && <div className="row-gap small">
        <label>from <input type="number" value={q.min ?? (q.kind === "rating" ? 1 : "")} onChange={(e) => set("min", e.target.value === "" ? undefined : Number(e.target.value))} style={{ width: 70 }} /></label>
        <label>to <input type="number" value={q.max ?? (q.kind === "rating" ? 5 : "")} onChange={(e) => set("max", e.target.value === "" ? undefined : Number(e.target.value))} style={{ width: 70 }} /></label>
        {q.kind === "rating" && <><input value={q.low_label || ""} onChange={(e) => set("low_label", e.target.value)} placeholder="low means…" />
          <input value={q.high_label || ""} onChange={(e) => set("high_label", e.target.value)} placeholder="high means…" /></>}
      </div>}
      <ConditionEdit c={q.condition} earlier={earlier} onChange={(c) => set("condition", c)} what="Ask only when" />
    </div>
  );
}

function SpecView({ spec }) {
  return (spec?.sections || []).map((s) => (
    <div key={s.key} className="survey-section-view">
      <h3>{s.title}{s.condition && <span className="badge"> · shown when an earlier answer fits</span>}</h3>
      <ol>{(s.questions || []).map((q) => <li key={q.key}>{q.text} <span className="badge">{KINDS[q.kind]}{q.required ? ", required" : ""}{q.condition ? ", conditional" : ""}</span>
        {q.options && <span className="small quiet"> — {q.options.map((o) => o.label).join(" · ").slice(0, 300)}</span>}</li>)}</ol>
    </div>));
}

// ---------------------------------------------------------------- answering
const draftKey = (id) => `eax-survey-draft-${id}`;

function AnswerPage({ id }) {
  const url = `/api/v1/surveys/${id}/answer`;
  const { data, error } = useApi(url);
  const [answers, setAnswers] = useState(null);
  const [msg, setMsg] = useState(null);
  const [sent, setSent] = useState(false);
  useEffect(() => {
    if (!data) return;
    let a = data.answers || {};
    if (data.anonymous) { try { a = JSON.parse(localStorage.getItem(draftKey(id)) || "{}"); } catch { a = {}; } }
    setAnswers(a);
  }, [data, id]);
  const shown = useMemo(() => visibleKeys(data?.spec, answers || {}), [data, answers]);
  if (error) return <section><p><a href="#/surveys">‹ Surveys</a></p><p className="status bad">{error}</p></section>;
  if (!data || !answers) return <p className="quiet">Loading...</p>;
  const set = (k, v) => {
    const next = { ...answers, [k]: v };
    setAnswers(next);
    if (data.anonymous) { try { localStorage.setItem(draftKey(id), JSON.stringify(next)); } catch { /* a convenience only */ } }
  };
  // a maturity assessment counts its elements (a level chosen), not its comments and evidence
  const qs = allQuestions(data.spec).filter((q) => shown.has(q.key) && !(data.kind === "maturity" && q.element && q.kind !== "single"));
  const done = qs.filter((q) => answers[q.key] !== undefined && answers[q.key] !== "" && !(Array.isArray(answers[q.key]) && !answers[q.key].length)).length;
  async function save(submit) {
    if (submit && !window.confirm(data.anonymous ? "Send your answers? An anonymous survey is answered once and cannot be changed." : "Send your answers? You can change them until the survey closes.")) return;
    try {
      await apiFetch(url, { method: "PUT", body: JSON.stringify({ answers, submit }) });
      if (submit) { setSent(true); if (data.anonymous) { try { localStorage.removeItem(draftKey(id)); } catch { /* fine */ } } refreshAll(); }
      setMsg({ ok: true, text: submit ? "Thank you: your answers were sent." : "Saved. You can come back to it." });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  }
  const closed = data.status !== "open";
  const readOnly = closed || !data.may_answer || sent;
  return (
    <section className="survey-answer">
      <p><a href="#/surveys">‹ Surveys</a></p>
      <h1>{data.title}</h1>
      {data.description && <p className="survey-intro">{data.description}</p>}
      <p className="small quiet">From {data.owner}{data.closes_at ? ` · closes on ${fmtDate(data.closes_at)}` : ""}
        {data.anonymous ? " · anonymous: your name is not kept with your answers; your draft stays in this browser until you send it" : " · press Save to keep your answers and come back later"}</p>
      {data.preview && <p className="status warn">A preview: this survey has not been sent, so nothing can be sent from here.</p>}
      {closed && !data.preview && <p className="status warn">This survey is closed.</p>}
      {data.anonymous && data.answered && <p className="status ok">You have answered this survey. Thank you.</p>}
      {!data.anonymous && data.response_status === "submitted" && !sent && <p className="status ok">You sent your answers on {fmtDateTime(data.submitted_at)}. You may change them until it closes.</p>}
      <Msg m={msg} />
      <div className="survey-meter" aria-label="Answered so far"><span style={{ width: `${qs.length ? Math.round((100 * done) / qs.length) : 0}%` }} /></div>
      <p className="small quiet">{done} of {qs.length} {data.kind === "maturity" ? "levels chosen" : "questions answered"}</p>
      {data.kind === "maturity" && <fieldset className="survey-section maturity-fieldset" disabled={readOnly && !data.preview}>
        <legend>Your assessment</legend>
        <p className="small quiet">For each element choose the level that fits best today (0 to 5). Open "Levels and examples" to see what each
          level typically looks like. A comment and evidence links are optional unless marked *.</p>
        <MaturityTable spec={data.spec} shown={shown} answers={answers} onChange={set} readOnly={readOnly && !data.preview} />
      </fieldset>}
      {(data.spec.sections || []).map((s) => {
        const items = (s.questions || []).filter((q) => shown.has(q.key) && !(data.kind === "maturity" && q.element));
        if (!items.length) return null;
        return (
          <fieldset key={s.key} className="survey-section" disabled={readOnly && !data.preview}>
            <legend>{s.title}</legend>
            {s.text && <p className="small quiet">{s.text}</p>}
            {items.map((q) => <AnswerField key={q.key} q={q} v={answers[q.key]} onChange={(v) => set(q.key, v)} />)}
          </fieldset>);
      })}
      {!readOnly && <div className="row-gap">
        {!data.anonymous && <button onClick={() => save(false)}>Save</button>}
        <button className="primary" onClick={() => save(true)}>Send my answers</button></div>}
    </section>
  );
}

function AnswerField({ q, v, onChange }) {
  const id = `sq-${q.key}`;
  const head = <span>{q.text}{q.required && <span className="survey-req" title="Required"> *</span>}{q.help && <span className="quiet"> {q.help}</span>}</span>;
  if (q.kind === "single") {
    const known = (q.options || []).some((o) => o.value === v);
    return (
      <div className="ed-field survey-q" role="radiogroup" aria-labelledby={id}><span id={id}>{head}</span>
        {q.options.map((o) => <label key={o.value} className="survey-opt"><input type="radio" name={id} checked={v === o.value} onChange={() => onChange(o.value)} /> {o.label}</label>)}
        {q.other && <label className="survey-opt"><input type="radio" name={id} checked={!!v && !known} onChange={() => onChange(" ")} /> Other:
          <input value={v && !known ? v.trim() : ""} onChange={(e) => onChange(e.target.value || " ")} aria-label="Other" /></label>}
        {v !== undefined && v !== "" && !q.required && <button className="linkish small" onClick={() => onChange("")}>clear</button>}
      </div>);
  }
  if (q.kind === "multi") {
    const vals = Array.isArray(v) ? v : [];
    return (
      <div className="ed-field survey-q"><span>{head}</span>
        {q.options.map((o) => <label key={o.value} className="survey-opt"><input type="checkbox" checked={vals.includes(o.value)}
          onChange={(e) => onChange(e.target.checked ? [...vals, o.value] : vals.filter((x) => x !== o.value))} /> {o.label}</label>)}
      </div>);
  }
  if (q.kind === "yes_no") {
    return (
      <div className="ed-field survey-q" role="radiogroup" aria-labelledby={id}><span id={id}>{head}</span>
        <div className="row-gap"><label className="survey-opt"><input type="radio" name={id} checked={v === true} onChange={() => onChange(true)} /> Yes</label>
          <label className="survey-opt"><input type="radio" name={id} checked={v === false} onChange={() => onChange(false)} /> No</label></div>
      </div>);
  }
  if (q.kind === "rating") {
    const nums = []; for (let i = q.min ?? 1; i <= (q.max ?? 5); i += 1) nums.push(i);
    return (
      <div className="ed-field survey-q" role="radiogroup" aria-labelledby={id}><span id={id}>{head}</span>
        <div className="row-gap survey-rating">{q.low_label && <span className="small quiet">{q.low_label}</span>}
          {nums.map((n) => <button key={n} type="button" className={Number(v) === n ? "primary" : ""} aria-pressed={Number(v) === n} onClick={() => onChange(n)}>{n}</button>)}
          {q.high_label && <span className="small quiet">{q.high_label}</span>}</div>
      </div>);
  }
  if (q.kind === "links") return <div className="ed-field survey-q"><span>{head}</span><LinkEditor id={id} value={v} onChange={onChange} /></div>;
  if (q.kind === "long_text") return <label className="ed-field survey-q">{head}<textarea value={v || ""} onChange={(e) => onChange(e.target.value)} rows={4} /></label>;
  if (q.kind === "number") return <label className="ed-field survey-q">{head}<input type="number" value={v ?? ""} min={q.min} max={q.max} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} /></label>;
  if (q.kind === "date") return <label className="ed-field survey-q">{head}<input type="date" value={v || ""} onChange={(e) => onChange(e.target.value)} /></label>;
  return <label className="ed-field survey-q">{head}<input value={v || ""} onChange={(e) => onChange(e.target.value)} /></label>;
}

// ---------------------------------------------------------------- results
function ResultsPage({ id }) {
  const { data, error } = useApi(`/api/v1/surveys/${id}/results`);
  const [msg, setMsg] = useState(null);
  if (error) return <section><p><a href="#/surveys">‹ Surveys</a></p><p className="status bad">{error}</p></section>;
  if (!data) return <p className="quiet">Loading...</p>;
  async function xlsx() {
    try { await apiDownload(`/api/v1/surveys/${id}/xlsx`, "survey results.xlsx"); } catch (e) { setMsg({ ok: false, text: e.message }); }
  }
  return (
    <section className="survey-results">
      <p><a href="#/surveys">‹ Surveys</a> · <a href={`#/surveys/${id}`}>{data.title}</a>{data.kind === "maturity" && <> · <a href={`#/maturity/${id}`}>Maturity scores</a></>}</p>
      <h1>Results: {data.title} <Status s={data.status} /></h1>
      <Msg m={msg} />
      <Progress p={data.progress} />
      <div className="row-gap"><button onClick={xlsx} disabled={!!data.hidden}>⬇ Excel</button>
        <span className="small quiet">{data.responses} responses{data.anonymous ? " · anonymous" : ""}</span></div>
      {data.hidden && <p className="status warn">{data.hidden}</p>}
      {data.results.map((q) => <ResultBlock key={q.key} q={q} anonymous={data.anonymous} />)}
      {data.people && <>
        <h2>The people asked</h2>
        <table className="grid-table">
          <thead><tr><th>Person</th><th>How</th><th>Asked</th><th>Reminded</th><th>Answered</th></tr></thead>
          <tbody>{data.people.map((p) => <tr key={p.username}><td>{p.username}</td><td className="small">{p.via === "link" ? "by the link" : "asked"}</td>
            <td className="small">{fmtDateTime(p.added_at)}</td><td className="small">{fmtDateTime(p.reminded_at)}</td>
            <td className="small">{p.answered_at ? fmtDateTime(p.answered_at) : p.response === "in_progress" ? "started" : "not yet"}</td></tr>)}</tbody>
        </table></>}
    </section>
  );
}

function ResultBlock({ q, anonymous }) {
  return (
    <div className="survey-result">
      <h3>{q.text} <span className="badge">{KINDS[q.kind]} · {q.answered} of {q.of} answered</span></h3>
      {q.options && <table className="survey-bars"><tbody>{q.options.map((o) => <tr key={String(o.value)}>
        <td className="small">{o.label}</td>
        <td className="survey-bar-cell"><span className="survey-bar" style={{ width: `${o.share}%` }} /></td>
        <td className="num small">{o.count} · {o.share}%</td></tr>)}</tbody></table>}
      {q.mean !== undefined && <p className="small">Mean {q.mean} · median {q.median} · from {q.min} to {q.max}</p>}
      {q.mean_score !== undefined && <p className="small">Mean score {q.mean_score}</p>}
      {q.other?.length > 0 && <p className="small">Other: {q.other.join("; ")}</p>}
      {q.links && <ul className="survey-texts">{q.links.map((a, i) => <li key={i}><LinkList value={a.links} inline />{!anonymous && a.by && <span className="small quiet"> — {a.by}</span>}</li>)}
        {!q.links.length && <li className="quiet">No links.</li>}</ul>}
      {q.answers && <ul className="survey-texts">{q.answers.map((a, i) => <li key={i}>{a.text}{!anonymous && a.by && <span className="small quiet"> — {a.by}</span>}</li>)}
        {!q.answers.length && <li className="quiet">No answers.</li>}</ul>}
    </div>
  );
}

// ---------------------------------------------------------------- EA capability maturity (phase 40)
function MaturityPage() {
  const { data, error } = useApi("/api/v1/maturity");
  const [making, setMaking] = useState(false);
  if (error) return <section><h1>EA capability maturity</h1><p className="status bad">{error}</p></section>;
  if (!data) return <p className="quiet">Loading...</p>;
  return (
    <section className="maturity">
      <p><a href="#/surveys">‹ Surveys</a> · <a href="#/repository">Architecture repository</a></p>
      <h1>EA capability maturity</h1>
      <p className="quiet">How mature the organisation's architecture practice is, by questions and evidence. Each assessment is a survey sent to the people you
        choose: for nine elements they pick the description that fits best today, on six levels from 0 None to 5 Measured. Scores are the mean level per element
        and the weighted mean overall, with the share of answers at or above each level, beside what EA Explorer measures itself.</p>
      <div className="row-gap"><button className="primary" onClick={() => setMaking(!making)}>{making ? "Cancel" : "＋ New assessment"}</button></div>
      {making && <NewAssessment elements={data.elements} />}
      <h2>Assessments</h2>
      <table className="grid-table">
        <thead><tr><th>Assessment</th><th>Status</th><th>Answered</th><th className="num">Overall</th><th>Closed</th><th /></tr></thead>
        <tbody>{data.assessments.map((a) => <tr key={a.id}>
          <td><b>{a.title}</b></td><td><Status s={a.status} /></td>
          <td className="small">{a.progress ? `${a.progress.answered_of_asked} of ${a.progress.asked}` : ""}</td>
          <td className="num">{a.overall ?? ""}</td><td className="small">{fmtDate(a.closed_at)}</td>
          <td><div className="row-gap">{a.status !== "draft" && <a href={`#/maturity/${a.id}`}>Scores</a>}<a href={`#/surveys/${a.id}`}>{a.status === "draft" ? "Edit and send" : "Run"}</a></div></td></tr>)}
          {!data.assessments.length && <tr><td colSpan={6} className="quiet">No assessments yet.</td></tr>}</tbody>
      </table>
      <h2>Trend</h2>
      <Trend trend={data.trend} elements={data.elements} />
      <h2>Evidence EA Explorer measures now</h2>
      <Evidence items={data.evidence} names={Object.fromEntries(data.elements.map((e) => [e.key, e.name]))} />
    </section>
  );
}

function NewAssessment({ elements }) {
  const [d, setD] = useState({ title: "", closes_at: "", remind_every_days: 7, anonymous: false, recipients: [], targets: {}, weights: {} });
  const [msg, setMsg] = useState(null);
  async function make(send) {
    try {
      const r = await apiFetch("/api/v1/maturity", { method: "POST", body: JSON.stringify({ ...d, closes_at: d.closes_at || null, send }) });
      refreshAll(); go(send ? `#/maturity/${r.id}` : `#/surveys/${r.id}`);
    } catch (e) { setMsg({ ok: false, text: e.message }); }
  }
  const num = (k, el, v) => setD({ ...d, [k]: { ...d[k], [el]: v === "" ? undefined : Number(v) } });
  return (
    <div className="ed-form maturity-new">
      <Msg m={msg} />
      <label className="ed-field"><span>Title <span className="quiet">(empty: EA capability maturity and this month)</span></span><input value={d.title} onChange={(e) => setD({ ...d, title: e.target.value })} /></label>
      <div className="row-gap">
        <label className="ed-field"><span>Closes on</span><input type="date" value={d.closes_at} onChange={(e) => setD({ ...d, closes_at: e.target.value })} /></label>
        <label className="ed-field"><span>Remind every (days)</span><input type="number" min="1" max="60" value={d.remind_every_days} onChange={(e) => setD({ ...d, remind_every_days: e.target.value })} /></label>
        <label className="ed-field check"><input type="checkbox" checked={d.anonymous} onChange={(e) => setD({ ...d, anonymous: e.target.checked })} /><span>Anonymous</span></label>
      </div>
      <div><b className="small">Who answers</b>
        <div>{d.recipients.map((r, i) => <span key={i} className="chip">{label(r)} <button className="linkish" onClick={() => setD({ ...d, recipients: d.recipients.filter((_x, j) => j !== i) })} aria-label="Remove">✕</button></span>)}</div>
        <RecipientPicker onPick={(r) => setD({ ...d, recipients: [...d.recipients, r] })} /></div>
      <table className="grid-table maturity-targets">
        <thead><tr><th>Element</th><th>Target level (0 to 5)</th><th>Weight</th></tr></thead>
        <tbody>{elements.map((e) => <tr key={e.key}><td>{e.name}<div className="small quiet">{e.about}</div></td>
          <td><input type="number" min="0" max="5" step="0.5" value={d.targets[e.key] ?? 3} onChange={(x) => num("targets", e.key, x.target.value)} aria-label={`${e.name} target`} style={{ width: 70 }} /></td>
          <td><input type="number" min="0" max="10" step="0.5" value={d.weights[e.key] ?? 1} onChange={(x) => num("weights", e.key, x.target.value)} aria-label={`${e.name} weight`} style={{ width: 70 }} /></td></tr>)}</tbody>
      </table>
      <div className="row-gap"><button onClick={() => make(false)}>Make a draft (change the questions first)</button>
        <button className="primary" disabled={!d.recipients.length} onClick={() => make(true)}>Make it and send it</button></div>
    </div>
  );
}

function Trend({ trend, elements }) {
  if (!trend.length) return <p className="quiet small">The trend shows once an assessment has closed.</p>;
  const W = 640; const H = 180; const P = 30;
  const x = (i) => (trend.length === 1 ? W / 2 : P + (i * (W - 2 * P)) / (trend.length - 1));
  const y = (v) => H - P - ((v || 0) * (H - 2 * P)) / 5;
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="maturity-trend" role="img" aria-label="Overall maturity over the assessments">
        {[0, 1, 2, 3, 4, 5].map((l) => <g key={l}><line x1={P} x2={W - P} y1={y(l)} y2={y(l)} className="grid-line" /><text x={4} y={y(l) + 4} className="axis">{l}</text></g>)}
        <polyline points={trend.map((t, i) => `${x(i)},${y(t.overall)}`).join(" ")} className="trend-line" />
        {trend.map((t, i) => <g key={t.id}><circle cx={x(i)} cy={y(t.overall)} r="4" className="trend-dot"><title>{`${t.title}: ${t.overall}`}</title></circle>
          <text x={x(i)} y={H - 8} textAnchor="middle" className="axis">{fmtDate(t.closed_at)}</text></g>)}
      </svg>
      <table className="grid-table">
        <thead><tr><th>Element</th>{trend.map((t) => <th key={t.id} className="num">{fmtDate(t.closed_at)}</th>)}</tr></thead>
        <tbody>{elements.map((e) => <tr key={e.key}><td>{e.name}</td>{trend.map((t) => <td key={t.id} className="num">{t.elements[e.key] ?? ""}</td>)}</tr>)}
          <tr><th>Overall</th>{trend.map((t) => <th key={t.id} className="num">{t.overall ?? ""}</th>)}</tr></tbody>
      </table>
    </>
  );
}

function Evidence({ items, names }) {
  return (
    <div className="maturity-evidence">
      {(items || []).map((e) => <div key={e.key} className="maturity-ev">
        <div className="small quiet">{e.name}</div><div className="maturity-ev-value">{e.value}</div>
        <div className="small">{e.note}</div>
        <div className="small quiet">Speaks to: {(e.elements || []).map((k) => names[k] || k).join(", ")}</div></div>)}
    </div>
  );
}

// ---------------------------------------------------------------- the assessment as one table, with live 0 to 5 bars (D456)
// colours by level (never colour alone: the level's number and name are always written beside the bar)
export const LEVEL_COLOURS = ["#8a94a3", "#b4532a", "#b98900", "#2f6fc4", "#127a72", "#1f7a3a"];
const levelName = (v) => ["None", "Initial", "Under development", "Defined", "Managed", "Measured"][Math.max(0, Math.min(5, Math.floor(v)))];

export function LevelBar({ value, target, previous, label }) {
  const has = value !== null && value !== undefined && value !== "";
  const v = has ? Number(value) : 0;
  const pct = (x) => `${(Math.max(0, Math.min(5, Number(x))) * 100) / 5}%`;
  const text = has ? `${label || "Level"} ${v} of 5 (${levelName(v)})` : "Not answered";
  return (
    <div className="lvl-bar" role="img" aria-label={`${text}${target !== undefined && target !== null ? `, target ${target}` : ""}${previous !== undefined && previous !== null ? `, before ${previous}` : ""}`}>
      <div className="lvl-track">
        {has && <span className="lvl-fill" style={{ width: pct(v), background: LEVEL_COLOURS[Math.floor(Math.min(v, 5))] }} />}
        {previous !== undefined && previous !== null && <span className="lvl-prev" style={{ left: pct(previous) }} title={`Before: ${previous}`} />}
        {target !== undefined && target !== null && <span className="lvl-target" style={{ left: pct(target) }} title={`Target: ${target}`} />}
      </div>
      <div className="lvl-ticks" aria-hidden="true">{[0, 1, 2, 3, 4, 5].map((t) => <span key={t} style={{ left: pct(t) }}>{t}</span>)}</div>
    </div>
  );
}

// the element rows of a maturity assessment: level, comment and evidence questions grouped by element
function elementRows(spec) {
  return (spec?.sections || []).map((s) => {
    const qs = (s.questions || []).filter((q) => q.element);
    const level = qs.find((q) => q.kind === "single");
    if (!level) return null;
    return { key: level.element, title: s.title, about: s.text, level, comment: qs.find((q) => q.kind === "long_text" || q.kind === "text"),
      evidence: qs.find((q) => q.kind === "links") };
  }).filter(Boolean);
}

function LevelsDetail({ q, chosen }) {
  return (
    <ol className="lvl-detail" start={0}>
      {(q.options || []).map((o) => <li key={o.value} className={String(chosen) === o.value ? "on" : ""}>
        <span className="lvl-chip" style={{ background: LEVEL_COLOURS[Math.min(5, Math.max(0, Math.floor(o.score ?? 0)))] }}>{o.score ?? o.value}</span>
        <b>{o.label.replace(/^\d+\s*/, "")}</b>{o.description && <> — {o.description}</>}
        {o.examples?.length > 0 && <ul className="lvl-examples">{o.examples.map((x, i) => <li key={i}>{x}</li>)}</ul>}
      </li>)}
    </ol>
  );
}

function MaturityTable({ spec, shown, answers, onChange, readOnly }) {
  const [open, setOpen] = useState({});
  const rows = elementRows(spec).filter((r) => shown.has(r.level.key));
  const scoreOf = (q, v) => q.options.find((o) => o.value === v)?.score;
  return (
    <table className="grid-table maturity-table">
      <thead><tr><th style={{ width: "22%" }}>Element</th><th style={{ width: "26%" }}>Levels and examples</th><th>Your response</th><th style={{ width: "20%" }}>Level 0 to 5</th></tr></thead>
      <tbody>{rows.map((r) => {
        const v = answers[r.level.key];
        const chosen = r.level.options.find((o) => o.value === v);
        return (
          <tr key={r.key}>
            <td><b>{r.title}</b>{r.level.required && <span className="survey-req" title="Required"> *</span>}{r.about && <div className="small quiet">{r.about}</div>}</td>
            <td>
              {chosen ? <div className="small"><b>{chosen.label}</b>{chosen.description && <>: {chosen.description}</>}</div> : <div className="small quiet">Not chosen yet</div>}
              <button type="button" className="linkish small" aria-expanded={!!open[r.key]} onClick={() => setOpen({ ...open, [r.key]: !open[r.key] })}>
                {open[r.key] ? "Hide levels and examples ▴" : "Levels and examples ▾"}</button>
              {open[r.key] && <LevelsDetail q={r.level} chosen={v} />}
            </td>
            <td>
              <div className="lvl-pick" role="radiogroup" aria-label={`${r.title}: level`}>
                {r.level.options.map((o) => <button key={o.value} type="button" role="radio" aria-checked={v === o.value} disabled={readOnly}
                  className={v === o.value ? "on" : ""} style={v === o.value ? { background: LEVEL_COLOURS[Math.min(5, Math.floor(o.score ?? 0))], borderColor: LEVEL_COLOURS[Math.min(5, Math.floor(o.score ?? 0))] } : undefined}
                  title={`${o.label}${o.description ? `: ${o.description}` : ""}${o.examples?.length ? `\nFor example: ${o.examples.join("; ")}` : ""}`}
                  onClick={() => onChange(r.level.key, v === o.value && !r.level.required ? "" : o.value)}>{o.score ?? o.value}</button>)}
              </div>
              {r.comment && shown.has(r.comment.key) && <textarea className="lvl-comment" rows={2} disabled={readOnly} value={answers[r.comment.key] || ""}
                placeholder={`Comment${r.comment.required ? " (required)" : " (optional)"}: why this level, or what is missing`} aria-label={`${r.title}: comment`}
                onChange={(e) => onChange(r.comment.key, e.target.value)} />}
              {r.evidence && shown.has(r.evidence.key) && <div className="lvl-evidence"><span className="small quiet">Evidence{r.evidence.required ? " (required)" : ""}</span>
                <LinkEditor id={`ev-${r.key}`} value={answers[r.evidence.key]} onChange={(x) => onChange(r.evidence.key, x)} /></div>}
            </td>
            <td><LevelBar value={v === undefined || v === "" ? null : scoreOf(r.level, v)} />
              <div className="small">{chosen ? chosen.label : <span className="quiet">not chosen</span>}</div></td>
          </tr>);
      })}</tbody>
    </table>
  );
}

function MaturityResult({ id }) {
  const { data, error } = useApi(`/api/v1/maturity/${id}`);
  const [open, setOpen] = useState({});
  const [person, setPerson] = useState("");
  if (error) return <section><p><a href="#/maturity">‹ Maturity</a></p><p className="status bad">{error}</p></section>;
  if (!data) return <p className="quiet">Loading...</p>;
  const sc = data.scores;
  const names = Object.fromEntries(sc.elements.map((e) => [e.element, e.name]));
  const rows = elementRows(data.spec);
  const byEl = Object.fromEntries(sc.elements.map((e) => [e.element, e]));
  const resp = (data.respondents || []).find((r) => r.who === person) || null;
  const answered = (data.people || []).filter((p) => p.answered_at);
  const waiting = (data.people || []).filter((p) => !p.answered_at);
  return (
    <section className="maturity">
      <p><a href="#/maturity">‹ Maturity assessments</a> · <a href={`#/surveys/${id}`}>Run it</a> · <a href={`#/surveys/${id}/results`}>Answers by question</a></p>
      <h1>{data.title} <Status s={data.status} /></h1>
      <Progress p={data.progress} />
      {!data.hidden && <p><button onClick={() => apiDownload(`/api/v1/surveys/${id}/xlsx`, "maturity.xlsx").catch(() => {})}>⬇ Excel: scores, levels and examples, every response</button></p>}
      <p className="small">Answered: {answered.map((p) => p.username).join(", ") || "nobody yet"}{waiting.length > 0 && <span className="quiet"> · not yet: {waiting.map((p) => p.username).join(", ")}</span>}
        {data.anonymous && <span className="quiet"> · anonymous: answers are not joined to these names</span>}</p>
      {data.hidden ? <p className="status warn">{data.hidden}</p> : <>
        <p className="small quiet">The final score: per element the mean of everyone's levels, its target and gap; overall the mean weighted by the elements' weights.
          Shown to Super Admins only. <span className="lvl-key"><span className="lvl-target-key" /> target <span className="lvl-prev-key" /> {data.previous ? data.previous.title : "previous"}</span></p>
        <table className="grid-table maturity-table">
          <thead><tr><th style={{ width: "20%" }}>Element</th><th style={{ width: "26%" }}>Levels and examples</th><th>Responses</th><th style={{ width: "24%" }}>Mean level 0 to 5</th></tr></thead>
          <tbody>{rows.map((r) => {
            const e = byEl[r.key] || {};
            return (
              <tr key={r.key}>
                <td><b>{r.title}</b><div className="small quiet">weight {e.weight}</div></td>
                <td><button type="button" className="linkish small" aria-expanded={!!open[r.key]} onClick={() => setOpen({ ...open, [r.key]: !open[r.key] })}>
                  {open[r.key] ? "Hide levels and examples ▴" : "Levels and examples ▾"}</button>{open[r.key] && <LevelsDetail q={r.level} />}</td>
                <td className="small">
                  <div><b className="maturity-mean">{e.mean ?? "–"}</b> {e.level && <span>{e.level}</span>} · {e.answers} answers</div>
                  <div>Target {e.target}{e.gap > 0 ? <span className="maturity-gap"> · gap {e.gap}</span> : e.gap === 0 ? " · target met" : ""}
                    {data.previous && data.previous.elements[r.key] !== undefined && <span className="quiet"> · before {data.previous.elements[r.key]}</span>}</div>
                  <div className="lvl-spread" aria-label="Answers at each level">{[0, 1, 2, 3, 4, 5].map((l) => <span key={l} title={`Level ${l}: ${e.spread?.[String(l)] || 0}`}
                    style={{ background: (e.spread?.[String(l)] || 0) ? LEVEL_COLOURS[l] : "#eef1f4", color: (e.spread?.[String(l)] || 0) ? "#fff" : "#8a94a3" }}>{l}:{e.spread?.[String(l)] || 0}</span>)}</div>
                </td>
                <td><LevelBar value={e.mean} target={e.target} previous={data.previous?.elements[r.key]} label="Mean" /></td>
              </tr>);
          })}
            <tr className="maturity-total"><td><b>Overall</b><div className="small quiet">weighted mean of {sc.responses} responses</div></td><td />
              <td><b className="maturity-mean">{sc.overall ?? "–"}</b> {sc.overall_level}{data.previous && <span className="small quiet"> · before {data.previous.overall}</span>}</td>
              <td><LevelBar value={sc.overall} previous={data.previous?.overall} label="Overall" /></td></tr>
          </tbody>
        </table>
        <details className="maturity-share"><summary>Share of answers at or above each level (the second scoring method)</summary>
          <table className="grid-table"><thead><tr><th>Element</th>{[1, 2, 3, 4, 5].map((l) => <th key={l} className="num">≥{l}</th>)}</tr></thead>
            <tbody>{sc.elements.map((e) => <tr key={e.element}><td>{e.name}</td>{[1, 2, 3, 4, 5].map((l) => <td key={l} className="num small maturity-heat"
              style={{ background: `rgba(31,122,58,${(e.at_or_above[String(l)] || 0) / 160})` }}>{e.at_or_above[String(l)]}%</td>)}</tr>)}</tbody></table>
        </details>
        <h2>Each person's answers</h2>
        <div className="row-gap"><select value={person} onChange={(e) => setPerson(e.target.value)} aria-label="Person">
          <option value="">Choose a person</option>{(data.respondents || []).map((r) => <option key={r.who} value={r.who}>{r.who}</option>)}</select>
          {resp && <span className="small quiet">sent {fmtDateTime(resp.submitted_at)}</span>}</div>
        {resp && <table className="grid-table maturity-table">
          <thead><tr><th style={{ width: "20%" }}>Element</th><th style={{ width: "20%" }}>Value</th><th>Comment</th><th>Evidence</th></tr></thead>
          <tbody>{rows.map((r) => {
            const x = resp.elements[r.key] || {};
            return <tr key={r.key}><td>{r.title}</td>
              <td><LevelBar value={x.level ? x.level.score : null} /><div className="small">{x.level?.label || "not answered"}</div></td>
              <td className="small">{x.comment || <span className="quiet">—</span>}</td>
              <td className="small"><LinkList value={x.evidence} empty={<span className="quiet">—</span>} /></td></tr>;
          })}</tbody></table>}
      </>}
      <h2>Evidence {data.evidence_at ? <span className="small quiet">kept when it closed, {fmtDateTime(data.evidence_at)}</span> : <span className="small quiet">now</span>}</h2>
      <Evidence items={data.evidence} names={names} />
    </section>
  );
}
