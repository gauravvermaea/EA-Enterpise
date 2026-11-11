// The project's ADM iteration (owner, 11 Nov 2026; D571-D574): near the top of the project page, which iteration of
// TOGAF's this cycle is, the phases it enables, and the history of changes. Anyone who can open the project may change
// it at any time (not while the project is read only); the phases left out are frozen, never deleted.
import { useState } from "react";
import { apiFetch } from "./auth";
import { fmtDateTime } from "./fmt";
import { refreshAll } from "./ModelViews";
import { Modal } from "./ModelOps";
import { PHASES, phaseName } from "./iterations";

export default function IterationControl({ p }) {
  const it = p.iteration;
  const [open, setOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  if (!it) return null;
  const may = it.may_change;
  const history = p.iteration_history || [];
  return (
    <div className="iteration-bar">
      {!it.chosen && may && <span className="iteration-ask">Which iteration is this?</span>}
      <span className="small">ADM iteration:</span>
      <span className={`chip${it.chosen ? " on" : ""}`} title={it.chosen ? `Chosen by ${it.by} on ${fmtDateTime(it.at)}` : "Not chosen yet: a Full cycle"}>
        {it.label}</span>
      {it.frozen_phases?.length > 0 && <span className="small quiet" title="Read only in this iteration: nothing is deleted">
        🔒 frozen: {it.frozen_phases.map(phaseName).join(", ")}</span>}
      {may && <button className="linkish small" onClick={() => setOpen(true)}>{it.chosen ? "Change…" : "Choose…"}</button>}
      {history.length > 0 && <button className="linkish small" aria-expanded={showHistory} onClick={() => setShowHistory((x) => !x)}>
        Iteration history ({history.length})</button>}
      {showHistory && <IterationHistory history={history} />}
      {open && <IterationDialog p={p} onClose={() => setOpen(false)} />}
    </div>
  );
}

function IterationHistory({ history }) {
  return (
    <table className="grid-table small iteration-history">
      <thead><tr><th>When</th><th>Who</th><th>Cycle</th><th>From</th><th>To</th><th>Note</th></tr></thead>
      <tbody>{history.map((h, i) => (
        <tr key={i}><td>{fmtDateTime(h.at)}</td><td>{h.by}</td><td>{h.cycle}</td><td>{h.from}</td><td><b>{h.to}</b></td><td>{h.note}</td></tr>
      ))}</tbody>
    </table>
  );
}

export function IterationDialog({ p, onClose }) {
  const it = p.iteration;
  const cat = p.iterations || [];
  const [code, setCode] = useState(it.chosen ? it.code : "full");
  const [custom, setCustom] = useState(() => new Set(it.code === "custom" ? it.phases : []));
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const phasesOf = (c) => (c === "custom" ? PHASES.filter((x) => custom.has(x)) : cat.find((x) => x.code === c)?.phases || []);
  const enabled = phasesOf(code);
  const frozen = PHASES.filter((x) => !enabled.includes(x));
  const bad = code === "custom" && !enabled.length;
  async function save() {
    setMsg("");
    try {
      const r = await apiFetch(`/api/v1/projects/${p.id}/iteration`, { method: "POST",
        body: JSON.stringify({ iteration: code, phases: code === "custom" ? enabled : undefined, note }) });
      setMsg(r.message); refreshAll(); setTimeout(onClose, 600);
    } catch (e) { setMsg(e.message); }
  }
  return (
    <Modal title="ADM iteration" onClose={onClose} actions={<>
      <button className="primary" disabled={bad} onClick={save}>Save</button><button onClick={onClose}>Cancel</button></>}>
      <div className="iteration-dialog">
      <p className="small">Which of TOGAF's iteration cycles this ADM cycle is. The phases it leaves out become read only (frozen);
        nothing is deleted, and choosing another iteration opens them again. Requirements Management stays open in every iteration.</p>
      <fieldset className="iteration-choices">
        <legend className="small">Iteration</legend>
        {cat.map((x) => (
          <label key={x.code} className="iteration-choice">
            <input type="radio" name="iteration" value={x.code} checked={code === x.code} onChange={() => setCode(x.code)} />
            <span><b>{x.name}</b>{x.phases && <> ({x.phases.map(phaseName).join(", ")})</>}<br /><span className="small quiet">{x.about}</span></span>
          </label>
        ))}
      </fieldset>
      {code === "custom" && <fieldset className="iteration-phases">
        <legend className="small">Phases enabled</legend>
        {PHASES.map((c) => (
          <label key={c} className="iteration-phase"><input type="checkbox" checked={custom.has(c)}
            onChange={(e) => setCustom((s) => { const n = new Set(s); if (e.target.checked) n.add(c); else n.delete(c); return n; })} />
            {c === "P" ? "Preliminary" : `Phase ${c}`}</label>
        ))}
        {bad && <p className="small error">Tick at least one phase.</p>}
      </fieldset>}
      <p className="small">{frozen.length ? <>Frozen (read only): <b>{frozen.map(phaseName).join(", ")}</b></> : "Every phase is open."}</p>
      <label className="small iteration-note">Note (optional)<input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)}
        placeholder="for example: B to D signed off, now planning the transition" /></label>
      {msg && <p className="small status">{msg}</p>}
      </div>
    </Modal>
  );
}
