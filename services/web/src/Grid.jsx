// A spreadsheet-style grid (build phase 7), used for entities, relationships and every part of the
// metamodel. Keyboard: arrows (Shift extends the selection), Enter or F2 edits, typing starts editing,
// Tab moves right, Escape cancels, Delete clears, Ctrl+C copies, Ctrl+V pastes from Excel (new rows are
// added below), Ctrl+Z undoes. Right-click for row actions. Changed cells are marked until saved; Save
// sends only the changed rows and shows each row's outcome. Large grids draw only the rows in view.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { downloadCsv } from "./exporting";

const ROW_H = 30;
const blankRow = () => ({});

function parseClipboard(text) {
  // tab-separated rows (what Excel and sheets copy), with quoted cells that may hold tabs or new lines
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i += 1; } else if (ch === '"') quoted = false; else cell += ch;
    } else if (ch === '"' && cell === "") quoted = true;
    else if (ch === "\t") { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += ch;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

const show = (v) => (v === null || v === undefined ? "" : typeof v === "boolean" ? (v ? "Yes" : "No") : Array.isArray(v) ? v.join(", ") : String(v));

function normalise(col, raw) {
  if (raw === null || raw === undefined) return "";
  const v = String(raw).trim();
  if (col.type === "bool") return /^(yes|true|1|y)$/i.test(v) ? "Yes" : /^(no|false|0|n)$/i.test(v) ? "No" : v;
  if (col.type === "select" && col.options && v) {
    const hit = col.options.find((o) => String(o).toLowerCase() === v.toLowerCase());
    return hit ?? v;
  }
  return v;
}

let newSeq = 0;
// the values someone changed in a row (and not yet saved)
function pick(it) {
  return Object.fromEntries(Object.keys(it.cur).filter((k) => show(it.cur[k]) !== show(it.orig[k])).map((k) => [k, it.cur[k]]));
}

function makeItems(rows, rowKey) {
  return rows.map((r) => ({ key: String(r[rowKey]), orig: r, cur: { ...r }, isNew: false, deleted: false, error: "", note: "" }));
}

export default function Grid({
  columns, rows, rowKey = "id", canEdit = true, why = "", onSave, allowAdd = true, allowDelete = true,
  name = "grid", toolbar = null, views = null, initialConfig = null, onConfig = null, emptyText = "No rows yet.",
  height = "64vh", deleteLabel = "Delete", saveNote = "",
  rowMark = null,    // (row) => a quick action shown on the left of a row, after its number (e.g. commit, D257)
  rowMenu = null,    // (row) => [{ label, onClick, disabled }] more right-click items for that row
}) {
  const [items, setItems] = useState(() => makeItems(rows, rowKey));
  const [active, setActive] = useState({ r: 0, c: 0 });
  const [anchor, setAnchor] = useState(null);
  const [editing, setEditing] = useState(null);   // { value }
  const [filter, setFilter] = useState(initialConfig?.filter || "");
  const [sort, setSort] = useState(initialConfig?.sort || null);   // { key, desc }
  const [hidden, setHidden] = useState(initialConfig?.hidden || []);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [menu, setMenu] = useState(null);
  const [scrollTop, setScrollTop] = useState(0);
  const undo = useRef([]);
  const box = useRef(null);
  const scroller = useRef(null);

  // fresh rows from the server: unsaved edits, new rows and rows marked for deletion are kept (another screen reading
  // again, a recheck of data quality, must never lose what someone is typing); everything else takes the new values
  useEffect(() => {
    setItems((old) => {
      const fresh = makeItems(rows, rowKey);
      const changed = new Map(old.filter((it) => !it.isNew && (it.deleted || it.error || Object.keys(it.cur).some((k) => show(it.cur[k]) !== show(it.orig[k]))))
        .map((it) => [it.key, it]));
      if (!changed.size && !old.some((it) => it.isNew)) return fresh;
      const merged = fresh.map((it) => (changed.has(it.key) ? { ...it, cur: { ...it.cur, ...pick(changed.get(it.key)) }, deleted: changed.get(it.key).deleted,
        error: changed.get(it.key).error || "" } : it));
      return [...merged, ...old.filter((it) => it.isNew)];
    });
  }, [rows]);
  useEffect(() => { onConfig?.({ filter, sort, hidden }); }, [filter, sort, hidden]);
  useEffect(() => {
    if (!initialConfig) return;
    setFilter(initialConfig.filter || ""); setSort(initialConfig.sort || null); setHidden(initialConfig.hidden || []);
  }, [initialConfig]);

  const cols = useMemo(() => columns.filter((c) => !hidden.includes(c.key)), [columns, hidden]);
  const view = useMemo(() => {
    const f = filter.trim().toLowerCase();
    let list = items.filter((it) => it.isNew || !f || cols.some((c) => show(it.cur[c.key]).toLowerCase().includes(f)));
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      const num = col?.type === "number";
      list = [...list].sort((a, b) => {
        if (a.isNew !== b.isNew) return a.isNew ? 1 : -1;
        const x = a.cur[sort.key], y = b.cur[sort.key];
        const cmp = num ? (Number(x) || 0) - (Number(y) || 0) : show(x).localeCompare(show(y), undefined, { numeric: true });
        return sort.desc ? -cmp : cmp;
      });
    }
    return list;
  }, [items, filter, sort, cols, columns]);

  const changed = items.filter((it) => it.deleted || it.isNew || columns.some((c) => !c.readOnly && show(it.cur[c.key]) !== show(it.orig[c.key])));
  const dirtyCount = changed.filter((it) => !(it.isNew && it.deleted)).length;
  const editable = (c, it) => canEdit && !c.readOnly && !(c.createOnly && !it.isNew) && !it.deleted;

  const setCells = useCallback((cells) => {
    // cells: [{ key (item), col, value }]
    if (!cells.length) return;
    setItems((list) => {
      const before = [];
      const next = list.map((it) => {
        const mine = cells.filter((x) => x.key === it.key);
        if (!mine.length) return it;
        const cur = { ...it.cur };
        mine.forEach((x) => { before.push({ key: it.key, col: x.col, value: it.cur[x.col] }); cur[x.col] = x.value; });
        return { ...it, cur, error: "" };
      });
      undo.current.push({ kind: "cells", before });
      return next;
    });
  }, []);

  function addRows(n, at = null, values = []) {
    const made = Array.from({ length: n }, (_, i) => {
      newSeq += 1;
      return { key: `new-${newSeq}`, orig: blankRow(), cur: { ...(values[i] || {}) }, isNew: true, deleted: false, error: "", note: "" };
    });
    setItems((list) => {
      if (at === null) return [...list, ...made];
      const idx = list.findIndex((x) => x.key === at);
      return [...list.slice(0, idx + 1), ...made, ...list.slice(idx + 1)];
    });
    undo.current.push({ kind: "add", keys: made.map((m) => m.key) });
    return made;
  }

  function selection() {
    const a = anchor || active;
    return { r0: Math.min(a.r, active.r), r1: Math.max(a.r, active.r), c0: Math.min(a.c, active.c), c1: Math.max(a.c, active.c) };
  }
  const inSel = (r, c) => { const s = selection(); return r >= s.r0 && r <= s.r1 && c >= s.c0 && c <= s.c1; };

  function move(dr, dc, extend = false) {
    if (!extend) setAnchor(null); else if (!anchor) setAnchor(active);
    // moving down from the last row starts a new row, as in a spreadsheet
    if (dr > 0 && !extend && active.r + dr >= view.length && allowAdd && canEdit && view.length && !view[view.length - 1].isNew) {
      addRows(1);
      setActive({ r: view.length, c: Math.max(0, Math.min(cols.length - 1, active.c + dc)) });
      setTimeout(() => keepInView(view.length), 0);
      return;
    }
    setActive((a) => {
      const r = Math.max(0, Math.min(view.length - 1, a.r + dr));
      const c = Math.max(0, Math.min(cols.length - 1, a.c + dc));
      keepInView(r);
      return { r, c };
    });
  }
  function keepInView(r) {
    const el = scroller.current;
    if (!el) return;
    const top = r * ROW_H, bottom = top + ROW_H + 34;
    if (top < el.scrollTop) el.scrollTop = top;
    else if (bottom > el.scrollTop + el.clientHeight) el.scrollTop = bottom - el.clientHeight;
  }

  // a click that should open the editor once the cell is active (pick lists and dates at once; any cell clicked again)
  const pendingEdit = useRef(null);
  useEffect(() => {
    const p = pendingEdit.current;
    if (p && p.r === active.r && p.c === active.c) { pendingEdit.current = null; startEdit(); }
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps
  function startEdit(initial) {
    const it = view[active.r], c = cols[active.c];
    if (!it || !c) return;
    if (!editable(c, it)) { setMsg(canEdit ? `${c.label} cannot be changed here.` : why); return; }
    setEditing({ value: initial !== undefined ? initial : show(it.cur[c.key]) });
  }
  function commit(value, then = [0, 0]) {
    const it = view[active.r], c = cols[active.c];
    setEditing(null);
    if (it && c && show(it.cur[c.key]) !== value) setCells([{ key: it.key, col: c.key, value: normalise(c, value) }]);
    if (then[0] || then[1]) move(then[0], then[1]);
    box.current?.focus();
  }

  function clearSelection() {
    const s = selection(), cells = [];
    for (let r = s.r0; r <= s.r1; r += 1) for (let c = s.c0; c <= s.c1; c += 1) {
      const it = view[r], col = cols[c];
      if (it && col && editable(col, it)) cells.push({ key: it.key, col: col.key, value: "" });
    }
    setCells(cells);
  }

  function onKeyDown(e) {
    if (editing) return;
    const ctrl = e.ctrlKey || e.metaKey;
    if (ctrl && e.key.toLowerCase() === "z") { e.preventDefault(); doUndo(); return; }
    if (ctrl && e.key.toLowerCase() === "s") { e.preventDefault(); save(); return; }
    if (ctrl) return;   // copy and paste go through the clipboard events
    const k = e.key;
    if (k === "ArrowDown") { e.preventDefault(); move(1, 0, e.shiftKey); }
    else if (k === "ArrowUp") { e.preventDefault(); move(-1, 0, e.shiftKey); }
    else if (k === "ArrowRight") { e.preventDefault(); move(0, 1, e.shiftKey); }
    else if (k === "ArrowLeft") { e.preventDefault(); move(0, -1, e.shiftKey); }
    else if (k === "Tab") { e.preventDefault(); move(0, e.shiftKey ? -1 : 1); }
    else if (k === "Enter" || k === "F2") { e.preventDefault(); startEdit(); }
    else if (k === "Delete" || k === "Backspace") { e.preventDefault(); clearSelection(); }
    else if (k === "PageDown") { e.preventDefault(); move(15, 0, e.shiftKey); }
    else if (k === "PageUp") { e.preventDefault(); move(-15, 0, e.shiftKey); }
    else if (k.length === 1 && !e.altKey) { e.preventDefault(); startEdit(k); }
  }

  function onCopy(e) {
    if (editing) return;
    const s = selection(), lines = [];
    for (let r = s.r0; r <= s.r1; r += 1) {
      const it = view[r];
      if (!it) continue;
      const cells = [];
      for (let c = s.c0; c <= s.c1; c += 1) cells.push(show(it.cur[cols[c].key]).replace(/\t/g, " "));
      lines.push(cells.join("\t"));
    }
    e.clipboardData.setData("text/plain", lines.join("\n"));
    e.preventDefault();
    setMsg(`Copied ${lines.length} row${lines.length === 1 ? "" : "s"}.`);
  }

  function onPaste(e) {
    if (editing) return;
    if (!canEdit) { setMsg(why); return; }
    const data = parseClipboard(e.clipboardData.getData("text/plain")).filter((r) => r.some((x) => x !== ""));
    e.preventDefault();
    if (!data.length) return;
    const start = active;
    const cells = [];
    const extra = Math.max(0, start.r + data.length - view.length);
    if (extra && !allowAdd) { setMsg("Rows cannot be added here; the paste was cut to the rows there are."); }
    // new rows for what goes past the end: filled in one go
    const newVals = [];
    data.forEach((line, i) => {
      const r = start.r + i;
      const it = view[r];
      line.forEach((raw, j) => {
        const col = cols[start.c + j];
        if (!col) return;
        if (it) { if (editable(col, it)) cells.push({ key: it.key, col: col.key, value: normalise(col, raw) }); }
        else if (allowAdd && (!col.readOnly || col.createOnly)) {
          const idx = r - view.length;
          newVals[idx] = { ...(newVals[idx] || {}), [col.key]: normalise(col, raw) };
        }
      });
    });
    setCells(cells);
    if (allowAdd && newVals.length) addRows(newVals.length, null, newVals);
    setMsg(`Pasted ${data.length} row${data.length === 1 ? "" : "s"} × ${data[0].length} column${data[0].length === 1 ? "" : "s"}${newVals.length ? `, ${newVals.length} new` : ""}. Save to keep.`);
  }

  function doUndo() {
    const step = undo.current.pop();
    if (!step) return;
    if (step.kind === "add") setItems((list) => list.filter((x) => !step.keys.includes(x.key)));
    else if (step.kind === "delete") setItems((list) => list.map((x) => (step.keys.includes(x.key) ? { ...x, deleted: !x.deleted } : x)));
    else setItems((list) => list.map((it) => {
      const mine = step.before.filter((b) => b.key === it.key);
      if (!mine.length) return it;
      const cur = { ...it.cur };
      mine.forEach((b) => { cur[b.col] = b.value; });
      return { ...it, cur };
    }));
  }

  function toggleDelete(keys) {
    if (!allowDelete || !canEdit) { setMsg(canEdit ? "Rows cannot be deleted here." : why); return; }
    setItems((list) => list.filter((x) => !(x.isNew && keys.includes(x.key))).map((x) => (keys.includes(x.key) ? { ...x, deleted: !x.deleted } : x)));
    undo.current.push({ kind: "delete", keys });
  }
  const selectedKeys = () => { const s = selection(); return view.slice(s.r0, s.r1 + 1).map((x) => x.key); };

  // save every change, or (onlyKey) one row's (owner, 6 Nov 2026: per-row save)
  async function save(onlyKey = null) {
    if (!dirtyCount || busy) return;
    setBusy(true); setMsg("");
    const batch = changed.filter((it) => !(it.isNew && it.deleted) && (!onlyKey || it.key === onlyKey)).map((it) => {
      const diff = {};
      columns.forEach((c) => {
        if (c.readOnly && !(c.createOnly && it.isNew)) return;
        if (it.isNew ? show(it.cur[c.key]) !== "" : show(it.cur[c.key]) !== show(it.orig[c.key])) diff[c.key] = it.cur[c.key];
      });
      return { key: it.key, orig: it.isNew ? null : it.orig, values: diff, delete: it.deleted, cur: it.cur };
    });
    try {
      const outcome = await onSave(batch);
      const byKey = {};
      (outcome?.rows || []).forEach((r) => { if (batch[r.row - 1]) byKey[batch[r.row - 1].key] = r; });
      const failed = (outcome?.rows || []).filter((r) => !r.ok);
      if (outcome?.error) {
        setMsg(outcome.error);
        if (outcome.row && batch[outcome.row - 1]) {
          const k = batch[outcome.row - 1].key;
          setItems((list) => list.map((x) => (x.key === k ? { ...x, error: outcome.error } : x)));
        }
      } else if (failed.length) {
        setItems((list) => list.filter((x) => !(byKey[x.key]?.ok)).map((x) => (byKey[x.key] && !byKey[x.key].ok ? { ...x, error: byKey[x.key].error } : x)));
        const why = failed.slice(0, 3).map((r) => { const b = batch[r.row - 1]; return `${b?.cur?.name || b?.cur?.display_id || `row ${r.row}`}: ${String(r.error || "").replace(/\.+$/, "")}`; }).join("; ");
        setMsg(`Saved ${outcome.saved}; ${failed.length} row${failed.length === 1 ? "" : "s"} not saved: ${why}${failed.length > 3 ? "; ..." : ""}. Fix and save again (the row is marked ⚠).`);
      } else {
        // saved: these rows are no longer changes of this screen (the server's rows replace them when they arrive)
        const keys = new Set(batch.map((b) => b.key));
        setItems((list) => list.filter((x) => !(keys.has(x.key) && (x.isNew || x.deleted))).map((x) => (keys.has(x.key) ? { ...x, orig: { ...x.cur }, error: "" } : x)));
        const warned = (outcome?.rows || []).filter((r) => r.warnings?.length).length;
        setMsg(`Saved ${batch.length} row${batch.length === 1 ? "" : "s"}${warned ? `, ${warned} with rule warnings (kept, flagged)` : ""}.${outcome?.note ? ` ${outcome.note}` : saveNote ? ` ${saveNote}` : ""}`);
      }
    } catch (err) {
      const m = /Row (\d+)/.exec(err.message);
      if (m && batch[Number(m[1]) - 1]) {
        const k = batch[Number(m[1]) - 1].key;
        setItems((list) => list.map((x) => (x.key === k ? { ...x, error: err.message } : x)));
      }
      setMsg(err.message);
    }
    setBusy(false);
  }

  function discard() { setItems(makeItems(rows, rowKey)); undo.current = []; setMsg("Changes discarded."); }
  // one row back to its saved values (a new row goes away)
  function revertRow(key) {
    setItems((list) => list.filter((x) => !(x.key === key && x.isNew)).map((x) => (x.key === key ? { ...x, cur: { ...x.orig }, deleted: false, error: "" } : x)));
    setEditing(null);
  }
  const rowDirty = (it) => it.isNew || it.deleted || columns.some((c) => !c.readOnly && show(it.cur[c.key]) !== show(it.orig[c.key]));

  // only the rows in view are drawn
  const viewportH = scroller.current?.clientHeight || 600;
  const first = Math.max(0, Math.floor(scrollTop / ROW_H) - 10);
  const last = Math.min(view.length, first + Math.ceil(viewportH / ROW_H) + 25);
  const shown = view.slice(first, last);

  const editor = (c, it) => {
    const done = (e2) => {
      if (e2.key === "Enter") { e2.preventDefault(); commit(e2.currentTarget.value, [1, 0]); }
      else if (e2.key === "Tab") { e2.preventDefault(); commit(e2.currentTarget.value, [0, e2.shiftKey ? -1 : 1]); }
      else if (e2.key === "Escape") { e2.preventDefault(); setEditing(null); box.current?.focus(); }
    };
    if (c.type === "select" || c.type === "bool") {
      const opts = c.type === "bool" ? ["", "Yes", "No"] : ["", ...(c.options || [])];
      return (
        <select autoFocus value={editing.value} onChange={(e2) => commit(e2.target.value)} onKeyDown={done} onBlur={(e2) => commit(e2.target.value)}
          ref={(el) => { if (el && !el.dataset.opened) { el.dataset.opened = "1"; try { el.showPicker?.(); } catch { /* older browsers: the list opens on the next click */ } } }}>
          {opts.map((o) => <option key={o} value={o}>{o || "(empty)"}</option>)}
          {editing.value && !opts.includes(editing.value) && <option value={editing.value}>{editing.value}</option>}
        </select>
      );
    }
    if (c.type === "links") {   // a Link (D418): a line a link, "address | note"; Shift+Enter for another line
      return <textarea autoFocus rows={3} defaultValue={editing.value} placeholder="address | note (a line each)" style={{ width: "100%", minWidth: 260 }}
        onKeyDown={(e2) => { if (e2.key === "Enter" && e2.shiftKey) return; done(e2); }} onBlur={(e2) => commit(e2.target.value)} />;
    }
    return <input autoFocus type={c.type === "date" ? "date" : "text"} defaultValue={c.type === "date" ? String(editing.value).slice(0, 10) : editing.value}
      ref={(el) => { if (el && c.type === "date" && !el.dataset.opened) { el.dataset.opened = "1"; try { el.showPicker?.(); } catch { /* typed instead */ } } }}
      onKeyDown={done} onBlur={(e2) => commit(e2.target.value)} list={c.suggest ? `dl-${c.key}` : undefined} />;
  };

  return (
    <div className="grid-wrap">
      <div className="toolbar">
        {toolbar}
        <input className="search" style={{ maxWidth: 220 }} placeholder={`Filter ${items.length} rows`} value={filter} onChange={(e) => setFilter(e.target.value)} />
        {allowAdd && <button className={canEdit ? "" : "later"} disabled={!canEdit} title={canEdit ? "Add an empty row at the end (or paste below the last row)" : why}
          onClick={() => { addRows(1); setTimeout(() => { setActive({ r: view.length, c: 0 }); keepInView(view.length); box.current?.focus(); }, 0); }}>+ Row</button>}
        <details className="col-chooser">
          <summary>Columns ({cols.length}/{columns.length})</summary>
          <div className="col-list">
            {columns.map((c) => (
              <label key={c.key}><input type="checkbox" checked={!hidden.includes(c.key)}
                onChange={(e) => setHidden((h) => (e.target.checked ? h.filter((x) => x !== c.key) : [...h, c.key]))} /> {c.label}</label>
            ))}
          </div>
        </details>
        <button onClick={() => downloadCsv([cols.map((c) => c.label), ...view.filter((x) => !x.isNew).map((x) => cols.map((c) => show(x.cur[c.key])))], name)}
          title="Download what the grid shows as CSV (opens in Excel)">CSV</button>
        {views}
        <span className="er-spacer" />
        {dirtyCount > 0 && <span className="dirty-count">{dirtyCount} changed row{dirtyCount === 1 ? "" : "s"}</span>}
        {dirtyCount > 0 && <button onClick={discard} title="Forget every change not saved">Discard</button>}
        <button className={canEdit ? "ed-btn" : "later"} disabled={!canEdit || !dirtyCount || busy} title={canEdit ? "Save the changed rows (Ctrl+S)" : why} onClick={() => save()}>
          {busy ? "Saving..." : "Save"}</button>
      </div>
      {msg && <p className={/not saved|cannot|Row \d|No |not |refused|needs/i.test(msg) ? "status bad" : "status ok"}>{msg}</p>}
      {!canEdit && why && <p className="quiet">{why}</p>}
      <div className="grid-box" ref={box} tabIndex={0} onKeyDown={onKeyDown} onCopy={onCopy} onPaste={onPaste}
        onClick={() => setMenu(null)}>
        <div className="grid-scroll" ref={scroller} style={{ maxHeight: height }} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}>
          <table className="sheet">
            <thead>
              <tr>
                <th className="rownum">#</th>
                {cols.map((c) => (
                  <th key={c.key} style={c.width ? { minWidth: c.width } : undefined} title={c.title || ""}
                    onClick={() => setSort((s) => (s?.key === c.key ? (s.desc ? null : { key: c.key, desc: true }) : { key: c.key, desc: false }))}>
                    {c.label}{c.required && <span className="req">*</span>}{c.readOnly && !c.createOnly && <span className="quiet" title="Read only"> 🔒</span>}
                    {sort?.key === c.key ? (sort.desc ? " ▼" : " ▲") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {first > 0 && <tr style={{ height: first * ROW_H }}><td colSpan={cols.length + 1} /></tr>}
              {shown.map((it, i) => {
                const r = first + i;
                return (
                  <tr key={it.key} className={`${it.isNew ? "new" : ""} ${it.deleted ? "deleted" : ""} ${it.error ? "row-error" : ""}`} style={{ height: ROW_H }}
                    onContextMenu={(e) => { e.preventDefault(); if (!inSel(r, active.c)) { setActive({ r, c: active.c }); setAnchor(null); } setMenu({ x: e.clientX, y: e.clientY, r }); }}>
                    <td className="rownum" title={it.error || (it.isNew ? "New row (not saved)" : it.deleted ? "Will be deleted when you save" : "")}>
                      {it.error ? "⚠" : it.isNew ? "+" : it.deleted ? "✕" : r + 1}
                      {canEdit && rowDirty(it) && <span className="row-acts" onMouseDown={(e) => e.stopPropagation()}>
                        <button className="linkish" disabled={busy} onClick={() => save(it.key)} title="Save this row">✓</button>
                        <button className="linkish" onClick={() => revertRow(it.key)} title="Put this row back as it was saved">↶</button>
                      </span>}
                      {rowMark && !it.isNew && !rowDirty(it) && <span className="row-acts" onMouseDown={(e) => e.stopPropagation()}>{rowMark(it.cur, it)}</span>}
                    </td>
                    {cols.map((c, ci) => {
                      const isActive = active.r === r && active.c === ci;
                      const dirty = !it.isNew && !c.readOnly && show(it.cur[c.key]) !== show(it.orig[c.key]);
                      return (
                        <td key={c.key} className={`${isActive ? "active" : ""} ${inSel(r, ci) ? "sel" : ""} ${dirty ? "dirty" : ""} ${c.readOnly && !(c.createOnly && it.isNew) ? "ro" : ""} ${c.type === "number" ? "num" : ""} ${(!dirty && c.cellClass?.(it.cur, it)) || ""} ${editable(c, it) && ["select", "bool", "date"].includes(c.type) ? `pick ${c.type}` : ""}`}
                          title={dirty ? `Was: ${show(it.orig[c.key]) || "(empty)"}` : c.cellTitle?.(it.cur, it) || undefined}
                          onMouseDown={(e) => {
                            if (e.button !== 0) return;
                            if (e.shiftKey) { if (!anchor) setAnchor(active); } else setAnchor(null);
                            if (isActive && editing) return;      // clicking inside the editor
                            // one click opens a pick list or a date; a second click on the same cell edits any cell
                            if (!e.shiftKey && editable(c, it) && (["select", "bool", "date"].includes(c.type) || isActive)) pendingEdit.current = { r, c: ci };
                            setActive({ r, c: ci });
                            if (isActive && pendingEdit.current) { pendingEdit.current = null; setTimeout(() => startEdit(), 0); }
                          }}
                          onDoubleClick={() => { setActive({ r, c: ci }); setTimeout(() => startEdit(), 0); }}>
                          {isActive && editing ? editor(c, it) : (c.render ? c.render(it.cur, it) : show(it.cur[c.key]))}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
              {last < view.length && <tr style={{ height: (view.length - last) * ROW_H }}><td colSpan={cols.length + 1} /></tr>}
              {!view.length && <tr><td colSpan={cols.length + 1} className="quiet">{items.length ? "No rows match the filter." : emptyText}</td></tr>}
            </tbody>
          </table>
        </div>
        {menu && (
          <ul className="ctx-menu" style={{ left: menu.x, top: menu.y }} onMouseDown={(e) => e.stopPropagation()}>
            <li><button disabled={!canEdit || !allowAdd} onClick={() => { addRows(1, view[menu.r]?.key ?? null); setMenu(null); }}>Insert a row below</button></li>
            <li><button disabled={!canEdit} onClick={() => { startEdit(); setMenu(null); }}>Edit cell (Enter)</button></li>
            <li><button disabled={!canEdit} onClick={() => { clearSelection(); setMenu(null); }}>Clear cells (Delete)</button></li>
            <li><button onClick={() => { document.execCommand("copy"); setMenu(null); }}>Copy (Ctrl+C)</button></li>
            <li><button disabled={!canEdit || !allowDelete} onClick={() => { toggleDelete(selectedKeys()); setMenu(null); }}>
              {deleteLabel} / undelete selected rows</button></li>
            <li><button onClick={() => { doUndo(); setMenu(null); }}>Undo (Ctrl+Z)</button></li>
            {rowMenu && view[menu.r] && !view[menu.r].isNew && rowMenu(view[menu.r].cur, view[menu.r]).map((x) => (
              <li key={x.label}><button disabled={!!x.disabled} onClick={() => { setMenu(null); x.onClick(); }}>{x.label}</button></li>))}
          </ul>
        )}
        {columns.filter((c) => c.suggest).map((c) => (
          <datalist key={c.key} id={`dl-${c.key}`}>{c.suggest.map((s) => <option key={s} value={s} />)}</datalist>
        ))}
      </div>
      <p className="quiet small-note">Click a cell, type to change it, Enter to move down (below the last row starts a new one). Copy and paste
        blocks to and from Excel (Ctrl+C, Ctrl+V); a paste that runs past the last row adds rows. Shift with arrows or click selects; right-click for rows. Changed cells are shaded until you Save.</p>
    </div>
  );
}
