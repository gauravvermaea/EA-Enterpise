"""Surveys (owner, 9 Nov 2026, phase 38.1, D375, D446 to D449): ask people questions and look at the answers.

- A survey has sections of questions. Question kinds: one choice, several choices, yes or no, a rating, a number, a
  date, short text and long text. A section or a question may be shown only when an earlier answer fits (a condition);
  a required question must be answered only when it is shown.
- Who it is for: people by name, everyone with a global role, everyone with a role (or one role) on a model, everyone
  on a project. They are worked out when the survey is sent and when more are added; nobody is ever taken off.
  "Open link": anyone signed in who has the link may answer too.
- Delivery through the task list and a link, never email: each person gets a notification that needs action (it is
  resolved when they answer or the survey closes) and the link #/surveys/<guid>/answer.
- Draft, open, closed (and reopened). The questions are changed only in a draft. A closing date closes it on its own;
  automatic reminders every N days go to those who have not answered; anyone running it can remind them by hand.
- Anonymous: an answer carries no name and nothing joins it to the person (only that they answered, so reminders go to
  the others); it is sent once and cannot be changed, and its draft stays in the person's browser; results show once
  three people have answered. Otherwise answers are saved as you go and may be changed until the survey closes.
- Results by question (counts and shares, mean, every text answer), progress, and an Excel download.
- Nothing in any model is changed by answers (D375). Kind 'maturity' is an EA capability maturity assessment
  (eax/maturity.py, phase 40): the same survey, scored.
- Who: Super Admins, Model Creators and Library Admins create surveys (permission surveys.create); the person who made
  one and Super Admins run it and see its results.
Every rule is here, in Python (D248); the tables are rows only (0037).
"""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import text

from . import notify
from . import permissions as perms
from .metamodel_edit import EditError

KINDS = {"single": "One choice", "multi": "Several choices", "yes_no": "Yes or no", "rating": "Rating",
         "number": "Number", "date": "Date", "text": "Short text", "long_text": "Long text", "links": "Links (evidence)"}
CHOICE_KINDS = ("single", "multi")
OPS = {"equals": "is", "not_equals": "is not", "includes": "includes", "answered": "is answered"}
RECIPIENT_KINDS = ("user", "role", "model", "project")
MAX_SECTIONS, MAX_QUESTIONS, MAX_OPTIONS = 40, 200, 50
MAX_TEXT, MAX_LONG = 500, 8000
ANONYMOUS_MIN = 3       # an anonymous survey's results show once this many have answered
LINK = "#/surveys/{g}/answer"


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings().all()]


def _one(conn, sql: str, **p) -> dict | None:
    r = conn.execute(text(sql), p).mappings().first()
    return dict(r) if r else None


def _user(user) -> tuple[str, set[str]]:
    return (getattr(user, "username", "") or "").lower(), set(getattr(user, "roles", ()) or ())


def may_create(user) -> bool:
    return perms.allowed(_user(user)[1], "surveys.create")


def _runs(s: dict, user) -> bool:
    """The person who made it, or a Super Admin."""
    name, roles = _user(user)
    return perms.SUPER_ADMIN in roles or s["owner"].lower() == name


# ---------------------------------------------------------------- the questions
def _key(v: Any, fallback: str) -> str:
    k = re.sub(r"[^a-z0-9_]", "_", str(v or "").strip().lower())[:40].strip("_")
    return k or fallback


def _str(v: Any, n: int) -> str:
    return " ".join(str(v if v is not None else "").split())[:n]


def _condition(c: Any, earlier: dict[str, dict], where: str) -> dict | None:
    """A condition on an earlier question: {question, op, value}."""
    if not c:
        return None
    if not isinstance(c, dict) or not c.get("question"):
        raise EditError(f"{where}: a condition names an earlier question.")
    q = earlier.get(str(c["question"]))
    if not q:
        raise EditError(f"{where}: the condition's question must come before it.")
    op = c.get("op") or "equals"
    if op not in OPS:
        raise EditError(f"{where}: a condition is one of {', '.join(OPS)}.")
    out = {"question": q["key"], "op": op}
    if op != "answered":
        out["value"] = _str(c.get("value"), MAX_TEXT)
    return out


