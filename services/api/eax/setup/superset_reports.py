"""Builds the Superset import bundles for the reports (phase 5 with the phase 11 standard reports).

One zip per dashboard, so a dashboard that fails to import does not stop the others:
  /rendered/superset/reports/<slug>.zip
Each holds the report database connection (the read-only login eax_report), the datasets it reads (views
in schema rpt), its charts and the dashboard. Every dashboard has a Model filter. Each person sees only the
models they have (model access, all data inside them) that the reports-init service adds after the import
(deploy/superset/eax_reports_init.py), which also adds the typed views rpt.t_* as datasets (D138, D139).

The column lists below match migrations/sql/0009_reports.sql (tests/test_reports.py checks them); the
reports-init service also re-reads every dataset's columns from the database after importing.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ..report_defs import REPORTS
from .superset_sample import DB_UUID
from .superset_sample import bundle_files as sample_files

NS = uuid.UUID("6f4c2a52-2b0e-4b5e-9d63-6b0c0e7a1000")
ROLE = "EA Explorer reports"          # the Superset role that may read the report datasets
RLS_NAME = "EA Explorer: models you can read"


def uid(*parts: str) -> str:
    """A fixed id per object, so importing again updates the same objects instead of adding copies."""
    return str(uuid.uuid5(NS, "/".join(parts)))


# the report views and their columns (name, Superset type)
VIEWS: dict[str, list[tuple[str, str]]] = {
    "catalogue": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("layer", "TEXT"), ("entity_type_code", "TEXT"), ("entity_type", "TEXT"), ("report_view", "TEXT"), ("attribute_code", "TEXT"), ("attribute", "TEXT"), ("data_type", "TEXT"), ("pick_list", "TEXT"), ("pick_list_values", "TEXT"), ("required", "BOOLEAN"), ("report_column", "TEXT")],
    "entities": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_id", "BIGINT"), ("entity_guid", "UUID"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("entity_type_code", "TEXT"), ("entity_type", "TEXT"), ("layer_code", "TEXT"), ("layer", "TEXT"), ("parent_id", "BIGINT"), ("parent_name", "TEXT"), ("status", "TEXT"), ("origin_guid", "UUID"), ("created_at", "TIMESTAMP WITH TIME ZONE"), ("created_by", "TEXT"), ("modified_at", "TIMESTAMP WITH TIME ZONE"), ("modified_by", "TEXT"), ("link", "TEXT")],
    "entity_pairs": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("a_id", "BIGINT"), ("a_name", "TEXT"), ("a_type_code", "TEXT"), ("a_type", "TEXT"), ("b_id", "BIGINT"), ("b_name", "TEXT"), ("b_type_code", "TEXT"), ("b_type", "TEXT"), ("relationship_type_code", "TEXT"), ("relationship_type", "TEXT"), ("verb", "TEXT"), ("access_type", "TEXT"), ("direction", "TEXT")],
    "entity_std": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_id", "BIGINT"), ("entity_guid", "UUID"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("entity_type_code", "TEXT"), ("entity_type", "TEXT"), ("layer_code", "TEXT"), ("layer", "TEXT"), ("parent_id", "BIGINT"), ("parent_name", "TEXT"), ("status", "TEXT"), ("origin_guid", "UUID"), ("created_at", "TIMESTAMP WITH TIME ZONE"), ("created_by", "TEXT"), ("modified_at", "TIMESTAMP WITH TIME ZONE"), ("modified_by", "TEXT"), ("link", "TEXT"), ("role", "TEXT"), ("owner", "TEXT"), ("lifecycle", "TEXT"), ("criticality", "NUMERIC"), ("annual_cost", "NUMERIC"), ("vendor", "TEXT"), ("version", "TEXT"), ("hosting", "TEXT"), ("go_live_date", "DATE"), ("retirement_date", "DATE"), ("data_classification", "TEXT"), ("maturity", "TEXT"), ("capability_level", "NUMERIC"), ("process_level", "NUMERIC"), ("domain", "TEXT"), ("priority", "TEXT"), ("measure", "TEXT"), ("architecture_state", "TEXT"), ("landscape_level", "TEXT"), ("start_date", "DATE"), ("end_date", "DATE"), ("time_classification", "TEXT"), ("functional_fit", "NUMERIC"), ("technical_fit", "NUMERIC")],
    "mo_pick_list_counts": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("attribute", "TEXT"), ("value", "TEXT"), ("entities", "BIGINT")],
    "mo_recent_changes": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("at", "TIMESTAMP WITH TIME ZONE"), ("changed_by", "TEXT"), ("kind", "TEXT"), ("operation", "TEXT"), ("entity", "TEXT"), ("entity_type", "TEXT"), ("label", "TEXT")],
    "mo_type_counts": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("model_kind", "TEXT"), ("layer", "TEXT"), ("entity_type", "TEXT"), ("entities", "BIGINT")],
    "models": [("model_id", "BIGINT"), ("model_guid", "UUID"), ("model_name", "TEXT"), ("model_kind", "TEXT"), ("version_label", "TEXT"), ("industry", "TEXT"), ("owner", "TEXT"), ("lifecycle", "TEXT"), ("is_draft", "BOOLEAN"), ("is_locked", "BOOLEAN"), ("library_state", "TEXT"), ("metamodel_name", "TEXT"), ("metamodel_version", "INTEGER"), ("source_model", "TEXT"), ("parent_model", "TEXT"), ("created_at", "TIMESTAMP WITH TIME ZONE"), ("modified_at", "TIMESTAMP WITH TIME ZONE"), ("source_model_id", "BIGINT")],
    "relationships": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("relationship_guid", "UUID"), ("relationship_type_code", "TEXT"), ("relationship_type", "TEXT"), ("verb", "TEXT"), ("source_id", "BIGINT"), ("source_name", "TEXT"), ("source_type_code", "TEXT"), ("source_type", "TEXT"), ("target_id", "BIGINT"), ("target_name", "TEXT"), ("target_type_code", "TEXT"), ("target_type", "TEXT"), ("name", "TEXT"), ("access_type", "TEXT"), ("allowed", "BOOLEAN")],
    "sr01_application_inventory": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("owner", "TEXT"), ("lifecycle", "TEXT"), ("criticality", "NUMERIC"), ("annual_cost", "NUMERIC"), ("vendor", "TEXT"), ("version", "TEXT"), ("hosting", "TEXT"), ("go_live_date", "DATE"), ("retirement_date", "DATE"), ("architecture_state", "TEXT"), ("time_classification", "TEXT"), ("functional_fit", "NUMERIC"), ("technical_fit", "NUMERIC"), ("status", "TEXT"), ("link", "TEXT")],
    "sr02_capability_catalogue": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("parent", "TEXT"), ("level", "NUMERIC"), ("owner", "TEXT"), ("maturity", "TEXT"), ("criticality", "NUMERIC"), ("lifecycle", "TEXT"), ("applications", "BIGINT"), ("link", "TEXT")],
    "sr03_technology_inventory": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("owner", "TEXT"), ("vendor", "TEXT"), ("version", "TEXT"), ("lifecycle", "TEXT"), ("hosting", "TEXT"), ("go_live_date", "DATE"), ("end_of_life", "DATE"), ("annual_cost", "NUMERIC"), ("criticality", "NUMERIC"), ("link", "TEXT")],
    "sr04_data_catalogue": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("owner", "TEXT"), ("data_classification", "TEXT"), ("lifecycle", "TEXT"), ("link", "TEXT")],
    "sr05_process_catalogue": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("parent", "TEXT"), ("level", "NUMERIC"), ("owner", "TEXT"), ("domain", "TEXT"), ("roles", "TEXT"), ("link", "TEXT")],
    "sr06_interfaces": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("source_application", "TEXT"), ("relationship_type", "TEXT"), ("target_application", "TEXT"), ("flow", "TEXT"), ("source_type", "TEXT"), ("target_type", "TEXT")],
    "sr07_actors": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("owner", "TEXT"), ("domain", "TEXT"), ("part_of", "TEXT"), ("link", "TEXT")],
    "sr08_motivation": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("owner", "TEXT"), ("priority", "TEXT"), ("measure", "TEXT"), ("link", "TEXT")],
    "sr17_technology_lifecycle": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("description", "TEXT"), ("owner", "TEXT"), ("vendor", "TEXT"), ("version", "TEXT"), ("lifecycle", "TEXT"), ("hosting", "TEXT"), ("go_live_date", "DATE"), ("end_of_life", "DATE"), ("annual_cost", "NUMERIC"), ("criticality", "NUMERIC"), ("link", "TEXT"), ("end_of_life_year", "TEXT"), ("end_of_life_status", "TEXT")],
    "sr18_application_fit": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("owner", "TEXT"), ("lifecycle", "TEXT"), ("time_classification", "TEXT"), ("functional_fit", "NUMERIC"), ("technical_fit", "NUMERIC"), ("criticality", "NUMERIC"), ("annual_cost", "NUMERIC"), ("suggested_time", "TEXT"), ("link", "TEXT")],
    "sr20_cost_by_capability": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("capability", "TEXT"), ("capability_level", "NUMERIC"), ("cost_of", "TEXT"), ("item", "TEXT"), ("annual_cost", "NUMERIC")],
    "sr21_vendors": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("vendor", "TEXT"), ("role", "TEXT"), ("entity_type", "TEXT"), ("name", "TEXT"), ("lifecycle", "TEXT"), ("annual_cost", "NUMERIC"), ("link", "TEXT")],
    "sr22_impact": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("chosen_entity", "TEXT"), ("chosen_type", "TEXT"), ("depth", "INTEGER"), ("dependant", "TEXT"), ("dependant_type", "TEXT"), ("last_relationship", "TEXT"), ("path", "TEXT"), ("link", "TEXT")],
    "sr23_obsolescence": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("risk", "TEXT"), ("technology", "TEXT"), ("technology_type", "TEXT"), ("end_of_life", "DATE"), ("lifecycle", "TEXT"), ("application", "TEXT"), ("capability", "TEXT")],
    "sr24_single_points": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("role", "TEXT"), ("entity_type", "TEXT"), ("name", "TEXT"), ("criticality", "NUMERIC"), ("lifecycle", "TEXT"), ("dependants", "BIGINT"), ("with_no_alternative", "BIGINT"), ("link", "TEXT")],
    "sr25_rationalisation": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("capability", "TEXT"), ("application", "TEXT"), ("applications", "BIGINT"), ("overlaps_with", "TEXT")],
    "sr26_completeness": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("owner", "TEXT"), ("attributes", "BIGINT"), ("filled", "BIGINT"), ("required", "BIGINT"), ("required_missing", "BIGINT"), ("missing_required", "TEXT"), ("completeness", "NUMERIC"), ("link", "TEXT")],
    "sr27_orphans": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("layer", "TEXT"), ("entity_type", "TEXT"), ("display_id", "TEXT"), ("name", "TEXT"), ("parent", "TEXT"), ("modified_at", "TIMESTAMP WITH TIME ZONE"), ("modified_by", "TEXT"), ("link", "TEXT")],
    "sr28_duplicates": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("entity_type", "TEXT"), ("name", "TEXT"), ("display_id", "TEXT"), ("similar_name", "TEXT"), ("similar_display_id", "TEXT"), ("similarity", "NUMERIC"), ("link", "TEXT")],
    "sr29_change_activity": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("at", "TIMESTAMP WITH TIME ZONE"), ("week", "TIMESTAMP WITH TIME ZONE"), ("changed_by", "TEXT"), ("kind", "TEXT"), ("operation", "TEXT"), ("entity_type", "TEXT"), ("label", "TEXT")],
    "sr30_source_comparison": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("compared_with", "TEXT"), ("status", "TEXT"), ("entity_type", "TEXT"), ("name", "TEXT"), ("name_in_source", "TEXT"), ("what_changed", "TEXT"), ("link", "TEXT")],
    "sr_matrix": [("model_id", "BIGINT"), ("model_name", "TEXT"), ("a_role", "TEXT"), ("a_type", "TEXT"), ("a_name", "TEXT"), ("b_role", "TEXT"), ("b_type", "TEXT"), ("b_name", "TEXT"), ("relationship_type", "TEXT"), ("verb", "TEXT"), ("direction", "TEXT"), ("cell", "TEXT")],
}



# Heatmaps with thresholds the person picks (owner, 4 Nov 2026): virtual datasets over the report views
# that band each row by the thresholds chosen in the dashboard's threshold filters (rpt.heat_thresholds),
# read with Superset's filter_values() and taken out of the query (remove_filter). Defaults when none chosen.
def _param(name: str, default: int) -> str:
    return f"{{{{ ((filter_values('{name}', None, True) or [{default}])[0]) | int }}}}"


HEAT = {
    # name: (base view, measure SQL, band SQL, extra columns)
    "sr16_capability_heat": (
        "sr02_capability_catalogue", "applications",
        f"CASE WHEN applications >= {_param('high_from', 4)} THEN '3 High (' || {_param('high_from', 4)} || ' or more)' "
        f"WHEN applications >= {_param('medium_from', 2)} THEN '2 Medium (' || {_param('medium_from', 2)} || ' or more)' "
        "ELSE '1 Low' END", []),
    "sr17_technology_heat": (
        "sr17_technology_lifecycle", "months_to_end_of_life",
        "CASE WHEN end_of_life IS NULL THEN '5 Not set' WHEN end_of_life < current_date THEN '1 Past end of life' "
        f"WHEN end_of_life < current_date + make_interval(months => {_param('red_within', 12)}) "
        f"THEN '2 Red (within ' || {_param('red_within', 12)} || ' months)' "
        f"WHEN end_of_life < current_date + make_interval(months => {_param('amber_within', 36)}) "
        f"THEN '3 Amber (within ' || {_param('amber_within', 36)} || ' months)' ELSE '4 Green' END",
        [("months_to_end_of_life", "NUMERIC")]),
    "sr23_obsolescence_heat": (
        "sr23_obsolescence", "end_of_life",
        "CASE WHEN end_of_life < current_date OR lifecycle = 'Retired' THEN '1 High (past end of life)' "
        f"WHEN end_of_life < current_date + make_interval(months => {_param('red_within', 12)}) "
        "OR lifecycle IN ('Retiring', 'Phase Out') "
        f"THEN '2 High (within ' || {_param('red_within', 12)} || ' months, or phasing out)' "
        f"WHEN end_of_life < current_date + make_interval(months => {_param('amber_within', 36)}) "
        f"THEN '3 Medium (within ' || {_param('amber_within', 36)} || ' months)' ELSE '4 Low' END", []),
    "hm_pick_list_heat": (
        "mo_pick_list_counts", "entities",
        f"CASE WHEN entities >= {_param('high_from', 20)} THEN '3 High (' || {_param('high_from', 20)} || ' or more)' "
        f"WHEN entities >= {_param('medium_from', 5)} THEN '2 Medium (' || {_param('medium_from', 5)} || ' or more)' "
        "ELSE '1 Low' END", []),
}


def heat_sql(name: str) -> str:
    base, _measure, band, extra = HEAT[name]
    more = ", round((end_of_life - current_date) / 30.0, 1) AS months_to_end_of_life" if extra else ""
    return f"SELECT b.*{more}, {band} AS band\nFROM rpt.{base} b"


for _name_, (_base, _m, _b, _extra) in HEAT.items():
    VIEWS[_name_] = [*VIEWS[_base], *_extra, ("band", "TEXT")]
VIEWS["heat_thresholds"] = [("medium_from", "INTEGER"), ("high_from", "INTEGER"), ("red_within", "INTEGER"),
                           ("amber_within", "INTEGER")]
THRESHOLD_FILTERS = {"sr16_capability_heat": [("Medium from", "medium_from"), ("High from", "high_from")],
                     "sr17_technology_heat": [("Red within (months)", "red_within"), ("Amber within (months)", "amber_within")],
                     "sr23_obsolescence_heat": [("High within (months)", "red_within"), ("Medium within (months)", "amber_within")],
                     "hm_pick_list_heat": [("Medium from", "medium_from"), ("High from", "high_from")]}


LINKED = {v for v, cols in VIEWS.items() if any(c == "link" for c, _ in cols)}
DTTM = {"TIMESTAMP WITH TIME ZONE", "DATE"}


def _column(name: str, type_: str) -> dict:
    return {"column_name": name, "verbose_name": name.replace("_", " ").capitalize(), "is_dttm": type_ in DTTM,
            "is_active": True, "type": type_, "advanced_data_type": None, "groupby": True, "filterable": True,
            "expression": None, "description": None, "python_date_format": None, "extra": {}}


def _open_column(public_url: str) -> dict:
    """A calculated column: a link that opens the entity in EA Explorer (drill-through, RPT-008)."""
    base = public_url.rstrip("/").replace("'", "''")
    return {"column_name": "open", "verbose_name": "Open", "is_dttm": False, "is_active": True, "type": "TEXT",
            "advanced_data_type": None, "groupby": False, "filterable": False,
            "expression": f"CASE WHEN link IS NULL OR link = '' THEN '' ELSE '<a href=\"{base}/' || link || "
                          "'\" target=\"_blank\">Open</a>' END",
            "description": "Opens the entity in EA Explorer", "python_date_format": None, "extra": {}}


# summed metrics, made on every dataset that has the column
SUMS = {"entities": "Entities", "annual_cost": "Annual cost", "applications": "Applications",
        "dependants": "Dependants", "with_no_alternative": "With no alternative", "required_missing": "Required values missing"}
AVERAGES = {"completeness": "Completeness %", "criticality": "Criticality (average)", "technical_fit": "Technical fit (average)",
            "functional_fit": "Functional fit (average)", "similarity": "Similarity"}


def _metric(name: str, label: str, expression: str, kind: str) -> dict:
    return {"metric_name": name, "verbose_name": label, "metric_type": kind, "expression": expression,
            "description": None, "d3format": None, "currency": None, "extra": {}, "warning_text": None}


def dataset(view: str, public_url: str) -> dict:
    names = {n for n, _ in VIEWS[view]}
    cols = [_column(n, t) for n, t in VIEWS[view]]
    if view in LINKED:
        cols.append(_open_column(public_url))
    metrics = [_metric("count", "Count", "COUNT(*)", "count")]
    metrics += [_metric(c, label, f"SUM({c})", "sum") for c, label in SUMS.items() if c in names]
    metrics += [_metric(f"avg_{c}", label, f"ROUND(AVG({c}), 1)", "avg") for c, label in AVERAGES.items() if c in names]
    dttm = next((n for n, t in VIEWS[view] if t == "TIMESTAMP WITH TIME ZONE"), None)
    return {
        "table_name": view, "main_dttm_col": dttm, "description": f"EA Explorer report view rpt.{view}",
        "default_endpoint": None, "offset": 0, "cache_timeout": None, "schema": "rpt",
        "sql": heat_sql(view) if view in HEAT else None, "params": None,
        "template_params": None, "filter_select_enabled": True, "fetch_values_predicate": None, "extra": None,
        "normalize_columns": False, "always_filter_main_dttm": False, "uuid": uid("dataset", view),
        "metrics": metrics, "columns": cols, "version": "1.0.0", "database_uuid": DB_UUID,
    }


def _filter(column: str, value: str, operator: str = "==") -> dict:
    return {"expressionType": "SIMPLE", "subject": column, "operator": operator, "comparator": value, "clause": "WHERE",
            "filterOptionName": uid("filter", column, operator, str(value)), "isExtra": False, "isNew": False,
            "sqlExpression": None}


def _chart(key: str, title: str, view: str, viz: str, params: dict, about: str = "", width: int = 12) -> dict:
    ds = uid("dataset", view)
    return {"slice_name": title, "description": about or None, "certified_by": None, "certification_details": None,
            "viz_type": viz, "params": {"datasource": f"{ds}__table", "viz_type": viz, **params},
            "query_context": None, "cache_timeout": None, "uuid": uid("chart", key), "version": "1.0.0",
            "dataset_uuid": ds, "_width": width}


def table_chart(key: str, title: str, view: str, columns: list[str], order: str | None = None,
                filters: list[dict] | None = None, about: str = "", desc: bool = False) -> dict:
    cols = [c for c in columns if c in {n for n, _ in VIEWS[view]}]
    if view in LINKED:
        cols.append("open")
    return _chart(key, title, view, "table", {
        "query_mode": "raw", "all_columns": cols, "order_by_cols": [f'["{order}", {"false" if desc else "true"}]'] if order else [],
        "row_limit": 10000, "server_page_length": 50, "adhoc_filters": filters or [], "include_search": True,
        "allow_render_html": True, "table_timestamp_format": "smart_date", "show_cell_bars": False}, about)


def pivot_chart(key: str, title: str, view: str, rows: list[str], columns: list[str], metric: str = "count",
                filters: list[dict] | None = None, about: str = "", width: int = 12) -> dict:
    # several models can be chosen at once: each model gets its own block of rows (unless models are the columns)
    if "model_name" not in rows + columns:
        rows = ["model_name", *rows]
    return _chart(key, title, view, "pivot_table_v2", {
        "groupbyRows": rows, "groupbyColumns": columns, "metrics": [metric], "metricsLayout": "COLUMNS",
        "aggregateFunction": "Sum", "rowTotals": True, "colTotals": True, "transposePivot": False,
        "combineMetric": False, "valueFormat": "SMART_NUMBER", "row_limit": 10000,
        "adhoc_filters": filters or [], "rowOrder": "key_a_to_z", "colOrder": "key_a_to_z",
        "conditional_formatting": [{"colorScheme": "#2F7D9B", "column": metric, "operator": ">", "targetValue": 0}]},
        about, width)


def bar_chart(key: str, title: str, view: str, x: str, metric: str = "count", group: list[str] | None = None,
              filters: list[dict] | None = None, about: str = "", width: int = 12, limit: int = 30) -> dict:
    return _chart(key, title, view, "echarts_timeseries_bar", {
        "x_axis": x, "metrics": [metric], "groupby": group or [], "adhoc_filters": filters or [],
        "row_limit": 10000, "series_limit": limit, "orientation": "horizontal", "stack": True,
        "x_axis_sort": metric, "x_axis_sort_asc": False, "show_legend": bool(group), "rich_tooltip": True,
        "truncate_metric": True, "show_value": False, "y_axis_format": "SMART_NUMBER"}, about, width)


def line_chart(key: str, title: str, view: str, x: str, metric: str = "count", group: list[str] | None = None,
               grain: str = "P1W", about: str = "", width: int = 12) -> dict:
    return _chart(key, title, view, "echarts_timeseries_line", {
        "x_axis": x, "time_grain_sqla": grain, "metrics": [metric], "groupby": group or [], "adhoc_filters": [],
        "row_limit": 10000, "show_legend": True, "rich_tooltip": True, "markerEnabled": True,
        "y_axis_format": "SMART_NUMBER"}, about, width)


LIST_COLUMNS = ["model_name", "entity_type", "display_id", "name", "description", "parent", "level", "owner",
                "lifecycle", "criticality", "annual_cost", "vendor", "version", "hosting", "go_live_date",
                "retirement_date", "end_of_life", "architecture_state", "time_classification", "functional_fit",
                "technical_fit", "maturity", "applications", "data_classification", "domain", "roles", "part_of",
                "priority", "measure", "status"]

# list reports SR-01 to SR-08: the summary pivot (rows, columns)
SUMMARY = {
    "SR-01": (["lifecycle"], ["hosting"]), "SR-02": (["level"], ["maturity"]),
    "SR-03": (["entity_type"], ["lifecycle"]), "SR-04": (["entity_type"], ["data_classification"]),
    "SR-05": (["level"], ["entity_type"]), "SR-06": (["source_application"], ["target_application"]),
    "SR-07": (["entity_type"], ["domain"]), "SR-08": (["entity_type"], ["priority"]),
}


def _list_report(report: dict) -> list[dict]:
    code, view, title = report["code"], report["view"].split(".", 1)[1], report["title"]
    rows, cols = SUMMARY[code]
    names = [n for n, _ in VIEWS[view]]
    detail = [c for c in LIST_COLUMNS if c in names] if code != "SR-06" else \
        ["model_name", "source_application", "relationship_type", "target_application", "flow", "source_type", "target_type"]
    return [pivot_chart(f"{code}/summary", f"{title}: summary", view, rows, cols, about=report["about"]),
            table_chart(f"{code}/list", title, view, detail, order="name" if "name" in names else None, about=report["about"])]


def charts_for(report: dict) -> list[dict]:  # noqa: C901 - one branch per report, kept together
    code, view, title, about = report["code"], report["view"].split(".", 1)[1], report["title"], report["about"]
    if code in SUMMARY:
        return _list_report(report)
    if view == "sr_matrix":
        flt = [_filter("a_role", report["a"]), _filter("b_role", report["b"])]
        if report["a"] == report["b"]:
            flt.append(_filter("direction", "outgoing"))
        return [pivot_chart(f"{code}/matrix", title, "sr_matrix", ["a_name"], ["b_name"], filters=flt, about=about),
                table_chart(f"{code}/pairs", f"{title}: relationships", "sr_matrix",
                            ["model_name", "a_type", "a_name", "verb", "b_type", "b_name", "relationship_type", "cell"],
                            order="a_name", filters=flt)]
    if code == "MO":
        return [
            pivot_chart("MO/types", "Entities by layer and type", "mo_type_counts", ["layer", "entity_type"], ["model_name"],
                        metric="entities", about="How many entities of each type, per model"),
            table_chart("MO/models", "Models", "models",
                        ["model_name", "model_kind", "version_label", "industry", "owner", "lifecycle", "is_draft",
                         "metamodel_name", "metamodel_version", "source_model", "parent_model", "modified_at"], order="model_name"),
            table_chart("MO/changes", "Changes in the last 90 days", "mo_recent_changes",
                        ["at", "model_name", "changed_by", "kind", "operation", "entity", "entity_type", "label"], order="at", desc=True),
        ]
    if code == "HM":
        heat = "hm_pick_list_heat"
        return [
            pivot_chart("HM/values", "Pick-list values by type and attribute", heat, ["entity_type", "attribute"], ["value"],
                        metric="entities", about="How many entities have each value: darker cells hold more"),
            pivot_chart("HM/bands", "Values by band (set the thresholds in the filter bar)", heat, ["entity_type", "attribute"],
                        ["band"], about="How many values fall in each band, by the thresholds chosen"),
            table_chart("HM/list", "Values and their band", heat, ["model_name", "entity_type", "attribute", "value", "entities", "band"],
                        order="entities", desc=True),
        ]
    if code == "SR-16":
        heat = "sr16_capability_heat"
        return [
            pivot_chart("SR-16/bands", "Capabilities by band of supporting applications", heat, ["level", "parent", "name"], ["band"],
                        about="Set Medium from and High from in the filter bar to change the bands"),
            pivot_chart("SR-16/maturity", "Capabilities by level and maturity", heat, ["level"], ["maturity"], width=6),
            pivot_chart("SR-16/criticality", "Capabilities by level and criticality", heat, ["level"], ["criticality"], width=6),
            table_chart("SR-16/list", "Capabilities, their applications and band", heat,
                        ["model_name", "level", "parent", "name", "applications", "band", "maturity", "criticality", "owner"],
                        order="applications", desc=True),
        ]
    if code == "SR-17":
        heat = "sr17_technology_heat"
        return [
            pivot_chart("SR-17/bands", "Technology by end-of-life band", heat, ["entity_type"], ["band"], width=6,
                        about="Set Red within and Amber within (months) in the filter bar"),
            pivot_chart("SR-17/eol", "Technology by lifecycle and end-of-life year", heat, ["lifecycle"], ["end_of_life_year"], width=6),
            table_chart("SR-17/list", "Technology and its end of life", heat,
                        ["model_name", "band", "end_of_life", "months_to_end_of_life", "name", "entity_type", "vendor", "version",
                         "lifecycle", "owner"], order="end_of_life"),
        ]
    if code == "SR-18":
        return [
            pivot_chart("SR-18/quadrant", "Functional fit (rows) against technical fit (columns)", view,
                        ["functional_fit"], ["technical_fit"], width=6, about="Top right Invest, top left Migrate, bottom right Tolerate, bottom left Eliminate"),
            pivot_chart("SR-18/time", "TIME set against TIME suggested by the fit scores", view,
                        ["time_classification"], ["suggested_time"], width=6),
            table_chart("SR-18/list", "Applications and their fit", view,
                        ["model_name", "name", "time_classification", "suggested_time", "functional_fit", "technical_fit",
                         "criticality", "annual_cost", "lifecycle", "owner"], order="name"),
        ]
    if code == "SR-19":
        return [
            pivot_chart("SR-19/matrix", "Criticality (rows) against technical fit (columns)", view, ["criticality"], ["technical_fit"],
                        about="High criticality with low technical fit is the risk corner"),
            table_chart("SR-19/list", "Applications by criticality and technical fit", view,
                        ["model_name", "name", "criticality", "technical_fit", "functional_fit", "time_classification", "lifecycle", "owner"],
                        order="criticality", desc=True),
        ]
    if code == "SR-20":
        return [
            bar_chart("SR-20/bar", "Annual cost by capability", view, "capability", metric="annual_cost", group=["cost_of"]),
            pivot_chart("SR-20/pivot", "Cost by capability and item", view, ["capability", "cost_of", "item"], [], metric="annual_cost"),
        ]
    if code == "SR-21":
        return [
            bar_chart("SR-21/bar", "Applications and technology per vendor", view, "vendor", group=["role"]),
            pivot_chart("SR-21/cost", "Annual cost per vendor", view, ["vendor"], ["role"], metric="annual_cost"),
            table_chart("SR-21/list", "Vendors and what they supply", view,
                        ["model_name", "vendor", "role", "entity_type", "name", "lifecycle", "annual_cost"], order="vendor"),
        ]
    if code == "SR-22":
        return [
            pivot_chart("SR-22/depth", "Dependants by type and steps away", view, ["dependant_type"], ["depth"],
                        about="Choose the entity in the Chosen entity filter"),
            table_chart("SR-22/list", "What depends on the chosen entity", view,
                        ["model_name", "chosen_entity", "chosen_type", "depth", "dependant", "dependant_type", "last_relationship", "path"],
                        order="depth"),
        ]
    if code == "SR-23":
        heat = "sr23_obsolescence_heat"
        return [
            pivot_chart("SR-23/risk", "Applications at risk by technology", heat, ["band", "technology"], [], width=6,
                        about="Set High within and Medium within (months) in the filter bar"),
            pivot_chart("SR-23/caps", "Capabilities at risk", heat, ["capability"], ["band"], width=6),
            table_chart("SR-23/list", "Obsolescence risk", heat,
                        ["model_name", "band", "technology", "technology_type", "end_of_life", "lifecycle", "application", "capability"],
                        order="band"),
        ]
    if code == "SR-24":
        return [
            bar_chart("SR-24/bar", "Dependants with no alternative", view, "name", metric="with_no_alternative", group=["role"]),
            table_chart("SR-24/list", "Applications and technology by dependants", view,
                        ["model_name", "role", "entity_type", "name", "dependants", "with_no_alternative", "criticality", "lifecycle"],
                        order="with_no_alternative", desc=True),
        ]
    if code == "SR-25":
        return [
            pivot_chart("SR-25/matrix", "Capabilities served by more than one application", view, ["capability"], ["application"]),
            table_chart("SR-25/list", "Rationalisation candidates", view,
                        ["model_name", "capability", "applications", "application", "overlaps_with"], order="capability"),
        ]
    if code == "SR-26":
        return [
            pivot_chart("SR-26/type", "Completeness % by type", view, ["entity_type"], [], metric="avg_completeness", width=6),
            pivot_chart("SR-26/owner", "Completeness % by owner", view, ["owner"], [], metric="avg_completeness", width=6),
            table_chart("SR-26/missing", "Entities missing required values", view,
                        ["model_name", "entity_type", "display_id", "name", "owner", "required_missing", "missing_required", "completeness"],
                        order="required_missing", desc=True, filters=[_filter("required_missing", 0, ">")]),
        ]
    if code == "SR-27":
        return [
            pivot_chart("SR-27/types", "Orphans by layer and type", view, ["layer", "entity_type"], ["model_name"]),
            table_chart("SR-27/list", "Entities with no relationships", view,
                        ["model_name", "layer", "entity_type", "display_id", "name", "modified_at", "modified_by"], order="entity_type"),
        ]
    if code == "SR-28":
        return [
            pivot_chart("SR-28/types", "Duplicate candidates by type", view, ["entity_type"], ["model_name"]),
            table_chart("SR-28/list", "Duplicate candidates", view,
                        ["model_name", "entity_type", "name", "display_id", "similar_name", "similar_display_id", "similarity"],
                        order="similarity", desc=True),
        ]
    if code == "SR-29":
        return [
            line_chart("SR-29/line", "Changes per week", view, "at", group=["model_name"]),
            pivot_chart("SR-29/who", "Changes by person and kind", view, ["changed_by"], ["kind"], width=6),
            pivot_chart("SR-29/types", "Changes by entity type and operation", view, ["entity_type"], ["operation"], width=6),
        ]
    if code == "SR-30":
        return [
            pivot_chart("SR-30/summary", "Kept, changed, new and removed by type", view, ["compared_with", "entity_type"], ["status"]),
            table_chart("SR-30/list", "Differences from the source model", view,
                        ["model_name", "compared_with", "status", "entity_type", "name", "name_in_source", "what_changed"],
                        order="status", filters=[_filter("status", "Kept", "!=")]),
        ]
    raise ValueError(f"no charts for {code}")


# Filters people can set on a dashboard (owner, 4 Nov 2026: let people tailor reports where possible):
# the Model filter (several models), drop-downs for the common columns the report has, number ranges for
# its measures, threshold pickers for heatmaps and banded reports, and a time range for change reports.
COMMON_SELECTS = [("Type", "entity_type"), ("Layer", "layer"), ("Owner", "owner"), ("Lifecycle", "lifecycle"),
                  ("Vendor", "vendor"), ("Changed by", "changed_by"), ("Status", "status"), ("Risk band", "band")]
RANGES = {
    "SR-01": [("Criticality", "criticality"), ("Annual cost", "annual_cost")],
    "SR-02": [("Applications", "applications")], "SR-19": [("Criticality", "criticality"), ("Technical fit", "technical_fit")],
    "SR-18": [("Functional fit", "functional_fit"), ("Technical fit", "technical_fit")],
    "SR-20": [("Annual cost", "annual_cost")], "SR-22": [("Steps away", "depth")],
    "SR-24": [("Dependants", "dependants"), ("With no alternative", "with_no_alternative")],
    "SR-25": [("Applications per capability", "applications")], "SR-26": [("Completeness %", "completeness")],
    "SR-28": [("Similarity (0 to 1)", "similarity")], "SR-16": [("Applications", "applications")],
    "SR-17": [("Months to end of life", "months_to_end_of_life")], "HM": [("Entities", "entities")],
}


def _native(slug: str, name: str, kind: str, view: str | None, column: str | None, n_charts: int,
            description: str = "", multi: bool = True) -> dict:
    target = {"datasetUuid": uid("dataset", view), "column": {"name": column}} if view else {}
    control = {"enableEmptyFilter": False}
    if kind == "filter_select":
        control.update({"defaultToFirstItem": False, "multiSelect": multi, "searchAllOptions": True, "inverseSelection": False})
    return {
        "id": "NATIVE_FILTER-" + uid("filter", slug, name)[:8], "name": name, "filterType": kind, "type": "NATIVE_FILTER",
        "description": description, "targets": [target], "controlValues": control,
        "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
        "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
        "chartsInScope": list(range(1, n_charts + 1)), "tabsInScope": [],
    }


def dataset_for(chart: dict) -> str:
    return next(v for v in VIEWS if uid("dataset", v) == chart["dataset_uuid"])


def dashboard_filters(report: dict, charts: list[dict]) -> list[dict]:
    slug, n = report["slug"], len(charts)
    first = dataset_for(charts[0])
    names = {c for c, _ in VIEWS[first]}
    out = [_native(slug, "Model", "filter_select", first, "model_name", n,
                   "The models to show: the models you have in EA Explorer (several at a time)")]
    if report["code"] == "SR-22":
        out.append(_native(slug, "Chosen entity", "filter_select", first, "chosen_entity", n,
                           "The entity whose dependants to show", multi=False))
    for label, column in THRESHOLD_FILTERS.get(first, []):
        out.append(_native(slug, label, "filter_select", "heat_thresholds", column, n,
                           "Threshold for the bands; leave empty for the default", multi=False))
    for label, column in COMMON_SELECTS:
        if column in names and not (column == "band" and first in HEAT):
            out.append(_native(slug, label, "filter_select", first, column, n))
    for label, column in RANGES.get(report["code"], []):
        if column in names:
            out.append(_native(slug, label, "filter_range", first, column, n, "Show rows between these values"))
    if any(t == "TIMESTAMP WITH TIME ZONE" for _, t in VIEWS[first]):
        out.append(_native(slug, "Time range", "filter_time", None, None, n, "The period to show"))
    return out


def dashboard(report: dict, charts: list[dict]) -> dict:
    slug = report["slug"]
    title = f"{report['code']} {report['title']}" if report["code"].startswith("SR") else report["title"]
    position: dict = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
    }
    note = (f"**{title}** ({report['group']}): {report['about']}  \nChoose one or more models in the Model filter on the left: "
            "it lists the models you have in EA Explorer, and inside them you see all their data. *Open* goes to the entity.")
    position["ROW-0"] = {"type": "ROW", "id": "ROW-0", "children": ["MARKDOWN-0"], "parents": ["ROOT_ID", "GRID_ID"],
                         "meta": {"background": "BACKGROUND_TRANSPARENT"}}
    position["MARKDOWN-0"] = {"type": "MARKDOWN", "id": "MARKDOWN-0", "children": [],
                              "parents": ["ROOT_ID", "GRID_ID", "ROW-0"], "meta": {"width": 12, "height": 14, "code": note}}
    position["GRID_ID"]["children"].append("ROW-0")
    row, used = None, 12
    for i, c in enumerate(charts, start=1):
        width = c.get("_width", 12)
        if row is None or used + width > 12:
            row, used = f"ROW-{i}", 0
            position[row] = {"type": "ROW", "id": row, "children": [], "parents": ["ROOT_ID", "GRID_ID"],
                             "meta": {"background": "BACKGROUND_TRANSPARENT"}}
            position["GRID_ID"]["children"].append(row)
        el = f"CHART-{i}"
        position[row]["children"].append(el)
        used += width
        position[el] = {"type": "CHART", "id": el, "children": [], "parents": ["ROOT_ID", "GRID_ID", row],
                        "meta": {"width": width, "height": 60 if c["viz_type"] == "table" else 50, "uuid": c["uuid"],
                                 "chartId": i, "sliceName": c["slice_name"]}}

    filters = dashboard_filters(report, charts)
    return {
        "dashboard_title": title, "description": None, "css": "", "slug": slug, "certified_by": "EA Explorer",
        "certification_details": f"Standard report ({report['group']})", "published": True, "uuid": uid("dashboard", slug),
        "position": position,
        "metadata": {"color_scheme": "", "refresh_frequency": 0, "expanded_slices": {}, "label_colors": {},
                     "timed_refresh_immune_slices": [], "cross_filters_enabled": True, "default_filters": "{}",
                     "chart_configuration": {}, "native_filter_configuration": filters},
        "version": "1.0.0",
    }


def _name(text_: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text_).strip("_")


def bundle(report: dict, db_password: str, db_name: str, public_url: str) -> dict[str, dict]:
    charts = charts_for(report)
    files: dict[str, dict] = {
        "metadata.yaml": {"version": "1.0.0", "type": "Dashboard", "timestamp": datetime.now(UTC).isoformat()},
        "databases/EA_Explorer_reports.yaml": sample_files(db_password, db_name)["databases/EA_Explorer_reports.yaml"],
    }
    wanted = {c["dataset_uuid"] for c in charts}
    wanted |= {t["datasetUuid"] for f in dashboard_filters(report, charts) for t in f["targets"] if t}
    for name in sorted(v for v in VIEWS if uid("dataset", v) in wanted):
        files[f"datasets/EA_Explorer_reports/{name}.yaml"] = dataset(name, public_url)
    for c in charts:
        files[f"charts/{_name(c['slice_name'])}_{c['uuid'][:8]}.yaml"] = {k: v for k, v in c.items() if not k.startswith("_")}
    files[f"dashboards/{_name(report['slug'])}.yaml"] = dashboard(report, charts)
    return files


def build_report_bundles(folder: Path, db_password: str, db_name: str = "eaexplorer",
                         public_url: str = "https://localhost") -> list[Path]:
    """Writes one zip per standard report into folder/reports and returns their paths."""
    out_dir = folder / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.zip"):
        old.unlink()
    written = []
    for report in REPORTS:
        buffer = io.BytesIO()
        root = report["slug"].replace("-", "_")
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in bundle(report, db_password, db_name, public_url).items():
                zf.writestr(f"{root}/{name}", yaml.safe_dump(content, sort_keys=False))
        out = out_dir / f"{report['slug']}.zip"
        out.write_bytes(buffer.getvalue())
        out.chmod(0o644)
        written.append(out)
    return written
