"""KPI trends (phase 24, D365, D430, D431).

A standard set of KPIs per model, plus a Model Admin's own KPIs (a count or a sum over one entity type, with one filter),
kept as snapshots:

* monthly: on the 1st of each month (the job runner checks every hour, so a month missed while the server was off is
  taken when it is back, dated the 1st of that month); a model's first snapshot is taken in the month it is first seen;
* on every tag: when a model is tagged (eax.tags.create_tag), the KPIs as they are at that moment, named after the tag.

Shown as trends on the model page (with the value now, worked out live) and in Superset (report KR-01 over
rpt.kpi_trends). Snapshots read the committed content only (never anyone's uncommitted changes), like the reports.
The rules are here (D248): the database only keeps the rows (migrations/sql/0035_kpi_reports.sql).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from . import repository as repo
from .metamodel_edit import EditError


def _maps(res) -> list[dict]:
    return [dict(r) for r in res.mappings()]

# ---------------------------------------------------------------- the standard set (D431)
STANDARD: list[dict[str, str]] = [
    {"code": "entities", "name": "Entities", "unit": "",
     "about": "How many entities the model holds (junctions are not counted)."},
    {"code": "entities_by_type", "name": "Entities by type", "unit": "",
     "about": "How many entities of each entity type."},
    {"code": "applications_by_time", "name": "Applications by TIME", "unit": "",
     "about": "Applications by their TIME classification (Tolerate, Invest, Migrate, Eliminate; Not set when empty)."},
    {"code": "applications_by_lifecycle", "name": "Applications by lifecycle", "unit": "",
     "about": "Applications by lifecycle (Not set when empty)."},
    {"code": "total_cost", "name": "Total annual cost", "unit": "cost",
     "about": "The annual cost of every entity that has one, added up."},
    {"code": "quality_score", "name": "Data quality score", "unit": "%",
     "about": "The model's data quality score at the time (its latest measurement); empty when never measured."},
    {"code": "orphans", "name": "Orphans", "unit": "",
     "about": "Entities with no relationship, no parent and no children."},
    {"code": "eol_technology", "name": "Technology past end of life", "unit": "",
     "about": "Technology whose end of life (or end of support, or retirement) date has passed."},
    {"code": "eol_technology_soon", "name": "Technology reaching end of life within 12 months", "unit": "",
     "about": "Technology whose end of life falls in the next twelve months."},
]
STANDARD_BY_CODE = {k["code"]: k for k in STANDARD}

# the standard roles the reports use (rpt.std_roles, D140), lower case
APPLICATION_TYPES = {"applicationcomponent", "application"}
TECHNOLOGY_TYPES = {"node", "systemsoftware", "device", "platform", "equipment", "facility", "communicationnetwork"}
TIME_ATTRS = ("timeclassification", "time")
LIFECYCLE_ATTRS = ("lifecycle",)
COST_ATTRS = ("annualcost", "cost")
EOL_ATTRS = ("endoflife", "endofsupport", "retirementdate")
NOT_SET = "Not set"

# ---------------------------------------------------------------- a Model Admin's own KPIs (D432)
KINDS = {"count": "Count of entities", "sum": "Sum of a number attribute"}
OPS = {"": "No filter", "equals": "is", "not-equals": "is not", "contains": "contains", "empty": "is empty",
       "not-empty": "is not empty", "more-than": "is more than", "less-than": "is less than"}
NUMBER_TYPES = {"integer", "decimal", "currency", "percent"}


# ---------------------------------------------------------------- the model's data, read once
def load(conn, model_id: int) -> dict[str, Any]:
    """The committed entities of a model with their attribute values and how they are linked: what the KPIs are worked
    out from. Read past row-level security (the job runner and the seed have no person; a person's call has already
    checked they may read the model)."""
    conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
    try:
        ents = _maps(conn.execute(text("""
            SELECT e.id, e.guid::text AS guid, e.name, e.parent_entity_id AS parent, t.code AS type_code, t.name AS type_name
              FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
             WHERE e.model_id = :m AND NOT e.is_deleted AND NOT t.is_connector"""), {"m": model_id}))
        vals = _maps(conn.execute(text("""
            SELECT v.entity_id, lower(a.code) AS attr, a.data_type_code AS data_type, v.value_text, v.value_number, v.value_date,
                   v.value_bool, r.name AS value_ref
              FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
              LEFT JOIN core.entities r ON r.id = v.value_ref
             WHERE v.model_id = :m AND NOT v.is_deleted AND v.entity_id IS NOT NULL"""), {"m": model_id}))
        linked = {r["e"] for r in conn.execute(text("""
            SELECT source_entity_id AS e FROM core.relationships WHERE model_id = :m AND NOT is_deleted
            UNION SELECT target_entity_id FROM core.relationships WHERE model_id = :m AND NOT is_deleted"""), {"m": model_id}).mappings()}
        quality = conn.execute(text("SELECT score FROM core.quality_runs WHERE model_id = :m ORDER BY run_at DESC LIMIT 1"),
                               {"m": model_id}).scalar()
    finally:
        conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
    return {"entities": ents, "values": vals, "linked": linked, "quality": quality}


def _display(v: dict) -> str:
    if v.get("value_text") is not None:
        return str(v["value_text"])
    if v.get("value_number") is not None:
        n = Decimal(str(v["value_number"]))
        return format(n.normalize(), "f") if n == n.to_integral() else str(n)
    if v.get("value_date") is not None:
        return str(v["value_date"])
    if v.get("value_bool") is not None:
        return "Yes" if v["value_bool"] else "No"
    return str(v.get("value_ref") or "")


def _by_entity(values: list[dict]) -> dict[int, dict[str, dict]]:
    out: dict[int, dict[str, dict]] = {}
    for v in values:
        out.setdefault(v["entity_id"], {}).setdefault(v["attr"], v)
    return out


def _first(attrs: dict[str, dict], codes: tuple[str, ...]) -> dict | None:
    for c in codes:
        if c in attrs:
            return attrs[c]
    return None


def _num(v: dict | None) -> Decimal | None:
    if not v:
        return None
    if v.get("value_number") is not None:
        return Decimal(str(v["value_number"]))
    try:
        return Decimal(str(v.get("value_text")).replace(",", "").strip()) if v.get("value_text") not in (None, "") else None
    except Exception:  # noqa: BLE001 - text that is not a number is not counted
        return None


def _date(v: dict | None) -> date | None:
    if not v:
        return None
    if v.get("value_date") is not None:
        d = v["value_date"]
        return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
    try:
        return date.fromisoformat(str(v.get("value_text") or "")[:10])
    except ValueError:
        return None


def standard_values(data: dict[str, Any], today: date | None = None) -> list[tuple[str, str, Decimal | None]]:
    """The standard KPIs of a model's data: [(code, dimension, value)]; dimension '' for a single number."""
    today = today or datetime.now(UTC).date()
    ents, attrs = data["entities"], _by_entity(data["values"])
    out: list[tuple[str, str, Decimal | None]] = [("entities", "", Decimal(len(ents)))]
    by_type: dict[str, int] = {}
    for e in ents:
        by_type[e["type_name"]] = by_type.get(e["type_name"], 0) + 1
    out += [("entities_by_type", t, Decimal(n)) for t, n in sorted(by_type.items())]
    apps = [e for e in ents if e["type_code"].lower() in APPLICATION_TYPES]
    for code, codes in (("applications_by_time", TIME_ATTRS), ("applications_by_lifecycle", LIFECYCLE_ATTRS)):
        groups: dict[str, int] = {}
        for e in apps:
            v = _first(attrs.get(e["id"], {}), codes)
            key = _display(v).strip() if v else ""
            groups[key or NOT_SET] = groups.get(key or NOT_SET, 0) + 1
        out += [(code, k, Decimal(n)) for k, n in sorted(groups.items())]
    cost = sum((_num(_first(attrs.get(e["id"], {}), COST_ATTRS)) or Decimal(0)) for e in ents)
    out.append(("total_cost", "", Decimal(cost)))
    q = data.get("quality")
    out.append(("quality_score", "", Decimal(str(q)) if q is not None else None))
    parents = {e["parent"] for e in ents if e["parent"]}
    orphans = sum(1 for e in ents if e["id"] not in data["linked"] and not e["parent"] and e["id"] not in parents)
    out.append(("orphans", "", Decimal(orphans)))
    past = soon = 0
    limit = date(today.year + 1, today.month, min(today.day, 28))
    for e in ents:
        if e["type_code"].lower() not in TECHNOLOGY_TYPES:
            continue
        d = _date(_first(attrs.get(e["id"], {}), EOL_ATTRS))
        if d is None:
            continue
        if d < today:
            past += 1
        elif d < limit:
            soon += 1
    out += [("eol_technology", "", Decimal(past)), ("eol_technology_soon", "", Decimal(soon))]
    return out


