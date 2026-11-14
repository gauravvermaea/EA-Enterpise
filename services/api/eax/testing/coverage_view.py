"""Coverage as pictures (R3.10; owner, 13 Nov 2026: "coverage should be shown with results in UI with some sort of
graph"): for a run, its code coverage (coverage.json, D642) and its negative tests (negative.json, R3.9), and the trend
over the last runs.

  gauge     the share of the API's lines run, against the goal (90%)
  areas     each area's share, the worst first
  trend     the share over the last runs of the same kind, with the goal as a line
  negative  the negative tests by kind: passed, warnings, failed (a stacked bar each)

The pictures are SVG drawn here from numbers only (area names escaped), so the Self-test page and the HTML report show the
same ones; the page also gets the numbers. Nothing here reads anything but a run's own two files."""

from __future__ import annotations

import html
import json
from collections.abc import Callable, Iterable

GOAL = 90.0
GOOD, NEAR, LOW = "#1a9e5a", "#c98a00", "#d64545"       # at the goal; within 15 points; further off
BAR, GRID = "#3d7bd9", "#8a93a0"
OUTCOME_COLOUR = {"passed": GOOD, "warning": NEAR, "failed": LOW}

Reader = Callable[[str, str], bytes | None]               # (folder, file name) -> the file, or None


def _load(raw: bytes | None) -> dict | None:
    if not raw:
        return None
    try:
        out = json.loads(raw)
    except ValueError:
        return None
    return out if isinstance(out, dict) else None


def run_files(folder: str, reader: Reader) -> dict:
    """{coverage, negative} of one run (either None when the run has not got it)."""
    if not folder:
        return {"coverage": None, "negative": None}
    return {"coverage": _load(reader(folder, "coverage.json")), "negative": _load(reader(folder, "negative.json"))}


def colour(percent: float, goal: float = GOAL) -> str:
    return GOOD if percent >= goal else NEAR if percent >= goal - 15 else LOW


def trend(runs: Iterable[dict], reader: Reader, scope: str | None = None, limit: int = 30) -> list[dict]:
    """[{run, at, scope, percent, goal}] oldest first, for the runs (newest first, with id, folder, finished_at) that
    kept a coverage.json; only those of `scope` when it is given."""
    out = []
    for r in runs:
        c = _load(reader(r["folder"], "coverage.json")) if r.get("folder") else None
        if not c or c.get("percent") is None or (scope is not None and c.get("scope", "") != scope):
            continue
        out.append({"run": r["id"], "at": str(r.get("finished_at") or ""), "scope": c.get("scope", ""),
                    "percent": float(c["percent"]), "goal": float(c.get("goal") or GOAL)})
        if len(out) >= limit:
            break
    return list(reversed(out))


def negative_totals(neg: dict | None) -> dict[str, int]:
    t = {"passed": 0, "warning": 0, "failed": 0}
    for counts in (neg or {}).values():
        for k in t:
            t[k] += int((counts or {}).get(k) or 0)
    return t


def gauge_svg(percent: float, goal: float = GOAL, size: int = 180) -> str:
    """A half-ring from 0 to 100% with the goal marked."""
    import math
    w, h, r, sw = size, size * 0.62, size * 0.4, size * 0.09
    cx, cy = w / 2, size * 0.5

    def at(p: float) -> tuple[float, float]:
        a = math.pi * (1 - max(0.0, min(100.0, p)) / 100)
        return cx + r * math.cos(a), cy - r * math.sin(a)

    x0, y0 = at(0)
    x1, y1 = at(100)
    xp, yp = at(percent)
    gx, gy = at(goal)
    ox, oy = cx + (r + sw) * (gx - cx) / r, cy + (r + sw) * (gy - cy) / r
    ix, iy = cx + (r - sw) * (gx - cx) / r, cy + (r - sw) * (gy - cy) / r
    value = (f"<path d='M{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 0 1 {xp:.1f},{yp:.1f}' fill='none' stroke='{colour(percent, goal)}' "
             f"stroke-width='{sw:.1f}' stroke-linecap='round'/>") if percent > 0 else ""
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h:.0f}' width='{w}' height='{h:.0f}' role='img' "
            f"aria-label='Code coverage {percent:g}% against a goal of {goal:g}%'>"
            f"<path d='M{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 0 1 {x1:.1f},{y1:.1f}' fill='none' stroke='{GRID}' stroke-opacity='0.3' "
            f"stroke-width='{sw:.1f}' stroke-linecap='round'/>{value}"
            f"<line x1='{ix:.1f}' y1='{iy:.1f}' x2='{ox:.1f}' y2='{oy:.1f}' stroke='currentColor' stroke-width='2'/>"
            f"<text x='{cx:.1f}' y='{cy - 4:.1f}' text-anchor='middle' font-size='{size * 0.16:.0f}' font-weight='700' "
            f"fill='currentColor'>{percent:g}%</text>"
            f"<text x='{cx:.1f}' y='{cy + size * 0.1:.1f}' text-anchor='middle' font-size='{size * 0.07:.0f}' fill='currentColor' "
            f"opacity='0.7'>goal {goal:g}%</text></svg>")


