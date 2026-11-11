"""What a test bench run found: one result per check, as the self-test records them (suite, name, outcome, detail, ms,
browser, screenshot, video, request, response), and the coverage summary (D581)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

OUTCOMES = ("passed", "failed", "skipped", "warning")


@dataclass
class Result:
    suite: str
    name: str
    outcome: str
    detail: str = ""
    ms: int = 0
    browser: str = ""
    screenshot: bytes | None = None
    video: str = ""
    request: str = ""
    response: str = ""


@dataclass
class Run:
    """A test bench run: its results, counts for the coverage summary, and its folder (report, screenshots, videos)."""
    target: str
    folder: Path
    level: str = "smoke"
    suites: list[str] = field(default_factory=list)
    browsers: list[str] = field(default_factory=list)
    started: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"))
    results: list[Result] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    log_lines: list[str] = field(default_factory=list)
    platform_run: int | None = None
    version: str = ""
    load: dict = field(default_factory=dict)
    quiet: bool = False
    t0: float = field(default_factory=time.time)

    def __post_init__(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.dir = self.folder            # what the shared code calls a run's folder

    # --- the shared code's Run interface (eax/testing/run.py: log, recorder, counts, dir) -------------------------
    def log(self, msg: str) -> None:
        line = f"{datetime.now(UTC).strftime('%H:%M:%S')} {msg}"
        self.log_lines.append(line)
        if not self.quiet:
            print(line, flush=True)
        with open(self.folder / "run.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def recorder(self, suite: str, browser: str = ""):
        def record(name: str, outcome: str, detail: str = "", ms: int = 0, screenshot: bytes | None = None, video: str = "",
                   request: str = "", response: str = "", browser: str = browser, **_kw) -> None:
            if outcome not in OUTCOMES:
                outcome = "failed"
            self.results.append(Result(suite, name, outcome, str(detail or ""), int(ms or 0), browser or "", screenshot,
                                       video or "", request or "", response or ""))
            if not self.quiet:
                print(f"  {outcome.upper():<8}{suite:<9}{name}" + (f": {str(detail)[:160]}" if outcome in ("failed", "warning") else ""),
                      flush=True)
        return record

    # --- totals ----------------------------------------------------------------------------------------------------
    def tally(self) -> dict[str, int]:
        out = {o: 0 for o in OUTCOMES}
        for r in self.results:
            out[r.outcome] += 1
        out["total"] = len(self.results)
        return out

    @property
    def failed(self) -> bool:
        return any(r.outcome == "failed" for r in self.results) or bool(self.load.get("failed"))

    def coverage(self) -> list[tuple[str, str]]:
        """The coverage summary, as on the self-test's report: pages, journeys, endpoints, writes per area, database,
        security, browsers and load (D581)."""
        def n(pred) -> tuple[int, int]:
            rs = [r for r in self.results if pred(r)]
            return sum(r.outcome == "passed" for r in rs), len([r for r in rs if r.outcome != "skipped"])
        rows: list[tuple[str, str]] = []
        p, t = n(lambda r: r.suite == "ui" and r.name.startswith("page: "))
        if t:
            rows.append(("Pages opened (every browser)", f"{p} of {t}"))
        p, t = n(lambda r: r.suite == "ui" and r.name.startswith("journey: "))
        if t:
            rows.append(("Journeys passed (every browser)", f"{p} of {t}"))
        p, t = n(lambda r: r.suite == "api" and r.name.endswith(": without a token"))
        if t:
            rows.append(("Endpoints refused without a sign-in", f"{p} of {t}"))
        p, t = n(lambda r: r.suite == "api" and ("every test role" in r.name or ": as " in r.name))
        if t:
            rows.append(("Reads as every test role", f"{p} of {t}"))
        p, t = n(lambda r: r.suite == "api" and "cross-user" in r.name)
        if t:
            rows.append(("Cross-user refusals", f"{p} of {t}"))
        areas: dict[str, list[int]] = {}
        for r in self.results:
            if r.suite == "api" and r.name.startswith("write"):
                a = r.name.split(":", 1)[0].removeprefix("write").strip(" []") or "writes"
                areas.setdefault(a, [0, 0])
                areas[a][1] += r.outcome != "skipped"
                areas[a][0] += r.outcome == "passed"
        if areas:
            rows.append(("Writes tested, by area", ", ".join(f"{a} {p}/{t}" for a, (p, t) in sorted(areas.items()))))
        for suite, label in (("db", "Database checks"), ("security", "Security checks"), ("smoke", "Smoke checks")):
            p, t = n(lambda r, s=suite: r.suite == s)
            if t:
                rows.append((label, f"{p} of {t} passed"))
        if self.browsers:
            rows.append(("Browsers", ", ".join(self.browsers)))
        if self.load:
            rows.append(("Load", self.load.get("summary", "")))
        return rows
