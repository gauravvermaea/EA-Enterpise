// Phase 7 screens built on Grid.jsx: entity grids per type, the relationships grid, metamodel grids
// (entity types, relationship types, attributes, mappings, pick-list values, rules), saved views,
// favourites, recent items and search.
import { useEffect, useMemo, useState } from "react";
import { apiFetch, canOn, needsRole } from "./auth";
import { contentAccess } from "./DataEntry";
import Grid from "./Grid";
import { fmtDateTime } from "./fmt";
import { fieldClass, q2, QualityCell, RecheckAll, ScoreChip, useTypeQuality } from "./QualityBits";
import { Modal } from "./ModelOps";
import { metamodelEditable } from "./MetamodelEditor";
import { refreshAll, Swatch, useApi } from "./ModelViews";

const NUMERIC = ["integer", "decimal", "currency", "percent"];
const cellType = (dt) => (dt === "list" ? "select" : dt === "boolean" ? "bool" : dt === "date" ? "date" : NUMERIC.includes(dt) ? "number" : "text");

// ---------------------------------------------------------------- saved views (columns, filter, sort)
export function ViewPicker({ model, kind, target, config, onApply }) {
  const params = new URLSearchParams({ kind, target: target || "", ...(model ? { model } : {}) });
  const { data: views } = useApi(`/api/v1/views?${params}`);
  const [saving, setSaving] = useState(false);
  const [chosen, setChosen] = useState("");
  const current = (views || []).find((v) => v.id === chosen);
  return (
    <span className="view-picker">
      <select value={chosen} title="Saved views: columns, filter and sort, yours or shared with you"
        onChange={(e) => { setChosen(e.target.value); const v = (views || []).find((x) => x.id === e.target.value); onApply(v ? v.config : { filter: "", sort: null, hidden: [] }); }}>
        <option value="">Views...</option>
        {(views || []).map((v) => <option key={v.id} value={v.id}>{v.name}{v.shared ? " (shared)" : ""}{v.mine ? "" : ` by ${v.owner}`}</option>)}
      </select>
      <button onClick={() => setSaving(true)} title="Save the columns, filter and sort as a view">Save view</button>
      {saving && <SaveViewDialog model={model} kind={kind} target={target} config={config} existing={current?.mine ? current : null}
        onClose={() => setSaving(false)} onSaved={(id) => { setChosen(id); setSaving(false); }} />}
    </span>
  );
}

