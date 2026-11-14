// System Admin › Footprint (R2.22; owner, 13 Nov 2026: "measure only for now"): how much each container takes, the newest
// measurement beside the one before (image, own disk, volumes, memory, CPU, seconds to start). The same as `eax footprint`.
// Memory over time (R3.5-M1): the newest watch (`eax footprint --watch`, or a self-test run, which is always watched):
// each container's lowest, average and peak, the whole installation's peak beside the guide (10 GB, not a limit) and
// whether the Docker host paged.
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
      <MemoryWatch w={data.memory} />
    </div>
  );
}

const gb = (mb) => `${(mb / 1024).toFixed(1)} GB`;

// The newest memory watch (R3.5-M1): a self-test run is always watched; `eax footprint --watch [minutes] [label]` too.
function MemoryWatch({ w }) {
  return (
    <div className="merge-step">
      <h3>Memory over time</h3>
      {!w ? <p className="quiet">Not watched yet: every self-test run is watched on its own, or run <code>eax footprint --watch 30 at-rest</code>.</p> : <>
        <p className="small">{fmtDateTime(w.at)} to {fmtDateTime(w.until)}{w.label && ` (${w.label})`} · {w.minutes} minutes, {w.samples} samples</p>
        <p><b>Peak of the whole installation: {gb(w.total_peak_mb)}</b> at {fmtDateTime(w.total_peak_at)}, average {gb(w.total_average_mb)}
          {" "}<span className={w.within_target ? "status ok" : "status warn"}>{w.within_target ? "within" : "above"} the guide of {gb(w.target_mb)}</span>
          {" "}<span className="quiet small">(a guide, not a limit)</span></p>
        {w.host && w.host.total_mb && <p className="small">Docker host {gb(w.host.total_mb)}; the least left at any moment {gb(w.host.least_available_mb)};
          swap in use at most {Math.round(w.host.most_swap_used_mb)} MB (at the start {Math.round(w.host.swap_used_at_start_mb)} MB):{" "}
          <b className={w.host.paged ? "status bad" : "status ok"}>{w.host.paged ? "it paged" : "no paging"}</b></p>}
        <table className="grid-table">
          <thead><tr><th>Container</th><th>Lowest MB</th><th>Average MB</th><th>Peak MB</th><th>Peak at</th></tr></thead>
          <tbody>{w.containers.map((r) => <tr key={r.container}><td>{r.container}</td><td>{r.lowest_mb}</td><td>{r.average_mb}</td>
            <td>{r.peak_mb}</td><td>{fmtDateTime(r.peak_at)}</td></tr>)}</tbody>
        </table>
      </>}
    </div>
  );
}
