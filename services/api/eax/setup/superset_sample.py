"""Builds the Superset import bundle for the phase 0 sample dashboard.

The bundle follows Superset's export format (version 1.0.0): one database connection (the
read-only report login), one dataset (rpt.v_heartbeat), one table chart and one dashboard.
The superset-init script imports it with:  superset import-dashboards -p <zip> -u admin
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import yaml

# Fixed IDs so that importing again updates the same objects instead of adding copies.
DB_UUID = "6f4c2a52-2b0e-4b5e-9d63-6b0c0e7a0001"
DATASET_UUID = "6f4c2a52-2b0e-4b5e-9d63-6b0c0e7a0002"
CHART_UUID = "6f4c2a52-2b0e-4b5e-9d63-6b0c0e7a0003"
DASHBOARD_UUID = "6f4c2a52-2b0e-4b5e-9d63-6b0c0e7a0004"

COLUMNS = [
    ("id", "BIGINT", False), ("at", "TIMESTAMP WITH TIME ZONE", True),
    ("day", "TIMESTAMP WITH TIME ZONE", True), ("source", "TEXT", False),
    ("note", "TEXT", False), ("requested_by", "TEXT", False), ("job_id", "BIGINT", False),
]


def _column(name: str, type_: str, is_dttm: bool) -> dict:
    return {
        "column_name": name, "verbose_name": None, "is_dttm": is_dttm, "is_active": True,
        "type": type_, "advanced_data_type": None, "groupby": True, "filterable": True,
        "expression": None, "description": None, "python_date_format": None, "extra": {},
    }


def bundle_files(db_password: str, db_name: str = "eaexplorer") -> dict[str, dict]:
    database = {
        "database_name": "EA Explorer reports",
        "sqlalchemy_uri": f"postgresql+psycopg2://eax_report:{quote(db_password, safe='')}@db:5432/{db_name}",
        "cache_timeout": None,
        "expose_in_sqllab": True,
        "allow_run_async": False,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allow_file_upload": False,
        "extra": {"allows_virtual_table_explore": True},
        "uuid": DB_UUID,
        "version": "1.0.0",
    }
    dataset = {
        "table_name": "v_heartbeat",
        "main_dttm_col": "at",
        "description": "Phase 0 sample: heartbeats recorded by the API and the job runner",
        "default_endpoint": None,
        "offset": 0,
        "cache_timeout": None,
        "schema": "rpt",
        "sql": None,
        "params": None,
        "template_params": None,
        "filter_select_enabled": True,
        "fetch_values_predicate": None,
        "extra": None,
        "normalize_columns": False,
        "always_filter_main_dttm": False,
        "uuid": DATASET_UUID,
        "metrics": [{
            "metric_name": "count", "verbose_name": "Heartbeats", "metric_type": "count",
            "expression": "COUNT(*)", "description": None, "d3format": None,
            "currency": None, "extra": {}, "warning_text": None,
        }],
        "columns": [_column(*c) for c in COLUMNS],
        "version": "1.0.0",
        "database_uuid": DB_UUID,
    }
    chart = {
        "slice_name": "Heartbeats recorded",
        "description": "Every heartbeat written by the API or the job runner",
        "certified_by": None,
        "certification_details": None,
        "viz_type": "table",
        "params": {
            "datasource": f"{DATASET_UUID}__table",
            "viz_type": "table",
            "query_mode": "raw",
            "all_columns": ["at", "source", "note", "requested_by", "job_id"],
            "order_by_cols": ['["at", false]'],
            "row_limit": 1000,
            "server_page_length": 25,
            "adhoc_filters": [],
            "include_search": True,
            "table_timestamp_format": "smart_date",
        },
        "query_context": None,
        "cache_timeout": None,
        "uuid": CHART_UUID,
        "version": "1.0.0",
        "dataset_uuid": DATASET_UUID,
    }
    dashboard = {
        "dashboard_title": "EA Explorer - phase 0 sample",
        "description": None,
        "css": "",
        "slug": "eax-phase0-sample",
        "certified_by": None,
        "certification_details": None,
        "published": True,
        "uuid": DASHBOARD_UUID,
        "position": {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
            "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["ROW-1"],
                        "parents": ["ROOT_ID"]},
            "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER",
                          "meta": {"text": "EA Explorer - phase 0 sample"}},
            "ROW-1": {"type": "ROW", "id": "ROW-1", "children": ["CHART-1"],
                      "parents": ["ROOT_ID", "GRID_ID"],
                      "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "CHART-1": {"type": "CHART", "id": "CHART-1", "children": [],
                        "parents": ["ROOT_ID", "GRID_ID", "ROW-1"],
                        "meta": {"width": 12, "height": 60, "uuid": CHART_UUID, "chartId": 1,
                                 "sliceName": "Heartbeats recorded"}},
        },
        "metadata": {
            "color_scheme": "", "refresh_frequency": 0, "expanded_slices": {},
            "label_colors": {}, "timed_refresh_immune_slices": [],
            "cross_filters_enabled": True, "default_filters": "{}",
            "chart_configuration": {}, "native_filter_configuration": [],
        },
        "version": "1.0.0",
    }
    meta = {
        "version": "1.0.0",
        "type": "Dashboard",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "metadata.yaml": meta,
        "databases/EA_Explorer_reports.yaml": database,
        "datasets/EA_Explorer_reports/v_heartbeat.yaml": dataset,
        "charts/Heartbeats_recorded.yaml": chart,
        "dashboards/EA_Explorer_-_phase_0_sample.yaml": dashboard,
    }


def build_sample_bundle(folder: Path, db_password: str, db_name: str = "eaexplorer") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "sample_dashboard.zip"
    root = "eax_phase0_sample"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in bundle_files(db_password, db_name).items():
            zf.writestr(f"{root}/{name}", yaml.safe_dump(content, sort_keys=False))
    out.write_bytes(buffer.getvalue())
    out.chmod(0o644)
    return out


# A fresh UUID helper for future bundles (kept here so new samples follow the same pattern).
def new_uuid() -> str:
    return str(uuid.uuid4())
