"""API writes of the self-test (D577): changes that really save, area by area, only inside the run's own fixtures
(self_test_<id>_1 and _2, the run's project, and things named self_test_<id> that the check itself removes again), plus
the same writes refused for a role without the right.

Each check is one result named "write <area>: <what>", so the report's coverage counts writes by area. A positive write
passes when the API answers as it should; a refused write passes when it answers 401 or 403 (a 400 before the rights
are checked is a warning: the refusal is right, but for the wrong reason). Nothing here touches anyone's real content."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable

Record = Callable[..., None]
REFUSED = {401, 403}


def call(base: str, method: str, path: str, token: str | None, body: dict | None = None,
         timeout: int = 60) -> tuple[int, dict | str]:
    """One call with a JSON body; the answer as JSON when it is JSON."""
    data = json.dumps(body if body is not None else {}).encode() if method.upper() in ("POST", "PUT", "PATCH") else None
    req = urllib.request.Request(base + path, data=data, method=method.upper(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            raw = ""
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 599, f"no answer: {exc}"
    try:
        return status, json.loads(raw) if raw else {}
    except ValueError:
        return status, raw[:1500]


def ident(answer) -> str | None:
    """The id of what a write made: id, guid or ident, at the top or one level down (entity, survey, credential...)."""
    if not isinstance(answer, dict):
        return None
    for k in ("id", "guid", "ident"):
        if isinstance(answer.get(k), str) and answer[k]:
            return answer[k]
    for v in answer.values():
        if isinstance(v, dict):
            for k in ("id", "guid", "ident"):
                if isinstance(v.get(k), str) and v[k]:
                    return v[k]
    return None


def judge(status: int, ok: set[int], refused: bool) -> tuple[str, str]:
    """passed, warning or failed for one write (also used by the unit tests)."""
    if refused:
        if status in REFUSED:
            return "passed", f"refused ({status})"
        if status == 400:
            return "warning", "400: refused, but before the rights were checked"
        return "failed", f"{status}: should have been refused"
    if status in ok:
        return "passed", f"{status}"
    if status >= 500 or status == 599:
        return "failed", f"{status}: server error"
    return "failed", f"{status}: expected {', '.join(map(str, sorted(ok)))}"


def plan(ids: dict[str, str], sid: str) -> list[dict]:
    """The writes, in order: area, what, method, path, body, who (a role, or the role refused), ok codes, and what to keep
    from the answer (save) for later steps ({name} in a path or body). Unit tested: every path is inside the fixtures."""
    m, other, p, ent = ids.get("model"), ids.get("other_model"), ids.get("project"), ids.get("entity")
    tag = f"self_test_{sid}"
    w: list[dict] = []
    if m:
        w += [
            dict(area="content", what="create an entity", method="post", path=f"/api/v1/models/{m}/content/entities",
                 body={"entity_type": "ApplicationComponent", "name": f"{tag} API application",
                       "description": "made by the self-test"}, who="model-admin", ok={200, 201}, save="entity"),
            dict(area="content", what="edit its description", method="patch",
                 path=f"/api/v1/models/{m}/content/entities/{{entity}}", body={"description": "changed by the self-test"},
                 who="model-admin", ok={200}),
            dict(area="content", what="refused: create as a Report Viewer", method="post",
                 path=f"/api/v1/models/{m}/content/entities",
                 body={"entity_type": "ApplicationComponent", "name": f"{tag} refused"}, who="report-viewer", refused=True),
            dict(area="relationships", what="add a relationship", method="post", path=f"/api/v1/models/{m}/content/relationships",
                 body={"relationship_type": "Association", "source": "{entity}", "target": ent}, who="model-admin",
                 ok={200, 201}, save="relationship", needs=["entity"] + ([] if ent else ["fixture entity"])),
            dict(area="relationships", what="refused: add as a Report Viewer", method="post",
                 path=f"/api/v1/models/{m}/content/relationships",
                 body={"relationship_type": "Association", "source": "{entity}", "target": ent}, who="report-viewer", refused=True),
            dict(area="relationships", what="remove it", method="delete",
                 path=f"/api/v1/models/{m}/content/relationships/{{relationship}}", who="model-admin", ok={200, 204}),
            dict(area="content", what="delete the entity", method="delete", path=f"/api/v1/models/{m}/content/entities/{{entity}}",
                 who="model-admin", ok={200, 204}),
            dict(area="content", what="commit the changes", method="post", path=f"/api/v1/models/{m}/changes/commit",
                 body={"message": f"{tag} API writes"}, who="model-admin", ok={200, 201, 409}),
            dict(area="metamodel", what="add a pick list", method="post", path=f"/api/v1/models/{m}/metamodel/changes",
                 body={"op": "pick_list.create", "name": f"{tag} list", "values": ["One", "Two"]}, who="model-admin", ok={200}),
            dict(area="metamodel", what="refused: change it as an Architect", method="post",
                 path=f"/api/v1/models/{m}/metamodel/changes",
                 body={"op": "pick_list.create", "name": f"{tag} refused", "values": ["One"], "dry_run": True},
                 who="architect", refused=True),
            dict(area="drawn views", what="refused: commit a view as a Report Viewer", method="post",
                 path=f"/api/v1/models/{m}/drawn-views/commit", body={}, who="report-viewer", refused=True),
        ]
    if other:
        w += [
            dict(area="merge requests", what="send the child for merge", method="post",
                 path=f"/api/v1/models/{other}/merge-requests", body={"note": f"{tag} API write"}, who="super-admin",
                 ok={200, 201, 202, 409}),
            dict(area="merge requests", what="refused: send as a Report Viewer", method="post",
                 path=f"/api/v1/models/{other}/merge-requests", body={"note": "refused"}, who="report-viewer", refused=True),
        ]
    if m:
        w += [dict(area="imports", what="refused: add an import source as a Report Viewer", method="post",
                   path=f"/api/v1/models/{m}/import-sources", body={"name": f"{tag} refused"}, who="report-viewer", refused=True)]
    if p:
        w += [
            dict(area="projects", what="refused: change the iteration as a Report Viewer", method="post",
                 path=f"/api/v1/projects/{p}/iteration", body={"iteration": "full"}, who="report-viewer", refused=True),
            dict(area="projects", what="refused: change the iteration with no role", method="post",
                 path=f"/api/v1/projects/{p}/iteration", body={"iteration": "full"}, who="no-role", refused=True),
        ]
    w += [
        dict(area="surveys", what="create a draft survey", method="post", path="/api/v1/surveys",
             body={"title": f"{tag} survey", "description": "made by the self-test"}, who="super-admin", ok={200, 201},
             save="survey"),
        dict(area="surveys", what="delete it", method="delete", path="/api/v1/surveys/{survey}", who="super-admin",
             ok={200, 204}),
        dict(area="surveys", what="refused: create as a Report Viewer", method="post", path="/api/v1/surveys",
             body={"title": f"{tag} refused"}, who="report-viewer", refused=True),
        dict(area="machine access", what="make the run's own token", method="post", path="/api/v1/machine-access/credentials",
             body={"kind": "token", "name": f"{tag} write check", "days": 1}, who="super-admin", ok={200, 201},
             save="credential"),
        dict(area="machine access", what="revoke it", method="post", path="/api/v1/machine-access/credentials/{credential}/revoke",
             body={"reason": "self-test"}, who="super-admin", ok={200, 204}),
        dict(area="machine access", what="refused: a client certificate with no role", method="post",
             path="/api/v1/machine-access/credentials", body={"kind": "certificate", "name": f"{tag} refused"},
             who="no-role", refused=True),
    ]
    return w


def _fill(x, saved: dict[str, str]):
    if isinstance(x, str):
        for k, v in saved.items():
            x = x.replace("{" + k + "}", v)
        return x
    if isinstance(x, dict):
        return {k: _fill(v, saved) for k, v in x.items()}
    if isinstance(x, list):
        return [_fill(v, saved) for v in x]
    return x


def run(base: str, tokens: dict[str, str], ids: dict[str, str], record: Record, area: str | None = None) -> dict[str, int]:
    """Runs the writes (of one area, if given); a write whose role is not in this run, or that needs something an
    earlier write did not make, is skipped with the reason. Returns passed and failed counts."""
    sid = ids.get("sid", "")
    saved: dict[str, str] = {}
    counts = {"writes": 0, "passed": 0, "failed": 0}
    for w in plan(ids, sid):
        if area and area.lower() not in w["area"]:
            continue
        name = f"write {w['area']}: {w['what']}"
        token = tokens.get(w["who"])
        if not token:
            record(name, "skipped", f"no {w['who']} account in this run (--role)", 0)
            continue
        missing = [n for n in w.get("needs", []) if n not in saved and n != "fixture entity"]
        if missing or "{" in json.dumps(_fill([w["path"], w.get("body")], saved)):
            record(name, "skipped", "an earlier write did not make what this one needs", 0)
            continue
        path, body = _fill(w["path"], saved), _fill(w.get("body"), saved)
        t0 = time.time()
        status, answer = call(base, w["method"], path, token, body)
        outcome, detail = judge(status, w.get("ok", {200}), w.get("refused", False))
        if outcome == "passed" and w.get("save"):
            got = ident(answer)
            if got:
                saved[w["save"]] = got
            else:
                outcome, detail = "failed", f"{status}, but the answer has no id"
        counts["writes"] += 1
        counts[outcome] = counts.get(outcome, 0) + 1
        req = f"{w['method'].upper()} {path} as {w['who']}" + (f"  body {json.dumps(body)}" if body is not None else "")
        record(name, outcome, f"{detail} (as {w['who']})", int((time.time() - t0) * 1000),
               request=req if outcome != "passed" else "",
               response=(f"{status}\n{json.dumps(answer)[:1500] if not isinstance(answer, str) else answer}"
                         if outcome != "passed" else ""))
    return counts
