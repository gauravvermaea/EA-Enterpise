"""Phase 24 (D365, D430 to D436): KPI trends, the OData feed and the report designer. No database needed."""

from __future__ import annotations

import base64
import inspect
import io
import json
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from eax import kpis
from eax import odata as od
from eax import report_designer as rd
from eax.metamodel_edit import EditError

API = Path(__file__).resolve().parents[1]
REPO = API.parents[1]
SQL = (API / "migrations" / "sql" / "0035_kpi_odata_reports.sql").read_text(encoding="utf-8")


def _data():
    ents = [
        {"id": 1, "guid": "a", "name": "Claims Platform", "parent": None, "type_code": "ApplicationComponent", "type_name": "Application"},
        {"id": 2, "guid": "b", "name": "Old Ledger", "parent": None, "type_code": "ApplicationComponent", "type_name": "Application"},
        {"id": 3, "guid": "c", "name": "Mainframe", "parent": None, "type_code": "Node", "type_name": "Node"},
        {"id": 4, "guid": "d", "name": "Database Server", "parent": None, "type_code": "Node", "type_name": "Node"},
        {"id": 5, "guid": "e", "name": "Claims", "parent": None, "type_code": "Capability", "type_name": "Capability"},
        {"id": 6, "guid": "f", "name": "Claims Intake", "parent": 5, "type_code": "Capability", "type_name": "Capability"},
        {"id": 7, "guid": "g", "name": "Lonely Goal", "parent": None, "type_code": "Goal", "type_name": "Goal"},
    ]

    def v(e, attr, **kw):
        return {"entity_id": e, "attr": attr, "data_type": "text", "value_text": None, "value_number": None, "value_date": None,
                "value_bool": None, "value_ref": None, **kw}
    vals = [v(1, "timeclassification", value_text="Invest"), v(1, "lifecycle", value_text="Production"),
            v(1, "annualcost", value_number=1500000), v(1, "hosting", value_text="SaaS"),
            v(2, "annualcost", value_number=Decimal("250000.50")), v(2, "lifecycle", value_text="Retiring"),
            v(3, "endoflife", value_date=date(2020, 1, 31)), v(4, "endofsupport", value_date="2026-12-31"),
            v(5, "owner", value_text="COO")]
    return {"entities": ents, "values": vals, "linked": {1, 2, 3, 4}, "quality": Decimal("71.25")}


def test_the_standard_kpis():
    got = {(c, d): v for c, d, v in kpis.standard_values(_data(), today=date(2026, 11, 10))}
    assert got[("entities", "")] == 7
    assert got[("entities_by_type", "Application")] == 2 and got[("entities_by_type", "Capability")] == 2
    assert got[("applications_by_time", "Invest")] == 1 and got[("applications_by_time", kpis.NOT_SET)] == 1
    assert got[("applications_by_lifecycle", "Retiring")] == 1
    assert got[("total_cost", "")] == Decimal("1750000.50")
    assert got[("quality_score", "")] == Decimal("71.25")
    assert got[("orphans", "")] == 1                       # the goal: no link, no parent, no children (the capabilities are a tree)
    assert got[("eol_technology", "")] == 1 and got[("eol_technology_soon", "")] == 1
    assert {k["code"] for k in kpis.STANDARD} == {c for c, _d in got}
    never = {**_data(), "quality": None}
    assert dict(((c, d), v) for c, d, v in kpis.standard_values(never))[("quality_score", "")] is None


