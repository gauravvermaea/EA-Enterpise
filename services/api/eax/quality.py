"""Validation and data quality (build phase 12, D239).

How good is a model's data, where is it weakest, who should fix it, and is it getting better?

* Who is responsible for an entity (D239.1): its Owner attribute when that names a person of the installation, else
  whoever last changed it, else the model's Model Admins. Every entity always has someone. The Owner attribute's text
  (a person or a business role) is also how scores are grouped "by owner".
* Completeness (MM-022, VAL-005): each entity scores 0-100% from weighted items: its description, each attribute its
  type has, and having a relationship. An attribute's weight is in the metamodel (D241): its default where the attribute
  is defined, which an entity type may override where it adds the attribute; without either, a required attribute
  weighs 3 and another 1. The description weighs 1 and having any relationship 2. A model's quality settings may change
  any weight (inherited down the hierarchy; a Model Admin's change waits for a Super Admin, D239.5). 0 leaves it out.
* Rules (VAL-006): the metamodel's own checks (required values, ranges, patterns, allowed relationships; eax.rules)
  plus rules without SQL of four kinds (RULE_KINDS); each an error (blocks a commit) or a warning (D239.8).
* Retired entities are not part of data quality (owner, 6 Nov 2026).
* Staleness (D239.2): one period per model; an entity not changed, attested or marked still current within it is stale.
* Seals (VAL-007, D239.6): an owner attests an entity is correct, or a Model Admin marks it still current (one or many);
  a seal expires after the stale period and an edit by someone else breaks it at once.
* The model's score (D244): by default 50% completeness, 30% the share of entities failing no rule, 20% the share that
  is not stale. Super Admins set the installation's weights and colour thresholds (green from 80, amber from 60, red
  below by default) on Administration > Quality; a model may set its own (inherited down the hierarchy; a Model Admin's
  change waits for a Super Admin, like every other quality setting). The estate is coloured by the installation's.

Every measurement is kept (core.quality_runs) with its scores by type and owner and its findings, so the dashboard shows
the trend. The job runner measures on each model's schedule, tells people about new problems as they happen and sends a
weekly digest (eax.jobs).
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from . import junctions, multiplicity
from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

DEFAULT_WEIGHTS = {"required": 3, "attribute": 1, "field:description": 1, "rel:any": 2}
IMPORTANT = 3                     # a missing item this heavy makes the entity "incomplete" (told as it happens)
SCORE_PARTS = {"completeness": 50, "rules": 30, "freshness": 20}   # the defaults; the installation and models set their own
BANDS = {"green": 80, "amber": 60}                                   # green from, amber from, red below (D244)
SYSTEM_ACTORS = re.compile(r"^(system|eax[_-]|postgres|seed|.*:)", re.I)
RULE_KINDS = {   # what each kind of rule checks, in words for the screens (the spec is in eax.mcp_server draft_quality_rule)
    "relationship": "Must have a relationship: at least (and at most) a number of relationships of a type, in a direction, "
                    "with an entity of a type; leave a field empty for any.",
    "attribute": "Attribute conditions: when one value meets a condition (optional), another must meet one too, for "
                 "example when Lifecycle is Retiring, Retirement date is filled.",
    "consistency": "Cross-entity consistency: the entities related to it must not (or must all) meet a condition, for "
                   "example no application in use runs on retired technology.",
    "naming": "Naming and uniqueness: the name follows a pattern (a regular expression) and/or no other entity of its type "
              "(or of the model) has the same name.",
}
# which models are measured (D242): never an archived model; otherwise the admins' choice, else project models that are
# not frozen
MEASURED_SQL = """(m.lifecycle = 'active' AND coalesce((SELECT q.measured FROM core.quality_scope q WHERE q.model_id = m.id),
                                                    m.kind_code = 'project' AND NOT m.is_locked AND m.lock_level <> 'content'))"""
OPS = ("filled", "empty", "equals", "not_equals", "in", "not_in", "matches", "at_least", "at_most", "before_today",
       "after_today")


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _now() -> datetime:
    return datetime.now(UTC)


def _ts(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------- who may do what
def _model_roles(conn, user, m: dict) -> list[str]:
    return perms.model_roles(conn, user.username, m["id"]) if user else []


def is_model_admin(conn, user, m: dict) -> bool:
    return bool(user) and (perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in _model_roles(conn, user, m))


def _bypass(conn, on: bool) -> None:
    conn.execute(text("SELECT set_config('eax.rls_bypass', :v, true)"), {"v": "on" if on else ""})


# ---------------------------------------------------------------- settings (inherited down the hierarchy)
def chain(conn, m: dict) -> list[int]:
    """The model's line of ancestors, the farthest first, ending with the model (parent, else source)."""
    out, seen, cur = [], set(), m["_id"]
    _bypass(conn, True)
    try:
        while cur and cur not in seen:
            seen.add(cur)
            out.append(cur)
            r = _rows(conn, "SELECT coalesce(parent_model_id, source_model_id) AS up FROM core.models WHERE id = :i", i=cur)
            cur = r[0]["up"] if r else None
    finally:
        _bypass(conn, False)
    return list(reversed(out))


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


def defaults(conn) -> dict:
    """The installation's defaults (D239, D244): stale period, schedule, score weights and colours."""
    d = _rows(conn, "SELECT * FROM core.quality_defaults")[0]
    return {"stale_days": d["stale_days"], "cron": d["cron"], "score_parts": {**SCORE_PARTS, **(_j(d.get("score_parts")) or {})},
            "bands": {**BANDS, **(_j(d.get("bands")) or {})}, "modified_by": d.get("modified_by"),
            "modified_at": d.get("modified_at")}


def set_defaults(conn, user, payload: dict) -> dict:
    """Super Admins set the installation's defaults (D244); every model inherits what it does not set itself."""
    from . import audit
    if perms.SUPER_ADMIN not in user.roles:
        raise EditError("The installation's data quality defaults are set by Super Admins.", 403)
    cur = defaults(conn)
    clean = _clean_settings({**{k: cur[k] for k in ("stale_days", "cron", "score_parts", "bands")},
                             **{k: v for k, v in (payload or {}).items() if k in ("stale_days", "cron", "score_parts", "bands")}})
    if not clean["stale_days"] or not clean["cron"] or not clean["score_parts"] or not clean["bands"]:
        raise EditError("The installation's defaults need a stale period, a schedule, the score weights and the colours.")
    _bypass(conn, True)
    try:
        conn.execute(text("""UPDATE core.quality_defaults SET stale_days = :s, cron = :c, score_parts = CAST(:p AS jsonb),
                                    bands = CAST(:b AS jsonb), modified_by = :u, modified_at = now()"""),
                     {"s": clean["stale_days"], "c": clean["cron"], "p": json.dumps(clean["score_parts"]),
                      "b": json.dumps(clean["bands"]), "u": user.username.lower()})
    finally:
        _bypass(conn, False)
    summary = _summary(clean)
    audit.record(conn, actor=user.username, action="quality.defaults", object_type="installation", object_id="quality",
                 details={"summary": summary})
    return {**defaults(conn), "summary": summary}


def bands_for(conn, m: dict) -> dict:
    """A model's colour thresholds (D244): its own, else its nearest ancestor's, else the installation's (cheap: for forms)."""
    ids = chain(conn, m)
    _bypass(conn, True)
    try:
        own = {r["model_id"]: _j(r["bands"]) for r in _rows(conn, """SELECT model_id, bands FROM core.quality_settings
                                                                      WHERE model_id = ANY (:i) AND bands IS NOT NULL""", i=ids)}
    finally:
        _bypass(conn, False)
    for mid in reversed(ids):
        if own.get(mid):
            return own[mid]
    return defaults(conn)["bands"]


def tone(v, bands: dict | None = None) -> str:
    """good, fair or poor for a percentage, by the colour thresholds (D244)."""
    if v is None:
        return ""
    b = bands or BANDS
    return "good" if float(v) >= b["green"] else "fair" if float(v) >= b["amber"] else "poor"


def settings(conn, model: Any) -> dict:
    """The model's effective settings: stale period, schedule, weights and rules, each with where it comes from."""
    m = model if isinstance(model, dict) and "_id" in model else repo.get_model(conn, model)
    ids = chain(conn, m)
    d = defaults(conn)
    out = {"stale_days": d["stale_days"], "stale_from": "default", "cron": d["cron"], "cron_from": "default",
           "score_parts": d["score_parts"], "score_parts_from": "default", "bands": d["bands"], "bands_from": "default",
           "weights": {}, "weight_from": {}, "rules": {}, "own": {}}
    _bypass(conn, True)
    try:
        names = {r["id"]: r["name"] for r in _rows(conn, "SELECT id, name FROM core.models WHERE id = ANY (:i)", i=ids)}
        own_rows = {r["model_id"]: r for r in _rows(conn, "SELECT * FROM core.quality_settings WHERE model_id = ANY (:i)", i=ids)}
        rules = _rows(conn, """SELECT r.*, r.guid::text AS id FROM core.quality_rules r WHERE r.model_id = ANY (:i)""", i=ids)
    finally:
        _bypass(conn, False)
    for mid in ids:
        s = own_rows.get(mid)
        if not s:
            continue
        if s["stale_days"]:
            out["stale_days"], out["stale_from"] = s["stale_days"], names.get(mid, "")
        if s["cron"]:
            out["cron"], out["cron_from"] = s["cron"], names.get(mid, "")
        if s.get("score_parts"):
            out["score_parts"], out["score_parts_from"] = _j(s["score_parts"]), names.get(mid, "")
        if s.get("bands"):
            out["bands"], out["bands_from"] = _j(s["bands"]), names.get(mid, "")
        w = s["weights"] if isinstance(s["weights"], dict) else json.loads(s["weights"] or "{}")
        for t, items in (w or {}).items():
            for item, val in (items or {}).items():
                out["weights"].setdefault(t, {})[item] = int(val)
                out["weight_from"].setdefault(t, {})[item] = names.get(mid, "")
    order = {mid: i for i, mid in enumerate(ids)}
    for r in sorted(rules, key=lambda r: order[r["model_id"]]):
        spec = r["spec"] if isinstance(r["spec"], dict) else json.loads(r["spec"] or "{}")
        out["rules"][r["code"]] = {"id": r["id"], "code": r["code"], "name": r["name"], "kind": r["kind"],
                                   "entity_type": r["entity_type"], "spec": spec, "severity": r["severity"],
                                   "enabled": r["enabled"], "message": r["message"], "from": names.get(r["model_id"], ""),
                                   "inherited": r["model_id"] != m["_id"], "modified_by": r["modified_by"],
                                   "modified_at": r["modified_at"]}
    own = own_rows.get(m["_id"])
    out["own"] = {"stale_days": own["stale_days"] if own else None, "cron": own["cron"] if own else None,
                  "score_parts": _j(own.get("score_parts")) if own else None, "bands": _j(own.get("bands")) if own else None,
                  "weights": (own["weights"] if isinstance(own["weights"], dict) else json.loads(own["weights"] or "{}"))
                  if own else {}}
    out["rules"] = list(out["rules"].values())
    return out


# ---------------------------------------------------------------- the model's content, loaded once
def _value(r: dict) -> Any:
    for k in ("value_text", "value_number", "value_date", "value_bool", "ref_name"):
        if r.get(k) is not None:
            v = r[k]
            return float(v) if isinstance(v, Decimal) else v
    return None


