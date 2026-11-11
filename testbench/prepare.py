"""The test bench prepares what it needs by itself (owner, 11 Nov 2026, D584): no separate steps.

Before a run it makes sure that:
  * testbench/data is there and as built (python -m testbench.data build, else it is rebuilt here);
  * the browsers asked for are installed for Playwright (python -m playwright install <browser>; quick when they are
    there). Microsoft Edge is a program of its own: when it is missing the run says so and skips it.
It says what it is doing; nothing here ever stops a run: what cannot be prepared is reported and skipped later.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

INSTALLABLE = ("chromium", "firefox", "webkit")


def data(say: Callable[[str], None]) -> list[str]:
    """Rebuilds testbench/data when a file is missing or differs; returns the names rebuilt."""
    from .data import build as B  # noqa: PLC0415
    wrong = B.check()
    if wrong:
        say(f"Preparing the test data: {len(wrong)} file(s) missing or changed, rebuilding testbench/data...")
        B.build()
    return wrong


def browsers(names: list[str], say: Callable[[str], None], runner=subprocess.run) -> dict[str, str]:
    """python -m playwright install for each browser asked for (Edge: not installed by us). {browser: ok|failed|edge}."""
    out: dict[str, str] = {}
    wanted = [n for n in names if n in INSTALLABLE]
    if wanted:
        say(f"Preparing the browsers ({', '.join(wanted)}): quick when they are installed, a few minutes the first time...")
        r = runner([sys.executable, "-m", "playwright", "install", *wanted], capture_output=True, text=True, timeout=1800)
        for n in wanted:
            out[n] = "ok" if r.returncode == 0 else "failed"
        if r.returncode != 0:
            say("  Could not install the browsers: " + ((r.stderr or r.stdout or "").strip().splitlines() or ["?"])[-1][:200])
    if "msedge" in names:
        out["msedge"] = "edge"
        say("  Microsoft Edge is used as installed on this computer (it is skipped, with the reason, when it is not there).")
    return out


def everything(names: list[str], ui: bool, say: Callable[[str], None]) -> dict:
    """What a run needs: the data always, the browsers when the browser suite runs."""
    got: dict = {"data": [], "browsers": {}}
    try:
        got["data"] = data(say)
    except Exception as exc:  # noqa: BLE001 - reported; the journeys that need a file then fail with the reason
        say(f"  Could not rebuild testbench/data: {exc}")
    if ui:
        try:
            got["browsers"] = browsers(names, say)
        except Exception as exc:  # noqa: BLE001
            say(f"  Could not prepare the browsers: {exc}")
    return got
