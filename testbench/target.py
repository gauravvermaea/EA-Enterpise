"""The target and the safety guard (D579): the test bench never runs against an installation unless the person says,
every time, that it is theirs: --target <address> --i-own-this (or EAX_TESTBENCH_I_OWN_THIS=<host> in CI). It makes
fixtures there (self_test_<id>_<n>) and, with --reset-survival, really wipes it."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse


class GuardError(Exception):
    pass


def clean(target: str) -> str:
    t = (target or "").strip().rstrip("/")
    if not t:
        raise GuardError("No target: give --target https://<host> (the EA Explorer address you sign in on).")
    if "://" not in t:
        t = "https://" + t
    u = urlparse(t)
    if u.scheme not in ("https", "http") or not u.hostname:
        raise GuardError(f"Not an address: {target}")
    if u.path not in ("", "/"):
        raise GuardError(f"Give the installation's address without a path: {u.scheme}://{u.netloc}")
    return f"{u.scheme}://{u.netloc}"


def host_of(target: str) -> str:
    return urlparse(target).hostname or ""


def check_owned(target: str, i_own_this: bool, env: dict | None = None) -> str:
    """The guard: the flag, or EAX_TESTBENCH_I_OWN_THIS set to this host (CI). Returns the host."""
    env = os.environ if env is None else env
    host = host_of(target)
    if i_own_this:
        return host
    if (env.get("EAX_TESTBENCH_I_OWN_THIS") or "").strip().lower() == host.lower():
        return host
    raise GuardError(f"The test bench makes test data on {host} (and some tests change it). Run it only against an "
                     f"installation you own: add --i-own-this (or set EAX_TESTBENCH_I_OWN_THIS={host} in CI).")


class Client:
    """The target's API with a Super Admin or IT Admin token (a machine-access token, D438): JSON in, JSON out."""

    def __init__(self, target: str, token: str = "", timeout: int = 60):
        self.target, self.token, self.timeout = target, token, timeout

    def call(self, method: str, path: str, body: dict | None = None, timeout: int | None = None) -> tuple[int, dict | str]:
        data = json.dumps(body).encode() if body is not None else (b"{}" if method.upper() in ("POST", "PUT") else None)
        req = urllib.request.Request(self.target + path, data=data, method=method.upper(),
                                     headers={"Content-Type": "application/json", "Accept": "application/json",
                                              **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                raw, status = r.read().decode("utf-8", "replace"), r.status
        except urllib.error.HTTPError as exc:
            raw, status = exc.read().decode("utf-8", "replace"), exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 599, f"no answer: {exc}"
        try:
            return status, json.loads(raw) if raw else {}
        except ValueError:
            return status, raw[:2000]

    def get(self, path: str, **kw):
        return self.call("GET", path, **kw)

    def post(self, path: str, body: dict | None = None, **kw):
        return self.call("POST", path, body, **kw)


def message(answer) -> str:
    return answer.get("message", "") if isinstance(answer, dict) else str(answer)[:300]


def password_token(target: str, user: str, password: str, realm: str = "eaexplorer", client: str = "eax-odata",
                   timeout: int = 30) -> str:
    """A Keycloak user's token, by the password grant of the realm's eax-odata client (the only client that allows it,
    D433; its tokens are for the API, with the person's own roles). Raises GuardError with why."""
    from urllib.parse import urlencode  # noqa: PLC0415
    url = f"{target}/auth/realms/{realm}/protocol/openid-connect/token"
    data = urlencode({"grant_type": "password", "client_id": client, "username": user, "password": password}).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())["access_token"]
    except urllib.error.HTTPError as exc:
        why = exc.read().decode("utf-8", "replace")[:300]
        raise GuardError(f"Keycloak refused {user} ({exc.code}): {why}") from None
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        raise GuardError(f"Could not sign in as {user} at {url}: {exc}") from None


def credentials(path: str) -> dict:
    """A credentials file (testbench/data/credentials.template.json, copied and filled in; never committed):
    {"token": "...", "user": "...", "password": "...", "realm": "eaexplorer", "client": "eax-odata"}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, str)}
