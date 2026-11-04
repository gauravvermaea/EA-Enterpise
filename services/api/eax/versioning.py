"""The API and the database carry the same version.

The API's version is in version.toml (eax.__version__). The database's is the newest row of
core.schema_versions, written by the migration that moves it. They must be equal; the heartbeat and
the service health check show a warning when they are not.
"""

from __future__ import annotations

from sqlalchemy import text

from . import __version__


def database_version(conn) -> str | None:
    """The database's version (core.schema_version()), or None before migration 0003."""
    if not conn.execute(text("SELECT to_regprocedure('core.schema_version()')")).scalar():
        return None
    return conn.execute(text("SELECT core.schema_version()")).scalar()


def version_warning(db_version: str | None) -> str | None:
    """A message when the API and the database are at different versions, else None."""
    if db_version == __version__:
        return None
    return (f"Version mismatch: API {__version__}, database {db_version or 'unknown'}. "
            "The database migrations have not run for this API version, or the API image is older "
            "than the database. Rebuild (eax clean-run) or check the api container's log.")
