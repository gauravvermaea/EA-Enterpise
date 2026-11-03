"""Writes to the append-only audit log (audit.events)."""

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
