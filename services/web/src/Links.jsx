import { useEffect, useState } from "react";

// Link attributes (data type code "url", D418): one or more links, each an address and an optional note
// (a version, what it is), kept one line each: "address | note". People enter anything; nothing is refused.
// The one guard is for display: only http(s)://, ftp(s)://, #/... and ea:... addresses are clickable; anything
// else (javascript:, data:, plain words) shows as plain text.

export const MAX_ADDRESS = 2000;
export const MAX_NOTE = 200;
export const MAX_LINKS = 20;

export function parseLinks(value) {
  if (value === null || value === undefined) return [];
  if (Array.isArray(value)) {
    return value.map((x) => (typeof x === "string" ? splitLine(x) : { address: String(x?.address || "").trim(), note: String(x?.note || "").trim() }))
      .filter((x) => x.address).slice(0, MAX_LINKS);
  }
  return String(value).split(/\r?\n/).map(splitLine).filter((x) => x.address).slice(0, MAX_LINKS);
}

function splitLine(line) {
  const i = line.indexOf("|");
  return i < 0 ? { address: line.trim(), note: "" } : { address: line.slice(0, i).trim(), note: line.slice(i + 1).trim() };
}

export const linesOf = (links) => links.filter((x) => x.address.trim())
  .map((x) => (x.note.trim() ? `${x.address.trim()} | ${x.note.trim()}` : x.address.trim())).join("\n");

export const linksText = (value) => parseLinks(value).map((x) => (x.note ? `${x.address} (${x.note})` : x.address)).join("; ");

// links inside EA Explorer (ea:...), as the libraries write them
export function eaHref(href) {
  const m = /^ea:([a-z]+):(.+)$/.exec(href || "");
  if (!m) return null;
  const [a, b] = m[2].split(":");
  switch (m[1]) {
    case "model": return `#/metamodel/${a}`;
    case "project": return `#/projects/${a}`;
    case "entity": return `#/metamodel/${a}/entity/${b}`;
    case "view": return `#/metamodel/${a}/views/${encodeURIComponent(b)}/diagram`;
    case "canvas": return `#/projects/${a}/canvas?c=${b}`;
    case "reference": return `#/reference-library/${a}`;
    case "page": return `#/enterprise-library/${a}/${b}`;
    default: return null;
  }
}

// display only: whether an address may be a clickable link, and the href it opens
export function linkHref(address) {
  const a = String(address || "").trim();
  if (/^(https?|ftps?):\/\//i.test(a)) return a;
  if (a.startsWith("#/")) return a;
  return eaHref(a);   // ea:model:…, ea:entity:…, ea:view:… (the links the libraries use)
}
const isOwn = (href) => href.startsWith("#/") || (typeof window !== "undefined" && href.startsWith(`${window.location.origin}/`));

export function LinkList({ value, inline = false, empty = null }) {
  const links = parseLinks(value);
  if (!links.length) return empty;
  const one = (x, i) => {
    const href = linkHref(x.address);
    const label = x.address.length > 80 ? `${x.address.slice(0, 77)}…` : x.address;
    return (
      <span key={i} className="link-value">
        {href ? (isOwn(href) ? <a href={href} title={x.address}>{label}</a>
          : <a href={href} target="_blank" rel="noopener noreferrer" title={x.address}>{label}</a>)
          : <span title="Not a web address: shown as text">{label}</span>}
        {x.note && <span className="quiet small"> · {x.note}</span>}
      </span>
    );
  };
  if (inline) return <span className="link-values">{links.map((x, i) => [i > 0 && "; ", one(x, i)])}</span>;
  return <ul className="link-list">{links.map((x, i) => <li key={i}>{one(x, i)}</li>)}</ul>;
}

// the field in a form: a row a link (address and note), + to add one, × to take one away
export function LinkEditor({ id, value, onChange }) {
  const [rows, setRows] = useState(() => (parseLinks(value).length ? parseLinks(value) : [{ address: "", note: "" }]));
  useEffect(() => {   // the value changed from outside (reset, roll back): show it
    if (linesOf(rows) !== linesOf(parseLinks(value))) setRows(parseLinks(value).length ? parseLinks(value) : [{ address: "", note: "" }]);
  }, [value]);   // eslint-disable-line react-hooks/exhaustive-deps
  const put = (list) => { setRows(list); onChange(linesOf(list)); };
  const change = (i, k, v) => put(rows.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const remove = (i) => put(rows.length > 1 ? rows.filter((_, j) => j !== i) : [{ address: "", note: "" }]);
  return (
    <div className="link-editor">
      {rows.map((x, i) => (
        <div key={i} className="link-row" style={{ display: "flex", gap: 4, marginBottom: 2 }}>
          <input id={i === 0 ? id : undefined} type="text" value={x.address} maxLength={MAX_ADDRESS} placeholder="https://…, #/… or any address"
            aria-label={`Link ${i + 1} address`} onChange={(e) => change(i, "address", e.target.value)} style={{ flex: 3 }} />
          <input type="text" value={x.note} maxLength={MAX_NOTE} placeholder="note, e.g. v2.1" aria-label={`Link ${i + 1} note`}
            onChange={(e) => change(i, "note", e.target.value)} style={{ flex: 2 }} />
          <span style={{ width: 32, textAlign: "center" }}>{linkHref(x.address) && <a className="button small" href={linkHref(x.address)}
            target="_blank" rel="noopener noreferrer" title="Open">↗</a>}</span>
          {(rows.length > 1 || x.address || x.note) && <button type="button" className="small" title="Take this link away"
            aria-label={`Remove link ${i + 1}`} onClick={() => remove(i)}>×</button>}
        </div>
      ))}
      {rows.length < MAX_LINKS && <button type="button" className="small" title="Add another link" aria-label="Add a link"
        onClick={() => setRows([...rows, { address: "", note: "" }])}>+</button>}
    </div>
  );
}
