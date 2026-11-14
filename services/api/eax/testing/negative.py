"""Negative tests for every endpoint (R3.9; owner, 13 Nov 2026: "I think we are not doing any negative test cases we need to
fix that"; "API testing and DB testing is must. This is not white box testing").

Black-box, through the API as a Super Admin (the role that gets furthest into each endpoint), in the run's own test data:

  bad JSON       every write is sent a body that is not JSON: answered 400 or 422 (or 401/403/404/405/409/415), never a
                 server error, never a success
  not an object  every write is sent a JSON array where an object is expected: the same
  unknown id     every read with an id in its path is called with an id that is not there (a well-formed guid, a number,
                 or self-test-nothing): 400, 403 or 404, never a server error, never someone else's data
  too long       every write that takes a name is sent one of 100,000 characters: refused or cut, never a server error
  SQL text       every write inside the test data that takes a name is sent one that is SQL: kept as text or refused,
                 never a server error (a server error is a sign the text reached the database as SQL)

A write is only ever sent to an endpoint that declares a JSON body (one that might act without reading a body is never
called), with a body the API must refuse before doing anything, and only to paths in the run's own test data or with an
id that is never there; the long name only inside the run's own test data. Nothing real can change even when a check
finds a bug. One result per
endpoint and kind ("negative: bad JSON: POST /api/v1/..."), in the suite "api"; the counts by kind go to the report and
the coverage page (R3.10)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .api_matrix import NOTHING, fill

KINDS = ("bad JSON", "not an object", "unknown id", "too long", "SQL text")
SQL_TEXT = "x'); DROP TABLE core.models; --"
GOOD = {400, 401, 403, 404, 405, 409, 413, 415, 422}
UNKNOWN_GUID = "00000000-0000-4000-8000-00000000dead"
WRITES = ("post", "put", "patch")


def send(base: str, method: str, path: str, token: str, raw: bytes | None, timeout: int = 60) -> tuple[int, str]:
    from ..service_split import route
    req = urllib.request.Request(route(base, path) + path, data=raw, method=method.upper(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(800).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, exc.read(800).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return exc.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 599, f"no answer: {exc}"


def judge(status: int, kind: str) -> tuple[str, str]:
    if status in GOOD:
        return "passed", f"refused: {status}"
    if status >= 500 and status != 599:
        return "failed", f"server error {status} for {kind}"
    if status == 599:
        return "warning", "no answer"
    if 200 <= status < 300 and kind == "SQL text":
        return "passed", f"kept as text ({status})"
    if 200 <= status < 300 and kind == "too long":
        return "warning", f"accepted a name of 100,000 characters ({status}): check it is cut"
    if 200 <= status < 300:
        return "failed", f"answered {status} to {kind}: it should be refused"
    return "warning", f"answered {status}"


def unknown_path(path: str, ids: dict[str, str]) -> str | None:
    """The path with its last parameter replaced by an id that is not there (the others from the test data)."""
    names = re.findall(r"\{([^}]+)\}", path)
    if not names:
        return None
    last = names[-1]
    kind = last.split(":")[0] if ":" in last else ""
    fake = "999999999" if kind == "int" else UNKNOWN_GUID if kind in ("", "uuid", "string") else NOTHING
    head = path[:path.rindex("{" + last + "}")] + fake + path[path.rindex("{" + last + "}") + len(last) + 2:]
    return fill(head, ids)


def _schema(spec: dict, body: dict) -> dict:
    """The JSON body's schema, its $ref followed."""
    sch = ((body.get("content") or {}).get("application/json") or {}).get("schema") or {}
    for _ in range(5):
        ref = sch.get("$ref")
        if not ref:
            break
        node = spec
        for part in ref.lstrip("#/").split("/"):
            node = (node or {}).get(part) or {}
        sch = node
    return sch


def checks(spec: dict, ids: dict[str, str]) -> list[tuple[str, str, str, bytes | None, str]]:
    """(kind, method, path, body, the endpoint as described) for every endpoint: only paths in the run's own test data,
    or with an id that is not there."""
    out = []
    for path, ops in (spec.get("paths") or {}).items():
        for method in ops:
            m = method.lower()
            if m in WRITES:
                body = ops[method].get("requestBody") or {}
                if "application/json" not in (body.get("content") or {}):
                    continue        # no JSON body declared: the endpoint may act without reading one, so nothing is sent
                p = fill(path, ids) or re.sub(r"\{([^}]+)\}", lambda x: fill("{" + x.group(1).split(":")[-1] + "}", ids) or NOTHING, path)
                out.append(("bad JSON", m, p, b"{this is not json", path))
                if _schema(spec, body).get("type") != "array":     # an endpoint that takes a list is not sent one
                    out.append(("not an object", m, p, b"[1, 2, 3]", path))
                # a long name could be accepted: only sent where the path is inside the run's own test data
                if "{" in path and fill(path, ids) and "name" in (_schema(spec, body).get("properties") or {}):
                    out.append(("too long", m, p, json.dumps({"name": "x" * 100_000}).encode(), path))
                    out.append(("SQL text", m, p, json.dumps({"name": SQL_TEXT}).encode(), path))
            elif m == "get":
                u = unknown_path(path, ids)
                if u:
                    out.append(("unknown id", "get", u, None, path))
    return out


def run(base: str, spec: dict, token: str, ids: dict[str, str], record: Callable[..., None], workers: int = 6,
        sender=send) -> dict[str, dict[str, int]]:
    """Runs the checks; returns the counts by kind and outcome (for the report and R3.10's chart)."""
    counts = {k: {"passed": 0, "failed": 0, "warning": 0} for k in KINDS}
    jobs = checks(spec, ids)

    def go(job):
        kind, method, path, body, described = job
        t0 = time.time()
        status, answer = sender(base, method, path, token, body)
        outcome, detail = judge(status, kind)
        return kind, method, path, described, outcome, detail, int((time.time() - t0) * 1000), status, answer

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for kind, method, path, described, outcome, detail, ms, status, answer in pool.map(go, jobs):
            counts[kind][outcome] = counts[kind].get(outcome, 0) + 1
            failed = outcome == "failed"
            record(f"negative: {kind}: {method.upper()} {described}", outcome, detail, ms,
                   request=f"{method.upper()} {path}  as super-admin ({kind})" if failed else "",
                   response=f"{status}\n{answer}" if failed else "")
    return counts
