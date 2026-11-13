"""Scheduled eax commands (owner, 10 Nov 2026, D559): a cron in the platform, e.g. a demo that resets every night.

Kept in persist/schedules.json (eaxcli/persist.py: it survives cleanup, clean-run and clean-restart). The operations
helper looks every 30 seconds (tick) and starts what is due through the Command centre's runner (a container of its
own, so a command that stops the stack still finishes); `eax schedule` changes the same file. A schedule's command is
checked like any command from the page (eaxcli/commands.py); the commands that delete everything need a Super Admin
and the strong confirm once, when the schedule is made. Times are in the installation's time zone (EAX_TIMEZONE).

A schedule: {id, name, argv, cron | once_at, enabled, created_by, created_at, wipe, backup_first, keep, banner,
last: {run, at, state, note}, checked}.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import commands as C
from . import persist

GRACE = timedelta(hours=1)          # a run missed while the machine was off: still run if found within the hour
BUSY_WAIT = timedelta(minutes=30)   # due while another command runs: wait up to this, then skip with a note
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
COMMENT = ("Scheduled eax commands (D559). Survives resets. Edit with care: cron is 'minute hour day month weekday' "
           "in the installation's time zone; argv is the eax command and its options.")


class ScheduleError(ValueError):
    """A schedule that cannot be made (the reason is the message)."""


# ---------------------------------------------------------------- cron
def _field(text: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in text.split(","):
        m = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", part.strip())
        if not m:
            raise ScheduleError(f"'{part}' is not a cron field (use numbers, *, ranges like 1-5, lists and /steps).")
        base, step = m.group(1), int(m.group(2) or 1)
        a, b = (lo, hi) if base == "*" else (tuple(int(x) for x in base.split("-")) if "-" in base else (int(base), int(base)))
        if step < 1 or a < lo or b > hi or a > b:
            raise ScheduleError(f"'{part}' is outside {lo}-{hi}.")
        out.update(range(a, b + 1, step))
    return out


def parse(cron: str) -> tuple[set[int], ...]:
    parts = (cron or "").split()
    if len(parts) != 5:
        raise ScheduleError("A cron expression has five parts: minute hour day-of-month month day-of-week.")
    dow = {0 if d == 7 else d for d in _field(parts[4], 0, 7)}      # 0 and 7 are both Sunday
    return _field(parts[0], 0, 59), _field(parts[1], 0, 23), _field(parts[2], 1, 31), _field(parts[3], 1, 12), dow


def next_after(cron: str, after: datetime) -> datetime:
    """The first time after `after` (aware, in the installation's zone) that the cron matches."""
    mins, hours, doms, months, dows = parse(cron)
    any_dom, any_dow = parts_star(cron)
    t = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        if t.month not in months:
            t = (t.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
            continue
        dow = (t.weekday() + 1) % 7
        day_ok = (t.day in doms and dow in dows) if (any_dom or any_dow) else (t.day in doms or dow in dows)
        if not day_ok:
            t = (t + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if t.hour not in hours:
            t = (t + timedelta(hours=1)).replace(minute=0)
            continue
        if t.minute not in mins:
            t += timedelta(minutes=1)
            continue
        return t
    raise ScheduleError("This cron expression never matches.")


def parts_star(cron: str) -> tuple[bool, bool]:
    p = cron.split()
    return p[2] == "*", p[4] == "*"


def describe(s: dict) -> str:
    """A schedule in words: 'every day at 02:00', 'every Monday at 07:30', 'every hour at :15', 'once at ...'."""
    if s.get("once_at"):
        return f"once at {s['once_at'].replace('T', ' ')[:16]}"
    cron = s.get("cron") or ""
    try:
        parse(cron)
    except ScheduleError:
        return cron
    m, h, dom, mon, dow = cron.split()
    if m.isdigit() and h.isdigit() and dom == "*" and mon == "*":
        at = f"{int(h):02d}:{int(m):02d}"
        if dow == "*":
            return f"every day at {at}"
        if dow.isdigit():
            return f"every {DAYS[int(dow) % 7]} at {at}"
        if dow == "1-5":
            return f"every weekday at {at}"
    if m.isdigit() and h == "*" and dom == mon == dow == "*":
        return f"every hour at :{int(m):02d}"
    return f"cron {cron}"


def preset(kind: str, time_: str = "02:00", day: int = 1, minute: int = 0, at: str = "") -> dict:
    """The page's choices: nightly at HH:MM, weekly on a day at HH:MM, hourly at :MM, once at a date and time."""
    def hm(x: str) -> tuple[int, int]:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", x or "")
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ScheduleError("Give the time as HH:MM, e.g. 02:00.")
        return int(m.group(1)), int(m.group(2))
    if kind == "nightly":
        h, m = hm(time_)
        return {"cron": f"{m} {h} * * *"}
    if kind == "weekly":
        h, m = hm(time_)
        if not 0 <= int(day) <= 6:
            raise ScheduleError("The day is 0 (Sunday) to 6 (Saturday).")
        return {"cron": f"{m} {h} * * {int(day)}"}
    if kind == "hourly":
        if not 0 <= int(minute) <= 59:
            raise ScheduleError("The minute is 0 to 59.")
        return {"cron": f"{int(minute)} * * * *"}
    if kind == "once":
        try:
            datetime.fromisoformat(at)
        except ValueError as exc:
            raise ScheduleError("Give the date and time as YYYY-MM-DDTHH:MM.") from exc
        return {"once_at": at[:16]}
    raise ScheduleError("Choose nightly, weekly, hourly or once, or give a cron expression.")


# ---------------------------------------------------------------- the time zone and the file
def zone(root: Path | str | None = None):
    import os
    name = (os.environ.get("EAX_TIMEZONE") or persist._config_value(Path(root) if root else persist.ROOT, "EAX_TIMEZONE")
            or "UTC")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - an unknown zone: UTC
        return UTC


def path(root: Path | str | None = None) -> Path:
    return persist.folder(root) / "schedules.json"


def load(root: Path | str | None = None) -> tuple[list[dict], str]:
    data, warn = persist.read_json(path(root), {"version": persist.VERSION, "schedules": []})
    items = [s for s in data.get("schedules") or [] if isinstance(s, dict) and s.get("id")]
    return items, warn


def save(items: list[dict], root: Path | str | None = None) -> None:
    persist.write_json(path(root), {"version": persist.VERSION, "_comment": COMMENT, "schedules": items})


def _when(s: dict, tz) -> datetime | None:
    v = s.get("checked") or s.get("created_at")
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d.astimezone(tz) if d.tzinfo else d.replace(tzinfo=tz)
    except ValueError:
        return None


def next_run(s: dict, tz, now: datetime | None = None) -> datetime | None:
    if not s.get("enabled"):
        return None
    now = now or datetime.now(tz)
    if s.get("once_at"):
        at = datetime.fromisoformat(s["once_at"]).replace(tzinfo=tz)
        return at if not (s.get("last") or {}).get("run") else None
    try:
        return next_after(s["cron"], max(now, _when(s, tz) or now) - timedelta(minutes=1))
    except (KeyError, ScheduleError):
        return None


def listing(root: Path | str | None = None, now: datetime | None = None) -> dict:
    tz = zone(root)
    items, warn = load(root)
    out = []
    for s in items:
        n = next_run(s, tz, now)
        out.append({**s, "when": describe(s), "next": n.isoformat(timespec="minutes") if n else None,
                    "command": " ".join(["eax", *s.get("argv", [])])})
    return {"schedules": out, "warning": warn, "time_zone": str(tz), "file": str(path(root))}


# ---------------------------------------------------------------- changes
def make(body: dict, by: str, roles: list[str], installation: str, root: Path | str | None = None) -> dict:
    """A new schedule from {name, argv | (command name, values), cron | preset, enabled, backup_first, keep, banner,
    confirm: {typed, understood}}; checked like a command from the page, the wipe commands with the strong confirm."""
    argv = body.get("argv")
    if not argv and body.get("command"):
        argv = C.build_argv(str(body["command"]), dict(body.get("values") or {}))
    if not isinstance(argv, list) or not argv:
        raise ScheduleError("Choose the command to run.")
    argv = C.check_argv([str(a) for a in argv])
    kind = C.kind_of_argv(argv)
    if kind in ("host", "interactive"):
        raise ScheduleError(f"eax {argv[0]} cannot run on a schedule: it needs the machine itself or asks as it goes.")
    if argv[0] in C.FOLLOWS:
        raise ScheduleError(f"eax {argv[0]} keeps going until stopped, so it cannot run on a schedule.")
    C.allowed_argv(argv, roles)
    if kind == "wipe":
        conf = body.get("confirm") or {}
        C.check_confirm(argv, str(conf.get("typed") or ""), installation, bool(conf.get("understood")))
    when = {"cron": str(body["cron"]).strip()} if body.get("cron") else preset(**(body.get("preset") or {}))
    if when.get("cron"):
        parse(when["cron"])
    name = re.sub(r"\s+", " ", str(body.get("name") or "").strip())[:80] or " ".join(["eax", *argv])
    tz = zone(root)
    now = datetime.now(tz).isoformat(timespec="seconds")
    s = {"id": secrets.token_hex(3), "name": name, "argv": argv, **when, "enabled": bool(body.get("enabled", True)),
         "created_by": by, "created_at": now, "checked": now, "wipe": kind == "wipe",
         "backup_first": bool(body.get("backup_first", True)) if kind == "wipe" else False,
         "keep": max(1, min(int(body.get("keep") or 3), 20)), "banner": bool(body.get("banner")) and kind == "wipe",
         "confirmed": {"by": by, "at": now, "installation": installation} if kind == "wipe" else None, "last": {}}
    items, _ = load(root)
    if any(x.get("name") == name for x in items):
        raise ScheduleError(f"There is already a schedule called {name}.")
    items.append(s)
    save(items, root)
    return {**s, "when": describe(s)}


def demo_reset(by: str, roles: list[str], installation: str, typed: str, understood: bool, at: str = "02:00",
               root: Path | str | None = None) -> dict:
    """The owner's one-click template: clean-restart laptop every night at 02:00, no backup first, the banner on.
    When the demo reset is there already but off, it is turned on (at the time given) after the same checks."""
    items, _ = load(root)
    old = next((x for x in items if x.get("name") == "Demo reset every night"), None)
    if old:
        if old.get("enabled"):
            raise ScheduleError("The demo reset is on already.")
        C.allowed("clean-restart", roles)
        C.check_confirm(["clean-restart", "laptop"], typed, installation, understood)
        old.update(preset("nightly", at), enabled=True, banner=True, argv=["clean-restart", "laptop"], wipe=True,
                   checked=datetime.now(zone(root)).isoformat(timespec="seconds"),
                   confirmed={"by": by, "at": datetime.now(zone(root)).isoformat(timespec="seconds"), "installation": installation})
        old.pop("once_at", None)
        save(items, root)
        return {**old, "when": describe(old)}
    return make({"name": "Demo reset every night", "argv": ["clean-restart", "laptop"], "preset": {"kind": "nightly", "time_": at},
                 "backup_first": False, "banner": True, "confirm": {"typed": typed, "understood": understood}},
                by, roles, installation, root)


def change(sid: str, what: str, by: str, roles: list[str], root: Path | str | None = None) -> dict:
    items, _ = load(root)
    s = next((x for x in items if x.get("id") == sid), None)
    if not s:
        raise FileNotFoundError("No such schedule.")
    if s.get("wipe"):
        C.allowed("clean-restart", roles)        # a schedule that deletes everything: Super Admins only
    if what == "remove":
        items.remove(s)
    elif what in ("on", "off"):
        s["enabled"] = what == "on"
        if s["enabled"]:
            s["checked"] = datetime.now(zone(root)).isoformat(timespec="seconds")   # no catching up on what passed
    else:
        raise ScheduleError("Choose on, off or remove.")
    s.setdefault("history", []).append({"at": datetime.now(zone(root)).isoformat(timespec="seconds"), "by": by, "what": what})
    s["history"] = s["history"][-20:]
    save(items, root)
    return s


def find(sid: str, root: Path | str | None = None) -> dict:
    items, _ = load(root)
    for s in items:
        if s.get("id") == sid or s.get("name") == sid:
            return s
    raise FileNotFoundError("No such schedule.")


def record(sid: str, last: dict, root: Path | str | None = None, checked: datetime | None = None,
           disable: bool = False) -> None:
    items, _ = load(root)
    for s in items:
        if s.get("id") == sid:
            s["last"] = last
            if checked:
                s["checked"] = checked.isoformat(timespec="seconds")
            if disable:
                s["enabled"] = False
    save(items, root)


# ---------------------------------------------------------------- what is due
def tick(start, busy, root: Path | str | None = None, now: datetime | None = None) -> list[dict]:
    """Start what is due. start(schedule) -> run id; busy() -> True while another command runs. Returns what happened.
    A run found more than an hour late (the machine was off) is skipped and recorded; a due run waits while another
    command runs and is skipped with a note after 30 minutes."""
    tz = zone(root)
    now = now or datetime.now(tz)
    items, _ = load(root)
    done = []
    for s in items:
        if not s.get("enabled"):
            continue
        since = _when(s, tz) or now
        due = None
        if s.get("once_at"):
            at = datetime.fromisoformat(s["once_at"]).replace(tzinfo=tz)
            if at <= now and not (s.get("last") or {}).get("run"):
                due = at
        else:
            try:
                t = next_after(s["cron"], since)
                for _ in range(5000):
                    if t > now:
                        break
                    due = t
                    t = next_after(s["cron"], t)
            except (KeyError, ScheduleError):
                continue
        if not due:
            continue
        stamp = now.isoformat(timespec="seconds")
        if now - due > GRACE and not (s.get("waiting_since")):
            record(s["id"], {"at": stamp, "state": "skipped", "note": f"missed at {due.isoformat(timespec='minutes')} "
                             "(EA Explorer was not running); runs again at the next time"}, root, checked=now,
                   disable=bool(s.get("once_at")))
            done.append({"id": s["id"], "what": "skipped-missed"})
            continue
        if busy():
            waiting = datetime.fromisoformat(s.get("waiting_since") or stamp)
            if now - waiting > BUSY_WAIT:
                record(s["id"], {"at": stamp, "state": "skipped", "note": "another command was still running after 30 minutes"},
                       root, checked=now, disable=bool(s.get("once_at")))
                _set(s["id"], "waiting_since", None, root)
                done.append({"id": s["id"], "what": "skipped-busy"})
            elif not s.get("waiting_since"):
                _set(s["id"], "waiting_since", stamp, root)
                done.append({"id": s["id"], "what": "waiting"})
            continue
        try:
            run_id = start(s)
            record(s["id"], {"run": run_id, "at": stamp, "state": "started", "due": due.isoformat(timespec="minutes")},
                   root, checked=now, disable=bool(s.get("once_at")))
            done.append({"id": s["id"], "what": "started", "run": run_id})
        except Exception as exc:  # noqa: BLE001 - recorded, never stops the helper
            record(s["id"], {"at": stamp, "state": "failed", "note": f"could not start: {exc}"}, root, checked=now,
                   disable=bool(s.get("once_at")))
            done.append({"id": s["id"], "what": "failed"})
        _set(s["id"], "waiting_since", None, root)
    return done


def _set(sid: str, key: str, value, root) -> None:
    items, _ = load(root)
    for s in items:
        if s.get("id") == sid:
            if value is None:
                s.pop(key, None)
            else:
                s[key] = value
    save(items, root)


def banner_text(s: dict) -> str:
    return f"This demo resets {describe(s)}: everything entered is deleted then."
