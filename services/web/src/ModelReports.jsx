// Model page, tab Reports (phase 5 with the phase 11 standard reports; phase 8.2 viewpoints, TOGAF, dependencies, audiences):
//   * the reports (Superset dashboards), each opening in a new tab; choose the model in the dashboard's Model
//     filter (you only see models you can read, D138). Grouped by family (standard, audience dashboards,
//     viewpoints VP, TOGAF catalogues TC and matrices TM, dependencies DR) and shown for one audience
//     (CEO, CFO, architects...: who a report interests, not a role, D153) or for everyone
//   * the report catalogue (D71): every entity type and attribute, with the report view and column it is
//     in, for SQL and BI tools on the read-only report login
import { Fragment, useMemo, useState } from "react";
import { CsvButton, useApi } from "./ModelViews";
import { serviceOn } from "./fmt";

const FAMILIES = [
  ["Audience", "Dashboards by audience", "The headline charts of every report a CEO, CFO, CIO, architect... usually wants, on one page."],
  ["Standard", "Standard reports", "The thirty standard reports, the model overview and the pick-list heatmaps."],
  ["Viewpoint", "Viewpoints (VP)", "The 25 example viewpoints of ArchiMate 4: each as a catalog, matrix, network and heat map."],
  ["TOGAF catalogue", "TOGAF catalogues (TC)", "TOGAF 10 catalogues the standard reports did not have."],
  ["TOGAF matrix", "TOGAF matrices (TM)", "TOGAF 10 matrices the standard reports did not have."],
  ["Dependency", "Dependencies (DR)", "What depends on what: up and down from an entity, between two types, from technology to value stream."],
  ["Gap analysis", "Gap analyses (GR)", "TOGAF gap analyses kept in the models: gaps by layer and type, the gap matrix, resolutions and work packages, Gap entities."],
];

export default function ModelReports({ model, m }) {
  if (!serviceOn("reports")) {
    return <p className="status warn">Reports are switched off on this installation (D191). A Super Admin switches them on in
      Administration &gt; System settings &gt; Services, or with <code>eax service reports on</code>.</p>;
  }
  return <ReportList model={model} m={m} />;
}

