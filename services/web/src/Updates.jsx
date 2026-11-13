// System admin › Updates (phase 36, D417, D512): for Super Admins and IT Admins.
//   the installed version; the repository link and the channels (Prod always; RC and Latest when enabled)
//   a channel's versions above the installed one (forward only), with release notes; update now or at a time
//   the update running (its log), or waiting for a decision after a failed step: Retry or Roll back
//   the schedule (cancel it) and the history of every update and rollback
// UpdateNotice (in App.jsx, everyone signed in): a banner before a scheduled update, and a What's new note once after one.
import { useEffect, useState } from "react";
import { apiFetch, can } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { Modal } from "./ModelOps";
import { fmtDateTime } from "./fmt";

const STATUS = {
  ok: ["ok", "Updated"], failed: ["bad", "Failed: waiting for Retry or Roll back"], running: ["warn", "Running"],
  "rolling-back": ["warn", "Rolling back"], "rolled-back": ["warn", "Rolled back"], "not-started": ["bad", "Did not start"],
  scheduled: ["", "Scheduled"], cancelled: ["", "Cancelled"],
};

export default function Updates() {
  const s = useApi("/api/v1/operations/updates");
  const [channel, setChannel] = useState("prod");
  const [editing, setEditing] = useState(false);
  const running = s.data?.current && ["running", "rolling-back"].includes(s.data.current.status);
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(() => refreshAll(), 4000);
    return () => clearInterval(t);
  }, [running]);
  if (s.error) return <p className="status bad">{s.error}</p>;
  if (!s.data) return <p>Loading...</p>;
  const d = s.data;
  const inst = d.installed || {};
  const chans = d.channels || {};
  return (
    <div className="updates">
      {d.helper_down && <p className="status warn">The operations helper does not answer (it may be restarting during an update): the history below is the database's copy.</p>}
      {d.available === false && !d.helper_down && <p className="status warn">Updates need the operations helper to see the eaxcli folder: run <code>eax clean-restart</code> once with this release.</p>}
      <div className="kpi-row">
        <div className="kpi"><b>{inst.version || "unknown"}</b><span>installed</span></div>
        <div className="kpi"><b>{chans[inst.channel]?.label || inst.channel || "Prod"}</b><span>channel</span></div>
        <div className="kpi"><b className="mono">{(inst.commit || "").slice(0, 8) || "-"}</b><span>commit</span></div>
        <div className="kpi"><b>{inst.at ? fmtDateTime(inst.at) : "-"}</b><span>last updated</span></div>
      </div>

      {d.current && <Current c={d.current} />}
      {d.scheduled && <Scheduled sc={d.scheduled} />}

      <h3>Repository and channels</h3>
      <div className="toolbar">
        <span>Repository: {d.settings?.git_url ? <code>{d.settings.git_url}</code> : <em className="quiet">not set</em>}</span>
        {can("system.operate") && <button onClick={() => setEditing(true)}>Change…</button>}
      </div>
      <div className="seg" role="tablist" aria-label="Channel">
        {Object.entries(chans).map(([k, c]) => (
          <button key={k} className={channel === k ? "on" : ""} disabled={!c.enabled} onClick={() => setChannel(k)}
            title={c.enabled ? c.about : `${c.about} Off: enable it with Change… first.`}>{c.label}{c.enabled ? "" : " (off)"}</button>
        ))}
      </div>
      <p className="quiet small">{chans[channel]?.about} Branch <code>{chans[channel]?.branch}</code>. Only versions newer than the installed one are offered (updates only go forward).</p>
      {d.settings?.git_url && !d.current && <Offered channel={channel} installed={inst} />}

      <History rows={d.history || []} />
      {editing && <SettingsDialog s={d.settings || {}} onClose={() => setEditing(false)} />}
    </div>
  );
}

