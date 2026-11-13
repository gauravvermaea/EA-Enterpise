"""System Admin › Estate (R2.33): the logical diagram and the physical one of the running installation, from docker
inspect of its containers (eaxcli/estate.py draws both)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.environ.get("EAX_REPO_MOUNT", "/eax-repo"))
try:
    from eaxcli import estate as E
except Exception:  # noqa: BLE001 - an older compose file without the eaxcli mount
    E = None

hooks: dict = {}       # set by ops.py: containers, docker


def live() -> dict:
    if E is None:
        raise RuntimeError("The estate needs eaxcli mounted into the operations helper (docker-compose.yml).")
    ids = [c["id"] for c in hooks["containers"]()]
    items = E.from_inspect(json.loads(hooks["docker"]("inspect", *ids, timeout=60) or "[]")) if ids else []
    ln, le = E.logical()
    pn, pe = E.physical(items)
    return {"logical": {"nodes": ln, "edges": le}, "physical": {"nodes": pn, "edges": pe}, "containers": items}
