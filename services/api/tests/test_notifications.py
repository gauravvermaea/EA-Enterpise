"""Phase 8.1: notifications, requests, webhooks, metamodel push-down (no database needed)."""

import hashlib
import hmac
import pathlib
import re

from eax import change_log, notify, pushdown, webhooks

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_routes_are_declared_and_registered():
    src = (ROOT / "eax" / "api" / "notifications.py").read_text(encoding="utf-8")
    for path in ("/notifications", "/notifications/counts", "/requests", "/requests/<rid>"):
        assert f'@personal_blp.route("{path}")' in src, path        # the personal data service's (/api/v1/me, R2.53)
    for path in ("/models/<uuid:model_id>/pushdown", "/change-documents/<ref>", "/admin/webhooks"):
        assert f'@blp.route("{path}")' in src, path
    assert "personal_blp" in (ROOT / "eax" / "app.py").read_text(encoding="utf-8")
    assert "notifications_blp" in (ROOT / "eax" / "app.py").read_text(encoding="utf-8")


def test_every_route_needs_sign_in():
    src = (ROOT / "eax" / "api" / "notifications.py").read_text(encoding="utf-8")
    assert src.count("@blp.route(") > 0
    for block in src.replace("@personal_blp.doc(security=SECURITY)", "@blp.doc(security=SECURITY)").split("    @blp.doc(security=SECURITY)")[1:]:
        assert "@require_auth(" in block.split("def ")[0], block[:120]


def test_audited_actions_that_notify_are_known_actions():
    assert set(notify.FROM_AUDIT) <= set(change_log.ACTIONS)
    for kind, category, _needs, title in notify.FROM_AUDIT.values():
        assert category in notify.CATEGORIES and kind.split(".")[0] in notify.CATEGORIES
        assert "{actor}" in title and "{model}" in title


def test_only_commit_requests_need_action_from_the_audit():
    assert [a for a, v in notify.FROM_AUDIT.items() if v[2]] == ["changes.request"]


def test_webhook_signature_is_hmac_sha256_of_the_body():
    body = b'{"kind":"x"}'
    assert webhooks.sign("s3cret", body) == "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()


def test_no_email_anywhere():
    """D209: notifications go to the application and to webhooks, never by email."""
    for f in ("notify.py", "webhooks.py", "tickets.py", "pushdown.py"):
        src = (ROOT / "eax" / f).read_text(encoding="utf-8").lower()
        assert "smtplib" not in src and "sendmail" not in src, f


def test_guids_are_recognised_for_translation():
    assert pushdown._as_uuid("6b9c0f5e-1d2a-4b8e-9c3f-0a1b2c3d4e5f")
    assert pushdown._as_uuid("Application Component") is None
    assert pushdown._as_uuid(12) is None


def test_metamodel_versions_record_their_changes():
    src = (ROOT / "eax" / "metamodel_edit.py").read_text(encoding="utf-8")
    assert len(re.findall(r"^ {8}_record_change\(conn", src, re.M)) == 2   # one change (apply) and a batch (apply_many)


def test_requests_and_notifications_are_not_in_reports():
    sql = (ROOT / "migrations" / "sql" / "0018_notifications.sql").read_text(encoding="utf-8")
    revoke = re.search(r"REVOKE ALL ON (.*?) FROM eax_report", sql, re.S).group(1)
    for t in ("core.requests", "core.notifications", "core.webhooks"):
        assert t in revoke


def test_mcp_reads_and_sends_requests_but_does_not_resolve():
    src = (ROOT / "eax" / "mcp_server.py").read_text(encoding="utf-8")
    for tool in ("list_my_notifications", "list_my_requests", "get_request", "send_request"):
        assert f"async def {tool}(" in src
    assert "notify.resolve(" not in src and "set_status(" not in src