function ReportList({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/reports`);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState({});
  const [audience, setAudience] = useState(() => { try { return localStorage.getItem("eax-audience") || ""; } catch { return ""; } });
  const [find, setFind] = useState("");
  const pickAudience = (a) => { setAudience(a); try { localStorage.setItem("eax-audience", a); } catch { /* not kept */ } };
  const types = useMemo(() => {
    if (!data) return [];
    const f = filter.trim().toLowerCase();
    return data.types.filter((t) => !f || t.name.toLowerCase().includes(f) || t.view.includes(f)
      || t.attributes.some((a) => a.name.toLowerCase().includes(f)));
  }, [data, filter]);
  if (error) return <p className="status bad">{error}</p>;
  if (!data) return <p>Loading...</p>;
  const roleOf = {};
  Object.entries(data.standard_roles).forEach(([role, codes]) => codes.forEach((c) => { roleOf[c.toLowerCase()] = role; }));
  const csvRows = () => data.types.flatMap((t) => (t.attributes.length ? t.attributes : [{}]).map((a) => ({
    layer: t.layer, entity_type: t.name, report_view: t.view, attribute: a.name || "", column: a.column || "",
    data_type: a.data_type || "", pick_list: a.pick_list || "", values: a.values || "", required: a.required ? "yes" : "",
  })));
  return (
    <div className="reports-tab">
      <h2>Reports and dashboards</h2>
      <p className="quiet">
        Dashboards in the reporting tool. Choose <strong>{m.name}</strong> in a dashboard's Model filter.
        You see only the models you can read here; <em>Open</em> in a report goes back to the entity.
        The viewpoints can also be seen right here, on the <a href={`#/metamodel/${model}/viewpoints`}>Viewpoints</a> tab.
      </p>
      <div className="toolbar">
        <label>Reports for <select value={audience} onChange={(e) => pickAudience(e.target.value)}
          title="Who the report interests: an audience is not a role and gives no access">
          <option value="">Everyone ({data.reports.length})</option>
          {["Executive", "Business", "Architecture", "Operations and control"].map((g) => (
            <optgroup key={g} label={g}>
              {(data.audiences || []).filter((a) => a.group === g).map((a) => (
                <option key={a.code} value={a.code}>{a.name} ({data.reports.filter((r) => (r.audiences || []).includes(a.code)).length})</option>
              ))}
            </optgroup>
          ))}
        </select></label>
        <input type="search" placeholder="Find a report" value={find} onChange={(e) => setFind(e.target.value)} />
      </div>
      {FAMILIES.map(([family, label, help]) => {
        const f = find.trim().toLowerCase();
        const list = data.reports.filter((r) => (r.family || "Standard") === family
          && (!audience || (r.audiences || []).includes(audience))
          && (!f || `${r.code} ${r.title} ${r.about} ${r.use || ""} ${r.read || ""}`.toLowerCase().includes(f)));
        if (!list.length) return null;
        return (
          <section key={family}>
            <h3 className="vp-group">{label} <span className="quiet">({list.length})</span></h3>
            <p className="quiet">{help}</p>
            <div className="report-cards">
              {list.map((r) => (
                <a key={r.code} className={family === "Audience" ? "report-card audience-card" : "report-card"} href={r.url} target="_blank"
                  rel="noreferrer" title={`Open ${r.title} in the reporting tool`}>
                  <span className="report-code">{r.code.startsWith("AU-") ? r.group : r.code}</span>
                  <strong>{r.title}</strong>
                  <span className="quiet">{r.about}</span>
                </a>
              ))}
            </div>
          </section>
        );
      })}
      <p className="quiet">
        Standard reports use these types as {Object.keys(data.standard_roles).length ? "" : "(none of the standard types are in this metamodel) "}
        {Object.entries(data.standard_roles).map(([role, codes], i) => (
          <span key={role}>{i ? "; " : ""}<strong>{role.replace("_", " ")}</strong>: {codes.join(", ")}</span>
        ))}.
      </p>

      <h2>Report catalogue</h2>
      <p className="quiet">
        For your own reports (in the reporting tool, SQL or another BI tool on the read-only report login): each entity
        type has a view with one column per attribute. Generic views: {data.generic_views.join(", ")}.
      </p>
      <div className="toolbar">
        <input type="search" placeholder="Filter types, attributes or views" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <CsvButton rows={csvRows} name={`${m.name} report catalogue`} title="Download the whole catalogue as CSV (opens in Excel)" />
        <a className="button" href={data.reports_url} target="_blank" rel="noreferrer" title="Open the reporting tool">Reporting tool</a>
      </div>
      <table className="grid-table">
        <thead><tr><th>Layer</th><th>Entity type</th><th>Report view</th><th>Standard report role</th><th>Attributes</th></tr></thead>
        <tbody>
          {types.map((t) => (
            <Fragment key={t.code}>
              <tr>
                <td>{t.layer}</td>
                <td>{t.name}</td>
                <td><code>{t.view}</code></td>
                <td>{roleOf[t.code.toLowerCase()] ? roleOf[t.code.toLowerCase()].replace("_", " ") : <span className="quiet">-</span>}</td>
                <td>
                  <button className="linkish" onClick={() => setOpen((o) => ({ ...o, [t.code]: !o[t.code] }))}
                    title="Show the attributes and their columns">
                    {t.attributes.length} {open[t.code] ? "▾" : "▸"}
                  </button>
                </td>
              </tr>
              {open[t.code] && (
                <tr>
                  <td colSpan={5}>
                    <table className="grid-table inner">
                      <thead><tr><th>Attribute</th><th>Column</th><th>Data type</th><th>Pick list values</th><th>Required</th></tr></thead>
                      <tbody>
                        {t.attributes.map((a) => (
                          <tr key={a.code}>
                            <td>{a.name}</td><td><code>{a.column}</code></td><td>{a.data_type}</td>
                            <td className="quiet">{a.pick_list ? `${a.pick_list}: ${a.values}` : ""}</td>
                            <td>{a.required ? "yes" : ""}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {!types.length && <tr><td colSpan={5} className="quiet">No entity types match.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
