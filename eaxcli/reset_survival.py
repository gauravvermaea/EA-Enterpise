"""The reset-survival test (owner, 10 Nov 2026, D561): settings in persist/ outlive a real reset.

`eax test --reset-survival --confirm <installation name>` (or the Self-test page's opt-in tick, through the Command
centre's runner, Super Admins only): it writes markers into persist/ (a schedule that is off, self_test_<run>, and a
banner marker for admins only, both changing nothing), notes every persist/ file's checksum, runs the real
`eax clean-restart`, which deletes every database and the work folder, waits for EA Explorer to answer again, then
checks the markers and the files are still there byte for byte, removes the markers and keeps the result in
persist/test-results/<run>.json and .log (a reset cannot delete them). It deletes all data: never part of a smoke
or the default detailed run.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from . import commands as C
from . import persist
from . import schedules as S

FILES = ("schedules.json", "banner.json")


def results_dir(root: Path) -> Path:
    return persist.folder(root) / "test-results"


def _sums(root: Path) -> dict[str, str]:
    """A checksum of every file in persist/ but the test's own results (which this run writes to)."""
    base = persist.folder(root)
    out = {}
    if base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_file() and "test-results" not in p.parts and not p.name.endswith((".bak", ".tmp")) and ".tmp" not in p.name:
                out[str(p.relative_to(base))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def place_markers(root: Path, run: str) -> None:
    items, _ = S.load(root)
    items = [s for s in items if not str(s.get("name", "")).startswith(f"self_test_{run}")]
    now = datetime.now(S.zone(root)).isoformat(timespec="seconds")
    items.append({"id": f"st{run[-4:]}", "name": f"self_test_{run}", "argv": ["status"], "cron": "0 4 * * *",
                  "enabled": False, "created_by": "self-test", "created_at": now, "checked": now, "wipe": False,
                  "backup_first": False, "keep": 1, "banner": False, "confirmed": None, "last": {}, "self_test": run})
    S.save(items, root)
    from . import banner as B
    data, _ = B.load(root)
    data["self_test_marker"] = {"run": run, "text": f"self_test_{run}", "audience": "admins", "enabled": False, "at": now}
    persist.write_json(B.path(root), {**data, "version": persist.VERSION})


def check_markers(root: Path, run: str) -> list[tuple[str, bool, str]]:
    from . import banner as B
    items, warn_s = S.load(root)
    data, warn_b = B.load(root)
    sched = any(s.get("name") == f"self_test_{run}" for s in items)
    ban = (data.get("self_test_marker") or {}).get("run") == run
    return [("the marker schedule is still there", sched, warn_s or ""),
            ("the marker banner is still there", ban, warn_b or "")]


def remove_markers(root: Path, run: str) -> None:
    items, _ = S.load(root)
    S.save([s for s in items if s.get("name") != f"self_test_{run}"], root)
    from . import banner as B
    data, _ = B.load(root)
    if (data.get("self_test_marker") or {}).get("run") == run:
        data.pop("self_test_marker", None)
        persist.write_json(B.path(root), {**data, "version": persist.VERSION})


def _write(root: Path, run: str, rec: dict) -> None:
    persist.write_json(results_dir(root) / f"{run}.json", rec)


def run(root: Path, reset, wait_back, log=print, run_id: str | None = None, strict: bool = False) -> dict:
    """The test, with the reset and the wait given (the real ones: eaxpy clean-restart and the API answering; tests
    pass simulated ones). Returns the result kept in persist/test-results/<run>.json. strict: schedules.json and
    banner.json must be byte for byte the same too (on a live installation the scheduler may record a run in
    schedules.json once EA Explorer is back, so there the markers are checked instead)."""
    root = Path(root)
    run_id = run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rec = {"version": 1, "_comment": "A reset-survival test (D561): settings in persist/ outlive a real reset.",
           "id": run_id, "kind": "reset-survival", "started": datetime.now(S.zone(root)).isoformat(timespec="seconds"),
           "state": "running", "checks": []}
    _write(root, run_id, rec)

    def check(name: str, ok: bool, note: str = "") -> None:
        rec["checks"].append({"name": name, "result": "passed" if ok else "failed", "note": note})
        log(f"  {'passed' if ok else 'FAILED'}: {name}{(' (' + note + ')') if note else ''}")

    place_markers(root, run_id)
    before = _sums(root)
    log(f"Markers written (self_test_{run_id}); {len(before)} file(s) in persist/ noted. Resetting now (clean-restart) ...")
    code = reset()
    check("the reset (eax clean-restart) finished", code == 0, f"exit code {code}")
    back = wait_back()
    check("EA Explorer answers again after the reset", bool(back), "" if back else "it did not come back in time")
    after = _sums(root)
    changed = [f for f in before if after.get(f) != before[f] and (strict or f not in FILES)]
    check("every file in persist/ survived byte for byte", not changed, ", ".join(changed[:10]))
    for name, ok, note in check_markers(root, run_id):
        check(name, ok, note)
    gone = not (root / "work" / "eaexplorer.env.self-test-marker").exists()
    check("the work folder was emptied by the reset", gone)
    remove_markers(root, run_id)
    rec.update(state="passed" if all(c["result"] == "passed" for c in rec["checks"]) else "failed",
               ended=datetime.now(S.zone(root)).isoformat(timespec="seconds"))
    _write(root, run_id, rec)
    log(f"Reset-survival test {rec['state']}: {sum(c['result'] == 'passed' for c in rec['checks'])} of {len(rec['checks'])} checks passed.")
    return rec


def history(root: Path) -> list[dict]:
    out = []
    d = results_dir(root)
    if d.is_dir():
        for p in d.glob("*.json"):
            data, _ = persist.read_json(p, {})
            if data.get("kind") == "reset-survival":
                out.append(data)
    return sorted(out, key=lambda r: r.get("started") or "", reverse=True)


def main(root: Path, args: list[str]) -> int:
    """eax test --reset-survival --confirm <installation name> [--yes]: from the page (EAX_COMMAND_RUN set, confirmed
    there) the --confirm is not asked again."""
    name = C.installation_name(root)
    if not os.environ.get("EAX_COMMAND_RUN"):
        typed = args[args.index("--confirm") + 1] if "--confirm" in args and args.index("--confirm") + 1 < len(args) else ""
        if typed != name:
            print(f"This runs a real clean-restart: it DELETES every database and the work folder. Add --confirm {name}")
            return 2
    kind = persist._config_value(root, "EAX_DEPLOYMENT") or "laptop"
    marker = root / "work" / "eaexplorer.env.self-test-marker"          # in work/: the reset must delete it
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("deleted by the reset\n", encoding="utf-8")
    log_path = results_dir(root)
    log_path.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    with open(log_path / f"{run_id}.log", "a", encoding="utf-8") as logf:
        def log(text: str) -> None:
            print(text, flush=True)
            logf.write(text + "\n")
            logf.flush()

        def reset() -> int:
            return subprocess.call([sys.executable, str(root / "eaxpy.py"), "clean-restart", kind], cwd=root,
                                   stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

        def wait_back() -> bool:
            for _ in range(60):                      # up to 10 minutes after clean-restart's own wait
                if subprocess.call([sys.executable, str(root / "eaxpy.py"), "status"], cwd=root, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL) == 0:
                    return True
                time.sleep(10)
            return False

        rec = run(root, reset, wait_back, log, run_id)
    return 0 if rec["state"] == "passed" else 1
