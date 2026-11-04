// Models, their metamodel and their content (read only until build phase 6).
//   #/metamodel                          every model
//   #/metamodel/<model>[/types]          tab Entity types (ModelViews.jsx), the default for models with content
//   #/metamodel/<model>/types/<id>       the entities of one type as a table
//   #/metamodel/<model>/rels[/<id>]      tab Relationship types, and the relationships of one type
//   #/metamodel/<model>/graph            tab Graph: entities and their relationships
//   #/metamodel/<model>/entity/<id>[/relations|/history|/graph]   one entity
//   #/metamodel/<model>/metamodel        tab Metamodel: layers, entity types, relationship types
//   #/metamodel/<model>/type/<id>        one entity type's definition: attributes, rules, allowed relationships
//   #/metamodel/<model>/diagram[/<id>]   tab ER diagram (MetamodelDiagram.jsx)
import { lazy, Suspense, useState } from "react";
import { keycloak } from "./auth";
import { CopyButton, LockBadge } from "./Library";
import {
  CsvButton, EntityPage, EntityTypesTab, GraphTab, Later, RelationshipsOfType, RelationshipTypesTab, Swatch, TypeEntitiesTable, useApi,
} from "./ModelViews";

// the diagram and its layout library load only when the ER diagram tab is opened
const MetamodelDiagram = lazy(() => import("./MetamodelDiagram"));

const go = (path) => { window.location.hash = path; };

// ---------------------------------------------------------------- model list
const KINDS = [["", "All kinds"], ["template", "Templates"], ["reference", "Reference models"], ["project", "Project models"]];

