"""Mayan EDMS, the document store behind the project repositories (phase 13, D260).

EA Explorer keeps the rules and the screens; Mayan keeps the files: each project is a cabinet with a cabinet per folder,
each document a Mayan document with its versions (files), and a check-out in EA Explorer is also a check-out in Mayan.
EA Explorer talks to Mayan's REST API (v4) inside the Docker network (http://dms:8000) as one service account, Mayan's
own administrator (EAX_MAYAN_ADMIN_USER), with an API token; the person who acted is kept by EA Explorer
(proj.document_events) and written into Mayan's comments. Project roles are not copied into Mayan.

The token: Mayan signs people in through Keycloak, so its administrator has no password sign-in for the API; EA Explorer
reads (or makes) the administrator's API token in Mayan's own database (`mayan`, Mayan's login, EAX_MAYAN_DB_PASSWORD),
once, and keeps it in memory.

Every call raises MayanError with a plain message when Mayan is off, still starting or refuses: the caller shows it and
the repository is built when Mayan is up (the repository job retries).
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .config import get_settings

BASE = os.environ.get("EAX_MAYAN_URL", "http://dms:8000").rstrip("/")
API = BASE + "/api/v4"
TIMEOUT = 60
_lock = threading.Lock()
_token: dict = {"key": None}


class MayanError(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


def enabled() -> bool:
    from . import services
    return services.enabled("documents")


def _db_token() -> str:
    """The administrator's API token, read or made in Mayan's database."""
    import psycopg
    s = get_settings()
    user = os.environ.get("EAX_MAYAN_ADMIN_USER", "admin")
    pw = os.environ.get("EAX_MAYAN_DB_PASSWORD", "")
    info = (f"host={s.db_host} port={s.db_port} dbname={os.environ.get('EAX_MAYAN_DB_NAME', 'mayan')} "
            f"user={os.environ.get('EAX_MAYAN_DB_USER', 'mayan')} password='{pw.replace(chr(92), chr(92) * 2).replace(chr(39), chr(92) + chr(39))}' "
            "connect_timeout=5")
    try:
        with psycopg.connect(info, autocommit=True) as conn:
            row = conn.execute("SELECT id FROM auth_user WHERE username = %s", (user,)).fetchone()
            if not row:
                raise MayanError(f"Mayan has no administrator '{user}' yet: it is still setting itself up.")
            tok = conn.execute("SELECT key FROM authtoken_token WHERE user_id = %s", (row[0],)).fetchone()
            if tok:
                return tok[0]
            key = secrets.token_hex(20)
            conn.execute("INSERT INTO authtoken_token (key, created, user_id) VALUES (%s, now(), %s)", (key, row[0]))
            return key
    except MayanError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise MayanError(f"Documents (Mayan) cannot be reached yet: {str(exc).splitlines()[0][:200]}") from exc


def _key() -> str:
    with _lock:
        if not _token["key"]:
            _token["key"] = _db_token()
        return _token["key"]


def _request(method: str, path: str, *, data: bytes | None = None, ctype: str | None = None, raw: bool = False,
             timeout: int = TIMEOUT):
    if not enabled():
        raise MayanError("Documents (Mayan) are switched off (Administration > System settings > Services).", 409)
    url = path if path.startswith("http") else API + path
    headers = {"Authorization": f"Token {_key()}", "Accept": "application/json"}
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if raw:
                return body, r.headers.get("Content-Type", "application/octet-stream")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        text = exc.read()[:500].decode(errors="replace")
        if exc.code == 401:
            _token["key"] = None   # read the token again next time
        raise MayanError(f"Mayan refused {method} {path.split('?')[0]}: HTTP {exc.code} {text}", 502) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MayanError(f"Documents (Mayan) cannot be reached: {exc}") from exc


def _json(method: str, path: str, body: dict | None = None):
    return _request(method, path, data=json.dumps(body or {}).encode() if body is not None else None,
                    ctype="application/json" if body is not None else None)


def _multipart(fields: dict, file_name: str, content: bytes, ctype: str = "application/octet-stream") -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    safe = file_name.replace('"', "'")
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n").encode() + content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def ping() -> bool:
    try:
        _json("GET", "/document_types/?page_size=1")
        return True
    except MayanError:
        return False


# ---------------------------------------------------------------- cabinets (folders)
def cabinet(label: str, parent: int | None = None) -> int:
    """The cabinet with this label under `parent` (made when missing); returns its id."""
    label = label[:128]
    page = f"/cabinets/?page_size=500&label={urllib.parse.quote(label)}"
    for c in _json("GET", page).get("results", []):
        pid = c.get("parent_id")
        if pid is None and isinstance(c.get("parent"), int):
            pid = c["parent"]
        if c.get("label") == label and pid == parent:
            return c["id"]
    body = {"label": label}
    if parent:
        body["parent"] = parent
    return _json("POST", "/cabinets/", body)["id"]


def cabinet_path(path: str, root: int) -> int:
    """Cabinets for every part of a folder path under the project's cabinet; returns the last one's id."""
    cid = root
    for part in [p for p in path.split("/") if p]:
        cid = cabinet(part, cid)
    return cid


def add_to_cabinet(cabinet_id: int, document_id: int) -> None:
    _json("POST", f"/cabinets/{cabinet_id}/documents/add/", {"document": document_id})


# ---------------------------------------------------------------- documents and versions
_doc_type: dict = {"id": None}


def document_type() -> int:
    """The document type EA Explorer files under: 'EA Explorer project document' (made when missing)."""
    if _doc_type["id"]:
        return _doc_type["id"]
    label = "EA Explorer project document"
    for t in _json("GET", "/document_types/?page_size=200").get("results", []):
        if t.get("label") == label:
            _doc_type["id"] = t["id"]
            return t["id"]
    _doc_type["id"] = _json("POST", "/document_types/", {"label": label})["id"]
    return _doc_type["id"]


def upload(file_name: str, content: bytes, ctype: str = "application/octet-stream", label: str | None = None) -> dict:
    """A new document; returns {id, file_id}."""
    body, ct = _multipart({"document_type_id": document_type(), "label": label or file_name}, file_name, content, ctype)
    doc = _request("POST", "/documents/upload/", data=body, ctype=ct, timeout=300)
    return {"id": doc.get("id"), "file_id": (doc.get("file_latest") or {}).get("id")}


def new_version(document_id: int, file_name: str, content: bytes, comment: str, ctype: str = "application/octet-stream") -> None:
    """A new file (version) of a document; the latest is the current one."""
    body, ct = _multipart({"action_name": "replace", "comment": comment[:250]}, file_name, content, ctype)
    _request("POST", f"/documents/{document_id}/files/", data=body, ctype=ct, timeout=300)


def latest(document_id: int) -> dict:
    d = _json("GET", f"/documents/{document_id}/")
    f = d.get("file_latest") or {}
    return {"file_id": f.get("id"), "file_name": f.get("filename") or d.get("label"), "label": d.get("label")}


def download(document_id: int) -> tuple[bytes, str, str]:
    """The latest version's bytes, content type and file name."""
    f = latest(document_id)
    if not f["file_id"]:
        raise MayanError("The document has no file in Mayan.", 404)
    content, ctype = _request("GET", f"/documents/{document_id}/files/{f['file_id']}/download/", raw=True, timeout=300)
    return content, ctype, f["file_name"] or "document"


def check_out(document_id: int, hours: int = 24 * 30) -> None:
    from datetime import UTC, datetime, timedelta
    until = (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
    _json("POST", f"/documents/{document_id}/checkout/", {"expiration_datetime": until, "block_new_file": True})


def check_in(document_id: int) -> None:
    try:
        _request("DELETE", f"/documents/{document_id}/checkout/")
    except MayanError as exc:
        if exc.status != 502 or "404" not in str(exc):
            raise


def tag(document_id: int, label: str, color: str = "#999999") -> None:
    tid = None
    for t in _json("GET", f"/tags/?page_size=200&label={urllib.parse.quote(label)}").get("results", []):
        if t.get("label") == label:
            tid = t["id"]
    if not tid:
        tid = _json("POST", "/tags/", {"label": label, "color": color})["id"]
    _json("POST", f"/documents/{document_id}/tags/attach/", {"tag": tid})


def web_link(document_id: int) -> str:
    """Where the document is in Mayan's own screens (docs.<host>)."""
    s = get_settings()
    port = "" if str(s.https_port) == "443" else f":{s.https_port}"
    return f"https://docs.{s.hostname}{port}/#/documents/documents/{document_id}/preview/"
