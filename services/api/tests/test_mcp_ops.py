"""MCP phases 26/27 (D458, D459, D482 to D489): preview then confirm, rights, read-only credentials, tag first, the AI
activity log, citations, OAuth discovery and the analysis functions. No database needed: the database parts are faked."""

from __future__ import annotations

import inspect
import types
from datetime import date
from pathlib import Path

import anyio
import pytest

pytest.importorskip("mcp")

from eax import mcp_activity as ma  # noqa: E402
from eax import mcp_analysis as an  # noqa: E402
from eax import mcp_ops as ops  # noqa: E402
from eax import mcp_server as ms  # noqa: E402
from eax import permissions as perms  # noqa: E402
from eax.metamodel_edit import EditError  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]

CHANGING = {"copy_model", "merge_duplicates", "override_parent", "decide_merge_request", "refresh_from_parent", "model_wizard",
            "common_analysis", "change_entities", "save_report_document", "create_survey", "survey_action", "add_own_kpi"}


def _tools() -> dict:
    return {t.name: t for t in ms.mcp._tool_manager.list_tools()}


# ---------------------------------------------------------------- the tools are there, and every changing one confirms
def test_capability_list_is_registered():
    names = set(_tools())
    for n in CHANGING | {"find_duplicates", "compare_duplicates", "list_merge_requests", "get_merge_request", "impact_analysis",
                         "application_rationalisation", "cost_rollup_analysis", "technology_risk_analysis",
                         "single_points_of_failure", "heat_map_data", "what_changed", "kpi_trend", "find_orphans", "tidy_names",
                         "why_commit_blocked", "principles_and_standards", "list_surveys", "survey_results", "maturity_overview",
                         "usage_insight", "housekeeping_dry_run"}:
        assert n in names, n
    prompts = {p.name for p in ms.mcp._prompt_manager.list_prompts()}
    assert {"copy_and_clean_up", "analyse_a_model", "build_from_material", "draw_a_view", "write_a_report",
            "governance_check", "plan_an_adm_project", "survey_from_words"} <= prompts


def test_every_changing_tool_takes_confirm_and_why():
    tools = _tools()
    for n in CHANGING:
        params = inspect.signature(tools[n].fn).parameters
        assert "confirm" in params and params["confirm"].default == "", n
        assert "why" in params, n


def test_no_tool_makes_credentials_roles_or_service_accounts():
    for n in _tools():
        assert not any(w in n for w in ("credential", "service_account", "role", "token", "api_key")), n


# ---------------------------------------------------------------- preview, then confirm (D458)
class FakeConn:
    """Enough of a connection for the preview store: rows kept in a dict."""

    def __init__(self, store):
        self.store = store

    def execute(self, sql, p=None):
        q = str(sql)
        p = p or {}
        if q.lstrip().startswith("INSERT INTO core.mcp_previews"):
            self.store[p["t"]] = {"username": p["u"], "tool": p["tool"], "args_hash": p["h"], "used_at": None, "expired": False}
            return None
        if "FROM core.mcp_previews" in q:
            row = self.store.get(p["t"])
            return types.SimpleNamespace(mappings=lambda: types.SimpleNamespace(first=lambda: row))
        if q.lstrip().startswith("UPDATE core.mcp_previews"):
            self.store[p["t"]]["used_at"] = "now"
            return None
        return None


class FakeEngine:
    def __init__(self):
        self.store = {}
        self.applied = []

    def _cm(self):
        eng = self

        class CM:
            def __enter__(self_):
                return FakeConn(eng.store)

            def __exit__(self_, *a):
                return False
        return CM()

    begin = connect = _cm


@pytest.fixture
def engine(monkeypatch):
    eng = FakeEngine()
    monkeypatch.setattr(ops, "get_engine", lambda: eng)
    monkeypatch.setattr(ops.repo, "get_model", lambda conn, ref: {"id": "11111111-2222-4333-8444-555555555555", "name": ref})
    monkeypatch.setattr(ops.audit, "record", lambda *a, **k: None)
    tagged = []
    monkeypatch.setattr(ops, "tag_before", lambda conn, user, model, why: tagged.append((model, why)) or {"model": model, "tag": "T"})
    eng.tagged = tagged
    return eng


def _as(name="user_model_admin", roles=("user",)):
    return perms.current.set(perms.Principal(name, roles))


