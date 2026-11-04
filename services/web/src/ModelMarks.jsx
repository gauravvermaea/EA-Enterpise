// The marks every screen uses to say what a model is and whether it can be changed (D102):
//   ◆ Root metamodel   ▣ Reference model   ● Working model      (what kind of model it is)
//   📚 In the library  (root metamodels and reference models; later, models promoted to the library)
//   👁 Read-only       (shipped library models for everyone; other models where your roles allow no changes)
//   🔒 Locked          (a Model Admin has locked it: metamodel, content or maintenance)
// Used by the model list, the hierarchy tree, the model page, the model switcher and the library.
import { canOn } from "./auth";

export const KINDS = {
  template: { glyph: "◆", label: "Root metamodel", help: "A framework other models are built on (ArchiMate 4, or one built from scratch)" },
  reference: { glyph: "▣", label: "Reference model", help: "Ready-made industry content on a root metamodel" },
  project: { glyph: "●", label: "Project model", help: "A model people work on" },
};
const LOCK_NAMES = { metamodel: "metamodel locked", content: "content locked", maintenance: "locked for maintenance" };

export const inLibrary = (m) => m.kind === "template" || m.kind === "reference";

// Why a model is read-only, or null when you may change it
export function readOnlyWhy(m) {
  if (m.is_locked) return "Read-only for everyone: a shipped library model. Nobody can change it; a release adds a new version beside it.";
  if (!canOn(m.id, "model.content") && !canOn(m.id, "model.metamodel")) return "Read-only for you: your roles on this model allow no changes.";
  return null;
}

export function lockWhy(m) {
  if (!m.lock_level || m.lock_level === "none") return null;
  return `Locked (${LOCK_NAMES[m.lock_level] || m.lock_level})${m.locked_by ? ` by ${m.locked_by}` : ""}${m.lock_reason ? `: ${m.lock_reason}` : ""}`;
}

// The marks as plain text, for places that cannot hold markup (select options, SVG titles)
export function marksText(m) {
  return [inLibrary(m) && "📚", readOnlyWhy(m) && "👁", lockWhy(m) && "🔒"].filter(Boolean).join(" ");
}

export function KindMark({ m, big = false }) {
  const k = KINDS[m.kind] || KINDS.project;
  return <span className={`kind-mark ${m.kind}${big ? " big" : ""}`} title={`${k.label}: ${k.help}`} aria-label={k.label}>{k.glyph}</span>;
}

export function StatusMarks({ m }) {
  const ro = readOnlyWhy(m), lock = lockWhy(m);
  return (
    <span className="status-marks">
      {inLibrary(m) && <span title="In the model library" aria-label="In the library">📚</span>}
      {ro && <span title={ro} aria-label="Read-only">👁</span>}
      {lock && <span title={lock} aria-label="Locked">🔒</span>}
    </span>
  );
}

export function MarksLegend() {
  return (
    <div className="marks-legend quiet">
      {Object.entries(KINDS).map(([kind, k]) => (
        <span key={kind} title={k.help}><KindMark m={{ kind }} /> {k.label}</span>
      ))}
      <span title="Root metamodels and reference models everyone can start from">📚 In the library</span>
      <span title="Shipped library models for everyone; other models where your roles allow no changes">👁 Read-only</span>
      <span title="A Model Admin has locked the metamodel, the content, or the whole model for maintenance">🔒 Locked</span>
    </div>
  );
}
