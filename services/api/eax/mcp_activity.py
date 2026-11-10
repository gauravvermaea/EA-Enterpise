"""The AI activity log (phases 26 and 27, D368, D482): every MCP call, per person.

Each call is kept with the tool, a summary of the question (the `why` the assistant passes, else the arguments
shortened), the size of the answer, what it changed, the model it was about and the machine credential used. The person
sees their own calls; Super Admins and IT Admins see everyone's (Administration, and the MCP page's AI activity tab).

Rules are here, never in the database (D248). Writing the log never stops a call: a failure is only logged.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from . import permissions as perms

log = logging.getLogger("eax.mcp")

KINDS = ("read", "preview", "change", "refused", "error")
ADMINS = {perms.SUPER_ADMIN, perms.IT_ADMIN}
MAX_TEXT = 300
MAX_ITEMS = 10


def shorten(value: Any, depth: int = 0) -> Any:
    """Arguments as kept: long texts cut, long lists cut, nested deeply only so far; secrets never come here."""
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + "…"
    if isinstance(value, dict):
        if depth > 2:
            return "{…}"
        return {str(k): shorten(v, depth + 1) for k, v in list(value.items())[:30] if str(k) not in ("confirm", "token", "secret")}
    if isinstance(value, (list, tuple)):
        if depth > 2:
            return f"[{len(value)} items]"
        items = [shorten(v, depth + 1) for v in list(value)[:MAX_ITEMS]]
        return items + ([f"… {len(value) - MAX_ITEMS} more"] if len(value) > MAX_ITEMS else [])
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:MAX_TEXT]


def summarise(tool: str, arguments: dict) -> str:
    """The question in a line: the assistant's own words (why) when given, else the tool and its main arguments."""
    why = str((arguments or {}).get("why") or "").strip()
    if why:
        return why[:MAX_TEXT]
    parts = []
    for k, v in (arguments or {}).items():
        if k in ("confirm", "why") or v in (None, "", [], {}):
            continue
        shown = v if isinstance(v, (str, int, float, bool)) else (f"{len(v)} items" if isinstance(v, (list, tuple)) else "{…}")
        parts.append(f"{k}={str(shown)[:60]}")
    return (tool.replace("_", " ") + (": " + ", ".join(parts[:5]) if parts else ""))[:MAX_TEXT]


def kind_of(result: Any, wrote: bool, previewed: bool) -> str:
    """read, preview, change, refused (no right) or error, from what came back."""
    err = ""
    if isinstance(result, dict) and result.get("error"):
        err = str(result["error"]).lower()
    if err:
        if any(w in err for w in ("needs the", "needs a ", "may only read", "not allowed", "sign in", "permission", "only a ", "right to")):
            return "refused"
        return "error"
    if previewed:
        return "preview"
    return "change" if wrote else "read"


def record(conn, *, username: str, tool: str, arguments: dict, result: Any, ms: int, wrote: bool = False,
           previewed: bool = False, changes: list | None = None, credential: str = "") -> None:
    """Keeps one call. `result` is the tool's answer (a dict, or text)."""
    try:
        size = len(result) if isinstance(result, str) else len(json.dumps(result, default=str))
    except (TypeError, ValueError):
        size = 0
    err = str(result.get("error"))[:500] if isinstance(result, dict) and result.get("error") else ""
    model = str((arguments or {}).get("model") or (arguments or {}).get("project") or "")[:200]
    conn.execute(text("""INSERT INTO core.mcp_activity (username, tool, kind, summary, arguments, result_size, changes, model,
                                                       credential, ms, error)
                         VALUES (:u, :t, :k, :s, CAST(:a AS jsonb), :r, CAST(:c AS jsonb), :m, :cred, :ms, :e)"""),
                 {"u": (username or "unknown").lower(), "t": tool, "k": kind_of(result, wrote, previewed),
                  "s": summarise(tool, arguments), "a": json.dumps(shorten(arguments or {}), default=str), "r": size,
                  "c": json.dumps((changes or [])[:50], default=str), "m": model, "cred": credential[:120], "ms": int(ms),
                  "e": err})


def is_admin(user) -> bool:
    return bool(ADMINS & set(getattr(user, "roles", ()) or ()))


def listing(conn, user, who: str = "", kind: str = "", tool: str = "", days: int = 30, limit: int = 300) -> dict:
    """Calls, newest first: the person's own, or (Super Admins and IT Admins) anyone's; with counts by kind and tool."""
    admin = is_admin(user)
    me = user.username.lower()
    who = (who or "").strip().lower()
    if who in ("", "me"):
        who = me if not admin else ""
    if who and who != me and not admin:
        raise PermissionError("Only Super Admins and IT Admins see other people's AI activity.")
    days = max(1, min(int(days or 30), 3650))
    limit = max(1, min(int(limit or 300), 2000))
    where = ["at > now() - make_interval(days => :d)"]
    p: dict[str, Any] = {"d": days, "l": limit}
    if who:
        where.append("username = :w")
        p["w"] = who
    if kind in KINDS:
        where.append("kind = :k")
        p["k"] = kind
    if tool:
        where.append("tool = :t")
        p["t"] = tool
    w = " AND ".join(where)
    def q(sql: str) -> list[dict]:
        return [dict(r) for r in conn.execute(text(sql), p).mappings()]
    rows = q(f"""SELECT id, at, username, tool, kind, summary, arguments, result_size, changes, model, credential, ms, error
                   FROM core.mcp_activity WHERE {w} ORDER BY at DESC, id DESC LIMIT :l""")
    by_kind = {r["kind"]: r["n"] for r in q(f"SELECT kind, count(*) AS n FROM core.mcp_activity WHERE {w} GROUP BY kind")}
    by_tool = [{"tool": r["tool"], "calls": r["n"]} for r in q(
        f"SELECT tool, count(*) AS n FROM core.mcp_activity WHERE {w} GROUP BY tool ORDER BY count(*) DESC, tool LIMIT 15")]
    people = [{"username": r["username"], "calls": r["n"]} for r in q(
        f"SELECT username, count(*) AS n FROM core.mcp_activity WHERE {w} GROUP BY username ORDER BY count(*) DESC LIMIT 50")] if admin else []
    for r in rows:
        for k in ("arguments", "changes"):
            if isinstance(r[k], str):
                r[k] = json.loads(r[k])
    return {"admin": admin, "who": who or ("everyone" if admin else me), "days": days, "calls": rows,
            "by_kind": {k: by_kind.get(k, 0) for k in KINDS}, "by_tool": by_tool, "people": people}
