"""Calendars (owner, 8 Nov 2026, phase 13.0.9, D324): a project's calendar, kept by the project's members, and the
organisation's, kept by Super Admins. An event is a date, a time and a topic (and notes), once or repeated: daily,
weekly on chosen weekdays, monthly or yearly, until a date or a number of times; one occurrence can be skipped. All a
project's members are taken as invited to its events, everyone to the organisation's. Changed or deleted by whoever
made it, a Project Admin or Lead Architect (a project's) or a Super Admin (the organisation's).

Each person subscribes from any calendar application through a private https link per calendar (iCalendar), renewed to
stop the old one; the link shows only what that person may see.
"""
from __future__ import annotations

import calendar as pycal
import secrets
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one
REPEATS = ("none", "daily", "weekly", "monthly", "yearly")
MAX_SPAN_DAYS = 400
MAX_OCCURRENCES = 2000


# ---------------------------------------------------------------- which calendar, and rights
def _cal(conn, scope: str):
    """'org' or a project's guid -> (project row or None)."""
    if scope == "org":
        return None
    return pj.project_row(conn, scope)


def _may_read(conn, p, user) -> None:
    if p is not None:
        pj._need(conn, p, user, "read")


def _may_add(conn, p, user) -> None:
    if p is None:
        if not pj._super(user):
            raise EditError("The organisation's calendar is kept by Super Admins.", 403)
    else:
        pj._need(conn, p, user, "contribute")


def _may_change(conn, p, user, ev: dict) -> None:
    if ev["created_by"].lower() == user.username.lower() or pj._super(user):
        return
    if p is not None:
        roles = pj._need(conn, p, user, "read")
        if roles & (pj.ADMINS | {"super-admin"}):
            return
        raise EditError("Only whoever made it, the Project Admin or the Lead Architect change it.", 403)
    raise EditError("The organisation's calendar is kept by Super Admins.", 403)


# ---------------------------------------------------------------- occurrences
def _d(v: Any) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as e:
        raise EditError(f"{v} is not a date (YYYY-MM-DD).") from e


def _add_months(d: date, n: int) -> date | None:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    if d.day > pycal.monthrange(y, m)[1]:
        return None                      # the 31st in a month without one: that month has no occurrence
    return date(y, m, d.day)


def occurrences(ev: dict, frm: date, to: date) -> list[date]:
    """The dates the event happens on between frm and to (both included), skipped dates left out."""
    start, rep = ev["starts_on"], ev["repeat"]
    until = ev.get("until_on")
    limit = ev.get("times")
    skipped = set(ev.get("skipped") or [])
    out: list[date] = []
    n = 0

    def take(d: date) -> bool:
        nonlocal n
        if until and d > until:
            return False
        n += 1
        if limit and n > limit:
            return False
        if frm <= d <= to and d not in skipped:
            out.append(d)
        return d <= to and len(out) < MAX_OCCURRENCES
    if rep == "none":
        take(start)
        return out
    if rep == "daily":
        d = start
        while take(d):
            d += timedelta(days=1)
    elif rep == "weekly":
        days = sorted(set(ev.get("weekdays") or [start.weekday()]))
        week = start - timedelta(days=start.weekday())
        go = True
        while go:
            for wd in days:
                d = week + timedelta(days=wd)
                if d < start:
                    continue
                if not take(d):
                    go = False
                    break
            week += timedelta(days=7)
    elif rep in ("monthly", "yearly"):
        step = 1 if rep == "monthly" else 12
        k = 0
        while True:
            d = _add_months(start, k * step)
            k += 1
            if d is None:
                if k > 2400:
                    break
                continue
            if not take(d):
                break
    return out


# ---------------------------------------------------------------- reading
def _t(v: Any) -> time | None:
    if v in (None, ""):
        return None
    return v if isinstance(v, time) else time.fromisoformat(str(v)[:8])


def _events(conn, p) -> list[dict]:
    rows = _rows(conn, f"""SELECT id AS _id, guid::text AS id, topic, starts_on, at_time, minutes, notes, repeat, weekdays, until_on, times,
                                  skipped, created_by, created_at, modified_by, modified_at
                             FROM proj.cal_events WHERE {'project_id IS NULL' if p is None else 'project_id = :p'}
                            ORDER BY starts_on, at_time NULLS FIRST""", p=p["id"] if p else None)
    for r in rows:          # dates and times as such, whatever the driver gives back
        r["starts_on"], r["until_on"], r["at_time"] = _d(r["starts_on"]), _d(r["until_on"]), _t(r["at_time"])
        r["skipped"] = [_d(x) for x in (r["skipped"] or [])]
        r["weekdays"] = [int(x) for x in (r["weekdays"] or [])]
    return rows


def _plain(ev: dict) -> dict:
    out = {k: v for k, v in ev.items() if not k.startswith("_")}
    for k in ("starts_on", "until_on"):
        out[k] = str(out[k]) if out.get(k) else None
    out["at_time"] = out["at_time"].strftime("%H:%M") if out.get("at_time") else None
    out["skipped"] = [str(x) for x in out.get("skipped") or []]
    out["weekdays"] = list(out.get("weekdays") or [])
    for k in ("created_at", "modified_at"):
        out[k] = out[k].isoformat() if hasattr(out.get(k), "isoformat") else out.get(k)
    return out


