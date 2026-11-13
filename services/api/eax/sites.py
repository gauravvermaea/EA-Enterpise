"""Sites (R2.1, D646; owner, 13 Nov 2026): one list of EA Explorer sites (installations) that everyone signed in sees in
the site picker at the top left, kept in the farm schema (EAX_FARM_DB_URL, D630).

* This site is a row of its own (Local), made the first time the list is read.
* Choosing a site opens its own screens in a new tab: the person signs in there and works with the role they have there
  (owner: "log into it, then manage that site as per the permissions they have"). Nothing is carried over.
* Only Super Admins add, change or remove a site. A site deployed from the Deploy page (Sites › Deploy EA Explorer) is
  added when its deployment finishes, at https://<the address people open>.
* Each row has a simple health, green, amber or red (owner, 11:24: "a simple health red ambre green can be added to each
  site"), from the site's public heartbeat, looked at every 5 minutes: green when it answers ok, amber when it warns or
  is in maintenance, red when its database is down or it does not answer.
Each person's own list of remote instances (R2.2, D634) stays beside it in the personal data service.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.request

from sqlalchemy import text

from . import databases
from .metamodel_edit import EditError

FIELDS = ("guid AS id, name, url, note, source, deployment, health, health_detail, version, checked_at, created_by, "
          "created_at, modified_at")
_URL = re.compile(r"^https?://[^\s/]+[^\s]*$")


def _db(conn):
    return databases.on("farm", conn)


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in _db(conn).execute(text(sql), p).mappings().all()]


def local_url() -> str:
    from .config import get_settings
    return get_settings().public_base_url.rstrip("/")


def ensure_local(conn) -> None:
    if not _rows(conn, "SELECT id FROM farm.sites WHERE source = 'local'"):
        _db(conn).execute(text("""INSERT INTO farm.sites (name, url, source, note) VALUES ('Local', :u, 'local', 'This site')
                                   ON CONFLICT DO NOTHING"""), {"u": local_url()})


def listing(conn) -> list[dict]:
    ensure_local(conn)
    return _rows(conn, f"SELECT {FIELDS} FROM farm.sites ORDER BY source <> 'local', lower(name)")


def _need_super(user) -> None:
    if "super-admin" not in (getattr(user, "roles", ()) or ()):
        raise EditError("Only a Super Admin adds, changes or removes a site.", 403)


def _clean(d: dict, partial: bool = False) -> dict:
    out = {}
    if not partial or "name" in d:
        name = str(d.get("name") or "").strip()
        if not name or len(name) > 120:
            raise EditError("Give the site a name (up to 120 characters).")
        out["name"] = name
    if not partial or "url" in d:
        url = str(d.get("url") or "").strip().rstrip("/")
        if not _URL.match(url) or len(url) > 500:
            raise EditError("The address is the site's web address, for example https://ea.example.com.")
        out["url"] = url
    if "note" in d:
        out["note"] = str(d.get("note") or "")[:2000]
    return out


def _one(conn, ident) -> dict:
    r = _rows(conn, f"SELECT {FIELDS} FROM farm.sites WHERE guid = CAST(:g AS uuid)", g=str(ident))
    if not r:
        raise EditError("No such site.", 404)
    return r[0]


def create(conn, user, d: dict, source: str = "added", deployment: str | None = None) -> dict:
    if source == "added":
        _need_super(user)
    v = _clean(d)
    if _rows(conn, "SELECT 1 AS x FROM farm.sites WHERE lower(name) = lower(:n) OR lower(url) = lower(:u)", n=v["name"], u=v["url"]):
        raise EditError(f"There is already a site called {v['name']} or at {v['url']}.", 409)
    g = _db(conn).execute(text("""INSERT INTO farm.sites (name, url, note, source, deployment, created_by)
                                   VALUES (:name, :url, :note, :source, :dep, :by) RETURNING guid"""),
                          {"name": v["name"], "url": v["url"], "note": v.get("note", ""), "source": source,
                           "dep": deployment, "by": getattr(user, "username", None) or "system"}).scalar_one()
    return _one(conn, g)


def update(conn, user, ident, d: dict) -> dict:
    _need_super(user)
    cur = _one(conn, ident)
    v = _clean(d, partial=True)
    if cur["source"] == "local":
        v.pop("url", None)                     # this site's own address comes from its settings
    if v:
        sets = ", ".join(f"{k} = :{k}" for k in v)
        _db(conn).execute(text(f"UPDATE farm.sites SET {sets}, modified_at = now() WHERE guid = CAST(:g AS uuid)"),
                          {**v, "g": str(ident)})
    return _one(conn, ident)


def delete(conn, user, ident) -> dict:
    _need_super(user)
    cur = _one(conn, ident)
    if cur["source"] == "local":
        raise EditError("This site (Local) stays in the list.", 409)
    _db(conn).execute(text("DELETE FROM farm.sites WHERE guid = CAST(:g AS uuid)"), {"g": str(ident)})
    return {"deleted": str(cur["id"])}


def from_deployments(conn, deployments: list[dict]) -> int:
    """Every deployment that finished (done, not a plan) and says the address people open: its site added once."""
    n = 0
    for r in deployments:
        target = str(r.get("target") or "")
        if r.get("plan") or r.get("status") != "done" or "." not in target or ":" in target or "@" in target:
            continue
        url = f"https://{target}"
        if _rows(conn, "SELECT 1 AS x FROM farm.sites WHERE lower(url) = lower(:u) OR deployment = :d", u=url,
                 d=str(r.get("run_id") or "")):
            continue
        name = target.split(".")[0] or target
        if _rows(conn, "SELECT 1 AS x FROM farm.sites WHERE lower(name) = lower(:n)", n=name):
            name = target
        create(conn, None, {"name": name, "url": url, "note": f"Deployed by {r.get('started_by') or '?'}"}, "deployed",
               str(r.get("run_id") or ""))
        n += 1
    return n


def health_of(beat: dict | None) -> tuple[str, str, str]:
    """green, amber or red, the reason and the version, from a site's heartbeat (None: it did not answer)."""
    if beat is None:
        return "red", "does not answer", ""
    version = str((beat.get("database") or {}).get("version") or beat.get("version") or "")
    status = str(beat.get("status") or "")
    if beat.get("maintenance"):
        return "amber", "in maintenance", version
    if status == "ok":
        return "green", "working", version
    if status == "warning":
        return "amber", "working, with warnings", version
    return "red", f"not working ({status or 'no status'})", version


def fetch_heartbeat(url: str, timeout: int = 10) -> dict | None:
    """A site's public heartbeat. Its certificate is not checked: a laptop's own certificate is not trusted here, and
    nothing is sent; only the public state is read."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/v1/heartbeat", timeout=timeout, context=ctx) as r:  # noqa: S310
            return json.loads(r.read() or b"{}")
    except Exception:  # noqa: BLE001 - unreachable, refused, not EA Explorer: red
        return None


def check_all(conn, fetch=fetch_heartbeat) -> int:
    """Every site's health now (the job, every 5 minutes). This site is read through its own API inside Docker."""
    import os
    ensure_local(conn)
    n = 0
    for s in _rows(conn, "SELECT guid, url, source FROM farm.sites"):
        url = os.environ.get("EAX_API_URL", "http://api:8000") if s["source"] == "local" else s["url"]
        h, why, version = health_of(fetch(url))
        _db(conn).execute(text("""UPDATE farm.sites SET health = :h, health_detail = :w, version = CASE WHEN :v = '' THEN version
                                   ELSE :v END, checked_at = now() WHERE guid = :g"""),
                          {"h": h, "w": why, "v": version, "g": s["guid"]})
        n += 1
    return n
