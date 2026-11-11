"""The test bench's own report (D581): report.html (one page, screenshots inside, the coverage summary at the top),
report.json (everything, for tools) and junit.xml (for CI: one test case per check, a failure per failed check)."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from .results import Run

_CSS = """
:root{--bg:#fbfbf8;--fg:#1b2430;--muted:#5b6573;--line:#d9dde3;--pass:#1a7f37;--fail:#b42318;--warn:#8a5a00;--skip:#5b6573}
@media (prefers-color-scheme:dark){:root{--bg:#14181f;--fg:#e8ebef;--muted:#a3adba;--line:#2c333d;--pass:#4fbf6b;--fail:#ff7b72;--warn:#e3b341;--skip:#a3adba}}
body{background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;margin:24px auto;max-width:1100px;padding:0 16px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 8px}.muted{color:var(--muted)}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.passed{color:var(--pass)}.failed{color:var(--fail);font-weight:600}.warning{color:var(--warn)}.skipped{color:var(--skip)}
pre{white-space:pre-wrap;font-size:12px;margin:4px 0}img{max-width:100%;border:1px solid var(--line);margin-top:6px}
.cov td:first-child{font-weight:600;width:40%}
"""


def write(run: Run, extra: dict | None = None) -> dict[str, Path]:
    """Writes the three files into the run's folder; returns their paths."""
    run.folder.mkdir(parents=True, exist_ok=True)
    out = {"html": run.folder / "report.html", "json": run.folder / "report.json", "junit": run.folder / "junit.xml"}
    out["json"].write_text(json.dumps(as_dict(run, extra), indent=2), encoding="utf-8")
    out["junit"].write_text(junit(run), encoding="utf-8")
    out["html"].write_text(as_html(run, extra), encoding="utf-8")
    return out


def as_dict(run: Run, extra: dict | None = None) -> dict:
    t = run.tally()
    return {"tool": "EA Explorer test bench", "target": run.target, "version": run.version, "started": run.started,
            "level": run.level, "suites": run.suites, "browsers": run.browsers, "platform_run": run.platform_run,
            "totals": t, "result": "failed" if run.failed else "passed",
            "coverage": [{"what": a, "value": b} for a, b in run.coverage()], "load": run.load, **(extra or {}),
            "results": [{"suite": r.suite, "name": r.name, "outcome": r.outcome, "detail": r.detail, "ms": r.ms,
                         "browser": r.browser, "video": r.video, "request": r.request, "response": r.response,
                         "screenshot": bool(r.screenshot)} for r in run.results]}


def junit(run: Run) -> str:
    suites = ET.Element("testsuites", name="EA Explorer test bench")
    by: dict[str, list] = {}
    for r in run.results:
        by.setdefault(r.suite, []).append(r)
    for suite, rs in by.items():
        s = ET.SubElement(suites, "testsuite", name=suite, tests=str(len(rs)),
                          failures=str(sum(r.outcome == "failed" for r in rs)),
                          skipped=str(sum(r.outcome == "skipped" for r in rs)),
                          time=f"{sum(r.ms for r in rs) / 1000:.3f}")
        for r in rs:
            c = ET.SubElement(s, "testcase", classname=f"testbench.{suite}" + (f".{r.browser}" if r.browser else ""),
                              name=r.name, time=f"{r.ms / 1000:.3f}")
            if r.outcome == "failed":
                f = ET.SubElement(c, "failure", message=r.detail[:500])
                f.text = "\n".join(x for x in (r.detail, r.request, r.response) if x)
            elif r.outcome == "skipped":
                ET.SubElement(c, "skipped", message=r.detail[:500])
            elif r.outcome == "warning":
                ET.SubElement(c, "system-out").text = f"warning: {r.detail}"
    if run.load:
        s = ET.SubElement(suites, "testsuite", name="load", tests="1", failures="1" if run.load.get("failed") else "0")
        c = ET.SubElement(s, "testcase", classname="testbench.load", name="load test")
        if run.load.get("failed"):
            ET.SubElement(c, "failure", message="; ".join(run.load.get("broken", []))[:500])
    ET.indent(suites)
    return ET.tostring(suites, encoding="unicode", xml_declaration=True)


def as_html(run: Run, extra: dict | None = None) -> str:
    e = html.escape
    t = run.tally()
    verdict = "failed" if run.failed else "passed"
    order = {"failed": 0, "warning": 1, "passed": 2, "skipped": 3}
    rows = []
    for r in sorted(run.results, key=lambda r: (order[r.outcome], r.suite, r.name)):
        more = ""
        if r.request or r.response:
            more += f"<pre>{e(r.request)}\n{e(r.response[:3000])}</pre>"
        if r.screenshot:
            more += f'<img alt="screenshot of {e(r.name)}" src="data:image/png;base64,{base64.b64encode(r.screenshot).decode()}">'
        if r.video:
            more += f'<div><a href="{e(r.video)}">video</a></div>'
        rows.append(f"<tr><td class='{r.outcome}'>{r.outcome}</td><td>{e(r.suite)}</td><td>{e(r.name)}"
                    f"{'<div class=muted>' + e(r.browser) + '</div>' if r.browser else ''}</td>"
                    f"<td>{e(r.detail[:1000])}{more}</td><td>{r.ms} ms</td></tr>")
    cov = "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td></tr>" for a, b in run.coverage())
    load = ""
    if run.load:
        load = "<h2>Load</h2><table>" + "".join(f"<tr><td>{e(str(k))}</td><td>{e(str(v))}</td></tr>"
                                                 for k, v in run.load.items() if k not in ("raw",)) + "</table>"
    notes = "".join(f"<li>{e(n)}</li>" for n in (extra or {}).get("notes", []))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test bench report</title><style>{_CSS}</style></head><body>
<h1>EA Explorer test bench: <span class="{verdict}">{verdict}</span></h1>
<div class="muted">{e(run.target)} · version {e(run.version or "unknown")} · {e(run.level)} · {e(", ".join(run.suites))} ·
started {e(run.started)}{f" · self-test run {run.platform_run} on the target" if run.platform_run else ""}</div>
<p>{t['passed']} passed · <span class="failed">{t['failed']} failed</span> · {t['warning']} warnings · {t['skipped']} skipped</p>
<h2>Coverage</h2><table class="cov">{cov or "<tr><td colspan=2>Nothing ran.</td></tr>"}</table>
{load}{f"<h2>Notes</h2><ul>{notes}</ul>" if notes else ""}
<h2>Every check</h2><table><tr><th>Result</th><th>Suite</th><th>Check</th><th>Detail</th><th>Time</th></tr>{"".join(rows)}</table>
</body></html>"""
