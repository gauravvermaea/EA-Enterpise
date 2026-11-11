"""The Console in a browser (D554): type eax commands as on the machine itself ("eax status", "backup nightly",
"eax help restore"; the eax is optional), with their real output and their questions, and "eax console" for its
numbered menu. Runs in a terminal the page opens: in EA Explorer through the operations helper (a short-lived container
beside the stack, System admin > Command centre > Console), in eax deploy's page on the machine itself or on the server
over SSH.

Only eax commands run (eaxcli/commands.py checks every line); anything else is refused with a short message, never a
shell. The commands that delete everything ask for the installation's name and "I understand" and take a backup first,
as in the Command centre; only Super Admins may run them. Every command is kept with who, when and its exit code in
work/commands/console-<session>/commands.jsonl, and the whole session in transcript.log beside it.

    python3 -m eaxcli.webconsole            (who and their roles in EAX_CONSOLE_USER, EAX_CONSOLE_ROLES)
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from . import commands as C

try:
    import pty
except ImportError:          # Windows: commands run through a pipe instead
    pty = None

ROOT = Path(__file__).resolve().parent.parent
BOLD, DIM, RED, YELLOW, OFF = "\x1b[1m", "\x1b[2m", "\x1b[31m", "\x1b[33m", "\x1b[0m"


class Session:
    def __init__(self, who: str, roles: list[str], local: bool, root: Path = ROOT, session: str = ""):
        self.who, self.roles, self.local, self.root = who, roles, local, root
        self.id = session or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)
        self.home = root / "work" / "commands" / f"console-{self.id}"
        self.home.mkdir(parents=True, exist_ok=True)
        self.transcript = open(self.home / "transcript.log", "ab", buffering=0)  # noqa: SIM115 - open for the session
        self.cat = C.catalogue()
        (self.home / "status.json").write_text(json.dumps({
            "id": f"console-{self.id}", "by": who, "kind": "console", "command": "Console session",
            "source": "console", "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "state": "running",
            "argv": [], "ended": None, "exit_code": None}, indent=2), encoding="utf-8")

    def write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()
        self.transcript.write(text.encode("utf-8", "replace"))

    def ask(self, prompt: str) -> str:
        self.write(prompt)
        line = sys.stdin.readline()
        if not line:
            raise EOFError
        self.transcript.write(line.encode("utf-8", "replace"))
        return line.rstrip("\r\n")

    def note(self, argv: list[str], code: int | None, refused: str = "") -> None:
        with open(self.home / "commands.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "by": self.who,
                                "command": " ".join(["eax", *argv]) if argv else "", "exit_code": code,
                                "refused": refused}) + "\n")

    def spawn(self, argv: list[str]) -> int:
        def read(fd: int) -> bytes:
            data = os.read(fd, 65536)
            self.transcript.write(data)
            return data
        os.environ.update(EAX_COMMAND_BY=self.who, PYTHONUNBUFFERED="1")
        cmd = [sys.executable, str(self.root / "eaxpy.py"), *argv]
        if pty is None or not sys.stdin.isatty():      # Windows, or no terminal: the output through a pipe
            proc = subprocess.Popen(cmd, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            for chunk in iter(lambda: proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1), b""):
                sys.stdout.buffer.write(chunk)
                sys.stdout.flush()
                self.transcript.write(chunk)
            return proc.wait()
        status = pty.spawn(cmd, read)
        return os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else status >> 8

    def confirm_wipe(self, argv: list[str]) -> bool:
        plan = C.wipe_plan(argv)
        name = C.installation_name(self.root)
        self.write(f"\n{RED}{BOLD}{plan['command']} deletes everything:{OFF}\n")
        for d in plan["deletes"]:
            self.write(f"{RED}  - {d}{OFF}\n")
        self.write(f"{plan['then']}\n{plan['backup_first']}\n")
        if not self.local:
            self.write(f"{YELLOW}EA Explorer goes offline: this page stops answering. Open the address again in a few "
                       f"minutes.{OFF}\n")
        typed = self.ask(f"Type the installation's name ({name}) to confirm: ")
        understood = self.ask("Type 'I understand' to confirm that this deletes everything: ").strip().lower() == "i understand"
        try:
            C.check_confirm(argv, typed, name, understood)
        except C.Refused as exc:
            self.write(f"{YELLOW}{exc} Nothing was deleted.{OFF}\n")
            return False
        return True

    def one(self, line: str) -> bool:
        """Run one line; False when the session should end."""
        text = line.strip()
        if not text:
            return True
        if text in ("exit", "quit", "logout"):
            return False
        try:
            argv = C.parse_line(text, self.cat)
            C.allowed(argv[0], self.roles)
        except C.Refused as exc:
            self.write(f"{YELLOW}{exc}{OFF}\n")
            self.note([], None, f"{text[:200]}: {exc}")
            return True
        kind = C.kind_of(argv[0])
        if kind == "host" and not self.local:
            cmd = C.find(argv[0], self.cat)
            self.write(f"{YELLOW}{argv[0]} runs on the machine itself, not from here. {cmd['host_why']}{OFF}\n"
                       f"Type it there:  {BOLD}eax {' '.join(argv)}{OFF}\n")
            self.note(argv, None, "host-only")
            return True
        if kind == "wipe" and not self.confirm_wipe(argv):
            self.note(argv, None, "not confirmed")
            return True
        if kind == "offline" and not self.local and not (argv[0] == "update" and "--status" in argv):
            self.write(f"{YELLOW}This stops or restarts EA Explorer: the page may stop answering until it is back."
                       f"{OFF}\n")
        if kind == "wipe":
            code = C.safety_backup(self.root, self.id, lambda t: self.write(t + "\n"))
            if code:
                self.write(f"{YELLOW}The backup first failed, so nothing was deleted.{OFF}\n")
                self.note(argv, code, "backup failed")
                return True
            argv = C.with_yes(argv)
        code = self.spawn(argv)
        self.note(argv, code)
        if code:
            self.write(f"{DIM}[exit code {code}]{OFF}\n")
        return True

    def loop(self) -> int:
        self.write(f"{BOLD}EA Explorer console{OFF}: type eax commands as on the machine itself (eax is optional): "
                   f"status, backup nightly, help restore. {BOLD}console{OFF} opens the numbered menu; "
                   f"{BOLD}help{OFF} lists every command; {BOLD}exit{OFF} ends.\n"
                   f"{DIM}Session {self.id}, as {self.who}. Everything typed here is kept.{OFF}\n")
        try:
            while True:
                if not self.one(self.ask(f"{BOLD}eax>{OFF} ")):
                    break
        except (EOFError, KeyboardInterrupt):
            pass
        rec = json.loads((self.home / "status.json").read_text(encoding="utf-8"))
        rec.update(ended=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), state="done", exit_code=0)
        (self.home / "status.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
        self.write("Console ended.\n")
        return 0


def main() -> int:
    who = os.environ.get("EAX_CONSOLE_USER", "") or os.environ.get("USER", "") or "?"
    roles = [r for r in os.environ.get("EAX_CONSOLE_ROLES", "").split(",") if r]
    local = os.environ.get("EAX_CONSOLE_LOCAL", "") == "1"
    if local and not roles:          # eax deploy's page on the machine itself: whoever runs eax is its administrator
        roles = ["super-admin"]
    return Session(who, roles, local, session=os.environ.get("EAX_CONSOLE_SESSION", "")).loop()


if __name__ == "__main__":
    sys.exit(main())
