"""Operations insight and housekeeping (phases 35 and 35.1, D371, D442 to D445). No database needed."""

from __future__ import annotations

from pathlib import Path

from eax import operations as ops

ROOT = Path(__file__).resolve().parents[1]
G = "0b4f6a52-4c1e-4f7d-9a8e-3b2c1d0e9f11"


def test_each_call_is_counted_by_part_and_model():
    assert ops.feature_of(f"/api/v1/models/{G}/entities/x") == ("models/entities", G)
    assert ops.feature_of(f"/api/v1/models/{G}") == ("models/model", G)
    assert ops.feature_of(f"/api/v1/projects/{G}/steps/") == ("projects/steps", "")
    assert ops.feature_of("/api/v1/admin/backups/") == ("admin/backups", "")
    assert ops.feature_of("/api/v1/change-log/") == ("change-log", "")
    assert ops.feature_of("/api/v1/models/") == ("models", "")


def test_counts_wait_in_memory_and_are_put_back_when_they_cannot_be_written():
    ops._counts.clear()
    ops.count_call("user_architect", f"/api/v1/models/{G}/entities/")
    ops.count_call("user_architect", f"/api/v1/models/{G}/entities/")
    ops.count_call("", "/api/v1/models/")                  # nobody signed in: not counted
    ops.count_call("x", "/api/health")                     # not an API call of a part
    assert sum(ops._counts.values()) == 2

    class Broken:
        def execute(self, *_a, **_k):
            raise RuntimeError("down")
    assert ops.flush(Broken()) == 0 and sum(ops._counts.values()) == 2  # kept for next time

    class Fine:
        rows: list = []

        def execute(self, _sql, params):
            self.rows.append(params)
    f = Fine()
    assert ops.flush(f) == 1 and f.rows[0]["n"] == 2 and f.rows[0]["m"] == G and f.rows[0]["a"] == "models"
    assert not ops._counts


def test_the_defaults_only_archive_and_delete_nothing():
    assert set(ops.DEFAULTS) == set(ops.RULES)
    assert all(a in ("keep", "archive") for a, _d in ops.DEFAULTS.values())
    assert ops.DEFAULTS["loads"] == ("archive", 90) and ops.DEFAULTS["task_files"] == ("archive", 90)
    assert ops.DEFAULTS["notifications"] == ("archive", 365)
    assert ops.DEFAULTS["history_versions"][0] == "keep"                    # off until a Super Admin sets an age (D445)
    sql = (ROOT / "migrations" / "sql" / "0036_machine_access_ops.sql").read_text()
    for code, (action, days) in ops.DEFAULTS.items():
        assert f"('{code}', '{action}', {days})" in sql, code
    for code, (_l, _c, actions, min_days) in ops.RULES.items():
        assert ops.DEFAULTS[code][0] in actions and ops.DEFAULTS[code][1] >= min_days
        assert code in ops._FIND or code in ops._COUNT or code == "history_versions", code


def test_old_history_is_removed_only_as_the_owner_set_it():
    """D445: off by default; a Super Admin sets an age of at least a year; removed, never archived; pinned moments and rows
    kept; the guard lifted only inside the run's own transaction and checked back on; recorded in the change log."""
    assert ops.RULES["history_versions"][2] == ("keep", "delete") and ops.RULES["history_versions"][3] == 365
    assert "history_versions" in ops.SUPER_ONLY and "history_versions" not in ops._FIND
    import pytest

    class C:
        def execute(self, *_a, **_k):
            raise AssertionError("nothing written")
    with pytest.raises(PermissionError):
        ops.set_rule(C(), "it", "history_versions", "delete", 400, ("it-admin",))
    with pytest.raises(ValueError):
        ops.set_rule(C(), "sa", "history_versions", "delete", 100, ("super-admin",))
    due = ops._DUE
    assert "next_at IS NOT NULL" in due                                    # never the current version
    assert "row_guid = ANY" in due and "pin.at >= v.changed_at AND pin.at < v.next_at" in due
    src = (ROOT / "eax" / "operations.py").read_text()
    body = src[src.index("def history_due"):src.index("def scheduled")]
    assert body.index("DISABLE TRIGGER") < body.index("DELETE FROM history.row_versions") < body.index("ENABLE TRIGGER")
    assert "tgenabled" in body and "housekeeping.history_removed" in body
    pins = src[src.index("def _pins"):src.index("def history_due")]
    for what in ("core.model_tags", "proj.view_evidence", "proj.gov_records"):
        assert what in pins
    from eax import change_log as cl
    assert "housekeeping.history_removed" in cl.ACTIONS
    sql = (ROOT / "migrations" / "sql" / "0036_machine_access_ops.sql").read_text()
    assert "TRIGGER" not in sql.upper()                                    # D248: the guard itself is untouched


def test_the_nightly_job_and_the_metrics():
    jobs = (ROOT / "eax" / "jobs.py").read_text()
    assert '@app.periodic(cron="40 2 * * *")' in jobs and "operations.scheduled(conn)" in jobs
    assert ops._line("eax_models", 3, {"kind": 'a"b'}) == 'eax_models{kind="a\\"b"} 3'
    names = [n for n, *_ in ops.METRICS]
    assert len(names) == len(set(names)) and all(n.startswith("eax_") for n in names)


def test_idle_models_are_a_report_only():
    src = (ROOT / "eax" / "operations.py").read_text()
    assert ops.IDLE_DAYS == 180
    # nothing about idle models notifies or changes anything
    body = src[src.index("def insight"):src.index("def model_use")]
    assert "notify" not in body and "UPDATE" not in body and "DELETE" not in body
