"""The API test harness (R3.16; owner, 13 Nov 2026: "Add another story to test API in a test harness to test an api from
selection"; decided: "Reads anywhere, writes test data only").

On the Self-test page (IT and Super Admins), and as `eax test api <method> <path> [--as role] [--body file]`:

  endpoints()        every endpoint of the API's own description, with its area, summary, parameters and an example body
  session(...)       a harness session: a self-test run record (closed at once, so it blocks nothing) holding the test
                     accounts of the roles asked for (one-day tokens) and its own test data (models, project), the same
                     fixtures as a self-test run (eax.testing.fixtures); removed with End, or by the next self-test
  call(...)          one call, as yourself or as one of the session's roles: reads go anywhere; a write only when every
                     model or project in its path is test data (is_test_data); the status, the time, the headers, the
                     start of the body and the same call as a curl line
  cases              saved calls with the answer expected (status, fields), run one by one or all together; the
                     self-test runs them too, in its own test data ("case: <name>" in the API suite)

Every call is in the audit trail (api.harness.call). Nothing here bypasses the API's own checks: a call is an HTTP request
to the API itself, with the role's own token."""

from __future__ import annotations

import json
import re
import shlex
import time
from typing import Any

from sqlalchemy import text

from .metamodel_edit import EditError

SELF = "http://127.0.0.1:8000"          # the API from inside its own container
GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
WRITES = ("post", "put", "patch", "delete")
BODY_LIMIT = 200_000
MESSAGE = "API test harness"


# ---------------------------------------------------------------- the endpoints
def endpoints(spec: dict) -> list[dict[str, Any]]:
    """Every operation of the OpenAPI document: method, path, area, summary, parameters (path and query), whether it
    writes, and an example body built from its request schema."""
    from .machine_access import area_of
    comps = (spec.get("components") or {}).get("schemas") or {}
    out = []
    for path, ops in (spec.get("paths") or {}).items():
        for method, op in ops.items():
            if method not in ("get", *WRITES) or not isinstance(op, dict):
                continue
            params = [{"name": p.get("name"), "in": p.get("in"), "required": bool(p.get("required"))}
                      for p in op.get("parameters") or [] if p.get("in") in ("path", "query")]
            for name in re.findall(r"\{([^}]+)\}", path):
                if not any(p["name"] == name.split(":")[-1] for p in params):
                    params.append({"name": name.split(":")[-1], "in": "path", "required": True})
            schema = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            out.append({"method": method, "path": path, "area": area_of(path) or "other",
                        "summary": (op.get("summary") or op.get("description") or "").split("\n")[0][:200],
                        "params": params, "writes": method in WRITES,
                        "example": example(schema, comps) if method in WRITES else None})
    return sorted(out, key=lambda e: (e["area"], e["path"], e["method"]))


def example(schema: dict, comps: dict, depth: int = 0) -> Any:
    """A small example of a JSON schema (the form's starting body)."""
    if depth > 4 or not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        return example(comps.get(schema["$ref"].rsplit("/", 1)[-1]) or {}, comps, depth + 1)
    if "example" in schema:
        return schema["example"]
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        return {k: example(v, comps, depth + 1) for k, v in (schema.get("properties") or {}).items()}
    if t == "array":
        return [example(schema.get("items") or {}, comps, depth + 1)]
    return {"string": "", "integer": 0, "number": 0, "boolean": False}.get(t or "", None)


# ---------------------------------------------------------------- the write rule
def test_data_ids(conn) -> set[str]:
    """The guids of every model and project marked as test data (R2.11)."""
    conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
    ids = {r[0] for r in conn.execute(text("SELECT guid::text FROM core.models WHERE is_test_data")).all()}
    try:
        ids |= {r[0] for r in conn.execute(text("SELECT guid::text FROM proj.projects WHERE is_test_data")).all()}
    except Exception:  # noqa: BLE001 - projects in a database of their own: their writes are refused below
        pass
    conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
    return {i.lower() for i in ids}


def may_call(method: str, path: str, test_ids: set[str]) -> str:
    """Why a call is refused ("" when it may go ahead): reads anywhere; a write only into test data, so every model or
    project id in its path must be test data, and a write naming none is refused."""
    if method.lower() not in WRITES:
        return ""
    found = [g.lower() for g in GUID.findall(path)]
    if not found:
        return ("The harness writes only into test data: this write names no test model or project in its path. Use the "
                "session's own models and project ({model}, {project}).")
    outside = [g for g in found if g not in test_ids]
    if outside:
        return f"The harness writes only into test data; {outside[0]} is not test data."
    return ""


