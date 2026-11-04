import json
import zipfile

import yaml

from eax.setup import __main__ as setup
from eax.setup.superset_sample import build_sample_bundle
from eax.setup.tls import ensure_certificate

REPO = __import__("pathlib").Path(__file__).resolve().parents[3]


def test_certificate_is_created_once(tmp_path):
    assert ensure_certificate(tmp_path, "localhost") is True
    assert (tmp_path / "tls.crt").read_bytes().startswith(b"-----BEGIN CERTIFICATE")
    assert ensure_certificate(tmp_path, "localhost") is False


def test_realm_renders_to_valid_json(tmp_path, monkeypatch):
    for line in (REPO / "deploy/templates/eaexplorer.laptop.env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            monkeypatch.setenv(k, v.strip().strip("'\""))
    monkeypatch.setenv("EAX_FIRST_ADMIN_PASSWORD", 'pa"ss\\word')  # must be escaped
    monkeypatch.setattr(setup, "DEPLOY", REPO / "deploy")
    monkeypatch.setattr(setup, "KC_IMPORT", tmp_path)
    out = setup.render_realm(setup.derived_values())
    realm = json.loads(out.read_text())
    assert realm["realm"] == "eaexplorer"
    web = next(c for c in realm["clients"] if c["clientId"] == "eax-web")
    assert "https://localhost/*" in web["redirectUris"]
    assert realm["users"][0]["credentials"][0]["value"] == 'pa"ss\\word'
    assert realm["users"][0]["credentials"][0]["temporary"] is False  # laptop template


def test_dev_password_is_url_encoded(monkeypatch):
    from eax.config import Settings

    monkeypatch.setenv("EAX_DB_PASSWORD", "P^55w0rd1234&")
    monkeypatch.setenv("EAX_DB_HOST", "db")    # conftest points tests at a closed port
    monkeypatch.setenv("EAX_DB_PORT", "5432")
    s = Settings()
    assert "P%5E55w0rd1234%26@db:5432" in s.sqlalchemy_url
    assert "password='P^55w0rd1234&'" in s.libpq_conninfo


def test_laptop_template_passes_checks_with_warnings(monkeypatch):
    for line in (REPO / "deploy/templates/eaexplorer.laptop.env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            monkeypatch.setenv(k, v.strip().strip("'\""))
    assert setup.check_config() == []
    monkeypatch.setenv("EAX_DEPLOYMENT", "server")
    assert setup.check_config()  # the development password is refused on a server


def test_superset_bundle(tmp_path):
    out = build_sample_bundle(tmp_path, db_password="secret")
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "eax_phase0_sample/metadata.yaml" in names
        db = yaml.safe_load(zf.read("eax_phase0_sample/databases/EA_Explorer_reports.yaml"))
    assert db["sqlalchemy_uri"].startswith("postgresql+psycopg2://eax_report:secret@db")
