"""The SQL window says what each database, schema and table is for (owner, 13 Nov 2026: "In the SQL tab do the same for
databases and schemas etc in them"; D650)."""

from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1]
WEB = API.parent / "web" / "src"


def test_every_schema_and_database_of_ours_has_a_line():
    from eax import databases, sqlconsole
    for schema in databases.SCHEMAS.values():
        assert sqlconsole.ABOUT_SCHEMAS.get(schema), schema
    for s in ("core", "proj", "history", "changelog", "audit", "rpt", "staging", "jobs", "public"):
        assert sqlconsole.ABOUT_SCHEMAS.get(s), s
    for d in ("eaexplorer", "keycloak", "superset", "mayan", "eaxlibrary", "eaxviews"):
        assert sqlconsole.ABOUT_DATABASES.get(d), d


def test_a_comment_reads_as_plain_words():
    from eax import sqlconsole
    assert sqlconsole.plain("R2.41: archived and deleted models") == "Archived and deleted models"
    assert sqlconsole.plain("When backups run") == "When backups run"
    assert sqlconsole.about_schema("somebody_else", "D630: theirs; more") == "Theirs"


def test_every_table_gets_its_line_from_the_migration_or_already_had_one():
    sql = (API / "migrations" / "sql" / "0064_about_tables.sql").read_text()
    tables = re.findall(r"\('([a-z_]+\.[a-z_]+)', '", sql)
    assert len(tables) >= 120 and "core.entities" in tables and "proj.projects" in tables
    assert "obj_description(to_regclass(r.tbl), 'pg_class') IS NULL" in sql      # an existing comment is kept
    assert "TRIGGER" not in sql.upper()


def test_the_window_shows_them():
    web = (WEB / "Sql.jsx").read_text()
    assert "tree-about" in web and "dbAbout" in web and "o.about" in web and "s.about" in web
    assert '"about": {d: sqlconsole.ABOUT_DATABASES.get(d, "") for d in dbs}' in (API / "eax" / "api" / "sql.py").read_text()


def test_setting_up_an_environment_is_on_the_start_page_and_in_the_documentation():
    """Owner, 13 Nov 2026: the commands for laptop, server and the other environments in the README, "add them to the
    home page" (both: a card on the Start page and the guide in Documentation)."""
    repo = API.parents[1]
    doc = (repo / "docs" / "setting-up.md").read_text()
    for cmd in (".\\eax clean-run", ".\\eax init laptop", "./eax.sh init server", ".\\eax deploy --kind server",
                "EAX_PLATFORM=managed"):
        assert cmd in doc, cmd
    assert "### Setting up the environment: laptop, server, cloud" in (repo / "README.md").read_text()
    start = (WEB / "StartPage.jsx").read_text()
    assert "<SetUpCard />" in start and "#/documentation/setting-up" in start
    from eax import shipped_docs
    assert "setting-up" in [k for k, _ in shipped_docs._sources(repo)]
