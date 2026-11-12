"""R2.51 (D609; owner, 12 Nov 2026: "when a test is in progress normal users can not login, they get a banner on login
environment test in progress. Admins can login and only see test results"; new sign-ins wait, those already in get a
banner and their changes wait)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_who_the_lock_does_not_stop():
    from eax import test_lock as tl
    assert tl.exempt("eaadmin", ["super-admin"]) and tl.exempt("ops", ["it-admin"])
    assert tl.exempt("svc-self-test-abc-architect", ["architect"])           # the test's own accounts
    assert not tl.exempt("jane", ["architect"]) and not tl.exempt("", [])


def test_the_refusal_says_why_and_that_reading_goes_on():
    from eax import test_lock as tl
    r = tl.refusal({"id": 7, "by": "eaadmin", "since": datetime(2026, 11, 12, 21, 5), "step": "api", "done": 40})
    assert "self-test 7" in r["message"] and "21:05" in r["message"] and "keep reading" in r["message"]
    assert r["test_in_progress"]["id"] == 7


def test_a_run_left_open_too_long_does_not_keep_people_out():
    src = (REPO / "services/api/eax/test_lock.py").read_text()
    assert "queued_at > now() - interval '{STALE_HOURS} hours'" in src and "state IN ('queued', 'running')" in src


def test_changes_are_refused_for_normal_people_only_while_reading_goes_on():
    auth = (REPO / "services/api/eax/auth.py").read_text()
    assert 'if request.method not in ("GET", "HEAD", "OPTIONS"):\n                    _test_lock(user)' in auth
    assert "abort(423, **test_lock.refusal(run))" in auth and "test_lock.exempt(user.username, user.roles)" in auth
    assert '"test_in_progress": _test_in_progress()' in (REPO / "services/api/eax/api/heartbeat.py").read_text()


def test_the_screens_hold_new_sign_ins_and_show_admins_only_the_self_test():
    app = (REPO / "services/web/src/App.jsx").read_text()
    assert "if (signedIn && testRunShown && testAtSignIn && !testExempt) return <TestInProgress run={testRunShown} />;" in app
    assert 'testRunShown && testExempt && !route.startsWith("#/admin/self-test") ? <TestOnlyPage />' in app
    assert "Environment test in progress" in app and "setInterval(beat, 20000)" in app
    assert 'startsWith("svc-self-test-") ? null : testRun' in app                # the test's browser sees EA Explorer as it is
