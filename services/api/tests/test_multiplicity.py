"""Relationship multiplicity (D395): the notation and the check."""

import pytest

from eax import multiplicity as M


def test_notation():
    assert M.parse("") is None and M.parse(None) is None
    assert M.parse("1") == (1, 1) and M.parse("*") == (0, None)
    assert M.parse("0..1") == (0, 1) and M.parse(" 1 .. * ") == (1, None)
    assert [M.clean(x) for x in ("", "1", "*", "0..*", "1..*", "2..5")] == ["", "1", "*", "*", "1..*", "2..5"]
    for bad in ("0", "a", "3..2", "1..1", "-1", "1..", "..2"):
        with pytest.raises(ValueError):
            M.parse(bad)
    assert M.label("1", "") == "1 : *" and M.label("", "") == ""


def test_fits():
    assert M.fits("", 7) and M.fits("*", 0)
    assert M.fits("1", 1) and not M.fits("1", 0) and not M.fits("1", 2)
    assert M.fits("0..1", 0) and not M.fits("0..1", 2) and M.fits("1..*", 9) and not M.fits("1..*", 0)


def test_check_reads_each_end():
    # a claim belongs to exactly one policy (Claim -> Policy, target end 1); a policy covers 1..* vehicles
    data = {"entities": {1: {"id": 1, "entity_type_id": 10}, 2: {"id": 2, "entity_type_id": 10},
                         5: {"id": 5, "entity_type_id": 20}, 6: {"id": 6, "entity_type_id": 20}},
            "rels": {1: [{"type": "Association", "dir": "out", "other": 5}],
                     2: [{"type": "Association", "dir": "out", "other": 5}, {"type": "Association", "dir": "out", "other": 6}],
                     5: [{"type": "Association", "dir": "in", "other": 1}, {"type": "Association", "dir": "in", "other": 2}],
                     6: [{"type": "Association", "dir": "in", "other": 2}]}}
    c = [{"type": "Association", "source_type_id": 10, "target_type_id": 20, "source_end": "0..1", "target_end": "1",
          "source_name": "Claim", "target_name": "Policy"}]
    assert M.check(data, data["entities"][1], c) == []
    assert M.check(data, data["entities"][2], c) == ["Has 2 Association to Policy (1 allowed)"]
    assert M.check(data, data["entities"][5], c) == ["Has 2 Association from Claim (0..1 allowed)"]
    assert M.check(data, data["entities"][6], c) == []
