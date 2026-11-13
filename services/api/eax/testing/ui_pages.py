"""The self-test's page sweep (D575): every page, group, tab and sub-tab of EA Explorer opened in a real browser, each
checked three ways, so "pages opened N of N" stands on the report.

Where the pages come from: the top-level routes (SEEDS, kept in step with App.jsx by a test) on the run's own model and
project, every page the menu bar reaches (window.__eaxMenu, TopMenu.jsx: the menu as the person sees it, since R2.0),
then every tab the page shows: the navigation registry the page publishes (window.__eaxNav, PageNav.jsx: every
group's tabs, in any navigation style) and the tab bars on the page itself (sub-tabs). A tab added later is found the
day it is added. Only the run's own model(s) and project are opened, plus pages that name no model or project.

Each page is checked:
  * it renders: no script error, no answer of 500 or more from the API, and not the "not found" of a missing route;
  * a heading shows (the page has a title);
  * F1 opens the help panel, with help for that screen (not "No help for this screen yet").

The same sweep runs headless (here, Chromium in the runner) and watched in the admin's browser (TestRuns.jsx, the same
rules in JavaScript: SWEEP_JS below is the one source for the browser side)."""

from __future__ import annotations

import re
import time
from collections.abc import Callable

Record = Callable[..., None]

# the top-level pages of App.jsx; {m} the run's model, {p} its project. test_selftest_coverage.py checks every route of
# App.jsx is here or in SKIP_ROUTES, so a new page cannot be missed.
SEEDS = [
    "#/", "#/work", "#/repository", "#/reference-library", "#/enterprise-library", "#/my-profile", "#/documentation",
    "#/merge-requests", "#/archive", "#/project-admin", "#/metamodel", "#/metamodel/{m}", "#/model-admin/{m}", "#/projects",
    "#/projects/{p}", "#/mcp", "#/library", "#/project-library", "#/principles", "#/compare", "#/compare/gaps", "#/compare/common", "#/change-log",
    "#/notifications", "#/surveys", "#/maturity", "#/change-documents", "#/admin", "#/search?q=self_test", "#/farm",
    "#/farm/connect",
]
# pages the sweep does not open, and why
SKIP_ROUTES = {
    "#/break-glass": "the emergency sign-in page (it signs the person out of the normal sign-in)",
    "#/more": "Everything else: a page of the Classic menus, which are being retired (R2.0.1); every item is in the menu bar",
}
MAX_PAGES = 400
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_LEAVE = re.compile(r"^#/break-glass\b|logout|sign-?out", re.I)


def seeds(ids: dict[str, str]) -> list[str]:
    m, p = ids.get("model", ""), ids.get("project", "")
    out = []
    for s in SEEDS:
        if "{m}" in s and not m or "{p}" in s and not p:
            continue
        out.append(s.replace("{m}", m).replace("{p}", p))
    return out


def in_scope(route: str, ids: dict[str, str]) -> bool:
    """A page the sweep may open: a hash route of the app that names no model, project or entity other than the run's own."""
    if not route.startswith("#/") or _LEAVE.search(route):
        return False
    own = {v.lower() for k, v in ids.items() if v and k in ("model", "other_model", "project", "entity")}
    return all(u.lower() in own for u in _UUID.findall(route))


def norm(route: str) -> str:
    r = route.strip()
    r = re.sub(r"/+(\?|$)", r"\1", r)
    return r or "#/"


# the browser side of one page: what it found and its links (the registry plus the tab bars on the page)
PAGE_JS = """() => {
  const txt = (document.querySelector('main') || document.body).innerText || '';
  const head = [...document.querySelectorAll('main h1, main h2, main h3, main .nav-crumbs [aria-current]')]
    .some((h) => (h.innerText || '').trim().length > 1 && h.offsetParent !== null);
  const links = new Set();
  const nav = window.__eaxNav;
  if (nav && nav.groups) for (const g of nav.groups) for (const t of g.tabs) if (t.href) links.add(t.href);
  for (const h of (window.__eaxMenu || [])) links.add(h);   // every page the menu bar reaches (R2.0, D586; TopMenu.jsx)
  for (const a of document.querySelectorAll('[role=tablist] a[href^="#/"], .tabs a[href^="#/"], .nav-groups a[href^="#/"], '
      + '.nav-menu a[href^="#/"], nav.subnav a[href^="#/"], .subtabs a[href^="#/"], .seg a[href^="#/"]')) links.add(a.getAttribute('href'));
  return { head, notFound: /\\bno route\\b|^\\s*Not found\\s*$/im.test(txt), links: [...links] };
}"""

