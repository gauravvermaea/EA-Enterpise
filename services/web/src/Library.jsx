// The model library (phase 2, redesigned in 0.3.1, D101): a browser on the left with every library model
// (root metamodels and reference models, grouped, with a search and a filter), and the chosen model on
// the right: what it is built on, its domains and types, its counts and its pack.
// Phase 4 (D108, D118): create a model from a library model, download a library model as one package
// (zip or Excel), upload a package (perhaps renamed, to test with a second copy), and, for Library Admins,
// publish, withdraw and restore. Pack files wait for Mayan (phase 13, D117); the industry packs are filled
// in phase 39 (D45).
import { useEffect, useMemo, useState } from "react";
import { apiFetch, can, needsRole } from "./auth";
import { CreateFromButton, DownloadButtons, libraryAction, UploadButton } from "./ModelOps";
import { IndustryPackTiles } from "./IndustryPack";
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

export function CopyButton({ m }) {
  return <CreateFromButton m={m} />;
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
  const [kind, setKind] = useState(() => (/[?&]kind=reference/.test(window.location.hash) ? "reference" : "all"));   // the repository map's link (D318)
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
        <UploadButton label="⬆ Upload a model package" />
        <p className="quiet">A package is one file (zip or Excel) downloaded from a model here or from another EA Explorer.
          To test, download a library model, change its name in the upload and upload it again: it lands beside the first.
          {can("library.curate") ? " As Library Admin you can upload it into the library." : " It is uploaded as your own project model; uploading into the library needs the Library Admin role."}</p>
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
  const wantPack = () => (/[?&]tab=pack/.test(window.location.hash) ? "pack" : "contents");   // the model page's link (D546)
  const [tab, setTab] = useState(wantPack);
  const [more, setMore] = useState(false);
  useEffect(() => { setTab(wantPack()); setMore(false); }, [m.id]);
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
        <Fact label="Domains" value={m.domains.length} />
        <Fact label="Entity types" value={m.entity_type_count} />
        <Fact label="Relationship types" value={m.relationship_type_count} />
        {!isRoot && <Fact label="Entities" value={m.entity_count} />}
        {!isRoot && <Fact label="Relationships" value={m.relationship_count} />}
        <Fact label="Owner" value={m.owner || "-"} />
      </div>

      <div className="lib-actions">
        <a className="button primary" href={`#/metamodel/${m.id}`}>Open{m.is_locked ? " (read-only)" : ""}</a>
        <a className="button" href={`#/metamodel/${m.id}/diagram`}>ER diagram</a>
        <CreateFromButton m={m} />
        <DownloadButtons m={m} compact />
        <LibraryButtons m={m} />
      </div>

      <div className="seg small lib-tabs">
        {[["contents", "Contents"], ["pack", "Pack"], ["derived", `Built on this (${derived.length})`]].map(([k, label]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>

      {tab === "contents" && (
        <div className="lib-contents">
          <div>
            <h3>Domains</h3>
            {m.domains.length ? (
              <ul className="lib-domains">
                {m.domains.map((l) => (
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
                      {isRoot ? <td className="quiet">{c.domain}</td> : (
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

      {tab === "pack" && m.kind === "reference" && <IndustryPackTiles model={m.id} />}
      {tab === "pack" && m.kind !== "reference" && (
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

function LibraryButtons({ m }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const top = m.is_top;
  const curator = can("library.curate");
  const why = needsRole(["library-admin"]);
  const act = async (a) => {
    setBusy(true); setError("");
    try { await libraryAction(m, a); window.dispatchEvent(new Event("eax-library")); } catch (e) { setError(e.message); }
    setBusy(false);
  };
  return (
    <>
      {m.library_state === "building" && m.approval_state !== "requested" && <button disabled={busy || !curator} onClick={() => act("request-publish")}
        title={curator ? "Ask for it to be published; it is then approved (two steps, D134)" : `Publishing: ${why}`}>Request publishing</button>}
      {m.library_state === "building" && m.approval_state === "requested" && <button disabled={busy || !curator} onClick={() => act("publish")}
        title={curator ? "Approve: everyone can then see it and start from it" : `Approving: ${why}`}>Approve and publish</button>}
      {m.library_state === "published" && <button disabled={busy || !curator || top} onClick={() => act("withdraw")}
        title={top ? "Root is the top of the hierarchy and always stays" : curator ? "Nobody can start a new model from it; models built on it keep working" : `Withdrawing: ${why}`}>Withdraw</button>}
      {m.library_state === "withdrawn" && <button disabled={busy || !curator} onClick={() => act("restore")}
        title={curator ? "Back in the library for everyone" : `Restoring: ${why}`}>Restore</button>}
      {error && <span className="status bad">{error}</span>}
    </>
  );
}

export default function Library({ route = "" }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [withdrawn, setWithdrawn] = useState(false);
  const [gen, setGen] = useState(0);
  useEffect(() => {
    const on = () => setGen((x) => x + 1);
    window.addEventListener("eax-library", on);
    window.addEventListener("eax-refresh", on);
    return () => { window.removeEventListener("eax-library", on); window.removeEventListener("eax-refresh", on); };
  }, []);
  useEffect(() => {
    apiFetch(`/api/v1/models/library${withdrawn ? "?withdrawn=true" : ""}`).then(setData).catch((e) => setError(e.message));
  }, [withdrawn, gen]);
  const wanted = (route.split("/")[2] || "").split("?")[0];   // #/library/<id>?tab=pack (D546)
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
      <label className="quiet" title={can("library.curate") ? "Withdrawn library models: no new models start from them" : `Seeing withdrawn models: ${needsRole(["library-admin"])}`}>
        <input type="checkbox" checked={withdrawn} disabled={!can("library.curate")} onChange={(e) => setWithdrawn(e.target.checked)} /> Show withdrawn library models</label>
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