function Current({ c }) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [confirm, setConfirm] = useState(false);
  const act = async (what, body) => {
    setBusy(what); setErr("");
    try { await apiFetch(`/api/v1/operations/updates/${what}`, { method: "POST", body: JSON.stringify(body || {}) }); refreshAll(); }
    catch (e) { setErr(String(e.message || e)); }
    setBusy(""); setConfirm(false);
  };
  const [cls, label] = STATUS[c.status] || ["", c.status];
  return (
    <section className={`update-current ${cls}`}>
      <h3>Update to {c.to} <span className={`status ${cls}`}>{label}</span></h3>
      <p className="small">From {c.from?.version} · by {c.by} · started {fmtDateTime(c.started)} · {c.steps?.length} step(s): {(c.steps || []).map((x) => `${x.ref} ${x.status}`).join(", ")}
        {c.backup && <> · backup <code>{c.backup}</code> (pinned)</>}</p>
      {c.error && <p className="status bad">{c.error}</p>}
      {c.status === "failed" && (
        <div className="toolbar">
          <span>The maintenance page stays on until you choose:</span>
          <button className="primary" disabled={!!busy} onClick={() => act("retry")}>{busy === "retry" ? "Starting…" : "Retry"}</button>
          <button className="danger" disabled={!!busy} onClick={() => setConfirm(true)}>Roll back…</button>
        </div>
      )}
      {err && <p className="status bad">{err}</p>}
      <pre className="update-log" aria-label="Update log">{(c.log || []).join("\n")}</pre>
      {confirm && (
        <Modal title="Roll back" onClose={() => setConfirm(false)}
          actions={<><button onClick={() => setConfirm(false)}>Cancel</button>
            <button className="danger" disabled={!!busy} onClick={() => act("rollback", { confirm: true })}>Roll back to {c.from?.version}</button></>}>
          <p>EA Explorer goes back to <b>{c.from?.version}</b>: the code as it was, and the backup taken before the update
            (<code>{c.backup}</code>) put back. Work done since {fmtDateTime(c.started)} is lost; the current state is backed up first and kept.</p>
          <p>{c.to} is marked failed in the history.</p>
        </Modal>
      )}
    </section>
  );
}

function Scheduled({ sc }) {
  const [err, setErr] = useState("");
  const cancel = async () => {
    try { await apiFetch("/api/v1/operations/updates/schedule/cancel", { method: "POST" }); refreshAll(); }
    catch (e) { setErr(String(e.message || e)); }
  };
  return (
    <div className="status warn">Scheduled: update to <b>{sc.to}</b> ({sc.channel}) at <b>{fmtDateTime(sc.at)}</b>, set by {sc.by}.
      Signed-in people see a banner beforehand. <button onClick={cancel}>Cancel the schedule</button>
      {err && <span className="status bad"> {err}</span>}
    </div>
  );
}

