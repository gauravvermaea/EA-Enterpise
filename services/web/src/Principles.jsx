// Architecture principles, shown properly (R2.48, D607; owner, 12 Nov 2026: "architecture principles and how show them
// current UI is not great"). The owner chose, one question at a time:
//   one principle    a TOGAF card: its name and code, the statement, the rationale and the implications; its area; where
//                    it comes from (enforced or optional from the organisation, inherited, the library, the project's own);
//                    what it refines and what refines it; the dispensations raised against it (governance log)
//   the set          cards grouped by area (Business, Data, Application, Technology, Security...), in a grid; search,
//                    an area and a "from" filter, and Expand all for the rationale and implications
//   where            an organisation page (Repository › Architecture principles, #/principles, for everyone; the
//                    Organisation base's principles) and each project's Principles tab, with the same cards
//   editing          on the card itself: Edit turns the card into its fields; Add puts a new card at the top; From the
//                    library adds one in the library's words; an enforced or inherited one is read only, and Refine it
//                    makes the project's own version under it
// The data and the rules are those of D327 (eax/project_work.py): a base's principle is enforced or optional below it;
// a library one keeps its words (its area and what it refines can change); a project's own is changed by contributors.
import { useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import RichText from "./RichText";
import { Field, Modal } from "./ModelOps";

const richOrPlain = (v) => (/^\s*</.test(v || "") ? <div className="rich-view" dangerouslySetInnerHTML={{ __html: v }} />
  : <div style={{ whiteSpace: "pre-line" }}>{v}</div>);
const asHtml = (v) => (/^\s*</.test(v || "") ? v : v ? `<p>${v.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>")}</p>` : "");
const empty = (v) => !String(v || "").replace(/<[^>]*>/g, "").trim();

// where a principle comes from, as a short chip and its class
function source(r, isBase) {
  if (isBase) return r.mandatory ? ["🔒 Enforced below", "enforced"] : ["Optional below", "optional"];
  if (r.from_base && r.mandatory) return ["🔒 Enforced by the organisation", "enforced"];
  if (r.from_base) return ["Optional, from the organisation", "optional"];
  if (r.inherited_from) return [`Inherited from ${r.inherited_from}`, "inherited"];
  if (r.library_id) return ["From the library", "library"];
  return ["The project's own", "own"];
}
const FROM = [["", "From anywhere"], ["enforced", "Enforced"], ["optional", "Optional"], ["own", "Own"], ["library", "Library"], ["inherited", "Inherited"]];

export function PrinciplesTab({ p }) {
  const isBase = !!p.base_kind;
  const can = p.may_contribute && !p.frozen;
  const all = p.principles || [];
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");
  const [area, setArea] = useState("");
  const [from, setFrom] = useState("");
  const [open, setOpen] = useState(false);             // Expand all: the rationale and implications of every card
  const [editing, setEditing] = useState(null);        // a principle's id, or {new: {area, refines}}
  const [lib, setLib] = useState(false);
  const { data: gov } = useApi(isBase ? null : `/api/v1/projects/${p.id}/governance`);
  const byKey = useMemo(() => {
    const m = {};
    for (const r of all) { if (r.guid) m[r.guid] = r; if (r.origin_guid) m[r.origin_guid] = r; }
    return m;
  }, [all]);
  const parentOf = (r) => (r.refines && byKey[r.refines] && byKey[r.refines] !== r ? byKey[r.refines] : null);
  const childrenOf = (r) => all.filter((k) => parentOf(k) === r);
  const dispensations = (r) => (gov?.records || gov?.items || gov?.rows || []).filter((g) => g.principle && (g.principle === r.guid || g.principle === r.origin_guid));
  const locked = (r) => !!r.inherited_from || (!isBase && r.from_base && r.mandatory);
  const term = q.trim().toLowerCase();
  const shown = all.filter((r) => (!area || (r.area || "") === area) && (!from || source(r, isBase)[1] === from)
    && (!term || `${r.name} ${r.code} ${r.area} ${r.statement} ${r.rationale} ${r.implications}`.toLowerCase().includes(term)));
  const areas = [...new Set([...(p.principle_area_list || []), ...all.map((r) => r.area || "")])]
    .sort((x, y) => (x || "~").localeCompare(y || "~"));
  const listed = areas.filter((a) => (!area || a === area) && (shown.some((r) => (r.area || "") === a) || (!term && !from && can)));

  async function call(url, opts) {
    try { const out = await apiFetch(url, opts); setMsg(out.message || ""); refreshAll(); return true; } catch (e) { setMsg(e.message); return false; }
  }
  function remove(r) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Take the principle ${r.name} out of the ${isBase ? "base" : "project"}?`)) return;
    call(`/api/v1/projects/${p.id}/principles/${r.id}`, { method: "DELETE" });
  }
  function addArea() {
    // eslint-disable-next-line no-alert
    const n = window.prompt("The new area's name (e.g. Business, Security, Data, AI)");
    if (n && n.trim()) call(`/api/v1/projects/${p.id}/principle-areas`, { method: "POST", body: JSON.stringify({ name: n }) });
  }
  const jump = (r) => document.getElementById(`principle-${r.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });

  const card = (r) => {
    if (editing === r.id) return <PrincipleEditor key={r.id} p={p} r={r} onDone={(m) => { setEditing(null); if (m) setMsg(m); }} />;
    const [label, kind] = source(r, isBase);
    const parent = parentOf(r);
    const kids = childrenOf(r);
    const disp = dispensations(r);
    return (
      <article key={r.id} id={`principle-${r.id}`} className={`principle-card from-${kind}`} aria-label={`Principle ${r.name}`}>
        <header>
          <div className="principle-chips">
            {r.code && <span className="chip small">{r.code}</span>}
            <span className={`chip small principle-from ${kind}`}>{label}</span>
          </div>
          <h4>{r.name}</h4>
          {parent && <p className="small quiet">Refines <button className="linkish" onClick={() => jump(parent)}>{parent.name}</button>
            {(parent.area || "") !== (r.area || "") ? ` (${parent.area || "Other"})` : ""}</p>}
        </header>
        <section className="principle-statement">
          <h5>Statement</h5>
          {empty(r.statement) ? <p className="small quiet">No statement yet.</p> : richOrPlain(r.statement)}
        </section>
        {[["rationale", "Rationale"], ["implications", "Implications"]].map(([k, l]) => (
          <details key={`${k}-${open}`} open={open} className="principle-part">
            <summary>{l}{empty(r[k]) ? <span className="small quiet"> (none yet)</span> : null}</summary>
            {!empty(r[k]) && richOrPlain(r[k])}
          </details>
        ))}
        {(kids.length > 0 || disp.length > 0) && <p className="small principle-links">
          {kids.length > 0 && <>Refined by {kids.map((k, i) => <span key={k.id}>{i ? ", " : ""}<button className="linkish" onClick={() => jump(k)}>{k.name}</button></span>)}</>}
          {kids.length > 0 && disp.length > 0 && " · "}
          {disp.length > 0 && <a href={`#/projects/${p.id}/governance?kind=Dispensation`}>
            {disp.length} dispensation{disp.length === 1 ? "" : "s"}</a>}</p>}
        {can && <footer className="small">
          {!locked(r) && <button className="linkish" onClick={() => setEditing(r.id)}>Edit</button>}
          {!locked(r) && isBase && p.is_super && <> · <button className="linkish" onClick={() => call(`/api/v1/projects/${p.id}/principles/${r.id}`,
            { method: "PUT", body: JSON.stringify({ mandatory: !r.mandatory }) })}>{r.mandatory ? "Make optional" : "Enforce"}</button></>}
          {!locked(r) && <> · <button className="linkish" onClick={() => remove(r)}>Take out</button> · </>}
          <button className="linkish" onClick={() => setEditing({ new: { area: r.area || "", refines: r.origin_guid || r.guid } })}>＋ Refine it</button>
          {locked(r) && <span className="quiet"> · read only here{r.from_base ? ": ask for a dispensation in the governance log" : ""}</span>}
        </footer>}
      </article>
    );
  };

  return (
    <div className="principles">
      <p className="quiet">{isBase
        ? "The organisation's architecture principles, by area. Enforced ones (🔒) are in every project below and cannot be taken out there; optional ones come to every new project, which may take them out."
        : "The principles this project works to, by area. Those the organisation enforces are locked (🔒: ask for a dispensation in the governance log); optional ones may be taken out; the project adds its own and may refine any of them."}</p>
      {msg && <p className="small status">{msg}</p>}
      <div className="row-gap filters">
        {can && <button className="primary" onClick={() => setEditing({ new: { area } })}>＋ Add a principle</button>}
        {can && <button onClick={() => setLib(true)}>＋ From the library</button>}
        {can && <button onClick={addArea}>＋ Add an area</button>}
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search principles" aria-label="Search principles" />
        <select value={area} onChange={(e) => setArea(e.target.value)} aria-label="Area">
          <option value="">Every area</option>{areas.map((a) => <option key={a || "~"} value={a}>{a || "Other"}</option>)}</select>
        <select value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From">
          {FROM.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <button className="linkish" onClick={() => setOpen(!open)}>{open ? "Collapse all" : "Expand all"}</button>
        <span className="small quiet">{shown.length === all.length ? `${all.length} principles` : `${shown.length} of ${all.length}`}</span>
      </div>
      {editing?.new && <div className="principle-cards"><PrincipleEditor p={p} r={editing.new} onDone={(m) => { setEditing(null); if (m) setMsg(m); }} /></div>}
      {!all.length && !areas.length && <p className="quiet">No principles yet.</p>}
      {all.length > 0 && !shown.length && <p className="quiet">Nothing matches.</p>}
      {listed.map((a) => {
        const here = shown.filter((r) => (r.area || "") === a);
        // a refining principle follows the one it refines
        const order = [];
        const seen = new Set();
        const put = (r) => { if (seen.has(r.id)) return; seen.add(r.id); order.push(r); childrenOf(r).filter((k) => here.includes(k)).forEach(put); };
        here.filter((r) => !parentOf(r) || !here.includes(parentOf(r))).forEach(put);
        here.forEach(put);
        return (
          <section key={a || "~"} className="principle-area">
            <h3>{a || "Other"} <span className="small quiet">{here.length}</span>
              {can && <button className="linkish small" onClick={() => setEditing({ new: { area: a } })}>＋ add here</button>}
              {can && !all.some((r) => (r.area || "") === a) && a && <button className="linkish small"
                onClick={() => call(`/api/v1/projects/${p.id}/principle-areas`, { method: "POST", body: JSON.stringify({ name: a, remove: true }) })}>remove the area</button>}</h3>
            {here.length ? <div className="principle-cards">{order.map(card)}</div> : <p className="small quiet">No principles in this area yet.</p>}
          </section>
        );
      })}
      {lib && <LibraryPicker p={p} have={all} onClose={(m) => { setLib(false); if (m) setMsg(m); }} />}
    </div>
  );
}

// a principle's fields, on its card (owner: "Edit on the card"); r without an id is a new one ({area, refines})
function PrincipleEditor({ p, r, onDone }) {
  const fromLib = !!r.library_id;
  const [f, setF] = useState({ name: r.name || "", area: r.area || "", code: r.code || "", statement: r.statement || "",
    rationale: r.rationale || "", implications: r.implications || "", refines: r.refines || "",
    ...(p.base_kind && !r.id ? { mandatory: true } : {}) });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const others = (p.principles || []).filter((x) => x.id !== r.id);
  async function save() {
    setErr(""); setBusy(true);
    try {
      const out = await apiFetch(r.id ? `/api/v1/projects/${p.id}/principles/${r.id}` : `/api/v1/projects/${p.id}/principles`,
        { method: r.id ? "PUT" : "POST", body: JSON.stringify(fromLib ? { area: f.area, refines: f.refines } : f) });
      refreshAll(); onDone(out.message);
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <article className="principle-card editing" aria-label={r.id ? `Editing ${r.name}` : "A new principle"}>
      <div className="ed-form">
        {fromLib && <p className="small quiet">From the library: it keeps its words; its area and what it refines can change.</p>}
        <Field label="Name"><input value={f.name} disabled={fromLib} onChange={(e) => set("name", e.target.value)} autoFocus /></Field>
        <div className="row-gap">
          <Field label="Area"><input list="principle-areas" value={f.area} onChange={(e) => set("area", e.target.value)} placeholder="Business, Data, Security..." />
            <datalist id="principle-areas">{(p.principle_areas || []).map((a) => <option key={a} value={a} />)}</datalist></Field>
          <Field label="Code" hint="(optional)"><input value={f.code} disabled={fromLib} onChange={(e) => set("code", e.target.value)} size={8} /></Field>
        </div>
        <Field label="Refines" hint="(optional)">
          <select value={f.refines} onChange={(e) => set("refines", e.target.value)}>
            <option value="">nothing: a top-level principle</option>
            {others.map((x) => <option key={x.id} value={x.origin_guid || x.guid}>{x.area ? `${x.area}: ` : ""}{x.name}</option>)}</select></Field>
        {p.base_kind && !r.id && <label className="small"><input type="checkbox" checked={!!f.mandatory} onChange={(e) => set("mandatory", e.target.checked)} />
          {" "}Enforced in every project below (otherwise optional: a project may take it out)</label>}
        {fromLib ? richOrPlain(f.statement) : <>
          <Field label="Statement"><RichText value={asHtml(f.statement)} onChange={(v) => set("statement", v)} placeholder="What the principle says" /></Field>
          <Field label="Rationale"><RichText value={asHtml(f.rationale)} onChange={(v) => set("rationale", v)} placeholder="Why it matters" /></Field>
          <Field label="Implications"><RichText value={asHtml(f.implications)} onChange={(v) => set("implications", v)} placeholder="What it means in practice" /></Field>
        </>}
        {err && <p className="status bad">{err}</p>}
        <div className="row-gap"><button className="primary" disabled={busy || !f.name.trim()} onClick={save}>Save</button>
          <button onClick={() => onDone()}>Cancel</button></div>
      </div>
    </article>
  );
}

// the principles library (TOGAF's and the organisation's sets), to add one in its own words
function LibraryPicker({ p, have, onClose }) {
  const { data, error } = useApi("/api/v1/projects/library");
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const taken = new Set(have.map((r) => r.library_id).filter(Boolean));
  const list = (data?.principles || []).filter((x) => !q.trim() || `${x.name} ${x.code} ${x.category} ${x.set_name}`.toLowerCase().includes(q.trim().toLowerCase()));
  async function add(x) {
    setErr("");
    try { const out = await apiFetch(`/api/v1/projects/${p.id}/principles`, { method: "POST", body: JSON.stringify({ library_id: x.id }) }); refreshAll(); onClose(out.message); }
    catch (e) { setErr(e.message); }
  }
  return (
    <Modal wide title="Add a principle from the library" onClose={() => onClose()} actions={<button onClick={() => onClose()}>Close</button>}>
      {(error || err) && <p className="status bad">{error || err}</p>}
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the library" aria-label="Search the library" autoFocus />
      {!data ? <p className="quiet">Loading...</p> : !list.length ? <p className="quiet">Nothing matches.</p> : (
        <div className="principle-cards">{list.map((x) => (
          <article key={x.id} className="principle-card from-library">
            <header><div className="principle-chips">{x.code && <span className="chip small">{x.code}</span>}
              <span className="chip small">{[x.set_name, x.category].filter(Boolean).join(" · ")}</span></div><h4>{x.name}</h4></header>
            <section className="principle-statement">{richOrPlain(x.statement)}</section>
            <footer className="small">{taken.has(x.id) ? <span className="quiet">In this {p.base_kind ? "base" : "project"} already</span>
              : <button className="linkish" onClick={() => add(x)}>＋ Add</button>}</footer>
          </article>))}</div>)}
    </Modal>
  );
}

// Repository › Architecture principles (#/principles): the organisation's principles for everyone, the same cards; Super
// Admins change them here (the Organisation base)
export function PrinciplesPage() {
  const { data: sum, error: e1 } = useApi("/api/v1/repository/summary");
  const { data: p, error } = useApi(sum?.org_base ? `/api/v1/projects/${sum.org_base.id}` : null);
  return (
    <div className="page">
      <h1>Architecture principles</h1>
      {(e1 || error) && <p className="status bad">{e1 || error}</p>}
      {sum && !sum.org_base && <p className="quiet">There is no Organisation base yet: its principles show here once it is made.</p>}
      {!p ? (!(e1 || error) && <p className="quiet">Loading...</p>) : <>
        <p className="small">The organisation's principles, kept in the <a href={`#/projects/${p.id}/principles`}>Organisation base</a>
          {p.may_contribute ? "" : "; Super Admins change them"}. Each project shows them on its own Principles tab with its own.</p>
        <PrinciplesTab p={p} />
      </>}
    </div>
  );
}
