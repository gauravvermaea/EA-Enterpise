// The model screens (phase 2): built for models with many entity types and thousands of entities.
//   #/metamodel/<m>/types                     Entity types: every type with its counts
//   #/metamodel/<m>/types/<typeId>            the entities of one type as a table (+ shows each one's relations)
//   #/metamodel/<m>/rels                      Relationship types: every type, how often used
//   #/metamodel/<m>/rels/<relTypeId>          the relationships of one type
//   #/metamodel/<m>/graph[/<kind>]            pictures: network, by domain, impact chain, hierarchy map, matrix
//   #/metamodel/<m>/entity/<id>[/relations|/history|/graph]   one entity
// Every list has a CSV button; every picture opens in draw.io (D256) and saves as SVG, PNG, CSV.
// Changing things arrives later: values and relationships in build phase 6; entity types,
// relationship types, mappings (allowed relationships) and rules in build phase 3. Those buttons
// are shown now, switched off, so the screens do not change shape when they arrive.
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { apiFetch, canOn } from "./auth";
import { downloadCsv } from "./exporting";
import { PendingMark } from "./ModelMarks";
import { EntityChanges, useEntityChanges, WasValue } from "./Changes";
import { AddRelationshipButton, EntityActions, NewEntityButton, NewRelationshipButton, RemoveRelationshipButton, RollBackButton, RowActions } from "./DataEntry";
import { fmtDate, fmtDateTime } from "./fmt";
import { EntityTree } from "./Trees";
import { EntityReasons, fieldClass, FieldQuality, q2, QualityBadge, QualityCell, RecheckAll, ScoreChip, useEntityQuality, useTypeQuality, useTypeScores } from "./QualityBits";
import { EditButton, entityTypeSpec, mappingSpec, relationshipTypeSpec } from "./MetamodelEditor";
import { EntityIcon } from "./DrawnView";
import { elementTypes } from "./elements.js";
import { LinkList, linksText } from "./Links";

const EntityGraph = lazy(() => import("./EntityGraph"));
const HierarchyMap = lazy(() => import("./HierarchyMap"));
const RelationMatrix = lazy(() => import("./RelationMatrix"));
const ValueStreamMap = lazy(() => import("./Maps").then((x) => ({ default: x.ValueStreamMap })));
const Roadmap = lazy(() => import("./Maps").then((x) => ({ default: x.Roadmap })));
const go = (path) => { window.location.hash = path; };
const PAGE = 100;

// ---------------------------------------------------------------- helpers
const cache = new Map();   // GET results kept for a minute, so moving between tabs is quick
let generation = 0;        // moves on after every change, so every screen reads afresh

// After a change: forget every cached answer and tell the screens to read again
export function refreshAll() {
  cache.clear();
  generation += 1;
  window.dispatchEvent(new Event("eax-refresh"));
}
// screens that cannot import this one (QualityBits) ask for the same with an event
window.addEventListener("eax-clear-cache", refreshAll);

export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null });
  const [gen, setGen] = useState(generation);
  useEffect(() => {
    const on = () => setGen(generation);
    window.addEventListener("eax-refresh", on);
    return () => window.removeEventListener("eax-refresh", on);
  }, []);
  useEffect(() => {
    if (!path) { setState({ data: null, error: null }); return undefined; }
    const hit = cache.get(path);
    if (hit && Date.now() - hit.at < 60000) { setState({ data: hit.data, error: null }); return undefined; }
    let live = true;
    setState((s) => ({ data: s.data && gen !== 0 ? s.data : null, error: null }));
    apiFetch(path)
      .then((data) => { cache.set(path, { data, at: Date.now() }); if (live) setState({ data, error: null }); })
      .catch((e) => live && setState({ data: null, error: e.message }));
    return () => { live = false; };
  }, [path, gen]);
  return state;
}

export function Swatch({ colour }) {
  return <span className="swatch" style={{ background: `#${colour || "eee"}` }} />;
}

// A button for something a later build phase brings: visible, switched off, saying when.
export function Later({ label, phase, model, what }) {
  const why = model?.is_locked
    ? `${model.name} is locked (read-only). ${what || label} will be possible in a copy of it (build phase 4) or in a project model (build phase ${phase}).`
    : `${what || label}: arrives in build phase ${phase}.`;
  return <button className="later" disabled title={why}>{label} <span className="phase">phase {phase}</span></button>;
}

function Loading({ error, what = "Loading..." }) {
  return error ? <p className="status bad">{error}</p> : <p className="quiet">{what}</p>;
}

function Checks({ errors, warnings, messages }) {
  if (!errors && !warnings) return <span className="ok-mark" title="Every rule passes">✓</span>;
  return (
    <span className="checks" title={(messages || []).join("\n")}>
      {errors > 0 && <span className="sev error">{errors}</span>}
      {warnings > 0 && <span className="sev warning">{warnings}</span>}
    </span>
  );
}

function Pager({ page, total, setPage }) {
  const pages = Math.max(1, Math.ceil(total / PAGE));
  if (pages <= 1) return <span className="quiet">{total} shown</span>;
  return (
    <span className="pager">
      <button disabled={page === 0} onClick={() => setPage(page - 1)}>‹</button>
      <span className="quiet">{page * PAGE + 1}–{Math.min(total, (page + 1) * PAGE)} of {total}</span>
      <button disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>›</button>
    </span>
  );
}

// sorting: click a column heading; again to reverse
function useSort(initial) {
  const [sort, setSort] = useState({ key: initial, desc: false });
  const head = (key, label, { key: reactKey, ...props } = {}) => (
    <th key={reactKey} {...props} className={`sortable${props.className ? ` ${props.className}` : ""}`}
      onClick={() => setSort((s) => ({ key, desc: s.key === key ? !s.desc : false }))}>
      {label}{sort.key === key ? (sort.desc ? " ▾" : " ▴") : ""}
    </th>
  );
  const apply = (rows, get) => {
    const value = (r) => get(r, sort.key);
    return [...rows].sort((a, b) => {
      const x = value(a), y = value(b);
      const r = typeof x === "number" && typeof y === "number" ? x - y
        : String(x ?? "").localeCompare(String(y ?? ""), undefined, { numeric: true, sensitivity: "base" });
      return sort.desc ? -r : r;
    });
  };
  return { head, apply };
}

export function CsvButton({ rows, name, title = "Download this table as CSV (opens in Excel)" }) {
  return <button onClick={() => downloadCsv(typeof rows === "function" ? rows() : rows, name)} title={title}>CSV</button>;
}

