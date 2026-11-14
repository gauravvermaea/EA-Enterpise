"""A self-test run's report (phase 36.1, D524): one HTML page (self-contained, screenshots inside) and an Excel workbook.

Made by the runner at the end of every run (work/tests/<folder>/report.html and report.xlsx, which `eax test --report`
shows) and by the API on request (System admin > Self-test > Download report), from the one results store."""

from __future__ import annotations

import base64
import html
import io
from typing import Any

from sqlalchemy import text

from . import coverage_view, store

STATE = {"queued": "Waiting", "running": "Running", "passed": "Passed", "failed": "Failed", "error": "Could not finish",
         "stopped": "Stopped"}
COLOUR = {"passed": "#1b7a3a", "failed": "#b42318", "warning": "#9a6700", "skipped": "#5d6470"}


def _shots(conn, run_id: int) -> dict[int, bytes]:
    rows = conn.execute(text("SELECT id, screenshot FROM tests.test_results WHERE run_id = :id AND screenshot IS NOT NULL"),
                        {"id": run_id}).mappings().all()
    return {int(r["id"]): bytes(r["screenshot"]) for r in rows}


def options_line(run: dict[str, Any]) -> str:
    bits = [", ".join(run["suites"]), run.get("mode") or "full"]
    if run.get("repeat_of"):
        bits.append(f"the failed checks of self-test {run['repeat_of']} again" + (" (and its warnings)" if run.get("repeat_warnings") else ""))
    if run.get("role"):
        bits.append(f"role {run['role']}")
    if run.get("area"):
        bits.append(f"area {run['area']}")
    if run.get("watch"):
        bits.append("journeys watched in a browser")
    return " · ".join(bits)


def coverage(results: list[dict[str, Any]]) -> list[tuple[str, int, int]]:
    """The report's coverage summary (D578), worked out from the results' names: [(what, passed, out of)]. Skipped ones
    are not counted in "out of" (they say why on their own row)."""
    def tally(rows):
        rows = [r for r in rows if r["outcome"] != "skipped"]
        return sum(1 for r in rows if r["outcome"] == "passed"), len(rows)
    out: list[tuple[str, int, int]] = []
    pages = [r for r in results if r["name"].startswith("page: ")]
    if pages:
        out.append(("Pages opened and checked (renders, heading, F1 help)", *tally(pages)))
    js = [r for r in results if r["name"].startswith("journey: ") or r["name"].startswith("journey ")]
    if js:
        refused = [r for r in js if ": refused to " in r["name"] or r["name"].endswith("(refused)")]
        done = [r for r in js if r not in refused]
        if done:
            out.append(("Journeys that click, type and save (each allowed role)", *tally(done)))
        if refused:
            out.append(("Journeys refused to a role that may not", *tally(refused)))
        # how many of the defined journeys passed in full, for every role tried (D583): smoke runs 3, detailed all
        from . import ui_flows
        keys = {ui_flows.key(j): j for j in ui_flows.JOURNEYS}
        tried: dict[str, bool] = {}
        for r in js:
            if r["outcome"] == "skipped":
                continue
            k = next((k for k in keys if r["name"].split(": ", 1)[-1].lower().startswith(k.lower())), None)
            if k:
                tried[k] = tried.get(k, True) and r["outcome"] == "passed"
        if tried:
            out.append((f"Journeys covered (of the {len(keys)} defined)", sum(tried.values()), len(keys)))
    anon = [r for r in results if r["suite"] == "api" and r["name"].endswith(": without a token")]
    if anon:
        out.append(("API endpoints refused without a sign-in", *tally(anon)))
    roles = [r for r in results if r["suite"] == "api" and (": every test role" in r["name"] or ": as " in r["name"])]
    if roles:
        out.append(("API reads (GET) as every test role", *tally(roles)))
    cross = [r for r in results if r["suite"] == "api" and "cross-user" in r["name"]]
    if cross:
        out.append(("API reads refused to someone with no role on the model", *tally(cross)))
    writes: dict[str, list] = {}
    for r in results:
        if r["suite"] == "api" and r["name"].startswith("write "):
            writes.setdefault(r["name"][6:].split(":")[0], []).append(r)
    for area, rows in sorted(writes.items()):
        out.append((f"API writes: {area}", *tally(rows)))
    for suite, label in (("db", "Database checks"), ("security", "Security checks"), ("smoke", "Smoke checks")):
        rows = [r for r in results if r["suite"] == suite]
        if rows:
            out.append((label, *tally(rows)))
    return out


