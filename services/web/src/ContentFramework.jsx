// A project's Content framework tab (owner, 8 Nov 2026, D299). The content framework's fixed areas drawn as a map in
// ArchiMate's colours, each with how much of the project sits there; a click opens the area as a tree:
//   Metamodels > each of the project's models > its entity types placed here > their entities
//   Documents  > the document types placed here > their documents (every state, the latest version)
// An entity opens on its model's page; an entity type on the metamodel; a document type or document on Home's
// Documents, highlighted. Where an entity type sits is part of its definition (the metamodel editor); contributors
// place the project's document types and documents here. Any of them may sit in several areas (D309). Tag items (D317)
// lists every deliverable and artifact, document, entity type and entity with its areas, to change one or many.
import { useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { CF_AREAS, CF_LABEL } from "./cfAreas";
import { AreaChips, AreaPicker } from "./CfAreaPicker";

// ArchiMate's colours for each part
const COLOUR = { motivation: "#D1BADC", strategy: "#EFBD5D", business: "#ECD678", application: "#B0D0D9", technology: "#BBD8AD",
  migration: "#F1BBB7", governance: "#D1BADC" };  // the ArchiMate 4 notation's colours (D392)
const colourOf = (code) => {
  const [part, leaf] = code.split(".");
  if (["prelim", "req", "vision", "motivation"].includes(part)) return COLOUR.motivation;
  if (part === "business") return ["value_streams", "capabilities", "courses_of_action"].includes(leaf) ? COLOUR.strategy : COLOUR.business;
  if (part === "data" || part === "app") return COLOUR.application;
  if (part === "tech") return COLOUR.technology;
  if (part === "real") return COLOUR.migration;
  return COLOUR.governance;
};
const phaseLink = (ph) => (ph === "C-D" || ph === "C-A" ? "C" : ph || "X");

export function ContentFrameworkTab({ p }) {
  const qs = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const area = qs.get("area");
  const tag = qs.get("view") === "tag";
  const view = (v) => { window.location.hash = `#/projects/${p.id}/content${v === "tag" ? "?view=tag" : ""}`; };
  return (
    <div>
      {!area && <div className="cf-views" role="tablist">
        <button role="tab" aria-selected={!tag} className={`cf-view${tag ? "" : " on"}`} onClick={() => view("map")}>▦ Map</button>
        <button role="tab" aria-selected={tag} className={`cf-view${tag ? " on" : ""}`} onClick={() => view("tag")}>🏷 Tag items</button>
      </div>}
      {area ? <AreaTree p={p} code={area} /> : tag ? <TagItems p={p} to={qs.get("to") || ""} /> : <FrameworkMap p={p} />}
    </div>
  );
}

// ---------------------------------------------------------------- Tag items (owner, 8 Nov 2026, D317)
// Another way to reach the project's things: every deliverable and artifact, document, entity type and entity with the
// areas where it sits; one by one or many at once. Dashed chips: the default; solid: chosen in this project.
const TAG_KINDS = [
  ["classes", "Deliverables and artifacts"], ["documents", "Documents"], ["types", "Metamodel entity types"], ["entities", "Entities"]];

function TagItems({ p, to }) {
  const [kind, setKind] = useState("classes");
  const [q, setQ] = useState("");
  const [find, setFind] = useState("");
  const [phase, setPhase] = useState("");
  const [area, setArea] = useState(to || "");
  const [offset, setOffset] = useState(0);
  const [ticked, setTicked] = useState(() => new Set());
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const args = new URLSearchParams({ kind, q: find, phase, area, offset: String(offset) });
  const { data, error } = useApi(`/api/v1/projects/${p.id}/cf-tags?${args}`);
  const rows = data?.rows || [];
  const can = !!data?.may_place;
  const reset = () => { setTicked(new Set()); setOffset(0); };
  async function place(ids, how, areas) {
    try {
      const r = await apiFetch(`/api/v1/projects/${p.id}/cf-tags`, { method: "PUT", body: JSON.stringify({ kind, ids, how, areas }) });
      setMsg({ ok: true, text: r.message }); refreshAll();
    } catch (e) { setMsg({ ok: false, text: e.message }); throw e; }
  }
  const tick = (id) => { const n = new Set(ticked); if (n.has(id)) n.delete(id); else n.add(id); setTicked(n); };
  const allOn = rows.length > 0 && rows.every((r) => ticked.has(r.id));
  const tickAll = () => setTicked(allOn ? new Set() : new Set(rows.map((r) => r.id)));
  const ids = [...ticked];
  const what = { classes: "Deliverable / artifact", documents: "Document", types: "Entity type", entities: "Entity" }[kind];
  const onPhase = kind === "classes" || kind === "documents";
  return (
    <div className="cf-tag">
      <p className="quiet small">Where each of the project's things sits in the content framework: another way to reach it. Dashed: where it
        sits by default; solid: chosen in this project. One thing may sit in several areas. {kind === "types" || kind === "entities"
        ? "Entity types and entities are placed for this project only; the model's metamodel keeps its own." : ""}
        {kind === "documents" ? " A document sits where its deliverable or artifact does, and in any areas of its own." : ""}</p>
      <div className="cf-views sub" role="tablist">
        {TAG_KINDS.map(([k, l]) => <button key={k} role="tab" aria-selected={kind === k} className={`cf-view${kind === k ? " on" : ""}`}
          onClick={() => { setKind(k); setPhase(""); reset(); }}>{l}{kind === k && data ? <span className="quiet small"> {data.total}</span> : null}</button>)}
      </div>
      {to && <p className="status ok small">Tagging items for <b>{CF_LABEL[to]}</b>: change the area filter to "Any area" or "Not placed", tick
        rows, then "＋ Add area to ticked…". <a href={`#/projects/${p.id}/content?area=${to}`}>Back to the area</a></p>}
      <div className="row-gap cf-tag-tools">
        <form onSubmit={(e) => { e.preventDefault(); setFind(q); reset(); }} className="row-gap">
          <input type="search" value={q} onChange={(e) => { setQ(e.target.value); if (!e.target.value) { setFind(""); reset(); } }}
            placeholder={`Find ${kind === "entities" ? "an entity (name or id)" : "by name"}`} aria-label="Find" />
          <button type="submit">Find</button>
        </form>
        {onPhase && <select value={phase} onChange={(e) => { setPhase(e.target.value); reset(); }} aria-label="Phase">
          <option value="">Every phase</option>
          {(data?.phases || []).map((ph) => <option key={ph} value={ph}>Phase {ph}</option>)}
        </select>}
        <select value={area} onChange={(e) => { setArea(e.target.value); reset(); }} aria-label="Area">
          <option value="">Any area</option>
          <option value="_none">Not placed</option>
          <option value="_changed">Changed from the default</option>
          {CF_AREAS.map(([c, l, , g]) => <option key={c} value={c}>In {g}: {l}</option>)}
        </select>
      </div>
      {can && <div className="cf-tag-bulk cf-tag-tools">
        <>
          <span className="small"><b>{ids.length}</b> ticked{ids.length ? "" : ": tick rows to change many at once"}</span>
          <AreaPicker value={to ? [to] : []} label="＋ Add area to ticked…" disabled={!ids.length}
            onSave={(list) => place(ids, "add", list).then(() => setTicked(new Set()))} />
          <AreaPicker value={[]} label="− Take area off ticked…" disabled={!ids.length}
            onSave={(list) => place(ids, "remove", list).then(() => setTicked(new Set()))} />
          <button className="linkish small" disabled={!ids.length} onClick={() => place(ids, "reset").then(() => setTicked(new Set())).catch(() => {})}>↺ Ticked back to default</button>
        </>
      </div>}
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      {error && <p className="status bad">{error}</p>}
      {!data ? <p className="quiet">Loading...</p> : (
        <div className="table-wrap">
          <table className="cf-tag-table">
            <thead><tr>
              {can && <th style={{ width: 24 }}><input type="checkbox" checked={allOn} onChange={tickAll} aria-label="Tick every row shown" /></th>}
              <th>{what}</th>
              {kind === "classes" && <><th>D/A</th><th>Phase</th></>}
              {kind === "documents" && <><th>Deliverable / artifact</th><th>Phase</th></>}
              {(kind === "types" || kind === "entities") && <th>{kind === "entities" ? "Type · model" : "Model"}</th>}
              <th>Content framework areas</th>
              <th title="The part of the Architecture Repository it is filed in: set on the document class or the entity type">Repository area</th>
              {can && <th />}
            </tr></thead>
            <tbody>
              {!rows.length && <tr><td colSpan={7} className="quiet">Nothing{find || area || phase ? " matches" : " yet"}.</td></tr>}
              {rows.map((r) => <TagRow key={r.id} p={p} r={r} kind={kind} can={can} on={ticked.has(r.id)} tick={() => tick(r.id)} place={place} />)}
            </tbody>
          </table>
        </div>
      )}
      {data && data.total > data.page && (
        <div className="row-gap small">
          <button disabled={!offset} onClick={() => { setOffset(Math.max(0, offset - data.page)); setTicked(new Set()); }}>‹ Previous</button>
          <span className="quiet">{offset + 1}–{Math.min(data.total, offset + data.page)} of {data.total}</span>
          <button disabled={offset + data.page >= data.total} onClick={() => { setOffset(offset + data.page); setTicked(new Set()); }}>Next ›</button>
        </div>
      )}
    </div>
  );
}

const shortDate = (s) => (s ? new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "");

function TagRow({ p, r, kind, can, on, tick, place }) {
  const ph = phaseLink(r.phase);
  const name = kind === "classes" ? <a href={`#/projects/${p.id}/phases?phase=${ph}&item=${r.id}`}>{r.name}</a>
    : kind === "documents" ? <a href={`#/projects/${p.id}/phases?phase=${ph}&doc=${r.id}`}>📄 {r.name}</a>
      : kind === "types" ? <a href={`#/metamodel/${r.model_id}/type/${r.id}`} title="Open the entity type">{r.name}</a>
        : <a href={`#/metamodel/${r.model_id}/entity/${r.id}`} title="Open the entity">{r.name}</a>;
  // chips: what it gets by default (dashed) and what was chosen here (solid)
  const own = kind === "documents" ? r.own || [] : r.chosen ? r.areas : [];
  const dflt = kind === "documents" ? r.default : r.chosen ? [] : r.default;
  return (
    <tr className={on ? "ticked" : ""}>
      {can && <td><input type="checkbox" checked={on} onChange={tick} aria-label={`Tick ${r.name}`} /></td>}
      <td>{name}
        <div className="quiet small">
          {kind === "classes" && `${r.type || r.kind || ""} · ${r.documents} document${r.documents === 1 ? "" : "s"}`}
          {kind === "documents" && r.file_name !== r.name ? r.file_name : ""}
          {kind === "types" && `${r.domain || ""} · ${r.entities} entit${r.entities === 1 ? "y" : "ies"}`}
          {kind === "entities" && (r.display_id || "")}
        </div></td>
      {kind === "classes" && <><td><span className={`kind-toggle ${r.kind === "Deliverable" ? "del" : "art"}`} title={r.kind}>{r.kind === "Deliverable" ? "D" : "A"}</span></td><td>{r.phase}{r.frozen && <span title="Frozen in this ADM iteration: read only"> 🔒</span>}</td></>}
      {kind === "documents" && <><td>{r.class}</td><td>{r.phase}</td></>}
      {kind === "types" && <td>{r.model}</td>}
      {kind === "entities" && <td>{r.type}<div className="quiet small">{r.model}</div></td>}
      <td>
        {!r.areas.length ? <span className="quiet small">not placed</span> : <>
          {dflt.length > 0 && <AreaChips codes={dflt} dflt small />} {own.length > 0 && <AreaChips codes={own} small />}</>}
        {r.chosen ? <div className="quiet small">{kind === "documents" ? "own areas" : "chosen here"}{r.set_by ? ` by ${r.set_by}` : ""}{r.set_at ? ` · ${shortDate(r.set_at)}` : ""}</div>
          : r.source && <div className="quiet small">from {r.source}</div>}
      </td>
      <td className="small">{r.repository}</td>
      {can && <td className="nowrap">
        <AreaPicker value={kind === "documents" ? r.own || [] : r.chosen ? r.areas : []} dflt={kind === "documents" ? [] : r.default}
          label={kind === "documents" ? "Also in…" : r.areas.length ? "Change…" : "Place…"}
          onSave={(list) => place([r.id], kind === "documents" || list.length ? "set" : "reset", list)} />
        {r.chosen && <button className="linkish small" onClick={() => place([r.id], "reset").catch(() => {})}>↺ {kind === "documents" ? "Class's areas only" : "Back to default"}</button>}
      </td>}
    </tr>
  );
}

function FrameworkMap({ p }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/content-framework`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const by = Object.fromEntries(data.areas.map((a) => [a.code, a]));
  const Tile = ({ code, tall }) => {
    const a = by[code] || {};
    const has = a.types || a.doc_types || a.documents;
    return (
      <a className={`cf-tile${has ? "" : " empty"}${tall ? " tall" : ""}`} style={{ background: colourOf(code) }}
        href={`#/projects/${p.id}/content?area=${code}`} title={`${CF_LABEL[code]}: open what sits here`}>
        <span className="cf-name">{CF_LABEL[code]}</span>
        <span className="cf-plus" role="button" tabIndex={0} title={`Tag more items into ${CF_LABEL[code]}`}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); window.location.hash = `#/projects/${p.id}/content?view=tag&to=${code}`; }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); window.location.hash = `#/projects/${p.id}/content?view=tag&to=${code}`; } }}>＋</span>
        <span className="cf-count">
          {a.types ? `${a.types} type${a.types === 1 ? "" : "s"} · ${a.entities} entit${a.entities === 1 ? "y" : "ies"}` : ""}
          {a.types && (a.doc_types || a.documents) ? <br /> : null}
          {a.doc_types || a.documents ? `${a.doc_types} doc type${a.doc_types === 1 ? "" : "s"} · ${a.documents} doc${a.documents === 1 ? "" : "s"}` : ""}
          {!has && "nothing yet"}
        </span>
      </a>
    );
  };
  const Box = ({ title, codes, cols, vertical }) => (
    <div className="cf-box">
      <div className="cf-box-title">{title}</div>
      <div className={vertical ? "cf-col" : "cf-row"} style={vertical ? undefined : { gridTemplateColumns: `repeat(${cols || codes.length}, minmax(0, 1fr))` }}>
        {codes.map((c) => <Tile key={c} code={c} tall={vertical} />)}
      </div>
    </div>
  );
  return (
    <div>
      <p className="quiet">The content framework: where the project's models and documents sit. Click an area to see its entity types and
        entities in each of the project's models ({data.models.map((m) => m.name).join(", ") || "none yet"}) and its document types and documents.
        Colours follow ArchiMate: motivation, strategy, business, application and data, technology, implementation and migration.</p>
      {(data.unplaced.entity_types > 0 || data.unplaced.document_types > 0) && (
        <p className="small"><a href={`#/projects/${p.id}/content?area=_unplaced`}>Not placed yet: {data.unplaced.entity_types} entity
          type{data.unplaced.entity_types === 1 ? "" : "s"}, {data.unplaced.document_types} document type{data.unplaced.document_types === 1 ? "" : "s"}</a></p>
      )}
      <div className="cf-map">
        <section className="cf-section">
          <h3>Architecture principles, vision and requirements</h3>
          <div className="cf-grid" style={{ gridTemplateColumns: "1fr 5fr" }}>
            <Box title="Preliminary" codes={["prelim.principles"]} />
            <Box title="Architecture requirements" codes={["req.requirements", "req.constraints", "req.assumptions", "req.gaps", "req.locations"]} />
          </div>
          <Box title="Architecture vision" codes={["vision.business_strategy", "vision.technology_strategy", "vision.principles_drivers",
            "vision.architecture_vision", "vision.stakeholders"]} />
        </section>
        <section className="cf-section">
          <h3>Architecture definition</h3>
          <Box title="Motivation" codes={["motivation.drivers", "motivation.goals", "motivation.outcomes", "motivation.measures"]} />
          <div className="cf-grid" style={{ gridTemplateColumns: "4fr 3fr 1.4fr" }}>
            <div className="cf-box cf-domain">
              <div className="cf-box-title">Business architecture</div>
              <Box title="Strategy" codes={["business.value_streams", "business.capabilities", "business.courses_of_action"]} />
              <Box title="Operational" codes={["business.services_contracts", "business.processes_events", "business.functions_org_units", "business.roles_actors"]} />
            </div>
            <div className="cf-box cf-domain">
              <div className="cf-box-title">Information systems architecture</div>
              <div className="cf-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <Box title="Data" vertical codes={["data.entities", "data.logical_components", "data.physical_components"]} />
                <Box title="Application" vertical codes={["app.services", "app.logical_components", "app.physical_components"]} />
              </div>
            </div>
            <div className="cf-box cf-domain">
              <div className="cf-box-title">Technology architecture</div>
              <Box title="Technology" vertical codes={["tech.services", "tech.logical_components", "tech.physical_components"]} />
            </div>
          </div>
        </section>
        <section className="cf-section">
          <h3>Architecture realisation</h3>
          <div className="cf-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Box title="Opportunities, solutions and migration planning" codes={["real.capabilities", "real.work_packages", "real.contracts"]} />
            <Box title="Implementation governance" codes={["gov.standards", "gov.guidelines", "gov.specifications"]} />
          </div>
        </section>
      </div>
    </div>
  );
}

