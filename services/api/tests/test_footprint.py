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
    assert "### footprint [label] | --watch" in (REPO / "eaxcli/help.txt").read_text()
    assert '@blp.route("/admin/footprint")' in (REPO / "services/api/eax/api/admin.py").read_text()
    assert '["footprint", "Footprint"' in (REPO / "services/web/src/Admin.jsx").read_text()


# ---------------------------------------------------------------- memory over time (Release 3.5, R3.5-M1)
STATS = "\n".join(json.dumps(x) for x in [
    {"Name": "eaexplorer-api-1", "MemUsage": "1.5GiB / 7.6GiB"},
    {"Name": "eaexplorer-db-1", "MemUsage": "800MiB / 7.6GiB"},
    {"Name": "eaexplorer-testrunner", "MemUsage": "2GiB / 7.6GiB"},
    {"Name": "otherproject-web-1", "MemUsage": "5GiB / 7.6GiB"},          # another installation: not counted
])
MEMINFO = "MemTotal: 16384000 kB\nMemFree: 1000 kB\nMemAvailable: 6144000 kB\nSwapTotal: 4096000 kB\nSwapFree: 4096000 kB\n"


def _ops_size(text):
    import re
    m = re.match(r"\s*([\d.]+)\s*([kKMGT]?i?B)", text)
    unit = m.group(2).upper().replace("I", "")
    return int(float(m.group(1)) * {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9}[unit] * (1.024 ** "BKMGT".index(unit[0]) if "i" in m.group(2) else 1))


def _memory_fp(tmp_path, monkeypatch, meminfo=MEMINFO):
    fp = _load(tmp_path, monkeypatch)
    info = tmp_path / "meminfo"
    info.write_text(meminfo)
    monkeypatch.setattr(fp, "MEMINFO", str(info))
    monkeypatch.setattr(fp, "host_memory", lambda path=str(info), _f=fp.host_memory: _f(path))
    calls = []
    fp.hooks.update(docker=lambda *a, timeout=60: calls.append(a) or STATS, project=lambda: "eaexplorer", _size=_ops_size)
    return fp, calls


def test_a_sample_counts_this_installation_and_the_test_runner_with_one_light_call(tmp_path, monkeypatch):
    fp, calls = _memory_fp(tmp_path, monkeypatch)
    s = fp.sample()
    assert set(s["containers"]) == {"api", "db", "testrunner"}                       # the other project left out
    assert s["containers"]["db"] == round(800 * 1.024 ** 2, 1)
    assert calls == [("stats", "--no-stream", "--format", "{{json .}}")]           # nothing heavier (no sizes)
    assert s["host"] == {"total_mb": 16000.0, "available_mb": 6000.0, "swap_total_mb": 4000.0, "swap_used_mb": 0.0}


def test_service_names():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fp_names", REPO / "services/ops/footprint.py")
    fp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fp)
    assert fp.service_of("eaexplorer-api-1", "eaexplorer") == "api"
    assert fp.service_of("eaexplorer-reports-init-1", "eaexplorer") == "reports-init"
    assert fp.service_of("eaexplorer-testrunner", "eaexplorer") == "testrunner"


def test_the_recorder_keeps_lowest_average_peak_and_paging(tmp_path, monkeypatch):
    fp = _load(tmp_path, monkeypatch)
    rec = fp.Recorder("full test")
    host = {"total_mb": 16000.0, "available_mb": 6000.0, "swap_total_mb": 4000.0, "swap_used_mb": 10.0}
    rec.add({"at": 1000.0, "containers": {"api": 1000.0, "testrunner": 500.0}, "host": host})
    rec.add({"at": 1015.0, "containers": {"api": 1500.0, "testrunner": 3000.0}, "host": {**host, "available_mb": 900.0, "swap_used_mb": 300.0}})
    rec.add({"at": 1030.0, "containers": {"api": 1200.0, "testrunner": 2000.0}, "host": host})
    m = rec.result()
    api = next(r for r in m["containers"] if r["container"] == "api")
    assert (api["lowest_mb"], api["average_mb"], api["peak_mb"]) == (1000.0, 1233.3, 1500.0)
    assert m["containers"][0]["container"] == "testrunner"                           # the biggest peak first
    assert m["total_peak_mb"] == 4500.0 and m["samples"] == 3 and m["within_target"]
    assert m["host"]["least_available_mb"] == 900.0 and m["host"]["most_swap_used_mb"] == 300.0 and m["host"]["paged"]
    md = fp.memory_markdown(m)
    assert "**Peak of the whole installation: 4.4 GB**" in md and "within the guide of 10.0 GB, not a limit" in md
    assert "**it paged**" in md and "| api | 1000.0 | 1233.3 | 1500.0 |" in md


