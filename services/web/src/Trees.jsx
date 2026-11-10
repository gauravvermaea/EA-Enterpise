// Tree views (D250): key and value only, each level read when it is opened.
//   MetamodelTree   model > entity types > attributes and relations (both ways); a relation jumps to its entity type
//   EntityTree      model > entity types > entities (with data quality, coloured) > values and relationships; a
//                   relationship jumps to that entity in the tree. Rooted at the model, one entity type, or one entity
//                   (then a relationship opens that entity's page).
// Each has a filter box, open and close all, and an Excel download (an outline: + opens a level).
import { useEffect, useMemo, useRef, useState } from "react";
import { apiDownload, apiFetch } from "./auth";
import { qTone, q2 } from "./QualityBits";

const go = (h) => { window.location.hash = h; };
const BANDS = { green: 80, amber: 60 };

function Toggle({ open, onClick, empty }) {
  return <button className="tree-toggle" onClick={onClick} aria-label={open ? "Close" : "Open"} disabled={empty}>{empty ? "·" : open ? "▾" : "▸"}</button>;
}

function KeyValue({ k, v, onClick }) {
  return <li className="tree-kv"><span className="tree-key">{k}</span><span className="tree-val">{onClick ? <button className="linkish" onClick={onClick}>{v}</button> : v}</span></li>;
}

