"""People's own skills and the Skills repository (D353)."""

from types import SimpleNamespace

import pytest

from eax import skills as sk
from eax.metamodel_edit import EditError


def test_tags_are_cleaned():
    assert sk.clean(" Cloud ,cloud,  Data   modelling, ,TOGAF") == ["Cloud", "Data modelling", "TOGAF"]
    assert sk.clean(["x" * 80]) == ["x" * 60]
    with pytest.raises(EditError):
        sk.clean([f"s{i}" for i in range(41)])


def test_repository_lists_every_user_with_their_own_skills(monkeypatch):
    monkeypatch.setattr(sk, "_users", lambda: ([{"username": "ann", "name": "Ann", "enabled": True},
                                                {"username": "bob", "name": "", "enabled": True},
                                                {"username": "service-account-x", "name": "", "enabled": True}]))
    monkeypatch.setattr(sk, "of", lambda conn, names: {"ann": ["Cloud", "TOGAF"]})
    monkeypatch.setattr(sk, "all_tags", lambda conn: ["Cloud", "TOGAF"])
    out = sk.repository(None, SimpleNamespace(username="Bob"))
    assert [u["username"] for u in out["users"]] == ["ann", "bob"]            # every user, service accounts left out
    assert out["without"] == 1 and out["me"] == "bob"
    assert [(s["skill"], s["people"]) for s in out["skills"]] == [("Cloud", ["ann"]), ("TOGAF", ["ann"])]


def test_screens_and_seed():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    org = (root / "web" / "src" / "ProjectOrg.jsx").read_text()
    assert 'placeholder="Skills, comma separated"' not in org and "my-profile" in org     # skills are each user's own
    assert "#/my-profile" in (root / "web" / "src" / "App.jsx").read_text()
    from eax.seed import sample_content as sc
    assert len(sc.USER_SKILLS) >= 8 and all(u.startswith("user_") for u in sc.USER_SKILLS)


def test_no_keycloak_says_so(monkeypatch):
    from eax import keycloak_admin as kc

    def down(**_k):
        raise OSError("refused")
    monkeypatch.setattr(kc, "users", down)
    with pytest.raises(EditError) as e:
        sk.repository(None, SimpleNamespace(username="ann"))
    assert e.value.status == 503 and "Keycloak" in str(e.value)