# ---------------------------------------------------------------- sessions
def session(repo, by: str, roles: list[str], log=lambda _m: None) -> dict[str, Any]:
    """A harness session: its run record (closed at once), the roles' accounts and tokens, its own test data."""
    from .testing import fixtures, store
    roles = [r for r in roles if r in store.TEST_ROLES] or ["super-admin"]
    if "super-admin" not in roles:
        roles = ["super-admin", *roles]                 # it makes the test data
    with store.engine().begin() as tc:
        run_id = store.create_run(tc, by, "web", ["api"], level="smoke")
        store.set_state(tc, run_id, state="running", step=MESSAGE)
        run = dict(tc.execute(text("SELECT id, run_guid::text AS run_guid FROM tests.test_runs WHERE id = :id"),
                              {"id": run_id}).mappings().first())
    with repo.begin() as conn:
        tokens = fixtures.accounts(conn, run, by, roles, log)
    ids = fixtures.models_and_project(repo, run, by, roles, log)
    with store.engine().begin() as tc:
        store.set_browser(tc, run_id, {"harness": True, "tokens": tokens, "ids": ids})
        store.finish(tc, run_id, stopped=f"{by} (an {MESSAGE} session: its test data stays until End)")
    return {"session": run_id, "roles": sorted(tokens), "ids": ids}


def session_row(run_id: int) -> dict[str, Any]:
    from .testing import store
    with store.engine().connect() as tc:
        row = tc.execute(text("SELECT id, browser FROM tests.test_runs WHERE id = :id"), {"id": run_id}).mappings().first()
    b = (row or {}).get("browser") or {}
    if isinstance(b, str):
        b = json.loads(b)
    if not row or not b.get("harness"):
        raise EditError(f"No API harness session {run_id}: start one first.", 404)
    return {"id": run_id, "tokens": b.get("tokens") or {}, "ids": b.get("ids") or {}}


def latest_session() -> int | None:
    from .testing import store
    with store.engine().connect() as tc:
        return tc.execute(text("""SELECT id FROM tests.test_runs WHERE browser ? 'harness' AND (browser ->> 'harness') = 'true'
                                     AND queued_at > now() - interval '20 hours' ORDER BY id DESC LIMIT 1""")).scalar()


def end(repo, run_id: int, by: str) -> dict[str, Any]:
    """Removes the session's test data, accounts and tokens."""
    from .testing import fixtures, store
    session_row(run_id)
    out = fixtures.remove_at_end(repo, run_id, lambda _m: None) or {}
    with store.engine().begin() as tc:
        store.set_browser(tc, run_id, {"harness": False, "tokens": {}, "ended_by": by})
    return {"session": run_id, "removed": out}


# ---------------------------------------------------------------- one call
def fill(path: str, ids: dict[str, str]) -> str:
    """{model}, {model_id}, {project}, {entity} ... from the session's own ids; others are left for the person."""
    def one(m: re.Match) -> str:
        name = m.group(1).split(":")[-1]
        for key in (name, name.removesuffix("_id"), name.removesuffix("_guid")):
            if ids.get(key):
                return str(ids[key])
        return m.group(0)
    return re.sub(r"\{([^}]+)\}", one, path)


def curl_line(method: str, url: str, body: Any, as_who: str) -> str:
    parts = ["curl", "-sk", "-X", method.upper(), shlex.quote(url), "-H", shlex.quote("Authorization: Bearer <token of " + as_who + ">")]
    if body is not None and method.lower() in WRITES:
        parts += ["-H", shlex.quote("Content-Type: application/json"), "--data", shlex.quote(json.dumps(body))]
    return " ".join(parts)


