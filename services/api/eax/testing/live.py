"""Watching a self-test as it runs (R3.2; owner, 13 Nov 2026: "When running test can we have the name of test being
executed with what it is testing. There should also be a window where someone can watch what is happening"; decided: the
window watches and can Stop the whole run, no per-step controls).

One snapshot, asked for again and again by the watch window (Self-test › a run › Watch) and by `eax test watch`:

  run       its state, the step now running (the runner's own line: what it is checking) and whether a stop was asked
  tally     the counts so far; progress: how many are left, roughly
  results   each check recorded since the last snapshot (after=<result id>): suite, name, outcome, why, how long
  failures  every failure so far with its reason (the newest first)
  log       run.log from byte `from` on (at most LOG_CHUNK bytes) and where to read on next time

Read only: nothing here changes a run (Stop is the existing POST /tests/<run>/stop)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

from . import store

LOG_CHUNK = 64_000
RESULTS_MAX = 500
FAILURES_MAX = 50

LogReader = Callable[[str, int], tuple[str, int]]       # (folder, from byte) -> (text, next byte)


def file_log_reader(root) -> LogReader:
    """run.log under root/<folder>, read from a byte on (a line cut at the chunk's end is read again next time)."""
    from pathlib import Path

    def read(folder: str, start: int) -> tuple[str, int]:
        if not folder:
            return "", start
        path = Path(root) / folder / "run.log"
        try:
            with open(path, "rb") as f:
                f.seek(max(0, start))
                raw = f.read(LOG_CHUNK)
        except OSError:
            return "", start
        if len(raw) == LOG_CHUNK and b"\n" in raw:
            raw = raw[:raw.rindex(b"\n") + 1]
        return raw.decode("utf-8", "replace"), max(0, start) + len(raw)
    return read


def snapshot(conn, run_id: int, after: int = 0, log_from: int = 0, read_log: LogReader | None = None) -> dict[str, Any] | None:
    """What a watcher sees now; None when there is no such run."""
    run = store.run_row(conn, run_id)
    if not run:
        return None
    rows = conn.execute(text("""SELECT id, suite, name, outcome, detail, duration_ms FROM tests.test_results
                                 WHERE run_id = :r AND id > :a ORDER BY id LIMIT :n"""),
                        {"r": run_id, "a": int(after or 0), "n": RESULTS_MAX}).mappings().all()
    fails = conn.execute(text("""SELECT id, suite, name, detail FROM tests.test_results
                                  WHERE run_id = :r AND outcome = 'failed' ORDER BY id DESC LIMIT :n"""),
                         {"r": run_id, "n": FAILURES_MAX}).mappings().all()
    t = store.tally(conn, run_id)
    done = sum(t.values())
    log, nxt = (read_log or (lambda _f, s: ("", s)))(run.get("folder") or "", int(log_from or 0))
    return {
        "run": {"id": run["id"], "state": run["state"], "step": run.get("step") or "", "stop_asked": run.get("stop_asked"),
                "level": run.get("level"), "suites": list(run.get("suites") or []), "started_at": str(run.get("started_at") or "")},
        "open": run["state"] in store.OPEN,
        "tally": t,
        "progress": store.progress(conn, run, done),
        "results": [{**dict(r), "detail": (r["detail"] or "")[:400]} for r in rows],
        "after": rows[-1]["id"] if rows else int(after or 0),
        "failures": [{**dict(r), "detail": (r["detail"] or "")[:400]} for r in fails],
        "log": log, "log_next": nxt,
    }


def line_for(r: dict) -> str:
    """One result as `eax test watch` prints it."""
    o = r["outcome"].upper()
    why = f": {str(r['detail']).splitlines()[0][:140]}" if r["outcome"] in ("failed", "warning", "skipped") and r.get("detail") else ""
    return f"  {o:<8}{r['suite']:<9}{r['name'][:110]}{why}"


def follow(get: Callable[[int, int], dict | None], out=print, every: float = 2.0, sleep=time.sleep,
           show_log: bool = False, max_rounds: int | None = None) -> str:
    """`eax test watch`: prints each new result (and the log with --log) and the step whenever it changes, until the run
    ends; returns its final state ('' when there is no such run). Ctrl+C stops watching, not the run."""
    after, log_at, step, rounds = 0, 0, None, 0
    while True:
        s = get(after, log_at)
        if s is None:
            out("No such self-test run.")
            return ""
        if s["run"]["step"] != step:
            step = s["run"]["step"]
            if step:
                out(f"> {step}")
        if show_log and s["log"]:
            out(s["log"].rstrip("\n"))
        for r in s["results"]:
            out(line_for(r))
        after, log_at = s["after"], s["log_next"]
        if not s["open"]:
            t = s["tally"]
            out(f"Self-test {s['run']['id']} {s['run']['state']}: {t.get('passed', 0)} passed, {t.get('failed', 0)} failed, "
                f"{t.get('warning', 0)} warnings, {t.get('skipped', 0)} skipped")
            return s["run"]["state"]
        rounds += 1
        if max_rounds is not None and rounds >= max_rounds:
            return s["run"]["state"]
        sleep(every)
