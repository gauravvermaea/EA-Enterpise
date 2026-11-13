// SQL window (D211; R2.57, owner 13 Nov 2026: "we need ours to be more like pgadmin"): a database workspace. On the left
// the tree of the chosen database (schemas, tables, views with rows and size) as the person's own database login may see
// it; on the right tabs: queries (several, with colouring, completion of table and column names on Ctrl+Space, history
// and saved queries, the query plan, CSV and Excel export) and tables (their rows a page at a time, sorted and filtered,
// and their structure: columns, indexes, constraints). Every run is rolled back unless "Keep the changes" is ticked (then
// committed); browsing, rows, plans and exports never change anything. Every run is in the audit trail. The login stays
// in this page only; history and saved queries in this browser only.
import { useEffect, useMemo, useRef, useState } from "react";
import { apiDownload, apiFetch, keycloak, signedIn } from "./auth";
import { config } from "./config";
import SchemaDiagram from "./SchemaDiagram";

const EXAMPLE = `-- Ctrl+Enter runs (the selection only, when there is one). Ctrl+Space completes a table or column name.
SELECT name, kind_code, is_locked FROM core.models ORDER BY name;`;
const KEYWORDS = new Set(("select from where and or not in is null as join left right inner outer full cross on group by order "
  + "having limit offset distinct union all insert into values update set delete create table view index drop alter add column "
  + "primary key foreign references with case when then else end exists between like ilike true false asc desc count sum avg "
  + "min max coalesce cast returning begin commit rollback explain analyze grant revoke schema default unique check constraint").split(" "));

// browser storage is a convenience only: it may be missing or throw (D-private window), never needed
function stored(key, fallback) { try { return JSON.parse(window.localStorage.getItem(key) || "null") ?? fallback; } catch { return fallback; } }
function store(key, value) { try { window.localStorage.setItem(key, JSON.stringify(value)); } catch { /* not kept */ } }

function fmtBytes(n) {
  if (n === null || n === undefined) return "";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i += 1; }
  return `${i ? v.toFixed(1) : v} ${u[i]}`;
}

// the text coloured: keywords, strings, numbers, comments (an overlay under a see-through text box)
function colour(text) {
  const out = [];
  const re = /(--[^\n]*)|('(?:[^']|'')*'?)|("(?:[^"]|"")*"?)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_$]*)|(\s+|.)/g;
  let m; let i = 0;
  while ((m = re.exec(text)) !== null) {
    const [tok, cm, str, quoted, num, word] = m;
    const cls = cm ? "sq-cm" : str ? "sq-str" : quoted ? "sq-id" : num ? "sq-num" : word && KEYWORDS.has(word.toLowerCase()) ? "sq-kw" : "";
    out.push(cls ? <span key={i} className={cls}>{tok}</span> : tok);
    i += 1;
  }
  return out;
}

function ResultTable({ r, n }) {
  if (!r.columns.length) {
    return <p className="quiet">Statement {n}: {r.status}{r.row_count !== null ? ` (${r.row_count} rows)` : ""}</p>;
  }
  return (
    <div className="sql-result">
      <p className="quiet">Result {n}: {r.row_count} row{r.row_count === 1 ? "" : "s"}{r.truncated ? " (first 1,000 shown; Export gives up to 100,000)" : ""}</p>
      <div className="scroll"><Grid columns={r.columns} rows={r.rows} /></div>
    </div>
  );
}

function Grid({ columns, rows, sort, onSort }) {
  return (
    <table className="grid-table">
      <thead><tr>{columns.map((c, i) => (
        <th key={i} onClick={onSort ? () => onSort(c) : undefined} className={onSort ? "sortable" : undefined}>
          {c}{sort && sort.order === c ? (sort.desc ? " ▼" : " ▲") : ""}</th>))}</tr></thead>
      <tbody>{rows.map((row, i) => (
        <tr key={i}>{row.map((v, j) => (
          <td key={j} className={v === null ? "quiet" : undefined} title={typeof v === "string" && v.length > 60 ? v : undefined}>
            {v === null ? "null" : typeof v === "object" ? JSON.stringify(v) : String(v)}</td>))}</tr>))}</tbody>
    </table>
  );
}

