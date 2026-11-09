// Business Model Canvases (owner, 9 Nov 2026, D344): a tab of the project, standing on its own (it touches nothing
// else in the project or its models). Any number of canvases: current state, target state, working copies and
// scenarios, draft or agreed. In a working copy changes are marked by hand (added green, changed amber with the old
// text crossed out, removed crossed out in red); "Make a clean canvas" makes a new one without the marks. Two canvases
// compare block by block, and the comparison becomes a working copy to adjust and clean up into a new target. A canvas
// copies to another project, keeps the documents used to build it, and exports to PDF, PowerPoint and draw.io.
import { useState } from "react";
import { apiBlobUrl, apiDownload, apiFetch, apiUpload } from "./auth";
import { openDrawioXml } from "./exporting";
import { refreshAll, useApi } from "./ModelViews";

const KINDS = { current: "Current state", target: "Target state", working: "Working copy", scenario: "Scenario" };
const STATUSES = { draft: "Draft", agreed: "Agreed" };
// the classic layout: five columns, two of them split, costs and revenue below
const LAYOUT = [
  ["key_partners", "1 / 1 / 3 / 3"], ["key_activities", "1 / 3 / 2 / 5"], ["key_resources", "2 / 3 / 3 / 5"],
  ["value_propositions", "1 / 5 / 3 / 7"], ["customer_relationships", "1 / 7 / 2 / 9"], ["channels", "2 / 7 / 3 / 9"],
  ["customer_segments", "1 / 9 / 3 / 11"], ["cost_structure", "3 / 1 / 4 / 6"], ["revenue_streams", "3 / 6 / 4 / 11"],
];
const when = (v) => (v ? new Date(v).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "");
const MARK = { added: "added", changed: "changed", removed: "removed" };

