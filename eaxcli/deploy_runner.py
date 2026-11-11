"""A deployment started from System admin > Deploy (D555): the eax deploy steps (eaxcli/deploy.py) driven by files in
one run folder, so the page can follow it and survive reloads. The operations helper runs this: a plan in its own
container, a deployment in a short-lived deployer container (deploy/deployer: ssh, curl, git and the aws, az and
doctl CLIs) with only the run folder and the release's eaxcli and templates mounted.

The run folder:
  answers.json    the answers (no secrets)                 written by the helper
  secrets.json    the cloud credentials, readable by root only; ssh_key: the private key (both deleted at the end
                  unless the person asked to keep them, then moved to the helper's own store, never shown again)
  state.json      status (running, failed, done, planned, quit), the steps, the failure, the result
  log.txt         everything the steps say (passwords, keys and tokens masked)
  decision.json   {"choice": "retry"|"back"|"quit"}       written by the helper when the person answers a failure

python -m eaxcli.deploy_runner <run folder> [--plan]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import deploy as D


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Runner:
    def __init__(self, folder: Path, plan: bool):
        self.folder = folder
        self.plan = plan
        self.state: dict = {"status": "running", "plan": plan, "steps": [], "failed": None, "result": {},
                            "started": _now(), "finished": None}

    def save(self) -> None:
        tmp = self.folder / "state.json.tmp"
        tmp.write_text(json.dumps(self.state), encoding="utf-8")
        os.replace(tmp, self.folder / "state.json")

    def out(self, text: str) -> None:
        with open(self.folder / "log.txt", "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def progress(self, i: int, n: int, title: str, status: str) -> None:
        steps = self.state["steps"]
        while len(steps) < n:
            steps.append({"title": "", "status": "waiting"})
        steps[i] = {"title": title, "status": status}
        self.save()

    def on_fail(self, step: D.Step, why: str) -> str:
        decision = self.folder / "decision.json"
        decision.unlink(missing_ok=True)
        self.state.update(status="failed", failed={"step": step.title, "why": why})
        self.save()
        while True:
            time.sleep(1)
            try:
                choice = json.loads(decision.read_text(encoding="utf-8")).get("choice")
            except (OSError, ValueError):
                continue
            decision.unlink(missing_ok=True)
            if choice in ("retry", "back", "quit"):
                self.state.update(status="running", failed=None)
                self.save()
                return choice

    def answers(self) -> dict:
        a = json.loads((self.folder / "answers.json").read_text(encoding="utf-8"))
        try:
            a.update(json.loads((self.folder / "secrets.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        key = self.folder / "ssh_key"
        if key.exists():
            a["ssh_key"] = str(key)
            pub = self.folder / "ssh_key.pub"
            if not pub.exists() and not self.plan:
                r = subprocess.run(["ssh-keygen", "-y", "-f", str(key)], capture_output=True, text=True, check=False)
                if r.returncode == 0:
                    pub.write_text(r.stdout, encoding="utf-8")
        elif self.plan:
            a.setdefault("ssh_key", str(key))
        a.pop("keep_credentials", None)            # kept by the helper, not written beside this copy of eaxcli
        return a

    def go(self) -> int:
        self.save()
        result: dict = {}
        try:
            a = self.answers()
            steps = D.all_steps(D.complete(a))
            self.state["steps"] = [{"title": s.title, "status": "waiting"} for s in steps]
            self.save()
            outcome = D.run(a, self.plan, self.on_fail, out=self.out, progress=self.progress, result=result, reveal=False)
        except Exception as exc:  # noqa: BLE001 - every failure ends in the state, never lost
            self.out(f"ERROR: {exc}")
            outcome = "quit"
        ctx = result.pop("_ctx", None)
        if ctx is not None:
            result.update({k: v for k, v in ctx.values.items() if k in D.RESULT_KEYS and v})
        self.state.update(status={"done": "planned" if self.plan else "done"}.get(outcome, outcome),
                          result=result, finished=_now(), failed=None)
        self.save()
        return 0 if outcome == "done" else 1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    return Runner(Path(argv[0]), "--plan" in argv[1:]).go()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
