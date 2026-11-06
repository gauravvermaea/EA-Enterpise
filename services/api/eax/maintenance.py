"""Read-only maintenance while a backup is restored (phase 8.4, D216).

The operations helper writes work/maintenance.json (mounted read-only at /eax-work) when a restore starts and removes it
when it ends; the API refuses every change meanwhile and the heartbeat says so, so the screens show a banner.
"""

from __future__ import annotations

import json
import os


def path() -> str:
    return os.path.join(os.environ.get("EAX_WORK_MOUNT", "/eax-work"), "maintenance.json")


def state() -> dict | None:
    try:
        with open(path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
