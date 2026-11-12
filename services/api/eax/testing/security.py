"""Basic security tests (phase 36.1, D367, D525).

Run by the runner: the security headers and cookies of the front door (the proxy, as people reach it) and of the
sign-in page, and the Python dependencies (pip-audit). Run by the operations helper next to the runner (they need
Docker): an OWASP ZAP baseline scan of the front door and Trivy scans of EA Explorer's images (which see the Python
packages in the API's image and the npm packages of the web image's lock file); the runner then reads their reports
(collect). Unauthenticated and cross-user access are tested in the API matrix (api_matrix.py)."""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

Record = Callable[[str, str, str, int], None]

# header: what a good value contains (lower case); None: only that it is there
HEADERS: list[tuple[str, str | None, str]] = [
    ("x-content-type-options", "nosniff", "failed"),
    ("referrer-policy", None, "failed"),
    ("strict-transport-security", "max-age", "warning"),       # on a server (EAX_HSTS); a laptop may leave it out
    ("x-frame-options", None, "warning"),
    ("content-security-policy", None, "warning"),
]


def _get(url: str, host: str) -> tuple[int, dict[str, str], list[str]]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE           # the front door is reached by its container name inside Docker
    req = urllib.request.Request(url, headers={"Host": host, "User-Agent": "EA Explorer test runner"})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), _NoRedirect())
    try:
        r = opener.open(req, timeout=20)
        status, headers = r.status, r.headers
    except urllib.error.HTTPError as exc:
        status, headers = exc.code, exc.headers
    return status, {k.lower(): v for k, v in headers.items()}, headers.get_all("Set-Cookie") or []


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: ANN002, ANN003
        return None


def check_headers(headers: dict[str, str], where: str, record: Record) -> None:
    for name, want, bad in HEADERS:
        have = headers.get(name)
        if have is None and name == "strict-transport-security" and os.environ.get("EAX_DEPLOYMENT", "laptop") == "laptop":
            # off on a laptop on purpose (D107): its certificate is the laptop's own, so the browser warning must stay
            # possible to accept; a server sets EAX_HSTS
            record(f"{where}: header {name}", "passed", "off on a laptop by design (D107); a server sets EAX_HSTS", 0)
        elif have is None:
            record(f"{where}: header {name}", bad, "missing", 0)
        elif want and want not in have.lower():
            record(f"{where}: header {name}", bad, f"is {have!r}; expected it to contain {want!r}", 0)
        else:
            record(f"{where}: header {name}", "passed", have[:200], 0)
    server = headers.get("server", "")
    if any(ch.isdigit() for ch in server):
        record(f"{where}: server version hidden", "warning", f"Server header shows a version: {server}", 0)


def check_cookies(cookies: list[str], where: str, record: Record) -> None:
    if not cookies:
        record(f"{where}: cookies", "passed", "no cookie set", 0)
        return
    for c in cookies:
        name = c.split("=", 1)[0].strip()
        flags = [p.strip().lower() for p in c.split(";")[1:]]
        missing = [f for f in ("secure", "httponly") if not any(x.startswith(f) for x in flags)]
        same = next((x for x in flags if x.startswith("samesite")), "")
        if "secure" in missing:
            record(f"{where}: cookie {name}", "failed", "not marked Secure", 0)
        elif "httponly" in missing and not name.upper().startswith("KC_RESTART"):
            record(f"{where}: cookie {name}", "warning", "not HttpOnly (readable by the page's scripts)", 0)
        elif not same:
            record(f"{where}: cookie {name}", "warning", "no SameSite attribute", 0)
        else:
            record(f"{where}: cookie {name}", "passed", "; ".join(flags), 0)


def front_door(record: Record) -> None:
    """The front door's headers and the sign-in page's cookies, asked inside Docker of the proxy container."""
    host = os.environ.get("EAX_HOSTNAME", "localhost")
    proxy = os.environ.get("EAX_TEST_PROXY", "https://proxy")
    realm = os.environ.get("EAX_KEYCLOAK_REALM", "eaexplorer")
    try:
        _status, headers, _ = _get(f"{proxy}/", host)
        check_headers(headers, "front door", record)
        _status, headers, cookies = _get(f"{proxy}/auth/realms/{realm}/protocol/openid-connect/auth?client_id=eax-web"
                                         f"&response_type=code&scope=openid&redirect_uri=https%3A%2F%2F{host}%2F", host)
        check_cookies(cookies, "sign-in page", record)
    except (urllib.error.URLError, OSError) as exc:
        record("front door reachable", "failed", f"the proxy did not answer: {exc}", 0)


