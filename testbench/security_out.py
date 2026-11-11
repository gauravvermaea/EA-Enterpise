"""The security suite from outside (D581): the self-test's own checks (eax/testing/security.py), run from this machine:

  * the front door's headers and the sign-in page's cookies, at the public address (security.front_door);
  * pip-audit of the API's requirements, from this checkout (security.python_dependencies; needs pip-audit and internet);
  * an OWASP ZAP baseline scan of the target, when Docker is here (read by security.read_zap);
  * Trivy scans of EA Explorer's images, when trivy and the images are here (read by security.read_trivy).
What cannot run here is skipped, with why."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import shared

IMAGES = ("api", "web", "ops", "library", "views", "drawio")


def run(run, target: str, version: str, zap: bool = True, trivy: bool = True) -> None:
    security = shared.module("security")
    rec = run.recorder("security")
    run.log("security: headers and cookies at the front door")
    security.front_door(rec)
    req = shared.API_SRC / "requirements.txt"
    real_path = security.Path
    try:                                       # the shared check reads /app/requirements.txt (inside the runner)
        security.Path = lambda p, _r=req: _r if str(p) == "/app/requirements.txt" else real_path(p)
        try:
            import pip_audit  # noqa: F401, PLC0415
            run.log("security: Python dependencies (pip-audit)")
            security.python_dependencies(rec)
        except ImportError:
            rec("Python dependencies (pip-audit)", "skipped", "pip-audit is not installed here (pip install pip-audit)", 0)
    finally:
        security.Path = real_path
    folder = Path(run.folder)
    if zap:
        if shutil.which("docker"):
            run.log("security: OWASP ZAP baseline scan of the target (Docker)")
            out = folder / "zap.json"
            p = subprocess.run(["docker", "run", "--rm", "-v", f"{folder.resolve()}:/zap/wrk:rw", "-t",
                                "ghcr.io/zaproxy/zaproxy:stable", "zap-baseline.py", "-t", target, "-J", "zap.json", "-I"],
                               capture_output=True, text=True, timeout=1800)
            if out.exists():
                security.read_zap(out, rec)
            else:
                rec("OWASP ZAP baseline scan", "skipped", f"ZAP did not write a report: {(p.stderr or p.stdout)[-300:]}", 0)
        else:
            rec("OWASP ZAP baseline scan", "skipped", "Docker is not here (the scan runs the ZAP image)", 0)
    if trivy:
        if shutil.which("trivy"):
            run.log("security: Trivy scans of EA Explorer's images")
            for name in IMAGES:
                image = f"eaexplorer/{name}:{version or 'dev'}"
                out = folder / f"trivy-{name}.json"
                p = subprocess.run(["trivy", "image", "--quiet", "--format", "json", "--output", str(out), image],
                                   capture_output=True, text=True, timeout=1800)
                if p.returncode != 0:          # no image here, or no database: skipped, not "passed"
                    out.unlink(missing_ok=True)
                    rec(f"image {name} (Trivy)", "skipped", f"{image}: {(p.stderr or p.stdout or '').strip()[-300:]}", 0)
            if any(folder.glob("trivy-*.json")):
                security.read_trivy(folder, rec)
        else:
            rec("image scans (Trivy)", "skipped", "trivy is not here (https://trivy.dev); the self-test runs it inside", 0)