def clean_spec(spec: Any) -> dict:
    """The survey's sections and questions, checked: unique keys, known kinds, options for choices, conditions only on
    earlier questions. Returns the clean document."""
    if isinstance(spec, str):
        try:
            spec = json.loads(spec or "{}")
        except ValueError as exc:
            raise EditError("The questions are not readable.") from exc
    sections = (spec or {}).get("sections") or []
    if not isinstance(sections, list) or len(sections) > MAX_SECTIONS:
        raise EditError(f"A survey has at most {MAX_SECTIONS} sections.")
    out, earlier, total, skeys = [], {}, 0, set()
    for si, s in enumerate(sections, 1):
        if not isinstance(s, dict):
            raise EditError(f"Section {si} is not readable.")
        sk = _key(s.get("key"), f"s{si}")
        while sk in skeys:
            sk += "_"
        skeys.add(sk)
        sec = {"key": sk, "title": _str(s.get("title"), 200) or f"Section {si}", "text": str(s.get("text") or "")[:2000],
               "condition": _condition(s.get("condition"), earlier, f"Section {si}"), "questions": []}
        for qi, q in enumerate(s.get("questions") or [], 1):
            total += 1
            if total > MAX_QUESTIONS:
                raise EditError(f"A survey has at most {MAX_QUESTIONS} questions.")
            where = f"Section {si}, question {qi}"
            if not isinstance(q, dict):
                raise EditError(f"{where} is not readable.")
            kind = q.get("kind") or "text"
            if kind not in KINDS:
                raise EditError(f"{where}: the kind is one of {', '.join(KINDS)}.")
            qk = _key(q.get("key"), f"q{total}")
            while qk in earlier:
                qk += "_"
            item = {"key": qk, "kind": kind, "text": _str(q.get("text"), 1000), "help": str(q.get("help") or "")[:2000],
                    "required": bool(q.get("required")), "condition": _condition(q.get("condition"), earlier, where)}
            if not item["text"]:
                raise EditError(f"{where}: give the question's wording.")
            if q.get("element"):                   # a maturity question: the architecture element it scores
                item["element"] = _key(q.get("element"), "element")
            if kind in CHOICE_KINDS:
                opts, seen = [], set()
                for oi, o in enumerate(q.get("options") or [], 1):
                    o = o if isinstance(o, dict) else {"label": o}
                    label = _str(o.get("label"), 1000)
                    if not label:
                        continue
                    value = _str(o.get("value"), 100) or str(oi)
                    if value in seen:
                        raise EditError(f"{where}: two options have the value {value}.")
                    seen.add(value)
                    opt = {"value": value, "label": label}
                    if o.get("description"):          # a level's description and what you typically see (D456)
                        opt["description"] = str(o["description"])[:1000]
                    ex = o.get("examples")
                    ex = ex.splitlines() if isinstance(ex, str) else (ex if isinstance(ex, list) else [])
                    ex = [_str(x, 300) for x in ex if _str(x, 300)][:12]
                    if ex:
                        opt["examples"] = ex
                    if o.get("score") not in (None, ""):
                        try:
                            opt["score"] = float(o["score"])
                        except (TypeError, ValueError) as exc:
                            raise EditError(f"{where}: an option's score is a number.") from exc
                    opts.append(opt)
                if len(opts) < 2 or len(opts) > MAX_OPTIONS:
                    raise EditError(f"{where}: a choice has 2 to {MAX_OPTIONS} options.")
                item["options"] = opts
                item["other"] = bool(q.get("other")) and kind == "single"
            if kind == "rating":
                lo, hi = int(q.get("min") or 1), int(q.get("max") or 5)
                if not 0 <= lo < hi <= 10:
                    raise EditError(f"{where}: a rating runs from 0 or more to 10 or less.")
                item["min"], item["max"] = lo, hi
                item["low_label"], item["high_label"] = _str(q.get("low_label"), 60), _str(q.get("high_label"), 60)
            if kind == "number":
                for b in ("min", "max"):
                    if q.get(b) not in (None, ""):
                        try:
                            item[b] = float(q[b])
                        except (TypeError, ValueError) as exc:
                            raise EditError(f"{where}: the {b}imum is a number.") from exc
            sec["questions"].append(item)
            earlier[qk] = item
        out.append(sec)
    return {"sections": out}


def questions(spec: dict) -> list[dict]:
    """Every question, in order, each with its section."""
    return [{**q, "section": s["key"], "section_title": s["title"]} for s in spec.get("sections", []) for q in s.get("questions", [])]


def _fits(c: dict | None, answers: dict, shown: set[str]) -> bool:
    if not c:
        return True
    if c["question"] not in shown:
        return False
    a = answers.get(c["question"])
    empty = a in (None, "", [])
    if c["op"] == "answered":
        return not empty
    if empty:
        return c["op"] == "not_equals"
    vals = [str(x) for x in a] if isinstance(a, list) else [str(a).lower() if isinstance(a, bool) else str(a)]
    want = str(c.get("value", ""))
    if c["op"] == "includes":
        return want in vals
    exactly = vals == [want]
    return exactly if c["op"] == "equals" else not exactly


def visible(spec: dict, answers: dict) -> set[str]:
    """The questions shown for these answers: a condition that does not fit hides its section or question, and a
    condition on a hidden question never fits."""
    shown: set[str] = set()
    for s in spec.get("sections", []):
        if not _fits(s.get("condition"), answers, shown):
            continue
        for q in s.get("questions", []):
            if _fits(q.get("condition"), answers, shown):
                shown.add(q["key"])
    return shown


def _value(q: dict, v: Any) -> Any:
    """One answer, checked for its kind; None when empty."""
    if v in (None, "", []) or (isinstance(v, str) and not v.strip()):
        return None
    k, t = q["kind"], q["text"][:60]
    if k == "single":
        v = str(v).strip()
        if v not in {o["value"] for o in q["options"]} and not q.get("other"):
            raise EditError(f"'{t}': choose one of the options.")
        return v[:MAX_TEXT]
    if k == "multi":
        vals = [str(x) for x in (v if isinstance(v, list) else [v])]
        allowed = {o["value"] for o in q["options"]}
        if any(x not in allowed for x in vals):
            raise EditError(f"'{t}': choose from the options.")
        return [o["value"] for o in q["options"] if o["value"] in vals]
    if k == "yes_no":
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ("yes", "true", "1"):
            return True
        if s in ("no", "false", "0"):
            return False
        raise EditError(f"'{t}': answer yes or no.")
    if k in ("rating", "number"):
        try:
            n = float(v)
        except (TypeError, ValueError) as exc:
            raise EditError(f"'{t}': give a number.") from exc
        lo, hi = q.get("min"), q.get("max")
        if (lo is not None and n < lo) or (hi is not None and n > hi):
            raise EditError(f"'{t}': give a number from {lo if lo is not None else 'any'} to {hi if hi is not None else 'any'}.")
        if k == "rating" and not n.is_integer():
            raise EditError(f"'{t}': a rating is a whole number.")
        return int(n) if n.is_integer() else n
    if k == "links":            # evidence: links with notes, like a Link attribute (D418): any text, never checked
        from . import links
        return links.parse(v) or None
    if k == "date":
        try:
            return date.fromisoformat(str(v)[:10]).isoformat()
        except ValueError as exc:
            raise EditError(f"'{t}': give a date (yyyy-mm-dd).") from exc
    return str(v)[:MAX_LONG if k == "long_text" else MAX_TEXT]


