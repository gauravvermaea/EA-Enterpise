// Code coverage as pictures on a self-test run (R3.10; owner, 13 Nov 2026: "coverage should be shown with results in UI
// with some sort of graph"): the share of the API's lines run against the goal (90%), each area the least covered first,
// the trend over the last runs of the same kind, and the negative tests by kind (R3.9). The pictures are drawn by the API
// from numbers only (eax/testing/coverage_view.py), the same ones as in the HTML report.

const FIGURES = [
  ["gauge", "Share of the API's lines run"],
  ["areas", "By area, the least covered first"],
  ["trend", "Over the last runs of this kind"],
  ["negative", "Negative tests by kind"],
];

export default function CoverageCharts({ c }) {
  if (!c) return null;
  const charts = c.charts || {};
  const shown = FIGURES.filter(([k]) => charts[k]);
  if (!shown.length) {
    return <p className="quiet small">This run kept no code coverage (EAX_COVERAGE=on measures it) and ran no negative tests.</p>;
  }
  const n = c.negative_totals || {};
  return (
    <section className="coverage-charts" aria-label="Code coverage">
      <h3>Code coverage</h3>
      {c.summary && <p className="small">{c.summary}</p>}
      <div className="coverage-figures">
        {shown.map(([k, label]) => (
          <figure key={k} className={`coverage-${k}`}>
            <div dangerouslySetInnerHTML={{ __html: charts[k] }} />
            <figcaption className="quiet small">{label}</figcaption>
          </figure>))}
      </div>
      {c.negative && <p className="small quiet">Negative tests: {n.passed || 0} refused as they should be,
        {" "}{n.warning || 0} warnings, {n.failed || 0} failed (each is a result line: "negative: kind: METHOD path").</p>}
    </section>
  );
}
