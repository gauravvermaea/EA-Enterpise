// The banner under the top bar (owner, 10 Nov 2026, D558): one message an admin sets on System admin > Banner.
// No banner set, outside its times, or not for this person: nothing at all is shown (no empty strip). It is kept by the
// operations helper in persist/banner.json, so it survives resets. Information (blue), notice (amber), urgent (red),
// each with its word and icon too (colour is never the only signal). A person may hide it when it allows that: hidden
// in this browser until the text changes.
import { useEffect, useState } from "react";
import { apiFetch, can } from "./auth";
import { fmtDateTime } from "./fmt";

const LEVEL = { info: ["ℹ", "Information"], notice: ["⚠", "Notice"], urgent: ["⛔", "Urgent"] };
const KEY = "eax.banner.hidden";

function hiddenKey() { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } }
function hide(k) { try { localStorage.setItem(KEY, k); } catch { /* private window: hidden for this page only */ } }

export function AdminBanner() {
  const [b, setB] = useState(null);
  const [gone, setGone] = useState("");
  useEffect(() => {
    let live = true;
    const load = () => apiFetch("/api/v1/banner").then((x) => { if (live) setB(x?.banner || null); }).catch(() => {});
    load();
    const t = setInterval(load, 60 * 1000);           // starts and ends by itself
    return () => { live = false; clearInterval(t); };
  }, []);
  if (!b || !b.text) return null;
  if (b.dismissible && (gone === b.key || hiddenKey() === b.key)) return null;
  const [icon, word] = LEVEL[b.level] || LEVEL.info;
  return (
    <div className={`admin-banner level-${b.level}`} role={b.level === "urgent" ? "alert" : "status"}>
      <span className="admin-banner-word"><span aria-hidden="true">{icon}</span> {word}:</span>{" "}
      <span>{b.text}</span>
      {b.link && (b.link_safe
        ? <> {" "}<a href={b.link} {...(b.link.startsWith("#") ? {} : { target: "_blank", rel: "noopener noreferrer" })}>{b.link_text || "More"}</a></>
        : <span className="small"> ({b.link})</span>)}
      {b.dismissible && <button className="linkish admin-banner-hide" onClick={() => { hide(b.key); setGone(b.key); }}
        aria-label="Hide this banner">Hide</button>}
    </div>
  );
}

// System admin > Banner
export function BannerAdmin() {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => apiFetch("/api/v1/admin/banner").then((x) => {
    setData(x);
    const b = x.banner || {};
    setForm({ text: b.text || "", link: b.link || "", link_text: b.link_text || "", level: b.level || "info",
      audience: b.audience || "everyone", dismissible: b.dismissible !== false, starts: b.starts || "", ends: b.ends || "" });
  }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  if (!can("system.operate")) return <p className="quiet">The banner is set by IT Admins and Super Admins.</p>;
  if (err && !data) return <p className="status bad">{err}</p>;
  if (!data || !form) return <p><span className="spinner" aria-hidden="true" /> Reading the banner…</p>;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  async function save() {
    setBusy(true); setErr(""); setMsg("");
    try { await apiFetch("/api/v1/admin/banner", { method: "PUT", body: JSON.stringify(form) }); setMsg("The banner is set."); load(); }
    catch (e) { setErr(e.message); }
    setBusy(false);
  }
  async function clear() {
    setBusy(true); setErr(""); setMsg("");
    try { await apiFetch("/api/v1/admin/banner", { method: "DELETE" }); setMsg("The banner is cleared: nothing is shown."); load(); }
    catch (e) { setErr(e.message); }
    setBusy(false);
  }
  const [icon, word] = LEVEL[form.level] || LEVEL.info;
  return (
    <div className="banner-admin">
      <p className="quiet">One short message under the top bar, for everyone signed in (or admins only). When no banner is set, nothing is shown.
        It is kept in <code>persist/banner.json</code>, so it survives resets.</p>
      {data.warning && <p className="status warn" role="alert">{data.warning}</p>}
      <p><strong>Now:</strong> {data.showing ? <>showing ({LEVEL[data.showing.level]?.[1]}) to {data.showing.audience === "admins" ? "admins only" : "everyone"}</>
        : data.banner ? "set, but not showing now (outside its times)" : "no banner: nothing is shown"}</p>
      {msg && <p className="status ok">{msg}</p>}
      {err && <p className="status bad">{err}</p>}
      <fieldset className="cc-form"><legend>The banner</legend>
        <label className="cc-param">Message <textarea rows={2} maxLength={400} value={form.text} onChange={(e) => set("text", e.target.value)}
          placeholder="e.g. EA Explorer is being upgraded on Saturday from 08:00 to 10:00." /></label>
        <label className="cc-param">Level <select value={form.level} onChange={(e) => set("level", e.target.value)}>
          <option value="info">Information (blue)</option><option value="notice">Notice (amber)</option><option value="urgent">Urgent (red)</option></select></label>
        <label className="cc-param">Link (optional) <input value={form.link} onChange={(e) => set("link", e.target.value)} placeholder="https://… or #/documentation" /></label>
        <label className="cc-param">Link text <input value={form.link_text} onChange={(e) => set("link_text", e.target.value)} placeholder="More" /></label>
        <label className="cc-param">Shown from (optional) <input type="datetime-local" value={form.starts} onChange={(e) => set("starts", e.target.value)} /></label>
        <label className="cc-param">Until (optional) <input type="datetime-local" value={form.ends} onChange={(e) => set("ends", e.target.value)} /></label>
        <label className="cc-param">Who sees it <select value={form.audience} onChange={(e) => set("audience", e.target.value)}>
          <option value="everyone">Everyone signed in</option><option value="admins">IT Admins and Super Admins only</option></select></label>
        <label className="cc-param"><input type="checkbox" checked={form.dismissible} onChange={(e) => set("dismissible", e.target.checked)} /> People may hide it (until the text changes)</label>
      </fieldset>
      {form.text.trim() && <><p className="small quiet">Preview:</p>
        <div className={`admin-banner level-${form.level}`}><span className="admin-banner-word"><span aria-hidden="true">{icon}</span> {word}:</span> {form.text}
          {form.link && <> <a href="#/admin/banner" onClick={(e) => e.preventDefault()}>{form.link_text || "More"}</a></>}</div></>}
      <div className="toolbar">
        <button className="primary" disabled={busy || !form.text.trim()} onClick={save}>Save the banner</button>
        <button disabled={busy || !data.banner} onClick={clear}>Clear the banner</button>
      </div>
      {data.history?.length > 0 && <>
        <h3>Earlier banners</h3>
        <table className="grid-table">
          <thead><tr><th>When</th><th>Who</th><th>What</th><th>Message</th><th>Level</th><th>Shown</th></tr></thead>
          <tbody>{data.history.map((h) => (
            <tr key={`${h.at}${h.what}${h.cleared_at || ""}`}>
              <td>{fmtDateTime(h.cleared_at || h.at)}</td><td>{h.cleared_by || h.by}</td>
              <td>{h.what === "cleared" ? "cleared" : "set"}{h.source && h.source !== "admin" ? ` (${h.source})` : ""}</td>
              <td>{h.text}</td><td>{LEVEL[h.level]?.[1]}</td>
              <td className="small">{h.starts || h.ends ? `${h.starts ? fmtDateTime(h.starts) : "…"} to ${h.ends ? fmtDateTime(h.ends) : "…"}` : "always"}</td>
            </tr>))}</tbody>
        </table>
      </>}
    </div>
  );
}
