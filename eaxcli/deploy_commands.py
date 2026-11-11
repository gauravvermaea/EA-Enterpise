"""The Commands and Console tabs of eax deploy's page (D554): eax commands run straight on this machine through eaxcli
(the same code as typing them), or on the server the wizard set up, over its SSH connection. EA Explorer may not be up,
so there is no operations helper here. The catalogue, the checks and the strong confirm are eaxcli/commands.py, the
same as EA Explorer's Command centre; each run is kept by eaxcli/cmdrun.py (work/commands/<run>) and logged to
work/logs. The page is only on 127.0.0.1 with its random key (eaxcli/deploy_web.py)."""

from __future__ import annotations

import os
import secrets
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import cmdrun
from . import commands as C
from .core import log_only

ROOT = Path(__file__).resolve().parent.parent


def _who() -> str:
    return os.environ.get("USER") or os.environ.get("USERNAME") or "deploy"


class Target:
    """Where commands run: here, or over SSH on the server the wizard set up (ssh argv and the installation folder)."""

    def __init__(self, ssh: list[str] | None = None, folder: str = ""):
        self.ssh, self.folder = ssh or [], folder

    @classmethod
    def from_answers(cls, a: dict, deployed: bool) -> Target:
        """The server the wizard set up, once it is deployed (a server over SSH, or a cloud machine); else here."""
        from . import deploy as D
        if not deployed or not D._remote(a) or not a.get("ssh_target"):
            return cls()
        return cls(["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                    "-i", str(a.get("ssh_key", "")), "-p", str(a.get("ssh_port", "22")), str(a["ssh_target"])],
                   str(a.get("install_dir") or "/opt/eaexplorer"))

    @property
    def remote(self) -> bool:
        return bool(self.ssh)

    def where(self) -> str:
        return f"{self.ssh[-1]}:{self.folder}" if self.remote else str(ROOT)


class Runs:
    def __init__(self):
        self.lock = threading.Lock()
        self.remote_runs: dict[str, dict] = {}       # over SSH: kept in memory and in work/logs here
        self.consoles: dict[str, dict] = {}

    # ---------------------------------------------------------------- one command
    def start(self, target: Target, argv: list[str], typed: str = "", understood: bool = False) -> dict:
        argv = C.check_argv(argv)
        kind = C.kind_of(argv[0])
        if kind == "interactive":
            raise C.Refused(f"eax {argv[0]} asks questions as it goes: run it in the Console tab.")
        if argv[0] == "deploy":
            raise C.Refused("This page is eax deploy: use the wizard's own tab.")
        name = C.installation_name(ROOT) if not target.remote else target.folder.rstrip("/").rsplit("/", 1)[-1]
        C.check_confirm(argv, typed, name, understood)
        run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + argv[0][:16] + "-" + secrets.token_hex(2)
        log_only(f"deploy page: {_who()} runs eax {' '.join(argv)} on {target.where()} (run {run_id})")
        if not target.remote:
            subprocess.Popen([sys.executable, "-m", "eaxcli.cmdrun", run_id, _who(), "--", *argv], cwd=ROOT,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"id": run_id, "argv": argv, "kind": kind, "command": "eax " + " ".join(argv), "where": "here"}
        remote = (f"cd {shlex.quote(target.folder)} && python3 -m eaxcli.cmdrun {run_id} {shlex.quote(_who())} -- "
                  + " ".join(shlex.quote(a) for a in argv)
                  + f" ; cat work/commands/{run_id}/output.log 2>/dev/null || cat persist/safety-backups/commands/{run_id}/output.log")
        rec = {"id": run_id, "by": _who(), "argv": argv, "command": "eax " + " ".join(argv), "kind": kind,
               "source": "deploy page", "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "ended": None, "exit_code": None, "state": "running", "where": target.where(), "text": ""}
        with self.lock:
            self.remote_runs[run_id] = rec

        def go():
            log = ROOT / "work" / "logs" / f"eax-{run_id}-web.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.Popen([*target.ssh, remote], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL)
            with open(log, "ab") as f:
                for chunk in iter(lambda: proc.stdout.read(1024), b""):
                    f.write(chunk)
                    with self.lock:
                        rec["text"] += chunk.decode("utf-8", "replace")
            code = proc.wait()
            with self.lock:
                rec.update(ended=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), exit_code=code,
                           state="done" if code == 0 else "failed")
        threading.Thread(target=go, daemon=True).start()
        return {"id": run_id, "argv": argv, "kind": kind, "command": rec["command"], "where": target.where()}

    def detail(self, run_id: str, start: int = 0) -> dict:
        with self.lock:
            rec = self.remote_runs.get(run_id)
            if rec:
                text = rec["text"].encode("utf-8")[start:].decode("utf-8", "replace")
                return {"status": {k: v for k, v in rec.items() if k != "text"}, "text": text,
                        "next": start + len(text.encode("utf-8"))}
        return cmdrun.output(run_id, start, ROOT)

    def history(self) -> list[dict]:
        with self.lock:
            remote = [{k: v for k, v in r.items() if k != "text"} for r in self.remote_runs.values()]
        return sorted(remote + cmdrun.history(ROOT), key=lambda r: r.get("started") or "", reverse=True)

    # ---------------------------------------------------------------- the Console: a session the page reads and writes
    def console_start(self, target: Target) -> dict:
        sid = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)
        env = {**os.environ, "EAX_CONSOLE_LOCAL": "1", "EAX_CONSOLE_USER": _who(), "EAX_CONSOLE_SESSION": sid,
               "PYTHONUNBUFFERED": "1", "TERM": "dumb"}
        if target.remote:
            ssh = list(target.ssh)
            if "BatchMode=yes" in ssh:              # the console may ask (a passphrase): not in batch mode
                i = ssh.index("BatchMode=yes")
                del ssh[i - 1:i + 1]
            remote = (f"cd {shlex.quote(target.folder)} && EAX_CONSOLE_LOCAL=1 EAX_CONSOLE_USER={shlex.quote(_who())} "
                      f"EAX_CONSOLE_SESSION={sid} python3 -m eaxcli.webconsole")
            cmd = [*ssh, "-tt", remote]
        else:
            cmd = [sys.executable, "-m", "eaxcli.webconsole"]
        try:
            import pty
            master, slave = pty.openpty()
            proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=slave, stdout=slave, stderr=slave, close_fds=True,
                                    start_new_session=True)
            os.close(slave)
            reader, writer = (lambda: os.read(master, 65536)), (lambda b: os.write(master, b))
        except (ImportError, OSError):      # Windows: pipes instead of a terminal
            proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            reader = lambda: proc.stdout.read1(65536) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)

            def writer(b: bytes) -> None:
                proc.stdin.write(b)
                proc.stdin.flush()
        s = {"id": sid, "proc": proc, "out": bytearray(), "write": writer, "ended": False}

        def pump():
            while True:
                try:
                    data = reader()
                except OSError:
                    break
                if not data:
                    break
                with self.lock:
                    s["out"] += data
                    del s["out"][:-2_000_000]
            s["ended"] = True
        threading.Thread(target=pump, daemon=True).start()
        with self.lock:
            self.consoles[sid] = s
        log_only(f"deploy page: {_who()} opened the Console on {target.where()} (session {sid})")
        return {"session": sid}

    def console_read(self, sid: str, start: int = 0) -> dict:
        with self.lock:
            s = self.consoles.get(sid)
            if not s:
                raise FileNotFoundError("No such console.")
            data = bytes(s["out"][start:])
            return {"text": data.decode("utf-8", "replace"), "next": start + len(data),
                    "ended": s["ended"] and s["proc"].poll() is not None}

    def console_write(self, sid: str, text: str) -> None:
        with self.lock:
            s = self.consoles.get(sid)
        if not s or s["ended"]:
            raise FileNotFoundError("The console has ended.")
        s["write"](text.encode("utf-8"))

    def console_end(self, sid: str) -> None:
        with self.lock:
            s = self.consoles.get(sid)
        if s and s["proc"].poll() is None:
            try:
                s["write"](b"exit\n")
            except OSError:
                pass
            try:
                s["proc"].wait(timeout=3)
            except subprocess.TimeoutExpired:
                s["proc"].terminate()
