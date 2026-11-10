"""Machine access (phase 25, D366, D378, D438 to D441): areas, scopes, secrets, certificates, the proxy's own port. No
database or Docker needed."""

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from eax import machine_access as ma

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
G = "0b4f6a52-4c1e-4f7d-9a8e-3b2c1d0e9f11"
H = "11111111-2222-4333-8444-555555555555"


@pytest.mark.parametrize("path, area", [
    ("/mcp", "mcp"),
    ("/api/v1/change-log/", "change_log"),
    ("/api/v1/admin/backups/", "administration"),
    ("/api/v1/audit", "administration"),
    ("/api/v1/sql/query", "administration"),
    ("/api/v1/machine-access/credentials", "administration"),
    ("/api/v1/operations/usage", "administration"),
    ("/api/metrics", "administration"),
    ("/api/v1/reference-library/", "library"),
    ("/api/v1/models/library/", "library"),
    (f"/api/v1/projects/{G}/library/", "library"),
    (f"/api/v1/projects/{G}/documents/x", "documents"),
    (f"/api/v1/models/{G}/change-documents/", "documents"),
    ("/api/v1/odata/Applications", "reports"),
    ("/api/v1/quality/", "reports"),
    (f"/api/v1/models/{G}/reports/", "reports"),
    (f"/api/v1/models/{G}/quality/runs", "reports"),
    ("/api/v1/gaps/x/download/", "reports"),
    (f"/api/v1/models/{G}/metamodel/", "metamodel"),
    (f"/api/v1/models/{G}/entity-types/x", "metamodel"),
    ("/api/v1/metamodel-drafts/", "metamodel"),
    (f"/api/v1/projects/{G}/steps/", "projects"),
    ("/api/v1/repository/board/", "projects"),
    ("/api/v1/models/", "models"),
    (f"/api/v1/models/{G}/entities/", "models"),
    (f"/api/v1/models/{G}/changes/", "models"),
    ("/api/v1/tags/", "models"),
])
def test_every_address_falls_in_its_area(path, area):
    assert ma.area_of(path) == area


def test_addresses_outside_the_api_have_no_area():
    assert ma.area_of("/api/health") is None
    assert ma.area_of("/api/docs") is None


def _m(**kw) -> ma.Machine:
    base = {"id": 1, "guid": G, "owner": "user_architect", "kind": "token", "name": "Excel", "scopes": {"reports": "read"}}
    return ma.Machine(**{**base, **kw})


def test_read_means_get_and_an_area_left_out_is_refused():
    m = _m()
    assert m.refusal("GET", f"/api/v1/models/{G}/reports/") is None
    assert "only read" in m.refusal("POST", f"/api/v1/models/{G}/reports/")
    assert "no access to Models and content" in m.refusal("GET", "/api/v1/models/")
    assert m.refusal("GET", "/api/v1/me") is None and m.refusal("GET", "/api/v1/heartbeat") is None   # always: who am I
    rw = _m(scopes={"models": "read-write"})
    assert rw.refusal("POST", f"/api/v1/models/{G}/changes/") is None
    assert rw.refusal("DELETE", f"/api/v1/models/{G}/entities/x") is None


def test_limits_to_models_and_projects():
    m = _m(scopes={"models": "read-write", "projects": "read"}, model_guids=[G], project_guids=[H])
    assert m.refusal("GET", f"/api/v1/models/{G}/entities/") is None
    assert "other models" in m.refusal("GET", f"/api/v1/models/{H}/entities/")
    assert m.refusal("GET", f"/api/v1/projects/{H}/steps/") is None
    assert "other projects" in m.refusal("GET", f"/api/v1/projects/{G}/steps/")
    assert m.refusal("GET", "/api/v1/models/") is None          # lists: what the owner sees


def test_secrets_are_long_random_and_kept_as_a_hash():
    t, k = ma.new_secret("token"), ma.new_secret("api_key")
    assert t.startswith("eaxt_") and k.startswith("eaxk_") and len(t) > 40 and t != ma.new_secret("token")
    assert ma.hash_secret(t) == ma.hash_secret(f" {t} ") and len(ma.hash_secret(t)) == 64 and t not in ma.hash_secret(t)
    assert ma.looks_like_secret(t) and not ma.looks_like_secret("eyJhbGciOi.keycloak.jwt")


def test_what_a_call_presents():
    t = ma.new_secret("token")
    assert ma.presented({}, t) == ("secret", t)
    assert ma.presented({"X-API-Key": t}, None) == ("secret", t)
    assert ma.presented({}, "eyJhbGciOiJSUzI1NiJ9.a.b") is None            # a Keycloak token: the usual sign-in
    pem = _pem()[0]
    assert ma.presented({ma.CERT_HEADER: urllib.parse.quote(pem)}, None) == ("certificate", pem.strip())
    assert ma.presented({ma.CERT_HEADER: "nonsense"}, None) is None


def _pem():
    from eax.seed.sample_machine_ops import _cert
    return _cert("test.example")


def test_a_certificate_is_known_by_its_sha256_fingerprint():
    pem, fp, _ = _pem()
    info = ma.cert_info(pem)
    assert info["fingerprint"] == fp and len(fp) == 64
    assert "CN=test.example" in info["subject"] and info["not_after"] > datetime.now(UTC)
    with pytest.raises(ValueError):
        ma.cert_info("-----BEGIN CERTIFICATE-----\nnot one\n-----END CERTIFICATE-----")