function ItemEditor({ item, onSave, onCancel, busy }) {
  const [t, setT] = useState(item?.text || "");
  const [n, setN] = useState(item?.note || "");
  return (
    <div className="bmc-edit">
      <input autoFocus value={t} onChange={(e) => setT(e.target.value)} placeholder="The item" aria-label="Item"
        onKeyDown={(e) => { if (e.key === "Enter" && t.trim()) onSave({ text: t, note: n }); if (e.key === "Escape") onCancel(); }} />
      <input value={n} onChange={(e) => setN(e.target.value)} placeholder="A note (optional)" aria-label="Note" />
      <div className="row-gap small">
        <button className="primary small" disabled={!t.trim() || busy} onClick={() => onSave({ text: t, note: n })}>Save</button>
        <button className="linkish" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

// one item on a canvas (or a row of a comparison)
function Sticky({ it, state, may, working, onEdit, onRemove, onRestore }) {
  const s = state || it.mark || "";
  return (
    <div className={`bmc-item ${MARK[s] || ""}`} title={it.note || ""}>
      {it.was_text && <div className="bmc-was">{it.was_text}</div>}
      <div className="bmc-text">{it.text}</div>
      {it.note && <div className="bmc-note">{it.note}</div>}
      {may && (
        <div className="bmc-tools">
          {s !== "removed" && <button className="linkish" onClick={onEdit} title="Change it">✎</button>}
          {(s === "removed" || s === "changed") && working
            ? <button className="linkish" onClick={onRestore} title="Undo the mark">↺</button>
            : s !== "removed" && <button className="linkish" onClick={onRemove} title={working ? "Cross it out" : "Remove it"}>×</button>}
        </div>
      )}
    </div>
  );
}

function Board({ blocks, data, render, adding }) {
  const label = Object.fromEntries(blocks.map((b) => [b.key, b]));
  return (
    <div className="bmc-grid">
      {LAYOUT.map(([k, area]) => (
        <section key={k} className="bmc-block" style={{ gridArea: area }}>
          <h4 title={label[k]?.question}>{label[k]?.label}</h4>
          {(data[k] || []).map((it, i) => render(k, it, i))}
          {adding && adding(k)}
        </section>
      ))}
    </div>
  );
}

function NewCanvas({ onMade, onCancel, busy, act, url }) {
  const [f, setF] = useState({ name: "", kind: "current", description: "" });
  return (
    <div className="goal-box">
      <div className="own-row">
        <input placeholder="Name, e.g. Claims business model 2026" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} aria-label="Canvas name" />
        <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} aria-label="Kind">
          {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      </div>
      <input className="wide" placeholder="What it is for (optional)" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} aria-label="Description" />
      <div className="row-gap">
        <button className="primary" disabled={!f.name.trim() || busy}
          onClick={() => act(() => apiFetch(`${url}/canvases`, { method: "POST", body: JSON.stringify(f) })).then((r) => r && onMade(r.id))}>Make the canvas</button>
        <button className="linkish" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

function Documents({ p, c, may, act, url, setMsg }) {
  const [file, setFile] = useState(null);
  const [note, setNote] = useState("");
  const [pick, setPick] = useState("");
  const have = new Set(c.documents.map((d) => d.id));
  const others = (p.documents || []).filter((d) => (d.file_name || d.title) && !have.has(d.id));
  const base = `${url}/canvases/${c.id}`;
  return (
    <div className="bmc-docs">
      <h4>Documents behind this canvas</h4>
      {!c.documents.length && <p className="quiet small">None yet: add what was used to build it (workshop notes, research, strategy papers).</p>}
      <ul className="small">{c.documents.map((d) => (
        <li key={d.id}><button className="linkish" onClick={() => apiDownload(`${url}/documents/${d.id}`, d.file_name).catch((e) => setMsg(e.message))}>📄 {d.title || d.file_name}</button>
          {d.note && <span className="quiet"> · {d.note}</span>}<span className="quiet"> · {d.added_by}, {when(d.added_at)}</span>
          {may && <> · <button className="linkish" onClick={() => act(() => apiFetch(`${base}/documents/${d.id}`, { method: "DELETE" }))}>take off</button></>}</li>))}</ul>
      {may && (
        <div className="row-gap small bmc-docs-add">
          <input type="file" onChange={(e) => setFile(e.target.files[0] || null)} aria-label="Upload a document" />
          <span className="quiet">or</span>
          <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="A document of the project">
            <option value="">a document of the project…</option>
            {others.map((d) => <option key={d.id} value={d.id}>{d.title || d.file_name}</option>)}
          </select>
          <input placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Document note" />
          <button disabled={!file && !pick} onClick={() => act(() => {
            if (file) { const fd = new FormData(); fd.append("file", file); fd.append("note", note); return apiUpload(`${base}/documents`, fd); }
            return apiFetch(`${base}/documents`, { method: "POST", body: JSON.stringify({ document: pick, note }) });
          }).then((ok) => { if (ok) { setFile(null); setPick(""); setNote(""); } })}>Add</button>
        </div>
      )}
    </div>
  );
}

export function CanvasTab({ p }) {
  const url = `/api/v1/projects/${p.id}`;
  const { data: list } = useApi(`${url}/canvases`);
  const { data: plist } = useApi("/api/v1/projects");
  const params = new URLSearchParams((window.location.hash.split("?")[1]) || "");
  const [sel, setSel] = useState(params.get("c") || "");
  const [cmpWith, setCmpWith] = useState("");
  const [making, setMaking] = useState(false);
  const [editing, setEditing] = useState(null);        // item id, or "new:<block>"
  const [dialog, setDialog] = useState("");           // rename | copy-to | clean | working
  const [form, setForm] = useState({});
  const [hist, setHist] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const canvases = list?.canvases || [];
  const current = sel || canvases[0]?.id || "";
  const { data: c } = useApi(current ? `${url}/canvases/${current}` : null);
  const { data: cmp } = useApi(current && cmpWith ? `${url}/canvases/${current}/compare/${cmpWith}` : null);
  const may = p.may_contribute && !p.frozen;
  const blocks = list?.blocks || [];
  async function act(fn) {
    setBusy(true); setMsg("");
    try { const r = await fn(); setMsg(r?.message || ""); setEditing(null); refreshAll(); return r || true; }
    catch (e) { setMsg(e.message); return false; } finally { setBusy(false); }
  }
  const choose = (id) => { setSel(id); setCmpWith(""); setDialog(""); setEditing(null); setHist(false); };
  const made = (id) => { setMaking(false); setDialog(""); setCmpWith(""); if (id) setSel(id); };
  const exp = (fmt, other) => {
    const q = `${url}/canvases/${current}/export?format=${fmt}${other ? `&compare=${other}` : ""}`;
    const title = other && cmp ? `${cmp.a.name} to ${cmp.b.name}` : c?.name || "canvas";
    if (fmt === "drawio") {
      openDrawioXml(title, apiBlobUrl(q).then((u) => fetch(u)).then((r) => r.text()));
      return;
    }
    apiDownload(q, `${title}.${fmt}`).catch((e) => setMsg(e.message));
  };
  const working = c?.kind === "working";
  return (
    <div className="bmc-tab">
      <p className="quiet small">Business Model Canvases for this project. They stand on their own: nothing here changes the project's models or
        documents. Make a current state and a target state, compare them, or make a working copy and mark changes by hand
        (added green, changed amber, removed crossed out in red), then make a clean canvas from it.</p>
      <div className="bmc-list">
        {canvases.map((x) => (
          <button key={x.id} className={`bmc-card${x.id === current ? " on" : ""}`} onClick={() => choose(x.id)}>
            <b>{x.name}</b>
            <span className="small"><span className={`kind ${x.kind}`}>{KINDS[x.kind]}</span> · {STATUSES[x.status]} · {x.items} items{x.marks ? ` · ${x.marks} marks` : ""}</span>
            {x.source_name && <span className="small quiet">from {x.source_name}</span>}
          </button>
        ))}
        {may && !making && <button className="bmc-card new" onClick={() => setMaking(true)}>＋ New canvas</button>}
      </div>
      {making && <NewCanvas url={url} act={act} busy={busy} onMade={made} onCancel={() => setMaking(false)} />}
      {!canvases.length && !making && <p className="quiet">No canvas yet.{may ? " Make the first: a current state is a good start." : ""}</p>}

      {c && !cmpWith && <>
        <div className="bmc-head">
          <div>
            <h3>{c.name} <span className={`kind ${c.kind}`}>{KINDS[c.kind]}</span> <span className={`chip ${c.status}`}>{STATUSES[c.status]}</span></h3>
            <div className="small quiet">{c.description && <>{c.description} · </>}
              {c.source && <>made from <button className="linkish" onClick={() => choose(c.source.id)}>{c.source.name}</button> · </>}
              {!c.source && c.source_note && <>{c.source_note} · </>}{c.changed_by || c.created_by}, {when(c.changed_at || c.created_at)}</div>
          </div>
          <div className="row-gap small bmc-actions">
            {may && <button onClick={() => { setDialog("working"); setForm({ name: `${c.name} (working copy)` }); }}>Make a working copy</button>}
            {may && working && <button className="primary" onClick={() => { setDialog("clean"); setForm({ name: c.name.replace(/ \(working copy\)$/, "") + " (clean)", kind: "target" }); }}>Make a clean canvas…</button>}
            <select value="" onChange={(e) => e.target.value && setCmpWith(e.target.value)} aria-label="Compare with">
              <option value="">Compare with…</option>
              {canvases.filter((x) => x.id !== c.id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
            <select value="" onChange={(e) => e.target.value && exp(e.target.value)} aria-label="Export">
              <option value="">Export…</option><option value="pdf">PDF</option><option value="pptx">PowerPoint</option><option value="drawio">Open in draw.io</option>
            </select>
            {may && <select value="" onChange={(e) => { const v = e.target.value; if (!v) return;
              if (v === "rename") { setDialog("rename"); setForm({ name: c.name, description: c.description }); }
              else if (v === "copy-to") { setDialog("copy-to"); setForm({ project: "" }); }
              else if (v === "delete") act(() => apiFetch(`${url}/canvases/${c.id}`, { method: "DELETE" })).then((r) => r && setSel(""));
              else if (v.startsWith("kind:")) act(() => apiFetch(`${url}/canvases/${c.id}`, { method: "PUT", body: JSON.stringify({ kind: v.slice(5) }) }));
              else if (v.startsWith("status:")) act(() => apiFetch(`${url}/canvases/${c.id}`, { method: "PUT", body: JSON.stringify({ status: v.slice(7) }) }));
            }} aria-label="More">
              <option value="">More…</option>
              {c.status === "draft" ? <option value="status:agreed">Mark it agreed</option> : <option value="status:draft">Make it a draft again</option>}
              {Object.entries(KINDS).filter(([k]) => k !== c.kind).map(([k, v]) => <option key={k} value={`kind:${k}`}>Make it a {v.toLowerCase()}</option>)}
              <option value="rename">Rename or describe…</option>
              <option value="copy-to">Copy to another project…</option>
              <option value="delete">Remove this canvas</option>
            </select>}
            <button className="linkish" onClick={() => setHist(!hist)}>History ({c.history.length})</button>
          </div>
        </div>
        {dialog && (
          <div className="goal-box bmc-dialog">
            {(dialog === "working" || dialog === "clean" || dialog === "rename") &&
              <input className="wide" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} aria-label="New name" />}
            {dialog === "rename" && <input className="wide" value={form.description || ""} placeholder="What it is for"
              onChange={(e) => setForm({ ...form, description: e.target.value })} aria-label="Description" />}
            {dialog === "clean" && <>
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} aria-label="Kind of the clean canvas">
                {Object.entries(KINDS).filter(([k]) => k !== "working").map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              <p className="small quiet">A new canvas: the crossed-out items left out and the marks gone. This working copy stays as it is.</p></>}
            {dialog === "copy-to" && <select value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })} aria-label="To project">
              <option value="">the project to copy it to…</option>
              {(plist?.projects || []).filter((x) => x.id !== p.id && !x.base_kind).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>}
            <div className="row-gap">
              <button className="primary" disabled={busy || (dialog === "copy-to" ? !form.project : !(form.name || "").trim())} onClick={() => {
                const call = dialog === "rename" ? apiFetch(`${url}/canvases/${c.id}`, { method: "PUT", body: JSON.stringify(form) })
                  : apiFetch(`${url}/canvases/${c.id}/${dialog === "working" ? "copy" : dialog}`, { method: "POST", body: JSON.stringify(dialog === "working" ? { ...form, kind: "working" } : form) });
                act(() => call).then((r) => r && made(dialog === "copy-to" || dialog === "rename" ? null : r.id));
              }}>{{ working: "Make the working copy", clean: "Make the clean canvas", rename: "Save", "copy-to": "Copy it" }[dialog]}</button>
              <button className="linkish" onClick={() => setDialog("")}>Cancel</button>
            </div>
          </div>
        )}
        {working && <p className="small bmc-legend"><span className="bmc-key added">added</span> <span className="bmc-key changed">changed</span>{" "}
          <span className="bmc-key removed">removed</span> Changes here are marked; ↺ undoes a mark.</p>}
        <Board blocks={blocks} data={c.blocks}
          render={(k, it) => (editing === it.id
            ? <ItemEditor key={it.id} item={it} busy={busy} onCancel={() => setEditing(null)}
              onSave={(b) => act(() => apiFetch(`${url}/canvas-items/${it.id}`, { method: "PUT", body: JSON.stringify(b) }))} />
            : <Sticky key={it.id} it={it} may={may} working={working} onEdit={() => setEditing(it.id)}
              onRemove={() => act(() => apiFetch(`${url}/canvas-items/${it.id}`, { method: "DELETE" }))}
              onRestore={() => act(() => apiFetch(`${url}/canvas-items/${it.id}/restore`, { method: "POST" }))} />)}
          adding={may ? (k) => (editing === `new:${k}`
            ? <ItemEditor busy={busy} onCancel={() => setEditing(null)}
              onSave={(b) => act(() => apiFetch(`${url}/canvases/${c.id}/items`, { method: "POST", body: JSON.stringify({ ...b, block: k }) }))} />
            : <button className="linkish small bmc-add" onClick={() => setEditing(`new:${k}`)}>＋ add</button>) : null} />
        {hist && <ul className="small kq-history">{c.history.map((h, i) => <li key={i}><span className="quiet">{when(h.at)}</span> {h.username} {h.action}{h.note ? `: ${h.note}` : ""}</li>)}</ul>}
        <Documents p={p} c={c} may={may} act={act} url={url} setMsg={setMsg} />
      </>}

      {cmpWith && cmp && <>
        <div className="bmc-head">
          <div>
            <h3>{cmp.a.name} → {cmp.b.name}</h3>
            <div className="small"><span className="bmc-key added">{cmp.counts.added} added</span> <span className="bmc-key changed">{cmp.counts.changed} changed</span>{" "}
              <span className="bmc-key removed">{cmp.counts.removed} removed</span> <span className="quiet">{cmp.counts.same} the same</span></div>
          </div>
          <div className="row-gap small bmc-actions">
            {may && <button className="primary" onClick={() => act(() => apiFetch(`${url}/canvases/${cmp.a.id}/compare/${cmp.b.id}`, { method: "POST", body: "{}" }))
              .then((r) => r && made(r.id))}>Make a working copy of these changes</button>}
            <button onClick={() => { const a = cmp.a.id; setSel(cmp.b.id); setCmpWith(a); }}>Swap</button>
            <select value="" onChange={(e) => e.target.value && exp(e.target.value, cmpWith)} aria-label="Export the comparison">
              <option value="">Export…</option><option value="pdf">PDF</option><option value="pptx">PowerPoint</option><option value="drawio">Open in draw.io</option>
            </select>
            <button className="linkish" onClick={() => setCmpWith("")}>Close the comparison</button>
          </div>
        </div>
        <div className="bmc-diff"><Board blocks={blocks} data={cmp.blocks} render={(k, r, i) => <Sticky key={`${k}${i}`} it={r} state={r.state} may={false} />} /></div>
      </>}
      {msg && <p className="small status">{msg}</p>}
    </div>
  );
}
