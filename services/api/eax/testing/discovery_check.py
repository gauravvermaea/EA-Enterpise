"""The self-test's black-box check of data discovery and ingestion (the Release 3 epic, D670), through the API in the
run's own test model (it has the ApplicationComponent type and "Self-test application 1" and "2"):

  a push source is set up             as a Super Admin: 201
  a push becomes a delivery           two records: one already there, one new: a delivery waits for review
  only what changed                   the same push again: nothing new or changed, no delivery
  a near name is suggested            "Self-test aplication 2" is suggested as "Self-test application 2", 85% or more
  refused without the right           a Report Viewer may not set up discovery, nor push: 403
  the source says how it went         GET the source: its last run

The source and its deliveries go with the test model at the run's end. One result each: "discovery: ..."."""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from .negative import send as _send

MAPPING = {"apps": {"entity_type": "ApplicationComponent", "key": "id", "name": "name", "description": "", "attributes": {},
                    "links": {}}}


def run(base: str, tokens: dict[str, str], ids: dict[str, str], record: Callable[..., None], send=_send) -> dict[str, int]:
    admin, model = tokens.get("super-admin", ""), ids.get("model", "")
    counts = {"passed": 0, "failed": 0, "skipped": 0}

    def rec(name: str, ok: bool | None, detail: str, ms: int, req: str = "", resp: str = "") -> None:
        outcome = "skipped" if ok is None else "passed" if ok else "failed"
        counts[outcome] += 1
        record(f"discovery: {name}", outcome, detail, ms, request=req if outcome == "failed" else "",
               response=resp if outcome == "failed" else "")

    def call(method: str, path: str, body: dict | None, token: str) -> tuple[int, dict, str, int]:
        t0 = time.time()
        status, text = send(base, method, path, token, json.dumps(body).encode() if body is not None else None)
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            data = {}
        return status, data if isinstance(data, dict) else {}, text, int((time.time() - t0) * 1000)

    if not admin or not model:
        rec("a push source is set up", None, "no Super Admin test account or test model", 0)
        return counts
    s, d, raw, ms = call("post", f"/api/v1/models/{model}/discovery-sources",
                         {"name": f"self-test push {ids.get('sid', '')}"[:60], "kind": "push", "mapping": MAPPING}, admin)
    ok = s == 201 and bool(d.get("id")) and (d.get("push") or "").endswith("/push")
    rec("a push source is set up", ok, f"{s}: {d.get('push') or raw[:200]}", ms, "POST discovery-sources", raw[:1000])
    if not ok:
        return counts
    sid = d["id"]
    push = f"/api/v1/import-sources/{sid}/push"
    s, d, raw, ms = call("post", push, {"apps": [{"id": "1", "name": "Self-test application 1"},
                                                 {"id": "9", "name": "Self-test discovered application"}]}, admin)
    load = d.get("load") or {}
    rec("a push becomes a delivery", s == 202 and bool(load.get("id")) and (d.get("counts") or {}).get("changed") == 2,
        f"{s}: {d.get('message') or raw[:200]}", ms, f"POST {push}", raw[:1000])
    s, d, raw, ms = call("post", push, {"apps": [{"id": "1", "name": "Self-test application 1"},
                                                 {"id": "9", "name": "Self-test discovered application"}]}, admin)
    rec("only what changed", s == 202 and not d.get("load") and (d.get("counts") or {}).get("unchanged") == 2,
        f"{s}: {d.get('message') or raw[:200]}", ms, f"POST {push} (again)", raw[:1000])
    s, d, raw, ms = call("post", push, {"apps": [{"id": "2", "name": "Self-test aplication 2"}]}, admin)
    sug = [x for x in d.get("suggestions") or [] if x.get("candidate") == "Self-test application 2"]
    rec("a near name is suggested", s == 202 and bool(sug) and sug[0].get("confidence", 0) >= 85,
        f"{s}: " + (f"suggested {sug[0]['candidate']} at {sug[0]['confidence']}%" if sug else (d.get("message") or raw[:200])),
        ms, f"POST {push} (a near name)", raw[:1000])
    viewer = tokens.get("report-viewer") or tokens.get("no-role") or ""
    if viewer:
        s1, _d, raw1, ms1 = call("post", f"/api/v1/models/{model}/discovery-sources", {"name": "refused", "kind": "push"}, viewer)
        s2, _d, raw2, ms2 = call("post", push, {"apps": [{"id": "x", "name": "refused"}]}, viewer)
        rec("refused without the right", s1 in (403, 404) and s2 in (403, 404), f"set up {s1}, push {s2}", ms1 + ms2,
            "as report-viewer", f"{raw1[:300]}\n{raw2[:300]}")
    else:
        rec("refused without the right", None, "no Report Viewer or no-role test account", 0)
    s, d, raw, ms = call("get", f"/api/v1/discovery-sources/{sid}", None, admin)
    rec("the source says how it went", s == 200 and bool((d.get("last_run") or {}).get("at")),
        f"{s}: {(d.get('last_run') or {}).get('message') or raw[:200]}", ms, f"GET /api/v1/discovery-sources/{sid}", raw[:1000])
    return counts
