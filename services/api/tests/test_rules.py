"""Validation rules (eax.rules): what shows as an error or warning on an entity."""

import datetime as dt
from decimal import Decimal

from eax.rules import evaluate, summary

ATTRS = [
    {"code": "Lifecycle", "name": "Lifecycle", "is_required": False, "value": "Retiring",
     "pick_list_values": ["Plan", "Production", "Retiring", "Retired"]},
    {"code": "Criticality", "name": "Criticality", "is_required": True, "value": Decimal("7")},
    {"code": "GoLiveDate", "name": "Go-live Date", "is_required": False, "value": dt.date(2020, 1, 1)},
    {"code": "RetirementDate", "name": "Retirement Date", "is_required": False, "value": None},
    {"code": "URL", "name": "URL", "is_required": False, "value": "intranet/claims"},
    {"code": "Owner", "name": "Owner", "is_required": True, "value": None},
]
RULES = [
    {"rule_type_code": "mandatory", "field_name": "name", "severity": "error", "message": "Name is required"},
    {"rule_type_code": "max_length", "field_name": "name", "param1": "10", "severity": "error", "message": None},
    {"rule_type_code": "range", "attribute_code": "Criticality", "param1": "1", "param2": "5", "severity": "error",
     "message": "Criticality must be a whole number from 1 to 5"},
    {"rule_type_code": "regex", "attribute_code": "URL", "param1": r"^https?://\S+$", "severity": "warning", "message": None},
    {"rule_type_code": "required_if", "attribute_code": "RetirementDate", "param1": "Lifecycle", "param2": "Retiring",
     "severity": "warning", "message": "Set a retirement date for a retiring element"},
    {"rule_type_code": "date_range", "attribute_code": "GoLiveDate", "param1": "1990-01-01", "param2": "2100-12-31",
     "severity": "warning", "message": None},
    {"rule_type_code": "unique", "field_name": "name", "param1": "Type", "severity": "warning", "message": None},
    {"rule_type_code": "range", "attribute_code": "NotOnThisType", "param1": "1", "param2": "2", "severity": "error"},
]


def test_failures_are_reported_errors_first():
    found = evaluate({"name": "Claims Platform X"}, ATTRS, RULES, duplicate_name=True)
    by = {(w["code"], w["rule"]): w for w in found}
    assert ("name", "max_length") in by                       # 17 characters > 10
    assert by[("Criticality", "range")]["severity"] == "error"
    assert ("Owner", "required") in by                         # the attribute's required flag
    assert by[("URL", "regex")]["severity"] == "warning"
    assert ("RetirementDate", "required_if") in by
    assert ("name", "unique") in by
    assert ("GoLiveDate", "date_range") not in by              # inside the range
    assert not any(w["code"] == "NotOnThisType" for w in found)  # rule for an attribute the type lacks
    severities = [w["severity"] for w in found]
    assert severities == sorted(severities, key=lambda s: s != "error")
    assert summary(found) == {"errors": 3, "warnings": 3}


def test_rules_about_content_pass_when_there_is_no_value():
    attrs = [dict(a, value=None, is_required=False) for a in ATTRS]
    found = evaluate({"name": "Ok"}, attrs, RULES)
    assert found == []                                         # Lifecycle is empty, so required_if does not apply


def test_date_order_pick_list_and_numbers():
    attrs = [
        {"code": "StartDate", "name": "Start Date", "is_required": False, "value": "2025-06-01"},
        {"code": "EndDate", "name": "End Date", "is_required": False, "value": "2025-01-01"},
        {"code": "Hosting", "name": "Hosting", "is_required": False, "value": "Mainframe",
         "pick_list_values": ["SaaS", "PaaS", "IaaS"]},
        {"code": "AnnualCost", "name": "Annual Cost", "is_required": False, "value": "-5"},
    ]
    rules = [
        {"rule_type_code": "date_order", "attribute_code": "EndDate", "param1": "StartDate", "severity": "error",
         "message": "End date must be after the start date"},
        {"rule_type_code": "min_value", "attribute_code": "AnnualCost", "param1": "0", "severity": "error", "message": None},
    ]
    found = {w["code"]: w for w in evaluate({"name": "Project"}, attrs, rules)}
    assert found["EndDate"]["message"] == "End date must be after the start date"
    assert found["Hosting"]["rule"] == "list"
    assert found["AnnualCost"]["message"] == "Annual Cost must be at least 0"


def test_unknown_rule_types_and_bad_patterns_never_raise():
    attrs = [{"code": "Version", "name": "Version", "is_required": False, "value": "1.2"}]
    rules = [{"rule_type_code": "something_new", "attribute_code": "Version", "severity": "error"},
             {"rule_type_code": "regex", "attribute_code": "Version", "param1": "([", "severity": "warning"}]
    assert evaluate({"name": "x"}, attrs, rules) == []