def areas_svg(areas: list[dict], goal: float = GOAL, width: int = 420) -> str:
    """One bar per area, the least covered first, with the goal as a dashed line."""
    rows = sorted(areas or [], key=lambda a: a.get("percent", 0.0))
    if not rows:
        return ""
    lab, bh, gap = 110, 16, 6
    plot = width - lab - 48
    h = len(rows) * (bh + gap) + 8
    gx = lab + plot * goal / 100
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {h}' width='{width}' height='{h}' role='img' "
           f"aria-label='Coverage by area, the least covered first'>"]
    for i, a in enumerate(rows):
        y, p = 4 + i * (bh + gap), float(a.get("percent", 0.0))
        out.append(f"<text x='{lab - 6}' y='{y + bh - 4}' text-anchor='end' font-size='12' fill='currentColor'>"
                   f"{html.escape(str(a.get('area', '')))}</text>"
                   f"<rect x='{lab}' y='{y}' width='{plot}' height='{bh}' rx='3' fill='{GRID}' fill-opacity='0.15'/>"
                   f"<rect x='{lab}' y='{y}' width='{plot * min(p, 100) / 100:.1f}' height='{bh}' rx='3' fill='{colour(p, goal)}'>"
                   f"<title>{html.escape(str(a.get('area', '')))}: {p:g}% ({a.get('run', '?')} of {a.get('lines', '?')} lines)</title></rect>"
                   f"<text x='{lab + plot + 6}' y='{y + bh - 4}' font-size='12' fill='currentColor'>{p:g}%</text>")
    out.append(f"<line x1='{gx:.1f}' y1='0' x2='{gx:.1f}' y2='{h}' stroke='currentColor' stroke-dasharray='4 3' opacity='0.6'/>"
               "</svg>")
    return "".join(out)


def trend_svg(points: list[dict], goal: float = GOAL, width: int = 420, height: int = 140) -> str:
    """The share over the runs, oldest on the left, the goal dashed."""
    if not points:
        return ""
    left, right, top, bottom = 34, 10, 8, 20
    pw, ph = width - left - right, height - top - bottom

    def y(p: float) -> float:
        return top + ph * (1 - max(0.0, min(100.0, p)) / 100)

    n = len(points)
    xs = [left + (pw * i / (n - 1) if n > 1 else pw / 2) for i in range(n)]
    line = " ".join(f"{x:.1f},{y(p['percent']):.1f}" for x, p in zip(xs, points, strict=True))
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
           f"role='img' aria-label='Coverage over the last {n} runs'>"]
    for t in (0, 50, 100):
        out.append(f"<line x1='{left}' x2='{width - right}' y1='{y(t):.1f}' y2='{y(t):.1f}' stroke='{GRID}' stroke-opacity='0.25'/>"
                   f"<text x='{left - 4}' y='{y(t) + 4:.1f}' text-anchor='end' font-size='10' fill='currentColor' opacity='0.7'>{t}%</text>")
    out.append(f"<line x1='{left}' x2='{width - right}' y1='{y(goal):.1f}' y2='{y(goal):.1f}' stroke='currentColor' "
               f"stroke-dasharray='4 3' opacity='0.6'/>")
    if n > 1:
        out.append(f"<polyline points='{line}' fill='none' stroke='{BAR}' stroke-width='2'/>")
    for x, p in zip(xs, points, strict=True):
        out.append(f"<circle cx='{x:.1f}' cy='{y(p['percent']):.1f}' r='3.5' fill='{colour(p['percent'], goal)}'>"
                   f"<title>Run {p['run']}: {p['percent']:g}%</title></circle>")
    out.append(f"<text x='{left}' y='{height - 4}' font-size='10' fill='currentColor' opacity='0.7'>run {points[0]['run']}</text>"
               f"<text x='{width - right}' y='{height - 4}' text-anchor='end' font-size='10' fill='currentColor' opacity='0.7'>"
               f"run {points[-1]['run']}</text></svg>")
    return "".join(out)


