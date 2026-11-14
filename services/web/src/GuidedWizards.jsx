// The guided wizards of phase 16.3 (D339): each a few steps over screens and data EA Explorer already has.
//   QualityWizard      WIZ-021/022  fix what data quality finds, one entity at a time: fill in, not applicable, still correct
//   ComplianceWizard   WIZ-019      review a solution against the project's principles and standards; the result in the log
//   MigrationWizard    WIZ-017      gaps into work packages (Work Package entities) and a roadmap sheet in a project
//   CollectWizard      WIZ-018      ask people to fill in entity types; their uploads come back as commit requests
//   LoadDataWizard     WIZ-013      download the sheet, fill it in, upload it and check the preview
//   FirstRunPanel      UI-009       a new installation's essentials, once, for the first Super Admin
import { useEffect, useMemo, useState } from "react";
import { apiFetch, can, canOn, myInfo } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Field, Modal } from "./ModelOps";
import { Download, Upload } from "./Sheets";
import { liveProjects } from "./ModelMarks";

const post = (path, body, method = "POST") => apiFetch(path, { method, body: JSON.stringify(body || {}) });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export function Steps({ names, at }) {
  return <ol className="wiz-steps">{names.map((n, i) => <li key={n} className={i === at ? "on" : i < at ? "done" : ""}>{n}</li>)}</ol>;
}

// ---------------------------------------------------------------- WIZ-021/022 data quality and staleness
const KINDS = [
  ["incomplete", "Missing values", "Fields and values that count towards data quality are empty"],
  ["rule", "Broken rules", "Values that break the model's data quality rules"],
  ["stale", "Not checked for a long time", "Not changed or confirmed within the model's stale period"],
  ["orphan", "Connected to nothing", "Entities with no relationship at all"],
];