def check_answers(spec: dict, answers: Any, final: bool) -> dict:
    """The answers kept: only the questions shown, each checked; when final, every required one shown is answered."""
    answers = answers if isinstance(answers, dict) else {}
    qs = {q["key"]: q for q in questions(spec)}
    typed, bad = {}, {}
    for k, v in answers.items():
        if k in qs:
            try:
                v = _value(qs[k], v)
            except EditError as exc:
                bad[k] = exc
                continue
            if v is not None:
                typed[k] = v
    shown = visible(spec, typed)
    for k in qs:                  # an answer that does not fit counts only when its question is shown
        if k in bad and k in visible(spec, {**typed, k: "?"}):
            raise bad[k]
    out = {k: v for k, v in typed.items() if k in shown}
    if final:
        missing = [qs[k]["text"] for k in qs if k in shown and qs[k]["required"] and k not in out]
        if missing:
            raise EditError("Answer the required questions first: " + "; ".join(m[:80] for m in missing[:5])
                            + (f" and {len(missing) - 5} more" if len(missing) > 5 else ""))
    return out


# ---------------------------------------------------------------- who it is for
def clean_recipients(spec: Any) -> list[dict]:
    if not isinstance(spec, list):
        raise EditError("Recipients are a list.")
    out, seen = [], set()
    for r in spec:
        if not isinstance(r, dict) or r.get("kind") not in RECIPIENT_KINDS or not str(r.get("value") or "").strip():
            raise EditError(f"A recipient is a {', '.join(RECIPIENT_KINDS)} with a value.")
        item = {"kind": r["kind"], "value": str(r["value"]).strip()[:200]}
        if r["kind"] == "user":
            item["value"] = item["value"].lower()
        if r["kind"] == "role" and item["value"] not in perms.GLOBAL_ROLES:
            raise EditError(f"No global role {item['value']}.")
        if r["kind"] == "model" and r.get("role"):
            if r["role"] not in perms.MODEL_ROLES:
                raise EditError(f"No model role {r['role']}.")
            item["role"] = r["role"]
        if r.get("label"):
            item["label"] = _str(r["label"], 200)
        key = (item["kind"], item["value"], item.get("role", ""))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _project_members(conn, guid: str) -> list[str]:
    from . import projects as pj
    try:
        from .db import base_engine, get_projects_engine
        peng = get_projects_engine()
        if peng is base_engine():
            rows = _rows(conn, """SELECT DISTINCT lower(m.username) AS u FROM proj.members m JOIN proj.projects p ON p.id = m.project_id
                                   WHERE p.guid = CAST(:g AS uuid)""", g=guid)
        else:
            with peng.connect() as pc:
                rows = pj._rows(pc, """SELECT DISTINCT lower(m.username) AS u FROM proj.members m JOIN proj.projects p ON p.id = m.project_id
                                        WHERE p.guid = CAST(:g AS uuid)""", g=guid)
    except Exception:  # noqa: BLE001 - projects switched off or not reachable: nobody from there
        return []
    return [r["u"] for r in rows]


def resolve(conn, spec: list[dict]) -> list[str]:
    """The people the recipients stand for now (lower case, sorted)."""
    from .quality import _bypass
    people: set[str] = set()
    _bypass(conn, True)            # everyone on a model, whoever sends the survey
    for r in spec:
        k, v = r["kind"], r["value"]
        if k == "user":
            people.add(v.lower())
        elif k == "role":
            people |= {x["u"] for x in _rows(conn, "SELECT lower(username) AS u FROM core.known_users WHERE :r = ANY (roles)", r=v)}
        elif k == "model":
            sql = """SELECT DISTINCT lower(u.username) AS u FROM core.model_users u JOIN core.models m ON m.id = u.model_id
                      WHERE m.guid::text = :m OR m.name = :m"""
            if r.get("role"):
                sql += " AND u.role = :role"
            people |= {x["u"] for x in _rows(conn, sql, m=v, role=r.get("role", ""))}
        elif k == "project":
            people |= set(_project_members(conn, v))
    _bypass(conn, False)
    return sorted(p for p in people if p)


def people_to_pick(conn, q: str = "") -> dict:
    """What a survey can go to: people seen signing in, global roles, models and projects."""
    like = f"%{(q or '').strip().lower()}%"
    users = [r["u"] for r in _rows(conn, "SELECT lower(username) AS u FROM core.known_users WHERE lower(username) LIKE :q "
                                         "ORDER BY 1 LIMIT 200", q=like)]
    models = _rows(conn, """SELECT guid::text AS id, name FROM core.models WHERE NOT is_deleted AND lower(name) LIKE :q
                             ORDER BY name LIMIT 200""", q=like)
    projects: list[dict] = []
    try:
        from .db import base_engine, get_projects_engine
        peng = get_projects_engine()
        sql = "SELECT guid::text AS id, name FROM proj.projects WHERE lower(name) LIKE :q ORDER BY name LIMIT 200"
        if peng is base_engine():
            projects = _rows(conn, sql, q=like)
        else:
            with peng.connect() as pc:
                projects = [dict(r) for r in pc.execute(text(sql), {"q": like}).mappings().all()]
    except Exception:  # noqa: BLE001 - projects off
        projects = []
    return {"users": users, "roles": [r for r in perms.GLOBAL_ROLES], "model_roles": list(perms.MODEL_ROLES),
            "models": models, "projects": projects}


# ---------------------------------------------------------------- surveys
def _survey(conn, guid: Any, lock: bool = False) -> dict:
    try:
        s = _one(conn, f"SELECT * FROM core.surveys WHERE guid = CAST(:g AS uuid) AND NOT is_deleted{' FOR UPDATE' if lock else ''}",
                 g=str(guid))
    except Exception as exc:  # noqa: BLE001 - not a guid
        raise EditError("No such survey.", 404) from exc
    if not s:
        raise EditError("No such survey.", 404)
    return s


def _now() -> datetime:
    return datetime.now(UTC)


