// Models, their metamodel and their content (read only until build phase 6).
//   #/metamodel                          every model
//   #/metamodel/<model>[/types]          tab Entity types (ModelViews.jsx), the default for models with content
//   #/metamodel/<model>/types/<id>       the entities of one type as a table
//   #/metamodel/<model>/rels[/<id>]      tab Relationship types, and the relationships of one type
//   #/metamodel/<model>/graph            tab Graph: entities and their relationships
//   #/metamodel/<model>/entity/<id>[/relations|/history|/graph]   one entity
//   #/metamodel/<model>/checks           tab Failing checks: every entity failing a check (phase 3)
//   #/metamodel/<model>/metamodel[/lists|/history]   tab Metamodel: definition, pick lists, history and versions
//   #/metamodel/<model>/type/<id>        one entity type's definition: attributes, rules, allowed relationships
//   #/metamodel/<model>/diagram[/<id>]   tab ER diagram (MetamodelDiagram.jsx)
//   #/metamodel/<model>/entry[/<type>]   tab Data entry: an entity type's entities as editable rows (DataEntry.jsx, D79)
//   #/metamodel/<model>/reports          tab Reports: standard reports and the report catalogue (ModelReports.jsx)
import { lazy, Suspense, useState } from "react";
import { can, keycloak, signedIn, canOn, myRolesOn, roleName } from "./auth";
import { CopyButton, LockBadge } from "./Library";
import { KindMark, MarksLegend, StatusMarks, readOnlyWhy } from "./ModelMarks";
import {
  CsvButton, EntityPage, EntityTypesTab, GraphTab, RelationshipsOfType, RelationshipTypesTab, Swatch, TypeEntitiesTable, useApi,
} from "./ModelViews";
import {
  attributeSpec, EditButton, entityTypeSpec, FailingChecks, lifecycleSpec, LockBanner, LockControl, mappingSpec,
  MetamodelHistory, PickLists, relationshipTypeSpec, removeAttributeSpec, ruleSpec, simpleSpec,
  changeableModel,
} from "./MetamodelEditor";
import ModelPeople from "./ModelPeople";
import ModelReports from "./ModelReports";
import { DataEntryTab } from "./DataEntry";
import { CopyBanner, DraftPage, Drafts, ModelActions, NewModelButton, UploadButton } from "./ModelOps";

// the diagram and its layout library load only when the ER diagram tab is opened
const MetamodelDiagram = lazy(() => import("./MetamodelDiagram"));
const ModelTree = lazy(() => import("./ModelTree"));

const go = (path) => { window.location.hash = path; };

// ---------------------------------------------------------------- model list
const KINDS = [["", "All kinds"], ["template", "Root metamodels"], ["reference", "Reference models"], ["project", "Project models"]];

// The model a model comes from in the hierarchy: the one it merges into, else the one it was created from
const upOf = (m) => m.parent_model_id || m.source_model_id || null;

