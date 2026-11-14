"""R2.35 (owner, 12 Nov 2026: "Mark tests critical and non critical and provide a ring chart showing how many fail and
provide a overall category of functional health")."""

from pathlib import Path

from eax.testing import health as H

REPO = Path(__file__).resolve().parents[3]


def _r(suite, name, outcome):
    return {"suite": suite, "name": name, "outcome": outcome}


def test_which_checks_are_critical():
    assert H.importance("api", "write content: create an entity") == "critical"
    assert H.importance("ui", "journey: child merge: send, accept, refresh") == "critical"
    assert H.importance("ui", "page: #/admin") == "critical"
    assert H.importance("smoke", "sign in as super-admin") == "critical"
    assert H.importance("db", "every relationship's ends are in its model") == "critical"
    assert H.importance("db", "foreign keys have an index (speed)") == "non-critical"
    assert H.importance("security", "image superset (Trivy)") == "non-critical"


def test_the_functional_health():
    ok = [_r("api", f"GET /x{i}: every test role", "passed") for i in range(5)]
    assert H.summary(ok)["health"] == "Healthy"
    # security never makes a run not healthy
    sec = ok + [_r("security", "image backup (Trivy)", "failed")] * 3
    s = H.summary(sec)
    assert s["health"] == "Healthy" and s["security"]["failed"] == 3
    # a critical failure: Not healthy, and it is named
    bad = ok + [_r("ui", "journey: import: upload a delivery, accept, undo", "failed")]
    s = H.summary(bad)
    assert s["health"] == "Not healthy" and "journey: import" in s["reason"] and s["critical"]["failed"] == 1
    # a critical warning, or many non-critical failures: Degraded
    assert H.summary(ok + [_r("ui", "page: #/x", "warning")])["health"] == "Degraded"
    many = ok + [_r("db", "foreign keys have an index (speed)", "failed")] * (H.NON_CRITICAL_LIMIT + 1)
    assert H.summary(many)["health"] == "Degraded"
    assert H.summary([])["health"] == "Not known"


def test_the_ring_chart():
    svg = H.ring_svg([("critical failed", 2), ("non-critical failed", 1), ("warning", 0), ("skipped", 3), ("passed", 94)], 140, "Every check")
    assert svg.startswith("<svg") and "3 failed of 100" in svg and svg.count("<circle") == 1 + 4   # the track and four parts
    assert ">3</text>" in svg


def test_report_page_and_command_line_show_it():
    report = (REPO / "services/api/eax/testing/report.py").read_text(encoding="utf-8")
    assert "Functional health:" in report and "H.ring_svg(H.ring_parts(hs)" in report and '"Importance"' in report
    store = (REPO / "services/api/eax/testing/store.py").read_text(encoding="utf-8")
    assert '"health": health.summary(every)' in store
    run = (REPO / "services/api/eax/testing/run.py").read_text(encoding="utf-8")
    assert "print(summary_text(store.run_detail(conn, r.id), summary_line(files)), flush=True)" in run and 'f"Functional health: {hs' in run
    page = (REPO / "services/web/src/TestRuns.jsx").read_text(encoding="utf-8")
    assert "export function HealthPanel" in page and page.count("<HealthPanel h=") == 2


def test_the_command_line_summary():
    """Owner, 12 Nov 2026: "when test have executed from command line, they should give a summary of what passed what
    failed etc"."""
    from eax.testing import run
    results = [_r("api", "GET /a: every test role", "passed"), _r("ui", "journey: child merge", "failed"),
               _r("security", "image backup (Trivy)", "failed"), _r("ui", "page: #/x", "warning")]
    for x in results:
        x["detail"] = "why it failed"
    d = {"run": {"id": 7}, "results": results, "tally": {"passed": 1, "failed": 2, "warning": 1, "skipped": 0},
         "health": H.summary(results)}
    text = run.summary_text(d)
    assert "Self-test 7: summary" in text and "Pages and journeys" in text and "Functional health: Not healthy" in text
    lines = text.splitlines()
    first = next(i for i, x in enumerate(lines) if "CRITICAL" in x)
    assert "journey: child merge" in lines[first] and "why it failed" in lines[first + 1]
    assert lines.index(next(x for x in lines if "image backup" in x)) > first           # critical failures first
    assert "Warnings (1)" in text
