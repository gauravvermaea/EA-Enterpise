"""The UI review (R2.12; owner, 13 Nov 2026: "the self-test takes the screenshots"; "I am happy with the UI as it is
discuss before you make changes"): `eax test ui-review` opens every main page as each test role at three widths (laptop,
large screen, narrow), takes a screenshot of each and notes what a reviewer looks at, then builds ui-review.html in the
run's folder: the pictures side by side, and the notes. It changes nothing in the screens: the findings are discussed
with the owner, who picks which to fix.

The notes, per page and width (in the four areas the owner chose): the page is wider than the window (the top bar on a
narrow screen); several or no page titles; buttons, fields and images with no name a screen reader can say; long blocks
of text before the content; the page's title against the menu's name for it."""

from __future__ import annotations

import html
import re
import time
from pathlib import Path

from . import store, ui_pages

WIDTHS = (("laptop", 1366, 768), ("large", 1920, 1080), ("narrow", 390, 844))
ADMIN_TABS = ("system", "running", "containers", "databases", "persist", "footprint", "backups", "settings", "users",
              "self-test")
LOOK_JS = r"""() => {
  const named = (el) => (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || el.value || el.alt || '').trim();
  const vis = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const notes = [];
  if (document.documentElement.scrollWidth > window.innerWidth + 4)
    notes.push(`wider than the window (${document.documentElement.scrollWidth} px in ${window.innerWidth} px)`);
  const h = [...document.querySelectorAll('main h1, main h2, .content h2, h1')].filter(vis);
  if (!h.length) notes.push('no page title');
  const btn = [...document.querySelectorAll('button, [role=button], a.button')].filter(vis).filter((b) => !named(b));
  if (btn.length) notes.push(`${btn.length} button(s) with no name a screen reader can say`);
  const fld = [...document.querySelectorAll('input:not([type=hidden]), select, textarea')].filter(vis).filter((f) => {
    const id = f.id && document.querySelector(`label[for="${f.id}"]`);
    return !(f.getAttribute('aria-label') || f.getAttribute('placeholder') || f.closest('label') || id || f.title);
  });
  if (fld.length) notes.push(`${fld.length} field(s) with no label`);
  const img = [...document.querySelectorAll('img')].filter(vis).filter((i) => !i.hasAttribute('alt'));
  if (img.length) notes.push(`${img.length} image(s) with no alt text`);
  const p = [...document.querySelectorAll('main p, .content p, p.quiet')].filter(vis).find((x) => (x.innerText || '').length > 450);
  if (p) notes.push(`a long block of text (${p.innerText.length} characters) before the content`);
  return { title: (h[0] && h[0].innerText || '').trim().slice(0, 80), notes };
}"""


def routes(ids: dict[str, str]) -> list[str]:
    """The main pages: the self-test's seeds (every area) and System Admin's tabs."""
    out = [r for r in ui_pages.seeds(ids) if not r.startswith("#/search")]
    return out + [f"#/admin/{t}" for t in ADMIN_TABS]


def slug(route: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", route.lower()).strip("-")[:60] or "home"


def run(ids: dict[str, str], ticket: str, folder: Path, record, roles: list[str] | None = None, base: str = "",
        shots_per_role: int = 200) -> dict[str, int]:
    """Screenshots and notes for each role, page and width; ui-review.html in the run's folder. One result per role
    ("ui review: <role>", passed: the review is information, never a failure)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        record("ui review", "skipped", "Playwright is not in this image (the test runner image has it)", 0)
        return {}
    import os

    from .ui_journeys import base_url
    base = base or base_url()
    host = base.split("//", 1)[1].split("/")[0].split(":")[0]
    proxy = os.environ.get("EAX_TEST_PROXY_HOST", "proxy")
    shots = folder / "ui-review"
    shots.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    roles = roles or list(store.TEST_ROLES)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=[f"--host-resolver-rules=MAP {host} {proxy}, MAP *.{host} {proxy}"])
        for role in roles:
            t0, n = time.time(), 0
            for wname, w, hgt in WIDTHS:
                ctx = browser.new_context(ignore_https_errors=True, viewport={"width": w, "height": hgt})
                page = ctx.new_page()
                for route in routes(ids)[:shots_per_role]:
                    try:
                        page.goto(f"{base}/?eaxselftest={ticket}&eaxrole={role}{route}", wait_until="domcontentloaded",
                                  timeout=60000)
                        page.wait_for_selector("text=EA Explorer", timeout=30000)
                        page.wait_for_timeout(1500)
                        look = page.evaluate(LOOK_JS)
                        f = f"{role}/{wname}/{slug(route)}.jpg"
                        (shots / role / wname).mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(shots / f), full_page=False, type="jpeg", quality=60)
                    except Exception as exc:  # noqa: BLE001 - a page that would not open is a note too
                        look, f = {"title": "", "notes": [f"did not open: {str(exc).splitlines()[0][:160]}"]}, ""
                    rows.append({"role": role, "width": wname, "route": route, "file": f, **look})
                    n += 1
                ctx.close()
            found = sum(1 for r in rows if r["role"] == role and r["notes"])
            record(f"ui review: {role}", "passed", f"{n} screenshots, {found} with notes (ui-review.html)",
                   int((time.time() - t0) * 1000))
        browser.close()
    (folder / "ui-review.html").write_text(to_html(rows), encoding="utf-8")
    return {"ui_review_shots": len(rows), "ui_review_notes": sum(1 for r in rows if r["notes"])}


def to_html(rows: list[dict]) -> str:
    """The review page: per role, each page in a row with its three widths side by side and the notes under each."""
    e = html.escape
    by: dict[tuple[str, str], dict[str, dict]] = {}
    for r in rows:
        by.setdefault((r["role"], r["route"]), {})[r["width"]] = r
    notes = sum(1 for r in rows if r["notes"])
    out = ["<!doctype html><meta charset='utf-8'><title>EA Explorer UI review</title><style>",
           "body{font:14px system-ui,sans-serif;margin:16px;color:#222}h2{margin-top:32px}"
           "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px;vertical-align:top}"
           "img{max-width:100%;border:1px solid #ccc}.note{color:#a33;font-size:12px}.ok{color:#2a7;font-size:12px}"
           "code{background:#f4f4f4;padding:1px 4px}</style>",
           "<h1>EA Explorer: UI review</h1>",
           f"<p>{len(rows)} screenshots, {notes} with notes. Nothing has been changed: each note is discussed first "
           "(R2.12). Widths: laptop 1366, large 1920, narrow 390 pixels.</p>"]
    for role in dict.fromkeys(r["role"] for r in rows):
        out.append(f"<h2>As {e(role)}</h2><table><tr><th>Page</th>" + "".join(f"<th>{w}</th>" for w, _, _ in WIDTHS) + "</tr>")
        for (rl, route), cells in by.items():
            if rl != role:
                continue
            out.append(f"<tr><td><code>{e(route)}</code></td>")
            for w, _, _ in WIDTHS:
                c = cells.get(w) or {}
                pic = f"<a href='ui-review/{e(c['file'])}'><img loading='lazy' src='ui-review/{e(c['file'])}'></a>" if c.get("file") else ""
                ns = "".join(f"<div class='note'>{e(n)}</div>" for n in c.get("notes") or []) or "<div class='ok'>no notes</div>"
                title = f"<div><b>{e(c.get('title') or '')}</b></div>" if c.get("title") else ""
                out.append(f"<td>{pic}{title}{ns}</td>")
            out.append("</tr>")
        out.append("</table>")
    return "\n".join(out)
