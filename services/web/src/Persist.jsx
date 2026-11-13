// System Admin › Persist (owner, 12 Nov 2026: "give command line and web ui ability to delete anything in persist", R2.26):
// what persist/ holds (the settings that survive every reset, the safety backups, the reset-survival results), with
// Delete beside each item and Delete everything, each confirmed by typing DELETE. The same as `eax persist`.
import { useState } from "react";
import { apiFetch } from "./auth";
import { useApi } from "./ModelViews";
import { fmtDateTime } from "./fmt";

function size(n) {
  const u = ["bytes", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i += 1; }
  return i ? `${n.toFixed(1)} ${u[i]}` : `${n} bytes`;
}

export default function PersistPage() {
  const [tick, setTick] = useState(0);
  const { data, error } = useApi(`/api/v1/admin/persist?t=${tick}`);
  const [asking, setAsking] = useState(null);     // {item} or {all: true}
  const [typed, setTyped] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true); setMsg("");
    try {
      const out = await apiFetch("/api/v1/admin/persist/delete", { method: "POST",
        body: JSON.stringify({ ...asking, confirm: typed }) });
      setMsg(`Deleted: ${(out.deleted || []).join(", ") || "nothing"}.`);
      setAsking(null); setTyped(""); setTick((t) => t + 1);
    } catch (e) { setMsg(e.message); }
    setBusy(false);
  }
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const items = data.items || [];
  return (
    <div>
      <p className="quiet">persist/ survives every reset by design. Deleting from it is for good; a deleted settings file falls back
        to its default (no schedules, no banner). The same on the command line: <code>eax persist</code>.</p>
      {msg && <p className="status">{msg}</p>}
      {!items.length ? <p className="quiet">persist/ is empty.</p> : (
        <table className="grid-table">
          <thead><tr><th>Item</th><th>What it is</th><th>Size</th><th>Changed</th><th /></tr></thead>
          <tbody>{items.map((i) => (
            <tr key={i.name}>
              <td><code>{i.name}</code></td><td className="small">{i.what}</td><td className="small">{size(i.size)}</td>
              <td className="small">{fmtDateTime(new Date(i.changed * 1000).toISOString())}</td>
              <td><button className="danger small" onClick={() => { setAsking({ item: i.name }); setTyped(""); }}>Delete</button></td>
            </tr>))}</tbody>
        </table>)}
      {items.length > 0 && <p><button className="danger" onClick={() => { setAsking({ all: true }); setTyped(""); }}>Delete everything</button></p>}
      {asking && (
        <div className="panel warn-panel" role="dialog" aria-label="Confirm delete">
          <p>This deletes <b>{asking.all ? "everything in persist/" : asking.item}</b> for good. It cannot be brought back.</p>
          <label>Type DELETE to confirm <input value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus /></label>
          <div className="row-gap">
            <button className="danger" disabled={busy || typed !== "DELETE"} onClick={go}>{busy ? "Deleting..." : "Delete"}</button>
            <button onClick={() => setAsking(null)}>Cancel</button>
          </div>
        </div>)}
    </div>
  );
}
