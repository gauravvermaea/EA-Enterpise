"""The load test (D582): `eax testbench load --users 200 --minutes 10`, with k6 (https://k6.io) and the scenarios in
testbench/load/scenarios.js. Chosen over a Python fallback so the numbers come from one tool everywhere (CI and
laptops); when k6 is missing the bench says how to get it and the load test is skipped, never faked.

Reported: p50, p95 and p99 response times, the error rate and the throughput (requests a second); judged against
testbench/thresholds.json (k6 is told the same marks, so its own exit code agrees)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "scenarios.js"
DATA = HERE / "data.json"
THRESHOLDS = HERE.parent / "thresholds.json"

HOW_TO_GET_K6 = ("k6 is not on this machine. Get it from https://grafana.com/docs/k6/latest/set-up/install-k6/ "
                 "(Windows: winget install k6 --source winget; macOS: brew install k6; Linux: the k6 package or the "
                 "single binary from https://github.com/grafana/k6/releases), then run the load test again.")


def thresholds(path: Path = THRESHOLDS) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def judge(summary: dict, marks: dict) -> dict:
    """k6's --summary-export JSON -> the load result: p50/p95/p99 (ms), error rate, throughput, what broke."""
    m = summary.get("metrics") or {}
    d = m.get("http_req_duration") or {}
    d = d.get("values", d)                                  # k6 0.x puts the values at the top, newer ones under values
    f = m.get("http_req_failed") or {}
    f = f.get("values", f)
    r = m.get("http_reqs") or {}
    r = r.get("values", r)
    out = {"p50_ms": round(float(d.get("med", 0)), 1), "p95_ms": round(float(d.get("p(95)", 0)), 1),
           "p99_ms": round(float(d.get("p(99)", 0)), 1),
           "error_rate": round(float(f.get("rate", f.get("value", 0)) or 0), 4),
           "rps": round(float(r.get("rate", 0)), 1), "requests": int(r.get("count", 0))}
    broken = []
    for k in ("p50_ms", "p95_ms", "p99_ms"):
        if k in marks and out[k] > marks[k]:
            broken.append(f"{k[:-3]} {out[k]} ms > {marks[k]} ms")
    if "error_rate" in marks and out["error_rate"] > marks["error_rate"]:
        broken.append(f"errors {out['error_rate'] * 100:.2f}% > {marks['error_rate'] * 100:.2f}%")
    if "min_rps" in marks and out["rps"] < marks["min_rps"]:
        broken.append(f"throughput {out['rps']}/s < {marks['min_rps']}/s")
    out["broken"], out["failed"] = broken, bool(broken)
    out["summary"] = (f"p50 {out['p50_ms']} ms, p95 {out['p95_ms']} ms, p99 {out['p99_ms']} ms, errors "
                      f"{out['error_rate'] * 100:.2f}%, {out['rps']} requests/s" + (f"; broken: {'; '.join(broken)}" if broken else ""))
    return out


def command(target: str, tokens: list[str], model: str, users: int, minutes: float, folder: Path, insecure: bool,
            marks: dict) -> tuple[list[str], dict]:
    env = {"TARGET": target, "TOKENS": ",".join(tokens), "MODEL": model or "", "USERS": str(users),
           "MINUTES": str(minutes), "THRESHOLDS": json.dumps(marks), "DATA": str(DATA), "INSECURE": "1" if insecure else "0"}
    argv = ["k6", "run", "--quiet", "--summary-export", str(folder / "k6-summary.json"), str(SCRIPT)]
    return argv, env


def run(run, target: str, tokens: list[str], model: str, users: int, minutes: float, insecure: bool = False,
        which=shutil.which, runner=subprocess.run) -> dict:
    marks = thresholds()
    rec = run.recorder("load")
    if not which("k6"):
        rec("load test (k6)", "skipped", HOW_TO_GET_K6, 0)
        run.load = {"summary": "skipped: k6 is not on this machine", "skipped": True}
        return run.load
    folder = Path(run.folder)
    argv, env = command(target, tokens, model, users, minutes, folder, insecure, marks)
    run.log(f"load: {users} virtual users for {minutes} minutes with k6")
    p = runner(argv, env={**os.environ, **env}, capture_output=True, text=True, timeout=int(minutes * 60) + 600)
    (folder / "k6.log").write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    summary_file = folder / "k6-summary.json"
    if not summary_file.exists():
        rec("load test (k6)", "failed", f"k6 wrote no summary (exit code {p.returncode}): {(p.stderr or '')[-400:]}", 0)
        run.load = {"summary": "k6 failed", "failed": True, "broken": ["k6 wrote no summary"]}
        return run.load
    out = judge(json.loads(summary_file.read_text(encoding="utf-8")), marks)
    out.update(users=users, minutes=minutes, thresholds=marks)
    rec("load test (k6)", "failed" if out["failed"] else "passed", out["summary"], int(minutes * 60000))
    run.load = out
    return out