def call(method: str, path: str, token: str, body: Any = None, query: dict | None = None, test_ids: set[str] | None = None,
         as_who: str = "you", base: str = SELF, http=None) -> dict[str, Any]:
    """One call through the API itself; refused (not sent) when it would write outside test data."""
    import urllib.error
    import urllib.parse
    import urllib.request

    from .service_split import route
    method = method.lower()
    if not path.startswith("/api/"):
        raise EditError("The path starts with /api/ (choose an endpoint from the list).", 400)
    if "{" in path:
        raise EditError(f"Fill in every part of the path first: {path}", 400)
    why = may_call(method, path, test_ids or set())
    if why:
        raise EditError(why, 403)
    qs = ("?" + urllib.parse.urlencode({k: v for k, v in (query or {}).items() if v not in (None, "")})) if query else ""
    target = route(base, path) + path + qs
    data = json.dumps(body if body is not None else {}).encode() if method in ("post", "put", "patch") else None
    req = urllib.request.Request(target, data=data, method=method.upper(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "Authorization": f"Bearer {token}"})
    t0 = time.time()
    opener = http or urllib.request.urlopen
    try:
        with opener(req, timeout=120) as r:
            status, headers, raw = r.status, dict(r.headers.items()), r.read(BODY_LIMIT + 1)
    except urllib.error.HTTPError as exc:
        status, headers, raw = exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read(BODY_LIMIT + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        status, headers, raw = 599, {}, f"no answer: {exc}".encode()
    ms = int((time.time() - t0) * 1000)
    txt = raw[:BODY_LIMIT].decode("utf-8", "replace")
    try:
        parsed: Any = json.loads(txt)
    except ValueError:
        parsed = None
    return {"status": status, "ms": ms, "headers": headers, "body": txt, "json": parsed, "cut": len(raw) > BODY_LIMIT,
            "curl": curl_line(method, f"https://<your EA Explorer>{path}{qs}", body, as_who)}


# ---------------------------------------------------------------- cases
def check(case: dict, answer: dict) -> tuple[bool, str]:
    """Whether an answer is what the case expects: its status, and each expected field (a dotted path) equal."""
    problems = []
    want = case.get("expect_status")
    if want and answer.get("status") != int(want):
        problems.append(f"status {answer.get('status')}, expected {want}")
    for field, value in (case.get("expect_fields") or {}).items():
        got: Any = answer.get("json")
        for part in str(field).split("."):
            got = got.get(part) if isinstance(got, dict) else (got[int(part)] if isinstance(got, list) and part.isdigit()
                                                               and int(part) < len(got) else None)
        if got != value:
            problems.append(f"{field} is {json.dumps(got)[:80]}, expected {json.dumps(value)[:80]}")
    return not problems, "; ".join(problems) or f"{answer.get('status')} as expected ({answer.get('ms')} ms)"


def save_case(conn, by: str, c: dict) -> dict[str, Any]:
    name = str(c.get("name") or "").strip()[:200]
    if not name:
        raise EditError("Give the case a name.", 400)
    method = str(c.get("method") or "get").lower()
    if method not in ("get", *WRITES):
        raise EditError(f"Unknown method {method}.", 400)
    row = conn.execute(text("""INSERT INTO tests.api_cases (name, method, path, query, body, as_role, expect_status,
                                                            expect_fields, created_by)
                               VALUES (:n, :m, :p, CAST(:q AS jsonb), CAST(:b AS jsonb), :a, :s, CAST(:f AS jsonb), :by)
                               ON CONFLICT (name) DO UPDATE SET method = EXCLUDED.method, path = EXCLUDED.path,
                                     query = EXCLUDED.query, body = EXCLUDED.body, as_role = EXCLUDED.as_role,
                                     expect_status = EXCLUDED.expect_status, expect_fields = EXCLUDED.expect_fields,
                                     created_by = EXCLUDED.created_by, created_at = now()
                               RETURNING id"""),
                       {"n": name, "m": method, "p": str(c.get("path") or "")[:500], "q": json.dumps(c.get("query") or {}),
                        "b": json.dumps(c.get("body")), "a": str(c.get("as") or "super-admin")[:40],
                        "s": int(c["expect_status"]) if c.get("expect_status") else None,
                        "f": json.dumps(c.get("expect_fields") or {}), "by": by}).scalar()
    return {"id": int(row), "name": name}


def cases(conn) -> list[dict[str, Any]]:
    rows = conn.execute(text("""SELECT id, name, method, path, query, body, as_role, expect_status, expect_fields,
                                       created_by, created_at FROM tests.api_cases ORDER BY name""")).mappings().all()
    return [dict(r) for r in rows]


def delete_case(conn, case_id: int) -> bool:
    return bool(conn.execute(text("DELETE FROM tests.api_cases WHERE id = :i RETURNING id"), {"i": case_id}).first())


def run_cases(rows: list[dict], tokens: dict[str, str], ids: dict[str, str], test_ids: set[str], base: str = SELF,
              http=None) -> list[dict[str, Any]]:
    """Each case in the session's (or a self-test run's) own test data, as its role; passed or failed with the reason."""
    out = []
    for c in rows:
        token = tokens.get(c.get("as_role") or "super-admin") or tokens.get("super-admin") or ""
        path = fill(c.get("path") or "", ids)
        try:
            answer = call(c.get("method") or "get", path, token, c.get("body"), c.get("query") or {}, test_ids,
                          c.get("as_role") or "super-admin", base, http)
            ok, why = check(c, answer)
        except EditError as exc:
            ok, why = False, str(exc)
        out.append({"id": c.get("id"), "name": c.get("name"), "passed": ok, "detail": why, "path": path})
    return out