def test_scopes_are_checked():
    assert ma.clean_scopes({"models": "read", "reports": "read-write", "library": "none"}) == {"models": "read", "reports": "read-write"}
    for bad in ({}, {"models": "write"}, {"everything": "read"}, "models"):
        with pytest.raises(ValueError):
            ma.clean_scopes(bad)


def test_who_manages_what():
    assert ma.can_manage_all(["it-admin"]) and ma.can_manage_all(["super-admin"]) and not ma.can_manage_all(["user", "model-creator"])
    with pytest.raises(PermissionError):
        ma._check_roles(["super-admin"], ["it-admin"])                    # never more than the maker's roles
    with pytest.raises(ValueError):
        ma._check_roles(["user-admin"], ["super-admin"])                  # not a role a service account takes
    assert ma._check_roles(["user", "model-creator"], ["it-admin"]) == ["model-creator", "user"]


def test_areas_list_the_routes_in_each():
    out = ma.areas([(["GET"], "/api/v1/models/<model_id>/reports/"), (["POST"], "/api/v1/sql/query"), (["GET"], "/api/health")])
    by = {a["code"]: a for a in out}
    assert [a["code"] for a in out] == ma.AREA_CODES
    assert by["reports"]["endpoints"] == [{"methods": ["GET"], "path": "/api/v1/models/<model_id>/reports/"}]
    assert by["administration"]["endpoints"][0]["path"] == "/api/v1/sql/query"


def test_expiry_limits():
    assert all(ma.DEFAULT_DAYS[k] <= ma.MAX_DAYS[k] for k in ma.KINDS)
    assert ma._dt("2026-11-10T08:00:00") == datetime(2026, 11, 10, 8, tzinfo=UTC)
    assert ma._dt(datetime(2026, 1, 1)) .tzinfo is not None
    assert ma._dt(datetime.now(UTC) + timedelta(days=1)) > datetime.now(UTC)


# ---------------------------------------------------------------- wiring
def test_the_migration_holds_rows_only():
    sql = (ROOT / "migrations" / "sql" / "0036_machine_access_ops.sql").read_text()
    assert "'0.17.0'" in sql and "0036_machine_access_ops" in sql and "ON CONFLICT (version) DO NOTHING" in sql
    body = sql.upper().replace("DO $$", "")
    for word in ("TRIGGER", "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", "POLICY"):
        assert word not in body, word                                      # D248: no logic in the database
    for t in ("service_accounts", "machine_credentials", "usage_daily", "retention_rules", "housekeeping_runs", "archived_items"):
        assert f"CREATE TABLE core.{t}" in sql
    py = (ROOT / "migrations" / "versions" / "0036_machine_access_ops.py").read_text()
    assert 'revision = "0036_machine_access_ops"' in py and "0036_machine_access_ops.sql" in py


def test_every_sign_in_path_takes_credentials():
    auth = (ROOT / "eax" / "auth.py").read_text()
    assert "ma.presented(request.headers, bearer)" in auth and "machine.refusal(request.method, request.path)" in auth
    mcp = (ROOT / "eax" / "mcp_server.py").read_text()
    assert "_authenticate_machine" in mcp and 'scopes", {}).get("mcp") != "read-write"' in mcp
    app = (ROOT / "eax" / "app.py").read_text()
    assert "machine_access.note_use" in app and "operations.count_call" in app and '"/api/metrics"' in app


def test_the_proxy_asks_for_certificates_on_its_own_port_only():
    tpl = (REPO / "deploy" / "proxy" / "templates" / "default.conf.template").read_text()
    main, mtls = tpl.split("listen 9443 ssl;")
    assert "ssl_verify_client" not in main                                 # browsers are never asked for a certificate
    assert "ssl_verify_client optional_no_ca;" in mtls and mtls.count("X-EAX-Client-Cert $ssl_client_escaped_cert") == 2
    # everywhere else the header is cleared, so nobody can send one of their own
    assert 'proxy_set_header X-EAX-Client-Cert "";' in main.split("server {")[0]
    for block in main.split("location ")[1:]:
        if "proxy_set_header X-Forwarded-For" in block:
            assert 'X-EAX-Client-Cert "";' in block, block[:40]
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    assert "${EAX_MTLS_PORT:-9443}:9443" in compose["services"]["proxy"]["ports"]
    assert compose["services"]["proxy"]["environment"]["EAX_MTLS_PORT"] == "${EAX_MTLS_PORT:-9443}"
    for env in ("eaexplorer.laptop.env", "eaexplorer.server.env"):
        assert "EAX_MTLS_PORT=9443" in (REPO / "deploy" / "templates" / env).read_text()


def test_credential_calls_go_to_the_change_log():
    from eax import change_log as cl
    for a in ("machine.call", "machine.credential.create", "machine.credential.revoke", "machine.service_account.create",
              "housekeeping.rule", "housekeeping.confirm", "housekeeping.run"):
        assert a in cl.ACTIONS


def test_the_sample_keeps_no_usable_secret():
    src = (ROOT / "eax" / "seed" / "sample_machine_ops.py").read_text()
    assert "ma.new_secret(kind)" in src and "ma.hash_secret(secret)" in src
    assert "eaxt_" not in src and "eaxk_" not in src and "BEGIN PRIVATE KEY" not in src
    assert "sample_machine_ops" in (ROOT / "eax" / "seed" / "later.py").read_text()


def test_the_odata_feed_takes_a_token_as_its_password():
    assert ma.odata_check("anyone", "not-a-secret") is None              # Keycloak is asked instead
    app = (ROOT / "eax" / "app.py").read_text()
    assert "_oa.CHECKS.append(_ma.odata_check)" in app
