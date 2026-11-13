"""Remote EA Explorer instances (R2.2, D634; owner, 10 Nov 2026, 22:25-22:28; answers 12 Nov 2026, 21:42 and 13 Nov 2026,
08:41-08:47).

* Each person keeps their own list (the personal schema, R2.53): a name and the instance's address, and, for a Super
  Admin, how to reach its host by SSH. The site picker at the top left shows ● Local and the list; choosing one opens
  that instance's own screens in a new tab, where the person signs in its own way and works with the role they have
  there. Nothing is carried over from here.
* A Super Admin may open an SSH session to the instance's host from the browser (through the operations helper, which
  holds the session and records it: operations.ssh_sessions and work/ssh-sessions/<session>.log).
* How a person proves who they are to the host is a configuration option, EAX_REMOTE_SSH_AUTH in eaexplorer.env:
    ask         (default) asked each time: the host's password prompt, or a private key pasted for that session only;
                nothing is kept
    stored      each person's private key kept with their instance, encrypted with EAX_REMOTE_SECRET_KEY
    server_key  this installation's own SSH key (its public part shown, to put on the remote host); people handle no key
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Any

from . import personal as P
from .metamodel_edit import EditError

MODES = ("ask", "stored", "server_key")
_URL = re.compile(r"^https?://[^\s/]+[^\s]*$")
_HOST = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")
_USER = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
FIELDS = "guid AS id, name, url, note, ssh_host, ssh_port, ssh_user, (ssh_key_enc IS NOT NULL) AS has_key, created_at, modified_at"


def auth_mode() -> str:
    v = (os.environ.get("EAX_REMOTE_SSH_AUTH") or "ask").strip().lower()
    return v if v in MODES else "ask"


def _fernet():
    from .config import _env
    secret = _env("EAX_REMOTE_SECRET_KEY")          # the environment, or a Docker secret (R2.44)
    if len(secret) < 16:
        raise EditError("Keeping keys needs EAX_REMOTE_SECRET_KEY (16 characters or more) in the config file.", 409)
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encrypt(text_: str) -> bytes:
    return _fernet().encrypt(text_.encode())


def decrypt(blob: bytes) -> str:
    return _fernet().decrypt(bytes(blob)).decode()


def _clean(d: dict, partial: bool = False) -> dict:
    out: dict[str, Any] = {}
    if not partial or "name" in d:
        name = str(d.get("name") or "").strip()
        if not name or len(name) > 120:
            raise EditError("Give the instance a name (up to 120 characters).")
        out["name"] = name
    if not partial or "url" in d:
        url = str(d.get("url") or "").strip().rstrip("/")
        if not _URL.match(url) or len(url) > 500:
            raise EditError("The address is the instance's web address, for example https://ea.example.com.")
        out["url"] = url
    if "note" in d:
        out["note"] = str(d.get("note") or "")[:2000]
    if "ssh_host" in d:
        h = str(d.get("ssh_host") or "").strip()
        if h and not _HOST.match(h):
            raise EditError("The SSH host is a host name or address.")
        out["ssh_host"] = h
    if "ssh_port" in d:
        try:
            port = int(d.get("ssh_port") or 22)
        except (TypeError, ValueError) as exc:
            raise EditError("The SSH port is a number from 1 to 65535.") from exc
        if not 1 <= port <= 65535:
            raise EditError("The SSH port is a number from 1 to 65535.")
        out["ssh_port"] = port
    if "ssh_user" in d:
        u = str(d.get("ssh_user") or "").strip()
        if u and not _USER.match(u):
            raise EditError("The SSH user is letters, digits, dots, dashes or underscores.")
        out["ssh_user"] = u
    return out


def listing(conn, username: str) -> dict:
    return {"items": P.rows(conn, f"SELECT {FIELDS} FROM personal.remote_instances WHERE username = lower(:u) ORDER BY lower(name)",
                            u=username),
            "ssh_auth": auth_mode()}


def _mine(conn, username: str, ident) -> dict:
    r = P.one(conn, "SELECT * FROM personal.remote_instances WHERE guid = CAST(:g AS uuid) AND username = lower(:u)",
              g=str(ident), u=username)
    if not r:
        raise EditError("No such instance in your list.", 404)
    return r


def create(conn, username: str, d: dict) -> dict:
    v = _clean(d)
    v.update({k: x for k, x in _clean({k: d[k] for k in ("ssh_host", "ssh_port", "ssh_user", "note") if k in d}, True).items()})
    if P.one(conn, "SELECT 1 AS x FROM personal.remote_instances WHERE username = lower(:u) AND lower(name) = lower(:n)",
             u=username, n=v["name"]):
        raise EditError(f"You already have an instance called {v['name']}.", 409)
    cols = ["username", *v.keys()]
    key = _key_blob(d)
    if key is not None:
        cols.append("ssh_key_enc")
    params = {"username": username.lower(), **v, **({"ssh_key_enc": key} if key is not None else {})}
    g = P.run(conn, f"INSERT INTO personal.remote_instances ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) "
              "RETURNING guid", **params).scalar_one()
    return get(conn, username, g)


def _key_blob(d: dict):
    """A private key given to keep (stored mode only); '' clears it; absent: unchanged (None)."""
    if "ssh_key" not in d:
        return None
    k = str(d.get("ssh_key") or "").strip()
    if not k:
        return b""
    if auth_mode() != "stored":
        raise EditError("Keys are kept only when EAX_REMOTE_SSH_AUTH=stored; with 'ask' you give it when you connect.", 409)
    if "PRIVATE KEY" not in k or len(k) > 20000:
        raise EditError("Paste the whole private key (the lines between BEGIN and END ... PRIVATE KEY).")
    return encrypt(k + "\n")


def get(conn, username: str, ident) -> dict:
    r = P.one(conn, f"SELECT {FIELDS} FROM personal.remote_instances WHERE guid = CAST(:g AS uuid) AND username = lower(:u)",
              g=str(ident), u=username)
    if not r:
        raise EditError("No such instance in your list.", 404)
    return r


def update(conn, username: str, ident, d: dict) -> dict:
    cur = _mine(conn, username, ident)
    v = _clean(d, partial=True)
    key = _key_blob(d)
    if key is not None:
        v["ssh_key_enc"] = key or None
    if not v:
        return get(conn, username, cur["guid"])
    sets = ", ".join(f"{k} = :{k}" for k in v)
    P.run(conn, f"UPDATE personal.remote_instances SET {sets}, modified_at = now() WHERE id = :i", i=cur["id"], **v)
    return get(conn, username, cur["guid"])


def delete(conn, username: str, ident) -> dict:
    cur = _mine(conn, username, ident)
    P.run(conn, "DELETE FROM personal.remote_instances WHERE id = :i", i=cur["id"])
    return {"deleted": str(cur["guid"])}


def ssh_request(conn, user, ident, d: dict) -> dict:
    """What the operations helper needs to open the SSH session (Super Admins only): host, port, user and, by the
    configured mode, the key given now (ask), the kept key (stored) or the installation's own key (server_key)."""
    if "super-admin" not in (getattr(user, "roles", ()) or ()):
        raise EditError("Only a Super Admin opens an SSH session to a remote instance's host.", 403)
    inst = _mine(conn, user.username, ident)
    if not inst["ssh_host"] or not inst["ssh_user"]:
        raise EditError(f"Give {inst['name']} its SSH host and user first.", 409)
    mode, key = auth_mode(), ""
    if mode == "ask":
        key = str(d.get("ssh_key") or "").strip()
        if key and "PRIVATE KEY" not in key:
            raise EditError("Paste the whole private key, or leave it empty to type the host's password.")
    elif mode == "stored":
        if not inst["ssh_key_enc"]:
            raise EditError(f"Keep your private key with {inst['name']} first (EAX_REMOTE_SSH_AUTH=stored).", 409)
        key = decrypt(inst["ssh_key_enc"])
    return {"host": inst["ssh_host"], "port": int(inst["ssh_port"]), "ssh_user": inst["ssh_user"], "auth": mode,
            "key": key, "instance": inst["name"], "user": user.username,
            "cols": int(d.get("cols") or 120), "rows": int(d.get("rows") or 32)}