def _dt(v: Any) -> datetime | None:
    """A timestamp as a datetime (the driver gives one; a text one is read)."""
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _closes(v: Any) -> datetime | None:
    if v in (None, ""):
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EditError("The closing date is a date (yyyy-mm-dd) or a date and time.") from exc
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
        if len(str(v)) <= 10:
            d = d + timedelta(hours=23, minutes=59)
    return d


def progress(conn, s: dict) -> dict:
    """Asked, answered (of those asked, and by the link), started but not sent, and the share of those asked who answered."""
    r = _one(conn, """SELECT count(*) FILTER (WHERE via = 'asked') AS asked,
                             count(answered_at) FILTER (WHERE via = 'asked') AS answered_of_asked,
                             count(answered_at) FILTER (WHERE via = 'link') AS by_link
                        FROM core.survey_recipients WHERE survey_guid = :g""", g=s["guid"])
    x = _one(conn, """SELECT count(*) FILTER (WHERE status = 'submitted') AS answered,
                             count(*) FILTER (WHERE status = 'in_progress') AS started
                        FROM core.survey_responses WHERE survey_guid = :g""", g=s["guid"])
    return {"asked": r["asked"], "answered": x["answered"], "answered_of_asked": r["answered_of_asked"], "by_link": r["by_link"],
            "in_progress": x["started"], "percent": round(100 * r["answered_of_asked"] / r["asked"]) if r["asked"] else 0}


def _out(conn, s: dict, user) -> dict:
    name, _roles = _user(user)
    me = _one(conn, "SELECT answered_at, added_at FROM core.survey_recipients WHERE survey_guid = :g AND username = :u",
              g=s["guid"], u=name)
    runs = _runs(s, user)
    out = {"id": str(s["guid"]), "kind": s["kind"], "title": s["title"], "description": s["description"], "status": s["status"],
           "anonymous": s["anonymous"], "open_link": s["open_link"], "owner": s["owner"], "created_at": s["created_at"],
           "updated_at": s["updated_at"], "opened_at": s["opened_at"], "closed_at": s["closed_at"], "closes_at": s["closes_at"],
           "remind_every_days": s["remind_every_days"], "last_reminded_at": s["last_reminded_at"],
           "questions": len(questions(s["spec"] or {})), "link": LINK.format(g=s["guid"]),
           "asked_me": bool(me), "answered": bool(me and me["answered_at"]), "runs": runs,
           "may_answer": s["status"] == "open" and (bool(me) or s["open_link"]) and not (s["anonymous"] and me and me["answered_at"])}
    if runs:
        out["progress"] = progress(conn, s)
        out["recipients"] = s["recipients_spec"] or []
    return out


def listing(conn, user) -> dict:
    """To answer (asked, open), answered, the ones I run, and every survey for a Super Admin."""
    name, roles = _user(user)
    asked = _rows(conn, """SELECT s.* FROM core.surveys s JOIN core.survey_recipients r ON r.survey_guid = s.guid
                            WHERE r.username = :u AND NOT s.is_deleted AND s.status <> 'draft' ORDER BY s.opened_at DESC NULLS LAST""",
                  u=name)
    mine = _rows(conn, """SELECT * FROM core.surveys WHERE lower(owner) = :u AND NOT is_deleted ORDER BY updated_at DESC""", u=name)
    every = (_rows(conn, "SELECT * FROM core.surveys WHERE NOT is_deleted ORDER BY updated_at DESC LIMIT 500")
             if perms.SUPER_ADMIN in roles else [])
    o = lambda xs: [_out(conn, s, user) for s in xs]  # noqa: E731
    asked_o = o(asked)
    return {"to_answer": [s for s in asked_o if s["status"] == "open" and not s["answered"]],
            "answered": [s for s in asked_o if s["answered"] or s["status"] == "closed"],
            "mine": o(mine), "all": o(every), "may_create": may_create(user), "kinds": KINDS, "ops": OPS}


def get(conn, user, guid: Any) -> dict:
    s = _survey(conn, guid)
    out = _out(conn, s, user)
    if not (out["runs"] or out["asked_me"] or (s["open_link"] and s["status"] != "draft")):
        raise EditError("This survey was not sent to you.", 403)
    out["spec"] = s["spec"]
    if s["kind"] == "maturity":
        out["maturity"] = s["maturity"] or {}
    return out


def _need_run(s: dict, user) -> None:
    if not _runs(s, user):
        raise EditError("Only the person who made this survey, or a Super Admin, runs it.", 403)


def create(conn, user, d: dict, kind: str = "survey") -> dict:
    if not may_create(user):
        raise EditError("Making surveys needs the Super Admin, Model Creator or Library Admin role.", 403)
    name, _roles = _user(user)
    title = _str(d.get("title"), 200)
    if not title:
        raise EditError("Give the survey a title.")
    spec = clean_spec(d.get("spec") or {"sections": []})
    rec = clean_recipients(d.get("recipients") or [])
    s = _one(conn, """INSERT INTO core.surveys (kind, title, description, spec, anonymous, open_link, recipients_spec,
                                                remind_every_days, closes_at, maturity, owner)
                      VALUES (:k, :t, :d, CAST(:sp AS jsonb), :a, :ol, CAST(:r AS jsonb), :re, :c, CAST(:mt AS jsonb), :o)
                      RETURNING *""",
             k=kind, t=title, d=str(d.get("description") or "")[:4000], sp=json.dumps(spec), a=bool(d.get("anonymous")),
             ol=bool(d.get("open_link")), r=json.dumps(rec), re=_remind(d.get("remind_every_days")),
             c=_closes(d.get("closes_at")), mt=json.dumps(d["maturity"]) if d.get("maturity") is not None else None, o=name)
    return get(conn, user, s["guid"])


