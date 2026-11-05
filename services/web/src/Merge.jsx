// The Merge tab of a project model (build phase 8, D165 point 6): upload another model (an Excel or zip package)
// and merge its entities, values and relationships into this one, deciding every conflict.
//   #/metamodel/<model>/merge
// Entities are matched by type and name. Nothing changes until the merge is applied; then it is the person's
// uncommitted changes (Changes tab), committed like any other change.
import { useMemo, useRef, useState } from "react";
import { apiDownload, apiFetch, apiUpload, canOn } from "./auth";
import { refreshAll, useApi } from "./ModelViews";
import { EntityLink } from "./Changes";

const go = (path) => { window.location.hash = path; };
const post = (path, body) => apiFetch(path, { method: "POST", body: JSON.stringify(body || {}) });
const show = (v) => (v === null || v === undefined || v === "" ? <span className="quiet">(empty)</span> : String(v));
const field = (f) => f.replace(/^value:/, "").replace(/^description$/, "Description").replace(/^parent$/, "Part of");
const GAP_NAMES = { entity_types: "Entity types", attributes: "Attributes", type_attributes: "Attributes on a type", relationship_types: "Relationship types" };

export default function MergeTab({ model, m }) {
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);
  const [decisions, setDecisions] = useState({});   // conflict id -> "mine" | "theirs" | {value}
  const [addMeta, setAddMeta] = useState(true);
  const [section, setSection] = useState("conflicts");
  const [filter, setFilter] = useState("");
  const [type, setType] = useState("");
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [withData, setWithData] = useState(true);   // merge the data too, or the metamodel only
  const [picked, setPicked] = useState(() => new Set());   // conflicts chosen for a bulk decision
  const [bulkValue, setBulkValue] = useState("");
  const fileRef = useRef(null);
  const mayContent = canOn(model, "model.content");

  const gaps = plan?.metamodel_gaps || {};
  const gapCount = useMemo(() => Object.values(gaps).reduce((n, v) => n + (Array.isArray(v) ? v.length : 0), 0), [gaps]);
  const types = useMemo(() => [...new Set((plan?.entities || []).map((e) => e.entity_type))].sort(), [plan]);
  const match = (e) => (!type || e.entity_type === type) && (!filter || `${e.name || e.entity} ${e.field || ""}`.toLowerCase().includes(filter.toLowerCase()));

  async function upload() {
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    setBusy(true); setError(""); setDone(null); setDecisions({}); setPicked(new Set());
    try {
      const form = new FormData();
      form.append("file", f);
      form.append("with_data", withData ? "true" : "false");
      const p = await apiUpload(`/api/v1/models/${model}/merges`, form);
      setPlan(p); setSection(p.conflicts.length ? "conflicts" : "new");
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  async function apply() {
    setBusy(true); setError("");
    try {
      setDone(await post(`/api/v1/models/${model}/merges/${plan.id}/apply`, { decisions, add_metamodel: addMeta && plan.may_add_metamodel }));
      setPlan(null); refreshAll();
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  async function cancel() {
    if (plan) await post(`/api/v1/models/${model}/merges/${plan.id}/cancel`).catch(() => {});
    setPlan(null); setDecisions({});
    if (fileRef.current) fileRef.current.value = "";
  }
  const decide = (ids, how) => setDecisions((d) => ({ ...d, ...Object.fromEntries(ids.map((i) => [i, how])) }));

  if (m.kind !== "project") {
    return <p className="quiet">Merging is for project models. Create a model from {m.name} and merge into that.</p>;
  }
  const conflicts = (plan?.conflicts || []).filter(match).filter((c) => !onlyOpen || !decisions[c.id]);
  const undecided = (plan?.conflicts || []).filter((c) => !decisions[c.id]).length;
  const created = (plan?.entities || []).filter((e) => e.action === "create").filter(match);
  const updated = (plan?.entities || []).filter((e) => e.action === "update" && e.fills.length).filter(match);
  const rels = (plan?.relationships || []).filter((r) => !filter || `${r.source_name} ${r.type} ${r.target_name}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="merge-page">
      <h2>Merge a model into {m.name}</h2>
      <p className="quiet">
        Upload a model package: the Excel workbook or zip from <em>Actions &gt; Download</em> of another model, here or
        elsewhere. Entities are matched by type and name: new ones are added, empty fields filled and missing relationships
        added; where both have a different value you decide. Nothing changes until you merge, and then the merge is your
        uncommitted changes (Changes tab): commit it, or ask for a commit.
      </p>

      {done && (
        done.recorded === 0 && done.metamodel_version ? (
          <div className="lock-banner pending-banner"><strong>Metamodel merged.</strong> {done.note}{" "}
            <a href={`#/metamodel/${model}/metamodel`}>Open the Metamodel tab</a></div>
        ) : <div className="lock-banner pending-banner">
          <strong>{done.recorded} changes recorded as your uncommitted changes.</strong>{" "}
          {done.metamodel_version && <>The metamodel was extended (version {done.metamodel_version}). </>}
          <a href={`#/metamodel/${model}/changes`}>Open the Changes tab</a> to commit them or ask for a commit.
          {done.failed_count > 0 && (
            <ul className="status bad small">{done.failed.slice(0, 30).map((f, i) => <li key={i}>{f.label || f.change}: {f.error}</li>)}</ul>
          )}
        </div>
      )}

      {!plan && (
        <div className="merge-step">
          <h3>1. Choose what to merge and the model to merge in</h3>
          <div className="merge-what">
            <label><input type="radio" name="what" checked={withData} onChange={() => setWithData(true)} /> <b>With data</b>: the metamodel parts
              the data needs, and the entities, values and relationships (they become your uncommitted changes)</label>
            <label><input type="radio" name="what" checked={!withData} onChange={() => setWithData(false)} /> <b>Without data</b>: only the
              metamodel, the entity types, attributes and relationship types {m.name} lacks (Model Admins; a new metamodel version at once)</label>
          </div>
          <div className="toolbar">
            <input type="file" ref={fileRef} accept=".zip,.xlsx" disabled={!mayContent} />
            <button className="primary" disabled={busy || !mayContent} onClick={upload}>{busy ? "Reading..." : "Read and compare"}</button>
            {!mayContent && <span className="quiet">Merging needs a role that changes content on {m.name} (Architect, Committer, Model Sub Admin or Model Admin).</span>}
          </div>
          <TestFiles model={model} m={m} withData={withData} />
        </div>
      )}

      {plan && (
        <>
          <div className="merge-step">
            <h3>2. What merging <em>{plan.source}</em> {plan.with_data ? "with its data" : "without data (the metamodel only)"} would do</h3>
            {!plan.with_data && withData && !plan.upload_has_data && <p className="status bad">The file has no data: only its metamodel is compared.</p>}
            {!plan.with_data && !gapCount && <p className="quiet">Its metamodel has nothing {m.name} lacks: nothing to merge.</p>}
            {plan.with_data && <div className="merge-stats">
              <button className={section === "conflicts" ? "on" : ""} onClick={() => setSection("conflicts")}>
                <b>{plan.counts.conflicts}</b> conflicts{undecided ? <span className="status bad"> · {undecided} to decide</span> : plan.counts.conflicts ? " · decided" : ""}</button>
              <button className={section === "new" ? "on" : ""} onClick={() => setSection("new")}><b>{plan.counts.create}</b> new entities</button>
              <button className={section === "fills" ? "on" : ""} onClick={() => setSection("fills")}><b>{updated.length}</b> entities with empty fields filled</button>
              <button className={section === "rels" ? "on" : ""} onClick={() => setSection("rels")}><b>{plan.counts.relationships}</b> new relationships</button>
              <span className="quiet">{plan.counts.same} entities and {plan.counts.relationships_already_there} relationships already the same</span>
            </div>}
            {gapCount > 0 && (
              <div className="lock-banner">
                <strong>The upload {plan.with_data ? "uses" : "has"} {gapCount} metamodel part{gapCount === 1 ? "" : "s"} {m.name} does not have:</strong>
                <ul className="small">
                  {Object.entries(gaps).filter(([, v]) => Array.isArray(v) && v.length).map(([k, v]) => (
                    <li key={k}>{GAP_NAMES[k] || k}: {v.slice(0, 15).map((x) => x.name || x.code || `${x.entity_type}.${x.attribute}`).join(", ")}{v.length > 15 ? ` and ${v.length - 15} more` : ""}</li>
                  ))}
                </ul>
                {!plan.with_data ? (plan.may_add_metamodel ? <span>Merging adds them as one new metamodel version.</span>
                  : <span className="status bad">Adding to the metamodel needs the Model Admin role on {m.name}.</span>)
                  : plan.may_add_metamodel
                  ? <label><input type="checkbox" checked={addMeta} onChange={(e) => setAddMeta(e.target.checked)} /> Add them to the metamodel as one new version (Model Admin); otherwise what uses them is left out</label>
                  : <span>Without the Model Admin role what uses them is left out. Ask a Model Admin to merge, or to add them first.</span>}
              </div>
            )}
            {plan.with_data && <div className="toolbar">
              <input className="search" placeholder="Filter by entity, field or relationship" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ maxWidth: 300 }} />
              <select value={type} onChange={(e) => setType(e.target.value)}>
                <option value="">All entity types</option>
                {types.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>}
          </div>

          {plan.with_data && section === "conflicts" && (
            <div className="merge-step">
              <div className="toolbar">
                <strong>Conflicts: both have a value and they differ</strong>
                <label><input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} /> Only those not decided</label>
              </div>
              {(() => {
                const ids = picked.size ? conflicts.filter((c) => picked.has(c.id)).map((c) => c.id) : conflicts.map((c) => c.id);
                const whom = picked.size ? `the ${ids.length} ticked` : filter || type ? `the ${ids.length} shown` : `all ${ids.length}`;
                return (
                  <div className="toolbar bulk-bar">
                    <span>For {whom}:</span>
                    <button disabled={!ids.length} onClick={() => decide(ids, "mine")}>Mine</button>
                    <button disabled={!ids.length} onClick={() => decide(ids, "theirs")}>Theirs</button>
                    <input placeholder="Another value" value={bulkValue} onChange={(e) => setBulkValue(e.target.value)} style={{ width: 200 }} />
                    <button disabled={!ids.length} onClick={() => decide(ids, { value: bulkValue })}
                      title="The same value for each of them (empty clears the field)">Use this value</button>
                    {picked.size > 0 && <button className="linkish" onClick={() => setPicked(new Set())}>Clear the ticks</button>}
                  </div>
                );
              })()}
              {!plan.conflicts.length ? <p className="quiet">No conflicts: nothing to decide.</p> : (
                <table className="grid-table">
                  <thead><tr>
                    <th><input type="checkbox" aria-label="Tick all shown" checked={conflicts.length > 0 && conflicts.every((c) => picked.has(c.id))}
                      onChange={(e) => setPicked(e.target.checked ? new Set(conflicts.map((c) => c.id)) : new Set())} /></th>
                    <th>Entity</th><th>Field</th><th>Mine ({m.name})</th><th>Theirs (upload)</th><th>Keep</th></tr></thead>
                  <tbody>
                    {conflicts.map((c) => {
                      const d = decisions[c.id];
                      const own = d && typeof d === "object";
                      return (
                        <tr key={c.id} className={d ? "" : "row-undecided"}>
                          <td><input type="checkbox" checked={picked.has(c.id)} aria-label={`${c.entity} ${c.field}`}
                            onChange={() => setPicked((x) => { const n = new Set(x); if (n.has(c.id)) n.delete(c.id); else n.add(c.id); return n; })} /></td>
                          <td>{c.entity} <span className="quiet">{c.entity_type}</span> <EntityLink model={model} id={c.match} /></td>
                          <td>{c.field}</td>
                          <td className={d === "mine" ? "chosen" : ""}>{show(c.mine)}</td>
                          <td className={d === "theirs" ? "chosen" : ""}>{show(c.theirs)}</td>
                          <td className="small nowrap">
                            <label><input type="radio" checked={d === "mine"} onChange={() => decide([c.id], "mine")} /> mine</label>{" "}
                            <label><input type="radio" checked={d === "theirs"} onChange={() => decide([c.id], "theirs")} /> theirs</label>{" "}
                            <label><input type="radio" checked={own} onChange={() => decide([c.id], { value: String(c.theirs ?? "") })} /> another value</label>
                            {own && <input value={d.value} onChange={(e) => decide([c.id], { value: e.target.value })} style={{ width: 150 }} />}
                          </td>
                        </tr>
                      );
                    })}
                    {!conflicts.length && <tr><td colSpan="6" className="quiet">None match the filter.</td></tr>}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {plan.with_data && section === "new" && (
            <div className="merge-step">
              <strong>New entities: in the upload, not in {m.name} (by type and name)</strong>
              <table className="grid-table">
                <thead><tr><th>Entity</th><th>Type</th><th>Values</th></tr></thead>
                <tbody>
                  {created.slice(0, 500).map((e) => (
                    <tr key={e.key}><td>{e.name}</td><td>{e.entity_type}</td>
                      <td className="small quiet">{Object.keys(e.theirs || {}).map(field).join(", ")}</td></tr>
                  ))}
                  {!created.length && <tr><td colSpan="3" className="quiet">No new entities{filter || type ? " match the filter" : ""}.</td></tr>}
                </tbody>
              </table>
              {created.length > 500 && <p className="quiet">And {created.length - 500} more.</p>}
            </div>
          )}

          {plan.with_data && section === "fills" && (
            <div className="merge-step">
              <strong>Entities in both: fields empty in {m.name} that the upload fills</strong>
              <table className="grid-table">
                <thead><tr><th>Entity</th><th>Type</th><th>Fills</th></tr></thead>
                <tbody>
                  {updated.slice(0, 500).map((e) => (
                    <tr key={e.key}><td>{e.name} <EntityLink model={model} id={e.match} /></td><td>{e.entity_type}</td>
                      <td className="small">{e.fills.map((f) => <div key={f.field}><span className="quiet">{field(f.field)}:</span> {show(f.theirs)}</div>)}</td></tr>
                  ))}
                  {!updated.length && <tr><td colSpan="3" className="quiet">Nothing to fill{filter || type ? " that matches the filter" : ""}.</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          {plan.with_data && section === "rels" && (
            <div className="merge-step">
              <strong>New relationships</strong>
              <table className="grid-table">
                <thead><tr><th>Source</th><th>Relationship</th><th>Target</th></tr></thead>
                <tbody>
                  {rels.slice(0, 500).map((r, i) => <tr key={i}><td>{r.source_name}</td><td>{r.type}{r.name ? ` (${r.name})` : ""}</td><td>{r.target_name}</td></tr>)}
                  {!rels.length && <tr><td colSpan="3" className="quiet">No new relationships{filter ? " match the filter" : ""}.</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          <div className="merge-step merge-actions">
            <h3>3. Merge</h3>
            <div className="toolbar">
              <button onClick={cancel} disabled={busy}>Cancel</button>
              {plan.with_data ? (
                <button className="primary" disabled={busy || undecided > 0} onClick={apply}
                  title={undecided ? `Decide the ${undecided} conflicts first` : "Record the merge as your uncommitted changes"}>
                  {busy ? "Merging..." : "Merge as my uncommitted changes"}</button>
              ) : (
                <button className="primary" disabled={busy || !gapCount || !plan.may_add_metamodel} onClick={apply}
                  title="Add the metamodel parts this model lacks, as one new metamodel version">
                  {busy ? "Merging..." : "Merge the metamodel"}</button>
              )}
              {undecided > 0 && <span className="status bad">Decide the {undecided} conflict{undecided === 1 ? "" : "s"} first: tick rows, or use the bar above the table for many at once.</span>}
            </div>
          </div>
        </>
      )}
      {error && <p className="status bad">{error}</p>}
      {done && !plan && done.recorded > 0 && <p><button className="linkish" onClick={() => go(`/metamodel/${model}/changes`)}>See my changes</button></p>}
    </div>
  );
}

// Files to try the merge with: a test file made from this model, or any model you may open (download, then upload above)
function TestFiles({ model, m, withData }) {
  const { data: models } = useApi("/api/v1/models?archived=false");
  const [other, setOther] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  async function get(path, name, what) {
    setErr(""); setBusy(what);
    try { await apiDownload(path, name); } catch (e) { setErr(e.message); }
    setBusy("");
  }
  const pick = (models || []).filter((x) => x.id !== model && x.kind !== "template");
  const chosen = pick.find((x) => x.id === other);
  const content = withData ? "content" : "metamodel";
  const what = withData ? "" : " metamodel";
  return (
    <div className="merge-test">
      <strong>Need a file to try it?</strong>
      <p className="quiet small">
        {withData ? "With data" : "Without data (as chosen above): the files hold the metamodel only, with the two new attributes"}. The <b>merge test file</b> is {m.name} itself with some descriptions and values changed (conflicts to decide), some empty
        fields filled, four new entities with relationships, and two attributes the metamodel lacks (a Model Admin may add them).
        Download it, then choose it above and press <em>Read and compare</em>.
      </p>
      <div className="toolbar">
        <button disabled={!!busy} onClick={() => get(`/api/v1/models/${model}/merge-test-file?format=xlsx&content=${content}`, `merge-test${withData ? "" : "-metamodel"}.xlsx`, "xlsx")}>
          {busy === "xlsx" ? "Making..." : `⬇ Merge test file${what} (Excel)`}</button>
        <button disabled={!!busy} onClick={() => get(`/api/v1/models/${model}/merge-test-file?format=zip&content=${content}`, `merge-test${withData ? "" : "-metamodel"}.zip`, "zip")}>
          {busy === "zip" ? "Making..." : `⬇ Merge test file${what} (zip)`}</button>
        <span className="quiet">or another model:</span>
        <select value={other} onChange={(e) => setOther(e.target.value)}>
          <option value="">Choose a model...</option>
          {pick.map((x) => <option key={x.id} value={x.id}>{x.name}{x.version_label ? ` ${x.version_label}` : ""}</option>)}
        </select>
        <button disabled={!chosen || !!busy} onClick={() => get(`/api/v1/models/${other}/package?format=xlsx&content=${content}`, `${chosen.name}.xlsx`, "oxlsx")}>⬇ Excel</button>
        <button disabled={!chosen || !!busy} onClick={() => get(`/api/v1/models/${other}/package?format=zip&content=${content}`, `${chosen.name}.zip`, "ozip")}>⬇ zip</button>
      </div>
      {err && <p className="status bad">{err}</p>}
    </div>
  );
}