function AreaTree({ p, code }) {
  const { data, error } = useApi(`/api/v1/projects/${p.id}/content-framework/${code}`);
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const unplaced = code === "_unplaced";
  const match = (s) => !q.trim() || (s || "").toLowerCase().includes(q.trim().toLowerCase());
  const nTypes = useMemo(() => (data?.models || []).reduce((n, m) => n + m.types.length, 0), [data]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const can = data.may_place_documents && !p.frozen;
  async function place(url, areas) {
    try { const r = await apiFetch(url, { method: "PUT", body: JSON.stringify({ areas }) }); setMsg({ ok: true, text: r.message }); refreshAll(); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
  }
  const go = (c) => { window.location.hash = `#/projects/${p.id}/content${c ? `?area=${c}` : ""}`; };
  return (
    <div>
      <div className="row-gap">
        <a href={`#/projects/${p.id}/content`}>‹ Content framework</a>
        <select value={code} onChange={(e) => go(e.target.value)} aria-label="Area">
          {CF_AREAS.map(([c, l, , g]) => <option key={c} value={c}>{g}: {l}</option>)}
          <option value="_unplaced">Not placed yet</option>
        </select>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by name" aria-label="Filter by name" />
        {!unplaced && <a className="small" href={`#/projects/${p.id}/content?view=tag&to=${code}`} title="Put more deliverables, documents, entity types or entities in this area">＋ Tag more items here</a>}
      </div>
      <h3 className="cf-area-title" style={{ background: unplaced ? "#eee" : colourOf(code) }}>
        {unplaced ? "Not placed in the content framework yet" : <>{data.area.group} › {data.area.label}</>}
      </h3>
      {unplaced && <p className="small quiet">An entity type is placed in its model's metamodel (Change entity type › Content framework area);
        a document type here, below.</p>}
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <div className="cf-tree">
        <details open>
          <summary><b>Metamodels</b> <span className="quiet small">{nTypes} entity type{nTypes === 1 ? "" : "s"}</span></summary>
          {!data.models.length && <p className="quiet small">The project has no models yet.</p>}
          {data.models.map((m) => (
            <details key={m.id} open className="cf-node">
              <summary>🧭 <a href={`#/metamodel/${m.id}`}>{m.name}</a> <span className="quiet small">{m.types.length} type{m.types.length === 1 ? "" : "s"}</span></summary>
              {!m.types.length && !(m.own_entities || []).length && <p className="quiet small cf-leaf">No entity type of this model sits here.</p>}
              {(m.own_entities || []).length > 0 && (
                <details className="cf-node" open>
                  <summary><b>Entities placed here on their own</b> <span className="quiet small">{m.own_entities.length}</span></summary>
                  <ul className="cf-leaves">{m.own_entities.filter((e) => match(e.name) || match(e.display_id)).map((e) => (
                    <li key={e.id}><a href={`#/metamodel/${m.id}/entity/${e.id}`}>{e.name}</a>
                      <span className="quiet small"> {e.type}{e.display_id ? ` · ${e.display_id}` : ""}</span></li>))}</ul>
                </details>
              )}
              {m.types.map((t) => {
                const ents = t.entities.filter((e) => match(e.name) || match(e.display_id));
                if (q && !ents.length && !match(t.name)) return null;
                return (
                  <details key={t.id} className="cf-node" open={!!q || nTypes <= 6}>
                    <summary><span className="cf-swatch" style={{ background: `#${t.colour || "ddd"}` }} />
                      <a href={`#/metamodel/${m.id}/type/${t.id}`} title="Open the entity type">{t.name}</a>
                      <span className="quiet small"> {t.count} entit{t.count === 1 ? "y" : "ies"} · {t.domain}{t.chosen ? "" : " · placed by default"}</span>
                      {(t.areas || []).length > 1 && <> <AreaChips codes={t.areas.filter((a) => a !== code)} dflt={!t.chosen} small /></>}</summary>
                    {!unplaced && (ents.length ? (
                      <ul className="cf-leaves">
                        {ents.map((e) => <li key={e.id}><a href={`#/metamodel/${m.id}/entity/${e.id}`}>{e.name}</a>
                          <span className="quiet small"> {e.display_id}{e.status === "retired" ? " · retired" : ""}</span></li>)}
                        {t.more > 0 && <li className="quiet small">and {t.more} more: <a href={`#/metamodel/${m.id}/types/${t.id}`}>open them all</a></li>}
                      </ul>
                    ) : <p className="quiet small cf-leaf">No entities{q ? " match" : " yet"}.</p>)}
                  </details>
                );
              })}
            </details>
          ))}
        </details>
        <details open>
          <summary><b>Documents</b> <span className="quiet small">{data.doc_types.length} document type{data.doc_types.length === 1 ? "" : "s"}</span></summary>
          {!data.doc_types.length && !data.documents.length && <p className="quiet small cf-leaf">No document type of the project sits here.</p>}
          {data.doc_types.map((t) => {
            const docs = t.documents.filter((d) => match(d.file_name));
            if (q && !docs.length && !match(t.name)) return null;
            return (
              <details key={t.id} className="cf-node" open>
                <summary>
                  <span className={`kind-toggle ${t.kind === "Deliverable" ? "del" : "art"}`} title={t.kind}>{t.kind === "Deliverable" ? "D" : "A"}</span>{" "}
                  <a href={`#/projects/${p.id}/phases?phase=${phaseLink(t.phase)}&item=${t.id}`} title="Open the document type">{t.name}</a>
                  <span className="quiet small"> phase {t.phase} · {t.documents.length} document{t.documents.length === 1 ? "" : "s"}{t.placed ? "" : " · placed by default"}</span>
                  {(t.areas || []).length > 1 && <> <AreaChips codes={t.areas.filter((a) => a !== code)} dflt={!t.placed} small /></>}
                  {can && <> <AreaPicker value={t.placed ? t.areas : []} dflt={t.areas || []} label={unplaced ? "Place it…" : "Areas…"} resetLabel={t.placed ? "Back to its default" : ""}
                    onSave={(list) => place(`/api/v1/projects/${p.id}/items/${t.id}/content-area`, list)} /></>}
                </summary>
                {docs.length ? <ul className="cf-leaves">{docs.map((d) => <DocLeaf key={d.id} p={p} d={d} phase={t.phase} can={can} place={place} />)}</ul>
                  : <p className="quiet small cf-leaf">No documents{q ? " match" : " yet"}.</p>}
              </details>
            );
          })}
          {data.documents.length > 0 && (
            <details className="cf-node" open>
              <summary><b>Placed here on their own</b></summary>
              <ul className="cf-leaves">{data.documents.filter((d) => match(d.file_name)).map((d) => <DocLeaf key={d.id} p={p} d={d} can={can} place={place} own />)}</ul>
            </details>
          )}
        </details>
      </div>
    </div>
  );
}

function DocLeaf({ p, d, phase, can, place, own }) {
  const href = `#/projects/${p.id}/phases?phase=${phaseLink(phase)}&doc=${d.id}`;
  return (
    <li>
      {d.is_link ? "🔗" : "📄"} <a href={href} title="Open it in the project's documents">{d.title || d.file_name}</a>
      <span className="quiet small"> {d.state}{d.user_version ? ` · ${d.user_version}` : ""}{d.versions ? ` · v${d.versions}` : ""}</span>
      {(d.own_areas || []).length > 0 && <> <span className="quiet small">{own ? "also in" : "also in"}</span> <AreaChips codes={d.own_areas} small /></>}
      {can && <> <AreaPicker value={d.own_areas || []} label={(d.own_areas || []).length ? "Areas…" : "Also place it in…"}
        resetLabel={(d.own_areas || []).length ? "Under its document type only" : ""}
        onSave={(list) => place(`/api/v1/projects/${p.id}/documents/${d.id}/content-area`, list)} /></>}
    </li>
  );
}
