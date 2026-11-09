"""The EA Explorer console (phase 13.5, owner 8 Nov 2026, D330): `.\\eax console` / `./eax.sh console`.

For getting a system that is down back up, by someone who need not be technical: a numbered menu, plain words, and
YES typed before anything that changes or replaces data. It runs in the operations helper (this container reaches
Docker and the work folder), started by the eax command on the machine itself: being on the machine is the trust, so
nobody signs in (the same as every eax command). What it does is written to work/logs/console-<date>.log.

The eax command runs it in a loop; a few items need the machine itself and are handed back by exit code:
  20 start everything (eax up)   21 stop everything (eax down)   23 save a diagnostics file (eax diag)
  25 the command prompt (any eax command)   0 quit
The parts that need the application's code (settings, background tasks, health and data quality) run in the api
container: python -m eax.console_cli.
"""

from __future__ import annotations

import json
import os
import secrets
import string
import subprocess
import sys
import time

import ops

START, STOP, DIAG, PROMPT = 20, 21, 23, 25
LOG = os.path.join(ops.WORK, "logs", f"console-{time.strftime('%Y%m%d', time.gmtime())}.log")
DB_ROLES = {    # service password -> its login in PostgreSQL
    "EAX_DB_SUPERUSER_PASSWORD": ("postgres", "the database's administrator"),
    "EAX_DB_PASSWORD": ("eax_app", "EA Explorer's own login"),
    "EAX_DB_REPORT_PASSWORD": ("eax_report", "the reports' read-only login"),
    "EAX_DB_MIGRATOR_PASSWORD": ("eax_migrator", "the installer's login"),
    "EAX_KEYCLOAK_DB_PASSWORD": ("keycloak", "Keycloak's database login"),
    "EAX_SUPERSET_DB_PASSWORD": ("superset", "Reports' (Superset) database login"),
    "EAX_MAYAN_DB_PASSWORD": ("mayan", "Documents' (Mayan) database login"),
    "EAX_LIBRARY_DB_PASSWORD": ("eax_library", "The library's database login"),
}
MENU = [
    "Status: what is running, what is not",
    "Start everything",
    "Restart everything / one service",
    "Stop everything",
    "Show problems and recent errors (logs)",
    "Back up now (infrastructure / application)",
    "Restore a backup (guided)",
    "Reset a password (a person, Keycloak admin, break-glass, service passwords)",
    "Users and roles",
    "Settings and switches (Projects, Repository, References, optional services)",
    "Background tasks and job servers",
    "Health and data quality, audit trail",
    "Maintenance mode on / off",
    "Save a diagnostics file for support",
]


# ---------------------------------------------------------------- plain helpers
def say(text: str = "") -> None:
    print(text, flush=True)


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def note(what: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}Z  {what}\n")
    except OSError:
        pass


def choose(title: str, items: list[str]) -> int | None:
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


def new_password() -> str:
    """A long password of letters and digits (safe in the config file, in Compose and in URLs)."""
    a = string.ascii_letters + string.digits
    return "".join(secrets.choice(a) for _ in range(24))


def password_from_person(what: str) -> str | None:
    i = choose(f"The new {what}:", ["Make one for me (24 letters and digits; recommended)", "I will type it"])
    if i is None:
        return None
    if i == 0:
        return new_password()
    pw = ask("Type it (at least 12 characters, no spaces, no quotes, no $): ")
    if len(pw) < 12 or any(c in pw for c in " '\"$`\\"):
        say("  Not taken: at least 12 characters, and none of: space ' \" $ ` \\")
        return None
    return pw


def running(service: str) -> dict | None:
    c = ops._container(service)
    return c if c and c["state"] == "running" else None


def need(service: str, why: str) -> dict | None:
    """The container of a service, started when it is stopped; None (said why) when there is none."""
    c = ops._container(service)
    if not c:
        say(f"  There is no {service} container yet: choose 2 (Start everything) first.")
        return None
    if c["state"] != "running":
        say(f"  {service} is not running: starting it ({why})...")
        try:
            ops.docker("start", c["id"], timeout=180)
            time.sleep(8 if service != "keycloak" else 30)
        except RuntimeError as exc:
            say(f"  It did not start: {exc}. Choose 5 (Show problems) to see why.")
            return None
    return ops._container(service)