def _remind(v: Any) -> int | None:
    if v in (None, "", 0, "0"):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError) as exc:
        raise EditError("Remind every so many days: a whole number.") from exc
    if not 1 <= n <= 60:
        raise EditError("Remind every 1 to 60 days.")
    return n


def update(conn, user, guid: Any, d: dict) -> dict:
    """A draft: anything. Open or closed: the title, description, closing date and reminders (the questions and
    anonymity stay as sent)."""
    s = _survey(conn, guid, lock=True)
    _need_run(s, user)
    sets, p = ["updated_at = now()"], {"g": s["guid"]}
    if "title" in d:
        if not _str(d["title"], 200):
            raise EditError("Give the survey a title.")
        sets.append("title = :t")
        p["t"] = _str(d["title"], 200)
    if "description" in d:
        sets.append("description = :d")
        p["d"] = str(d["description"] or "")[:4000]
    if "closes_at" in d:
        c = _closes(d["closes_at"])
        if c and s["status"] == "open" and c < _now():
            raise EditError("The closing date has passed: close the survey instead.")
        sets.append("closes_at = :c")
        p["c"] = c
    if "remind_every_days" in d:
        sets.append("remind_every_days = :re")
        p["re"] = _remind(d["remind_every_days"])
    if "open_link" in d:
        sets.append("open_link = :ol")
        p["ol"] = bool(d["open_link"])
    if "maturity" in d and s["kind"] == "maturity" and isinstance(d["maturity"], dict):
        from . import maturity as mt
        sets.append("maturity = CAST(:mt AS jsonb)")
        p["mt"] = json.dumps(mt.clean_settings({**(s["maturity"] or {}), **d["maturity"]}))
    draft_only = [k for k in ("spec", "anonymous", "recipients") if k in d]
    if draft_only and s["status"] != "draft":
        if draft_only == ["recipients"]:
            raise EditError("The survey has been sent: add people with Add recipients.")
        raise EditError("The questions and anonymity change only while the survey is a draft.")
    if "spec" in d:
        sets.append("spec = CAST(:sp AS jsonb)")
        p["sp"] = json.dumps(clean_spec(d["spec"]))
    if "anonymous" in d:
        sets.append("anonymous = :a")
        p["a"] = bool(d["anonymous"])
    if "recipients" in d:
        sets.append("recipients_spec = CAST(:r AS jsonb)")
        p["r"] = json.dumps(clean_recipients(d["recipients"]))
    conn.execute(text(f"UPDATE core.surveys SET {', '.join(sets)} WHERE guid = :g"), p)
    return get(conn, user, s["guid"])


def delete(conn, user, guid: Any) -> dict:
    s = _survey(conn, guid, lock=True)
    _need_run(s, user)
    if s["status"] != "draft":
        raise EditError("Only a draft is deleted; close a sent survey instead (its answers are kept).")
    conn.execute(text("UPDATE core.surveys SET is_deleted = true, updated_at = now() WHERE guid = :g"), {"g": s["guid"]})
    return {"deleted": str(s["guid"])}


def copy(conn, user, guid: Any) -> dict:
    """A new draft with the same questions and recipients (no answers)."""
    s = _survey(conn, guid)
    if not (_runs(s, user) or may_create(user)):
        raise EditError("Making surveys needs the Super Admin, Model Creator or Library Admin role.", 403)
    d = {"title": f"{s['title']} (copy)"[:200], "description": s["description"], "spec": s["spec"], "anonymous": s["anonymous"],
         "open_link": s["open_link"], "recipients": s["recipients_spec"] or [], "remind_every_days": s["remind_every_days"]}
    if s["kind"] == "maturity":
        from . import maturity as mt
        d["maturity"] = mt.clean_settings({k: v for k, v in (s["maturity"] or {}).items() if k in ("targets", "weights")})
    return create(conn, user, d, kind=s["kind"])


def _ask(conn, s: dict, people: list[str], actor: str) -> int:
    """Adds people not yet asked and gives each a notification that needs action (their task list)."""
    n = 0
    what = "maturity assessment" if s["kind"] == "maturity" else "survey"
    for u in people:
        r = _one(conn, """INSERT INTO core.survey_recipients (survey_guid, username) VALUES (:g, :u)
                          ON CONFLICT (survey_guid, username) DO NOTHING RETURNING id""", g=s["guid"], u=u)
        if not r:
            continue
        n += 1
        notify.create(conn, kind="survey.asked", category="request", title=f"Please answer the {what} '{s['title']}'",
                      body=(s["description"] or "")[:1000] + (f"\nIt closes on {_dt(s['closes_at']):%Y-%m-%d}." if s.get("closes_at") else ""),
                      actor=actor, link=LINK.format(g=s["guid"]), recipients=[u], needs_action=True,
                      ref_kind="survey_recipient", ref_id=r["id"], include_actor=True)
    return n


def send(conn, user, guid: Any) -> dict:
    """Draft to open: the people it is for are worked out and asked."""
    s = _survey(conn, guid, lock=True)
    _need_run(s, user)
    if s["status"] != "draft":
        raise EditError("Only a draft is sent; it is already " + s["status"] + ".")
    if not questions(s["spec"] or {}):
        raise EditError("Add at least one question first.")
    people = resolve(conn, s["recipients_spec"] or [])
    if not people and not s["open_link"]:
        raise EditError("Nobody to ask: choose recipients, or let anyone with the link answer.")
    if s["closes_at"] and _dt(s["closes_at"]) < _now():
        raise EditError("The closing date has passed: change it first.")
    conn.execute(text("UPDATE core.surveys SET status = 'open', opened_at = now(), updated_at = now() WHERE guid = :g"),
                 {"g": s["guid"]})
    s = _survey(conn, s["guid"])
    if s["kind"] == "maturity":
        from . import maturity as mt
        mt.on_open(conn, s)
    n = _ask(conn, s, people, _user(user)[0])
    out = get(conn, user, s["guid"])
    out["asked_now"] = n
    return out


