// SQL window: write a query, run it, see the results. Uses POST /api/v1/sql/query with a
// PostgreSQL login. Rolled back at the end unless "Allow changes" is ticked. The login stays in this page only.
import { useState } from "react";
import { apiFetch, keycloak } from "./auth";
import { config } from "./config";

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
  const [allowChanges, setAllowChanges] = useState(false);
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState(null);
  const [error, setError] = useState(null);

  if (!keycloak.authenticated) {
    return (
      <section>
        <h1>SQL</h1>
        <p>Sign in first (system administrators only).</p>
        <button className="primary" onClick={() => keycloak.login()}>Sign in</button>
      </section>
    );
  }

  async function run(text) {
    setBusy(true); setError(null); setOut(null);
    try {
      setOut(await apiFetch("/api/v1/sql/query", {
        method: "POST",
        body: JSON.stringify({ ...login, sql: text, allow_changes: allowChanges }),
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
        Nothing is saved unless you tick <em>Allow changes</em>: otherwise each run is rolled back at the end.
        Temporary tables (<code>eax.get_entity('Capability', 'caps')</code>) last for one run.
      </p>
      <div className="sql-login">
        {field("database", "Database")}
        {field("username", "User")}
        {field("password", "Password", "password")}
        <label><input type="checkbox" checked={allowChanges} onChange={(e) => setAllowChanges(e.target.checked)} /> Allow changes</label>
      </div>
      <details className="sql-tables" open>
        <summary>Tables and how they join</summary>
        <a href="/db-tables.svg" target="_blank" rel="noreferrer" title="Open full size">
          <img src="/db-tables.svg" alt="Database tables and the columns that join them" />
        </a>
        <p className="quiet">
          Lines are joins (child column → parent <code>id</code>). Every core table also has <code>model_id</code> →
          <code> core.models.id</code> and <code>status_code</code> → <code>core.item_statuses.code</code>.
          For one table per entity type use <code>eax.get_entity('Capability', 'caps')</code>.
        </p>
      </details>
      <textarea id="sql-text" className="sql-text" spellCheck="false" value={sql}
        onChange={(e) => setSql(e.target.value)}
        onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); runFromBox(e.target); } }} />
      <div>
        <button className="primary" disabled={busy} onClick={() => runFromBox(document.getElementById("sql-text"))}>
          {busy ? "Running..." : "Run"}
        </button>
        <span className="quiet"> Ctrl+Enter. With text selected, only the selection runs.</span>
      </div>

      {error && <p className="status bad sql-error">{error}</p>}
      {out && (
        <>
          <p className="quiet">
            Done in {out.duration_ms} ms{out.committed ? " · changes committed" : " · rolled back, nothing saved"}
          </p>
          {out.notices.map((m, i) => <p key={i} className="quiet">{m}</p>)}
          {out.results.map((r, i) => <ResultTable key={i} r={r} n={i + 1} />)}
        </>
      )}
    </section>
  );
}
