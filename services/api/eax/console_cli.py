"""The EA Explorer console, the parts that need the application (phase 13.5, owner 8 Nov 2026, D330).

The console (`eax console`) is for getting a system that is down back up, by someone who need not be technical: a
numbered menu, plain words, and YES typed before anything that changes or replaces data. Most of it runs in the
operations helper (services/ops/console.py: containers, backups, passwords, users); these parts need the application's
own code and database, so they run in the api container:

  python -m eax.console_cli settings     settings and switches: Projects, Repository, References, the system settings
  python -m eax.console_cli tasks        background tasks of everyone, the job queue; cancel a queued one
  python -m eax.console_cli health       every service's health, measure data quality now, the audit trail
  python -m eax.console_cli remote --server https://host [--insecure]
                                         the console against another installation through its API: sign in with
                                         Keycloak (a code shown here, typed in a browser), with your own roles

On the machine itself nobody signs in (being on it is the trust, as for every eax command); what is done is written to
the audit trail as "console (on the machine)".
"""

from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

WHO = "console"
SOURCE = "console (on the machine)"


# ---------------------------------------------------------------- plain console helpers
def say(text: str = "") -> None:
    print(text, flush=True)


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def choose(title: str, items: list[str]) -> int | None:
    """A numbered list; the index chosen, or None for back."""
    say("")
    say(title)
    for i, it in enumerate(items, 1):
        say(f" {i:>2}  {it}")
    say("  b  Back")
    while True:
        a = ask("Choose: ").lower()
        if a in ("b", "q", ""):
            return None
        if a.isdigit() and 1 <= int(a) <= len(items):
            return int(a) - 1
        say("  Type one of the numbers, or b to go back.")


def confirm(what: str) -> bool:
    say(f"\n{what}")
    return ask("Type YES to go ahead (anything else stops): ") == "YES"


def pause() -> None:
    ask("\nPress Enter to go back to the menu ")


def table(rows: list[dict], cols: list[tuple[str, str, int]]) -> None:
    if not rows:
        say("  (none)")
        return
    say("  " + "  ".join(f"{h:<{w}}" for _k, h, w in cols))
    for r in rows:
        say("  " + "  ".join(f"{str(r.get(k) if r.get(k) is not None else ''):<{w}.{w}}" for k, _h, w in cols))


# ---------------------------------------------------------------- on the machine: the application's own code
def _console_user():
    from . import permissions as perms
    from .auth import User
    perms.current.set(perms.Principal(WHO, (perms.SUPER_ADMIN,)))
    return User(username=WHO, name="Console on the machine", roles=[perms.SUPER_ADMIN])


def _audit(conn, action: str, object_type: str = "", object_id: str = "", details: dict | None = None) -> None:
    from . import audit
    try:
        audit.record(conn, actor=WHO, action=action, object_type=object_type, object_id=object_id, source=SOURCE,
                     details=details or {})
    except TypeError:          # an older record() without details
        audit.record(conn, actor=WHO, action=action, object_type=object_type, object_id=object_id, source=SOURCE)


def local_settings() -> int:
    from . import settings as st
    from .db import get_engine
    user = _console_user()
    while True:
        with get_engine().connect() as conn:
            d = st.describe(conn)
        rows = d["system"]
        parts = d["parts"]
        say("\nSettings and switches (System admin > System settings)")
        say("  Parts: " + ", ".join(f"{k.title()} {'on' if v else 'OFF'}" for k, v in parts.items()))
        items = []
        for s in rows:
            v = s["value"]
            shown = ("on" if v else "off") if s["type"] == "bool" else v
            if s["key"].startswith("part_") and v and not parts[s["key"][5:]]:
                shown = "on, but off while Projects is off"
            items.append(f"{s['label']:<34} {shown}")
        i = choose("Choose one to change:", items)
        if i is None:
            return 0
        s = rows[i]
        say(f"\n{s['label']}: {s['help']}")
        if s["type"] == "bool":
            new: Any = not s["value"]
            if not confirm(f"Switch {s['label']} {'on' if new else 'off'}?"
                           + (" Its data is kept; its screens, menus and API go until it is on again." if not new and s["key"].startswith("part_") else "")):
                continue
        else:
            hint = f" (one of: {', '.join(map(str, s['choices']))})" if s.get("choices") else \
                f" ({s['range'][0]} to {s['range'][1]})" if s.get("range") else ""
            new = ask(f"New value{hint}, Enter to keep {s['value']}: ")
            if not new:
                continue
            if not confirm(f"Change {s['label']} from {s['value']} to {new}?"):
                continue
        try:
            with get_engine().begin() as conn:
                out = st.update(conn, user, {s["key"]: new})
                _audit(conn, "settings.change", "settings", "", {"changed": {s["key"]: new}})
            say("  " + out["note"])
        except Exception as exc:  # noqa: BLE001 - said plainly; the menu goes on
            say(f"  Not changed: {exc}")