def negative_svg(neg: dict | None, width: int = 420) -> str:
    """A stacked bar per kind of negative test: passed, warnings, failed."""
    rows = [(k, v) for k, v in (neg or {}).items() if sum((v or {}).values())]
    if not rows:
        return ""
    lab, bh, gap = 110, 16, 6
    plot = width - lab - 60
    h = len(rows) * (bh + gap) + 8
    most = max(sum(v.values()) for _, v in rows)
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {h}' width='{width}' height='{h}' role='img' "
           f"aria-label='Negative tests by kind'>"]
    for i, (kind, v) in enumerate(rows):
        y, x = 4 + i * (bh + gap), float(lab)
        out.append(f"<text x='{lab - 6}' y='{y + bh - 4}' text-anchor='end' font-size='12' fill='currentColor'>{html.escape(kind)}</text>")
        for outcome in ("passed", "warning", "failed"):
            n = int(v.get(outcome) or 0)
            if not n:
                continue
            w = plot * n / most
            out.append(f"<rect x='{x:.1f}' y='{y}' width='{w:.1f}' height='{bh}' fill='{OUTCOME_COLOUR[outcome]}'>"
                       f"<title>{html.escape(kind)}: {n} {outcome}</title></rect>")
            x += w
        out.append(f"<text x='{x + 6:.1f}' y='{y + bh - 4}' font-size='12' fill='currentColor'>{sum(v.values())}</text>")
    out.append("</svg>")
    return "".join(out)


def charts(files: dict, points: list[dict] | None = None) -> dict[str, str]:
    """The four pictures for a run (each '' when there is nothing to draw)."""
    c = files.get("coverage") or {}
    goal = float(c.get("goal") or GOAL)
    return {"gauge": gauge_svg(float(c["percent"]), goal) if c.get("percent") is not None else "",
            "areas": areas_svg(c.get("areas") or [], goal),
            "trend": trend_svg(points or [], goal),
            "negative": negative_svg(files.get("negative"))}


def summary_line(files: dict) -> str:
    """One line for `eax test`'s summary: the coverage against the goal and the negative tests."""
    c, neg = files.get("coverage") or {}, files.get("negative")
    parts = []
    if c.get("percent") is not None:
        goal = float(c.get("goal") or GOAL)
        worst = (sorted(c.get("areas") or [], key=lambda a: a.get("percent", 0.0)) or [{}])[0]
        parts.append(f"Coverage {c['percent']:g}% of the API's lines (goal {goal:g}%"
                     + (f", was {c['before']:g}%" if c.get("before") is not None else "") + ")"
                     + (f"; least covered: {worst['area']} {worst['percent']:g}%" if worst.get("area") else ""))
    if neg:
        t = negative_totals(neg)
        parts.append(f"negative tests {sum(t.values())}: {t['passed']} passed, {t['warning']} warnings, {t['failed']} failed")
    return "; ".join(parts)


def html_section(files: dict, points: list[dict] | None = None) -> str:
    """The report's section: the four pictures, or a line saying the run kept no coverage."""
    ch = charts(files, points)
    if not any(ch.values()):
        return ("<h2>Code coverage</h2><p class='q'>This run kept no code coverage (EAX_COVERAGE=on measures it) and ran no "
                "negative tests.</p>")
    figs = [(k, t) for k, t in (("gauge", "Share of the API's lines run"), ("areas", "By area, the least covered first"),
                                ("trend", "Over the last runs of this kind"), ("negative", "Negative tests by kind")) if ch[k]]
    line = html.escape(summary_line(files))
    return ("<h2>Code coverage</h2>" + (f"<p>{line}</p>" if line else "") + "<div class='covcharts'>"
            + "".join(f"<figure>{ch[k]}<figcaption>{t}</figcaption></figure>" for k, t in figs) + "</div>")
