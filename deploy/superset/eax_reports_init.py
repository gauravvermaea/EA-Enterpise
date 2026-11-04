"""Run by the reports-init service after the report dashboards are imported (superset-init.sh).

1. Adds a dataset for every typed report view (rpt.t_<entity type>, one column per attribute) and
   removes datasets whose view has gone (when no chart uses them) (D139).
2. Re-reads every report dataset's columns from the database, so the datasets follow the views.
3. The role "EA Explorer reports" may read every report dataset; Keycloak users get it at sign-in
   (superset_config.AUTH_ROLES_MAPPING), except IT Admins and Keycloak Admins, who see no content (D98).
4. Model access (D138): reports run in the context of one or more models, and a person sees only the
   models they have in EA Explorer (rpt.model_access: their model roles, the models above them and the
   published library). Inside a model they see all of its data: there is no filtering by record.
   Superset applies this with one rule on every report dataset (its "row level security" feature, used
   here at model level only), so the Model drop-down lists only their models and a chart without a
   model filter still shows nothing else. Superset's Admin role (the Super Admin and the break-glass
   admin) sees every model.

Safe to run on every start. Any failure is reported and the service still finishes: Superset works,
only the reports are affected.
"""

from __future__ import annotations

import sys

from sqlalchemy import text

DATABASE = "EA Explorer reports"
ROLE = "EA Explorer reports"
RLS_NAME = "EA Explorer: model access"
CLAUSE = "model_id IN (SELECT model_id FROM rpt.model_access WHERE username = lower('{{ current_username() }}'))"
NOT_REPORTS = {"v_heartbeat"}   # operations, not content: Admin only


def _engine(database):
    """Superset 4.x gives the engine as a context manager."""
    return database.get_sqla_engine()


def main() -> int:
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import db
        from superset import security_manager as sm
        from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable, SqlMetric
        from superset.models.core import Database
        from superset.utils.core import RowLevelSecurityFilterType

        database = db.session.query(Database).filter_by(database_name=DATABASE).one_or_none()
        if database is None:
            print("EA Explorer WARNING: the report database connection is missing; reports not set up")
            return 0
        with _engine(database) as engine, engine.connect() as conn:
            views = {r[0]: {c for c in r[1]} for r in conn.execute(text(
                """SELECT table_name, array_agg(column_name::text) FROM information_schema.columns
                    WHERE table_schema = 'rpt' GROUP BY table_name"""))}

        existing = {t.table_name: t for t in db.session.query(SqlaTable).filter_by(database_id=database.id, schema="rpt")}
        added = removed = 0
        for name in sorted(v for v in views if v.startswith("t_") and v not in existing):
            t = SqlaTable(table_name=name, schema="rpt", database=database,
                          description=f"EA Explorer typed report view rpt.{name} (one column per attribute)")
            db.session.add(t)
            db.session.flush()
            existing[name] = t
            added += 1
        for name, t in list(existing.items()):
            if t.sql:          # a dataset written as SQL (the heatmaps with thresholds): kept, not a view
                continue
            if name not in views:
                if not t.slices:
                    db.session.delete(t)
                    removed += 1
                existing.pop(name)
        db.session.commit()

        for name, t in existing.items():
            try:
                t.fetch_metadata()
            except Exception as exc:  # noqa: BLE001
                print(f"EA Explorer WARNING: could not read the columns of rpt.{name}: {exc}")
            if not any(m.metric_name == "count" for m in t.metrics):
                t.metrics.append(SqlMetric(metric_name="count", verbose_name="Count", metric_type="count",
                                           expression="COUNT(*)"))
        db.session.commit()

        role = sm.find_role(ROLE) or sm.add_role(ROLE)
        for name, t in existing.items():
            if name in NOT_REPORTS:
                continue
            pv = sm.add_permission_view_menu("datasource_access", t.get_perm())
            sm.add_permission_role(role, pv)
        db.session.commit()

        rule = db.session.query(RowLevelSecurityFilter).filter_by(name=RLS_NAME).one_or_none()
        if rule is None:
            rule = RowLevelSecurityFilter(name=RLS_NAME)
            db.session.add(rule)
        rule.description = "The models the person has in EA Explorer; all data inside them (D138)"
        rule.filter_type = RowLevelSecurityFilterType.BASE
        rule.clause = CLAUSE
        rule.group_key = None
        rule.tables = [t for name, t in existing.items()
                       if name not in NOT_REPORTS and "model_id" in {c.column_name for c in t.columns}]
        admin = sm.find_role("Admin")
        rule.roles = [admin] if admin else []
        db.session.commit()
        print(f"EA Explorer: report datasets ready ({len(existing)} datasets, {added} added, {removed} removed); "
              f"model access on {len(rule.tables)} datasets")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"EA Explorer WARNING: report set-up failed: {exc}")
        sys.exit(0)