def test_own_kpis_count_and_sum_with_a_filter():
    d = _data()
    count = {"kind": "count", "entity_type_code": "ApplicationComponent", "filter_attribute": "Lifecycle", "filter_op": "equals",
             "filter_value": "production"}
    assert kpis.own_value(count, d) == 1
    assert kpis.own_value({**count, "filter_attribute": "", "filter_op": ""}, d) == 2
    assert kpis.own_value({**count, "filter_attribute": "TimeClassification", "filter_op": "empty"}, d) == 1
    total = {"kind": "sum", "entity_type_code": "ApplicationComponent", "attribute_code": "AnnualCost",
             "filter_attribute": "AnnualCost", "filter_op": "more-than", "filter_value": "300000"}
    assert kpis.own_value(total, d) == 1500000
    assert kpis.own_value({**total, "filter_op": "less-than"}, d) == Decimal("250000.50")
    eol = {"kind": "count", "entity_type_code": "Node", "filter_attribute": "EndOfLife", "filter_op": "less-than",
           "filter_value": "2025-01-01"}
    assert kpis.own_value(eol, d) == 1                     # dates compare as dates


def test_the_migration_keeps_rows_only_and_follows_the_chain():
    upper = SQL.upper().replace("DO $$", "")
    assert "TRIGGER" not in upper and "FUNCTION" not in upper            # D248: no logic in the database
    for t in ("core.kpi_definitions", "core.kpi_snapshots", "core.kpi_values", "core.report_designs"):
        assert f"CREATE TABLE {t}" in SQL, t
    assert "CREATE VIEW rpt.kpi_trends" in SQL and "GRANT SELECT ON rpt.kpi_trends, rpt.report_designs TO eax_report" in SQL
    assert "kpi_snapshots_month ON core.kpi_snapshots (model_id, period) WHERE reason = 'monthly'" in SQL
    ver = (API / "migrations" / "versions" / "0035_kpi_odata_reports.py").read_text()
    assert 'revision = "0035_kpi_odata_reports"' in ver and 'down_revision = "0034_merge_dedupe"' in ver


def test_snapshots_are_taken_monthly_and_on_every_tag():
    from eax import tags
    assert "kpis.on_tag(conn, m, t, user.username)" in inspect.getsource(tags.create_tag)
    src = (API / "eax" / "jobs.py").read_text()
    assert '@app.periodic(cron="7 * * * *")' in src and "kpis.take_monthly(" in src
    assert "lifecycle = 'active' AND m.frozen_at IS NULL" in kpis.LIVE_SQL       # archived and frozen models are left alone


def test_the_report_designer_quotes_every_value():
    assert rd.snake("ApplicationComponent") == "application_component" and rd.snake("TIMEClass") == "time_class"
    cond = rd._condition('t."name"', "text", "equals", "x'); DROP TABLE core.models; --")
    assert "'x''); DROP TABLE core.models; --'" in cond
    assert rd._condition('t."c"', "numeric", "more-than", "1,000") == 't."c" > 1000'
    with pytest.raises(EditError):
        rd._condition('t."c"', "numeric", "more-than", "1; DROP")
    with pytest.raises(EditError):
        rd._condition('t."d"', "date", "less-than", "2026-01-01' OR '1'='1")
    assert "ILIKE '%50\\%%'" in rd._condition('t."n"', "text", "contains", "50%")
    with pytest.raises(EditError):
        rd._ident('name"; DROP')


def test_odata_filters():
    cols = {"Name", "AnnualCost", "GoLiveDate", "Lifecycle", "Id"}
    row = {"Name": "Claims Platform", "AnnualCost": Decimal(1500000), "GoLiveDate": date(2019, 3, 1), "Lifecycle": None,
           "Id": "6fdeb4a4-1cf8-5d15-bfd2-f37aacd04b71"}

    def ok(expr):
        return od.evaluate(od.parse_filter(expr, cols), row)
    assert ok("AnnualCost gt 1000000 and contains(Name,'claims')")
    assert ok("Lifecycle eq null and not (Name eq 'Other')")
    assert ok("GoLiveDate lt 2020-01-01 or AnnualCost lt 0")
    assert ok("startswith(Name, 'Claims') and endswith(Name,'form')")
    assert ok("Name eq 'claims platform'")                    # without case, as people expect
    assert ok("Id eq 6fdeb4a4-1cf8-5d15-bfd2-f37aacd04b71")
    assert not ok("AnnualCost le 10 or Lifecycle ne null")
    assert ok("Name eq 'O''Brien' or AnnualCost ge 1500000")
    for bad in ("Missing eq 1", "Name eq", "Name like 'x'", "Name eq 'x' extra"):
        with pytest.raises(od.ODataError):
            od.parse_filter(bad, cols)