def local_tasks() -> int:
    from sqlalchemy import text

    from .db import get_engine
    _console_user()
    while True:
        with get_engine().connect() as conn:
            rows = [dict(r) for r in conn.execute(text("""
                SELECT t.id, t.status, t.kind, left(t.label, 40) AS label, t.requested_by AS who,
                       to_char(t.requested_at, 'YYYY-MM-DD HH24:MI') AS asked, t.job_id
                  FROM core.tasks t WHERE t.status IN ('queued', 'running') ORDER BY t.requested_at LIMIT 40""")).mappings()]
            q = {}
            if conn.execute(text("SELECT to_regclass('jobs.procrastinate_jobs')")).scalar():
                q = {r["status"]: r["n"] for r in conn.execute(text(
                    "SELECT status::text AS status, count(*) AS n FROM jobs.procrastinate_jobs GROUP BY 1")).mappings()}
        say("\nBackground tasks waiting or running (everyone's)")
        table(rows, [("id", "Id", 6), ("status", "Status", 8), ("label", "What", 40), ("who", "Asked by", 16), ("asked", "When", 16)])
        say("  Job queue: " + (", ".join(f"{k} {v}" for k, v in sorted(q.items())) or "empty"))
        i = choose("What now?", ["Look again", "Cancel a queued task", "Cancel every queued task"])
        if i is None:
            return 0
        if i == 0:
            continue
        queued = [r for r in rows if r["status"] == "queued"]
        if not queued:
            say("  Nothing is queued (a running task cannot be stopped from here: it finishes, or restart the API).")
            continue
        if i == 1:
            n = ask("The task's id: ")
            pick = [r for r in queued if str(r["id"]) == n]
            if not pick:
                say("  No queued task with that id.")
                continue
        else:
            pick = queued
        if not confirm(f"Cancel {len(pick)} queued task(s)? The people who asked see them as failed (cancelled from the console)."):
            continue
        with get_engine().begin() as conn:
            for r in pick:
                if r["job_id"]:
                    conn.execute(text("UPDATE jobs.procrastinate_jobs SET status = 'cancelled' WHERE id = :j AND status = 'todo'"),
                                 {"j": r["job_id"]})
                conn.execute(text("""UPDATE core.tasks SET status = 'failed', message = 'Cancelled from the console on the machine.',
                                            finished_at = now() WHERE id = :i AND status = 'queued'"""), {"i": r["id"]})
            _audit(conn, "tasks.cancel", "task", ",".join(str(r["id"]) for r in pick))
        say(f"  {len(pick)} cancelled.")


def local_health() -> int:
    from sqlalchemy import text

    from . import health
    from .db import get_engine
    user = _console_user()
    while True:
        i = choose("Health and data quality", ["Every service's health now", "Measure the data quality of every model now",
                                               "The audit trail: the last 30 things done"])
        if i is None:
            return 0
        if i == 0:
            h = health.check_all()
            say(f"\nOverall: {h['status'].upper()}  ({', '.join(f'{k} {v}' for k, v in h['counts'].items() if v)})")
            table(h["services"], [("name", "Service", 22), ("status", "Status", 8), ("detail", "What it says", 60)])
            down = [s for s in h["services"] if s["status"] == "down"]
            if down:
                say("\n  Something is down: choose 3 (Restart) in the main menu, or 5 (Show problems) to see why.")
        elif i == 1:
            from . import quality as q
            with get_engine().begin() as conn:
                reqs = [q.request_run(conn, m["id"], user) for m in q.installation(conn, user)["models"]]
            new = [r for r in reqs if r.get("new")]
            try:
                from .jobs import app as jobs_app
                from .jobs import quality_measure
                with jobs_app.open():
                    for r in new:
                        quality_measure.defer(request_id=r["id"])
                say(f"  {len(new)} measurements queued ({len(reqs) - len(new)} already running); see Health > Quality in the screens.")
            except Exception as exc:  # noqa: BLE001
                say(f"  Asked, but the job runner could not be reached ({exc}): they run when it is back.")
        else:
            with get_engine().connect() as conn:
                rows = [dict(r) for r in conn.execute(text("""
                    SELECT to_char(at, 'YYYY-MM-DD HH24:MI') AS at, actor, action, coalesce(object_type, '') || ' ' ||
                           coalesce(left(object_id, 30), '') AS what, source FROM audit.events ORDER BY id DESC LIMIT 30""")).mappings()]
            table(rows, [("at", "When", 16), ("actor", "Who", 18), ("action", "Did", 26), ("what", "To", 34), ("source", "From", 14)])
        pause()