// a query plan as a tree: each step, the table it reads, its cost, rows planned (and with analyze: rows and time taken)
function PlanNode({ node, depth = 0 }) {
  const slow = node["Actual Total Time"] !== undefined && node["Actual Total Time"] > 100;
  return (
    <div className="plan-node" style={{ marginLeft: depth * 18 }}>
      <b className={slow ? "bad-text" : undefined}>{node["Node Type"]}</b>
      {node["Relation Name"] && <> on <code>{node.Schema ? `${node.Schema}.` : ""}{node["Relation Name"]}</code></>}
      {node["Index Name"] && <> using <code>{node["Index Name"]}</code></>}
      <span className="quiet small"> cost {node["Total Cost"]}, rows {node["Plan Rows"]}
        {node["Actual Rows"] !== undefined && <>, actual rows {node["Actual Rows"]} in {node["Actual Total Time"]} ms × {node["Actual Loops"]}</>}</span>
      {(node["Filter"] || node["Index Cond"] || node["Hash Cond"] || node["Join Filter"]) &&
        <div className="quiet small" style={{ marginLeft: 12 }}>{node["Index Cond"] || node["Hash Cond"] || node["Join Filter"] || node.Filter}</div>}
      {(node.Plans || []).map((p, i) => <PlanNode key={i} node={p} depth={depth + 1} />)}
    </div>
  );
}