def interactive(cid: str, *cmd: str, env: dict | None = None) -> int:
    """A command in a container with this console attached (it can ask and show progress)."""
    args = ["docker", "exec", "-it"]
    for k, v in (env or {}).items():
        args += ["-e", f"{k}={v}"]
    return subprocess.run([*args, cid, *cmd], check=False).returncode


def config() -> dict[str, str]:
    return ops._values(ops._read_config())


def set_config(key: str, value: str, why: str) -> str:
    """Writes one value into the config file, a dated copy first (work/config-history)."""
    with ops.config_lock:
        name = ops.copy_config("console", why)
        lines, done = ops._read_config(), False
        out = []
        for line in lines:
            if line.strip().startswith(f"{key}=") or line.replace(" ", "").startswith(f"{key}="):
                out.append(f"{key}={value}")
                done = True
            else:
                out.append(line)
        if not done:
            out += [f"{key}={value}"]
        ops._write(out)
    note(f"config: {key} changed ({why}); copy {name}")
    return name


# ---------------------------------------------------------------- 1 status, 3 restart, 5 problems
def status() -> None:
    rows = ops.containers()
    if not rows:
        say("\nNothing is set up yet: choose 2 (Start everything).")
        return
    say(f"\n  {'Service':<18}{'State':<12}What Docker says")
    for c in rows:
        mark = "OK " if c["state"] == "running" and "unhealthy" not in c["status"] else "-- " if c["state"] == "exited" else "!! "
        say(f"{mark}{c['key']:<18}{c['state']:<12}{c['status']}")
    bad = [c for c in rows if (c["state"] != "running" and c["service"] not in ("setup", "reports-init"))
           or "unhealthy" in c["status"]]
    say("")
    say("Everything is running." if not bad else
        f"{len(bad)} not running or unhealthy: {', '.join(c['key'] for c in bad)}. Choose 3 (Restart) or 5 (Show problems).")
    m = ops.maintenance()
    if m or os.path.exists(ops.PROXY_FLAG):
        say("The maintenance page is on: people cannot use EA Explorer until it is off (13).")
    try:
        for f in ops.filesystems():
            if f.get("level") == "red" and not f.get("same_as"):
                say(f"Disk almost full: {f['label']} has {f['free_bytes'] / 1e9:.1f} GB free. Delete old backups or free space.")
    except Exception as exc:  # noqa: BLE001 - the disk check is a help only
        note(f"disk check: {exc}")


def restart() -> None:
    names = sorted({c["service"] for c in ops.containers() if c["state"] == "running" and not c["self"]})
    i = choose("Restart what?", ["Everything (one after the other, the database first)"] + names)
    if i is None:
        return
    svc = None if i == 0 else [names[i - 1]]
    if not confirm(f"Restart {'everything' if svc is None else svc[0]}? People are signed out of what restarts for a minute or two."):
        return
    note(f"restart {svc or 'everything'}")
    stopped = [c for c in ops.containers() if c["state"] != "running" and not c["self"]
               and c["service"] not in ("setup", "reports-init") and (svc is None or c["service"] in svc)]
    for c in stopped:      # what had stopped is started too
        try:
            ops.docker("start", c["id"], timeout=180)
            say(f"  started {c['key']}")
        except RuntimeError as exc:
            say(f"  {c['key']} did not start: {exc}")
    ops._restart(svc)
    for line in ops.state["log"]:
        say("  " + line)
    say("Done. Choose 1 (Status) in a minute to see that everything is up.")


def problems() -> None:
    rows = [c for c in ops.containers() if ((c["state"] != "running" and c["service"] not in ("setup", "reports-init"))
                                            or "unhealthy" in c["status"])]
    for c in ops.containers():
        if c["service"] in ("setup", "reports-init") and c["state"] == "exited" and not ops._finished_ok(c["id"]):
            rows.append(c)
    if not rows:
        say("\nEvery service is running and healthy.")
        i = choose("Look at a service's last lines anyway?", [c["key"] for c in ops.containers()])
        if i is not None:
            c = ops.containers()[i]
            say("\n".join(ops.container_logs(c["key"], 40)["lines"]))
        return
    for c in rows:
        say(f"\n== {c['key']}: {c['state']}, {c['status']} ==")
        try:
            lines = ops.container_logs(c["key"], 25)["lines"]
            errs = [x for x in lines if any(w in x.lower() for w in ("error", "fatal", "exception", "refused", "denied"))]
            say("\n".join(errs[-10:] or lines[-12:]))
        except Exception as exc:  # noqa: BLE001
            say(f"  (its log could not be read: {exc})")
    say("\nWhat usually helps: 3 (Restart) that service; if it keeps stopping, 14 (Save a diagnostics file) and send it.")


