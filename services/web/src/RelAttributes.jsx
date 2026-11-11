// A relationship's name and attribute values (D563, D564): its type's attributes and its allowed relationship's own,
// edited as key : value rows. Used on drawn views (the line's Properties) and on the entity page.
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "./auth";

// a line's attributes (D563, D564): its type's and its allowed relationship's, edited as key : value rows; saved at once
export function RelationshipAttributes({ model, id, readOnly, onSave, note = "", saveLabel = "Save and commit" }) {
  const [d, setD] = useState(null);
  const [vals, setVals] = useState({});
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const load = useCallback(() => {
    apiFetch(`/api/v1/models/${model}/content/relationships/${id}`)
      .then((x) => { setD(x); setName(x.name || ""); setVals(Object.fromEntries((x.attributes || []).map((a) => [a.name, x.values?.[a.name] ?? ""]))); })
      .catch((e) => setD({ error: e.message }));
  }, [model, id]);
  useEffect(() => { setD(null); setMsg(null); load(); }, [load]);
  if (!d) return <p className="quiet">Loading its attributes…</p>;
  if (d.error) return <p className="status bad">{d.error}</p>;
  const attrs = d.attributes || [];
  const changed = name !== (d.name || "") || attrs.some((a) => String(vals[a.name] ?? "") !== String(d.values?.[a.name] ?? ""));
  async function save() {
    setBusy(true); setMsg(null);
    try {
      const values = Object.fromEntries(attrs.filter((a) => String(vals[a.name] ?? "") !== String(d.values?.[a.name] ?? "")).map((a) => [a.name, vals[a.name]]));
      const data = { ...(name !== (d.name || "") ? { name } : {}), ...(Object.keys(values).length ? { values } : {}) };
      await onSave(id, data);
      setMsg({ ok: true, text: "Saved." });
      load();
    } catch (e) { setMsg({ ok: false, text: e.message }); } finally { setBusy(false); }
  }
  return (
    <div className="drawn-lineattrs">
      <table className="facts"><tbody>
        <tr><th>Name</th><td>{readOnly ? (d.name || "—")
          : <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Relationship name" placeholder="No name: the line shows its type" />}</td></tr>
        {attrs.length === 0 && <tr><th>Attributes</th><td className="quiet">This relationship has no attributes in the metamodel.</td></tr>}
        {attrs.map((a) => (
          <tr key={a.code} className={a.required && !String(vals[a.name] ?? "").trim() ? "missing" : ""}>
            <th title={a.only_for?.length ? `Only on ${a.only_for.join(", ")}` : `On every ${d.relationship_type} relationship`}>
              {a.name}{a.required && <span className="req" title="Required"> *</span>} :</th>
            <td>{readOnly ? (String(vals[a.name] ?? "") || "—")
              : a.values?.length
                ? <select value={vals[a.name] ?? ""} aria-label={a.name} onChange={(e) => setVals((v) => ({ ...v, [a.name]: e.target.value }))}>
                  <option value="">—</option>{a.values.map((x) => <option key={x} value={x}>{x}</option>)}</select>
                : a.data_type === "boolean"
                  ? <select value={String(vals[a.name] ?? "")} aria-label={a.name} onChange={(e) => setVals((v) => ({ ...v, [a.name]: e.target.value }))}>
                    <option value="">—</option><option value="true">Yes</option><option value="false">No</option></select>
                  : <input value={vals[a.name] ?? ""} aria-label={a.name} type={a.data_type === "date" ? "date" : "text"}
                    onChange={(e) => setVals((v) => ({ ...v, [a.name]: e.target.value }))} />}</td>
          </tr>))}
      </tbody></table>
      {(d.findings || []).map((f) => <p key={f.kind + f.attribute} className="small status warn">{f.message}</p>)}
      {!readOnly && <p><button className="primary" disabled={busy || !changed} onClick={save}>{busy ? "Saving…" : saveLabel}</button>
        {note && <span className="quiet"> {note}</span>}</p>}
      {msg && <p className={`small status ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
    </div>
  );
}

