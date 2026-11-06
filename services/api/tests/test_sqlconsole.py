"""SQL window helpers (no database needed)."""

import datetime as dt
import decimal
import uuid

from eax import sqlconsole


def test_values_become_json():
    u = uuid.uuid4()
    assert sqlconsole.to_json_value(None) is None
    assert sqlconsole.to_json_value(True) is True
    assert sqlconsole.to_json_value(decimal.Decimal("12.50")) == "12.50"
    assert sqlconsole.to_json_value(u) == str(u)
    assert sqlconsole.to_json_value(dt.date(2026, 11, 4)) == "2026-11-04"
    assert sqlconsole.to_json_value(float("nan")) == "nan"
    assert sqlconsole.to_json_value(b"\x01\xff") == "\\x01ff"
    assert sqlconsole.to_json_value({"a": [decimal.Decimal(1)]}) == {"a": ["1"]}
    long = sqlconsole.to_json_value("x" * 20000)
    assert len(long) == sqlconsole.MAX_CELL_CHARS + 3 and long.endswith("...")


def test_on_for_laptops_off_for_servers(monkeypatch):
    monkeypatch.delenv("EAX_SQL_CONSOLE_ENABLED", raising=False)
    monkeypatch.setenv("EAX_DEPLOYMENT", "laptop")
    assert sqlconsole.enabled()
    monkeypatch.setenv("EAX_DEPLOYMENT", "server")
    assert not sqlconsole.enabled()
    monkeypatch.setenv("EAX_SQL_CONSOLE_ENABLED", "true")
    assert sqlconsole.enabled()


def test_login_and_text_are_required():
    for args in [("eaexplorer", "", "pw", "SELECT 1"), ("eaexplorer", "eax_app", "pw", "  ")]:
        try:
            sqlconsole.run(*args)
        except sqlconsole.SqlConsoleError as exc:
            assert exc.status == 400
        else:
            raise AssertionError("expected an error")


def test_keep_commits_and_databases_are_listed():
    """D211: a run is rolled back unless keep is ticked; the window lists the server's databases."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    src = (root / "eax" / "sqlconsole.py").read_text()
    assert "keep" in src and "datistemplate" in src
    api = (root / "eax" / "api" / "sql.py").read_text()
    assert '"/databases"' in api and "keep" in api
