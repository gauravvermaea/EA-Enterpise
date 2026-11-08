// Calendars (owner, 8 Nov 2026, phase 13.0.9, D324): a project's (kept by its members) and the organisation's (kept by
// Super Admins). An event is a date, a time and a topic, once or repeated; everyone on the project (or in the
// organisation) is taken as invited. Month, week and day views; download as .ics, or subscribe with a private link.
import { useEffect, useMemo, useState } from "react";
import { apiDownload, apiFetch } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const monday = (d) => addDays(d, -((d.getDay() + 6) % 7));
const REPEAT = { none: "Once", daily: "Every day", weekly: "Every week", monthly: "Every month", yearly: "Every year" };

export function CalendarView({ cal, title }) {
  const [view, setView] = useState("month");
  const [day, setDay] = useState(() => new Date());
  const [edit, setEdit] = useState(null);
  const [sub, setSub] = useState(false);
  const [msg, setMsg] = useState({ ok: true, text: "" });
  const range = useMemo(() => {
    if (view === "day") return [day, day];
    if (view === "week") { const a = monday(day); return [a, addDays(a, 6)]; }
    const first = new Date(day.getFullYear(), day.getMonth(), 1);
    const a = monday(first);
    return [a, addDays(a, 41)];
  }, [view, day]);
  const { data, error } = useApi(`/api/v1/calendars/${cal}?from=${iso(range[0])}&to=${iso(range[1])}`);
  const byDate = useMemo(() => {
    const m = {};
    for (const o of data?.occurrences || []) (m[o.date] = m[o.date] || []).push(o);
    return m;
  }, [data]);
  const evs = Object.fromEntries((data?.events || []).map((e) => [e.id, e]));
  const move = (n) => setDay(view === "month" ? new Date(day.getFullYear(), day.getMonth() + n, 1) : addDays(day, view === "week" ? 7 * n : n));
  const today = iso(new Date());
  const label = view === "month" ? day.toLocaleDateString(undefined, { month: "long", year: "numeric" })
    : view === "week" ? `${range[0].toLocaleDateString()} – ${range[1].toLocaleDateString()}` : day.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const Occ = ({ o }) => (
    <button className="cal-occ" onClick={() => setEdit({ ...evs[o.event], _date: o.date })} title={`${o.topic}${o.at_time ? ` at ${o.at_time}` : ""} · ${REPEAT[o.repeat]}`}>
      {o.at_time && <span className="cal-time">{o.at_time}</span>} {o.topic}{o.repeat !== "none" ? " ↻" : ""}</button>
  );
  if (error) return <p className="status bad">{error}</p>;
  return (
    <div className="cal">
      {title}
      <p className="small quiet">{data ? `Everyone invited: ${data.invited}. ` : ""}Download it, or subscribe from Outlook, Google or Apple Calendar with your own private link.</p>
      <div className="row-gap cal-bar">
        <button onClick={() => move(-1)} aria-label="Earlier">‹</button>
        <button onClick={() => setDay(new Date())}>Today</button>
        <button onClick={() => move(1)} aria-label="Later">›</button>
        <b className="cal-label">{label}</b>
        <span style={{ flex: 1 }} />
        <div className="view-toggle" role="group" aria-label="View">
          {["month", "week", "day"].map((v) => <button key={v} className={view === v ? "on" : ""} onClick={() => setView(v)}>{v[0].toUpperCase() + v.slice(1)}</button>)}
        </div>
        {data?.may_add && <button className="primary" onClick={() => setEdit({ starts_on: iso(day), repeat: "none", minutes: 60 })}>＋ Event</button>}
        <button onClick={() => apiDownload(`/api/v1/calendars/${cal}/ics`, `${data?.name || "calendar"}.ics`).catch((e) => setMsg({ ok: false, text: e.message }))}>⬇ .ics</button>
        <button onClick={() => setSub(true)}>🔗 Subscribe…</button>
      </div>
      {msg.text && <p className={`status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      {!data ? <p className="quiet">Loading...</p> : view === "month" ? (
        <div className="cal-month">
          {DAYS.map((d) => <div key={d} className="cal-head">{d}</div>)}
          {Array.from({ length: 42 }, (_, i) => addDays(range[0], i)).map((d) => {
            const k = iso(d);
            return (
              <div key={k} className={`cal-cell${d.getMonth() !== day.getMonth() ? " out" : ""}${k === today ? " today" : ""}`}
                onDoubleClick={() => data.may_add && setEdit({ starts_on: k, repeat: "none", minutes: 60 })}>
                <button className="linkish cal-num" onClick={() => { setDay(d); setView("day"); }}>{d.getDate()}</button>
                {(byDate[k] || []).slice(0, 4).map((o, j) => <Occ key={j} o={o} />)}
                {(byDate[k] || []).length > 4 && <button className="linkish small" onClick={() => { setDay(d); setView("day"); }}>+{byDate[k].length - 4} more</button>}
              </div>
            );
          })}
        </div>
      ) : (
        <div className={view === "week" ? "cal-week" : "cal-day"}>
          {Array.from({ length: view === "week" ? 7 : 1 }, (_, i) => addDays(range[0], i)).map((d) => {
            const k = iso(d);
            return (
              <div key={k} className={`cal-col${k === today ? " today" : ""}`}>
                <div className="cal-head">{d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}</div>
                {(byDate[k] || []).map((o, j) => <Occ key={j} o={o} />)}
                {!(byDate[k] || []).length && <p className="small quiet">Nothing.</p>}
              </div>
            );
          })}
        </div>
      )}
      {edit && <EventDialog cal={cal} ev={edit} may={data?.may_add} onClose={(m) => { setEdit(null); if (m) setMsg({ ok: true, text: m }); }} />}
      {sub && <SubscribeDialog cal={cal} onClose={() => setSub(false)} />}
    </div>
  );
}

function EventDialog({ cal, ev, may, onClose }) {
  const isNew = !ev.id;
  const [f, setF] = useState({ topic: ev.topic || "", starts_on: ev.starts_on, at_time: ev.at_time || "", minutes: ev.minutes || 60, notes: ev.notes || "",
    repeat: ev.repeat || "none", weekdays: ev.weekdays || [], until_on: ev.until_on || "", times: ev.times || "" });
  const [err, setErr] = useState("");
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const base = `/api/v1/calendars/${cal}`;
  async function go(fn) {
    setErr("");
    try { const r = await fn(); refreshAll(); onClose(r.message); } catch (e) { setErr(e.message); }
  }
  const save = () => go(() => apiFetch(isNew ? base : `${base}/events/${ev.id}`, { method: isNew ? "POST" : "PUT", body: JSON.stringify(f) }));
  const canEdit = isNew ? may : true;     // the server says no when it is not yours to change
  return (
    <Modal title={isNew ? "A new event" : ev.topic} onClose={() => onClose()}
      actions={<>{!isNew && <><button className="danger" onClick={() => go(() => apiFetch(`${base}/events/${ev.id}`, { method: "DELETE" }))}>Delete</button>
        {ev.repeat !== "none" && ev._date && <button onClick={() => go(() => apiFetch(`${base}/events/${ev.id}`, { method: "PUT", body: JSON.stringify({ skip: ev._date }) }))}>Skip {ev._date}</button>}</>}
        <button onClick={() => onClose()}>Cancel</button>{canEdit && <button className="primary" disabled={!f.topic.trim() || !f.starts_on} onClick={save}>Save</button>}</>}>
      {err && <p className="status bad">{err}</p>}
      <div className="ed-form">
        <label className="ed-field"><span>Topic</span><input value={f.topic} onChange={(e) => set("topic", e.target.value)} autoFocus /></label>
        <div className="row-gap">
          <label className="ed-field"><span>Date</span><input type="date" value={f.starts_on} onChange={(e) => set("starts_on", e.target.value)} /></label>
          <label className="ed-field"><span>Time <span className="quiet">(empty: all day)</span></span><input type="time" value={f.at_time} onChange={(e) => set("at_time", e.target.value)} /></label>
          <label className="ed-field"><span>Minutes</span><input type="number" min="5" max="1440" value={f.minutes} onChange={(e) => set("minutes", e.target.value)} style={{ width: 90 }} /></label>
        </div>
        <div className="row-gap">
          <label className="ed-field"><span>Repeats</span><select value={f.repeat} onChange={(e) => set("repeat", e.target.value)}>
            {Object.entries(REPEAT).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          {f.repeat !== "none" && <>
            <label className="ed-field"><span>Until <span className="quiet">(optional)</span></span><input type="date" value={f.until_on || ""} onChange={(e) => set("until_on", e.target.value)} /></label>
            <label className="ed-field"><span>or this many times</span><input type="number" min="1" value={f.times || ""} onChange={(e) => set("times", e.target.value)} style={{ width: 90 }} /></label>
          </>}
        </div>
        {f.repeat === "weekly" && <div className="row-gap small">On {DAYS.map((d, i) => (
          <label key={d}><input type="checkbox" checked={f.weekdays.includes(i)} onChange={() => set("weekdays", f.weekdays.includes(i) ? f.weekdays.filter((x) => x !== i) : [...f.weekdays, i])} /> {d}</label>))}
          <span className="quiet">(none ticked: the start date's weekday)</span></div>}
        <label className="ed-field"><span>Notes <span className="quiet">(optional)</span></span><textarea rows={3} value={f.notes} onChange={(e) => set("notes", e.target.value)} /></label>
        {!isNew && <p className="small quiet">Added by {ev.created_by}. Changed or deleted by them, the Project Admin or Lead Architect (a project's), or a Super Admin.</p>}
      </div>
    </Modal>
  );
}

function SubscribeDialog({ cal, onClose }) {
  const [link, setLink] = useState(null);
  const [msg, setMsg] = useState("");
  const get = (renew) => apiFetch(`/api/v1/calendars/${cal}/feed`, { method: "POST", body: JSON.stringify({ renew }) })
    .then((r) => { setLink(`${window.location.origin}${r.path}`); setMsg(r.message); }).catch((e) => setMsg(e.message));
  useEffect(() => { get(false); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Modal title="Subscribe to this calendar" onClose={onClose} actions={<><button onClick={() => get(true)}>Renew the link</button><button className="primary" onClick={onClose}>Done</button></>}>
      <p className="small">Your own private link: add it in Outlook (Add calendar › From internet), Google Calendar (Other calendars › From URL) or Apple
        Calendar (New calendar subscription). Keep it to yourself; <b>Renew the link</b> stops the old one.</p>
      {link ? <input readOnly value={link} onFocus={(e) => e.target.select()} style={{ width: "100%" }} aria-label="Subscription link" /> : <p className="quiet">Making the link...</p>}
      {link && <p><button onClick={() => navigator.clipboard?.writeText(link).then(() => setMsg("Copied."))}>Copy</button></p>}
      {msg && <p className="small status ok">{msg}</p>}
    </Modal>
  );
}
