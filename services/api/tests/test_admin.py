"""Phase 10: the administration console's settings, start-up view, licences, the operations helper (no database)."""

import json
import os
import pathlib

import pytest

from eax import settings as st
from eax.metamodel_edit import EditError

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_settings_are_checked():
    assert st.check("upload_max_mb", "25") == 25
    assert st.check("financial_year_start", 3) == 3
    assert st.check("time_zone", "Africa/Johannesburg") == "Africa/Johannesburg"
    for key, bad in (("upload_max_mb", 500), ("time_zone", "Mars/Olympus"), ("date_format", "YY"), ("base_currency", "XXX"),
                     ("financial_year_start", 13), ("nope", 1)):
        with pytest.raises(EditError):
            st.check(key, bad)
    assert {v[0] for v in st.REGISTRY.values()} == {"application", "system"}
    assert {"base_currency", "time_zone", "date_format", "financial_year_start"} <= {k for k, v in st.REGISTRY.items() if v[0] == "application"}


def test_only_super_admin_changes():
    class U:
        roles = ["it-admin"]
    with pytest.raises(EditError):
        st.update(None, U(), {"upload_max_mb": 10})


def test_startup_settings_in_clear_text(monkeypatch):   # IT and Super Admins only (owner, 5 Nov 2026)
    monkeypatch.setenv("EAX_DB_PASSWORD", "very-secret")
    monkeypatch.setenv("EAX_CHANGELOG_DB_URL", "postgresql://eax_app:hidden@db:5432/eaexplorer")
    monkeypatch.setenv("EAX_HOSTNAME", "localhost")
    flat = {x["key"]: x["value"] for g in st.startup()["groups"] for x in g["settings"]}
    assert flat["EAX_DB_PASSWORD"] == "very-secret" and "eax_app:hidden@" in flat["EAX_CHANGELOG_DB_URL"]
    assert flat["EAX_HOSTNAME"] == "localhost"


def test_licences_and_helper():
    lic = json.loads((ROOT / "eax" / "licences.json").read_text(encoding="utf-8"))
    assert "AGPL-3.0" in lic["own"] and any(x["product"] == "PostgreSQL" for x in lic["items"])
    ops = (ROOT.parent / "ops" / "ops.py").read_text(encoding="utf-8")
    assert "X-Ops-Token" in ops and "com.docker.compose.project" in ops
    compose = (ROOT.parent.parent / "docker-compose.yml").read_text(encoding="utf-8")
    assert "/var/run/docker.sock" in compose and "EAX_OPS_URL" in compose
    assert os.path.exists(ROOT / "migrations" / "sql" / "0016_settings.sql")


def test_admin_console_in_the_web():
    src = (WEB / "Admin.jsx").read_text(encoding="utf-8")
    for bit in ("/api/v1/admin/settings", "/api/v1/admin/restart", "/api/v1/admin/licences", "Type RESTART to confirm"):
        assert bit in src, bit
    app = (WEB / "App.jsx").read_text(encoding="utf-8")
    assert "#/admin" in app and "setAppSettings" in app
    assert "toLocaleString()" not in "".join(p.read_text(encoding="utf-8") for p in WEB.glob("*.jsx"))   # D182: installation formats
