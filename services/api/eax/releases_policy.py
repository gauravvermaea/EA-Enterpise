"""The supported-versions policy (8.5, D515) for the API: the same rules as eaxcli/releases.py (the updater and eax
deploy), which the API image does not carry; tests/test_updates.py checks the two agree.

Supported: the newest release line (X.Y) and the one before; a release candidate only until its release is out.
"""

from __future__ import annotations

import re

TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?$")


def parse(version: str) -> tuple[int, int, int, int, int] | None:
    """'0.19.0' or 'v0.19.0-rc.2' -> a key that sorts versions: a release sorts after its RCs. None if not a version."""
    m = TAG.match(version if version.startswith("v") else f"v{version}")
    if not m:
        return None
    major, minor, patch, rc = m.groups()
    return (int(major), int(minor), int(patch), 0 if rc else 1, int(rc or 0))


def base(version: str) -> str:
    """'0.19.0-rc.2' -> '0.19.0'."""
    return version.lstrip("v").split("-")[0]


def is_rc(version: str) -> bool:
    return "-rc." in version


def newer(a: str, b: str) -> bool:
    """Is version a newer than version b? (unknown versions are never newer)"""
    ka, kb = parse(a), parse(b)
    return bool(ka and kb and ka > kb)


def supported(installed: str, releases: list[str]) -> tuple[bool, str]:
    """The supported-versions policy (docs/release-process.md): the newest release line (X.Y) and the one before are
    supported; a release candidate or a Latest build only until its release is out."""
    finals = sorted({base(r) for r in releases if not is_rc(r) and parse(r)}, key=parse)
    if not finals or not parse(installed):
        return True, ""
    lines = []
    for f in reversed(finals):
        line = ".".join(f.split(".")[:2])
        if line not in lines:
            lines.append(line)
    keep = lines[:2]
    mine = ".".join(base(installed).split(".")[:2])
    if is_rc(installed) and base(installed) in finals:
        return False, f"{installed} is a release candidate of {base(installed)}, which is now released: update to it."
    if mine in keep or newer(installed, finals[-1]):
        return True, ""
    return False, (f"{installed} is no longer supported: the supported release lines are {', '.join(keep)}. "
                   f"Update to {finals[-1]}.")