def load(conn, m: dict) -> dict:
    """Everything quality needs from one model: types, attributes, entities, values, relationships, seals, people."""
    mid = m["_id"]
    types = {r["id"]: r for r in _rows(conn, """SELECT id, guid::text AS guid, code, name FROM core.entity_types
                                                  WHERE model_id = :m AND NOT is_deleted AND NOT is_connector""", m=mid)}   # junctions are not measured (D397)
    attrs = defaultdict(list)
    for r in _rows(conn, """SELECT ia.entity_type_id, a.code, a.name, ia.is_required, ia.quality_weight AS item_weight,
                                   a.quality_weight AS attribute_weight FROM core.item_attributes ia
                              JOIN core.attribute_types a ON a.id = ia.attribute_type_id
                             WHERE ia.model_id = :m AND ia.entity_type_id IS NOT NULL AND NOT ia.is_deleted AND NOT a.is_deleted
                             ORDER BY ia.sort_order""", m=mid):
        attrs[r["entity_type_id"]].append(r)
    ents = {r["id"]: r for r in _rows(conn, """
        SELECT e.id, e.guid::text AS guid, e.display_id, e.name, e.description, e.entity_type_id, e.created_by,
               e.modified_at, e.modified_by, e.status_code
          FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
         WHERE e.model_id = :m AND NOT e.is_deleted AND NOT t.is_connector""", m=mid)}
    values = defaultdict(dict)
    last_value = {}
    for r in _rows(conn, """
        SELECT v.entity_id, a.code, v.value_text, v.value_number, v.value_date, v.value_bool, x.name AS ref_name,
               v.modified_at, v.modified_by
          FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
          LEFT JOIN core.entities x ON x.id = v.value_ref
         WHERE v.model_id = :m AND v.entity_id IS NOT NULL AND NOT v.is_deleted""", m=mid):
        values[r["entity_id"]][r["code"]] = _value(r)
        cur = last_value.get(r["entity_id"])
        if cur is None or _ts(r["modified_at"]) > cur[0]:
            last_value[r["entity_id"]] = (_ts(r["modified_at"]), r["modified_by"])
    rels = defaultdict(list)
    for r in _rows(conn, """
        SELECT r.source_entity_id AS s, r.target_entity_id AS t, rt.code AS type FROM core.relationships r
          JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities a ON a.id = r.source_entity_id AND NOT a.is_deleted
          JOIN core.entities b ON b.id = r.target_entity_id AND NOT b.is_deleted
         WHERE r.model_id = :m AND NOT r.is_deleted""", m=mid):
        rels[r["s"]].append({"type": r["type"], "dir": "out", "other": r["t"]})
        rels[r["t"]].append({"type": r["type"], "dir": "in", "other": r["s"]})
    # multiplicities on allowed relationships (D395): only those with an end set
    mult = _rows(conn, """SELECT rt.code AS type, ar.source_type_id, ar.target_type_id, ar.source_multiplicity AS source_end,
                                 ar.target_multiplicity AS target_end, s.name AS source_name, t.name AS target_name
                            FROM core.allowed_relationships ar JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
                            JOIN core.entity_types s ON s.id = ar.source_type_id JOIN core.entity_types t ON t.id = ar.target_type_id
                           WHERE ar.model_id = :m AND NOT ar.is_deleted
                             AND (ar.source_multiplicity <> '' OR ar.target_multiplicity <> '')""", m=mid)
    seals = {r["entity_id"]: r for r in _rows(conn, "SELECT * FROM core.quality_seals WHERE model_id = :m", m=mid)}
    exempt, exempt_pending = defaultdict(dict), defaultdict(dict)        # D246: not applicable on one entity
    exempt_rejected = defaultdict(dict)
    for r in _rows(conn, """SELECT guid::text AS id, entity_id, item, reason, status, requested_by, requested_at, decided_by,
                                   decision_note FROM core.quality_exemptions
                             WHERE model_id = :m AND status IN ('pending', 'approved', 'rejected') ORDER BY requested_at""", m=mid):
        if r["status"] == "rejected":
            exempt_rejected[r["entity_id"]][r["item"]] = r          # the latest; shown until asked again
            continue
        exempt_rejected[r["entity_id"]].pop(r["item"], None)
        (exempt if r["status"] == "approved" else exempt_pending)[r["entity_id"]][r["item"]] = r
    people = {r["u"] for r in _rows(conn, "SELECT lower(username) AS u FROM core.model_users WHERE model_id = :m", m=mid)}
    people |= {r["u"] for r in _rows(conn, "SELECT lower(username) AS u FROM core.known_users")}
    admins = sorted({r["u"] for r in _rows(conn, """SELECT lower(username) AS u FROM core.model_users
                                                       WHERE model_id = :m AND role = 'model-admin'""", m=mid)})
    return {"types": types, "attrs": attrs, "entities": ents, "values": values, "last_value": last_value, "rels": rels,
            "multiplicity": mult, "junctions": junctions.problems(conn, mid), "seals": seals, "people": people, "admins": admins, "exempt": exempt, "exempt_pending": exempt_pending,
            "exempt_rejected": exempt_rejected}


# ---------------------------------------------------------------- conditions and rules
def _get(data: dict, e: dict, attribute: str) -> Any:
    a = (attribute or "").strip()
    if a.lower() in ("name", "description", "display_id"):
        return e.get(a.lower())
    vals = data["values"].get(e["id"], {})
    if a in vals:
        return vals[a]
    low = a.lower()
    return next((v for k, v in vals.items() if k.lower() == low), None)


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cond(data: dict, e: dict, c: dict | None) -> bool:
    """Whether an entity meets a condition {attribute, op, value} (no condition: true)."""
    if not c or not c.get("attribute"):
        return True
    v, op, want = _get(data, e, c["attribute"]), c.get("op") or "filled", c.get("value")
    sv = "" if v is None else str(v).strip()
    wants = [str(x).strip().lower() for x in (want if isinstance(want, list) else str(want or "").split(","))] \
        if op in ("in", "not_in") else []
    if op == "filled":
        return not _empty(v)
    if op == "empty":
        return _empty(v)
    if op == "equals":
        return sv.lower() == str(want or "").strip().lower()
    if op == "not_equals":
        return sv.lower() != str(want or "").strip().lower()
    if op == "in":
        return sv.lower() in wants
    if op == "not_in":
        return sv.lower() not in wants
    if op == "matches":
        try:
            return bool(re.fullmatch(str(want or ""), sv))
        except re.error:
            return False
    if op in ("at_least", "at_most"):
        a, b = _num(v), _num(want)
        if a is None or b is None:
            return False
        return a >= b if op == "at_least" else a <= b
    if op in ("before_today", "after_today"):
        d = str(v or "")[:10]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            return False
        today = _now().date().isoformat()
        return d < today if op == "before_today" else d > today
    return True


def _cond_text(c: dict | None) -> str:
    if not c or not c.get("attribute"):
        return ""
    op = (c.get("op") or "filled").replace("_", " ")
    val = c.get("value")
    val = ", ".join(map(str, val)) if isinstance(val, list) else val
    return f"{c['attribute']} {op}{'' if op in ('filled', 'empty', 'before today', 'after today') else f' {val}'}"


def _related(data: dict, e: dict, via: dict) -> list[dict]:
    rt, d, ot = (via.get("relationship_type") or "").lower(), via.get("direction") or "any", (via.get("other_type") or "").lower()
    out = []
    for r in data["rels"].get(e["id"], []):
        if rt and r["type"].lower() != rt:
            continue
        if d != "any" and r["dir"] != d:
            continue
        other = data["entities"].get(r["other"])
        if not other:
            continue
        if ot and data["types"][other["entity_type_id"]]["code"].lower() != ot:
            continue
        out.append(other)
    return out


def check_rule(data: dict, rule: dict, e: dict, names: Counter | None = None) -> str | None:
    """Why an entity fails a quality rule, or None."""
    s = rule.get("spec") or {}
    k = rule["kind"]
    if k == "relationship":
        n = len(_related(data, e, s))
        lo = int(s.get("min") if s.get("min") not in (None, "") else 1)
        hi = s.get("max")
        hi = int(hi) if hi not in (None, "") else None
        if n < lo or (hi is not None and n > hi):
            what = (f"{s['relationship_type']} " if s.get("relationship_type") else "") + \
                   ("relationship" if n == 1 else "relationships") + \
                   {"out": " from it", "in": " to it"}.get(s.get("direction") or "any", "") + \
                   (f" with a {s['other_type']}" if s.get("other_type") else "")
            has = "no" if n == 0 else str(n)
            return rule.get("message") or f"Has {has} {what}; needs {lo}{f' to {hi}' if hi is not None else ' or more'}"
        return None
    if k == "attribute":
        if not cond(data, e, s.get("when")):
            return None
        if cond(data, e, s.get("then")):
            return None
        w = _cond_text(s.get("when"))
        return rule.get("message") or f"{_cond_text(s.get('then'))} is required{f' when {w}' if w else ''}"
    if k == "consistency":
        if not cond(data, e, s.get("when")):
            return None
        others = _related(data, e, s.get("via") or {})
        match = [o for o in others if cond(data, o, s.get("other"))]
        bad = match if (s.get("must") or "none") == "none" else [o for o in others if o not in match]
        if bad:
            names_ = ", ".join(o["name"] for o in bad[:3]) + ("..." if len(bad) > 3 else "")
            return rule.get("message") or (f"Related to {names_}, which {'meet' if (s.get('must') or 'none') == 'none' else 'do not meet'} "
                                           f"{_cond_text(s.get('other'))}")
        return None
    if k == "naming":
        if s.get("pattern"):
            try:
                if not re.fullmatch(s["pattern"], e["name"] or ""):
                    return rule.get("message") or f"The name does not follow the pattern {s['pattern']}"
            except re.error:
                return f"The rule's pattern {s['pattern']} is not a valid regular expression"
        if s.get("unique") and names is not None and names[(e["name"] or "").strip().lower()] > 1:
            return rule.get("message") or f"Another {'entity' if s.get('scope') == 'model' else 'entity of this type'} has the name {e['name']}"
        return None
    return None


def validate_rule(conn, m: dict, rule: dict) -> dict:
    """A rule as it will be kept: its code, kind, entity type (of this model's metamodel), spec and severity checked."""
    r = {k: rule.get(k) for k in ("code", "name", "kind", "entity_type", "spec", "severity", "enabled", "message")}
    r["code"] = str(r["code"] or "").strip().upper()
    if not re.match(r"^[A-Z]{1,4}-[0-9A-Za-z-]{1,20}$", r["code"]):
        raise EditError("Give the rule a code like QR-01 (1 to 4 capital letters, a dash and a number or name).")
    r["name"] = str(r["name"] or "").strip()
    if not r["name"]:
        raise EditError("Give the rule a name, for example 'Every application serves a process'.")
    if r["kind"] not in RULE_KINDS:
        raise EditError(f"The kind of rule is one of {', '.join(RULE_KINDS)}.")
    types = {t["code"].lower(): t["code"] for t in _rows(conn, """SELECT code FROM core.entity_types
                                                                     WHERE model_id = :m AND NOT is_deleted""", m=m["_id"])}
    if types and str(r["entity_type"] or "").lower() not in types:
        raise EditError(f"The entity type {r['entity_type']!r} is not in {m['name']}'s metamodel.")
    r["entity_type"] = types.get(str(r["entity_type"] or "").lower(), r["entity_type"])
    s = r["spec"] if isinstance(r["spec"], dict) else json.loads(r["spec"] or "{}")
    for c in (s.get("when"), s.get("then"), s.get("other")):
        if c and (c.get("op") or "filled") not in OPS:
            raise EditError(f"A condition's operator is one of {', '.join(OPS)}.")
    if r["kind"] == "attribute" and not (s.get("then") or {}).get("attribute"):
        raise EditError("An attribute rule needs 'then': the attribute that must meet a condition.")
    if r["kind"] == "consistency" and not (s.get("other") or {}).get("attribute"):
        raise EditError("A consistency rule needs 'other': the condition the related entities must (not) meet.")
    if r["kind"] == "naming":
        if not s.get("pattern") and not s.get("unique"):
            raise EditError("A naming rule needs a pattern, unique, or both.")
        if s.get("pattern"):
            try:
                re.compile(s["pattern"])
            except re.error as exc:
                raise EditError(f"The pattern is not a valid regular expression: {exc}") from exc
    r["spec"] = s
    r["severity"] = "error" if r["severity"] == "error" else "warning"
    r["enabled"] = r["enabled"] is not False
    r["message"] = str(r["message"] or "").strip()[:300]
    return r


# ---------------------------------------------------------------- measuring
def responsible(data: dict, e: dict, owner_value: Any) -> list[str]:
    """D239.1: the Owner when it names a person, else the last person who changed it, else the Model Admins."""
    o = str(owner_value or "").strip().lower()
    if o and o in data["people"]:
        return [o]
    last = data["last_value"].get(e["id"])
    who = e["modified_by"]
    if last and last[0] and _ts(e["modified_at"]) and last[0] > _ts(e["modified_at"]):
        who = last[1]
    who = str(who or "").strip().lower()
    if who and not SYSTEM_ACTORS.match(who):
        return [who]
    return list(data["admins"])


def metamodel_weight(a: dict) -> int:
    """An attribute's weight from the metamodel (D241): the entity type's override, else the attribute's default, else 3
    for a required attribute and 1 for another."""
    if a.get("item_weight") is not None:
        return int(a["item_weight"])
    if a.get("attribute_weight") is not None:
        return int(a["attribute_weight"])
    return DEFAULT_WEIGHTS["required"] if a.get("is_required") else DEFAULT_WEIGHTS["attribute"]


