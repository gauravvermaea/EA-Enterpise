"""The Python kit of a Push source (R3 discovery, D674; owner, 14 Nov 2026: "a .py file + a bunch of CSV's that someone
can download from the discovery page with some sample data ... users can look at python code and decide how it will
work. Keep the code as simple as possible ... focus on oData calling").

The kit is downloaded from the model's Discovery tab as a zip:
  push_to_eax.py     the script (this folder, the same for every source): push_dataframe(url, df, username, password)
  requirements.txt   pandas and requests
  README.md          setting up a venv, running it, what happens next; this source's Push address filled in
  samples/*.csv      sample records made from the model's own metamodel: two entity types joined by a relationship the
                     metamodel allows, named so a push maps them by itself (the file's name is the type's name, the
                     link column the relationship type's name)

The push endpoint takes a user name and password (HTTP Basic, as the OData feed, D433: an EA Explorer or directory
account), as well as every machine credential (phase 25): a personal token (the way for single sign-on users), a
service account's API key, a client certificate on the machine-access port. The script's sign_in() shows each
(owner, 14 Nov 2026: "People can also use other mechanisms like SSO, AD, keys, certs as well for auth")."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Any

from .. import discovery as dc
from .. import repository as repo
from ..metamodel_edit import EditError

HERE = Path(__file__).parent
FILES = ("push_to_eax.py", "requirements.txt", "README.md")
ATTRIBUTE_COLUMNS = 6              # the type's attributes shown as (empty) columns in a sample, at most
SAMPLE_ROWS = (3, 2)               # records of the first type, of the related type
TARGETS = ("business process", "process", "business function", "business service")   # the related type, best first


def text_of(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def file_name(type_name: str) -> str:
    """A type's name as a file name (the set's name a push maps back to the type)."""
    return re.sub(r'[\\/:*?"<>|]+', "-", type_name).strip(" .") or "records"


def maps_to_itself(t: dict, types: list[dict]) -> bool:
    """A push of a set named after this type would be mapped to this very type (as eax.discovery.suggest does)."""
    stem = dc.singular(file_name(t["name"]))
    best = max(types, key=lambda x: dc.type_score(stem, x), default=None)
    return best is not None and best["code"] == t["code"] and dc.type_score(stem, t) >= 0.8


def choose(types: list[dict], allowed: list[dict]) -> tuple[dict | None, dict | None, dict | None]:
    """The two types and the relationship type of the samples: an allowed relationship between two types a push maps by
    name, application components serving something first; else one type alone."""
    usable = {t["code"]: t for t in types if maps_to_itself(t, types)}
    pairs = [a for a in allowed if a["source"] in usable and a["target"] in usable and a["source"] != a["target"]]
    pairs.sort(key=lambda a: (not usable[a["source"]]["name"].lower().startswith("application"),
                              a["relationship_name"].lower() != "serving", _rank(usable[a["target"]]["name"]),
                              usable[a["source"]]["name"], usable[a["target"]]["name"]))
    if pairs:
        a = pairs[0]
        return usable[a["source"]], usable[a["target"]], {"code": a["relationship"], "name": a["relationship_name"]}
    first = sorted(usable.values(), key=lambda t: (not t["name"].lower().startswith("application"), t["name"]))
    return (first[0] if first else None), None, None


def _rank(name: str) -> int:
    return TARGETS.index(name.lower()) if name.lower() in TARGETS else len(TARGETS)


def _prefix(name: str) -> str:
    return "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", name)).upper()[:4] or "R"


def _csv(header: list[str], rows: list[list[str]]) -> str:
    s = io.StringIO()
    w = csv.writer(s, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return s.getvalue()


def samples(types: list[dict], allowed: list[dict]) -> dict[str, str]:
    """{file name: CSV text}: sample records of the chosen types (id, name, description, the type's attributes left
    empty, and the relationship column holding the related records' ids)."""
    first, second, rel = choose(types, allowed)
    if first is None:
        return {}
    out = {}
    ids2 = []
    if second is not None:
        p2 = _prefix(second["name"])
        ids2 = [f"{p2}-{i}" for i in range(1, SAMPLE_ROWS[1] + 1)]
        attrs2 = [a["name"] for a in second.get("attributes") or []][:ATTRIBUTE_COLUMNS]
        rows2 = [[k, f"Sample {second['name']} {i}", f"A sample {second['name'].lower()} pushed with Python", *[""] * len(attrs2)]
                 for i, k in enumerate(ids2, 1)]
        out[f"{file_name(second['name'])}.csv"] = _csv(["id", "name", "description", *attrs2], rows2)
    p1 = _prefix(first["name"])
    attrs1 = [a["name"] for a in first.get("attributes") or []][:ATTRIBUTE_COLUMNS]
    header = ["id", "name", "description", *attrs1, *([rel["name"]] if rel else [])]
    rows1 = []
    for i in range(1, SAMPLE_ROWS[0] + 1):
        link = [ids2[(i - 1) % len(ids2)]] if rel else []
        rows1.append([f"{p1}-{i}", f"Sample {first['name']} {i}", f"A sample {first['name'].lower()} pushed with Python",
                      *[""] * len(attrs1), *link])
    out[f"{file_name(first['name'])}.csv"] = _csv(header, rows1)
    return dict(sorted(out.items()))


def _metamodel(conn, m: dict) -> tuple[list[dict], list[dict]]:
    types, _rts = dc._types(conn, m)
    allowed = repo._rows(conn, """SELECT s.code AS source, t.code AS target, rt.code AS relationship, rt.name AS relationship_name
                                    FROM core.allowed_relationships a
                                    JOIN core.relationship_types rt ON rt.id = a.relationship_type_id AND NOT rt.is_deleted
                                    JOIN core.entity_types s ON s.id = a.source_type_id AND NOT s.is_deleted
                                    JOIN core.entity_types t ON t.id = a.target_type_id AND NOT t.is_deleted
                                   WHERE a.model_id = :m AND NOT a.is_deleted""", m=m["_id"])
    return list(types.values()), allowed


def _source(conn, user, source: Any) -> tuple[dict, dict]:
    from .. import deliveries as dv
    src = dv._source(conn, source)
    m = repo.get_model(conn, str(src["model_guid"]))
    dc._may_write(conn, user, m)
    if src["kind"] != "push":
        raise EditError(f"{src['name']} is not a push source: the Python kit is for push sources.", 409)
    return src, m


def push_url(src: dict, base: str) -> str:
    return f"{base.rstrip('/')}/api/v1/import-sources/{src['guid']}/push"


def readme(src: dict, m: dict, base: str) -> str:
    return (text_of("README.md").replace("{push_url}", push_url(src, base)).replace("{model}", m["name"])
            .replace("{source}", src["name"]))


def code(conn, user, source: Any, base: str) -> dict:
    """What the Discovery tab shows to copy: the script, its requirements, the command and the sample files' names."""
    src, m = _source(conn, user, source)
    types, allowed = _metamodel(conn, m)
    url = push_url(src, base)
    return {"script": text_of("push_to_eax.py"), "requirements": text_of("requirements.txt"), "push_url": url,
            "command": f"python push_to_eax.py --url {url} --user <your user name>",
            "samples": samples(types, allowed), "zip": f"{kit_name(m, src)}.zip"}


def kit_name(m: dict, src: dict) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{m['name']} {src['name']}").strip("-").lower()[:60]
    return f"eax-push-{slug or 'kit'}"


def kit(conn, user, source: Any, base: str) -> tuple[str, bytes]:
    """The kit as a zip: (file name, bytes); everything inside one folder of the kit's name."""
    src, m = _source(conn, user, source)
    types, allowed = _metamodel(conn, m)
    name = kit_name(m, src)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{name}/push_to_eax.py", text_of("push_to_eax.py"))
        z.writestr(f"{name}/requirements.txt", text_of("requirements.txt"))
        z.writestr(f"{name}/README.md", readme(src, m, base))
        for fname, body in samples(types, allowed).items():
            z.writestr(f"{name}/samples/{fname}", body)
    return f"{name}.zip", buf.getvalue()