function QueryTab({ tab, update, login, names, keep, setKeep }) {
  const box = useRef(null);
  const [busy, setBusy] = useState("");
  const [suggest, setSuggest] = useState(null);       // {word, start, items}
  const history = stored("eax.sql.history", []);
  const saved = stored("eax.sql.saved", []);
  const [, refresh] = useState(0);
  function picked() {
    const t = box.current;
    return t && t.selectionStart !== t.selectionEnd ? tab.sql.slice(t.selectionStart, t.selectionEnd) : tab.sql;
  }
  async function call(kind, extra = {}) {
    const sql = picked();
    if (kind === "run" && keep && !window.confirm(`Keep the changes? The statements are committed to ${login.database} as ${login.username}; ` // eslint-disable-line no-alert
      + "this cannot be undone here. The run is recorded in the audit trail.")) return;
    setBusy(kind); update({ error: null });
    try {
      if (kind === "run") {
        const out = await apiFetch("/api/v1/sql/query", { method: "POST", body: JSON.stringify({ ...login, sql, keep }) });
        update({ out, plan: null });
        store("eax.sql.history", [{ sql, at: new Date().toISOString(), db: login.database }, ...history.filter((h) => h.sql !== sql)].slice(0, 50));
      } else if (kind === "explain") {
        update({ plan: await apiFetch("/api/v1/sql/explain", { method: "POST", body: JSON.stringify({ ...login, sql, ...extra }) }), out: null });
      } else {
        await apiDownload("/api/v1/sql/export", `query.${extra.format}`, { ...login, sql, ...extra });
      }
    } catch (e) { update({ error: e.message }); }
    setBusy("");
  }
  function complete() {
    const t = box.current; const at = t.selectionStart;
    const m = /[A-Za-z_][A-Za-z0-9_.]*$/.exec(tab.sql.slice(0, at));
    const word = m ? m[0] : "";
    const items = names.filter((n) => n.toLowerCase().startsWith(word.toLowerCase().split(".").pop()) || n.toLowerCase().startsWith(word.toLowerCase())).slice(0, 12);
    setSuggest(items.length ? { word, start: at - word.length, items } : null);
  }
  function insert(name) {
    const s = suggest; const t = box.current;
    const text = tab.sql.slice(0, s.start) + name + tab.sql.slice(t.selectionStart);
    update({ sql: text }); setSuggest(null);
    setTimeout(() => { t.focus(); t.selectionStart = t.selectionEnd = s.start + name.length; }, 0);
  }
  function save() {
    const name = window.prompt("A name for this query", tab.title || "My query"); // eslint-disable-line no-alert
    if (!name) return;
    store("eax.sql.saved", [{ name, sql: tab.sql }, ...saved.filter((x) => x.name !== name)].slice(0, 100));
    update({ title: name }); refresh((n) => n + 1);
  }
  return (
    <div>
      <div className="sql-editor">
        <pre className="sql-colour" aria-hidden="true">{colour(tab.sql)}{"\n"}</pre>
        <textarea ref={box} className="sql-text" spellCheck="false" value={tab.sql} aria-label="SQL"
          onScroll={(e) => { const pre = e.target.previousSibling; pre.scrollTop = e.target.scrollTop; pre.scrollLeft = e.target.scrollLeft; }}
          onChange={(e) => { update({ sql: e.target.value }); setSuggest(null); }}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); call("run"); }
            else if (e.ctrlKey && e.key === " ") { e.preventDefault(); complete(); }
            else if (e.key === "Escape") setSuggest(null);
          }} />
        {suggest && <ul className="sql-suggest" role="listbox" aria-label="Names">
          {suggest.items.map((n) => <li key={n} role="option" aria-selected="false"><button onClick={() => insert(n)}>{n}</button></li>)}</ul>}
      </div>
      <div className="row-gap">
        <button className="primary" disabled={!!busy} onClick={() => call("run")}>{busy === "run" ? "Running..." : "Run"}</button>
        <button disabled={!!busy} onClick={() => call("explain", { analyze: false })} title="The plan PostgreSQL would follow">Explain</button>
        <button disabled={!!busy} onClick={() => call("explain", { analyze: true })} title="Runs it (rolled back) and shows the real rows and times">Explain analyse</button>
        <button disabled={!!busy} onClick={() => call("export", { format: "csv" })}>Export CSV</button>
        <button disabled={!!busy} onClick={() => call("export", { format: "xlsx" })}>Export Excel</button>
        <button onClick={save}>Save query</button>
        <label className={`sql-keep${keep ? " on" : ""}`}>
          <input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} /> Keep the changes (commit)
        </label>
      </div>
      <div className="row-gap small">
        <select aria-label="History" value="" onChange={(e) => e.target.value && update({ sql: history[Number(e.target.value)].sql })}>
          <option value="">History ({history.length})</option>
          {history.map((h, i) => <option key={i} value={i}>{h.sql.replace(/\s+/g, " ").slice(0, 80)}</option>)}
        </select>
        <select aria-label="Saved queries" value="" onChange={(e) => { const s = saved[Number(e.target.value)]; if (s) update({ sql: s.sql, title: s.name }); }}>
          <option value="">Saved queries ({saved.length})</option>
          {saved.map((s, i) => <option key={i} value={i}>{s.name}</option>)}
        </select>
        <span className="quiet">History and saved queries are kept in this browser only.</span>
      </div>
      {tab.error && <p className="status bad sql-error">{tab.error}</p>}
      {tab.plan && <div className="sql-plan"><p className="quiet">{tab.plan.analyzed ? "Ran and rolled back: real rows and times." : "The plan, not run."}
        {tab.plan.plan["Execution Time"] !== undefined && <> Took {tab.plan.plan["Execution Time"]} ms.</>}</p><PlanNode node={tab.plan.plan.Plan} /></div>}
      {tab.out && (
        <>
          <p className="quiet">Done in {tab.out.duration_ms} ms{tab.out.committed ? <b className="warn-text"> · committed: the changes are kept</b> : " · rolled back, nothing saved"}</p>
          {tab.out.notices.map((m, i) => <p key={i} className="quiet">{m}</p>)}
          {tab.out.results.map((r, i) => <ResultTable key={i} r={r} n={i + 1} />)}
        </>
      )}
    </div>
  );
}