function ModelList() {
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [archived, setArchived] = useState(false);
  const q = new URLSearchParams();
  if (search.trim()) q.set("search", search.trim());
  if (kind) q.set("kind", kind);
  if (!archived) q.set("archived", "false");
  const { data: models, error } = useApi(`/api/v1/models?${q}`);
  return (
    <section>
      <h1>Models</h1>
      <p className="quiet">
        Every model you may open. Reference models are also in the <a href="#/library">model library</a>.
      </p>
      <div className="toolbar">
        <input className="search" style={{ maxWidth: 320 }} placeholder="Search name, description, owner, industry"
          value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <label><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> Show archived</label>
        {models && <CsvButton name="EA Explorer models" rows={() => [["Model", "Version", "Kind", "Industry", "Owner", "Status", "Locked", "Created from", "Merges into", "Entity types", "Entities", "Relationships", "Changed"],
          ...models.map((m) => [m.name, m.version_label, m.kind_name, m.industry, m.owner, m.lifecycle, m.is_locked ? "yes" : "", m.source_model_name, m.parent_model_name,
            m.entity_type_count, m.entity_count, m.relationship_count, m.modified_at])]} />}
      </div>
      {error && <p className="status bad">{error}</p>}
      {!models && !error && <p>Loading...</p>}
      {models && (
        <div className="scroll">
          <table className="grid-table models-table">
            <thead><tr><th>Model</th><th>Kind</th><th>Owner</th><th>Status</th><th>Types</th><th>Entities</th><th>Relationships</th><th>Changed</th></tr></thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td>
                    <a href={`#/metamodel/${m.id}`}><strong>{m.name}</strong></a>
                    {m.version_label && <span className="quiet"> {m.version_label}</span>}
                    {m.is_locked && <span className="quiet" title="Locked: read-only"> 🔒</span>}
                    <br /><span className="quiet">{m.industry && `${m.industry} · `}{m.metamodel_name}
                      {m.parent_model_name && ` · merges into ${m.parent_model_name}`}</span>
                  </td>
                  <td>{m.kind_name}</td>
                  <td>{m.owner || <span className="quiet">-</span>}</td>
                  <td>{m.lifecycle}</td>
                  <td className="num">{m.entity_type_count}</td>
                  <td className="num">{m.kind === "template" ? "-" : m.entity_count}</td>
                  <td className="num">{m.kind === "template" ? "-" : m.relationship_count}</td>
                  <td className="quiet">{new Date(m.modified_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {!models.length && <tr><td colSpan="8" className="quiet">No models match.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function EntityLink({ model, id, children }) {
  return <a href={`#/metamodel/${model}/entity/${id}`}>{children}</a>;
}

// ---------------------------------------------------------------- metamodel
function grouped(list) {
  const out = {};
  for (const a of list) (out[a.relationship_type] ||= []).push(a);
  return out;
}

function Allowed({ title, list, model }) {
  const groups = grouped(list);
  const names = Object.keys(groups);
  if (!names.length) return null;
  return (
    <>
      <h3>{title}</h3>
      <table className="grid-table">
        <tbody>
          {names.map((rel) => (
            <tr key={rel}>
              <th>{rel}</th>
              <td>
                {groups[rel].length >= 40 ? <em>any type ({groups[rel].length})</em>
                  : groups[rel].map((a, i) => (
                    <span key={a.other_type_id}>{i > 0 && ", "}<a href={`#/metamodel/${model}/type/${a.other_type_id}`}>{a.other_type}</a></span>
                  ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function TypeDetail({ model, typeId, holdsContent }) {
  const { data: t, error } = useApi(`/api/v1/models/${model}/entity-types/${typeId}`);
  const { data: list } = useApi(holdsContent ? `/api/v1/models/${model}/entity-list?type=${typeId}` : null);
  if (error) return <p className="status bad">{error}</p>;
  if (!t) return <p>Loading...</p>;
  return (
    <div>
      <h2><Swatch colour={t.colour} /> {t.name}</h2>
      <p className="quiet">
        {t.layer} layer · {t.aspect} · display IDs {t.id_prefix}-0001 · code <code>{t.code}</code> ·
        SQL <code>eax.get_entity('{t.name}', '{t.table_name}')</code> ·{" "}
        <a href={`#/metamodel/${model}/diagram/${typeId}`}>show in the ER diagram</a>
      </p>
      {holdsContent && list && (
        <p>{list.length ? <a href={`#/metamodel/${model}/types/${typeId}`}>{list.length} {t.name} entities in this model: open the table</a>
          : <span className="quiet">No {t.name} entities in this model yet.</span>}
          {list.length > 0 && list.length <= 12 && <span className="quiet"> ({list.map((e, i) => <span key={e.id}>{i > 0 && ", "}<EntityLink model={model} id={e.id}>{e.name}</EntityLink></span>)})</span>}</p>
      )}
      <h3>Attributes <CsvButton name={`${t.name} - definition`} rows={() => [["Attribute", "Column", "Type", "Unit", "Required", "Section", "Values"],
        ...t.attributes.map((a) => [a.name, a.column_name, a.data_type_name, a.unit, a.is_required ? "yes" : "", a.section, a.pick_list_values.join("; ")]),
        [], ["Rule field", "Rule", "Param 1", "Param 2", "Severity", "Message"], ...t.rules.map((r) => [r.field, r.rule, r.param1, r.param2, r.severity, r.message])]} /></h3>
      <p className="quiet">Every entity also has a display ID, name, description, parent, status and history.</p>
      <table className="grid-table">
        <thead><tr><th>Attribute</th><th>Type</th><th>Required</th><th>Section</th><th>Values</th></tr></thead>
        <tbody>
          {t.attributes.map((a) => (
            <tr key={a.code}>
              <td title={a.description}>{a.name}<br /><code className="quiet">{a.column_name}</code></td>
              <td>{a.data_type_name}{a.unit && ` (${a.unit})`}</td>
              <td>{a.is_required ? "Yes" : ""}</td>
              <td>{a.section}</td>
              <td className="quiet">{a.pick_list_values.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {t.rules.length > 0 && (
        <>
          <h3>Validation rules</h3>
          <table className="grid-table">
            <thead><tr><th>Field</th><th>Rule</th><th>Severity</th><th>Message</th></tr></thead>
            <tbody>{t.rules.map((r, i) => <tr key={i}><td>{r.field}</td><td>{r.rule}</td><td>{r.severity}</td><td>{r.message}</td></tr>)}</tbody>
          </table>
        </>
      )}
      <Allowed title={`From ${t.name} to other types`} list={t.outgoing} model={model} />
      <Allowed title={`From other types to ${t.name}`} list={t.incoming} model={model} />
    </div>
  );
}

function MetamodelView({ model, m, typeId, holdsContent }) {
  const { data: mm, error } = useApi(`/api/v1/models/${model}/metamodel`);
  if (error) return <p className="status bad">{error}</p>;
  if (!mm) return <p>Loading...</p>;
  return (
    <>
    <div className="toolbar">
      <span className="quiet">The definition of this model: what may be stored and how it is checked.</span>
      <span className="er-spacer" />
      <Later label="+ Entity type" phase={3} model={m} what="Adding an entity type" />
      <Later label="+ Attribute" phase={3} model={m} what="Adding an attribute" />
      <Later label="+ Relationship type" phase={3} model={m} what="Adding a relationship type" />
      <Later label="+ Mapping" phase={3} model={m} what="Adding a mapping (an allowed relationship between two entity types)" />
      <Later label="+ Rule" phase={3} model={m} what="Adding a validation rule" />
    </div>
    <div className="mm">
      <div className="layers">
        {mm.layers.map((l) => (
          <div key={l.id} className="layer">
            <h3><Swatch colour={l.colour} /> {l.name}</h3>
            <ul>
              {l.entity_types.map((t) => (
                <li key={t.id}>
                  <a href={`#/metamodel/${model}/type/${t.id}`} className={t.id === typeId ? "current" : ""}>{t.name}</a>
                  {t.entity_count > 0 && <span className="count">{t.entity_count}</span>}
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="layer">
          <h3>Relationship types</h3>
          <ul>{mm.relationship_types.map((r) => <li key={r.id} title={r.description}>{r.name} <span className="quiet">({r.verb})</span></li>)}</ul>
        </div>
      </div>
      <div className="detail">
        {typeId ? <TypeDetail model={model} typeId={typeId} holdsContent={holdsContent} />
          : <p className="quiet">Choose an entity type on the left.</p>}
      </div>
    </div>
    </>
  );
}

// ---------------------------------------------------------------- one model
function ModelPage({ model, view, itemId, sub }) {
  const { data: m, error } = useApi(`/api/v1/models/${model}`);
  const [showProps, setShowProps] = useState(false);
  if (error) return <section><p className="status bad">{error}</p><a href="#/metamodel">All models</a></section>;
  if (!m) return <section><p>Loading...</p></section>;
  const holdsContent = m.kind !== "template";
  const v = view === "relationships" ? "rels" : view;   // older links
  const tab = !v ? (holdsContent ? "types" : "metamodel")
    : v === "type" ? "metamodel" : v === "entity" ? "types" : v;
  const tabs = [
    ...(holdsContent ? [["types", "Entity types", m.entity_type_count], ["rels", "Relationship types", null], ["graph", "Graph", null]] : []),
    ["metamodel", "Metamodel", null], ["diagram", "ER diagram", null],
  ];
  return (
    <section className="model-page">
      <p className="quiet"><a href="#/metamodel">Models</a>{m.kind === "reference" && <> · <a href="#/library">Library</a></>} / {m.name}</p>
      <div className="model-head">
        <h1>{m.name} {m.version_label && <span className="quiet">{m.version_label}</span>}</h1>
        <LockBadge model={m} />
        {m.is_locked && <CopyButton />}
        <button className="linkish" onClick={() => setShowProps((x) => !x)}>{showProps ? "Hide details" : "Details"}</button>
      </div>
      <p className="quiet">
        {m.kind_name}{m.is_locked ? " · read-only" : ""} · {m.metamodel_name} · {m.entity_type_count} entity types
        {holdsContent && ` · ${m.entity_count} entities · ${m.relationship_count} relationships`}
      </p>
      {showProps && (
        <div className="model-props-box">
          {m.description && <p>{m.description}</p>}
          <p className="quiet">
            Owner {m.owner || "-"} · {m.lifecycle}{m.industry && ` · ${m.industry}`}
            {m.source_model_id && <> · created from <a href={`#/metamodel/${m.source_model_id}`}>{m.source_model_name}</a></>}
            {m.parent_model_id && <> · merges into <a href={`#/metamodel/${m.parent_model_id}`}>{m.parent_model_name}</a></>} ·
            created {new Date(m.created_at).toLocaleDateString()} by {m.created_by} ·
            changed {new Date(m.modified_at).toLocaleDateString()} by {m.modified_by}
          </p>
        </div>
      )}
      <div className="tabs" role="tablist">
        {tabs.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "tab on" : "tab"} onClick={() => go(`/metamodel/${model}/${k}`)}>{label}</button>
        ))}
      </div>
      <div className="tab-panel" role="tabpanel">
      {v === "entity" && itemId ? <EntityPage model={model} m={m} entityId={itemId} sub={sub} />
        : tab === "types" ? (itemId ? <TypeEntitiesTable model={model} m={m} typeId={itemId} /> : <EntityTypesTab model={model} m={m} />)
        : tab === "rels" ? (itemId ? <RelationshipsOfType model={model} m={m} relTypeId={itemId} /> : <RelationshipTypesTab model={model} m={m} />)
        : tab === "graph" ? <GraphTab model={model} kind={itemId} />
        : tab === "diagram" ? <Suspense fallback={<p>Loading the diagram...</p>}><MetamodelDiagram model={model} focus={itemId || null} /></Suspense>
        : <MetamodelView model={model} m={m} typeId={v === "type" ? itemId : null} holdsContent={holdsContent} />}
      </div>
    </section>
  );
}

export default function Metamodel({ route }) {
  if (!keycloak.authenticated) {
    return (
      <section>
        <h1>Models and metamodels</h1>
        <p>Sign in to browse models.</p>
        <button className="primary" onClick={() => keycloak.login()}>Sign in</button>
      </section>
    );
  }
  // #/metamodel/<model>/<view>/<id>/<sub>
  const [, , model, view, itemId, sub] = (route || "").replace(/^#/, "").split("/");
  return model ? <ModelPage model={model} view={view} itemId={itemId} sub={sub} /> : <ModelList />;
}