# ---------------------------------------------------------------- against another installation, through its API
class Remote:
    """The API of an installation, signed in with Keycloak's device sign-in (client eax-console): the person's own roles."""

    def __init__(self, server: str, realm: str = "eaexplorer", insecure: bool = False):
        self.server = server.rstrip("/")
        self.realm = realm
        self.ctx = ssl._create_unverified_context() if insecure else None  # noqa: S323 - asked for: a laptop's own certificate
        self.token = ""

    def _call(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None) -> Any:
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=30, context=self.ctx) as r:
                body = r.read()
        except urllib.error.HTTPError as exc:
            try:
                msg = json.loads(exc.read()).get("message") or exc.reason
            except ValueError:
                msg = exc.reason
            raise RuntimeError(f"{exc.code}: {msg}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{self.server} does not answer: {exc.reason}") from exc
        return json.loads(body) if body else {}

    def sign_in(self) -> str:
        base = f"{self.server}/auth/realms/{self.realm}/protocol/openid-connect"
        form = lambda d: urllib.parse.urlencode(d).encode()  # noqa: E731
        hdr = {"Content-Type": "application/x-www-form-urlencoded"}
        d = self._call("POST", f"{base}/auth/device", form({"client_id": "eax-console", "scope": "openid"}), hdr)
        say(f"\nSign in: open {d.get('verification_uri_complete') or d['verification_uri']}")
        say(f"in a browser and check the code {d['user_code']}. Waiting...")
        until = time.time() + int(d.get("expires_in", 600))
        while time.time() < until:
            time.sleep(int(d.get("interval", 5)))
            try:
                t = self._call("POST", f"{base}/token", form({"client_id": "eax-console", "device_code": d["device_code"],
                                                               "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}), hdr)
            except RuntimeError as exc:
                if "authorization_pending" in str(exc) or "slow_down" in str(exc) or str(exc).startswith("400"):
                    continue
                raise
            self.token = t["access_token"]
            me = self.get("/api/v1/me")
            return f"{me.get('username')} ({', '.join(me.get('roles') or []) or 'no role'})"
        raise RuntimeError("The sign-in was not finished in time.")

    def _api(self, method: str, path: str, body: Any = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        return self._call(method, self.server + path, data, {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})

    def get(self, path: str) -> Any:
        return self._api("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self._api("POST", path, body if body is not None else {})

    def put(self, path: str, body: Any) -> Any:
        return self._api("PUT", path, body)


REMOTE_MENU = ["Status: every service's health", "Restart everything / one service", "Show problems: what is not running",
               "Back up now (infrastructure / application)", "Restore a backup (guided)", "Users and roles (read only)",
               "Settings and switches", "Background tasks (yours) and job servers", "Data quality now, the audit trail"]


def remote(server: str, realm: str, insecure: bool) -> int:
    r = Remote(server, realm, insecure)
    say(f"EA Explorer console, through the API of {r.server}")
    try:
        who = r.sign_in()
    except RuntimeError as exc:
        say(f"Could not sign in: {exc}")
        say("When the installation is down, run the console on its machine instead: .\\eax console (no sign-in there).")
        return 1
    say(f"Signed in as {who}. Everything is done with your own roles (IT Admin or Super Admin for most of it).")
    while True:
        i = choose(f"EA Explorer console ({r.server})", REMOTE_MENU + ["Quit"])
        if i is None or i == len(REMOTE_MENU):
            return 0
        try:
            _remote_item(r, i)
        except RuntimeError as exc:
            say(f"  Not done: {exc}")
        pause()


def _remote_item(r: Remote, i: int) -> None:  # noqa: C901 - one branch per menu item, kept together to read
    if i == 0:
        h = r.get("/api/v1/admin/services/health")
        say(f"\nOverall: {str(h.get('status', '?')).upper()}")
        table(h.get("services") or [], [("name", "Service", 22), ("status", "Status", 8), ("detail", "What it says", 60)])
    elif i == 1:
        cs = r.get("/api/v1/admin/containers").get("containers") or []
        names = sorted({c.get("service") for c in cs if c.get("service")})
        j = choose("Restart what?", ["Everything"] + names)
        if j is None:
            return
        svc = None if j == 0 else names[j - 1]
        if confirm(f"Restart {svc or 'everything'}? People are signed out of what restarts for a minute or two."):
            say("  " + str(r.post("/api/v1/admin/restart", {"service": svc} if svc else {}).get("message", "Asked.")))
    elif i == 2:
        cs = r.get("/api/v1/admin/containers").get("containers") or []
        bad = [c for c in cs if c.get("state") != "running" or "unhealthy" in str(c.get("status", ""))]
        table(bad or [], [("service", "Service", 18), ("state", "State", 10), ("status", "Docker says", 40)])
        for c in bad[:5]:
            try:
                logs = r.get(f"/api/v1/admin/containers/{urllib.parse.quote(c['service'])}/logs?tail=15").get("logs", "")
                say(f"\n-- {c['service']}: its last lines --\n{logs}")
            except RuntimeError:
                pass
    elif i == 3:
        j = choose("Back up what?", ["Infrastructure: every database, the documents, the config file",
                                     "Application: every model"])
        if j is None:
            return
        tag = ask("A tag for it (Enter for on-demand): ") or "on-demand"
        path = "/api/v1/admin/backups/infrastructure" if j == 0 else "/api/v1/admin/backups/application"
        say("  " + str(r.post(path, {"tag": tag}).get("message", "Started.")))
    elif i == 4:
        b = r.get("/api/v1/admin/backups")
        infra = [x for x in (b.get("infrastructure") or []) if x.get("status") == "ok"][:15]
        j = choose("Restore which infrastructure backup? (newest first)",
                   [f"{x.get('name')}  tag {x.get('tag') or '-'}  by {x.get('by') or '?'}" for x in infra])
        if j is None:
            return
        whats = ["full", "app", "app+data", "db", "files"]
        k = choose("What to restore?", ["full: everything", "app: the config file", "app+data: config, databases, documents",
                                        "db: every database", "files: the documents and the certificate"])
        if k is None:
            return
        if confirm(f"Restore {whats[k]} from {infra[j]['name']}? What is there now is backed up first, then replaced; "
                   "everyone is told and signed out."):
            say("  " + str(r.post(f"/api/v1/admin/backups/infrastructure/{urllib.parse.quote(infra[j]['name'])}/restore",
                                  {"what": whats[k]}).get("message", "Started: follow it with Status.")))
    elif i == 5:
        people = r.get("/api/v1/people")
        rows = people if isinstance(people, list) else people.get("people", [])
        table([{**p, "roles": ", ".join(p.get("roles") or [])} for p in rows],
              [("username", "User", 20), ("name", "Name", 24), ("roles", "Roles", 50)])
        say("\n  Roles are given in Keycloak. To reset a password or change roles when you cannot reach Keycloak's screens,"
            " use the console on the machine: .\\eax console, 8 or 9.")
    elif i == 6:
        d = r.get("/api/v1/admin/settings")
        rows = d.get("system") or []
        j = choose("Change which?", [f"{s['label']:<34} {('on' if s['value'] else 'off') if s['type'] == 'bool' else s['value']}" for s in rows])
        if j is None:
            return
        s = rows[j]
        new: Any = (not s["value"]) if s["type"] == "bool" else ask(f"New value for {s['label']}: ")
        if new != "" and confirm(f"Set {s['label']} to {new}?"):
            say("  " + str(r.put("/api/v1/admin/settings", {s["key"]: new}).get("note", "Saved.")))
    elif i == 7:
        t = r.get("/api/v1/tasks?active=true")
        rows = t.get("tasks", t if isinstance(t, list) else [])
        table(rows, [("status", "Status", 8), ("label", "What", 50), ("message", "Says", 40)])
        s = r.get("/api/v1/admin/servers")
        say(f"\n  API and job servers: {s.get('wanted', '?')} wanted, {len(s.get('servers') or [])} running.")
    elif i == 8:
        j = choose("Which?", ["Measure the data quality of every model now", "The audit trail: the last 30 things done"])
        if j == 0:
            out = r.post("/api/v1/quality/run")
            say(f"  {len(out.get('requests') or [])} measurements asked for.")
        elif j == 1:
            rows = r.get("/api/v1/audit?limit=30")
            table(rows, [("at", "When", 20), ("actor", "Who", 18), ("action", "Did", 28), ("object_id", "To", 30)])


# ---------------------------------------------------------------- the command line
def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "help"
    try:
        if cmd == "settings":
            return local_settings()
        if cmd == "tasks":
            return local_tasks()
        if cmd == "health":
            return local_health()
        if cmd == "remote":
            args = argv[1:]
            server = args[args.index("--server") + 1] if "--server" in args else ""
            realm = args[args.index("--realm") + 1] if "--realm" in args else "eaexplorer"
            if not server:
                say("Usage: remote --server https://host [--realm eaexplorer] [--insecure]")
                return 2
            return remote(server, realm, "--insecure" in args)
    except KeyboardInterrupt:
        say("\nStopped.")
        return 130
    say(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