NOW_COLOUR = {**COLOUR, "not repeated": "#5d6470"}


def repeat_html(rp: dict[str, Any] | None) -> str:
    """A repeat's section (R2.36): which run it repeats and each check's outcome then and now."""
    if not rp:
        return ""
    e = html.escape
    rows = "".join(f"<tr><td>{e(c['suite'])}</td><td>{e(c['name'])}</td>"
                   f"<td style='color:{COLOUR.get(c['then'], '#5d6470')};font-weight:600'>{e(c['then'])}</td>"
                   f"<td style='color:{NOW_COLOUR.get(c['now'], '#5d6470')};font-weight:600'>{e(c['now'])}</td></tr>"
                   for c in rp["checks"])
    verdict = ("Every repeated check passes now: self-test {of} is marked as followed up." if rp["all_passed"] else
               "{fixed} of {n} now pass; {still} still fail or were not repeated.").format(
        of=rp["of"], fixed=rp["fixed"], n=len(rp["checks"]), still=rp["still"])
    return (f"<h2>Repeat of self-test {rp['of']}</h2><p>The checks that failed in self-test {rp['of']}"
            f"{' (and its warnings)' if rp['with_warnings'] else ''}, run again in fresh fixtures. {e(verdict)}</p>"
            f"<table><thead><tr><th>Suite</th><th>Check</th><th>Then</th><th>Now</th></tr></thead><tbody>{rows}</tbody></table>")


