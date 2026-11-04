// People and their roles on one model (phase 3.1, D96). Roles on a model are given here by the model's
// Model Admins (and Super Admins): Model Admin, Architect, Model Sub Admin, Report Viewer; a person may
// hold several. Global roles (Super Admin, IT Admin, User Admin, Keycloak Admin, Model Creator, User) are
// given in Keycloak. Anyone with a role on this model also reads the models it comes from (D60).
import { useEffect, useState } from "react";
import { apiFetch, canOn, MODEL_ROLES, roleName } from "./auth";
import { refreshAll, useApi } from "./ModelViews";

const DOES = {
  "model-admin": "owns the model: metamodel, locks, people, content, derived models (and commits, later)",
  "model-sub-admin": "the Model Admin's deputy for content: changes content; reviews and commits others' changes (commits phase)",
  architect: "works on the content: entities, relationships, values",
  "report-viewer": "reads screens, pictures, reports and exports; changes nothing",
};

export default function ModelPeople({ model, m }) {
  const { data: assigned, error } = useApi(`/api/v1/models/${model}/people`);
  const [people, setPeople] = useState(null);       // from Keycloak, to find people
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("architect");
  const [msg, setMsg] = useState("");
  const manage = canOn(model, "model.people");
  useEffect(() => {
    if (!manage) return undefined;
    const t = setTimeout(() => apiFetch(`/api/v1/people${search ? `?search=${encodeURIComponent(search)}` : ""}`)
      .then(setPeople).catch((e) => setMsg(e.message)), 250);
    return () => clearTimeout(t);
  }, [search, manage]);
  const byName = Object.fromEntries((people || []).map((p) => [p.username, p]));
  async function give(username, r) {
    setMsg("");
    try { await apiFetch(`/api/v1/models/${model}/people`, { method: "POST", body: JSON.stringify({ username, role: r }) }); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  async function take(username, r) {
    setMsg("");
    const q = r ? `?role=${encodeURIComponent(r)}` : "";
    try { await apiFetch(`/api/v1/models/${model}/people/${encodeURIComponent(username)}${q}`, { method: "DELETE" }); refreshAll(); }
    catch (e) { setMsg(e.message); }
  }
  if (error) return <p className="status bad">{error}</p>;
  if (!assigned) return <p className="quiet">Loading...</p>;
  // one row per person, with every role they hold here
  const rows = Object.values(assigned.reduce((acc, a) => {
    const p = acc[a.username] || (acc[a.username] = { username: a.username, roles: [], since: a.created_at, by: a.created_by });
    p.roles.push(a.role);
    return acc;
  }, {})).sort((x, y) => x.username.localeCompare(y.username));
  const taken = new Set(rows.map((r) => r.username));
  return (
    <div>
      <p className="quiet">People with roles on {m.name}. Roles on a model are given here, by its Model Admins; a person may hold
        several. Global roles (Super Admin, IT Admin, User Admin, Keycloak Admin, Model Creator) are given in Keycloak. Everyone here
        also reads the models {m.name} comes from. Super Admins read every model.</p>
      <table className="grid-table">
        <thead><tr><th>Person</th>{MODEL_ROLES.map((r) => <th key={r} className="center" title={DOES[r]}>{roleName(r)}</th>)}<th>Since</th>{manage && <th />}</tr></thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.username}>
              <td><strong>{p.username}</strong>{byName[p.username]?.name && <><br /><span className="quiet">{byName[p.username].name}</span></>}</td>
              {MODEL_ROLES.map((r) => (
                <td key={r} className="center">
                  {manage
                    ? <input type="checkbox" checked={p.roles.includes(r)} aria-label={`${roleName(r)}: ${p.username}`}
                        onChange={(e) => (e.target.checked ? give(p.username, r) : take(p.username, r))} />
                    : p.roles.includes(r) ? "✓" : ""}
                </td>
              ))}
              <td className="quiet small">{new Date(p.since).toLocaleDateString()} by {p.by}</td>
              {manage && <td><button className="small" onClick={() => take(p.username)}>Remove all</button></td>}
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={MODEL_ROLES.length + 3} className="quiet">Nobody has a role on this model yet.</td></tr>}
        </tbody>
      </table>
      <p className="quiet small">{MODEL_ROLES.map((r) => `${roleName(r)}: ${DOES[r]}`).join(" · ")}</p>
      {manage && (
        <div className="assign-box">
          <h3>Give someone a role</h3>
          <div className="toolbar">
            <input className="search" placeholder="Search people in Keycloak" value={search} onChange={(e) => setSearch(e.target.value)} />
            <label className="quiet">as{" "}
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                {MODEL_ROLES.map((r) => <option key={r} value={r}>{roleName(r)}</option>)}
              </select>
            </label>
          </div>
          <ul className="assign-list">
            {(people || []).filter((p) => !taken.has(p.username)).slice(0, 20).map((p) => (
              <li key={p.id}>
                <button className="small" onClick={() => give(p.username, role)}>Make {roleName(role)}</button>{" "}
                <strong>{p.username}</strong> {p.name && <span className="quiet">{p.name}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {msg && <p className="status bad">{msg}</p>}
    </div>
  );
}
