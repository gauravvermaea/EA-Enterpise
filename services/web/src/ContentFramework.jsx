// A project's Content framework tab (owner, 8 Nov 2026, D299). The content framework's fixed areas drawn as a map in
// ArchiMate's colours, each with how much of the project sits there; a click opens the area as a tree:
//   Metamodels > each of the project's models > its entity types placed here > their entities
//   Documents  > the document types placed here > their documents (every state, the latest version)
// An entity opens on its model's page; an entity type on the metamodel; a document type or document on Home's
// Documents, highlighted. Where an entity type sits is part of its definition (the metamodel editor); contributors
// place the project's document types and documents here. Any of them may sit in several areas (D309).
import { useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { CF_AREAS, CF_LABEL } from "./cfAreas";
import { AreaChips, AreaPicker } from "./CfAreaPicker";

// ArchiMate's colours for each part
const COLOUR = { motivation: "#CCCCFF", strategy: "#F5DEAA", business: "#FFFFB5", application: "#B5FFFF", technology: "#C9E7B7",
  migration: "#FFE0E0", governance: "#E0FFE0" };
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
  const area = new URLSearchParams(window.location.hash.split("?")[1] || "").get("area");
  return area ? <AreaTree p={p} code={area} /> : <FrameworkMap p={p} />;
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
              {!m.types.length && <p className="quiet small cf-leaf">No entity type of this model sits here.</p>}
              {m.types.map((t) => {
                const ents = t.entities.filter((e) => match(e.name) || match(e.display_id));
                if (q && !ents.length && !match(t.name)) return null;
                return (
                  <details key={t.id} className="cf-node" open={!!q || nTypes <= 6}>
                    <summary><span className="cf-swatch" style={{ background: `#${t.colour || "ddd"}` }} />
                      <a href={`#/metamodel/${m.id}/type/${t.id}`} title="Open the entity type">{t.name}</a>
                      <span className="quiet small"> {t.count} entit{t.count === 1 ? "y" : "ies"} · {t.layer}{t.chosen ? "" : " · placed by default"}</span>
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
