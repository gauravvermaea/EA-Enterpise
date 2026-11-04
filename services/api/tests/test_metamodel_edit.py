"""Metamodel editing helpers (eax.metamodel_edit): names, defaults, impact summaries."""

import datetime as dt
from decimal import Decimal

import pytest

from eax import metamodel_edit as ed


def test_codes_and_snake_names():
    assert ed.code_from("Data classification") == "DataClassification"
    assert ed.code_from("2nd line support") == "X2ndLineSupport"
    assert ed.snake_from("Go-live Date") == "go_live_date"
    assert ed.snake_from("  ") == "x_"


@pytest.mark.parametrize("dtype,value,expected", [
    ("text", "Unknown", ("value_text", "Unknown")),
    ("integer", "4", ("value_number", Decimal("4"))),
    ("currency", "1250.50", ("value_number", Decimal("1250.50"))),
    ("date", "2026-11-04", ("value_date", dt.date(2026, 11, 4))),
    ("boolean", "yes", ("value_bool", True)),
    ("list", "Internal", ("value_text", "Internal")),
])
def test_typed_defaults(dtype, value, expected):
    assert ed.typed_default(dtype, value, ["Public", "Internal"] if dtype == "list" else None) == expected


def test_empty_default_means_none():
    assert ed.typed_default("text", "") is None
    assert ed.typed_default("integer", None) is None


@pytest.mark.parametrize("dtype,value", [("integer", "4.5"), ("decimal", "x"), ("date", "4 Nov"), ("boolean", "maybe"),
                                         ("list", "Secret"), ("entity_ref", "APP-0001")])
def test_defaults_that_cannot_be_stored_are_refused(dtype, value):
    with pytest.raises(ed.EditError):
        ed.typed_default(dtype, value, ["Public", "Internal"])


def test_impact_lists_new_and_fixed_failures():
    before = {"t": {("e1", "required", "Owner", "error", "A", "APP-1")}}
    after = {"t": {("e2", "required", "Owner", "error", "B", "APP-2"), ("e3", "max_length", "Name", "warning", "C", "APP-3")}}
    out = ed._impact(before, after)
    assert out["newly_failing_count"] == 2 and out["now_passing_count"] == 1
    assert out["summary"][0].startswith("2 entities will fail 2 more checks")
    assert out["now_passing"][0]["entity_id"] == "e1"
    assert ed._impact({}, {})["summary"] == ["No change to any entity's check results"]


def test_unknown_operation():
    with pytest.raises(ed.EditError):
        ed.apply(None, "m", "entity_type.explode", {}, "me")


@pytest.mark.parametrize("rule_type, p1, p2", [
    ("regex", "^[A-Z]{3}-\\d+$", ""), ("date_range", "2026-01-01", "2026-12-31"), ("date_range", "", "2030-01-01"),
    ("range", "1", "5"), ("max_length", "120", ""), ("mandatory", "", ""),
])
def test_rule_parameters_that_work(rule_type, p1, p2):
    ed.check_rule_params(rule_type, p1, p2)


@pytest.mark.parametrize("rule_type, p1, p2", [
    ("regex", "([A-Z", ""), ("regex", "", ""), ("date_range", "2026-13-01", ""), ("date_range", "", ""),
    ("date_range", "2027-01-01", "2026-01-01"), ("range", "5", "1"), ("min_value", "abc", ""),
])
def test_rule_parameters_refused(rule_type, p1, p2):
    with pytest.raises(ed.EditError):
        ed.check_rule_params(rule_type, p1, p2)
