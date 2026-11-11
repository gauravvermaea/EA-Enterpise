"""The banner under the top bar (owner, 10 Nov 2026, D558): one message an admin sets; nothing shows without it.

Kept in persist/banner.json (eaxcli/persist.py: it survives cleanup, clean-run and clean-restart), written by the
operations helper when an admin saves it on System admin > Banner (the API records who in the change log), and read by
the API for every signed-in person. A banner: {text, link, level (info | notice | urgent), starts, ends (ISO times in
the installation's zone, optional), audience (everyone | admins), dismissible, by, at, source (admin | schedule:<id>)}.
`history` keeps the last 20 banners set or cleared, for the page.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import persist
from . import schedules as S

LEVELS = ("info", "notice", "urgent")
AUDIENCES = ("everyone", "admins")
SAFE_LINK = re.compile(r"^(https?://|ftps?://|#/|ea:)", re.IGNORECASE)   # clickable only when safe (the Link rule, D418)
COMMENT = ("The banner under EA Explorer's top bar (D558). Survives resets. Remove 'banner' (or set it to null) and "
           "nothing is shown. level: info | notice | urgent; audience: everyone | admins; times in the installation's zone.")


def path(root: Path | str | None = None) -> Path:
    return persist.folder(root) / "banner.json"


def load(root: Path | str | None = None) -> tuple[dict, str]:
    return persist.read_json(path(root), {"version": persist.VERSION, "banner": None, "history": []})


def _clean(b: dict, by: str, source: str, root) -> dict:
    text = re.sub(r"\s+", " ", str(b.get("text") or "")).strip()
    if not text:
        raise ValueError("Write the banner's message.")
    if len(text) > 400:
        raise ValueError("Keep the banner's message to 400 characters.")
    level = str(b.get("level") or "info")
    audience = str(b.get("audience") or "everyone")
    if level not in LEVELS:
        raise ValueError("The level is information, notice or urgent.")
    if audience not in AUDIENCES:
        raise ValueError("Show it to everyone or to admins only.")
    out = {"text": text, "link": str(b.get("link") or "").strip()[:2000], "link_text": str(b.get("link_text") or "").strip()[:80],
           "level": level, "audience": audience, "dismissible": bool(b.get("dismissible", True)),
           "starts": str(b.get("starts") or "")[:16] or None, "ends": str(b.get("ends") or "")[:16] or None,
           "by": by, "at": datetime.now(S.zone(root)).isoformat(timespec="seconds"), "source": source}
    for k in ("starts", "ends"):
        if out[k]:
            try:
                datetime.fromisoformat(out[k])
            except ValueError as exc:
                raise ValueError("Give the times as YYYY-MM-DDTHH:MM.") from exc
    if out["starts"] and out["ends"] and out["ends"] <= out["starts"]:
        raise ValueError("The end is before the start.")
    return out


def set_banner(b: dict, by: str, source: str = "admin", root: Path | str | None = None) -> dict:
    data, _ = load(root)
    new = _clean(b, by, source, root)
    hist = [*(data.get("history") or []), {**new, "what": "set"}][-20:]
    persist.write_json(path(root), {"version": persist.VERSION, "_comment": COMMENT, "banner": new, "history": hist,
                                    **({"self_test_marker": data["self_test_marker"]} if data.get("self_test_marker") else {})})
    return new


def clear(by: str, root: Path | str | None = None, source: str | None = None) -> bool:
    """Clear the banner (only one from this source, when given: removing a schedule clears its own banner)."""
    data, _ = load(root)
    cur = data.get("banner")
    if not cur or (source and cur.get("source") != source):
        return False
    hist = [*(data.get("history") or []), {**cur, "what": "cleared", "cleared_by": by,
                                             "cleared_at": datetime.now(S.zone(root)).isoformat(timespec="seconds")}][-20:]
    persist.write_json(path(root), {**{k: v for k, v in data.items() if k not in ("banner", "history")},
                                    "version": persist.VERSION, "_comment": COMMENT, "banner": None, "history": hist})
    return True


def current(root: Path | str | None = None, admin: bool = False, now: datetime | None = None) -> dict | None:
    """What a person sees now: the banner if it is set, within its times and for them; else None (nothing shown)."""
    data, _ = load(root)
    b = data.get("banner")
    if not isinstance(b, dict) or not b.get("text"):
        return None
    tz = S.zone(root)
    now = now or datetime.now(tz)
    local = now.astimezone(tz).replace(tzinfo=None).isoformat(timespec="minutes")
    if (b.get("starts") and local < b["starts"]) or (b.get("ends") and local >= b["ends"]):
        return None
    if b.get("audience") == "admins" and not admin:
        return None
    return {**b, "link_safe": bool(b.get("link") and SAFE_LINK.match(b["link"])),
            "key": f"{b.get('at')}|{b.get('text')}"}   # a dismissal holds until the text or the time it was set changes
