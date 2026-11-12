"""API tests: every endpoint, every test role, allowed and refused (phase 36.1, D367, D524).

The endpoints come from the test API's own OpenAPI document, so a new endpoint is tested the day it is added. For
each one:
  * **no token**: refused (401) unless the document marks it public; never a server error;
  * **every test role** (the run's own accounts, one per role: eax/testing/fixtures.py) on GET: allowed or refused, never a
    server error (500) and never "not signed in" (401) with a valid token. 502/503/504 are a warning: the endpoint
    needs a service the test API is kept away from (the operations helper, the library, views, Documents);
  * a writing call (POST, PUT, PATCH, DELETE) by **someone with no global role** (the run's no-role account) on /admin/...:
    refused (403), so nobody without a role can change the system;
  * **cross-user**: a model's content (entities, relationships, history...) read by someone with no role on the model
    (the run's no-role account on the run's second model) is refused; anything else readable without a role on the model is listed as
    a warning to look at.
Path parameters are filled from the run's own fixtures (self_test_<id>_1, one of its entities, self_test_<id>_3); an
endpoint whose parameters cannot be filled is skipped with the reason. The whole matrix is one result per endpoint and
check, so the Health page lists exactly what failed."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

NO_GLOBAL_ROLE = "no-role"          # the run's account with no global role and no role on any model
# reads too heavy or not meant for an automated reader (whole-estate files, live logs, terminals, the SQL window): skipped
HEAVY = re.compile(r"/(backups?|restores?|export|download|package|packages|terminal|logs|sql|stats|files|repo-zip)(/|$)|\.(zip|xlsx|pdf|docx)$")
CONTENT = re.compile(r"/(entities|relationships|history|grid|content|changes|commits|data-entry|hierarchy|export)\b")
WRITE = ("post", "put", "patch", "delete")


def call(base: str, method: str, path: str, token: str | None = None, timeout: int = 60,
         size: int | None = 1500) -> tuple[int, str]:
    """The HTTP status of one call and the start of its answer, its first `size` bytes (None: the whole answer); a
    writing call sends an empty JSON body."""
    data = b"{}" if method.upper() in ("POST", "PUT", "PATCH") else None
    req = urllib.request.Request(base + path, data=data, method=method.upper(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(size if size else -1).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(1500).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            body = ""
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 599, f"no answer: {exc}"


def _ask(method: str, path: str, who: str | None) -> str:
    return f"{method.upper()} {path}  as {who or 'nobody (no token)'}" + ("  body {}" if method.upper() in ("POST", "PUT", "PATCH") else "")


def _answer(status: int, body: str) -> str:
    return f"{status}\n{body}"


def endpoints(spec: dict) -> list[dict]:
    """(path, method, public) for every operation of an OpenAPI 3 document; public = no security asked."""
    default = spec.get("security")
    out = []
    for path, ops in (spec.get("paths") or {}).items():
        for method, op in ops.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete") or not isinstance(op, dict):
                continue
            sec = op.get("security", default)
            out.append({"path": path, "method": method.lower(), "public": not sec})
    return sorted(out, key=lambda e: (e["path"], e["method"]))


def fill(path: str, ids: dict[str, str]) -> str | None:
    """The path with its {parameters} filled from ids (by name; *_id names fall back to their stem), or None."""
    def one(m: re.Match) -> str:
        name = m.group(1).split(":")[-1]
        for key in (name, name.removesuffix("_id"), name.removesuffix("_guid")):
            if key in ids:
                return ids[key]
        raise KeyError(name)
    try:
        return re.sub(r"\{([^}]+)\}", one, path)
    except KeyError:
        return None


def judge_anonymous(status: int, public: bool) -> tuple[str, str]:
    if status >= 500 and status != 599:
        return ("warning" if status in (502, 503, 504) else "failed"), f"server error {status} without a token"
    if status == 599:
        return "failed", "no answer"
    if public:
        return "passed", f"public: {status}"
    if 200 <= status < 300:
        return "failed", f"answered {status} without a token: it should be refused (401)"
    return "passed", f"refused: {status}"


# endpoints that take their own key instead of a person's token: a 401 or 400 with a valid token is right there (R2.0.1)
OWN_KEY = {
    "/api/v1/admin/scaling/load": "the operations helper's X-Ops-Token",
    "/api/v1/selftest/session": "a running self-test's ticket",
    "/api/v1/testbench/runs/{run_id}/session": "a test bench run's ticket",
}


def judge_role(status: int, own_key: str = "") -> tuple[str, str]:
    if own_key and status in (400, 401, 403):
        return "passed", f"refused: {status} (it takes {own_key}, not a token)"
    if status in (502, 503, 504):
        return "warning", f"{status}: needs a service the test API is kept away from"
    if status == 599:
        return "failed", "no answer"
    if status >= 500:
        return "failed", f"server error {status}"
    if status == 401:
        return "failed", "401 with a valid token"
    return "passed", ("allowed" if status < 400 else "refused") + f": {status}"


def in_area(path: str, area: str) -> bool:
    """True when the endpoint belongs to the API area (machine access's areas, D366), or no area is asked."""
    if not area:
        return True
    from ..machine_access import area_of
    return (area_of(path) or "other") == area


Record = Callable[..., None]


def run(base: str, spec: dict, tokens: dict[str, str], ids: dict[str, str], other_model: str | None, record: Record,
        workers: int = 6, area: str = "", only: set[str] | None = None) -> dict[str, int]:
    """Runs the matrix against base (the test API) and records each check with record(name, outcome, detail, ms,
    request=..., response=...); a failed check keeps what was asked and what came back. area: one API area only;
    only: these checks by name only (a repeat of the failed ones, R2.36).
    Six calls at a time, each given 60 seconds (R2.0.1): more at once queued behind the API's workers and database
    connections on a laptop and timed out as "no answer" though every endpoint answers in well under a second alone."""
    eps = [e for e in endpoints(spec) if in_area(e["path"], area)]
    counts = {"endpoints": len(eps), "checks": 0}
    jobs: list[tuple[str, Callable[[], tuple]]] = []

    for ep in eps:
        path = fill(ep["path"], ids)
        label = f"{ep['method'].upper()} {ep['path']}"
        if HEAVY.search(ep["path"]):
            jobs.append((f"{label}: skipped", lambda: ("skipped", "a heavy or live read (files, logs, terminals): not read by the self-test", "", "")))
            continue
        if path is None:
            jobs.append((f"{label}: skipped", lambda: ("skipped", "a path parameter the run's fixtures cannot fill", "", "")))
            continue

        def anon(p=path, m=ep["method"], pub=ep["public"]):
            status, body = call(base, m, p)
            outcome, detail = judge_anonymous(status, pub)
            return outcome, detail, _ask(m, p, None), _answer(status, body)
        jobs.append((f"{label}: without a token", anon))
        if ep["method"] == "get":
            key = OWN_KEY.get(ep["path"], "")

            def roles(p=path, key=key):
                bad, seen, asked, answered = [], [], "", ""
                for user, token in tokens.items():
                    status, body = call(base, "get", p, token)
                    outcome, detail = judge_role(status, key)
                    seen.append(f"{user.removeprefix('user_')} {detail.split(':')[-1].strip()}")
                    if outcome != "passed":
                        bad.append((outcome, f"{user}: {detail}"))
                        if outcome == "failed" and not asked:
                            asked, answered = _ask("get", p, user), _answer(status, body)
                if any(o == "failed" for o, _ in bad):
                    return "failed", "; ".join(d for o, d in bad if o == "failed"), asked, answered
                if bad:
                    return "warning", "; ".join(d for _o, d in bad), "", ""
                return "passed", ", ".join(seen), "", ""
            if tokens:
                jobs.append((f"{label}: every test role" if len(tokens) > 1 else f"{label}: as {next(iter(tokens))}", roles))
            if other_model and NO_GLOBAL_ROLE in tokens and "{model_id}" in ep["path"]:
                p2 = fill(ep["path"], {**ids, "model": other_model, "model_id": other_model})
                is_content = bool(CONTENT.search(ep["path"]))

                def cross(p=p2, content=is_content):
                    s, body = call(base, "get", p, tokens[NO_GLOBAL_ROLE])
                    req, resp = _ask("get", p, NO_GLOBAL_ROLE), _answer(s, body)
                    if s in (403, 404):
                        return "passed", f"refused to someone with no role on the model: {s}", "", ""
                    if 200 <= s < 300:
                        return ("failed" if content else "warning"), \
                            f"answered {s} to someone with no role on the model" + ("" if content else ": check this is meant"), req, resp
                    o, d = judge_role(s)
                    return o, d, req if o == "failed" else "", resp if o == "failed" else ""
                if p2:
                    jobs.append((f"{label}: cross-user (no role on the model)", cross))
        elif ep["path"].startswith("/api/v1/admin/") and NO_GLOBAL_ROLE in tokens:
            def refused(p=path, m=ep["method"]):
                s, body = call(base, m, p, tokens[NO_GLOBAL_ROLE])
                req, resp = _ask(m, p, NO_GLOBAL_ROLE), _answer(s, body)
                if 200 <= s < 300:
                    return "failed", f"{m.upper()} answered {s} to someone with no global role", req, resp
                if s >= 500:
                    o, d = judge_role(s)
                    return o, d, req if o == "failed" else "", resp if o == "failed" else ""
                return "passed", f"refused: {s}", "", ""
            jobs.append((f"{label}: refused without a global role", refused))

    def go(job):
        name, fn = job
        t0 = time.time()
        try:
            outcome, detail, req, resp = fn()
        except Exception as exc:  # noqa: BLE001 - one check never stops the matrix
            outcome, detail, req, resp = "failed", f"the check broke: {exc}", "", ""
        if outcome not in ("failed",):
            req, resp = "", ""
        return name, outcome, detail, int((time.time() - t0) * 1000), req, resp

    if only is not None:                                   # a repeat (R2.36): the failed checks only
        jobs = [j for j in jobs if j[0] in only]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for name, outcome, detail, ms, req, resp in pool.map(go, jobs):
            record(name, outcome, detail, ms, request=req, response=resp)
            counts["checks"] += 1
    return counts


def fetch_spec(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/api/openapi.json", timeout=30) as r:
        return json.load(r)


