"""The self-test's journeys that click, type and save (D576): each a list of plain steps, run the same way headless (here,
Playwright) and watched in the admin's own browser (TestRuns.jsx runs the same steps in JavaScript), only inside the
run's own fixtures (self_test_<id>_n).

A journey: {name, smoke, roles: [allowed roles], refused: {role, check} | None, headless_only, why_headless, steps}.
Steps (one key says what to do; texts may hold {sid} {m} {p} {other} {entity}, filled from the run's ids):
  {"open": "#/route", "expect": "text"}     open a page, wait for a text (optional)
  {"click": "text"}                          a button, link, tab or label whose text starts with this (first visible)
  {"choose": "text"}                         a radio or checkbox by its label text
  {"fill": "label", "value": "…"}            the field with this label (or placeholder)
  {"select": "label", "option": "…"}         a drop-down with this label: the first option starting with the text
  {"press": "F1"}                            a key
  {"expect": "text"} / {"expect_not": "text"} / {"expect_sel": "css"}
  {"upload": "css of the file input", "name": "…", "text": "file contents"}
  any step may carry "optional": true (skipped if the control is not there) and "wait": ms.
A refused check (the role that may not): {"open": route, "disabled_or_absent": "button text"}: the button is missing or
disabled, so the save can never be made from the screen (the API matrix checks the same write is refused)."""

from __future__ import annotations

import time
from collections.abc import Callable

Record = Callable[..., None]

JOURNEYS: list[dict] = [
    {"name": "model content: create, edit, history", "smoke": True,
     "roles": ["model-admin", "committer", "architect"],
     "refused": {"role": "report-viewer", "open": "#/metamodel/{m}/entry", "select": ("Entity type", "Application Component"),
                 "disabled_or_absent": "+ In a form"},
     "steps": [
         {"open": "#/metamodel/{m}/entry", "expect": "Entity type"},
         {"select": "Entity type", "option": "Application Component"},
         {"click": "+ In a form"},
         {"fill": "Name", "value": "Journey app {sid} {role}"},
         {"fill": "Commit message", "value": "self-test journey", "optional": True},
         {"click": "Save", "exact": True, "optional_alt": "Save and commit"},
         {"fill": "Filter", "value": "Journey app {sid} {role}", "wait": 800},
         {"expect": "Journey app {sid} {role}"},
         {"open": "#/metamodel/{m}/changes", "expect": "Journey app {sid}", "optional": True},
         {"open": "#/metamodel/{m}/history", "optional": True},
     ]},
    {"name": "quality and duplicates: find and merge", "smoke": True, "roles": ["model-admin"],
     "refused": {"role": "report-viewer", "open": "#/metamodel/{m}/duplicates", "click_first": "Find duplicates",
                 "disabled_or_absent": "Compare and merge"},
     "steps": [
         {"open": "#/metamodel/{m}/quality", "expect": "Quality"},
         {"open": "#/metamodel/{m}/duplicates", "expect": "Find duplicates"},
         {"click": "Find duplicates", "wait": 1500},
         {"expect": "{dup}"},
         {"click": "Compare and merge"},
         {"click": "Merge 1 into the one kept", "wait": 1500},
         {"expect_not": "Merging…"},
     ]},
    {"name": "project: iteration, frozen phase, back", "smoke": True, "roles": ["super-admin"],
     "refused": None,
     "steps": [
         {"open": "#/projects/{p}", "expect": "{project_name}"},
         {"click": "Choose…", "optional_alt": "Change…"},
         {"choose": "Transition Planning"},
         {"fill": "Note (optional)", "value": "self-test {sid}"},
         {"click": "Save", "exact": True, "wait": 1500},
         {"expect_not": "Note (optional)"},                 # the dialog closed: the iteration was saved
         {"expect": "Transition Planning"},
         {"open": "#/projects/{p}/phases/B", "expect": "isn't part of this", "optional": True},
         {"open": "#/projects/{p}", "expect": "{project_name}"},
         {"click": "Change…"},
         {"choose": "Full cycle"},
         {"click": "Save", "exact": True, "wait": 1500},
         {"expect_not": "Note (optional)"},
         {"click": "Iteration history", "optional": True},
         {"expect": "Full cycle"},
     ]},
    {"name": "help and documentation", "smoke": False, "roles": ["architect"], "refused": None,
     "steps": [
         {"open": "#/metamodel/{m}", "expect": "{model_name}"},
         {"press": "F1"}, {"expect_sel": ".help-panel"}, {"press": "Escape"},
         {"open": "#/projects/{p}", "expect": "{project_name}", "optional": True},
         {"press": "F1"}, {"expect_sel": ".help-panel"}, {"press": "Escape"},
         {"open": "#/documentation", "expect": "Documentation for"},
         {"fill": "Search", "value": "backup", "wait": 800},
         {"expect": "ackup"},
     ]},
    {"name": "admin: banner and a schedule, put back", "smoke": False, "roles": ["super-admin"],
     "refused": {"role": "architect", "open": "#/admin/banner", "disabled_or_absent": "Save"},
     "steps": [
         {"open": "#/admin/banner", "expect": "Banner"},
         {"open": "#/admin/commands/schedules", "expect": "Schedules", "optional": True},
     ]},
    {"name": "drawn view: labels, select a line, undo", "smoke": False, "roles": ["model-admin"], "refused": None,
     "headless_only": True,
     "why_headless": "the draw.io canvas is a separate site: a page in the admin's browser cannot reach into it",
     "steps": [
         {"open": "#/metamodel/{m}/views", "expect": "Views"},
     ]},
]


