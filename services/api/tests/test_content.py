"""Phase 6: data entry helpers (no database needed)."""

import datetime as dt
from decimal import Decimal

import pytest

from eax import content as ct
from eax.metamodel_edit import EditError


def attr(data_type, name="Field", picks=None):
    return {"data_type": data_type, "name": name, "data_type_name": data_type, "pick_list_values": picks or []}


def test_values_are_coerced_to_their_data_type():
    assert ct._coerce(attr("integer"), "1,200") == Decimal("1200")
    assert ct._coerce(attr("currency"), "250 000.50") == Decimal("250000.50")
    assert ct._coerce(attr("percent"), "12.5%") == Decimal("12.5")
    assert ct._coerce(attr("date"), "2026-11-04T10:00") == dt.date(2026, 11, 4)
    assert ct._coerce(attr("boolean"), "Yes") is True and ct._coerce(attr("boolean"), "no") is False
    assert ct._coerce(attr("list", picks=["Plan", "Production"]), "Plan") == "Plan"
    assert ct._coerce(attr("text"), "  x  ") == "x"


@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_clears(value):
    assert ct._coerce(attr("text"), value) is None


def test_bad_values_are_refused_with_the_field_name():
    with pytest.raises(EditError, match="Criticality holds whole numbers"):
        ct._coerce(attr("integer", "Criticality"), "3.5")
    with pytest.raises(EditError, match="Go-live"):
        ct._coerce(attr("date", "Go-live"), "next week")
    with pytest.raises(EditError, match="not in its pick list"):
        ct._coerce(attr("list", "Lifecycle", ["Plan"]), "Sometime")
    with pytest.raises(EditError):
        ct._coerce(attr("boolean"), "maybe")


def test_tags_from_text_or_list():
    assert ct._tags("cloud, critical ,") == ["cloud", "critical"]
    assert ct._tags(["a", " ", "b"]) == ["a", "b"]
    assert ct._tags(None) == []


def test_every_data_type_has_a_column():
    for t in ("text", "long_text", "integer", "decimal", "currency", "percent", "date", "boolean", "list", "url",
              "email", "entity_ref"):
        assert t in ct.STORAGE