def python_dependencies(record: Record) -> None:
    """pip-audit of the API's requirements (needs the internet to read the advisory database)."""
    req = Path("/app/requirements.txt")
    if not req.exists():
        record("Python dependencies (pip-audit)", "skipped", "no requirements.txt in the runner", 0)
        return
    r = subprocess.run([sys.executable, "-m", "pip_audit", "-r", str(req), "--format", "json", "--progress-spinner", "off"],
                       capture_output=True, text=True, timeout=900)
    try:
        data = json.loads(r.stdout or "{}")
    except ValueError:
        record("Python dependencies (pip-audit)", "skipped", f"pip-audit could not run: {(r.stderr or '')[-500:]}", 0)
        return
    found = [(d["name"], d["version"], v["id"]) for d in data.get("dependencies", []) for v in d.get("vulns", [])]
    if found:
        record("Python dependencies (pip-audit)", "failed",
               "; ".join(f"{n} {ver}: {vid}" for n, ver, vid in found[:60]), 0)
    else:
        record("Python dependencies (pip-audit)", "passed", f"{len(data.get('dependencies', []))} packages, no known vulnerability", 0)


def read_zap(path: Path, record: Record) -> None:
    """The ZAP baseline report (zap.json): a High alert fails, Medium warns."""
    if not path.exists():
        record("OWASP ZAP baseline scan", "skipped", "no ZAP report (the scan did not run: see the run's log)", 0)
        return
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    alerts = [a for s in data.get("site", []) for a in s.get("alerts", [])]
    risk = lambda a: int(str(a.get("riskcode", "0")) or 0)  # noqa: E731
    high = [a for a in alerts if risk(a) >= 3]
    medium = [a for a in alerts if risk(a) == 2]
    if high:
        record("OWASP ZAP baseline scan", "failed", "High: " + "; ".join(a.get("alert", "") for a in high), 0)
    elif medium:
        record("OWASP ZAP baseline scan", "warning", "Medium: " + "; ".join(a.get("alert", "") for a in medium), 0)
    else:
        record("OWASP ZAP baseline scan", "passed", f"{len(alerts)} low or informational alerts", 0)


def read_trivy(folder: Path, record: Record) -> None:
    """Every trivy-*.json in the run's folder: one result per image; a CRITICAL vulnerability with a fix fails,
    HIGH warns."""
    files = sorted(folder.glob("trivy-*.json"))
    if not files:
        record("image and dependency scans (Trivy)", "skipped", "no Trivy report (the scan did not run: see the run's log)", 0)
        return
    for f in files:
        image = f.stem.removeprefix("trivy-")
        try:
            data = json.loads(f.read_text(encoding="utf-8") or "{}")
        except ValueError:
            record(f"image {image} (Trivy)", "skipped", "the report could not be read", 0)
            continue
        vulns = [v for r in data.get("Results") or [] for v in (r.get("Vulnerabilities") or [])]
        crit = [v for v in vulns if v.get("Severity") == "CRITICAL" and v.get("FixedVersion")]
        high = [v for v in vulns if v.get("Severity") in ("HIGH", "CRITICAL")]
        show = lambda vs: "; ".join(f"{v.get('PkgName')} {v.get('InstalledVersion')}: {v.get('VulnerabilityID')}"  # noqa: E731
                                    + (f" (fixed in {v['FixedVersion']})" if v.get("FixedVersion") else "") for v in vs[:40])
        if crit:
            record(f"image {image} (Trivy)", "failed", f"{len(crit)} critical with a fix: " + show(crit), 0)
        elif high:
            record(f"image {image} (Trivy)", "warning", f"{len(high)} high or critical: " + show(high), 0)
        else:
            record(f"image {image} (Trivy)", "passed", "no high or critical vulnerability", 0)
