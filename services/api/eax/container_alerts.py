"""Container alerts become notifications (R2.19, D641): the operations helper's watcher sends what it found; each
alert, reminder and recovery is one notification for the IT Admins and Super Admins (an alert needs action until someone
resolves it or the container works again) and goes to the webhooks (category system), so Teams, Slack or a monitoring
tool hear it too. No email. Every one is in the audit trail."""

from __future__ import annotations

from sqlalchemy import text

from . import audit, notify

LINK = "#/admin/containers"


def admins(conn) -> list[str]:
    return [r[0] for r in conn.execute(text("""SELECT lower(username) FROM core.known_users
                                                 WHERE 'super-admin' = ANY (roles) OR 'it-admin' = ANY (roles)"""))]


def title_of(e: dict) -> str:
    return str(e.get("text") or f"Container {e.get('service')}: {e.get('event')} ({e.get('kind')})")[:300]


def tell(conn, events: list[dict]) -> int:
    people, n = admins(conn), 0
    for e in events:
        ev = str(e.get("event") or "")
        if ev not in ("alert", "reminder", "recovered", "restarted"):
            continue
        notify.create(conn, kind=f"container.{ev}", category="system", title=title_of(e),
                      body=str(e.get("detail") or ""), link=LINK, actor="system", recipients=people,
                      needs_action=ev in ("alert", "reminder"))
        audit.record(conn, actor="system", action=f"container.{ev}", object_type="container",
                     object_id=str(e.get("service") or ""), details={k: e.get(k) for k in ("kind", "detail", "minutes")})
        n += 1
    return n
