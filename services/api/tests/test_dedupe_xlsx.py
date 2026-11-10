"""The likely duplicates as Excel (owner, 10 Nov 2026, D541)."""

import io

from openpyxl import load_workbook

from eax import dedupe


def _wb(res):
    return load_workbook(io.BytesIO(dedupe.to_xlsx(res, "Protea", "https://eax.example/", "Application Component")))


def test_one_row_per_entity_with_links_and_about():
    res = {"model": "m1", "threshold": 0.88, "attributes": ["vendor"], "count": 1, "groups": [
        {"type": "Application Component", "reasons": ["close names"], "score": 93, "entities": [
            {"id": "a", "name": "Claims Platform", "display_id": "APP-1", "values": {"vendor": "Acme"}},
            {"id": "b", "name": "Claims Platfrom", "display_id": "APP-2", "values": {"vendor": "Acme"}}]}]}
    wb = _wb(res)
    rows = list(wb["Duplicates"].iter_rows(values_only=True))
    assert rows[0] == ("Group", "Entity type", "Why", "How alike (%)", "Entity", "Display ID", "vendor", "Link")
    assert rows[1][:7] == (1, "Application Component", "close names", 93, "Claims Platform", "APP-1", "Acme")
    assert rows[2][-1] == "https://eax.example/#/metamodel/m1/entity/b"
    about = dict(wb["About"].iter_rows(values_only=True))
    assert about["Groups found"] == 1 and about["Searched"] == "Application Component"


def test_nothing_found_says_so():
    wb = _wb({"model": "m1", "threshold": 1, "attributes": [], "count": 0, "groups": []})
    rows = list(wb["Duplicates"].iter_rows(values_only=True))
    assert rows[1][1] == "No likely duplicates found."
