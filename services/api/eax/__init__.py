"""EA Explorer API."""

import tomllib
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "version.toml"


def _read_version() -> str:
    """The version from version.toml (kept with the code, so the image always carries it)."""
    try:
        return tomllib.loads(_VERSION_FILE.read_text(encoding="utf-8"))["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "unknown"


__version__ = _read_version()
