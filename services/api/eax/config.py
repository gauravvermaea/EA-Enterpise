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
    # the installer's login: loads and changes locked reference models (seed step only)
    db_migrator_user: str = field(default_factory=lambda: _env("EAX_DB_MIGRATOR_USER", "eax_migrator"))
    db_migrator_password: str = field(default_factory=lambda: _env("EAX_DB_MIGRATOR_PASSWORD"))

    # phase 9 (D180): the change log has a connection string of its own, so it can live on another server; empty
    # means the repository's database (development: its own schema there)
    changelog_db_url: str = field(default_factory=lambda: _env("EAX_CHANGELOG_DB_URL"))
    changelog_db_schema: str = field(default_factory=lambda: _env("EAX_CHANGELOG_DB_SCHEMA", "changelog"))

    keycloak_internal_url: str = field(
        default_factory=lambda: _env("EAX_KEYCLOAK_INTERNAL_URL", "http://keycloak:8080/auth")
    )
    realm: str = field(default_factory=lambda: _env("EAX_KEYCLOAK_REALM", "eaexplorer"))
    api_audience: str = field(default_factory=lambda: _env("EAX_API_AUDIENCE", "eax-api"))
    # phase 3.1: the API's own Keycloak client (service account) for reading users and roles
    admin_client_id: str = field(default_factory=lambda: _env("EAX_KC_SERVICE_CLIENT", "eax-admin"))
    admin_client_secret: str = field(default_factory=lambda: _env("EAX_KC_SERVICE_SECRET"))
    # phase 3.1: the break-glass account's password (D80); empty turns break-glass sign-in off
    break_glass_password: str = field(default_factory=lambda: _env("EAX_BREAK_GLASS_PASSWORD"))

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
    def changelog_sqlalchemy_url(self) -> str:
        """The change log's database: EAX_CHANGELOG_DB_URL (postgresql://user:password@host:port/database), or the
        repository's database when it is empty."""
        url = self.changelog_db_url
        if not url:
            return self.sqlalchemy_url
        for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def libpq_conninfo(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={_conninfo_quote(self.db_user)} password={_conninfo_quote(self.db_password)}"
        )

    @property
    def migrator_conninfo(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={_conninfo_quote(self.db_migrator_user)} password={_conninfo_quote(self.db_migrator_password)}"
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