function TableTab({ tab, login }) {
  const [view, setView] = useState("rows");
  const [rows, setRows] = useState(null);
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState({ page: 0, order: "", desc: false, column: "", contains: "" });
  const [typed, setTyped] = useState("");
  useEffect(() => {
    setErr("");
    apiFetch("/api/v1/sql/describe", { method: "POST", body: JSON.stringify({ ...login, schema: tab.schema, table: tab.table }) })
      .then(setInfo).catch((e) => setErr(e.message));
  }, [tab.schema, tab.table]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (view !== "rows") return;
    apiFetch("/api/v1/sql/rows", { method: "POST", body: JSON.stringify({ ...login, schema: tab.schema, table: tab.table, ...q }) })
      .then(setRows).catch((e) => setErr(e.message));
  }, [view, q, tab.schema, tab.table]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div>
      <p className="small"><b>{tab.schema}.{tab.table}</b>{info && <span className="quiet"> · about {info.rows_estimate} rows · {fmtBytes(info.bytes)}{info.comment ? ` · ${info.comment}` : ""}</span>}</p>
      <div className="tabs small-tabs" role="tablist">
        {[["rows", "Rows"], ["structure", "Structure"]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={view === k} className={view === k ? "tab on" : "tab"} onClick={() => setView(k)}>{l}</button>))}
      </div>
      {err && <p className="status bad">{err}</p>}
      {view === "rows" && rows && (
        <>
          <div className="row-gap filters">
            <select aria-label="Filter column" value={q.column} onChange={(e) => setQ({ ...q, column: e.target.value, page: 0 })}>
              <option value="">Filter a column…</option>{rows.columns.map((c) => <option key={c}>{c}</option>)}
            </select>
            <input type="search" placeholder="contains" value={typed} onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") setQ({ ...q, contains: typed, page: 0 }); }} aria-label="Contains" />
            <span className="quiet small">{rows.total} row(s) · page {rows.page + 1} of {rows.pages}</span>
            <button className="small" disabled={rows.page === 0} onClick={() => setQ({ ...q, page: q.page - 1 })}>‹ Earlier</button>
            <button className="small" disabled={rows.page >= rows.pages - 1} onClick={() => setQ({ ...q, page: q.page + 1 })}>Later ›</button>
          </div>
          <div className="sql-result"><div className="scroll"><Grid columns={rows.columns} rows={rows.rows} sort={q}
            onSort={(c) => setQ({ ...q, order: c, desc: q.order === c ? !q.desc : false, page: 0 })} /></div></div>
          <p className="quiet small">Read only here: change rows with a query and Keep the changes, or better in the screens, which keep their history.</p>
        </>)}
      {view === "structure" && info && (
        <>
          <h4>Columns</h4>
          <table className="grid-table"><thead><tr><th>Column</th><th>Type</th><th>Null</th><th>Default</th><th>About</th></tr></thead>
            <tbody>{info.columns.map((c) => <tr key={c.name}><td><code>{c.name}</code></td><td>{c.type}</td><td>{c.nullable ? "yes" : "no"}</td>
              <td className="small">{c.default}</td><td className="small">{c.comment}</td></tr>)}</tbody></table>
          <h4>Indexes</h4>
          <table className="grid-table"><tbody>{info.indexes.map((i) => <tr key={i.name}><td><code>{i.name}</code>{i.primary ? " (primary)" : i.unique ? " (unique)" : ""}</td>
            <td className="small"><code>{i.definition}</code></td><td className="small">{fmtBytes(i.bytes)}</td></tr>)}</tbody></table>
          <h4>Constraints</h4>
          <table className="grid-table"><tbody>{info.constraints.map((c) => <tr key={c.name}><td><code>{c.name}</code></td><td>{c.kind}</td>
            <td className="small"><code>{c.definition}</code></td></tr>)}</tbody></table>
          {info.view_definition && <><h4>View definition</h4><pre className="ct-log">{info.view_definition}</pre></>}
        </>)}
    </div>
  );
}

