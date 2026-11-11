// The start-up status (D255): EA Explorer starts in two tiers. The core (database, sign-in, the API, these screens) comes
// first; Reports, Documents, Diagrams (draw.io) and the sample data come after it, in the background. Everyone sees each
// in the header: green up, amber starting, red down, grey off. Click for the details; IT and Super Admins also get a
// link to every container (Administration > Containers, where each shows its tier and start-up state).
import { useEffect, useState } from "react";
import { apiFetch } from "./auth";

export const TONE = { up: "green", starting: "amber", down: "red", off: "grey" };
export const WORD = { up: "up", starting: "starting", down: "down", off: "off" };
const CORE = ["db", "setup", "proxy", "web", "keycloak", "api"];
const ONE_SHOT = ["setup", "reports-init"];

let last = null;                       // the latest answer, for screens that ask "is draw.io up?"
const listeners = new Set();

export function startupPart(key) {
  return last?.all?.find((p) => p.key === key) || null;
}

async function load(fresh) {
  try {
    last = await apiFetch(`/api/v1/startup${fresh ? "?fresh=1" : ""}`);
    listeners.forEach((f) => f(last));
  } catch { /* the header keeps the last answer */ }
  return last;
}

// read every 8 seconds while anything is starting or down, every minute once everything is up
export function useStartup() {
  const [data, setData] = useState(last);
  useEffect(() => {
    let stop = false;
    let timer = null;
    listeners.add(setData);
    const tick = async () => {
      const d = await load(false);
      if (!stop) timer = setTimeout(tick, d && d.overall === "up" ? 60000 : 8000);
    };
    tick();
    return () => { stop = true; clearTimeout(timer); listeners.delete(setData); };
  }, []);
  return data;
}

const partText = (p) => ((p.key === "later" || p.key === "packs") && p.status === "starting" && p.total ? `loading ${p.done} of ${p.total}` : WORD[p.status] || p.status);

export default function StartupStatus() {
  const data = useStartup();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return undefined;
    const close = () => setOpen(false);
    window.addEventListener("click", close);
    window.addEventListener("hashchange", close);
    return () => { window.removeEventListener("click", close); window.removeEventListener("hashchange", close); };
  }, [open]);
  if (!data) return null;
  const parts = data.all || [];
  const waiting = parts.filter((p) => p.status === "starting" || p.status === "down");
  const title = parts.map((p) => `${p.name}: ${partText(p)}${p.detail ? ` (${p.detail})` : ""}`).join("\n");
  return (
    <div className="startup" onClick={(e) => e.stopPropagation()}>
      <button className={`startup-btn ${TONE[data.overall] || "grey"}`} onClick={() => setOpen((o) => !o)} title={title}
        aria-expanded={open}>
        {waiting.length === 0
          ? <><span className="dot green" /> All up</>
          : waiting.length === 1
            ? <span className="startup-chip"><span className={`dot ${TONE[waiting[0].status]}`} />{waiting[0].name} <b>{partText(waiting[0])}</b></span>
            // more than one: one short chip so it stays on the top row (owner, 11 Nov 2026); the list is in the pop-up and the tooltip
            : <span className="startup-chip"><span className={`dot ${TONE[data.overall] || "amber"}`} /><b>{waiting.length} starting</b></span>}
      </button>
      {open && (
        <div className="startup-pop" role="dialog" aria-label="Start-up status">
          <p className="small quiet">EA Explorer starts the core first (sign-in, the API, these screens); these start after it,
            in the background, and turn green when they are up.</p>
          <table className="grid-table startup-table">
            <tbody>
              {parts.map((p) => (
                <tr key={p.key}>
                  <td><span className={`rag ${TONE[p.status] === "grey" ? "off" : TONE[p.status]}`}>{partText(p)}</span></td>
                  <td><b>{p.name}</b><div className="small quiet">{p.product}</div></td>
                  <td className="small">{p.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row-gap">
            <button onClick={() => load(true)}>↻ Check again</button>
            {data.admin && <a href="#/admin/containers" onClick={() => setOpen(false)}>Every container →</a>}
          </div>
        </div>
      )}
    </div>
  );
}

// a container's start-up state, from its Docker state and health (Administration > Containers)
export function containerStartup(c) {
  const state = (c.state || "").toLowerCase();
  const status = (c.status || "").toLowerCase();
  const health = (c.health || "").toLowerCase();
  if (ONE_SHOT.includes(c.service)) {
    if (state === "exited") return (c.exit_code ?? (status.includes("exited (0)") ? 0 : 1)) === 0 ? "up" : "down";
    return "starting";
  }
  if (state === "running") {
    if (health === "starting" || status.includes("health: starting")) return "starting";
    if (health === "unhealthy" || status.includes("unhealthy")) return "down";
    return "up";
  }
  if (state === "created" || state === "restarting") return "starting";
  if (state === "exited" && (c.exit_code === 0 || status.includes("exited (0)"))) return "off";   // stopped (switched off)
  return "down";
}

export const containerTier = (c) => (CORE.includes(c.service) ? "first" : "after");

export function StartupCell({ c }) {
  const s = containerStartup(c);
  const tier = containerTier(c);
  return (
    <span className="nowrap" title={tier === "first" ? "Starts first: needed to sign in and work" : "Starts after the core, in the background"}>
      <span className={`rag ${TONE[s] === "grey" ? "off" : TONE[s]}`}>{WORD[s]}</span>
      <span className="small quiet"> {tier === "first" ? "1st" : "2nd"}</span>
    </span>
  );
}

// one line with every part (Administration > Containers)
export function StartupLine() {
  const data = useStartup();
  if (!data) return null;
  return (
    <p className="row-gap startup-line"><b>Start-up:</b> <span className="rag green">core up</span>
      {(data.all || []).map((p) => <span key={p.key} className={`rag ${TONE[p.status] === "grey" ? "off" : TONE[p.status]}`} title={p.detail}>{p.name}: {partText(p)}</span>)}
    </p>
  );
}
