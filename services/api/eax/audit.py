"""Writes to the append-only audit log (audit.events). The change log (phase 9) ships the actions people take from
here to its own database in the background (eax/change_log.py)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


def record(
    conn: Connection,
    *,
    actor: str,
    action: str,
    object_type: str | None = None,
    object_id: str | None = None,
    details: dict[str, Any] | None = None,
    source: str = "api",
    request_id: str | None = None,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO audit.events (actor, action, object_type, object_id, details, source, request_id)
            VALUES (:actor, :action, :object_type, :object_id, CAST(:details AS jsonb), :source, :request_id)
            """
        ),
        {
            "actor": actor,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "details": json.dumps(details or {}),
            "source": source,
            "request_id": request_id,
        },
    )
    # notifications (phase 8.1): the audited actions people must know about notify everyone on the model; a failure there
    # never undoes the action itself (a savepoint keeps the two apart)
    from . import notify
    if action in notify.FROM_AUDIT:
        import logging
        try:
            nested = getattr(conn, "begin_nested", None)
            if nested is None:   # a plain driver connection (tests): no savepoint
                notify.on_audit(conn, actor=actor, action=action, object_type=object_type, object_id=object_id,
                                details=details)
            else:
                with nested():
                    notify.on_audit(conn, actor=actor, action=action, object_type=object_type, object_id=object_id,
                                    details=details)
        except Exception:  # noqa: BLE001
            logging.getLogger("eax.notify").exception("notification for %s failed", action)