def _weights_for(cfg: dict, type_code: str, attrs: list[dict]) -> dict[str, int]:
    """The weighted items of an entity type: the metamodel's weights (D241), then the model's quality settings (D239)."""
    w = {"field:description": DEFAULT_WEIGHTS["field:description"], "rel:any": DEFAULT_WEIGHTS["rel:any"]}
    for a in attrs:
        w[f"attr:{a['code']}"] = metamodel_weight(a)
    for scope in ("*", type_code):
        for item, val in (cfg["weights"].get(scope) or {}).items():
            if item.startswith("attr:") and item not in w and scope == "*":
                continue          # a weight for every type only counts where the type has the attribute
            w[item] = max(0, min(10, int(val)))
    return {k: v for k, v in w.items() if v > 0}


def measure(conn, model: Any, *, only: set[int] | None = None, metamodel_checks: bool = True) -> dict:
    """The model's quality now: scores, by type and owner, and every finding (not kept; see run())."""
    started = time.monotonic()
    m = model if isinstance(model, dict) and "_id" in model else repo.get_model(conn, model)
    cfg = settings(conn, m)
    data = load(conn, m)
    now = _now()
    stale_after = timedelta(days=int(cfg["stale_days"]))
    rules = [r for r in cfg["rules"] if r["enabled"]]
    by_type_rules = defaultdict(list)
    for r in rules:
        by_type_rules[r["entity_type"].lower()].append(r)
    names_type, names_model = Counter(), Counter()
    for e in data["entities"].values():
        n = (e["name"] or "").strip().lower()
        names_type[(e["entity_type_id"], n)] += 1
        names_model[n] += 1
    checks = defaultdict(list)
    if metamodel_checks and data["entities"]:
        try:
            if only is not None:     # one entity or one type: only its types' checks
                tids = {data["entities"][i]["entity_type_id"] for i in only if i in data["entities"]}
                guids = [data["types"][x]["guid"] for x in tids if x in data["types"]]
                fc = {"rows": [row for g_ in guids for row in repo.failing_checks(conn, m["id"], g_)["rows"]]}
            else:
                fc = repo.failing_checks(conn, m["id"])
            gid = {e["guid"]: e["id"] for e in data["entities"].values()}
            for r in fc["rows"]:
                eid = gid.get(str(r["entity_id"]))
                if eid:
                    checks[eid].append(r)
        except Exception:  # noqa: BLE001 - the metamodel checks are a part; quality still measures the rest
            pass
    findings, per_entity = [], []
    parts = cfg.get("score_parts") or SCORE_PARTS
    for e in data["entities"].values():
        if only is not None and e["id"] not in only:
            continue
        if e.get("status_code") == "retired":      # retired entities are not part of data quality (owner, 6 Nov 2026)
            continue
        t = data["types"].get(e["entity_type_id"])
        if not t:
            continue
        vals = data["values"].get(e["id"], {})
        owner_value = next((v for k, v in vals.items() if k.lower() == "owner"), None)
        who = responsible(data, e, owner_value)
        w = _weights_for(cfg, t["code"], data["attrs"].get(e["entity_type_id"], []))
        exempt = data["exempt"].get(e["id"], {})
        w = {k: v for k, v in w.items() if k not in exempt}          # not applicable here (D246)
        labels = {f"attr:{a['code']}": a["name"] for a in data["attrs"].get(e["entity_type_id"], [])}
        rels = data["rels"].get(e["id"], [])
        missing = []
        for item, weight in w.items():
            kind, _, code = item.partition(":")
            if kind == "field":
                ok = not _empty(e.get(code))
            elif kind == "attr":
                ok = not _empty(next((v for k, v in vals.items() if k.lower() == code.lower()), None))
            elif code == "any":
                ok = bool(rels)
            else:
                ok = any(r["type"].lower() == code.lower() for r in rels)
            if not ok:
                missing.append((item, weight))
        total = sum(w.values())
        completeness = 100.0 if not total else round(100.0 * (total - sum(x for _, x in missing)) / total, 2)
        last_change = max([x for x in (_ts(e["modified_at"]), (data["last_value"].get(e["id"]) or (None,))[0]) if x])
        seal = data["seals"].get(e["id"])
        seal_state = "none"
        fresh_at = last_change
        if seal:
            sat = _ts(seal["sealed_at"])
            last_by = e["modified_by"]
            lv = data["last_value"].get(e["id"])
            if lv and lv[0] and lv[0] >= _ts(e["modified_at"]):
                last_by = lv[1]
            if last_change > sat + timedelta(seconds=2) and str(last_by or "").lower() != str(seal["sealed_by"]).lower():
                seal_state = "broken"
            elif now - sat > stale_after:
                seal_state = "expired"
            else:
                seal_state = "valid"
            fresh_at = max(fresh_at, sat)
        stale = now - fresh_at > stale_after
        failing = []
        for c in checks.get(e["id"], []):
            failing.append({"rule": c["rule"], "name": c["field"], "severity": c["severity"], "message": c["message"],
                            "source": "metamodel", "field": c.get("code") or ("name" if c["field"] == "Name" else None)})
        for why in (data.get("junctions") or {}).get(e["id"], []):           # D397: a junction's rules
            failing.append({"rule": "junction", "name": "Junction", "severity": "warning", "message": why,
                            "source": "metamodel", "field": None})
        for why in multiplicity.check(data, e, data.get("multiplicity") or []):    # D395: a warning, never blocks a commit
            failing.append({"rule": "multiplicity", "name": "Relationship multiplicity", "severity": "warning", "message": why,
                            "source": "metamodel", "field": None})
        for r in by_type_rules.get(t["code"].lower(), []):
            names = names_model if (r["spec"] or {}).get("scope") == "model" else \
                Counter({k[1]: v for k, v in names_type.items() if k[0] == e["entity_type_id"]})
            why = check_rule(data, r, e, names)
            if why:
                spec = r["spec"] or {}
                field = (spec.get("then") or {}).get("attribute") if r["kind"] == "attribute" else \
                    "name" if r["kind"] == "naming" else None
                failing.append({"rule": r["code"], "name": r["name"], "severity": r["severity"], "message": why,
                                "source": "quality", "field": field})
        orphan = not rels
        base = {"entity": e["guid"], "display_id": e["display_id"], "name": e["name"], "type": t["code"],
                "type_name": t["name"], "owner": str(owner_value or "").strip(), "responsible": who}
        per_entity.append({**base, "completeness": completeness, "stale": stale, "seal": seal_state, "orphan": orphan,
                           "failing": len(failing), "errors": sum(1 for f in failing if f["severity"] == "error"),
                           "last_change": last_change.isoformat(), "missing": [i for i, _ in missing],
                           "score": round((completeness * parts["completeness"] + (0 if failing else 100) * parts["rules"]
                                           + (0 if stale else 100) * parts["freshness"]) / (sum(parts.values()) or 100), 2),
                           "type_id": e["entity_type_id"],
                           "_problems": failing, "_missing": missing, "_exempt": exempt,
                           "_pending": data["exempt_pending"].get(e["id"], {}), "_labels": labels,
                           "_rejected": data["exempt_rejected"].get(e["id"], {}),
                           "_fresh_at": fresh_at.isoformat()})
        for item, weight in missing:
            what = labels.get(item) or {"field:description": "The description", "rel:any": "A relationship"}.get(item) or \
                f"A {item.split(':', 1)[1]} relationship"
            findings.append({**base, "kind": "incomplete", "important": weight >= IMPORTANT, "item": item,
                             "message": f"{what} is missing"
                                        + (" (weighs " + str(weight) + ")" if weight >= IMPORTANT else "")})
        for f in failing:
            findings.append({**base, "kind": "rule", "rule": f["rule"], "rule_name": f["name"], "severity": f["severity"],
                             "source": f["source"], "message": f["message"]})
        if stale:
            findings.append({**base, "kind": "stale", "message": f"Not changed or confirmed since {fresh_at.date().isoformat()}"})
        if orphan:
            findings.append({**base, "kind": "orphan", "message": "Connected to nothing"})
        if seal_state in ("broken", "expired"):
            findings.append({**base, "kind": f"seal-{seal_state}", "message": "The quality seal was broken by a later change"
                             if seal_state == "broken" else "The quality seal has expired: check it and renew it"})
    details = {p["entity"]: {k[1:]: p.pop(k) for k in [k for k in p if k.startswith("_")]} for p in per_entity}
    n = len(per_entity)
    comp = round(sum(p["completeness"] for p in per_entity) / n, 2) if n else 100.0
    passing = round(100.0 * sum(1 for p in per_entity if not p["failing"]) / n, 2) if n else 100.0
    fresh = round(100.0 * sum(1 for p in per_entity if not p["stale"]) / n, 2) if n else 100.0
    score = round((comp * parts["completeness"] + passing * parts["rules"] + fresh * parts["freshness"])
                  / (sum(parts.values()) or 100), 2)

    def group(key):
        g = defaultdict(list)
        for p in per_entity:
            g[p[key] or "(no owner)"].append(p)
        rows = []
        for k, ps in g.items():
            rows.append({"name": k, "entities": len(ps),
                         "completeness": round(sum(p["completeness"] for p in ps) / len(ps), 2),
                         "failing": sum(1 for p in ps if p["failing"]), "errors": sum(1 for p in ps if p["errors"]),
                         "stale": sum(1 for p in ps if p["stale"]), "orphans": sum(1 for p in ps if p["orphan"]),
                         "incomplete": sum(1 for p in ps if p["completeness"] < 100)})
        return sorted(rows, key=lambda r: (r["completeness"], -r["entities"]))
    by_type = group("type_name")
    by_owner = group("owner")
    seals = Counter(p["seal"] for p in per_entity)
    summary = {"entities": n, "score": score, "completeness": comp, "passing": passing, "fresh": fresh,
               "incomplete": sum(1 for p in per_entity if p["completeness"] < 100),
               "important_missing": len({f["entity"] for f in findings if f["kind"] == "incomplete" and f["important"]}),
               "failing": sum(1 for p in per_entity if p["failing"]), "errors": sum(1 for p in per_entity if p["errors"]),
               "warnings": sum(1 for p in per_entity if p["failing"] and not p["errors"]),
               "stale": sum(1 for p in per_entity if p["stale"]), "orphans": sum(1 for p in per_entity if p["orphan"]),
               "seals": {"valid": seals["valid"], "broken": seals["broken"], "expired": seals["expired"], "none": seals["none"]},
               "rules": len(rules), "stale_days": cfg["stale_days"], "parts": parts,
               "bands": cfg.get("bands") or BANDS,
               "by_rule": [{"rule": k[0], "name": k[1], "severity": k[2], "entities": v} for k, v in Counter(
                   (f["rule"], f["rule_name"], f["severity"]) for f in findings if f["kind"] == "rule").most_common()]}
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "summary": summary, "by_type": by_type, "by_owner": by_owner,
            "entities": per_entity, "findings": findings, "seconds": round(time.monotonic() - started, 2),
            "_details": details, "_data": data, "_cfg": cfg,
            "measured_at": now.isoformat()}


def run(conn, model: Any, by: str, trigger: str = "on-demand") -> dict:
    """Measures and keeps the measurement (VAL-003): the trend and the dashboard read these."""
    m = model if isinstance(model, dict) and "_id" in model else repo.get_model(conn, model)
    q = measure(conn, m)
    s = q["summary"]
    row = _rows(conn, """INSERT INTO core.quality_runs (model_id, run_by, trigger, score, completeness, entities, summary,
                                                         by_type, by_owner, findings, seconds)
                         VALUES (:m, :b, :t, :s, :c, :n, CAST(:sum AS jsonb), CAST(:bt AS jsonb), CAST(:bo AS jsonb),
                                 CAST(:f AS jsonb), :sec) RETURNING guid::text AS id, run_at""",
                m=m["_id"], b=by or "system", t=trigger, s=s["score"], c=s["completeness"], n=s["entities"],
                sum=json.dumps(s, default=str), bt=json.dumps(q["by_type"], default=str),
                bo=json.dumps(q["by_owner"], default=str), f=json.dumps(q["findings"], default=str), sec=q["seconds"])[0]
    _store(conn, m, q, None)
    q["run"] = row
    return _public(q)


