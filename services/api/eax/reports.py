"""Reports (phase 5 with the phase 11 standard reports, D137-D140).

* refresh_typed_views: one report view per entity type (rpt.t_<type>), one column per attribute; run after
  every metamodel change and after the seed. Views that did not change are left alone.
* note_user: records each person's global roles (core.known_users) so the reports' model access knows who is a
  Super Admin; at most once every few minutes per person.
* catalogue: the metamodel as the report builder sees it: every type, attribute, view and column (D71).
* REPORTS: the standard reports and their Superset dashboards (built by eax.setup.superset_reports).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy import text

from .report_defs import REPORTS

_seen: dict[str, tuple[float, tuple[str, ...]]] = {}
_seen_lock = threading.Lock()
NOTE_EVERY = 300  # seconds


def refresh_typed_views(conn) -> int:
    """Brings the typed report views in line with every metamodel (SQLAlchemy connection, same transaction)."""
    return int(conn.execute(text("SELECT rpt.refresh_typed_views()")).scalar_one() or 0)


def note_user(username: str, roles: list[str] | tuple[str, ...]) -> None:
    """Upserts the person's global roles; skipped when seen recently with the same roles. Never fails a call."""
    if not username:
        return
    key, now, wanted = username.lower(), time.monotonic(), tuple(sorted(roles or ()))
    with _seen_lock:
        last = _seen.get(key)
        if last and last[1] == wanted and now - last[0] < NOTE_EVERY:
            return
        _seen[key] = (now, wanted)
    try:
        from .db import get_engine
        with get_engine().begin() as conn:
            conn.execute(text("""INSERT INTO core.known_users (username, roles, seen_at) VALUES (:u, :r, now())
                                 ON CONFLICT (username) DO UPDATE SET roles = EXCLUDED.roles, seen_at = now()"""),
                         {"u": key, "r": list(wanted)})
    except Exception:  # noqa: BLE001 - reports must never stop the API answering
        with _seen_lock:
            _seen.pop(key, None)


def catalogue(conn, model_id: int) -> dict[str, Any]:
    """The model's types and attributes with the report view and column each is in."""
    rows = conn.execute(text("""SELECT layer, entity_type_code, entity_type, report_view, attribute_code, attribute,
                                       data_type, pick_list, pick_list_values, required, report_column
                                  FROM rpt.catalogue WHERE model_id = :m
                                 ORDER BY layer, entity_type, attribute"""), {"m": model_id}).mappings().all()
    types: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = types.setdefault(r["entity_type_code"], {
            "layer": r["layer"], "code": r["entity_type_code"], "name": r["entity_type"], "view": r["report_view"],
            "attributes": []})
        if r["attribute_code"]:
            t["attributes"].append({
                "code": r["attribute_code"], "name": r["attribute"], "data_type": r["data_type"],
                "pick_list": r["pick_list"] or "", "values": r["pick_list_values"] or "",
                "required": bool(r["required"]), "column": r["report_column"]})
    roles = conn.execute(text("SELECT role, entity_type_code FROM rpt.std_roles ORDER BY role, entity_type_code")).mappings().all()
    present = {c.lower() for c in types}
    standard: dict[str, list[str]] = {}
    for r in roles:
        if r["entity_type_code"].lower() in present:
            standard.setdefault(r["role"], []).append(r["entity_type_code"])
    return {"types": list(types.values()), "standard_roles": standard,
            "generic_views": ["rpt.models", "rpt.entities", "rpt.entity_values", "rpt.relationships", "rpt.changes",
                              "rpt.entity_pairs", "rpt.entity_std"],
            "reports": [dict(r) for r in REPORTS]}


def reports_base_url() -> str:
    from .config import get_settings, public_url
    s = get_settings()
    return public_url(s.hostname, s.https_port, prefix="reports.")


def model_reports(conn, model: Any) -> dict[str, Any]:
    """A model's reports: the standard dashboards (with links) and its report catalogue. The person must
    be able to read the model (core.models shows only the models they have)."""
    from . import repository as repo
    m = repo.get_model(conn, model)
    base = reports_base_url()
    out = catalogue(conn, m["_id"])
    out["model"] = {"id": str(m["id"]), "name": m["name"]}
    out["reports_url"] = base
    out["reports"] = [{**r, "url": f"{base}/login/keycloak?next=/superset/dashboard/{r['slug']}/"} for r in REPORTS]
    return out