// keep the highlighted node in view
function useFlash() {
  const [flash, setFlash] = useState("");
  useEffect(() => {
    if (!flash) return undefined;
    const t1 = setTimeout(() => document.querySelector(`[data-node="${window.CSS.escape(flash)}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" }), 60);
    const t2 = setTimeout(() => setFlash(""), 2500);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [flash]);
  return [flash, setFlash];
}

function Bar({ filter, setFilter, placeholder, onOpenAll, onCloseAll, onExcel, note }) {
  return (
    <div className="toolbar tree-bar">
      <input className="search" style={{ maxWidth: 300 }} placeholder={placeholder} value={filter} onChange={(e) => setFilter(e.target.value)} />
      <button onClick={onOpenAll} title="Open every level read so far">Open all</button>
      <button onClick={onCloseAll}>Close all</button>
      <button onClick={onExcel} title="The tree as an Excel outline: the + opens a level">Download Excel</button>
      {note && <span className="quiet small">{note}</span>}
    </div>
  );
}

// ---------------------------------------------------------------- the metamodel
export function MetamodelTree({ model, m }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(() => new Set(["root"]));
  const [filter, setFilter] = useState("");
  const [flash, setFlash] = useFlash();
  useEffect(() => { apiFetch(`/api/v1/models/${model}/tree/metamodel`).then(setData).catch((e) => setErr(e.message)); }, [model]);
  const f = filter.trim().toLowerCase();
  // filtering shows only what matches: an entity type whose name matches with everything under it; otherwise only its
  // matching attributes and relations
  const types = useMemo(() => (data?.types || []).map((t) => {
    if (!f || t.name.toLowerCase().includes(f) || t.code.toLowerCase().includes(f)) return t;
    const rm = (r) => r.relationship.toLowerCase().includes(f) || r.other_type.toLowerCase().includes(f);
    return { ...t, attributes: t.attributes.filter((a) => a.key.toLowerCase().includes(f) || a.value.toLowerCase().includes(f)),
      relations: { out: t.relations.out.filter(rm), in: t.relations.in.filter(rm) } };
  }).filter((t) => !f || t.name.toLowerCase().includes(f) || t.code.toLowerCase().includes(f) || t.attributes.length
    || t.relations.out.length || t.relations.in.length), [data, f]);
  if (err) return <p className="status bad">{err}</p>;
  if (!data) return <p>Loading...</p>;
  const isOpen = (k) => open.has(k) || (f && k !== "root");
  const toggle = (k) => setOpen((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  function jump(typeId) {
    setFilter("");
    setOpen((s) => new Set([...s, "root", `t:${typeId}`]));
    setFlash(`t:${typeId}`);
  }
  const hit = (s) => f && s.toLowerCase().includes(f);
  return (
    <div className="tree">
      <Bar filter={filter} setFilter={setFilter} placeholder="Filter entity types, attributes, relations"
        onOpenAll={() => setOpen(new Set(["root", ...data.types.flatMap((t) => [`t:${t.id}`, `a:${t.id}`, `r:${t.id}`])]))}
        onCloseAll={() => setOpen(new Set(["root"]))}
        onExcel={() => apiDownload(`/api/v1/models/${model}/tree/xlsx?scope=metamodel`, `${m.name} metamodel tree.xlsx`).catch((e) => setErr(e.message))}
        note={`${data.types.length} entity types · click a relation to go to its entity type`} />
      <ul className="tree-root">
        <li>
          <Toggle open={isOpen("root")} onClick={() => toggle("root")} /> <b>{m.name}</b> <span className="quiet small">model</span>
          {isOpen("root") && <ul>
            {types.map((t) => {
              const k = `t:${t.id}`;
              return (
                <li key={t.id} data-node={k} className={flash === k ? "tree-flash" : ""}>
                  <Toggle open={isOpen(k)} onClick={() => toggle(k)} />{" "}
                  <span className="tree-swatch" style={{ background: `#${t.colour}` }} /> <b className={hit(t.name) ? "tree-hit" : ""}>{t.name}</b>
                  <span className="quiet small"> {t.domain} · {t.entities} entities{t.status === "retired" ? " · retired" : ""}</span>
                  {isOpen(k) && <ul>
                    {(!f || t.attributes.length > 0) && <li><Toggle open={isOpen(`a:${t.id}`)} onClick={() => toggle(`a:${t.id}`)} empty={!t.attributes.length} /> Attributes <span className="quiet small">({t.attributes.length})</span>
                      {isOpen(`a:${t.id}`) && <ul>{t.attributes.map((a) => <KeyValue key={a.code} k={<span className={hit(a.key) ? "tree-hit" : ""}>{a.key}</span>} v={a.value} />)}</ul>}</li>}
                    {(!f || t.relations.out.length + t.relations.in.length > 0) && <li><Toggle open={isOpen(`r:${t.id}`)} onClick={() => toggle(`r:${t.id}`)} empty={!t.relations.out.length && !t.relations.in.length} /> Relations{" "}
                      <span className="quiet small">({t.relations.out.length} out, {t.relations.in.length} in)</span>
                      {isOpen(`r:${t.id}`) && <ul>
                        {t.relations.out.map((r, i) => <KeyValue key={`o${i}`} k={`${r.relationship} →`} v={<span className={hit(r.other_type) ? "tree-hit" : ""}>{r.other_type}</span>} onClick={() => jump(r.other_type_id)} />)}
                        {t.relations.in.map((r, i) => <KeyValue key={`i${i}`} k={`← ${r.relationship}`} v={<span className={hit(r.other_type) ? "tree-hit" : ""}>{r.other_type}</span>} onClick={() => jump(r.other_type_id)} />)}
                      </ul>}</li>}
                  </ul>}
                </li>
              );
            })}
            {!types.length && <li className="quiet">Nothing matches.</li>}
          </ul>}
        </li>
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- the entities
// typeId: only that entity type; entityId: only that entity (its relationships open the other entity's page)
export function EntityTree({ model, m, typeId = null, entityId = null }) {
  const [types, setTypes] = useState(null);
  const [bands, setBands] = useState(BANDS);
  const [ents, setEnts] = useState({});        // type id -> { list, total, pinned }
  const [nodes, setNodes] = useState({});      // entity id -> node
  const [open, setOpen] = useState(() => new Set(["root"]));
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("");
  const [found, setFound] = useState(null);
  const [flash, setFlash] = useFlash();
  const timer = useRef(null);

  useEffect(() => {
    setErr("");
    if (entityId) {
      apiFetch(`/api/v1/models/${model}/tree/entities/${entityId}`).then((n) => {
        setNodes({ [n.id]: n }); setBands(n.bands || BANDS); setOpen(new Set(["root", `e:${n.id}`, `v:${n.id}`, `r:${n.id}`]));
      }).catch((e) => setErr(e.message));
      return;
    }
    apiFetch(`/api/v1/models/${model}/tree/types`).then((d) => {
      const list = d.types.filter((t) => t.entities > 0 && (!typeId || t.id === typeId || t.code === typeId));
      setTypes(list); setBands(d.bands || BANDS);
      if (typeId && list[0]) loadType(list[0].id, 0).then(() => setOpen(new Set(["root", `t:${list[0].id}`])));
    }).catch((e) => setErr(e.message));
  }, [model, typeId, entityId]); // eslint-disable-line react-hooks/exhaustive-deps

  // the filter box: entity types, entities and values that match (from the server, so nothing has to be open first)
  useEffect(() => {
    clearTimeout(timer.current);
    const q = filter.trim();
    if (q.length < 2) { setFound(null); return undefined; }
    timer.current = setTimeout(() => apiFetch(`/api/v1/models/${model}/tree/search?q=${encodeURIComponent(q)}`).then(setFound).catch(() => setFound(null)), 300);
    return () => clearTimeout(timer.current);
  }, [filter, model]);

  async function loadType(tid, offset = 0) {
    const d = await apiFetch(`/api/v1/models/${model}/tree/types/${tid}?offset=${offset}&limit=200`);
    setEnts((s) => ({ ...s, [tid]: { list: [...(offset ? s[tid]?.list || [] : []), ...d.entities], total: d.total, pinned: s[tid]?.pinned || [] } }));
    return d;
  }
  async function loadNode(eid) {
    if (nodes[eid]) return nodes[eid];
    const n = await apiFetch(`/api/v1/models/${model}/tree/entities/${eid}`);
    setNodes((s) => ({ ...s, [eid]: n }));
    return n;
  }
  const toggle = (k) => setOpen((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  async function openType(tid) {
    if (!ents[tid]) await loadType(tid, 0).catch((e) => setErr(e.message));
    toggle(`t:${tid}`);
  }
  async function openEntity(eid) {
    if (!nodes[eid]) await loadNode(eid).catch((e) => setErr(e.message));
    toggle(`e:${eid}`);
  }
  // a relationship (or a search match): open its type and the entity, add it if it is not on the page read, and show it
  async function jump(tid, eid, name, display) {
    if (entityId) { go(`/metamodel/${model}/entity/${eid}/tree`); return; }
    try {
      if (typeId && tid !== typeId && !types?.some((t) => t.id === tid)) { go(`/metamodel/${model}/entity/${eid}/tree`); return; }
      let page = ents[tid];
      if (!page) { const d = await loadType(tid, 0); page = { list: d.entities }; }
      if (!page.list.some((e) => e.id === eid)) {
        const n = await loadNode(eid);
        setEnts((s) => ({ ...s, [tid]: { ...(s[tid] || { list: [], total: 0 }), pinned: [...(s[tid]?.pinned || []).filter((x) => x.id !== eid),
          { id: eid, name: name || n.name, display_id: display || n.display_id, score: n.score }] } }));
      } else await loadNode(eid);
      setOpen((s) => new Set([...s, "root", `t:${tid}`, `e:${eid}`, `v:${eid}`, `r:${eid}`]));
      setFlash(`e:${eid}`);
    } catch (e) { setErr(e.message); }
  }
  function openAll() {
    const keys = ["root", ...(types || []).map((t) => `t:${t.id}`)];
    Object.keys(nodes).forEach((id) => keys.push(`e:${id}`, `v:${id}`, `r:${id}`));
    setOpen(new Set(keys));
  }
  const excel = () => apiDownload(`/api/v1/models/${model}/tree/xlsx?scope=${entityId ? "entity" : "entities"}${typeId ? `&type=${typeId}` : ""}${entityId ? `&entity=${entityId}` : ""}`,
    `${m.name} ${entityId ? "entity" : "entities"} tree.xlsx`).catch((e) => setErr(e.message));

  // the filter: only the entity types and entities that match (by name, ID or a value), and under each entity only the
  // values and relations that match (all of them when its name matches)
  const fq = filter.trim().toLowerCase();
  const filtering = !entityId && !!found && fq.length >= 2;
  const matched = useMemo(() => {
    if (!filtering) return null;
    const byType = {};
    const seen = new Set();
    for (const e of [...found.entities, ...found.values]) {
      if (seen.has(e.id)) continue;
      seen.add(e.id);
      (byType[e.type_id] = byType[e.type_id] || []).push({ id: e.id, name: e.name, display_id: e.display_id || "" });
    }
    return { byType, types: new Set(found.types.map((x) => x.id)), ids: [...seen] };
  }, [found, filtering]);
  useEffect(() => {          // read the matching entities so their matching values show
    if (!matched) return;
    matched.ids.filter((id) => !nodes[id]).slice(0, 60).forEach((id) => { loadNode(id).catch(() => null); });
  }, [matched]); // eslint-disable-line react-hooks/exhaustive-deps
  const inTree = (typeOf, id) => (entityId ? id === entityId : !typeId || (types || []).some((x) => x.id === typeOf));
  const elsewhere = !found || fq.length < 2 ? null : {
    types: found.types.filter((x) => entityId || !inTree(x.id)),
    entities: [...found.entities, ...found.values.map((v) => ({ ...v, via: `${v.attribute}: ${v.value}` }))]
      .filter((e, i, all) => all.findIndex((y) => y.id === e.id) === i && !inTree(e.type_id, e.id)),
  };
  const aside = elsewhere && (elsewhere.types.length > 0 || elsewhere.entities.length > 0) ? (
    <aside className="tree-aside small">
      <b>Also matches elsewhere in {m.name}</b>
      <ul>
        {elsewhere.types.map((x) => <li key={x.id}><a href={`#/metamodel/${model}/types/${x.id}`}>{x.name}</a> <span className="quiet">entity type</span></li>)}
        {elsewhere.entities.slice(0, 60).map((e) => <li key={e.id}><a href={`#/metamodel/${model}/entity/${e.id}${entityId ? "/tree" : ""}`}>{e.name}</a>
          <span className="quiet"> {e.type}{e.via ? ` · ${e.via}` : ""}</span></li>)}
      </ul>
    </aside>) : null;
  const isOpen = (k) => open.has(k) || (filtering && k !== "root" && !k.startsWith("t:")) || (filtering && k.startsWith("t:") && !!matched?.byType[k.slice(2)]);
  const nameHit = (s) => fq && String(s || "").toLowerCase().includes(fq);

  function EntityRow({ e, tid }) {
    const k = `e:${e.id}`;
    const n0 = nodes[e.id];
    const n = n0 && filtering && !nameHit(n0.name) && !nameHit(n0.display_id) ? filtered(n0, filter) : n0;
    const score = n?.score ?? e.score;
    return (
      <li data-node={k} className={flash === k ? "tree-flash" : ""}>
        <Toggle open={isOpen(k)} onClick={() => openEntity(e.id)} />{" "}
        <span className={`tree-ent ${qTone(score, bands)}${nameHit(e.name) ? " tree-hit" : ""}`} title={score == null ? "Data quality not calculated yet" : `Data quality ${q2(score)} (as last calculated)`}>{e.name}</span>
        <span className="quiet small"> {e.display_id}</span>
        {score != null && <span className={`q-chip ${qTone(score, bands)}`} title={`Data quality ${q2(score)}`}>{Math.round(score)}%</span>}{" "}
        <a className="small" href={`#/metamodel/${model}/entity/${e.id}`} title="Open its page">open</a>
        {isOpen(k) && n && <NodeBody n={n} tid={tid} />}
      </li>
    );
  }
  function NodeBody({ n }) {
    return (
      <ul>
        {(!fq || n.values.length > 0) && <li><Toggle open={isOpen(`v:${n.id}`)} onClick={() => toggle(`v:${n.id}`)} empty={!n.values.length} /> Attributes{" "}
          <span className="quiet small">({n.values.length}{n.empty ? `, ${n.empty} empty not shown` : ""})</span>
          {isOpen(`v:${n.id}`) && <ul>{n.values.map((v, i) => <KeyValue key={i} k={v.key} v={nameHit(v.value) ? <span className="tree-hit">{v.value}</span> : v.value}
            onClick={v.ref_id ? () => go(`/metamodel/${model}/entity/${v.ref_id}${entityId ? "/tree" : ""}`) : null} />)}</ul>}</li>}
        {(!fq || n.relations.out.length + n.relations.in.length > 0) && <li><Toggle open={isOpen(`r:${n.id}`)} onClick={() => toggle(`r:${n.id}`)} empty={!n.relations.out.length && !n.relations.in.length} /> Relations{" "}
          <span className="quiet small">({n.relations.out.length} out, {n.relations.in.length} in)</span>
          {isOpen(`r:${n.id}`) && <ul>
            {n.relations.out.map((r, i) => <KeyValue key={`o${i}`} k={`${r.relationship} →`} v={`${r.other} (${r.other_type})`} onClick={() => jump(r.other_type_id, r.other_id, r.other, r.other_display_id)} />)}
            {n.relations.in.map((r, i) => <KeyValue key={`i${i}`} k={`← ${r.relationship}`} v={`${r.other} (${r.other_type})`} onClick={() => jump(r.other_type_id, r.other_id, r.other, r.other_display_id)} />)}
          </ul>}</li>}
      </ul>
    );
  }

  if (err) return <p className="status bad">{err}</p>;
  if (entityId) {
    const n = nodes[entityId] || Object.values(nodes)[0];
    if (!n) return <p>Loading...</p>;
    return (
      <div className="tree">
        <Bar filter={filter} setFilter={setFilter} placeholder="Filter its values and relations" onOpenAll={openAll} onCloseAll={() => setOpen(new Set(["root"]))} onExcel={excel}
          note="click a relationship to open that entity" />
        <div className="tree-with-aside"><ul className="tree-root"><li>
          <Toggle open={open.has("root")} onClick={() => toggle("root")} /> <b>{m.name}</b> <span className="quiet small">model</span>
          {open.has("root") && <ul><li><span className="quiet small">{n.type}</span>
            <ul><li data-node={`e:${n.id}`}>
              <Toggle open={open.has(`e:${n.id}`)} onClick={() => toggle(`e:${n.id}`)} />{" "}
              <span className={`tree-ent ${qTone(n.score, bands)}`}>{n.name}</span> <span className="quiet small">{n.display_id}</span>
              {n.score != null && <span className={`q-chip ${qTone(n.score, bands)}`} title={`Data quality ${q2(n.score)} (as last calculated)`}>{Math.round(n.score)}%</span>}
              {open.has(`e:${n.id}`) && <NodeBody n={filtered(n, filter)} />}
            </li></ul></li></ul>}
        </li></ul>{aside}</div>
      </div>
    );
  }
  if (!types) return <p>Loading...</p>;
  return (
    <div className="tree">
      <Bar filter={filter} setFilter={setFilter} placeholder="Filter: entity type, entity, ID or value" onOpenAll={openAll}
        onCloseAll={() => setOpen(new Set(["root"]))} onExcel={excel}
        note={`${types.reduce((n, t) => n + t.entities, 0)} entities · names coloured by data quality as last calculated · click a relationship to go to that entity`} />
      {filtering && !matched.ids.length && !matched.types.size && <p className="quiet small">Nothing matches.</p>}
      {filtering && (found.entities.length >= 50 || found.values.length >= 50) && <p className="quiet small">Showing the first matches: type more to narrow them.</p>}
      <div className="tree-with-aside"><ul className="tree-root"><li>
        <Toggle open={open.has("root")} onClick={() => toggle("root")} /> <b>{m.name}</b> <span className="quiet small">model</span>
        {open.has("root") && <ul>
          {types.filter((t) => !filtering || matched.types.has(t.id) || matched.byType[t.id]).map((t) => {
            const k = `t:${t.id}`;
            const page = ents[t.id];
            const pinned = (page?.pinned || []).filter((p) => !page.list.some((e) => e.id === p.id));
            if (filtering && matched.byType[t.id]) {          // only its matching entities
              return (
                <li key={t.id} data-node={k}>
                  <Toggle open={isOpen(k)} onClick={() => toggle(k)} />{" "}
                  <span className="tree-swatch" style={{ background: `#${t.colour}` }} /> <b className={`tree-ent ${qTone(t.score, bands)}${nameHit(t.name) ? " tree-hit" : ""}`}>{t.name}</b>
                  <span className="quiet small"> {matched.byType[t.id].length} of {t.entities} match</span>
                  {isOpen(k) && <ul>{matched.byType[t.id].map((e) => <EntityRow key={e.id} e={{ ...e, score: nodes[e.id]?.score }} tid={t.id} />)}</ul>}
                </li>
              );
            }
            return (
              <li key={t.id} data-node={k} className={flash === k ? "tree-flash" : ""}>
                <Toggle open={open.has(k)} onClick={() => (open.has(k) ? toggle(k) : openType(t.id))} />{" "}
                <span className="tree-swatch" style={{ background: `#${t.colour}` }} /> <b className={`tree-ent ${qTone(t.score, bands)}${nameHit(t.name) ? " tree-hit" : ""}`}>{t.name}</b>
                <span className="quiet small"> {t.entities} entities</span>
                {t.score != null && <span className={`q-chip ${qTone(t.score, bands)}`} title={`Data quality ${q2(t.score)} (as last calculated)`}>{Math.round(t.score)}%</span>}
                {open.has(k) && page && <ul>
                  {pinned.map((e) => <EntityRow key={`p${e.id}`} e={e} tid={t.id} />)}
                  {page.list.map((e) => <EntityRow key={e.id} e={e} tid={t.id} />)}
                  {page.list.length < page.total && <li><button className="linkish" onClick={() => loadType(t.id, page.list.length).catch((e) => setErr(e.message))}>
                    Show {Math.min(200, page.total - page.list.length)} more of {page.total - page.list.length}</button></li>}
                </ul>}
              </li>
            );
          })}
        </ul>}
      </li></ul>{aside}</div>
    </div>
  );
}

// one entity's values and relations narrowed to what the filter box says
function filtered(n, filter) {
  const f = filter.trim().toLowerCase();
  if (!f) return n;
  const has = (...s) => s.some((x) => String(x || "").toLowerCase().includes(f));
  return { ...n, values: n.values.filter((v) => has(v.key, v.value)),
    relations: { out: n.relations.out.filter((r) => has(r.relationship, r.other, r.other_type)), in: n.relations.in.filter((r) => has(r.relationship, r.other, r.other_type)) } };
}
