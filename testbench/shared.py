"""The thin adapter to the self-test's own tests (services/api/eax/testing/): they are imported, never copied (D580).

The shared modules read a few settings from the environment when they run inside (the API by its Docker name, the
front door through the proxy container). point_at(target) sets them to the target's public address before any test
runs, so the same code talks to the installation from outside."""

from __future__ import annotations

import os
import ssl
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # the repository (or an installation folder: it holds both)
API_SRC = ROOT / "services" / "api"
DATA = Path(__file__).resolve().parent / "data"


def _path() -> None:
    if str(API_SRC) not in sys.path:
        sys.path.insert(0, str(API_SRC))


def testing():
    """The self-test package: api_matrix, api_writes, db_checks, security, ui_flows, ui_pages, run, store."""
    _path()
    import eax.testing as t  # noqa: PLC0415
    return t


def module(name: str):
    _path()
    import importlib  # noqa: PLC0415
    return importlib.import_module(f"eax.testing.{name}")


def insecure() -> None:
    """--insecure: a laptop's own certificate is not trusted by this machine: do not check it (every HTTPS call)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx)))
    ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001 - opt-in, for self-signed laptops


def point_at(target: str) -> dict[str, str]:
    """Points the shared tests at the target from outside: the API, the library, the browser's address and the front
    door are all the public address. Returns what was set (shown in the run's log)."""
    host = target.split("//", 1)[1].split("/")[0].split(":")[0]
    env = {
        "EAX_TEST_API_URL": target,              # run.API, api_matrix/api_writes calls
        "EAX_TEST_LIBRARY_URL": target,          # the library's API through the front door
        "EAX_TEST_BASE_URL": target,             # ui_journeys.base_url
        "EAX_TEST_PROXY_HOST": host,             # the browser's host mapping: the host itself (no mapping)
        "EAX_TEST_PROXY": target,                # security.front_door
        "EAX_HOSTNAME": host,
    }
    os.environ.update(env)
    run = module("run")
    run.API = target                             # read once at import time inside the module
    return env