def listing(conn, scope: str, user, frm: Any = None, to: Any = None) -> dict:
    """The calendar's events and their occurrences between frm and to (a month around today by default)."""
    p = _cal(conn, scope)
    _may_read(conn, p, user)
    today = date.today()
    a = _d(frm) or today.replace(day=1) - timedelta(days=7)
    b = _d(to) or a + timedelta(days=45)
    if b < a or (b - a).days > MAX_SPAN_DAYS:
        raise EditError(f"Ask for {MAX_SPAN_DAYS} days at most.")
    evs = _events(conn, p)
    occ = []
    for ev in evs:
        for d in occurrences(ev, a, b):
            occ.append({"event": ev["id"], "date": str(d), "at_time": ev["at_time"].strftime("%H:%M") if ev["at_time"] else None,
                        "minutes": ev["minutes"], "topic": ev["topic"], "repeat": ev["repeat"]})
    occ.sort(key=lambda o: (o["date"], o["at_time"] or ""))
    may_add = True
    try:
        _may_add(conn, p, user)
    except EditError:
        may_add = False
    return {"calendar": scope, "name": p["name"] if p else "The organisation", "from": str(a), "to": str(b),
            "events": [_plain(e) for e in evs], "occurrences": occ, "may_add": may_add and not (p and p.get("frozen")),
            "invited": "every member of the project" if p else "everyone in the organisation"}


# ---------------------------------------------------------------- writing
def _vals(d: dict) -> dict:
    topic = " ".join((d.get("topic") or "").split())[:300]
    if not topic:
        raise EditError("Give the event a topic.")
    start = _d(d.get("starts_on"))
    if not start:
        raise EditError("Give the event a date.")
    at = (d.get("at_time") or "").strip()
    if at:
        try:
            at_t = time.fromisoformat(at[:5])
        except ValueError as e:
            raise EditError("The time is HH:MM.") from e
    else:
        at_t = None
    rep = d.get("repeat") or "none"
    if rep not in REPEATS:
        raise EditError("Repeat: none, daily, weekly, monthly or yearly.")
    wd = sorted({int(x) for x in (d.get("weekdays") or []) if str(x).isdigit() and 0 <= int(x) <= 6})
    until = _d(d.get("until_on"))
    times = int(d["times"]) if str(d.get("times") or "").isdigit() and int(d["times"]) > 0 else None
    if until and until < start:
        raise EditError("It cannot end before it starts.")
    minutes = int(d.get("minutes") or 60)
    if not 0 < minutes <= 24 * 60:
        raise EditError("An event lasts between a minute and a day.")
    return {"topic": topic, "starts_on": start, "at_time": at_t, "minutes": minutes, "notes": (d.get("notes") or "").strip()[:4000],
            "repeat": rep, "weekdays": wd if rep == "weekly" else [], "until_on": until if rep != "none" else None,
            "times": times if rep != "none" else None}


def add(conn, scope: str, user, d: dict) -> dict:
    p = _cal(conn, scope)
    _may_add(conn, p, user)
    v = _vals(d)
    g = conn.execute(text("""INSERT INTO proj.cal_events (project_id, topic, starts_on, at_time, minutes, notes, repeat, weekdays, until_on, times,
                                                          created_by)
                             VALUES (:p, :topic, :starts_on, :at_time, :minutes, :notes, :repeat, CAST(:weekdays AS integer[]), :until_on, :times, :u)
                             RETURNING guid::text"""), {**v, "p": p["id"] if p else None, "u": user.username}).scalar()
    return {"id": g, "message": f"{v['topic']} on {v['starts_on']}{' (repeats ' + v['repeat'] + ')' if v['repeat'] != 'none' else ''} added."}


def _ev(conn, p, eid: str) -> dict:
    ev = _one(conn, f"""SELECT * FROM proj.cal_events WHERE guid = CAST(:g AS uuid)
                         AND {'project_id IS NULL' if p is None else 'project_id = :p'}""", g=eid, p=p["id"] if p else None)
    if not ev:
        raise EditError("No such event in this calendar.", 404)
    return ev


def update(conn, scope: str, user, eid: str, d: dict) -> dict:
    p = _cal(conn, scope)
    ev = _ev(conn, p, eid)
    _may_change(conn, p, user, ev)
    if d.get("skip"):                                   # one occurrence left out
        day = _d(d["skip"])
        conn.execute(text("UPDATE proj.cal_events SET skipped = array_append(skipped, :d), modified_by = :u, modified_at = now() WHERE id = :i"),
                     {"d": day, "u": user.username, "i": ev["id"]})
        return {"message": f"{ev['topic']} on {day} skipped."}
    base = {k: ev[k] for k in ("topic", "starts_on", "at_time", "minutes", "notes", "repeat", "weekdays", "until_on", "times")}
    base["at_time"] = _t(ev["at_time"]).strftime("%H:%M") if ev["at_time"] else ""
    v = _vals({**base, **d})
    conn.execute(text("""UPDATE proj.cal_events SET topic = :topic, starts_on = :starts_on, at_time = :at_time, minutes = :minutes, notes = :notes,
                                repeat = :repeat, weekdays = CAST(:weekdays AS integer[]), until_on = :until_on, times = :times,
                                modified_by = :u, modified_at = now() WHERE id = :i"""), {**v, "u": user.username, "i": ev["id"]})
    return {"message": f"{v['topic']} saved."}


