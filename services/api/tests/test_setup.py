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


def test_site_certificate_is_signed_by_the_local_ca(tmp_path):
    """D107: a local CA signs the site certificate; its key is not kept; it may vouch only for our names."""
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import padding
    ensure_certificate(tmp_path, "eax.example.test")
    ca = x509.load_pem_x509_certificate((tmp_path / "ca.crt").read_bytes())
    site = x509.load_pem_x509_certificates((tmp_path / "tls.crt").read_bytes())[0]
    ca.public_key().verify(site.signature, site.tbs_certificate_bytes, padding.PKCS1v15(), site.signature_hash_algorithm)
    assert site.issuer == ca.subject
    sans = site.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    assert {"eax.example.test", "reports.eax.example.test", "docs.eax.example.test", "localhost"} <= set(sans)
    nc = ca.extensions.get_extension_for_class(x509.NameConstraints).value
    assert {g.value for g in nc.permitted_subtrees if isinstance(g, x509.DNSName)} == {"eax.example.test", "localhost"}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ca.crt", "tls.crt", "tls.key"]   # no CA key on disk


def test_certificate_is_remade_for_a_new_host_but_an_organisations_own_is_left(tmp_path):
    ensure_certificate(tmp_path, "localhost")
    assert ensure_certificate(tmp_path, "eax.example.test") is True    # ours, for another host: remade
    own = tmp_path / "own"
    own.mkdir()
    ensure_certificate(own, "localhost")
    (own / "ca.crt").unlink()
    import datetime as dt

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.oid.NameOID.ORGANIZATION_NAME, "Fynbos Mutual")])
    now = dt.datetime.now(dt.UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + dt.timedelta(days=5)).sign(k, hashes.SHA256()))
    (own / "tls.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    assert ensure_certificate(own, "eax.example.test") is False   # an organisation's own: never touched


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
    monkeypatch.setenv("EAX_KEYCLOAK_REALM", "acme-ea")   # chosen at the first install
    assert json.loads(setup.render_realm(setup.derived_values()).read_text())["realm"] == "acme-ea"
    assert not [p for p in setup.check_config() if "EAX_KEYCLOAK_REALM" in p]
    for bad in ("master", "Acme", "1ea", "a"):
        monkeypatch.setenv("EAX_KEYCLOAK_REALM", bad)
        assert [p for p in setup.check_config() if "EAX_KEYCLOAK_REALM" in p], bad
    monkeypatch.setenv("EAX_KEYCLOAK_REALM", "eaexplorer")
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
