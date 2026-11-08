// Phase 13.1 (owner, 8 Nov 2026, D303 to D307): a project's Base tab (what it derives from and what its base offers),
// Standards (by area, mandatory ones from the base locked), Governance log (a tab per kind of record, kinds of one's
// own), Architecture charter (sections, approve); and Project admin's hierarchy of project bases.
import { Suspense, useMemo, useState } from "react";
import ProjectTree, { flatten } from "./ProjectTree";
import { apiFetch, apiUpload } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import RichText from "./RichText";
import { Field, Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";

const BASE_LABEL = { empty: "Empty project", togaf: "TOGAF 10 project", org: "Organisation base" };
const rich = (v) => (v ? <div className="rich-view" dangerouslySetInnerHTML={{ __html: v }} /> : <span className="quiet">–</span>);

function useAct(setMsg) {
  return async (fn) => {
    try { const r = await fn(); setMsg({ ok: true, text: r?.message || "Done." }); refreshAll(); return true; }
    catch (e) { setMsg({ ok: false, text: e.message }); return false; }
  };
}
const Msg = ({ m }) => (m.text ? <p className={`status ${m.ok ? "ok" : "bad"}`}>{m.text}</p> : null);

// ---------------------------------------------------------------- the banner on a base's page
export function BaseBanner({ p }) {
  if (p.base_kind === "empty" || p.base_kind === "togaf") {
    return <div className="lock-banner">🔒 {p.name} is a project base: read-only for everyone. Every project derives from it through the Organisation base.</div>;
  }
  if (p.base_kind === "org") {
    return <div className="lock-banner">🏛 The Organisation base: its steps, principles, standards and charter are offered to every project below it.
      Only Super Admins change it.</div>;
  }
  if (p.base_offers > 0) {
    return <div className="lock-banner small">{p.base_offers} item{p.base_offers === 1 ? "" : "s"} from {p.base_chain?.[0]?.name || "the base"} not taken yet:{" "}
      <a href={`#/projects/${p.id}/base`}>see the Base tab</a>.</div>;
  }
  return null;
}

// ---------------------------------------------------------------- Base tab
export function BaseTab({ p }) {
  const url = `/api/v1/projects/${p.id}/base`;
  const { data, error } = useApi(url);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const [newBase, setNewBase] = useState("");
  const act = useAct(setMsg);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const post = (body) => act(() => apiFetch(url, { method: "POST", body: JSON.stringify(body) }));
  const KIND = { principle: "Principles", standard: "Standards", step: "Steps" };
  return (
    <div>
      <p className="quiet">What this project derives from. A base's principles and standards bind the projects below it (mandatory); its steps and
        charter are where a project starts. When a base changes, what is new or changed is offered here to take or skip (mandatory items cannot be skipped).</p>
      <Msg m={msg} />
      {/* the chain drawn as the hierarchy (owner, 8 Nov 2026): this project under the bases above it */}
      <ProjectTree items={data.chain.map((c, i) => ({ id: c.id, name: c.name, kind: c.base_kind || (c.is_library ? "library" : "project"),
        up: data.chain[i + 1]?.id || null }))} focus={p.id} height={200} />
      <div className="base-chain" style={{ marginTop: 8 }}>
        {[...data.chain].reverse().map((c, i) => (
          <span key={c.id} className="row-gap">{i > 0 && <span className="quiet">›</span>}
            {c.id === p.id ? <b>{c.name}</b> : <a href={`#/projects/${c.id}`}>{c.name}</a>}
            {c.base_kind && <span className="chip small">base</span>}{c.is_library && <span className="chip small">library</span>}</span>
        ))}
      </div>
      {data.may_rebase && (
        <div className="row-gap small" style={{ marginTop: 8 }}>
          <span>Derive from</span>
          <select value={newBase} onChange={(e) => setNewBase(e.target.value)} aria-label="Derive from">
            <option value="">choose a base or library project…</option>
            {data.bases.filter((b) => b.id !== p.id).map((b) => <option key={b.id} value={b.id}>{b.name}{b.base_kind ? "" : " (library project)"}</option>)}
          </select>
          <button disabled={!newBase} onClick={() => post({ base: newBase })}>Change (Super Admin)</button>
        </div>
      )}
      <h3>Offered from {data.base?.name || "the base"}</h3>
      {!data.offers.length ? <p className="quiet">Nothing new: the project has everything its base holds{data.base ? "" : " (it has no base)"}.</p> : (
        <>
          {data.may_take && <p><button className="primary" onClick={() => post({ kind: "*", id: "*", take: true })}>Take everything ({data.offers.length})</button></p>}
          {Object.keys(KIND).map((k) => {
            const xs = data.offers.filter((o) => o.kind === k);
            if (!xs.length) return null;
            return (
              <section key={k}>
                <h4>{KIND[k]} <span className="quiet small">{xs.length}</span>
                  {data.may_take && <button className="linkish small" onClick={() => post({ kind: k, id: "*", take: true })}> take all {KIND[k].toLowerCase()}</button>}</h4>
                <table className="grid-table small">
                  <thead><tr><th>{k === "step" ? "Phase" : "Area"}</th><th>Name</th><th>What</th><th /></tr></thead>
                  <tbody>{xs.map((o) => (
                    <tr key={o.id}>
                      <td>{o.area}</td><td><b>{o.name}</b>{o.mandatory && <span title="Mandatory below the base"> 🔒</span>}</td>
                      <td>{o.action === "add" ? "new in the base" : `changed in the base (${(o.changed || []).join(", ") || "mandatory"})`}</td>
                      <td className="nowrap">{data.may_take && <>
                        <button className="linkish" onClick={() => post({ kind: o.kind, id: o.id, take: true })}>Take</button>
                        {!o.mandatory && <> · <button className="linkish" onClick={() => post({ kind: o.kind, id: o.id, take: false })}>Skip</button></>}</>}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </section>
            );
          })}
          {!data.may_take && <p className="small quiet">A Project Admin or Lead Architect takes or skips these.</p>}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- Standards tab
export function StandardsTab({ p }) {
  const url = `/api/v1/projects/${p.id}/standards`;
  const { data, error } = useApi(url);
  const [dlg, setDlg] = useState(null);
  const [q, setQ] = useState("");
  // opened on one group, or on the external ones, from the repository map (D324): ?group=Business | ?external=1
  const [group, setGroup] = useState(() => decodeURIComponent((window.location.hash.match(/[?&]group=([^&]+)/) || [])[1] || ""));
  const [ext, setExt] = useState(() => /[?&]external=1/.test(window.location.hash));
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const act = useAct(setMsg);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const can = data.may_edit && !p.frozen;
  const shown = data.standards.filter((s) => (!q.trim() || `${s.name} ${s.source} ${s.area}`.toLowerCase().includes(q.trim().toLowerCase()))
    && (!group || (s.area || "Other").toLowerCase() === group.toLowerCase()) && (!ext || /external|iso|open group|ieee|nist|w3c|ietf/i.test(s.source || "")));
  const areas = [...new Set([...data.areas, ...shown.map((s) => s.area || "Other")])].filter((a) => shown.some((s) => (s.area || "Other") === a));
  const locked = (s) => s.mandatory && s.from_base && data.locked_from_base;
  return (
    <div>
      <p className="quiet">The standards this project follows, by area: business, data, application, technology, security, and any group of your own.
        Those from the project's base are mandatory (🔒): a project that cannot follow one asks for a dispensation in its governance log.</p>
      <Msg m={msg} />
      <div className="row-gap filters">
        {can && <button className="primary" onClick={() => setDlg({})}>＋ Add a standard</button>}
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search standards" aria-label="Search standards" />
        <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Group"><option value="">Every group</option>
          {[...new Set([...data.areas, ...data.standards.map((s) => s.area || "Other")])].map((a) => <option key={a} value={a}>{a}</option>)}</select>
        <label className="small"><input type="checkbox" checked={ext} onChange={(e) => setExt(e.target.checked)} /> external only</label>
        <span className="small quiet">{data.standards.length} standards</span>
      </div>
      {!shown.length && <p className="quiet">{data.standards.length ? "Nothing matches." : "No standards yet."}</p>}
      {areas.map((a) => (
        <section key={a} className="principle-area">
          <h3>{a} <span className="small quiet">{shown.filter((s) => (s.area || "Other") === a).length}</span></h3>
          <table className="grid-table">
            <thead><tr><th>Standard</th><th>Description</th><th>Status</th><th>Source</th><th>From</th>{can && <th />}</tr></thead>
            <tbody>{shown.filter((s) => (s.area || "Other") === a).map((s) => (
              <tr key={s.id}>
                <td><b>{s.name}</b></td><td className="small">{rich(s.description)}</td>
                <td><span className={`chip small std-${s.status.toLowerCase()}`}>{s.status}</span></td><td className="small">{s.source}</td>
                <td className="small">{s.from_base && s.mandatory ? "🔒 mandatory, from the base" : "the project's own"}</td>
                {can && <td className="small nowrap">{!locked(s) && <><button className="linkish" onClick={() => setDlg(s)}>Change</button> ·{" "}
                  <button className="linkish" onClick={() => act(() => apiFetch(`${url}/${s.id}`, { method: "DELETE" }))}>Take out</button></>}</td>}
              </tr>
            ))}</tbody>
          </table>
        </section>
      ))}
      {dlg && <StandardDialog url={url} data={data} s={dlg} onClose={(m) => { setDlg(null); if (m) setMsg({ ok: true, text: m }); }} />}
    </div>
  );
}

function StandardDialog({ url, data, s, onClose }) {
  const [f, setF] = useState({ area: s.area || "", name: s.name || "", description: s.description || "", status: s.status || "Active", source: s.source || "" });
  const [err, setErr] = useState("");
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  async function save() {
    try { const r = await apiFetch(s.id ? `${url}/${s.id}` : url, { method: s.id ? "PUT" : "POST", body: JSON.stringify(f) }); refreshAll(); onClose(r.message); }
    catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={s.id ? `Change ${s.name}` : "Add a standard"} onClose={() => onClose()} wide
      actions={<><button onClick={() => onClose()}>Cancel</button><button className="primary" disabled={!f.name.trim()} onClick={save}>Save</button></>}>
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        <Field label="Area" hint="(Business, Data, Application, Technology, Security, or a new group)">
          <input list="std-areas" value={f.area} onChange={(e) => set("area", e.target.value)} />
          <datalist id="std-areas">{data.areas.map((a) => <option key={a} value={a} />)}</datalist></Field>
        <Field label="Name"><input value={f.name} onChange={(e) => set("name", e.target.value)} autoFocus /></Field>
        <div className="row-gap">
          <Field label="Status"><select value={f.status} onChange={(e) => set("status", e.target.value)}>{data.statuses.map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Source"><input value={f.source} onChange={(e) => set("source", e.target.value)} placeholder="e.g. ISO, NIST, Organisation" /></Field>
        </div>
        <Field label="Description"><RichText value={f.description} onChange={(v) => set("description", v)} placeholder="What it requires, where it applies" /></Field>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- Governance log tab
export function GovernanceTab({ p }) {
  const url = `/api/v1/projects/${p.id}/governance`;
  const { data, error } = useApi(url);
  // opened on one kind from the repository map (D318): #/projects/<p>/governance?kind=Decision
  const [kind, setKind] = useState(() => decodeURIComponent((window.location.hash.match(/[?&]kind=([^&]+)/) || [])[1] || "*"));
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [dlg, setDlg] = useState(null);
  const [newKind, setNewKind] = useState(null);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const act = useAct(setMsg);
  const recs = useMemo(() => (data?.records || []).filter((r) => (kind === "*" || r.kind === kind) && (!status || r.status === status)
    && (!q.trim() || `${r.ref} ${r.title} ${r.owner} ${r.related}`.toLowerCase().includes(q.trim().toLowerCase()))), [data, kind, status, q]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const can = data.may_edit && !p.frozen;
  const k = data.kinds.find((x) => x.name === kind);
  return (
    <div>
      <p className="quiet">The project's governance log: decisions, dispensations, compliance assessments, risks and issues, and any kind of record
        the project adds. Each kind has its own tab. Every record needs approval: send it to the project's sign-off people
        ({(data.signers || []).join(", ") || "none set yet"}{data.quorum ? `; ${data.quorum} must approve` : ""}), or approve it with evidence or a reason.</p>
      {data.records.some((r) => r.request?.mine) && <p className="status warn">Waiting for your approval: {data.records.filter((r) => r.request?.mine).map((r) =>
        <button key={r.id} className="linkish" onClick={() => setDlg(r)}>{r.ref} </button>)}</p>}
      <Msg m={msg} />
      <div className="tabs sub" role="tablist">
        <button className={`tab${kind === "*" ? " on" : ""}`} onClick={() => { setKind("*"); setStatus(""); }}>All <span className="quiet small">{data.records.length}</span></button>
        {data.kinds.map((x) => (
          <button key={x.name} className={`tab${kind === x.name ? " on" : ""}`} onClick={() => { setKind(x.name); setStatus(""); }}>
            {x.name}{x.name.endsWith("s") ? "" : "s"} <span className="quiet small">{data.records.filter((r) => r.kind === x.name).length}</span></button>
        ))}
        {can && <button className="tab" onClick={() => setNewKind({ name: "", prefix: "", statuses: "Open, Closed" })} title="A kind of record of the project's own, as a tab">＋ New kind</button>}
      </div>
      <div className="row-gap filters">
        {can && <button className="primary" onClick={() => setDlg({ kind: kind === "*" ? "Decision" : kind })}>＋ Log {kind === "*" ? "a record" : `a ${kind.toLowerCase()}`}</button>}
        {k && <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">Any status</option>
          {k.statuses.map((x) => <option key={x}>{x}</option>)}</select>}
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the log" aria-label="Search the log" />
        {k?.own && can && <button className="linkish small push-right" onClick={() => act(() => apiFetch(url, { method: "POST", body: JSON.stringify({ remove_kind: k.name }) })).then((ok) => ok && setKind("*"))}>Remove the kind {k.name}</button>}
      </div>
      {!recs.length ? <p className="quiet">Nothing logged{kind === "*" ? "" : ` as ${kind.toLowerCase()}`} yet.</p> : (
        <table className="grid-table">
          <thead><tr><th>Ref</th><th>Title</th>{kind === "*" && <th>Kind</th>}<th>Status</th><th>Approval</th><th>Owner</th><th>Date</th><th>Ends / review</th><th>About</th></tr></thead>
          <tbody>{recs.map((r) => (
            <tr key={r.id}>
              <td className="nowrap"><button className="linkish" onClick={() => setDlg(r)}>{r.ref}</button></td>
              <td><button className="linkish task-title" onClick={() => setDlg(r)}>{r.title}</button></td>
              {kind === "*" && <td className="small">{r.kind}</td>}
              <td><span className="chip small">{r.status}</span></td>
              <td><ApprovalChip r={r} /></td><td className="small">{r.owner}</td><td className="small nowrap">{r.raised_on}</td>
              <td className={`small nowrap${r.overdue ? " status bad" : ""}`}>{r.expires_on}</td>
              <td className="small">{[r.principle_name && `principle ${r.principle_name}`, r.standard_name && `standard ${r.standard_name}`, r.related].filter(Boolean).join("; ")}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {dlg && <GovDialog url={url} data={data} r={dlg} can={can} onDelete={() => act(() => apiFetch(`${url}/${dlg.id}`, { method: "DELETE" })).then(() => setDlg(null))}
        onClose={(m) => { setDlg(null); if (m) setMsg({ ok: true, text: m }); }} />}
      {newKind && (
        <Modal title="A new kind of record" onClose={() => setNewKind(null)}
          actions={<><button onClick={() => setNewKind(null)}>Cancel</button><button className="primary" disabled={!newKind.name.trim()}
            onClick={() => act(() => apiFetch(url, { method: "POST", body: JSON.stringify({ new_kind: { ...newKind, statuses: newKind.statuses.split(",") } }) }))
              .then((ok) => { if (ok) { setKind(newKind.name.trim()); setNewKind(null); } })}>Add</button></>}>
          <div className="ed-form">
            <Field label="Name"><input value={newKind.name} onChange={(e) => setNewKind({ ...newKind, name: e.target.value })} placeholder="e.g. Assumption, Action, Lesson" autoFocus /></Field>
            <Field label="Reference prefix" hint="(up to 4 letters)"><input value={newKind.prefix} maxLength={4} onChange={(e) => setNewKind({ ...newKind, prefix: e.target.value })} /></Field>
            <Field label="Statuses" hint="(comma separated, the first for new records)"><input value={newKind.statuses} onChange={(e) => setNewKind({ ...newKind, statuses: e.target.value })} /></Field>
          </div>
        </Modal>
      )}
    </div>
  );
}

function GovDialog({ url, data, r, can, onClose, onDelete }) {
  const k = data.kinds.find((x) => x.name === r.kind) || data.kinds[0];
  const [f, setF] = useState({ kind: r.kind || k.name, title: r.title || "", html: r.html || "", status: r.status || k.statuses[0], owner: r.owner || "",
    raised_on: r.raised_on || new Date().toISOString().slice(0, 10), expires_on: r.expires_on || "", principle: r.principle || "", standard: r.standard || "", related: r.related || "" });
  const [err, setErr] = useState("");
  const set = (key, v) => setF((x) => ({ ...x, [key]: v }));
  const kk = data.kinds.find((x) => x.name === f.kind) || k;
  async function save() {
    try { const out = await apiFetch(r.id ? `${url}/${r.id}` : url, { method: r.id ? "PUT" : "POST", body: JSON.stringify({ ...f, principle: f.principle || null, standard: f.standard || null }) }); refreshAll(); onClose(out.message); }
    catch (e) { setErr(e.message); }
  }
  return (
    <Modal title={r.id ? `${r.ref} ${r.title}` : `Log a ${f.kind.toLowerCase()}`} onClose={() => onClose()} wide
      actions={<>{r.id && can && <button className="danger" onClick={onDelete}>Take out</button>}<button onClick={() => onClose()}>{can ? "Cancel" : "Close"}</button>
        {can && <button className="primary" disabled={!f.title.trim()} onClick={save}>Save</button>}</>}>
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        {!r.id && <Field label="Kind"><select value={f.kind} onChange={(e) => { const nk = data.kinds.find((x) => x.name === e.target.value); setF({ ...f, kind: e.target.value, status: nk.statuses[0] }); }}>
          {data.kinds.map((x) => <option key={x.name}>{x.name}</option>)}</select></Field>}
        <Field label="Title"><input value={f.title} onChange={(e) => set("title", e.target.value)} disabled={!can} autoFocus /></Field>
        <div className="row-gap">
          <Field label="Status"><select value={f.status} onChange={(e) => set("status", e.target.value)} disabled={!can}>{kk.statuses.map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Owner"><input value={f.owner} onChange={(e) => set("owner", e.target.value)} disabled={!can} /></Field>
          <Field label="Date"><input type="date" value={f.raised_on} onChange={(e) => set("raised_on", e.target.value)} disabled={!can} /></Field>
          <Field label="Ends / review" hint="(optional)"><input type="date" value={f.expires_on} onChange={(e) => set("expires_on", e.target.value)} disabled={!can} /></Field>
        </div>
        <div className="row-gap">
          <Field label="About a principle"><select value={f.principle} onChange={(e) => set("principle", e.target.value)} disabled={!can}><option value="">–</option>
            {data.principles.map((x) => <option key={x.id} value={x.id}>{x.area ? `${x.area}: ` : ""}{x.name}</option>)}</select></Field>
          <Field label="About a standard"><select value={f.standard} onChange={(e) => set("standard", e.target.value)} disabled={!can}><option value="">–</option>
            {data.standards.map((x) => <option key={x.id} value={x.id}>{x.area ? `${x.area}: ` : ""}{x.name}</option>)}</select></Field>
        </div>
        <Field label="Related" hint="(documents, entities, other records)"><input value={f.related} onChange={(e) => set("related", e.target.value)} disabled={!can} /></Field>
        <Field label="Detail">{can ? <RichText value={f.html} onChange={(v) => set("html", v)} placeholder="Context, options, reasons, conditions, actions" /> : rich(f.html)}</Field>
        {r.id && <p className="small quiet">Logged by {r.created_by}; last changed by {r.modified_by}, {fmtDateTime(r.modified_at)}.</p>}
      </div>
      {r.id && <ApprovalBox url={url} r={r} can={can} onDone={(m) => onClose(m)} />}
    </Modal>
  );
}

// ---------------------------------------------------------------- Architecture charter tab
export function CharterTab({ p }) {
  const url = `/api/v1/projects/${p.id}/charter`;
  const { data, error } = useApi(url);
  const [edit, setEdit] = useState(null);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const act = useAct(setMsg);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const can = data.may_edit && !p.frozen;
  const put = (body) => act(() => apiFetch(url, { method: "PUT", body: JSON.stringify(body) }));
  return (
    <div>
      <div className="row-gap">
        <span className={`chip ${data.state === "Approved" ? "ok" : ""}`}>{data.state}</span>
        {data.state === "Approved" && <span className="small quiet">approved by {data.approved_by}, {fmtDateTime(data.approved_at)}</span>}
        {data.modified_at && <span className="small quiet">last changed by {data.modified_by}, {fmtDateTime(data.modified_at)}</span>}
        {can && data.state !== "Approved" && <button className="primary push-right" onClick={() => put({ approve: true })}>Approve the charter</button>}
      </div>
      <p className="quiet">The project's architecture charter: why it does architecture, its scope and authority, how it is governed, the principles and
        standards it applies, its roles, method and how compliance is checked. It starts from the base's charter; a Project Admin or Lead Architect changes and approves it.</p>
      <Msg m={msg} />
      {data.sections.map((s) => (
        <section key={s.key} className="charter-section">
          <h3>{s.title} {can && edit?.key !== s.key && <button className="linkish small" onClick={() => setEdit({ key: s.key, html: s.html })}>✎ Change</button>}</h3>
          {edit?.key === s.key ? (
            <>
              <RichText value={edit.html} onChange={(v) => setEdit({ ...edit, html: v })} />
              <div className="row-gap" style={{ marginTop: 6 }}>
                <button className="primary" onClick={() => put({ sections: { [s.key]: edit.html } }).then((ok) => ok && setEdit(null))}>Save</button>
                <button onClick={() => setEdit(null)}>Cancel</button></div>
            </>
          ) : rich(s.html)}
        </section>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- Project admin: the hierarchy of bases
// The hierarchy on the left; on the right, for the base or project chosen, its principles, standards, steps, document types
// with their templates, and charter: all in one place (owner, 8 Nov 2026).
export function BasesTree() {
  const { data, error } = useApi("/api/v1/projects/bases");
  const [sel, setSel] = useState(null);
  const [graph, setGraph] = useState(true);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const kids = (id) => data.nodes.filter((n) => n.parent === id);
  const pick = (id) => (e) => { e.preventDefault(); setSel(id); };
  const Node = ({ n }) => (
    <li>
      <a href={`#/projects/${n.id}`} onClick={pick(n.id)} className={sel === n.id ? "on" : ""}><b>{n.name}</b></a>{" "}
      {n.base_kind ? <span className="chip small">{BASE_LABEL[n.base_kind]}</span> : <span className="chip small">library project</span>}
      {n.base_kind === "empty" || n.base_kind === "togaf" ? <span className="small quiet"> read-only</span> : n.base_kind === "org" ? <span className="small quiet"> Super Admins</span> : null}
      <ul className="tree-list">
        {kids(n.id).map((c) => <Node key={c.id} n={c} />)}
        {n.projects.map((x) => <li key={x.id}><a href={`#/projects/${x.id}`} onClick={pick(x.id)} className={sel === x.id ? "on" : ""}>{x.name}</a>
          <span className="small quiet"> {x.status}</span></li>)}
      </ul>
    </li>
  );
  return (
    <div>
      <p className="quiet">Every project derives from a base, as models derive from root metamodels: the Empty project, the TOGAF 10 project (every ADM step,
        every document type, the TOGAF 10 content metamodel, principles and standards) and the Organisation base (the organisation's own, changed by Super
        Admins). Choose a base or project to see its principles, standards, steps, document types and templates, and charter in one place.</p>
      <div className="view-toggle" role="group" aria-label="View" style={{ marginBottom: 8 }}>
        <button className={graph ? "on" : ""} onClick={() => setGraph(true)}>🌳 Graph</button>
        <button className={!graph ? "on" : ""} onClick={() => setGraph(false)}>☰ List</button>
      </div>
      {graph ? (
        <>
          <Suspense fallback={<p className="quiet">Loading the tree...</p>}><ProjectTree items={flatten(data.nodes)} focus={sel} onPick={(id, kind) => {
            // a project opens (owner, 8 Nov 2026); a base shows what it holds below the tree, scrolled into view
            if (kind === "project") { window.location.hash = `/projects/${id}`; return; }
            setSel(id);
            setTimeout(() => document.getElementById("base-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
          }} /></Suspense>
          <div id="base-detail" style={{ marginTop: 12 }}>{sel ? <BaseDetail key={sel} id={sel} /> : <p className="quiet">Click a box to see its principles, standards, steps, document types and charter.</p>}</div>
        </>
      ) : (
        <div className="bases-layout">
          <ul className="tree-list root">{data.nodes.filter((n) => !n.parent || !data.nodes.some((x) => x.id === n.parent)).map((n) => <Node key={n.id} n={n} />)}</ul>
          <div>{sel ? <BaseDetail key={sel} id={sel} /> : <p className="quiet">Choose a base or a project on the left.</p>}</div>
        </div>
      )}
    </div>
  );
}

function BaseDetail({ id }) {
  const { data: p, error } = useApi(`/api/v1/projects/${id}`);
  const { data: std } = useApi(`/api/v1/projects/${id}/standards`);
  const { data: ch } = useApi(`/api/v1/projects/${id}/charter`);
  const [part, setPart] = useState("principles");
  const [q, setQ] = useState("");
  if (error) return <p className="status bad">{error}</p>;
  if (!p) return <p className="quiet">Loading...</p>;
  const m = (s) => !q.trim() || (s || "").toLowerCase().includes(q.trim().toLowerCase());
  const items = p.items.filter((i) => i.chosen && m(`${i.name} ${i.phase}`));
  const tpl = p.templates || {};
  const PARTS = [["principles", `Principles (${p.principles.length})`], ["standards", `Standards (${std?.standards.length ?? "…"})`],
    ["steps", `Steps (${p.steps.filter((s) => !s.parent && !s.removed).length})`], ["documents", `Document types (${p.items.filter((i) => i.chosen).length})`], ["charter", "Charter"]];
  return (
    <div className="base-detail">
      <h3><a href={`#/projects/${p.id}`}>{p.name}</a> {p.base_kind && <span className="chip small">{BASE_LABEL[p.base_kind]}</span>}</h3>
      {p.base_chain?.length > 0 && <p className="small quiet">derives from {p.base_chain.map((c) => c.name).join(" › ")}</p>}
      <div className="tabs sub" role="tablist">{PARTS.map(([k, l]) => <button key={k} className={`tab${part === k ? " on" : ""}`} onClick={() => setPart(k)}>{l}</button>)}</div>
      {part !== "charter" && <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter" aria-label="Filter" style={{ margin: "6px 0" }} />}
      {part === "principles" && <table className="grid-table small"><thead><tr><th>Area</th><th>Principle</th><th>Statement</th><th /></tr></thead>
        <tbody>{p.principles.filter((r) => m(`${r.name} ${r.area}`)).map((r) => <tr key={r.id}><td>{r.area}</td><td><b>{r.name}</b></td>
          <td>{rich(r.statement)}</td><td>{r.mandatory ? "🔒" : ""}</td></tr>)}</tbody></table>}
      {part === "standards" && (std ? <table className="grid-table small"><thead><tr><th>Area</th><th>Standard</th><th>Status</th><th>Source</th><th /></tr></thead>
        <tbody>{std.standards.filter((r) => m(`${r.name} ${r.area} ${r.source}`)).map((r) => <tr key={r.id}><td>{r.area}</td><td><b>{r.name}</b></td>
          <td>{r.status}</td><td>{r.source}</td><td>{r.mandatory ? "🔒" : ""}</td></tr>)}</tbody></table> : <p className="quiet">Loading...</p>)}
      {part === "steps" && <table className="grid-table small"><thead><tr><th>Phase</th><th>#</th><th>Step</th></tr></thead>
        <tbody>{p.steps.filter((s) => !s.parent && !s.removed && m(`${s.name} ${s.phase}`)).map((s) => <tr key={s.id}><td>{s.phase}</td><td>{s.seq}</td>
          <td>{s.name}{s.own && <span className="chip small">own</span>}</td></tr>)}</tbody></table>}
      {part === "documents" && <table className="grid-table small"><thead><tr><th>Phase</th><th>Document type</th><th>D/A</th><th>Templates</th></tr></thead>
        <tbody>{items.map((i) => <tr key={i.id}><td>{i.phase}</td><td>{i.name}</td><td>{i.kind === "Deliverable" ? "D" : "A"}</td>
          <td>{(tpl[i.library_id] || []).map((t) => <div key={t.id}>📄 {t.name} <span className="quiet">({t.library})</span></div>)}
            {!(tpl[i.library_id] || []).length && <span className="quiet">blank</span>}</td></tr>)}</tbody></table>}
      {part === "charter" && (ch ? <div>{ch.sections.map((s2) => <section key={s2.key} className="charter-section"><h4>{s2.title}</h4>{rich(s2.html)}</section>)}</div>
        : <p className="quiet">Loading...</p>)}
    </div>
  );
}

// ---------------------------------------------------------------- approval of a record (owner, 8 Nov 2026, D321)
const APPROVAL_TONE = { Draft: "off", "Waiting for approval": "amber", Approved: "green", Rejected: "red" };
export function ApprovalChip({ r }) {
  const tip = r.approval === "Approved" ? `by ${r.approved_by || ""}${r.approval_note ? `: ${r.approval_note}` : ""}${r.evidence_name ? ` (evidence: ${r.evidence_name})` : ""}`
    : r.request ? `waiting for ${r.request.waiting_for.join(", ")}` : "";
  return <span className={`rag ${APPROVAL_TONE[r.approval] || "off"} small`} title={tip}>{r.approval || "Draft"}</span>;
}

function ApprovalBox({ url, r, can, onDone }) {
  const [mode, setMode] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [err, setErr] = useState("");
  const [hist, setHist] = useState(null);
  const base = `${url}/${r.id}`;
  async function run(fn) {
    setErr("");
    try { const out = await fn(); refreshAll(); onDone(out.message); } catch (e) { setErr(e.message); }
  }
  const post = (body) => apiFetch(`${base}/approval`, { method: "POST", body: JSON.stringify(body) });
  async function evidence() {
    const fd = new FormData();
    fd.append("reason", text);
    if (file) fd.append("file", file);
    return apiUpload(`${base}/evidence`, fd);
  }
  const q = r.request;
  return (
    <div className="gov-approval">
      <h4>Approval: <ApprovalChip r={r} /></h4>
      {r.approval === "Approved" && <p className="small">Approved by {r.approved_by}{r.approved_at ? `, ${fmtDateTime(r.approved_at)}` : ""}
        {r.approval_note ? <>: {r.approval_note}</> : null}{r.evidence_name ? <> · evidence <b>{r.evidence_name}</b> (Sign-off evidence)</> : null}</p>}
      {r.approval === "Rejected" && <p className="small status bad">Rejected{r.approval_note ? `: ${r.approval_note}` : ""}. Change it and send it again, or approve it with evidence.</p>}
      {q && <p className="small">Sent by {q.raised_by} to {q.signers.join(", ")}: {q.quorum} must approve, any rejection rejects it.
        {q.decisions.length ? <> So far: {q.decisions.map((d) => `${d.signer} ${d.decision}${d.comment ? ` (${d.comment})` : ""}`).join("; ")}.</> : null}
        {q.waiting_for.length ? <> Waiting for {q.waiting_for.join(", ")}.</> : null}</p>}
      {err && <p className="status bad small">{err}</p>}
      <div className="row-gap">
        {q?.mine && <>
          <button className="primary" onClick={() => run(() => post({ action: "approve", comment: text }))}>✓ Approve</button>
          <button className="danger" onClick={() => (text.trim() ? run(() => post({ action: "reject", comment: text })) : setErr("Say why it is rejected (in the box below)."))}>✗ Reject</button>
        </>}
        {can && r.approval !== "Approved" && !q && <button onClick={() => setMode(mode === "send" ? "" : "send")}>Send for approval…</button>}
        {can && r.approval !== "Approved" && <button onClick={() => setMode(mode === "evidence" ? "" : "evidence")}>Approve with evidence…</button>}
        <button className="linkish small" onClick={() => apiFetch(`${base}/history`).then((h) => setHist(h.history)).catch((e) => setErr(e.message))}>🕘 History</button>
      </div>
      {(q?.mine || mode) && <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} style={{ width: "100%", marginTop: 6 }}
        placeholder={mode === "evidence" ? "Why it is approved (e.g. Architecture Board, 8 Nov: approved)" : mode === "send" ? "A note for the approvers (optional)" : "Your comment (needed to reject)"} />}
      {mode === "send" && <button className="primary" onClick={() => run(() => post({ action: "send", note: text }))}>Send to the sign-off people</button>}
      {mode === "evidence" && <div className="row-gap">
        <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} aria-label="Evidence file" />
        <button className="primary" disabled={!text.trim() && !file} onClick={() => run(evidence)}>Mark approved</button>
        <span className="small quiet">A reason, a file (minutes, an email, a signed page), or both.</span></div>}
      {hist && <table className="grid-table small" style={{ marginTop: 8 }}>
        <thead><tr><th>When</th><th>Who</th><th>What</th><th>Note</th></tr></thead>
        <tbody>{hist.map((h, i) => <tr key={i}><td className="nowrap">{fmtDateTime(h.at)}</td><td>{h.by_user}</td><td>{h.action}
          {h.snapshot && <span className="quiet" title={`${h.snapshot.title} · ${h.snapshot.status} · ${h.snapshot.approval}`}> (as it was ⓘ)</span>}</td><td>{h.note}</td></tr>)}</tbody>
      </table>}
    </div>
  );
}
