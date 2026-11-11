// The industry packs' files (phase 39; owner 10 Nov 2026, D546 to D549): tiles to click and download on the library's
// Pack tab and on a reference model's page. The files are kept in the repository (library/industry-packs), put into
// Documents (Mayan) at start-up, and downloaded through the API: the book, the workbook, the metamodel Excel to study,
// the metamodel template, the ArchiMate 4 views, the Excel templates, the PowerPoints and the read-me.
import { useEffect, useState } from "react";
import { apiDownload, apiFetch, can } from "./auth";

const ICONS = { readme: "📄", book: "📘", workbook: "📗", metamodel: "📊", metamodel_template: "🧾", example_views: "🗺️",
  template: "📑", powerpoint: "📽️" };

export function size(n) {
  if (!n && n !== 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

async function download(f) {
  await apiDownload(f.download, f.file_name);
}

function FileRow({ f }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <li className="pack-file">
      <span className="pack-file-name" title={f.file_name}>{f.title}</span>
      <span className="quiet small">{f.type} · {size(f.file_size)}{f.versions > 1 ? ` · version ${f.versions}` : ""}</span>
      <button className="small" disabled={busy} title={`Download ${f.file_name}`}
        onClick={async () => { setBusy(true); setError(""); try { await download(f); } catch (e) { setError(e.message); } finally { setBusy(false); } }}>
        {busy ? "…" : "Download"}
      </button>
      {error && <span className="status error small">{error}</span>}
    </li>
  );
}

function LoadButton({ onDone }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  if (!can("library.curate")) return null;
  return (
    <span className="pack-load">
      <button className="small" disabled={busy}
        title="Load the industry packs shipped with EA Explorer (library/industry-packs) into Documents now: new and changed files only"
        onClick={async () => {
          setBusy(true); setMsg("");
          try { const out = await apiFetch("/api/v1/industry-packs/load", { method: "POST", body: JSON.stringify({ folder: "shipped" }) }); setMsg(out.message); onDone?.(); }
          catch (e) { setMsg(e.message); } finally { setBusy(false); }
        }}>{busy ? "Loading…" : "Load packs from the folder on the server"}</button>
      {msg && <span className="quiet small"> {msg}</span>}
    </span>
  );
}

// model: a library reference model's id (guid); compact: a smaller version for the model page
export function IndustryPackTiles({ model, compact = false }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [n, setN] = useState(0);
  useEffect(() => {
    let live = true;
    setData(null); setError("");
    apiFetch(`/api/v1/models/${model}/industry-pack`).then((d) => live && setData(d)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [model, n]);
  if (error) return <p className="status error">{error}</p>;
  if (!data) return <p className="quiet"><span className="spinner" aria-hidden="true" /> Reading the pack…</p>;
  if (!data.industry) return compact ? null : <p className="quiet">{data.message}</p>;
  return (
    <section className={`industry-pack${compact ? " compact" : ""}`} aria-label={`${data.name} industry pack`}>
      <div className="pack-head">
        <h3>{data.name} industry pack</h3>
        <span className="quiet small">{data.files} file{data.files === 1 ? "" : "s"} · {size(data.size)}</span>
        <LoadButton onDone={() => setN(n + 1)} />
      </div>
      <div className="pack-grid">
        {data.tiles.map((t) => (
          <div key={t.kind} className={`pack-tile ${t.state === "loaded" ? "loaded" : "not-loaded"}`}>
            <div className="pack-name"><span><span aria-hidden="true">{ICONS[t.kind] || "📄"}</span> {t.title}</span>
              {t.state !== "loaded" && <span className="phase">not loaded</span>}</div>
            {!compact && <p>{t.about}</p>}
            {t.files.length ? <ul className="pack-files">{t.files.map((f) => <FileRow key={f.id} f={f} />)}</ul>
              : <p className="quiet small">Not loaded yet. Ask an admin to run <code>eax packs load</code>.</p>}
          </div>
        ))}
      </div>
    </section>
  );
}