function SaveViewDialog({ model, kind, target, config, existing, onClose, onSaved }) {
  const [name, setName] = useState(existing?.name || "");
  const [shared, setShared] = useState(!!existing?.shared);
  const [replace, setReplace] = useState(!!existing);
  const [msg, setMsg] = useState("");
  return (
    <Modal title="Save view" onClose={onClose} actions={<button className="ed-btn" disabled={!name.trim()} onClick={async () => {
      try {
        const out = await apiFetch("/api/v1/views", { method: "POST", body: JSON.stringify({
          id: replace && existing ? existing.id : null, name, view_kind: kind, model, target: target || "", config, shared }) });
        refreshAll(); onSaved(out.id);
      } catch (err) { setMsg(err.message); }
    }}>Save</button>}>
      <div className="ed-form">
        <label className="ed-field"><span>Name</span><input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="for example Cloud apps by owner" /></label>
        <label className="ed-field check"><input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
          <span title="Everyone who can read this model sees it in their Views list">Share with everyone who can read the model</span></label>
        {existing && <label className="ed-field check"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
          <span>Replace "{existing.name}" (otherwise a new view)</span></label>}
        <p className="quiet">Keeps the columns shown, the filter and the sort: {config.hidden?.length || 0} hidden columns{config.filter ? `, filter "${config.filter}"` : ""}{config.sort ? `, sorted by ${config.sort.key}` : ""}.</p>
        {msg && <p className="status bad">{msg}</p>}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- search
export function SearchPage({ route }) {
  const qs = new URLSearchParams(route.split("?")[1] || "");
  const [q, setQ] = useState(qs.get("q") || "");
  const [model, setModel] = useState(qs.get("model") || "");
  const [type, setType] = useState(qs.get("type") || "");
  const [attribute, setAttribute] = useState(qs.get("attribute") || "");
  const [tag, setTag] = useState(qs.get("tag") || "");
  const [run, setRun] = useState(qs.toString());
  const { data: models } = useApi("/api/v1/models");
  const { data, error } = useApi(run ? `/api/v1/search?${run}` : null);
  function go(e) {
    e?.preventDefault();
    const p = new URLSearchParams();
    if (q) p.set("q", q); if (model) p.set("model", model); if (type) p.set("type", type);
    if (attribute) p.set("attribute", attribute); if (tag) p.set("tag", tag);
    setRun(p.toString());
    window.history.replaceState(null, "", `#/search?${p}`);
  }
  return (
    <section>
      <h1>Search</h1>
      <form className="toolbar search-form" onSubmit={go}>
        <input className="search" autoFocus style={{ minWidth: 280 }} placeholder="Name, ID, description, tag or any value" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={model} onChange={(e) => setModel(e.target.value)} title="Only this model">
          <option value="">Every model you can read</option>
          {(models || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <input placeholder="Entity type" value={type} onChange={(e) => setType(e.target.value)} style={{ width: 150 }} title="For example Application Component" />
        <input placeholder="In attribute" value={attribute} onChange={(e) => setAttribute(e.target.value)} style={{ width: 130 }} title="Only values of this attribute, for example Vendor" />
        <input placeholder="Tag" value={tag} onChange={(e) => setTag(e.target.value)} style={{ width: 110 }} />
        <button className="ed-btn" type="submit">Search</button>
      </form>
      {error && <p className="status bad">{error}</p>}
      {data && (
        <>
          <p className="quiet">{data.total}{data.more ? "+" : ""} result{data.total === 1 ? "" : "s"}{data.query ? ` for "${data.query}"` : ""}.</p>
          <table className="grid-table">
            <thead><tr><th>Entity</th><th>Type</th><th>Model</th><th>Found in</th><th>Tags</th></tr></thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.id}>
                  <td><Swatch colour={r.colour} /> <a href={`#/metamodel/${r.model_id}/entity/${r.id}`}>{r.name}</a> <span className="quiet">{r.display_id}{r.status === "retired" ? " · retired" : ""}</span></td>
                  <td>{r.entity_type}</td>
                  <td><a href={`#/metamodel/${r.model_id}`}>{r.model}</a></td>
                  <td className="quiet">{r.field}{r.snippet ? `: ${r.snippet}` : ""}</td>
                  <td>{(r.tags || []).map((t) => <span key={t} className="tag">{t}</span>)}</td>
                </tr>
              ))}
              {!data.results.length && <tr><td colSpan="5" className="quiet">Nothing found.</td></tr>}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

export function TopSearch() {
  const [q, setQ] = useState("");
  useEffect(() => {
    const key = (e) => {
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) && !document.activeElement?.closest?.(".grid-box")) {
        e.preventDefault(); document.getElementById("top-search")?.focus();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  return (
    <form className="top-search" onSubmit={(e) => { e.preventDefault(); window.location.hash = `/search?q=${encodeURIComponent(q)}`; }}>
      <input id="top-search" type="search" placeholder="Search (/)" value={q} onChange={(e) => setQ(e.target.value)} title="Search every model you can read (press / to jump here)" />
    </form>
  );
}

// ---------------------------------------------------------------- the entity grid of one type
// a cell's data quality (D246): highlighted with its reasons when it lowers the entity's quality
const qCell = (tq, code) => ({
  cellClass: (row) => fieldClass(tq?.entities?.[row.id], code),
  cellTitle: (row) => (tq?.entities?.[row.id]?.fields?.[code] || []).map((x) => x.message).join("\n"),
});

function EntityGrid({ model, m, typeId }) {
  const { data, error } = useApi(`/api/v1/models/${model}/grids/entities/${typeId}`);
  const tq = useTypeQuality(m?.kind === "project" ? model : null, typeId).data;    // as last calculated (D245)
  // my saved, uncommitted changes, by entity: commit (or ask to), or discard, in place (owner, 6 Nov 2026)
  const ch = useApi(m?.kind === "project" ? `/api/v1/models/${model}/changes` : null).data;
  const pendingBy = useMemo(() => {
    const out = {};
    for (const s of ch?.mine || []) for (const c of s.changes) for (const e of c.entities || []) (out[e] = out[e] || []).push(c.id);
    return out;
  }, [ch]);
  const [cmsg, setCmsg] = useState("");
  async function changeStep(step, ids, entities) {
    setCmsg("");
    try {
      const r = await apiFetch(`/api/v1/models/${model}/changes/${step}`, { method: "POST", body: JSON.stringify({ changes: ids }) });
      if (step === "commit") {      // the committed rows' data quality, checked at once (one entity at a time)
        await Promise.all(entities.slice(0, 50).map((e) => apiFetch(`/api/v1/models/${model}/entities/${e}/quality/recheck`, { method: "POST", body: "{}" }).catch(() => null)));
      }
      setCmsg(step === "commit" ? `Committed${r.number ? ` (commit ${r.number})` : ""}.` : step === "request" ? "Asked the committers to commit it." : "Discarded: back to the committed values.");
      refreshAll();
    } catch (e) { setCmsg(e.status === 409 ? `${e.message} Open the Changes tab to resolve it.` : e.message); }
  }
  const [config, setConfig] = useState(null);
  const [applied, setApplied] = useState(null);
  const access = contentAccess(model, m, data?.retired);
  const columns = useMemo(() => (data ? [
    { key: "display_id", label: "ID", readOnly: true, createOnly: true, width: 90, title: "Given when saved; you may type your own for a new row" },
    { key: "name", label: "Name", required: true, width: 200, ...qCell(tq, "name") },
    ...(tq ? [{ key: "quality", label: "Quality", readOnly: true, type: "number", width: 92,
      title: "Data quality of the entity now (completeness, rules, freshness); hover a highlighted cell for why",
      render: (row) => (row.id ? <QualityCell model={model} entity={row.id} row={tq.entities?.[row.id]} bands={tq.bands} /> : "") }] : []),
    { key: "description", label: "Description", width: 220, ...qCell(tq, "description") },
    { key: "parent_name", label: "Part of", width: 160, title: "The parent entity: its name or ID" },
    { key: "tags", label: "Tags", width: 140, title: "Separated by commas" },
    ...data.attributes.map((a) => ({ key: `v:${a.code}`, label: a.name, type: cellType(a.data_type), options: a.pick_list_values,
      required: a.is_required, width: a.data_type === "long_text" ? 220 : 120, ...qCell(tq, a.code),
      title: [a.data_type_name, a.unit, a.pick_list_values.length ? `One of: ${a.pick_list_values.join(", ")}` : "", a.data_type === "entity_ref" ? "an entity's name or ID" : ""].filter(Boolean).join(" · ") })),
    { key: "status", label: "Status", readOnly: true, width: 80 },
    { key: "relationship_count", label: "Rel.", readOnly: true, type: "number", width: 50 },
    { key: "checks", label: "Checks", readOnly: true, width: 160 },
  ] : []), [data, tq, ch, pendingBy]);
  const rows = useMemo(() => (data ? data.rows.map((r) => ({
    id: r.id, row_version: r.row_version, display_id: r.display_id, name: r.name, description: r.description,
    parent_name: r.parent_name || "", tags: (r.tags || []).join(", "), status: r.pending ? `✎ ${r.pending}, uncommitted` : r.status, relationship_count: r.relationship_count,
    checks: r.messages?.join("; ") || "",
    ...Object.fromEntries(data.attributes.map((a) => [`v:${a.code}`, r.values[a.code] ?? ""])),
  })) : []), [data]);   // not the quality: a new quality result must never reset rows being edited
  if (!data) return <p className="quiet">{error || "Loading..."}</p>;
  async function save(batch) {
    const body = batch.map((b) => {
      if (b.delete) return { id: b.orig.id, delete: true };
      const out = b.orig ? { id: b.orig.id, row_version: b.orig.row_version } : {};
      const values = {};
      Object.entries(b.values).forEach(([k, v]) => {
        if (k.startsWith("v:")) values[k.slice(2)] = v ?? "";
        else if (k === "parent_name") out.parent = v || "";
        else out[k] = v ?? "";
      });
      if (Object.keys(values).length) out.values = values;
      if (!b.orig && !out.name) out.name = b.cur.name || "";
      return out;
    });
    const res = await apiFetch(`/api/v1/models/${model}/grids/entities/${typeId}`, { method: "POST", body: JSON.stringify({ rows: body }) });
    refreshAll();
    return res;
  }
  return (
    <Grid key={typeId} columns={columns} rows={rows} canEdit={access.ok} why={access.why} onSave={save} name={`${m.name} - ${data.entity_type.name}`}
      initialConfig={applied} onConfig={setConfig} deleteLabel="Delete"
      rowMark={ch?.uses_commits ? (row) => {
        const ids = pendingBy[row.id];
        if (!ids) return null;
        const n = `${ids.length} saved change${ids.length === 1 ? "" : "s"} not committed yet`;
        return ch.may_commit
          ? <button className="linkish grid-commit-one" onClick={() => changeStep("commit", ids, [row.id])} title={`Commit now: ${n} (right-click to discard them)`}>⇪</button>
          : <button className="linkish grid-commit-one ask" onClick={() => changeStep("request", ids, [row.id])} title={`Ask a committer to commit: ${n} (right-click to discard them)`}>⇪</button>;
      } : null}
      rowMenu={ch?.uses_commits ? (row) => (pendingBy[row.id] ? [{ label: "Discard this row's uncommitted changes",
        onClick: () => changeStep("discard", pendingBy[row.id], [row.id]) }] : []) : null}
      emptyText={`No ${data.entity_type.name} entities yet: press + Row or paste rows from Excel.`}
      views={<ViewPicker model={model} kind="entity_grid" target={typeId} config={config || {}} onApply={setApplied} />}
      toolbar={<>{ch?.uses_commits && Object.keys(pendingBy).length > 0 && <span className="small grid-commit">
        <span className="uc">✎ {Object.keys(pendingBy).filter((k) => rows.some((r) => r.id === k)).length} {data.entity_type.name} uncommitted</span>
        {(() => {
          const ents = Object.keys(pendingBy).filter((k) => rows.some((r) => r.id === k));
          const ids = [...new Set(ents.flatMap((k) => pendingBy[k]))];
          return ents.length ? <>{ch.may_commit ? <button onClick={() => changeStep("commit", ids, ents)}>Commit all</button>
            : <button onClick={() => changeStep("request", ids, ents)}>Ask to commit all</button>}{" "}
            <button onClick={() => changeStep("discard", ids, ents)}>Discard all</button></> : null;
        })()}
        {cmsg && <span className="quiet"> {cmsg}</span>}</span>}
      {!Object.keys(pendingBy).length && cmsg && <span className="small quiet">{cmsg} </span>}
      {tq && <span className="small" title={`${data.entity_type.name}: data quality ${q2(tq.summary.score)} over ${tq.summary.entities} entities; completeness ${q2(tq.summary.completeness)}, rules passed ${q2(tq.summary.passing)}, fresh ${q2(tq.summary.fresh)}`}>
        {data.entity_type.name} data quality <ScoreChip score={tq.summary.score} bands={tq.bands} /> <span className="quiet">· as calculated {tq.calculated_to ? fmtDateTime(tq.calculated_to) : "- not yet"}; highlighted cells lower it (hover for why); ↻ rechecks a row</span>{" "}
        <RecheckAll model={model} type={typeId} /></span>}</>} />
  );
}

// ---------------------------------------------------------------- the relationships grid
function RelationshipGrid({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/grids/relationships`);
  const [outside, setOutside] = useState(false);
  const [config, setConfig] = useState(null);
  const [applied, setApplied] = useState(null);
  const access = contentAccess(model, m);
  const columns = useMemo(() => (data ? [
    { key: "source", label: "Source", required: true, width: 110, title: "The source entity's ID or name" },
    { key: "source_name", label: "Source name", readOnly: true, width: 180 },
    { key: "relationship_type", label: "Relationship", type: "select", options: data.relationship_types.map((t) => t.name), required: true, width: 130 },
    { key: "target", label: "Target", required: true, width: 110, title: "The target entity's ID or name" },
    { key: "target_name", label: "Target name", readOnly: true, width: 180 },
    { key: "name", label: "Label", width: 160 },
    { key: "types", label: "Types", readOnly: true, width: 220 },
    { key: "allowed", label: "In metamodel", readOnly: true, width: 90 },
  ] : []), [data]);
  const rows = useMemo(() => (data ? data.rows.map((r) => ({
    id: r.id, source: r.source_display_id, source_name: r.source_name, relationship_type: r.relationship_type, target: r.target_display_id,
    target_name: r.target_name, name: r.name, types: `${r.source_type} ${r.verb} ${r.target_type}`, allowed: r.allowed ? "yes" : "no",
  })) : []), [data]);
  if (!data) return <p className="quiet">{error || "Loading..."}</p>;
  async function save(batch) {
    const body = batch.map((b) => {
      if (b.delete) return { id: b.orig.id, delete: true };
      const r = { ...(b.orig ? { id: b.orig.id } : {}), allow_outside: outside };
      ["source", "target", "relationship_type", "name"].forEach((k) => { if (k in b.values || !b.orig) r[k] = b.cur[k] ?? ""; });
      return r;
    });
    const res = await apiFetch(`/api/v1/models/${model}/grids/relationships`, { method: "POST", body: JSON.stringify({ rows: body }) });
    refreshAll();
    return res;
  }
  return (
    <Grid columns={columns} rows={rows} canEdit={access.ok} why={access.why} onSave={save} name={`${m.name} - relationships`}
      initialConfig={applied} onConfig={setConfig} emptyText="No relationships yet: paste rows of source, relationship, target."
      toolbar={<label className="quiet" title="A row the metamodel does not allow is then added to the metamodel, flagged for a Model Admin (D49)">
        <input type="checkbox" checked={outside} onChange={(e) => setOutside(e.target.checked)} disabled={!access.ok} /> Allow outside the metamodel</label>}
      views={<ViewPicker model={model} kind="relationship_grid" target="" config={config || {}} onApply={setApplied} />} />
  );
}

// ---------------------------------------------------------------- the data entry tab's grid mode
export function GridTab({ model, m, typeFromUrl }) {
  const { data: mm } = useApi(`/api/v1/models/${model}/metamodel`);
  const [type, setType] = useState(typeFromUrl || "");
  return (
    <div>
      <div className="toolbar">
        <label>Grid of{" "}
          <select value={type} onChange={(e) => { setType(e.target.value); window.location.hash = `/metamodel/${model}/grid${e.target.value ? `/${e.target.value}` : ""}`; }}>
            <option value="">Choose...</option>
            <option value="relationships">Relationships (all types)</option>
            {mm?.layers.map((l) => (
              <optgroup key={l.id} label={l.name}>
                {l.entity_types.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.entity_count ?? 0})</option>)}
              </optgroup>
            ))}
          </select></label>
      </div>
      {!type && <p className="quiet">Choose an entity type, or Relationships, to work on many rows at once: type into cells, paste blocks from Excel,
        add and delete rows, then Save. Each row is saved on its own; rows that cannot be saved are marked with the reason.</p>}
      {type === "relationships" ? <RelationshipGrid model={model} m={m} /> : type ? <EntityGrid model={model} m={m} typeId={type} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------- metamodel grids (Model Admins)
const MM_GRIDS = [
  ["entity_types", "Entity types"], ["relationship_types", "Relationship types"], ["attributes", "Attributes"],
  ["mappings", "Allowed relationships"], ["pick_list_values", "Pick-list values"], ["rules", "Validation rules"],
];

function mmColumns(kind, ch) {
  switch (kind) {
    case "entity_types": return [
      { key: "name", label: "Name", required: true, width: 180 }, { key: "code", label: "Code", readOnly: true, createOnly: true, width: 140 },
      { key: "layer", label: "Layer", type: "select", options: ch.layers, required: true, width: 130 },
      { key: "id_prefix", label: "ID prefix", width: 80 }, { key: "aspect", label: "Aspect", width: 110 },
      { key: "description", label: "Description", width: 260 },
      { key: "status", label: "Status", type: "select", options: ch.statuses, width: 90, title: "Retired: no new entities, existing ones read-only (D87)" },
      { key: "entities", label: "Entities", readOnly: true, type: "number", width: 70 }];
    case "relationship_types": return [
      { key: "name", label: "Name", required: true, width: 160 }, { key: "code", label: "Code", readOnly: true, createOnly: true, width: 130 },
      { key: "verb", label: "Reads as", required: true, width: 130 }, { key: "category", label: "Category", width: 110 },
      { key: "is_directed", label: "Directed", type: "bool", width: 70 }, { key: "description", label: "Description", width: 260 },
      { key: "status", label: "Status", type: "select", options: ch.statuses, width: 90 },
      { key: "relationships", label: "In use", readOnly: true, type: "number", width: 60 }];
    case "attributes": return [
      { key: "entity_type", label: "Entity type", type: "select", options: ch.entity_types, required: true, createOnly: true, readOnly: true, width: 170 },
      { key: "name", label: "Attribute", required: true, width: 160 }, { key: "code", label: "Code", readOnly: true, width: 120 },
      { key: "data_type", label: "Data type", type: "select", options: ch.data_types, required: true, createOnly: true, readOnly: true, width: 100 },
      { key: "pick_list", label: "Pick list", type: "select", options: ch.pick_lists, createOnly: true, readOnly: true, width: 130,
        title: "For a list attribute: an existing pick list, or type values separated by commas for a new one" },
      { key: "is_required", label: "Required", type: "bool", width: 70 }, { key: "section", label: "Section", width: 110 },
      { key: "unit", label: "Unit", width: 60 }, { key: "default_value", label: "Default", width: 100 },
      { key: "description", label: "Description", width: 220 }];
    case "mappings": return [
      { key: "source_type", label: "Source type", type: "select", options: ch.entity_types, required: true, width: 180 },
      { key: "relationship_type", label: "Relationship", type: "select", options: ch.relationship_types, required: true, width: 140 },
      { key: "target_type", label: "Target type", type: "select", options: ch.entity_types, required: true, width: 180 },
      { key: "note", label: "Note", width: 240 }, { key: "from_content", label: "Added from data entry", readOnly: true, type: "bool", width: 90 }];
    case "pick_list_values": return [
      { key: "pick_list", label: "Pick list", type: "select", options: ch.pick_lists, required: true, createOnly: true, readOnly: true, width: 180 },
      { key: "value", label: "Value", required: true, createOnly: true, readOnly: true, width: 200 },
      { key: "status", label: "Status", readOnly: true, width: 90 }];
    default: return [
      { key: "entity_type", label: "Entity type", type: "select", options: ["", ...ch.entity_types], createOnly: true, readOnly: true, width: 160, title: "Empty: every type" },
      { key: "field", label: "Field or attribute", type: "select", options: ch.fields, required: true, createOnly: true, readOnly: true, width: 160 },
      { key: "rule_type", label: "Rule", type: "select", options: ch.rule_types, required: true, createOnly: true, readOnly: true, width: 130 },
      { key: "param1", label: "Parameter 1", width: 120 }, { key: "param2", label: "Parameter 2", width: 120 },
      { key: "severity", label: "Severity", type: "select", options: ch.severities, width: 90 }, { key: "message", label: "Message", width: 280 }];
  }
}

// a grid's changed rows as metamodel changes (one metamodel version)
function mmOps(kind, batch, ch) {
  const ops = [];
  const bool = (v) => v === true || v === "Yes";
  for (const b of batch) {
    const v = b.values, cur = b.cur, id = b.orig?.id;
    if (kind === "entity_types") {
      if (b.delete) { ops.push({ op: "entity_type.retire", id }); continue; }
      if (!id) { ops.push({ op: "entity_type.create", name: cur.name, layer: cur.layer, code: cur.code || undefined, id_prefix: cur.id_prefix || undefined, aspect: cur.aspect || "", description: cur.description || "" }); continue; }
      const upd = Object.fromEntries(["name", "layer", "id_prefix", "aspect", "description"].filter((k) => k in v).map((k) => [k, v[k] ?? ""]));
      if (Object.keys(upd).length) ops.push({ op: "entity_type.update", id, ...upd });
      if ("status" in v) ops.push({ op: v.status === "retired" ? "entity_type.retire" : "entity_type.restore", id });
    } else if (kind === "relationship_types") {
      if (b.delete) { ops.push({ op: "relationship_type.remove", id }); continue; }
      if (!id) { ops.push({ op: "relationship_type.create", name: cur.name, verb: cur.verb, code: cur.code || undefined, category: cur.category || "", is_directed: cur.is_directed === "" || cur.is_directed === undefined ? true : bool(cur.is_directed), description: cur.description || "" }); continue; }
      const upd = Object.fromEntries(["name", "verb", "category", "description"].filter((k) => k in v).map((k) => [k, v[k] ?? ""]));
      if ("is_directed" in v) upd.is_directed = bool(v.is_directed);
      if (Object.keys(upd).length) ops.push({ op: "relationship_type.update", id, ...upd });
      if ("status" in v) ops.push({ op: v.status === "retired" ? "relationship_type.retire" : "relationship_type.restore", id });
    } else if (kind === "attributes") {
      if (b.delete) { ops.push({ op: "attribute.remove", item: id }); continue; }
      if (!id) {
        const pl = cur.pick_list || "";
        const known = ch.pick_list_ids[pl];
        ops.push({ op: "attribute.create", entity_type: cur.entity_type, name: cur.name, data_type: cur.data_type || "text",
          ...(cur.data_type === "list" ? (known ? { pick_list: known } : { values: pl.split(",").map((x) => x.trim()).filter(Boolean) }) : {}),
          is_required: bool(cur.is_required), section: cur.section || "", unit: cur.unit || "", description: cur.description || "",
          ...(cur.default_value ? { default_value: cur.default_value } : {}) });
        continue;
      }
      const upd = Object.fromEntries(["name", "section", "unit", "description", "default_value"].filter((k) => k in v).map((k) => [k, v[k] ?? ""]));
      if ("is_required" in v) upd.is_required = bool(v.is_required);
      if (Object.keys(upd).length) ops.push({ op: "attribute.update", item: id, ...upd });
    } else if (kind === "mappings") {
      if (id) ops.push({ op: "mapping.remove", id });
      if (!b.delete) ops.push({ op: "mapping.add", relationship_type: cur.relationship_type, source_type: cur.source_type, target_type: cur.target_type, note: cur.note || "" });
    } else if (kind === "pick_list_values") {
      if (b.delete && id) { ops.push({ op: "pick_list.retire_value", value_id: id }); continue; }
      if (!id) ops.push({ op: "pick_list.add_value", pick_list: ch.pick_list_ids[cur.pick_list] || cur.pick_list, value: cur.value });
    } else {
      if (b.delete) { ops.push({ op: "rule.remove", id }); continue; }
      if (!id) {
        const builtIn = ["name", "description", "display_id", "relationships"].includes(cur.field);
        ops.push({ op: "rule.create", rule_type: cur.rule_type, ...(builtIn ? { field_name: cur.field } : { attribute: cur.field }),
          ...(cur.entity_type ? { entity_type: cur.entity_type } : {}), param1: cur.param1 || "", param2: cur.param2 || "",
          severity: cur.severity || "error", message: cur.message || "" });
        continue;
      }
      const upd = Object.fromEntries(["param1", "param2", "severity", "message"].filter((k) => k in v).map((k) => [k, v[k] ?? ""]));
      if (Object.keys(upd).length) ops.push({ op: "rule.update", id, ...upd });
    }
  }
  return ops;
}

export function MetamodelGrids({ model, m, kindFromUrl }) {
  const [kind, setKind] = useState(kindFromUrl || "entity_types");
  const { data, error } = useApi(`/api/v1/models/${model}/grids/metamodel/${kind}`);
  const [config, setConfig] = useState(null);
  const [applied, setApplied] = useState(null);
  const allowed = canOn(model, "model.metamodel");
  const ok = allowed && metamodelEditable(m);
  const why = !allowed ? `Changing the metamodel: ${needsRole("model-admin", m?.name)}` : !ok ? `${m.name}'s metamodel cannot be changed here (locked, a library model or a lock is set).` : "";
  const columns = useMemo(() => (data ? mmColumns(kind, data.choices) : []), [data, kind]);
  const rows = useMemo(() => (data ? data.rows.map((r) => ({ ...r, is_directed: r.is_directed === undefined ? undefined : r.is_directed ? "Yes" : "No",
    is_required: r.is_required === undefined ? undefined : r.is_required ? "Yes" : "No", from_content: r.from_content ? "Yes" : "" })) : []), [data]);
  async function save(batch) {
    const changes = mmOps(kind, batch, data.choices);
    if (!changes.length) return { rows: [] };
    try {
      const out = await apiFetch(`/api/v1/models/${model}/metamodel/batch`, { method: "POST", body: JSON.stringify({ changes }) });
      refreshAll();
      return { rows: batch.map((_, i) => ({ row: i + 1, ok: true })), saved: batch.length, note: out.note };
    } catch (err) {
      // the server numbers changes, not rows: find the grid row of the failing change
      const n = Number((/Row (\d+)/.exec(err.message) || [])[1] || 0);
      let count = 0, row = 0;
      batch.forEach((b, i) => { const k = mmOps(kind, [b], data.choices).length; if (!row && n && count + k >= n) row = i + 1; count += k; });
      return { error: `${err.message.replace(/^Row \d+ /, `Row ${row || n} `)} Nothing was saved.`, row };
    }
  }
  return (
    <div>
      <div className="seg small">
        {MM_GRIDS.map(([k, l]) => <button key={k} className={k === kind ? "on" : ""}
          onClick={() => { setKind(k); window.location.hash = `/metamodel/${model}/metamodel/grids/${k}`; }}>{l}</button>)}
      </div>
      <p className="quiet seg-help">Every Save makes one new metamodel version with all the rows changed, or nothing if a row is wrong (the row is marked).
        Deleting an entity type retires it; deleting a relationship type removes it when unused; deleting a pick-list value retires it.</p>
      {!data ? <p className="quiet">{error || "Loading..."}</p> : (
        <Grid key={kind} columns={columns} rows={rows} canEdit={ok} why={why} onSave={save} name={`${m.name} - ${kind.replace(/_/g, " ")}`}
          initialConfig={applied} onConfig={setConfig} deleteLabel={kind === "entity_types" ? "Retire" : "Delete"} saveNote="Saved as one new metamodel version."
          views={<ViewPicker model={model} kind="metamodel_grid" target={kind} config={config || {}} onApply={setApplied} />} />
      )}
    </div>
  );
}