def add_recipients(conn, user, guid: Any, recipients: Any) -> dict:
    """While open: more people (never fewer)."""
    s = _survey(conn, guid, lock=True)
    _need_run(s, user)
    rec = clean_recipients(recipients or [])
    merged = clean_recipients((s["recipients_spec"] or []) + rec)
    conn.execute(text("UPDATE core.surveys SET recipients_spec = CAST(:r AS jsonb), updated_at = now() WHERE guid = :g"),
                 {"r": json.dumps(merged), "g": s["guid"]})
    n = _ask(conn, s, resolve(conn, rec), _user(user)[0]) if s["status"] == "open" else 0
    out = get(conn, user, s["guid"])
    out["asked_now"] = n
    return out


def _recipient_ids(conn, s: dict, username: str | None = None) -> list[int]:
    where = "r.survey_guid = :g" + (" AND r.username = :u" if username else "")
    return [int(x) for x in conn.execute(text(f"SELECT r.id FROM core.survey_recipients r WHERE {where}"),
                                         {"g": s["guid"], "u": username}).scalars()]


def _resolve_open(conn, s: dict, note: str, username: str | None = None) -> int:
    """The survey's open notifications resolved: the recipients from the repository, the notifications in the personal
    schema (no join across schemas, D632)."""
    from . import personal as P
    ids = _recipient_ids(conn, s, username)
    if not ids:
        return 0
    try:
        return P.run(conn, """
            UPDATE personal.notifications n SET resolved_at = now(), resolved_by = :b, resolution = :note
             WHERE n.ref_kind = 'survey_recipient' AND n.ref_id = ANY(:ids) AND n.needs_action AND n.resolved_at IS NULL""",
                     ids=ids, b=username or "system", note=note).rowcount
    except P.Unavailable:
        return 0


def close(conn, user, guid: Any, by: str | None = None) -> dict:
    s = _survey(conn, guid, lock=True)
    if user is not None:
        _need_run(s, user)
    if s["status"] != "open":
        raise EditError("Only an open survey is closed.")
    _close(conn, s, by or _user(user)[0])
    return get(conn, user, s["guid"]) if user is not None else {"closed": str(s["guid"])}


def _close(conn, s: dict, by: str) -> None:
    conn.execute(text("UPDATE core.surveys SET status = 'closed', closed_at = now(), updated_at = now() WHERE guid = :g"),
                 {"g": s["guid"]})
    _resolve_open(conn, s, "The survey closed")
    from . import personal as P
    ids = _recipient_ids(conn, s)
    if ids:
        try:
            P.run(conn, """UPDATE personal.notifications n SET resolved_by = :b
                            WHERE n.ref_kind = 'survey_recipient' AND n.ref_id = ANY(:ids)
                              AND n.resolution = 'The survey closed' AND n.resolved_by = 'system'""", b=by, ids=ids)
        except P.Unavailable:
            pass
    if s["kind"] == "maturity":
        from . import maturity as mt
        mt.on_close(conn, _survey(conn, s["guid"]))


def reopen(conn, user, guid: Any) -> dict:
    s = _survey(conn, guid, lock=True)
    _need_run(s, user)
    if s["status"] != "closed":
        raise EditError("Only a closed survey is reopened.")
    conn.execute(text("""UPDATE core.surveys SET status = 'open', closed_at = NULL, updated_at = now(),
                                closes_at = CASE WHEN closes_at < now() THEN NULL ELSE closes_at END WHERE guid = :g"""),
                 {"g": s["guid"]})
    # the people who had not answered get their task back
    s = _survey(conn, s["guid"])
    for r in _rows(conn, "SELECT id, username FROM core.survey_recipients WHERE survey_guid = :g AND answered_at IS NULL AND via = 'asked'",
                   g=s["guid"]):
        notify.create(conn, kind="survey.asked", category="request", title=f"Reopened: please answer '{s['title']}'",
                      actor=_user(user)[0], link=LINK.format(g=s["guid"]), recipients=[r["username"]], needs_action=True,
                      ref_kind="survey_recipient", ref_id=r["id"], include_actor=True)
    return get(conn, user, s["guid"])


def remind(conn, user, guid: Any, by: str | None = None) -> dict:
    """Everyone asked who has not answered gets a reminder (information; their task is still open)."""
    s = _survey(conn, guid, lock=True)
    if user is not None:
        _need_run(s, user)
    if s["status"] != "open":
        raise EditError("Only an open survey sends reminders.")
    who = _rows(conn, """SELECT id, username FROM core.survey_recipients
                          WHERE survey_guid = :g AND answered_at IS NULL AND via = 'asked'""", g=s["guid"])
    for r in who:
        notify.create(conn, kind="survey.reminder", category="request", title=f"Reminder: please answer '{s['title']}'",
                      body=f"It closes on {_dt(s['closes_at']):%Y-%m-%d}." if s["closes_at"] else "", actor=by or _user(user)[0],
                      link=LINK.format(g=s["guid"]), recipients=[r["username"]], include_actor=True)
    conn.execute(text("UPDATE core.survey_recipients SET reminded_at = now() WHERE survey_guid = :g AND answered_at IS NULL AND via = 'asked'"),
                 {"g": s["guid"]})
    conn.execute(text("UPDATE core.surveys SET last_reminded_at = now() WHERE guid = :g"), {"g": s["guid"]})
    return {"reminded": len(who)}


def housekeeping(conn) -> dict:
    """Every hour (eax.surveys job): surveys past their closing date close; automatic reminders go out."""
    closed = reminded = 0
    for s in _rows(conn, "SELECT * FROM core.surveys WHERE status = 'open' AND NOT is_deleted AND closes_at IS NOT NULL AND closes_at <= now()"):
        _close(conn, s, "system")
        closed += 1
    for s in _rows(conn, """SELECT * FROM core.surveys WHERE status = 'open' AND NOT is_deleted AND remind_every_days IS NOT NULL
                              AND COALESCE(last_reminded_at, opened_at) <= now() - make_interval(days => remind_every_days)"""):
        reminded += remind(conn, None, s["guid"], by="system")["reminded"]
    return {"closed": closed, "reminded": reminded}