HELP_JS = """() => {
  const p = document.querySelector('.help-panel');
  if (!p) return 'closed';
  return /No help for this screen yet/.test(p.innerText) ? 'empty' : 'ok';
}"""


def judge(found: dict, errors: list[str], help_state: str) -> tuple[str, str]:
    """The outcome of one page from what the browser saw (also used by the unit tests)."""
    bad = []
    if errors:
        bad.append("; ".join(errors[:5]))
    if found.get("notFound"):
        bad.append("shows not found")
    if not found.get("head"):
        bad.append("no heading")
    if help_state != "ok":
        bad.append("F1 opened no help" if help_state == "closed" else "F1: no help for this screen")
    if not bad:
        return "passed", "renders, has a heading, F1 help"
    if errors or found.get("notFound"):
        return "failed", "; ".join(bad)
    return "warning", "; ".join(bad)


def sweep(page, open_route: Callable[[str], None], ids: dict[str, str], record: Record, max_pages: int = MAX_PAGES,
          role: str = "super-admin", routes: list[str] | None = None) -> dict[str, int]:
    """Opens every page reachable from the seeds through tab links, in scope; records one result per page
    ("page: <route>"). open_route(route) loads a route (the self-test's sign-in in the URL). Returns the counts.
    routes: these pages only, no links followed (a repeat of the failed pages, R2.36)."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"script error: {str(e)[:200]}"))
    page.on("response", lambda r: errors.append(f"{r.request.method} {r.url.split('?')[0]}: {r.status}")
            if "/api/" in r.url and r.status >= 500 else None)
    only = routes is not None
    queue = [norm(s) for s in (routes if only else seeds(ids))]
    seen: set[str] = set(queue)
    counts = {"pages": 0, "passed": 0, "failed": 0, "warning": 0}
    for route, why in ({} if only else SKIP_ROUTES).items():
        record(f"page: {route}", "skipped", why, 0)
    loaded = 0
    while queue and counts["pages"] < max_pages:
        route = queue.pop(0)
        t0 = time.time()
        errors.clear()
        try:
            if loaded % 25 == 0:
                open_route(route)                                  # a fresh load now and then: nothing carries over
            else:
                page.evaluate("r => { window.location.hash = r.slice(1); }", route)
            loaded += 1
            page.wait_for_selector("text=EA Explorer", timeout=60000)
            page.wait_for_timeout(1200)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:  # noqa: BLE001 - a page that keeps asking (a live status) is fine
                pass
            found = page.evaluate(PAGE_JS)
            for _ in range(20):                            # a heading that comes with the page's data: up to 10 s more
                if found.get("head") or found.get("notFound"):
                    break
                page.wait_for_timeout(500)
                found = page.evaluate(PAGE_JS)
            page.keyboard.press("F1")
            page.wait_for_timeout(300)
            help_state = page.evaluate(HELP_JS)
            page.keyboard.press("Escape")
            outcome, detail = judge(found, list(errors), help_state)
            for link in ([] if only else found["links"]):
                n = norm(link)
                if n not in seen and in_scope(n, ids):
                    seen.add(n)
                    queue.append(n)
        except Exception as exc:  # noqa: BLE001 - a page that breaks the browser is a failed page
            outcome, detail = "failed", str(exc).splitlines()[0][:300]
        counts["pages"] += 1
        counts[outcome] = counts.get(outcome, 0) + 1
        shot = None
        if outcome == "failed":
            try:
                shot = page.screenshot(full_page=False)
            except Exception:  # noqa: BLE001
                shot = None
            loaded = 0                                             # the next page loads fresh
        record(f"page: {route}", outcome, f"{detail} (as {role})", int((time.time() - t0) * 1000), screenshot=shot)
    if queue:
        record("page sweep", "warning", f"stopped at {max_pages} pages; {len(queue)} more not opened", 0)
    return counts