def delete(conn, scope: str, user, eid: str) -> dict:
    p = _cal(conn, scope)
    ev = _ev(conn, p, eid)
    _may_change(conn, p, user, ev)
    conn.execute(text("DELETE FROM proj.cal_events WHERE id = :i"), {"i": ev["id"]})
    return {"message": f"{ev['topic']} deleted."}


# ---------------------------------------------------------------- iCalendar: download and subscribe
def _esc(s: str) -> str:
    return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, b = [], line.encode("utf-8")
    while len(b) > 74:
        cut = 74
        while cut > 0 and (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b" " + b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)


def ics(conn, scope: str, name: str, events: list[dict]) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    days = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EA Explorer//Calendar//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_esc(name)}"]
    for e in events:
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@ea-explorer", f"DTSTAMP:{stamp}", f"SUMMARY:{_esc(e['topic'])}"]
        if e["at_time"]:
            st = datetime.combine(e["starts_on"], e["at_time"])
            en = st + timedelta(minutes=e["minutes"] or 60)
            lines += [f"DTSTART:{st.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{en.strftime('%Y%m%dT%H%M%S')}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{e['starts_on'].strftime('%Y%m%d')}",
                      f"DTEND;VALUE=DATE:{(e['starts_on'] + timedelta(days=1)).strftime('%Y%m%d')}"]
        if e["notes"]:
            lines.append(f"DESCRIPTION:{_esc(e['notes'])}")
        if e["repeat"] != "none":
            rule = f"RRULE:FREQ={e['repeat'].upper()}"
            if e["repeat"] == "weekly" and e["weekdays"]:
                rule += ";BYDAY=" + ",".join(days[d] for d in e["weekdays"])
            if e["until_on"]:
                rule += f";UNTIL={e['until_on'].strftime('%Y%m%d')}T235959"
            elif e["times"]:
                rule += f";COUNT={e['times']}"
            lines.append(rule)
            for s in e["skipped"] or []:
                lines.append(f"EXDATE;VALUE=DATE:{s.strftime('%Y%m%d')}" if not e["at_time"]
                             else f"EXDATE:{datetime.combine(s, e['at_time']).strftime('%Y%m%dT%H%M%S')}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def download(conn, scope: str, user) -> tuple[str, str]:
    p = _cal(conn, scope)
    _may_read(conn, p, user)
    name = f"{p['name'] if p else 'Organisation'} calendar"
    return ics(conn, scope, name, _events(conn, p)), f"{name}.ics"


def feed_link(conn, scope: str, user, renew: bool = False) -> dict:
    """The person's private subscription link for the calendar (made once; renew to stop the old one)."""
    p = _cal(conn, scope)
    _may_read(conn, p, user)
    key = "org" if p is None else str(p["guid"])
    me = user.username.lower()
    row = _one(conn, "SELECT token FROM proj.cal_feeds WHERE username = :u AND calendar = :c", u=me, c=key)
    if renew or not row:
        tok = secrets.token_urlsafe(32)
        from .org_repository import may_see_all_users
        conn.execute(text("""INSERT INTO proj.cal_feeds (username, calendar, token, every) VALUES (:u, :c, :t, :e)
                             ON CONFLICT (username, calendar) DO UPDATE SET token = EXCLUDED.token, every = EXCLUDED.every, created_at = now()"""),
                     {"u": me, "c": key, "t": tok, "e": may_see_all_users(user)})
    else:
        tok = row["token"]
    return {"path": f"/api/v1/calendar-feed/{tok}.ics", "message": "A new link: the old one no longer works." if renew else ""}


def feed(conn, token: str) -> tuple[str, str]:
    """The calendar behind a private link, as the person it belongs to may see it (no sign-in: the token is the key)."""
    row = _one(conn, "SELECT username, calendar, every FROM proj.cal_feeds WHERE token = :t", t=token)
    if not row:
        raise EditError("No such calendar link (it may have been renewed).", 404)
    p = _cal(conn, row["calendar"])
    if p is not None and not row["every"]:
        member = _one(conn, "SELECT 1 AS x FROM proj.members WHERE project_id = :p AND lower(username) = :u", p=p["id"], u=row["username"])
        if not member:
            raise EditError("This calendar is no longer shared with you.", 403)
    name = f"{p['name'] if p else 'Organisation'} calendar"
    return ics(conn, row["calendar"], name, _events(conn, p)), name
