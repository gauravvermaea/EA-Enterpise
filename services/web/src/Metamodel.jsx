// Models, their metamodel and their content (build phase 1, read only).
//   #/metamodel                        every model, as links
//   #/metamodel/<model>                the model: entities and relationships, or its metamodel
//   #/metamodel/<model>/entity/<id>    one entity, with its attributes and relationships
//   #/metamodel/<model>/type/<id>      one entity type, with its attributes, rules and allowed relationships
import { useEffect, useMemo, useState } from "react";
import { apiFetch, keycloak } from "./auth";

const go = (path) => { window.location.hash = path; };

function Swatch({ colour }) {
  return <span className="swatch" style={{ background: `#${colour || "eee"}` }} />;
}

function useApi(path) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    if (!path) return;
    let live = true;
    setState({ data: null, error: null });
    apiFetch(path)
      .then((data) => live && setState({ data, error: null }))
      .catch((e) => live && setState({ data: null, error: e.message }));
    return () => { live = false; };
  }, [path]);
  return state;
}

// ---------------------------------------------------------------- model list
function ModelList() {
  const { data: models, error } = useApi("/api/v1/models");
  return (
    <section>
      <h1>Models and metamodels</h1>
      <p className="quiet">Read only in this build. Open a model to see its entities, relationships and metamodel.</p>
      {error && <p className="status bad">{error}</p>}
      {!models && !error && <p>Loading...</p>}
      <div className="grid">
        {models?.map((m) => (
          <a key={m.id} className="tile live" href={`#/metamodel/${m.id}`}>
            <h3>{m.name}</h3>
            <p>{m.description}</p>
            <span className="badge">
              {m.kind_name}{m.is_locked ? " · read-only" : ""} · {m.metamodel_name} · {m.entity_type_count} types
              {m.kind !== "template" && ` · ${m.entity_count} entities · ${m.relationship_count} relationships`}
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- entities and relationships
function EntityLink({ model, id, children }) {
  return <a href={`#/metamodel/${model}/entity/${id}`}>{children}</a>;
}

function EntityDetail({ model, entityId }) {
  const { data: e, error } = useApi(`/api/v1/models/${model}/entities/${entityId}`);
  if (error) return <p className="status bad">{error}</p>;
  if (!e) return <p>Loading...</p>;
  const filled = e.attributes.filter((a) => a.value !== null && a.value !== "");
  const empty = e.attributes.filter((a) => a.value === null || a.value === "");
  const out = e.relationships.filter((r) => r.direction === "outgoing");
  const inc = e.relationships.filter((r) => r.direction === "incoming");
  return (
    <div>
      <h2><Swatch colour={e.colour} /> {e.name}</h2>
      <p className="quiet">
        {e.display_id} · {e.entity_type} ({e.layer}) · {e.status} · version {e.row_version}, changed by {e.modified_by}
      </p>
      {e.description && <p>{e.description}</p>}
      {e.parent_name && <p>Part of <EntityLink model={model} id={e.parent_id}>{e.parent_name}</EntityLink></p>}

      <h3>Attributes</h3>
      <table className="grid-table">
        <tbody>
          {filled.map((a) => (
            <tr key={a.code}><th>{a.name}</th><td>{a.value}{a.unit && ` ${a.unit}`}</td></tr>
          ))}
          {!filled.length && <tr><td className="quiet">No attribute values yet.</td></tr>}
        </tbody>
      </table>
      {empty.length > 0 && <p className="quiet">Not filled in: {empty.map((a) => a.name).join(", ")}.</p>}

      <h3>Relationships ({e.relationships.length})</h3>
      {!e.relationships.length && <p className="quiet">None yet.</p>}
      {e.relationships.length > 0 && (
        <table className="grid-table">
          <thead><tr><th>Relationship</th><th>Entity</th><th>Type</th></tr></thead>
          <tbody>
            {[...out, ...inc].map((r) => (
              <tr key={`${r.id}-${r.direction}`}>
                <td>{r.direction === "outgoing" ? `${e.name} ${r.verb} →` : `← ${r.verb} ${e.name}`}</td>
                <td><Swatch colour={r.other_colour} /> <EntityLink model={model} id={r.other_id}>{r.other_name}</EntityLink>
                  <span className="quiet"> {r.other_display_id}</span></td>
                <td>{r.other_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {e.children.length > 0 && (
        <>
          <h3>Parts ({e.children.length})</h3>
          <ul>{e.children.map((c) => <li key={c.id}><EntityLink model={model} id={c.id}>{c.name}</EntityLink> <span className="quiet">{c.display_id}</span></li>)}</ul>
        </>
      )}
    </div>
  );
}

function AllRelationships({ model }) {
  const { data, error } = useApi(`/api/v1/models/${model}/relationships`);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  if (!data.length) return <p className="quiet">No relationships in this model yet.</p>;
  return (
    <div className="scroll">
      <table className="grid-table">
        <thead><tr><th>Source</th><th>Relationship</th><th>Target</th></tr></thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.id}>
              <td><EntityLink model={model} id={r.source_id}>{r.source_name}</EntityLink><br /><span className="quiet">{r.source_type}</span></td>
              <td>{r.verb}<br /><span className="quiet">{r.relationship_type}</span></td>
              <td><EntityLink model={model} id={r.target_id}>{r.target_name}</EntityLink><br /><span className="quiet">{r.target_type}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Content({ model, entityId }) {
  const { data: entities, error } = useApi(`/api/v1/models/${model}/entity-list`);
  const [filter, setFilter] = useState("");
  const groups = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const out = [];
    for (const e of entities || []) {
      if (f && !`${e.name} ${e.display_id} ${e.entity_type}`.toLowerCase().includes(f)) continue;
      let g = out.find((x) => x.type === e.entity_type);
      if (!g) out.push(g = { type: e.entity_type, colour: e.colour, items: [] });
      g.items.push(e);
    }
    return out;
  }, [entities, filter]);

  if (error) return <p className="status bad">{error}</p>;
  if (!entities) return <p>Loading...</p>;
  if (!entities.length) return <p className="quiet">This model has no entities yet. Data entry arrives in build phase 6.</p>;
  return (
    <div className="mm">
      <div className="layers">
        <input className="search" placeholder="Filter entities" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <a href={`#/metamodel/${model}/relationships`} className="quiet">All relationships</a>
        {groups.map((g) => (
          <div key={g.type} className="layer">
            <h3><Swatch colour={g.colour} /> {g.type} <span className="count">{g.items.length}</span></h3>
            <ul>
              {g.items.map((e) => (
                <li key={e.id}>
                  <a href={`#/metamodel/${model}/entity/${e.id}`} className={e.id === entityId ? "current" : ""}>{e.name}</a>
                  <span className="count" title="relationships">{e.relationship_count}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="detail">
        {entityId === "relationships" ? <><h2>All relationships</h2><AllRelationships model={model} /></>
          : entityId ? <EntityDetail model={model} entityId={entityId} />
          : <p className="quiet">Choose an entity on the left, or open <a href={`#/metamodel/${model}/relationships`}>all relationships</a>.</p>}
      </div>
    </div>
  );
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
        SQL <code>eax.get_entity('{t.name}')</code>
      </p>
      {holdsContent && list && (
        <p>{list.length ? <>Entities: {list.map((e, i) => <span key={e.id}>{i > 0 && ", "}<EntityLink model={model} id={e.id}>{e.name}</EntityLink></span>)}</>
          : <span className="quiet">No {t.name} entities in this model yet.</span>}</p>
      )}
      <h3>Attributes</h3>
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

function MetamodelView({ model, typeId, holdsContent }) {
  const { data: mm, error } = useApi(`/api/v1/models/${model}/metamodel`);
  if (error) return <p className="status bad">{error}</p>;
  if (!mm) return <p>Loading...</p>;
  return (
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
  );
}

// ---------------------------------------------------------------- one model
function ModelPage({ model, view, itemId }) {
  const { data: m, error } = useApi(`/api/v1/models/${model}`);
  if (error) return <section><p className="status bad">{error}</p><a href="#/metamodel">All models</a></section>;
  if (!m) return <section><p>Loading...</p></section>;
  const holdsContent = m.kind !== "template";
  const tab = view === "type" || !holdsContent ? "metamodel" : (view || "content");
  return (
    <section>
      <p className="quiet"><a href="#/metamodel">Models</a> / {m.name}</p>
      <h1>{m.name}</h1>
      <p className="quiet">
        {m.kind_name}{m.is_locked ? " · read-only" : ""} · {m.metamodel_name} · {m.entity_type_count} entity types
        {holdsContent && ` · ${m.entity_count} entities · ${m.relationship_count} relationships`}
        {m.parent_model_name && ` · created from ${m.parent_model_name}`}
      </p>
      <div className="tabs">
        {holdsContent && (
          <button className={tab !== "metamodel" ? "tab on" : "tab"} onClick={() => go(`/metamodel/${model}`)}>
            Entities and relationships
          </button>
        )}
        <button className={tab === "metamodel" ? "tab on" : "tab"} onClick={() => go(`/metamodel/${model}/metamodel`)}>
          Metamodel
        </button>
      </div>
      {tab === "metamodel"
        ? <MetamodelView model={model} typeId={view === "type" ? itemId : null} holdsContent={holdsContent} />
        : <Content model={model} entityId={view === "entity" ? itemId : view === "relationships" ? "relationships" : null} />}
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
  // #/metamodel/<model>/<view>/<id>
  const [, , model, view, itemId] = (route || "").replace(/^#/, "").split("/");
  return model ? <ModelPage model={model} view={view} itemId={itemId} /> : <ModelList />;
}