function Tree({ tree, open, onOpen, onInsert }) {
  const [shut, setShut] = useState({});
  const [find, setFind] = useState("");
  if (!tree) return <p className="quiet small">Give the login and press Connect to see the database.</p>;
  return (
    <div className="sql-tree">
      <input type="search" placeholder="Find a table" value={find} onChange={(e) => setFind(e.target.value)} aria-label="Find a table" />
      {tree.schemas.map((s) => {
        const objs = s.objects.filter((o) => !find || o.name.toLowerCase().includes(find.toLowerCase()));
        if (find && !objs.length) return null;
        const isShut = shut[s.name] ?? !find;
        return (
          <div key={s.name}>
            <button className="tree-schema" title={s.about || ""} onClick={() => setShut({ ...shut, [s.name]: !isShut })}>{isShut ? "▸" : "▾"} {s.name} <span className="quiet">({s.objects.length})</span></button>
            {s.about && <div className="tree-about quiet small">{s.about}</div>}
            {!isShut && <ul>{objs.map((o) => (
              <li key={o.name}>
                <button className={open === `${s.name}.${o.name}` ? "tree-obj on" : "tree-obj"} title={`${o.about ? `${o.about}. ` : ""}${o.kind}, about ${o.rows} rows, ${fmtBytes(o.bytes)}. Double-click puts the name in the query.`}
                  onClick={() => onOpen(s.name, o.name)} onDoubleClick={() => onInsert(`${s.name}.${o.name}`)}>
                  {o.kind === "table" ? "▦" : "◇"} {o.name}</button>
                {o.about && <div className="tree-about quiet small">{o.about}</div>}
              </li>))}</ul>}
          </div>);
      })}
    </div>
  );
}

