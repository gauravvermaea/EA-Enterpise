"""Whether a self-test run is still being run (R2.64; owner, 13 Nov 2026: a run killed by `eax up` stayed "Running" for
good, and Stop could not end it).

Whoever is running a run touches `.alive` in its folder (work/tests/<folder>) every EVERY seconds: the runner itself
(eax.testing.run, in the test runner's container or the always-on runner service) and the operations helper while it
waits for the runner, runs the security scans and collects (services/ops/testruns.py, which keeps its own copy of these
few lines because it does not import this package). A run marked running whose `.alive` is older than STALE seconds,
and which started more than GRACE seconds ago, has no one running it: store.close_orphans closes it as stopped, with
the reason. Nothing is written to the database for the heartbeat itself (D248: no logic in the database)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

BEAT_FILE = ".alive"
EVERY = 20          # seconds between beats
STALE = 180         # seconds without a beat: no one is running it
GRACE = 300         # seconds after it started before a missing beat counts (the runner is still starting)


def results_root() -> Path:
    """work/tests as this container sees it: the API reads it at /eax-work/tests (read only)."""
    return Path(os.environ.get("EAX_TESTS_FOLDER", "/eax-work/tests"))


def beat(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / BEAT_FILE).write_text(str(int(time.time())), encoding="utf-8")
    except OSError:
        pass                                    # a heartbeat never stops the run


def keep_beating(folder: Path, stop: threading.Event | None = None) -> threading.Event:
    """Beats in the background until `stop` is set or the process ends."""
    stop = stop or threading.Event()

    def loop() -> None:
        while not stop.is_set():
            beat(folder)
            stop.wait(EVERY)
    threading.Thread(target=loop, daemon=True, name="selftest-heartbeat").start()
    return stop


def last_beat(folder: Path) -> float | None:
    try:
        return (folder / BEAT_FILE).stat().st_mtime
    except OSError:
        return None


def is_orphan(folder: Path | None, started: float | None, now: float | None = None) -> bool:
    """True when no one has run it for STALE seconds and it started more than GRACE seconds ago."""
    now = time.time() if now is None else now
    if started is not None and now - started < GRACE:
        return False
    seen = last_beat(folder) if folder is not None else None
    return seen is None or now - seen > STALE
