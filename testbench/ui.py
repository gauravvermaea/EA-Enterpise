"""The browser suite from outside, in every browser asked for (D579): the self-test's own page sweep
(eax/testing/ui_pages.sweep) and journeys (eax/testing/ui_flows), signed in with the run's ticket as the self-test does
(?eaxselftest=<ticket>&eaxrole=<role>). Chromium, Firefox, WebKit (Safari's engine) and Edge (Chromium's msedge
channel, where Edge is installed)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import shared

BROWSERS = ("chromium", "firefox", "webkit", "msedge")
LABEL = {"chromium": "Chromium", "firefox": "Firefox", "webkit": "WebKit (Safari's engine)", "msedge": "Microsoft Edge"}


def clean_browsers(text: str | list[str] | None) -> list[str]:
    items = text if isinstance(text, list) else (text or "chromium").replace(";", ",").split(",")
    out: list[str] = []
    for b in (x.strip().lower() for x in items):
        if not b:
            continue
        b = {"edge": "msedge", "safari": "webkit", "chrome": "chromium"}.get(b, b)
        if b == "all":
            return list(BROWSERS)
        if b not in BROWSERS:
            raise ValueError(f"Unknown browser '{b}': choose from {', '.join(BROWSERS)} (or all).")
        if b not in out:
            out.append(b)
    return out or ["chromium"]


def launch(pw, name: str):
    """(browser, label) or raises with why it cannot start here."""
    if name == "msedge":
        b = pw.chromium.launch(channel="msedge")
    else:
        b = getattr(pw, name).launch()
    return b, f"{LABEL[name]} {b.version} (headless, test bench)"


def run(run, target: str, ticket: str, ids: dict[str, str], browsers: list[str], role: str = "", smoke: bool = False,
        journeys: list[str] | None = None, pages_only: bool = False) -> dict[str, int]:
    """Runs the sweep and the journeys in each browser; records into run.recorder("ui", browser) and returns counts
    (also kept by browser: "<browser> pages", "<browser> journeys")."""
    ui_pages, ui_flows = shared.module("ui_pages"), shared.module("ui_flows")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        run.recorder("ui")("browser", "skipped", "Playwright is not installed here: pip install -r testbench/requirements.txt "
                                                 "and python -m playwright install", 0)
        return {}
    app = os.environ.get("EAX_TESTBENCH_APP_PATH", "/")          # a preview build serves the app at /app.html
    try:
        headers = json.loads(os.environ.get("EAX_TESTBENCH_HEADERS") or "{}")   # a preview's stand-in sign-in
    except ValueError:
        headers = {}
    videos = Path(run.folder) / "videos"
    videos.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with sync_playwright() as pw:
        for name in browsers:
            try:
                browser, label = launch(pw, name)
            except Exception as exc:  # noqa: BLE001 - a browser missing on this machine is skipped, with why
                run.recorder("ui")(f"browser {LABEL[name]}", "skipped",
                                   f"cannot start here: {str(exc).splitlines()[0][:200]} (python -m playwright install {name if name != 'msedge' else 'msedge'})", 0)
                continue
            if label not in run.browsers:
                run.browsers.append(label)
            rec = run.recorder("ui", label)
            run.log(f"browser: {label}")

            def context(as_role: str, video: bool = True, b=browser):
                ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1400, "height": 900},
                                    extra_http_headers=headers or None,
                                    **({"record_video_dir": str(videos)} if video else {}))
                page = ctx.new_page()
                page.on("dialog", lambda d: d.accept())

                def open_route(route: str, r=as_role) -> None:
                    page.goto(f"{target}{app}?eaxselftest={ticket}&eaxrole={r}{route}", wait_until="domcontentloaded", timeout=60000)
                return ctx, page, open_route

            if not journeys:                                     # every page, group, tab and sub-tab
                s_ctx, s_page, s_open = context(role or "super-admin", video=False)
                pc = ui_pages.sweep(s_page, s_open, ids, rec, role=role or "super-admin")
                s_ctx.close()
                for k, v in pc.items():
                    counts[f"{name} pages {k}"] = v
            if not pages_only:                                   # the journeys that click, type and save
                def factory(as_role: str, ctx_of=context, b_name=name):
                    ctx, page, open_route = ctx_of(as_role)

                    def close(outcome: str, c=ctx, p=page) -> str:
                        video = p.video.path() if p.video else None
                        c.close()
                        if not video:
                            return ""
                        v = Path(video)
                        if outcome == "failed":
                            kept = f"{b_name}-journey-{int(time.time() * 1000)}.webm"
                            v.rename(videos / kept)
                            return f"videos/{kept}"
                        v.unlink(missing_ok=True)
                        return ""
                    return page, open_route, close
                js = ui_flows.journeys(ids, role=role, only=journeys, smoke=smoke)
                jc = ui_flows.run(factory, js, rec)
                for k, v in jc.items():
                    counts[f"{name} journeys {k}"] = v
            browser.close()
    return counts
