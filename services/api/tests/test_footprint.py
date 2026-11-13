"""R2.22 (owner, 13 Nov 2026: measure only for now; both `eax footprint` and a System Admin page): each container's
image, own disk, volumes, memory, CPU and seconds to start, kept in work/footprint beside the measurement before."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _load(tmp_path, monkeypatch):
    monkeypatch.setenv("EAX_WORK_MOUNT", str(tmp_path))
    spec = importlib.util.spec_from_file_location("footprint_t", REPO / "services/ops/footprint.py")
    fp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fp)
    return fp


def test_measure_keeps_each_and_shows_the_change(tmp_path, monkeypatch):
    fp = _load(tmp_path, monkeypatch)
    mem = {"v": 300e6}

    def stats(fresh=False):
        return {"containers": [{"id": "aaaaaaaaaaaa1", "key": "api", "service": "api", "state": "running", "image": "eax-api",
                                "layer_bytes": 2e6, "volume_bytes": 0, "memory_bytes": mem["v"], "memory_limit_bytes": 8e9,
                                "cpu_percent": 1.5, "restarts": 0}], "problems": []}

    def docker(*args, timeout=60):
        if args[0] == "inspect":
            return json.dumps([{"Id": "aaaaaaaaaaaa1xyz", "Image": "sha256:1", "State": {
                "StartedAt": "2026-11-13T05:00:00.123456789Z",
                "Health": {"Log": [{"ExitCode": 1, "End": "2026-11-13T05:00:10Z"}, {"ExitCode": 0, "End": "2026-11-13T05:00:42.5Z"}]}}}])
        return json.dumps([{"Size": 512e6}])
    fp.hooks.update(stats=stats, docker=docker)
    first = fp.measure("before")
    row = first["containers"][0]
    assert row["image_mb"] == 512.0 and row["memory_mb"] == 300.0 and row["start_seconds"] == 42.4
    import time
    time.sleep(1.1)
    mem["v"] = 250e6
    fp.measure("after")
    latest = (tmp_path / "footprint/latest.md").read_text()
    assert "| api | 512.0 | 2.0 | 0.0 | 250.0 (-50.0) |" in latest and "(before)" in latest
    got = fp.latest()
    assert got["count"] == 2 and got["before"]["label"] == "before" and got["latest"]["label"] == "after"


def test_wired_in_every_form_and_the_page():
    ops = (REPO / "services/ops/ops.py").read_text()
    assert 'if cmd == "footprint":' in ops and 'self.path == "/footprint"' in ops
    assert "COPY footprint.py /app/footprint.py" in (REPO / "services/ops/Dockerfile").read_text()
    assert 'footprint) shift; compose exec ops python3 /app/ops.py footprint' in (REPO / "eax.sh").read_text()
    assert '"footprint" { Invoke-Interactive @("ops", "python3", "/app/ops.py", "footprint")' in (REPO / "eax.ps1").read_text()
    assert 'stack.interactive([*ops, "footprint"], rest)' in (REPO / "eaxcli/main.py").read_text()
    assert "### footprint [label]" in (REPO / "eaxcli/help.txt").read_text()
    assert '@blp.route("/admin/footprint")' in (REPO / "services/api/eax/api/admin.py").read_text()
    assert '["footprint", "Footprint"' in (REPO / "services/web/src/Admin.jsx").read_text()
