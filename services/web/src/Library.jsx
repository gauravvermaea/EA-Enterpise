// The model library (build phase 2): read-only reference models, with their counts by type.
// Reference models are locked in the database; copying one to start a model arrives in phase 4.
// Each model has an industry pack (guidance, workbooks, reports, diagrams...): the places are shown
// now and are filled in build phase 39 (D45). The documents live in Mayan and the tiles link to them (D51).
import { useEffect, useState } from "react";
import { apiFetch } from "./auth";

function Swatch({ colour }) {
  return <span className="swatch" style={{ background: `#${colour || "eee"}` }} />;
}

export function LockBadge({ model }) {
  if (!model?.is_locked) return null;
  return (
    <span className="lock" title="Locked: nobody can change this model, administrators included. A product release adds new versions beside it.">
      🔒 Read-only {model.kind === "template" ? "template" : "reference model"}
    </span>
  );
}

export function CopyButton() {
  return (
    <button disabled title="Copying a model to work on arrives in build phase 4">Copy this model</button>
  );
}

// What an industry pack holds. Filled in build phase 39 with the industry models (D45).
const PACK = [
  ["📘", "Industry guidance", "How the industry works, how to use this model, its capabilities and value streams explained, and how to tailor it"],
  ["📊", "Workbooks", "Spreadsheets (CSV) to collect and load applications, owners, processes and assessments for this industry"],
  ["📈", "Reports and views", "Standard reports, dashboards and views for this industry: capability heat maps, application landscapes"],
  ["🗺️", "Example diagrams", "Ready-made draw.io diagrams on this model: capability map, value streams, key processes"],
  ["⚖️", "Regulation and frameworks", "The regulations and industry frameworks the model maps to, with their obligations"],
  ["🧭", "Getting started", "A step-by-step path from copying the model to a first landscape and report"],
];

function IndustryPack({ m }) {
  return (
    <div className="pack">
      <h3>{m.industry || "Industry"} pack <span className="quiet">· coming in build phase 39</span></h3>
      <p className="quiet pack-note">The pack's documents are kept in the document management system (Mayan), one cabinet per
        model version; each tile will open its documents there (D51).</p>
      <div className="pack-grid">
        {PACK.map(([icon, name, text]) => (
          <div key={name} className="pack-tile" title="Arrives in build phase 39 with the industry models">
            <div className="pack-name"><span><span aria-hidden="true">{icon}</span> {name}</span><span className="phase">phase 39</span></div>
            <p>{text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function LibraryCard({ m }) {
  const [all, setAll] = useState(false);
  const types = all ? m.counts_by_type : m.counts_by_type.slice(0, 8);
  const max = Math.max(1, ...m.counts_by_type.map((c) => c.count));
  return (
    <div className="lib-card">
      <div className="lib-head">
        <div>
          <h2>{m.name} <span className="quiet">{m.version_label && `version ${m.version_label}`}</span></h2>
          <p className="quiet">{m.industry} · {m.metamodel_name} · {m.entity_count} entities · {m.relationship_count} relationships · owner {m.owner || "-"}</p>
        </div>
        <LockBadge model={m} />
      </div>
      <p>{m.description}</p>
      <table className="lib-counts">
        <tbody>
          {types.map((c) => (
            <tr key={c.entity_type}>
              <td><Swatch colour={c.colour} /> {c.entity_type}</td>
              <td className="lib-bar"><span style={{ width: `${(100 * c.count) / max}%`, background: `#${c.colour}` }} /></td>
              <td className="num">{c.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {m.counts_by_type.length > 8 && (
        <button className="linkish" onClick={() => setAll(!all)}>{all ? "Fewer types" : `All ${m.counts_by_type.length} types`}</button>
      )}
      <p className="quiet">Relationships: {m.relationship_counts.map((r) => `${r.relationship_type} ${r.count}`).join(" · ") || "none"}</p>
      <div className="lib-actions">
        <a className="button primary" href={`#/metamodel/${m.id}`}>Open (read-only)</a>
        <a className="button" href={`#/metamodel/${m.id}/diagram`}>ER diagram</a>
        <CopyButton />
      </div>
      <IndustryPack m={m} />
    </div>
  );
}

export default function Library() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    apiFetch("/api/v1/models/library").then(setData).catch((e) => setError(e.message));
  }, []);
  return (
    <section>
      <h1>Model library</h1>
      <p className="quiet">
        Reference models to start from. They are locked: nobody can change them, administrators included, and the
        database itself refuses it. A product release adds a new version beside the old one. Copy one to start your
        own model (build phase 4). Each model comes with an industry pack of guidance, workbooks, reports and diagrams;
        those, and more industries, follow at the end of the build.
      </p>
      {error && <p className="status bad">{error}</p>}
      {!data && !error && <p>Loading...</p>}
      {data && !data.length && <p className="quiet">No reference models installed.</p>}
      {data?.map((m) => <LibraryCard key={m.id} m={m} />)}
    </section>
  );
}