# ---------------------------------------------------------------- 6 back up, 7 restore
def back_up(version: str) -> None:
    i = choose("Back up what?", [("Infrastructure: every database, the documents, the certificate and the config file "
                                  "(what you need to rebuild the machine)"), "Application: every model, one file each"])
    if i is None:
        return
    tag = ask("A tag to find it by (Enter for on-demand): ") or "on-demand"
    note(f"backup {'infrastructure' if i == 0 else 'application'} {tag}")
    if i == 0:
        if not need("db", "the backup reads the databases") or not need("backup", "it makes the backup"):
            return
        m = ops._do_backup(tag, "console", "on-demand", version)
        say(f"\nBackup {m.get('name')}: {m.get('status')}. {m.get('error') or ''}")
    else:
        c = need("api", "the application backup runs in it")
        if c:
            interactive(c["id"], "python", "-m", "eax.backups_cli", "backup", tag)


def restore(version: str) -> None:
    i = choose("Restore what?", ["Infrastructure backup (guided: choose the backup, then what to put back)",
                                 "Every model from an application backup", "One model (as a new model or over itself)",
                                 "List the backups", "The restores so far, with their status"])
    if i is None:
        return
    note(f"restore menu {i + 1}")
    if i == 0:
        if not need("db", "the restore needs the database") or not need("backup", "it restores"):
            return
        ops.cli(["restore", "--version", version])
    elif i in (1, 2):
        c = need("api", "it restores models")
        if c:
            interactive(c["id"], "python", "-m", "eax.backups_cli", "restore-all" if i == 1 else "restore")
    elif i == 3:
        ops.cli(["list"])
    else:
        ops.cli(["restores"])


# ---------------------------------------------------------------- 8 passwords, 9 users and roles (Keycloak's own admin tool)
class Kc:
    """Keycloak's admin command (kcadm.sh) in the keycloak container, signed in as Keycloak's administrator."""

    def __init__(self):
        self.c = None
        v = config()
        self.realm = v.get("EAX_KEYCLOAK_REALM", "eaexplorer") or "eaexplorer"
        self.admin = v.get("EAX_KC_ADMIN", "kcadmin") or "kcadmin"
        self.password = v.get("EAX_KC_ADMIN_PASSWORD", "")

    def start(self, user: str = "", password: str = "") -> bool:
        self.c = need("keycloak", "passwords and roles are kept there")
        if not self.c:
            return False
        for _ in range(12):
            r = self.run("config", "credentials", "--server", "http://localhost:8080/auth", "--realm", "master",
                         "--user", user or self.admin, "--password", "$KCPW", pw=password or self.password, quiet=True)
            if r.returncode == 0:
                return True
            if "Invalid user credentials" in (r.stderr + r.stdout) or "401" in (r.stderr + r.stdout):
                return False
            time.sleep(5)          # Keycloak still starting
        return False

    def run(self, *args: str, pw: str = "", quiet: bool = False) -> subprocess.CompletedProcess:
        cmd = " ".join(f'"{a}"' if a != "$KCPW" else '"$KCPW"' for a in args)
        r = subprocess.run(["docker", "exec", "-e", f"KCPW={pw}", self.c["id"], "bash", "-c",
                            f"/opt/keycloak/bin/kcadm.sh {cmd} --config /tmp/eax-console-kcadm.config"],
                           capture_output=True, text=True, timeout=120, check=False)
        if r.returncode and not quiet:
            raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "kcadm failed")
        return r

    def json(self, *args: str) -> list | dict:
        out = self.run(*args).stdout
        return json.loads(out) if out.strip() else []

    def users(self, search: str = "") -> list[dict]:
        args = ["get", "users", "-r", self.realm, "--fields", "id,username,email,enabled,firstName,lastName", "-q", "max=200"]
        if search:
            args += ["-q", f"search={search}"]
        return self.json(*args)

    def roles_of(self, username: str) -> list[str]:
        rows = self.json("get-roles", "-r", self.realm, "--uusername", username)
        return sorted(r["name"] for r in rows if not r["name"].startswith("default-roles-") and r["name"] not in ("offline_access", "uma_authorization"))

    def realm_roles(self) -> list[str]:
        return sorted(r["name"] for r in self.json("get", "roles", "-r", self.realm, "--fields", "name")
                      if not r["name"].startswith("default-roles-") and r["name"] not in ("offline_access", "uma_authorization"))