export function QualityWizard({ m, onClose }) {
  // measured now, so the wizard works on the model as it is (D339)
  const { data: d, error } = useApi(`/api/v1/models/${m.id}/quality?fresh=true`);
  const [step, setStep] = useState(0);
  const [kinds, setKinds] = useState(["incomplete", "stale"]);
  const [onlyImportant, setOnlyImportant] = useState(false);
  const [mine, setMine] = useState(false);
  const [type, setType] = useState("");
  const [at, setAt] = useState(0);
  const [log, setLog] = useState([]);
  const me = (myInfo()?.username || "").toLowerCase();
  const admin = !!d?.may_manage;
  const findings = d?.findings || [];
  const types = [...new Set(findings.map((f) => f.type_name))].sort();
  const queue = useMemo(() => {
    const pick = findings.filter((f) => kinds.includes(f.kind) && (!onlyImportant || f.kind !== "incomplete" || f.important)
      && (!type || f.type_name === type) && (!mine || (f.responsible || []).includes(me)));
    const by = new Map();
    for (const f of pick) { if (!by.has(f.entity)) by.set(f.entity, { ...f, findings: [] }); by.get(f.entity).findings.push(f); }
    return [...by.values()];
  }, [d, kinds, onlyImportant, type, mine]);
  const done = (what) => { setLog((l) => [...l, what]); setAt((n) => n + 1); };
  if (error) return <Modal title="Data quality" onClose={onClose}><p className="status bad">{error}</p></Modal>;
  if (!d) return <Modal title="Data quality" onClose={onClose}><p className="quiet">Measuring {m.name} now…</p></Modal>;
  const cur = queue[at];
  const names = ["What to fix", "One entity at a time", "Done"];
  return (
    <Modal wide title={`Improve the data quality of ${m.name}`} onClose={onClose}
      actions={step === 0 ? <><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={!queue.length} onClick={() => setStep(1)}>Start with {queue.length} entit{queue.length === 1 ? "y" : "ies"}</button></>
        : step === 1 ? <><button onClick={() => setStep(2)}>Stop here</button></> : <button className="primary" onClick={() => { refreshAll(); onClose(); }}>Close</button>}>
      <Steps names={names} at={step} />
      {step === 0 && <div className="ed-form">
        <p className="quiet small">Measured now: score {d.summary?.score}%, {d.summary?.incomplete} incomplete, {d.summary?.failing} failing a rule,
          {" "}{d.summary?.stale} stale, {d.summary?.orphans} connected to nothing.</p>
        {!queue.length && <p className="status ok">Nothing to work through with these choices.</p>}
        <fieldset className="form-section"><legend>What to work through</legend>
          {KINDS.map(([k, l, help]) => <label key={k} className="type-choice" title={help}>
            <input type="checkbox" checked={kinds.includes(k)} onChange={(e) => setKinds(e.target.checked ? [...kinds, k] : kinds.filter((x) => x !== k))} />
            {" "}{l} <span className="quiet small">{findings.filter((f) => f.kind === k).length}</span></label>)}
        </fieldset>
        <Field label="Entity type"><select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Every type</option>{types.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <label className="small"><input type="checkbox" checked={onlyImportant} onChange={(e) => setOnlyImportant(e.target.checked)} /> Only the important missing values</label>
        <label className="small"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Only the entities I am responsible for</label>
      </div>}
      {step === 1 && (cur ? <QualityEntity key={cur.entity} m={m} d={d} e={cur} admin={admin} n={at + 1} of={queue.length} onDone={done} />
        : <p>That was the last one. <button className="linkish" onClick={() => setStep(2)}>See what was done</button></p>)}
      {step === 2 && <div>
        <p><b>{log.filter((x) => x !== "skipped").length}</b> entities improved, {log.filter((x) => x === "skipped").length} skipped.</p>
        <p className="quiet small">Changes you typed in are your uncommitted changes in {m.name}: commit them (or ask for them to be committed) on its
          Changes tab. Data quality is measured again within minutes, or now from the Quality tab.</p>
      </div>}
    </Modal>
  );
}

function QualityEntity({ m, d, e, admin, n, of, onDone }) {
  const [vals, setVals] = useState({});
  const [why, setWhy] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: form } = useApi(`/api/v1/models/${m.id}/forms/${encodeURIComponent(e.type)}`);
  const attr = (item) => (form?.attributes || []).find((a) => `attr:${a.code}` === item);
  const label = (item) => (d.items?.[e.type]?.items || []).find((x) => x.item === item)?.label || item.split(":")[1];
  // each field as data entry shows it: a pick list as a drop-down, a date as a date, a number as a number
  const input = (item) => {
    const a = attr(item);
    const v = vals[item] || "";
    const on = (x) => setVals({ ...vals, [item]: x.target.value });
    if (item === "field:description") return <textarea rows={2} value={v} onChange={on} />;
    if (a?.pick_list_values?.length) return <select value={v} onChange={on}><option value="">Choose…</option>{a.pick_list_values.map((p) => <option key={p}>{p}</option>)}</select>;
    if (a?.data_type === "boolean") return <select value={v} onChange={on}><option value="">Choose…</option><option value="true">Yes</option><option value="false">No</option></select>;
    const type = { date: "date", integer: "number", decimal: "number", currency: "number", percent: "number", email: "email" }[a?.data_type] || "text";
    return <input type={type} value={v} onChange={on} placeholder={a?.unit || a?.description || ""} />;
  };
  const missing = e.findings.filter((f) => f.kind === "incomplete" && !f.item.startsWith("rel:"));
  const stale = e.findings.some((f) => f.kind === "stale");
  async function act(fn, what) {
    setBusy(true); setMsg("");
    try { await fn(); onDone(what); } catch (x) { setMsg(x.message); }
    setBusy(false);
  }
  const save = () => act(async () => {
    const body = { values: {} };
    for (const [item, v] of Object.entries(vals)) {
      if (!String(v).trim()) continue;
      if (item === "field:description") body.description = v; else body.values[item.split(":")[1]] = v;
    }
    if (!body.description && !Object.keys(body.values).length) throw new Error("Type a value, or choose another way below.");
    if (!Object.keys(body.values).length) delete body.values;
    await post(`/api/v1/models/${m.id}/content/entities/${e.entity}`, body, "PATCH");
  }, "filled");
  const notApplicable = () => act(async () => {
    if (!why.trim()) throw new Error("Say why they do not apply.");
    for (const f of missing) await post(`/api/v1/models/${m.id}/quality/not-applicable`, { entity: e.entity, item: f.item, reason: why });
  }, "not applicable");
  const current = () => act(() => post(`/api/v1/models/${m.id}/quality/seal`, { entities: [e.entity], kind: admin ? "current" : "seal",
    note: "Confirmed in the data quality wizard" }), "still correct");
  return (
    <div className="ed-form">
      <p className="small quiet">{n} of {of}</p>
      <h3>{e.name} <span className="small quiet">{e.type_name}{e.display_id ? ` · ${e.display_id}` : ""}{e.owner ? ` · owner ${e.owner}` : ""}</span>
        {" "}<a className="small" href={`#/metamodel/${m.id}/entity/${e.entity}`} target="_blank" rel="noreferrer">open it ↗</a></h3>
      <ul className="small">{e.findings.map((f, i) => <li key={i}>{f.message}</li>)}</ul>
      {missing.length > 0 && <fieldset className="form-section"><legend>Fill in</legend>
        {missing.map((f) => <Field key={f.item} label={label(f.item)} hint={f.important ? "(important)" : ""}>{input(f.item)}</Field>)}
        <p className="quiet small">Fill in what you know; empty fields stay as they are.</p>
        <button className="primary" disabled={busy} onClick={save}>Save and next</button>
        <div className="row-gap" style={{ marginTop: 8 }}>
          <input placeholder="Why these do not apply to this entity" value={why} onChange={(x) => setWhy(x.target.value)} style={{ minWidth: 300 }} />
          <button disabled={busy} onClick={notApplicable}>Not applicable here</button></div>
        <p className="quiet small">Not applicable needs a Model Admin's approval (theirs applies at once).</p>
      </fieldset>}
      {e.findings.some((f) => f.kind === "rule" || f.kind === "orphan" || f.item?.startsWith("rel:")) &&
        <p className="small">Rules and relationships are fixed on the entity itself: <a href={`#/metamodel/${m.id}/entity/${e.entity}`} target="_blank" rel="noreferrer">open it ↗</a>, then Next.</p>}
      <div className="row-gap">
        {stale && <button disabled={busy} onClick={current} title={admin ? "Marked still current (Model Admin)" : "Attested as correct (the person responsible)"}>Still correct</button>}
        <button disabled={busy} onClick={() => onDone("skipped")}>Next (skip)</button>
      </div>
      {msg && <p className="status bad">{msg}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- WIZ-019 architecture compliance review
const VERDICTS = ["Complies", "Partly", "Does not comply", "Not applicable"];

export function ComplianceWizard({ p, onClose }) {
  const { data: std } = useApi(`/api/v1/projects/${p.id}/standards`);
  const [step, setStep] = useState(0);
  const [subject, setSubject] = useState("");
  const [scope, setScope] = useState("");
  const [owner, setOwner] = useState("");
  const [rows, setRows] = useState({});
  const [dispense, setDispense] = useState({});
  const [msg, setMsg] = useState("");
  const [done, setDone] = useState(null);
  const items = useMemo(() => [
    ...(p.principles || []).map((r) => ({ key: `p:${r.id}`, kind: "Principle", id: r.guid, name: r.name, area: r.area || "", statement: r.statement })),
    ...((std?.standards || []).filter((s) => s.status !== "Retired")).map((s) => ({ key: `s:${s.id}`, kind: "Standard", id: s.id, name: s.name, area: s.area || "" })),
  ], [p, std]);
  const set = (k, f, v) => setRows((r) => ({ ...r, [k]: { ...(r[k] || {}), [f]: v } }));
  const answered = items.filter((i) => rows[i.key]?.verdict);
  const fails = items.filter((i) => rows[i.key]?.verdict === "Does not comply");
  const partly = items.filter((i) => rows[i.key]?.verdict === "Partly");
  const result = fails.length ? "Not compliant" : partly.length ? "Compliant with conditions" : "Compliant";
  async function record() {
    setMsg("");
    try {
      const table = `<table><thead><tr><th>Kind</th><th>Area</th><th>Principle or standard</th><th>Verdict</th><th>Notes</th></tr></thead><tbody>${
        answered.map((i) => `<tr><td>${i.kind}</td><td>${esc(i.area)}</td><td>${esc(i.name)}</td><td>${esc(rows[i.key].verdict)}</td><td>${esc(rows[i.key].note || "")}</td></tr>`).join("")}</tbody></table>`;
      const html = `<p><b>${esc(subject)}</b>${scope ? `: ${esc(scope)}` : ""}</p><p>Result: <b>${result}</b> (${answered.length} of ${items.length} reviewed; `
        + `${fails.length} not met, ${partly.length} partly).</p>${table}`;
      const out = await post(`/api/v1/projects/${p.id}/governance`, { kind: "Compliance assessment", title: `Compliance review: ${subject}`, html, status: result, owner });
      let n = 0;
      for (const i of fails.filter((x) => dispense[x.key])) {
        await post(`/api/v1/projects/${p.id}/governance`, { kind: "Dispensation", title: `${subject}: ${i.name}`, owner,
          html: `<p>${esc(subject)} does not comply with the ${i.kind.toLowerCase()} <b>${esc(i.name)}</b>.</p><p>${esc(rows[i.key].note || "")}</p><p>From the compliance review ${out.ref}.</p>`,
          ...(i.kind === "Principle" ? { principle: i.id } : { standard: i.id }) });
        n += 1;
      }
      setDone({ ref: out.ref, n }); setStep(3); refreshAll();
    } catch (e) { setMsg(e.message); }
  }
  const names = ["What is reviewed", "Principles and standards", "Result", "Recorded"];
  return (
    <Modal wide title={`Architecture compliance review in ${p.name}`} onClose={onClose}
      actions={step === 3 ? <button className="primary" onClick={onClose}>Close</button> : <>
        {step > 0 && <button onClick={() => setStep(step - 1)}>Back</button>}
        {step < 2 && <button className="primary" disabled={step === 0 ? !subject.trim() || !items.length : !answered.length} onClick={() => setStep(step + 1)}>Next</button>}
        {step === 2 && <button className="primary" onClick={record}>Record it in the governance log</button>}</>}>
      <Steps names={names} at={step} />
      {step === 0 && <div className="ed-form">
        <Field label="The solution or change reviewed"><input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="For example: Claims portal release 2" autoFocus /></Field>
        <Field label="What was looked at" hint="(optional)"><textarea rows={3} value={scope} onChange={(e) => setScope(e.target.value)} placeholder="Design documents, the solution architecture, the models…" /></Field>
        <Field label="Owner" hint="(optional: who answers for the solution)"><input value={owner} onChange={(e) => setOwner(e.target.value)} /></Field>
        {std && !items.length ? <p className="status bad">{p.name} has no principles or standards to review against: add them on its Principles and
          Standards tabs (or take them from its base, on the Base tab).</p>
          : <p className="quiet small">Next: each of the project's {items.length} principles and standards, with a verdict and a note.</p>}
      </div>}
      {step === 1 && <div>
        <p className="quiet small">{answered.length} of {items.length} answered. Leave out what was not looked at.</p>
        <table className="grid-table small"><thead><tr><th>Kind</th><th>Principle or standard</th><th>Verdict</th><th>Notes</th></tr></thead>
          <tbody>{items.map((i) => <tr key={i.key}><td>{i.kind}<div className="quiet">{i.area}</div></td><td><b>{i.name}</b></td>
            <td><select value={rows[i.key]?.verdict || ""} onChange={(e) => set(i.key, "verdict", e.target.value)}>
              <option value="">not reviewed</option>{VERDICTS.map((v) => <option key={v}>{v}</option>)}</select></td>
            <td><input value={rows[i.key]?.note || ""} onChange={(e) => set(i.key, "note", e.target.value)} style={{ width: "100%" }} /></td></tr>)}</tbody></table>
      </div>}
      {step === 2 && <div className="ed-form">
        <p>Result: <b>{result}</b>: {answered.length} reviewed, {fails.length} not met, {partly.length} partly met.</p>
        {fails.length > 0 && <fieldset className="form-section"><legend>Ask for a dispensation for what is not met</legend>
          {fails.map((i) => <label key={i.key} className="type-choice"><input type="checkbox" checked={!!dispense[i.key]}
            onChange={(e) => setDispense({ ...dispense, [i.key]: e.target.checked })} /> {i.kind}: {i.name}</label>)}</fieldset>}
        <p className="quiet small">The review is logged as a Compliance assessment with its table (a draft: send it for approval from the governance log);
          each dispensation is logged as its own record, pointing at its principle or standard.</p>
        {msg && <p className="status bad">{msg}</p>}
      </div>}
      {step === 3 && done && <p>Logged as <b>{done.ref}</b>{done.n ? ` with ${done.n} dispensation request${done.n === 1 ? "" : "s"}` : ""}.
        {" "}<a href={`#/projects/${p.id}/governance?kind=Compliance%20assessment`} onClick={onClose}>Open the governance log</a></p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- WIZ-017 a migration plan from gaps
export function MigrationWizard({ m, onClose }) {
  const { data: list } = useApi(`/api/v1/gaps?model=${m.id}`);
  const { data: projects_ } = useApi("/api/v1/projects");
  const projects = projects_ && { ...projects_, projects: liveProjects(projects_.projects) };   // never a frozen project (D360)
  const [analysis, setAnalysis] = useState("");
  const [by, setBy] = useState("domain");
  const { data: sug } = useApi(analysis ? `/api/v1/gaps/${analysis}/migration-plan?by=${by}` : null);
  const [pk, setPk] = useState(null);
  const [step, setStep] = useState(0);
  const [project, setProject] = useState("");
  const [msg, setMsg] = useState("");
  const [out, setOut] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (sug) setPk(sug.packages); }, [sug]);
  const gapName = Object.fromEntries((sug?.gaps || []).map((x) => [x.id, x]));
  const where = {};
  (pk || []).forEach((p, i) => p.gaps.forEach((gid) => { where[gid] = i; }));
  const setP = (i, f, v) => setPk(pk.map((p, j) => (j === i ? { ...p, [f]: v } : p)));
  const moveGap = (gid, to) => setPk(pk.map((p, j) => ({ ...p, gaps: j === to ? [...new Set([...p.gaps, gid])] : p.gaps.filter((x) => x !== gid) })));
  async function make() {
    setBusy(true); setMsg("");
    try {
      const r = await post(`/api/v1/gaps/${analysis}/migration-plan`, { packages: pk.filter((p) => p.gaps.length), project: project || null });
      setOut(r); setStep(3); refreshAll();
    } catch (e) { setMsg(e.message); }
    setBusy(false);
  }
  const names = ["The gap analysis", "Work packages", "Where it goes", "Done"];
  const analyses = list?.analyses || [];
  return (
    <Modal wide title={`A migration plan in ${m.name}`} onClose={onClose}
      actions={step === 3 ? <button className="primary" onClick={onClose}>Close</button> : <>
        {step > 0 && <button onClick={() => setStep(step - 1)}>Back</button>}
        {step < 2 && <button className="primary" disabled={step === 0 ? !analysis || !pk?.length : !pk?.some((p) => p.gaps.length && p.name.trim())}
          onClick={() => setStep(step + 1)}>Next</button>}
        {step === 2 && <button className="primary" disabled={busy} onClick={make}>{busy ? "Making…" : "Make the work packages"}</button>}</>}>
      <Steps names={names} at={step} />
      {step === 0 && <div className="ed-form">
        {list && !analyses.length && <p>{m.name} holds no gap analysis yet: make one first (Compare › Gap analysis).</p>}
        <Field label="Gap analysis"><select value={analysis} onChange={(e) => setAnalysis(e.target.value)}>
          <option value="">Choose…</option>{analyses.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
        <Field label="First grouping" hint="(you change it on the next step)"><select value={by} onChange={(e) => setBy(e.target.value)}>
          <option value="domain">One work package per domain</option><option value="type">Per entity type</option>
          <option value="resolution">Per resolution (Build, Buy, Retire…)</option><option value="each">One per gap</option></select></Field>
        {sug && <p className="quiet small">{sug.gaps.length} gaps without a work package{sug.already ? `; ${sug.already} are in one already` : ""}.</p>}
      </div>}
      {step === 1 && pk && <div>
        <p className="quiet small">Rename, date and order the packages; move a gap with its drop-down. A package with no gaps is left out.</p>
        {pk.map((p, i) => <fieldset key={i} className="form-section"><legend>Work package {i + 1}</legend>
          <div className="row-gap">
            <input value={p.name} onChange={(e) => setP(i, "name", e.target.value)} style={{ minWidth: 280 }} />
            <label className="small">Wave <input value={p.wave} onChange={(e) => setP(i, "wave", e.target.value)} style={{ width: 60 }} /></label>
            <label className="small">From <input type="date" value={p.start} onChange={(e) => setP(i, "start", e.target.value)} /></label>
            <label className="small">to <input type="date" value={p.end} onChange={(e) => setP(i, "end", e.target.value)} /></label>
            <select value={p.resolution} onChange={(e) => setP(i, "resolution", e.target.value)}><option value="">resolution…</option>
              {(sug?.resolutions || []).map((r) => <option key={r}>{r}</option>)}</select></div>
          <ul className="small">{p.gaps.map((gid) => <li key={gid}>{gapName[gid]?.name} <span className="quiet">({gapName[gid]?.status}, {gapName[gid]?.type})</span>
            {" "}<select className="small" value={i} onChange={(e) => moveGap(gid, Number(e.target.value))}>
              {pk.map((q, j) => <option key={j} value={j}>{j === i ? "here" : `→ ${q.name || `package ${j + 1}`}`}</option>)}</select></li>)}</ul>
        </fieldset>)}
        <button onClick={() => setPk([...pk, { name: `New work package ${pk.length + 1}`, wave: "", start: "", end: "", resolution: "", gaps: [] }])}>＋ A work package</button>
        {Object.keys(gapName).filter((gid) => where[gid] === undefined).length > 0 &&
          <p className="small quiet">Not in a package: {Object.keys(gapName).filter((gid) => where[gid] === undefined).map((gid) => gapName[gid].name).join(", ")}</p>}
      </div>}
      {step === 2 && <div className="ed-form">
        <p>{pk.filter((p) => p.gaps.length).length} Work Package entities are made in <b>{m.name}</b> and committed at once (Model Admins), each linked to
          the elements its gaps are about; each gap points at its work package, and gets its package's resolution when it has none.</p>
        <Field label="The roadmap as a tracking sheet in a project" hint="(optional)"><select value={project} onChange={(e) => setProject(e.target.value)}>
          <option value="">No sheet</option>{(projects?.projects || []).filter((x) => x.status === "active").map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        {msg && <p className="status bad">{msg}</p>}
      </div>}
      {step === 3 && out && <div><p className="status ok">{out.note}</p>
        {out.failed?.length > 0 && <p className="status bad">Not made: {out.failed.map((f) => `${f.what}: ${f.error}`).join("; ")}</p>}
        {out.sheet && <p><a href={`#/projects/${out.sheet.project}/sheets`} onClick={onClose}>Open the roadmap sheet</a></p>}</div>}
    </Modal>
  );
}

// ---------------------------------------------------------------- WIZ-018 collect data from people
export function CollectWizard({ m, onClose }) {
  const { data: t } = useApi(`/api/v1/models/${m.id}/sheets`);
  const { data: ppl } = useApi(`/api/v1/models/${m.id}/collect`);
  const [step, setStep] = useState(0);
  const [types, setTypes] = useState([]);
  const [who, setWho] = useState([]);
  const [note, setNote] = useState("");
  const [due, setDue] = useState("");
  const [msg, setMsg] = useState("");
  const [out, setOut] = useState(null);
  async function send() {
    setMsg("");
    try { setOut(await post(`/api/v1/models/${m.id}/collect`, { types, people: who, note, due })); setStep(3); } catch (e) { setMsg(e.message); }
  }
  const names = ["What to fill in", "Who", "The request", "Sent"];
  const people = ppl?.people || [];
  return (
    <Modal wide title={`Collect data for ${m.name}`} onClose={onClose}
      actions={step === 3 ? <button className="primary" onClick={onClose}>Close</button> : <>
        {step > 0 && <button onClick={() => setStep(step - 1)}>Back</button>}
        {step < 2 && <button className="primary" disabled={step === 0 ? !types.length : !who.length} onClick={() => setStep(step + 1)}>Next</button>}
        {step === 2 && <button className="primary" onClick={send}>Send the request</button>}</>}>
      <Steps names={names} at={step} />
      {step === 0 && <div>
        <p className="quiet small">The entity types the people fill in: each gets the sheet with these types, holding what is there now.</p>
        <div className="type-domains">{(t?.types || []).map((x) => <label key={x.code} className="type-choice">
          <input type="checkbox" checked={types.includes(x.code)} onChange={(e) => setTypes(e.target.checked ? [...types, x.code] : types.filter((c) => c !== x.code))} />
          {" "}{x.name} <span className="quiet small">{x.domain} · {x.entities}</span></label>)}</div>
      </div>}
      {step === 1 && <div>
        <p className="quiet small">People with a role on {m.name}. Only those whose role changes its content can load a sheet; give others access first
          (Model admin › Hand over, or the model's People tab).</p>
        {people.map((p) => <label key={p.username} className="type-choice" style={{ opacity: p.may_load ? 1 : 0.55 }}>
          <input type="checkbox" disabled={!p.may_load} checked={who.includes(p.username)}
            onChange={(e) => setWho(e.target.checked ? [...who, p.username] : who.filter((u) => u !== p.username))} />
          {" "}{p.username} <span className="quiet small">{p.roles.join(", ")}{p.may_load ? "" : " · cannot load"}</span></label>)}
      </div>}
      {step === 2 && <div className="ed-form">
        <Field label="A note for them" hint="(optional)"><textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <Field label="By" hint="(optional)"><input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
        <p className="quiet small">Each person gets a request in their bell with a link to the sheet. What they upload becomes their changes: they ask for them
          to be committed, and you review them on the Changes tab as any commit request.</p>
        {msg && <p className="status bad">{msg}</p>}
      </div>}
      {step === 3 && out && <div><p className="status ok">{out.message}</p>
        {out.skipped?.length > 0 && <ul className="small">{out.skipped.map((s) => <li key={s.username}>{s.username}: {s.why}</li>)}</ul>}</div>}
    </Modal>
  );
}

// ---------------------------------------------------------------- WIZ-013 load data into a model
export function LoadDataWizard({ m, onClose }) {
  const [step, setStep] = useState(0);
  const may = canOn(m.id, "model.content");
  const names = ["How it works", "Download the sheet", "Upload it"];
  return (
    <Modal wide title={`Load data into ${m.name}`} onClose={onClose}
      actions={<>{step > 0 && <button onClick={() => setStep(step - 1)}>Back</button>}
        {step < 2 ? <button className="primary" onClick={() => setStep(step + 1)}>Next</button> : <button onClick={onClose}>Close</button>}</>}>
      <Steps names={names} at={step} />
      {step === 0 && <div>
        <ol>
          <li>Choose the entity types and download a workbook: one sheet per type, holding what is there now, and a sheet of relationships.</li>
          <li>Fill it in: change values, add rows (a new row needs no ID), mark rows to delete. A sheet from another system works too: you map its columns.</li>
          <li>Upload it: you see a preview first (new, changed, unchanged, to delete, problems) and correct rows there.</li>
          <li>Add the rows: they become <b>your uncommitted changes</b>, which you commit (or ask to be committed) on the Changes tab.</li>
        </ol>
        {!may && <p className="status bad">Loading needs a role that changes the content of {m.name}.</p>}
      </div>}
      {step === 1 && <Download model={m.id} m={m} />}
      {step === 2 && <><Upload model={m.id} m={m} may={may} />
        <p className="quiet small">After the upload the preview opens: check it, then add the rows.</p></>}
    </Modal>
  );
}

// ---------------------------------------------------------------- UI-009 the first-run setup
export function FirstRunPanel({ always = false }) {
  const { data, error } = useApi(can("settings.manage") ? "/api/v1/admin/first-run" : null);
  const [st, setSt] = useState(null);
  const [msg, setMsg] = useState("");
  const d = st || data;
  if (error || !d || (!always && !d.show)) return null;
  const mark = async (body) => { try { setSt(await post("/api/v1/admin/first-run", body)); } catch (e) { setMsg(e.message); } };
  return (
    <section className="first-run">
      <h2>Set up this installation <span className="small quiet">{d.done} of {d.total} done</span></h2>
      <p className="quiet small">Once, for the first Super Admin: the essentials, each on its own screen. A step is ticked when the installation shows it done,
        or when you mark it.</p>
      <ol className="first-run-steps">
        {d.steps.map((s) => <li key={s.key} className={s.done ? "done" : ""}>
          <span aria-hidden="true">{s.done ? "✓" : "○"}</span> <b>{s.label}</b> <span className="small quiet">{s.why}</span>
          {" "}<a href={s.link} className="small">Open</a>
          {!s.seen && <> · <button className="linkish small" onClick={() => mark({ step: s.key, done: !s.marked })}>{s.marked ? "Not done yet" : "Mark done"}</button></>}
        </li>)}
      </ol>
      <div className="row-gap">
        {!d.finished ? <button className="primary" onClick={() => mark({ finished: true })}>Finished: put this away</button>
          : <button onClick={() => mark({ finished: false })}>Show it on the start page again</button>}
      </div>
      {msg && <p className="status bad">{msg}</p>}
    </section>
  );
}
