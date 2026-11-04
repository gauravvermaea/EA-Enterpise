"""API and database versions."""

import tomllib
from pathlib import Path

import eax
from eax import versioning


def test_version_comes_from_version_toml():
    data = tomllib.loads((Path(eax.__file__).resolve().parent.parent / "version.toml").read_text())
    assert eax.__version__ == data["version"]
    assert eax.__version__.count(".") == 2


def test_matching_versions_give_no_warning():
    assert versioning.version_warning(eax.__version__) is None


def test_mismatch_and_unknown_are_warnings():
    assert "Version mismatch" in versioning.version_warning("0.1.0")
    assert "unknown" in versioning.version_warning(None)


def test_latest_migration_records_the_api_version():
    sql = (Path(eax.__file__).resolve().parent.parent / "migrations" / "sql").glob("*.sql")
    recorded = [line for f in sql for line in f.read_text().splitlines() if f"('{eax.__version__}'," in line]
    assert recorded, f"no migration writes version {eax.__version__} to core.schema_versions"
