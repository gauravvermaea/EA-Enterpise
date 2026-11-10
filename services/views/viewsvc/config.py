"""The views service's settings, from the environment (work/eaexplorer.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    superuser_password: str        # only to make the database and its login when they are missing
    api_url: str                   # the main API, inside the network: who someone is, their rights on a model, entity checks
    internal_key: str              # the main API's key for /internal (tags, copies, merges, packages, MCP, sample data)
    keep_versions: int             # 0: every version; n: the last n of each view (never one a tag holds)
    deployment: str

    def dsn(self, user: str | None = None, password: str | None = None, db: str | None = None) -> str:
        return (f"host={self.db_host} port={self.db_port} dbname={db or self.db_name} user={user or self.db_user} "
                f"password={password if password is not None else self.db_password}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    e = os.environ.get
    laptop = e("EAX_DEPLOYMENT", "laptop") == "laptop"
    # a config file made before the views service (0.16.0) has no views settings: on a laptop they fall back to the main
    # database password and the laptop key; a server must set its own (setup refuses the laptop key there)
    return Settings(
        db_host=e("EAX_VIEWS_DB_HOST", e("EAX_DB_HOST", "db")),
        db_port=int(e("EAX_VIEWS_DB_PORT", e("EAX_DB_PORT", "5432"))),
        db_name=e("EAX_VIEWS_DB_NAME", "eaxviews"),
        db_user=e("EAX_VIEWS_DB_USER", "eax_views"),
        db_password=e("EAX_VIEWS_DB_PASSWORD") or (e("EAX_DB_PASSWORD", "") if laptop else ""),
        superuser_password=e("EAX_DB_SUPERUSER_PASSWORD", ""),
        api_url=e("EAX_API_INTERNAL_URL", "http://api:8000").rstrip("/"),
        internal_key=e("EAX_VIEWS_KEY") or ("eax-views-laptop" if laptop else ""),
        keep_versions=max(0, int(e("EAX_VIEWS_KEEP_VERSIONS", "0") or 0)),
        deployment=e("EAX_DEPLOYMENT", "laptop"),
    )
