// System Admin › Running › Hosts and Mounts (Release 2: R2.16, R2.17; owner, 11 Nov 2026), and the container alert banner
// (R2.19). Read through the operations helper. Hosts: the Docker engine EA Explorer runs on, its CPUs, memory and disks,
// what EA Explorer takes of them, levels (green, amber, red) and the day's history. Mounts: every volume and bind mount,
// who uses it where, warnings; one looked into read only (size, free space, largest, newest and oldest files, folders,
// search). Every look at a mount is in the audit trail.
import { useEffect, useState } from "react";
import FileExplorer from "./FileExplorer";
import { apiFetch, can } from "./auth";
import { fmtDateTime } from "./fmt";
import { useApi } from "./ModelViews";

export const bytes = (b) => (b == null ? "?" : b >= 1e12 ? `${(b / 1e12).toFixed(1)} TB` : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB`
  : b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB` : b >= 1e3 ? `${Math.round(b / 1e3)} kB` : `${b} B`);
const pct = (v) => (v == null ? "?" : `${v}%`);
const TONE = { green: "ok", amber: "warn", red: "bad", unknown: "" };
const since = (s) => (s == null ? "?" : s > 86400 ? `${Math.floor(s / 86400)} d ${Math.floor((s % 86400) / 3600)} h` : `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`);

function Spark({ points, field, max = 100, label }) {
  const vals = points.map((p) => p[field]).filter((v) => v != null);
  if (vals.length < 2) return <span className="quiet small">no history yet</span>;
  const w = 240, h = 40;
  const d = vals.map((v, i) => `${i ? "L" : "M"}${(i / (vals.length - 1)) * w},${h - (Math.min(v, max) / max) * h}`).join(" ");
  return (<svg width={w} height={h} role="img" aria-label={`${label}: the last ${vals.length} minutes`} className="spark">
    <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>);
}

export function HostsPage() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const load = () => apiFetch("/api/v1/admin/hosts").then(setD).catch((e) => setErr(e.message));
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, []);
  if (!can("system.operate")) return <p className="status bad">Hosts are for IT Admins and Super Admins.</p>;
  if (!d) return err ? <p className="status bad">{err}</p> : <p>Loading...</p>;
  const hist = d.history || [];
  return (
    <section className="hosts" aria-label="Hosts">
      <p className="quiet">The Docker engine EA Explorer runs on (one on a laptop or a single server). Amber at {d.thresholds.cpu.warn}% CPU,
        {" "}{d.thresholds.memory.warn}% memory and {d.thresholds.disk.warn}% disk; red (and an alert) at {d.thresholds.cpu.alert}%,
        {" "}{d.thresholds.memory.alert}% and {d.thresholds.disk.alert}% (EAX_HOST_WARN_* and EAX_HOST_ALERT_* in System settings).</p>
      <button onClick={load}>Refresh</button>
      {d.hosts.map((h) => (
        <div key={h.name || "host"} className="card host-card">
          <h3>{h.name || "Docker engine"} <span className="quiet small">{h.os} · kernel {h.kernel} · {h.architecture}</span></h3>
          {h.error && <p className="status bad">{h.error}</p>}
          <table className="grid-table">
            <tbody>
              <tr><th>Docker</th><td>{h.docker_version}{h.compose_version ? ` · Compose ${h.compose_version}` : ""} · data in <code>{h.docker_root}</code></td></tr>
              <tr><th>CPU</th><td><span className={`status ${TONE[h.levels.cpu]}`}>{pct(h.cpu_percent)}</span> of {h.cpus} CPUs
                · load {h.load.join(" / ")} · EA Explorer {pct(h.eax_cpu_percent)} <Spark points={hist} field="cpu" label="CPU" /></td></tr>
              <tr><th>Memory</th><td><span className={`status ${TONE[h.levels.memory]}`}>{pct(h.memory_percent)}</span> of {bytes(h.memory_total_bytes)}
                {" "}· free {bytes(h.memory_free_bytes)} · EA Explorer {bytes(h.eax_memory_bytes)} · the rest of the machine {bytes(h.other_memory_bytes)}
                <Spark points={hist} field="memory" label="Memory" /></td></tr>
              <tr><th>Disk</th><td><span className={`status ${TONE[h.levels.disk]}`}>{pct(h.disk_percent)}</span> used on Docker's disk
                <Spark points={hist} field="disk" label="Disk" /></td></tr>
              <tr><th>Containers</th><td>{h.eax_running} of EA Explorer's {h.eax_containers} running · {h.containers_running} running on the engine in all
                · {h.images} images</td></tr>
              <tr><th>Up</th><td>{since(h.uptime_seconds)}</td></tr>
            </tbody>
          </table>
          <h4>Disks</h4>
          <table className="grid-table"><thead><tr><th>Where</th><th>Holds</th><th>Size</th><th>Used</th><th>Free</th></tr></thead>
            <tbody>{h.disks.map((x) => (
              <tr key={x.path}><td>{x.label} <code className="small">{x.path}</code></td><td className="small">{x.same_as ? `the same disk as ${x.same_as}` : x.holds}</td>
                <td>{bytes(x.total_bytes)}</td><td><span className={`status ${TONE[x.level] || ""}`}>{pct(x.used_percent)}</span></td><td>{bytes(x.free_bytes)}</td></tr>))}
            </tbody></table>
          {h.docker_disk.length > 0 && <>
            <h4>Docker's own disk</h4>
            <table className="grid-table"><thead><tr><th>Kind</th><th>Count</th><th>Active</th><th>Size</th><th>Could be cleared</th></tr></thead>
              <tbody>{h.docker_disk.map((k) => <tr key={k.kind}><td>{k.kind}</td><td>{k.count}</td><td>{k.active}</td><td>{bytes(k.bytes)}</td><td>{k.reclaimable}</td></tr>)}</tbody></table></>}
          <h4>What each container takes</h4>
          <table className="grid-table"><thead><tr><th>Container</th><th>CPU (of the machine)</th><th>Memory</th></tr></thead>
            <tbody>{h.shares.map((s) => <tr key={s.service}><td>{s.service}</td><td>{pct(s.cpu_percent)}</td><td>{bytes(s.memory_bytes)}</td></tr>)}</tbody></table>
        </div>
      ))}
    </section>
  );
}