function Offered({ channel, installed }) {
  const v = useApi(`/api/v1/operations/updates/versions/${channel}`);
  const [pick, setPick] = useState(null);
  if (v.error) return <p className="status bad">{v.error}</p>;
  if (!v.data) return <p><span className="spinner" aria-hidden="true" /> Reading the repository…</p>;
  if (v.data.error) return <p className="status bad">{v.data.error}</p>;
  const rows = v.data.versions || [];
  if (!rows.length) return <p className="status ok">Nothing newer on this channel: {installed.version} is the newest.</p>;
  return (
    <>
      <table className="grid-table">
        <thead><tr><th>Version</th><th>Date</th><th>Notes</th><th /></tr></thead>
        <tbody>
          {rows.slice().reverse().map((r) => (
            <tr key={r.ref}>
              <td><b>{r.version}</b>{channel === "latest" && <> <code>{r.commit.slice(0, 8)}</code></>}
                {r.failed_before && <span className="status bad small"> failed here before</span>}</td>
              <td className="nowrap">{r.date ? fmtDateTime(r.date) : ""}</td>
              <td className="small">{(r.title || (r.notes || "").split("\n").find((x) => x.trim() && !x.startsWith("#")) || "").slice(0, 140)}</td>
              <td><button onClick={() => setPick(r)}>Update to this…</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {pick && <UpdateDialog r={pick} rows={rows} channel={channel} installed={installed} onClose={() => setPick(null)} />}
    </>
  );
}

function UpdateDialog({ r, rows, channel, installed, onClose }) {
  const [when, setWhen] = useState("now");
  const [at, setAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const steps = channel === "latest" ? [r] : stepsTo(rows, r);
  const go = async () => {
    setBusy(true); setErr("");
    try {
      await apiFetch("/api/v1/operations/updates/start", { method: "POST",
        body: JSON.stringify({ channel, to: channel === "latest" ? r.ref : r.version, at: when === "later" ? new Date(at).toISOString() : "", confirm: true }) });
      refreshAll(); onClose();
    } catch (e) { setErr(String(e.message || e)); setBusy(false); }
  };
  return (
    <Modal wide title={`Update ${installed.version} to ${r.version}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy || (when === "later" && !at)} onClick={go}>{busy ? "Starting…" : when === "later" ? "Schedule" : "Update now"}</button></>}>
      <ol className="small">
        <li>A full backup first: every database, every file, the configuration and the code as it is (local changes included); pinned.</li>
        <li>The maintenance page for everyone, then {steps.length > 1 ? <>each release in turn: <b>{steps.map((x) => x.version).join(" → ")}</b></> : <b>{r.version}</b>}: built here, started, checked.</li>
        <li>If a step fails it stops and asks: Retry, or Roll back to {installed.version}.</li>
      </ol>
      <fieldset className="inline">
        <label><input type="radio" checked={when === "now"} onChange={() => setWhen("now")} /> Now</label>
        <label><input type="radio" checked={when === "later"} onChange={() => setWhen("later")} /> At
          {" "}<input type="datetime-local" value={at} onChange={(e) => { setAt(e.target.value); setWhen("later"); }} aria-label="When" /></label>
      </fieldset>
      {r.failed_before && <p className="status warn">This version failed here before and was rolled back.</p>}
      <h4>Release notes</h4>
      <pre className="release-notes">{steps.map((x) => (x.notes ? `${x.version}\n${x.notes}` : `${x.version}: no notes`)).join("\n\n")}</pre>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// the releases gone through on the way (D417: one at a time): each release once, its final version or its newest RC
export function stepsTo(rows, target) {
  const key = (v) => {
    const m = /^(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?$/.exec(v || "");
    return m ? [+m[1], +m[2], +m[3], m[4] ? 0 : 1, +(m[4] || 0)] : [0, 0, 0, 0, 0];
  };
  const cmp = (a, b) => { const x = key(a), y = key(b); for (let i = 0; i < 5; i += 1) if (x[i] !== y[i]) return x[i] - y[i]; return 0; };
  const base = (v) => (v || "").split("-")[0];
  const by = {};
  rows.filter((x) => cmp(x.version, target.version) <= 0).forEach((x) => {
    const b = base(x.version);
    if (!by[b] || cmp(x.version, by[b].version) > 0) by[b] = x;
  });
  by[base(target.version)] = target;
  return Object.keys(by).sort(cmp).map((b) => by[b]);
}

function History({ rows }) {
  const [open, setOpen] = useState(null);
  return (
    <>
      <h3>History</h3>
      {!rows.length ? <p className="quiet">No updates yet.</p> : (
        <table className="grid-table">
          <thead><tr><th>Started</th><th>From</th><th>To</th><th>Channel</th><th>By</th><th>Result</th><th>Backup</th></tr></thead>
          <tbody>
            {rows.map((h) => {
              const [cls, label] = STATUS[h.status] || ["", h.status];
              return (
                <tr key={h.id} onClick={() => setOpen(h)} className="clickable">
                  <td className="nowrap">{fmtDateTime(h.started_at)}</td>
                  <td>{h.from_version}</td><td><b>{h.to_version}</b>{h.failed_version && <span className="status bad small"> {h.failed_version} failed</span>}</td>
                  <td>{h.channel}</td><td>{h.by_user}</td>
                  <td><span className={`status ${cls}`}>{label}</span>{h.sample && <span className="quiet small"> (sample)</span>}</td>
                  <td className="small mono">{h.backup}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {open && (
        <Modal wide title={`${open.kind === "rollback" ? "Roll back" : "Update"} ${open.from_version} → ${open.to_version}`} onClose={() => setOpen(null)}>
          <p className="small">By {open.by_user} · {fmtDateTime(open.started_at)}{open.finished_at && ` to ${fmtDateTime(open.finished_at)}`} · {open.channel}</p>
          {open.error && <p className="status bad">{open.error}</p>}
          <p className="small">Steps: {(open.steps || []).map((x) => `${x.ref} ${x.status}`).join(", ") || "-"}</p>
          {open.notes && <><h4>Release notes</h4><pre className="release-notes">{open.notes}</pre></>}
        </Modal>
      )}
    </>
  );
}

function SettingsDialog({ s, onClose }) {
  const [url, setUrl] = useState(s.git_url || "");
  const [rc, setRc] = useState(!!s.rc);
  const [latest, setLatest] = useState(!!s.latest);
  const [err, setErr] = useState("");
  const save = async () => {
    try {
      await apiFetch("/api/v1/operations/updates/settings", { method: "PUT", body: JSON.stringify({ git_url: url.trim(), rc, latest }) });
      refreshAll(); onClose();
    } catch (e) { setErr(String(e.message || e)); }
  };
  return (
    <Modal title="Repository and channels" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={save}>Save</button></>}>
      <label>Repository link (public git, https)<input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/<owner>/<repository>.git" /></label>
      <label className="switch-label"><input type="checkbox" checked disabled /> Prod (tags vX.Y.Z on <code>release</code>): always offered</label>
      <label className="switch-label"><input type="checkbox" checked={rc} onChange={(e) => setRc(e.target.checked)} /> RC (tags vX.Y.Z-rc.N on <code>rc</code>)</label>
      <label className="switch-label"><input type="checkbox" checked={latest} onChange={(e) => setLatest(e.target.checked)} /> Latest (every commit on <code>main</code>, untested)</label>
      <p className="quiet small">Written to the config file (a dated copy is kept first). Versions are built on this host; nothing is published to a registry.</p>
      {err && <p className="status bad">{err}</p>}
    </Modal>
  );
}

// ---------------------------------------------------------------- everyone: the banner and the What's new note
function seenKey(v) { return `eax.whatsnew.${v}`; }
function seen(v) { try { return window.localStorage.getItem(seenKey(v)) === "1"; } catch { return false; } }
function markSeen(v) { try { window.localStorage.setItem(seenKey(v), "1"); } catch { /* private window: shown again next time */ } }

export function UpdateNotice() {
  const [n, setN] = useState(null);
  const [hide, setHide] = useState(false);
  useEffect(() => {
    let live = true;
    const load = () => apiFetch("/api/v1/operations/updates/notice").then((x) => { if (live) setN(x); }).catch(() => {});
    load();
    const t = setInterval(load, 5 * 60 * 1000);
    return () => { live = false; clearInterval(t); };
  }, []);
  if (!n) return null;
  const w = n.whats_new;
  return (
    <>
      {n.scheduled && !hide && (
        <div className="break-glass-banner update-banner">EA Explorer will be updated to {n.scheduled.to} at {fmtDateTime(n.scheduled.at)}:
          it will be unavailable for a while. Save your work before then. <button className="link" onClick={() => setHide(true)}>Hide</button></div>
      )}
      {w && !seen(w.to_version) && (
        <Modal wide title={`What's new in ${w.to_version}`} onClose={() => { markSeen(w.to_version); setN({ ...n, whats_new: null }); }}
          actions={<button className="primary" onClick={() => { markSeen(w.to_version); setN({ ...n, whats_new: null }); }}>Got it</button>}>
          <p className="small">EA Explorer was updated on {fmtDateTime(w.finished_at)}.</p>
          <pre className="release-notes">{w.notes || "No release notes."}</pre>
        </Modal>
      )}
    </>
  );
}