def _matches(op: str, wanted: str, v: dict | None) -> bool:
    shown = _display(v).strip() if v else ""
    if op == "":
        return True
    if op == "empty":
        return shown == ""
    if op == "not-empty":
        return shown != ""
    if op == "equals":
        return shown.lower() == (wanted or "").strip().lower()
    if op == "not-equals":
        return shown.lower() != (wanted or "").strip().lower()
    if op == "contains":
        return (wanted or "").strip().lower() in shown.lower()
    if op in ("more-than", "less-than"):
        n = _num(v)
        try:
            w = Decimal(str(wanted).replace(",", "").strip())
        except Exception:  # noqa: BLE001 - a date compared as a date
            d, wd = _date(v), None
            try:
                wd = date.fromisoformat(str(wanted).strip()[:10])
            except ValueError:
                return False
            return d is not None and (d > wd if op == "more-than" else d < wd)
        return n is not None and (n > w if op == "more-than" else n < w)
    return False


def own_value(defn: dict, data: dict[str, Any]) -> Decimal:
    """One of a Model Admin's own KPIs over a model's data: a count of the entities of its type that pass its filter, or the
    sum of a number attribute over them."""
    attrs = _by_entity(data["values"])
    tcode = (defn.get("entity_type_code") or "").lower()
    fattr = (defn.get("filter_attribute") or "").lower()
    total = Decimal(0)
    for e in data["entities"]:
        if e["type_code"].lower() != tcode:
            continue
        mine = attrs.get(e["id"], {})
        if fattr and not _matches(defn.get("filter_op") or "", defn.get("filter_value") or "", mine.get(fattr)):
            continue
        if defn.get("kind") == "sum":
            total += _num(mine.get((defn.get("attribute_code") or "").lower())) or Decimal(0)
        else:
            total += 1
    return total


