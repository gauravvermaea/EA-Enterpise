// The model screens (phase 2): built for models with many entity types and thousands of entities.
//   #/metamodel/<m>/types                     Entity types: every type with its counts
//   #/metamodel/<m>/types/<typeId>            the entities of one type as a table (+ shows each one's relations)
//   #/metamodel/<m>/rels                      Relationship types: every type, how often used
//   #/metamodel/<m>/rels/<relTypeId>          the relationships of one type
//   #/metamodel/<m>/graph[/<kind>]            pictures: network, layered, impact chain, hierarchy map, matrix
//   #/metamodel/<m>/entity/<id>[/relations|/history|/graph]   one entity
// Every list has a CSV button; every picture saves as .drawio (and SVG, PNG, CSV).
// Changing things arrives later: values and relationships in build phase 6; entity types,
// relationship types, mappings (allowed relationships) and rules in build phase 3. Those buttons
// are shown now, switched off, so the screens do not change shape when they arrive.
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { downloadCsv } from "./exporting";

const EntityGraph = lazy(() => import("./EntityGraph"));
const HierarchyMap = lazy(() => import("./HierarchyMap"));
const RelationMatrix = lazy(() => import("./RelationMatrix"));
const go = (path) => { window.location.hash = path; };
const PAGE = 100;

// ---------------------------------------------------------------- helpers
const cache = new Map();   // GET results kept for a minute, so moving between tabs is quick

