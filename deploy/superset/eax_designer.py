"""Superset's side of EA Explorer's report designer (phase 24, D365, D434).

EA Explorer keeps a report design and the SQL made from it (core.report_designs, read here through rpt.report_designs
with the report login). Its Open button comes here, signed in to Superset through Keycloak as the person:

    /eax/designs/<guid>/open

This page makes the design's dataset (a dataset written as SQL on the "EA Explorer reports" connection), or brings it up to
date with the design, gives the readers' role access to it, puts it under the model-access rule (D138: the person still
sees only the models they have), and opens Superset's chart builder on it. Nothing else: charts and dashboards are made in
Superset as usual.
"""

from __future__ import annotations

from flask import Blueprint, abort, redirect, request
from sqlalchemy import text

DATABASE = "EA Explorer reports"
ROLE = "EA Explorer reports"
RLS_NAME = "EA Explorer: model access"

bp = Blueprint("eax_designer", __name__, url_prefix="/eax")


def dataset_name(name: str, guid: str) -> str:
    return f"Designed: {name} [{guid[:8]}]"


@bp.route("/designs/<guid>/open")
def open_design(guid: str):
    import re

    from flask_login import current_user
    from superset import db
    from superset import security_manager as sm
    from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable
    from superset.models.core import Database
    user = current_user._get_current_object() if current_user else None
    if user is None or not getattr(user, "is_authenticated", False):
        return redirect(f"/login/keycloak?next={request.path}")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", guid):
        abort(404)
    database = db.session.query(Database).filter_by(database_name=DATABASE).one_or_none()
    if database is None:
        abort(503, "The report connection is not set up yet; try again after the reports have started.")
    with database.get_sqla_engine() as engine, engine.connect() as conn:
        d = conn.execute(text("SELECT design_guid::text, model_id, name, sql FROM rpt.report_designs "
                              "WHERE design_guid = CAST(:g AS uuid)"), {"g": guid}).mappings().first()
        if d is None:
            abort(404, "No such report design: it may have been deleted in EA Explorer.")
        admin = any(r.name == "Admin" for r in user.roles)
        if not admin and not conn.execute(text("SELECT 1 FROM rpt.model_access WHERE username = lower(:u) AND model_id = :m"),
                                          {"u": user.username, "m": d["model_id"]}).first():
            abort(403, "You do not have this design's model in EA Explorer.")
    name = dataset_name(d["name"], guid)
    ds = (db.session.query(SqlaTable).filter(SqlaTable.database_id == database.id, SqlaTable.schema == "rpt",
                                             SqlaTable.table_name.like(f"Designed: % [{guid[:8]}]")).one_or_none())
    if ds is None:
        ds = SqlaTable(table_name=name, schema="rpt", database=database, sql=d["sql"],
                       description="Made from an EA Explorer report design (D434)")
        db.session.add(ds)
    else:
        ds.table_name, ds.sql = name, d["sql"]
    if user not in ds.owners:
        ds.owners.append(user)
    db.session.flush()
    ds.fetch_metadata()
    role = sm.find_role(ROLE) or sm.add_role(ROLE)
    sm.add_permission_role(role, sm.add_permission_view_menu("datasource_access", ds.get_perm()))
    rule = db.session.query(RowLevelSecurityFilter).filter_by(name=RLS_NAME).one_or_none()
    if rule is not None and ds not in rule.tables:
        rule.tables.append(ds)
    db.session.commit()
    return redirect(f"/explore/?datasource_type=table&datasource_id={ds.id}")