def _pick_user(kc: Kc) -> dict | None:
    s = ask("Part of the user's name or email (Enter for everyone): ")
    rows = kc.users(s)
    if not rows:
        say("  Nobody found.")
        return None
    i = choose("Which person?", [f"{u['username']:<24} {u.get('email') or '':<32} {'' if u.get('enabled', True) else '(disabled)'}"
                                 for u in rows[:40]])
    return None if i is None else rows[i]


def passwords() -> int:
    i = choose("Reset which password?", ["A person's sign-in (a temporary one: they choose their own at the next sign-in)",
                                         "Keycloak's administrator", "The break-glass account (signs in when Keycloak is down)",
                                         "A service password (the databases' logins)"])
    if i is None:
        return 0
    if i == 0:
        kc = Kc()
        if not kc.start():
            say("  Keycloak did not accept its administrator's password from the config file: reset that first (2 in this list).")
            return 0
        u = _pick_user(kc)
        if not u:
            return 0
        pw = password_from_person(f"temporary password for {u['username']}")
        if not pw or not confirm(f"Give {u['username']} this temporary password? They must change it when they sign in."):
            return 0
        kc.run("set-password", "-r", kc.realm, "--username", u["username"], "--new-password", "$KCPW", "--temporary", pw=pw)
        if not u.get("enabled", True):
            kc.run("update", f"users/{u['id']}", "-r", kc.realm, "-s", "enabled=true")
        note(f"password: temporary password set for {u['username']}")
        say(f"\n  Done. {u['username']} signs in with:  {pw}\n  (shown once: tell them in person or by phone, not by email)")
    elif i == 1:
        kc = Kc()
        ok = kc.start()
        tmp_user = ""
        if not ok:
            say("  The password in the config file does not work any more: a temporary administrator is made to reset it.")
            tmp_user, tmp_pw = f"eax-console-{secrets.token_hex(3)}", new_password()
            if not _bootstrap_admin(tmp_user, tmp_pw) or not kc.start(tmp_user, tmp_pw):
                say("  It could not be made: choose 5 (Show problems) and look at keycloak.")
                return 0
        pw = password_from_person(f"password of Keycloak's administrator ({kc.admin})")
        if not pw or not confirm(f"Set the password of {kc.admin} and write it into the config file (a dated copy first)?"):
            return 0
        kc.run("set-password", "-r", "master", "--username", kc.admin, "--new-password", "$KCPW", pw=pw)
        if tmp_user:
            for u in kc.json("get", "users", "-r", "master", "-q", f"username={tmp_user}"):
                kc.run("delete", f"users/{u['id']}", "-r", "master")
        set_config("EAX_KC_ADMIN_PASSWORD", pw, "kc-admin-password")
        note("password: Keycloak administrator")
        say(f"\n  Done. Keycloak's administrator {kc.admin} signs in with:  {pw}\n  It is in the config file (work/eaexplorer.env).")
    elif i == 2:
        pw = password_from_person("break-glass password")
        if not pw or not confirm("Change the break-glass password? Everyone signed in with break-glass is signed out; "
                                 "the API is started again to take it (a minute)."):
            return 0
        set_config("EAX_BREAK_GLASS_PASSWORD", pw, "break-glass-password")
        note("password: break-glass")
        say(f"\n  The break-glass account (user break-glass) signs in with:  {pw}\n  Starting the API again with it...")
        return START
    else:
        keys = list(DB_ROLES)
        j = choose("Which service password?", [f"{DB_ROLES[k][1]} ({k})" for k in keys]
                   + ["Every database login at once"])
        if j is None:
            return 0
        todo = keys if j == len(keys) else [keys[j]]
        if not confirm(f"Change {len(todo)} database password(s)? New ones are made, set in PostgreSQL and written into the "
                       "config file (a dated copy first); then every service is started again to take them (a few minutes)."):
            return 0
        if not need("db", "the logins are in it"):
            return 0
        db = ops._container("db")
        for k in todo:
            role, what = DB_ROLES[k]
            pw = new_password()
            r = subprocess.run(["docker", "exec", "-i", db["id"], "psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1",
                                "-v", f"pw={pw}"], input=f"ALTER ROLE \"{role}\" PASSWORD :'pw';\n", capture_output=True, text=True, check=False)
            if r.returncode:
                say(f"  {what}: not changed ({(r.stderr or r.stdout).strip()[:200]})")
                continue
            set_config(k, pw, f"password-{role}")
            note(f"password: database login {role}")
            say(f"  {what}: changed")
        say("  Starting every service again so they use the new passwords...")
        return START
    return 0


