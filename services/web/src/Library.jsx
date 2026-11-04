// The model library (phase 2, redesigned in 0.3.1, D101): a browser on the left with every library model
// (root metamodels and reference models, grouped, with a search and a filter), and the chosen model on
// the right: what it is built on, its layers and types, its counts and its pack.
// Coming in phase 4 (D101): create a model from a library model, create a model as a library model
// (with its pack of guidance and workbooks), promote a model to the library, and download or upload a
// library model as one package file. The industry packs are filled in phase 39 (D45); their documents
// live in Mayan and the tiles link to them (D51).
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./auth";
import { KINDS, KindMark, MarksLegend, StatusMarks } from "./ModelMarks";

function Swatch({ colour }) {
  return <span className="swatch" style={{ background: `#${colour || "eee"}` }} />;
}

export function LockBadge({ model }) {
  if (!model?.is_locked) return null;
  return (
    <span className="lock" title="Locked: nobody can change this model, administrators included. A product release adds new versions beside it.">
      👁 Read-only {model.kind === "template" ? "root metamodel" : "reference model"}
    </span>
  );
}

export function CopyButton() {
  return (
    <button disabled title="Creating a model from this one arrives in build phase 4">Create a model from this</button>
  );
}

const KIND = { template: KINDS.template.label, reference: KINDS.reference.label };

// What a library model's pack holds. Industry packs are filled in build phase 39 (D45).
const PACK = [
  ["📘", "Guidance", "How the industry works, how to use this model, its capabilities and value streams explained, and how to tailor it"],
  ["📊", "Workbooks", "Spreadsheets to collect and load applications, owners, processes and assessments"],
  ["📈", "Reports and views", "Standard reports, dashboards and views: capability heat maps, application landscapes"],
  ["🗺️", "Example diagrams", "Ready-made draw.io diagrams on this model: capability map, value streams, key processes"],
  ["⚖️", "Regulation and frameworks", "The regulations and frameworks the model maps to, with their obligations"],
  ["🧭", "Getting started", "A step-by-step path from creating a model to a first landscape and report"],
];

// The left-hand browser: root metamodels first, then the reference models grouped by the root they are built on.
function groupsOf(models) {
  const roots = models.filter((m) => m.kind === "template");
  const refs = models.filter((m) => m.kind === "reference");
  const groups = [{ title: "Root metamodels", hint: "The framework a model is built on", items: roots }];
  const byRoot = {};
  refs.forEach((r) => { (byRoot[r.built_on || "Other"] ||= []).push(r); });
  Object.keys(byRoot).sort().forEach((root) => {
    groups.push({ title: `Reference models on ${root}`, hint: "Industry content, ready to start from", items: byRoot[root] });
  });
  return groups.filter((g) => g.items.length);
}