def _store(conn, m: dict, q: dict, ids: set[int] | None) -> int:
    """Writes each measured entity's row (D245, D248): every entity of the model (ids None: the others are removed), or
    only those ids (removing the ones no longer measured: retired or deleted)."""
    gid = {e["guid"]: e["id"] for e in q["_data"]["entities"].values()}
    rows = []
    for p in q["entities"]:
        eid = gid.get(p["entity"])
        if eid is not None:
            rows.append({"e": eid, "t": p["type"], "r": p, "f": _reasons(p, q["_details"][p["entity"]])})
    if ids is None:
        conn.execute(text("DELETE FROM core.quality_entities WHERE model_id = :m"), {"m": m["_id"]})
    else:
        conn.execute(text("DELETE FROM core.quality_entities WHERE entity_id = ANY (:i)"), {"i": sorted(ids)})
    if rows:
        # one statement for every row (fast for thousands)
        conn.execute(text("""INSERT INTO core.quality_entities (entity_id, model_id, entity_type, row, fields, calculated_at)
                             SELECT x.e, :m, x.t, x.r, x.f, now()
                               FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x (e bigint, t text, r jsonb, f jsonb)
                             ON CONFLICT (entity_id) DO UPDATE SET row = EXCLUDED.row, fields = EXCLUDED.fields,
                                 entity_type = EXCLUDED.entity_type, calculated_at = now()"""),
                     {"m": m["_id"], "rows": json.dumps(rows, default=str)})
    return len(rows)


def refresh_entities(conn, model: Any, entities: list[str]) -> int:
    """The background job after a commit (D245): recalculates just these entities (guids) and stores their rows."""
    m = model if isinstance(model, dict) and "_id" in model else repo.get_model(conn, model)
    ids = {r["id"] for r in _rows(conn, """SELECT id FROM core.entities WHERE model_id = :m
                                             AND guid::text = ANY (:g)""", m=m["_id"], g=[str(x) for x in entities or []])}
    if not ids:
        return 0
    q = measure(conn, m, only=ids)
    return _store(conn, m, q, ids)


def queue_entities(model_guid: str, entities: list[str], delay: int = 3) -> bool:
    """Asks for the entities a commit touched to be recalculated in the background a few seconds later (after the commit
    is visible); never fails the caller. False when no job runner took it."""
    if not entities:
        return True
    try:
        from .jobs import app as jobs_app
        from .jobs import quality_entities
        with jobs_app.open():
            quality_entities.configure(schedule_in={"seconds": delay}).defer(model=str(model_guid),
                                                                             entities=sorted(str(e) for e in entities))
        return True
    except Exception:  # noqa: BLE001 - no job runner (tests, the preview): the next full measurement catches up
        return False


def stored(conn, m: dict, entity_type: str | None = None) -> dict:
    """The stored rows (as last calculated) of a model, or of one entity type, with when they were calculated."""
    rows = _rows(conn, """SELECT e.guid::text AS entity, q.entity_type, q.row, q.fields, q.calculated_at
                            FROM core.quality_entities q JOIN core.entities e ON e.id = q.entity_id
                           WHERE q.model_id = :m AND (CAST(:t AS text) IS NULL OR q.entity_type = :t)""",
                 m=m["_id"], t=entity_type)
    when = [r["calculated_at"] for r in rows]
    return {"rows": rows, "oldest": min(when) if when else None, "newest": max(when) if when else None}


def _public(q: dict) -> dict:
    """A measurement without its working parts (they hold the loaded model)."""
    return {k: v for k, v in q.items() if not k.startswith("_")}


def kept(conn, m: dict) -> dict | None:
    """The latest kept measurement, as measure() returns it (D245: the Quality tab opens at once from it)."""
    r = _rows(conn, """SELECT r.guid::text AS id, r.run_at, r.run_by, r.trigger, r.summary, r.by_type, r.by_owner, r.findings,
                              r.seconds
                         FROM core.quality_runs r WHERE r.model_id = :m ORDER BY r.run_at DESC LIMIT 1""", m=m["_id"])
    if not r:
        return None
    r = r[0]
    ents = [_j(x["row"]) for x in stored(conn, m)["rows"]]
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "summary": _j(r["summary"]), "by_type": _j(r["by_type"]),
            "by_owner": _j(r["by_owner"]), "findings": _j(r["findings"]), "entities": ents,
            "measured_at": r["run_at"].isoformat() if hasattr(r["run_at"], "isoformat") else r["run_at"],
            "seconds": r["seconds"], "run": {"id": r["id"], "run_at": r["run_at"], "by": r["run_by"], "trigger": r["trigger"]}}


# ---------------------------------------------------------------- measuring in the background (D245)
def jobs(conn, m: dict) -> list[dict]:
    """The model's measurements queued or running, and the last one finished."""
    return _rows(conn, """SELECT guid::text AS id, status, requested_by, requested_at, started_at, finished_at, score, error
                            FROM core.quality_requests WHERE model_id = :m
                           ORDER BY requested_at DESC LIMIT 3""", m=m["_id"])


def request_run(conn, model: Any, user) -> dict:
    """Asks for a measurement in the background (Measure now, Recalculate): one queued or running per model at a time.
    Returns {id, model, new}; the caller defers the job when new."""
    m = model if isinstance(model, dict) and "_id" in model else repo.get_model(conn, model)
    _bypass(conn, True)
    try:
        busy = _rows(conn, """SELECT guid::text AS id FROM core.quality_requests WHERE model_id = :m
                                AND status IN ('queued', 'running') AND requested_at > now() - interval '2 hours'""", m=m["_id"])
        if busy:
            return {"id": busy[0]["id"], "model": str(m["id"]), "name": m["name"], "new": False}
        row = _rows(conn, """INSERT INTO core.quality_requests (model_id, requested_by) VALUES (:m, :u)
                              RETURNING guid::text AS id""", m=m["_id"], u=user.username.lower())[0]
    finally:
        _bypass(conn, False)
    return {"id": row["id"], "model": str(m["id"]), "name": m["name"], "new": True}


def run_request(conn_factory, request_id: str) -> None:
    """The job: measures and keeps, then tells the person who asked (D245). conn_factory() gives a transaction."""
    from . import notify
    with conn_factory() as conn:
        _bypass(conn, True)
        r = _rows(conn, """UPDATE core.quality_requests SET status = 'running', started_at = now()
                            WHERE guid = CAST(:g AS uuid) AND status = 'queued'
                        RETURNING model_id, requested_by""", g=request_id)
        _bypass(conn, False)
    if not r:
        return
    mid, who = r[0]["model_id"], r[0]["requested_by"]
    try:
        with conn_factory() as conn:
            _bypass(conn, True)
            mm = _rows(conn, "SELECT id AS _id, guid::text AS id, name, kind_code AS kind FROM core.models WHERE id = :i", i=mid)[0]
            q = run(conn, mm, who, "on-demand")
            conn.execute(text("""UPDATE core.quality_requests SET status = 'done', finished_at = now(), score = :s
                                 WHERE guid = CAST(:g AS uuid)"""), {"s": q["summary"]["score"], "g": request_id})
            notify.create(conn, kind="quality.measured", category="system", model_id=mid,
                          title=f"{mm['name']} measured: score {q['summary']['score']}",
                          body=f"{q['summary']['entities']} entities, {q['summary']['incomplete']} incomplete, "
                               f"{q['summary']['failing']} failing a rule, {q['summary']['stale']} stale.",
                          link=f"#/metamodel/{mm['id']}/quality", actor="system", recipients=[who])
            _bypass(conn, False)
    except Exception as exc:
        with conn_factory() as conn:
            _bypass(conn, True)
            conn.execute(text("""UPDATE core.quality_requests SET status = 'failed', finished_at = now(), error = :e
                                 WHERE guid = CAST(:g AS uuid)"""), {"e": str(exc)[:500], "g": request_id})
            _bypass(conn, False)
        raise


def runs(conn, model: Any, limit: int = 60) -> list[dict]:
    m = repo.get_model(conn, model)
    return _rows(conn, """SELECT guid::text AS id, run_at, run_by, trigger, score, completeness, entities, summary, seconds
                            FROM core.quality_runs WHERE model_id = :m ORDER BY run_at DESC LIMIT :l""", m=m["_id"], l=limit)


def dashboard(conn, model: Any, fresh: bool = False) -> dict:
    """The Quality tab: the model's latest kept measurement (D245; fresh=True measures now instead), its trend, settings,
    pending changes and the measurements queued or running."""
    m = repo.get_model(conn, model)
    q = _public(measure(conn, m)) if fresh else kept(conn, m)
    trend = list(reversed(runs(conn, m["id"], 90)))
    cfg = settings(conn, m)
    pending = _rows(conn, """SELECT guid::text AS id, kind, summary, requested_by, requested_at, note FROM core.quality_changes
                              WHERE model_id = :m AND status = 'pending' ORDER BY requested_at""", m=m["_id"])
    items = {}
    for t in _rows(conn, "SELECT id, code, name FROM core.entity_types WHERE model_id = :m AND NOT is_deleted AND NOT is_connector ORDER BY sort_order",
                   m=m["_id"]):
        attrs = _rows(conn, """SELECT a.code, a.name, ia.is_required, ia.quality_weight AS item_weight,
                                      a.quality_weight AS attribute_weight FROM core.item_attributes ia
                                 JOIN core.attribute_types a ON a.id = ia.attribute_type_id
                                WHERE ia.entity_type_id = :t AND NOT ia.is_deleted AND NOT a.is_deleted ORDER BY ia.sort_order""",
                      t=t["id"])
        eff = _weights_for(cfg, t["code"], attrs)
        rows = [{"item": "field:description", "label": "Description"}, {"item": "rel:any", "label": "Any relationship"}] + \
               [{"item": f"attr:{a['code']}", "label": a["name"] + (" (required)" if a["is_required"] else "")} for a in attrs]
        mm = {f"attr:{a['code']}": metamodel_weight(a) for a in attrs}
        mm.update({"field:description": DEFAULT_WEIGHTS["field:description"], "rel:any": DEFAULT_WEIGHTS["rel:any"]})
        for r in rows:
            r["metamodel"] = mm.get(r["item"])
            r["weight"] = eff.get(r["item"], 0)
            r["own"] = ((cfg["own"]["weights"] or {}).get(t["code"]) or {}).get(r["item"])
            r["from"] = (cfg["weight_from"].get(t["code"]) or {}).get(r["item"]) or ""
        items[t["code"]] = {"name": t["name"], "items": rows}
    _bypass(conn, True)
    try:
        measured = bool(_rows(conn, f"SELECT {MEASURED_SQL} AS v FROM core.models m WHERE m.id = :i", i=m["_id"])[0]["v"])
    finally:
        _bypass(conn, False)
    return {**(q or {}), "model": {"id": str(m["id"]), "name": m["name"], "kind": m["kind"]}, "items": items, "measured": measured,
            "trend": [{"at": r["run_at"], "score": r["score"], "completeness": r["completeness"], "trigger": r["trigger"],
                       "stale": (r["summary"] or {}).get("stale"), "failing": (r["summary"] or {}).get("failing")}
                      for r in trend],
            "settings": {k: cfg[k] for k in ("stale_days", "stale_from", "cron", "cron_from", "score_parts", "score_parts_from",
                                             "bands", "bands_from", "weights", "weight_from", "own")},
            "bands": cfg["bands"], "installation": defaults(conn),
            "rules": cfg["rules"], "rule_kinds": RULE_KINDS, "ops": OPS, "default_weights": DEFAULT_WEIGHTS,
            "pending": pending, "rejected": _rows(conn, """SELECT guid::text AS id, kind, summary, requested_by, decided_by,
                                                                  decided_at, decision_note FROM core.quality_changes
                                                            WHERE model_id = :m AND status = 'rejected'
                                                              AND decided_at > now() - interval '60 days' ORDER BY decided_at DESC""",
                                                         m=m["_id"]),
            "jobs": jobs(conn, m), "kept": not fresh, "has_measurement": q is not None,
            "exemptions": exemptions(conn, m)}


