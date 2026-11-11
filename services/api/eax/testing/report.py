"""A self-test run's report (phase 36.1, D524): one HTML page (self-contained, screenshots inside) and an Excel workbook.

Made by the runner at the end of every run (work/tests/<folder>/report.html and report.xlsx, which `eax test --report`
shows) and by the API on request (System admin > Self-test > Download report), from the one results store."""

from __future__ import annotations

import base64
import html
import io
from typing import Any

from sqlalchemy import text

from . import store

STATE = {"queued": "Waiting", "running": "Running", "passed": "Passed", "failed": "Failed", "error": "Could not finish",
         "stopped": "Stopped"}
COLOUR = {"passed": "#1b7a3a", "failed": "#b42318", "warning": "#9a6700", "skipped": "#5d6470"}


def _shots(conn, run_id: int) -> dict[int, bytes]:
    rows = conn.execute(text("SELECT id, screenshot FROM core.test_results WHERE run_id = :id AND screenshot IS NOT NULL"),
                        {"id": run_id}).mappings().all()
    return {int(r["id"]): bytes(r["screenshot"]) for r in rows}


def options_line(run: dict[str, Any]) -> str:
    bits = [", ".join(run["suites"]), run.get("mode") or "full"]
    if run.get("role"):
        bits.append(f"role {run['role']}")
    if run.get("area"):
        bits.append(f"area {run['area']}")
    if run.get("watch"):
        bits.append("journeys watched in a browser")
    return " · ".join(bits)


def to_html(conn, run_id: int) -> str:
    d = store.run_detail(conn, run_id)
    if not d:
        raise KeyError(run_id)
    run, results, t = d["run"], d["results"], d["tally"]
    shots = _shots(conn, run_id)
    e = html.escape
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
</style></head><body>
<h1>EA Explorer self-test {run_id}: {e(STATE.get(run['state'], run['state']))}</h1>
<p>{e(options_line(run))}<br><span class="q">Started by {e(run['started_by'])} ({e(run['trigger'])}) {run['started_at'] or run['queued_at']}, finished {run['finished_at'] or '-'} · version {e(run['version'] or '?')} · run on a separate test database</span></p>
<p><span class="k"><b>{t['passed']}</b>passed</span><span class="k"><b style="color:{COLOUR['failed']}">{t['failed']}</b>failed</span>
<span class="k"><b>{t['warning']}</b>warnings</span><span class="k"><b>{t['skipped']}</b>skipped</span></p>
<p>{e(run['message'] or '')}</p>
<table><thead><tr><th>Suite</th><th>Check</th><th>Outcome</th><th>Details</th></tr></thead><tbody>
{''.join(rows)}
</tbody></table></body></html>"""


def to_xlsx(conn, run_id: int) -> bytes:
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
                ("Skipped", t["skipped"]), ("Message", run["message"]),
                ("Where", "A separate test database (eaxtest) and the runner's own copy of the API: no real data")]:
        ws.append(list(row))
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 18, 90
    rs = wb.create_sheet("Results")
    head = ["Suite", "Check", "Outcome", "Details", "Request", "Response", "Browser", "Video", "Took (ms)"]
    rs.append(head)
    for c in rs[1]:
        c.font = Font(bold=True)
    fills = {"failed": "FDE7E6", "warning": "FFF4D6"}
    for r in results:
        rs.append([r["suite"], r["name"], r["outcome"], r["detail"][:32000], r["request"], r["response"][:32000], r["browser"],
                   r["video"], r["duration_ms"]])
        if r["outcome"] in fills:
            rs.cell(rs.max_row, 3).fill = PatternFill("solid", fgColor=fills[r["outcome"]])
    for col, w in zip("ABCDEFGHI", (10, 60, 10, 70, 40, 50, 24, 30, 10), strict=True):
        rs.column_dimensions[col].width = w
    rs.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
