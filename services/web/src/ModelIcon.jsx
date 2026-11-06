// Model icons (D247): a model's icon from the built-in library or uploaded for it alone, shown wherever the model is
// named; the picker used when creating a model and by its Model Admins (Actions > Icon).
import { useEffect, useRef, useState } from "react";
import { apiBlobUrl, apiFetch, apiUpload } from "./auth";
import { ICON_COLOURS, ICON_NAMES, MODEL_ICONS } from "./modelIcons";

const uploads = new Map();   // model id + version -> object URL (or a promise of one), fetched once per page

export function LibraryIcon({ name, size = 18, colour = "currentColor", title }) {
  const d = MODEL_ICONS[name];
  if (!d) return null;
  return (
    <svg className="model-icon lib" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={colour} strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" role="img" aria-label={title || name}>
      {title && <title>{title}</title>}<path d={d} />
    </svg>
  );
}

function useUpload(m) {
  const key = m && m.icon === "upload" ? `${m.id}:${m.icon_version || 0}` : null;
  const hit = key ? uploads.get(key) : null;
  const [url, setUrl] = useState(typeof hit === "string" ? hit : null);
  useEffect(() => {
    if (!key) return undefined;
    let live = true;
    let p = uploads.get(key);
    if (!p) { p = apiBlobUrl(`/api/v1/models/${m.id}/icon`); uploads.set(key, p); }
    Promise.resolve(p).then((u) => { uploads.set(key, u); if (live) setUrl(u); }).catch(() => uploads.delete(key));
    return () => { live = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return url;
}

// the model's icon, or nothing when it has none (the kind mark beside it still says what it is)
export function ModelIcon({ m, size = 18 }) {
  const url = useUpload(m);
  if (!m?.icon) return null;
  if (m.icon === "upload") {
    return url ? <img className="model-icon up" src={url} width={size} height={size} alt="" title={`${m.name}: its own icon`} />
      : <span className="model-icon" style={{ width: size, height: size }} />;
  }
  return <LibraryIcon name={m.icon.replace(/^lib:/, "")} size={size} colour={ICON_COLOURS[m.kind] || ICON_COLOURS.project} title={m.name} />;
}

// pick from the library, or choose an image to upload (sent by the caller once the model exists)
export function IconPicker({ value, onChange, file, onFile, kind = "project" }) {
  const input = useRef(null);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState(null);
  useEffect(() => {
    if (!file) { setPreview(null); return undefined; }
    const u = URL.createObjectURL(file);
    setPreview(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  function pick(f) {
    setErr("");
    if (!f) return;
    if (!/^image\/(png|jpeg|webp|svg\+xml)$/.test(f.type)) { setErr("PNG, JPEG, WebP or SVG only."); return; }
    if (f.size > 256 * 1024) { setErr(`${Math.round(f.size / 1024)} KB: the icon may be up to 256 KB.`); return; }
    onFile(f);
  }
  return (
    <div className="icon-picker">
      <div className="icon-grid" role="listbox" aria-label="Icon library">
        {ICON_NAMES.map((n) => (
          <button key={n} type="button" role="option" aria-selected={!file && value === n} className={!file && value === n ? "on" : ""}
            title={n} onClick={() => { onFile(null); onChange(n); }}>
            <LibraryIcon name={n} size={22} colour={ICON_COLOURS[kind] || ICON_COLOURS.project} />
          </button>
        ))}
        <button type="button" className={file ? "on upload" : "upload"} title="Upload your own (PNG, JPEG, WebP or SVG, up to 256 KB): for this model only"
          onClick={() => input.current?.click()}>
          {preview ? <img src={preview} width={22} height={22} alt="" /> : "⬆"}
        </button>
      </div>
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden onChange={(e) => pick(e.target.files?.[0])} />
      <span className="quiet small">{file ? `Your own: ${file.name} (${Math.round(file.size / 1024)} KB), for this model only` : `From the library: ${value}`}</span>
      {err && <span className="status bad small"> {err}</span>}
    </div>
  );
}

// after a model is created, or from its page: save what was picked
export async function saveIcon(modelId, name, file) {
  if (file) {
    const form = new FormData();
    form.append("file", file);
    return apiUpload(`/api/v1/models/${modelId}/icon`, form);
  }
  return apiFetch(`/api/v1/models/${modelId}/icon`, { method: "PUT", body: JSON.stringify({ library: name || null }) });
}
