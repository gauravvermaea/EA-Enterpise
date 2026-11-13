"""Installation-wide webhooks (phase 8.1, D209): IT and Super Admins add an address, the categories of notification it
receives and a shared secret. Each notification is sent as one plain JSON format, signed with HMAC-SHA256 of the body
in the X-EAX-Signature header ("sha256=<hex>"), retried with back-off when the receiver fails, with a delivery log.
Never email.

Deliveries are rows in core.webhook_deliveries; a job every minute sends the ones due (eax.jobs.deliver_webhooks).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.request

from sqlalchemy import text

from .notify import CATEGORIES, _one, _rows

MAX_ATTEMPTS = 8           # then failed: 1, 2, 4, 8, 16, 32, 64 minutes apart (about two hours in all)
TIMEOUT = 10


class HookError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def queue(conn, nid: int) -> int:
    """Queues one notification for every enabled webhook that wants its category."""
    from . import personal as P
    from .notify import payload
    n = P.one(conn, "SELECT category FROM personal.notifications WHERE id = :n", n=nid)
    body = json.dumps(payload(conn, nid), default=str)
    return conn.execute(text("""
        INSERT INTO core.webhook_deliveries (webhook_id, notification_id, payload)
        SELECT id, :n, CAST(:p AS jsonb) FROM core.webhooks WHERE enabled AND (kinds = '{}' OR :c = ANY (kinds))"""),
        {"n": nid, "p": body, "c": n["category"]}).rowcount


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(url: str, secret: str, body: dict, event: str, delivery: str) -> tuple[int | None, str]:
    raw = json.dumps(body, default=str, separators=(",", ":")).encode()
    req = urllib.request.Request(url, data=raw, method="POST", headers={
        "Content-Type": "application/json", "User-Agent": "EA-Explorer-Webhook/1", "X-EAX-Event": event,
        "X-EAX-Delivery": delivery, "X-EAX-Signature": sign(secret, raw)})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - an address an admin set
            return r.status, ""
    except urllib.error.HTTPError as exc:
        return exc.code, f"answered HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return None, f"{exc.__class__.__name__}: {exc}"[:300]


def deliver_due(conn, limit: int = 200, notification_id: int | None = None) -> dict:
    """Sends the deliveries that are due (or, with notification_id, that notification's now); each in the caller's
    transaction (commit after)."""
    sent = failed = retried = 0
    for d in _rows(conn, """
            SELECT d.id, d.payload, d.attempts, w.url, w.secret, w.enabled FROM core.webhook_deliveries d
              JOIN core.webhooks w ON w.id = d.webhook_id
             WHERE d.status = 'pending' AND (CAST(:n AS bigint) IS NULL AND d.next_at <= now() OR d.notification_id = :n)
             ORDER BY d.id LIMIT :l FOR UPDATE OF d SKIP LOCKED""", l=limit, n=notification_id):
        body = d["payload"] if isinstance(d["payload"], dict) else json.loads(d["payload"])
        status, error = _post(d["url"], d["secret"], body, body.get("kind", ""), str(d["id"]))
        attempts = d["attempts"] + 1
        if status is not None and 200 <= status < 300:
            conn.execute(text("""UPDATE core.webhook_deliveries SET status = 'sent', attempts = :a, last_status = :s,
                                 last_error = '', sent_at = now() WHERE id = :i"""), {"a": attempts, "s": status, "i": d["id"]})
            sent += 1
        elif attempts >= MAX_ATTEMPTS:
            conn.execute(text("""UPDATE core.webhook_deliveries SET status = 'failed', attempts = :a, last_status = :s,
                                 last_error = :e WHERE id = :i"""), {"a": attempts, "s": status, "e": error, "i": d["id"]})
            failed += 1
        else:
            conn.execute(text("""UPDATE core.webhook_deliveries SET attempts = :a, last_status = :s, last_error = :e,
                                 next_at = now() + make_interval(mins => :w) WHERE id = :i"""),
                         {"a": attempts, "s": status, "e": error, "w": 2 ** (attempts - 1), "i": d["id"]})
            retried += 1
    return {"sent": sent, "failed": failed, "retried": retried}


# ---------------------------------------------------------------- managing them (IT and Super Admins)

def _check(body: dict, partial: bool = False) -> dict:
    out = {}
    if not partial or "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            raise HookError("Give the webhook a name.")
        out["name"] = name[:120]
    if not partial or "url" in body:
        url = (body.get("url") or "").strip()
        if not url.lower().startswith(("https://", "http://")):
            raise HookError("The address starts with https:// (or http:// inside your network).")
        out["url"] = url[:2000]
    if not partial or "kinds" in body:
        kinds = [k for k in (body.get("kinds") or []) if k]
        bad = [k for k in kinds if k not in CATEGORIES]
        if bad:
            raise HookError(f"Unknown kinds: {', '.join(bad)}. Known: {', '.join(CATEGORIES)}.")
        out["kinds"] = kinds
    if "enabled" in body:
        out["enabled"] = bool(body["enabled"])
    return out


def _out(r: dict) -> dict:
    return {"id": str(r["guid"]), "name": r["name"], "url": r["url"], "secret": r["secret"], "kinds": list(r["kinds"] or []),
            "enabled": r["enabled"], "created_by": r["created_by"], "created_at": r["created_at"],
            "sent": r.get("sent", 0), "failed": r.get("failed", 0), "pending": r.get("pending", 0),
            "last_sent_at": r.get("last_sent_at")}


def listing(conn) -> list[dict]:
    return [_out(r) for r in _rows(conn, """
        SELECT w.*, (SELECT count(*) FROM core.webhook_deliveries d WHERE d.webhook_id = w.id AND d.status = 'sent') AS sent,
               (SELECT count(*) FROM core.webhook_deliveries d WHERE d.webhook_id = w.id AND d.status = 'failed') AS failed,
               (SELECT count(*) FROM core.webhook_deliveries d WHERE d.webhook_id = w.id AND d.status = 'pending') AS pending,
               (SELECT max(sent_at) FROM core.webhook_deliveries d WHERE d.webhook_id = w.id) AS last_sent_at
          FROM core.webhooks w ORDER BY w.name""")]


def _hook(conn, guid) -> dict:
    r = _one(conn, "SELECT * FROM core.webhooks WHERE guid = CAST(:g AS uuid)", g=str(guid))
    if not r:
        raise HookError("No such webhook.", 404)
    return r


def create(conn, body: dict, by: str) -> dict:
    v = _check(body)
    r = _one(conn, """INSERT INTO core.webhooks (name, url, secret, kinds, enabled, created_by)
                      VALUES (:n, :u, :s, CAST(:k AS text[]), :e, :b) RETURNING *""",
             n=v["name"], u=v["url"], s=secrets.token_hex(24), k=v["kinds"], e=v.get("enabled", True), b=by)
    return _out(r)


def update(conn, guid, body: dict) -> dict:
    h = _hook(conn, guid)
    v = _check(body, partial=True)
    if body.get("new_secret"):
        v["secret"] = secrets.token_hex(24)
    if v:
        sets = ", ".join(f"{k} = CAST(:{k} AS text[])" if k == "kinds" else f"{k} = :{k}" for k in v)
        conn.execute(text(f"UPDATE core.webhooks SET {sets}, modified_at = now() WHERE id = :i"), {**v, "i": h["id"]})
    return _out(_hook(conn, guid))


def delete(conn, guid) -> dict:
    h = _hook(conn, guid)
    conn.execute(text("DELETE FROM core.webhooks WHERE id = :i"), {"i": h["id"]})
    return {"deleted": h["name"]}


def deliveries(conn, guid, limit: int = 100) -> list[dict]:
    h = _hook(conn, guid)
    return _rows(conn, """SELECT d.id, d.status, d.attempts, d.last_status, d.last_error, d.created_at, d.sent_at, d.next_at,
                                 d.payload->>'kind' AS kind, d.payload->>'title' AS title
                            FROM core.webhook_deliveries d WHERE d.webhook_id = :w ORDER BY d.id DESC LIMIT :l""",
                 w=h["id"], l=limit)


def test(conn, guid, by: str) -> dict:
    """Sends one test message now (not queued) and says what the receiver answered."""
    h = _hook(conn, guid)
    body = {"id": "test", "kind": "webhook.test", "category": "test", "needs_action": False,
            "title": f"Test message from EA Explorer, sent by {by}", "body": "", "link": "", "actor": by, "model": None,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    status, error = _post(h["url"], h["secret"], body, "webhook.test", "test")
    ok = status is not None and 200 <= status < 300
    return {"ok": ok, "status": status, "message": f"The receiver answered HTTP {status}." if ok else
            f"Not delivered: {error or f'HTTP {status}'}."}
