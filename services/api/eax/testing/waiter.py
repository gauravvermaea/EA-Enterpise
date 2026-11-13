"""The test runner as an always-on service (R2.44, D635; owner, 12 Nov 2026, 21:46: on a platform with no Docker socket
"the test runner runs as an always-on service that waits for runs").

  python -m eax.testing.waiter      waits for runs: every few seconds it takes the oldest run the API queued for it
                                    (EAX_PLATFORM=managed), runs it here (python -m eax.testing run --run-id N), then
                                    collects it, as the operations helper does on a laptop or server

The run's folder is a temporary one in this container; with EAX_FILE_STORE=database (no local file system) its files go
into the file store when it ends (eax/testing/run.py). The security scanners (ZAP and Trivy) are containers of their
own, started through the Docker socket, so a platform run leaves them out and says so.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

from sqlalchemy import text

WAITING = "Waiting for the test runner service"


def platform_managed() -> bool:
    """EAX_PLATFORM=managed: a Docker platform (Swarm or another orchestrator) runs the containers; no Docker socket."""
    from ..config import _env
    return _env("EAX_PLATFORM", "compose").lower() in ("managed", "swarm", "kubernetes", "platform")


def take(conn) -> dict | None:
    """The oldest run waiting for this service, marked as taken (one service takes it)."""
    r = conn.execute(text(f"""SELECT id, level, suites, role, area, watch, journeys, pages_only, repeat_of, repeat_warnings,
                                      started_by FROM tests.test_runs
                               WHERE state = 'queued' AND step LIKE '{WAITING}%' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED""")).mappings().first()
    if not r:
        return None
    conn.execute(text("UPDATE tests.test_runs SET step = 'Starting in the test runner service' WHERE id = :i"), {"i": r["id"]})
    return dict(r)


def argv_for(r: dict, folder: str) -> list[str]:
    suites = [s for s in (r["suites"] or ["api", "ui", "db"]) if s != "security"]   # the scanners need the Docker socket
    cmd = [sys.executable, "-m", "eax.testing", "run", "--level", r["level"] or "smoke", "--suites", ",".join(suites) or "api",
           "--trigger", "web", "--folder", folder, "--run-id", str(r["id"]), "--by", r["started_by"] or ""]
    if r.get("role"):
        cmd += ["--role", r["role"]]
    if r.get("area"):
        cmd += ["--area", r["area"]]
    if r.get("watch"):
        cmd.append("--watch")
    for j in r.get("journeys") or []:
        cmd += ["--journey", j]
    if r.get("pages_only"):
        cmd.append("--pages-only")
    if r.get("repeat_of") is not None:
        cmd += ["--repeat", str(int(r["repeat_of"]))] + (["--warnings"] if r.get("repeat_warnings") else [])
    return cmd


def run_one(r: dict) -> int:
    folder = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-run{r['id']}"
    results = tempfile.mkdtemp(prefix="eax-test-results-")
    env = {**os.environ, "EAX_TEST_RESULTS": results}
    code = subprocess.call(argv_for(r, folder), env=env)
    subprocess.call([sys.executable, "-m", "eax.testing", "collect", "--run-id", str(r["id"])], env=env)
    return code


def main() -> int:
    from . import store
    print("EA Explorer test runner service: waiting for runs", flush=True)
    while True:
        try:
            with store.engine().begin() as conn:
                r = take(conn)
        except Exception as exc:  # noqa: BLE001 - the database may not be there yet
            print(f"test runner service: {str(exc).splitlines()[0][:200]}", flush=True)
            r = None
        if r:
            print(f"test runner service: run {r['id']} ({r['level']})", flush=True)
            run_one(r)
            continue
        time.sleep(int(os.environ.get("EAX_TEST_WAIT_SECONDS", "5")))


if __name__ == "__main__":
    sys.exit(main())
