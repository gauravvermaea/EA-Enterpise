// "Open in draw.io" (owner, 11 Nov 2026, D585): a generated picture, a canvas or the metamodel diagram in our own
// draw.io (with our plugin, stencil and ArchiMate notation), full screen in a tab of its own (D411), as a scratch view.
// It is kept nowhere and changes nothing: it opens read only (look, zoom, export; draw.io's File > Export as too), so
// nothing on it can touch the model (D408, D413). A picture of a model has the drawn view's panels below it, read only
// (R2.7): the objects on it, and the selected one's properties, relationships and allowed relationships. To change it, Save as a drawn view (those who may draw on the model):
// the tab then becomes that drawn view. The picture comes from drawioScratch.js (#/drawio/open/<key>).
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "./auth";
import { useApi } from "./ModelViews";
import { NewDrawnView, PicturePanels, dataUriToBlob, mayDraw, pngToPdf } from "./DrawnView";
import { saveBlob } from "./exporting";
import { forgetScratch, takeScratch } from "./drawioScratch";

const LEAVE = "Leave without saving? This picture isn't kept.";
// a picture of no model, or a model whose setup cannot be read: draw.io and our plugin, nothing of a metamodel
const PLAIN_SETUP = { eax: "setup", types: {}, domains: [], allowed: [], relationshipTypes: {} };
const safeName = (t) => String(t || "picture").replace(/[\\/:*?"<>|]+/g, "-").trim() || "picture";

export function ScratchDrawioFullScreen({ scratchKey }) {
  const [got] = useState(() => takeScratch(scratchKey));
  useEffect(() => { document.body.classList.add("drawn-full-body"); return () => document.body.classList.remove("drawn-full-body"); }, []);
  if (!got) {
    return (
      <div className="drawn-full"><div className="drawn-page full scratch-gone">
        <h2>This picture is no longer here</h2>
        <p>A picture opened in draw.io is kept nowhere: once its tab is closed it is gone. Open it again from where it was made.</p>
        <p><a href="#/">EA Explorer</a></p>
      </div></div>
    );
  }
  return <div className="drawn-full"><ScratchDrawio scratchKey={scratchKey} pic={got.pic} reloadable={got.reloadable} /></div>;
}

function ScratchDrawio({ scratchKey, pic, reloadable }) {
  const model = pic.model || null;
  const { data: m } = useApi(model ? `/api/v1/models/${model}` : null);
  const [setup, setSetup] = useState(model ? null : PLAIN_SETUP);
  const [phase, setPhase] = useState("starting");
  const [dlg, setDlg] = useState(null);
  const [toast, setToast] = useState(null);
  const [selected, setSelected] = useState(null);   // what is selected on the picture, for the panels (R2.7)
  const frame = useRef(null);
  const st = useRef({ ready: false, loaded: false, setupSent: false, guard: true, exportWaiting: null, v: Date.now() });
  const may = !!model && !!m && mayDraw(model, m);
  const say = (text, ok = true) => setToast({ text, ok, at: Date.now() });
  const post = useCallback((msg) => { frame.current?.contentWindow?.postMessage(JSON.stringify(msg), "*"); }, []);

  useEffect(() => { document.title = `${pic.title} · draw.io · EA Explorer`; }, [pic.title]);
  useEffect(() => {
    if (!model) return undefined;
    let live = true;
    apiFetch(`/api/v1/models/${model}/drawn-views/setup`).then((s) => live && setSetup(s)).catch(() => live && setSetup(PLAIN_SETUP));
    return () => { live = false; };
  }, [model]);

  const trySetup = useCallback(() => {
    const s = st.current;
    if (!s.ready || !s.loaded || s.setupSent || !setup) return;
    s.setupSent = true;
    // as made: its colours (a heat map's), and its labels when its boxes are not entities (the metamodel's types, a canvas)
    post({ ...setup, readOnly: true, keepLook: true, plainLabels: !model || !!pic.plain, title: pic.title });
    setPhase("ready");
  }, [setup, post, pic.title, pic.plain, model]);
  useEffect(() => { trySetup(); }, [trySetup]);

  // leaving: the picture is kept nowhere
  useEffect(() => {
    const before = (e) => { if (st.current.guard) { e.preventDefault(); e.returnValue = LEAVE; } };
    const here = window.location.hash;
    const onHash = () => {
      const s = st.current;
      if (!s.guard || s.leaving || window.location.hash === here) return;
      if (window.confirm(LEAVE)) { s.guard = false; forgetScratch(scratchKey); return; }
      s.leaving = true; window.location.hash = here; setTimeout(() => { s.leaving = false; }, 0);
    };
    window.addEventListener("beforeunload", before);
    window.addEventListener("hashchange", onHash);
    return () => { window.removeEventListener("beforeunload", before); window.removeEventListener("hashchange", onHash); };
  }, [scratchKey]);

  useEffect(() => {
    function handle(ev) {
      if (!frame.current || ev.source !== frame.current.contentWindow) return;
      let msg; try { msg = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data; } catch { return; }
      if (!msg || !msg.event) return;
      const s = st.current;
      switch (msg.event) {
        case "configure": post({ action: "configure", config: { defaultLibraries: "", enabledLibraries: [], compressXml: false } }); break;
        case "init": post({ action: "load", xml: pic.xml, autosave: 0, title: pic.title }); break;
        case "load": s.loaded = true; trySetup(); break;
        case "eax-ready": s.ready = true; trySetup(); break;
        case "export": if (s.exportWaiting) { const f = s.exportWaiting; s.exportWaiting = null; f(msg.data); } break;
        case "eax-open": if (model && !pic.plain && msg.entity) window.open(`#/metamodel/${model}/entity/${msg.entity}`, "_blank"); break;
        case "eax-exported-drawio": say(`Downloaded ${msg.name}.`); break;
        case "eax-selected": setSelected(msg.cell && (msg.entity || msg.relationship || msg.relType) ? msg : null); break;
        default: break;
      }
    }
    window.addEventListener("message", handle);
    return () => window.removeEventListener("message", handle);
  });

  async function download(format) {
    const name = safeName(pic.title);
    try {
      if (format === "drawio") { saveBlob(new Blob([pic.xml], { type: "application/xml" }), `${name}.drawio`); return; }
      const data = await new Promise((resolve) => { st.current.exportWaiting = resolve; post({ action: "export", format: format === "pdf" ? "png" : format }); });
      saveBlob(format === "pdf" ? await pngToPdf(data) : dataUriToBlob(data), `${name}.${format}`);
    } catch (e) { say(e.message, false); }
  }
  function close() {
    if (st.current.guard && !window.confirm(LEAVE)) return;
    st.current.guard = false; forgetScratch(scratchKey);
    window.close();
    setTimeout(() => { window.location.hash = "#/"; }, 300);           // a tab the browser will not close
  }

  // no draw.io Save button: nothing here is saved (the toolbar's Save as a drawn view keeps it)
  const src = `/drawio/index.html?embed=1&proto=json&configure=1&eax=1&spin=1&libraries=1&noExitBtn=1&noSaveBtn=1&saveAndExit=0&eaxv=${st.current.v}`;
  const off = phase !== "ready";
  return (
    <div className="drawn-page full scratch">
      <div className="drawn-head">
        {model && <span className="drawn-crumb small"><a href={`#/metamodel/${model}/views/custom`} target="_blank" rel="noopener"
          title="The model's Views tab, in a new tab">{m?.name || "Model"}</a> ›</span>}
        <h2>{pic.title}</h2>
        <span className="rag off" title="Opened from a picture to look at and export: kept nowhere, it does not follow the model. Save as a drawn view to keep and change it">not saved</span>
        <span className="er-spacer" />
        {may && <button className="primary" disabled={off} onClick={() => setDlg("save")}
          title="Keep this picture, with its layout, as a drawn view of the model: change it there and save versions">Save as a drawn view</button>}
        <button disabled={off} onClick={() => download("drawio")} title="Download the picture as a draw.io file (yours to keep: it does not follow the model)">Download .drawio</button>
        <button disabled={off} onClick={() => download("png")} title="Download the picture as a PNG image">PNG</button>
        <button disabled={off} onClick={() => download("svg")} title="Download the picture as an SVG drawing">SVG</button>
        <button disabled={off} onClick={() => download("pdf")} title="Download the picture as a one-page PDF">PDF</button>
        <button onClick={close} title="Close this tab: the picture is kept nowhere, so it asks first">Close</button>
      </div>
      {!reloadable && <div className="status warn drawn-banner">This picture is too big to keep for a reload of this tab: reloading loses it. Download it or save it as a drawn view to keep it.</div>}
      {toast && <p className={`status ${toast.ok ? "ok" : "bad"} drawn-toast`} key={toast.at}>{toast.text} <button className="linkish" onClick={() => setToast(null)}>✕</button></p>}
      <div className="drawn-body">
        <div className="drawn-row">
          <div className="drawn-frame">
            <iframe ref={frame} title="The picture in draw.io" src={src} />
            {off && <div className="drawn-wait">Starting draw.io…</div>}
          </div>
        </div>
        {/* R2.7: the objects on the picture and their properties, relationships and allowed relationships, read only */}
        {model && !pic.plain && setup && !off && <PicturePanels model={model} setup={setup} xml={pic.xml} selected={selected} post={post} />}
      </div>
      {dlg === "save" && <NewDrawnView model={model} views={[]} xml={pic.xml} source="generated" sourceNote={pic.title} sameTab
        onSaved={() => { st.current.guard = false; forgetScratch(scratchKey); }} onClose={() => setDlg(null)} />}
    </div>
  );
}