function Browser({ models, current, onPick }) {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("all");
  const shown = models.filter((m) => (kind === "all" || m.kind === kind)
    && `${m.name} ${m.industry || ""} ${m.built_on || ""} ${m.description || ""}`.toLowerCase().includes(q.toLowerCase()));
  const groups = groupsOf(shown);
  return (
    <aside className="lib-browser">
      <input className="search" placeholder="Search the library" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="seg small">
        {[["all", "All"], ["template", "Root"], ["reference", "Reference"]].map(([k, label]) => (
          <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{label}</button>
        ))}
      </div>
      {!groups.length && <p className="quiet">Nothing matches.</p>}
      {groups.map((g) => (
        <div key={g.title} className="lib-group">
          <div className="lib-group-title" title={g.hint}>{g.title} <span className="quiet">{g.items.length}</span></div>
          <ul>
            {g.items.map((m) => (
              <li key={m.id}>
                <button className={`lib-item ${current?.id === m.id ? "on" : ""}`} onClick={() => onPick(m)}>
                  <KindMark m={m} />
                  <span className="lib-item-text">
                    <span className="lib-item-name">{m.name} <StatusMarks m={m} /></span>
                    <span className="lib-item-sub">
                      {[m.industry, m.version_label && `v${m.version_label}`, m.kind === "reference" ? `${m.entity_count} entities` : `${m.entity_type_count} types`]
                        .filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="lib-browser-foot">
        <button disabled title="Upload a library model package someone else built (build phase 4)">⬆ Upload a library model</button>
        <p className="quiet">Experts can build library models and share them as one package file. Upload, download,
          creating a library model and promoting your own model to the library arrive in build phase 4.</p>
      </div>
    </aside>
  );
}

function Fact({ label, value, href }) {
  return (
    <div className="lib-fact">
      <div className="lib-fact-label">{label}</div>
      <div className="lib-fact-value">{href ? <a href={href}>{value}</a> : value}</div>
    </div>
  );
}

function Detail({ m, all }) {
  const [tab, setTab] = useState("contents");
  const [more, setMore] = useState(false);
  useEffect(() => { setTab("contents"); setMore(false); }, [m.id]);
  const types = more ? m.counts_by_type : m.counts_by_type.slice(0, 10);
  const max = Math.max(1, ...m.counts_by_type.map((c) => c.count));
  const derived = all.filter((x) => x.source_model_id === m.id);
  const source = all.find((x) => x.id === m.source_model_id);
  const isRoot = m.kind === "template";
  return (
    <div className="lib-detail">
      <div className="lib-detail-head">
        <KindMark m={m} big />
        <div className="lib-detail-title">
          <div className="quiet lib-kind">{KIND[m.kind]}{m.industry ? ` · ${m.industry}` : ""}</div>
          <h2>{m.name} {m.version_label && <span className="quiet">version {m.version_label}</span>}</h2>
        </div>
        <StatusMarks m={m} />
        <LockBadge model={m} />
      </div>
      <p className="lib-desc">{m.description || <span className="quiet">No description.</span>}</p>

      <div className="lib-facts">
        <Fact label="Built on" value={source ? source.name : "Nothing (top of the hierarchy)"} href={source && `#/library/${source.id}`} />
        <Fact label="Layers" value={m.layers.length} />
        <Fact label="Entity types" value={m.entity_type_count} />
        <Fact label="Relationship types" value={m.relationship_type_count} />
        {!isRoot && <Fact label="Entities" value={m.entity_count} />}
        {!isRoot && <Fact label="Relationships" value={m.relationship_count} />}
        <Fact label="Owner" value={m.owner || "-"} />
      </div>

      <div className="lib-actions">
        <a className="button primary" href={`#/metamodel/${m.id}`}>Open{m.is_locked ? " (read-only)" : ""}</a>
        <a className="button" href={`#/metamodel/${m.id}/diagram`}>ER diagram</a>
        <CopyButton />
        <button disabled title="Download this library model as one package file to share (build phase 4)">⬇ Download package</button>
      </div>

      <div className="seg small lib-tabs">
        {[["contents", "Contents"], ["pack", "Pack"], ["derived", `Built on this (${derived.length})`]].map(([k, label]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>

      {tab === "contents" && (
        <div className="lib-contents">
          <div>
            <h3>Layers</h3>
            {m.layers.length ? (
              <ul className="lib-layers">
                {m.layers.map((l) => (
                  <li key={l.name}><Swatch colour={l.colour} /> {l.name} <span className="quiet">{l.types} types</span></li>
                ))}
              </ul>
            ) : <p className="quiet">None. {m.is_top ? "The root of the hierarchy: every root metamodel is built on it." : ""}</p>}
          </div>
          <div>
            <h3>{isRoot ? "Entity types" : "Entities by type"}</h3>
            {types.length ? (
              <table className="lib-counts">
                <tbody>
                  {types.map((c) => (
                    <tr key={c.entity_type}>
                      <td><Swatch colour={c.colour} /> {c.entity_type}</td>
                      {isRoot ? <td className="quiet">{c.layer}</td> : (
                        <>
                          <td className="lib-bar"><span style={{ width: `${(100 * c.count) / max}%`, background: `#${c.colour}` }} /></td>
                          <td className="num">{c.count}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="quiet">None.</p>}
            {m.counts_by_type.length > 10 && (
              <button className="linkish" onClick={() => setMore(!more)}>{more ? "Fewer" : `All ${m.counts_by_type.length}`}</button>
            )}
            {!isRoot && (
              <p className="quiet">Relationships: {m.relationship_counts.map((r) => `${r.relationship_type} ${r.count}`).join(" · ") || "none"}</p>
            )}
          </div>
        </div>
      )}

      {tab === "pack" && (
        <div className="pack">
          <p className="quiet pack-note">Every library model carries a pack: guidance, workbooks, reports and diagrams, plus any other files its builders add. The pack is
            added when a model is created as a library model, and travels with it in its package (phase 4); the industry packs are
            filled in build phase 39. Documents are kept in Mayan, one cabinet per model version (D51).</p>
          <div className="pack-grid">
            {PACK.map(([icon, name, text]) => (
              <div key={name} className="pack-tile" title="Arrives in build phase 4 (the pack's places) and 39 (the industry content)">
                <div className="pack-name"><span><span aria-hidden="true">{icon}</span> {name}</span><span className="phase">phase 4</span></div>
                <p>{text}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "derived" && (
        derived.length ? (
          <ul className="lib-derived">
            {derived.map((d) => (
              <li key={d.id}><KindMark m={d} /> <a href={`#/library/${d.id}`}>{d.name}</a> <span className="quiet">{KIND[d.kind]}</span></li>
            ))}
          </ul>
        ) : <p className="quiet">No library models are built on this one. Your own models built on it are in Models &gt; Hierarchy.</p>
      )}
    </div>
  );
}

export default function Library({ route = "" }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    apiFetch("/api/v1/models/library").then(setData).catch((e) => setError(e.message));
  }, []);
  const wanted = route.split("/")[2];
  const current = useMemo(() => {
    if (!data?.length) return null;
    return data.find((m) => m.id === wanted)
      || data.find((m) => m.kind === "template" && !m.is_top) || data[0];
  }, [data, wanted]);
  return (
    <section>
      <h1>Model library</h1>
      <p className="quiet lib-intro">
        The models everyone starts from. <b>Root metamodels</b> are frameworks (ArchiMate 4, or one your organisation
        builds from scratch); <b>reference models</b> add ready-made industry content. Shipped ones are locked: nobody can
        change them and a release adds a new version beside the old one.
      </p>
      <MarksLegend />
      {error && <p className="status bad">{error}</p>}
      {!data && !error && <p>Loading...</p>}
      {data && (
        <div className="lib-layout">
          <Browser models={data} current={current} onPick={(m) => { window.location.hash = `#/library/${m.id}`; }} />
          {current ? <Detail m={current} all={data} /> : <p className="quiet">The library is empty.</p>}
        </div>
      )}
    </section>
  );
}
