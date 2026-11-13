"""Bugs from the laptop's full run of 12 Nov 2026 (D599: each test fails without its fix).

1. "write metamodel: add a pick list" waited past a minute (599, no answer): every metamodel change rebuilt the typed
   report views, waiting without limit for their one lock. Now only changes the views are made of (entity types,
   attributes, lifecycles) rebuild them, and the rebuild waits seconds at most, then leaves it to the next refresh.
2. "journey: project: iteration, frozen phase, back as architect" (step 7): the journey's steps looked for the button,
   the choice and the field on the whole page, before the open dialog's; now a dialog's own come first, a radio that
   was not chosen says so, and the journey checks what saving said."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def test_only_changes_the_views_are_made_of_rebuild_them():
    from eax import metamodel_edit as ed
    for op in ("pick_list.create", "pick_list.add_value", "pick_list.retire_value", "rule.create", "mapping.add",
               "relationship_type.create"):
        assert not ed.changes_views(op), op
    for op in ("entity_type.create", "entity_type.update", "attribute.create", "attribute.remove", "lifecycle.create"):
        assert ed.changes_views(op), op
    assert set(ed.OPS) >= {"pick_list.create", "attribute.create"}
    src = inspect.getsource(ed.apply) + inspect.getsource(ed.apply_many)
    assert src.count("changes_views(") == 2


class _Exc(Exception):
    sqlstate = "55P03"


class _Conn:
    """Enough of a connection: the refresh fails as a lock wait that ran out."""
    def __init__(self, fail):
        self.fail, self.sql, self.rolled = fail, [], False

    def execute(self, stmt, params=None):
        q = str(stmt)
        self.sql.append((q, params))
        if "rpt.refresh_typed_views()" in q and self.fail:
            from eax import reports

            class Busy(reports.DBAPIError):
                def __init__(self, orig):
                    Exception.__init__(self, str(orig))
                    self.orig = orig
            raise Busy(self.fail)

        class R:
            def scalar_one(self_inner):
                return "0" if "current_setting" in q else 3
        return R()

    def begin_nested(self):
        conn = self

        class Sp:
            def commit(self):
                pass

            def rollback(self):
                conn.rolled = True
        return Sp()


def test_the_rebuild_waits_seconds_then_leaves_it_for_later():
    from eax import reports
    ok = _Conn(None)
    assert reports.refresh_typed_views(ok) == 3
    assert any(p == {"w": "10s"} for _, p in ok.sql) and ok.sql[-1][1] == {"w": "0"}      # the wait put back
    busy = _Conn(_Exc("canceling statement due to lock timeout"))
    assert reports.refresh_typed_views(busy) == -1 and busy.rolled
    other = _Conn(type("E", (Exception,), {"sqlstate": "42P01"})("no such view"))
    with pytest.raises(reports.DBAPIError):
        reports.refresh_typed_views(other)                                              # a real fault still says so
    assert '"eax.reports_refresh"' in (REPO / "services/api/eax/jobs.py").read_text()


def test_journey_steps_look_in_the_open_dialog_first():
    from eax.testing import ui_flows as uf
    src = inspect.getsource(uf.step)
    assert src.count("_in_modal_first(") >= 4 and "was not chosen" in src
    j = next(j for j in uf.JOURNEYS if j["name"] == "project: iteration, frozen phase, back")
    assert {"expect": "Now a Transition Planning"} in j["steps"]
    assert "setTimeout(onClose, 1500)" in (REPO / "services/web/src/IterationControl.jsx").read_text()


def test_in_modal_first_prefers_the_dialog_and_falls_back():
    from eax.testing import ui_flows as uf

    class Loc:
        def __init__(self, n):
            self.n = n

        def count(self):
            return self.n

        def nth(self, i):
            return "dialog"

    class Page:
        def __init__(self, n):
            self.n = n

        def locator(self, sel):
            return Loc(self.n)

    orig = uf._visible
    uf._visible = lambda el: True
    try:
        page = Page(1)
        assert uf._in_modal_first(page, page, {}, lambda w: "in " + ("dialog" if w == "dialog" else "page")) == "in dialog"
        assert uf._in_modal_first(page, page, {}, lambda w: None if w == "dialog" else "page") == "page"
        assert uf._in_modal_first(page, page, {"within": ".x"}, lambda w: "page" if w is page else "d") == "page"
        none = Page(0)
        assert uf._in_modal_first(none, none, {}, lambda w: "page" if w is none else "d") == "page"
    finally:
        uf._visible = orig
