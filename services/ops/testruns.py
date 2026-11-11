"""Test runs started by the operations helper (phase 36.1, D367, D523, D525).

The helper has Docker, so it starts the test runner (image eaexplorer/testrunner:<version>, built by `eax test` or
`docker compose --profile test build testrunner`) with the api container's settings on the backend and frontend
networks, and, for the security suite, an OWASP ZAP baseline scan of the front door and Trivy scans of EA Explorer's
images next to it; then the runner reads their reports (collect) and closes the run. Files: work/tests/<folder>.

  GET  /tests                   whether the runner image is there, the run going on (if any)
  POST /tests                   {run_id, level, suites, role, area, watch, by}: start a run the API has recorded (Self-test)
  POST /tests/stop              {run_id, by}: stop it (the runner ends at its next step; if it does not, it is removed)
  ops.py test [--smoke|--detailed] [--suite S]... [--role R] [--area A] [--version V] [--ci]
                                the same from `eax test`, at once, following the runner's output in the console

Bound to ops.py's helpers with bind(globals()) (ops.py runs as __main__, so it is not imported back)."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time

H: dict = {}                                   # ops.py's globals: docker, containers, jobs, _in_background...
SUITES = ("api", "ui", "db", "security")
ZAP_IMAGE = os.environ.get("EAX_IMAGE_ZAP", "ghcr.io/zaproxy/zaproxy:2.15.0")
TRIVY_IMAGE = os.environ.get("EAX_IMAGE_TRIVY", "aquasec/trivy:0.56.2")
WORK = "/eax-work"
_lock = threading.Lock()
current: dict = {}


def bind(ns: dict) -> None:
    H.update(ns)


def suites_of(args: list[str] | str | None) -> list[str]:
    if isinstance(args, str):
        args = args.replace(",", " ").split()
    asked = [a.lower() for a in (args or []) if a and not a.startswith("--")]
    if not asked or "all" in asked:
        return list(SUITES)
    bad = [a for a in asked if a not in SUITES]
    if bad:
        raise ValueError(f"Unknown suite {', '.join(bad)}: choose from {', '.join(SUITES)} (or all).")
    return [s for s in SUITES if s in asked]


def _api_container() -> dict:
    api = [s for s in H["api_servers"]() if s["state"] == "running"]
    if not api:
        raise RuntimeError("The API is not running: start EA Explorer first (eax up).")
    return json.loads(H["docker"]("inspect", "--format", "{{json .}}", api[0]["id"]))


def runner_image(info: dict | None = None) -> str:
    info = info or _api_container()
    tag = info["Config"]["Image"].rsplit(":", 1)[-1] if ":" in info["Config"]["Image"] else "dev"
    return f"eaexplorer/testrunner:{tag}"


def image_present(image: str) -> bool:
    try:
        H["docker"]("image", "inspect", image, timeout=30)
        return True
    except RuntimeError:
        return False


def host_work() -> str:
    """The work folder's path on the host (the source of this helper's /eax-work mount): new containers bind it."""
    me = json.loads(H["docker"]("inspect", "--format", "{{json .Mounts}}", socket.gethostname()))
    for m in me:
        if m.get("Destination") == WORK:
            return m["Source"]
    raise RuntimeError("The operations helper has no /eax-work mount.")


def _networks(info: dict) -> list[str]:
    return list(((info.get("NetworkSettings") or {}).get("Networks") or {}).keys())


def status() -> dict:
    try:
        image = runner_image()
        present = image_present(image)
    except RuntimeError as exc:
        return {"image": "", "image_present": False, "running": dict(current), "message": str(exc)}
    return {"image": image, "image_present": present, "running": dict(current),
            "message": "" if present else "The test runner is not built yet: run eax test once on this server (it builds it)."}


def _runner_args(info: dict, name: str, folder: str, cmd: list[str]) -> list[str]:
    env = [e for e in (info["Config"].get("Env") or []) if not e.startswith(("EAX_ROLE=", "PATH=", "HOME="))]
    args = ["create", "--name", name, "--label", "eaexplorer.test-runner=1"]
    for e in env + ["EAX_TEST_RESULTS=/results"]:
        args += ["-e", e]
    args += ["-v", f"{host_work()}/tests/{folder}:/results/{folder}"]
    nets = _networks(info)
    backend = next((n for n in nets if n.endswith("backend")), nets[0] if nets else "")
    if backend:
        args += ["--network", backend]
    return args + [runner_image(info), *cmd]


def _start_runner(info: dict, name: str, folder: str, cmd: list[str]) -> str:
    for n in (name,):
        try:
            H["docker"]("rm", "-f", n, timeout=60)
        except RuntimeError:
            pass
    cid = H["docker"](*_runner_args(info, name, folder, cmd), timeout=120).strip()
    for n in _networks(info):
        if not n.endswith("backend"):
            try:
                H["docker"]("network", "connect", n, cid, timeout=60)
            except RuntimeError:
                pass
    H["docker"]("start", cid, timeout=120)
    return cid


def _wait(cid: str, follow=None, limit: int = 7200) -> tuple[int, str]:
    """Waits for the container to end; returns its exit code and output (and prints it as it comes with follow)."""
    out: list[str] = []
    if follow:
        p = subprocess.Popen(["docker", "logs", "-f", cid], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:                         # ends when the container stops
            out.append(line)
            follow(line.rstrip("\n"))
        p.wait()
    code = int((H["docker"]("wait", cid, timeout=limit) or "1").strip() or 1)
    if not follow:
        out.append(H["docker"]("logs", cid, timeout=120))
    return code, "".join(out)


def _security_scans(info: dict, folder: str, say) -> None:
    hostdir = f"{host_work()}/tests/{folder}"
    nets = _networks(info)
    front = next((n for n in nets if n.endswith("frontend")), "")
    say(f"OWASP ZAP baseline scan of the front door ({ZAP_IMAGE})")
    try:
        subprocess.run(check=False, args=["docker", "run", "--rm", *(["--network", front] if front else []), "-v", f"{hostdir}:/zap/wrk:rw",
                        "-t", ZAP_IMAGE, "zap-baseline.py", "-t", "https://proxy/", "-J", "zap.json", "-I"],
                       capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        say(f"ZAP did not run: {exc}")
    images = sorted({c["image"] for c in H["containers"]() if str(c.get("image", "")).startswith("eaexplorer/")})
    for image in images:
        short = re.sub(r"[^a-z0-9-]", "-", image.split("/")[-1].split(":")[0])
        say(f"Trivy scan of {image}")
        try:
            subprocess.run(check=False, args=["docker", "run", "--rm", "-v", "/var/run/docker.sock:/var/run/docker.sock",
                            "-v", "eaexplorer-trivy-cache:/root/.cache/", "-v", f"{hostdir}:/out", TRIVY_IMAGE, "image",
                            "--quiet", "--format", "json", "--output", f"/out/trivy-{short}.json",
                            "--severity", "HIGH,CRITICAL", image], capture_output=True, text=True, timeout=3600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            say(f"Trivy did not run on {image}: {exc}")


def run_sequence(level: str, suites: list[str], role: str = "", area: str = "", watch: bool = False, run_id: int = 0,
                 by: str = "", trigger: str = "web", follow=None) -> dict:
    """The whole run: the runner, then (detailed with security) ZAP and Trivy, then collect. Returns {run_id, folder, code}."""
    say = follow or (lambda _m: None)
    with _lock:
        if current.get("busy"):
            raise RuntimeError(f"A self-test is going on already (run {current.get('run_id') or '?'}).")
        current.clear()
        current.update(busy=True, started=time.time(), run_id=run_id, level=level, suites=suites, by=by, stop="")
    folder = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + (f"-run{run_id}" if run_id else "")
    project = H["project"]() or "eaexplorer"
    name = f"{project}-testrunner"
    try:
        info = _api_container()
        image = runner_image(info)
        if not image_present(image):
            raise RuntimeError(f"The test runner image {image} is not built yet: run eax test once on this server.")
        os.makedirs(f"{WORK}/tests/{folder}", exist_ok=True)
        os.chmod(f"{WORK}/tests/{folder}", 0o777)
        current["folder"] = folder
        cmd = ["run", "--level", level, "--suites", ",".join(suites), "--trigger", trigger, "--folder", folder]
        for flag, value in (("--run-id", str(run_id) if run_id else ""), ("--by", by), ("--role", role), ("--area", area)):
            if value:
                cmd += [flag, value]
        if watch:
            cmd.append("--watch")
        cid = _start_runner(info, name, folder, cmd)
        current["container"] = cid
        code, out = _wait(cid, follow)
        m = re.search(r"RUN_ID=(\d+)", out)
        run_id = run_id or (int(m.group(1)) if m else 0)
        current["run_id"] = run_id
        with open(f"{WORK}/tests/{folder}/runner-output.log", "w", encoding="utf-8") as f:
            f.write(out)
        H["docker"]("rm", "-f", cid, timeout=60)
        if current.get("stop") and run_id:
            _collect(info, name, folder, run_id, ["--stopped", current["stop"]])
        elif level == "detailed" and "security" in suites and run_id and code == 0:
            _security_scans(info, folder, say)
            code = _collect(info, name, folder, run_id, [], follow)
        return {"run_id": run_id, "folder": folder, "code": code}
    except Exception as exc:  # noqa: BLE001 - closes the run as an error, with the reason, when it was recorded
        say(f"ERROR: {exc}")
        if run_id:
            try:
                _collect(_api_container(), name, folder, run_id, ["--error", str(exc)[:1500]])
            except Exception:  # noqa: BLE001, S110
                pass
        return {"run_id": run_id, "folder": folder, "code": 1, "error": str(exc)}
    finally:
        with _lock:
            current.update(busy=False, finished=time.time())


def _collect(info: dict, name: str, folder: str, run_id: int, extra: list[str], follow=None) -> int:
    cid = _start_runner(info, name, folder, ["collect", "--run-id", str(run_id), *extra])
    code, _ = _wait(cid, follow)
    H["docker"]("rm", "-f", cid, timeout=60)
    return code


def stop(body: dict) -> dict:
    """The runner sees the stop in the database at its next step and ends; if it is in a long step (a scan), it is
    removed after a minute and the run closed as stopped."""
    by = str(body.get("by") or "someone")
    if not current.get("busy"):
        return {"message": "No self-test is running here."}
    current["stop"] = by

    def later() -> None:
        time.sleep(60)
        cid = current.get("container")
        if current.get("busy") and cid:
            try:
                H["docker"]("rm", "-f", cid, timeout=60)
            except RuntimeError:
                pass
    threading.Thread(target=later, daemon=True).start()
    return {"message": "Stopping: the runner ends at its next step."}


def start(body: dict) -> dict:
    """POST /tests from the API: at once, in the background; the Self-test page follows the run in the database."""
    suites = suites_of(body.get("suites"))
    if current.get("busy"):
        raise RuntimeError(f"A self-test is going on already (run {current.get('run_id') or '?'}).")
    threading.Thread(target=run_sequence, kwargs={
        "level": "detailed" if body.get("level") == "detailed" else "smoke", "suites": suites, "role": str(body.get("role") or ""),
        "area": str(body.get("area") or ""), "watch": bool(body.get("watch")), "run_id": int(body.get("run_id") or 0),
        "by": str(body.get("by") or ""), "trigger": "web"}, daemon=True).start()
    return {"run_id": int(body.get("run_id") or 0), "suites": suites, "message": "The self-test is starting."}


def _opt(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else ""


def cli(args: list[str]) -> int:
    """ops.py test [--smoke|--detailed] [--suite S]... [--role R] [--area A] [--version V] [--ci]"""
    level = "detailed" if "--detailed" in args else "smoke"
    picked = [args[i + 1] for i, a in enumerate(args) if a in ("--suite", "--suites") and i + 1 < len(args)]
    picked += [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in
               ("--suite", "--suites", "--role", "--area", "--version"))]
    try:
        suites = suites_of(",".join(picked))
    except ValueError as exc:
        print(exc)
        return 2
    role, area = _opt(args, "--role"), _opt(args, "--area")
    if picked and level == "smoke":
        level = "detailed"                            # choosing suites means the detailed tests
    print(f"Self-test now: {level}" + ("" if level == "smoke" else f" ({', '.join(suites)})") + (f", role {role}" if role else "")
          + (f", area {area}" if area else "") + ". It makes its own self_test_<id>_<n> models, project and accounts and tests "
          "in them; nothing else changes. Results: System admin > Self-test, and work/tests.", flush=True)
    r = run_sequence(level, suites, role, area, False, by="eax test", trigger="ci" if "--ci" in args else "eax",
                     follow=lambda line: print(line, flush=True))
    if r.get("error"):
        print(f"The self-test could not finish: {r['error']}")
        return 1
    print(f"Self-test {r['run_id']} {'passed' if r['code'] == 0 else 'FAILED'}. Report: work/tests/{r['folder']}/report.html",
          flush=True)
    return 0 if r["code"] == 0 else 1
