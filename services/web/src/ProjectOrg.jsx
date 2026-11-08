// A project's Organisation tab (owner, 8 Nov 2026, D302): who works on the project and their role on it. Flat, like a
// matrix organisation: no reporting lines. People are typed in and may be linked to an EA Explorer user; the
// project's members and the stakeholders of its matrix are added in one click. Shown as a list or by role.
import { useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";

export function ProjectOrgTab({ p }) {
  const url = `/api/v1/projects/${p.id}/organisation`;
  const { data, error } = useApi(url);
  const [view, setView] = useState("list");
  const [q, setQ] = useState("");
  const [nw, setNw] = useState({ name: "", role: "", username: "", skills: "" });
  const [skill, setSkill] = useState("");
  const [edit, setEdit] = useState(null);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const people = data?.people || [];
  const shown = useMemo(() => people.filter((x) => (!q.trim() || `${x.name} ${x.role} ${x.username} ${(x.skills || []).join(" ")}`.toLowerCase().includes(q.trim().toLowerCase()))
    && (!skill || (x.skills || []).includes(skill))), [people, q, skill]);
  const byRole = useMemo(() => {
    const o = {};
    shown.forEach((x) => (x.role || "(no role yet)").split(",").map((r) => r.trim()).filter(Boolean).forEach((r) => { (o[r] = o[r] || []).push(x); }));
    return Object.entries(o).sort(([a], [b]) => a.localeCompare(b));
  }, [shown]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading...</p>;
  const can = data.may_edit && !p.frozen;
  async function act(fn) {
    try { const r = await fn(); setMsg({ ok: true, text: r?.message || "Done." }); refreshAll(); return true; } catch (e) { setMsg({ ok: false, text: e.message }); return false; }
  }
  const post = (body) => act(() => apiFetch(url, { method: "POST", body: JSON.stringify(body) }));
  async function add(e) {
    e.preventDefault();
    if (await post({ ...nw, skills: nw.skills.split(",") })) setNw({ name: "", role: "", username: "", skills: "" });
  }
  async function save() {
    if (await act(() => apiFetch(`${url}/${edit.id}`, { method: "PUT", body: JSON.stringify({ name: edit.name, role: edit.role, username: edit.username,
      skills: (edit.skillsText || "").split(",") }) }))) setEdit(null);
  }
  const userPick = (value, onChange) => (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="EA Explorer user">
      <option value="">not a user</option>
      {[...new Set([...data.members, ...(value ? [value] : [])])].map((u) => <option key={u} value={u}>{u}</option>)}
    </select>
  );
  return (
    <div>
      <p className="quiet">Who works on the project, their role on it and their skills. It is flat, like a matrix organisation: people keep their place in the
        organisation and take a role here, with no reporting lines. Anyone can be listed (client staff, vendors, consultants); link them to an
        EA Explorer user when they are one.</p>
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <datalist id="org-roles">{data.roles.map((r) => <option key={r} value={r} />)}</datalist>
      <datalist id="org-skills">{(data.skills || []).map((k) => <option key={k} value={k} />)}</datalist>
      {can && (
        <form className="row-gap" onSubmit={add}>
          <input value={nw.name} onChange={(e) => setNw({ ...nw, name: e.target.value })} placeholder="Name" aria-label="Name" />
          <input value={nw.role} onChange={(e) => setNw({ ...nw, role: e.target.value })} placeholder="Role on the project" aria-label="Role on the project" list="org-roles" />
          <input value={nw.skills} onChange={(e) => setNw({ ...nw, skills: e.target.value })} placeholder="Skills, comma separated" aria-label="Skills" list="org-skills" />
          {userPick(nw.username, (v) => setNw({ ...nw, username: v, name: nw.name || v }))}
          <button className="primary" type="submit" disabled={!nw.name.trim()}>＋ Add</button>
          {data.not_listed.length > 0 && <button type="button" onClick={() => post({ members: true })}
            title={data.not_listed.join(", ")}>＋ The project's members ({data.not_listed.length})</button>}
          {data.stakeholders_not_listed.length > 0 && <button type="button" onClick={() => post({ stakeholders: true })}
            title={data.stakeholders_not_listed.map((s) => s.name).join(", ")}>＋ Stakeholders ({data.stakeholders_not_listed.length})</button>}
        </form>
      )}
      <div className="row-gap filters">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search people and roles" aria-label="Search people and roles" />
        {(data.skills || []).length > 0 && <select value={skill} onChange={(e) => setSkill(e.target.value)} aria-label="Skill"><option value="">Any skill</option>
          {data.skills.map((k) => <option key={k}>{k}</option>)}</select>}
        <span className="small quiet">{people.length} {people.length === 1 ? "person" : "people"}</span>
        <span className="push-right view-toggle" role="group" aria-label="View">
          <button className={view === "list" ? "on" : ""} onClick={() => setView("list")}>☰ List</button>
          <button className={view === "roles" ? "on" : ""} onClick={() => setView("roles")}>▦ By role</button>
        </span>
      </div>
      {!shown.length ? <p className="quiet">{people.length ? "Nobody matches." : "Nobody listed yet."}</p> : view === "roles" ? (
        <div className="org-roles">
          {byRole.map(([role, xs]) => (
            <div key={role} className="org-role">
              <div className="org-role-title">{role} <span className="quiet small">{xs.length}</span></div>
              {xs.map((x) => <div key={x.id} className="org-person">{x.name}{x.username && <span className="quiet small"> · {x.username}</span>}
                {(x.skills || []).length > 0 && <div className="small quiet">{x.skills.join(", ")}</div>}
                {x.stakeholder && <span className="chip small">stakeholder</span>}</div>)}
            </div>
          ))}
        </div>
      ) : (
        <table className="grid-table">
          <thead><tr><th>Name</th><th>Role on the project</th><th>Skills</th><th>EA Explorer user</th><th /></tr></thead>
          <tbody>
            {shown.map((x) => (edit?.id === x.id ? (
              <tr key={x.id}>
                <td><input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} aria-label="Name" /></td>
                <td><input value={edit.role} onChange={(e) => setEdit({ ...edit, role: e.target.value })} list="org-roles" aria-label="Role on the project" /></td>
                <td><input value={edit.skillsText} onChange={(e) => setEdit({ ...edit, skillsText: e.target.value })} list="org-skills" aria-label="Skills" /></td>
                <td>{userPick(edit.username, (v) => setEdit({ ...edit, username: v }))}</td>
                <td className="nowrap"><button className="primary" onClick={save} disabled={!edit.name.trim()}>Save</button> <button onClick={() => setEdit(null)}>Cancel</button></td>
              </tr>
            ) : (
              <tr key={x.id}>
                <td><b>{x.name}</b>{x.stakeholder && <a className="chip small" href={`#/projects/${p.id}/stakeholders`} title="On the stakeholder matrix">stakeholder</a>}</td>
                <td>{x.role || <span className="quiet">–</span>}</td>
                <td>{(x.skills || []).map((k) => <span key={k} className="chip small">{k}</span>)}</td>
                <td>{x.username || <span className="quiet">–</span>}</td>
                <td className="nowrap">{can && <>
                  <button className="linkish" onClick={() => setEdit({ ...x, skillsText: (x.skills || []).join(", ") })} aria-label={`Change ${x.name}`}>✎</button>{" "}
                  <button className="linkish" onClick={() => act(() => apiFetch(`${url}/${x.id}`, { method: "DELETE" }))} aria-label={`Take ${x.name} out`}>🗑</button></>}</td>
              </tr>
            )))}
          </tbody>
        </table>
      )}
    </div>
  );
}
