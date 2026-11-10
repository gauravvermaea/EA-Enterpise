"""Validation rules: what is missing or wrong in an entity, as warnings.

Rules come from the model's metamodel (core.validation_rules, plus the "required" flag of each
attribute in core.item_attributes). Phase 2 shows the results; from phase 6 they are checked when
values are saved. A failed rule never blocks a save (decision D48): the value is saved with an
override flag and its details (rule, severity, who, when, reason), and the warning stays visible
until someone fixes it.

Pure Python, no database: eax.repository loads the rows and calls evaluate().

Every rule row has: rule_type_code, field_name (a built-in field such as name) or attribute_code
(an attribute), param1, param2, severity (error or warning) and message. Rule types:
  mandatory     a value is required
  min_length    text at least param1 characters      max_length  text at most param1 characters
  min_value     number at least param1               max_value   number at most param1
  range         number from param1 to param2         regex       text matches param1
  date_range    date from param1 to param2           date_order  date after attribute param1
  required_if   required when attribute param1 has value param2
  list          the value is one of the pick list's values
  entity_ref    the value links to an entity of type param1
  unique        no other entity of the same type has this value
  has_relationship  (on the built-in field "relationships") at least one relationship of type param1
                (name or code; empty: any) to or from an entity of type param2 (empty: any), D113
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

BUILT_IN = {"name": "Name", "description": "Description", "display_id": "Display ID", "relationships": "Relationships"}


def _same(a: Any, *names: Any) -> bool:
    a = str(a or "").strip().lower()
    return any(a == str(n or "").strip().lower() for n in names)


def matching_relationships(rule: dict, relationships: Iterable[dict]) -> list[dict]:
    """The entity's relationships a has_relationship rule asks for: of type param1 (name or code;
    empty: any) with an entity of type param2 at the other end (name or code; empty: any)."""
    p1, p2 = str(rule.get("param1") or "").strip(), str(rule.get("param2") or "").strip()
    return [r for r in relationships or []
            if (not p1 or _same(p1, r.get("type"), r.get("type_code")))
            and (not p2 or _same(p2, r.get("other_type"), r.get("other_type_code")))]


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _missing(a: dict) -> bool:
    """A required attribute with no value; a Link (D418) needs at least one link with an address."""
    if a.get("data_type") == "url":
        from . import links
        return not links.parse(a.get("value"))
    return _empty(a.get("value"))


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        return None


def _fmt(n: Decimal | None) -> str:
    return "" if n is None else format(n.normalize(), "f")


def check(rule: dict, value: Any, values: dict[str, Any], duplicate: bool) -> bool:
    """True when the rule passes. A rule about the value's content passes when there is no value
    (missing values are the business of mandatory, required_if and the required flag)."""
    kind = rule["rule_type_code"]
    p1, p2 = rule.get("param1"), rule.get("param2")
    if kind == "has_relationship":
        return bool(matching_relationships(rule, value))
    if kind == "mandatory":
        return not _empty(value)
    if kind == "required_if":
        other = values.get(str(p1 or "").lower())
        applies = other is not None and str(other).strip().lower() == str(p2 or "").strip().lower()
        return not applies or not _empty(value)
    if _empty(value):
        return True
    if kind in ("min_length", "max_length"):
        limit = _number(p1)
        if limit is None:
            return True
        return len(str(value)) >= limit if kind == "min_length" else len(str(value)) <= limit
    if kind in ("min_value", "max_value", "range"):
        n = _number(value)
        if n is None:
            return False
        low = _number(p1) if kind in ("min_value", "range") else None
        high = _number(p1) if kind == "max_value" else _number(p2) if kind == "range" else None
        return (low is None or n >= low) and (high is None or n <= high)
    if kind == "regex":
        try:
            return re.search(str(p1), str(value)) is not None
        except re.error:
            return True  # a broken pattern is the metamodel's problem, not the entity's
    if kind == "date_range":
        d = _date(value)
        if d is None:
            return False
        low, high = _date(p1), _date(p2)
        return (low is None or d >= low) and (high is None or d <= high)
    if kind == "date_order":
        d, other = _date(value), _date(values.get(str(p1 or "").lower()))
        return d is None or other is None or d > other
    if kind == "list":
        allowed = rule.get("allowed_values") or []
        return not allowed or str(value) in allowed
    if kind == "entity_ref":
        ref_type = rule.get("ref_type")
        return ref_type is None or str(ref_type).lower() in {str(p1 or "").lower()}
    if kind == "unique":
        return not duplicate
    return True  # a rule type this version does not know: never a false alarm


def default_message(rule: dict, label: str) -> str:
    kind, p1, p2 = rule["rule_type_code"], rule.get("param1"), rule.get("param2")
    return {
        "mandatory": f"{label} is required",
        "required": f"{label} is required",
        "required_if": f"{label} is required when {p1} is {p2}",
        "min_length": f"{label} must be at least {p1} characters",
        "max_length": f"{label} must be {p1} characters or fewer",
        "min_value": f"{label} must be at least {p1}",
        "max_value": f"{label} must be at most {p1}",
        "range": f"{label} must be from {p1} to {p2}",
        "regex": f"{label} does not match the expected pattern",
        "date_range": f"{label} must be from {p1} to {p2}",
        "date_order": f"{label} must be after {p1}",
        "list": f"{label} is not one of the allowed values",
        "entity_ref": f"{label} must link to a {p1}",
        "unique": f"Another entity of this type has the same {label.lower()}",
        "has_relationship": "Needs a " + (f"{p1} relationship" if p1 else "relationship")
                            + (f" to or from a {p2}" if p2 else ""),
    }.get(kind, f"{label} breaks rule {kind}")


def evaluate(entity: dict, attributes: Iterable[dict], rules: Iterable[dict],
             duplicate_name: bool = False) -> list[dict]:
    """The warnings for one entity.

    entity:      name, description, display_id
    attributes:  every attribute of its type: code, name, is_required, value (typed: str, Decimal,
                 date, bool or None), pick_list_values (list), ref_type (type code of a linked entity)
    rules:       the rules that apply to its type (see the module docstring)
    Returns one dict per failure: field (label), code (attribute code or built-in field), rule,
    severity, message. Errors first, then warnings, in attribute order.
    """
    attributes = list(attributes)
    by_code = {a["code"].lower(): a for a in attributes}
    values = {a["code"].lower(): a.get("value") for a in attributes}
    out: list[dict] = []

    def add(code: str, label: str, rule: dict, severity: str, message: str | None):
        out.append({"field": label, "code": code, "rule": rule["rule_type_code"], "severity": severity,
                    "message": message or default_message(rule, label)})

    for a in attributes:  # the metamodel's "required" flag on the attribute
        if a.get("is_required") and _missing(a):
            add(a["code"], a["name"], {"rule_type_code": "required"}, "error", None)
        if a.get("pick_list_values") and not _empty(a.get("value")) \
                and str(a["value"]) not in a["pick_list_values"]:
            add(a["code"], a["name"], {"rule_type_code": "list"}, "warning",
                f"{a['name']} \"{a['value']}\" is not one of the pick list values")

    for rule in rules:
        field = (rule.get("field_name") or "").lower()
        if field:
            label, value, code = BUILT_IN.get(field, field.title()), entity.get(field), field
        else:
            a = by_code.get(str(rule.get("attribute_code") or "").lower())
            if a is None:
                continue  # the rule is about an attribute this type does not have
            if rule["rule_type_code"] == "mandatory" and a.get("is_required"):
                continue  # already reported by the required flag
            label, value, code = a["name"], a.get("value"), a["code"]
            rule = {**rule, "allowed_values": a.get("pick_list_values"), "ref_type": a.get("ref_type")}
        if not check(rule, value, values, duplicate_name):
            add(code, label, rule, rule.get("severity") or "warning", rule.get("message"))

    order = {a["code"].lower(): i for i, a in enumerate(attributes)}
    out.sort(key=lambda w: (w["severity"] != "error", order.get(w["code"].lower(), -1)))
    return out


def summary(warnings: list[dict]) -> dict:
    return {"errors": sum(1 for w in warnings if w["severity"] == "error"),
            "warnings": sum(1 for w in warnings if w["severity"] != "error")}


# what each rule type checks, for a rule that passed or did not apply
RULE_NAMES = {
    "required": "Required (metamodel)", "mandatory": "Mandatory", "required_if": "Required when",
    "min_length": "Minimum length", "max_length": "Maximum length", "min_value": "Minimum value",
    "max_value": "Maximum value", "range": "Range", "regex": "Pattern", "date_range": "Date range",
    "date_order": "Date order", "list": "Pick list value", "entity_ref": "Links to type", "unique": "Unique",
    "has_relationship": "Has relationship",
}
_ABOUT_CONTENT = {"min_length", "max_length", "min_value", "max_value", "range", "regex", "date_range",
                  "date_order", "list", "entity_ref"}


def results(entity: dict, attributes: Iterable[dict], rules: Iterable[dict],
            duplicate_name: bool = False) -> list[dict]:
    """Every check applied to one entity, passed, failed or not applicable (D113): the metamodel's
    required flag and pick lists on its attributes, and every validation rule for its type. Same rules
    and arguments as evaluate(); one dict per check: field, code, rule, rule_name, checks (what the rule
    asks), severity, status (passed, failed, not_applicable), message (why it failed or did not apply),
    value (as displayed)."""
    attributes = list(attributes)
    by_code = {a["code"].lower(): a for a in attributes}
    values = {a["code"].lower(): a.get("value") for a in attributes}
    out: list[dict] = []

    def shown(v):
        if isinstance(v, list):
            return None
        if _empty(v):
            return None
        if isinstance(v, Decimal):
            return _fmt(v)
        return str(v)

    def add(code, label, rule, severity, status, message, value):
        kind = rule["rule_type_code"]
        out.append({"field": label, "code": code, "rule": kind, "rule_name": RULE_NAMES.get(kind, kind),
                    "checks": default_message(rule, label).replace(" is not one of the allowed values",
                                                                    " is one of the pick list's values")
                    .replace("Another entity of this type has the same", "No other entity of this type has the same"),
                    "severity": severity, "status": status, "message": message, "value": shown(value)})

    for a in attributes:
        if a.get("is_required"):
            ok = not _missing(a)
            add(a["code"], a["name"], {"rule_type_code": "required"}, "error", "passed" if ok else "failed",
                None if ok else f"{a['name']} is required", a.get("value"))
        if a.get("pick_list_values"):
            r = {"rule_type_code": "list"}
            if _empty(a.get("value")):
                add(a["code"], a["name"], r, "warning", "not_applicable", "No value to check", None)
            else:
                ok = str(a["value"]) in a["pick_list_values"]
                add(a["code"], a["name"], r, "warning", "passed" if ok else "failed",
                    None if ok else f"{a['name']} \"{a['value']}\" is not one of the pick list values", a.get("value"))

    for rule in rules:
        field = (rule.get("field_name") or "").lower()
        if field:
            label, value, code = BUILT_IN.get(field, field.title()), entity.get(field), field
        else:
            a = by_code.get(str(rule.get("attribute_code") or "").lower())
            if a is None:
                continue
            if rule["rule_type_code"] == "mandatory" and a.get("is_required"):
                continue
            label, value, code = a["name"], a.get("value"), a["code"]
            rule = {**rule, "allowed_values": a.get("pick_list_values"), "ref_type": a.get("ref_type")}
        kind = rule["rule_type_code"]
        severity = rule.get("severity") or "warning"
        if kind in _ABOUT_CONTENT and _empty(value):
            add(code, label, rule, severity, "not_applicable", "No value to check", value)
            continue
        if kind == "required_if":
            other = values.get(str(rule.get("param1") or "").lower())
            if other is None or str(other).strip().lower() != str(rule.get("param2") or "").strip().lower():
                add(code, label, rule, severity, "not_applicable",
                    f"Applies only when {rule.get('param1')} is {rule.get('param2')}", value)
                continue
        ok = check(rule, value, values, duplicate_name)
        if kind == "has_relationship":
            found = matching_relationships(rule, value)
            add(code, label, rule, severity, "passed" if ok else "failed",
                None if ok else (rule.get("message") or default_message(rule, label)), None)
            out[-1]["value"] = ", ".join(f"{r.get('verb') or r.get('type')} {r.get('other_name', '')}".strip()
                                         for r in found[:5]) + (f" (+{len(found) - 5} more)" if len(found) > 5 else "") \
                if found else None
            continue
        add(code, label, rule, severity, "passed" if ok else "failed",
            None if ok else (rule.get("message") or default_message(rule, label)), value)

    status_order = {"failed": 0, "passed": 1, "not_applicable": 2}
    order = {a["code"].lower(): i for i, a in enumerate(attributes)}
    out.sort(key=lambda w: (status_order[w["status"]], w["severity"] != "error", order.get(w["code"].lower(), -1)))
    return out
