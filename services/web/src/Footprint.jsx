// System Admin › Footprint (R2.22; owner, 13 Nov 2026: "measure only for now"): how much each container takes, the newest
// measurement beside the one before (image, own disk, volumes, memory, CPU, seconds to start). The same as `eax footprint`.
import { useState } from "react";
import { apiFetch } from "./auth";
import { useApi } from "./ModelViews";
import { fmtDateTime } from "./fmt";

const COLS = [["image_mb", "Image MB"], ["own_disk_mb", "Own disk MB"], ["volumes_mb", "Volumes MB"], ["memory_mb", "Memory MB"],
  ["cpu_percent", "CPU %"], ["start_seconds", "Start s"]];

export default function FootprintPage() {
  const [tick, setTick] = useState(0);
  const { data, error } = useApi(`/api/v1/admin/footprint?t=${tick}`);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function measure() {
    setBusy(true); setErr("");
    try { await apiFetch("/api/v1/admin/footprint", { method: "POST", body: JSON.stringify({ label }) }); setTick((t) => t + 1); }
    catch (e) { setErr(e.message); }
    setBusy(false);
  }
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const m = data.latest;
  const was = Object.fromEntries(((data.before || {}).containers || []).map((r) => [r.container, r]));
  const cell = (r, k) => {
    const v = r[k]; const b = (was[r.container] || {})[k];
    if (v === null || v === undefined) return "-";
    return typeof b === "number" && b !== v ? <>{v} <span className="quiet small">({v - b > 0 ? "+" : ""}{(v - b).toFixed(1)})</span></> : v;
  };
  return (
    <div>
      <p className="quiet">How much each container takes. Measure before and after a change: the change since the measurement before
        is in brackets. The same on the command line: <code>eax footprint [label]</code> (kept in work/footprint).</p>
      <div className="row-gap">
        <input placeholder="Label (optional)" value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Label" />
        <button className="primary" onClick={measure} disabled={busy}>{busy ? "Measuring..." : "Measure now"}</button>
      </div>
      {err && <p className="status bad">{err}</p>}
      {!m ? <p className="quiet">Nothing measured yet.</p> : (
        <>
          <p className="small">{fmtDateTime(m.at)}{m.label && ` (${m.label})`}{data.before && <> · compared with {fmtDateTime(data.before.at)}</>}</p>
          <table className="grid-table">
            <thead><tr><th>Container</th>{COLS.map(([k, l]) => <th key={k}>{l}</th>)}<th>Restarts</th></tr></thead>
            <tbody>{m.containers.map((r) => (
              <tr key={r.container}><td>{r.container}</td>{COLS.map(([k]) => <td key={k}>{cell(r, k)}</td>)}<td>{r.restarts || 0}</td></tr>))}
              <tr><td><b>All</b></td><td>{m.totals.image_mb}</td><td>{m.totals.own_disk_mb}</td><td>{m.totals.volumes_mb}</td><td>{m.totals.memory_mb}</td><td /><td /><td /></tr>
            </tbody>
          </table>
          {m.problems && m.problems.length > 0 && <p className="quiet small">Not measured: {m.problems.join("; ")}</p>}
        </>)}
    </div>
  );
}
