"""Self-signed certificate for laptops and first starts (replace with a real one on servers)."""

from __future__ import annotations

import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def ensure_certificate(folder: Path, hostname: str) -> bool:
    """Create tls.crt and tls.key in `folder` unless both exist. Returns True if created."""
    crt, key = folder / "tls.crt", folder / "tls.key"
    if crt.exists() and key.exists():
        return False
    folder.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    names = sorted({hostname, f"reports.{hostname}", f"docs.{hostname}", "localhost"})
    sans: list[x509.GeneralName] = [x509.DNSName(n) for n in names]
    sans.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EA Explorer (self-signed)"),
    ])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )
    key.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key.chmod(0o644)  # read by the nginx worker inside the proxy container only
    return True
