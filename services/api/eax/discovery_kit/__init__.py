"""The Python kit of a Push source (R3 discovery, D674; owner, 14 Nov 2026: "a .py file + a bunch of CSV's that someone
can download from the discovery page with some sample data ... users can look at python code and decide how it will
work. Keep the code as simple as possible ... focus on oData calling").

The kit is downloaded from the model's Discovery tab as a zip:
  push_to_eax.py     the script (this folder, the same for every source): push_dataframe(url, df, username, password)
  requirements.txt   pandas and requests
  README.md          setting up a venv, running it, what happens next; this source's Push address filled in
  samples/*.csv      sample records made from the model's own metamodel (owner, 14 Nov 2026: "The samples need to show how
                     relations will be published ... sheets for all existing entities"): a file for every entity type,
                     each with a relationship column the metamodel allows (named after the relationship type, holding
                     ids from the related type's file), named so a push maps them by itself

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
SAMPLE_ROWS = 2                    # records in each sample file
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


def usable_types(types: list[dict]) -> tuple[list[dict], list[dict]]:
    """(the types with a sample file, the types left out): a type is left out when a set named after it would be read
    as another type (eax.discovery.suggest picks by name)."""
    ok = [t for t in types if maps_to_itself(t, types)]
    return sorted(ok, key=lambda t: t["name"].lower()), sorted((t for t in types if t not in ok), key=lambda t: t["name"].lower())


def links(types: list[dict], allowed: list[dict]) -> dict[str, dict]:
    """For each type with a sample file, the relationship its sample shows: {source code: {relationship, relationship
    name, target}}, one the metamodel allows to another type with a sample file; Serving first and the catch-all
    Association last, then a target with nothing pointing at it yet, so as many types as possible appear at both ends."""
    usable = {t["code"]: t for t in usable_types(types)[0]}
    out: dict[str, dict] = {}
    pointed: dict[str, int] = {}
    by_source: dict[str, list[dict]] = {}
    for a in allowed:
        if a["source"] in usable and a["target"] in usable and a["source"] != a["target"]:
            by_source.setdefault(a["source"], []).append(a)
    for code in usable:
        options = by_source.get(code) or []
        if not options:
            continue
        best = min(options, key=lambda a: (a["relationship_name"].lower() != "serving",
                                           a["relationship_name"].lower() == "association", pointed.get(a["target"], 0),
                                           _rank(usable[a["target"]]["name"]), usable[a["target"]]["name"].lower(),
                                           a["relationship_name"].lower()))
        out[code] = {"relationship": best["relationship"], "relationship_name": best["relationship_name"], "target": best["target"]}
        pointed[best["target"]] = pointed.get(best["target"], 0) + 1
    return out


def _rank(name: str) -> int:
    return TARGETS.index(name.lower()) if name.lower() in TARGETS else len(TARGETS)


def sample_id(t: dict, i: int) -> str:
    """A record's id in the samples: the type's code and a number, so no two files share an id and a link column can
    only ever point at the type it means."""
    return f"{t['code']}-{i}"


def _csv(header: list[str], rows: list[list[str]]) -> str:
    s = io.StringIO()
    w = csv.writer(s, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return s.getvalue()


def samples(types: list[dict], allowed: list[dict]) -> dict[str, str]:
    """{file name: CSV text}: a file for every entity type of the model (that a push maps back to itself), each with
    SAMPLE_ROWS records: id, name, description, the type's attributes (left empty) and, where the metamodel allows one,
    a relationship column named after the relationship type holding the ids of records in the related type's file."""
    ok, _left = usable_types(types)
    by_code = {t["code"]: t for t in ok}
    rel = links(types, allowed)
    out = {}
    for t in ok:
        attrs = [a["name"] for a in t.get("attributes") or []][:ATTRIBUTE_COLUMNS]
        link = rel.get(t["code"])
        header = ["id", "name", "description", *attrs, *([link["relationship_name"]] if link else [])]
        rows = []
        for i in range(1, SAMPLE_ROWS + 1):
            target = [sample_id(by_code[link["target"]], (i - 1) % SAMPLE_ROWS + 1)] if link else []
            rows.append([sample_id(t, i), f"Sample {t['name']} {i}", f"A sample {t['name'].lower()} pushed with Python",
                         *[""] * len(attrs), *target])
        out[f"{file_name(t['name'])}.csv"] = _csv(header, rows)
    return out


def example_text(types: list[dict], allowed: list[dict]) -> str:
    """One relationship of the samples spelt out for the README (an application component's first, if there is one)."""
    ok, _left = usable_types(types)
    by_code = {t["code"]: t for t in ok}
    found = links(types, allowed)
    if not found:
        return "This model's samples have no relationship: its metamodel allows none between their types."
    code = next((c for c in found if by_code[c]["name"].lower().startswith("application")), next(iter(found)))
    link, s, t = found[code], by_code[code], by_code[found[code]["target"]]
    verb = link["relationship_name"].lower()
    return (f"For example, in the samples `{file_name(s['name'])}.csv` has a `{link['relationship_name']}` column whose first row "
            f"holds `{sample_id(t, 1)}`: once the delivery is accepted, *Sample {s['name']} 1* has a {verb} relationship to "
            f"*Sample {t['name']} 1*.")


def relationships_text(types: list[dict], allowed: list[dict]) -> str:
    """The README's list of the relationships the samples publish, one line each, and the types left out."""
    ok, left = usable_types(types)
    by_code = {t["code"]: t for t in ok}
    lines = []
    for code, link in links(types, allowed).items():
        s, t = by_code[code], by_code[link["target"]]
        lines.append(f"| `{file_name(s['name'])}.csv` | `{link['relationship_name']}` | {s['name']} "
                     f"*{link['relationship_name'].lower()}* {t['name']} | `{sample_id(t, 1)}` in `{file_name(t['name'])}.csv` |")
    table = ("| File | Column | Relationship published | Its values are ids such as |\n| --- | --- | --- | --- |\n" + "\n".join(lines)
             if lines else "The metamodel allows no relationship between these types, so the samples have none.")
    if left:
        table += ("\n\nNo sample file for " + ", ".join(t["name"] for t in left)
                  + ": a set named after it would be read as another type (name the set with the type's code instead).")
    return table


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


def readme(src: dict, m: dict, base: str, types: list[dict] | None = None, allowed: list[dict] | None = None) -> str:
    return (text_of("README.md").replace("{push_url}", push_url(src, base)).replace("{model}", m["name"])
            .replace("{source}", src["name"]).replace("{relationships}", relationships_text(types or [], allowed or []))
            .replace("{example}", example_text(types or [], allowed or [])))


def code(conn, user, source: Any, base: str) -> dict:
    """What the Discovery tab shows to copy: the script, its requirements, the command and the sample files' names."""
    src, m = _source(conn, user, source)
    types, allowed = _metamodel(conn, m)
    url = push_url(src, base)
    return {"script": text_of("push_to_eax.py"), "requirements": text_of("requirements.txt"), "push_url": url,
            "command": f"python push_to_eax.py --url {url} --user <your user name>",
            "samples": samples(types, allowed), "relationships": relationships_text(types, allowed),
            "zip": f"{kit_name(m, src)}.zip"}


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
        z.writestr(f"{name}/README.md", readme(src, m, base, types, allowed))
        for fname, body in samples(types, allowed).items():
            z.writestr(f"{name}/samples/{fname}", body)
    return f"{name}.zip", buf.getvalue()