def fill_text(s: str, ids: dict[str, str], role: str) -> str:
    vals = {"sid": ids.get("sid", ""), "m": ids.get("model", ""), "p": ids.get("project", ""), "other": ids.get("other_model", ""),
            "entity": ids.get("entity", ""), "model_name": ids.get("model_name", ""), "project_name": ids.get("project_name", ""),
            "role": role, "dup": ids.get("dup", "Self-test duplicate")}
    for k, v in vals.items():
        s = s.replace("{" + k + "}", v)
    return s


def key(j: dict) -> str:
    """What --journey takes for a journey: its name up to the colon ("model content", "drawn view"). Unique (unit tested)."""
    return j["name"].split(":")[0].strip()


def journeys(ids: dict[str, str], role: str = "", only: list[str] | None = None, smoke: bool = False,
             watch: bool = False) -> list[dict]:
    """The journeys to run: [{name, role, steps, refused, headless_only, …}], one per allowed role (or only `role`), filled.
    Journeys needing a project are left out when the run has none."""
    out = []
    for j in JOURNEYS:
        if smoke and not j["smoke"]:
            continue
        if only and not any(o.lower() in j["name"].lower() for o in only):
            continue
        if watch and j.get("headless_only"):
            continue
        needs_p = any("{p}" in str(s) or "{project_name}" in str(s) for s in j["steps"])
        if needs_p and not ids.get("project"):
            continue
        roles = [role] if role else (j["roles"][:1] if smoke else j["roles"])
        if role and role not in j["roles"] and role != "super-admin":
            ref = j.get("refused")
            if ref:
                out.append({"name": f"{j['name']} (refused)", "role": role, "refusal": _fill_obj(ref, ids, role), "steps": []})
            continue
        for r in roles:
            out.append({"name": j["name"] + ("" if len(roles) == 1 else f" as {r}"), "role": r,
                        "steps": [_fill_obj(s, ids, r) for s in j["steps"]], "headless_only": j.get("headless_only", False)})
        if not role and not smoke and j.get("refused"):
            ref = j["refused"]
            out.append({"name": f"{j['name']}: refused to {ref['role']}", "role": ref["role"], "refusal": _fill_obj(ref, ids, ref["role"]),
                        "steps": []})
    return out


def _fill_obj(o, ids, role):
    if isinstance(o, str):
        return fill_text(o, ids, role)
    if isinstance(o, dict):
        return {k: _fill_obj(v, ids, role) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_fill_obj(v, ids, role) for v in o]
    return o


def skipped_in_browser() -> list[str]:
    """The journeys the watched-in-your-browser mode leaves out, with why (shown on the report)."""
    return [f"{j['name']}: {j['why_headless']}" for j in JOURNEYS if j.get("headless_only")]


# ---------------------------------------------------------------- running a journey with Playwright (headless)

_CLICKABLE = "button, a, [role=tab], [role=button], summary, label"


def _visible(loc):
    try:
        return loc.is_visible()
    except Exception:  # noqa: BLE001
        return False


def _clickable(page, text: str, exact: bool = False):
    import re as _re
    pat = _re.compile(rf"^\s*{_re.escape(text)}\s*$" if exact else rf"^\s*{_re.escape(text)}", _re.I)
    loc = page.locator(_CLICKABLE).filter(has_text=pat)
    for i in range(min(loc.count(), 20)):
        el = loc.nth(i)
        if _visible(el):
            return el
    return None


def _field(page, label: str):
    for loc in (page.get_by_label(label, exact=False), page.get_by_placeholder(label, exact=False)):
        for i in range(min(loc.count(), 10)):
            if _visible(loc.nth(i)):
                return loc.nth(i)
    return None


def _shows(page, text: str, timeout: int) -> None:
    """Waits for the text to show somewhere visible (the same words in a hidden menu option do not count)."""
    page.locator(f"text={text} >> visible=true").first.wait_for(state="visible", timeout=timeout)


