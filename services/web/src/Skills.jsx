// People's skills (owner, 9 Nov 2026, D353): each user adds their own on My profile (#/my-profile); the Skills
// repository (#/repository/skills) lists every EA Explorer user (from Keycloak) with theirs, by skill and by person.
import { useEffect, useState } from "react";
import { apiFetch, myInfo, roleName, roles } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { fmtDateTime } from "./fmt";

export function SkillTags({ value, onChange, suggestions = [], disabled }) {
  const [t, setT] = useState("");
  const add = (s) => {
    const k = s.split(",").map((x) => x.trim().replace(/\s+/g, " ")).filter(Boolean);
    const next = [...value];
    for (const x of k) if (!next.some((y) => y.toLowerCase() === x.toLowerCase())) next.push(x.slice(0, 60));
    onChange(next); setT("");
  };
  const offered = suggestions.filter((s) => !value.some((v) => v.toLowerCase() === s.toLowerCase()));
  return (
    <div className="skill-tags">
      <div className="skill-chips">
        {value.map((s) => <span key={s} className="chip skill-chip">{s}{!disabled &&
          <button className="linkish" aria-label={`Remove ${s}`} onClick={() => onChange(value.filter((x) => x !== s))}>✕</button>}</span>)}
        {!value.length && <span className="quiet small">No skills yet.</span>}
      </div>
      {!disabled && <form className="row-gap" onSubmit={(e) => { e.preventDefault(); if (t.trim()) add(t); }}>
        <input value={t} onChange={(e) => setT(e.target.value)} list="all-skills" placeholder="Add a skill (commas for several)" aria-label="Add a skill" style={{ minWidth: 300 }} />
        <datalist id="all-skills">{offered.map((s) => <option key={s} value={s} />)}</datalist>
        <button type="submit" disabled={!t.trim()}>Add</button>
      </form>}
    </div>
  );
}

export default function MyProfile() {
  const me = myInfo() || {};
  const { data, error } = useApi("/api/v1/me/skills");
  const [skills, setSkills] = useState(null);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  useEffect(() => { if (data && skills === null) setSkills(data.skills); }, [data, skills]);
  async function save() {
    try { const r = await apiFetch("/api/v1/me/skills", { method: "PUT", body: JSON.stringify({ skills }) }); setMsg({ ok: true, text: r.message }); refreshAll(); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
  }
  const changed = data && skills && JSON.stringify(skills) !== JSON.stringify(data.skills);
  return (
    <section className="page">
      <h1>My profile</h1>
      <p className="quiet small">Press / (or Ctrl+K) anywhere to find a function or content.</p>
      <table className="facts">
        <tbody>
          <tr><th>Name</th><td>{me.name || me.username}</td></tr>
          <tr><th>User name</th><td>{me.username}</td></tr>
          <tr><th>Roles</th><td>{roles().length ? roles().map(roleName).join(", ") : "none yet"}</td></tr>
          {me.email && <tr><th>Email</th><td>{me.email}</td></tr>}
        </tbody>
      </table>
      <h2>My skills</h2>
      <p className="quiet">What you know and do: any words you like (tools, methods, domains, industries). They show beside your name in the
        <a href="#/repository/skills"> Skills repository</a> and on the Organisation tab of the projects you are on. The skills other people use
        are offered as you type, so the same skill is spelled the same way.</p>
      {error && <p className="status bad">{error}</p>}
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      {skills === null ? (!error && <p className="quiet">Loading…</p>) : <>
        <SkillTags value={skills} onChange={setSkills} suggestions={data?.suggestions || []} />
        <div className="row-gap" style={{ marginTop: 10 }}>
          <button className="primary" disabled={!changed} onClick={save}>Save my skills</button>
          {changed && <button onClick={() => setSkills(data.skills)}>Undo my edits</button>}
          {data?.modified_at && <span className="small quiet">Last saved {fmtDateTime(data.modified_at)}</span>}
        </div>
      </>}
    </section>
  );
}

// the organisation's Skills repository: every user, with their own skills
export function SkillsRepository() {
  const { data, error } = useApi("/api/v1/repository/skills");
  const [q, setQ] = useState("");
  const [skill, setSkill] = useState("");
  const [view, setView] = useState("skills");
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p className="quiet">Loading…</p>;
  const ql = q.trim().toLowerCase();
  const has = (u, s) => u.skills.some((x) => x.toLowerCase() === s.toLowerCase());
  const users = data.users.filter((u) => (!skill || has(u, skill)) && (!ql || `${u.name} ${u.username} ${u.skills.join(" ")}`.toLowerCase().includes(ql)));
  const byName = Object.fromEntries(data.users.map((u) => [u.username, u]));
  const label = (u) => u.name || u.username;
  return (
    <div>
      <p className="quiet">Every EA Explorer user ({data.users.length}) with the skills
        they gave themselves on <a href="#/my-profile">My profile</a>. {data.without ? `${data.without} have none yet.` : ""} Add yours on <a href="#/my-profile">My profile</a>.</p>
      <div className="row-gap">
        <div className="cf-views" role="tablist">
          <button role="tab" aria-selected={view === "skills"} className={`cf-view${view === "skills" ? " on" : ""}`} onClick={() => setView("skills")}>By skill</button>
          <button role="tab" aria-selected={view === "people"} className={`cf-view${view === "people" ? " on" : ""}`} onClick={() => setView("people")}>By person</button>
        </div>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a person or skill" aria-label="Find" />
        <select value={skill} onChange={(e) => setSkill(e.target.value)} aria-label="Skill"><option value="">Any skill</option>
          {data.skills.map((s) => <option key={s.skill} value={s.skill}>{s.skill} ({s.people.length})</option>)}</select>
      </div>
      {view === "skills" ? (
        <div className="level-cols">
          {data.skills.filter((s) => (!skill || s.skill === skill) && (!ql || s.skill.toLowerCase().includes(ql) || s.people.some((p) => `${label(byName[p] || { username: p })}`.toLowerCase().includes(ql))))
            .map((s) => (
              <div key={s.skill} className="level-col"><h3>{s.skill} <span className="small quiet">{s.people.length}</span></h3>
                {s.people.map((p) => <div key={p} className={`level-item${p === data.me ? " skill-me" : ""}`}>{label(byName[p] || { username: p })}
                  {byName[p]?.name && <span className="small quiet"> {p}</span>}</div>)}
              </div>
            ))}
          {!data.skills.length && <p className="quiet">No one has added skills yet. Add yours on <a href="#/my-profile">My profile</a>.</p>}
        </div>
      ) : (
        <table className="grid-table">
          <thead><tr><th>Person</th><th>User name</th><th>Skills</th></tr></thead>
          <tbody>
            {users.map((u) => <tr key={u.username} className={u.username === data.me ? "skill-me" : ""}>
              <td>{label(u)}{!u.enabled && <span className="small quiet"> (disabled)</span>}</td><td className="small">{u.username}</td>
              <td>{u.skills.length ? u.skills.map((s) => <button key={s} className="tag-chip" onClick={() => setSkill(s)}>{s}</button>)
                : <span className="small quiet">none yet{u.username === data.me ? <> · <a href="#/my-profile">add yours</a></> : ""}</span>}</td></tr>)}
            {!users.length && <tr><td colSpan={3} className="quiet">Nothing matches.</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}