# ---------------------------------------------------------------- definitions
def definitions(conn, model_id: int) -> list[dict]:
    return _maps(conn.execute(text("""
        SELECT d.guid::text AS id, d.name, d.kind, d.entity_type_code, d.attribute_code, d.filter_attribute, d.filter_op,
               d.filter_value, d.unit, d.description, d.created_by, d.created_at, d.modified_by, d.modified_at
          FROM core.kpi_definitions d WHERE d.model_id = :m AND NOT d.is_deleted ORDER BY lower(d.name)"""), {"m": model_id}))


def _check(conn, model_id: int, body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        raise EditError("Give the KPI a name, for example Applications to retire.")
    if len(name) > 120:
        raise EditError("Keep the KPI's name under 120 characters.")
    kind = body.get("kind") or "count"
    if kind not in KINDS:
        raise EditError("A KPI is a count or a sum.")
    tcode = (body.get("entity_type_code") or "").strip()
    t = conn.execute(text("""SELECT id, code, name FROM core.entity_types WHERE model_id = :m AND lower(code) = lower(:c)
                              AND NOT is_deleted AND NOT is_connector"""), {"m": model_id, "c": tcode}).mappings().first()
    if not t:
        raise EditError("Choose the entity type the KPI counts or adds up.")
    attrs = {r["code"].lower(): dict(r) for r in conn.execute(text("""
        SELECT a.code, a.name, a.data_type_code AS data_type FROM core.item_attributes i
          JOIN core.attribute_types a ON a.id = i.attribute_type_id
         WHERE i.entity_type_id = :t AND NOT i.is_deleted AND NOT a.is_deleted"""), {"t": t["id"]}).mappings()}
    acode = (body.get("attribute_code") or "").strip()
    if kind == "sum":
        a = attrs.get(acode.lower())
        if not a or a["data_type"] not in NUMBER_TYPES:
            raise EditError(f"A sum adds up a number attribute of {t['name']}: choose one.")
        acode = a["code"]
    else:
        acode = ""
    op = body.get("filter_op") or ""
    if op not in OPS:
        raise EditError("Choose how the filter compares.")
    fattr = (body.get("filter_attribute") or "").strip()
    if op:
        a = attrs.get(fattr.lower())
        if not a:
            raise EditError(f"Choose the attribute of {t['name']} to filter on.")
        fattr = a["code"]
    else:
        fattr = ""
    fval = "" if op in ("", "empty", "not-empty") else str(body.get("filter_value") or "").strip()
    if op in ("equals", "not-equals", "contains", "more-than", "less-than") and not fval:
        raise EditError("Give the value the filter compares with.")
    return {"name": name, "kind": kind, "entity_type_code": t["code"], "attribute_code": acode, "filter_attribute": fattr,
            "filter_op": op, "filter_value": fval[:200], "unit": (body.get("unit") or "").strip()[:20],
            "description": (body.get("description") or "").strip()[:500]}


def _admin(conn, user, m: dict) -> None:
    from . import quality as q
    if not q.is_model_admin(conn, user, m):
        raise EditError("Only the model's Model Admins (and Super Admins) set its own KPIs.", 403)


def add_definition(conn, model: Any, user, body: dict) -> dict:
    m = repo.get_model(conn, model)
    _admin(conn, user, m)
    d = _check(conn, m["_id"], body)
    row = conn.execute(text("""
        INSERT INTO core.kpi_definitions (model_id, name, kind, entity_type_code, attribute_code, filter_attribute, filter_op,
                                          filter_value, unit, description, created_by, modified_by)
        VALUES (:m, :name, :kind, :entity_type_code, :attribute_code, :filter_attribute, :filter_op, :filter_value, :unit,
                :description, :u, :u) RETURNING guid::text"""), {**d, "m": m["_id"], "u": user.username.lower()}).scalar()
    return next(x for x in definitions(conn, m["_id"]) if x["id"] == row)


def update_definition(conn, model: Any, user, kpi: str, body: dict) -> dict:
    m = repo.get_model(conn, model)
    _admin(conn, user, m)
    cur = next((x for x in definitions(conn, m["_id"]) if x["id"] == str(kpi)), None)
    if not cur:
        raise EditError("No such KPI on this model.", 404)
    d = _check(conn, m["_id"], {**cur, **body})
    conn.execute(text("""
        UPDATE core.kpi_definitions SET name = :name, kind = :kind, entity_type_code = :entity_type_code,
               attribute_code = :attribute_code, filter_attribute = :filter_attribute, filter_op = :filter_op,
               filter_value = :filter_value, unit = :unit, description = :description, modified_by = :u, modified_at = now()
         WHERE model_id = :m AND guid = CAST(:g AS uuid)"""), {**d, "m": m["_id"], "u": user.username.lower(), "g": str(kpi)})
    return next(x for x in definitions(conn, m["_id"]) if x["id"] == str(kpi))


def delete_definition(conn, model: Any, user, kpi: str) -> dict:
    """The KPI is no longer kept from now on; the values it already has stay in the snapshots (the trend so far)."""
    m = repo.get_model(conn, model)
    _admin(conn, user, m)
    n = conn.execute(text("""UPDATE core.kpi_definitions SET is_deleted = true, modified_by = :u, modified_at = now()
                              WHERE model_id = :m AND guid = CAST(:g AS uuid) AND NOT is_deleted"""),
                     {"m": m["_id"], "u": user.username.lower(), "g": str(kpi)}).rowcount
    if not n:
        raise EditError("No such KPI on this model.", 404)
    return {"deleted": str(kpi)}


# ---------------------------------------------------------------- snapshots
def values_now(conn, model_id: int, data: dict | None = None) -> list[dict]:
    """Every KPI of the model now: [{kpi, name, kind, dimension, value}]."""
    data = data if data is not None else load(conn, model_id)
    rows = [{"kpi": c, "name": STANDARD_BY_CODE[c]["name"], "kind": "standard", "dimension": d, "value": v}
            for c, d, v in standard_values(data)]
    for d in definitions(conn, model_id):
        rows.append({"kpi": f"own:{d['id']}", "name": d["name"], "kind": "own", "dimension": "", "value": own_value(d, data)})
    return rows


def take(conn, model_id: int, reason: str, *, by: str = "system", tag_id: int | None = None, tag_name: str = "",
         period: date | None = None, at: datetime | None = None, rows: list[dict] | None = None) -> int:
    """Keeps a snapshot of the model's KPIs; returns its id. rows: the values to keep (the seed's history), else now's."""
    if reason not in ("monthly", "tag"):
        raise ValueError(reason)
    rows = rows if rows is not None else values_now(conn, model_id)
    sid = conn.execute(text("""
        INSERT INTO core.kpi_snapshots (model_id, taken_at, period, reason, tag_id, tag_name, taken_by)
        VALUES (:m, coalesce(:at, now()), :p, :r, :t, :tn, :by) RETURNING id"""),
        {"m": model_id, "at": at, "p": period, "r": reason, "t": tag_id, "tn": tag_name, "by": by}).scalar()
    for start in range(0, len(rows), 200):          # one statement per 200 values
        chunk = rows[start:start + 200]
        params: dict[str, Any] = {"s": sid, "m": model_id}
        parts = []
        for i, r in enumerate(chunk):
            parts.append(f"(:s, :m, :k{i}, :n{i}, :t{i}, :d{i}, CAST(:v{i} AS numeric))")
            params.update({f"k{i}": r["kpi"], f"n{i}": r["name"], f"t{i}": r["kind"], f"d{i}": r["dimension"],
                           f"v{i}": None if r["value"] is None else str(r["value"])})
        conn.execute(text("INSERT INTO core.kpi_values (snapshot_id, model_id, kpi, name, kind, dimension, value) VALUES "
                          + ", ".join(parts)), params)
    return int(sid)


def on_tag(conn, m: dict, tag: dict, by: str) -> None:
    """A tag keeps the KPIs as they are at that moment (D365). Never stops the tag: a failure is only logged."""
    import logging
    try:
        with conn.begin_nested():
            take(conn, m["_id"], "tag", by=by, tag_id=tag.get("id"), tag_name=tag.get("name") or "")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("KPI snapshot on tag of %s: %s", m.get("name"), exc)


LIVE_SQL = """SELECT m.id, m.name FROM core.models m
               WHERE NOT m.is_deleted AND m.source_model_id IS NOT NULL AND m.kind_code IN ('project', 'reference')
                 AND m.lifecycle = 'active' AND m.frozen_at IS NULL"""


def monthly_due(conn, today: date) -> list[dict]:
    """The live models (not archived or frozen, D360) with no monthly snapshot for this month yet."""
    period = today.replace(day=1)
    return _maps(conn.execute(text(LIVE_SQL + """
                 AND NOT EXISTS (SELECT 1 FROM core.kpi_snapshots s WHERE s.model_id = m.id AND s.reason = 'monthly'
                                   AND s.period = :p) ORDER BY m.id"""), {"p": period}))


def take_monthly(begin, today: date | None = None) -> int:
    """The monthly snapshot of every live model due one (begin(): a new transaction). Returns how many were taken."""
    import logging
    today = today or datetime.now(UTC).date()
    with begin() as conn:
        due = monthly_due(conn, today)
    n = 0
    for m in due:
        try:
            with begin() as conn:
                take(conn, m["id"], "monthly", period=today.replace(day=1))
            n += 1
        except Exception as exc:  # noqa: BLE001 - one model never stops the others
            logging.getLogger(__name__).warning("monthly KPIs of %s: %s", m["name"], exc)
    return n


# ---------------------------------------------------------------- the trends
def _f(v) -> float | None:
    return None if v is None else float(v)


def trends(conn, model: Any, user=None) -> dict:
    """The model's KPIs: every snapshot kept (oldest first) and the value now, by KPI and dimension, for the model page."""
    m = repo.get_model(conn, model)
    snaps = _maps(conn.execute(text("""
        SELECT id, guid::text AS id_text, taken_at, period, reason, tag_name, taken_by FROM core.kpi_snapshots
         WHERE model_id = :m ORDER BY taken_at, id"""), {"m": m["_id"]}))
    vals = conn.execute(text("""SELECT snapshot_id, kpi, name, kind, dimension, value FROM core.kpi_values WHERE model_id = :m"""),
                        {"m": m["_id"]}).mappings().all()
    data = load(conn, m["_id"])
    now = values_now(conn, m["_id"], data)
    defs = definitions(conn, m["_id"])
    order = [k["code"] for k in STANDARD] + [f"own:{d['id']}" for d in defs]
    kpis: dict[str, dict] = {}

    def entry(code: str, name: str, kind: str) -> dict:
        if code not in kpis:
            std = STANDARD_BY_CODE.get(code)
            own = next((d for d in defs if f"own:{d['id']}" == code), None)
            kpis[code] = {"code": code, "name": (own or {}).get("name") or name, "kind": kind,
                          "about": std["about"] if std else (own or {}).get("description") or "",
                          "unit": std["unit"] if std else (own or {}).get("unit") or "",
                          "definition": own, "retired": kind == "own" and own is None, "dimensions": {}}
        return kpis[code]

    pos = {s["id"]: i for i, s in enumerate(snaps)}
    for v in vals:
        k = entry(v["kpi"], v["name"], v["kind"])
        dim = k["dimensions"].setdefault(v["dimension"], {"dimension": v["dimension"], "series": [None] * len(snaps), "now": None})
        if v["snapshot_id"] in pos:
            dim["series"][pos[v["snapshot_id"]]] = _f(v["value"])
    for v in now:
        k = entry(v["kpi"], v["name"], v["kind"])
        dim = k["dimensions"].setdefault(v["dimension"], {"dimension": v["dimension"], "series": [None] * len(snaps), "now": None})
        dim["now"] = _f(v["value"])
    for k in kpis.values():               # a dimension gone since (a type emptied) reads 0 now, not blank
        if k["kind"] == "standard" and k["code"] not in ("quality_score",):
            for d in k["dimensions"].values():
                if d["now"] is None and d["dimension"]:
                    d["now"] = 0.0
    ordered = sorted(kpis.values(), key=lambda k: (order.index(k["code"]) if k["code"] in order else len(order), k["name"]))
    for k in ordered:
        k["dimensions"] = sorted(k["dimensions"].values(), key=lambda d: (-(d["now"] or 0), d["dimension"]))
    from . import quality as q
    return {"model": {"id": str(m["id"]), "name": m["name"]},
            "snapshots": [{"id": s["id_text"], "taken_at": s["taken_at"], "period": s["period"], "reason": s["reason"],
                           "tag": s["tag_name"], "by": s["taken_by"]} for s in snaps],
            "kpis": ordered, "definitions": defs, "kinds": KINDS, "ops": OPS,
            "may_manage": bool(user) and q.is_model_admin(conn, user, m),
            "superset": "eax-kr01"}


# ---------------------------------------------------------------- a model package carries them (D410)
def export_model(conn, model_id: int) -> dict:
    """The model's own KPIs, snapshots and report designs, for a model package or backup (reports/reports.json)."""
    defs = definitions(conn, model_id)
    snaps = _maps(conn.execute(text("""
        SELECT id, taken_at, period, reason, tag_name, taken_by FROM core.kpi_snapshots WHERE model_id = :m ORDER BY id"""),
        {"m": model_id}))
    vals: dict[int, list] = {}
    for r in conn.execute(text("SELECT snapshot_id, kpi, name, kind, dimension, value FROM core.kpi_values WHERE model_id = :m"),
                          {"m": model_id}).mappings():
        vals.setdefault(r["snapshot_id"], []).append({k: (str(r[k]) if k == "value" and r[k] is not None else r[k])
                                                      for k in ("kpi", "name", "kind", "dimension", "value")})
    designs = _maps(conn.execute(text("""
        SELECT guid::text AS id, name, spec, created_by FROM core.report_designs WHERE model_id = :m AND NOT is_deleted ORDER BY id"""),
        {"m": model_id}))
    return {"format": "eax-model-reports/1", "kpi_definitions": defs,
            "kpi_snapshots": [{"taken_at": str(s["taken_at"]), "period": str(s["period"]) if s["period"] else None,
                               "reason": s["reason"], "tag_name": s["tag_name"], "taken_by": s["taken_by"],
                               "values": vals.get(s["id"], [])} for s in snaps],
            "report_designs": designs}


def import_model(conn, model_id: int, data: dict | None, actor: str, replace: bool = False) -> dict:
    """Puts a package's KPIs, snapshots and report designs on a model (a new model made from it, or a restore over itself)."""
    import json
    if not data:
        return {}
    if replace:
        conn.execute(text("DELETE FROM core.kpi_snapshots WHERE model_id = :m"), {"m": model_id})
        conn.execute(text("UPDATE core.kpi_definitions SET is_deleted = true WHERE model_id = :m"), {"m": model_id})
        conn.execute(text("UPDATE core.report_designs SET is_deleted = true WHERE model_id = :m"), {"m": model_id})
    remap: dict[str, str] = {}
    for d in data.get("kpi_definitions") or []:
        new = str(uuid.uuid4())
        remap[f"own:{d['id']}"] = f"own:{new}"
        conn.execute(text("""
            INSERT INTO core.kpi_definitions (guid, model_id, name, kind, entity_type_code, attribute_code, filter_attribute,
                                              filter_op, filter_value, unit, description, created_by, modified_by)
            VALUES (CAST(:g AS uuid), :m, :name, :kind, :t, :a, :fa, :fo, :fv, :unit, :desc, :by, :by)"""),
            {"g": new, "m": model_id, "name": d["name"], "kind": d["kind"], "t": d["entity_type_code"], "a": d.get("attribute_code") or "",
             "fa": d.get("filter_attribute") or "", "fo": d.get("filter_op") or "", "fv": d.get("filter_value") or "",
             "unit": d.get("unit") or "", "desc": d.get("description") or "", "by": d.get("created_by") or actor})
    for s in data.get("kpi_snapshots") or []:
        rows = [{**v, "kpi": remap.get(v["kpi"], v["kpi"]), "value": Decimal(v["value"]) if v.get("value") not in (None, "") else None}
                for v in s.get("values") or []]
        take(conn, model_id, s["reason"], by=s.get("taken_by") or actor, tag_name=s.get("tag_name") or "",
             period=date.fromisoformat(s["period"]) if s.get("period") else None,
             at=datetime.fromisoformat(s["taken_at"]) if s.get("taken_at") else None, rows=rows)
    from . import report_designer as rd
    for d in data.get("report_designs") or []:
        spec = d["spec"] if isinstance(d["spec"], dict) else json.loads(d["spec"])
        try:
            rd.save_design(conn, model_id, d["name"], spec, d.get("created_by") or actor)
        except EditError:
            pass                         # a design the new model's metamodel cannot hold is left out
    return {"kpi_definitions": len(data.get("kpi_definitions") or []), "kpi_snapshots": len(data.get("kpi_snapshots") or []),
            "report_designs": len(data.get("report_designs") or [])}
