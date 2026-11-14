"""`eax measure`: how much memory EA Explorer needs, measured in one go (Release 3.5, R3.5-M1; owner, 14 Nov 2026:
"can we not build a script for it that I need to run which opens stuff and does everything automatically checks status
etc and then runs what is needed"; "This will be great it can be used on production etc").

It runs the steps below one after the other, each an ordinary eax command, checks each one's result, stops with the
reason and the command to carry on (--from N) when one fails, and ends with one summary (work/footprint/measure-*.md):

  1 restart    only when asked: --restart (stop and start, data kept) or --clean-restart (DELETES everything and starts
               fresh: a laptop only, refused anywhere else)
  2 start-up   after a restart: every container's memory for 20 minutes while the content loads
  3 snapshot   eax footprint: image, disk and memory now
  4 smoke      eax test smoke, then checks the run was measured (its memory.md)
  5 at-rest    10 minutes, nobody using it
  6 using-it   20 minutes while people use it (on a laptop the browser is opened for you; on a server, its real users)
  7 full       eax test full while it is used (a laptop by default; a server only with --full, and the restore part asked
               first there, as restores stop the services)
  8 summary    each situation's peak and average, paging, the biggest containers, beside the guide (10 GB, not a limit)

Safe on a running installation: it only reads and measures, except the restart asked for and the tests, which work in
their own test data. Ctrl+C stops it; --from N carries on from a step.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import webbrowser
from datetime import UTC, datetime
from pathlib import Path

from .core import ROOT, setting

WORK = ROOT / "work"
FOOT = WORK / "footprint"
TESTS = WORK / "tests"
PROGRESS = FOOT / "measure-progress.json"
MINUTES = {"start-up": 20, "at-rest": 10, "using-it": 20}
NAMES = ["restart", "start-up", "snapshot", "smoke", "at-rest", "using-it", "full", "summary"]


def argv_for(line: list[str]) -> list[str]:
    """An eax command in the form of eax that started this one (ps1, sh or Python)."""
    from .screen import argv_for as _argv
    return _argv(line)


def deployment() -> str:
    return (setting("EAX_DEPLOYMENT", "laptop") or "laptop").lower()


def address() -> str:
    h, p = setting("EAX_HOSTNAME", "localhost"), setting("EAX_HTTPS_PORT", "443")
    return f"https://{h}{'' if p == '443' else ':' + p}/"


def parse(args: list[str]) -> dict:
    """The choices: --restart | --clean-restart, --full, --unattended (nobody there: no browser, no waiting for use),
    --use-minutes N, --from N, --yes (no question first)."""
    o = {"restart": "", "full": False, "unattended": False, "use_minutes": MINUTES["using-it"], "from": 1, "yes": False}
    it = iter(args)
    for a in it:
        if a in ("--restart", "--clean-restart"):
            o["restart"] = a[2:]
        elif a == "--full":
            o["full"] = True
        elif a == "--unattended":
            o["unattended"] = True
        elif a == "--yes":
            o["yes"] = True
        elif a in ("--use-minutes", "--from"):
            v = next(it, "")
            if not v.isdigit():
                raise ValueError(f"{a} takes a number")
            o["use_minutes" if a == "--use-minutes" else "from"] = int(v)
        else:
            raise ValueError(f"Not known: {a} (see eax help measure)")
    return o


def plan(o: dict, kind: str) -> list[dict]:
    """The steps for these choices on this deployment: {n, name, what, line, skip}."""
    laptop = kind == "laptop"
    if o["restart"] == "clean-restart" and not laptop:
        raise ValueError(f"--clean-restart deletes every database: refused on a {kind} installation. Use --restart "
                         "(data kept), or leave it out to measure it as it is.")
    full = o["full"] or laptop
    use = o["use_minutes"]
    steps = [
        ("restart", f"eax {o['restart'] or 'restart'}" + (" (DELETES everything, starts fresh)" if o["restart"] == "clean-restart" else " (data kept)"),
         [o["restart"]] if o["restart"] else None, "" if o["restart"] else "no restart asked for (--restart or --clean-restart)"),
        ("start-up", f"memory for {MINUTES['start-up']} minutes while it starts and loads",
         ["footprint", "--watch", str(MINUTES["start-up"]), "start-up"], "" if o["restart"] else "only after a restart"),
        ("snapshot", "one snapshot: image, disk and memory now", ["footprint", "snapshot"], ""),
        ("smoke", "the smoke test, measured", ["test", "smoke"], ""),
        ("at-rest", f"memory for {MINUTES['at-rest']} minutes, nobody using it", ["footprint", "--watch", str(MINUTES["at-rest"]), "at-rest"], ""),
        ("using-it", f"memory for {use} minutes while it is used" + ("" if o["unattended"] else (" (the browser opens: use it)" if laptop else " (its users at work)")),
         ["footprint", "--watch", str(use), "using-it"], "unattended: nobody to use it" if o["unattended"] and laptop else ""),
        ("full", "the full test, measured" + ("" if o["unattended"] else ", while you use it"),
         ["test", "full"] + (["--yes"] if laptop else []), "" if full else "a server: only with --full"),
        ("summary", "the summary", None, ""),
    ]
    return [{"n": i + 1, "name": n, "what": w, "line": line, "skip": skip} for i, (n, w, line, skip) in enumerate(steps)]


def newest_run(after: float) -> Path | None:
    runs = [p for p in TESTS.glob("*") if p.is_dir() and p.stat().st_mtime >= after] if TESTS.is_dir() else []
    return max(runs, key=lambda p: p.name) if runs else None


def measured(after: float) -> Path | None:
    """The memory table of the newest self-test run since `after`, if it was measured."""
    run = newest_run(after)
    return run / "memory.json" if run and (run / "memory.json").exists() else None


def watches(after: float) -> list[dict]:
    """The memory watches kept since `after` (work/footprint/*-memory.json), and the self-test runs' ones."""
    out = []
    for f in sorted(FOOT.glob("*-memory.json")) if FOOT.is_dir() else []:
        if f.stat().st_mtime >= after:
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return out


def situation(label: str) -> str:
    lab = label.lower()
    for key, name in (("start-up", "Starting up"), ("at-rest", "At rest"), ("using-it", "In use"), ("smoke", "Smoke test"),
                      ("detailed", "Full test"), ("full", "Full test")):
        if key in lab:
            return name
    return label or "Watched"


def summary(found: list[dict], kind: str) -> str:
    """One table: each situation's peak, average, paging and its three biggest containers, beside the guide."""
    gb = lambda mb: f"{mb / 1024:.1f}"  # noqa: E731
    guide = found[0]["target_mb"] if found else 10240
    lines = [f"# EA Explorer memory, measured {datetime.now(UTC).strftime('%d %b %Y %H:%M')} UTC ({kind})", "",
             f"`eax measure` (R3.5-M1). The guide: {gb(guide)} GB on a laptop (not a limit). Paging: the Docker host's swap grew.", "",
             "| Situation | Peak GB | Average GB | Paged | Least left GB | Biggest at its peak |", "|---|---:|---:|---|---:|---|"]
    worst = None
    for m in found:
        h = m.get("host") or {}
        top = ", ".join(f"{r['container']} {gb(r['peak_mb'])}" for r in (m.get("containers") or [])[:3])
        lines.append(f"| {situation(m.get('label', ''))} | {gb(m['total_peak_mb'])} | {gb(m['total_average_mb'])} | "
                     f"{'**yes**' if h.get('paged') else 'no' if h else '-'} | {gb(h['least_available_mb']) if h else '-'} | {top} |")
        if worst is None or m["total_peak_mb"] > worst["total_peak_mb"]:
            worst = m
    if worst:
        h = worst.get("host") or {}
        lines += ["", f"**Highest: {gb(worst['total_peak_mb'])} GB ({situation(worst.get('label', ''))})**, "
                      f"{'within' if worst['total_peak_mb'] <= guide else 'above'} the guide of {gb(guide)} GB"
                  + (f"; the Docker host has {gb(h['total_mb'])} GB" if h else "") + "."]
        if any((m.get("host") or {}).get("paged") for m in found):
            lines.append("**It paged**: memory ran short at some point; see which situation above.")
    lines += ["", "Each watch in full: work/footprint/*-memory.md; each test run's: work/tests/<run>/memory.md.", ""]
    return "\n".join(lines)


def resume(args: list[str], n: int) -> str:
    """The command that carries on from step n with the same choices (the steps before n are not run again)."""
    keep, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "--from":
            skip = True
            continue
        keep.append(a)
    return " ".join(["eax measure", *keep, "--from", str(n)])


def save_progress(state: dict) -> None:
    FOOT.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(state, indent=1), encoding="utf-8")


def load_progress() -> dict:
    try:
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main(args: list[str], run=subprocess.call, ask=input, open_browser=webbrowser.open, out=print, now=time.time) -> int:
    try:
        o = parse(args)
        kind = deployment()
        steps = plan(o, kind)
    except ValueError as exc:
        out(f"ERROR: {exc}")
        return 2
    todo = [s for s in steps if s["n"] >= o["from"]]
    out(f"eax measure on this {kind} installation ({address()}): how much memory it needs (R3.5-M1).")
    for s in steps:
        mark = "skip" if s["skip"] else ("done" if s["n"] < o["from"] else f"{s['n']}")
        out(f"  {mark:>4}  {s['name']:<9} {s['what']}" + (f"  [{s['skip']}]" if s["skip"] else ""))
    if not o["yes"]:
        answer = ask("Start? Type yes: ").strip().lower()
        if answer != "yes":
            out("Nothing done.")
            return 1
    state = load_progress() if o["from"] > 1 else {}
    started = state.get("started") or now()
    save_progress({"started": started, "kind": kind, "args": args})
    for s in todo:
        if s["skip"]:
            continue
        out(f"\n=== Step {s['n']} of {len(steps)}: {s['name']}: {s['what']}")
        if s["name"] == "summary":
            text = summary(watches(started), kind)
            FOOT.mkdir(parents=True, exist_ok=True)
            name = FOOT / f"measure-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.md"
            name.write_text(text, encoding="utf-8")
            out(text)
            out(f"Kept in {name.relative_to(ROOT)}. Tell Claude \"measured\" for the suggested limits.")
            continue
        if s["name"] in ("using-it", "full") and not o["unattended"] and kind == "laptop":
            out(f"Opening {address()}: use EA Explorer as you normally do (models, grids, reports, drawn views, an import).")
            try:
                open_browser(address())
            except Exception:  # noqa: BLE001 - the address is printed anyway
                pass
        t0 = now()
        code = run(argv_for(s["line"]), cwd=str(ROOT))
        if code != 0:
            out(f"\nStep {s['n']} ({s['name']}) did not finish (exit code {code}). Put it right, then carry on with: "
                f"{resume(args, s['n'])}")
            return code or 1
        if s["name"] in ("smoke", "full"):
            mem = measured(t0 - 5)
            if not mem:
                out(f"\nStep {s['n']} ({s['name']}): the test ran but was not measured (no memory.json in its folder in "
                    "work/tests): the operations helper may be older than this eax. Run eax restart, then: "
                    f"{resume(args, s['n'])}")
                return 1
            out(f"Measured: {mem.parent.relative_to(ROOT)}/memory.md")
    try:
        PROGRESS.unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

