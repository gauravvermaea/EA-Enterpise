"""The metamodel ER diagram rules (eax.diagram), on a small made-up metamodel."""

import pytest

from eax import diagram

L1, L2 = "11111111-0000-0000-0000-000000000001", "11111111-0000-0000-0000-000000000002"
A, B, C = ("22222222-0000-0000-0000-00000000000a", "22222222-0000-0000-0000-00000000000b",
           "22222222-0000-0000-0000-00000000000c")

DATA = {
    "layers": [{"id": L1, "code": "business", "name": "Business"},
               {"id": L2, "code": "application", "name": "Application"}],
    "entity_types": [
        {"id": A, "code": "BusinessActor", "name": "Business Actor", "table_name": "business_actor", "layer_id": L1,
         "attributes": [{"name": "Owner", "column_name": "owner", "data_type": "text", "is_required": True,
                         "pick_list": None, "unit": ""}]},
        {"id": B, "code": "BusinessRole", "name": "Business Role", "table_name": "business_role", "layer_id": L1,
         "attributes": []},
        {"id": C, "code": "ApplicationComponent", "name": "Application Component",
         "table_name": "application_component", "layer_id": L2,
         "attributes": [{"name": "Lifecycle", "column_name": "lifecycle", "data_type": "list", "is_required": False,
                         "pick_list": "Lifecycle", "unit": ""}]},
    ],
    "relationship_types": [{"id": "r1", "code": c, "name": c} for c in
                           ("Assignment", "Serving", "Association", "Specialization")],
    "links": [
        {"source": A, "target": B, "relationship_types": ["Assignment", "Association"]},
        {"source": C, "target": A, "relationship_types": ["Serving", "Association"]},
        {"source": C, "target": C, "relationship_types": ["Specialization"]},
    ],
}


def ids(part):
    return {t["id"] for t in part["entity_types"]}


def test_layer_alone_and_with_connected_types():
    part = diagram.scope(DATA, layers=["business"])
    assert ids(part) == {A, B} and len(part["links"]) == 1
    assert part["links"][0]["relationship_types"] == ["Assignment"]  # Association left out by default
    part = diagram.scope(DATA, layers=["Business"], include_connected=True)
    assert ids(part) == {A, B, C} and len(part["links"]) == 2


def test_focus_shows_neighbours_and_only_their_links():
    part = diagram.scope(DATA, entity_type="application_component")
    assert part["focus"] == C and ids(part) == {A, C}
    assert [x["relationship_types"] for x in part["links"]] == [["Serving"]]
    part = diagram.scope(DATA, entity_type="Application Component", include_generic=True)
    assert len(part["links"]) == 2  # the Specialization loop on itself too


def test_chosen_relationship_types():
    part = diagram.scope(DATA, relationship_types=["serving"])
    assert part["relationship_types"] == ["Serving"] and len(part["links"]) == 1


@pytest.mark.parametrize("kw", [{"layers": ["Nope"]}, {"entity_type": "Nope"}, {"relationship_types": ["Nope"]}])
def test_unknown_names_are_reported(kw):
    with pytest.raises(LookupError):
        diagram.scope(DATA, **kw)


def test_mermaid_text():
    text = diagram.to_mermaid(diagram.scope(DATA, include_generic=True))
    assert text.startswith("erDiagram\n")
    assert 'BusinessActor["Business Actor"] {' in text
    assert '        text owner "required"' in text
    assert '        list lifecycle "Lifecycle"' in text
    assert 'BusinessRole["Business Role"]\n' in text  # no attributes: no braces
    assert 'ApplicationComponent }o--o{ BusinessActor : "Serving, Association"' in text
    assert "{" not in diagram.to_mermaid(diagram.scope(DATA), with_attributes=False).split("\n", 1)[1].replace("}o--o{", "")
