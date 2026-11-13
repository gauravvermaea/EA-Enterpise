"""The updater (phase 36, D417, D511): moves an installation to a newer release, one release at a time, and rolls back.

It runs in a short-lived **updater** container that the operations helper starts (services/ops/updates.py), with the
Docker socket and the installation folder mounted at the same path as on the host, so it carries on while the API, the
helper and everything else are rebuilt and restarted. It is copied to work/updates/<id>/runner first, so changing the
code under it does not change it. Standard library, git and docker compose only.

  python3 updater.py run      --id <id>      an update asked for (work/updates/<id>/request.json)
  python3 updater.py retry    --id <id>      the failed step again, then the rest
  python3 updater.py rollback --id <id>      back to the version before the update: its backup put back

What it keeps in work/updates (on the host; the API copies the history into the database, operations.update_history):
  installed.json       the installed version, its channel, commit and when
  current.json         the update running or waiting for a decision (status running, failed, rolling-back)
  history.json         every update and rollback: from, to, who, when, the backup taken, the steps, the result
  scheduled.json       an update set for later (the helper starts it at that time)
  <id>/update.log      the whole log;  <id>/code.tar.gz  the code as it was, local changes included;  <id>/request.json

An update, in order (D417):
  1. a full backup: an infrastructure backup through the operations helper (every database, every file set, the config
     file), pinned, plus the code as it is (the commit and every file, local changes included) beside it
  2. the maintenance page on
  3. for each release on the way: its files (git checkout of the tag, or the files of that version when the folder is
     not a git checkout), the images built, everything started (the API upgrades the databases as it starts), and the
     check: the API answers with that version and the database at the same version
  4. the maintenance page off, the installed version and the history written, a What's new note for everyone
A failed step stops: the maintenance page stays with the log, and an admin chooses Retry or Roll back.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eaxcli import releases as R  # noqa: E402

KEEP = ("work/", ".git/", "library/templates/")       # never written or removed by an update or a rollback
SKIP = ("node_modules/", "__pycache__/", ".pytest_cache/", ".ruff_cache/")
HEALTH_MINUTES = int(os.environ.get("EAX_UPDATE_HEALTH_MINUTES", "20"))


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, p)


class UpdateError(RuntimeError):
    pass


class Env:
    """Everything the updater does to the outside world; the tests give a fake one."""

    def __init__(self, root: str | os.PathLike, project: str = ""):
        self.root = Path(root)
        self.work = self.root / "work"
        self.project = project or os.environ.get("COMPOSE_PROJECT_NAME", "")

    # -- config file
    def setting(self, name: str, default: str = "") -> str:
        f = self.work / "eaexplorer.env"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{name}="):
                    v = line.split("=", 1)[1].strip().strip("'\"")
                    return v or default
        return default

    # -- commands
    def run(self, cmd: list[str], timeout: int = 3600, log=None) -> int:
        p = subprocess.Popen(cmd, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        t0 = time.time()
        for line in p.stdout:              # type: ignore[union-attr]
            if log:
                log(line.rstrip())
            if time.time() - t0 > timeout:
                p.kill()
                raise UpdateError(f"{' '.join(cmd[:3])} took longer than {timeout // 60} minutes")
        return p.wait()

    def git(self, *args: str) -> str:
        return R.git(*args, cwd=self.root)

    def compose(self, args: list[str], log=None, timeout: int = 3600) -> None:
        kind = self.setting("EAX_DEPLOYMENT", "laptop")
        cmd = ["docker", "compose", "--ansi", "never", "--progress", "plain", "--env-file", "work/eaexplorer.env",
               *(["-p", self.project] if self.project else []),
               "-f", "docker-compose.yml", "-f", f"deploy/compose/docker-compose.{kind}.yml", *args]
        code = self.run(cmd, timeout=timeout, log=log)
        if code:
            raise UpdateError(f"docker compose {args[0]} failed (exit {code})")

    # -- the operations helper and the API (on the backend network)
    def ops(self, method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
        url = os.environ.get("EAX_OPS_URL", "http://ops:8090") + path
        token = os.environ.get("EAX_OPS_TOKEN") or self.setting("EAX_OPS_TOKEN", "eax-ops-laptop")
        data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"X-Ops-Token": token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - this installation's helper
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                msg = json.loads(exc.read() or b"{}").get("message")
            except ValueError:
                msg = exc.reason
            raise UpdateError(f"the operations helper refused {path}: {msg}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise UpdateError(f"the operations helper is not reachable ({exc})") from exc

    def heartbeat(self) -> dict:
        url = os.environ.get("EAX_API_URL", "http://api:8000") + "/api/v1/heartbeat"
        try:
            with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 - this installation's API
                return json.loads(r.read() or b"{}")
        except (urllib.error.URLError, OSError, ValueError):
            return {}

    def sleep(self, s: float) -> None:
        time.sleep(s)


# ---------------------------------------------------------------- state
class Updater:
    def __init__(self, env: Env):
        self.env = env
        self.dir = env.work / "updates"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state: dict = {}

    # files
    @property
    def current_path(self) -> Path:
        return self.dir / "current.json"

    def installed(self) -> dict:
        got = read_json(self.dir / "installed.json")
        if got:
            return got
        v = ""
        toml = self.env.root / "services" / "api" / "version.toml"
        if toml.exists():
            import re
            m = re.search(r'^version\s*=\s*"([^"]+)"', toml.read_text(encoding="utf-8"), re.M)
            v = m.group(1) if m else ""
        commit = ""
        if (self.env.root / ".git").exists():
            try:
                commit = self.env.git("rev-parse", "HEAD").strip()
            except R.ReleaseError:
                pass
        return {"version": v, "channel": "prod", "commit": commit, "ref": f"v{v}" if v else "", "at": ""}

    def log(self, msg: str, step: str = "") -> None:
        line = f"{now()} {msg}"
        if self.state.get("id"):
            with open(self.dir / self.state["id"] / "update.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self.state.setdefault("log", []).append(line)
            self.state["log"] = self.state["log"][-60:]
            if step:
                self.state["step"] = step
            self.save()
        print(line, flush=True)

    def save(self) -> None:
        self.state["updated"] = now()
        write_json(self.current_path, self.state)

    def history_add(self, entry: dict) -> None:
        hist = read_json(self.dir / "history.json", []) or []
        hist = [h for h in hist if h.get("id") != entry.get("id")] + [entry]
        write_json(self.dir / "history.json", hist)

    def summary(self) -> dict:
        s = self.state
        return {k: s.get(k) for k in ("id", "kind", "by", "channel", "from", "to", "steps", "status", "backup", "error",
                                      "started", "finished", "notes", "failed_version", "rollback_backup")}

    # maintenance page (the same files the operations helper writes, D230)
    def maintenance(self, on: bool, what: str = "") -> None:
        m, flag = self.env.work / "maintenance.json", self.env.work / "proxy" / "maintenance"
        if on:
            write_json(m, {"since": now(), "what": what, "by": self.state.get("by", "")})
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text(what + "\n", encoding="utf-8")
        else:
            for p in (m, flag):
                if p.exists():
                    p.unlink()

    # ------------------------------------------------------------ code: kept and put back
    def _files(self) -> list[str]:
        root = self.env.root
        out = []
        for dirpath, dirnames, filenames in os.walk(root):
            rel = Path(dirpath).relative_to(root).as_posix()
            rel = "" if rel == "." else rel + "/"
            dirnames[:] = [d for d in dirnames if not any((rel + d + "/").startswith(k) for k in KEEP + SKIP)
                           and d not in ("node_modules", "__pycache__")]
            out += [rel + f for f in filenames]
        return sorted(out)

    def keep_code(self, folder: Path) -> dict:
        """The code as it is now: every file (local changes included) in code.tar.gz, the list, and the git commit."""
        folder.mkdir(parents=True, exist_ok=True)
        files = self._files()
        with tarfile.open(folder / "code.tar.gz", "w:gz") as t:
            for f in files:
                t.add(self.env.root / f, arcname=f, recursive=False)
        (folder / "files.txt").write_text("\n".join(files) + "\n", encoding="utf-8")
        info = {"files": len(files), "commit": "", "local_changes": ""}
        if (self.env.root / ".git").exists():
            try:
                info["commit"] = self.env.git("rev-parse", "HEAD").strip()
                diff = self.env.git("status", "--porcelain", "--untracked-files=normal")
                info["local_changes"] = "\n".join(ln for ln in diff.splitlines() if not ln[3:].startswith(KEEP))
            except R.ReleaseError:
                pass
        write_json(folder / "code.json", info)
        return info

    def put_back_code(self, folder: Path) -> None:
        """The code exactly as kept: the commit checked out (a git folder), every kept file written back, and files that
        were not there then taken away (never work/, .git/ or library/templates/)."""
        info = read_json(folder / "code.json", {}) or {}
        if info.get("commit") and (self.env.root / ".git").exists():
            self.env.git("checkout", "--force", "--detach", info["commit"])
        kept = set((folder / "files.txt").read_text(encoding="utf-8").split())
        for f in self._files():
            if f not in kept:
                (self.env.root / f).unlink(missing_ok=True)
        with tarfile.open(folder / "code.tar.gz") as t:
            t.extractall(self.env.root, filter="data")

    # ------------------------------------------------------------ one version's files
    def checkout(self, url: str, ref: str) -> str:
        """The files of one version in the installation folder; its commit."""
        if (self.env.root / ".git").exists():
            if R.TAG.match(ref):
                self.env.git("fetch", "--quiet", "--no-tags", url, f"+refs/tags/{ref}:refs/tags/{ref}")
                sha = self.env.git("rev-parse", f"refs/tags/{ref}^{{commit}}").strip()
            else:                          # Latest: a commit of main
                branch = R.CHANNELS["latest"]["branch"]
                self.env.git("fetch", "--quiet", "--no-tags", url, f"+refs/heads/{branch}:refs/remotes/eax-updates/{branch}")
                sha = self.env.git("rev-parse", f"{ref}^{{commit}}").strip()
            self.env.git("checkout", "--force", "--detach", sha)
            return sha
        staging = self.dir / self.state["id"] / "staging"
        shutil.rmtree(staging, ignore_errors=True)
        sha = R.export(url, ref, staging, cache=self.dir / "cache.git")
        new = {p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()}
        for f in self._files():
            if f not in new:
                (self.env.root / f).unlink(missing_ok=True)
        for f in sorted(new):
            if f.startswith(KEEP):
                continue
            (self.env.root / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staging / f, self.env.root / f)
        shutil.rmtree(staging, ignore_errors=True)
        return sha

    def version_here(self) -> str:
        import re
        toml = self.env.root / "services" / "api" / "version.toml"
        m = re.search(r'^version\s*=\s*"([^"]+)"', toml.read_text(encoding="utf-8"), re.M) if toml.exists() else None
        return m.group(1) if m else ""

    # ------------------------------------------------------------ the operations helper
    def backup(self, tag: str, version: str) -> str:
        """An infrastructure backup through the helper, pinned; waits for it; its name."""
        self.env.ops("POST", "/backups/backup", {"tag": tag, "by": self.state.get("by", "updater"), "kind": "update",
                                                  "version": version, "pinned": True})
        t0 = time.time()
        while True:
            self.env.sleep(3)
            st = self.env.ops("GET", "/backups").get("state") or {}
            if not st.get("busy"):
                res = st.get("result") or {}
                if res.get("status") != "ok":
                    raise UpdateError(f"the backup failed: {res.get('error') or st.get('error') or 'no result'}")
                return res.get("name", "")
            if time.time() - t0 > 6 * 3600:
                raise UpdateError("the backup took longer than 6 hours")

    def restore(self, name: str, version: str) -> None:
        r = self.env.ops("POST", "/backups/restore", {"name": name, "what": "full", "by": self.state.get("by", "updater"),
                                                       "version": version})
        rid = r.get("restore")
        while True:
            self.env.sleep(5)
            d = self.env.ops("GET", f"/restores/{rid}?tail=20")
            st = d.get("status") or (d.get("record") or {}).get("status")
            if st and st not in ("running", "started", "waiting"):
                if st != "ok":
                    raise UpdateError(f"the restore of {name} ended {st}: {d.get('error') or ''}")
                return

    def wait_healthy(self, version: str) -> None:
        """The API answers with this version and the database is at the same version (migrations ran)."""
        t0 = time.time()
        while True:
            last = self.env.heartbeat()
            if last.get("version") == version and last.get("versions_match") and last.get("status") in ("ok", "warning"):
                return
            if time.time() - t0 >= HEALTH_MINUTES * 60:
                break
            self.env.sleep(10)
        raise UpdateError(f"EA Explorer did not come up at version {version} within {HEALTH_MINUTES} minutes "
                          f"(the API answered: {last.get('version') or 'nothing'}, database {((last.get('database') or {}).get('version')) or '?'})")

    # ------------------------------------------------------------ an update
    def start(self, request: dict) -> dict:
        """The update asked for: request = {id, by, channel, to, url, steps:[refs], notes}."""
        cur = read_json(self.current_path)
        if cur and cur.get("status") in ("running", "failed", "rolling-back") and cur.get("id") != request.get("id"):
            raise UpdateError(f"Update {cur['id']} is {cur['status']}: finish it (Retry or Roll back) first.")
        inst = self.installed()
        self.state = {"id": request.get("id") or uuid.uuid4().hex[:12], "kind": "update", "by": request.get("by", ""),
                      "channel": request["channel"], "url": request["url"], "from": inst, "to": request["to"],
                      "steps": [{"ref": r, "status": "waiting"} for r in request["steps"]], "status": "running",
                      "started": now(), "finished": None, "backup": "", "error": "", "notes": request.get("notes", ""),
                      "log": []}
        (self.dir / self.state["id"]).mkdir(parents=True, exist_ok=True)
        self.save()
        self.log(f"update {self.state['id']} by {self.state['by']}: {inst.get('version')} -> {request['to']} on "
                 f"{request['channel']}, {len(request['steps'])} step(s): {', '.join(request['steps'])}", "backup")
        try:
            code = self.keep_code(self.dir / self.state["id"])
            self.log(f"the code as it is: {code['files']} files, commit {code['commit'][:12] or '(not a git folder)'}"
                     + ("; local changes kept in the backup:\n" + code["local_changes"] if code["local_changes"] else ""))
            self.state["backup"] = self.backup(f"before update to {request['to']}", inst.get("version", ""))
            self._copy_code_into_backup()
            self.log(f"full backup taken and pinned: {self.state['backup']}")
        except Exception as exc:  # noqa: BLE001 - nothing changed yet: the update simply did not start
            self.state.update(status="not-started", error=f"Not started, nothing changed: {exc}", finished=now())
            self.log(self.state["error"], "done")
            self.history_add(self.summary())
            self.current_path.unlink(missing_ok=True)
            return self.summary()
        self.maintenance(True, f"Updating EA Explorer to {request['to']}")
        self.log("maintenance page on: EA Explorer cannot be used until the update has finished", "steps")
        return self._steps()

    def _copy_code_into_backup(self) -> None:
        dest = self.env.work / "backups" / "infrastructure" / self.state["backup"] / "code"
        if dest.parent.exists():
            dest.mkdir(parents=True, exist_ok=True)
            for n in ("code.tar.gz", "files.txt", "code.json"):
                src = self.dir / self.state["id"] / n
                if src.exists():
                    shutil.copy2(src, dest / n)

    def _steps(self) -> dict:
        for i, step in enumerate(self.state["steps"]):
            if step["status"] == "ok":
                continue
            ref = step["ref"]
            step.update(status="running", started=now(), error="")
            self.log(f"step {i + 1} of {len(self.state['steps'])}: {ref}", f"step {i + 1}")
            try:
                sha = self.checkout(self.state["url"], ref)
                version = self.version_here()
                step.update(commit=sha, version=version)
                self.log(f"  files of {ref} in place (commit {sha[:12]}, version {version}); building the images")
                self.env.compose(["build"], log=lambda s: self.log("  " + s) if s.strip() else None)
                self.log("  starting everything (the API upgrades the databases as it starts)")
                self.env.compose(["up", "-d", "--remove-orphans"], log=lambda s: self.log("  " + s) if s.strip() else None)
                self.maintenance(True, f"Updating EA Explorer to {self.state['to']}")   # a recreated proxy keeps showing it
                self.log(f"  checking that EA Explorer answers at version {version}")
                self.wait_healthy(version)
                step.update(status="ok", finished=now())
                write_json(self.dir / "installed.json", {"version": version, "channel": self.state["channel"], "commit": sha,
                                                         "ref": ref, "at": now()})
                self.log(f"  {ref} is installed and healthy")
            except Exception as exc:  # noqa: BLE001 - stop and ask (D417)
                step.update(status="failed", error=str(exc)[:500], finished=now())
                self.state.update(status="failed", error=f"Step {i + 1} ({ref}) failed: {exc}")
                self.log(f"FAILED: {self.state['error']}. The maintenance page stays on. Choose Retry or Roll back "
                         "(System admin > Updates, or eax update --retry / eax rollback).", "failed")
                self.history_add(self.summary())
                return self.summary()
        self.state.update(status="ok", finished=now(), error="")
        self.maintenance(False)
        self.log(f"update finished: {self.state['from'].get('version')} -> {self.state['to']}; maintenance page off", "done")
        self.history_add(self.summary())
        self.current_path.unlink(missing_ok=True)
        return self.summary()

    def retry(self, by: str = "") -> dict:
        self.state = read_json(self.current_path) or {}
        if self.state.get("status") != "failed":
            raise UpdateError("No failed update to retry.")
        self.state.update(status="running", error="", retried_by=by or self.state.get("by"))
        self.log(f"retry by {by or self.state.get('by')}", "steps")
        return self._steps()

    def rollback(self, by: str = "") -> dict:
        """Back to the version before the update: the code as kept, then its full backup put back (the current state is
        backed up first by the restore, D226). Work done since the update is lost."""
        self.state = read_json(self.current_path) or {}
        if not self.state.get("backup"):
            last = [h for h in (read_json(self.dir / "history.json", []) or []) if h.get("kind") == "update" and h.get("status") == "ok"]
            if not last:
                raise UpdateError("Nothing to roll back: no update with a backup is waiting or was the last one.")
            self.state = dict(last[-1], log=[])
        failed = next((s.get("version") or s["ref"] for s in self.state.get("steps", []) if s.get("status") == "failed"),
                      self.state.get("to"))
        frm = self.state.get("from") or {}
        self.state.update(status="rolling-back", rollback_by=by or self.state.get("by"), error="", failed_version=failed)
        self.log(f"roll back by {by or self.state.get('by')}: to {frm.get('version')} (commit {str(frm.get('commit'))[:12]}),"
                 f" restoring {self.state['backup']}", "rollback")
        try:
            self.maintenance(True, f"Rolling EA Explorer back to {frm.get('version')}")
            now_folder = self.dir / self.state["id"] / "before-rollback"
            self.keep_code(now_folder)
            self.log("the code as it is now kept (before-rollback)")
            self.put_back_code(self.dir / self.state["id"])
            self.log(f"code back at {frm.get('version')}; building and starting")
            self.env.compose(["build"], log=lambda s: self.log("  " + s) if s.strip() else None)
            self.env.compose(["up", "-d", "--remove-orphans"], log=lambda s: self.log("  " + s) if s.strip() else None)
            self._wait_ops()
            self.log(f"restoring the backup taken before the update ({self.state['backup']}); the restore backs up the current state first")
            self.restore(self.state["backup"], frm.get("version", ""))
            self.wait_healthy(frm.get("version", ""))
            write_json(self.dir / "installed.json", dict(frm, at=now()))
            self.state.update(status="rolled-back", finished=now())
            self.maintenance(False)
            self.log(f"rolled back to {frm.get('version')}; {failed} is marked failed in the history; maintenance page off", "done")
            self.history_add(self.summary())
            failed_list = read_json(self.dir / "failed-versions.json", []) or []
            write_json(self.dir / "failed-versions.json", sorted(set(failed_list + [str(failed)])))
            self.current_path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001 - a rollback that fails stays on the maintenance page with its log
            self.state.update(status="failed", error=f"Roll back failed: {exc}")
            self.log(f"ROLL BACK FAILED: {exc}. The maintenance page stays on; see this log and the restore's log.", "failed")
            self.history_add(self.summary())
        return self.summary()

    def _wait_ops(self) -> None:
        for _ in range(60):
            try:
                self.env.ops("GET", "/backups", timeout=5)
                return
            except UpdateError:
                self.env.sleep(5)
        raise UpdateError("the operations helper did not come back")


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    uid = argv[argv.index("--id") + 1] if "--id" in argv else ""
    by = argv[argv.index("--by") + 1] if "--by" in argv else ""
    u = Updater(Env(os.getcwd()))
    try:
        if cmd == "run":
            req = read_json(u.dir / uid / "request.json")
            if not req:
                print(f"No request for update {uid}")
                return 2
            out = u.start(req)
        elif cmd == "retry":
            out = u.retry(by)
        elif cmd == "rollback":
            out = u.rollback(by)
        else:
            print(__doc__)
            return 2
    except UpdateError as exc:
        print(f"updater: {exc}", flush=True)
        return 1
    return 0 if out.get("status") in ("ok", "rolled-back") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
