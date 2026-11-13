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


def build() -> dict:
    """The build this API runs (R2.47): the commit's short id, or the CI build number, set by eax when it builds and
    starts the stack (EAX_BUILD; "dev" when not known, "-changed" when built from files not yet committed), when it was
    built (EAX_BUILT_AT) and the update channel."""
    import os
    return {"build": os.environ.get("EAX_BUILD", "").strip() or "dev",
            "built_at": os.environ.get("EAX_BUILT_AT", "").strip() or None,
            "commit": os.environ.get("EAX_COMMIT", "").strip() or None,
            "channel": os.environ.get("EAX_UPDATE_CHANNEL", "").strip() or None,
            # where it runs (R2.44, D635): compose (a laptop or server with Docker) or managed (a platform, no socket)
            "platform": "managed" if os.environ.get("EAX_PLATFORM", "").strip().lower() in ("managed", "swarm", "kubernetes", "platform")
            else "compose",
            "file_store": "database" if os.environ.get("EAX_FILE_STORE", "").strip().lower() == "database" else "folder"}