def _op(engine, args, confirm=""):
    def preview(conn, user):
        return {"will": "do it"}

    def apply(conn, user):
        engine.applied.append(dict(args))
        return {"message": "done"}
    return anyio.run(lambda: ops.operate("t_tool", args, confirm, preview, apply, tag=["M"], label="testing"))


def test_preview_first_then_confirm_once_and_tag_first(engine):
    tok = _as()
    try:
        first = _op(engine, {"model": "M", "x": 1, "why": "because"})
        assert first["preview"] == {"will": "do it"} and first["confirm"].startswith("pv_") and not engine.applied
        assert "confirm=" in first["next"]
        done = _op(engine, {"model": "M", "x": 1, "why": "said differently"}, first["confirm"])   # why may differ
        assert done["done"] and engine.applied == [{"model": "M", "x": 1, "why": "said differently"}]
        assert engine.tagged and engine.tagged[0][0] == "M" and "through MCP" in engine.tagged[0][1]
        again = _op(engine, {"model": "M", "x": 1}, first["confirm"])
        assert "confirmed already" in again["error"] and len(engine.applied) == 1
    finally:
        perms.current.reset(tok)


def test_confirm_must_match_arguments_person_and_be_known(engine):
    tok = _as()
    try:
        first = _op(engine, {"model": "M", "x": 1})
        assert "differ" in _op(engine, {"model": "M", "x": 2}, first["confirm"])["error"]
        assert "No such preview" in _op(engine, {"model": "M", "x": 1}, "pv_made_up")["error"]
    finally:
        perms.current.reset(tok)
    tok = _as("someone_else")
    try:
        assert "someone else" in _op(engine, {"model": "M", "x": 1}, first["confirm"])["error"]
        assert not engine.applied
    finally:
        perms.current.reset(tok)


def test_read_only_credentials_get_reading_tools_only(engine):
    tok = _as("user_super_admin", ("super-admin",))
    mach = ms._machine.set(types.SimpleNamespace(name="Reader", scopes={"mcp": "read"}))
    try:
        r = _op(engine, {"model": "M"})
        assert "may only read" in r["error"] and not engine.store
        assert "may only read" in anyio.run(lambda: ms._run(lambda conn: 1, begin=True))["error"]
    finally:
        ms._machine.reset(mach)
        perms.current.reset(tok)


def test_without_a_person_nothing_runs(engine):
    assert perms.current.get() is None
    assert _op(engine, {"model": "M"}) == {"error": "Sign in required."}


def test_rights_refusals_come_back_as_errors(engine):
    def preview(conn, user):
        raise EditError("Overriding X needs the Committer, Model Sub Admin or Model Admin role on it.", 403)
    tok = _as()
    try:
        r = anyio.run(lambda: ops.operate("t", {"model": "M"}, "", preview, lambda c, u: {}))
        assert "needs the Committer" in r["error"] and ma.kind_of(r, False, False) == "refused"
    finally:
        perms.current.reset(tok)


def test_args_hash_ignores_confirm_and_why_only():
    a = ops.args_hash("t", {"model": "M", "groups": [{"keep": "a"}], "why": "x", "confirm": "y"})
    assert a == ops.args_hash("t", {"groups": [{"keep": "a"}], "model": "M"})
    assert a != ops.args_hash("t", {"groups": [{"keep": "b"}], "model": "M"})
    assert a != ops.args_hash("u", {"groups": [{"keep": "a"}], "model": "M"})


# ---------------------------------------------------------------- the AI activity log (D482)
def test_activity_kinds_and_summary():
    assert ma.kind_of({"items": []}, False, False) == "read"
    assert ma.kind_of({"preview": {}}, False, True) == "preview"
    assert ma.kind_of({"done": True}, True, False) == "change"
    assert ma.kind_of({"error": "This credential ('x') may only read through MCP"}, False, False) == "refused"
    assert ma.kind_of({"error": "No tag 'Q5'."}, False, False) == "error"
    assert ma.summarise("copy_model", {"model": "M", "why": "Copy and clean it up"}) == "Copy and clean it up"
    assert ma.summarise("copy_model", {"model": "M", "confirm": "pv_x"}) == "copy model: model=M"
    short = ma.shorten({"confirm": "pv_secret", "text": "x" * 1000, "rows": list(range(50))})
    assert "confirm" not in short and len(short["text"]) < 400 and len(short["rows"]) == ma.MAX_ITEMS + 1


