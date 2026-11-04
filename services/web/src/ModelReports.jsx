// Model page, tab Reports (phase 5 with the phase 11 standard reports):
//   * the standard reports (Superset dashboards), each opening in a new tab; choose the model in the
//     dashboard's Model filter (you only see models you can read, D138)
//   * the report catalogue (D71): every entity type and attribute, with the report view and column it is
//     in, for SQL and BI tools on the read-only report login
import { Fragment, useMemo, useState } from "react";
import { CsvButton, useApi } from "./ModelViews";

export default function ModelReports({ model, m }) {
  const { data, error } = useApi(`/api/v1/models/${model}/reports`);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState({});
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
      <h2>Standard reports</h2>
      <p className="quiet">
        Dashboards in the reporting tool. Choose <strong>{m.name}</strong> in a dashboard's Model filter.
        You see only the models you can read here; <em>Open</em> in a report goes back to the entity.
      </p>
      <div className="report-cards">
        {data.reports.map((r) => (
          <a key={r.code} className="report-card" href={r.url} target="_blank" rel="noreferrer" title={`Open ${r.title} in the reporting tool`}>
            <span className="report-code">{r.code}</span>
            <strong>{r.title}</strong>
            <span className="quiet">{r.about}</span>
          </a>
        ))}
      </div>
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
