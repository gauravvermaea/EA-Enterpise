"""R3.14: the three journey failures of the last Release 2 full test (13 Nov 2026, 17:25), all the tests' own timing on
a busy machine: a dialog closing later than the step looked, a new row not in the list yet when the step looked for it,
and a merge request sent more slowly than the step waited."""

from __future__ import annotations

from eax.testing import ui_flows as uf


class _Loc:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel

    def filter(self, **_kw):
        return self

    def count(self):
        return 1 if self.page.looks >= self.page.shows_after else 0

    def nth(self, _i):
        return self


class _Page:
    """A page whose row (or pop-up) shows only after the step has looked `shows_after` times."""

    def __init__(self, shows_after):
        self.looks, self.shows_after = 0, shows_after

    def locator(self, sel):
        self.looks += 1
        return _Loc(self, sel)

    def wait_for_timeout(self, _ms):
        pass


def test_a_row_step_waits_for_its_row(monkeypatch):
    monkeypatch.setattr(uf, "_visible", lambda loc: True)
    page = _Page(shows_after=4)                       # the list catches up on the fourth look
    root = uf._root(page, {"click": "Turn off", "row": "self_test_x schedule super-admin"})
    assert root is not None and root is not page and page.looks >= 4
    pop = _Page(shows_after=3)
    assert uf._root(pop, {"click": "Open the request", "within": uf.DIALOG}) is not None


def test_a_row_that_never_comes_gives_up_after_the_steps_timeout(monkeypatch):
    monkeypatch.setattr(uf, "_visible", lambda loc: True)
    t = {"now": 0.0}
    monkeypatch.setattr(uf.time, "time", lambda: t.__setitem__("now", t["now"] + 1) or t["now"])
    assert uf._root(_Page(shows_after=10**6), {"click": "X", "row": "never", "timeout": 5000}) is None
    assert t["now"] < 20                                              # about 5 seconds, not forever
    t["now"] = 0.0
    assert uf._root(_Page(shows_after=10**6), {"click": "X", "row": "never", "optional": True}) is None
    assert t["now"] < 8                                               # an optional step: 3 seconds
    assert uf._root(_Page(0), {"click": "X"}).__class__ is _Page      # no row, no pop-up: the page itself


def test_the_steps_wait_longer_where_the_machine_was_busy():
    steps = {j["name"]: j["steps"] for j in uf.JOURNEYS}
    it = steps["project: iteration, frozen phase, back"]
    assert {"expect_not": "Note (optional)", "timeout": 8000} in it
    merge = steps["child merge: send, accept, refresh"]
    assert {"click": "Open the request", "within": uf.DIALOG, "wait": 2000, "timeout": 240000} in merge


def test_a_failed_step_says_what_an_open_dialog_showed():
    class P:
        def evaluate(self, _js):
            return {"at": "#/model-admin/x/send", "h1": ["m"], "status": [], "dialog": "Send m for merge … Sending…"}
    assert 'the open dialog: "Send m for merge … Sending…"' in uf._page_says(P())