def _bootstrap_admin(user: str, pw: str) -> bool:
    """A temporary Keycloak administrator, made with Keycloak's own bootstrap command in a one-off container beside it."""
    c = ops._container("keycloak")
    d = json.loads(ops.docker("inspect", c["id"]))[0]
    env = [e for e in d["Config"]["Env"] if e.startswith("KC_DB")]
    net = next(iter((d.get("NetworkSettings") or {}).get("Networks") or {}), "")
    args = ["docker", "run", "--rm", "--network", net]
    for e in env + [f"EAX_TMP_USER={user}", f"EAX_TMP_PW={pw}"]:
        args += ["-e", e]
    args += [d["Config"]["Image"], "bootstrap-admin", "user", "--username:env", "EAX_TMP_USER", "--password:env", "EAX_TMP_PW", "--no-prompt"]
    say("  Making a temporary administrator (a minute)...")
    r = subprocess.run(args, capture_output=True, text=True, timeout=600, check=False)
    if r.returncode:
        say("  " + (r.stderr or r.stdout).strip()[-400:])
    return r.returncode == 0


def users() -> None:
    kc = Kc()
    if not kc.start():
        say("  Keycloak did not accept its administrator's password: choose 8 (Reset a password), then 2.")
        return
    while True:
        i = choose("Users and roles (kept in Keycloak; a person's roles on a model are on the model's People tab)",
                   ["List everyone with their roles", "Give someone a role", "Take a role away", "Disable or enable a person",
                    "Add a person"])
        if i is None:
            return
        if i == 0:
            rows = kc.users()
            say(f"\n  {'User':<24}{'Email':<32}Roles")
            for u in rows:
                say(f"  {u['username']:<24}{(u.get('email') or ''):<32}{', '.join(kc.roles_of(u['username']))}"
                    + ("" if u.get("enabled", True) else "  (disabled)"))
            continue
        if i == 4:
            name = ask("User name (letters, digits, dots): ").lower()
            email = ask("Email (Enter for none): ")
            if not name or not confirm(f"Add {name}? Then give them a temporary password (8, 1) and roles (here, 2)."):
                continue
            args = ["create", "users", "-r", kc.realm, "-s", f"username={name}", "-s", "enabled=true"]
            if email:
                args += ["-s", f"email={email}"]
            kc.run(*args)
            note(f"users: added {name}")
            say(f"  {name} added.")
            continue
        u = _pick_user(kc)
        if not u:
            continue
        if i == 3:
            on = not u.get("enabled", True)
            if confirm(f"{'Enable' if on else 'Disable'} {u['username']}?"):
                kc.run("update", f"users/{u['id']}", "-r", kc.realm, "-s", f"enabled={'true' if on else 'false'}")
                note(f"users: {'enabled' if on else 'disabled'} {u['username']}")
                say("  Done.")
            continue
        have = kc.roles_of(u["username"])
        pool = [r for r in kc.realm_roles() if (r not in have if i == 1 else r in have)]
        if not pool:
            say("  Nothing to " + ("give." if i == 1 else "take away."))
            continue
        j = choose(f"{u['username']} has: {', '.join(have) or 'no role'}. Which role?", pool)
        if j is None or not confirm(f"{'Give' if i == 1 else 'Take'} {pool[j]} {'to' if i == 1 else 'from'} {u['username']}?"):
            continue
        kc.run("add-roles" if i == 1 else "remove-roles", "-r", kc.realm, "--uusername", u["username"], "--rolename", pool[j])
        note(f"users: {'gave' if i == 1 else 'took'} {pool[j]} {u['username']}")
        say("  Done: it applies at their next sign-in.")


# ---------------------------------------------------------------- 10 settings, 11 tasks, 12 health (in the api container)
def app_part(area: str) -> None:
    c = running("api")
    if not c:
        say("  The API is not running: choose 2 (Start everything) or 3 (Restart) first.")
        return
    interactive(c["id"], "python", "-m", "eax.console_cli", area)