def test_every_call_is_logged_through_the_tool_manager(monkeypatch):
    seen = []
    monkeypatch.setattr(ms, "_log_call", lambda user, tool, args, result, started, state: seen.append((user.username, tool, state)))

    @ms.mcp.tool()
    async def _test_echo(model: str = "") -> dict:
        ms.note_call(wrote=True, changes=[{"what": "x"}])
        return {"ok": model}
    tok = _as()
    try:
        anyio.run(lambda: ms.mcp._tool_manager.call_tool("_test_echo", {"model": "M"}, None, convert_result=False))
    finally:
        perms.current.reset(tok)
        ms.mcp._tool_manager.remove_tool("_test_echo")
    assert seen and seen[0][0] == "user_model_admin" and seen[0][1] == "_test_echo"
    assert seen[0][2]["wrote"] and seen[0][2]["changes"] == [{"what": "x"}]


def test_admins_see_everyone_others_only_themselves():
    assert ma.is_admin(perms.Principal("a", ("super-admin",))) and ma.is_admin(perms.Principal("b", ("it-admin",)))
    with pytest.raises(PermissionError):
        ma.listing(None, perms.Principal("c", ("user",)), who="someone_else")


# ---------------------------------------------------------------- citations and OAuth discovery
def test_citations_link_entities_and_models():
    g, m = "aaaaaaaa-0000-4000-8000-000000000001", "bbbbbbbb-0000-4000-8000-000000000002"
    out = ms.cite({"items": [{"id": g, "display_id": "APP-1", "name": "A"}], "model": {"id": m, "kind": "project", "name": "M"}}, m)
    assert out["items"][0]["link"] == f"/#/metamodel/{m}/entity/{g}"
    assert out["model"]["link"] == f"/#/metamodel/{m}"
    assert "link" not in ms.cite({"id": "not-a-guid", "display_id": "x"}, m)


def test_oauth_discovery_names_keycloak_and_401_points_to_it():
    h = {"x-forwarded-host": "ea.example.org", "x-forwarded-proto": "https", "x-forwarded-port": "443"}
    st, doc = ms.discovery("/.well-known/oauth-protected-resource/mcp", h)
    assert st == 200 and doc["resource"] == "https://ea.example.org/mcp"
    assert doc["authorization_servers"][0].startswith("https://ea.example.org/auth/realms/")
    st, meta = ms.discovery("/.well-known/oauth-authorization-server", h)
    assert meta["code_challenge_methods_supported"] == ["S256"] and meta["token_endpoint"].endswith("/protocol/openid-connect/token")
    assert ms.discovery("/mcp", h) is None
    assert ms.external_base({"host": "localhost", "x-forwarded-proto": "https", "x-forwarded-port": "8443"}) == "https://localhost:8443"


def test_keycloak_has_the_mcp_client_and_the_proxy_routes_discovery():
    realm = (REPO / "deploy" / "keycloak" / "realm-eaexplorer.json.tmpl").read_text()
    assert '"clientId": "eax-mcp"' in realm and '"pkce.code.challenge.method": "S256"' in realm
    nginx = (REPO / "deploy" / "proxy" / "templates" / "default.conf.template").read_text()
    assert "location /.well-known/oauth-protected-resource" in nginx and "location /.well-known/oauth-authorization-server" in nginx


def test_migration_keeps_activity_and_previews_as_rows_only():
    sql = (ROOT / "migrations" / "sql" / "0040_mcp_activity.sql").read_text()
    assert "CREATE TABLE core.mcp_activity" in sql and "CREATE TABLE core.mcp_previews" in sql
    assert "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()     # D248


