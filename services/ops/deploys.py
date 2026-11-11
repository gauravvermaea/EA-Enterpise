"""Deployments started from System admin > Deploy (phase 36, D555 to D557): EA Explorer deploys itself to another place
(a server over SSH, or AWS, Azure or DigitalOcean) with the eax deploy steps (eaxcli/deploy.py). The laptop kind and
"this machine is the server" are not offered here: this installation is already running.

  GET  /deploys                       the runs (newest first), the deployer image, the kept credentials (names only)
  GET  /deploys/<id>                  one run: its state, steps, failure, result and log
  POST /deploys/questions             {answers}: the questions that apply (defaults filled), for the page
  POST /deploys                       {answers, secrets, ssh_key, keep, plan, use_kept, by}: start a run
  POST /deploys/<id>/decide           {choice: retry|back|quit}: the answer to a failed step
  POST /deploys/kept/<target>/forget  forget kept credentials

A plan runs here (it runs nothing); a deployment runs in a short-lived **deployer** container (deploy/deployer: ssh,
curl, git, aws, az, doctl), built from the release the first time, with only its run folder (work/deploys/<id>) and
the release's eaxcli and templates mounted. The run folder holds the state, so a page reload (or this helper
restarting) loses nothing. Secrets (the SSH private key, cloud credentials) are files readable by root only, deleted
when the run ends, or, when the person asked, moved to work/deploy-keep/<target> (root only) to be used again;
nothing ever sends them back. Bound to ops.py's helpers with bind(globals())."""

from __future__ import annotations

import json
import os
import re
import secrets as _secrets
import shutil
import subprocess
import sys
import threading
from datetime import UTC, datetime

H: dict = {}
REPO = "/eax-repo"
WORK = "/eax-work"
RUNS = f"{WORK}/deploys"
KEEP = f"{WORK}/deploy-keep"
SECRET_FIELDS = ("aws_access_key_id", "aws_secret_access_key", "do_token", "spaces_key", "spaces_secret",
                 "az_client_id", "az_client_secret", "az_tenant")
_lock = threading.Lock()


def bind(ns: dict) -> None:
    H.update(ns)


def _D():
    """eaxcli/deploy.py of this release (mounted read-only at /eax-repo/eaxcli)."""
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    from eaxcli import deploy
    return deploy


def _run_dir(run_id: str) -> str:
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{6}", run_id or ""):
        raise ValueError("No such deployment.")
    return f"{RUNS}/{run_id}"


def _text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _json(path: str):
    return json.loads(_text(path))