function ModelList({ view }) {
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [archived, setArchived] = useState(false);
  const q = new URLSearchParams();
  if (search.trim()) q.set("search", search.trim());
  if (kind) q.set("kind", kind);
  if (!archived) q.set("archived", "false");
  const { data: models, error } = useApi(view === "drafts" ? null : `/api/v1/models?${q}`);
  const tree = view === "hierarchy";
  const drafts = view === "drafts";
  return (
    <section>
      <h1>Models</h1>
      <p className="quiet">
        Every model you may open. Root metamodels and reference models are also in the <a href="#/library">model library</a>.
      </p>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={!tree && !drafts} className={!tree && !drafts ? "tab on" : "tab"} onClick={() => go("/metamodel")}>List</button>
        <button role="tab" aria-selected={tree} className={tree ? "tab on" : "tab"} onClick={() => go("/metamodel/hierarchy")}>Hierarchy</button>
        <button role="tab" aria-selected={drafts} className={drafts ? "tab on" : "tab"} onClick={() => go("/metamodel/drafts")}>Metamodel drafts</button>
        <span className="tabs-right">
          <NewModelButton />
          <UploadButton />
        </span>
      </div>
      {drafts ? <Drafts /> : <>
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
      <MarksLegend />
      {error && <p className="status bad">{error}</p>}
      {!models && !error && <p>Loading...</p>}
      {models && tree && <Suspense fallback={<p>Loading the tree...</p>}><ModelTree models={models} /></Suspense>}
      {models && !tree && (
        <div className="scroll">
          <table className="grid-table models-table">
            <thead><tr><th>Model</th><th>Kind</th><th>Comes from</th><th>Owner</th><th>Status</th><th>Types</th><th>Entities</th><th>Relationships</th><th>Changed</th></tr></thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td>
                    <KindMark m={m} /> <a href={`#/metamodel/${m.id}`}><strong>{m.name}</strong></a>
                    {m.version_label && <span className="quiet"> {m.version_label}</span>}
                    <StatusMarks m={m} />
                    <br /><span className="quiet">{m.industry && `${m.industry} · `}{m.metamodel_name}</span>
                  </td>
                  <td>{m.kind_name}</td>
                  <td className="small">
                    {m.parent_model_id && <>merges into <a href={`#/metamodel/${m.parent_model_id}`}>{m.parent_model_name}</a></>}
                    {m.source_model_id && m.source_model_id !== m.parent_model_id && <>{m.parent_model_id && <br />}created from <a href={`#/metamodel/${m.source_model_id}`}>{m.source_model_name}</a></>}
                    {!m.parent_model_id && !m.source_model_id && <span className="quiet">-</span>}
                  </td>
                  <td>{m.owner || <span className="quiet">-</span>}</td>
                  <td>{m.lifecycle}</td>
                  <td className="num">{m.entity_type_count}</td>
                  <td className="num">{m.kind === "template" ? "-" : m.entity_count}</td>
                  <td className="num">{m.kind === "template" ? "-" : m.relationship_count}</td>
                  <td className="quiet">{new Date(m.modified_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {!models.length && <tr><td colSpan="9" className="quiet">{search || kind ? "No models match."
                : can("models.all") ? "There are no models yet."
                : "No models for you yet: a model's Model Admin gives you a role on its People tab."}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      </>}
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

function Allowed({ title, list, model, m, typeName, outgoing }) {
  const groups = grouped(list);
  const names = Object.keys(groups);
  if (!names.length) return null;
  const removeSpec = (a) => simpleSpec(
    `Remove mapping: ${outgoing ? `${typeName} ${a.verb} ${a.other_type}` : `${a.other_type} ${a.verb} ${typeName}`}`, "mapping.remove", { id: a.id },
    "Existing relationships of this kind are kept and show as outside the metamodel.", true, "Remove");
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
                    <span key={a.other_type_id} className="mapping">{i > 0 && ", "}<a href={`#/metamodel/${model}/type/${a.other_type_id}`}>{a.other_type}</a>
                      <EditButton model={model} m={m} label="×" className="tiny" title="Remove this mapping" spec={() => removeSpec(a)} /></span>
                  ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function TypeDetail({ model, m, mm, typeId, holdsContent }) {
  const { data: t, error } = useApi(`/api/v1/models/${model}/entity-types/${typeId}`);
  const { data: list } = useApi(holdsContent ? `/api/v1/models/${model}/entity-list?type=${typeId}` : null);
  const { data: pickLists } = useApi(changeableModel(m) ? `/api/v1/models/${model}/metamodel/pick-lists` : null);
  if (error) return <p className="status bad">{error}</p>;
  if (!t) return <p>Loading...</p>;
  const hasEntities = !!(list && list.length);
  const types = mm.layers.flatMap((l) => l.entity_types).filter((x) => x.status !== "retired");
  const retired = t.status === "retired";
  return (
    <div>
      <h2><Swatch colour={t.colour} /> {t.name} {retired && <span className="sev warning">retired</span>}</h2>
        <div className="toolbar ed-bar">
          <EditButton model={model} m={m} label="+ Attribute" spec={() => attributeSpec(t, pickLists || [], hasEntities)} />
          <EditButton model={model} m={m} label="+ Lifecycle" spec={() => lifecycleSpec(t)} />
          <EditButton model={model} m={m} label="+ Mapping" spec={() => mappingSpec(types, mm.relationship_types, t.id)} />
          <EditButton model={model} m={m} label="+ Rule" spec={() => ruleSpec(t)} />
          <span className="er-spacer" />
          <EditButton model={model} m={m} label="Change type" spec={() => entityTypeSpec(mm.layers, t)} />
          {retired
            ? <EditButton model={model} m={m} label="Restore" spec={simpleSpec(`Restore ${t.name}`, "entity_type.restore", { id: t.id }, "The type is offered again for new entities and its entities can be changed again.")} />
            : <EditButton model={model} m={m} label="Retire" spec={simpleSpec(`Retire ${t.name}`, "entity_type.retire", { id: t.id },
              `A retired type is no longer offered for new entities${hasEntities ? ` and its ${list.length} entities become read-only` : ""} until it is restored. Nothing is removed.`, true, "Retire")} />}
        </div>
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
        <thead><tr><th>Attribute</th><th>Type</th><th>Required</th><th>Default</th><th>Section</th><th>Values</th><th /></tr></thead>
        <tbody>
          {t.attributes.map((a) => (
            <tr key={a.code}>
              <td title={a.description}>{a.name}<br /><code className="quiet">{a.column_name}</code></td>
              <td>{a.data_type_name}{a.unit && ` (${a.unit})`}</td>
              <td>{a.is_required ? "Yes" : ""}</td>
              <td className="quiet">{a.default_value ?? ""}</td>
              <td>{a.section}</td>
              <td className="quiet">{a.pick_list_values.join(", ")}</td>
                <td className="nowrap row-actions">
                  <EditButton model={model} m={m} label="Change" className="small" spec={() => attributeSpec(t, pickLists || [], hasEntities, a)} />
                  <EditButton model={model} m={m} label="Remove" className="small" spec={() => removeAttributeSpec(t, a)} />
                </td>
            </tr>
          ))}
          {!t.attributes.length && <tr><td colSpan="7" className="quiet">No attributes yet.</td></tr>}
        </tbody>
      </table>
      {t.rules.length > 0 && (
        <>
          <h3>Validation rules</h3>
          <table className="grid-table">
            <thead><tr><th>Field</th><th>Rule</th><th>Parameters</th><th>Severity</th><th>Message</th><th /></tr></thead>
            <tbody>{t.rules.map((r, i) => (
              <tr key={i}>
                <td>{r.field}{r.all_types && <span className="quiet" title="Applies to every entity type"> (all types)</span>}</td><td>{r.rule}</td>
                <td className="quiet">{[r.param1, r.param2].filter(Boolean).join(" · ")}</td>
                <td><span className={`sev ${r.severity}`}>{r.severity}</span></td><td>{r.message}</td>
                  <td className="nowrap row-actions">
                    <EditButton model={model} m={m} label="Change" className="small" spec={() => ruleSpec(t, r)} />
                    <EditButton model={model} m={m} label="Remove" className="small" spec={simpleSpec(`Remove rule: ${r.message}`, "rule.remove", { id: r.id },
                      "Entities failing only this rule will pass again.", true, "Remove")} />
                  </td>
              </tr>))}</tbody>
          </table>
        </>
      )}
      <Allowed title={`From ${t.name} to other types`} list={t.outgoing} model={model} m={m} typeName={t.name} outgoing />
      <Allowed title={`From other types to ${t.name}`} list={t.incoming} model={model} m={m} typeName={t.name} />
    </div>
  );
}

const MM_VIEWS = [["", "Definition"], ["lists", "Pick lists"], ["history", "History and versions"]];

function MetamodelView({ model, m, typeId, holdsContent, sub }) {
  const { data: mm, error } = useApi(`/api/v1/models/${model}/metamodel`);
  if (error) return <p className="status bad">{error}</p>;
  if (!mm) return <p>Loading...</p>;
  const view = typeId ? "" : (sub || "");
  const seg = (
    <div className="seg small" role="tablist">
      {MM_VIEWS.map(([k, l]) => <button key={k} className={view === k ? "on" : ""} onClick={() => go(`/metamodel/${model}/metamodel${k ? `/${k}` : ""}`)}>{l}</button>)}
    </div>
  );
  if (view === "lists") return <>{seg}<PickLists model={model} m={m} /></>;
  if (view === "history") return <>{seg}<MetamodelHistory model={model} m={m} /></>;
  const types = mm.layers.flatMap((l) => l.entity_types).filter((x) => x.status !== "retired");
  return (
    <>
    {seg}
    <div className="toolbar">
      <span className="quiet">Metamodel <strong>version {m.metamodel_version}</strong>: what may be stored and how it is checked.
        {changeableModel(m) && canOn(model, "model.metamodel") ? " Every change publishes a new version." : ""}</span>
      <span className="er-spacer" />
      <EditButton model={model} m={m} label="+ Entity type" spec={() => entityTypeSpec(mm.layers)} />
      <EditButton model={model} m={m} label="+ Relationship type" spec={relationshipTypeSpec()} />
      <EditButton model={model} m={m} label="+ Mapping" spec={() => mappingSpec(types, mm.relationship_types)} />
      <span className="quiet small-note">
        {!changeableModel(m) ? "Read-only: create a model from it (Actions) to change a copy."
          : !canOn(model, "model.metamodel") ? "Read-only for you: hover a button to see the role it needs."
          : "+ Attribute and + Rule: on an entity type's page"}
      </span>
    </div>
    <div className="mm">
      <div className="layers">
        {mm.layers.map((l) => (
          <div key={l.id} className="layer">
            <h3><Swatch colour={l.colour} /> {l.name}</h3>
            <ul>
              {l.entity_types.map((t) => (
                <li key={t.id} className={t.status === "retired" ? "retired" : ""}>
                  <a href={`#/metamodel/${model}/type/${t.id}`} className={t.id === typeId ? "current" : ""}>{t.name}</a>
                  {t.entity_count > 0 && <span className="count">{t.entity_count}</span>}
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="layer">
          <h3>Relationship types</h3>
          <ul>{mm.relationship_types.map((r) => (
            <li key={r.id} title={r.description} className={r.status === "retired" ? "retired" : ""}>
              <span>{r.name} <span className="quiet">({r.verb})</span></span>
                <span className="row-actions">
                  <EditButton model={model} m={m} label="✎" className="tiny" title={`Change ${r.name}`} spec={() => relationshipTypeSpec(r)} />
                  {r.status === "retired"
                    ? <EditButton model={model} m={m} label="↺" className="tiny" title={`Restore ${r.name}`} spec={simpleSpec(`Restore ${r.name}`, "relationship_type.restore", { id: r.id }, "")} />
                    : <EditButton model={model} m={m} label="×" className="tiny" title={`Remove ${r.name}`} spec={simpleSpec(`Remove relationship type ${r.name}`, "relationship_type.remove", { id: r.id },
                      `Every ${r.name} relationship in this model is removed with it. Each stays in the history of the entities it connected. Check impact shows how many.`, true, "Remove")} />}
                </span>
            </li>))}</ul>
        </div>
      </div>
      <div className="detail">
        {typeId ? <TypeDetail model={model} m={m} mm={mm} typeId={typeId} holdsContent={holdsContent} />
          : <p className="quiet">Choose an entity type on the left.</p>}
      </div>
    </div>
    </>
  );
}

// ---------------------------------------------------------------- one model
// Models / grandparent / parent / this model: the way up the hierarchy (the models you may read)
function Lineage({ m }) {
  const { data: all } = useApi("/api/v1/models");
  const chain = [];
  if (all) {
    const byId = Object.fromEntries(all.map((x) => [x.id, x]));
    let up = upOf(m);
    while (up && byId[up] && !chain.some((c) => c.id === up) && chain.length < 20) { chain.unshift(byId[up]); up = upOf(byId[up]); }
  }
  return (
    <p className="quiet breadcrumb">
      <a href="#/metamodel">Models</a> (<a href="#/metamodel/hierarchy">hierarchy</a>)
      {chain.map((c) => <span key={c.id}> / <a href={`#/metamodel/${c.id}`}>{c.name}</a></span>)} / {m.name}
    </p>
  );
}

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
    ...(holdsContent ? [["types", "Entity types", m.entity_type_count], ["entry", "Data entry", null], ["rels", "Relationship types", null],
      ["graph", "Graph", null], ["checks", "Failing checks", null]] : []),
    ["metamodel", "Metamodel", null], ["diagram", "ER diagram", null], ["reports", "Reports", null],
    ...(changeableModel(m) ? [["people", "People", null]] : []),
  ];
  return (
    <section className="model-page">
      <Lineage m={m} />
      <div className="model-head">
        <KindMark m={m} big />
        <h1>{m.name} {m.version_label && <span className="quiet">{m.version_label}</span>}</h1>
        <StatusMarks m={m} />
        <LockBadge model={m} />
        {m.is_locked && <CopyButton m={m} />}
        <ModelActions m={m} />
        <LockControl model={model} m={m} />
        {myRolesOn(model).length > 0 && <span className="rchip on" title="Your roles on this model">You: {myRolesOn(model).map(roleName).join(", ")}</span>}
        <button className="linkish" onClick={() => setShowProps((x) => !x)}>{showProps ? "Hide details" : "Details"}</button>
      </div>
      <p className="quiet">
        {m.kind_name}{readOnlyWhy(m) ? ` · ${m.is_locked ? "read-only" : "read-only for you"}` : ""} · {m.metamodel_name} · {m.entity_type_count} entity types
        {holdsContent && ` · ${m.entity_count} entities · ${m.relationship_count} relationships`}
        {m.parent_model_id && <> · merges into <a href={`#/metamodel/${m.parent_model_id}`}><strong>{m.parent_model_name}</strong></a></>}
        {m.source_model_id && m.source_model_id !== m.parent_model_id && <> · created from <a href={`#/metamodel/${m.source_model_id}`}>{m.source_model_name}</a></>}
        {(m.kind === "reference" || m.kind === "template") && <> · in the <a href={`#/library/${m.id}`}>library</a></>}
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
      <LockBanner m={m} />
      <CopyBanner m={m} />
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
        : tab === "checks" ? <FailingChecks model={model} m={m} />
        : tab === "people" ? <ModelPeople model={model} m={m} />
        : tab === "reports" ? <ModelReports model={model} m={m} />
        : tab === "entry" ? <DataEntryTab key={itemId || "none"} model={model} m={m} typeFromUrl={itemId || ""} />
        : tab === "diagram" ? <Suspense fallback={<p>Loading the diagram...</p>}><MetamodelDiagram model={model} focus={itemId || null} /></Suspense>
        : <MetamodelView model={model} m={m} typeId={v === "type" ? itemId : null} holdsContent={holdsContent} sub={v === "metamodel" ? itemId : null} />}
      </div>
    </section>
  );
}

export default function Metamodel({ route }) {
  if (!signedIn()) {
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
  if (model === "hierarchy") return <ModelList view="hierarchy" />;
  if (model === "drafts") return view ? <DraftPage id={view} /> : <ModelList view="drafts" />;
  return model ? <ModelPage model={model} view={view} itemId={itemId} sub={sub} /> : <ModelList />;
}
