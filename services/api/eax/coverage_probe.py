"""Code coverage of the API while it is tested (D642; owner, 13 Nov 2026: "In testing can we get code coverage? If so
then build it").

  EAX_COVERAGE=on      each API worker measures which lines of EA Explorer's own code run (coverage.py), from its start,
                       saved every 30 seconds into EAX_COVERAGE_DIR (default /tmp/eax-coverage, in the container)
  off (default)        nothing is measured; it costs nothing

The self-test reads the report at its end (GET /api/v1/admin/coverage): the share of lines run, by file and by area, and
keeps it in its run's folder (coverage.json and coverage.html) and as a result line. Measured since the API started, so
after `eax clean-restart` and one full self-test it is that test's coverage. Measuring slows the API a little (about a
fifth): on for test installations (the laptop template), off on servers. The unit tests' own coverage: pytest --cov
(requirements-dev.txt; CI runs it).
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

ON = ("on", "1", "true", "yes")
PACKAGE = str(Path(__file__).resolve().parent)
_cov: dict = {"c": None}


def enabled() -> bool:
    return (os.environ.get("EAX_COVERAGE") or "off").strip().lower() in ON


def folder() -> Path:
    return Path(os.environ.get("EAX_COVERAGE_DIR") or "/tmp/eax-coverage")


def start() -> bool:
    """In each worker before EA Explorer's modules are imported (eax/wsgi.py). True when measuring."""
    if not enabled() or _cov["c"] is not None:
        return False
    try:
        import coverage
    except ImportError:
        return False
    folder().mkdir(parents=True, exist_ok=True)
    c = coverage.Coverage(data_file=str(folder() / ".coverage"), data_suffix=True, source=[PACKAGE],
                          omit=[f"{PACKAGE}/testing/*"])
    c.start()
    _cov["c"] = c

    def keep():
        while True:
            time.sleep(30)
            save()
    threading.Thread(target=keep, daemon=True, name="eax-coverage").start()
    atexit.register(save)
    return True


def save() -> None:
    c = _cov["c"]
    if c is not None:
        try:
            c.save()
        except Exception:  # noqa: BLE001 - a measurement never breaks a request
            pass


def area_of(path: str) -> str:
    """eax/api/models.py -> api; eax/repository.py -> core; eax/testing/... is left out."""
    rel = path.split("eax/", 1)[-1]
    return rel.split("/", 1)[0] if "/" in rel else "core"


def summarise(files: dict) -> dict:
    """A coverage.py JSON report's files -> the totals, each area and the files least covered."""
    rows, areas = [], {}
    run = total = 0
    for name, f in files.items():
        s = f.get("summary") or {}
        n, hit = int(s.get("num_statements") or 0), int(s.get("covered_lines") or 0)
        if not n:
            continue
        short = "eax/" + name.split("eax/", 1)[-1]
        rows.append({"file": short, "lines": n, "run": hit, "percent": round(hit / n * 100, 1)})
        a = areas.setdefault(area_of(short), {"area": area_of(short), "lines": 0, "run": 0})
        a["lines"] += n
        a["run"] += hit
        run += hit
        total += n
    for a in areas.values():
        a["percent"] = round(a["run"] / a["lines"] * 100, 1) if a["lines"] else 0.0
    rows.sort(key=lambda r: (r["percent"], -r["lines"]))
    return {"on": True, "percent": round(run / total * 100, 1) if total else 0.0, "lines": total, "run": run,
            "areas": sorted(areas.values(), key=lambda a: a["percent"]), "files": rows, "at": time.time()}


def report() -> dict:
    """Every worker's measurement so far, combined, as a summary (the workers' own files are kept)."""
    if not enabled():
        return {"on": False, "why": "Code coverage is off: set EAX_COVERAGE=on in the config file and restart (eax up)."}
    try:
        import coverage
    except ImportError:
        return {"on": False, "why": "coverage.py is not installed in this image."}
    save()
    work = Path(tempfile.mkdtemp(prefix="eax-cov-"))
    try:
        for f in folder().glob(".coverage*"):
            shutil.copy(f, work / f.name)
        c = coverage.Coverage(data_file=str(work / ".coverage"))
        c.combine([str(work)], keep=False)
        c.save()
        out = work / "coverage.json"
        c.json_report(outfile=str(out), ignore_errors=True)
        import json
        return summarise(json.loads(out.read_text(encoding="utf-8")).get("files") or {})
    except Exception as exc:  # noqa: BLE001 - no data yet (nothing run since the start)
        return {"on": True, "percent": None, "why": f"No coverage data yet ({exc})."}
    finally:
        shutil.rmtree(work, ignore_errors=True)
