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

const go = (path) => { window.location.hash = path; };
const post = (path, body, method = "POST") => apiFetch(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
// Root, the top of the hierarchy every root metamodel is built on
// Who may create something (the server and the database check again)
const mayCreate = () => can("models.create") || can("library.curate");
const CREATE_ROLES = ["model-creator", "library-admin"];
const isTop = (m) => m.is_top || (m.kind === "template" && !m.source_model_id);
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
function Field({ label: text, hint, tip, children }) {
  return (
    <label className="ed-field">
      <span title={tip}>{text} {tip && <span className="tip" aria-label={tip}>ⓘ</span>} {hint && <span className="quiet">{hint}</span>}</span>
      {children}
    </label>
  );
}

// ------------------------------------------------------------------ create a model
const COPIES = [
  ["metamodel", "The metamodel only", "An empty model on the same metamodel"],
  ["content", "The metamodel and the content", "Every entity and relationship, as they are now"],
  ["history", "The content with its history", "As above, and the entity histories show the source model's past"],
];

export function NewModelDialog({ from, onClose }) {
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
  const [copy, setCopy] = useState(from && from.kind !== "template" ? "content" : "metamodel");
  const [link, setLink] = useState(!creator && !curator && fromProjectAdmin ? "child" : "independent");   // project sources: "child" (merges back) or "independent"
  const [version, setVersion] = useState(kind === "project" ? "" : "1.0");
  const [industry, setIndustry] = useState(from?.industry || "");
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

  async function create() {
    setBusy(true); setError("");
    try {
      const out = await post("/api/v1/models", {
        kind, name: name.trim(), source: source || null, parent: child ? source : null,
        copy: holdsContent && kind !== "root" ? copy : "metamodel", version_label: version, industry, description,
        framework: kind === "root" ? framework : "",
      });
      refreshAll();
      onClose();
      go(`/metamodel/${out.model.id}`);
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
                {list.map((m) => <option key={m.id} value={m.id}>{label(m)}{isTop(m) ? " (the top of the hierarchy)" : ""}</option>)}
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
            {src.kind === "template" ? " root metamodel" : " library model"}; to take a newer framework version, use Actions &gt; Move to another framework.</p>
        )}
        {kind === "root" && <Field label="Framework" hint="(for example ArchiMate, or your own)" tip="The name of the metamodel, shown beside every model built on this root."><input value={framework} onChange={(e) => setFramework(e.target.value)} /></Field>}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Version" tip="Your own label, for example 1.0 or 2026. Library models and roots are matched by name and version when packages are uploaded."><input value={version} onChange={(e) => setVersion(e.target.value)} /></Field>
          <Field label="Industry" tip="Used to group and search models and library models."><input value={industry} onChange={(e) => setIndustry(e.target.value)} /></Field>
        </div>
        <Field label="Description" tip="What the model is for and who looks after it."><textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <p className="quiet small-note">You become the new model's Model Admin.</p>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

const mayCreateFrom = (m) => mayCreate() || (m.kind === "project" && canOn(m.id, "model.derive"));

export function CreateFromButton({ m, className = "" }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className={className} onClick={() => setOpen(true)} disabled={!mayCreateFrom(m)}
        title={!mayCreateFrom(m) ? `Creating a model: ${needsRole(m.kind === "project" ? ["model-creator", "library-admin"] : CREATE_ROLES)}${m.kind === "project" ? ` (or Model Admin of ${m.name}, for a child of it)` : ""}`
          : m.kind === "project" ? "A child model (merges back into this one) or an independent copy (compared, never merged)" : "A new model built on this one's metamodel, with or without its content"}>Create a model from this</button>
      {open && <NewModelDialog from={m} onClose={() => setOpen(false)} />}
    </>
  );
}

export function NewModelButton() {
  const [open, setOpen] = useState(false);
  const ok = mayCreate();
  return (
    <>
      <button className="primary" disabled={!ok} onClick={() => setOpen(true)}
        title={ok ? "A project model, a root metamodel or (Library Admins) a library model, empty or from an existing model" : `Creating a model: ${needsRole(CREATE_ROLES)}`}>+ New model</button>
      {open && <NewModelDialog onClose={() => setOpen(false)} />}
    </>
  );
}

// ------------------------------------------------------------------ download a package
export function DownloadButtons({ m, compact }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  async function get(format) {
    setBusy(format); setError("");
    try { await apiDownload(`/api/v1/models/${m.id}/package?format=${format}`, `${m.name}.${format}`); }
    catch (e) { setError(e.message); }
    setBusy("");
  }
  return (
    <span className="dl-buttons">
      <button disabled={!!busy} onClick={() => get("zip")} title="One zip: manifest, metamodel (JSON) and the content as CSV files">
        {busy === "zip" ? "Downloading..." : `⬇ ${compact ? "Zip" : "Download package (zip)"}`}</button>
      <button disabled={!!busy} onClick={() => get("xlsx")} title="One Excel workbook: the metamodel and every entity type on its own sheet">
        {busy === "xlsx" ? "Downloading..." : `⬇ ${compact ? "Excel" : "Download as Excel"}`}</button>
      {error && <span className="status bad"> {error}</span>}
    </span>
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
      const out = await apiUpload("/api/v1/packages/analyse", form);
      setInfo(out);
      const mm = out.manifest?.model || {};
      setName(mm.name || f.name.replace(/\.(zip|xlsx)$/i, ""));
      const best = out.placements.find((p) => p.code === "root" && p.matches);
      setPlacement(best ? `root:${best.root_id}` : "own_root");
      if (mm.kind === "project" || !curator) setAsKind("project"); else setAsKind("library");
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
    if (!isRoot) form.append("as_kind", asKind);
    try {
      const out = await apiUpload("/api/v1/packages/import", form);
      refreshAll();
      onClose();
      go(`/metamodel/${out.model.id}`);
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
              {info.manifest.exported_at && <span className="quiet"> on {new Date(info.manifest.exported_at).toLocaleString()}</span>}
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
function FrameworkMoveDialog({ m, onClose }) {
  const { data: roots } = useApi("/api/v1/models?kind=template&archived=false");
  const [target, setTarget] = useState("");
  const [map, setMap] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mode, setMode] = useState("copy");
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
      const out = await post(`/api/v1/models/${m.id}/framework-move`, { target, mode, map, name: mode === "copy" ? name.trim() : null });
      refreshAll();
      onClose();
      go(`/metamodel/${out.model.id}`);
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
          </>
        )}
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ delete, archive, library actions
function DeleteDialog({ m, onClose }) {
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

function PromoteDialog({ m, onClose }) {
  const [name, setName] = useState(m.name);
  const [version, setVersion] = useState(m.version_label || "1.0");
  const [industry, setIndustry] = useState(m.industry || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function promote() {
    setBusy(true); setError("");
    try {
      const out = await post(`/api/v1/models/${m.id}/promote`, { name: name.trim(), version_label: version, industry });
      refreshAll();
      onClose();
      go(`/metamodel/${(out.model || out).id}`);
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Promote ${m.name} to the library`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || !name.trim()} onClick={promote}>{busy ? "Promoting..." : "Promote"}</button></>}>
      <div className="ed-form">
        <p>A copy of this model, its metamodel and content, becomes a published library model that everyone can start from. This model stays as it is.</p>
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
  async function download(format) {
    setOpen(false); setBusy("Downloading"); setError("");
    try { await apiDownload(`/api/v1/models/${m.id}/package?format=${format}`, `${m.name}.${format}`); }
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
      needsRole(CREATE_ROLES) + (m.kind === "project" ? ` (or Model Admin of ${m.name}, for a child of it)` : "")],
    ["Download package (zip)", () => download("zip"), true, "One zip: manifest, metamodel (JSON) and the content as CSV files, to upload here or elsewhere"],
    ["Download as Excel", () => download("xlsx"), true, "One workbook: the metamodel and each entity type on its own sheet; it can be changed and uploaded again"],
    ["Download the metamodel (JSON)", spec, true, "The metamodel as one document, to give an AI assistant or upload as a metamodel draft"],
    ["Move to another framework...", () => setDialog("move"), admin && m.kind === "project" && !m.is_locked,
      "Put this model on another root metamodel, for example a newer framework version",
      m.kind !== "project" ? "Only project models move to another framework; create a model from this one first"
        : m.is_locked ? `${m.name} is locked` : adminWhy],
    ["-"],
    ["Promote to the library...", () => setDialog("promote"), curator && m.kind === "project", "A copy of this model becomes a library model everyone can start from",
      m.kind !== "project" ? "Only project models are promoted; this one is already a library model" : libWhy],
    ["Publish in the library", () => act("publish", "Publishing"), curator && library && m.library_state === "building", "Everyone can see it and start from it; it becomes read-only",
      !library ? "Only library models and root metamodels are published; promote a project model instead"
        : m.library_state !== "building" ? `Already ${m.library_state}` : libWhy],
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
      {dialog === "move" && <FrameworkMoveDialog m={m} onClose={close} />}
      {dialog === "delete" && <DeleteDialog m={m} onClose={close} />}
      {dialog === "promote" && <PromoteDialog m={m} onClose={close} />}
    </span>
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
    return <div className="lock-banner">Not yet published in the library: only its makers and Library Admins see it. A Library Admin publishes it from Actions when it is ready.</div>;
  }
  if (m.library_state === "withdrawn") {
    return <div className="lock-banner content">Withdrawn from the library: nobody can start a new model from it. Models already built on it keep working.</div>;
  }
  return null;
}

// ------------------------------------------------------------------ metamodel drafts (D115, D120)
const DRAFT_STATUS = { draft: "Waiting for review", applied: "Applied", rejected: "Rejected" };

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
        (start_metamodel_draft, draft_set_item, draft_replace), or uploaded here as a metamodel JSON file. Nothing changes
        until someone with the rights applies it: a new root metamodel (Model Creators) or changes to a model (its Model Admin).
      </p>
      <div className="toolbar">
        <div className="seg small">
          {[["draft", "Waiting"], ["applied", "Applied"], ["rejected", "Rejected"], ["", "All"]].map(([k, l]) => (
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
            <thead><tr><th>Draft</th><th>For</th><th>Contents</th><th>Checks</th><th>By</th><th>Status</th><th>Changed</th></tr></thead>
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
                    <td>{DRAFT_STATUS[d.status] || d.status}</td>
                    <td className="quiet">{new Date(d.modified_at).toLocaleString()}</td>
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
      } catch { setError("That file is not JSON: a metamodel file is the JSON a model's Actions > Download the metamodel gives."); }
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

export function DraftPage({ id }) {
  const { data: d, error } = useApi(`/api/v1/metamodel-drafts/${id}`);
  const [section, setSection] = useState("entity_types");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [apply, setApply] = useState(false);
  const [reject, setReject] = useState(false);
  if (error) return <section><p className="status bad">{error}</p><a href="#/metamodel/drafts">All drafts</a></section>;
  if (!d) return <section><p>Loading...</p></section>;
  const open = d.status === "draft";
  const may = d.kind === "root" ? (can("models.create") || can("library.curate")) : canOn(d.target_model_id, "model.metamodel");
  const mayWhy = d.kind === "root" ? needsRole(["model-creator", "library-admin"]) : needsRole("model-admin", d.target_model);
  const errors = d.checks.filter((c) => c.level === "error");
  const items = d.spec[section] || [];

  async function remove(code) {
    setBusy(code); setMsg("");
    try { await post(`/api/v1/metamodel-drafts/${id}/edit`, { action: "remove", section, code }); refreshAll(); }
    catch (e) { setMsg(e.message); }
    setBusy("");
  }
  function downloadJson() {
    const blob = new Blob([JSON.stringify(d.spec, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${d.name}.json`;
    a.click();
  }

  return (
    <section className="model-page">
      <p className="lineage"><a href="#/metamodel/drafts">Metamodel drafts</a> /</p>
      <div className="model-head">
        <h1>{d.name}</h1>
        <span className={`rchip ${open ? "on" : ""}`}>{DRAFT_STATUS[d.status]}</span>
        <button onClick={downloadJson} title="The draft's metamodel as one JSON document">⬇ JSON</button>
        <button className="primary" disabled={!open || !may || errors.length > 0} onClick={() => setApply(true)}
          title={!open ? `This draft was ${d.status}` : !may ? `Applying: ${mayWhy}` : errors.length ? "Fix the errors first: remove or correct the items the checks name" : "Make the new root metamodel, or publish the changes as one metamodel version"}>Apply...</button>
        <button disabled={!open || !may} onClick={() => setReject(true)}
          title={!open ? `This draft was ${d.status}` : !may ? `Rejecting: ${mayWhy}` : "Close the draft without applying it, saying why"}>Reject...</button>
      </div>
      <p className="quiet">
        {d.kind === "root" ? <>A new root metamodel{d.base_model && <> starting from {d.base_model}</>}</> : <>Changes to <a href={`#/metamodel/${d.target_model_id}`}>{d.target_model}</a></>}
        {" · "}by {d.proposed_by} {d.proposed_via === "mcp" ? "through an AI assistant (MCP)" : `(${d.proposed_via})`} · changed {new Date(d.modified_at).toLocaleString()}
        {d.decided_by && <> · {d.status} by {d.decided_by} on {new Date(d.decided_at).toLocaleString()}</>}
        {d.applied_model_id && <> · <a href={`#/metamodel/${d.applied_model_id}`}>{d.applied_model}</a></>}
      </p>
      {d.note && <p className="lib-desc">{d.note}</p>}
      {open && !may && <p className="quiet">You can look at this draft. {mayWhy}</p>}
      {msg && <p className="status bad">{msg}</p>}

      <div className={errors.length ? "removals" : "impact"} style={{ margin: "8px 0" }}>
        <b>Checks:</b> {d.checks.length ? `${errors.length} errors, ${d.checks.length - errors.length} notes` : <span className="all-pass">everything passes</span>}
        {d.checks.length > 0 && <ul className="impact-list">{d.checks.map((c, i) => <li key={i}>{c.level === "error" ? "✖" : "⚠"} {c.where}: {c.message}</li>)}</ul>}
      </div>

      {(d.differences || []).length > 0 && (
        <details className="compare">
          <summary><b>{d.differences.length} differences</b> from {d.kind === "root" ? d.base_model || "the start" : `${d.target_model} now`}</summary>
          <Differences list={d.differences} />
        </details>
      )}

      <div className="tabs" role="tablist">
        {SECTIONS.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={section === k} className={section === k ? "tab on" : "tab"} onClick={() => setSection(k)}>{l} <span className="quiet">{d.counts[k]}</span></button>
        ))}
      </div>
      <div className="tab-panel">
        {!items.length ? <p className="quiet">None.</p> : (
          <div className="table-wrap">
            <table className="grid-table">
              <thead><tr><th>{section === "allowed" || section === "rules" ? "#" : "Code"}</th><th>Name</th><th>Details</th><th /></tr></thead>
              <tbody>
                {items.map((x, i) => {
                  const key = section === "allowed" || section === "rules" ? String(i) : x.code;
                  return (
                    <tr key={key}>
                      <td className="quiet">{section === "allowed" || section === "rules" ? i + 1 : x.code}</td>
                      <td>{itemText(section, x)}</td>
                      <td className="quiet">{itemMore(section, x)}</td>
                      <td className="row-actions"><button className="small" disabled={!open || !may || busy === key} onClick={() => remove(key)}
                        title={!open ? `This draft was ${d.status}` : !may ? `Changing the draft: ${mayWhy}` : section === "entity_types" ? "Take it out of the draft, with its allowed relationships and rules" : section === "relationship_types" ? "Take it out of the draft, with its allowed relationships" : section === "attributes" ? "Take it out of the draft, from every type and rule" : "Take it out of the draft"}>Remove</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {apply && <ApplyDraftDialog d={d} onClose={() => setApply(false)} />}
      {reject && <RejectDraftDialog d={d} onClose={() => setReject(false)} />}
    </section>
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
      const out = await post(`/api/v1/metamodel-drafts/${d.id}/apply`, d.kind === "root"
        ? { name: name.trim(), version_label: version, create_model: model.trim() || null }
        : { remove_missing: removeMissing });
      refreshAll();
      onClose();
      const to = out.model?.id || out.draft?.applied_model_id;
      if (to) go(`/metamodel/${to}`);
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Apply ${d.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || (d.kind === "root" && !name.trim())} onClick={go2}>{busy ? "Applying..." : "Apply"}</button></>}>
      <div className="ed-form">
        {d.kind === "root" ? <>
          <p>A new root metamodel is created under Root with this metamodel. You become its Model Admin.</p>
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

function RejectDraftDialog({ d, onClose }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function reject() {
    setBusy(true); setError("");
    try { await post(`/api/v1/metamodel-drafts/${d.id}/reject`, { reason }); refreshAll(); onClose(); }
    catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <Modal title={`Reject ${d.name}`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="danger" disabled={busy} onClick={reject}>Reject</button></>}>
      <div className="ed-form">
        <Field label="Why" hint="(shown to whoever made it)"><textarea value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        {error && <p className="status bad">{error}</p>}
      </div>
    </Modal>
  );
}