def test_odata_pages_selects_and_counts(monkeypatch):
    m = {"_id": 1, "id": "m1", "name": "Demo"}
    table = {"type": "Thing", "name": "Thing", "columns": [("Id", "Edm.Guid", "Id"), ("Name", "Edm.String", "Name"),
                                                           ("Cost", "Edm.Decimal", "attr:cost")]}
    data = [{"Id": f"g{i}", "Name": f"Item {i:05d}", "Cost": Decimal(i)} for i in range(od.PAGE + 30)]
    monkeypatch.setattr(od.repo, "get_model", lambda conn, model: m)
    monkeypatch.setattr(od, "schema", lambda conn, mm: {"Thing": table})
    monkeypatch.setattr(od, "rows", lambda conn, mm, t: [dict(r) for r in data])
    first = od.query(None, "m1", "Thing", {"$select": "Name", "$count": "true", "$orderby": "Cost desc"}, "https://h/f/")
    assert first["@odata.count"] == od.PAGE + 30 and len(first["value"]) == od.PAGE
    assert first["value"][0] == {"Id": f"g{od.PAGE + 29}", "Name": f"Item {od.PAGE + 29:05d}"}
    assert "$skiptoken=" in first["@odata.nextLink"] and first["@odata.context"].endswith("#Thing(Id,Name)")
    from urllib.parse import parse_qsl, urlsplit
    second = od.query(None, "m1", "Thing", dict(parse_qsl(urlsplit(first["@odata.nextLink"]).query)), "https://h/f/")
    assert len(second["value"]) == 30 and "@odata.nextLink" not in second
    top = od.query(None, "m1", "Thing", {"$top": "3", "$skip": "2", "$filter": "Cost lt 10"}, "https://h/f/")
    assert [r["Id"] for r in top["value"]] == ["g2", "g3", "g4"]
    with pytest.raises(od.ODataError):
        od.query(None, "m1", "Thing", {"$select": "Secret"}, "https://h/f/")
    with pytest.raises(od.ODataError):
        od.query(None, "m1", "Nope", {}, "https://h/f/")
    assert od.pascal("annual cost") == "AnnualCost" and od.pascal("9lives") == "X9lives"


def test_odata_signs_in_with_basic_and_lets_machine_access_add_its_credentials(monkeypatch):
    flask = pytest.importorskip("flask")
    if not hasattr(flask, "Flask"):
        pytest.skip("Flask is not installed here (the API image has it)")
    Flask = flask.Flask

    from eax import auth
    from eax import odata_auth as oa
    app = Flask(__name__)
    seen = {}

    def check(username, secret):
        seen["got"] = (username, secret)
        return auth.User(username="svc_powerbi", roles=["eax-user"]) if secret == "key-123" else None
    monkeypatch.setattr(oa, "CHECKS", [check])
    monkeypatch.setattr(auth.permissions, "app_roles", lambda kc, mapping=None: ["user"])   # no database: no role mappings
    monkeypatch.setattr(oa, "_keycloak_claims", lambda u, p: {"preferred_username": u, "realm_access": {"roles": []}}
                        if p == "right" else None)
    basic = "Basic " + base64.b64encode(b"svc_powerbi:key-123").decode()
    with app.test_request_context(headers={"Authorization": basic}):
        assert oa.user().username == "svc_powerbi" and seen["got"] == ("svc_powerbi", "key-123")
    with app.test_request_context(headers={"Authorization": "Basic " + base64.b64encode(b"Thandi:right").decode()}):
        assert oa.user().username == "thandi"
    with app.test_request_context(headers={"Authorization": "Basic " + base64.b64encode(b"thandi:wrong").decode()}):
        with pytest.raises(Exception) as err:        # 401 (flask-smorest's abort)
            oa.user()
        assert getattr(err.value, "code", 401) == 401 and "not accepted" in str(getattr(err.value, "data", err.value))
    with app.test_request_context():
        with pytest.raises(Exception) as err:          # noqa: B017 - flask-smorest's abort (an HTTP 401)
            oa.user()
        assert getattr(err.value, "code", 401) == 401