export default function Sql() {
  const [login, setLogin] = useState({ database: "eaexplorer", username: "eax_app", password: "" });
  const [dbAbout, setDbAbout] = useState({});    // what each database is for (owner, 13 Nov 2026)
  const [dbs, setDbs] = useState([]);
  const [tree, setTree] = useState(null);
  const [treeErr, setTreeErr] = useState("");
  const [keep, setKeep] = useState(false);
  const [tabs, setTabs] = useState([{ id: 1, kind: "query", title: "Query 1", sql: EXAMPLE }]);
  const [on, setOn] = useState(1);
  const [cols, setCols] = useState({});                 // table -> its columns, for completion
  useEffect(() => {
    if (!signedIn()) return;
    apiFetch("/api/v1/sql/databases").then((d) => {
      setDbs(d.databases || []);
      setDbAbout(d.about || {});
      if (d.databases?.length && !d.databases.includes(login.database)) setLogin((l) => ({ ...l, database: d.databases[0] }));
    }).catch(() => setDbs([]));
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const names = useMemo(() => {
    const out = new Set();
    for (const s of tree?.schemas || []) { out.add(s.name); for (const o of s.objects) { out.add(o.name); out.add(`${s.name}.${o.name}`); } }
    for (const cs of Object.values(cols)) for (const c of cs) out.add(c);
    return [...out].sort();
  }, [tree, cols]);

  if (!signedIn()) {
    return (
      <section>
        <h1>SQL</h1>
        <p>Sign in first (system administrators only).</p>
        <button className="primary" onClick={() => keycloak.login()}>Sign in</button>
      </section>
    );
  }
  async function connect() {
    setTreeErr("");
    try { setTree(await apiFetch("/api/v1/sql/browse", { method: "POST", body: JSON.stringify(login) })); }
    catch (e) { setTree(null); setTreeErr(e.message); }
  }
  function update(id, patch) { setTabs((ts) => ts.map((t) => (t.id === id ? { ...t, ...patch } : t))); }
  function newQuery(sql = "") {
    const id = Math.max(0, ...tabs.map((t) => t.id)) + 1;
    setTabs([...tabs, { id, kind: "query", title: `Query ${id}`, sql }]); setOn(id);
  }
  function openTable(schema, table) {
    const key = `${schema}.${table}`;
    const have = tabs.find((t) => t.kind === "table" && t.key === key);
    if (have) { setOn(have.id); return; }
    const id = Math.max(0, ...tabs.map((t) => t.id)) + 1;
    setTabs([...tabs, { id, kind: "table", key, title: key, schema, table }]); setOn(id);
    apiFetch("/api/v1/sql/describe", { method: "POST", body: JSON.stringify({ ...login, schema, table }) })
      .then((d) => setCols((c) => ({ ...c, [key]: d.columns.map((x) => x.name) }))).catch(() => {});
  }
  function insertName(name) {
    const t = tabs.find((x) => x.id === on);
    if (t && t.kind === "query") update(on, { sql: `${t.sql}${t.sql.endsWith(" ") || !t.sql ? "" : " "}${name}` });
    else newQuery(`SELECT * FROM ${name} LIMIT 100;`);
  }
  function close(id) {
    const rest = tabs.filter((t) => t.id !== id);
    setTabs(rest.length ? rest : [{ id: id + 1, kind: "query", title: "Query 1", sql: "" }]);
    if (on === id) setOn((rest[rest.length - 1] || { id: id + 1 }).id);
  }
  const field = (key, label, type = "text") => (
    <label>{label}
      <input type={type} value={login[key]} autoComplete="off" onChange={(e) => setLogin({ ...login, [key]: e.target.value })} />
    </label>
  );
  const tab = tabs.find((t) => t.id === on) || tabs[0];
  return (
    <section className="sql">
      <h1>SQL</h1>
      <p className="quiet">
        Works on this installation's PostgreSQL with a database login
        {config.deployment === "laptop" && <> (laptop: user <code>eax_app</code> or <code>postgres</code>, password <code>P^55w0rd1234&amp;</code>)</>}:
        what that login may see and do decides the rest. A run is rolled back unless you tick <b>Keep the changes</b>; browsing,
        a table's rows, plans and exports never change anything. Every run is in the audit trail.
      </p>
      <div className="sql-login">
        {dbs.length ? (
          <label>Database
            <select value={login.database} onChange={(e) => { setLogin({ ...login, database: e.target.value }); setTree(null); }}>
              {dbs.map((d) => <option key={d} value={d} title={dbAbout[d] || ""}>{d}{dbAbout[d] ? ` · ${dbAbout[d]}` : ""}</option>)}
            </select>
          </label>
        ) : field("database", "Database")}
        {field("username", "User")}
        {field("password", "Password", "password")}
        <button onClick={connect} disabled={!login.password}>Connect</button>
      </div>
      {(dbAbout[login.database] || tree?.about) && <p className="quiet small sql-db-about">{login.database}: {dbAbout[login.database] || tree?.about}</p>}
      {treeErr && <p className="status bad">{treeErr}</p>}
      <div className="sql-workspace">
        <aside className="sql-side"><Tree tree={tree} open={tab.kind === "table" ? tab.key : ""} onOpen={openTable} onInsert={insertName} /></aside>
        <div className="sql-main">
          <div className="tabs small-tabs sql-tabs" role="tablist">
            {tabs.map((t) => (
              <span key={t.id} className={t.id === on ? "tab on" : "tab"}>
                <button role="tab" aria-selected={t.id === on} onClick={() => setOn(t.id)}>{t.kind === "table" ? "▦ " : ""}{t.title}</button>
                <button className="tab-close" aria-label={`Close ${t.title}`} onClick={() => close(t.id)}>×</button>
              </span>))}
            <button className="tab" onClick={() => newQuery()} aria-label="New query">+ Query</button>
          </div>
          {tab.kind === "query"
            ? <QueryTab key={tab.id} tab={tab} update={(p) => update(tab.id, p)} login={login} names={names} keep={keep} setKeep={setKeep} />
            : <TableTab key={tab.id} tab={tab} login={login} />}
        </div>
      </div>
      <details className="sql-tables">
        <summary>Database diagram: the tables behind models and behind projects, and how they join</summary>
        <SchemaDiagram />
        <p className="quiet">For one table per entity type of a model use <code>eax.get_entity('Capability', 'caps')</code>.</p>
      </details>
    </section>
  );
}
