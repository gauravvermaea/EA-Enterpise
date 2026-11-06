// The marks every screen uses to say what a model is and whether it can be changed (D102):
//   ◆ Root metamodel   ▣ Reference model   ● Working model      (what kind of model it is)
//   📚 In the library  (root metamodels and reference models; later, models promoted to the library)
//   👁 Read-only       (shipped library models for everyone; other models where your roles allow no changes)
//   🔒 Locked          (a Model Admin has locked it: metamodel, content or maintenance)
// Used by the model list, the hierarchy tree, the model page, the model switcher and the library.
import { canOn } from "./auth";
import { ModelIcon } from "./ModelIcon";

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

// the kind mark, with the model's icon before it when it has one (D247)
export function KindMark({ m, big = false, noIcon = false }) {
  const k = KINDS[m.kind] || KINDS.project;
  const mark = <span className={`kind-mark ${m.kind}${big ? " big" : ""}`} title={`${k.label}: ${k.help}`} aria-label={k.label}>{k.glyph}</span>;
  if (noIcon || !m.icon) return mark;
  return <span className={`model-marks${big ? " big" : ""}`}><ModelIcon m={m} size={big ? 34 : 18} />{mark}</span>;
}

export function StatusMarks({ m }) {
  const ro = readOnlyWhy(m), lock = lockWhy(m);
  return (
    <span className="status-marks">
      {inLibrary(m) && m.library_state !== "building" && m.library_state !== "withdrawn" && !m.is_draft && <span title="In the model library" aria-label="In the library">📚</span>}
      {(m.is_draft || m.library_state === "building") && <span title="Draft: not published yet; only its Model Admins create models from it" aria-label="Draft">📝</span>}
      {m.library_state === "withdrawn" && <span title="Withdrawn from the library: no new models start from it" aria-label="Withdrawn">⛔</span>}
      {m.copy_state === "copying" && <span title="Its content is being copied in the background" aria-label="Copying">⏳</span>}
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
      <span title="Not published yet: only its Model Admins create models from it">📝 Draft</span>
    </div>
  );
}

// An uncommitted change of mine (phase 8, D165): only I see it until it is committed (the Changes tab)
const PENDING = { created: "new", changed: "changed", deleted: "deleted" };
export function PendingMark({ kind, model }) {
  if (!kind) return null;
  return (
    <a className="pending-mark" href={model ? `#/metamodel/${model}/changes` : undefined}
      title="Your uncommitted change: only you see it until it is committed (Changes tab)">✎ {PENDING[kind] || kind}, uncommitted</a>
  );
}

// Above a page holding my uncommitted changes
export function PendingBanner({ count, model }) {
  if (!count) return null;
  return (
    <div className="lock-banner pending-banner">
      You have {count} uncommitted change{count === 1 ? "" : "s"} in this model: you see them here, nobody else does until they are
      committed. <a href={`#/metamodel/${model}/changes`}>Changes tab</a>: commit, ask for a commit, or discard.
    </div>
  );
}

// a model's state in words with an icon (owner, 6 Nov 2026): what it is now, for the Models page (list and tiles) and
// Administration > Quality
export const MODEL_STATES = {
  archived: ["🗄", "archived", "Archived (retired): kept for history; data quality never measures it"],
  readonly: ["👁", "read-only", "Read-only for everyone: a shipped library model or locked by the installer"],
  content: ["❄", "frozen", "Content locked (frozen): nobody changes its content"],
  maintenance: ["🛠", "maintenance", "Locked for maintenance"],
  metamodel: ["🔒", "metamodel locked", "Its metamodel is locked; its content can still change"],
  draft: ["📝", "draft", "A draft: only its Model Admins create models from it until it is published"],
  library: ["📚", "in the library", "In the model library: everyone may start a model from it"],
  active: ["🟢", "active", "Active: people work on it"],
};
export function modelStateOf(m) {
  if (m.lifecycle && m.lifecycle !== "active") return "archived";
  if (m.lock_level && MODEL_STATES[m.lock_level]) return m.lock_level;
  if (m.is_draft || m.library_state === "building") return "draft";
  if (m.is_locked) return inLibrary(m) ? "library" : "readonly";
  if (inLibrary(m) && m.library_state !== "withdrawn") return "library";
  return "active";
}
export function ModelStateBadge({ m }) {
  const k = modelStateOf(m);
  const [icon, label, help] = MODEL_STATES[k];
  const why = [help, m.locked_by && `by ${m.locked_by}`, m.lock_reason].filter(Boolean).join(" · ");
  return <span className={`model-state ${k}`} title={why}><span aria-hidden="true">{icon}</span> {label}</span>;
}