# ---------------------------------------------------------------- the analysis functions
def _snap():
    def e(g, name, t, values=None, parent=None, desc=""):
        return {"guid": g, "name": name, "entity_type": t, "type_code": t.replace(" ", ""), "display_id": g.upper(),
                "values": values or {}, "parent": parent, "description": desc}

    def r(g, s, t, typ, verb=""):
        return {"guid": g, "source": s, "target": t, "type_code": typ, "relationship_type": typ, "verb": verb, "name": ""}
    ents = [e("cap1", "Claims Management", "Capability"), e("cap2", "Billing", "Capability"),
            e("app1", "Claims Platform", "Application Component", {"FunctionalFit": 4, "TechnicalFit": 2, "TimeClassification": "Invest",
                                                                    "AnnualCost": "1000"}),
            e("app2", "Legacy Claims", "Application Component", {"FunctionalFit": 2, "TechnicalFit": 2, "AnnualCost": "500"}),
            e("fn1", "Register Claim", "Application Function"),
            e("node1", "Old Server", "Node", {"EndOfLife": "2020-01-01"}),
            e("orph", "claims  archive mgmt.", "Application Component", desc="Feeds the Claims Platform")]
    rels = [r("r1", "app1", "fn1", "Assignment"), r("r2", "fn1", "cap1", "Realization", "realizes"),
            r("r3", "app2", "cap1", "Association"), r("r4", "node1", "app1", "Serving", "serves"),
            r("r5", "app2", "cap2", "Association")]
    return {"entities": {x["guid"]: x for x in ents}, "relationships": {x["guid"]: x for x in rels}}


def test_impact_follows_dependency_direction():
    out = an.impact(_snap(), "node1", model="m")
    names = [x["name"] for x in out["affected"]]
    assert names[:1] == ["Claims Platform"] and "Register Claim" in names and "Claims Management" in names
    assert out["affected"][0]["link"] == "/#/metamodel/m/entity/app1"
    assert "Legacy Claims" not in names              # an association is shown, not followed
    with pytest.raises(EditError):
        an.impact(_snap(), "nope")


def test_rationalisation_finds_overlap_and_time_suggestions():
    out = an.rationalise(_snap())
    cap = out["capabilities_with_overlap"][0]
    assert cap["name"] == "Claims Management" and {a["name"] for a in cap["applications"]} == {"Claims Platform", "Legacy Claims"}
    differs = {d["name"]: d["suggested_time"] for d in out["time_differs_from_fit"]}
    assert differs == {"Claims Platform": "Migrate"}     # recorded Invest; good function, poor technology
    assert an.time_suggestion({"values": {"FunctionalFit": 1, "TechnicalFit": 1}})[0] == "Eliminate"


def test_cost_rollup_full_and_shared():
    out = an.cost_rollup(_snap(), "Capability")
    by = {g["name"]: g for g in out["groups"]}
    assert by["Claims Management"]["cost_full"] == 1500 and by["Billing"]["cost_full"] == 500
    assert by["Claims Management"]["cost_shared"] == 1250       # Legacy Claims shared by two capabilities
    assert out["total_cost"] == 1500


def test_technology_risk_and_single_points():
    tr = an.technology_risk(_snap(), date(2026, 11, 10))
    assert tr["technology"][0]["name"] == "Old Server" and tr["technology"][0]["past"]
    assert [c["name"] for c in tr["capabilities_at_risk"]] == ["Claims Management"]
    sp = an.single_points(_snap())
    assert {p["name"] for p in sp["split_the_landscape"]} >= {"Claims Platform", "Register Claim"}
    assert {a["name"] for a in sp["applications_on_one_technology_element"]} == {"Claims Platform"}


def test_tidy_names_orphans_and_heat_map():
    tidy = {t["name"]: t for t in an.tidy_suggestions(_snap())}
    assert tidy["claims  archive mgmt."]["suggested"] == "Claims archive Management"
    orph = an.orphans(_snap())
    assert orph[0]["name"] == "claims  archive mgmt." and orph[0]["likely_partners"][0]["name"] == "Claims Platform"
    hm = an.heat_map(_snap(), "Application Component", "AnnualCost")
    assert hm["numeric"] and hm["counts"] == {"high": 1, "low": 1, "Not set": 1}


def test_word_report_from_markdown():
    from docx import Document

    from eax import mcp_more
    data = mcp_more.docx_from_markdown("Claims summary", "# Today\nSome **bold** text.\n- one\n- two\n\n| A | B |\n|---|---|\n| 1 | 2 |")
    import io
    doc = Document(io.BytesIO(data))
    texts = [p.text for p in doc.paragraphs]
    assert "Claims summary" in texts and "Today" in texts and "one" in texts
    assert doc.tables[0].cell(1, 1).text == "2"
    assert mcp_more._file_name("A/B: report") == "AB report.docx"


def test_plain_operations_are_there_for_scenario_planning():
    from eax import model_operations as mo
    for n in ("copy_or_child", "tag_before", "compare_now", "override"):
        assert callable(getattr(mo, n))