export function MountsPage() {
  const { data, error } = useApi("/api/v1/admin/mounts");
  const [pick, setPick] = useState(null);
  const [browse, setBrowse] = useState(null);
  if (!can("system.operate")) return <p className="status bad">Mounts are for IT Admins and Super Admins.</p>;
  if (!data) return error ? <p className="status bad">{error}</p> : <p>Loading...</p>;
  return (
    <section className="mounts" aria-label="Mounts">
      <p className="quiet">Every Docker volume and bind mount EA Explorer's containers use. Look into one to see its size, the free space
        under it and its largest, newest and oldest files; it is attached read only, so nothing in it changes. Every look is in the audit trail.</p>
      <table className="grid-table">
        <thead><tr><th>Mount</th><th>Kind</th><th>Used by (where in the container)</th><th>Size</th><th>Warnings</th><th /></tr></thead>
        <tbody>{data.mounts.map((m) => (
          <tr key={m.id} className={m.warnings.length ? "warn-row" : ""}>
            <td><code className="small">{m.source}</code>{m.type === "bind" && m.host_path !== m.source && <div className="quiet small">{m.host_path}</div>}</td>
            <td>{m.type}</td>
            <td className="small">{m.used_by.map((u) => <div key={u.service + u.path}>{u.service}: <code>{u.path}</code> {u.read_only ? "(read only)" : ""}</div>)}</td>
            <td>{m.bytes != null ? bytes(m.bytes) : ""}</td>
            <td className="small bad-text">{m.warnings.join("; ")}</td>
            <td className="nowrap"><button onClick={() => setPick(m)}>Look into</button>{" "}
              {explorerFor(m) && <button onClick={() => { setPick(null); setBrowse(m); }}>Open in the explorer</button>}</td>
          </tr>))}</tbody>
      </table>
      {pick && <MountDetail m={pick} onClose={() => setPick(null)} />}
      {browse && (
        <div className="card mount-detail" aria-label={`Explorer: ${browse.source}`}>
          <h3>{browse.source} <span className="quiet small">through {explorerFor(browse).service}, at {explorerFor(browse).path}
            {explorerFor(browse).read_only ? " (read only there)" : ""}</span> <button className="linkish" onClick={() => setBrowse(null)}>Close</button></h3>
          <FileExplorer service={explorerFor(browse).service} start={explorerFor(browse).path} />
        </div>)}
    </section>
  );
}

// R3.5 (owner, 13 Nov 2026: Mounts uses the same explorer, read and write): a mount is opened in the file explorer of a
// container that uses it, at the folder where it is mounted; a container that has it writable first, never the
// operations helper (its own files are read only), so what can be written is written as in that container.
export function explorerFor(m) {
  const users = (m.used_by || []).filter((u) => !String(u.service).startsWith("ops"));
  return users.find((u) => !u.read_only) || users[0] || null;
}

