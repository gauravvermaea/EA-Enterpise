"""Validation and data quality (phase 12, D239): rules, conditions, weights, responsibility, routes and jobs."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from eax import quality as q

ROOT = Path(__file__).resolve().parents[1]


def _data():
    types = {1: {"id": 1, "code": "ApplicationComponent", "name": "Application Component"},
             2: {"id": 2, "code": "SystemSoftware", "name": "System Software"},
             3: {"id": 3, "code": "Process", "name": "Process"}}
    ents = {10: {"id": 10, "guid": "g10", "display_id": "APP-1", "name": "Claims", "description": "", "entity_type_id": 1,
                 "modified_at": "2026-11-01T00:00:00+00:00", "modified_by": "alice"},
            11: {"id": 11, "guid": "g11", "display_id": "APP-2", "name": "claims", "description": "x", "entity_type_id": 1,
                 "modified_at": "2026-11-01T00:00:00+00:00", "modified_by": "system:seed"},
            20: {"id": 20, "guid": "g20", "display_id": "SSW-1", "name": "Old DB", "description": "", "entity_type_id": 2,
                 "modified_at": "2026-11-01T00:00:00+00:00", "modified_by": "bob"},
            30: {"id": 30, "guid": "g30", "display_id": "PRC-1", "name": "Pay claims", "description": "", "entity_type_id": 3,
                 "modified_at": "2026-11-01T00:00:00+00:00", "modified_by": "bob"}}
    values = {10: {"Lifecycle": "Retiring", "Owner": "carol"}, 11: {"Lifecycle": "Production"}, 20: {"Lifecycle": "Retired"}}
    rels = {10: [{"type": "Serving", "dir": "out", "other": 30}, {"type": "Assignment", "dir": "in", "other": 20}],
            30: [{"type": "Serving", "dir": "in", "other": 10}], 20: [{"type": "Assignment", "dir": "out", "other": 10}]}
    return {"types": types, "entities": ents, "values": values, "rels": rels, "last_value": {}, "attrs": {},
            "seals": {}, "people": {"alice", "bob", "carol"}, "admins": ["admin1"]}


def test_conditions():
    d = _data()
    e = d["entities"][10]
    assert q.cond(d, e, None) and q.cond(d, e, {"attribute": "Lifecycle", "op": "equals", "value": "retiring"})
    assert q.cond(d, e, {"attribute": "lifecycle", "op": "in", "value": ["Retiring", "Sunset"]})
    assert q.cond(d, e, {"attribute": "Lifecycle", "op": "in", "value": "Sunset, Retiring"})
    assert not q.cond(d, e, {"attribute": "RetirementDate", "op": "filled"})
    assert q.cond(d, e, {"attribute": "description", "op": "empty"})
    assert q.cond(d, e, {"attribute": "name", "op": "matches", "value": "C.*"})


def test_the_four_kinds_of_rule():
    d = _data()
    app, other = d["entities"][10], d["entities"][11]
    serves = {"code": "QR-01", "name": "serves", "kind": "relationship",
              "spec": {"relationship_type": "Serving", "direction": "out", "other_type": "Process", "min": 1}}
    assert q.check_rule(d, serves, app) is None
    assert "Has no Serving relationships from it with a Process; needs 1 or more" == q.check_rule(d, serves, other)
    date = {"kind": "attribute", "spec": {"when": {"attribute": "Lifecycle", "op": "equals", "value": "Retiring"},
                                          "then": {"attribute": "RetirementDate", "op": "filled"}}}
    assert "required when Lifecycle equals Retiring" in q.check_rule(d, date, app)
    assert q.check_rule(d, date, other) is None                         # the condition does not hold: nothing asked
    retired = {"kind": "consistency", "spec": {"via": {"direction": "any", "other_type": "SystemSoftware"},
                                               "other": {"attribute": "Lifecycle", "op": "equals", "value": "Retired"},
                                               "must": "none"}}
    assert "Old DB" in q.check_rule(d, retired, app) and q.check_rule(d, retired, other) is None
    unique = {"kind": "naming", "spec": {"unique": True, "pattern": "[A-Z].*"}}
    names = Counter(["claims", "claims"])
    assert "has the name" in q.check_rule(d, unique, app, names)
    assert "pattern" in q.check_rule(d, unique, other, Counter(["claims"]))   # lower case: the pattern fails first
    msg = {**serves, "message": "Link it to the process it serves"}
    assert q.check_rule(d, msg, other) == "Link it to the process it serves"


def test_who_is_responsible():
    d = _data()
    assert q.responsible(d, d["entities"][10], "Carol") == ["carol"]           # the Owner names a person
    assert q.responsible(d, d["entities"][20], "Head of IT") == ["bob"]        # else the last person who changed it
    assert q.responsible(d, d["entities"][11], None) == ["admin1"]             # else the Model Admins (the seed is no one)


def test_weights_default_and_inherited():
    attrs = [{"code": "Owner", "name": "Owner", "is_required": True}, {"code": "Vendor", "name": "Vendor", "is_required": False}]
    w = q._weights_for({"weights": {}}, "ApplicationComponent", attrs)
    assert w == {"field:description": 1, "rel:any": 2, "attr:Owner": 3, "attr:Vendor": 1}
    w = q._weights_for({"weights": {"*": {"attr:Owner": 5, "attr:Nothing": 4}, "ApplicationComponent": {"attr:Vendor": 0,
                                                                                                         "rel:Serving": 2}}},
                       "ApplicationComponent", attrs)
    assert w == {"field:description": 1, "rel:any": 2, "attr:Owner": 5, "rel:Serving": 2}   # 0 leaves out; * only where it has


def test_settings_are_checked():
    out = q._clean_settings({"stale_days": "90", "cron": "", "weights": {"*": {"attr:Owner": 4}}})
    assert out == {"stale_days": 90, "cron": None, "weights": {"*": {"attr:Owner": 4}}, "score_parts": None, "bands": None}
    for bad in ({"stale_days": 3}, {"weights": {"*": {"owner": 3}}}, {"weights": {"*": {"attr:Owner": 11}}}):
        try:
            q._clean_settings(bad)
        except q.EditError:
            continue
        raise AssertionError(bad)


def test_routes_jobs_and_commits():
    src = (ROOT / "eax" / "api" / "quality.py").read_text()
    for route in ('"/models/<uuid:model_id>/quality"', '"/models/<uuid:model_id>/quality/settings"',
                  '"/models/<uuid:model_id>/quality/rules"', '"/models/<uuid:model_id>/quality/seal"', '"/quality"',
                  '"/quality/changes/<uuid:change_id>/<string:decision>"'):
        assert f"@blp.route({route})" in src, route
    assert "quality_blp" in (ROOT / "eax" / "app.py").read_text()
    jobs = (ROOT / "eax" / "jobs.py").read_text()
    for job in ("eax.quality_scheduler", "eax.quality_watch", "eax.quality_digest"):
        assert job in jobs
    assert "quality.commit_errors" in (ROOT / "eax" / "commits.py").read_text()
    mcp = (ROOT / "eax" / "mcp_server.py").read_text()
    for tool in ("quality_summary", "quality_findings", "suggest_quality_fix", "draft_quality_rule"):
        assert f"async def {tool}(" in mcp
    sql = (ROOT / "migrations" / "sql" / "0020_quality.sql").read_text()
    for t in ("quality_settings", "quality_rules", "quality_changes", "quality_runs", "quality_seals", "quality_told",
              "quality_defaults"):
        assert f"CREATE TABLE core.{t}" in sql
    assert "0.13.0" in sql


def test_model_admins_changes_wait_for_a_super_admin():
    src = (ROOT / "eax" / "quality.py").read_text()
    i = src.index("def change(")
    body = src[i:src.index("def pending(")]
    assert "perms.SUPER_ADMIN in user.roles" in body and "core.quality_changes" in body and "_super_admins(conn)" in body


def _dash():
    e = {"entity": "g1", "display_id": "APP-1", "name": "Claims", "type": "ApplicationComponent", "type_name": "Application Component",
         "owner": "COO", "responsible": ["alice"], "completeness": 50.0, "stale": True, "seal": "broken", "orphan": False,
         "failing": 1, "errors": 1, "last_change": "2026-01-01T00:00:00+00:00", "missing": ["attr:Owner"]}
    f = [{**{k: e[k] for k in ("entity", "display_id", "name", "type", "type_name", "owner", "responsible")}, "kind": "rule",
          "rule": "QR-01", "rule_name": "Serves", "severity": "error", "message": "Has no relationships", "source": "quality"},
         {**{k: e[k] for k in ("entity", "display_id", "name", "type", "type_name", "owner", "responsible")}, "kind": "stale",
          "message": "Not changed since 2026-01-01"}]
    grp = [{"name": "Application Component", "entities": 1, "completeness": 50.0, "incomplete": 1, "failing": 1, "errors": 1,
            "stale": 1, "orphans": 0}]
    s = {"entities": 1, "score": 40.0, "completeness": 50.0, "passing": 0.0, "fresh": 0.0, "incomplete": 1, "failing": 1,
         "errors": 1, "warnings": 0, "stale": 1, "orphans": 0, "seals": {"valid": 0, "broken": 1, "expired": 0, "none": 0},
         "rules": 1, "stale_days": 365, "by_rule": [{"rule": "QR-01", "name": "Serves", "severity": "error", "entities": 1}]}
    return {"model": {"id": "m1", "name": "Fynbos"}, "summary": s, "by_type": grp, "by_owner": [{**grp[0], "name": "COO"}],
            "entities": [e], "findings": f, "measured_at": "2026-11-06T10:00:00+00:00",
            "trend": [{"at": "2026-10-01T00:00:00+00:00", "score": 30, "completeness": 40, "stale": 1, "failing": 1, "trigger": "scheduled"},
                      {"at": "2026-11-01T00:00:00+00:00", "score": 40, "completeness": 50, "stale": 1, "failing": 1, "trigger": "scheduled"}]}


def test_pdf_and_excel_with_drill_downs():
    import io

    import openpyxl

    from eax import quality_pdf, quality_xlsx
    d = _dash()
    assert quality_pdf.model_pdf(d)[:4] == b"%PDF"
    assert quality_pdf.model_pdf(d, "owner", "COO", "alice")[:4] == b"%PDF"
    wb = openpyxl.load_workbook(io.BytesIO(quality_xlsx.model_xlsx(d, "https://eax.example/")))
    assert wb.sheetnames == ["Summary", "By type", "By owner", "Rules", "Findings", "Entities", "Trend"]
    ws = wb["By type"]
    assert ws["A2"].value == "Application Component" and ws.row_dimensions[3].outlineLevel == 1 and ws.row_dimensions[3].hidden
    assert ws.row_dimensions[4].outlineLevel == 2 and "QR-01" in ws["L4"].value       # type > entity > finding
    assert ws["I3"].hyperlink.target == "https://eax.example/#/metamodel/m1/entity/g1"
    assert wb["Findings"].auto_filter.ref == "A1:I3"
    empty = openpyxl.load_workbook(io.BytesIO(quality_xlsx.model_xlsx(d, "https://eax.example/", "owner", "Nobody")))
    assert empty["Entities"].max_row == 1
    estate = {"estate": {"score": 40, "models": 1, "measured": 1, "entities": 1, "trend": [{"at": "2026-11-01", "score": 40, "models": 1}]},
              "models": [{"id": "m1", "name": "Fynbos", "entities": 1, "score": 40, "month_ago": 30, "completeness": 50,
                          "measured_at": "2026-11-06", "summary": d["summary"], "trend": [], "by_type": d["by_type"]}]}
    assert quality_pdf.installation_pdf(estate)[:4] == b"%PDF"
    ws = openpyxl.load_workbook(io.BytesIO(quality_xlsx.estate_xlsx(estate, "https://eax.example/")))["Models"]
    assert ws["A2"].value == "Fynbos" and ws.row_dimensions[3].outlineLevel == 1


def test_metamodel_weights_d241():
    assert q.metamodel_weight({"is_required": True}) == 3 and q.metamodel_weight({"is_required": False}) == 1
    assert q.metamodel_weight({"is_required": True, "attribute_weight": 7}) == 7
    assert q.metamodel_weight({"attribute_weight": 7, "item_weight": 0}) == 0          # the type overrides, even to 0
    w = q._weights_for({"weights": {}}, "X", [{"code": "Owner", "attribute_weight": 5}, {"code": "Note", "item_weight": 0}])
    assert w == {"field:description": 1, "rel:any": 2, "attr:Owner": 5}
    sql = (ROOT / "migrations" / "sql" / "0020_quality.sql").read_text()
    assert "quality_weight" in sql and "CREATE TABLE core.quality_scope" in sql
    for f in ("metamodel_edit.py", "model_ops.py", "content.py"):
        assert "quality_weight" in (ROOT / "eax" / f).read_text(), f


def test_scope_d242_archived_never_measured():
    assert q.MEASURED_SQL.lstrip("(").startswith("m.lifecycle = 'active' AND")
    assert "m.kind_code = 'project'" in q.MEASURED_SQL and "core.quality_scope" in q.MEASURED_SQL
    src = (ROOT / "eax" / "quality.py").read_text()
    body = src[src.index("def set_scope("):]
    assert "perms.IT_ADMIN" in body and "lifecycle\"] != \"active\"" in body
    for fn in ("def due(", "def changed_since("):
        i = src.index(fn)
        assert "MEASURED_SQL" in src[i:i + 1500], fn
    assert '"/quality/scope"' in (ROOT / "eax" / "api" / "quality.py").read_text()

    class U:
        roles = ["model-admin"]
    try:
        q.set_scope(None, U(), [], True)
    except q.EditError as e:
        assert e.status == 403 if hasattr(e, "status") else True
    else:
        raise AssertionError("a Model Admin may not choose")


def test_score_weights_and_colours_d244():
    out = q._clean_settings({"score_parts": {"completeness": 60, "rules": 30, "freshness": 10}, "bands": {"green": 85, "amber": 65}})
    assert out["score_parts"] == {"completeness": 60, "rules": 30, "freshness": 10} and out["bands"] == {"green": 85, "amber": 65}
    assert q._clean_settings({"score_parts": None, "bands": None})["score_parts"] is None      # inherited again
    for bad in ({"score_parts": {"completeness": 60, "rules": 30, "freshness": 20}}, {"score_parts": {"speed": 100}},
                {"bands": {"green": 60, "amber": 70}}, {"bands": {"green": 101, "amber": 50}}, {"bands": {"green": 80}}):
        try:
            q._clean_settings(bad)
        except q.EditError:
            continue
        raise AssertionError(bad)
    assert q.tone(85, {"green": 85, "amber": 65}) == "good" and q.tone(70, {"green": 85, "amber": 65}) == "fair"
    assert q.tone(64.9, {"green": 85, "amber": 65}) == "poor" and q.tone(None) == ""
    src = (ROOT / "eax" / "quality.py").read_text()
    body = src[src.index("def set_defaults("):src.index("def tone(")]
    assert "perms.SUPER_ADMIN not in user.roles" in body                     # only Super Admins set the installation's
    assert '"/quality/defaults"' in (ROOT / "eax" / "api" / "quality.py").read_text()
    sql = (ROOT / "migrations" / "sql" / "0020_quality.sql").read_text()
    assert sql.count("score_parts") >= 2 and sql.count("bands ") >= 2
    from eax import quality_pdf
    d = _dash()
    d["summary"]["parts"] = {"completeness": 40, "rules": 40, "freshness": 20}
    d["bands"] = {"green": 30, "amber": 20}
    assert quality_pdf.model_pdf(d)[:4] == b"%PDF"
    assert quality_pdf.BANDS.get() == {"green": 30, "amber": 20} and quality_pdf._tone(35) == quality_pdf.GOOD


def test_stored_results_and_background_jobs_d245_d248():
    src = (ROOT / "eax" / "quality.py").read_text()
    sql = (ROOT / "migrations" / "sql" / "0020_quality.sql").read_text()
    assert "CREATE TABLE core.quality_entities" in sql and "CREATE TABLE core.quality_requests" in sql
    assert "CREATE TRIGGER" not in sql                                  # D248: no logic in triggers
    assert "quality.queue_entities(" in (ROOT / "eax" / "commits.py").read_text()   # a commit queues, never measures
    jobs = (ROOT / "eax" / "jobs.py").read_text()
    assert "eax.quality_entities" in jobs and "eax.quality_measure" in jobs
    tq = src[src.index("def type_quality("):src.index("def type_scores(")]
    assert "stored(conn" in tq and "measure(" not in tq                 # grids read what was last calculated
    ts = src[src.index("def type_scores("):src.index("# ---------------------------------------------------------------- \"not applicable\"")]
    assert "stored(conn" in ts and "measure(" not in ts
    eq = src[src.index("def entity_quality("):src.index("def type_quality(")]
    assert "measure(conn, m, only=" in eq                               # a single entity is checked at once
    assert 'e.get("status_code") == "retired"' in src                   # retired entities are left out


def test_reasons_and_aggregate():
    p = {"stale": True, "seal": "expired"}
    d = {"missing": [("attr:Vendor", 3), ("rel:any", 2)], "problems": [{"rule": "QR-01", "name": "Serves", "severity": "error",
                                                                        "message": "none", "source": "quality", "field": None}],
         "exempt": {"attr:Url": {"id": "x", "reason": "n/a", "requested_by": "a"}}, "pending": {},
         "rejected": {"attr:Owner": {"id": "y", "reason": "r", "decided_by": "boss", "decision_note": "fill it"}},
         "fresh_at": "2025-01-01T00:00:00"}
    out = q._reasons(p, d)
    assert out["Vendor"][0]["kind"] == "missing" and "(important)" in out["Vendor"][0]["message"]
    assert {r["kind"] for r in out["*"]} == {"missing", "rule", "stale", "seal-expired"}
    assert out["Url"][0]["kind"] == "not-applicable" and out["Owner"][0]["kind"] == "not-applicable-rejected"
    rows = [{"completeness": 100, "failing": 0, "stale": False}, {"completeness": 50, "failing": 1, "stale": True}]
    a = q._agg(rows, {"completeness": 50, "rules": 30, "freshness": 20})
    assert a["completeness"] == 75 and a["passing"] == 50 and a["fresh"] == 50 and a["score"] == 62.5


def test_not_applicable_and_bulk_d246():
    src = (ROOT / "eax" / "quality.py").read_text()
    for fn in ("def request_exemption(", "def decide_exemption(", "def decide_exemptions(", "def decide_many(",
               "def resubmit_change(", "def leave_out("):
        assert fn in src, fn
    lo = src[src.index("def leave_out("):]
    assert "is_model_admin" in lo and "_apply(conn, m, \"settings\"" in lo   # a Model Admin's leave-out applies at once
    api = (ROOT / "eax" / "api" / "quality.py").read_text()
    for route in ('"/models/<uuid:model_id>/quality/not-applicable/decide"', '"/quality/changes/decide"',
                  '"/quality/changes/<uuid:change_id>/resubmit"', '"/models/<uuid:model_id>/quality/leave-out"',
                  '"/models/<uuid:model_id>/entities/<string:entity>/quality"', '"/quality/run"'):
        assert f"@blp.route({route})" in api, route


def test_model_icons_d247():
    from eax import model_icons as mi
    assert mi.sniff(b"\x89PNG\r\n\x1a\n" + b"0" * 20) == "image/png" and mi.sniff(b"\xff\xd8\xff\xe0abc") == "image/jpeg"
    assert mi.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert mi.sniff(b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>') == "image/svg+xml"
    for bad in (b"<svg><script>alert(1)</script></svg>", b'<svg onload="x()"></svg>', b'<svg><a href="https://x">a</a></svg>',
                b"GIF89a....", b"%PDF-1.7"):
        try:
            mi.sniff(bad)
        except mi.EditError:
            continue
        raise AssertionError(bad)
    js = (ROOT.parent / "web" / "src" / "modelIcons.js").read_text()
    for name in mi.LIBRARY:
        assert f"  {name}: \"" in js, name
    assert set(mi.DEFAULT_BY_KIND.values()) <= set(mi.LIBRARY)
    sql = (ROOT / "migrations" / "sql" / "0020_quality.sql").read_text()
    assert "CREATE TABLE core.model_icons" in sql and "262144" in sql
    assert "icons_blp" in (ROOT / "eax" / "app.py").read_text()


def test_several_servers_d249():
    ep = (ROOT / "entrypoint.sh").read_text()
    assert "eax.startup serial" in ep and "eax.startup single change_log" in ep
    st = (ROOT / "eax" / "startup.py").read_text()
    assert "pg_advisory_lock" in st and "pg_try_advisory_lock" in st
    ops = (ROOT.parent / "ops" / "ops.py").read_text()
    assert "def scale_api(" in ops and 'self.path == "/servers"' in ops and '"--network-alias", "api"' in ops
    compose = (ROOT.parents[1] / "docker-compose.yml").read_text()
    api = compose[compose.index("\n  api:"):compose.index("\n  backup:")]
    assert "container_name" not in api and "ports:" not in api and "stop_grace_period" in api
    assert '"/admin/servers"' in (ROOT / "eax" / "api" / "admin.py").read_text()


def test_tree_views_d250():
    src = (ROOT / "eax" / "trees.py").read_text()
    for fn in ("def metamodel_tree(", "def types_tree(", "def type_entities(", "def entity_node(", "def search(", "def tree_xlsx(",
               "def _nodes("):
        assert fn in src, fn
    assert "a[\"value\"] in (None, \"\")" in src and "empty += 1" in src        # key and value only; empty ones counted
    assert "core.quality_entities" in src                                   # quality as last calculated (D245)
    api = (ROOT / "eax" / "api" / "trees.py").read_text()
    for route in ("/tree/metamodel", "/tree/types", "/tree/types/<string:entity_type>", "/tree/entities/<string:entity>",
                  "/tree/search", "/tree/xlsx"):
        assert route in api, route
    assert "trees_blp" in (ROOT / "eax" / "app.py").read_text()
    web = (ROOT.parent / "web" / "src")
    assert "export function MetamodelTree" in (web / "Trees.jsx").read_text()
    assert "<EntityTree" in (web / "ModelViews.jsx").read_text() and '["tree", "Tree"]' in (web / "Metamodel.jsx").read_text()
    assert "function ModelTiles" in (web / "Metamodel.jsx").read_text()


def test_recheck_from_tables_and_model_states():
    src = (ROOT / "eax" / "quality.py").read_text()
    rc = src[src.index("def recheck_entity("):src.index("def recheck_type(")]
    assert "measure(conn, m, only={e[\"id\"]})" in rc and "_store(conn, m, q, {e[\"id\"]})" in rc   # one entity at once
    rt = src[src.index("def recheck_type("):]
    assert "queue_entities(" in rt                                                     # the whole type: a job
    api = (ROOT / "eax" / "api" / "quality.py").read_text()
    assert '"/models/<uuid:model_id>/entities/<string:entity>/quality/recheck"' in api
    assert '"/models/<uuid:model_id>/quality/types/<string:entity_type>/recheck"' in api
    web = ROOT.parent / "web" / "src"
    for f in ("DataEntry.jsx", "ModelViews.jsx", "GridPages.jsx"):
        s = (web / f).read_text()
        assert "QualityCell" in s and "RecheckAll" in s, f
    marks = (web / "ModelMarks.jsx").read_text()
    assert "export function ModelStateBadge" in marks and "frozen" in marks and "in the library" in marks
    assert "<ModelStateBadge" in (web / "Metamodel.jsx").read_text()
    assert 'dialog === "icon"' in (web / "ModelOps.jsx").read_text()


def test_each_api_server_named_d249():
    ops = (ROOT.parent / "ops" / "ops.py").read_text()
    assert "r[\"key\"] = f\"{r['service']}-{r['number']}\"" in ops and 'if c.get("key") == service' in ops
    assert "c.key || c.service" in (ROOT.parent / "web" / "src" / "ContainerConsole.jsx").read_text()
