"""Test results by importance, and the installation's functional health (R2.35, owner, 12 Nov 2026: "Mark tests critical
and non critical and provide a ring chart showing how many fail and provide a overall category of functional health").

Every check is **critical** or **non-critical**, from its suite and name (so a new check is placed the day it is added):
  critical      what the application must do: signing in and the smoke checks; the database's integrity; reading as each
                role and being refused where one must be; every write (creating, editing, committing, deleting, merging,
                importing, analyses); the pages opening; the journeys
  non-critical  what is worth fixing but leaves the application working: security findings (headers, packages and
                images), speed hints (an index), a page's look (no heading, no F1 help: a warning)
The **functional health** of the run:
  Healthy      no critical check failed, and at most NON_CRITICAL_LIMIT non-critical ones failed
  Degraded     no critical check failed, but more non-critical ones did, or a critical one warns
  Not healthy  a critical check failed
Security findings never make a run Not healthy: they are shown beside it (the report's Security count).
The list and the limit of 10 were decided on 13 Nov 2026 (D645, the owner asked us to decide): kept as built, with the
coverage line, the alert check and the UI review's notes non-critical; change them here (and in docs/testing.md).
"""

from __future__ import annotations

import math
from typing import Any

NON_CRITICAL_LIMIT = 10
OUTCOMES = ("passed", "failed", "warning", "skipped")
NON_CRITICAL_DB = ("speed", "an index")
# decided 13 Nov 2026 (the owner: "take a decision"): measurements and the watchers around the application, not the
# application itself: the code coverage line (D642), the container alert check (D641) and the UI review's notes (D621)
NON_CRITICAL_PREFIXES = ("coverage:", "alerts:", "ui review")


def importance(suite: str, name: str) -> str:
    """critical or non-critical, for one check (its suite and its name)."""
    n = (name or "").lower()
    if suite == "security":
        return "non-critical"
    if n.startswith(NON_CRITICAL_PREFIXES):
        return "non-critical"
    if suite == "db" and any(x in n for x in NON_CRITICAL_DB):
        return "non-critical"
    return "critical"


def summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts by importance and outcome, by suite, and the health with its reason."""
    by = {imp: dict.fromkeys(OUTCOMES, 0) for imp in ("critical", "non-critical")}
    suites: dict[str, dict[str, int]] = {}
    critical_failed: list[str] = []
    for r in results:
        o = r.get("outcome") if r.get("outcome") in OUTCOMES else "failed"
        imp = importance(r.get("suite", ""), r.get("name", ""))
        by[imp][o] += 1
        suites.setdefault(r.get("suite", ""), dict.fromkeys(OUTCOMES, 0))[o] += 1
        if imp == "critical" and o == "failed":
            critical_failed.append(f"{r.get('suite')}: {r.get('name')}")
    c, nc = by["critical"], by["non-critical"]
    if c["failed"]:
        health, reason = "Not healthy", (f"{c['failed']} critical check{'s' if c['failed'] != 1 else ''} failed: "
                                         + "; ".join(critical_failed[:3]) + ("…" if len(critical_failed) > 3 else ""))
    elif nc["failed"] > NON_CRITICAL_LIMIT or c["warning"]:
        parts = []
        if nc["failed"] > NON_CRITICAL_LIMIT:
            parts.append(f"{nc['failed']} non-critical checks failed (more than {NON_CRITICAL_LIMIT})")
        if c["warning"]:
            parts.append(f"{c['warning']} critical check{'s' if c['warning'] != 1 else ''} with a warning")
        health, reason = "Degraded", "; ".join(parts)
    elif not (c["passed"] or c["failed"]):
        health, reason = "Not known", "no critical check has run yet"
    else:
        health = "Healthy"
        reason = (f"every critical check passed ({c['passed']})"
                  + (f"; {nc['failed']} non-critical failed" if nc["failed"] else ""))
    sec = suites.get("security", dict.fromkeys(OUTCOMES, 0))
    return {"health": health, "reason": reason, "critical": c, "non_critical": nc, "suites": suites,
            "critical_failed": critical_failed, "security": {"failed": sec["failed"], "warning": sec["warning"]},
            "limit": NON_CRITICAL_LIMIT}


COLOURS = {"critical failed": "#b42318", "non-critical failed": "#e8833a", "warning": "#d4a72c", "skipped": "#9aa3af",
           "passed": "#2e7d4f"}
HEALTH_COLOUR = {"Healthy": "#2e7d4f", "Degraded": "#d4a72c", "Not healthy": "#b42318", "Not known": "#9aa3af"}


def ring_parts(s: dict[str, Any]) -> list[tuple[str, int]]:
    c, nc = s["critical"], s["non_critical"]
    return [("critical failed", c["failed"]), ("non-critical failed", nc["failed"]),
            ("warning", c["warning"] + nc["warning"]), ("skipped", c["skipped"] + nc["skipped"]),
            ("passed", c["passed"] + nc["passed"])]


def ring_svg(parts: list[tuple[str, int]], size: int = 140, label: str = "") -> str:
    """A ring chart (SVG, no script): each part its arc; the middle says how many failed."""
    total = sum(n for _, n in parts) or 1
    r, w = size / 2 - 10, 18
    cx = cy = size / 2
    circ = 2 * math.pi * r
    arcs, at = [], 0.0
    for name, n in parts:
        if not n:
            continue
        frac = n / total
        arcs.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="{COLOURS[name]}" stroke-width="{w}" '
                    f'stroke-dasharray="{frac * circ:.2f} {circ:.2f}" stroke-dashoffset="{-at * circ:.2f}" '
                    f'transform="rotate(-90 {cx} {cy})"><title>{name}: {n}</title></circle>')
        at += frac
    failed = sum(n for k, n in parts if k.endswith("failed"))
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="{label}: {failed} failed of {total}">'
            f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="#e5e7eb" stroke-width="{w}"/>{"".join(arcs)}'
            f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="22" font-weight="700" fill="currentColor">{failed}</text>'
            f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" font-size="11" fill="currentColor">failed</text></svg>')
