"""The status shows the file systems with the containers (owner, 8 Nov 2026)."""

from pathlib import Path

from eax import admin_check as ac

ROOT = Path(__file__).resolve().parents[1]


def test_full_disks_need_attention():
    h = {"checks": {}, "containers": [], "filesystems": [
        {"path": "/", "label": "Docker's disk", "used_percent": 93.0, "free_bytes": 4e9, "level": "red"},
        {"path": "/eax-work", "label": "Work folder", "used_percent": 93.0, "free_bytes": 4e9, "level": "red", "same_as": "Docker's disk"},
        {"path": "/backups", "label": "Backups folder", "used_percent": 84.0, "free_bytes": 40e9, "level": "amber"},
        {"path": "/x", "label": "Gone", "error": "no such folder"}]}
    got = [p for p in ac.find_problems(h) if p["area"] == "File systems"]
    assert [p["level"] for p in got] == ["red", "amber"]
    assert "Docker's disk is 93% full (4.0 GB free)" in got[0]["text"]


def test_wired_through():
    ops = (ROOT.parent / "ops/ops.py").read_text(encoding="utf-8")
    assert "def filesystems()" in ops and '"filesystems": fs' in ops and 'if cmd == "filesystems":' in ops
    assert 'out["filesystems"]' in (ROOT / "eax/admin_check.py").read_text(encoding="utf-8")
    js = (ROOT.parent / "web/src/ContainerConsole.jsx").read_text(encoding="utf-8")
    assert "function FileSystems" in js and "<FileSystems h={h} />" in js
    repo = ROOT.parents[1]
    assert "Show-FileSystems" in (repo / "eax.ps1").read_text(encoding="utf-8")
    assert "show_filesystems" in (repo / "eax.sh").read_text(encoding="utf-8")
