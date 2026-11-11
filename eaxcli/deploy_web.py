"""eax deploy in a web page (D498, D500): a small page served by eax itself on this computer (127.0.0.1, a free port,
a random key in the address so no other page can drive it), before EA Explorer is up. The same questions and steps
as the console wizard (eaxcli/deploy.py); the page shows the steps as they run, the log, and Retry / Back / Quit
when a step fails. Ctrl+C in the console (or Close in the page) stops it."""

from __future__ import annotations

import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import commands as C
from . import deploy as D
from . import deploy_commands as DC
from .core import Failure, log_only, say

PAGE = Path(__file__).with_name("deploy.html")


class State:
    def __init__(self, answers: dict, plan: bool):
        self.answers = {**D.kept_credentials(), **answers}
        self.plan = plan
        self.lines: list[str] = []
        self.steps: list[dict] = []
        self.status = "asking"                 # asking, running, failed, done, quit, back
        self.failed: dict | None = None
        self.decision = threading.Event()
        self.choice = ""
        self.lock = threading.Lock()
        self.runs = DC.Runs()             # the Commands and Console tabs (D554)

    def target(self) -> DC.Target:
        with self.lock:
            return DC.Target.from_answers(self.answers, self.status == "done" and not self.plan)

    def out(self, text: str) -> None:
        with self.lock:
            self.lines.append(text)
            del self.lines[:-2000]
        log_only(text)

    def progress(self, i: int, n: int, title: str, status: str) -> None:
        with self.lock:
            while len(self.steps) < n:
                self.steps.append({"title": "", "status": "waiting"})
            self.steps[i] = {"title": title, "status": status}

    def on_fail(self, step: D.Step, why: str) -> str:
        with self.lock:
            self.status, self.failed = "failed", {"step": step.title, "why": why}
        self.decision.clear()
        self.decision.wait()
        with self.lock:
            self.status, self.failed = "running", None
        return self.choice

    def start(self, answers: dict, plan: bool) -> None:
        a = D.complete(answers)
        with self.lock:
            self.answers, self.lines, self.steps, self.status = a, [], [], "running"
        steps = D.all_steps(a)
        self.steps = [{"title": s.title, "status": "waiting"} for s in steps]

        def go():
            try:
                result = D.run(a, plan, self.on_fail, out=self.out, progress=self.progress)
            except Exception as exc:  # noqa: BLE001 - shown in the page, never lost
                self.out(f"ERROR: {exc}")
                result = "quit"
            with self.lock:
                self.status = {"done": "planned" if plan else "done", "back": "asking"}.get(result, "quit")
        threading.Thread(target=go, daemon=True).start()


def make_handler(state: State, key: str, stop: threading.Event):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body, kind: str = "application/json") -> None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(data)

        def _ok(self) -> bool:
            if self.headers.get("X-Deploy-Key") != key:
                self._send(403, {"message": "Not this wizard's page."})
                return False
            return True

        def do_GET(self):
            if self.path.split("?")[0] == "/" or self.path.startswith("/?"):
                html = PAGE.read_text(encoding="utf-8").replace("__KEY__", key)
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if not self._ok():
                return None
            if self.path == "/api/state":
                with state.lock:
                    return self._send(200, {"status": state.status, "steps": state.steps, "lines": state.lines[-400:],
                                            "failed": state.failed, "plan": state.plan,
                                            "answers": {k: ("" if k in D.SECRET_KEYS else v) for k, v in state.answers.items()}})
            return self._commands_get()

        def _commands_get(self):
            path, _, query = self.path.partition("?")
            start = int((query.split("from=", 1)[1].split("&")[0] if "from=" in query else "0") or 0)
            try:
                if path == "/api/commands":
                    t = state.target()
                    return self._send(200, {**C.catalogue(), "where": t.where(), "remote": t.remote,
                                            "installation": C.installation_name(DC.ROOT) if not t.remote
                                            else t.folder.rstrip("/").rsplit("/", 1)[-1], "you": {"super_admin": True}})
                if path == "/api/commands/runs":
                    return self._send(200, {"runs": state.runs.history()})
                if path.startswith("/api/commands/runs/"):
                    return self._send(200, state.runs.detail(path.rsplit("/", 1)[1], start))
                if path.startswith("/api/console/"):
                    return self._send(200, state.runs.console_read(path.rsplit("/", 1)[1], start))
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            except ValueError as exc:
                return self._send(400, {"message": str(exc)})
            return self._send(404, {"message": "No such page."})

        def _commands_post(self, body: dict):
            try:
                if self.path == "/api/commands/run":
                    conf = body.get("confirm") or {}
                    return self._send(202, state.runs.start(state.target(), [str(a) for a in body.get("argv") or []],
                                                            str(conf.get("typed") or ""), bool(conf.get("understood"))))
                if self.path == "/api/console/start":
                    return self._send(200, state.runs.console_start(state.target()))
                if self.path.startswith("/api/console/") and self.path.endswith("/write"):
                    state.runs.console_write(self.path.split("/")[3], str(body.get("text") or "")[:4000])
                    return self._send(200, {"ok": True})
                if self.path.startswith("/api/console/") and self.path.endswith("/end"):
                    state.runs.console_end(self.path.split("/")[3])
                    return self._send(200, {"ok": True})
            except C.Refused as exc:
                return self._send(400, {"message": str(exc)})
            except FileNotFoundError as exc:
                return self._send(404, {"message": str(exc)})
            return self._send(404, {"message": "No such page."})

        def do_POST(self):
            if not self._ok():
                return None
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"message": "Not JSON."})
            if self.path.startswith("/api/commands/") or self.path.startswith("/api/console/"):
                return self._commands_post(body)
            answers = {k: str(v) for k, v in (body.get("answers") or {}).items()}
            if self.path == "/api/questions":
                merged = {**{q.key: q.default_for(answers) for q in D.visible(answers) if q.key not in answers}, **answers}
                return self._send(200, {"questions": [q.as_dict(merged) for q in D.visible(merged)]})
            if self.path in ("/api/plan", "/api/run"):
                with state.lock:
                    busy = state.status in ("running", "failed")
                if busy:
                    return self._send(409, {"message": "A deployment is running."})
                try:
                    state.start(answers, plan=self.path == "/api/plan" or state.plan)
                except Failure as exc:
                    return self._send(400, {"message": str(exc)})
                return self._send(200, {"ok": True})
            if self.path == "/api/decide":
                choice = body.get("choice")
                if choice not in ("retry", "back", "quit"):
                    return self._send(400, {"message": "retry, back or quit"})
                state.choice = choice
                state.decision.set()
                return self._send(200, {"ok": True})
            if self.path == "/api/close":
                self._send(200, {"ok": True})
                stop.set()
                return None
            return self._send(404, {"message": "No such page."})
    return H


def serve(answers: dict, plan: bool, open_browser: bool = True, port: int = 0) -> int:
    state = State(answers, plan)
    key = secrets.token_urlsafe(24)
    stop = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state, key, stop))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    say(f"The deployment wizard is open in your browser: {url}", "cyan")
    say("Keep this window open while it runs; Ctrl+C (or Close in the page) stops the wizard.")
    if open_browser and not os.environ.get("EAX_NO_BROWSER"):
        webbrowser.open(url)
    try:
        while not stop.wait(0.5):
            pass
    except KeyboardInterrupt:
        say("Stopped.")
    finally:
        server.shutdown()
    return 0 if state.status in ("done", "planned", "asking") else 1