function MountDetail({ m, onClose }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [folder, setFolder] = useState(null);
  const [path, setPath] = useState("/");
  const [q, setQ] = useState({ name: "", min_mb: "", days: "" });
  const [found, setFound] = useState(null);
  useEffect(() => { apiFetch(`/api/v1/admin/mounts/${m.id}`).then(setD).catch((e) => setErr(e.message)); }, [m.id]);
  const open = (p) => { setPath(p); apiFetch(`/api/v1/admin/mounts/${m.id}?path=${encodeURIComponent(p)}`).then(setFolder).catch((e) => setErr(e.message)); };
  const search = () => {
    const u = new URLSearchParams(Object.entries(q).filter(([, v]) => v));
    apiFetch(`/api/v1/admin/mounts/${m.id}/search?${u}`).then((x) => setFound(x.found)).catch((e) => setErr(e.message));
  };
  const list = (xs) => <ul className="small">{xs.map((f) => <li key={f.path}><code>{f.path}</code> · {bytes(f.bytes)} · {fmtDateTime(new Date(f.modified * 1000).toISOString())}</li>)}</ul>;
  return (
    <div className="card mount-detail" aria-label={`Mount ${m.source}`}>
      <h3>{m.source} <button className="linkish" onClick={onClose}>Close</button></h3>
      {err && <p className="status bad">{err}</p>}
      {!d ? !err && <p>Looking into it (read only)...</p> : <>
        <p>{d.files} files, {bytes(d.bytes)} · the disk under it: {bytes(d.disk_free)} free of {bytes(d.disk_total)}</p>
        {d.warnings.length > 0 && <p className="status bad">{d.warnings.join("; ")}</p>}
        <div className="cols3">
          <div><h4>Largest folders</h4><ul className="small">{d.folders.map((f) => <li key={f.path}><button className="linkish" onClick={() => open(f.path)}>{f.path}</button> {bytes(f.bytes)}</li>)}</ul></div>
          <div><h4>Largest files</h4>{list(d.largest)}</div>
          <div><h4>Newest</h4>{list(d.newest)}<h4>Oldest</h4>{list(d.oldest)}</div>
        </div></>}
      <h4>Open a folder (read only)</h4>
      <label>Folder <input value={path} onChange={(e) => setPath(e.target.value)} /></label> <button onClick={() => open(path)}>Open</button>
      {folder && <ul className="small">{folder.path !== "/" && <li><button className="linkish" onClick={() => open(folder.path.split("/").slice(0, -1).join("/") || "/")}>..</button></li>}
        {folder.entries.map((e) => <li key={e.name}>{e.dir ? <button className="linkish" onClick={() => open(`${folder.path.replace(/\/$/, "")}/${e.name}`)}>{e.name}/</button> : e.name} {!e.dir && bytes(e.bytes)}</li>)}</ul>}
      <h4>Search</h4>
      <label>Name has <input value={q.name} onChange={(e) => setQ({ ...q, name: e.target.value })} /></label>{" "}
      <label>At least MB <input value={q.min_mb} size="5" onChange={(e) => setQ({ ...q, min_mb: e.target.value })} /></label>{" "}
      <label>Changed in the last days <input value={q.days} size="4" onChange={(e) => setQ({ ...q, days: e.target.value })} /></label>{" "}
      <button onClick={search}>Search</button>
      {found && (found.length ? list(found) : <p className="quiet">Nothing found.</p>)}
    </div>
  );
}

// a red banner on every page for IT and Super Admins while a container is not working (R2.19)
export function ContainerAlertBanner() {
  const [open, setOpen] = useState([]);
  useEffect(() => {
    if (!can("system.operate")) return undefined;
    const look = () => apiFetch("/api/v1/admin/alerts").then((x) => setOpen(x.open || [])).catch(() => {});
    look();
    const t = setInterval(look, 60000);
    return () => clearInterval(t);
  }, []);
  if (!open.length) return null;
  const down = open.filter((o) => o.service !== "host");     // a container not working; the host running high is a warning
  const high = open.filter((o) => o.service === "host");
  return (
    <div className={`alert-banner ${down.length ? "bad" : "warn"}`} role="alert">
      {down.length > 0 && <>Not working: {down.map((o) => o.text || `${o.service} (${o.kind})`).join("; ")}. </>}
      {high.length > 0 && <>Needs attention: {high.map((o) => o.text).join("; ")}. </>}
      <a href="#/admin/containers">Containers</a> · <a href={high.length && !down.length ? "#/admin/hosts" : "#/admin/health"}>{high.length && !down.length ? "Hosts" : "Health"}</a>
    </div>
  );
}
