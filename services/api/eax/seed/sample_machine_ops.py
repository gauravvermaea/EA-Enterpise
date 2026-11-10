"""Laptop sample (owner, 10 Nov 2026, phases 25 and 35, AGENTS.md): machine access and operations in every state, made once.

Machine access: three service accounts (one disabled) and credentials in every state: tokens, API keys and a client
certificate; active, expiring within two weeks, expired, revoked, never used; limited to the demo estate or not; read
or read-write on different areas. Every secret is random and thrown away at once (only its hash is kept), so none of
them can be used: make your own on System admin > Machine access. The certificate is a self-signed one made here.

Operations: usage over the last 200 days (two models idle for more than 180 days), an uncommitted change and a load left
for weeks, retention rules (one changed by an IT Admin), a confirmed dry run, a run that archived old records, and a new
dry run waiting to be confirmed because rules changed since: one, set by a Super Admin, removes history versions older
than a year, and the dry run shows the sample's older history (two and three years old) it would remove (D445).
"""

from __future__ import annotations

import json
import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from .demo_estate import DEMO_NAME

MARK = "svc-reporting-hub"


def _cert(common_name: str) -> tuple[str, str, datetime]:
    """A self-signed certificate (PEM), its SHA-256 fingerprint and its expiry."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())          # the key is thrown away: the sample cannot sign anything in
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Protea Insurance (sample)")])
    now = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=400)).sign(key, hashes.SHA256()))
    return cert.public_bytes(Encoding.PEM).decode(), cert.fingerprint(hashes.SHA256()).hex(), now + timedelta(days=400)


def run() -> list[str]:
    from .. import machine_access as ma
    from .. import operations as ops
    from ..db import get_engine

    said: list[str] = []
    with get_engine().begin() as conn:
        if conn.execute(text("SELECT 1 FROM core.service_accounts WHERE username = :u"), {"u": MARK}).first():
            return []
        demo = conn.execute(text("SELECT guid::text FROM core.models WHERE name = :n AND NOT is_deleted"), {"n": DEMO_NAME}).scalar()
        now = datetime.now(UTC)

        # ---- service accounts
        for user, name, desc, roles, disabled in [
            ("svc-reporting-hub", "Reporting hub", "The group reporting platform reads the estate every night.", ["user"], False),
            ("svc-cmdb-sync", "Configuration database sync", "Sends technology changes from the configuration database.", ["user"], False),
            ("svc-old-import", "Old spreadsheet import", "Replaced by the configuration database sync.", ["user"], True),
        ]:
            conn.execute(text("""INSERT INTO core.service_accounts (username, name, description, roles, created_by, created_at,
                                         disabled_at, disabled_by)
                                  VALUES (:u, :n, :d, :r, 'user_it_admin', :c, :da, :db)"""),
                         {"u": user, "n": name, "d": desc, "r": roles, "c": now - timedelta(days=120),
                          "da": now - timedelta(days=20) if disabled else None, "db": "user_it_admin" if disabled else None})
        if demo:
            for user, role in (("svc-reporting-hub", "report-viewer"), ("svc-cmdb-sync", "architect")):
                conn.execute(text("""INSERT INTO core.model_users (model_id, username, role)
                                      SELECT id, :u, :r FROM core.models WHERE guid = CAST(:m AS uuid)
                                      ON CONFLICT DO NOTHING"""), {"u": user, "r": role, "m": demo})
        said.append("3 service accounts (one disabled)")

        # ---- credentials in every state (random secrets, thrown away)
        def cred(owner, kind, name, scopes, days_left, *, models=(), used=None, revoked=None, created_ago=30,
                 cert=None, by=None):
            secret = None if kind == "certificate" else ma.new_secret(kind)
            conn.execute(text("""
                INSERT INTO core.machine_credentials (owner, kind, name, secret_prefix, secret_hash, cert_fingerprint, cert_subject,
                       cert_not_after, cert_pem, scopes, model_guids, expires_at, created_by, created_at, revoked_at, revoked_by,
                       revoke_reason, last_used_at, last_used_from, last_used_path, use_count)
                VALUES (:o, :k, :n, :sp, :sh, :cf, :cs, :cn, :cp, CAST(:sc AS jsonb), CAST(:mg AS uuid[]), :e, :by, :ca, :ra, :rb,
                        :rr, :lu, :lf, :lp, :uc)"""),
                {"o": owner, "k": kind, "n": name, "sp": secret[:12] if secret else "",
                 "sh": ma.hash_secret(secret) if secret else None, "cf": cert and cert[1],
                 "cs": "CN=cmdb-sync.protea.example,O=Protea Insurance (sample)" if cert else "",
                 "cn": cert and cert[2], "cp": cert[0] if cert else "", "sc": json.dumps(scopes),
                 "mg": "{" + ",".join(m for m in models if m) + "}", "e": now + timedelta(days=days_left),
                 "by": by or owner, "ca": now - timedelta(days=created_ago),
                 "ra": now - timedelta(days=revoked) if revoked else None, "rb": owner if revoked else None,
                 "rr": "The laptop it ran on was replaced." if revoked else "",
                 "lu": now - timedelta(hours=used) if used is not None else None,
                 "lf": "10.20.4.17" if used is not None else "", "lp": "GET /api/v1/models" if used is not None else "",
                 "uc": random.randint(40, 900) if used is not None else 0})
        cred("user_architect", "token", "Excel OData feed", {"reports": "read"}, 60, used=20)
        cred("user_architect", "token", "Claude desktop", {"mcp": "read", "models": "read"}, 85)
        cred("user_architect", "token", "Old capacity script", {"models": "read-write"}, 40, used=24 * 50, revoked=45, created_ago=100)
        cred("user_model_admin", "api_key", "Portfolio planning tool", {"models": "read-write", "reports": "read"}, 7,
             models=[demo], used=3, created_ago=358)
        cred("svc-reporting-hub", "api_key", "Nightly extract", {"models": "read", "reports": "read", "metamodel": "read"}, 300,
             used=9, by="user_it_admin")
        cred("svc-cmdb-sync", "certificate", "Configuration database (mutual TLS)", {"models": "read-write"}, 365,
             models=[demo], used=1, cert=_cert("cmdb-sync.protea.example"), by="user_it_admin")
        cred("svc-old-import", "api_key", "Spreadsheet import", {"models": "read-write"}, -25, used=24 * 30, created_ago=390,
             by="user_it_admin")
        cred("user_it_admin", "token", "Prometheus", {"administration": "read"}, 300, used=0)
        said.append("8 credentials: active, expiring, expired, revoked, never used, a client certificate")

        # ---- usage over the last 200 days; two models idle for more than 180 days
        models = {r["name"]: r["guid"] for r in conn.execute(text(
            "SELECT name, guid::text AS guid FROM core.models WHERE NOT is_deleted AND kind_code <> 'template'")).mappings()}
        idle = [n for n in ("Karoo Re (independent)", "Lean EA metamodel") if n in models]
        busy = [n for n in models if n not in idle]
        rng = random.Random(25)
        people = ["user_architect", "user_model_admin", "user_model_sub_admin", "user_super_admin", "user_lead_architect",
                  "user_project_admin"]
        feats = [("models", "models/entities"), ("models", "models/content"), ("metamodel", "models/metamodel"),
                 ("reports", "models/reports"), ("reports", "quality"), ("projects", "projects/steps"),
                 ("models", "models/drawn-views"), ("change_log", "change-log")]
        rows = {}
        for back in range(0, 200):
            day = (date.today() - timedelta(days=back))
            if day.weekday() >= 5 and rng.random() < 0.8:
                continue
            for p in rng.sample(people, rng.randint(2, len(people))):
                for area, feat in rng.sample(feats, 3):
                    m = models[rng.choice(busy)] if feat.startswith("models/") and busy else ""
                    if back > 185 and idle and feat.startswith("models/") and rng.random() < 0.5 and idle[0] in models:
                        m = models[idle[0]]          # Karoo Re: last used more than 180 days ago
                    key = (day.isoformat(), p, area, feat, m, False)
                    rows[key] = rows.get(key, 0) + rng.randint(3, 60)
            if back < 60:
                rows[(day.isoformat(), "svc-reporting-hub", "reports", "models/reports", models.get(DEMO_NAME, ""), True)] = 24
        for (d, u, a, f, m, mc), n in rows.items():
            conn.execute(text("""INSERT INTO core.usage_daily (day, username, area, feature, model_guid, machine, calls)
                                  VALUES (CAST(:d AS date), :u, :a, :f, :m, :mc, :n) ON CONFLICT DO NOTHING"""),
                         {"d": d, "u": u, "a": a, "f": f, "m": m, "mc": mc, "n": n})
        said.append(f"usage over 200 days ({len(rows)} rows); idle: {', '.join(idle) or 'none'}")

        # ---- stale work: one uncommitted change and one load left for weeks (the sample data's own, made older)
        pc = conn.execute(text("SELECT id FROM core.pending_changes WHERE status = 'pending' ORDER BY id LIMIT 1")).scalar()
        if pc:
            conn.execute(text("UPDATE core.pending_changes SET created_at = now() - interval '45 days' WHERE id = :i"), {"i": pc})
        ld = conn.execute(text("SELECT id FROM core.loads WHERE status IN ('uploaded', 'mapping', 'previewed') ORDER BY id LIMIT 1")).scalar()
        if ld:
            conn.execute(text("UPDATE core.loads SET created_at = now() - interval '21 days' WHERE id = :i"), {"i": ld})

        # ---- housekeeping: a confirmed dry run and a run 40 days ago, then a rule changed, and a new dry run waiting
        old_rules = {code: list(ops.DEFAULTS[code]) for code in ops.RULES}
        dry = conn.execute(text("""INSERT INTO core.housekeeping_runs (dry_run, started_by, started_at, finished_at, rules, results,
                                           confirmed_at, confirmed_by, status)
                                    VALUES (true, 'schedule', :s, :s, CAST(:r AS jsonb), CAST(:res AS jsonb), :c, 'user_super_admin', 'done')
                                    RETURNING id"""),
                           {"s": now - timedelta(days=41), "c": now - timedelta(days=41) + timedelta(hours=7), "r": json.dumps(old_rules),
                            "res": json.dumps({k: {"action": v[0], "after_days": v[1], "found": {"notifications": 2, "loads": 1}.get(k, 0),
                                                   "archived": 0, "deleted": 0, "note": ops.HISTORY_NOTE if k == "history_versions" else ""}
                                               for k, v in old_rules.items()})}).scalar()
        real = conn.execute(text("""INSERT INTO core.housekeeping_runs (dry_run, started_by, started_at, finished_at, rules, results, status)
                                     VALUES (false, 'schedule', :s, :s, CAST(:r AS jsonb), CAST(:res AS jsonb), 'done') RETURNING id"""),
                            {"s": now - timedelta(days=40), "r": json.dumps(old_rules),
                             "res": json.dumps({k: {"action": v[0], "after_days": v[1], "found": {"notifications": 2, "loads": 1}.get(k, 0),
                                                    "archived": {"notifications": 2, "loads": 1}.get(k, 0), "deleted": 0,
                                                    "note": ops.HISTORY_NOTE if k == "history_versions" else ""}
                                                for k, v in old_rules.items()})}).scalar()
        archived = [
            ("loads", "core.loads", "Claims applications 2025.csv (added)", {"file_name": "Claims applications 2025.csv",
             "status": "added", "owner": "user_architect", "format": "csv"}, b"Name,Lifecycle\nClaims Hub,Active\nOld Claims Desk,Retiring\n", 400),
            ("notifications", "core.notifications", "Changes committed on Protea Insurance (demo estate)",
             {"kind": "commit.done", "title": "Changes committed on Protea Insurance (demo estate)", "actor": "user_model_admin",
              "recipients": [{"username": "user_architect"}]}, None, 420),
            ("notifications", "core.notifications", "The Fynbos Life model was locked",
             {"kind": "model.locked", "title": "The Fynbos Life model was locked", "actor": "user_model_admin",
              "recipients": [{"username": "user_architect"}, {"username": "user_model_sub_admin"}]}, None, 380),
        ]
        for i, (rule, table, summary, data, content, age) in enumerate(archived, start=1):
            conn.execute(text("""INSERT INTO core.archived_items (rule, source_table, source_id, summary, data, content, created_at,
                                         archived_at, run_id)
                                  VALUES (:r, :t, :i, :s, CAST(:d AS jsonb), :c, :ca, :aa, :run)
                                  ON CONFLICT (source_table, source_id) DO NOTHING"""),
                         {"r": rule, "t": table, "i": 900000 + i, "s": summary, "d": json.dumps(data), "c": content,
                          "ca": now - timedelta(days=age), "aa": now - timedelta(days=40), "run": real})
        # old history (D445): earlier versions of 30 demo-estate entities, two and three years old, so the history rule
        # (set by a Super Admin to remove versions older than a year) shows what it would remove in the waiting dry run
        if demo:
            conn.execute(text("""
                INSERT INTO history.row_versions (table_name, row_id, row_guid, model_id, row_version, operation, data, label,
                                                  changed_at, changed_by)
                SELECT h.table_name, h.row_id, h.row_guid, h.model_id, v.n, CASE WHEN v.n = -1 THEN 'insert' ELSE 'update' END,
                       h.data, 'Sample: older history (laptop)', now() - make_interval(days => v.age), 'user_architect'
                  FROM (SELECT DISTINCT ON (h.row_id) h.* FROM history.row_versions h
                          JOIN core.models m ON m.id = h.model_id AND m.guid = CAST(:m AS uuid)
                         WHERE h.table_name = 'entities' ORDER BY h.row_id, h.row_version LIMIT 30) h
                 CROSS JOIN (VALUES (-1, 1100), (0, 730)) AS v(n, age)"""), {"m": demo})
        ops.set_rule(conn, "user_super_admin", "history_versions", "delete", 365, ("super-admin",))
        ops.set_rule(conn, "user_it_admin", "webhook_deliveries", "delete", 180)
        conn.execute(text("UPDATE core.retention_rules SET set_at = now() - interval '3 days' WHERE code IN ('webhook_deliveries', 'history_versions')"))
        waiting = ops.run(conn, "schedule", dry_run=True)
        said.append(f"housekeeping: confirmed dry run {dry}, run {real} (3 archived), a dry run waiting ({waiting['id']})")
    return said

