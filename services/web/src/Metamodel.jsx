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
//   #/metamodel/<model>/grid[/<type>|/relationships]   tab Grid: spreadsheet-style editing (GridPages.jsx, phase 7)
//   #/metamodel/<model>/metamodel/grids/<kind>   metamodel grids: entity types, attributes, mappings... (phase 7)
//   #/metamodel/<model>/reports          tab Reports: standard reports and the report catalogue (ModelReports.jsx)
//   #/metamodel/<model>/changes[/requests|/history[/<commit>]]   tab Changes: uncommitted changes, commit requests, commits, merges (Changes.jsx, phase 8)
//   #/metamodel/<model>/tags             tab Tags: frozen snapshots of the model (Versions.jsx, phase 8.3)
//   #/metamodel/<model>/merge            tab Merge: merge an uploaded model into this one, conflicts decided (Merge.jsx, phase 8)
//   #/metamodel/<model>/viewpoints[/<code>[/<view>]]   tab Viewpoints: the model through VP-01 to VP-26 and your own (Viewpoints.jsx, phase 8.2)
import PinButton from "./PinButton";
import { lazy, Suspense, useEffect, useState } from "react";
import { apiFetch, can, keycloak, signedIn, canOn, myRolesOn, roleName } from "./auth";
import { CopyButton, LockBadge } from "./Library";
import { KindMark, MarksLegend, ModelStateBadge, StatusMarks, readOnlyWhy } from "./ModelMarks";
import { RecalculateButton } from "./QualityBits";
import { MetamodelTree } from "./Trees";
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
import SheetsTab from "./Sheets";
import ViewpointsTab from "./Viewpoints";
import ChangesTab, { LiveCommits, usePendingCount } from "./Changes";
import MergeTab from "./Merge";
import { TagPage, TagsTab } from "./Versions";
import { DataEntryTab } from "./DataEntry";
import { ChangeDocumentsTab, PushDownTab } from "./Notifications";
import { ModelBackupsTab } from "./Backups";
import QualityTab from "./Quality";
import { GridTab, MetamodelGrids } from "./GridPages";
import { CopyBanner, DraftPage, Drafts, IconDialog, ModelActions, NewModelButton, UploadButton } from "./ModelOps";
import { fmtDate } from "./fmt";
import { modelOrigin } from "./modelOrigin";

// what kind of model it is, from where it came (owner, 7 Nov 2026)
export function OriginChip({ m }) {
  const o = modelOrigin(m);
  return o.key ? <span className={`chip origin-${o.key}`} title={o.text}>{o.label}</span> : null;
}

// the diagram and its layout library load only when the ER diagram tab is opened
const MetamodelDiagram = lazy(() => import("./MetamodelDiagram"));
const ModelTree = lazy(() => import("./ModelTree"));

const go = (path) => { window.location.hash = path; };

// ---------------------------------------------------------------- model list
const KINDS = [["", "All kinds"], ["template", "Root metamodels"], ["reference", "Reference models"], ["project", "Project models"]];

// The model a model comes from in the hierarchy: the one it merges into, else the one it was created from
const upOf = (m) => m.parent_model_id || m.source_model_id || null;

