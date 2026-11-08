// Phase 4: creating, copying, moving, packaging and retiring models, and metamodel drafts (D108, D115-D121).
//   NewModelDialog     create a project, root or library model, empty or from an existing model
//   CreateFromButton   "Create a model from this" on a model page and in the library
//   DownloadButtons    the model as one package: zip (JSON + CSV) or Excel
//   UploadWizard       choose a package, see what it holds and where it can go, rename it, upload it
//   ModelActions       the model page's Actions menu: copy, download, move framework, archive, delete,
//                      publish / withdraw / restore / promote (Library Admins)
//   CopyBanner         "copying the content..." while the background job runs
//   Drafts, DraftPage  metamodel drafts (made by AI through MCP, or uploaded): review, trim, apply, reject
// The server decides (and the database enforces) what is allowed; the screens only offer it.
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { apiDownload, apiFetch, apiUpload, can, canOn, myInfo, needsRole } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { fmtDateTime } from "./fmt";
import { runTask, startDownload, trackTask, useTask } from "./tasks";
import { IconPicker, saveIcon } from "./ModelIcon";

const go = (path) => { window.location.hash = path; };
const post = (path, body, method = "POST") => apiFetch(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
// Root, the top of the hierarchy every root metamodel is built on
// Who may create something (the server and the database check again)
export const mayCreate = () => can("models.create") || can("library.curate");
const CREATE_ROLES = ["model-creator", "library-admin"];
export const isTop = (m) => m.is_top || (m.kind === "template" && !m.source_model_id);
const label = (m) => `${m.name}${m.version_label ? ` ${m.version_label}` : ""}`;

export function Modal({ title, onClose, children, actions, wide }) {
  useEffect(() => {
    const esc = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  // drawn on the page itself, so the styles of wherever the button sits do not reach the dialog
  return createPortal(
    <div className="ed-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="ed-dialog" role="dialog" aria-modal="true" aria-label={title} style={wide ? { width: "min(900px, 100%)" } : undefined}>
        <div className="ed-head"><h2>{title}</h2><button className="linkish" onClick={onClose} aria-label="Close">✕</button></div>
        {children}
        {actions && <div className="ed-actions">{actions}</div>}
      </div>
    </div>,
    document.body,
  );
}

// A form field; `tip` is the longer explanation shown when the mouse rests on the label or the ⓘ
export function Field({ label: text, hint, tip, children }) {
  return (
    <label className="ed-field">
      <span title={tip}>{text} {tip && <span className="tip" aria-label={tip}>ⓘ</span>} {hint && <span className="quiet">{hint}</span>}</span>
      {children}
    </label>
  );
}

// ------------------------------------------------------------------ create a model
const COPIES = [
  ["metamodel", "Without data: the metamodel only", "An empty model on the same metamodel"],
  ["content", "With the data", "Every entity, value and relationship as they are now; each keeps its source's guid for merging back and comparing"],
  ["history", "Deep copy: the data with its full history", "As above, and every entity keeps its whole history from the source, even if the source changes or is deleted later"],
];

export function NewModelDialog({ from, onClose, preset = {}, admin = false }) {
  const { data: models } = useApi("/api/v1/models?archived=false");
  const curator = can("library.curate");
  const creator = can("models.create");
  const fromProjectAdmin = from && from.kind === "project" && canOn(from.id, "model.derive");
  // [code, label, what it is, allowed, why not]: every kind is shown; those your roles do not give are greyed out
  const kinds = [
    ["project", "Project model", "A working model people fill in", creator || curator || fromProjectAdmin,
      needsRole(["model-creator"]) + (from && from.kind === "project" ? ` (or Model Admin of ${from.name}, for a child of it)` : "")],
    ["root", "Root metamodel", "A framework of its own: a metamodel with no content", creator || curator, needsRole(["model-creator", "library-admin"])],
    ["library", "Library model", "A reference model for the library, with ready-made content", curator, needsRole(["library-admin"])],
  ];
  const firstAllowed = kinds.find((k) => k[3]);
  const [kind, setKind] = useState(firstAllowed ? firstAllowed[0] : "project");
  const kindAllowed = !!kinds.find((k) => k[0] === kind)?.[3];
  const [name, setName] = useState(from ? `Copy of ${from.name}` : "");
  const [source, setSource] = useState(from?.id || "");
  const [copy, setCopy] = useState(preset.copy || (from && from.kind !== "template" ? "content" : "metamodel"));
  const [link, setLink] = useState(preset.link || (!creator && !curator && fromProjectAdmin ? "child" : "independent"));   // project sources: "child" (merges back) or "independent"
  const [version, setVersion] = useState(kind === "project" ? "" : "1.0");
  const [industry, setIndustry] = useState(from?.industry || "");
  const [icon, setIcon] = useState("");          // D247: every new model has an icon; empty until picked: the kind's
  const [iconFile, setIconFile] = useState(null);
  const [description, setDescription] = useState("");
  const [framework, setFramework] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const all = models || [];
  const src = all.find((m) => m.id === source) || (from && from.id === source ? from : null);
  const roots = all.filter((m) => m.kind === "template");
  const sources = kind === "root" ? roots : all;
  const groups = useMemo(() => [
    ["Root metamodels", sources.filter((m) => m.kind === "template")],
    ["Library models", sources.filter((m) => m.kind === "reference")],
    ["Your models", sources.filter((m) => m.kind === "project")],
  ].filter(([, list]) => list.length), [sources]);
  const holdsContent = src && src.kind !== "template";
  const projectSource = src && src.kind === "project";
  const mayChild = projectSource && canOn(src.id, "model.derive");
  const child = kind === "project" && projectSource && link === "child";

  const mayIndependent = creator || curator;
  const createWhy = !kindAllowed ? kinds.find((k) => k[0] === kind)[4]
    : kind === "project" && link === "independent" && !mayIndependent ? `An independent model: ${needsRole(["model-creator"])}`
    : "";

  const iconName = icon || { root: "layers", library: "bank", project: "building" }[kind] || "building";
  async function create() {
    setBusy(true); setError("");
    try {
      const out = await post("/api/v1/models", {
        kind, name: name.trim(), source: source || null, parent: child ? source : null,
        copy: holdsContent && kind !== "root" ? copy : "metamodel", version_label: version, industry, description,
        framework: kind === "root" ? framework : "", icon: iconName,
      });
      if (iconFile) await saveIcon(out.model.id, null, iconFile).catch(() => {});   // the model exists; an upload failing leaves the library icon
      refreshAll();
      onClose();
      go(`/${admin ? "model-admin" : "metamodel"}/${out.model.id}`);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return (
    <Modal title={from ? `Create a model from ${from.name}` : "New model"} onClose={onClose}
      actions={<>
        <button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy || !!createWhy || !name.trim() || (kind !== "root" && !source)} onClick={create}
          title={createWhy || (!name.trim() ? "Give it a name" : kind !== "root" && !source ? "Choose the model to start from" : "Create the model and open it")}>
          {busy ? "Creating..." : "Create"}</button>
      </>}>
      <div className="ed-form">
        <Field label="What to create" tip="Project model: a working model people fill in. Root metamodel: a framework of its own (types, attributes, rules) with no content. Library model: ready-made content everyone can start from (Library Admins).">
          <div className="seg small">
            {kinds.map(([k, l, hint, ok, why]) => (
              <button key={k} type="button" title={ok ? hint : `${hint}. ${why}`} disabled={!ok} className={kind === k ? "on" : ""}
                onClick={() => { setKind(k); if (k === "root") setCopy("metamodel"); setVersion(k === "project" ? "" : version || "1.0"); }}>{l}</button>
            ))}
          </div>
          <span className="quiet">{kinds.find(([k]) => k === kind)?.[2]}
            {kind === "library" && ". It starts as not yet published until a Library Admin publishes it."}</span>
          {createWhy && <span className="status bad">{createWhy}</span>}
        </Field>
        <Field label="Name" tip="Shown everywhere the model is listed. It must not be the same as another model's name."><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
        <Field label="Start from" hint={kind === "root" ? "(empty: a new framework from scratch, under Root)" : "(the metamodel it is built on)"}
          tip="The new model gets a copy of this model's metamodel, and sits under it in the hierarchy. Choose a library model or one of your own models to copy its content too.">
          <select value={source} onChange={(e) => {
            setSource(e.target.value);
            const s = all.find((m) => m.id === e.target.value);
            if (s && s.kind === "template") setCopy("metamodel");
          }}>
            {kind === "root" ? <option value="">Nothing: start empty under Root</option> : <option value="">Choose a model...</option>}
            {from && !all.some((m) => m.id === from.id) && <option value={from.id}>{label(from)}</option>}
            {groups.map(([g, list]) => (
              <optgroup key={g} label={g}>
                {list.map((m) => {
                  const off = m.is_draft && !ownsDraft(m);
                  return <option key={m.id} value={m.id} disabled={off} title={off ? draftWhy(m) : undefined}>
                    {label(m)}{isTop(m) ? " (the top of the hierarchy)" : ""}{m.is_draft ? " · draft" : ""}</option>;
                })}
              </optgroup>
            ))}
          </select>
        </Field>
        {holdsContent && kind !== "root" && (
          <Field label="Copy" tip="What comes across from the model you start from. The copy is independent: changes to either model do not reach the other.">
            <div className="ed-radio">
              {COPIES.map(([k, l, hint]) => (
                <label key={k} className="lock-opt" title={hint}>
                  <input type="radio" name="copy" checked={copy === k} onChange={() => setCopy(k)} />
                  <span><b>{l}</b><br /><span className="quiet">{hint}</span></span>
                </label>
              ))}
            </div>
            {copy !== "metamodel" && src && <span className="quiet">Large models are copied in the background: the new model opens at once and shows when the copy is done
              ({src.entity_count} entities, {src.relationship_count} relationships).</span>}
          </Field>
        )}
        {kind === "project" && projectSource && (
          <Field label={`Relationship to ${src.name}`}
            tip="A child model stays linked to its parent: its work merges back, and metamodel changes and attribute updates flow down from the parent. An independent model is a separate copy: it never merges back, but the two can still be compared.">
            <div className="ed-radio">
              <label className="lock-opt" title={mayIndependent ? "A separate copy. Nothing flows between the two models; you can compare them later (gap analysis)." : needsRole(["model-creator"])}>
                <input type="radio" name="link" checked={link === "independent"} disabled={!mayIndependent} onChange={() => setLink("independent")} />
                <span><b>Independent model</b><br /><span className="quiet">A separate copy that never merges back. It can be compared with {src.name}.</span></span>
              </label>
              <label className="lock-opt" title={mayChild ? "Stays linked to the parent: merges back, and receives the parent's metamodel changes and attribute updates."
                : `A child model: ${needsRole("model-admin", src.name)}`}>
                <input type="radio" name="link" checked={link === "child"} disabled={!mayChild} onChange={() => setLink("child")} />
                <span><b>Child model</b>{!mayChild && <span className="quiet"> (needs the Model Admin role on {src.name})</span>}<br />
                  <span className="quiet">Stays linked to {src.name}: its work merges back into the parent, and the parent's metamodel
                    changes and attribute updates flow down to it.</span></span>
              </label>
            </div>
          </Field>
        )}
        {kind === "project" && src && !projectSource && (
          <p className="quiet small-note" style={{ margin: 0 }}>Built on {src.name}: an independent model on its metamodel. It never merges back into a
            {src.kind === "template" ? " root metamodel" : " library model"}; to take a newer framework version, use Model admin &gt; Wizards &gt; Upgrade to another framework.</p>
        )}
        {kind === "root" && <Field label="Framework" hint="(for example ArchiMate, or your own)" tip="The name of the metamodel, shown beside every model built on this root."><input value={framework} onChange={(e) => setFramework(e.target.value)} /></Field>}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Version" tip="Your own label, for example 1.0 or 2026. Library models and roots are matched by name and version when packages are uploaded."><input value={version} onChange={(e) => setVersion(e.target.value)} /></Field>
          <Field label="Industry" tip="Used to group and search models and library models."><input value={industry} onChange={(e) => setIndustry(e.target.value)} /></Field>
        </div>
        <Field label="Description" tip="What the model is for and who looks after it."><textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <Field label="Icon" tip="Shown wherever the model is named. Pick one from the library or upload your own (for this model only); its Model Admins can change it later.">
          <IconPicker value={iconName} onChange={setIcon} file={iconFile} onFile={setIconFile} kind={kind === "root" ? "template" : kind === "library" ? "reference" : "project"} /></Field>
        <p className="quiet small-note">You become the new model's Model Admin. It starts as a <b>draft</b>: you and the people you give roles
          work on it, and nobody else can create a model from it until you publish it (Model admin &gt; Wizards &gt; Request publishing).</p>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

export const ownsDraft = (m) => canOn(m.id, "model.lock") || (m.kind !== "project" && can("library.curate"));
export const mayCreateFrom = (m) => (!m.is_draft || ownsDraft(m)) && (mayCreate() || (m.kind === "project" && canOn(m.id, "model.derive")));
export const draftWhy = (m) => `${m.name} is a draft: only its Model Admins create models from it until it is published`;

export function CreateFromButton({ m, className = "" }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className={className} onClick={() => setOpen(true)} disabled={!mayCreateFrom(m)}
        title={m.is_draft && !ownsDraft(m) ? draftWhy(m) : !mayCreateFrom(m) ? `Creating a model: ${needsRole(m.kind === "project" ? ["model-creator", "library-admin"] : CREATE_ROLES)}${m.kind === "project" ? ` (or Model Admin of ${m.name}, for a child of it)` : ""}`
          : m.kind === "project" ? "A child model (merges back into this one) or an independent copy (compared, never merged)" : "A new model built on this one's metamodel, with or without its content"}>Create a model from this</button>
      {open && <NewModelDialog from={m} onClose={() => setOpen(false)} />}
    </>
  );
}

export function NewModelButton({ admin = false }) {
  const [open, setOpen] = useState(false);
  const ok = mayCreate();
  return (
    <>
      <button className="primary" disabled={!ok} onClick={() => setOpen(true)}
        title={ok ? "A project model, a root metamodel or (Library Admins) a library model, empty or from an existing model" : `Creating a model: ${needsRole(CREATE_ROLES)}`}>+ New model</button>
      {open && <NewModelDialog admin={admin} onClose={() => setOpen(false)} />}
    </>
  );
}

// ------------------------------------------------------------------ download a package
const CONTENT_LEVELS = [
  ["metamodel", "Without data: the metamodel only", "Layers, types, attributes, pick lists, relationship types, rules"],
  ["content", "With the data", "The metamodel and every entity, value and relationship as they are now"],
  ["history", "Deep: the data with its full history", "As above, plus every change to every entity and the metamodel's version history: readable sheets, and loaded again on upload"],
];

export function DownloadDialog({ m, onClose }) {
  const [format, setFormat] = useState("xlsx");
  const [content, setContent] = useState(m.kind === "template" ? "metamodel" : "content");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function get() {
    setBusy(true); setError("");
    try {
      // D273: made in the background; downloaded when ready (also from the Tasks tab on the right for 24 hours)
      await startDownload(`/api/v1/models/${m.id}/package?format=${format}&content=${content}`, undefined, `#/metamodel/${m.id}`);
      onClose();
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Download ${m.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy} onClick={get}>{busy ? "Starting..." : "Download"}</button></>}>
      <div className="ed-form">
        <Field label="Format" tip="Both upload again, here or in another EA Explorer. Excel is easiest to read and change; the zip holds JSON and CSV files.">
          <div className="seg small">
            <button type="button" className={format === "xlsx" ? "on" : ""} onClick={() => setFormat("xlsx")}>Excel workbook</button>
            <button type="button" className={format === "zip" ? "on" : ""} onClick={() => setFormat("zip")}>Zip (JSON and CSV)</button>
          </div>
        </Field>
        <Field label="What to include" tip="Without data: to start a new model on the same metamodel. With the data: a working copy. Deep: also every change made so far, for a faithful copy you can compare or merge later.">
          <div className="ed-radio">
            {CONTENT_LEVELS.map(([k, l, hint]) => {
              const off = m.kind === "template" && k !== "metamodel";
              return (
                <label key={k} className="lock-opt" title={off ? "A root metamodel has no data" : hint}>
                  <input type="radio" name="content" checked={content === k} disabled={off} onChange={() => setContent(k)} />
                  <span><b>{l}</b><br /><span className="quiet">{hint}</span></span>
                </label>
              );
            })}
          </div>
        </Field>
        {content === "history" && format === "xlsx" && <p className="quiet small-note">Sheets Metamodel versions, Metamodel changes and Change history are
          for reading; History data is what an upload loads again (leave it as it is).</p>}
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

export function DownloadButtons({ m }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)} title="The model as one package, Excel or zip: without data, with the data, or deep with its full history">⬇ Download...</button>
      {open && <DownloadDialog m={m} onClose={() => setOpen(false)} />}
    </>
  );
}

// ------------------------------------------------------------------ upload a package
export function UploadButton({ label: text = "⬆ Upload a model", className = "" }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className={className} onClick={() => setOpen(true)} disabled={!mayCreate()}
        title={mayCreate() ? "A package (zip or Excel) downloaded from this or another EA Explorer, perhaps renamed or changed" : `Uploading a model: ${needsRole(CREATE_ROLES)}`}>{text}</button>
      {open && <UploadWizard onClose={() => setOpen(false)} />}
    </>
  );
}

export function UploadWizard({ onClose }) {
  const curator = can("library.curate");
  const [file, setFile] = useState(null);
  const [info, setInfo] = useState(null);
  const [placement, setPlacement] = useState("own_root");   // "own_root" or "root:<id>"
  const [name, setName] = useState("");
  const [asKind, setAsKind] = useState(curator ? "library" : "project");
  const [load, setLoad] = useState("content");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showDiff, setShowDiff] = useState(false);

  async function analyse(f) {
    setFile(f); setInfo(null); setError("");
    if (!f) return;
    setBusy(true);
    const form = new FormData();
    form.append("file", f);
    try {
      const out = await runTask(apiUpload("/api/v1/packages/analyse", form));
      setInfo(out);
      const mm = out.manifest?.model || {};
      setName(mm.name || f.name.replace(/\.(zip|xlsx)$/i, ""));
      const best = out.placements.find((p) => p.code === "root" && p.matches);
      setPlacement(best ? `root:${best.root_id}` : "own_root");
      if (mm.kind === "project" || !curator) setAsKind("project"); else setAsKind("library");
      setLoad(out.counts.history_rows ? "history" : out.counts.entities ? "content" : "metamodel");
    } catch (e) { setError(e.message); }
    setBusy(false);
  }

  async function upload() {
    setBusy(true); setError("");
    const form = new FormData();
    form.append("file", file);
    form.append("placement", placement === "own_root" ? "own_root" : "root");
    if (placement !== "own_root") form.append("root", placement.slice(5));
    form.append("name", name.trim());
    if (!isRoot) { form.append("as_kind", asKind); form.append("content", load); }
    try {
      const from = window.location.hash;
      const out = await runTask(apiUpload("/api/v1/packages/import", form));
      refreshAll();
      onClose();
      if (window.location.hash === from) go(`/metamodel/${out.model.id}`);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  const mm = info?.manifest?.model || {};
  const isRoot = mm.kind === "template";
  const placeKey = (p) => (p.code === "own_root" ? "own_root" : `root:${p.root_id}`);
  const chosen = info?.placements.find((p) => placeKey(p) === placement);
  const canUpload = info && !info.errors && name.trim() && chosen && chosen.matches;
  const findings = info?.findings || [];

  return (
    <Modal title="Upload a model" wide onClose={onClose}
      actions={<>
        <button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy || !canUpload} onClick={upload}
          title={!info ? "Choose a package first" : info.errors ? "The package has errors" : !chosen?.matches ? "Choose where it goes" : "Upload the package as a new model"}>{busy && info ? "Uploading..." : "Upload"}</button>
      </>}>
      <div className="ed-form">
        <Field label="1. The package" hint="(a .zip or .xlsx downloaded from a model's Actions, or from the library)"
          tip="The package is read and checked first; nothing is uploaded until you press Upload.">
          <input type="file" accept=".zip,.xlsx" onChange={(e) => analyse(e.target.files?.[0] || null)} />
        </Field>
        {busy && !info && <p>Reading the package...</p>}
        {info && (
          <>
            <div className="impact" style={{ margin: 0 }}>
              <b>{mm.name}</b> {mm.version && <span className="quiet">version {mm.version}</span>} · {({ template: "root metamodel", reference: "library model", project: "project model" })[mm.kind] || mm.kind}
              {info.manifest.built_on && <> · built on <b>{info.manifest.built_on.name} {info.manifest.built_on.version}</b></>}
              <br />{info.counts.entity_types} entity types · {info.counts.entities} entities · {info.counts.relationships} relationships
              {info.manifest.exported_from && <span className="quiet"> · from {info.manifest.exported_from}</span>}
              {info.manifest.exported_at && <span className="quiet"> on {fmtDateTime(info.manifest.exported_at)}</span>}
            </div>
            {findings.length > 0 && (
              <div className={info.errors ? "removals" : "impact"} style={{ margin: 0 }}>
                <b>{info.errors ? `${info.errors} error${info.errors > 1 ? "s" : ""}: fix the package and choose it again` : "Notes"}</b>
                <ul className="impact-list">{findings.slice(0, 50).map((f, i) => <li key={i}>{f.level === "error" ? "✖" : "⚠"} {f.where}: {f.message}</li>)}</ul>
              </div>
            )}
            {!isRoot && (
              <Field label="2. Where it goes" hint={`(${info.placements.length} choices)`}
                tip="A model sits under a root metamodel. It can go under any root whose metamodel matches the package's completely (the one the package names comes first), or under Root, where the package's metamodel becomes a new root metamodel of its own with all its values.">
                <select value={placement} onChange={(e) => { setPlacement(e.target.value); setShowDiff(false); }}>
                  {info.placements.filter((p) => p.code === "root").length > 0 && (
                    <optgroup label="Under a root metamodel">
                      {info.placements.filter((p) => p.code === "root").map((p) => (
                        <option key={placeKey(p)} value={placeKey(p)} disabled={!p.matches}
                          title={p.matches ? "Matches the package completely" : `${p.difference_count} differences`}>
                          {p.root}{p.named ? " (named in the package)" : ""} · {p.matches ? "matches completely" : `differs in ${p.difference_count} places`}
                        </option>
                      ))}
                    </optgroup>
                  )}
                  <optgroup label="A new root">
                    <option value="own_root">Under Root, as a root of its own (its metamodel with all its values)</option>
                  </optgroup>
                </select>
                {info.missing && <span className="quiet">{info.missing}</span>}
                {chosen && chosen.code === "root" && (
                  <span className={chosen.matches ? "all-pass" : "status bad"}>
                    {chosen.matches ? `Matches ${chosen.root} completely: the model goes under it.` : `Differs from ${chosen.root} in ${chosen.difference_count} places.`}
                  </span>
                )}
                {chosen && chosen.code === "own_root" && (
                  <span className="quiet">A new root metamodel "{name.trim() || mm.name} metamodel" is made under Root, and the model goes under it.</span>
                )}
                {info.placements.some((p) => p.code === "root" && !p.matches) && (
                  <button className="linkish" type="button" style={{ justifySelf: "start" }} title="Why a root metamodel cannot take this package"
                    onClick={() => setShowDiff(!showDiff)}>{showDiff ? "Hide" : "Show"} how the other root metamodels differ</button>
                )}
                {showDiff && info.placements.filter((p) => p.code === "root" && !p.matches).map((p) => (
                  <details key={p.root_id} className="compare">
                    <summary><b>{p.root}</b> · {p.difference_count} differences</summary>
                    <Differences list={p.differences} />
                  </details>
                ))}
              </Field>
            )}
            {isRoot && <p className="quiet">A root metamodel: it is uploaded as a new root metamodel under Root.</p>}
            <Field label={isRoot ? "2. Name" : "3. Name"} hint="(change it to upload a second copy beside the first)"
              tip="The name the uploaded model gets here. Change it to upload the same package again for testing: each upload is a separate model.">
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            {!isRoot && (
              <Field label="Load" tip="What to bring in from the package. A deep package carries every entity's history; loading it keeps that history in the new model.">
                <div className="ed-radio">
                  {[["metamodel", "Without data: the metamodel only", true],
                    ["content", `With the data (${info.counts.entities} entities, ${info.counts.relationships} relationships)`, info.counts.entities > 0],
                    ["history", `With the data and its history (${info.counts.history_rows} history rows)`, info.counts.history_rows > 0]].map(([k, l, ok]) => (
                    <label key={k} className="lock-opt" title={ok ? "" : "The package does not have this"}>
                      <input type="radio" name="load" checked={load === k} disabled={!ok} onChange={() => setLoad(k)} />
                      <span>{l}{!ok && <span className="quiet"> · not in this package</span>}</span>
                    </label>
                  ))}
                </div>
              </Field>
            )}
            {!isRoot && (
              <Field label="Upload it as" tip="A library model is published in the library for everyone to start from (Library Admins). A project model is a working model of your own.">
                <select value={asKind} onChange={(e) => setAsKind(e.target.value)}>
                  <option value="library" disabled={!curator}>A library model (published in the library){curator ? "" : " · needs the Library Admin role"}</option>
                  <option value="project">A project model (you become its Model Admin)</option>
                </select>
              </Field>
            )}
          </>
        )}
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

const CHANGE = { added: "Added", removed: "Removed", changed: "Changed" };
const SECTION = { layers: "Layer", pick_lists: "Pick list", attributes: "Attribute", entity_types: "Entity type",
  relationship_types: "Relationship type", allowed: "Allowed relationship", rules: "Rule", meta: "Metamodel" };

function Differences({ list }) {
  if (!list.length) return <p className="quiet">No differences.</p>;
  return (
    <ul className="impact-list diff-list">
      {list.map((d, i) => (
        <li key={i}>
          <span className={`diff-tag ${d.change}`}>{CHANGE[d.change] || d.change}</span> {SECTION[d.section] || d.section} <b>{d.code}</b> {d.name && d.name !== d.code && <span className="quiet">{d.name}</span>}
          {d.fields?.length > 0 && <span className="quiet"> · {d.fields.map((f) => (typeof f === "string" ? f : f.field)).join(", ")}</span>}
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------ move to another framework
export function FrameworkMoveDialog({ m, onClose }) {
  const { data: roots } = useApi("/api/v1/models?kind=template&archived=false");
  const [target, setTarget] = useState("");
  const [map, setMap] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mode, setMode] = useState("copy");
  const [withData, setWithData] = useState(true);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const choices = (roots || []).filter((r) => !isTop(r) && r.id !== m.source_model_id);

  async function look(t, mapping) {
    if (!t) { setPreview(null); return; }
    setBusy(true); setError("");
    try {
      const q = new URLSearchParams({ target: t });
      if (mapping) q.set("map", JSON.stringify(mapping));
      const p = await apiFetch(`/api/v1/models/${m.id}/framework-preview?${q}`);
      setPreview(p);
      if (!mapping) setMap(Object.fromEntries(p.types.map((x) => [x.code, x.to])));
      if (!name) setName(`${m.name} on ${p.target}`);
    } catch (e) { setError(e.message); }
    setBusy(false);
  }

  async function move() {
    setBusy(true); setError("");
    try {
      const from = window.location.hash;
      const out = await runTask(post(`/api/v1/models/${m.id}/framework-move`, { target, mode, map, name: mode === "copy" ? name.trim() : null, with_data: mode === "copy" ? withData : true }));
      refreshAll();
      onClose();
      if (window.location.hash === from) go(`/metamodel/${out.model.id}`);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  const leftOut = preview ? preview.types.filter((x) => !map?.[x.code]).reduce((n, x) => n + x.entities, 0) : 0;
  return (
    <Modal title={`Move ${m.name} to another framework`} wide onClose={onClose}
      actions={<>
        <button onClick={onClose}>Cancel</button>
        <button className={mode === "in_place" ? "danger" : "primary"} disabled={busy || !preview || (mode === "copy" && !name.trim())} onClick={move}>
          {busy && preview ? "Moving..." : mode === "copy" ? "Create the moved copy" : "Move this model"}</button>
      </>}>
      <div className="ed-form">
        <Field label="1. The root metamodel to move to" tip="For example a newer version of the framework. Its entity types are matched to this model's by code, then by name.">
          <select value={target} onChange={(e) => { setTarget(e.target.value); setMap(null); look(e.target.value, null); }}>
            <option value="">Choose...</option>
            {choices.map((r) => <option key={r.id} value={r.id}>{label(r)}</option>)}
          </select>
        </Field>
        {busy && !preview && <p>Comparing the metamodels...</p>}
        {preview && (
          <>
            <Field label="2. Where each entity type goes" hint="(matched by code, then by name; change any of them)"
              tip="Every entity of a type moves to the type chosen here. Leave out a type to drop its entities from the moved model.">
              <div className="table-wrap" style={{ maxHeight: 300, overflowY: "auto" }}>
                <table className="grid-table">
                  <thead><tr><th>Entity type</th><th className="num">Entities</th><th>Becomes</th><th>Matched</th></tr></thead>
                  <tbody>
                    {preview.types.map((x) => (
                      <tr key={x.code} className={map?.[x.code] ? "" : "retired"}>
                        <td>{x.name} <span className="quiet">{x.code}</span></td>
                        <td className="num">{x.entities}</td>
                        <td>
                          <select value={map?.[x.code] || ""} onChange={(e) => setMap({ ...map, [x.code]: e.target.value || null })}>
                            <option value="">Leave out</option>
                            {preview.target_types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
                          </select>
                        </td>
                        <td className="quiet">{map?.[x.code] === x.to ? x.how : "chosen"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <span className="quiet">
                {leftOut ? `${leftOut} entities are left out. ` : "Every entity has a place. "}
                {preview.attributes_left_out.length > 0 && `Attributes the target does not have are left out: ${preview.attributes_left_out.join(", ")}. `}
                Relationships whose type is not in the target are left out ({preview.relationship_types.filter((r) => !r.to).length} types).
              </span>
            </Field>
            <Field label="3. How" tip="A moved copy is the safe choice: this model stays as it is. In place changes this model and cannot be undone except from its history.">
              <label className="lock-opt"><input type="radio" checked={mode === "copy"} onChange={() => setMode("copy")} />
                <span><b>Make a moved copy</b> <span className="quiet">a new model on {preview.target}; this one stays as it is</span></span></label>
              <label className="lock-opt"><input type="radio" checked={mode === "in_place"} onChange={() => setMode("in_place")} />
                <span><b>Move this model in place</b> <span className="quiet">its metamodel takes on {preview.target}'s (one new metamodel version);
                  entity types left out are retired and their entities removed. History keeps everything.</span></span></label>
            </Field>
            {mode === "copy" && <Field label="The new model's name"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>}
            {mode === "copy" && (
              <label className="ed-field check" title="Without data: the target framework's metamodel only, for a fresh start or a comparison later">
                <input type="checkbox" checked={withData} onChange={(e) => setWithData(e.target.checked)} />
                <span>Bring the data across <span className="quiet">(untick for the metamodel only)</span></span></label>
            )}
          </>
        )}
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ delete, archive, library actions
export function DeleteDialog({ m, onClose }) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function remove() {
    setBusy(true); setError("");
    try {
      await apiFetch(`/api/v1/models/${m.id}?confirm=${encodeURIComponent(typed)}`, { method: "DELETE" });
      refreshAll();
      onClose();
      go("/metamodel");
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Delete ${m.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="danger" disabled={busy || typed !== m.name} onClick={remove}>{busy ? "Deleting..." : "Delete the model"}</button></>}>
      <div className="ed-form">
        <p>The model, its metamodel, content and history are deleted. A package of it is saved first in the exports folder
          (deleted-&lt;date&gt;-&lt;name&gt;.zip), so it can be uploaded again. A model other models are built on or merge into cannot be deleted.</p>
        <Field label={`Type the model's name (${m.name}) to confirm`}><input value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus /></Field>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

export function PromoteDialog({ m, onClose }) {
  const [name, setName] = useState(m.name);
  const [version, setVersion] = useState(m.version_label || "1.0");
  const [industry, setIndustry] = useState(m.industry || "");
  const [copy, setCopy] = useState("content");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function promote() {
    setBusy(true); setError("");
    try {
      const from = window.location.hash;
      const out = await runTask(post(`/api/v1/models/${m.id}/promote`, { name: name.trim(), version_label: version, industry, copy }), "#/library");
      refreshAll();
      onClose();
      if (window.location.hash === from) go(`/metamodel/${(out.model || out).id}`);
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Promote ${m.name} to the library`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !name.trim()} onClick={promote}>{busy ? "Promoting..." : "Promote"}</button></>}>
      <div className="ed-form">
        <p>A copy of this model becomes a library model (a draft until a Library Admin publishes it). This model stays as it is.</p>
        <Field label="Copy">
          <div className="ed-radio">
            {COPIES.map(([k, l, hint]) => (
              <label key={k} className="lock-opt" title={hint}>
                <input type="radio" name="pcopy" checked={copy === k} onChange={() => setCopy(k)} />
                <span><b>{l}</b><br /><span className="quiet">{hint}</span></span>
              </label>
            ))}
          </div>
        </Field>
        <Field label="Library model name"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Version"><input value={version} onChange={(e) => setVersion(e.target.value)} /></Field>
          <Field label="Industry"><input value={industry} onChange={(e) => setIndustry(e.target.value)} /></Field>
        </div>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

// Publish, withdraw and restore: one click, with the answer shown
export async function libraryAction(m, action) {
  await post(`/api/v1/models/${m.id}/${action}`, {});
  refreshAll();
}

// The model page's Actions menu
export function ModelActions({ m }) {
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const admin = canOn(m.id, "model.lock");
  const curator = can("library.curate");
  const library = m.kind === "reference" || m.kind === "template";
  const close = () => setDialog(null);

  async function act(path, what) {
    setOpen(false); setBusy(what); setError("");
    try { await post(`/api/v1/models/${m.id}/${path}`, {}); refreshAll(); }
    catch (e) { setError(e.message); }
    setBusy("");
  }
  async function spec() {
    setOpen(false); setError("");
    try { await apiDownload(`/api/v1/models/${m.id}/metamodel-spec`, `${m.name} metamodel.json`); }
    catch (e) { setError(e.message); }
  }

  // [label, action, allowed, what it does, why not]: every item is always listed; greyed out with the reason when not allowed
  const adminWhy = needsRole("model-admin", m.name);
  const libWhy = needsRole(["library-admin"]);
  const items = [
    ["Create a model from this", () => setDialog("new"), mayCreateFrom(m), m.kind === "project"
      ? "A child model that merges back into this one, or an independent copy that can be compared" : "A new model built on this one's metamodel, with or without its content and history",
      m.is_draft && !ownsDraft(m) ? draftWhy(m) : needsRole(CREATE_ROLES) + (m.kind === "project" ? ` (or Model Admin of ${m.name}, for a child of it)` : "")],
    ["Change the icon...", () => setDialog("icon"), admin || can("models.delete"),
      "Pick the model's icon from the library or upload your own (for this model only); shown wherever the model is named", adminWhy],
    ["Download...", () => setDialog("download"), true, "The model as one package, Excel or zip: without data, with the data, or deep with its full history (to upload here or elsewhere)"],
    ["Download the metamodel (JSON)", spec, true, "The metamodel as one document, to give an AI assistant or upload as a metamodel draft"],
    ["-"],
    ["Tag this model now...", () => setDialog("tag"), m.kind !== "template" && canOn(m.id, "model.content"),
      "A frozen copy of the model under a name (for example Baseline 2026), to compare with later or make the latest again",
      m.kind === "template" ? "A root metamodel has no content to tag; its versions are in its metamodel history"
        : needsRole(["architect", "committer", "model-sub-admin", "model-admin"], m.name)],
    ["Tags of this model", () => { window.location.hash = `/metamodel/${m.id}/tags`; }, m.kind !== "template",
      "Every tag of this model: open one to see what it holds, compare, download or make it the latest",
      "A root metamodel has no content to tag"],
    ["Compare...", () => { window.location.hash = `/compare?model=${m.id}`; }, m.kind !== "template",
      "Compare this model (as it is now or a tag) with itself, another tag, or any other model and its tags",
      "A root metamodel has no content to compare"],
    ["Gap analyses", () => { window.location.hash = `/compare/gaps?model=${m.id}`; }, m.kind !== "template",
      "The gap analyses stored in this model, or with it as the source or target",
      "A root metamodel has no content"],
    ["Move to another framework...", () => setDialog("move"), admin && m.kind === "project" && !m.is_locked,
      "Put this model on another root metamodel, for example a newer framework version",
      m.kind !== "project" ? "Only project models move to another framework; create a model from this one first"
        : m.is_locked ? `${m.name} is locked` : adminWhy],
    ["-"],
    ["Promote to the library...", () => setDialog("promote"), curator && m.kind === "project" && !m.is_draft,
      "A copy of this model becomes a library model (a draft until a Library Admin publishes it)",
      m.kind !== "project" ? "Only project models are promoted; this one is already a library model" : m.is_draft ? "Publish the model first" : libWhy],
    // publishing a draft is two steps, always (D134): request, then approve (or send back)
    ["Request publishing...", () => setDialog("request-publish"),
      m.is_draft && ["editing", "returned"].includes(m.approval_state) && (admin || (library && curator)),
      "Ask for this draft to be published; an approver then approves it or sends it back",
      !m.is_draft ? "Already published" : m.approval_state === "requested" ? "Already waiting for approval" : adminWhy],
    [library ? "Approve and publish in the library..." : "Approve and publish...", () => setDialog("publish"),
      m.is_draft && m.approval_state === "requested" && (library ? curator : admin),
      library ? "Everyone can see it and start from it; it becomes read-only" : "It stops being a draft: others with a role on it can create models from it",
      !m.is_draft ? "Already published" : m.approval_state !== "requested" ? "Publishing has not been requested yet" : library ? libWhy : adminWhy],
    ["Send back...", () => setDialog("send-back-publish"),
      m.is_draft && m.approval_state === "requested" && (library ? curator : admin),
      "Send the draft back to its makers with a note on what to change",
      m.approval_state !== "requested" ? "Only a draft waiting for approval is sent back" : library ? libWhy : adminWhy],
    ["Reject...", () => setDialog("reject-publish"),
      m.is_draft && m.approval_state === "requested" && (library ? curator : admin),
      "Reject the draft with the reason: it is not published and is archived (its Model Admin can open it again)",
      m.approval_state !== "requested" ? "Only a draft waiting for approval is rejected" : library ? libWhy : adminWhy],
    ["Open the rejected draft again...", () => setDialog("reopen"),
      m.is_draft && m.approval_state === "rejected" && admin,
      "Work on the draft again and request publishing once more",
      m.approval_state !== "rejected" ? "Only a rejected draft is opened again" : adminWhy],
    [m.library_state === "withdrawn" ? "Restore to the library" : "Withdraw from the library",
      () => act(m.library_state === "withdrawn" ? "restore" : "withdraw", m.library_state === "withdrawn" ? "Restoring" : "Withdrawing"),
      curator && library && !isTop(m) && ["published", "withdrawn"].includes(m.library_state),
      m.library_state === "withdrawn" ? "Back in the library for everyone" : "Nobody can start new models from it; models built on it keep working",
      !library ? "Only library models are withdrawn" : isTop(m) ? "Root is the top of the hierarchy and always stays"
        : m.library_state === "building" ? "Not published yet" : libWhy],
    ["-"],
    [m.lifecycle === "archived" ? "Reactivate" : "Archive",
      () => act(m.lifecycle === "archived" ? "reactivate" : "archive", m.lifecycle === "archived" ? "Reactivating" : "Archiving"),
      admin && !m.is_locked && !isTop(m),
      m.lifecycle === "archived" ? "Back in the lists" : "Hidden from lists (Show archived shows it); nothing is lost and it can be reactivated",
      isTop(m) ? "Root is the top of the hierarchy and always stays" : m.is_locked ? `${m.name} is a locked library model: a Library Admin withdraws it instead` : adminWhy],
    ["Delete...", () => setDialog("delete"), can("models.delete") && !isTop(m), "Delete the model for good, after saving a package of it",
      isTop(m) ? "Root is the top of the hierarchy and always stays" : needsRole(["super-admin"])],
  ];

  return (
    <span className="lock-ctl">
      <button onClick={() => setOpen(!open)} aria-expanded={open} disabled={!!busy} title="Copy, download, move, archive or delete this model; library actions for Library Admins">{busy ? `${busy}...` : "Actions ▾"}</button>
      {open && (
        <div className="lock-pop menu-pop" onMouseLeave={() => setOpen(false)}>
          {items.map(([text, fn, ok, tip, why], i) => (text === "-" ? <hr key={i} />
            : <button key={text} className="menu-item" disabled={!ok} title={ok ? tip : `${tip}. ${why}`} onClick={() => { setOpen(false); fn(); }}>
              {text}{!ok && <span className="menu-why">{why}</span>}</button>))}
        </div>
      )}
      {error && <span className="status bad"> {error}</span>}
      {dialog === "new" && <NewModelDialog from={m} onClose={close} />}
      {dialog === "download" && <DownloadDialog m={m} onClose={close} />}
      {dialog === "icon" && <IconDialog m={m} onClose={close} />}
      {["request-publish", "publish", "send-back-publish", "reject-publish", "reopen"].includes(dialog) && <PublishStepDialog m={m} step={dialog} onClose={close} />}
      {dialog === "move" && <FrameworkMoveDialog m={m} onClose={close} />}
      {dialog === "delete" && <DeleteDialog m={m} onClose={close} />}
      {dialog === "promote" && <PromoteDialog m={m} onClose={close} />}
      {dialog === "tag" && <TagNowDialog m={m} onClose={close} />}
    </span>
  );
}

// Actions > Tag this model now (phase 8.3): the same as the Tags tab's box. Tagging reads the whole model, so it runs
// in the background (D192): the dialog follows it; close it any time, the top bar says when the tag is made
export function TagNowDialog({ m, onClose }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [lock, setLock] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [taskId, setTaskId] = useState(null);
  const task = useTask(taskId);
  async function tag() {
    setBusy(true); setError("");
    try {
      const out = await post(`/api/v1/models/${m.id}/tags`, { name, description: desc, lock });
      if (out.task) { trackTask(out.task, `#/metamodel/${m.id}/tags`); setTaskId(out.task.id); return; }
      refreshAll(); onClose(); window.location.hash = `/metamodel/${m.id}/tags/${out.id}`;   // tagged in the request
    } catch (e) { setError(e.message); setBusy(false); }
  }
  if (taskId) {
    const t = task || {};
    return (
      <Modal title={`Tag ${m.name}`} onClose={onClose}
        actions={t.done && t.status === "done"
          ? <><button onClick={onClose}>Close</button><button className="primary" onClick={() => { onClose(); window.location.hash = `/metamodel/${m.id}/tags/${t.result.id}`; }}>Open the tag</button></>
          : <button onClick={onClose}>{t.done ? "Close" : "Close: keep working"}</button>}>
        {!t.done && <p><span className="spinner" aria-hidden="true" /> Tagging {m.name} as <b>{name}</b> in the background
          {t.status === "queued" ? " (waiting to start)" : ""}... On a large model this takes a while: close this and carry on;
          the bar at the top says when the tag is made.</p>}
        {t.done && <p className={`status ${t.status === "done" ? "ok" : "bad"}`}>{t.message}</p>}
      </Modal>
    );
  }
  return (
    <Modal title={`Tag ${m.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !name.trim()} onClick={tag}>🏷 Tag it now</button></>}>
      <p className="quiet">A frozen copy of the model as committed now: its metamodel and every entity, value and relationship.
        It is made in the background: you can carry on working.</p>
      <div className="ed-form">
        <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Baseline 2026" autoFocus /></Field>
        <Field label="What it is (optional)"><input value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
        <label><input type="checkbox" checked={lock} onChange={(e) => setLock(e.target.checked)} /> Lock it (never changed or deleted; a Model Admin unlocks)</label>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

const PUBLISH_STEPS = {
  "request-publish": ["Request publishing", "A note for the approver (optional)", "primary", false],
  publish: ["Approve and publish", "A note (optional)", "primary", false],
  "send-back-publish": ["Send back", "What to change", "danger", true],
  "reject-publish": ["Reject", "Why it is rejected", "danger", true],
  reopen: ["Open again", "A note (optional)", "primary", false],
};

export function PublishStepDialog({ m, step, onClose }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [title, label, cls, needed] = PUBLISH_STEPS[step];
  async function send() {
    setBusy(true); setError("");
    try { await post(`/api/v1/models/${m.id}/${step}`, { note }); refreshAll(); onClose(); }
    catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`${title}: ${m.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className={cls} disabled={busy || (needed && !note.trim())} onClick={send}>{title}</button></>}>
      <div className="ed-form">
        <Field label={label}><textarea value={note} onChange={(e) => setNote(e.target.value)} autoFocus /></Field>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

// While the content is being copied in the background, and when the copy failed
export function CopyBanner({ m }) {
  useEffect(() => {
    if (m.copy_state !== "copying") return undefined;
    const t = setInterval(refreshAll, 2500);
    return () => clearInterval(t);
  }, [m.copy_state]);
  if (m.copy_state === "copying") {
    return <div className="lock-banner">⏳ Copying the content from {m.source_model_name || "the source model"} in the background. The page fills in when it is done.</div>;
  }
  if (m.copy_state === "failed") {
    return <div className="lock-banner content">The copy failed: {m.copy_note || "see the job log"}. Delete this model and create it again, or ask an IT Admin.</div>;
  }
  if (m.library_state === "building") {
    return <div className="lock-banner draft-banner">📝 Draft: not yet published in the library. {m.approval_state === "requested"
      ? "Publishing requested: a Library Admin approves it (Model admin > Wizards > Approve and publish) or sends it back."
      : "Request publishing (Actions) when it is ready; a Library Admin approves it."}</div>;
  }
  if (m.is_draft) {
    const st = { requested: "Publishing requested: waiting for approval (Model admin > Wizards > Approve and publish).",
      returned: "Sent back: change it and request publishing again (Model admin > Wizards > Request publishing).",
      rejected: "Rejected: not published and archived. Its Model Admin can open it again (Model admin > Wizards > Open the rejected draft again).",
      editing: "Nobody else can create a model from it until it is published: Model admin > Wizards > Request publishing, then it is approved." }[m.approval_state] || "";
    return <div className="lock-banner draft-banner">📝 Draft model. {st}</div>;
  }
  if (m.library_state === "withdrawn") {
    return <div className="lock-banner content">Withdrawn from the library: nobody can start a new model from it. Models already built on it keep working.</div>;
  }
  return null;
}

// ------------------------------------------------------------------ metamodel drafts (D115, D120)
const DRAFT_STATUS = { draft: "Waiting for review", returned: "Sent back for changes", applied: "Applied", rejected: "Rejected" };

// Drafting: Model Creators and Library Admins (new roots), or the Model Admin of some model (changes to it)
const mayDraft = () => mayCreate() || (myInfo()?.models || []).some((x) => (x.roles || [x.role]).includes("model-admin"));

export function Drafts() {
  const [status, setStatus] = useState("draft");
  const { data: drafts, error } = useApi(`/api/v1/metamodel-drafts${status ? `?status=${status}` : ""}`);
  const [open, setOpen] = useState(false);
  return (
    <div>
      <p className="quiet">
        A draft is a whole metamodel waiting for a person to review it: built by an AI assistant through the MCP tools
        (start_metamodel_draft, draft_set_item, draft_replace), or uploaded here as a metamodel JSON file. A reviewer applies it,
        sends it back for changes with comments (its maker, or their AI, fixes it and resubmits), or rejects it (it can be reopened).
        Nothing changes until it is applied: a new root metamodel (Model Creators), which starts as a draft model, or changes to a model (its Model Admin).
      </p>
      <div className="toolbar">
        <div className="seg small">
          {[["draft", "Waiting for review"], ["returned", "Sent back"], ["applied", "Applied"], ["rejected", "Rejected"], ["", "All"]].map(([k, l]) => (
            <button key={k} className={status === k ? "on" : ""} onClick={() => setStatus(k)}>{l}</button>
          ))}
        </div>
        <button onClick={() => setOpen(true)} disabled={!mayDraft()}
          title={mayDraft() ? "Start a draft by hand: empty, from a copy of a root metamodel, or from a metamodel JSON file"
            : `Drafting a metamodel: ${needsRole(["model-creator", "library-admin"])} (or Model Admin of a model, for changes to it)`}>+ New draft</button>
        <a className="small-link" href="#/mcp">How AI assistants make drafts</a>
      </div>
      {error && <p className="status bad">{error}</p>}
      {drafts && !drafts.length && <p className="quiet">No drafts.</p>}
      {drafts && drafts.length > 0 && (
        <div className="table-wrap">
          <table className="grid-table">
            <thead><tr><th>Draft</th><th>For</th><th>Contents</th><th>Checks</th><th>By</th><th>Status</th><th>Comments</th><th>Changed</th></tr></thead>
            <tbody>
              {drafts.map((d) => {
                const errors = (d.checks || []).filter((c) => c.level === "error").length;
                return (
                  <tr key={d.id}>
                    <td><a href={`#/metamodel/drafts/${d.id}`}>{d.name}</a></td>
                    <td>{d.kind === "root" ? <>New root{d.base_model && <span className="quiet"> from {d.base_model}</span>}</> : <>Changes to {d.target_model}</>}</td>
                    <td className="quiet">{d.counts.entity_types} entity types · {d.counts.relationship_types} relationship types · {d.counts.attributes} attributes</td>
                    <td>{errors ? <span className="status bad">{errors} errors</span> : <span className="all-pass">OK</span>}</td>
                    <td>{d.proposed_by} <span className="quiet">{d.proposed_via === "mcp" ? "via AI (MCP)" : d.proposed_via}</span></td>
                    <td title={DRAFT_HELP[d.status]}>{DRAFT_STATUS[d.status] || d.status} <span className="quiet">round {d.round}</span></td>
                    <td>{d.open_comments ? <span title="Open review comments">💬 {d.open_comments}</span> : <span className="quiet">-</span>}</td>
                    <td className="quiet">{fmtDateTime(d.modified_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {open && <NewDraftDialog onClose={() => setOpen(false)} />}
    </div>
  );
}

function NewDraftDialog({ onClose }) {
  const { data: models } = useApi("/api/v1/models?archived=false");
  const [kind, setKind] = useState("root");
  const [name, setName] = useState("");
  const [base, setBase] = useState("");
  const [target, setTarget] = useState("");
  const [spec, setSpec] = useState(null);
  const [fileName, setFileName] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const roots = (models || []).filter((m) => m.kind === "template" && !isTop(m));
  const targets = (models || []).filter((m) => canOn(m.id, "model.metamodel") && !m.is_locked);

  function read(f) {
    setError(""); setSpec(null); setFileName(f?.name || "");
    if (!f) return;
    f.text().then((t) => {
      try {
        const j = JSON.parse(t);
        setSpec(j);
        if (!name && j.name) setName(j.name);
      } catch { setError("That file is not JSON: a metamodel file is the JSON Model admin > Wizards > Download the metamodel gives."); }
    });
  }
  async function create() {
    setBusy(true); setError("");
    try {
      const d = await post("/api/v1/metamodel-drafts", {
        kind, name: name.trim() || null, base: kind === "root" && base ? base : null, target: kind === "changes" ? target : null, note, spec,
      });
      refreshAll();
      onClose();
      go(`/metamodel/drafts/${d.id}`);
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title="New metamodel draft" onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy || (kind === "changes" && !target) || (kind === "root" && !name.trim())} onClick={create}>{busy ? "Creating..." : "Create the draft"}</button></>}>
      <div className="ed-form">
        <Field label="The draft is">
          <div className="seg small">
            <button type="button" className={kind === "root" ? "on" : ""} onClick={() => setKind("root")}>A new root metamodel</button>
            <button type="button" className={kind === "changes" ? "on" : ""} onClick={() => setKind("changes")}>Changes to a model</button>
          </div>
        </Field>
        {kind === "root" ? <>
          <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Start from" hint="(ignored when you choose a file)">
            <select value={base} onChange={(e) => setBase(e.target.value)}>
              <option value="">Empty</option>
              {roots.map((r) => <option key={r.id} value={r.id}>A copy of {label(r)}</option>)}
            </select>
          </Field>
        </> : (
          <Field label="The model" hint="(models you are Model Admin of)">
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose...</option>
              {targets.map((m) => <option key={m.id} value={m.id}>{label(m)}</option>)}
            </select>
          </Field>
        )}
        <Field label="A metamodel file" hint="(optional: eax-metamodel/1 JSON)">
          <input type="file" accept=".json,application/json" onChange={(e) => read(e.target.files?.[0] || null)} />
          {spec && <span className="quiet">{fileName}: {(spec.entity_types || []).length} entity types, {(spec.relationship_types || []).length} relationship types</span>}
        </Field>
        <Field label="Note" hint="(what it is for)"><textarea value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

const SECTIONS = [["layers", "Layers"], ["pick_lists", "Pick lists"], ["attributes", "Attributes"], ["entity_types", "Entity types"],
  ["relationship_types", "Relationship types"], ["allowed", "Allowed relationships"], ["rules", "Rules"]];

function itemText(section, x) {
  if (section === "allowed") return `${x.source} —${x.relationship}→ ${x.target}`;
  if (section === "rules") return `${x.entity_type}.${x.field || x.attribute || ""} ${x.rule || x.type || ""}`;
  return x.name && x.name !== x.code ? `${x.name}` : x.code;
}
function itemMore(section, x) {
  if (section === "entity_types") return [x.layer, (x.attributes || []).length && `${x.attributes.length} attributes`].filter(Boolean).join(" · ");
  if (section === "attributes") return [x.data_type, x.pick_list].filter(Boolean).join(" · ");
  if (section === "pick_lists") return (x.values || []).map((v) => (typeof v === "string" ? v : v.value || v.code)).join(", ");
  if (section === "relationship_types") return x.description || "";
  return "";
}

// A readable key for an item, used to hang comments on it (allowed and rules have no code)
function itemKey(section, x) {
  if (section === "allowed") return `${x.source} ${x.relationship} ${x.target}`;
  if (section === "rules") return `${x.entity_type || "*"}.${x.attribute || x.field || ""} ${x.rule_type || x.rule || ""}`.trim();
  return x.code;
}

const ACTION_TEXT = { created: "Created", sent_back: "Sent back for changes", resubmitted: "Resubmitted for review",
  rejected: "Rejected", reopened: "Reopened", applied: "Applied" };

export function DraftPage({ id }) {
  const { data: d, error } = useApi(`/api/v1/metamodel-drafts/${id}`);
  const [section, setSection] = useState("entity_types");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [dialog, setDialog] = useState(null);       // apply, reject, send-back, resubmit, reopen
  const [commentOn, setCommentOn] = useState(null); // {section, code} or "draft"
  const [showResolved, setShowResolved] = useState(false);
  if (error) return <section><p className="status bad">{error}</p><a href="#/metamodel/drafts">All drafts</a></section>;
  if (!d) return <section><p>Loading...</p></section>;
  const waiting = d.status === "draft", returned = d.status === "returned", rejected = d.status === "rejected";
  const may = d.may_review;
  const mayWhy = d.kind === "root" ? needsRole(["model-creator", "library-admin"]) : needsRole("model-admin", d.target_model);
  const editWhy = !d.may_edit ? (d.status === "applied" ? "This draft was applied: change the model's metamodel in its Metamodel tab"
    : rejected ? "This draft was rejected: reopen it to change it" : `Changing the draft: its maker or a reviewer (${mayWhy})`) : "";
  const errors = d.checks.filter((c) => c.level === "error");
  const items = d.spec[section] || [];
  const comments = d.comments || [];
  const openOn = (sec, code) => comments.filter((c) => c.section === sec && c.code === code && !c.resolved_at);
  const general = comments.filter((c) => !c.section && (showResolved || !c.resolved_at));
  const onItems = comments.filter((c) => c.section && (showResolved || !c.resolved_at));

  async function call(path, body, what) {
    setBusy(what); setMsg("");
    try { await post(`/api/v1/metamodel-drafts/${id}/${path}`, body); refreshAll(); }
    catch (e) { setMsg(e.message); }
    setBusy("");
  }
  const remove = (code) => call("edit", { action: "remove", section, code }, code);
  const resolve = (c, resolved) => call(`comments/${c.id}/resolve`, { resolved }, c.id);
  function downloadJson() {
    const blob = new Blob([JSON.stringify(d.spec, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${d.name}.json`;
    a.click();
  }
  function replaceFromFile(f) {
    if (!f) return;
    f.text().then((t) => {
      let spec;
      try { spec = JSON.parse(t); } catch { setMsg("That file is not JSON (a metamodel document, eax-metamodel/1)."); return; }
      call("edit", { action: "replace", spec }, "replace");
    });
  }
  const sectionName = (k) => SECTIONS.find(([c]) => c === k)?.[1] || k;

  return (
    <section className="model-page">
      <p className="lineage"><a href="#/metamodel/drafts">Metamodel drafts</a> /</p>
      <div className="model-head">
        <h1>{d.name}</h1>
        <span className={`rchip ${waiting || returned ? "on" : ""}`} title={DRAFT_HELP[d.status]}>{DRAFT_STATUS[d.status]}</span>
        <span className="quiet">round {d.round}</span>
        <button onClick={downloadJson} title="The draft's metamodel as one JSON document">⬇ JSON</button>
        <label className={`button file-button${d.may_edit ? "" : " off"}`} title={d.may_edit ? "Replace the whole draft with a metamodel JSON file (for example one you edited, or your AI made); it is checked again" : editWhy}>
          ⬆ Replace from file<input type="file" accept=".json,application/json" disabled={!d.may_edit} onChange={(e) => replaceFromFile(e.target.files?.[0])} hidden />
        </label>
        <span className="er-spacer" />
        <button className="primary" disabled={!waiting || !may || errors.length > 0 || !!busy} onClick={() => setDialog("apply")}
          title={!waiting ? (returned ? "Sent back for changes: it is applied after it is resubmitted" : `This draft was ${d.status}`) : !may ? `Applying: ${mayWhy}`
            : errors.length ? "Fix the errors first: remove or correct the items the checks name" : "Make the new root metamodel (a draft model until published), or publish the changes as one metamodel version"}>Apply...</button>
        <button disabled={!waiting || !may || !!busy} onClick={() => setDialog("send-back")}
          title={!waiting ? "Only a draft waiting for review is sent back" : !may ? `Sending back: ${mayWhy}` : "Send it back to its maker with your comments: it becomes editable again"}>Send back...</button>
        <button disabled={!(waiting || returned) || !may || !!busy} onClick={() => setDialog("reject")}
          title={!(waiting || returned) ? `This draft was ${d.status}` : !may ? `Rejecting: ${mayWhy}` : "Close the draft without applying it, saying why (it can be reopened)"}>Reject...</button>
        <button disabled={!returned || !d.may_edit || !!busy} onClick={() => setDialog("resubmit")}
          title={!returned ? "Only a draft sent back for changes is resubmitted" : !d.may_edit ? editWhy : errors.length ? "Resubmit (it still has errors: the reviewer cannot apply it until they are fixed)" : "Send it for review again: a new round"}>Resubmit...</button>
        <button disabled={!rejected || !!busy || !(d.may_review || d.proposed_by === (myInfo()?.username))} onClick={() => setDialog("reopen")}
          title={!rejected ? "Only a rejected draft is reopened" : "Open it again for changes, as a new round"}>Reopen...</button>
      </div>
      <p className="quiet">
        {d.kind === "root" ? <>A new root metamodel{d.base_model && <> starting from {d.base_model}</>}</> : <>Changes to <a href={`#/metamodel/${d.target_model_id}`}>{d.target_model}</a></>}
        {" · "}by {d.proposed_by} {d.proposed_via === "mcp" ? "through an AI assistant (MCP)" : `(${d.proposed_via})`} · changed {fmtDateTime(d.modified_at)}
        {d.decided_by && <> · {DRAFT_STATUS[d.status].toLowerCase()} by {d.decided_by} on {fmtDateTime(d.decided_at)}</>}
        {d.applied_model_id && <> · <a href={`#/metamodel/${d.applied_model_id}/metamodel`}>{d.applied_model}</a></>}
      </p>
      {d.note && <p className="lib-desc">{d.note}</p>}
      {returned && <div className="lock-banner">Sent back for changes. Deal with the open comments (remove items here, ask your AI to change them through MCP,
        or replace the draft from a file), mark them fixed, then <b>Resubmit</b>.</div>}
      {waiting && !may && <p className="quiet">You can look at this draft. {mayWhy}</p>}
      <p className="quiet small-note">A draft is for review: trim it, comment on it and send it back. Detailed changes are easier once it is applied,
        in the new model's Metamodel tab (it stays a draft model until published).</p>
      {msg && <p className="status bad">{msg}</p>}

      <div className={errors.length ? "removals" : "impact"} style={{ margin: "8px 0" }}>
        <b>Checks:</b> {d.checks.length ? `${errors.length} errors, ${d.checks.length - errors.length} notes` : <span className="all-pass">everything passes</span>}
        {d.checks.length > 0 && <ul className="impact-list">{d.checks.map((c, i) => <li key={i}>{c.level === "error" ? "✖" : "⚠"} {c.where}: {c.message}</li>)}</ul>}
      </div>

      <div className="draft-comments">
        <div className="draft-comments-head">
          <b>Review comments</b> <span className="quiet">{d.open_comments} open</span>
          <span className="er-spacer" />
          <label className="quiet"><input type="checkbox" checked={showResolved} onChange={(e) => setShowResolved(e.target.checked)} /> Show fixed</label>
          <button className="small" disabled={d.status === "applied"} onClick={() => setCommentOn("draft")}
            title={d.status === "applied" ? "This draft was applied" : "A comment on the whole draft"}>+ Comment</button>
        </div>
        {!general.length && !onItems.length && <p className="quiet">No comments{showResolved ? "" : " open"}.</p>}
        <ul className="comment-list">
          {[...general, ...onItems].map((c) => (
            <li key={c.id} className={c.resolved_at ? "resolved" : ""}>
              <label title={c.resolved_at ? `Fixed by ${c.resolved_by}` : "Mark fixed once the draft deals with it"}>
                <input type="checkbox" checked={!!c.resolved_at} disabled={!!busy} onChange={(e) => resolve(c, e.target.checked)} />
              </label>
              <span>
                {c.section && <button className="linkish" onClick={() => setSection(c.section)}>{sectionName(c.section)} {c.code}</button>}
                {c.section && ": "}{c.body}
                <span className="quiet"> · {c.author}, round {c.round}, {fmtDateTime(c.created_at)}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      {d.since_last_review && d.since_last_review.length > 0 && (
        <details className="compare">
          <summary><b>{d.since_last_review.length} changes since the last review</b></summary>
          <Differences list={d.since_last_review} />
        </details>
      )}
      {(d.differences || []).length > 0 && (
        <details className="compare">
          <summary><b>{d.differences.length} differences</b> from {d.kind === "root" ? d.base_model || "the start" : `${d.target_model} now`}</summary>
          <Differences list={d.differences} />
        </details>
      )}

      <div className="tabs" role="tablist">
        {SECTIONS.map(([k, l]) => {
          const n = comments.filter((c) => c.section === k && !c.resolved_at).length;
          return (
            <button key={k} role="tab" aria-selected={section === k} className={section === k ? "tab on" : "tab"} onClick={() => setSection(k)}>
              {l} <span className="quiet">{d.counts[k]}</span>{n > 0 && <span className="comment-count" title={`${n} open comments`}>💬 {n}</span>}</button>
          );
        })}
      </div>
      <div className="tab-panel">
        {!items.length ? <p className="quiet">None.</p> : (
          <div className="table-wrap">
            <table className="grid-table">
              <thead><tr><th>{section === "allowed" || section === "rules" ? "#" : "Code"}</th><th>Name</th><th>Details</th><th /></tr></thead>
              <tbody>
                {items.map((x, i) => {
                  const key = section === "allowed" || section === "rules" ? String(i) : x.code;
                  const ck = itemKey(section, x);
                  const notes = openOn(section, ck);
                  return (
                    <tr key={key} className={notes.length ? "has-comment" : ""}>
                      <td className="quiet">{section === "allowed" || section === "rules" ? i + 1 : x.code}</td>
                      <td>{itemText(section, x)}{notes.map((c) => <div key={c.id} className="item-comment">💬 {c.body} <span className="quiet">· {c.author}</span></div>)}</td>
                      <td className="quiet">{itemMore(section, x)}</td>
                      <td className="row-actions">
                        <button className="small" disabled={d.status === "applied"} onClick={() => setCommentOn({ section, code: ck })}
                          title={d.status === "applied" ? "This draft was applied" : "Comment on this item"}>💬</button>
                        <button className="small" disabled={!d.may_edit || busy === key} onClick={() => remove(key)}
                          title={!d.may_edit ? editWhy : section === "entity_types" ? "Take it out of the draft, with its allowed relationships and rules" : section === "relationship_types" ? "Take it out of the draft, with its allowed relationships" : section === "attributes" ? "Take it out of the draft, from every type and rule" : "Take it out of the draft"}>Remove</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <details className="compare">
        <summary><b>History</b> <span className="quiet">{(d.events || []).length} steps</span></summary>
        <ul className="impact-list">
          {(d.events || []).map((e, i) => (
            <li key={i}>Round {e.round}: <b>{ACTION_TEXT[e.action] || e.action}</b> by {e.actor} on {fmtDateTime(e.at)}
              {e.error_count > 0 && <span className="quiet"> ({e.error_count} errors then)</span>}{e.note && <> · <i>{e.note}</i></>}</li>
          ))}
        </ul>
      </details>

      {dialog === "apply" && <ApplyDraftDialog d={d} onClose={() => setDialog(null)} />}
      {dialog === "reject" && <NoteDialog d={d} action="reject" onClose={() => setDialog(null)} />}
      {dialog === "send-back" && <NoteDialog d={d} action="send-back" onClose={() => setDialog(null)} />}
      {dialog === "resubmit" && <NoteDialog d={d} action="resubmit" onClose={() => setDialog(null)} />}
      {dialog === "reopen" && <NoteDialog d={d} action="reopen" onClose={() => setDialog(null)} />}
      {commentOn && <CommentDialog d={d} on={commentOn} sectionName={sectionName} onClose={() => setCommentOn(null)} />}
    </section>
  );
}

const DRAFT_HELP = {
  draft: "Waiting for review: a reviewer applies it, sends it back for changes, or rejects it",
  returned: "Sent back for changes: its maker fixes it and resubmits it",
  applied: "Applied: it made a model or a metamodel version",
  rejected: "Rejected: kept for the record; it can be reopened",
};

const NOTE_TEXT = {
  reject: ["Reject", "Why (added to the draft as a comment)", "danger", "reason"],
  "send-back": ["Send back for changes", "What to change (added as a comment; you can also comment on single items)", "primary", "note"],
  resubmit: ["Resubmit for review", "What you changed (optional)", "primary", "note"],
  reopen: ["Reopen", "Why it is reopened (optional)", "primary", "note"],
};

function NoteDialog({ d, action, onClose }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [title, label, cls, field] = NOTE_TEXT[action];
  const needs = action === "send-back" && !text.trim() && !d.open_comments;
  async function send() {
    setBusy(true); setError("");
    try { await post(`/api/v1/metamodel-drafts/${d.id}/${action}`, { [field]: text }); refreshAll(); onClose(); }
    catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`${title}: ${d.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button>
        <button className={cls} disabled={busy || needs} title={needs ? "Say what to change, or add comments on items first" : undefined} onClick={send}>{title}</button></>}>
      <div className="ed-form">
        <Field label={label}><textarea value={text} onChange={(e) => setText(e.target.value)} autoFocus /></Field>
        {action === "send-back" && d.open_comments > 0 && <p className="quiet">{d.open_comments} open comments go with it.</p>}
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

function CommentDialog({ d, on, sectionName, onClose }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function send() {
    setBusy(true); setError("");
    try {
      await post(`/api/v1/metamodel-drafts/${d.id}/comments`, on === "draft" ? { body: text } : { body: text, section: on.section, code: on.code });
      refreshAll(); onClose();
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={on === "draft" ? "Comment on the draft" : `Comment on ${sectionName(on.section)} ${on.code}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !text.trim()} onClick={send}>Add comment</button></>}>
      <div className="ed-form">
        <Field label="Comment" tip="Everyone who can see the draft reads it, including the maker's AI through MCP. Mark it fixed once the draft deals with it.">
          <textarea value={text} onChange={(e) => setText(e.target.value)} autoFocus /></Field>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

function ApplyDraftDialog({ d, onClose }) {
  const [name, setName] = useState(d.name);
  const [version, setVersion] = useState("1.0");
  const [model, setModel] = useState("");
  const [removeMissing, setRemoveMissing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const removed = (d.differences || []).filter((x) => x.change === "removed").length;
  async function go2() {
    setBusy(true); setError("");
    try {
      const from = window.location.hash;
      const out = await runTask(post(`/api/v1/metamodel-drafts/${d.id}/apply`, d.kind === "root"
        ? { name: name.trim(), version_label: version, create_model: model.trim() || null }
        : { remove_missing: removeMissing }));
      refreshAll();
      onClose();
      const to = out.model?.id || out.draft?.applied_model_id;
      if (to && window.location.hash === from) go(`/metamodel/${to}/metamodel`);   // detailed changes are made here, in the metamodel editor
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Apply ${d.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || (d.kind === "root" && !name.trim())} onClick={go2}>{busy ? "Applying..." : "Apply"}</button></>}>
      <div className="ed-form">
        {d.kind === "root" ? <>
          <p>A new root metamodel is created under Root with this metamodel. You become its Model Admin. It starts as a draft:
            change it in detail in its Metamodel tab (it opens there), and a Library Admin publishes it when it is ready.</p>
          <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Version"><input value={version} onChange={(e) => setVersion(e.target.value)} /></Field>
          <Field label="Also create a project model on it" hint="(optional: its name)"><input value={model} onChange={(e) => setModel(e.target.value)} /></Field>
        </> : <>
          <p>The changes are published to {d.target_model} as one new metamodel version, exactly as if you made them by hand.</p>
          {removed > 0 && (
            <label className="ed-field check"><input type="checkbox" checked={removeMissing} onChange={(e) => setRemoveMissing(e.target.checked)} />
              <span>Also retire the {removed} item{removed > 1 ? "s" : ""} the draft leaves out <span className="quiet">(otherwise they stay)</span></span></label>
          )}
        </>}
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

// a model's icon (D247): its Model Admins pick one from the library or upload their own, for this model only
export function IconDialog({ m, onClose }) {
  const [name, setName] = useState(m.icon?.startsWith("lib:") ? m.icon.slice(4) : "building");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function save() {
    setBusy(true); setErr("");
    try { await saveIcon(m.id, name, file); refreshAll(); onClose(); } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Icon of ${m.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy} onClick={save}>{busy ? "Saving..." : "Save"}</button></>}>
      <div className="ed-form">
        <p className="quiet small">Shown wherever the model is named. An image you upload is for this model only.</p>
        <IconPicker value={name} onChange={setName} file={file} onFile={setFile} kind={m.kind} />
        {m.icon === "upload" && !file && <p className="small">It has its own uploaded icon now; pick one above to replace it.</p>}
        {err && <p className="status bad">{err}</p>}
      </div>
    </Modal>
  );
}
