"""Settings, all read from the environment (filled from eaexplorer.env by Docker Compose)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import quote


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _conninfo_quote(value: str) -> str:
    """Quote a value for a libpq key=value connection string (handles spaces, quotes, backslashes)."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def public_url(host: str, port: str, prefix: str = "") -> str:
    """https URL for a host, leaving out the port when it is the default 443."""
    host = f"{prefix}{host}"
    return f"https://{host}" if port in ("", "443") else f"https://{host}:{port}"


@dataclass(frozen=True)
class Settings:
    version: str = field(default_factory=lambda: _env("EAX_VERSION", "dev"))
    deployment: str = field(default_factory=lambda: _env("EAX_DEPLOYMENT", "laptop"))
    hostname: str = field(default_factory=lambda: _env("EAX_HOSTNAME", "localhost"))
    https_port: str = field(default_factory=lambda: _env("EAX_HTTPS_PORT", "443"))

    db_host: str = field(default_factory=lambda: _env("EAX_DB_HOST", "db"))
    db_port: str = field(default_factory=lambda: _env("EAX_DB_PORT", "5432"))
    db_name: str = field(default_factory=lambda: _env("EAX_DB_NAME", "eaexplorer"))
    db_user: str = field(default_factory=lambda: _env("EAX_DB_USER", "eax_app"))
    db_password: str = field(default_factory=lambda: _env("EAX_DB_PASSWORD"))

    keycloak_internal_url: str = field(
        default_factory=lambda: _env("EAX_KEYCLOAK_INTERNAL_URL", "http://keycloak:8080/auth")
    )
    realm: str = field(default_factory=lambda: _env("EAX_KEYCLOAK_REALM", "eaexplorer"))
    api_audience: str = field(default_factory=lambda: _env("EAX_API_AUDIENCE", "eax-api"))

    @property
    def public_base_url(self) -> str:
        return public_url(self.hostname, self.https_port)

    @property
    def sqlalchemy_url(self) -> str:
        return (
            # user and password are URL-encoded: passwords may hold characters such as ^ & @ $
            f"postgresql+psycopg://{quote(self.db_user, safe='')}:{quote(self.db_password, safe='')}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def libpq_conninfo(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={_conninfo_quote(self.db_user)} password={_conninfo_quote(self.db_password)}"
        )

    @property
    def jwks_url(self) -> str:
        return f"{self.keycloak_internal_url}/realms/{self.realm}/protocol/openid-connect/certs"

    @property
    def accepted_issuers(self) -> list[str]:
        """Keycloak may write the issuer with or without the default port."""
        base = f"https://{self.hostname}"
        issuers = {
            f"{public_url(self.hostname, self.https_port)}/auth/realms/{self.realm}",
            f"{base}:{self.https_port}/auth/realms/{self.realm}",
        }
        return sorted(issuers)


def get_settings() -> Settings:
    return Settings()