def test_the_odata_feed_is_its_own_blueprint_with_a_basic_challenge():
    src = (API / "eax" / "api" / "kpi_reports.py").read_text()
    assert 'FlaskBlueprint("odata", __name__, url_prefix="/api/v1/odata")' in src
    assert "WWW-Authenticate" in src and "Basic realm=" in src
    app_src = (API / "eax" / "app.py").read_text()
    assert "app.register_blueprint(odata_blp)" in app_src and "kpi_reports_blp" in app_src
    realm = (REPO / "deploy" / "keycloak" / "realm-eaexplorer.json.tmpl").read_text()
    client = realm[realm.index('"clientId": "eax-odata"'):]
    client = client[:client.index('"protocolMappers"')]
    assert '"directAccessGrantsEnabled": true' in client and '"standardFlowEnabled": false' in client


def test_a_model_package_carries_its_kpis_and_report_designs():
    from eax import model_ops as mo
    reports = {"format": "eax-model-reports/1", "kpi_definitions": [{"id": "d1", "name": "Apps to retire"}],
               "kpi_snapshots": [{"taken_at": "2026-10-01T01:07:00+00:00", "period": "2026-10-01", "reason": "monthly",
                                  "tag_name": "", "taken_by": "system", "values": [{"kpi": "entities", "value": "12"}]}],
               "report_designs": [{"id": "r1", "name": "Apps", "spec": {"entity_type": "ApplicationComponent"}}]}
    data, name, _ct = mo.write_package({"format": "eax-package/1", "counts": {}}, {"name": "x"}, {"entities": {}, "relationships": []},
                                       {"reports": reports, "metamodel_versions": [], "metamodel_changes": []}, "zip", "m")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert json.loads(z.read("reports/reports.json"))["kpi_snapshots"][0]["values"] == [{"kpi": "entities", "value": "12"}]
    assert mo.read_package(data, name)["reports"]["report_designs"][0]["name"] == "Apps"
    from eax import backups
    assert "kpis.import_model(conn, m[\"_id\"], pkg[\"reports\"], actor, replace=True)" in inspect.getsource(backups._views_back)


def test_superset_gets_the_kpi_report_and_the_designer_page():
    from eax.report_defs import REPORTS
    from eax.setup import superset_reports as sr
    kr = next(r for r in REPORTS if r["code"] == "KR-01")
    charts = sr.charts_for(kr)
    assert {c["dataset_uuid"] for c in charts} == {sr.uid("dataset", "kpi_trends")}
    assert any(f["name"] == "KPI" for f in sr.dashboard_filters(kr, charts))
    cfg = (REPO / "deploy" / "superset" / "superset_config.py").read_text()
    assert "BLUEPRINTS = [_eax_designer]" in cfg
    page = (REPO / "deploy" / "superset" / "eax_designer.py").read_text()
    assert "rpt.model_access" in page and "datasource_access" in page and "RLS_NAME" in page and "/explore/?datasource_type=table" in page


def test_sample_kpis_show_each_state():
    from eax.seed import sample_kpis as sk
    assert sk.MONTHS == 12 and len(sk.OWN) == 2 and sk.NEW["filter_op"] == "empty" and sk.RETIRED
    assert sk._back("orphans", Decimal(1), 5) == 6 and sk._back("entities", Decimal(100), 10) == 80
    assert sk._back("quality_score", None, 0) is not None
    assert '"Sample KPI trends on the demo estate", sample_kpis' in (API / "eax" / "seed" / "later.py").read_text()
