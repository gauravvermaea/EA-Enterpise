"""Database engine (SQLAlchemy 2, psycopg 3)."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from . import permissions
from .config import get_settings


def get_engine() -> Engine:
    """The repository's engine; inside a library model's request, task or tool (R2.42, D633) the library engine, whose
    statements read the library model's content from the library_models schema (eax/library_models.py)."""
    from . import library_models
    if library_models.routed():
        return library_models.engine()
    return base_engine()


@lru_cache(maxsize=1)
def base_engine() -> Engine:
    """The repository's own engine, whatever the route."""
    settings = get_settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 3, "application_name": "eaexplorer-api"},
    )

    @event.listens_for(engine, "checkout")
    def _who_is_asking(dbapi_connection, _record, _proxy):
        """Tell the database who is asking (phase 3.1): the signed-in user and their EA Explorer roles.
        Row-level security and the permission triggers use these (migrations/sql/0006_roles.sql).
        With nobody signed in (the job runner, the seed) both are empty and nothing is restricted:
        every route that serves people requires sign-in first."""
        who = permissions.current.get()
        with dbapi_connection.cursor() as cur:
            cur.execute("SELECT set_config('eax.actor', %s, false), set_config('eax.user_roles', %s, false)",
                        (who.username if who else "",
                         # a signed-in person with no EA Explorer role gets "none", never "" (which means no user)
                         (",".join(who.roles) or "none") if who else ""))
        dbapi_connection.commit()

    @event.listens_for(engine, "checkin")
    def _discard_temp(dbapi_connection, _record):
        """A pooled connection goes back clean: no temporary tables (eax.get_entity) and no user carry over."""
        try:
            dbapi_connection.rollback()
            with dbapi_connection.cursor() as cur:
                cur.execute("DISCARD TEMP")
                cur.execute("SELECT set_config('eax.actor', '', false), set_config('eax.user_roles', '', false)")
            dbapi_connection.commit()
        except Exception:  # a broken connection is replaced by the pool anyway
            pass

    return engine


@lru_cache(maxsize=1)
def installer_engine() -> Engine:
    """The installer's engine (the migrations' login): the application's own work on read-only (locked) models, which
    the database allows only to the installer, such as moving a library model's content (R2.42, D633). Small pool."""
    return create_engine(get_settings().migrator_sqlalchemy_url, pool_pre_ping=True, pool_size=1, max_overflow=1,
                         connect_args={"connect_timeout": 5, "application_name": "eaexplorer-installer"})


@lru_cache(maxsize=1)
def get_changelog_engine() -> Engine:
    """The change log's own database (phase 9, D180): EAX_CHANGELOG_DB_URL, or the repository's database when it is
    empty. No user identity is set on it: who sees which rows is decided in eax/change_log.py."""
    settings = get_settings()
    return create_engine(settings.changelog_sqlalchemy_url, pool_pre_ping=True, pool_size=2, max_overflow=3,
                         connect_args={"connect_timeout": 5, "application_name": "eaexplorer-changelog"})


def projects_separate() -> bool:
    """True when the architecture projects (schema proj) live in a database of their own (EAX_PROJECTS_DB_URL, D266)."""
    return bool(get_settings().projects_db_url)


@lru_cache(maxsize=1)
def get_projects_engine() -> Engine:
    """The architecture projects' database (schema proj, D266): EAX_PROJECTS_DB_URL, or the repository's engine when it
    is empty (one database, one transaction). eax/projects.py never joins proj with another schema; what it needs from
    the repository (models, views, model roles, notifications) goes through the repository connection."""
    if not projects_separate():
        return base_engine()
    return create_engine(get_settings().projects_sqlalchemy_url, pool_pre_ping=True, pool_size=3, max_overflow=5,
                         connect_args={"connect_timeout": 5, "application_name": "eaexplorer-projects"})