def installation(conn, user=None) -> dict:
    """The estate: every project model with its latest kept measurement, a month before and its trend, weakest first,
    and the overall quality of the estate (each model weighs as many entities as it has) with its weekly trend. Super
    Admins and IT Admins see every model; everyone else the models they read."""
    every = bool(user) and (perms.SUPER_ADMIN in user.roles or perms.IT_ADMIN in user.roles)
    if every:
        _bypass(conn, True)
    try:
        allm = _rows(conn, f"""SELECT m.id AS _id, m.guid::text AS id, m.name, m.kind_code AS kind, m.lifecycle, m.is_locked,
                                      m.lock_level, m.lock_reason, m.locked_by, m.library_state,
                                      CASE WHEN ic.library IS NOT NULL THEN 'lib:' || ic.library WHEN ic.data IS NOT NULL THEN 'upload' END AS icon,
                                      CAST(extract(epoch FROM ic.set_at) AS bigint) AS icon_version, {MEASURED_SQL} AS measured, (s.model_id IS NOT NULL) AS chosen,
                                      (SELECT count(*) FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                                        WHERE e.model_id = m.id AND NOT e.is_deleted AND NOT t.is_connector) AS entities
                                 FROM core.models m LEFT JOIN core.quality_scope s ON s.model_id = m.id
                                 LEFT JOIN core.model_icons ic ON ic.model_id = m.id
                                WHERE NOT m.is_deleted {'' if every else 'AND core.can_read_model(m.id)'}
                                ORDER BY m.kind_code <> 'project', m.name""")
        models = [m for m in allm if m["measured"]]
        ids = [m["_id"] for m in models]
        runs = _rows(conn, """SELECT model_id, run_at, score, completeness, summary FROM core.quality_runs
                               WHERE model_id = ANY (:i) ORDER BY run_at""", i=ids) if ids else []
        latest_types = {r["model_id"]: r["by_type"] for r in _rows(conn, """
            SELECT DISTINCT ON (model_id) model_id, by_type FROM core.quality_runs WHERE model_id = ANY (:i)
             ORDER BY model_id, run_at DESC""", i=ids)} if ids else {}
    finally:
        if every:
            _bypass(conn, False)
    by_model = defaultdict(list)
    for r in runs:
        by_model[r["model_id"]].append(r)
    month = _now() - timedelta(days=28)
    out = []
    for m in models:
        rs = by_model.get(m["_id"], [])
        last = rs[-1] if rs else None
        before = [r for r in rs if _ts(r["run_at"]) < month]
        out.append({"id": m["id"], "name": m["name"], "entities": m["entities"], "kind": m["kind"], "icon": m["icon"],
                    "icon_version": m["icon_version"],
                    "score": last["score"] if last else None, "completeness": last["completeness"] if last else None,
                    "measured_at": last["run_at"] if last else None, "summary": last["summary"] if last else None,
                    "month_ago": before[-1]["score"] if before else None,
                    "trend": [{"at": r["run_at"], "score": r["score"]} for r in rs[-30:]],
                    "by_type": latest_types.get(m["_id"]) or []})
    out.sort(key=lambda x: (x["score"] is None, float(x["score"]) if x["score"] is not None else 0))
    # the estate: entity-weighted averages of each model's latest measurement, and the same week by week
    measured = [x for x in out if x["score"] is not None]
    weight = sum(max(1, x["entities"]) for x in measured)

    def wavg(key):
        return round(sum(float(x[key]) * max(1, x["entities"]) for x in measured) / weight, 2) if weight else None
    sums = Counter()
    for x in measured:
        for k in ("incomplete", "failing", "errors", "stale", "orphans"):
            sums[k] += int((x["summary"] or {}).get(k) or 0)
    weeks = []
    if runs:
        start = _ts(runs[0]["run_at"])
        start = (start - timedelta(days=start.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        size = {m["_id"]: max(1, m["entities"]) for m in models}
        t = start
        while t <= _now() and len(weeks) < 104:
            end = t + timedelta(days=7)
            latest = {}
            for r in runs:
                if _ts(r["run_at"]) < end:
                    latest[r["model_id"]] = r
            if latest:
                w = sum(size.get(k, 1) for k in latest)
                weeks.append({"at": end.isoformat(), "score": round(sum(float(r["score"]) * size.get(k, 1) for k, r in latest.items()) / w, 2),
                              "models": len(latest)})
            t = end
    estate = {"score": wavg("score"), "completeness": wavg("completeness"), "models": len(out), "measured": len(measured),
              "entities": sum(x["entities"] for x in out), "trend": weeks, **sums,
              "month_ago": weeks[-5]["score"] if len(weeks) >= 5 else None}
    last_all = {}
    if every and allm:
        _bypass(conn, True)
        try:
            last_all = {r["model_id"]: r for r in _rows(conn, """SELECT DISTINCT ON (model_id) model_id, score, run_at
                                                                   FROM core.quality_runs WHERE model_id = ANY (:i)
                                                                  ORDER BY model_id, run_at DESC""", i=[m["_id"] for m in allm])}
        finally:
            _bypass(conn, False)
    scope = [{"id": m["id"], "name": m["name"], "kind": m["kind"], "lifecycle": m["lifecycle"], "icon": m["icon"],
              "icon_version": m["icon_version"],
              "score": (last_all.get(m["_id"]) or {}).get("score"), "measured_at": (last_all.get(m["_id"]) or {}).get("run_at"),
              "frozen": bool(m["is_locked"]) or m["lock_level"] == "content", "is_locked": bool(m["is_locked"]), "lock_level": m["lock_level"],
              "lock_reason": m["lock_reason"], "locked_by": m["locked_by"], "library_state": m["library_state"], "measured": m["measured"], "chosen": m["chosen"],
              "entities": m["entities"]} for m in allm] if every else []
    active = {r["m"]: r for r in _rows(conn, """SELECT DISTINCT ON (q.model_id) m.guid::text AS m, q.status, q.requested_at
                                                  FROM core.quality_requests q JOIN core.models m ON m.id = q.model_id
                                                 WHERE q.status IN ('queued', 'running') AND q.requested_at > now() - interval '2 hours'
                                                 ORDER BY q.model_id, q.requested_at DESC""")}
    for x in out:
        x["job"] = active.get(x["id"])
    return {"models": out, "estate": estate, "every": every, "scope": scope, "defaults": defaults(conn),
            "jobs": len(active),
            "bands": defaults(conn)["bands"]}


def set_scope(conn, user, models: list[str], measured: bool) -> dict:
    """Super Admins and IT Admins choose which models are measured; the choice stays (D242)."""
    from . import audit
    if not (perms.SUPER_ADMIN in user.roles or perms.IT_ADMIN in user.roles):
        raise EditError("Choosing which models are measured needs the Super Admin or IT Admin role.", 403)
    _bypass(conn, True)
    try:
        n = 0
        for g in models or []:
            r = _rows(conn, "SELECT id, name, lifecycle FROM core.models WHERE guid = CAST(:g AS uuid) AND NOT is_deleted", g=str(g))
            if not r:
                raise EditError(f"No model {g}.", 404)
            if measured and r[0]["lifecycle"] != "active":
                raise EditError(f"{r[0]['name']} is archived: archived models are never measured.", 409)
            conn.execute(text("""INSERT INTO core.quality_scope (model_id, measured, set_by) VALUES (:m, :v, :u)
                                 ON CONFLICT (model_id) DO UPDATE SET measured = EXCLUDED.measured, set_by = EXCLUDED.set_by,
                                     set_at = now()"""), {"m": r[0]["id"], "v": bool(measured), "u": user.username.lower()})
            n += 1
    finally:
        _bypass(conn, False)
    audit.record(conn, actor=user.username, action="quality.scope", object_type="model", object_id=",".join(map(str, models))[:200],
                 details={"measured": bool(measured), "models": n})
    return {"changed": n, "measured": bool(measured)}


# ---------------------------------------------------------------- changing settings and rules (approval, D239.5)
def _apply(conn, m: dict, kind: str, payload: dict, actor: str) -> None:
    if kind == "settings":
        conn.execute(text("""INSERT INTO core.quality_settings (model_id, stale_days, cron, weights, score_parts, bands,
                                                               modified_by, modified_at)
                             VALUES (:m, :s, :c, CAST(:w AS jsonb), CAST(:p AS jsonb), CAST(:b AS jsonb), :a, now())
                             ON CONFLICT (model_id) DO UPDATE SET stale_days = EXCLUDED.stale_days, cron = EXCLUDED.cron,
                                 weights = EXCLUDED.weights, score_parts = EXCLUDED.score_parts, bands = EXCLUDED.bands,
                                 modified_by = EXCLUDED.modified_by, modified_at = now()"""),
                     {"m": m["_id"], "s": payload.get("stale_days"), "c": payload.get("cron"),
                      "w": json.dumps(payload.get("weights") or {}),
                      "p": json.dumps(payload["score_parts"]) if payload.get("score_parts") else None,
                      "b": json.dumps(payload["bands"]) if payload.get("bands") else None, "a": actor})
    elif kind == "rule":
        r = payload
        conn.execute(text("""INSERT INTO core.quality_rules (model_id, code, name, kind, entity_type, spec, severity, enabled,
                                                            message, created_by, modified_by)
                             VALUES (:m, :code, :name, :kind, :t, CAST(:spec AS jsonb), :sev, :en, :msg, :a, :a)
                             ON CONFLICT (model_id, code) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind,
                                 entity_type = EXCLUDED.entity_type, spec = EXCLUDED.spec, severity = EXCLUDED.severity,
                                 enabled = EXCLUDED.enabled, message = EXCLUDED.message, modified_by = EXCLUDED.modified_by,
                                 modified_at = now()"""),
                     {"m": m["_id"], "code": r["code"], "name": r["name"], "kind": r["kind"], "t": r["entity_type"],
                      "spec": json.dumps(r["spec"]), "sev": r["severity"], "en": r["enabled"], "msg": r["message"], "a": actor})
    elif kind == "rule.delete":
        conn.execute(text("DELETE FROM core.quality_rules WHERE model_id = :m AND code = :c"),
                     {"m": m["_id"], "c": payload["code"]})


def _clean_settings(payload: dict) -> dict:
    out = {}
    sd = payload.get("stale_days")
    if sd not in (None, ""):
        sd = int(sd)
        if not 7 <= sd <= 3650:
            raise EditError("The stale period is 7 to 3650 days.")
        out["stale_days"] = sd
    else:
        out["stale_days"] = None
    cron = str(payload.get("cron") or "").strip()
    if cron:
        from . import backup_schedule as bs
        try:
            bs.parse(cron)
        except Exception as exc:  # noqa: BLE001
            raise EditError(f"The schedule is not a valid cron line: {exc}") from exc
    out["cron"] = cron or None
    w = payload.get("weights") or {}
    if not isinstance(w, dict):
        raise EditError("Weights are {entity type or *: {item: weight}}.")
    clean = {}
    for t, items in w.items():
        if not isinstance(items, dict):
            raise EditError("Weights are {entity type or *: {item: weight}}.")
        for item, val in items.items():
            if not re.match(r"^(attr:[A-Za-z0-9_ -]+|rel:[A-Za-z0-9_-]+|field:description)$", str(item)):
                raise EditError(f"{item!r} is not a weighted item: attr:<attribute code>, rel:any, rel:<relationship type "
                                "code> or field:description.")
            v = int(val)
            if not 0 <= v <= 10:
                raise EditError("A weight is 0 (left out) to 10.")
            clean.setdefault(str(t), {})[str(item)] = v
    out["weights"] = clean
    sp = payload.get("score_parts")
    if sp:
        if not isinstance(sp, dict) or set(sp) - set(SCORE_PARTS):
            raise EditError("The score's weights are completeness, rules and freshness.")
        try:
            sp = {k: int(sp.get(k) or 0) for k in SCORE_PARTS}
        except (TypeError, ValueError) as exc:
            raise EditError("The score's weights are whole numbers.") from exc
        if any(v < 0 for v in sp.values()) or sum(sp.values()) != 100:
            raise EditError(f"The score's weights add up to 100 (completeness, rules passed and fresh; 0 leaves one out); "
                            f"these add up to {sum(sp.values())}.")
    out["score_parts"] = sp or None
    b = payload.get("bands")
    if b:
        try:
            b = {"green": int(b["green"]), "amber": int(b["amber"])}
        except (KeyError, TypeError, ValueError) as exc:
            raise EditError("The colours need green from and amber from, as whole percentages.") from exc
        if not 0 < b["amber"] < b["green"] <= 100:
            raise EditError("Amber starts below green: 0 < amber < green <= 100 (red is below amber).")
    out["bands"] = b or None
    return out


DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def cron_text(c: str) -> str:
    """A schedule in words: every day, every <weekday> or the 1st of every month at a time, else the cron line."""
    m = re.match(r"^(\d+) (\d+) (\S+) \* (\S+)$", str(c or "").strip())
    if not m:
        return f"on the schedule {c}"
    at = f"{int(m.group(2)):02d}:{int(m.group(1)):02d}"
    if m.group(3) == "*" and m.group(4) == "*":
        return f"every day at {at}"
    if m.group(3) == "*" and re.fullmatch(r"[0-7]", m.group(4)):
        return f"every {DAY_NAMES[int(m.group(4)) % 7]} at {at}"
    if m.group(3) == "1" and m.group(4) == "*":
        return f"on the 1st of every month at {at}"
    return f"on the schedule {c}"


def _summary(p: dict) -> str:
    out = [f"Stale after {p.get('stale_days') or 'the inherited'} days",
           f"measured again {cron_text(p['cron'])}" if p.get("cron") else "schedule inherited"]
    sp = p.get("score_parts")
    out.append(f"score {sp['completeness']}% completeness, {sp['rules']}% rules passed, {sp['freshness']}% fresh" if sp
               else "score weights inherited")
    b = p.get("bands")
    out.append(f"green from {b['green']}, amber from {b['amber']}" if b else "colours inherited")
    if "weights" in p:
        out.append(f"weights for {', '.join(sorted(p['weights'])) or 'nothing (inherited)'}")
    return "; ".join(out)


def _super_admins(conn) -> list[str]:
    return [r["u"] for r in _rows(conn, """SELECT lower(username) AS u FROM core.known_users
                                            WHERE 'super-admin' = ANY (roles)""")]


def change(conn, model: Any, user, kind: str, payload: dict, note: str = "") -> dict:
    """A change to a model's quality settings or rules: a Super Admin's applies at once; a Model Admin's waits for a Super
    Admin's approval (D239.5) and the Super Admins are told."""
    from . import audit, notify
    m = repo.get_model(conn, model)
    if not is_model_admin(conn, user, m):
        raise EditError(f"Changing {m['name']}'s quality settings and rules needs the Model Admin role on it (or Super Admin).", 403)
    if kind == "settings":   # only what is given changes; the rest of the model's own settings stays
        own = settings(conn, m)["own"]
        keys = ("stale_days", "cron", "weights", "score_parts", "bands")
        payload = _clean_settings({**{k: own.get(k) for k in keys}, **{k: v for k, v in payload.items() if k in keys}})
        summary = _summary(payload)
    elif kind == "rule":
        payload = validate_rule(conn, m, payload)
        summary = f"Rule {payload['code']} {payload['name']} ({payload['kind']}, {payload['severity']}, {'on' if payload['enabled'] else 'off'})"
    elif kind == "rule.delete":
        code = str(payload.get("code") or "").strip().upper()
        if not _rows(conn, "SELECT 1 AS x FROM core.quality_rules WHERE model_id = :m AND code = :c", m=m["_id"], c=code):
            raise EditError(f"{m['name']} has no rule {code} of its own (an inherited rule is switched off with a rule of "
                            "the same code that is off).", 404)
        payload = {"code": code}
        summary = f"Delete rule {code}"
    else:
        raise EditError("Unknown change.")
    if perms.SUPER_ADMIN in user.roles:
        _apply(conn, m, kind, payload, user.username)
        queue_model(conn, m, user.username)
        audit.record(conn, actor=user.username, action=f"quality.{kind}", object_type="model", object_id=str(m["id"]),
                     details={"summary": summary})
        return {"applied": True, "summary": summary}
    row = _rows(conn, """INSERT INTO core.quality_changes (model_id, kind, payload, summary, note, requested_by)
                         VALUES (:m, :k, CAST(:p AS jsonb), :s, :n, :u) RETURNING guid::text AS id""",
                m=m["_id"], k=kind, p=json.dumps(payload), s=summary, n=(note or "")[:1000], u=user.username.lower())[0]
    notify.create(conn, kind="quality.approval", category="system", needs_action=True, model_id=m["_id"],
                  title=f"Approve a quality change to {m['name']}", body=f"{user.username} asks: {summary}. {note}".strip(),
                  link="#/admin/quality", actor=user.username, recipients=_super_admins(conn), ref_kind="quality_change")
    audit.record(conn, actor=user.username, action=f"quality.{kind}.request", object_type="model", object_id=str(m["id"]),
                 details={"summary": summary})
    return {"applied": False, "pending": row["id"], "summary": summary,
            "message": "Saved for approval: a Super Admin applies it (or not); you are told either way."}


def pending(conn, user) -> list[dict]:
    if perms.SUPER_ADMIN not in user.roles:
        raise EditError("Approving quality changes needs the Super Admin role.", 403)
    return _rows(conn, """SELECT c.guid::text AS id, m.guid::text AS model_id, m.name AS model, c.kind, c.summary, c.payload,
                                 c.note, c.requested_by, c.requested_at, c.status, c.decided_by, c.decided_at, c.decision_note
                            FROM core.quality_changes c JOIN core.models m ON m.id = c.model_id
                           ORDER BY c.status <> 'pending', c.requested_at DESC LIMIT 200""")


def decide(conn, user, change_id: str, approve: bool, note: str = "") -> dict:
    """A Super Admin approves (applies) or rejects a Model Admin's quality change; the requester is told."""
    from . import audit, notify
    if perms.SUPER_ADMIN not in user.roles:
        raise EditError("Approving quality changes needs the Super Admin role.", 403)
    rows = _rows(conn, """SELECT c.*, m.guid::text AS mguid FROM core.quality_changes c JOIN core.models m ON m.id = c.model_id
                           WHERE c.guid = CAST(:g AS uuid)""", g=str(change_id))
    if not rows:
        raise EditError("No such quality change.", 404)
    c = rows[0]
    if c["status"] != "pending":
        raise EditError(f"This change was {c['status']} already.", 409)
    m = repo.get_model(conn, c["mguid"])
    payload = c["payload"] if isinstance(c["payload"], dict) else json.loads(c["payload"])
    if approve:
        if c["kind"] == "rule":
            payload = validate_rule(conn, m, payload)
        _apply(conn, m, c["kind"], payload, c["requested_by"])
        queue_model(conn, m, user.username)
    conn.execute(text("""UPDATE core.quality_changes SET status = :s, decided_by = :u, decided_at = now(), decision_note = :n
                         WHERE id = :i"""), {"s": "approved" if approve else "rejected", "u": user.username.lower(),
                                             "n": (note or "")[:1000], "i": c["id"]})
    notify.create(conn, kind="quality.decided", category="system", model_id=m["_id"],
                  title=f"Your quality change to {m['name']} was {'approved' if approve else 'rejected'}",
                  body=f"{c['summary']}. {note}".strip(), link=f"#/metamodel/{m['id']}/quality", actor=user.username,
                  recipients=[c["requested_by"]])
    audit.record(conn, actor=user.username, action="quality.approve" if approve else "quality.reject", object_type="model",
                 object_id=str(m["id"]), details={"summary": c["summary"], "by": c["requested_by"]})
    return {"status": "approved" if approve else "rejected", "summary": c["summary"]}


# ---------------------------------------------------------------- seals and "still current" (D239.6)
def seal(conn, model: Any, user, entities: list[str], kind: str = "seal", note: str = "") -> dict:
    """Attest entities as correct (their responsible person, a Model Admin or a Super Admin) or mark them still current
    (a Model Admin or a Super Admin: one click for one or many)."""
    from . import audit
    m = repo.get_model(conn, model)
    if kind not in ("seal", "current"):
        raise EditError("Kind is seal or current.")
    admin = is_model_admin(conn, user, m)
    if kind == "current" and not admin:
        raise EditError("Marking entities still current needs the Model Admin role on the model.", 403)
    data = None if admin else load(conn, m)
    ids = []
    for g in entities or []:
        r = _rows(conn, "SELECT id, name FROM core.entities WHERE guid = CAST(:g AS uuid) AND model_id = :m AND NOT is_deleted",
                  g=str(g), m=m["_id"])
        if not r:
            raise EditError(f"No entity {g} in {m['name']}.", 404)
        if not admin:
            e = data["entities"][r[0]["id"]]
            vals = data["values"].get(e["id"], {})
            owner = next((v for k, v in vals.items() if k.lower() == "owner"), None)
            if user.username.lower() not in responsible(data, e, owner):
                raise EditError(f"Only the person responsible for {r[0]['name']} or a Model Admin attests it.", 403)
        ids.append(r[0]["id"])
    for i in ids:
        conn.execute(text("""INSERT INTO core.quality_seals (entity_id, model_id, kind, sealed_by, sealed_at, note)
                             VALUES (:e, :m, :k, :u, now(), :n)
                             ON CONFLICT (entity_id) DO UPDATE SET kind = EXCLUDED.kind, sealed_by = EXCLUDED.sealed_by,
                                 sealed_at = now(), note = EXCLUDED.note"""),
                     {"e": i, "m": m["_id"], "k": kind, "u": user.username.lower(), "n": (note or "")[:500]})
        conn.execute(text("DELETE FROM core.quality_told WHERE entity_id = :e AND problem IN ('stale', 'seal-broken', 'seal-expired')"),
                     {"e": i})
    audit.record(conn, actor=user.username, action=f"quality.{kind}", object_type="model", object_id=str(m["id"]),
                 details={"entities": len(ids)})
    queue_entities(str(m["id"]), [str(x) for x in entities or []])
    return {"done": len(ids), "kind": kind}


def unseal(conn, model: Any, user, entities: list[str]) -> dict:
    m = repo.get_model(conn, model)
    if not is_model_admin(conn, user, m):
        raise EditError("Removing seals needs the Model Admin role on the model.", 403)
    n = 0
    for g in entities or []:
        n += conn.execute(text("""DELETE FROM core.quality_seals s USING core.entities e WHERE e.id = s.entity_id
                                    AND e.guid = CAST(:g AS uuid) AND e.model_id = :m"""), {"g": str(g), "m": m["_id"]}).rowcount
    queue_entities(str(m["id"]), [str(x) for x in entities or []])
    return {"removed": n}


# ---------------------------------------------------------------- errors block commits (D239.8)
def commit_errors(conn, m: dict, entity_guids: set[str]) -> list[str]:
    """The error rules the committed entities now fail (empty: the commit may go ahead). Only quality rules of severity
    error count: the metamodel's own checks keep their behaviour (D48)."""
    if not entity_guids:
        return []
    cfg = settings(conn, m)
    if not any(r["enabled"] and r["severity"] == "error" for r in cfg["rules"]):
        return []
    ids = {r["id"] for r in _rows(conn, """SELECT id FROM core.entities WHERE model_id = :m AND NOT is_deleted
                                             AND guid = ANY (CAST(:g AS uuid[]))""", m=m["_id"], g=sorted(entity_guids))}
    if not ids:
        return []
    q = measure(conn, m, only=ids, metamodel_checks=False)
    return [f"{f['name']} ({f['display_id']}): {f['rule_name']}: {f['message']}" for f in q["findings"]
            if f["kind"] == "rule" and f.get("severity") == "error" and f.get("source") == "quality"]


# ---------------------------------------------------------------- telling people (as it happens, weekly)
TOLD_KINDS = {"incomplete", "rule", "stale", "seal-broken", "seal-expired"}


def _problem(f: dict) -> str | None:
    if f["kind"] == "incomplete":
        return "incomplete" if f.get("important") else None
    if f["kind"] == "rule":
        return f"rule:{f['rule']}"
    return f["kind"] if f["kind"] in TOLD_KINDS else None


def tell_new(conn, model: Any) -> int:
    """Tells each responsible person about problems of their entities that are new since they were last told (D239.3);
    a model's first measurement only records what is there (nobody is flooded). Problems that went away are forgotten,
    so they are told again if they come back. Returns how many people were told."""
    from . import notify
    m = model if isinstance(model, dict) and "_id" in model else repo.get_model(conn, model)
    q = measure(conn, m)
    first = not _rows(conn, "SELECT 1 AS x FROM core.quality_told WHERE model_id = :m LIMIT 1", m=m["_id"]) and \
        not _rows(conn, "SELECT 1 AS x FROM core.quality_runs WHERE model_id = :m LIMIT 1", m=m["_id"])
    gid = {r["g"]: r["id"] for r in _rows(conn, "SELECT guid::text AS g, id FROM core.entities WHERE model_id = :m", m=m["_id"])}
    now_set = {}
    for f in q["findings"]:
        p = _problem(f)
        if p and f["entity"] in gid:
            now_set[(gid[f["entity"]], p)] = f
    told = {(r["entity_id"], r["problem"]) for r in _rows(conn, "SELECT entity_id, problem FROM core.quality_told WHERE model_id = :m",
                                                           m=m["_id"])}
    gone = told - set(now_set)
    for e, p in gone:
        conn.execute(text("DELETE FROM core.quality_told WHERE entity_id = :e AND problem = :p"), {"e": e, "p": p})
    new = {k: v for k, v in now_set.items() if k not in told}
    per_person = defaultdict(list)
    for (e, p), f in new.items():
        for who in f["responsible"]:
            per_person[who].append(f)
        conn.execute(text("""INSERT INTO core.quality_told (entity_id, problem, model_id, told) VALUES (:e, :p, :m, :t)
                             ON CONFLICT DO NOTHING"""), {"e": e, "p": p, "m": m["_id"], "t": ",".join(f["responsible"])})
    if first:
        return 0
    for who, fs in per_person.items():
        ents = {f["entity"]: f for f in fs}
        lines = [f"• {f['name']} ({f['type_name']}): {f['message']}" for f in fs[:12]]
        notify.create(conn, kind="quality.problem", category="system", model_id=m["_id"],
                      title=f"{len(ents)} of your entities in {m['name']} need attention",
                      body="\n".join(lines) + ("\n..." if len(fs) > 12 else ""), link=f"#/metamodel/{m['id']}/quality",
                      actor="system", recipients=[who])
    return len(per_person)


def weekly_digest(conn) -> int:
    """Once a week, each responsible person gets one notification listing their open problems in every model (D239.3)."""
    from . import notify
    per = defaultdict(lambda: defaultdict(Counter))
    links = {}
    for m in _rows(conn, """SELECT DISTINCT ON (r.model_id) r.model_id, r.findings, m.guid::text AS g, m.name
                              FROM core.quality_runs r JOIN core.models m ON m.id = r.model_id AND NOT m.is_deleted
                             ORDER BY r.model_id, r.run_at DESC"""):
        fs = m["findings"] if isinstance(m["findings"], list) else json.loads(m["findings"] or "[]")
        links[m["name"]] = m["g"]
        for f in fs:
            p = _problem(f)
            if not p:
                continue
            for who in f.get("responsible") or []:
                per[who][m["name"]][p.split(":")[0]] += 1
    for who, models in per.items():
        total = sum(sum(c.values()) for c in models.values())
        body = "\n".join(f"• {name}: " + ", ".join(f"{n} {k.replace('-', ' ')}" for k, n in c.most_common())
                         for name, c in models.items())
        first = next(iter(models))
        notify.create(conn, kind="quality.digest", category="system", title=f"Your weekly data quality digest: {total} "
                      f"thing{'s' if total != 1 else ''} to look at in {len(models)} model{'s' if len(models) != 1 else ''}",
                      body=body, link=f"#/metamodel/{links[first]}/quality", actor="system", recipients=[who])
    return len(per)


# ---------------------------------------------------------------- the schedule (the job runner, every minute)
def due(conn, at: datetime) -> list[dict]:
    """The models whose quality is due on their schedule now (once per matching minute)."""
    from . import backup_schedule as bs
    out = []
    _bypass(conn, True)
    try:
        models = _rows(conn, f"""SELECT m.id, m.guid::text AS g, m.name FROM core.models m
                                  WHERE NOT m.is_deleted AND {MEASURED_SQL}""")
    finally:
        _bypass(conn, False)
    for m in models:
        try:
            cfg = settings(conn, {"_id": m["id"], "id": m["g"], "name": m["name"]})
            if bs.matches(cfg["cron"], at):
                last = _rows(conn, "SELECT max(run_at) AS t FROM core.quality_runs WHERE model_id = :m AND trigger = 'scheduled'",
                             m=m["id"])[0]["t"]
                if not last or _ts(last) < _now() - timedelta(minutes=50):
                    out.append(m)
        except Exception:  # noqa: BLE001 - one model's settings never stop the others
            continue
    return out


def changed_since(conn, since: datetime) -> list[dict]:
    """Project models whose content changed since a moment (for telling people as it happens)."""
    _bypass(conn, True)
    try:
        return _rows(conn, f"""SELECT m.id, m.guid::text AS g, m.name FROM core.models m
                               WHERE NOT m.is_deleted AND {MEASURED_SQL} AND (
                                     EXISTS (SELECT 1 FROM core.entities e WHERE e.model_id = m.id AND e.modified_at > :t)
                                  OR EXISTS (SELECT 1 FROM core.attribute_values v WHERE v.model_id = m.id AND v.modified_at > :t)
                                  OR EXISTS (SELECT 1 FROM core.relationships r WHERE r.model_id = m.id AND r.modified_at > :t))""",
                     t=since)
    finally:
        _bypass(conn, False)


def preview_rule(conn, model: Any, rule: dict) -> dict:
    """What a rule would find in the model now, without keeping it: how many entities fail it, and the first of them."""
    m = repo.get_model(conn, model)
    r = validate_rule(conn, m, rule)
    data = load(conn, m)
    names_type, names_model = Counter(), Counter()
    for e in data["entities"].values():
        n = (e["name"] or "").strip().lower()
        names_type[(e["entity_type_id"], n)] += 1
        names_model[n] += 1
    checked, failing = 0, []
    for e in data["entities"].values():
        t = data["types"].get(e["entity_type_id"])
        if not t or t["code"].lower() != r["entity_type"].lower():
            continue
        checked += 1
        names = names_model if r["spec"].get("scope") == "model" else \
            Counter({k[1]: v for k, v in names_type.items() if k[0] == e["entity_type_id"]})
        why = check_rule(data, r, e, names)
        if why:
            failing.append({"entity": e["guid"], "display_id": e["display_id"], "name": e["name"], "message": why})
    return {"rule": r, "checked": checked, "failing": len(failing), "examples": failing[:25]}


# ---------------------------------------------------------------- one entity, one type, every type: live (D246)
def _find_entity(conn, m: dict, entity: str) -> dict:
    r = _rows(conn, """SELECT id, guid::text AS guid, name, display_id, entity_type_id, status_code FROM core.entities
                        WHERE model_id = :m AND NOT is_deleted AND (guid::text = :e OR display_id = :e)""", m=m["_id"], e=str(entity))
    if not r:
        raise EditError(f"No entity {entity} in {m['name']}.", 404)
    return r[0]


def _reasons(p: dict, d: dict) -> dict:
    """Per field (attribute code, description or name; '*' for the whole entity): why it lowers data quality."""
    out = defaultdict(list)
    for item, weight in d["missing"]:
        kind, _, code = item.partition(":")
        if kind == "rel":
            out["*"].append({"kind": "missing", "item": item, "weight": weight,
                                   "message": "Has no relationship" if code == "any" else f"Has no {code} relationship"})
            continue
        out[code].append({"kind": "missing", "item": item, "weight": weight,
                          "message": f"Missing: counts {weight} towards data quality"
                                     + (" (important)" if weight >= IMPORTANT else "")})
    for f in d["problems"]:
        out[f.get("field") or "*"].append({"kind": "rule", "rule": f["rule"], "severity": f["severity"],
                                                  "message": f"{f['name']}: {f['message']}" if f["source"] == "quality" else f["message"]})
    for item, r in d["exempt"].items():
        out[item.partition(":")[2]].append({"kind": "not-applicable", "item": item, "id": r["id"], "reason": r["reason"],
                                            "by": r["requested_by"], "message": f"Not applicable: {r['reason']}"})
    for item, r in d["pending"].items():
        out[item.partition(":")[2]].append({"kind": "not-applicable-pending", "item": item, "id": r["id"], "reason": r["reason"],
                                            "by": r["requested_by"],
                                            "message": f"Not applicable, waiting for a Model Admin: {r['reason']}"})
    for item, r in d.get("rejected", {}).items():
        out[item.partition(":")[2]].append({"kind": "not-applicable-rejected", "item": item, "id": r["id"], "reason": r["reason"],
                                            "by": r["decided_by"],
                                            "message": f"Not applicable was rejected by {r['decided_by']}"
                                                       + (f": {r['decision_note']}" if r["decision_note"] else "")})
    if p["stale"]:
        out["*"].append({"kind": "stale", "message": f"Not changed or confirmed since {d['fresh_at'][:10]}"})
    if p["seal"] in ("broken", "expired"):
        out["*"].append({"kind": f"seal-{p['seal']}", "message": "The quality seal was broken by a later change"
                               if p["seal"] == "broken" else "The quality seal has expired"})
    return dict(out)


def _agg(rows: list[dict], parts: dict) -> dict:
    n = len(rows)
    if not n:
        return {"entities": 0, "score": None, "completeness": None, "passing": None, "fresh": None}
    comp = sum(r["completeness"] for r in rows) / n
    passing = 100.0 * sum(1 for r in rows if not r["failing"]) / n
    fresh = 100.0 * sum(1 for r in rows if not r["stale"]) / n
    score = (comp * parts["completeness"] + passing * parts["rules"] + fresh * parts["freshness"]) / (sum(parts.values()) or 100)
    return {"entities": n, "score": round(score, 2), "completeness": round(comp, 2), "passing": round(passing, 2),
            "fresh": round(fresh, 2), "failing": sum(1 for r in rows if r["failing"]), "stale": sum(1 for r in rows if r["stale"]),
            "incomplete": sum(1 for r in rows if r["completeness"] < 100)}


def entity_quality(conn, model: Any, entity: str) -> dict:
    """One entity's data quality now: its score and parts, and per field why it lowers it (shown while editing)."""
    m = repo.get_model(conn, model)
    e = _find_entity(conn, m, entity)
    q = measure(conn, m, only={e["id"]})
    if not q["entities"]:
        raise EditError("Retired: not part of data quality." if e.get("status_code") == "retired" else
                        "This entity's type is not measured.", 404)
    p = q["entities"][0]
    cfg = q["_cfg"]
    return {"entity": p["entity"], "name": p["name"], "score": p["score"], "completeness": p["completeness"],
            "failing": p["failing"], "errors": p["errors"], "stale": p["stale"], "seal": p["seal"],
            "responsible": p["responsible"], "fields": _reasons(p, q["_details"][p["entity"]]),
            "parts": cfg["score_parts"], "bands": cfg["bands"], "stale_days": cfg["stale_days"]}


def type_quality(conn, model: Any, entity_type: str) -> dict:
    """One entity type's data quality as last calculated (D248): its overall score and each entity's, with the fields
    that lower it (grids), and when it was calculated."""
    m = repo.get_model(conn, model)
    t = _rows(conn, """SELECT id, code, name FROM core.entity_types WHERE model_id = :m AND NOT is_deleted
                        AND (guid::text = :t OR code = :t OR lower(name) = lower(:t))""", m=m["_id"], t=str(entity_type))
    if not t:
        raise EditError(f"No entity type {entity_type} in {m['name']}.", 404)
    t = t[0]
    cfg = settings(conn, m)
    s = stored(conn, m, t["code"])
    rows = [_j(r["row"]) for r in s["rows"]]
    return {"type": t["code"], "name": t["name"], "summary": _agg(rows, cfg["score_parts"]), "bands": cfg["bands"],
            "calculated_from": s["oldest"], "calculated_to": s["newest"],
            "entities": {r["entity"]: {**{k: _j(r["row"]).get(k) for k in ("score", "completeness", "failing", "stale")},
                                       "fields": _j(r["fields"])} for r in s["rows"]}}


def type_scores(conn, model: Any) -> dict:
    """Every entity type's overall data quality as last calculated (D248), with when."""
    m = repo.get_model(conn, model)
    cfg = settings(conn, m)
    s = stored(conn, m)
    by = defaultdict(list)
    for r in s["rows"]:
        row = _j(r["row"])
        by[(row["type"], row["type_name"])].append(row)
    rows = [_j(r["row"]) for r in s["rows"]]
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "score": _agg(rows, cfg["score_parts"])["score"],
            "bands": cfg["bands"], "calculated_from": s["oldest"], "calculated_to": s["newest"],
            "types": sorted(({"type": k[0], "name": k[1], **_agg(v, cfg["score_parts"])} for k, v in by.items()),
                            key=lambda r: (r["score"] is None, r["score"] or 0))}


# ---------------------------------------------------------------- "not applicable" on one entity (D246)
def _may_edit(conn, user, m: dict) -> bool:
    return perms.SUPER_ADMIN in user.roles or bool(set(_model_roles(conn, user, m)) & perms.MODEL_PERMISSIONS["model.content"])


def exemptions(conn, m: dict, status: str = "pending") -> list[dict]:
    return _rows(conn, """SELECT x.guid::text AS id, e.guid::text AS entity, e.display_id, e.name, x.item, x.reason, x.status,
                                 x.requested_by, x.requested_at, x.decided_by, x.decided_at, x.decision_note
                            FROM core.quality_exemptions x JOIN core.entities e ON e.id = x.entity_id
                           WHERE x.model_id = :m AND (:s = '' OR x.status = :s) ORDER BY x.requested_at DESC LIMIT 500""",
                 m=m["_id"], s=status or "")


def request_exemption(conn, model: Any, user, entity: str, item: str, reason: str) -> dict:
    """Marks an item not applicable on one entity: anyone who may edit it asks, with a reason; it counts once a Model Admin
    of the model approves (they are told); a Model Admin's own applies at once (D246)."""
    from . import audit, notify
    m = repo.get_model(conn, model)
    if not _may_edit(conn, user, m):
        raise EditError(f"Marking a field not applicable needs a role that edits {m['name']}'s content.", 403)
    e = _find_entity(conn, m, entity)
    item = str(item or "").strip()
    if not re.fullmatch(r"attr:[A-Za-z0-9_ -]+|field:description", item):
        raise EditError("Only an attribute (attr:<code>) or the description can be marked not applicable.")
    reason = str(reason or "").strip()
    if not reason:
        raise EditError("Say why it does not apply (for example: this application has no vendor, it was built in house).")
    admin = is_model_admin(conn, user, m)
    if _rows(conn, """SELECT 1 AS x FROM core.quality_exemptions WHERE entity_id = :e AND item = :i
                        AND status IN ('pending', 'approved')""", e=e["id"], i=item):
        raise EditError(f"{item.partition(':')[2]} is already marked not applicable on {e['name']} (or waiting).", 409)
    try:
        row = _rows(conn, """INSERT INTO core.quality_exemptions (model_id, entity_id, item, reason, status, requested_by,
                                                                  decided_by, decided_at)
                             VALUES (:m, :e, :i, :r, :s, :u, CASE WHEN :a THEN :u END, CASE WHEN :a THEN now() END)
                             RETURNING guid::text AS id""",
                    m=m["_id"], e=e["id"], i=item, r=reason[:500], s="approved" if admin else "pending",
                    u=user.username.lower(), a=admin)[0]
    except Exception as exc:  # the unique index: already asked or approved
        raise EditError(f"{item.partition(':')[2]} is already marked not applicable on {e['name']} (or waiting).", 409) from exc
    label = item.partition(":")[2]
    if not admin:
        admins = [r["u"] for r in _rows(conn, """SELECT lower(username) AS u FROM core.model_users
                                                  WHERE model_id = :m AND role = 'model-admin'""", m=m["_id"])] or _super_admins(conn)
        notify.create(conn, kind="quality.not_applicable", category="system", needs_action=True, model_id=m["_id"],
                      title=f"Approve: {label} not applicable on {e['name']}", body=f"{user.username}: {reason}",
                      link=f"#/metamodel/{m['id']}/quality", actor=user.username, recipients=admins, ref_kind="quality_exemption")
    audit.record(conn, actor=user.username, action="quality.not_applicable" + ("" if admin else ".request"),
                 object_type="entity", object_id=e["guid"], details={"item": item, "reason": reason})
    queue_entities(str(m["id"]), [e["guid"]])
    return {"id": row["id"], "status": "approved" if admin else "pending",
            "message": f"{label} is not applicable on {e['name']}." if admin else
            f"Asked: a Model Admin of {m['name']} approves it (you are told)."}


def decide_exemption(conn, model: Any, user, exemption_id: str, decision: str, note: str = "") -> dict:
    """A Model Admin approves or rejects a 'not applicable', or withdraws an approved one; the asker withdraws their own."""
    from . import audit, notify
    m = repo.get_model(conn, model)
    r = _rows(conn, """SELECT x.*, e.name AS ename FROM core.quality_exemptions x JOIN core.entities e ON e.id = x.entity_id
                        WHERE x.guid = CAST(:g AS uuid) AND x.model_id = :m""", g=str(exemption_id), m=m["_id"])
    if not r:
        raise EditError("No such request.", 404)
    x = r[0]
    admin = is_model_admin(conn, user, m)
    if decision not in ("approve", "reject", "withdraw"):
        raise EditError("approve, reject or withdraw.")
    if decision == "withdraw":
        if not admin and x["requested_by"] != user.username.lower():
            raise EditError("Only the person who asked or a Model Admin withdraws it.", 403)
        if x["status"] not in ("pending", "approved"):
            raise EditError(f"It was {x['status']} already.", 409)
    else:
        if not admin:
            raise EditError(f"Approving needs the Model Admin role on {m['name']}.", 403)
        if x["status"] != "pending":
            raise EditError(f"It was {x['status']} already.", 409)
    status = {"approve": "approved", "reject": "rejected", "withdraw": "withdrawn"}[decision]
    conn.execute(text("""UPDATE core.quality_exemptions SET status = :s, decided_by = :u, decided_at = now(), decision_note = :n
                         WHERE id = :i"""), {"s": status, "u": user.username.lower(), "n": (note or "")[:500], "i": x["id"]})
    label = x["item"].partition(":")[2]
    if x["requested_by"] != user.username.lower():
        notify.create(conn, kind="quality.not_applicable.decided", category="system", model_id=m["_id"],
                      title=f"{label} not applicable on {x['ename']}: {status}", body=note or x["reason"],
                      link=f"#/metamodel/{m['id']}/quality", actor=user.username, recipients=[x["requested_by"]])
    audit.record(conn, actor=user.username, action=f"quality.not_applicable.{decision}", object_type="model",
                 object_id=str(m["id"]), details={"item": x["item"], "entity": x["ename"]})
    eg = _rows(conn, "SELECT guid::text AS g FROM core.entities WHERE id = :i", i=x["entity_id"])
    queue_entities(str(m["id"]), [eg[0]["g"]] if eg else [])
    return {"status": status}


# ---------------------------------------------------------------- leaving an attribute out for the whole model (D246)
def leave_out(conn, model: Any, user, item: str, entity_type: str = "*", include: bool = False) -> dict:
    """A Model Admin leaves an item (an attribute or the description) out of data quality for their whole model, for every
    entity type that has it (entity_type '*') or one type; it applies at once (owner, 6 Nov 2026) and the Super Admins are
    told. include=True puts it back (as inherited)."""
    from . import audit, notify
    m = repo.get_model(conn, model)
    if not is_model_admin(conn, user, m):
        raise EditError(f"Leaving a field out of data quality needs the Model Admin role on {m['name']}.", 403)
    item = str(item or "").strip()
    if not re.fullmatch(r"attr:[A-Za-z0-9_ -]+|field:description", item):
        raise EditError("Only an attribute (attr:<code>) or the description can be left out.")
    scope = str(entity_type or "*").strip() or "*"
    own = settings(conn, m)["own"]
    weights = {k: dict(v) for k, v in (own.get("weights") or {}).items()}
    if include:
        (weights.get(scope) or {}).pop(item, None)
        weights = {k: v for k, v in weights.items() if v}
    else:
        weights.setdefault(scope, {})[item] = 0
    payload = _clean_settings({**{k: own.get(k) for k in ("stale_days", "cron", "score_parts", "bands")}, "weights": weights})
    _apply(conn, m, "settings", payload, user.username)
    label = item.partition(":")[2]
    where = "every entity type" if scope == "*" else scope
    summary = f"{label} {'counts again' if include else 'left out of data quality'} in {m['name']} ({where})"
    if perms.SUPER_ADMIN not in user.roles:
        notify.create(conn, kind="quality.left_out", category="system", model_id=m["_id"], title=summary,
                      body=f"By {user.username}, a Model Admin of {m['name']}.", link=f"#/metamodel/{m['id']}/quality",
                      actor=user.username, recipients=_super_admins(conn))
    audit.record(conn, actor=user.username, action="quality.leave_out" + (".undo" if include else ""), object_type="model",
                 object_id=str(m["id"]), details={"item": item, "entity_type": scope})
    queue_model(conn, m, user.username)
    return {"applied": True, "summary": summary}


# ---------------------------------------------------------------- deciding many at once, and asking again
def decide_exemptions(conn, model: Any, user, ids: list[str], decision: str, note: str = "") -> dict:
    """Approve or reject many 'not applicable' requests in one go (a Model Admin); each asker is told."""
    done, failed = [], []
    for i in ids or []:
        try:
            decide_exemption(conn, model, user, str(i), decision, note)
            done.append(str(i))
        except EditError as exc:
            failed.append({"id": str(i), "why": str(exc)})
    return {"decided": len(done), "failed": failed, "status": {"approve": "approved", "reject": "rejected"}.get(decision, decision)}


def decide_many(conn, user, ids: list[str], approve: bool, note: str = "") -> dict:
    """A Super Admin approves or rejects many Model Admins' quality changes in one go."""
    done, failed = 0, []
    for i in ids or []:
        try:
            decide(conn, user, str(i), approve, note)
            done += 1
        except EditError as exc:
            failed.append({"id": str(i), "why": str(exc)})
    return {"decided": done, "failed": failed}


def resubmit_change(conn, user, change_id: str, note: str = "", payload: dict | None = None) -> dict:
    """Asks again for a rejected quality change (the same, or changed with payload), with a new note: it waits for a
    Super Admin again."""
    r = _rows(conn, """SELECT c.*, m.guid::text AS mguid FROM core.quality_changes c JOIN core.models m ON m.id = c.model_id
                        WHERE c.guid = CAST(:g AS uuid)""", g=str(change_id))
    if not r:
        raise EditError("No such quality change.", 404)
    c = r[0]
    if c["status"] != "rejected":
        raise EditError(f"Only a rejected change is asked for again; this one is {c['status']}.", 409)
    if c["requested_by"] != user.username.lower() and perms.SUPER_ADMIN not in user.roles:
        raise EditError("Only the person who asked can ask again.", 403)
    p = payload if payload is not None else (c["payload"] if isinstance(c["payload"], dict) else json.loads(c["payload"]))
    if c["kind"] == "rule.delete":
        p = {"code": p.get("code")}
    conn.execute(text("UPDATE core.quality_changes SET status = 'withdrawn' WHERE id = :i"), {"i": c["id"]})
    return change(conn, c["mguid"], user, c["kind"], p, note or f"Asked again: {c['note']}".strip())



def queue_model(conn, m: dict, by: str) -> None:
    """A change that affects every entity (a field left out, settings or a rule approved): the whole model is measured
    again in the background (D245, D248)."""
    class _Who:
        username = by or "system"
        roles = ()
    try:
        r = request_run(conn, m, _Who())
        if r["new"]:
            from .jobs import app as jobs_app
            from .jobs import quality_measure
            with jobs_app.open():
                quality_measure.configure(schedule_in={"seconds": 3}).defer(request_id=r["id"])
    except Exception:  # noqa: BLE001 - no job runner: the next scheduled measurement catches up
        pass



# ---------------------------------------------------------------- recheck from the grids and tables (owner, 6 Nov 2026)
def recheck_entity(conn, model: Any, entity: str) -> dict:
    """Recheck one entity now (a single entity is checked at once, D248) and store the result, so its row shows it."""
    m = repo.get_model(conn, model)
    e = _find_entity(conn, m, entity)
    q = measure(conn, m, only={e["id"]})
    _store(conn, m, q, {e["id"]})
    if not q["entities"]:
        return {"entity": e["guid"], "retired": True}
    p = q["entities"][0]
    return {"entity": p["entity"], "score": p["score"], "completeness": p["completeness"], "failing": p["failing"],
            "stale": p["stale"], "fields": _reasons(p, q["_details"][p["entity"]]), "bands": q["_cfg"]["bands"]}


def recheck_type(conn, model: Any, entity_type: str) -> dict:
    """Recheck every entity of a type: a background job (D248); without a job runner, at once."""
    m = repo.get_model(conn, model)
    t = _rows(conn, """SELECT id, code, name FROM core.entity_types WHERE model_id = :m AND NOT is_deleted
                        AND (guid::text = :t OR code = :t OR lower(name) = lower(:t))""", m=m["_id"], t=str(entity_type))
    if not t:
        raise EditError(f"No entity type {entity_type} in {m['name']}.", 404)
    guids = [r["g"] for r in _rows(conn, """SELECT guid::text AS g FROM core.entities WHERE model_id = :m
                                              AND entity_type_id = :t AND NOT is_deleted""", m=m["_id"], t=t[0]["id"])]
    if queue_entities(str(m["id"]), guids, delay=0):
        return {"queued": len(guids), "background": True,
                "message": f"Rechecking {len(guids)} {t[0]['name']} entities in the background; the rows update when done."}
    n = refresh_entities(conn, m, guids)
    return {"queued": n, "background": False, "message": f"{n} {t[0]['name']} entities rechecked."}
