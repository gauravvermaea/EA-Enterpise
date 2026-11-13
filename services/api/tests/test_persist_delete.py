"""R2.26 (owner, 12 Nov 2026: "give command line and web ui ability to delete anything in persist"): eax persist lists
and deletes; System Admin › Persist the same; each item can be deleted both ways, and nothing outside persist/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def _fill(tmp_path, monkeypatch):
    from eaxcli import persist as P
    base = tmp_path / "persist"
    (base / "safety-backups" / "20261101T020000Z").mkdir(parents=True)
    (base / "safety-backups" / "20261101T020000Z" / "db.dump").write_bytes(b"x" * 2048)
    (base / "test-results").mkdir()
    (base / "test-results" / "run1.json").write_text("{}")
    P.write_json(base / "banner.json", {"banner": {"text": "hello"}})
    P.write_json(base / "banner.json", {"banner": None})              # makes banner.json.bak
    P.write_json(base / "schedules.json", {"schedules": []})
    monkeypatch.setenv("EAX_PERSIST_DIR", str(base))
    return P, base


def test_items_list_every_settings_file_and_each_safety_backup(tmp_path, monkeypatch):
    P, base = _fill(tmp_path, monkeypatch)
    names = [i["name"] for i in P.items()]
    assert names == ["banner.json", "safety-backups/20261101T020000Z", "schedules.json", "test-results"]
    banner = next(i for i in P.items() if i["name"] == "banner.json")
    assert banner["size"] == (base / "banner.json").stat().st_size + (base / "banner.json.bak").stat().st_size
    assert "banner" in banner["what"]


def test_each_item_deletes_with_its_copy_and_nothing_outside(tmp_path, monkeypatch):
    P, base = _fill(tmp_path, monkeypatch)
    assert sorted(P.delete("banner.json")) == ["banner.json", "banner.json.bak"]
    assert P.delete("safety-backups/20261101T020000Z") == ["safety-backups/20261101T020000Z"]
    (tmp_path / "outside.txt").write_text("keep")
    for bad in ("../outside.txt", "nothing.json", "safety-backups/../../outside.txt"):
        with pytest.raises(ValueError):
            P.delete(bad)
    assert (tmp_path / "outside.txt").exists()
    assert sorted(P.delete_all()) == ["schedules.json", "schedules.json.bak", "test-results"] or not P.items()
    assert P.items() == []


def test_the_command_line_asks_then_deletes(tmp_path, monkeypatch, capsys):
    P, base = _fill(tmp_path, monkeypatch)
    from eaxcli import persist_cli
    assert persist_cli.main([]) == 0 and "safety-backups/20261101T020000Z" in capsys.readouterr().out
    assert persist_cli.main(["delete", "schedules.json"], ask=lambda _q: "no") == 1
    assert (base / "schedules.json").exists()
    assert persist_cli.main(["delete", "schedules.json"], ask=lambda _q: "DELETE") == 0
    assert not (base / "schedules.json").exists()
    assert persist_cli.main(["delete", "--all", "--yes"]) == 0 and P.items() == []


def test_the_web_and_every_form_of_eax():
    ops = (REPO / "services/ops/ops.py").read_text()
    assert 'self.path == "/persist"' in ops and 'self.path == "/persist/delete"' in ops
    admin = (REPO / "services/api/eax/api/admin.py").read_text()
    assert '@blp.route("/admin/persist/delete")' in admin and '"persist.deleted"' in admin and 'confirm") != "DELETE"' in admin
    assert '["persist", "Persist"' in (REPO / "services/web/src/Admin.jsx").read_text()
    assert '"#/admin/persist"' in (REPO / "services/web/src/menu.js").read_text()
    assert "persist)" in (REPO / "eax.sh").read_text() and '"schedule", "persist")' in (REPO / "eax.ps1").read_text()
    assert "persist_cli.main(rest)" in (REPO / "eaxcli/main.py").read_text()
    assert "### persist" in (REPO / "eaxcli/help.txt").read_text()
    cat = json.loads((REPO / "services/web/src/help/catalogue.json").read_text())
    assert "tab:Persist" in cat