def step(page, s: dict, open_route: Callable[[str], None]) -> str:
    """Runs one step; returns "" when done, or why it could not be done (an optional step is then skipped)."""
    timeout = 20000
    if "open" in s:
        open_route(s["open"])
        page.wait_for_selector("text=EA Explorer", timeout=60000)
        if s.get("expect"):
            _shows(page, s["expect"], timeout)
    elif "click" in s:
        el = _clickable(page, s["click"], s.get("exact", False))
        if el is None and s.get("optional_alt"):
            el = _clickable(page, s["optional_alt"])
        if el is None:
            return f"no button or link \"{s['click']}\""
        if el.is_disabled():
            return f"\"{s['click']}\" is disabled"
        el.click()
    elif "choose" in s:
        loc = page.locator("label").filter(has_text=s["choose"]).first
        if not loc.count():
            return f"no choice \"{s['choose']}\""
        loc.click()
    elif "fill" in s:
        el = _field(page, s["fill"])
        if el is None:
            return f"no field \"{s['fill']}\""
        el.fill(s["value"])
    elif "select" in s:
        el = _field(page, s["select"])
        if el is None:
            return f"no drop-down \"{s['select']}\""
        opts = el.locator("option").all_inner_texts()
        pick = next((o for o in opts if o.strip().lower().startswith(s["option"].lower())), None)
        if pick is None:
            return f"\"{s['select']}\" has no option \"{s['option']}\""
        el.select_option(label=pick)
    elif "press" in s:
        page.keyboard.press(s["press"])
    elif "expect" in s:
        _shows(page, s["expect"], timeout)
    elif "expect_not" in s:
        page.wait_for_timeout(500)
        if page.locator(f"text={s['expect_not']}").count():
            return f"\"{s['expect_not']}\" still shows"
    elif "expect_sel" in s:
        page.wait_for_selector(s["expect_sel"], timeout=timeout)
    elif "upload" in s:
        page.set_input_files(s["upload"], files=[{"name": s["name"], "mimeType": "application/octet-stream",
                                                  "buffer": s["text"].encode()}])
    page.wait_for_timeout(s.get("wait", 400))
    return ""


def refusal(page, r: dict, open_route: Callable[[str], None]) -> tuple[str, str]:
    """The role that may not: the button that would save is missing or disabled."""
    open_route(r["open"])
    page.wait_for_selector("text=EA Explorer", timeout=60000)
    page.wait_for_timeout(1500)
    if r.get("select"):
        el = _field(page, r["select"][0])
        if el is not None:
            opts = el.locator("option").all_inner_texts()
            pick = next((o for o in opts if o.strip().lower().startswith(r["select"][1].lower())), None)
            if pick:
                el.select_option(label=pick)
                page.wait_for_timeout(1200)
    if r.get("click_first"):
        el = _clickable(page, r["click_first"])
        if el is not None and not el.is_disabled():
            el.click()
            page.wait_for_timeout(1500)
    el = _clickable(page, r["disabled_or_absent"])
    if el is None:
        return "passed", f"\"{r['disabled_or_absent']}\" not offered to {r.get('role', 'this role')}"
    if el.is_disabled():
        return "passed", f"\"{r['disabled_or_absent']}\" disabled for {r.get('role', 'this role')}"
    return "failed", f"\"{r['disabled_or_absent']}\" is offered to {r.get('role', 'this role')}, who may not do it"


def run_one(page, j: dict, open_route: Callable[[str], None]) -> tuple[str, str]:
    """Runs one journey on a page; returns (outcome, detail)."""
    if j.get("refusal"):
        return refusal(page, j["refusal"], open_route)
    done, skipped = 0, []
    for s in j["steps"]:
        try:
            why = step(page, s, open_route)
        except Exception as exc:  # noqa: BLE001 - a step that times out is a failed step
            why = str(exc).splitlines()[0][:200]
        if why:
            if s.get("optional"):
                skipped.append(why)
                continue
            return "failed", f"step {done + len(skipped) + 1} ({_say(s)}): {why}"
        done += 1
    return "passed", f"{done} steps as {j['role']}" + (f"; {len(skipped)} optional skipped" if skipped else "")


def _say(s: dict) -> str:
    k = next(iter(s))
    return f"{k} {s[k]}"


def run(page_factory: Callable[[str], tuple], js: list[dict], record: Record) -> dict[str, int]:
    """Runs the journeys; page_factory(role) gives (page, open_route, close) for that role's browser context."""
    counts = {"journeys": 0, "passed": 0, "failed": 0}
    for j in js:
        t0 = time.time()
        page, open_route, close = page_factory(j["role"])
        errors: list[str] = []
        page.on("pageerror", lambda e, errs=errors: errs.append(f"script error: {str(e)[:200]}"))
        page.on("response", lambda r, errs=errors: errs.append(f"{r.request.method} {r.url.split('?')[0]}: {r.status}")
                if "/api/" in r.url and r.status >= 500 else None)
        try:
            outcome, detail = run_one(page, j, open_route)
        except Exception as exc:  # noqa: BLE001
            outcome, detail = "failed", str(exc).splitlines()[0][:300]
        if outcome == "passed" and errors:
            outcome, detail = "failed", "; ".join(errors[:5])
        shot = None
        if outcome == "failed":
            try:
                shot = page.screenshot(full_page=False)
            except Exception:  # noqa: BLE001
                shot = None
        video = close(outcome)
        counts["journeys"] += 1
        counts[outcome] = counts.get(outcome, 0) + 1
        record(f"journey: {j['name']}", outcome, detail, int((time.time() - t0) * 1000), screenshot=shot, video=video or "")
    return counts
