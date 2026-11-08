"""D327: a principle may refine another (by its guid); the reference must be a real id."""
import pytest

from eax.metamodel_edit import EditError
from eax.project_work import _principle_vals


def test_refines_is_a_uuid_or_nothing():
    assert _principle_vals({"name": "A"})["ref"] is None
    g = "93e868e1-ea1b-43be-b136-eeea58001da0"
    assert _principle_vals({"name": "A", "refines": g.upper()})["ref"] == g
    with pytest.raises(EditError):
        _principle_vals({"name": "A", "refines": "not-a-guid"})
    with pytest.raises(EditError):
        _principle_vals({"name": "  "})


def test_backup_carries_principle_areas():
    from eax.project_backup import TABLES
    assert "principle_areas" in str(TABLES)
