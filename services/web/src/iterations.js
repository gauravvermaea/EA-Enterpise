// ADM iteration types on a project (owner, 11 Nov 2026; D571-D574): the twin of services/api/eax/iterations.py.
// A project's current cycle runs as one of TOGAF's iteration cycles, which decides which phases are enabled; the others
// are frozen (read only, never hidden or deleted). Requirements Management (RM) and "across the cycle" (X) stay enabled.
export const PHASES = ["P", "A", "B", "C", "D", "E", "F", "G", "H"];
const FOLLOWS = { "C-D": "C", "C-A": "C" };
const ALWAYS = new Set(["RM", "X", ""]);

export const basePhase = (code) => FOLLOWS[code] || code || "";
export const phaseName = (c) => (c === "P" ? "Preliminary" : c);

// the enabled phases of an iteration object from the API ({code, phases}); none: a Full cycle
export function phaseEnabled(it, code) {
  const ph = basePhase(code);
  if (ALWAYS.has(ph) || !PHASES.includes(ph)) return true;
  return !it || (it.phases || PHASES).includes(ph);
}

export const projectPhaseEnabled = (p, code) => phaseEnabled(p?.iteration, code);

export function frozenNote(p, code) {
  const ph = basePhase(code);
  const name = ph === "P" ? "The Preliminary phase" : `Phase ${ph}`;
  return `${name} isn't part of this ${p?.iteration?.name || "iteration"}. Change the iteration to work on it.`;
}

// a project as seen while a frozen phase is open: everything read only, nothing hidden
export function readOnlyIn(p, code) {
  return projectPhaseEnabled(p, code) ? p : { ...p, may_contribute: false, may_admin: false, may_undo: false, frozen: true, phase_frozen: true };
}

export function iterationLabel(code, phases, catalogue) {
  const it = (catalogue || []).find((x) => x.code === code);
  return `${it?.name || code} (${(phases || []).map(phaseName).join(", ")})`;
}