# ---------------------------------------------------------------- answering
def my_answer(conn, user, guid: Any) -> dict:
    """The survey to answer, with my saved answers (not in an anonymous survey: those stay in my browser)."""
    s = _survey(conn, guid)
    name, _roles = _user(user)
    out = get(conn, user, guid)
    if s["status"] == "draft":
        if not out["runs"]:
            raise EditError("This survey has not been sent yet.", 403)
        out["preview"] = True
    resp = None if s["anonymous"] else _one(conn, "SELECT answers, status, updated_at, submitted_at FROM core.survey_responses "
                                                  "WHERE survey_guid = :g AND respondent = :u", g=s["guid"], u=name)
    out["answers"] = (resp or {}).get("answers") or {}
    out["response_status"] = (resp or {}).get("status") or ("submitted" if out["answered"] else "")
    out["submitted_at"] = (resp or {}).get("submitted_at")
    return out


def answer(conn, user, guid: Any, answers: Any, submit: bool) -> dict:
    """Saves (or sends) my answers. Anonymous: sent once, with no name, and only sending is kept."""
    s = _survey(conn, guid, lock=True)
    name, _roles = _user(user)
    if s["status"] != "open":
        raise EditError("This survey is " + ("not sent yet." if s["status"] == "draft" else "closed."))
    me = _one(conn, "SELECT * FROM core.survey_recipients WHERE survey_guid = :g AND username = :u", g=s["guid"], u=name)
    if not me and not s["open_link"]:
        raise EditError("This survey was not sent to you.", 403)
    clean = check_answers(s["spec"] or {}, answers, final=submit)
    if s["anonymous"]:
        if not submit:
            raise EditError("An anonymous survey keeps nothing until you send it: your draft stays in this browser.")
        if me and me["answered_at"]:
            raise EditError("You have already answered this anonymous survey.")
        if not me:
            me = _one(conn, "INSERT INTO core.survey_recipients (survey_guid, username, via) VALUES (:g, :u, 'link') RETURNING *",
                      g=s["guid"], u=name)
        conn.execute(text("""INSERT INTO core.survey_responses (survey_guid, respondent, answers, status, submitted_at)
                             VALUES (:g, NULL, CAST(:a AS jsonb), 'submitted', now())"""), {"g": s["guid"], "a": json.dumps(clean)})
    else:
        if not me:
            me = _one(conn, "INSERT INTO core.survey_recipients (survey_guid, username, via) VALUES (:g, :u, 'link') RETURNING *",
                      g=s["guid"], u=name)
        conn.execute(text("""INSERT INTO core.survey_responses (survey_guid, respondent, answers, status, submitted_at)
                             VALUES (:g, :u, CAST(:a AS jsonb), :st, CASE WHEN :sub THEN now() END)
                             ON CONFLICT (survey_guid, respondent) DO UPDATE SET answers = EXCLUDED.answers, updated_at = now(),
                                 status = CASE WHEN :sub THEN 'submitted' ELSE core.survey_responses.status END,
                                 submitted_at = CASE WHEN :sub THEN now() ELSE core.survey_responses.submitted_at END"""),
                     {"g": s["guid"], "u": name, "a": json.dumps(clean), "st": "submitted" if submit else "in_progress", "sub": submit})
    if submit:
        conn.execute(text("UPDATE core.survey_recipients SET answered_at = now() WHERE id = :i"), {"i": me["id"]})
        _resolve_open(conn, s, "Answered", username=name)
    return {"saved": True, "submitted": submit, "answers": clean if not s["anonymous"] else {}}


# ---------------------------------------------------------------- results
def _responses(conn, s: dict) -> list[dict]:
    return _rows(conn, """SELECT guid, respondent, answers, submitted_at FROM core.survey_responses
                           WHERE survey_guid = :g AND status = 'submitted' ORDER BY submitted_at, id""", g=s["guid"])


def summarise(spec: dict, responses: list[dict]) -> list[dict]:
    """Results by question: counts and shares for choices, mean and spread for numbers and ratings, text answers."""
    out = []
    for q in questions(spec):
        vals = [(r.get("respondent"), (r.get("answers") or {}).get(q["key"])) for r in responses]
        vals = [(who, v) for who, v in vals if v not in (None, "", [])]
        item = {"key": q["key"], "kind": q["kind"], "text": q["text"], "section": q["section_title"], "answered": len(vals),
                "of": len(responses)}
        if q.get("element"):
            item["element"] = q["element"]
        if q["kind"] in CHOICE_KINDS or q["kind"] == "yes_no":
            opts = q.get("options") or [{"value": True, "label": "Yes"}, {"value": False, "label": "No"}]
            counts = []
            for o in opts:
                n = sum(1 for _w, v in vals if (o["value"] in v if isinstance(v, list) else v == o["value"]))
                counts.append({"value": o["value"], "label": o["label"], "count": n,
                               "share": round(100 * n / len(vals)) if vals else 0, **({"score": o["score"]} if "score" in o else {})})
            item["options"] = counts
            others = [v for _w, v in vals if q["kind"] == "single" and v not in {o["value"] for o in opts}]
            if others:
                item["other"] = others
            scored = [o for o in (q.get("options") or []) if "score" in o]
            if scored and q["kind"] == "single":
                sc = {o["value"]: o["score"] for o in scored}
                xs = [sc[v] for _w, v in vals if v in sc]
                if xs:
                    item["mean_score"] = round(sum(xs) / len(xs), 2)
        elif q["kind"] in ("rating", "number"):
            xs = [float(v) for _w, v in vals]
            if xs:
                xs.sort()
                mid = len(xs) // 2
                item.update({"mean": round(sum(xs) / len(xs), 2), "min": xs[0], "max": xs[-1],
                             "median": xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2})
            if q["kind"] == "rating":
                item["options"] = [{"value": i, "label": str(i), "count": sum(1 for x in xs if x == i),
                                    "share": round(100 * sum(1 for x in xs if x == i) / len(xs)) if xs else 0}
                                   for i in range(q.get("min", 1), q.get("max", 5) + 1)]
        elif q["kind"] == "links":
            item["links"] = [{"by": who, "links": v} for who, v in vals]
        else:
            item["answers"] = [{"by": who, "text": v} for who, v in vals]
        out.append(item)
    return out


