"""Code coverage in testing (D642; owner, 13 Nov 2026: "In testing can we get code coverage? If so then build it")."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_off_by_default_and_costs_nothing(monkeypatch):
    from eax import coverage_probe as cp
    monkeypatch.delenv("EAX_COVERAGE", raising=False)
    assert not cp.enabled() and cp.start() is False
    assert cp.report()["on"] is False and "EAX_COVERAGE=on" in cp.report()["why"]


def test_the_summary_by_area_and_file():
    from eax import coverage_probe as cp
    files = {"/app/eax/api/models.py": {"summary": {"num_statements": 100, "covered_lines": 80}},
             "/app/eax/repository.py": {"summary": {"num_statements": 50, "covered_lines": 10}},
             "/app/eax/empty.py": {"summary": {"num_statements": 0, "covered_lines": 0}}}
    s = cp.summarise(files)
    assert s["percent"] == 60.0 and s["lines"] == 150 and s["run"] == 90
    assert [a["area"] for a in s["areas"]] == ["core", "api"]                 # the least covered first
    assert s["files"][0] == {"file": "eax/repository.py", "lines": 50, "run": 10, "percent": 20.0}


def test_the_self_test_keeps_the_coverage_with_its_run(monkeypatch, tmp_path):
    from eax.testing import run as R
    got = []
    r = R.Run.__new__(R.Run)
    r.dir, r.counts, r.only = tmp_path, {}, None
    r.recorder = lambda suite: (lambda name, outcome, detail="", ms=0: got.append((name, outcome, detail)))
    r.log = lambda m: None
    c = {"on": True, "percent": 61.5, "run": 615, "lines": 1000, "areas": [{"area": "api", "percent": 40.0, "run": 4, "lines": 10}],
         "files": [{"file": "eax/x.py", "run": 1, "lines": 2, "percent": 50.0}]}
    monkeypatch.setattr(R.api_matrix, "call", lambda *a, **k: (200, json.dumps(c)))
    assert R.coverage_result(r, "tok")["percent"] == 61.5
    assert got[0][1] == "passed" and "61.5% of lines" in got[0][2] and r.counts["coverage %"] == 61.5
    assert "Code coverage of the API: 61.5%" in (tmp_path / "coverage.html").read_text()
    assert json.loads((tmp_path / "coverage.json").read_text())["run"] == 615
    monkeypatch.setattr(R.api_matrix, "call", lambda *a, **k: (200, json.dumps({"on": False, "why": "off"})))
    got.clear()
    assert R.coverage_result(r, "tok") is None and got[0][1] == "skipped"


def test_it_is_wired_from_the_worker_start_to_ci():
    wsgi = (REPO / "services/api/eax/wsgi.py").read_text()
    assert wsgi.index("coverage_probe.start()") < wsgi.index("from .app import create_app")
    assert '@blp.route("/admin/coverage")' in (REPO / "services/api/eax/api/admin.py").read_text()
    assert "coverage>=7.6" in (REPO / "services/api/requirements.txt").read_text()
    assert "pytest-cov" in (REPO / "services/api/requirements-dev.txt").read_text()
    assert "--cov=eax" in (REPO / "ci/github-actions-ci.yml").read_text()
    assert "EAX_COVERAGE=on" in (REPO / "deploy/templates/eaexplorer.laptop.env").read_text()
    assert "EAX_COVERAGE=off" in (REPO / "deploy/templates/eaexplorer.server.env").read_text()
    assert 'coverage_result(r, tokens.get("super-admin", ""))' in (REPO / "services/api/eax/testing/run.py").read_text()