// ---------------------------------------------------------------- tab 1: entity types
export function EntityTypesTab({ model, m }) {
  const { data: mm, error } = useApi(`/api/v1/models/${model}/metamodel`);
  const tq = useTypeScores(m?.kind === "project" ? model : null).data;      // each type's data quality now (D246)
  const tScore = (t) => tq?.types?.find((x) => x.type === t.code);
  const [asTree, setAsTree] = useState(false);       // D250: the entity tree
  const [filter, setFilter] = useState("");
  const [domain, setDomain] = useState("");
  const [withEntities, setWithEntities] = useState(true);
  const { head, apply } = useSort("domain_order");
  const types = useMemo(() => (mm ? mm.domains.flatMap((l, i) => elementTypes(l).map((t) => ({
    ...t, domain: l.name, domain_id: l.id, colour: l.colour, domain_order: i * 1000 + l.entity_types.indexOf(t),
  }))) : []), [mm]);
  if (!mm) return <Loading error={error} />;
  const treeSeg = (
    <div className="seg small" role="tablist" style={{ marginBottom: 8 }}>
      <button className={!asTree ? "on" : ""} onClick={() => setAsTree(false)}>Table</button>
      <button className={asTree ? "on" : ""} onClick={() => setAsTree(true)}>Entity tree</button>
    </div>
  );
  if (asTree) return <div>{treeSeg}<EntityTree model={model} m={m} /></div>;
  const anyContent = types.some((t) => t.entity_count > 0);
  const f = filter.trim().toLowerCase();
  const shown = apply(types.filter((t) => (!f || `${t.name} ${t.code} ${t.description}`.toLowerCase().includes(f))
    && (!domain || t.domain_id === domain) && (!withEntities || !anyContent || t.entity_count > 0)),
  (r, k) => r[k]);
  return (
    <div>
      {treeSeg}
      <div className="toolbar">
        <input className="search" style={{ maxWidth: 260 }} placeholder="Filter entity types" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <select value={domain} onChange={(e) => setDomain(e.target.value)}>
          <option value="">All domains</option>
          {mm.domains.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        {anyContent && <label><input type="checkbox" checked={withEntities} onChange={(e) => setWithEntities(e.target.checked)} /> Only types with entities</label>}
        <CsvButton name={`${m.name} - entity types`} rows={() => [["Entity type", "Domain", "Entities", "Attributes", "Code", "Description"],
          ...shown.map((t) => [t.name, t.domain, t.entity_count, t.attribute_count, t.code, t.description])]} />
        <span className="er-spacer" />
        <EditButton model={model} m={m} label="+ Entity type" spec={() => entityTypeSpec(mm.domains)} />
        <button className="ed-btn" onClick={() => go(`/metamodel/${model}/entry`)} title="Enter entities of any type on the Data entry tab">+ Entity</button>
      </div>
      <div className="scroll">
        <table className="grid-table click-rows">
          <thead><tr>{head("name", "Entity type")}{head("domain_order", "Domain")}{head("entity_count", "Entities", { className: "num" })}
            {head("attribute_count", "Attributes", { className: "num" })}{tq && <th className="num" title={`Each entity type's data quality as last calculated${tq.calculated_to ? ` (${fmtDateTime(tq.calculated_to)})` : ""}: completeness, rules, freshness`}>Quality</th>}{head("code", "Code")}<th>Description</th></tr></thead>
          <tbody>
            {shown.map((t) => (
              <tr key={t.id} onClick={() => go(`/metamodel/${model}/types/${t.id}`)}>
                <td><Swatch colour={t.colour} /> <a href={`#/metamodel/${model}/types/${t.id}`}><strong>{t.name}</strong></a></td>
                <td>{t.domain}</td>
                <td className="num">{t.entity_count}</td>
                <td className="num">{t.attribute_count}</td>
                {tq && <td className="num">{tScore(t) ? <a href={`#/metamodel/${model}/quality/type/${encodeURIComponent(t.name)}`}><ScoreChip score={tScore(t).score} bands={tq.bands}
                  title={`${t.name}: data quality ${q2(tScore(t).score)} · completeness ${q2(tScore(t).completeness)} · ${tScore(t).failing} failing a rule · ${tScore(t).stale} stale`} /></a> : <span className="quiet">-</span>}</td>}
                <td><code className="quiet">{t.code}</code></td>
                <td className="quiet clip">{t.description}</td>
              </tr>
            ))}
            {!shown.length && <tr><td colSpan="6" className="quiet">No entity types match.</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="quiet">{shown.length} of {types.length} entity types. Click one to see its entities.</p>
    </div>
  );
}

// ---------------------------------------------------------------- one type: its entities as a table
function RelationsUnder({ model, entityId, colSpan }) {
  const { data: e, error } = useApi(`/api/v1/models/${model}/entities/${entityId}`);
  return (
    <tr className="expanded">
      <td colSpan={colSpan}>
        {!e ? <Loading error={error} /> : !e.relationships.length && !e.children.length && !e.parent_id
          ? <span className="quiet">No relationships.</span>
          : (
            <table className="grid-table inner">
              <tbody>
                {e.parent_id && (
                  <tr><td className="rel-verb">part of</td><td><a href={`#/metamodel/${model}/entity/${e.parent_id}`}>{e.parent_name}</a></td><td className="quiet">parent</td><td /></tr>
                )}
                {e.relationships.map((r) => (
                  <tr key={`${r.id}-${r.direction}`}>
                    <td className="rel-verb">{r.direction === "outgoing" ? `${r.verb} →` : `← ${r.verb}`}</td>
                    <td><Swatch colour={r.other_colour} /> <a href={`#/metamodel/${model}/entity/${r.other_id}`}>{r.other_name}</a>
                      <span className="quiet"> {r.other_display_id}</span></td>
                    <td className="quiet">{r.other_type} · {r.relationship_type}</td>
                    <td>{!r.allowed && <span className="sev warning" title="The metamodel has no rule allowing this relationship">not in metamodel</span>}</td>
                  </tr>
                ))}
                {e.children.length > 0 && (
                  <tr><td className="rel-verb">has parts</td><td colSpan="3">
                    {e.children.slice(0, 30).map((c, i) => <span key={c.id}>{i > 0 && ", "}<a href={`#/metamodel/${model}/entity/${c.id}`}>{c.name}</a></span>)}
                    {e.children.length > 30 && <span className="quiet"> and {e.children.length - 30} more</span>}
                  </td></tr>
                )}
              </tbody>
            </table>
          )}
      </td>
    </tr>
  );
}

export function TypeEntitiesTable({ model, m, typeId }) {
  const { data: t, error } = useApi(`/api/v1/models/${model}/entity-types/${typeId}/table`);
  const [filter, setFilter] = useState("");
  const [check, setCheck] = useState("");
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState({});
  const [hiddenCols, setHiddenCols] = useState([]);
  const [asTree, setAsTree] = useState(false);       // D250: this entity type's tree
  const tqt = useTypeQuality(m?.kind === "project" ? model : null, typeId).data;     // data quality as last calculated (D245)
  const { head, apply } = useSort("display_id");
  useEffect(() => { setPage(0); }, [filter, check, typeId]);
  if (!t) return <Loading error={error} />;
  const treeSeg = (
    <div className="seg small" role="tablist" style={{ margin: "6px 0" }}>
      <button className={!asTree ? "on" : ""} onClick={() => setAsTree(false)}>Table</button>
      <button className={asTree ? "on" : ""} onClick={() => setAsTree(true)}>Tree</button>
    </div>
  );
  if (asTree) return <div><p className="quiet crumbs"><a href={`#/metamodel/${model}/types`}>Entity types</a> / {t.entity_type.name}</p>{treeSeg}<EntityTree model={model} m={m} typeId={typeId} /></div>;
  const et = t.entity_type;
  const cols = t.columns.filter((c) => !hiddenCols.includes(c.code));
  const f = filter.trim().toLowerCase();
  const rows = apply(t.rows.filter((r) => {
    if (check === "errors" && !r.errors) return false;
    if (check === "warnings" && !r.warnings) return false;
    if (check === "any" && !r.errors && !r.warnings) return false;
    if (check === "clean" && (r.errors || r.warnings)) return false;
    return !f || `${r.display_id} ${r.name} ${r.description} ${r.parent_name || ""} ${Object.values(r.values).join(" ")}`.toLowerCase().includes(f);
  }), (r, k) => (k.startsWith("v:") ? r.values[k.slice(2)] : k === "checks" ? r.errors * 1000 + r.warnings : r[k]));
  const pageRows = rows.slice(page * PAGE, (page + 1) * PAGE);
  const withIssues = t.rows.filter((r) => r.errors || r.warnings).length;
  const colSpan = 8 + cols.length + (tqt ? 1 : 0);

  function exportCsv() {
    const header = ["Display ID", "Name", "Description", "Parent", "Status", ...t.columns.map((c) => c.name), "Relationships", "Errors", "Warnings", "Messages", "Created in metamodel v", "Last changed in metamodel v"];
    const body = rows.map((r) => [r.display_id, r.name, r.description, r.parent_name, r.status,
      ...t.columns.map((c) => r.values[c.code]), r.relationship_count, r.errors, r.warnings, r.messages.join("; "), r.created_mm_version, r.modified_mm_version]);
    downloadCsv([header, ...body], `${m.name} - ${et.name}`);
  }

  return (
    <div>
      <p className="quiet crumbs">
        <a href={`#/metamodel/${model}/types`}>Entity types</a> / <Swatch colour={et.colour} /> <strong>{et.name}</strong>
        <span> · {et.domain} domain · <a href={`#/metamodel/${model}/type/${et.id}`}>definition and rules</a>
          {" · "}<a href={`#/metamodel/${model}/diagram/${et.id}`}>in the ER diagram</a></span>
      </p>
      {treeSeg}
      <div className="toolbar">
        <input className="search" style={{ maxWidth: 280 }} placeholder={`Search ${t.rows.length} ${et.name} entities`} value={filter} onChange={(e) => setFilter(e.target.value)} />
        <select value={check} onChange={(e) => setCheck(e.target.value)} title="Validation results">
          <option value="">All ({t.rows.length})</option>
          <option value="any">With errors or warnings ({withIssues})</option>
          <option value="errors">With errors</option>
          <option value="warnings">With warnings</option>
          <option value="clean">Passing every rule</option>
        </select>
        {t.columns.length > 0 && (
          <details className="col-chooser">
            <summary>Columns ({cols.length}/{t.columns.length})</summary>
            <div>
              {t.columns.map((c) => (
                <label key={c.code}><input type="checkbox" checked={!hiddenCols.includes(c.code)}
                  onChange={() => setHiddenCols((h) => (h.includes(c.code) ? h.filter((x) => x !== c.code) : [...h, c.code]))} /> {c.name}</label>
              ))}
            </div>
          </details>
        )}
        <button onClick={exportCsv}>CSV</button>
        {tqt && <span className="small">Data quality <ScoreChip score={tqt.summary.score} bands={tqt.bands} title={`${q2(tqt.summary.score)} as calculated ${tqt.calculated_to ? fmtDateTime(tqt.calculated_to) : "- not yet"}`} />{" "}
          <RecheckAll model={model} type={typeId} /></span>}
        <span className="er-spacer" />
        <Pager page={page} total={rows.length} setPage={setPage} />
        <NewEntityButton model={model} m={m} typeId={typeId} typeName={et.name} retired={et.status === "retired"} />
        <button onClick={() => go(`/metamodel/${model}/entry/${typeId}`)} title={`Enter many ${et.name} entities as rows`}>Data entry</button>
      </div>
      <div className="scroll table-frame">
        <table className="grid-table entity-table">
          <thead>
            <tr>
              <th className="stick0" title="Show the relationships" />
              {head("display_id", "ID", { className: "stick1" })}
              {head("name", "Name", { className: "stick2" })}
              {head("checks", "Rules")}
              {tqt && <th title="Data quality as last calculated; ↻ rechecks the row now">Quality</th>}
              {head("parent_name", "Parent")}
              {cols.map((c) => head(`v:${c.code}`, <>{c.name}{c.is_required && <span className="req" title="Required">*</span>}</>, { key: c.code }))}
              {head("relationship_count", "Rel.", { className: "num" })}
              {head("modified_mm_version", "Metamodel v", { title: "Metamodel version it was created in / last changed in" })}
              {head("modified_at", "Changed")}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((r) => [
              <tr key={r.id} className={open[r.id] ? "is-open" : ""}>
                <td className="stick0">
                  <button className="expand" title={open[r.id] ? "Hide relationships" : "Show related entities"}
                    onClick={() => setOpen((o) => ({ ...o, [r.id]: !o[r.id] }))}>{open[r.id] ? "−" : "+"}</button>
                </td>
                <td className="stick1 nowrap">{r.display_id}</td>
                <td className="stick2"><a href={`#/metamodel/${model}/entity/${r.id}`}>{r.name}</a>{" "}
                  <RowActions model={model} m={m} entityId={r.id} name={r.name} retiredType={et.status === "retired"} /></td>
                <td><Checks {...r} /></td>
                {tqt && <td><QualityCell model={model} entity={r.id} row={tqt.entities?.[r.id]} bands={tqt.bands} /></td>}
                <td>{r.parent_id ? <a href={`#/metamodel/${model}/entity/${r.parent_id}`}>{r.parent_name}</a> : ""}</td>
                {cols.map((c) => {
                  const v = r.values[c.code];
                  const qc = fieldClass(tqt?.entities?.[r.id], c.code);
                  return <td key={c.code} className={qc || (c.is_required && (v === undefined || v === "") ? "missing" : "")}
                    title={(tqt?.entities?.[r.id]?.fields?.[c.code] || []).map((x) => x.message).join("\n") || undefined}>
                    {v ?? ""}{v !== undefined && c.unit ? ` ${c.unit}` : ""}</td>;
                })}
                <td className="num">{r.relationship_count}</td>
                <td className="quiet nowrap" title={`Created in metamodel v${r.created_mm_version}, last changed in v${r.modified_mm_version}`}>
                  v{r.created_mm_version}{r.modified_mm_version !== r.created_mm_version ? ` / v${r.modified_mm_version}` : ""}</td>
                <td className="quiet nowrap" title={`by ${r.modified_by}`}>{fmtDate(r.modified_at)}</td>
              </tr>,
              open[r.id] && <RelationsUnder key={`${r.id}-rel`} model={model} entityId={r.id} colSpan={colSpan} />,
            ])}
            {!pageRows.length && <tr><td colSpan={colSpan} className="quiet">{t.rows.length ? "No entities match." : `No ${et.name} entities in this model yet.`}</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="quiet">
        * required. Rules: <span className="sev error">n</span> errors, <span className="sev warning">n</span> warnings
        ({t.rules} rules apply to {et.name}); hover to read them. A failed rule never stops a save: the value is kept with an
        override flag and its details, and the warning shows until someone fixes it. Shaded cells are required values that are missing.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- tab 2: relationship types
export function RelationshipTypesTab({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/relationship-types`);
  const [usedOnly, setUsedOnly] = useState(true);
  const { head, apply } = useSort("order");
  if (!data) return <Loading error={error} />;
  const anyUsed = data.some((r) => r.relationship_count > 0);
  const rows = apply(data.map((r, i) => ({ ...r, order: i })).filter((r) => !usedOnly || !anyUsed || r.relationship_count > 0), (r, k) => r[k]);
  return (
    <div>
      <div className="toolbar">
        {anyUsed && <label><input type="checkbox" checked={usedOnly} onChange={(e) => setUsedOnly(e.target.checked)} /> Only types in use</label>}
        <CsvButton name={`${m.name} - relationship types`} rows={() => [["Relationship type", "Reads as", "Category", "Directed", "In this model", "Allowed type pairs", "Outside the rules", "Description"],
          ...rows.map((r) => [r.name, r.verb, r.category, r.is_directed ? "yes" : "no", r.relationship_count, r.allowed_pairs, r.outside_rules, r.description])]} />
        <span className="er-spacer" />
        <EditButton model={model} m={m} label="+ Relationship type" spec={relationshipTypeSpec()} />
        <MappingButton model={model} m={m} relTypes={data} />
        <NewRelationshipButton model={model} m={m} />
      </div>
      <table className="grid-table click-rows">
        <thead><tr>{head("name", "Relationship type")}{head("verb", "Reads as")}{head("category", "Category")}
          {head("relationship_count", "In this model", { className: "num" })}{head("allowed_pairs", "Allowed type pairs", { className: "num" })}
          {head("outside_rules", "Outside the rules", { className: "num" })}<th>Description</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} onClick={() => go(`/metamodel/${model}/rels/${r.id}`)}>
              <td><a href={`#/metamodel/${model}/rels/${r.id}`}><strong>{r.name}</strong></a></td>
              <td>A <em>{r.verb}</em> B{r.is_directed ? "" : " (both ways)"}</td>
              <td>{r.category}</td>
              <td className="num">{r.relationship_count}</td>
              <td className="num">{r.allowed_pairs}</td>
              <td className="num">{r.outside_rules > 0 ? <span className="sev warning">{r.outside_rules}</span> : 0}</td>
              <td className="quiet clip">{r.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="quiet">
        "Allowed type pairs" are the mappings: which source and target entity types the metamodel allows for the
        relationship type. "Outside the rules" counts relationships whose pair of types has no mapping.
      </p>
    </div>
  );
}


export function RelationshipsOfType({ model, m, relTypeId }) {
  const { data: types } = useApi(`/api/v1/models/${model}/relationship-types`);
  const { data, error } = useApi(`/api/v1/models/${model}/relationships?type=${relTypeId}`);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(0);
  const { head, apply } = useSort("source_name");
  useEffect(() => { setPage(0); }, [filter, relTypeId]);
  const rt = types?.find((r) => r.id === relTypeId);
  if (!data) return <Loading error={error} />;
  const f = filter.trim().toLowerCase();
  const rows = apply(data.filter((r) => !f || `${r.source_name} ${r.source_type} ${r.target_name} ${r.target_type} ${r.source_display_id} ${r.target_display_id}`.toLowerCase().includes(f)), (r, k) => r[k]);
  return (
    <div>
      <p className="quiet crumbs"><a href={`#/metamodel/${model}/rels`}>Relationship types</a> / <strong>{rt?.name || "..."}</strong>
        {rt && <span> · A <em>{rt.verb}</em> B · {rt.allowed_pairs} allowed type pairs</span>}</p>
      <div className="toolbar">
        <input className="search" style={{ maxWidth: 280 }} placeholder="Filter by entity or type" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <CsvButton name={`${m.name} - ${rt?.name || "relationships"}`} rows={() => [["Source ID", "Source", "Source type", "Relationship", "Target ID", "Target", "Target type", "In the metamodel"],
          ...rows.map((r) => [r.source_display_id, r.source_name, r.source_type, r.verb, r.target_display_id, r.target_name, r.target_type, r.allowed ? "yes" : "no"])]} />
        <span className="er-spacer" />
        <NewRelationshipButton model={model} m={m} relType={rt} label={`+ ${rt?.name || "Relationship"}`} />
        <Pager page={page} total={rows.length} setPage={setPage} />
      </div>
      <table className="grid-table">
        <thead><tr>{head("source_name", "Source")}{head("source_type", "Source type")}<th>Relationship</th>{head("target_name", "Target")}{head("target_type", "Target type")}<th /></tr></thead>
        <tbody>
          {rows.slice(page * PAGE, (page + 1) * PAGE).map((r) => (
            <tr key={r.id}>
              <td><Swatch colour={r.source_colour} /> <a href={`#/metamodel/${model}/entity/${r.source_id}`}>{r.source_name}</a> <span className="quiet">{r.source_display_id}</span></td>
              <td className="quiet">{r.source_type}</td>
              <td className="rel-verb">{r.verb} →</td>
              <td><Swatch colour={r.target_colour} /> <a href={`#/metamodel/${model}/entity/${r.target_id}`}>{r.target_name}</a> <span className="quiet">{r.target_display_id}</span></td>
              <td className="quiet">{r.target_type}</td>
              <td>{!r.allowed && <span className="sev warning" title="No mapping allows this pair of types">not in metamodel</span>}
                {" "}<RemoveRelationshipButton model={model} m={m} e={{ name: r.source_name }} r={{ id: r.id, verb: r.verb, other_name: r.target_name }} /></td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan="6" className="quiet">No relationships of this type{f ? " match" : " in this model"}.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- graph tab
const GRAPH_KINDS = [
  ["network", "Network", "Entities and their relationships; or one entity in the middle with what surrounds it"],
  ["domains", "By domain", "Entities in bands by ArchiMate domain, top to bottom: read traceability from strategy down to technology"],
  ["impact", "Impact chain", "From one entity, follow the lines one way: what it leads to (impact) or what leads to it (dependencies)"],
  ["hierarchy", "Hierarchy map", "Parents holding their parts as nested boxes (the capability map), coloured by an attribute as a heat map"],
  ["matrix", "Matrix", "One entity type against another, with the relationships between them in the cells"],
  ["valuestreams", "Value stream map", "Each value stream's stages with the capabilities that enable them, coloured by an attribute; or as a value stream x capability heat map"],
  ["roadmap", "Roadmap", "Plateaus, work packages and deliverables on a timeline from their start and end dates"],
];

export function GraphTab({ model, kind }) {
  const k = GRAPH_KINDS.some(([x]) => x === kind) ? kind : "network";
  return (
    <div>
      <div className="seg" role="tablist" aria-label="Kind of picture">
        {GRAPH_KINDS.map(([x, label, help]) => (
          <button key={x} role="tab" aria-selected={k === x} className={k === x ? "on" : ""} title={help}
            onClick={() => go(`/metamodel/${model}/graph/${x}`)}>{label}</button>
        ))}
      </div>
      <p className="quiet seg-help">{GRAPH_KINDS.find(([x]) => x === k)[2]}.</p>
      <Suspense fallback={<p>Loading the picture...</p>}>
        {k === "hierarchy" ? <HierarchyMap model={model} />
          : k === "valuestreams" ? <ValueStreamMap model={model} />
          : k === "roadmap" ? <Roadmap model={model} />
          : k === "matrix" ? <RelationMatrix model={model} />
          : <EntityGraph key={k} model={model} kind={k} />}
      </Suspense>
    </div>
  );
}

// ---------------------------------------------------------------- one entity
function WarningList({ warnings }) {
  if (!warnings.length) return <p className="all-pass">✓ Every validation rule passes.</p>;
  const errors = warnings.filter((w) => w.severity === "error").length;
  return (
    <div className="warn-box">
      <strong>{errors > 0 && `${errors} error${errors > 1 ? "s" : ""}`}{errors > 0 && warnings.length > errors && ", "}
        {warnings.length > errors && `${warnings.length - errors} warning${warnings.length - errors > 1 ? "s" : ""}`}</strong>
      <ul>{warnings.map((w, i) => <li key={i}><span className={`sev ${w.severity}`}>{w.severity}</span> {w.message}</li>)}</ul>
      <p className="quiet">A failed rule never stops a save: the value is saved with a flag and the rule's details (who saved it and when),
        and the warning shows here until it is fixed (D48).</p>
    </div>
  );
}

function DetailsTab({ model, m, e, q }) {
  const ec = useEntityChanges(model, m, e.id);
  const mayEdit = canOn(model, "model.content");
  const fq = (code) => <FieldQuality model={model} entity={e.id} code={code} q={q} mayEdit={mayEdit} />;
  const f = (code) => ec.fields[String(code).toLowerCase()];
  const hl = (code) => (f(code) ? "pending-field" : "");
  const sections = [];
  for (const a of e.attributes) {
    let s = sections.find((x) => x.name === (a.section || "Attributes"));
    if (!s) sections.push(s = { name: a.section || "Attributes", items: [] });
    s.items.push(a);
  }
  const fieldWarnings = (code) => e.warnings.filter((w) => w.code === code);
  const Status = ({ list, hide }) => (hide && !list.length ? null : list.length
    ? <span className={`sev ${list.some((w) => w.severity === "error") ? "error" : "warning"}`} title={list.map((w) => w.message).join("\n")}>
      {list.map((w) => w.message).join("; ")}</span>
    : <span className="ok-mark">✓</span>);
  return (
    <div>
      <WarningList warnings={e.warnings} />
      <EntityChanges model={model} entity={e} ec={ec} />
      <div className="toolbar">
        <CsvButton name={`${e.display_id} ${e.name} - details`} rows={() => [["Section", "Field", "Value", "Type", "Required", "Check"],
          ["Basic", "Name", e.name, "Text", "yes", fieldWarnings("name").map((w) => w.message).join("; ")],
          ...[["Display ID", e.display_id, "Generated", "display_id"], ["Description", e.description, "Text", "description"],
            ["Parent", e.parent_name, "Entity", "parent"], ["Status", e.status, "Workflow", "status"], ["Tags", (e.tags || []).join(", "), "Tags", "tags"]]
            .map(([label, v, t, code]) => ["Basic", label, v, t, "", fieldWarnings(code).map((w) => w.message).join("; ")]),
          ...e.attributes.map((a) => [a.section, a.name, a.data_type === "url" ? linksText(a.value) : a.value, a.data_type_name, a.is_required ? "yes" : "", a.warnings.map((w) => w.message).join("; ")])]} />
        <span className="er-spacer" />
        <EntityActions model={model} m={m} e={e} />
      </div>
      <table className="grid-table attr-table">
        <thead><tr><th>Field</th><th>Value</th><th>Type</th><th>Check</th></tr></thead>
        <tbody>
          <tr className="section-row"><td colSpan="4">Basic</td></tr>
          <tr className={[hl("name"), fieldClass(q, "name")].join(" ").trim()}><th>Name <span className="req">*</span></th><td>{e.name} <WasValue f={f("name")} /></td><td className="quiet">Text</td><td><Status list={fieldWarnings("name")} hide={!!q?.fields?.name} />{fq("name")}</td></tr>
          <tr><th>Display ID</th><td>{e.display_id}</td><td className="quiet">Generated</td><td><Status list={fieldWarnings("display_id")} /></td></tr>
          <tr className={[hl("description"), fieldClass(q, "description")].join(" ").trim()}><th>Description</th><td className="pre">{e.description} <WasValue f={f("description")} /></td><td className="quiet">Text</td><td><Status list={fieldWarnings("description")} hide={!!q?.fields?.description} />{fq("description")}</td></tr>
          <tr className={hl("parent")}><th>Parent</th><td>{e.parent_id ? <a href={`#/metamodel/${model}/entity/${e.parent_id}`}>{e.parent_name}</a> : <span className="quiet">-</span>}</td><td className="quiet">Entity</td><td><Status list={fieldWarnings("parent")} /></td></tr>
          <tr className={hl("status")}><th>Status</th><td>{e.status} <WasValue f={f("status")} /></td><td className="quiet">Workflow</td><td><Status list={fieldWarnings("status")} /></td></tr>
          <tr className={hl("tags")}><th>Tags</th><td>{(e.tags || []).length ? e.tags.map((t) => <span key={t} className="tag">{t}</span>) : <span className="quiet">-</span>}</td><td className="quiet">Tags</td><td><Status list={fieldWarnings("tags")} /></td></tr>
          {sections.map((s) => [
            <tr key={`s-${s.name}`} className="section-row"><td colSpan="4">{s.name}</td></tr>,
            ...s.items.map((a) => {
              const empty = a.value === null || a.value === "";
              return (
                <tr key={a.code} className={[a.warnings.length ? "has-warning" : "", hl(`value:${a.code}`), fieldClass(q, a.code)].join(" ").trim()}>
                  <th>{a.name}{a.is_required && <span className="req" title="Required">*</span>}</th>
                  <td>{empty ? <span className="quiet">not set</span>
                    : a.data_type === "url" ? <LinkList value={a.value} />
                    : a.ref_id ? <a href={`#/metamodel/${model}/entity/${a.ref_id}`}>{a.value}</a>
                    : <>{a.value}{a.unit && ` ${a.unit}`}</>} <WasValue f={f(`value:${a.code}`)} /></td>
                  <td className="quiet" title={a.pick_list_values.length ? `One of: ${a.pick_list_values.join(", ")}` : undefined}>
                    {a.data_type_name}</td>
                  <td><Status list={a.warnings} hide={!!q?.fields?.[a.code]} />{a.override && <span className="override-mark" title={`Saved although it fails the rule, by ${a.override.by} on ${fmtDateTime(a.override.at)}`}> saved anyway</span>}{fq(a.code)}</td>
                </tr>
              );
            }),
          ])}
        </tbody>
      </table>
      {e.children.length > 0 && (
        <>
          <h3>Parts ({e.children.length})</h3>
          <p>{e.children.map((c, i) => <span key={c.id}>{i > 0 && ", "}<a href={`#/metamodel/${model}/entity/${c.id}`}>{c.name}</a></span>)}</p>
        </>
      )}
      <p className="quiet">Created {fmtDateTime(e.created_at)} by {e.created_by} in metamodel v{e.created_mm_version} · changed {fmtDateTime(e.modified_at)} by {e.modified_by} in metamodel v{e.modified_mm_version} · version {e.row_version}</p>
    </div>
  );
}

function RelationsTab({ model, m, e }) {
  const [filter, setFilter] = useState("");
  const [showAllowed, setShowAllowed] = useState(false);
  const f = filter.trim().toLowerCase();
  const groups = [];
  for (const r of e.relationships) {
    if (f && !`${r.other_name} ${r.other_type} ${r.relationship_type} ${r.verb}`.toLowerCase().includes(f)) continue;
    const key = `${r.direction}|${r.relationship_type}`;
    let g = groups.find((x) => x.key === key);
    if (!g) groups.push(g = { key, direction: r.direction, type: r.relationship_type, verb: r.verb, items: [] });
    g.items.push(r);
  }
  const used = new Set(e.relationships.map((r) => `${r.direction}|${r.relationship_type}|${r.other_type_id}`));
  const outside = e.relationships.filter((r) => !r.allowed).length;
  return (
    <div>
      <div className="toolbar">
        <input className="search" style={{ maxWidth: 260 }} placeholder="Filter relations" value={filter} onChange={(ev) => setFilter(ev.target.value)} />
        <label><input type="checkbox" checked={showAllowed} onChange={(ev) => setShowAllowed(ev.target.checked)} /> Show what the metamodel allows ({e.allowed.length})</label>
        <CsvButton name={`${e.display_id} ${e.name} - relations`} rows={() => [["Direction", "Relationship", "Reads as", "Other ID", "Other entity", "Other type", "Status", "In the metamodel"],
          ...e.relationships.map((r) => [r.direction, r.relationship_type, r.verb, r.other_display_id, r.other_name, r.other_type, r.status, r.allowed ? "yes" : "no"])]} />
        <span className="er-spacer" />
        <AddRelationshipButton model={model} m={m} e={e} />
      </div>
      {outside > 0 && <p><span className="sev warning">{outside} not in metamodel</span> <span className="quiet">These relationships have no mapping that allows them. They are kept, and flagged.</span></p>}
      {!groups.length && <p className="quiet">{e.relationships.length ? "No relations match." : "No relationships yet."}</p>}
      {groups.map((g) => (
        <div key={g.key} className="rel-group">
          <h3>{g.direction === "outgoing" ? <>{e.name} <em>{g.verb}</em> →</> : <>← <em>{g.verb}</em> {e.name}</>}
            <span className="quiet"> {g.type} · {g.items.length}</span></h3>
          <table className="grid-table fixed-cols">
            <colgroup><col style={{ width: "45%" }} /><col style={{ width: "25%" }} /><col style={{ width: "12%" }} /><col /></colgroup>
            <tbody>
              {g.items.map((r) => (
                <tr key={r.id}>
                  <td><Swatch colour={r.other_colour} /> <a href={`#/metamodel/${model}/entity/${r.other_id}`}>{r.other_name}</a> <span className="quiet">{r.other_display_id}</span></td>
                  <td className="quiet">{r.other_type}</td>
                  <td className="quiet">{r.status}</td>
                  <td>{!r.allowed && <span className="sev warning" title="No mapping in the metamodel allows this">not in metamodel</span>}
                    {" "}<RemoveRelationshipButton model={model} m={m} e={e} r={r} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {showAllowed && (
        <>
          <h3>What the metamodel allows for {e.entity_type}</h3>
          <p className="quiet">+ Relationship offers these first. A relationship outside them can still be added: that adds the mapping to this
            model's metamodel as a new version, flagged as added from data entry for a Model Admin to review (D49).</p>
          <table className="grid-table">
            <thead><tr><th>Direction</th><th>Relationship</th><th>Other entity type</th><th>In use</th></tr></thead>
            <tbody>
              {e.allowed.map((a, i) => (
                <tr key={i}>
                  <td>{a.direction === "outgoing" ? "this →" : "→ this"}</td>
                  <td>{a.relationship_type} <span className="quiet">({a.verb})</span></td>
                  <td><a href={`#/metamodel/${model}/types/${a.other_type_id}`}>{a.other_type}</a></td>
                  <td>{used.has(`${a.direction}|${a.relationship_type}|${a.other_type_id}`) ? "✓" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

const KINDS = [["", "Everything"], ["entity", "Entity"], ["attribute", "Values"], ["relationship", "Relationships"]];
const verbOf = (op) => (op === "insert" ? "added" : op === "delete" ? "removed" : "changed");

// the changes of one moment (the same person within the same second) as one point on the timeline
function moments(events) {
  const out = [];
  for (const ev of events) {   // newest first
    const key = `${Math.floor(new Date(ev.at).getTime() / 1000)}|${ev.by}`;
    let g = out[out.length - 1];
    if (!g || g.key !== key) out.push(g = { key, id: ev.id, at: ev.at, by: ev.by, events: [] });
    g.events.push(ev);
  }
  // within a moment: the entity itself first (created or changed), then its values, then relationships
  const order = { entity: 0, attribute: 1, relationship: 2 };
  out.forEach((g) => g.events.sort((x, y) => (order[x.kind] ?? 9) - (order[y.kind] ?? 9)));
  return out;
}

function AsOfPanel({ model, m, entityId, point, list, index, setPoint }) {
  const { data: a, error } = useApi(`/api/v1/models/${model}/entities/${entityId}/as-of?event=${point}`);
  if (!a) return <Loading error={error} />;
  const rows = [...a.fields.map((f) => ({ ...f, section: "Basic", name: f.field })), ...a.attributes];
  const changed = rows.filter((r) => r.changed).length;
  const removed = a.relationships.filter((r) => !r.still_there);
  // what this moment itself did (highlighted; hover a highlighted value for its old value)
  const created = !!a.moment?.created;
  const here = rows.filter((r) => r.changed_here).length;
  const addedHere = a.relationships.filter((r) => r.added_here).length;
  const removedHere = a.moment?.removed_relationships || [];
  const did = [
    created && "created the entity",
    here && `${created ? "set" : "changed"} ${here} value${here > 1 ? "s" : ""}`,
    addedHere && `added ${addedHere} relationship${addedHere > 1 ? "s" : ""}`,
    removedHere.length && `removed ${removedHere.length} relationship${removedHere.length > 1 ? "s" : ""}`,
  ].filter(Boolean);
  return (
    <div>
      <div className="asof-head">
        <div>
          <strong>As it was on {fmtDateTime(a.as_of.at)}</strong>
          <span className="quiet"> · after a change by {a.as_of.by} · change {a.as_of.position} of {a.as_of.of}</span>
          <div className="asof-did">This change {did.length ? did.join(", ") : "changed nothing shown here"}
            {here > 0 && <span className="quiet"> (highlighted in yellow{created ? "" : ", shown as old → new"})</span>}</div>
          <div className="quiet">{changed ? `${changed} value${changed > 1 ? "s" : ""} differ from now (shaded in the Now column)` : "Every value is the same as now"}
            {removed.length > 0 && ` · ${removed.length} relationship${removed.length > 1 ? "s" : ""} since removed`}
            {a.added_since.length > 0 && ` · ${a.added_since.length} added since`}</div>
        </div>
        <span className="er-spacer" />
        <button disabled={index >= list.length - 1} onClick={() => setPoint(list[index + 1].id)} title="The change before this one">◀ Earlier</button>
        <button disabled={index <= 0} onClick={() => setPoint(list[index - 1].id)} title="The change after this one">Later ▶</button>
        <button className="primary" onClick={() => setPoint(null)}>Current</button>
        <RollBackButton model={model} m={m} e={{ id: entityId, name: a.entity.name }} eventId={a.as_of.event_id} at={a.as_of.at} />
        <CsvButton name={`${a.entity.display_id} ${a.entity.name} - as of ${String(a.as_of.at).slice(0, 19).replace(/[T:]/g, "-")}`}
          rows={() => [["Section", "Field", "Then", "Now", "Changed"], ...rows.map((r) => [r.section, r.name, r.then, r.now, r.changed ? "yes" : ""]),
            ...a.relationships.map((r) => ["Relationship", `${r.direction === "outgoing" ? "" : "← "}${r.verb} ${r.other_name}`, "yes", r.still_there ? "yes" : "", r.still_there ? "" : "yes"]),
            ...a.added_since.map((r) => ["Relationship", `${r.direction === "outgoing" ? "" : "← "}${r.verb} ${r.other_name}`, "", "yes", "yes"])]} />
      </div>
      <table className="grid-table attr-table asof">
        <thead><tr><th>Field</th><th>Then: this change, old → new</th><th>Now</th></tr></thead>
        <tbody>
          {rows.map((r, i) => {
            const isHere = r.changed_here;
            const how = created ? "set" : r.before == null ? "set" : r.then == null ? "cleared" : "changed";
            return (
              <tr key={`${r.name}-${i}`} className={isHere ? "changed-here" : ""}>
                <th>{r.name}{isHere && <span className={`here-chip ${how}`}>{created ? "set when created" : `${how} here`}</span>}</th>
                <td className={isHere ? "then-here" : ""}>
                  {isHere && !created ? (
                    <span className="old-new">
                      <span className="old-val" title="Old value, before this change">{r.before ?? <em>not set</em>}</span>
                      <span className="arrow" aria-label="changed to">→</span>
                      <span className="new-val" title="New value, after this change">{r.then ?? <em>not set</em>}</span>
                    </span>
                  ) : (r.then ?? <span className="quiet">not set</span>)}
                </td>
                <td className={r.changed ? "differs-now" : "quiet"}>{r.now ?? "not set"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <h3>Relationships then ({a.relationships.length})</h3>
      {!a.relationships.length && <p className="quiet">None.</p>}
      <ul className="asof-rels">
        {a.relationships.map((r, i) => (
          <li key={i} className={`${r.still_there ? "" : "gone"}${r.added_here ? " added-here" : ""}`}>
            {r.direction === "outgoing" ? <>{a.entity.name} <em>{r.verb}</em> → </> : <>← <em>{r.verb}</em> </>}
            {r.other_id ? <a href={`#/metamodel/${model}/entity/${r.other_id}`}>{r.other_name}</a> : r.other_name}
            {r.added_here && <span className="here-chip added">added here</span>}
            {!r.still_there && <span className="sev warning">removed since</span>}
          </li>
        ))}
        {removedHere.map((r, i) => (
          <li key={`gone-${i}`} className="removed-here" title="This change removed the relationship">
            <del>{r.direction === "outgoing" ? <>{a.entity.name} <em>{r.verb}</em> → </> : <>← <em>{r.verb}</em> </>}{r.other_name}</del>
            <span className="here-chip removed">removed here</span>
          </li>
        ))}
      </ul>
      {a.added_since.length > 0 && (
        <>
          <h3>Added since ({a.added_since.length})</h3>
          <ul className="asof-rels">{a.added_since.map((r, i) => (
            <li key={i}>{r.direction === "outgoing" ? <><em>{r.verb}</em> → </> : <>← <em>{r.verb}</em> </>}
              <a href={`#/metamodel/${model}/entity/${r.other_id}`}>{r.other_name}</a></li>))}</ul>
        </>
      )}
    </div>
  );
}

function HistoryTab({ model, m, e }) {
  const entityId = e.id;
  const { data, error } = useApi(`/api/v1/models/${model}/entities/${entityId}/history`);
  const [kind, setKind] = useState("");
  const [point, setPoint] = useState(null);
  const ec = useEntityChanges(model, m, entityId);   // my uncommitted changes, marked under "Current values"
  const f = (code) => ec.fields[String(code).toLowerCase()];
  const hl = (code) => (f(code) ? "pending-field" : "");
  if (!data) return <Loading error={error} />;
  const events = data.events.filter((ev) => !kind || ev.kind === kind);
  const list = moments(events);
  const index = point ? list.findIndex((g) => g.id === point) : -1;
  return (
    <div>
      <div className="toolbar">
        {KINDS.map(([k, l]) => <button key={k} className={`chip${kind === k ? " on" : ""}`} onClick={() => setKind(k)}>{l}</button>)}
        <CsvButton name={`${e.display_id} ${e.name} - history`} rows={() => [["When", "Who", "What", "Item", "Version", "Field", "Old", "New", "Commit", "Commit message"],
          ...events.flatMap((ev) => (ev.changes.length ? ev.changes : [{ field: "", old: "", new: "" }]).map((c) =>
            [ev.at, ev.by, `${ev.kind} ${verbOf(ev.operation)}`, ev.item, ev.version, c.field, c.old, c.new,
              ev.commit ? ev.commit.number : "", ev.commit ? ev.commit.message : ""]))]} />
        <span className="er-spacer" />
        <span className="quiet">{data.total} recorded changes at {list.length} moments</span>
      </div>
      <div className="history-split">
        <ol className="timeline">
          <li className={`moment now${point === null ? " on" : ""}`}>
            <button className="linkish" onClick={() => setPoint(null)}><strong>Now</strong> <span className="quiet">current values</span></button>
          </li>
          {list.map((g) => (
            <li key={g.key} className={`moment${point === g.id ? " on" : ""}`}>
              <button className="linkish" onClick={() => setPoint(g.id)} title="Show the entity as it was just after this">
                <span className="when">{fmtDateTime(g.at)}</span> <span className="who">{g.by}</span>
              </button>
              {(() => {
                const c = g.events.find((ev) => ev.commit)?.commit;   // the commit it came in with, and its message (D195)
                return c ? <div className="commit-note small">Commit #{c.number}{c.by && c.by !== g.by ? ` by ${c.by}` : ""}{c.message ? `: ${c.message}` : ""}
                  {(c.sources || []).map((x) => <span key={x} className="source-chip">{x}</span>)}</div> : null;
              })()}
              <ul>
                {g.events.slice(0, 4).map((ev) => (
                  <li key={ev.id}>
                    <span className={`kind ${ev.kind}`}>{ev.kind === "attribute" ? "value" : ev.kind}</span>{" "}
                    {ev.action === "created" ? <span><span className="act created">created</span> <strong>{ev.item}</strong></span>
                    : ev.changes.length ? ev.changes.slice(0, 1).map((c, i) => (
                      <span key={i}><span className={`act ${c.action}`}>{c.action}</span> <strong>{c.field}</strong>{" "}
                        {c.action === "changed" && <><del>{c.old}</del> → {c.new}</>}
                        {(c.action === "set" || c.action === "added") && c.new}
                        {(c.action === "cleared" || c.action === "removed") && <del>{c.old}</del>}</span>
                    )) : <span className="quiet">{verbOf(ev.operation)} {ev.item}</span>}
                    {ev.action !== "created" && ev.changes.length > 1 && <span className="quiet"> +{ev.changes.length - 1} more</span>}
                  </li>
                ))}
                {g.events.length > 4 && <li className="quiet">and {g.events.length - 4} more changes</li>}
              </ul>
            </li>
          ))}
          {!list.length && <li className="quiet">Nothing recorded.</li>}
        </ol>
        <div className="history-view">
          {point === null ? (
            <div>
              <div className="asof-head">
                <div><strong>Current values</strong><div className="quiet">Click a moment in the timeline to see the entity as it was then.</div></div>
              </div>
              <table className="grid-table attr-table">
                <tbody>
                  <tr><th>Name</th><td>{e.name}</td></tr>
                  <tr className={hl("description")}><th>Description</th><td className="pre">{e.description} <WasValue f={f("description")} /></td></tr>
                  <tr><th>Parent</th><td>{e.parent_name || <span className="quiet">-</span>}</td></tr>
                  <tr className={hl("status")}><th>Status</th><td>{e.status} <WasValue f={f("status")} /></td></tr>
                  {e.attributes.map((a) => <tr key={a.code}><th>{a.name}</th><td>{a.value == null ? <span className="quiet">not set</span> : a.data_type === "url" ? <LinkList value={a.value} /> : a.value}</td></tr>)}
                </tbody>
              </table>
            </div>
          ) : <AsOfPanel model={model} m={m} entityId={entityId} point={point} list={list} index={index} setPoint={setPoint} />}
        </div>
      </div>
      <p className="quiet">From the history table: every change to the entity, its values and its relationships is kept, with who made it
        and when. Click a moment, then Roll back to here: the old values are saved as a new version, so nothing is lost.</p>
    </div>
  );
}

const ENTITY_GRAPHS = [
  ["network", "Neighbourhood", "The entity in the middle, what surrounds it on rings, 1 to 3 steps out"],
  ["split", "Both ways", "What leads to it on the left (dependencies), what it leads to on the right (impact)"],
  ["impact", "One way", "Follow the lines out (impact) or in (dependencies) only, up to 6 steps"],
  ["tree", "Family tree", "Every parent up to the top and its parts below: where it sits in its hierarchy"],
  ["domains", "By domain", "Its neighbours in the bands of the ArchiMate domains, to read traceability up and down"],
  ["path", "Path to...", "The shortest chains connecting it to another entity you choose"],
  ["asof", "As it was", "Its relationships at a moment of its history: removed since in red, added since in green"],
];

function EntityGraphTab({ model, e }) {
  const [kind, setKind] = useState("network");
  return (
    <div>
      <div className="seg small" role="tablist">
        {ENTITY_GRAPHS.map(([k, l, help]) => (
          <button key={k} className={kind === k ? "on" : ""} title={help} onClick={() => setKind(k)}>{l}</button>
        ))}
      </div>
      <p className="quiet seg-help">{ENTITY_GRAPHS.find(([k]) => k === kind)[2]}.</p>
      <Suspense fallback={<p>Loading the graph...</p>}>
        <EntityGraph key={`${model}-${e.id}-${kind}`} model={model} focus={e.id} lockFocus kind={kind} focusColour={e.colour} />
      </Suspense>
    </div>
  );
}

function Lineage({ e }) {
  const m = e.model, l = e.lineage || {};
  const modelLink = (id, name, extra) => <a href={`#/metamodel/${id}`}>{name}{extra ? ` ${extra}` : ""}</a>;
  return (
    <div className="lineage">
      <span>Model {modelLink(m.id, m.name, m.version_label)} <span className="quiet">({m.kind_name}{m.is_locked ? ", read-only" : ""})</span></span>
      {m.source_model_id && <span>· model created from {modelLink(m.source_model_id, m.source_model_name)}</span>}
      {m.parent_model_id && <span>· merges into {modelLink(m.parent_model_id, m.parent_model_name)}</span>}
      {l.copied_from
        ? <span>· copied from <a href={`#/metamodel/${l.copied_from.model_id}/entity/${l.copied_from.id}`}>{l.copied_from.name}</a> in {modelLink(l.copied_from.model_id, l.copied_from.model_name, l.copied_from.model_version)}</span>
        : l.copied_from_guid ? <span className="quiet">· copied from an entity in a model you may not open</span>
          : <span className="quiet">· not copied from another model</span>}
      {l.type_from && <span>· type {e.entity_type} from <a href={`#/metamodel/${l.type_from.model_id}/type/${l.type_from.id}`}>{l.type_from.model_name}</a></span>}
      {l.copies?.length > 0 && (
        <span>· copies: {l.copies.map((c, i) => <span key={c.id}>{i > 0 && ", "}<a href={`#/metamodel/${c.model_id}/entity/${c.id}`}>{c.model_name}{c.model_version ? ` ${c.model_version}` : ""}</a></span>)}</span>
      )}
    </div>
  );
}

// Every rule applied to the entity and its relationships: passed, failed or not applicable (D113)
const RULE_STATUS = { failed: ["✗", "Failed"], passed: ["✓", "Passed"], not_applicable: ["–", "Not applicable"] };

function RulesTab({ model, e }) {
  const { data, error } = useApi(`/api/v1/models/${model}/entities/${e.id}/rules`);
  const [show, setShow] = useState("all");
  if (!data) return <Loading error={error} />;
  const s = data.summary;
  const keep = (x) => show === "all" || x.status === show;
  const rules = data.rules.filter(keep);
  const rels = data.relationships.filter(keep);
  const badge = (x) => (
    <span className={`rule-status ${x.status}${x.status === "failed" ? ` ${x.severity}` : ""}`} title={RULE_STATUS[x.status][1]}>
      {RULE_STATUS[x.status][0]} {x.status === "failed" ? (x.severity === "error" ? "Error" : "Warning") : RULE_STATUS[x.status][1]}
    </span>
  );
  return (
    <div>
      <div className="toolbar">
        {[["all", `All (${s.checks})`], ["failed", `Failed (${s.failed})`], ["passed", `Passed (${s.passed})`],
          ["not_applicable", `Not applicable (${s.not_applicable})`]].map(([k, l]) => (
          <button key={k} className={`chip${show === k ? " on" : ""}`} onClick={() => setShow(k)}>{l}</button>
        ))}
        <CsvButton name={`${e.display_id} ${e.name} - rules`} rows={() => [["Status", "Severity", "Field", "Rule", "Checks", "Value", "Message"],
          ...data.rules.map((r) => [r.status, r.severity, r.field, r.rule_name, r.checks, r.value, r.message]),
          ...data.relationships.map((r) => [r.status, r.severity, "Relationship", "Allowed by the metamodel",
            `${r.direction === "outgoing" ? "" : "← "}${r.verb} ${r.other_name} (${r.other_type})`, "", r.message])]} />
        <span className="er-spacer" />
        <span className={s.failed ? "status bad" : "status ok"}>
          {s.failed ? `${s.errors} error${s.errors === 1 ? "" : "s"}, ${s.warnings} warning${s.warnings === 1 ? "" : "s"}` : "Every rule passes"}
        </span>
      </div>
      <h3>Rules on values and relationships ({rules.length})</h3>
      {!rules.length ? <p className="quiet">None {show === "all" ? "apply to this entity type" : "here"}.</p> : (
        <table className="grid-table rules-table">
          <thead><tr><th>Result</th><th>Field</th><th>Rule</th><th>What it checks</th><th>Value</th><th>Why</th></tr></thead>
          <tbody>
            {rules.map((r, i) => (
              <tr key={i} className={`rule-row ${r.status}${r.status === "failed" ? ` ${r.severity}` : ""}`}>
                <td>{badge(r)}</td>
                <td><strong>{r.field}</strong></td>
                <td>{r.rule_name}</td>
                <td>{r.checks}</td>
                <td>{r.value ?? <span className="quiet">{r.rule === "has_relationship" ? "none found" : "not set"}</span>}</td>
                <td className={r.status === "failed" ? "" : "quiet"}>{r.message || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Each relationship against the metamodel ({rels.length})</h3>
      {!rels.length ? <p className="quiet">None{show === "all" ? ": this entity has no relationships" : " here"}.</p> : (
        <table className="grid-table rules-table">
          <thead><tr><th>Result</th><th>Relationship</th><th>Other entity</th><th>Why</th></tr></thead>
          <tbody>
            {rels.map((r) => (
              <tr key={r.id} className={`rule-row ${r.status}${r.status === "failed" ? ` ${r.severity}` : ""}`}>
                <td>{badge(r)}</td>
                <td>{r.direction === "outgoing" ? <>{e.name} <em>{r.verb}</em> →</> : <>← <em>{r.verb}</em></>}</td>
                <td><a href={`#/metamodel/${model}/entity/${r.other_id}`}>{r.other_name}</a> <span className="quiet">{r.other_display_id} · {r.other_type}</span></td>
                <td className={r.status === "failed" ? "" : "quiet"}>{r.message || "Allowed by the metamodel"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="quiet">The rules come from the metamodel (version {data.metamodel_version}): required attributes, pick lists and the
        type's validation rules, including the relationships an entity must have. Rules warn, they never block a save; the model's
        Failing checks tab lists every entity that fails one.</p>
    </div>
  );
}

export function EntityPage({ model, m, entityId, sub }) {
  const { data: e, error } = useApi(`/api/v1/models/${model}/entities/${entityId}`);
  const quality = useEntityQuality(m?.kind === "project" ? model : null, entityId);     // live (D246)
  if (!e) return <Loading error={error} />;
  const tab = sub || "details";
  const errors = e.warnings.filter((w) => w.severity === "error").length;
  const failing = e.warnings.length + e.relationships.filter((r) => !r.allowed).length;
  const tabs = [["details", "Details"], ["relations", `Relations (${e.relationships.length})`],
    ["rules", failing ? `Rules (${failing} failing)` : "Rules ✓"], ["history", "History"], ["graph", "Graph"], ["tree", "Tree"]];
  return (
    <div>
      <p className="quiet crumbs">
        <a href={`#/metamodel/${model}/types`}>Entity types</a> / <a href={`#/metamodel/${model}/types/${e.entity_type_id}`}>{e.entity_type}</a> / {e.display_id}
      </p>
      {e.merged_from && <p className="status ok small">{e.merged_from} was merged into {e.name} as a duplicate: links to it open this one.</p>}
      <div className="entity-card">
        <div className="entity-card-head">
          <div className="entity-head">
            <h2><Swatch colour={e.colour} /> {e.name} <PendingMark kind={e.pending} model={model} /></h2>
            <span className="quiet">{e.display_id} · {e.entity_type} · {e.domain} domain · {e.status} · metamodel v{e.created_mm_version}{e.modified_mm_version !== e.created_mm_version ? `, changed in v${e.modified_mm_version}` : ""}</span>
            <Checks errors={errors} warnings={e.warnings.length - errors} messages={e.warnings.map((w) => w.message)} />
            {quality.data && <div className="q-entity-head"><QualityBadge q={quality.data} /> <a className="small" href={`#/metamodel/${model}/quality`}>Quality tab</a>
              <EntityReasons q={quality.data} /></div>}
          </div>
          {e.description && <p className="entity-desc">{e.description}</p>}
          <EntityIcon model={model} m={m} e={e} />
          <Lineage e={e} />
          <div className="tabs sub" role="tablist">
            {tabs.map(([k, l]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "tab on" : "tab"}
                onClick={() => go(`/metamodel/${model}/entity/${entityId}${k === "details" ? "" : `/${k}`}`)}>{l}</button>
            ))}
          </div>
        </div>
        <div className="entity-card-body" role="tabpanel">
          {/* keyed by entity, so moving to another entity starts each tab afresh */}
          {tab === "details" && <DetailsTab key={e.id} model={model} m={m} e={e} q={quality.data} />}
          {tab === "relations" && <RelationsTab key={e.id} model={model} m={m} e={e} />}
          {tab === "rules" && <RulesTab key={e.id} model={model} e={e} />}
          {tab === "history" && <HistoryTab key={e.id} model={model} m={m} e={e} />}
          {tab === "graph" && <EntityGraphTab key={e.id} model={model} e={e} />}
          {tab === "tree" && <EntityTree key={e.id} model={model} m={m} entityId={e.id} />}
        </div>
      </div>
    </div>
  );
}


function MappingButton({ model, m, relTypes }) {
  const { data: mm } = useApi(`/api/v1/models/${model}/metamodel`);
  const types = mm ? mm.domains.flatMap((l) => elementTypes(l)).filter((t) => t.status !== "retired") : [];
  return <EditButton model={model} m={m} label="+ Mapping" spec={() => mappingSpec(types, relTypes)} />;
}
