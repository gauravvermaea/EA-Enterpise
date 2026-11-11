// EA Explorer's own documentation, for everyone signed in (owner, 10 Nov 2026, D550): the documents of the version
// that runs, from the user menu's Documentation link.
//   #/documentation              every document, grouped, with a search across them all
//   #/documentation/<key>        one document, rendered (the API escapes everything first: nothing in a document runs)
// The same documents are in the Enterprise library, folder "EA Explorer documentation" (refreshed at every start).
import { useEffect, useRef, useState } from "react";
import { apiDownload, apiFetch } from "./auth";
import { useApi } from "./ModelViews";

export default function DocumentationPage({ route }) {
  const m = /^#\/documentation\/([^?]+)(?:\?at=(.*))?/.exec(route);
  if (m) return <DocumentPage key={m[1]} docKey={decodeURIComponent(m[1])} at={m[2] ? decodeURIComponent(m[2]) : ""} />;
  return <DocumentList />;
}

function DocumentList() {
  const { data, error } = useApi("/api/v1/documentation");
  const [q, setQ] = useState("");
  const [found, setFound] = useState(null);
  useEffect(() => {
    if (q.trim().length < 2) { setFound(null); return undefined; }
    const t = setTimeout(() => {
      apiFetch(`/api/v1/documentation/search?q=${encodeURIComponent(q.trim())}`).then((r) => setFound(r.results)).catch(() => setFound([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);
  if (error) return <p className="status error">{error}</p>;
  if (!data) return <p><span className="spinner" aria-hidden="true" /> Loading the documentation…</p>;
  const groups = data.groups.filter((g) => data.documents.some((d) => d.group === g));
  return (
    <section className="docs-page">
      <h1>Documentation for EA Explorer {data.version}</h1>
      <p className="quiet">
        Every document that ships with this version: how to use EA Explorer, run it, the command line, and how it was designed.
        The same documents are in the <a href="#/enterprise-library">Enterprise library</a>, folder <em>EA Explorer documentation</em>.
      </p>
      <div className="toolbar docs-search">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search all documents"
          aria-label="Search all documents" autoFocus />
        {found && <span className="quiet">{found.length} document{found.length === 1 ? "" : "s"} found</span>}
      </div>
      {found ? (
        found.length ? (
          <ul className="docs-found">
            {found.map((d) => (
              <li key={d.key}>
                <a href={`#/documentation/${encodeURIComponent(d.key)}`}><strong>{d.title}</strong></a> <span className="quiet small">· {d.group}</span>
                <div className="small quiet">…{d.snippet}…</div>
              </li>
            ))}
          </ul>
        ) : <p className="status">No document holds every word of “{q}”.</p>
      ) : (
        <div className="docs-groups">
          {groups.map((g) => (
            <div key={g} className="docs-group card">
              <h2>{g}</h2>
              <ul>
                {data.documents.filter((d) => d.group === g).map((d) => (
                  <li key={d.key}>
                    <a href={`#/documentation/${encodeURIComponent(d.key)}`}>{d.title}</a>
                    {d.summary && <div className="small quiet">{d.summary}</div>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function DocumentPage({ docKey, at }) {
  const { data, error } = useApi(`/api/v1/documentation/${encodeURIComponent(docKey)}`);
  const body = useRef(null);
  useEffect(() => {
    if (!data || !body.current) return;
    const el = at ? body.current.querySelector(`#doc-${CSS.escape(at.toLowerCase())}`) : null;
    if (el) el.scrollIntoView(); else window.scrollTo(0, 0);
  }, [data, at]);
  if (error) return <section><p><a href="#/documentation">Documentation</a></p><p className="status error">{error}</p></section>;
  if (!data) return <p><span className="spinner" aria-hidden="true" /> Loading…</p>;
  const onClick = (e) => {                        // anchors within the document scroll; others are normal links
    const a = e.target.closest("a");
    const href = a && a.getAttribute("href");
    if (href && href.startsWith("#doc-")) {
      e.preventDefault();
      body.current.querySelector(`#${CSS.escape(href.slice(1))}`)?.scrollIntoView();
    }
  };
  return (
    <section className="docs-page">
      <p className="small"><a href="#/documentation">Documentation</a> › {data.group}</p>
      <div className="toolbar docs-doc-bar">
        <span className="quiet small">EA Explorer {data.version} · {data.file}</span>
        <span className="spacer" />
        <button onClick={() => apiDownload(`/api/v1/documentation/${encodeURIComponent(docKey)}/download`, data.file)}
          title="Download this document's own file">⬇ Download</button>
        <button onClick={() => window.print()} title="Print this document, or save it as a PDF from the print dialog">Print or save as PDF</button>
      </div>
      {/* the API built this HTML from the document escaped first, so it holds only the tags it made itself */}
      <article ref={body} className="doc-body" onClick={onClick} dangerouslySetInnerHTML={{ __html: data.html }} />
    </section>
  );
}