def results(conn, user, guid: Any) -> dict:
    s = _survey(conn, guid)
    _need_run(s, user)
    if s["kind"] == "maturity" and not perms.allowed(_user(user)[1], "maturity.manage"):
        raise EditError("A maturity assessment's scores are shown to Super Admins only.", 403)   # D456
    resp = _responses(conn, s)
    out = get(conn, user, guid)
    if s["anonymous"] and len(resp) < ANONYMOUS_MIN:
        out["results"] = []
        out["hidden"] = f"An anonymous survey's results show once {ANONYMOUS_MIN} people have answered ({len(resp)} so far)."
    else:
        out["results"] = summarise(s["spec"] or {}, resp)
    out["responses"] = len(resp)
    # who has answered and who has not (D456); in an anonymous survey only that, never joined to what they answered
    out["people"] = _rows(conn, """SELECT username, via, added_at, reminded_at, answered_at,
                                          (SELECT status FROM core.survey_responses x WHERE x.survey_guid = r.survey_guid
                                              AND x.respondent = r.username) AS response
                                     FROM core.survey_recipients r WHERE survey_guid = :g ORDER BY username""", g=s["guid"])
    if s["kind"] == "maturity":
        from . import maturity as mt
        out["scores"] = mt.scores(s, resp)
    return out


def _cell(v: Any) -> Any:
    if isinstance(v, list) and v and isinstance(v[0], dict):      # evidence links: one line each, "address | note"
        from . import links
        return links.store(v)
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (datetime, date)):
        return v.isoformat(sep=" ")[:16] if isinstance(v, datetime) else v.isoformat()
    return v


def to_xlsx(conn, user, guid: Any) -> tuple[bytes, str]:
    """The results by question and every response (no names in an anonymous survey)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    r = results(conn, user, guid)
    s = _survey(conn, guid)
    if r.get("hidden"):
        raise EditError(r["hidden"])
    wb = Workbook()
    ws = wb.active
    ws.title = "About"
    bold = Font(bold=True)
    for row in (("Survey", s["title"]), ("Status", s["status"]), ("Anonymous", "Yes" if s["anonymous"] else "No"),
                ("Asked", r["progress"]["asked"]), ("Answered", r["responses"]), ("Owner", s["owner"]),
                ("Sent", _cell(s["opened_at"]) or ""), ("Closed", _cell(s["closed_at"]) or ""),
                ("Note", "Answers never change any model (D375).")):
        ws.append(row)
        ws.cell(ws.max_row, 1).font = bold
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 14, 70
    sm = wb.create_sheet("By question")
    sm.append(["Section", "Question", "Kind", "Answered", "Answer", "Count", "Share %", "Mean", "Median", "Min", "Max"])
    for c in sm[1]:
        c.font = bold
    for q in r["results"]:
        base = [q["section"], q["text"], KINDS[q["kind"]], q["answered"]]
        if q.get("options"):
            for o in q["options"]:
                sm.append(base + [o["label"], o["count"], o["share"], q.get("mean", q.get("mean_score")), q.get("median"),
                                  q.get("min"), q.get("max")])
            for v in q.get("other", []):
                sm.append(base + [f"Other: {v}", 1])
        elif q.get("links") is not None:
            for a in q["links"]:
                sm.append(base + [_cell(a["links"])])
            if not q["links"]:
                sm.append(base)
        elif q.get("answers") is not None:
            for a in q["answers"]:
                sm.append(base + [a["text"]])
            if not q["answers"]:
                sm.append(base)
        else:
            sm.append(base + ["", "", "", q.get("mean"), q.get("median"), q.get("min"), q.get("max")])
    for col, w in zip("ABCDE", (22, 50, 14, 10, 60), strict=False):
        sm.column_dimensions[col].width = w
    rs = wb.create_sheet("Responses")
    qs = questions(s["spec"] or {})
    many = len({q["section"] for q in qs}) > 1        # the section's title first, so repeated wording stays clear
    rs.append(["Response", "Sent"] + [f"{q['section_title']}: {q['text']}" if many else q["text"] for q in qs])
    for c in rs[1]:
        c.font = bold
    names = {q["key"]: {o["value"]: o["label"] for o in q.get("options", [])} for q in qs}

    def shown(q: dict, v: Any) -> Any:       # a choice as its label (a maturity level as "2 Under development")
        if isinstance(v, list) and q["kind"] == "multi":
            return "; ".join(names[q["key"]].get(x, x) for x in v)
        return _cell(names[q["key"]].get(v, v) if isinstance(v, str) else v)
    for i, x in enumerate(_responses(conn, s), 1):
        who = x["respondent"] if not s["anonymous"] else f"Response {i}"
        rs.append([who, _cell(x["submitted_at"])] + [shown(q, (x["answers"] or {}).get(q["key"])) for q in qs])
    if s["kind"] == "maturity" and r.get("scores"):
        from . import maturity as mt
        mt.xlsx_sheet(wb, r["scores"], bold, s["spec"] or {})
    buf = io.BytesIO()
    wb.save(buf)
    safe = re.sub(r"[^A-Za-z0-9 _-]", "", s["title"]).strip()[:60] or "survey"
    return buf.getvalue(), f"{safe} results.xlsx"
