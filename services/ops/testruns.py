"""Test runs started by the operations helper (phase 36.1, D367, D523, D525).

The helper has Docker, so it starts the test runner (image eaexplorer/testrunner:<version>, built by `eax test` or
`docker compose --profile test build testrunner`) with the api container's settings on the backend and frontend
networks, and, for the security suite, an OWASP ZAP baseline scan of the front door and Trivy scans of EA Explorer's
images next to it; then the runner reads their reports (collect) and closes the run. Files: work/tests/<folder>.

  GET  /tests                   whether the runner image is there, the run going on (if any)
  POST /tests                   {run_id, level, suites, role, area, watch, by}: start a run the API has recorded (Self-test)
  POST /tests/stop              {run_id, by}: stop it (the runner ends at its next step; if it does not, it is removed)
  POST /tests/build             {by, then?}: build the runner image (`eax test --build` in the Command centre's
                                short-lived container, D554), then start `then` (a run the API recorded) if given (D570)
  GET  /tests/build/<id>?from=  the build's record, its log from byte `from` and its steps
  POST /tests/settings          {auto_build, by}: build it automatically after each start or update (persist/settings.json)
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


NOT_BUILT = ("The test runner is prepared when a test starts (the first time about 1.5 GB, 5 to 15 minutes); "
             "nothing to do by hand.")


def status() -> dict:
    extra = {"build": build_status(), "auto_build": auto_build(_deployment()), "size_gb": RUNNER_SIZE_GB,
             "build_minutes": BUILD_MINUTES}
    try:
        image = runner_image()
        present = image_present(image)
    except RuntimeError as exc:
        return {"image": "", "image_present": False, "running": dict(current), "message": str(exc), **extra}
    return {"image": image, "image_present": present, "running": dict(current),
            "message": "" if present else NOT_BUILT, **extra}


# ---------------------------------------------------------------- building the runner from the page (D570)
RUNNER_SIZE_GB = 1.5
BUILD_MINUTES = [5, 15]
SETTINGS = "settings.json"                     # in persist/ (D558): {"testrunner_auto_build": true|false, ...}
AUTO_KEY = "testrunner_auto_build"
BUILD_STEPS = (("base", "Base image (python:3.12-slim)"), ("python", "Python packages"),
               ("chromium", "Chromium for the browser tests"), ("scanners", "Scanners (pip-audit)"),
               ("code", "EA Explorer's code"))
build_state: dict = {}                         # {busy, run_id, by, then, started, state, reason}


def _persist():
    try:
        from eaxcli import persist
        return persist
    except Exception:  # noqa: BLE001 - an older compose file without the eaxcli mount
        return None


def _deployment() -> str:
    try:
        return H["_values"](H["_read_config"]()).get("EAX_DEPLOYMENT", "")
    except Exception:  # noqa: BLE001
        return ""


def auto_build(deployment: str = "") -> bool:
    """Build the runner automatically after each start or update: persist/settings.json, else on everywhere (owner,
    11 Nov 2026, D584: a test right after a start should not wait for the build; about 1.5 GB of disk)."""
    default = True
    P = _persist()
    if P is None:
        return default
    data, _warn = P.read_json(P.folder() / SETTINGS, {})
    value = data.get(AUTO_KEY)
    return default if value is None else bool(value)


def set_auto_build(on: bool, by: str = "") -> dict:
    P = _persist()
    if P is None:
        raise RuntimeError("persist/ is not reachable from the operations helper (docker-compose.yml mounts it).")
    path = P.folder() / SETTINGS
    data, _warn = P.read_json(path, {"version": P.VERSION})
    data.update({AUTO_KEY: bool(on), f"{AUTO_KEY}_by": by or "?",
                 f"{AUTO_KEY}_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    P.write_json(path, data)
    return {"auto_build": bool(on)}


def build_steps(log: str, finished: bool = False, ok: bool = False) -> list[dict]:
    """The build's steps from its plain log: base (FROM / load metadata), then the EAX-STEP markers the Dockerfile
    echoes; each step before the last seen is done; the last is running until the build ends."""
    seen = []
    if re.search(r"load metadata for|FROM docker\.io|\[1/\d+\] FROM", log):
        seen.append("base")
    for m in re.finditer(r"EAX-STEP (\w+)", log):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    out, last = [], seen[-1] if seen else ""
    for key, label in BUILD_STEPS:
        if key not in seen:
            state = "done" if finished and ok else "waiting"
        elif key != last or (finished and ok):
            state = "done"
        else:
            state = "failed" if finished and not ok else "running"
        out.append({"key": key, "label": label, "state": state})
    return out


def _reason(log: str) -> str:
    lines = [x for x in log.splitlines() if x.strip() and not x.startswith("[finished")]
    bad = [x for x in lines if re.search(r"error|failed|denied|no space|could not|not found", x, re.IGNORECASE)]
    return (bad[-1] if bad else (lines[-1] if lines else "The build stopped without a message."))[-400:]


def build_status() -> dict:
    """The build going on or the last one (from this helper's memory, else the Command centre's history)."""
    st = dict(build_state)
    if not st.get("run_id"):
        try:
            last = [r for r in H["commandcentre"].history(100) if (r.get("argv") or [])[:2] == ["test", "--build"]]
        except Exception:  # noqa: BLE001
            last = []
        if not last:
            return {}
        r = last[0]
        st = {"run_id": r["id"], "by": r.get("by"), "busy": r.get("state") == "running",
              "state": {"done": "done", "running": "running"}.get(r.get("state"), "failed")}
    st.pop("then", None)
    return st


def build_detail(run_id: str, start: int = 0) -> dict:
    d = H["commandcentre"].detail(run_id, 0)
    rec = d["status"]
    log = d["text"]
    finished = rec.get("state") != "running" and not d.get("running")
    ok = finished and rec.get("exit_code") == 0
    return {"status": rec, "text": log[max(0, start):], "next": len(log.encode()) if start == 0 else d["next"],
            "steps": build_steps(log, finished, ok), "finished": finished, "ok": ok,
            "reason": "" if ok or not finished else _reason(log)}


def build(body: dict) -> dict:
    """Start `eax test --build` in the Command centre's short-lived container (it has the installation folder and
    Docker); `then` (a run the API recorded) starts when the image is there."""
    by, then = str(body.get("by") or "someone"), body.get("then") or None
    cc = H["commandcentre"]
    with _lock:
        if build_state.get("busy"):
            if then:
                build_state["then"] = then
            return {k: v for k, v in build_state.items() if k != "then"}
        run_id = cc._new_id("testbuild")
        cc._launch(["test", "--build"], by, run_id, env={"BUILDKIT_PROGRESS": "plain"})
        build_state.clear()
        build_state.update(busy=True, run_id=run_id, by=by, then=then, started=time.time(), state="running", reason="")
    threading.Thread(target=_after_build, args=(run_id,), daemon=True).start()
    return {"run_id": run_id, "busy": True, "state": "running",
            "message": "Building the test runner: about 1.5 GB, 5 to 15 minutes."}


def _after_build(run_id: str) -> None:
    cc = H["commandcentre"]
    time.sleep(5)
    while cc._container(run_id):
        time.sleep(5)
    try:
        d = build_detail(run_id)
        ok, reason = d["ok"], d["reason"]
    except Exception as exc:  # noqa: BLE001
        ok, reason = False, str(exc)
    if ok:
        try:
            ok = image_present(runner_image())
            reason = "" if ok else "The build ended but the image for this version is not there."
        except RuntimeError as exc:
            ok, reason = False, str(exc)
    with _lock:
        then = build_state.get("then")
        build_state.update(busy=False, state="done" if ok else "failed", reason=reason, finished=time.time(), then=None)
    if then and ok:
        try:
            start(then)
        except Exception as exc:  # noqa: BLE001
            print(f"ops: the self-test after the build did not start ({exc})", flush=True)
    elif then and then.get("run_id"):
        try:
            api = _api_container()                       # the runner is not there: the api's own copy closes the run
            H["docker"]("exec", "-e", "EAX_TEST_RESULTS=/tmp/eax-test-results", api["Id"], "python", "-m", "eax.testing",
                        "collect", "--run-id", str(int(then["run_id"])),
                        "--error", f"The test runner could not be built: {reason}"[:1500], timeout=300)
        except Exception as exc:  # noqa: BLE001
            print(f"ops: could not close run {then.get('run_id')} ({exc})", flush=True)


def auto_build_loop() -> None:
    """When the setting is on: build the runner in the background after start-up (and so after an update, which
    starts this helper again), and whenever the image for the running version is missing; looked at every 15 minutes."""
    time.sleep(120)                           # let the stack come up first
    while True:
        try:
            gave_up = build_state.get("state") == "failed" and build_state.get("by") == "automatic build"
            if (auto_build(_deployment()) and not gave_up and not build_state.get("busy") and not current.get("busy")
                    and not image_present(runner_image()) and not H["commandcentre"].busy()):
                print("ops: building the test runner (automatic build is on)", flush=True)
                build({"by": "automatic build"})
        except Exception as exc:  # noqa: BLE001 - the API not up yet, Docker busy: try again later
            print(f"ops: automatic test-runner build skipped ({exc})", flush=True)
        time.sleep(900)


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
                 by: str = "", trigger: str = "web", follow=None, journeys: list[str] | None = None,
                 pages_only: bool = False) -> dict:
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
            raise RuntimeError(f"The test runner image {image} is not there: start the test again (it prepares the runner first).")
        os.makedirs(f"{WORK}/tests/{folder}", exist_ok=True)
        os.chmod(f"{WORK}/tests/{folder}", 0o777)
        current["folder"] = folder
        cmd = ["run", "--level", level, "--suites", ",".join(suites), "--trigger", trigger, "--folder", folder]
        for flag, value in (("--run-id", str(run_id) if run_id else ""), ("--by", by), ("--role", role), ("--area", area)):
            if value:
                cmd += [flag, value]
        if watch:
            cmd.append("--watch")
        for j in journeys or []:                       # one browser journey only (D577)
            cmd += ["--journey", j]
        if pages_only:
            cmd.append("--pages-only")
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
        "by": str(body.get("by") or ""), "trigger": "web", "journeys": [str(j) for j in body.get("journeys") or []][:20],
        "pages_only": bool(body.get("pages_only"))}, daemon=True).start()
    return {"run_id": int(body.get("run_id") or 0), "suites": suites, "message": "The self-test is starting."}


def _opt(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else ""


def cli(args: list[str]) -> int:
    """ops.py test [--smoke|--detailed] [--suite S]... [--role R] [--area A] [--journey J]... [--pages-only] [--version V] [--ci]"""
    level = "detailed" if "--detailed" in args else "smoke"
    picked = [args[i + 1] for i, a in enumerate(args) if a in ("--suite", "--suites") and i + 1 < len(args)]
    picked += [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in
               ("--suite", "--suites", "--role", "--area", "--version", "--journey"))]
    try:
        suites = suites_of(",".join(picked))
    except ValueError as exc:
        print(exc)
        return 2
    role, area = _opt(args, "--role"), _opt(args, "--area")
    journeys = [args[i + 1] for i, a in enumerate(args) if a == "--journey" and i + 1 < len(args)]
    pages_only = "--pages-only" in args
    if journeys or pages_only:                        # a journey or the page sweep: the browser suite, detailed (D577)
        suites, level = ["ui"], "detailed"
    if picked and level == "smoke":
        level = "detailed"                            # choosing suites means the detailed tests
    print(f"Self-test now: {level}" + ("" if level == "smoke" else f" ({', '.join(suites)})") + (f", role {role}" if role else "")
          + (f", area {area}" if area else "") + ". It makes its own self_test_<id>_<n> models, project and accounts and tests "
          "in them; nothing else changes. Results: System admin > Self-test, and work/tests.", flush=True)
    r = run_sequence(level, suites, role, area, False, by="eax test", trigger="ci" if "--ci" in args else "eax",
                     follow=lambda line: print(line, flush=True), journeys=journeys, pages_only=pages_only)
    if r.get("error"):
        print(f"The self-test could not finish: {r['error']}")
        return 1
    print(f"Self-test {r['run_id']} {'passed' if r['code'] == 0 else 'FAILED'}. Report: work/tests/{r['folder']}/report.html",
          flush=True)
    return 0 if r["code"] == 0 else 1
