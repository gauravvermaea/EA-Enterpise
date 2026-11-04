"""Phase 5: the standard report bundles for Superset and the report list (no database needed)."""

import re
import zipfile
from pathlib import Path

import yaml

from eax.report_defs import REPORTS
from eax.setup import superset_reports as sr

SQL = (Path(__file__).resolve().parent.parent / "migrations" / "sql" / "0009_reports.sql").read_text(encoding="utf-8")
SUPERSET = Path(__file__).resolve().parents[3] / "deploy" / "superset"


def test_reports_have_unique_codes_and_slugs():
    assert len({r["code"] for r in REPORTS}) == len(REPORTS)
    assert len({r["slug"] for r in REPORTS}) == len(REPORTS)
    assert {f"SR-{i:02d}" for i in range(1, 31)} <= {r["code"] for r in REPORTS}


def test_every_report_view_is_made_by_the_migration():
    for r in REPORTS:
        view = r["view"].split(".", 1)[1]
        assert re.search(rf"CREATE VIEW rpt\.{view}\b", SQL), view
    for view in sr.VIEWS:
        if view in sr.HEAT:   # SQL datasets over a view, banded by the thresholds people choose
            assert re.search(rf"CREATE VIEW rpt\.{sr.HEAT[view][0]}\b", SQL), view
        else:
            assert re.search(rf"CREATE VIEW rpt\.{view}\b", SQL), view


def test_matrix_roles_are_standard_roles():
    roles = set(re.findall(r"\('(\w+)', '\w+'\)", SQL[SQL.index("CREATE VIEW rpt.std_roles"):SQL.index("CREATE VIEW rpt.entity_std")]))
    for r in REPORTS:
        if r["view"] == "rpt.sr_matrix":
            assert r["a"] in roles and r["b"] in roles, r["code"]


def test_charts_use_columns_their_dataset_has(tmp_path):
    for report in REPORTS:
        for c in sr.charts_for(report):
            view = next(v for v in sr.VIEWS if sr.uid("dataset", v) == c["dataset_uuid"])
            names = {n for n, _ in sr.VIEWS[view]} | ({"open"} if view in sr.LINKED else set())
            p = c["params"]
            used = p.get("all_columns", []) + p.get("groupbyRows", []) + p.get("groupbyColumns", []) \
                + p.get("groupby", []) + ([p["x_axis"]] if "x_axis" in p else []) \
                + [f["subject"] for f in p.get("adhoc_filters", [])]
            metrics = {m["metric_name"] for m in sr.dataset(view, "https://x")["metrics"]}
            assert set(p.get("metrics", [])) <= metrics, (report["code"], p.get("metrics"))
            assert set(used) <= names, (report["code"], set(used) - names)
            assert "model_name" in names, view   # every dashboard filters on the model


def test_bundles_are_written_one_per_report(tmp_path):
    paths = sr.build_report_bundles(tmp_path, "secret", "eaexplorer", "https://ea.example.org")
    assert len(paths) == len(REPORTS)
    for path in paths:   # every dataset a chart or filter uses is in the same bundle
        with zipfile.ZipFile(path) as zf:
            docs = [yaml.safe_load(zf.read(n)) for n in zf.namelist() if n.endswith(".yaml")]
            have = {d["uuid"] for d in docs if "table_name" in d}
            need = {d["dataset_uuid"] for d in docs if "slice_name" in d}
            need |= {t["datasetUuid"] for d in docs if "dashboard_title" in d
                     for f in d["metadata"]["native_filter_configuration"] for t in f["targets"] if t}
            assert need <= have, path.name
    with zipfile.ZipFile(paths[0]) as zf:
        names = zf.namelist()
        assert any(n.endswith("metadata.yaml") for n in names)
        dash = yaml.safe_load(zf.read(next(n for n in names if "/dashboards/" in n)))
        model_filter = dash["metadata"]["native_filter_configuration"][0]
        assert model_filter["name"] == "Model" and model_filter["controlValues"]["multiSelect"]   # several models at once
        ds = yaml.safe_load(zf.read(next(n for n in names if "/datasets/" in n)))
        assert ds["schema"] == "rpt"


def test_superset_model_access_and_roles():
    init = (SUPERSET / "eax_reports_init.py").read_text(encoding="utf-8")
    assert "rpt.model_access" in init and "current_username()" in init
    config = (SUPERSET / "superset_config.py").read_text(encoding="utf-8")
    assert '"ENABLE_TEMPLATE_PROCESSING": True' in config
    assert '"eax-it-admin": ["Gamma"]' in config   # IT Admins see no content (D98)
    assert '"eax-super-admin": ["Admin"]' in config


def test_heatmaps_offer_thresholds_and_reports_offer_filters():
    for report in REPORTS:
        charts = sr.charts_for(report)
        filters = sr.dashboard_filters(report, charts)
        assert filters[0]["name"] == "Model"
        first = next(v for v in sr.VIEWS if sr.uid("dataset", v) == charts[0]["dataset_uuid"])
        if first in sr.HEAT:
            assert len([f for f in filters if f["targets"][0].get("column", {}).get("name") in
                        ("medium_from", "high_from", "red_within", "amber_within")]) == 2, report["code"]
            assert "filter_values(" in sr.heat_sql(first) and "| int" in sr.heat_sql(first)
    codes = {r["code"] for r in REPORTS if any(
        sr.dataset_for(c) in sr.HEAT for c in sr.charts_for(r))}
    assert {"SR-16", "SR-17", "SR-23", "HM"} <= codes
