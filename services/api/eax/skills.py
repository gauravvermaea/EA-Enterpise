"""People's skills (owner, 9 Nov 2026, D353).

* Each user adds their own skills on their profile (My profile): free tags, with the tags others use offered as they type.
* The Skills repository lists **every EA Explorer user** (the people in Keycloak, not names typed into projects; when
  Keycloak is not answering it says so: nobody can sign in then anyway), with
  their skills, by skill and by person. Everyone signed in reads it.
* A project's Organisation tab shows a linked user's skills from their profile; it no longer keeps skills of its own.
"""

from __future__ import annotations

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one
MAX_SKILLS, MAX_LEN = 40, 60
HIDDEN = {"system", "break-glass", "service-account-eaexplorer-api"}


def clean(skills) -> list[str]:
    """Tags as kept: trimmed, single spaces, at most 60 characters, no repeats (ignoring case), at most 40."""
    if isinstance(skills, str):
        skills = skills.split(",")
    out: dict[str, str] = {}
    for k in skills or []:
        k = " ".join(str(k).split())[:MAX_LEN]
        if k and k.lower() not in out:
            out[k.lower()] = k
    if len(out) > MAX_SKILLS:
        raise EditError(f"At most {MAX_SKILLS} skills.")
    return list(out.values())


def of(conn, usernames) -> dict[str, list[str]]:
    names = sorted({(u or "").lower() for u in usernames if u})
    if not names:
        return {}
    return {r["username"]: list(r["skills"] or []) for r in _rows(
        conn, "SELECT username, skills FROM proj.user_skills WHERE username = ANY (CAST(:u AS text[]))", u=names)}


def all_tags(conn) -> list[str]:
    """Every skill anyone has, spelled as most people spell it."""
    rows = _rows(conn, """SELECT k, count(*) AS n FROM proj.user_skills, unnest(skills) AS k GROUP BY k""")
    best: dict[str, tuple[int, str]] = {}
    for r in rows:
        key = r["k"].lower()
        if key not in best or r["n"] > best[key][0]:
            best[key] = (r["n"], r["k"])
    return sorted((v[1] for v in best.values()), key=str.lower)


def mine(conn, user) -> dict:
    r = _one(conn, "SELECT skills, modified_at FROM proj.user_skills WHERE username = :u", u=user.username.lower())
    return {"username": user.username.lower(), "skills": list((r or {}).get("skills") or []),
            "modified_at": str(getattr(r["modified_at"], "isoformat", lambda: r["modified_at"])()) if r and r.get("modified_at") else None,
            "suggestions": all_tags(conn)}


def set_mine(conn, user, skills) -> dict:
    tags = clean(skills)
    conn.execute(text("""INSERT INTO proj.user_skills (username, skills, modified_by) VALUES (:u, CAST(:s AS text[]), :u)
                          ON CONFLICT (username) DO UPDATE SET skills = EXCLUDED.skills, modified_by = EXCLUDED.modified_by,
                                                               modified_at = now()"""),
                 {"u": user.username.lower(), "s": tags})
    return {"skills": tags, "message": f"Your skills are saved ({len(tags)})." if tags else "Your skills are cleared."}


def _users() -> list[dict]:
    """Every user in the realm (Keycloak). Without Keycloak nobody can sign in anyway, so there is no fallback (owner,
    9 Nov 2026): the repository says the sign-in service is not answering."""
    from . import keycloak_admin as kc
    out, first = [], 0
    while True:
        try:
            page = kc.users(first=first, limit=100)
        except Exception as exc:  # noqa: BLE001
            raise EditError("The sign-in service (Keycloak) is not answering, so the list of users cannot be read.", 503) from exc
        out += page
        if len(page) < 100 or first > 5000:
            break
        first += 100
    return [{"username": u["username"], "name": u.get("name") or "", "enabled": u.get("enabled", True)} for u in out]


def repository(conn, user) -> dict:
    """The Skills repository: every user with their skills; and every skill with how many have it."""
    users = _users()
    users = [u for u in users if u["username"] and u["username"] not in HIDDEN and not u["username"].startswith("service-account-")]
    have = of(conn, [u["username"] for u in users])
    for u in users:
        u["skills"] = have.get(u["username"], [])
    counts: dict[str, list[str]] = {}
    for u in users:
        for k in u["skills"]:
            counts.setdefault(k.lower(), []).append(u["username"])
    tags = {t.lower(): t for t in all_tags(conn)}
    return {"users": sorted(users, key=lambda u: (u["name"] or u["username"]).lower()),
            "skills": sorted(({"skill": tags.get(k, k), "people": v} for k, v in counts.items()), key=lambda s: s["skill"].lower()),
            "without": sum(1 for u in users if not u["skills"]), "me": user.username.lower()}