def _owner_only(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


def target_of(answers: dict) -> str:
    """The target's name: the address people open, else the SSH address, else the cloud and its name."""
    t = answers.get("hostname") or answers.get("ssh_target") or f"{answers.get('kind', '')}:{answers.get('name', '')}"
    return re.sub(r"[^A-Za-z0-9@._:-]", "-", str(t))[:120]


def _defaults() -> dict:
    """The repository link and this installation's version: the release a target gets unless the person changes it."""
    out = {}
    try:
        import updates
        out["repo"] = updates.settings().get("git_url", "")
    except Exception as exc:  # noqa: BLE001 - no repository link set yet: the person types it
        print(f"deploys: no repository link from the update settings ({exc})", flush=True)
    try:
        text = _text(f"{REPO}/services/api/version.toml")
        m = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
        if m:
            out["ref"] = f"v{m.group(1)}"
    except OSError:
        pass
    return out


def offered(answers: dict) -> dict:
    """The page's answers: never the laptop, never 'this machine is the server'."""
    a = {k: str(v) for k, v in (answers or {}).items() if v is not None}
    if a.get("kind") in ("", None, "laptop"):
        a["kind"] = "server"
    if a.get("kind") == "server":
        a["where"] = "ssh"
    return a


def questions(answers: dict) -> dict:
    D = _D()
    a = {**_defaults(), **offered(answers), "aws_profile": ""}     # no AWS profiles here: an access key
    merged = {**{q.key: q.default_for(a) for q in D.visible(a) if q.key not in a}, **a}
    qs = []
    for q in D.visible(merged):
        d = q.as_dict(merged)
        if merged.get(q.key) not in (None, ""):
            d["default"] = merged[q.key]                  # this installation's repository link and version
        if q.key == "kind":
            d["choices"] = {k: v for k, v in q.choices.items() if k != "laptop"}
        if q.key == "where":
            continue                                      # always over SSH from here
        if q.key == "ssh_key":
            d.update(text="SSH private key (paste it or choose the file; used for this deployment only unless kept)",
                     kind="key", default="", help="An OpenSSH private key without a passphrase. Never shown again.")
        if q.key == "aws_profile":
            continue                                      # no AWS profiles here: an access key
        if q.key == "tls_dir":
            continue                                      # an own certificate is put in place after (deployment.md)
        if q.key == "move_from":
            d["choices"] = {"empty": q.choices["empty"]}  # a backup folder is on the old machine, not here
        if q.key in SECRET_FIELDS or q.secret:
            d["secret"] = True
        qs.append(d)
    return {"questions": qs, "answers": merged}


def _split(answers: dict, given_secrets: dict) -> tuple[dict, dict]:
    a, s = {}, {}
    for k, v in answers.items():
        (s if k in SECRET_FIELDS else a)[k] = v
    for k, v in (given_secrets or {}).items():
        if k in SECRET_FIELDS and v:
            s[k] = str(v)
    a.pop("ssh_key", None)
    a["aws_profile"] = ""
    if a.get("tls") == "own":
        a["tls"] = "self-signed"
    a["move_from"] = "empty"
    return a, s


def start(body: dict) -> dict:
    D = _D()
    answers = offered({**_defaults(), **(body.get("answers") or {})})
    plan = bool(body.get("plan"))
    a, s = _split(answers, body.get("secrets") or {})
    key = str(body.get("ssh_key") or "")
    use_kept = str(body.get("use_kept") or "")
    if use_kept:
        kept = f"{KEEP}/{re.sub(r'[^A-Za-z0-9@._:-]', '-', use_kept)}"
        if not os.path.isdir(kept):
            raise ValueError("No credentials are kept for that target.")
        try:
            s = {**_json(f"{kept}/secrets.json"), **s}
        except (OSError, ValueError):
            pass
        if not key and os.path.exists(f"{kept}/ssh_key"):
            key = _text(f"{kept}/ssh_key")
    if not plan and not key.strip():
        raise ValueError("Give the SSH private key: the target is reached over SSH.")
    if key and "PRIVATE KEY" not in key:
        raise ValueError("That does not look like an SSH private key (it should start with -----BEGIN ... PRIVATE KEY-----).")
    a.setdefault("ssh_key", "/run/ssh_key")
    try:
        full = D.complete({**a, **s, "ssh_key": "/run/ssh_key"})
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    with _lock:
        running = [r for r in runs() if r["status"] in ("running", "failed") and not r.get("plan")]
        if running and not plan:
            raise RuntimeError(f"A deployment is running ({running[0]['target']}): finish or quit it first.")
        run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{_secrets.token_hex(3)}"
        folder = _run_dir(run_id)
        os.makedirs(f"{folder}/work", exist_ok=True)
        os.makedirs(f"{folder}/home", exist_ok=True)
        os.chmod(folder, 0o700)
        about = {"id": run_id, "target": target_of(full), "kind": full["kind"], "plan": plan,
                 "version": full.get("ref", ""), "by": str(body.get("by") or ""), "keep": bool(body.get("keep")),
                 "started": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        with open(f"{folder}/about.json", "w", encoding="utf-8") as f:
            json.dump(about, f)
        with open(f"{folder}/answers.json", "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in a.items() if k not in SECRET_FIELDS}, f)
        if s:
            _owner_only(f"{folder}/secrets.json", json.dumps(s))
        if key.strip():
            _owner_only(f"{folder}/ssh_key", key.strip() + "\n")
        with open(f"{folder}/state.json", "w", encoding="utf-8") as f:
            json.dump({"status": "running", "plan": plan, "steps": [], "failed": None, "result": {}}, f)
    if plan:
        _plan_here(folder)
    else:
        _start_deployer(run_id, folder)
    return about


def _plan_here(folder: str) -> None:
    """A plan runs nothing: run here, in this helper (python3 with the release's eaxcli)."""
    env = {**os.environ, "PYTHONPATH": REPO, "HOME": f"{folder}/home"}
    log = open(f"{folder}/runner.txt", "w", encoding="utf-8")  # noqa: SIM115 - handed to the process
    subprocess.Popen([sys.executable, "-m", "eaxcli.deploy_runner", folder, "--plan"], cwd=REPO, env=env,
                     stdout=log, stderr=subprocess.STDOUT)


def deployer_image() -> str:
    try:
        text = _text(f"{REPO}/services/api/version.toml")
        version = re.search(r'^version = "([^"]+)"', text, re.MULTILINE).group(1)
    except (OSError, AttributeError):
        version = "dev"
    return f"eaexplorer/deployer:{version}"


def image_present(image: str) -> bool:
    try:
        H["docker"]("image", "inspect", image)
        return True
    except Exception:  # noqa: BLE001
        return False


def _host_install() -> str:
    import updates
    return updates._me()["install"]


def _start_deployer(run_id: str, folder: str) -> None:
    """The deployer container: built the first time (deploy/deployer), then started with the run folder mounted."""
    def go():
        image = deployer_image()
        try:
            if not image_present(image):
                with open(f"{folder}/log.txt", "a", encoding="utf-8") as f:
                    f.write("Building the deployer image the first time (ssh and the cloud command-line tools; "
                            "5 to 10 minutes)...\n")
                subprocess.run(["docker", "build", "-t", image, f"{REPO}/deploy/deployer"], check=True,
                               capture_output=True, text=True, timeout=3600)
            install = _host_install()
            host_run = f"{install}/work/deploys/{run_id}"
            H["docker"]("run", "-d", "--rm", "--name", f"eax-deploy-{run_id}"[:60], "--label", "eax.deploy=" + run_id,
                        "-v", f"{host_run}:/run", "-v", f"{install}/eaxcli:/eax/eaxcli:ro",
                        "-v", f"{install}/deploy/templates:/eax/deploy/templates:ro",
                        "-v", f"{host_run}/work:/eax/work", "-e", "HOME=/run/home", "-w", "/eax",
                        image, "python", "-m", "eaxcli.deploy_runner", "/run")
        except Exception as exc:  # noqa: BLE001 - shown on the page as the run's failure
            msg = getattr(exc, "stderr", "") or str(exc)
            with open(f"{folder}/log.txt", "a", encoding="utf-8") as f:
                f.write(f"ERROR: the deployer could not start: {str(msg)[-1500:]}\n")
            with open(f"{folder}/state.json", "w", encoding="utf-8") as f:
                json.dump({"status": "quit", "plan": False, "steps": [], "failed": None, "result": {},
                           "error": "The deployer could not start: see the log."}, f)
    threading.Thread(target=go, daemon=True).start()


def _finish(folder: str, about: dict, state: dict) -> None:
    """Once a run has ended: its secrets deleted, or moved to the kept store when asked (never shown again)."""
    done = f"{folder}/finished"
    if os.path.exists(done) or state.get("status") in ("running", "failed"):
        return
    if about.get("keep") and not about.get("plan"):
        kept = f"{KEEP}/{about['target']}"
        os.makedirs(kept, exist_ok=True)
        os.chmod(KEEP, 0o700)
        for name in ("secrets.json", "ssh_key", "ssh_key.pub"):
            if os.path.exists(f"{folder}/{name}"):
                shutil.move(f"{folder}/{name}", f"{kept}/{name}")
                os.chmod(f"{kept}/{name}", 0o600)
    for name in ("secrets.json", "ssh_key", "ssh_key.pub"):
        try:
            os.remove(f"{folder}/{name}")
        except OSError:
            pass
    shutil.rmtree(f"{folder}/home", ignore_errors=True)
    shutil.rmtree(f"{folder}/work", ignore_errors=True)
    with open(done, "w", encoding="utf-8") as f:
        f.write(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))


def _read(folder: str) -> tuple[dict, dict]:
    try:
        about = _json(f"{folder}/about.json")
    except (OSError, ValueError):
        about = {}
    try:
        state = _json(f"{folder}/state.json")
    except (OSError, ValueError):
        state = {"status": "running", "steps": []}
    return about, state


def run(run_id: str, log_lines: int = 600) -> dict:
    folder = _run_dir(run_id)
    if not os.path.isdir(folder):
        raise ValueError("No such deployment.")
    about, state = _read(folder)
    _finish(folder, about, state)
    try:
        lines = _text(f"{folder}/log.txt").splitlines()[-log_lines:]
    except OSError:
        lines = []
    return {**about, **state, "lines": lines}


def runs(limit: int = 50) -> list[dict]:
    out = []
    try:
        names = sorted(os.listdir(RUNS), reverse=True)[:limit]
    except OSError:
        names = []
    for name in names:
        folder = f"{RUNS}/{name}"
        about, state = _read(folder)
        if not about:
            continue
        _finish(folder, about, state)
        out.append({**about, "status": state.get("status"), "finished": state.get("finished"),
                    "result": state.get("result") or {}, "failed": state.get("failed")})
    return out


def kept() -> list[str]:
    try:
        return sorted(os.listdir(KEEP))
    except OSError:
        return []


def forget(target: str) -> dict:
    path = f"{KEEP}/{re.sub(r'[^A-Za-z0-9@._:-]', '-', target)}"
    if not os.path.isdir(path):
        raise ValueError("No credentials are kept for that target.")
    shutil.rmtree(path)
    return {"forgotten": target}


def decide(run_id: str, choice: str) -> dict:
    if choice not in ("retry", "back", "quit"):
        raise ValueError("Choose retry, back or quit.")
    folder = _run_dir(run_id)
    _about, state = _read(folder)
    if state.get("status") != "failed":
        raise RuntimeError("That deployment is not waiting for an answer.")
    with open(f"{folder}/decision.json", "w", encoding="utf-8") as f:
        json.dump({"choice": choice}, f)
    return {"choice": choice}


def overview() -> dict:
    image = deployer_image()
    return {"runs": runs(), "kept": kept(), "image": image, "image_present": image_present(image) if H else False,
            "defaults": _defaults()}