def settings() -> None:
    i = choose("Settings and switches", ["Projects, Repository, References and the system settings",
                                         "Optional services on or off (reports, documents, draw.io, MCP, change log, backups)"])
    if i == 0:
        app_part("settings")
    elif i == 1:
        sw = ops.switches()
        keys = list(sw)
        j = choose("Switch which?", [f"{k:<12} {'on' if sw[k] else 'off'}" for k in keys])
        if j is None:
            return
        k, on = keys[j], not sw[keys[j]]
        if not confirm(f"Switch {k} {'on' if on else 'off'}? The config file is changed (a dated copy first)."):
            return
        with ops.config_lock:
            ops.copy_config("console", f"service-{k}-{'on' if on else 'off'}")
            ops._write(ops.set_switch(ops._read_config(), k, on))
        note(f"service {k} {'on' if on else 'off'}")
        try:
            for line in ops.apply_switch(k, on):
                say("  " + line)
        except RuntimeError as exc:
            say(f"  Saved; {exc}")


def tasks() -> None:
    i = choose("Background tasks and job servers", ["Background tasks: waiting and running; cancel a queued one",
                                                    "API and job servers: how many run"])
    if i == 0:
        app_part("tasks")
    elif i == 1:
        rows = ops.api_servers()
        say(f"\n  {len([r for r in rows if r['state'] == 'running'])} running; wanted: {ops.servers_wanted()}")
        n = ask("How many should run (1 to 16, Enter to keep): ")
        if n.isdigit() and 1 <= int(n) <= 16 and confirm(f"Run {n} API and job server(s)?"):
            with ops.config_lock:
                ops.copy_config("console", f"servers-{n}")
                ops._write(ops._set_value(ops._read_config(), "EAX_API_SERVERS", n))
            for line in ops.scale_api(int(n)):
                say("  " + line)
            note(f"servers {n}")


def maintenance_mode() -> None:
    on = bool(ops.maintenance()) or os.path.exists(ops.PROXY_FLAG)
    if any(r.get("status") == "running" for r in ops.list_restores()):
        say("\nA restore is running: it switches the maintenance page off itself when it is done.")
        return
    if confirm(f"The maintenance page is {'ON' if on else 'off'}. Switch it {'off' if on else 'on'}?"
               + ("" if on else " Everyone sees the maintenance page and nobody can use EA Explorer until it is off.")):
        ops._set_maintenance(not on, "maintenance (console)", "console")
        note(f"maintenance {'off' if on else 'on'}")
        say(f"  The maintenance page is {'off' if on else 'on'}.")


# ---------------------------------------------------------------- the menu
def menu(version: str, kind: str) -> int:
    say(f"\nEA Explorer console  ({kind}, {version})")
    for i, it in enumerate(MENU, 1):
        say(f" {i:>2}  {it}")
    say("  c  Command prompt (every eax command)")
    say("  q  Quit")
    a = ask("Choose: ").lower()
    if a in ("q", "quit", "exit"):
        return 0
    if a == "c":
        return PROMPT
    if not a.isdigit() or not 1 <= int(a) <= len(MENU):
        say("  Type a number from the menu, c or q.")
        return -1
    n = int(a)
    try:
        if n == 1:
            status()
        elif n == 2:
            return START
        elif n == 3:
            restart()
        elif n == 4:
            if confirm("Stop everything? Nobody can use EA Explorer until it is started again (2). The data is kept."):
                note("stop everything")
                return STOP
            return -1
        elif n == 5:
            problems()
        elif n == 6:
            back_up(version)
        elif n == 7:
            restore(version)
        elif n == 8:
            code = passwords()
            if code:
                return code
        elif n == 9:
            users()
        elif n == 10:
            settings()
        elif n == 11:
            tasks()
        elif n == 12:
            app_part("health")
        elif n == 13:
            maintenance_mode()
        elif n == 14:
            return DIAG
    except KeyboardInterrupt:
        say("\n  Stopped.")
    except Exception as exc:  # noqa: BLE001 - said plainly, the console goes on
        say(f"\n  That did not work: {exc}")
        note(f"error in {n}: {exc}")
    pause()
    return -1


def main(argv: list[str]) -> int:
    version = argv[argv.index("--version") + 1] if "--version" in argv else os.environ.get("EAX_VERSION", "")
    kind = config().get("EAX_DEPLOYMENT", "laptop")
    note("console opened")
    while True:
        code = menu(version, kind)
        if code >= 0:
            return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
