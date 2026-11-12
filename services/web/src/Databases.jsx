// System Admin › Databases (R2.50, D611; owner, 12 Nov 2026: "We need a setting in config for all the different DBs to have
// same or separate container"): every database EA Explorer uses, what it holds, its setting in eaexplorer.env and where
// it lives now (the shared PostgreSQL, or a container or server of its own), and whether it answers. Read only: a
// database moves by its setting (docs/databases.md).
import { useApi } from "./ModelViews";

export default function DatabasesPage() {
  const { data, error } = useApi("/api/v1/admin/databases");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  return (
    <div>
      <p className="quiet">Every database EA Explorer uses. Each has its own setting in work/eaexplorer.env: empty means the shared
        PostgreSQL (the db container); set it to move that database to a container or server of its own: dump it, restore it
        there, set the setting, restart (docs/databases.md). Backups and restores follow each one to where it lives.</p>
      <table className="grid-table">
        <thead><tr><th>Database</th><th>What it holds</th><th>Where it lives</th><th>Setting</th><th>Answers</th></tr></thead>
        <tbody>{data.databases.map((d) => (
          <tr key={d.key}>
            <td><b>{d.key}</b></td><td className="small">{d.what}</td>
            <td className="small">{d.where}{d.own && <span className="badge"> own server</span>}</td>
            <td><code className="small">{d.setting}</code></td>
            <td className="small">{d.answers === null ? <span className="quiet">its service checks it</span>
              : d.answers ? <span className="ok-text">yes</span> : <span className="bad-text" title={d.error}>no: {d.error}</span>}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

