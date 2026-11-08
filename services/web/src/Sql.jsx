// SQL window: write a query, run it, see the results. Uses POST /api/v1/sql/query with a
// PostgreSQL login. A run is rolled back at the end unless "Keep the changes" is ticked (D211, replacing the read-only
// rule of D52): then it is committed and the run is in the audit trail. The database is chosen from the server's
// databases. The login stays in this page only.
import { useEffect, useState } from "react";
import { apiFetch, keycloak, signedIn } from "./auth";
import { config } from "./config";
import SchemaDiagram from "./SchemaDiagram";

const EXAMPLE = `-- Ctrl+Enter runs. Several statements in one run are fine.
SELECT name, kind_code, is_locked FROM core.models ORDER BY name;`;

function ResultTable({ r, n }) {
  if (!r.columns.length) {
    return <p className="quiet">Statement {n}: {r.status}{r.row_count !== null ? ` (${r.row_count} rows)` : ""}</p>;
  }
  return (
    <div className="sql-result">
      <p className="quiet">Result {n}: {r.row_count} row{r.row_count === 1 ? "" : "s"}{r.truncated ? " (first 1,000 shown)" : ""}</p>
      <div className="scroll">
        <table className="grid-table">
          <thead><tr>{r.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
          <tbody>
            {r.rows.map((row, i) => (
              <tr key={i}>{row.map((v, j) => (
                <td key={j} className={v === null ? "quiet" : undefined}>
                  {v === null ? "null" : typeof v === "object" ? JSON.stringify(v) : String(v)}
                </td>
              ))}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Sql() {
  const [login, setLogin] = useState({ database: "eaexplorer", username: "eax_app", password: "" });
  const [sql, setSql] = useState(EXAMPLE);
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState(null);
  const [error, setError] = useState(null);
  const [keep, setKeep] = useState(false);
  const [dbs, setDbs] = useState([]);
  useEffect(() => {
    if (!signedIn()) return;
    apiFetch("/api/v1/sql/databases").then((d) => {
      setDbs(d.databases || []);
      if (d.databases?.length && !d.databases.includes(login.database)) setLogin((l) => ({ ...l, database: d.databases[0] }));
    }).catch(() => setDbs([]));
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!signedIn()) {
    return (
      <section>
        <h1>SQL</h1>
        <p>Sign in first (system administrators only).</p>
        <button className="primary" onClick={() => keycloak.login()}>Sign in</button>
      </section>
    );
  }

  async function run(text) {
    // eslint-disable-next-line no-alert
    if (keep && !window.confirm(`Keep the changes? The statements are committed to ${login.database} as ${login.username}; `
      + "this cannot be undone here. The run is recorded in the audit trail.")) return;
    setBusy(true); setError(null); setOut(null);
    try {
      setOut(await apiFetch("/api/v1/sql/query", {
        method: "POST",
        body: JSON.stringify({ ...login, sql: text, keep }),
      }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function runFromBox(textarea) {
    const { selectionStart: a, selectionEnd: b, value } = textarea;
    run(a !== b ? value.slice(a, b) : value);  // the selected part, or everything
  }

  const field = (key, label, type = "text") => (
    <label>{label}
      <input type={type} value={login[key]} autoComplete="off"
        onChange={(e) => setLogin({ ...login, [key]: e.target.value })} />
    </label>
  );

  return (
    <section className="sql">
      <h1>SQL</h1>
      <p className="quiet">
        Runs on this installation's PostgreSQL with a database login
        {config.deployment === "laptop" && <> (laptop: user <code>eax_app</code> or <code>postgres</code>, password <code>P^55w0rd1234&amp;</code>)</>}.
        A run is rolled back at the end, so nothing is saved, unless you tick <b>Keep the changes</b>: then it is committed
        (what the login is allowed to change) and recorded in the audit trail. Changes to models are better made in the
        screens or the API, which keep their history.
        Temporary tables (<code>eax.get_entity('Capability', 'caps')</code>) last for one run.
      </p>
      <div className="sql-login">
        {dbs.length ? (
          <label>Database
            <select value={login.database} onChange={(e) => setLogin({ ...login, database: e.target.value })}>
              {dbs.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </label>
        ) : field("database", "Database")}
        {field("username", "User")}
        {field("password", "Password", "password")}
      </div>
      <details className="sql-tables" open>
        <summary>Database diagram: the tables behind models and behind projects, and how they join</summary>
        <SchemaDiagram />
        <p className="quiet">
          For one table per entity type of a model use <code>eax.get_entity('Capability', 'caps')</code>.
        </p>
      </details>
      <textarea id="sql-text" className="sql-text" spellCheck="false" value={sql}
        onChange={(e) => setSql(e.target.value)}
        onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); runFromBox(e.target); } }} />
      <div>
        <button className="primary" disabled={busy} onClick={() => runFromBox(document.getElementById("sql-text"))}>
          {busy ? "Running..." : "Run"}
        </button>
        <label className={`sql-keep${keep ? " on" : ""}`}>
          <input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} /> Keep the changes (commit)
        </label>
        <span className="quiet"> Ctrl+Enter. With text selected, only the selection runs.</span>
      </div>

      {error && <p className="status bad sql-error">{error}</p>}
      {out && (
        <>
          <p className="quiet">
            Done in {out.duration_ms} ms{out.committed ? <b className="warn-text"> · committed: the changes are kept</b> : " · rolled back, nothing saved"}
          </p>
          {out.notices.map((m, i) => <p key={i} className="quiet">{m}</p>)}
          {out.results.map((r, i) => <ResultTable key={i} r={r} n={i + 1} />)}
        </>
      )}
    </section>
  );
}