def to_html(conn, run_id: int, files: dict | None = None, points: list[dict] | None = None) -> str:
    """The run's report; files ({coverage, negative}) and points (the coverage trend) draw its coverage section (R3.10)."""
    d = store.run_detail(conn, run_id)
    if not d:
        raise KeyError(run_id)
    run, results, t = d["run"], d["results"], d["tally"]
    shots = _shots(conn, run_id)
    e = html.escape
    from . import health as H
    hs = d["health"]
    suite_names = {"smoke": "Smoke", "api": "API", "ui": "Pages and journeys", "db": "Database", "security": "Security"}
    rings = "".join(
        f"<figure class='ring'>{H.ring_svg([('critical failed' if H.importance(s, '') == 'critical' else 'non-critical failed', n['failed']), ('warning', n['warning']), ('skipped', n['skipped']), ('passed', n['passed'])], 110, suite_names.get(s, s))}"
        f"<figcaption>{e(suite_names.get(s, s))}</figcaption></figure>" for s, n in hs["suites"].items())
    legend = "".join(f"<span><i style='background:{c}'></i>{e(k)}</span>" for k, c in H.COLOURS.items())
    health_block = (
        f"<section class='health' style='border-color:{H.HEALTH_COLOUR[hs['health']]}'>"
        f"<div class='overall'>{H.ring_svg(H.ring_parts(hs), 160, 'Every check')}</div>"
        f"<div><p class='hl' style='color:{H.HEALTH_COLOUR[hs['health']]}'>Functional health: {e(hs['health'])}</p>"
        f"<p>{e(hs['reason'])}</p>"
        f"<p class='q'>Critical: {hs['critical']['passed']} passed, {hs['critical']['failed']} failed, {hs['critical']['warning']} warnings, "
        f"{hs['critical']['skipped']} skipped · Non-critical: {hs['non_critical']['passed']} passed, {hs['non_critical']['failed']} failed, "
        f"{hs['non_critical']['warning']} warnings · Security (never counted against the health): {hs['security']['failed']} failed, "
        f"{hs['security']['warning']} warnings</p><div class='legend'>{legend}</div></div></section>"
        f"<div class='rings'>{rings}</div>")
    rows = []
    for r in results:
        extra = ""
        if r["request"] or r["response"]:
            extra += f"<details><summary>Request and response</summary><pre>{e(r['request'])}\n\n{e(r['response'])}</pre></details>"
        if r["id"] in shots:
            extra += (f"<details><summary>Screenshot</summary><img alt='{e(r['name'])}' "
                      f"src='data:image/png;base64,{base64.b64encode(shots[r['id']]).decode()}'></details>")
        if r["video"]:
            extra += f"<div class='q'>Video: work/tests/{e(run['folder'])}/{e(r['video'])}</div>"
        rows.append(f"<tr><td>{e(r['suite'])}</td><td>{e(r['name'])}{'<div class=q>' + e(r['browser']) + '</div>' if r['browser'] else ''}</td>"
                    f"<td style='color:{COLOUR[r['outcome']]};font-weight:600'>{r['outcome']}</td>"
                    f"<td><div class='d'>{e(r['detail'])}</div>{extra}</td></tr>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>EA Explorer self-test {run_id}</title><style>
:root {{ --bg:#fff; --fg:#1d2330; --line:#d9dde3; --q:#5d6470; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14171c; --fg:#e6e9ee; --line:#323843; --q:#9aa3af; }} }}
body {{ font: 14px/1.45 system-ui, sans-serif; background:var(--bg); color:var(--fg); margin:24px; }}
table {{ border-collapse: collapse; width: 100%; }} td, th {{ border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }}
.q {{ color: var(--q); font-size: 12px; }} .d {{ white-space: pre-wrap; word-break: break-word; }} pre {{ white-space: pre-wrap; font-size: 12px; }}
img {{ max-width: 100%; border: 1px solid var(--line); }} .k {{ display:inline-block; margin-right:18px; }} .k b {{ font-size: 22px; display:block; }}
.health {{ display:flex; gap:20px; align-items:center; border:2px solid; border-radius:10px; padding:12px 16px; margin:12px 0; }}
.health .hl {{ font-size:20px; font-weight:700; margin:0 0 4px; }} .rings {{ display:flex; flex-wrap:wrap; gap:16px; }}
.ring {{ margin:0; text-align:center; }} .ring figcaption {{ font-size:12px; color:var(--q); }}
.covcharts {{ display:flex; flex-wrap:wrap; gap:18px; }} .covcharts figure {{ margin:0; }} .covcharts figcaption {{ font-size:12px; color:var(--q); }}
.legend span {{ display:inline-flex; align-items:center; gap:4px; margin-right:12px; font-size:12px; }} .legend i {{ width:10px; height:10px; display:inline-block; border-radius:2px; }}
</style></head><body>
<h1>EA Explorer self-test {run_id}: {e(STATE.get(run['state'], run['state']))}</h1>
<p>{e(options_line(run))}<br><span class="q">Started by {e(run['started_by'])} ({e(run['trigger'])}) {run['started_at'] or run['queued_at']}, finished {run['finished_at'] or '-'} · version {e(run['version'] or '?')} · in the run's own fixtures</span></p>
<p><span class="k"><b>{t['passed']}</b>passed</span><span class="k"><b style="color:{COLOUR['failed']}">{t['failed']}</b>failed</span>
<span class="k"><b>{t['warning']}</b>warnings</span><span class="k"><b>{t['skipped']}</b>skipped</span></p>
<p>{e(run['message'] or '')}</p>
{health_block}
{repeat_html(d.get("repeat"))}
{coverage_view.html_section(files or {}, points)}
<p class="q">The same run from the command line: <code>{e(store.command_line(run))}</code></p>
<h2>Coverage</h2>
<table class="cov"><thead><tr><th>What</th><th>Passed</th><th>Out of</th></tr></thead><tbody>
{''.join(f"<tr><td>{e(w)}</td><td>{p}</td><td>{n}</td></tr>" for w, p, n in coverage(results)) or '<tr><td colspan=3>Nothing ran yet</td></tr>'}
</tbody></table>
<h2>Every check</h2>
<table><thead><tr><th>Suite</th><th>Check</th><th>Outcome</th><th>Details</th></tr></thead><tbody>
{''.join(rows)}
</tbody></table></body></html>"""


def _coverage_sheet(wb, files: dict, points: list[dict], Font) -> None:
    """The code coverage (R3.10): the total and goal, each area, the negative tests by kind and the trend, with a chart."""
    c, neg = files.get("coverage") or {}, files.get("negative") or {}
    if c.get("percent") is None and not neg:
        return
    from openpyxl.chart import BarChart, LineChart, Reference
    ws = wb.create_sheet("Code coverage")
    ws.append(["Code coverage of the API", c.get("percent"), "goal", c.get("goal") or coverage_view.GOAL])
    ws.append([coverage_view.summary_line(files)])
    ws.append([])
    ws.append(["Area", "Percent", "Lines run", "Lines"])
    head = ws.max_row
    for cell in ws[head]:
        cell.font = Font(bold=True)
    areas = sorted(c.get("areas") or [], key=lambda a: a.get("percent", 0.0))
    for a in areas:
        ws.append([a.get("area"), a.get("percent"), a.get("run"), a.get("lines")])
    if areas:
        ch = BarChart()
        ch.type, ch.title, ch.y_axis.title = "bar", "By area, the least covered first", "%"
        ch.add_data(Reference(ws, min_col=2, min_row=head, max_row=head + len(areas)), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=head + 1, max_row=head + len(areas)))
        ws.add_chart(ch, "G2")
    ws.append([])
    ws.append(["Negative tests", "passed", "warnings", "failed"])
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    for kind, v in neg.items():
        ws.append([kind, v.get("passed", 0), v.get("warning", 0), v.get("failed", 0)])
    if points:
        ws.append([])
        ws.append(["Run", "Percent", "Goal"])
        top = ws.max_row
        for cell in ws[top]:
            cell.font = Font(bold=True)
        for p in points:
            ws.append([p["run"], p["percent"], p["goal"]])
        lc = LineChart()
        lc.title, lc.y_axis.title = "Over the last runs of this kind", "%"
        lc.add_data(Reference(ws, min_col=2, max_col=3, min_row=top, max_row=top + len(points)), titles_from_data=True)
        lc.set_categories(Reference(ws, min_col=1, min_row=top + 1, max_row=top + len(points)))
        ws.add_chart(lc, "G20")
    ws.column_dimensions["A"].width = 30


def to_xlsx(conn, run_id: int, files: dict | None = None, points: list[dict] | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    d = store.run_detail(conn, run_id)
    if not d:
        raise KeyError(run_id)
    run, results, t = d["run"], d["results"], d["tally"]
    wb = Workbook()
    ws = wb.active
    ws.title = "About"
    for row in [("EA Explorer self-test", run_id), ("Result", STATE.get(run["state"], run["state"])),
                ("What ran", options_line(run)), ("Started by", f"{run['started_by']} ({run['trigger']})"),
                ("Started", str(run["started_at"] or run["queued_at"])), ("Finished", str(run["finished_at"] or "")),
                ("Version", run["version"]), ("Passed", t["passed"]), ("Failed", t["failed"]), ("Warnings", t["warning"]),
                ("Skipped", t["skipped"]), ("Functional health", d["health"]["health"]), ("Why", d["health"]["reason"]),
                ("Critical failed", d["health"]["critical"]["failed"]), ("Non-critical failed", d["health"]["non_critical"]["failed"]),
                ("Message", run["message"]),
                ("Where", "This installation, inside the run's own fixtures (self_test_<id>_<n>): nothing else is changed"),
                ("Command line", store.command_line(run))]:
        ws.append(list(row))
    ws.append([])
    ws.append(["Coverage", "Passed", "Out of"])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for w, p, n in coverage(results):
        ws.append([w, p, n])
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 18, 90
    _coverage_sheet(wb, files or {}, points or [], Font)
    rs = wb.create_sheet("Results")
    from . import health as H
    head = ["Suite", "Check", "Outcome", "Details", "Request", "Response", "Browser", "Video", "Took (ms)", "Importance"]
    rs.append(head)
    for c in rs[1]:
        c.font = Font(bold=True)
    fills = {"failed": "FDE7E6", "warning": "FFF4D6"}
    for r in results:
        rs.append([r["suite"], r["name"], r["outcome"], r["detail"][:32000], r["request"], r["response"][:32000], r["browser"],
                   r["video"], r["duration_ms"], H.importance(r["suite"], r["name"])])
        if r["outcome"] in fills:
            rs.cell(rs.max_row, 3).fill = PatternFill("solid", fgColor=fills[r["outcome"]])
    for col, w in zip("ABCDEFGHIJ", (10, 60, 10, 70, 40, 50, 24, 30, 10, 14), strict=True):
        rs.column_dimensions[col].width = w
    rs.freeze_panes = "A2"
    rp = d.get("repeat")
    if rp:                                             # a repeat: each check then and now (R2.36)
        ps = wb.create_sheet("Then and now")
        ps.append([f"Repeat of self-test {rp['of']}", f"{rp['fixed']} of {len(rp['checks'])} now pass"
                   + (" (followed up)" if rp["all_passed"] else "")])
        ps.append(["Suite", "Check", "Then", "Now"])
        for c in ps[2]:
            c.font = Font(bold=True)
        for c in rp["checks"]:
            ps.append([c["suite"], c["name"], c["then"], c["now"]])
            if c["now"] != "passed":
                ps.cell(ps.max_row, 4).fill = PatternFill("solid", fgColor=fills.get(c["now"], "EEEEEE"))
        for col, w in zip("ABCD", (10, 80, 10, 14), strict=True):
            ps.column_dimensions[col].width = w
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
