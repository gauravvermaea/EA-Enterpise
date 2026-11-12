"""R2.21 (owner, 11 Nov 2026: "Total CPU > 100%"): Docker gives a container's CPU as a share of one core, so the
Containers page's total ran past 100% on a machine with several cores. Now each figure is a share of the whole host,
with the cores in use beside it. Tested with a fake 8-core host."""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _ops(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "eaexplorer.env").write_text("EAX_TIMEZONE=UTC\n")
    for k in ("EAX_WORK_MOUNT", "EAX_BACKUP_MOUNT", "EAX_REPO_MOUNT"):
        monkeypatch.setenv(k, str(work))
    spec = importlib.util.spec_from_file_location("ops_cpu", REPO / "services" / "ops" / "ops.py")
    ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ops)
    return ops


def test_cpu_is_a_share_of_the_whole_host(tmp_path, monkeypatch):
    ops = _ops(tmp_path, monkeypatch)
    assert ops.cpu_of_host(250.0, 8) == (31.2, 2.5)           # two and a half of eight cores
    assert ops.cpu_of_host(800.0, 8) == (100.0, 8.0)          # every core busy: 100%, never more
    assert ops.cpu_of_host(None, 8) == (None, None)
    assert ops.cpu_of_host(50.0, None) == (None, 0.5)         # the host unknown: no share
    monkeypatch.setattr(ops, "docker", lambda *a, **k: "8\n")
    ops._host_cpus_cache["n"] = None
    assert ops.host_cpus() == 8
    # the containers of a busy 8-core laptop add up to no more than 100%
    shares = [ops.cpu_of_host(x, 8)[0] for x in (250.0, 300.0, 150.0, 100.0)]
    assert sum(shares) <= 100


def test_the_page_shows_the_share_and_the_cores():
    page = (REPO / "services" / "web" / "src" / "ContainerConsole.jsx").read_text(encoding="utf-8")
    assert "CPU is a share of the whole machine" in page and "CPU is per core" not in page
    assert 'sum("cpu_cores")' in page and "h.host_cpus" in page
