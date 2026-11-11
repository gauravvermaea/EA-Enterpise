"""The self-test's browser journeys (phase 36.1, D367, D524, D529): the main journeys through the screens, in the run's
own fixtures, signed in as the run's test accounts.

Two ways, the same journeys (journeys()):
  * **headless on the server** (the default): Chromium in the test runner opens the installation's own screens through
    the front door (the proxy container, reached by its Docker name: the public host name is mapped to it inside the
    browser), each journey in its own context with a video; a failed one keeps a screenshot and its video;
  * **watched in the admin's own browser** (Self-test > Watch it in this browser): the Self-test page opens the same
    screens in a frame of its own and drives them (TestRuns.jsx), recording each journey with the browser's name and
    version; no extension is needed.
Either way the screens are opened with ?eaxselftest=<ticket>&eaxrole=<role>: the app then signs in with the run's own
token for that role (auth.js, D529) instead of Keycloak, so the admin's sign-in is never used and the journeys can only
see and change what the role may: the run's own fixtures (and read standard screens)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

Record = Callable[..., None]


def base_url() -> str:
    explicit = os.environ.get("EAX_TEST_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    host, port = os.environ.get("EAX_HOSTNAME", "localhost"), os.environ.get("EAX_HTTPS_PORT", "443")
    return f"https://{host}" + ("" if port == "443" else f":{port}")


def journeys(ids: dict[str, str], role: str = "") -> list[dict]:
    """[{name, role, steps: [{route, expect}]}]: each step opens a route and waits for its text (empty: the page settles).
    With a role, each journey runs as that role."""
    m, p = ids.get("model", ""), ids.get("project", "")
    out = [
        {"name": "sign in and the start page", "role": "architect", "steps": [{"route": "#/", "expect": "Start"}]},
        {"name": "a model: overview, grid and quality", "role": "model-admin",
         "steps": [{"route": f"#/metamodel/{m}", "expect": ids.get("model_name", "")}, {"route": f"#/metamodel/{m}/grid", "expect": ""},
                   {"route": f"#/metamodel/{m}/quality", "expect": "Quality"}]},
        {"name": "the models list", "role": "architect", "steps": [{"route": "#/models", "expect": "Models"}]},
        {"name": "System admin: health and machine access", "role": "super-admin",
         "steps": [{"route": "#/admin/health", "expect": "Health"}, {"route": "#/admin/machine-access", "expect": "Machine access"}]},
    ]
    if p:
        out.insert(2, {"name": "a project and its tasks", "role": "super-admin",
                       "steps": [{"route": f"#/projects/{p}", "expect": ids.get("project_name", "")}, {"route": f"#/projects/{p}/tasks", "expect": ""}]})
    if not m:
        out = [j for j in out if "model:" not in j["name"]]
    if role:
        out = [{**j, "role": role} for j in out]
    return out


def run(ids: dict[str, str], ticket: str, folder: Path, record: Record, role: str = "", only: list[str] | None = None) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        record("browser journeys", "skipped", "Playwright is not in this image (the test runner image has it)", 0)
        return
    base = base_url()
    host = base.split("//", 1)[1].split("/")[0].split(":")[0]
    proxy = os.environ.get("EAX_TEST_PROXY_HOST", "proxy")
    videos = folder / "videos"
    videos.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=[f"--host-resolver-rules=MAP {host} {proxy}, MAP *.{host} {proxy}"])
        version = f"Chromium {browser.version} (headless, on the server)"
        for j in journeys(ids, role):
            if only and j["name"] not in only:
                continue
            t0 = time.time()
            ctx = browser.new_context(ignore_https_errors=True, record_video_dir=str(videos), viewport={"width": 1400, "height": 900})
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
            page.on("response", lambda r, errs=errors: errs.append(f"{r.request.method} {r.url.split('?')[0]}: {r.status}")
                    if "/api/" in r.url and r.status >= 500 else None)
            outcome, detail, shot = "passed", "", None
            try:
                for step in j["steps"]:
                    page.goto(f"{base}/?eaxselftest={ticket}&eaxrole={j['role']}{step['route']}", wait_until="domcontentloaded",
                              timeout=60000)
                    page.wait_for_selector("text=EA Explorer", timeout=60000)
                    if step["expect"]:
                        page.wait_for_selector(f"text={step['expect']}", timeout=30000)
                    page.wait_for_timeout(1500)
                if errors:
                    outcome, detail = "failed", "; ".join(errors[:20])
                else:
                    detail = f"{len(j['steps'])} page(s) as {j['role']}"
            except Exception as exc:  # noqa: BLE001 - a journey that breaks is a failed journey
                outcome = "failed"
                detail = str(exc).splitlines()[0][:500] + (f"; also: {'; '.join(errors[:5])}" if errors else "")
            if outcome == "failed":
                try:
                    shot = page.screenshot(full_page=False)
                except Exception:  # noqa: BLE001
                    shot = None
            video = page.video.path() if page.video else None
            ctx.close()
            kept = ""
            if video:
                v = Path(video)
                if outcome == "failed":
                    kept = f"{''.join(c if c.isalnum() else '-' for c in j['name'])[:60]}.webm"
                    v.rename(videos / kept)
                else:
                    v.unlink(missing_ok=True)
            record(f"journey: {j['name']}", outcome, detail, int((time.time() - t0) * 1000), screenshot=shot,
                   video=f"videos/{kept}" if kept else "", browser=version)
        browser.close()