def test_no_paging_when_swap_stays_put_and_the_guide_can_be_set(tmp_path, monkeypatch):
    monkeypatch.setenv("EAX_MEMORY_TARGET_MB", "4000")
    fp = _load(tmp_path, monkeypatch)
    rec = fp.Recorder()
    host = {"total_mb": 16000.0, "available_mb": 6000.0, "swap_total_mb": 4000.0, "swap_used_mb": 200.0}
    rec.add({"at": 1.0, "containers": {"api": 4500.0}, "host": host})
    rec.add({"at": 2.0, "containers": {"api": 4400.0}, "host": {**host, "swap_used_mb": 230.0}})
    m = rec.result()
    assert not m["host"]["paged"] and not m["within_target"] and m["target_mb"] == 4000.0
    assert "above the guide of 3.9 GB" in fp.memory_markdown(m) and "no paging" in fp.memory_markdown(m)


def test_a_watch_runs_until_stopped_and_keeps_its_table(tmp_path, monkeypatch):
    import threading
    fp, _calls = _memory_fp(tmp_path, monkeypatch)
    run = tmp_path / "tests" / "run1"
    run.mkdir(parents=True)
    stop = threading.Event()
    n = {"v": 0}
    real = fp.sample

    def counting():
        n["v"] += 1
        if n["v"] == 3:
            stop.set()
        return real()
    monkeypatch.setattr(fp, "sample", counting)
    m = fp.watch("self-test 1", seconds=0, every=0.01, folder=run, stop=stop)
    assert m["samples"] == 3 and m["label"] == "self-test 1"
    assert (run / "memory.md").read_text().startswith("# EA Explorer memory") and (run / "memory.json").exists()
    assert (tmp_path / "footprint/latest-memory.md").exists()
    got = fp.latest()
    assert got["memory"]["samples"] == 3 and got["target_mb"] == 10240.0 and got["count"] == 0   # not a footprint row


def test_a_missed_sample_never_stops_a_watch(tmp_path, monkeypatch):
    fp = _load(tmp_path, monkeypatch)
    said = []
    monkeypatch.setattr(fp, "sample", lambda: (_ for _ in ()).throw(RuntimeError("docker away")))
    m = fp.watch("x", seconds=0.05, every=0.01, say=said.append)
    assert m["samples"] == 0 and any("a sample was missed: docker away" in s for s in said)


def test_the_command_line_watch(tmp_path, monkeypatch, capsys):
    fp = _load(tmp_path, monkeypatch)
    got = {}
    monkeypatch.setattr(fp, "watch", lambda label, seconds, say=None: got.update(label=label, seconds=seconds) or fp.Recorder(label).result())
    assert fp.cli(["--watch", "30", "at", "rest"]) == 0
    assert got == {"label": "at rest", "seconds": 1800.0}
    assert fp.cli(["--watch"]) == 0 and got["seconds"] == 600.0
    assert "Kept in work/footprint: latest-memory.md" in capsys.readouterr().out


def test_every_self_test_run_is_watched_and_never_stopped_by_it():
    runs = (REPO / "services/ops/testruns.py").read_text()
    assert "memory = memory_watch(folder, run_id, level, suites)" in runs
    assert "        if memory is not None:\n            memory.set()" in runs                # stopped with the run, whatever happens
    assert "except Exception:  # noqa: BLE001 - measuring is never in a test's way" in runs
    assert "footprint.hooks.update(stats=stats, docker=docker, project=project, _size=_size)" in (REPO / "services/ops/ops.py").read_text()
    help_ = (REPO / "eaxcli/help.txt").read_text()
    assert "### footprint [label] | --watch [minutes] [label]" in help_ and "$ {eax} footprint --watch 30 at-rest" in help_
    page = (REPO / "services/web/src/Footprint.jsx").read_text()
    assert "<MemoryWatch w={data.memory} />" in page and "a guide, not a limit" in page