export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    if (!path) { setState({ data: null, error: null }); return undefined; }
    const hit = cache.get(path);
    if (hit && Date.now() - hit.at < 60000) { setState({ data: hit.data, error: null }); return undefined; }
    let live = true;
    setState({ data: null, error: null });
    apiFetch(path)
      .then((data) => { cache.set(path, { data, at: Date.now() }); if (live) setState({ data, error: null }); })
      .catch((e) => live && setState({ data: null, error: e.message }));
    return () => { live = false; };
  }, [path]);
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
  const [filter, setFilter] = useState("");
  const [layer, setLayer] = useState("");
  const [withEntities, setWithEntities] = useState(true);
  const { head, apply } = useSort("layer_order");
  const types = useMemo(() => (mm ? mm.layers.flatMap((l, i) => l.entity_types.map((t) => ({
    ...t, layer: l.name, layer_id: l.id, colour: l.colour, layer_order: i * 1000 + l.entity_types.indexOf(t),
  }))) : []), [mm]);
  if (!mm) return <Loading error={error} />;
  const anyContent = types.some((t) => t.entity_count > 0);
  const f = filter.trim().toLowerCase();
  const shown = apply(types.filter((t) => (!f || `${t.name} ${t.code} ${t.description}`.toLowerCase().includes(f))
    && (!layer || t.layer_id === layer) && (!withEntities || !anyContent || t.entity_count > 0)),
  (r, k) => r[k]);
  return (
    <div>
      <div className="toolbar">
        <input className="search" style={{ maxWidth: 260 }} placeholder="Filter entity types" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <select value={layer} onChange={(e) => setLayer(e.target.value)}>
          <option value="">All layers</option>
          {mm.layers.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        {anyContent && <label><input type="checkbox" checked={withEntities} onChange={(e) => setWithEntities(e.target.checked)} /> Only types with entities</label>}
        <CsvButton name={`${m.name} - entity types`} rows={() => [["Entity type", "Layer", "Entities", "Attributes", "Code", "Description"],
          ...shown.map((t) => [t.name, t.layer, t.entity_count, t.attribute_count, t.code, t.description])]} />
        <span className="er-spacer" />
        <Later label="+ Entity type" phase={3} model={m} what="Adding an entity type" />
        <Later label="+ Entity" phase={6} model={m} what="Adding an entity" />
      </div>
      <div className="scroll">
        <table className="grid-table click-rows">
          <thead><tr>{head("name", "Entity type")}{head("layer_order", "Layer")}{head("entity_count", "Entities", { className: "num" })}
            {head("attribute_count", "Attributes", { className: "num" })}{head("code", "Code")}<th>Description</th></tr></thead>
          <tbody>
            {shown.map((t) => (
              <tr key={t.id} onClick={() => go(`/metamodel/${model}/types/${t.id}`)}>
                <td><Swatch colour={t.colour} /> <a href={`#/metamodel/${model}/types/${t.id}`}><strong>{t.name}</strong></a></td>
                <td>{t.layer}</td>
                <td className="num">{t.entity_count}</td>
                <td className="num">{t.attribute_count}</td>
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
  const { head, apply } = useSort("display_id");
  useEffect(() => { setPage(0); }, [filter, check, typeId]);
  if (!t) return <Loading error={error} />;
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
  const colSpan = 7 + cols.length;

  function exportCsv() {
    const header = ["Display ID", "Name", "Description", "Parent", "Status", ...t.columns.map((c) => c.name), "Relationships", "Errors", "Warnings", "Messages"];
    const body = rows.map((r) => [r.display_id, r.name, r.description, r.parent_name, r.status,
      ...t.columns.map((c) => r.values[c.code]), r.relationship_count, r.errors, r.warnings, r.messages.join("; ")]);
    downloadCsv([header, ...body], `${m.name} - ${et.name}`);
  }

  return (
    <div>
      <p className="quiet crumbs">
        <a href={`#/metamodel/${model}/types`}>Entity types</a> / <Swatch colour={et.colour} /> <strong>{et.name}</strong>
        <span> · {et.layer} layer · <a href={`#/metamodel/${model}/type/${et.id}`}>definition and rules</a>
          {" · "}<a href={`#/metamodel/${model}/diagram/${et.id}`}>in the ER diagram</a></span>
      </p>
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
        <span className="er-spacer" />
        <Pager page={page} total={rows.length} setPage={setPage} />
        <Later label="+ Entity" phase={6} model={m} what={`Adding a ${et.name}`} />
      </div>
      <div className="scroll table-frame">
        <table className="grid-table entity-table">
          <thead>
            <tr>
              <th className="stick0" title="Show the relationships" />
              {head("display_id", "ID", { className: "stick1" })}
              {head("name", "Name", { className: "stick2" })}
              {head("checks", "Rules")}
              {head("parent_name", "Parent")}
              {cols.map((c) => head(`v:${c.code}`, <>{c.name}{c.is_required && <span className="req" title="Required">*</span>}</>, { key: c.code }))}
              {head("relationship_count", "Rel.", { className: "num" })}
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
                <td className="stick2"><a href={`#/metamodel/${model}/entity/${r.id}`}>{r.name}</a></td>
                <td><Checks {...r} /></td>
                <td>{r.parent_id ? <a href={`#/metamodel/${model}/entity/${r.parent_id}`}>{r.parent_name}</a> : ""}</td>
                {cols.map((c) => {
                  const v = r.values[c.code];
                  return <td key={c.code} className={c.is_required && (v === undefined || v === "") ? "missing" : ""}>
                    {v ?? ""}{v !== undefined && c.unit ? ` ${c.unit}` : ""}</td>;
                })}
                <td className="num">{r.relationship_count}</td>
                <td className="quiet nowrap" title={`by ${r.modified_by}`}>{new Date(r.modified_at).toLocaleDateString()}</td>
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
        <Later label="+ Relationship type" phase={3} model={m} what="Adding a relationship type" />
        <Later label="+ Mapping" phase={3} model={m} what="Adding a mapping (which entity types a relationship type may connect)" />
        <Later label="+ Relationship" phase={6} model={m} what="Adding a relationship" />
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
              <td>{!r.allowed && <span className="sev warning" title="No mapping allows this pair of types">not in metamodel</span>}</td>
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
  ["layers", "Layered", "Entities in bands by ArchiMate layer, top to bottom: read traceability from strategy down to technology"],
  ["impact", "Impact chain", "From one entity, follow the lines one way: what it leads to (impact) or what leads to it (dependencies)"],
  ["hierarchy", "Hierarchy map", "Parents holding their parts as nested boxes (the capability map), coloured by an attribute as a heat map"],
  ["matrix", "Matrix", "One entity type against another, with the relationships between them in the cells"],
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
      <p className="quiet">A failed rule never stops a save. From build phase 6 the value is saved with an override flag and its details
        (the rule, who saved it, when, and why), and the warning shows here until it is fixed.</p>
    </div>
  );
}

function DetailsTab({ model, m, e }) {
  const sections = [];
  for (const a of e.attributes) {
    let s = sections.find((x) => x.name === (a.section || "Attributes"));
    if (!s) sections.push(s = { name: a.section || "Attributes", items: [] });
    s.items.push(a);
  }
  const fieldWarnings = (code) => e.warnings.filter((w) => w.code === code);
  const Status = ({ list }) => (list.length
    ? <span className={`sev ${list.some((w) => w.severity === "error") ? "error" : "warning"}`} title={list.map((w) => w.message).join("\n")}>
      {list.map((w) => w.message).join("; ")}</span>
    : <span className="ok-mark">✓</span>);
  return (
    <div>
      <WarningList warnings={e.warnings} />
      <div className="toolbar">
        <CsvButton name={`${e.display_id} ${e.name} - details`} rows={() => [["Section", "Field", "Value", "Type", "Required", "Check"],
          ["Basic", "Name", e.name, "Text", "yes", fieldWarnings("name").map((w) => w.message).join("; ")],
          ["Basic", "Display ID", e.display_id, "Generated", "", ""],
          ["Basic", "Description", e.description, "Text", "", ""],
          ["Basic", "Parent", e.parent_name, "Entity", "", ""],
          ["Basic", "Status", e.status, "Workflow", "", ""],
          ...e.attributes.map((a) => [a.section, a.name, a.value, a.data_type_name, a.is_required ? "yes" : "", a.warnings.map((w) => w.message).join("; ")])]} />
        <span className="er-spacer" />
        <Later label="Edit values" phase={6} model={m} what="Changing values" />
      </div>
      <table className="grid-table attr-table">
        <thead><tr><th>Field</th><th>Value</th><th>Type</th><th>Check</th></tr></thead>
        <tbody>
          <tr className="section-row"><td colSpan="4">Basic</td></tr>
          <tr><th>Name <span className="req">*</span></th><td>{e.name}</td><td className="quiet">Text</td><td><Status list={fieldWarnings("name")} /></td></tr>
          <tr><th>Display ID</th><td>{e.display_id}</td><td className="quiet">Generated</td><td /></tr>
          <tr><th>Description</th><td className="pre">{e.description}</td><td className="quiet">Text</td><td><Status list={fieldWarnings("description")} /></td></tr>
          <tr><th>Parent</th><td>{e.parent_id ? <a href={`#/metamodel/${model}/entity/${e.parent_id}`}>{e.parent_name}</a> : <span className="quiet">-</span>}</td><td className="quiet">Entity</td><td /></tr>
          <tr><th>Status</th><td>{e.status}</td><td className="quiet">Workflow</td><td /></tr>
          {sections.map((s) => [
            <tr key={`s-${s.name}`} className="section-row"><td colSpan="4">{s.name}</td></tr>,
            ...s.items.map((a) => {
              const empty = a.value === null || a.value === "";
              return (
                <tr key={a.code} className={a.warnings.length ? "has-warning" : ""}>
                  <th>{a.name}{a.is_required && <span className="req" title="Required">*</span>}</th>
                  <td>{empty ? <span className="quiet">not set</span>
                    : a.ref_id ? <a href={`#/metamodel/${model}/entity/${a.ref_id}`}>{a.value}</a>
                    : <>{a.value}{a.unit && ` ${a.unit}`}</>}</td>
                  <td className="quiet" title={a.pick_list_values.length ? `One of: ${a.pick_list_values.join(", ")}` : undefined}>
                    {a.data_type_name}</td>
                  <td><Status list={a.warnings} /></td>
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
      <p className="quiet">Created {new Date(e.created_at).toLocaleString()} by {e.created_by} · changed {new Date(e.modified_at).toLocaleString()} by {e.modified_by} · version {e.row_version}</p>
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
        <Later label="+ Relationship" phase={6} model={m}
          what="Adding a relationship (a type the metamodel allows, or a new one, which adds the relationship type and mapping to this model)" />
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
                  <td>{!r.allowed && <span className="sev warning" title="No mapping in the metamodel allows this">not in metamodel</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {showAllowed && (
        <>
          <h3>What the metamodel allows for {e.entity_type}</h3>
          <p className="quiet">From phase 6, + Relationship offers these first. A relationship outside them can still be added: that adds the
            relationship type (if new) and the mapping to this model's metamodel, and records who added it.</p>
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
  return out;
}

function AsOfPanel({ model, m, entityId, point, list, index, setPoint }) {
  const { data: a, error } = useApi(`/api/v1/models/${model}/entities/${entityId}/as-of?event=${point}`);
  if (!a) return <Loading error={error} />;
  const rows = [...a.fields.map((f) => ({ ...f, section: "Basic", name: f.field })), ...a.attributes];
  const changed = rows.filter((r) => r.changed).length;
  const removed = a.relationships.filter((r) => !r.still_there);
  return (
    <div>
      <div className="asof-head">
        <div>
          <strong>As it was on {new Date(a.as_of.at).toLocaleString()}</strong>
          <span className="quiet"> · after a change by {a.as_of.by} · change {a.as_of.position} of {a.as_of.of}</span>
          <div className="quiet">{changed ? `${changed} value${changed > 1 ? "s" : ""} differ from now (shaded)` : "Every value is the same as now"}
            {removed.length > 0 && ` · ${removed.length} relationship${removed.length > 1 ? "s" : ""} since removed`}
            {a.added_since.length > 0 && ` · ${a.added_since.length} added since`}</div>
        </div>
        <span className="er-spacer" />
        <button disabled={index >= list.length - 1} onClick={() => setPoint(list[index + 1].id)} title="The change before this one">◀ Earlier</button>
        <button disabled={index <= 0} onClick={() => setPoint(list[index - 1].id)} title="The change after this one">Later ▶</button>
        <button className="primary" onClick={() => setPoint(null)}>Current</button>
        <Later label="Roll back to this point" phase={6} model={m}
          what="Rolling the entity back to these values (a new version that copies them; the history is kept)" />
        <CsvButton name={`${a.entity.display_id} ${a.entity.name} - as of ${String(a.as_of.at).slice(0, 19).replace(/[T:]/g, "-")}`}
          rows={() => [["Section", "Field", "Then", "Now", "Changed"], ...rows.map((r) => [r.section, r.name, r.then, r.now, r.changed ? "yes" : ""]),
            ...a.relationships.map((r) => ["Relationship", `${r.direction === "outgoing" ? "" : "← "}${r.verb} ${r.other_name}`, "yes", r.still_there ? "yes" : "", r.still_there ? "" : "yes"]),
            ...a.added_since.map((r) => ["Relationship", `${r.direction === "outgoing" ? "" : "← "}${r.verb} ${r.other_name}`, "", "yes", "yes"])]} />
      </div>
      <table className="grid-table attr-table asof">
        <thead><tr><th>Field</th><th>Then</th><th>Now</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.name}-${i}`} className={r.changed ? "was-different" : ""}>
              <th>{r.name}</th>
              <td>{r.then ?? <span className="quiet">not set</span>}</td>
              <td className="quiet">{r.now ?? "not set"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Relationships then ({a.relationships.length})</h3>
      {!a.relationships.length && <p className="quiet">None.</p>}
      <ul className="asof-rels">
        {a.relationships.map((r, i) => (
          <li key={i} className={r.still_there ? "" : "gone"}>
            {r.direction === "outgoing" ? <>{a.entity.name} <em>{r.verb}</em> → </> : <>← <em>{r.verb}</em> </>}
            {r.other_id ? <a href={`#/metamodel/${model}/entity/${r.other_id}`}>{r.other_name}</a> : r.other_name}
            {!r.still_there && <span className="sev warning">removed since</span>}
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
  if (!data) return <Loading error={error} />;
  const events = data.events.filter((ev) => !kind || ev.kind === kind);
  const list = moments(events);
  const index = point ? list.findIndex((g) => g.id === point) : -1;
  return (
    <div>
      <div className="toolbar">
        {KINDS.map(([k, l]) => <button key={k} className={`chip${kind === k ? " on" : ""}`} onClick={() => setKind(k)}>{l}</button>)}
        <CsvButton name={`${e.display_id} ${e.name} - history`} rows={() => [["When", "Who", "What", "Item", "Version", "Field", "Old", "New"],
          ...events.flatMap((ev) => (ev.changes.length ? ev.changes : [{ field: "", old: "", new: "" }]).map((c) =>
            [ev.at, ev.by, `${ev.kind} ${verbOf(ev.operation)}`, ev.item, ev.version, c.field, c.old, c.new]))]} />
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
                <span className="when">{new Date(g.at).toLocaleString()}</span> <span className="who">{g.by}</span>
              </button>
              <ul>
                {g.events.slice(0, 4).map((ev) => (
                  <li key={ev.id}>
                    <span className={`kind ${ev.kind}`}>{ev.kind === "attribute" ? "value" : ev.kind}</span>{" "}
                    {ev.changes.length ? ev.changes.slice(0, 1).map((c, i) => (
                      <span key={i}><strong>{c.field}</strong>{" "}
                        {c.old !== null && c.old !== undefined && <><del>{c.old}</del> → </>}{c.new ?? <em className="quiet">removed</em>}</span>
                    )) : <span className="quiet">{verbOf(ev.operation)} {ev.item}</span>}
                    {ev.changes.length > 1 && <span className="quiet"> +{ev.changes.length - 1} more</span>}
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
                  <tr><th>Description</th><td className="pre">{e.description}</td></tr>
                  <tr><th>Parent</th><td>{e.parent_name || <span className="quiet">-</span>}</td></tr>
                  <tr><th>Status</th><td>{e.status}</td></tr>
                  {e.attributes.map((a) => <tr key={a.code}><th>{a.name}</th><td>{a.value ?? <span className="quiet">not set</span>}</td></tr>)}
                </tbody>
              </table>
            </div>
          ) : <AsOfPanel model={model} m={m} entityId={entityId} point={point} list={list} index={index} setPoint={setPoint} />}
        </div>
      </div>
      <p className="quiet">From the history table: every change to the entity, its values and its relationships is kept, with who made it
        and when. Rolling back arrives with editing (build phase 6): it will save the old values as a new version, so nothing is lost.</p>
    </div>
  );
}

const ENTITY_GRAPHS = [
  ["network", "Neighbourhood", "The entity in the middle, what surrounds it on rings, 1 to 3 steps out"],
  ["split", "Both ways", "What leads to it on the left (dependencies), what it leads to on the right (impact)"],
  ["impact", "One way", "Follow the lines out (impact) or in (dependencies) only, up to 6 steps"],
  ["tree", "Family tree", "Every parent up to the top and its parts below: where it sits in its hierarchy"],
  ["layers", "By layer", "Its neighbours in the bands of the ArchiMate layers, to read traceability up and down"],
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

export function EntityPage({ model, m, entityId, sub }) {
  const { data: e, error } = useApi(`/api/v1/models/${model}/entities/${entityId}`);
  if (!e) return <Loading error={error} />;
  const tab = sub || "details";
  const errors = e.warnings.filter((w) => w.severity === "error").length;
  const tabs = [["details", "Details"], ["relations", `Relations (${e.relationships.length})`], ["history", "History"], ["graph", "Graph"]];
  return (
    <div>
      <p className="quiet crumbs">
        <a href={`#/metamodel/${model}/types`}>Entity types</a> / <a href={`#/metamodel/${model}/types/${e.entity_type_id}`}>{e.entity_type}</a> / {e.display_id}
      </p>
      <div className="entity-card">
        <div className="entity-card-head">
          <div className="entity-head">
            <h2><Swatch colour={e.colour} /> {e.name}</h2>
            <span className="quiet">{e.display_id} · {e.entity_type} · {e.layer} layer · {e.status}</span>
            <Checks errors={errors} warnings={e.warnings.length - errors} messages={e.warnings.map((w) => w.message)} />
          </div>
          {e.description && <p className="entity-desc">{e.description}</p>}
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
          {tab === "details" && <DetailsTab key={e.id} model={model} m={m} e={e} />}
          {tab === "relations" && <RelationsTab key={e.id} model={model} m={m} e={e} />}
          {tab === "history" && <HistoryTab key={e.id} model={model} m={m} e={e} />}
          {tab === "graph" && <EntityGraphTab key={e.id} model={model} e={e} />}
        </div>
      </div>
    </div>
  );
}
