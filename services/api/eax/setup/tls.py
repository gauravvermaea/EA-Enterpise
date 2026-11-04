"""The certificate for laptops and first starts (replace it with your organisation's on servers), D107.

EA Explorer makes a small local certificate authority (CA) and signs the site certificate with it:
  ca.crt   the local CA, which `eax trust` adds to the computer's trusted certificates (and which MCP
           clients that run on Node are pointed at with NODE_EXTRA_CA_CERTS);
  tls.crt  the site certificate for EAX_HOSTNAME, reports.<host>, docs.<host>, localhost and 127.0.0.1;
  tls.key  its private key, read by nginx.
The CA's own private key is thrown away once the site certificate is signed, and the CA may only vouch
for this installation's names (name constraints), so trusting it cannot be used to fake any other site.
A new certificate therefore means a new CA, trusted again with `eax trust`.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ORG = "EA Explorer (self-signed)"
CA_NAME = "EA Explorer local CA"
DAYS = 825


def _names(hostname: str) -> list[str]:
    return sorted({hostname, f"reports.{hostname}", f"docs.{hostname}", "localhost"})


def _ours(cert: x509.Certificate) -> bool:
    """True for a certificate EA Explorer made (never touch an organisation's own)."""
    orgs = [a.value for a in cert.issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)]
    return ORG in orgs


def _needs_new(folder: Path, hostname: str) -> bool:
    crt, key, ca = folder / "tls.crt", folder / "tls.key", folder / "ca.crt"
    if not (crt.exists() and key.exists()):
        return True
    try:
        cert = x509.load_pem_x509_certificate(crt.read_bytes())
    except ValueError:
        return False                       # not ours to judge: leave it
    if not _ours(cert):
        return False                       # an organisation's own certificate
    if not ca.exists():
        return True                        # an older self-signed one, before the local CA
    try:
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        return True
    soon = dt.datetime.now(dt.UTC) + dt.timedelta(days=30)
    return hostname not in sans or cert.not_valid_after_utc < soon


def ensure_certificate(folder: Path, hostname: str) -> bool:
    """Make ca.crt, tls.crt and tls.key in `folder` when there is no certificate, or when EA Explorer's
    own one is from before the local CA, is for another host name or runs out within 30 days.
    Returns True if they were made."""
    if not _needs_new(folder, hostname):
        return False
    folder.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.UTC)
    names = _names(hostname)

    # the local CA: may sign only for this installation's names
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"{CA_NAME} ({hostname}, {now:%Y-%m-%d})"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORG),
    ])
    permitted: list[x509.GeneralName] = [x509.DNSName(n) for n in sorted({hostname, "localhost"})]
    permitted.append(x509.IPAddress(ipaddress.ip_network("127.0.0.1/32")))
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.NameConstraints(permitted_subtrees=permitted, excluded_subtrees=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    # the site certificate, signed by the CA
    site_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sans: list[x509.GeneralName] = [x509.DNSName(n) for n in names]
    sans.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    site = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORG),
        ]))
        .issuer_name(ca_subject)
        .public_key(site_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=DAYS))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(site_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    del ca_key  # never written anywhere

    pem = serialization.Encoding.PEM
    (folder / "tls.key").write_bytes(site_key.private_bytes(pem, serialization.PrivateFormat.TraditionalOpenSSL,
                                                            serialization.NoEncryption()))
    # nginx serves the site certificate followed by the CA, so clients that are given only the CA can build the chain
    (folder / "tls.crt").write_bytes(site.public_bytes(pem) + ca_cert.public_bytes(pem))
    (folder / "ca.crt").write_bytes(ca_cert.public_bytes(pem))
    (folder / "tls.key").chmod(0o644)  # read by the nginx worker inside the proxy container only
    return True