export function ModelList({ view, admin = false }) {
  const base = admin ? "model-admin" : "metamodel";
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [archived, setArchived] = useState(false);
  // list or tiles, remembered for this person in this browser (owner, 6 Nov 2026)
  const [tiles, setTilesState] = useState(() => { try { return localStorage.getItem("eax.models.view") === "tiles"; } catch { return false; } });
  const setTiles = (v) => { setTilesState(v); try { localStorage.setItem("eax.models.view", v ? "tiles" : "list"); } catch { /* per-viewer convenience only */ } };
  const q = new URLSearchParams();
  if (search.trim()) q.set("search", search.trim());
  if (kind) q.set("kind", kind);
  if (!archived) q.set("archived", "false");
  const { data: models, error } = useApi(view === "drafts" ? null : `/api/v1/models?${q}`);
  const tree = view === "hierarchy";
  const drafts = view === "drafts";
  return (
    <section>
      <h1>{admin ? "Model admin" : "Models"}</h1>
      <p className="quiet">
        {admin ? <>Start a new model or upload one, or pick a model to run its wizards: copy and derive, merge into the parent and
          freeze, propagate, split, extend or upgrade the metamodel, lock, freeze, tag, promote, hand over, download, archive or delete.
          Entering data and reports are on the model's own page (<a href="#/work">Architecture work</a>).</>
          : <>Every model you may open. Root metamodels and reference models are also in the <a href="#/library">model library</a>.</>}
      </p>
      <div className="tabs" role="tablist">
        {admin && <button role="tab" aria-selected={false} className="tab" onClick={() => go("/model-admin")}>Wizards</button>}
        <button role="tab" aria-selected={!tree && !drafts} className={!tree && !drafts ? "tab on" : "tab"} onClick={() => go(admin ? "/model-admin/list" : `/${base}`)}>{admin ? "Models" : "List"}</button>
        <button role="tab" aria-selected={tree} className={tree ? "tab on" : "tab"} onClick={() => go(`/${base}/hierarchy`)}>Hierarchy</button>
        <button role="tab" aria-selected={drafts} className={drafts ? "tab on" : "tab"} onClick={() => go(admin ? "/model-admin/drafts" : "/metamodel/drafts")}>Metamodel drafts</button>
        <span className="tabs-right">
          <NewModelButton admin={admin} />
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
        {!tree && <div className="seg small" role="tablist" aria-label="Show as">
          <button className={!tiles ? "on" : ""} onClick={() => setTiles(false)} title="A table: one row per model">☰ List</button>
          <button className={tiles ? "on" : ""} onClick={() => setTiles(true)} title="A tile per model, with its icon">▦ Tiles</button>
        </div>}
        {models && <CsvButton name="EA Explorer models" rows={() => [["Model", "Version", "Kind", "Industry", "Owner", "Status", "Locked", "Created from", "Merges into", "Entity types", "Entities", "Relationships", "Changed"],
          ...models.map((m) => [m.name, m.version_label, m.kind_name, m.industry, m.owner, m.lifecycle, m.is_locked ? "yes" : "", m.source_model_name, m.parent_model_name,
            m.entity_type_count, m.entity_count, m.relationship_count, m.modified_at])]} />}
      </div>
      <MarksLegend />
      <WaitingDrafts />
      {error && <p className="status bad">{error}</p>}
      {!models && !error && <p>Loading...</p>}
      {models && tree && <Suspense fallback={<p>Loading the tree...</p>}><ModelTree models={models} base={base} /></Suspense>}
      {models && !tree && tiles && <ModelTiles models={models} base={base} empty={search || kind ? "No models match." : "There are no models for you yet."} />}
      {models && !tree && !tiles && (
        <div className="scroll">
          <table className="grid-table models-table">
            <thead><tr><th>Model</th><th>Kind</th><th>Comes from</th><th>Owner</th><th>State</th><th className="num">Types</th><th className="num">Entities</th><th className="num">Relationships</th><th>Changed</th></tr></thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td>
                    <KindMark m={m} /> <a href={`#/${base}/${m.id}`}><strong>{m.name}</strong></a>
                    {m.version_label && <span className="quiet"> {m.version_label}</span>}
                    <StatusMarks m={m} />
                    <br /><span className="quiet">{m.industry && `${m.industry} · `}{m.metamodel_name}</span>
                  </td>
                  <td>{m.kind_name}<br /><OriginChip m={m} /></td>
                  <td className="small">
                    {m.parent_model_id && <>merges into <a href={`#/metamodel/${m.parent_model_id}`}>{m.parent_model_name}</a></>}
                    {m.source_model_id && m.source_model_id !== m.parent_model_id && <>{m.parent_model_id && <br />}created from <a href={`#/metamodel/${m.source_model_id}`}>{m.source_model_name}</a>{m.source_tag_name ? ` at the tag ${m.source_tag_name}` : ""}</>}
                    {!m.parent_model_id && !m.source_model_id && <span className="quiet">-</span>}
                  </td>
                  <td>{m.owner || <span className="quiet">-</span>}</td>
                  <td className="nowrap"><ModelStateBadge m={m} /></td>
                  <td className="num">{m.entity_type_count}</td>
                  <td className="num">{m.kind === "template" ? "-" : m.entity_count}</td>
                  <td className="num">{m.kind === "template" ? "-" : m.relationship_count}</td>
                  <td className="quiet">{fmtDate(m.modified_at)}</td>
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

// the models as tiles: the icon large, the name, kind and state marks, what it comes from and its counts
function ModelTiles({ models, empty, base = "metamodel" }) {
  if (!models.length) return <p className="quiet">{empty}</p>;
  return (
    <div className="model-tiles">
      {models.map((m) => (
        <a key={m.id} className={`model-tile ${m.kind}${m.lifecycle === "archived" ? " archived" : ""}`} href={`#/${base}/${m.id}`}>
          <div className="model-tile-head"><KindMark m={m} big /><span><ModelStateBadge m={m} /> <StatusMarks m={m} /></span></div>
          <strong className="model-tile-name">{m.name}{m.version_label && <span className="quiet"> {m.version_label}</span>}</strong>
          <span className="small quiet">{m.kind_name}{m.industry ? ` · ${m.industry}` : ""} · {m.metamodel_name} <OriginChip m={m} /></span>
          {m.description && <span className="small model-tile-desc">{m.description}</span>}
          <span className="small">{m.entity_type_count} types{m.kind !== "template" ? ` · ${m.entity_count} entities · ${m.relationship_count} relationships` : ""}</span>
          <span className="small quiet">{m.parent_model_name ? `merges into ${m.parent_model_name}` : m.source_model_name ? `from ${m.source_model_name}` : ""}
            {" · "}changed {fmtDate(m.modified_at)}</span>
        </a>
      ))}
    </div>
  );
}

// Draft models waiting for my approval (D134, D165): approve, send back or reject on the model's Actions menu
function WaitingDrafts() {
  const { data } = useApi("/api/v1/drafts/waiting");
  if (!data?.length) return null;
  return (
    <div className="lock-banner draft-banner">
      <strong>{data.length} draft model{data.length === 1 ? "" : "s"} waiting for your approval</strong>
      <ul>
        {data.map((d) => (
          <li key={d.id}><a href={`#/model-admin/${d.id}`}>{d.name}</a> <span className="quiet">· asked by {d.requested_by || d.created_by}
            {d.requested_at ? ` on ${fmtDate(d.requested_at)}` : ""}{d.note ? `: “${d.note}”` : ""}</span></li>
        ))}
      </ul>
      <span className="quiet small">Open one and use its Library and publishing wizards: Approve and publish, Send back, or Reject.</span>
    </div>
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
      {holdsContent && <p><a className="button" href={`#/metamodel/${model}/types/${typeId}`} title="The entity grid of this type, with its values">
        ▦ Open the {t.name} entities (grid){list ? ` · ${list.length}` : ""}</a></p>}
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

const MM_VIEWS = [["", "Definition"], ["tree", "Tree"], ["grids", "Grids"], ["lists", "Pick lists"], ["history", "History and versions"]];

// find an entity of this model by name from the metamodel tab (owner, 8 Nov 2026): it opens on its own page
function EntityFinder({ model }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState(null);
  useEffect(() => {
    const t = q.trim();
    if (t.length < 2) { setHits(null); return undefined; }
    let live = true;
    const h = setTimeout(() => apiFetch(`/api/v1/search?q=${encodeURIComponent(t)}&model=${model}&limit=12`)
      .then((r) => live && setHits(r.results || [])).catch(() => live && setHits([])), 250);
    return () => { live = false; clearTimeout(h); };
  }, [q, model]);
  return (
    <span className="entity-finder">
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find an entity by name" aria-label="Find an entity by name" />
      {hits && (
        <div className="entity-finder-list" role="listbox">
          {!hits.length ? <div className="quiet small">Nothing found.</div> : hits.map((h) => (
            <a key={h.id} href={`#/metamodel/${model}/entity/${h.id}`} onClick={() => setQ("")}>
              <Swatch colour={h.colour} /> <b>{h.name}</b> <span className="quiet small">{h.display_id} · {h.entity_type}</span></a>
          ))}
        </div>
      )}
    </span>
  );
}

function MetamodelView({ model, m, typeId, holdsContent, sub, gridKind }) {
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
  if (view === "tree") return <>{seg}<MetamodelTree model={model} m={m} /></>;
  if (view === "grids") return <>{seg}<MetamodelGrids key={gridKind || "entity_types"} model={model} m={m} kindFromUrl={gridKind || "entity_types"} /></>;
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
      {holdsContent && <EntityFinder model={model} />}
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

// tab Hierarchy: where this model comes from (every model up to the root it was created from or merges into) and
// the models made from it, drawn as the model tree with this model outlined in red
function ModelLineageTab({ model, m }) {
  const { data: models, error } = useApi("/api/v1/models?archived=true");
  if (error) return <p className="status bad">{error}</p>;
  if (!models) return <p>Loading...</p>;
  const byId = Object.fromEntries(models.map((x) => [x.id, x]));
  const up = (x) => x.parent_model_id || x.source_model_id || null;
  const keep = new Set([model]);
  for (let x = byId[model]; x && up(x) && byId[up(x)] && !keep.has(up(x)); x = byId[up(x)]) keep.add(up(x));
  const chain = [...keep].map((id) => byId[id]).filter(Boolean).reverse();
  models.forEach((x) => { if (descendsFrom(x, model, byId, up)) keep.add(x.id); });
  const shown = models.filter((x) => keep.has(x.id));
  const below = shown.length - chain.length;
  return (
    <div>
      <p className="quiet">
        Where {m.name} comes from: {chain.map((x, i) => <span key={x.id}>{i > 0 && " → "}{x.id === model ? <b>{x.name}</b> : <a href={`#/metamodel/${x.id}`}>{x.name}</a>}</span>)}
        {below > 0 ? `, and the ${below} model${below > 1 ? "s" : ""} made from it below.` : "."} A solid line merges into the model above;
        a dashed one was created from it. Click a box to open that model.
      </p>
      <Suspense fallback={<p>Loading the tree...</p>}><ModelTree models={shown} focus={model} /></Suspense>
    </div>
  );
}

function descendsFrom(x, root, byId, up) {
  for (let y = x, n = 0; y && n < 50; y = byId[up(y)], n += 1) if (up(y) === root) return true;
  return false;
}

function ModelPage({ model, view, itemId, sub }) {
  const { data: m, error } = useApi(`/api/v1/models/${model}`);
  const [showProps, setShowProps] = useState(false);
  const [iconOpen, setIconOpen] = useState(false);
  const pending = usePendingCount(model, m);
  if (error) return <section><p className="status bad">{error}</p><a href="#/metamodel">All models</a></section>;
  if (!m) return <section><p>Loading...</p></section>;
  const holdsContent = m.kind !== "template";
  const v = view === "relationships" ? "rels" : view === "sheets" ? "import" : view;   // older links
  const tab = !v ? (holdsContent ? "types" : "metamodel")
    : v === "type" ? "metamodel" : v === "entity" ? "types" : v;
  // every tab the model page always had (the owner wants them all here); Model admin has the same admin tabs and the wizards
  const tabs = [
    ...(holdsContent ? [["types", "Entity types", m.entity_type_count], ["entry", "Data entry", null], ["grid", "Grid", null], ["rels", "Relationship types", null],
      ["graph", "Graph", null], ["viewpoints", "Viewpoints", null], ["checks", "Failing checks", null]] : []),
    ...(m.kind === "project" ? [["quality", "Quality", null]] : []),
    ...(m.kind === "project" ? [["changes", pending ? `Changes (${pending})` : "Changes", null], ["merge", "Merge", null]] : []),
    ...(holdsContent ? [["tags", "Tags", null], ["import", "Import and export", null]] : []),
    ["metamodel", "Metamodel", null],
    ...(m.kind === "project" || m.kind === "template" ? [["pushdown", "Push down", null]] : []),
    ["documents", "Change documents", null],
    ["diagram", "ER diagram", null], ["reports", "Reports", null], ["hierarchy", "Hierarchy", null],
    ...(changeableModel(m) ? [["people", "People", null]] : []),
    ...(canOn(model, "model.metamodel") && m.kind !== "template" ? [["backups", "Backups", null]] : []),
  ];
  const mayAdmin = canOn(model, "model.lock") || can("models.delete") || ((m.kind === "reference" || m.kind === "template") && can("library.curate"));
  return (
    <section className="model-page">
      <Lineage m={m} />
      <div className="model-head">
        {canOn(model, "model.lock") || can("models.delete")
          ? <button className="linkish icon-edit" onClick={() => setIconOpen(true)} title="Change the model's icon: pick one from the library or upload your own">
            <KindMark m={m} big />{!m.icon && <span className="icon-add">+ icon</span>}<span className="icon-pencil" aria-hidden="true">✎</span></button>
          : <KindMark m={m} big />}
        {iconOpen && <IconDialog m={m} onClose={() => setIconOpen(false)} />}
        <h1>{m.name} {m.version_label && <span className="quiet">{m.version_label}</span>}</h1>
        <PinButton k="model" x={m} />
        <StatusMarks m={m} />
        <LockBadge model={m} />
        {m.frozen_at && <span className="rag off" title={m.frozen_note || ""}>frozen</span>}
        {m.is_locked && <CopyButton m={m} />}
        <ModelActions m={m} />
        {!m.frozen_at && <LockControl model={model} m={m} />}
        {mayAdmin && <a className="button" href={`#/model-admin/${model}`} title="Model admin: every model wizard (copy, merge, freeze, split, extend...) for this model">⚙ Model wizards</a>}
        {myRolesOn(model).length > 0 && <span className="rchip on" title="Your roles on this model">You: {myRolesOn(model).map(roleName).join(", ")}</span>}
        {m.kind === "project" && m.lifecycle !== "archived" && <RecalculateButton model={model} />}
        <button className="linkish" onClick={() => setShowProps((x) => !x)}>{showProps ? "Hide details" : "Details"}</button>
      </div>
      <p className="quiet">
        <OriginChip m={m} /> {m.kind_name}{readOnlyWhy(m) ? ` · ${m.is_locked ? "read-only" : "read-only for you"}` : ""} · {m.metamodel_name} · {m.entity_type_count} entity types
        {holdsContent && ` · ${m.entity_count} entities · ${m.relationship_count} relationships`}
        {m.parent_model_id && <> · merges into <a href={`#/metamodel/${m.parent_model_id}`}><strong>{m.parent_model_name}</strong></a></>}
        {m.source_model_id && m.source_model_id !== m.parent_model_id && <> · created from <a href={`#/metamodel/${m.source_model_id}`}>{m.source_model_name}</a>{m.source_tag_name ? ` at the tag ${m.source_tag_name}` : ""}</>}
        {(m.kind === "reference" || m.kind === "template") && <> · in the <a href={`#/library/${m.id}`}>library</a></>}
      </p>
      {showProps && (
        <div className="model-props-box">
          {m.description && <p>{m.description}</p>}
          <p className="quiet">
            Owner {m.owner || "-"} · {m.lifecycle}{m.industry && ` · ${m.industry}`}
            {m.source_model_id && <> · created from <a href={`#/metamodel/${m.source_model_id}`}>{m.source_model_name}</a></>}
            {m.parent_model_id && <> · merges into <a href={`#/metamodel/${m.parent_model_id}`}>{m.parent_model_name}</a></>} ·
            created {fmtDate(m.created_at)} by {m.created_by} ·
            changed {fmtDate(m.modified_at)} by {m.modified_by}
          </p>
        </div>
      )}
      <LockBanner m={m} />
      <CopyBanner m={m} />
      <LiveCommits model={model} m={m} />
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
        : tab === "viewpoints" ? <ViewpointsTab model={model} m={m} code={itemId} sub={sub} />
        : tab === "checks" ? <FailingChecks model={model} m={m} />
        : tab === "quality" ? <QualityTab model={model} m={m} drill={itemId} value={sub} />
        : tab === "hierarchy" ? <ModelLineageTab model={model} m={m} />
        : tab === "changes" ? <ChangesTab model={model} m={m} sub={itemId} itemId={sub} />
        : tab === "reports" ? <ModelReports model={model} m={m} />
        : tab === "import" ? <SheetsTab model={model} m={m} sub={itemId} itemId={sub} />
        : tab === "grid" ? <GridTab key={itemId || "none"} model={model} m={m} typeFromUrl={itemId || ""} />
        : tab === "entry" ? <DataEntryTab key={itemId || "none"} model={model} m={m} typeFromUrl={itemId || ""} />
        : v === "type" ? <MetamodelView model={model} m={m} typeId={itemId} holdsContent={holdsContent} />
        : ADMIN_VIEWS.includes(tab) ? <ModelAdminPanel model={model} m={m} tab={tab} itemId={itemId} sub={sub} />
        : <Suspense fallback={<p>Loading the diagram...</p>}><MetamodelDiagram model={model} focus={tab === "diagram" ? itemId || null : null} /></Suspense>}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- the admin parts of a model (shown in Model admin, D285)
export const ADMIN_VIEWS = ["metamodel", "people", "merge", "tags", "pushdown", "documents", "backups"];

export function ModelAdminPanel({ model, m, tab, itemId, sub }) {
  const holdsContent = m.kind !== "template";
  return tab === "people" ? <ModelPeople model={model} m={m} />
    : tab === "merge" ? <MergeTab model={model} m={m} />
    : tab === "pushdown" ? <PushDownTab model={model} m={m} />
    : tab === "documents" ? <ChangeDocumentsTab model={model} m={m} />
    : tab === "backups" ? <ModelBackupsTab model={model} />
    : tab === "tags" ? (itemId ? <TagPage key={itemId} model={model} m={m} tagId={itemId} entityId={sub} /> : <TagsTab model={model} m={m} />)
    : <MetamodelView model={model} m={m} typeId={null} holdsContent={holdsContent} sub={itemId || null}
        gridKind={itemId === "grids" ? sub : null} />;
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
  const [, , model, view, itemId, sub] = (route || "").replace(/^#/, "").split("?")[0].split("/");
  if (model === "hierarchy") return <ModelList view="hierarchy" />;
  if (model === "drafts") return view ? <DraftPage id={view} /> : <ModelList view="drafts" />;
  return model ? <ModelPage model={model} view={view} itemId={itemId} sub={sub} /> : <ModelList />;
}
