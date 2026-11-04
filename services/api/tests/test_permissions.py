"""Roles and permissions (phase 3.1): global roles from Keycloak, roles per model, one permission check."""

import jwt
import pytest

from eax import auth
from eax import permissions as p

MAPPING = {f"eax-{r}": {r} for r in p.GLOBAL_ROLES} | {"ea model owners": {"model-creator"}, "eax-architect": {"architect"}}


def test_keycloak_roles_map_to_global_roles_only():
    assert p.app_roles(["eax-model-creator", "offline_access"], MAPPING) == ["model-creator"]
    assert p.app_roles(["EA Model Owners"], MAPPING) == ["model-creator"]      # any Keycloak role, any case
    assert p.app_roles(["eax-user", "eax-super-admin"], MAPPING) == ["super-admin", "user"]
    assert p.app_roles(["eax-architect"], MAPPING) == []      # a model role never comes from Keycloak (D96)
    assert p.app_roles(["offline_access"], MAPPING) == []


@pytest.mark.parametrize("roles, permission, model_roles, expected", [
    (["super-admin"], "model.metamodel", None, True),
    (["user"], "model.metamodel", ["model-admin"], True),         # D89: the model's Model Admin
    (["user"], "model.metamodel", ["architect"], False),
    (["user"], "model.content", ["model-admin"], True),           # D90
    (["user"], "model.content", ["architect"], True),
    (["user"], "model.content", ["model-sub-admin"], True),
    (["user"], "model.content", ["report-viewer"], False),
    (["user"], "model.content", ["report-viewer", "architect"], True),   # several roles on one model
    (["user"], "model.read", ["report-viewer"], True),
    (["user"], "model.read", None, False),                        # no role on the model
    (["it-admin"], "model.read", None, False),                    # IT Admins run the installation, not models
    (["it-admin"], "system.operate", None, True),
    (["user-admin"], "roles.map", None, True),
    (["user-admin"], "users.read", None, True),
    (["user-admin"], "model.people", None, False),                # roles on a model: its Model Admin
    (["user-admin"], "model.read", None, False),
    (["model-creator"], "models.create", None, True),
    (["model-creator"], "model.read", None, False),               # only models they have a role on
    (["model-creator"], "model.people", ["model-admin"], True),   # e.g. on a model they created
    (["user"], "models.create", None, False),
    (["user"], "model.lock", ["model-admin"], True),
    (["user"], "model.lock", ["architect"], False),
    ([], "model.read", None, False),
])
def test_permission_matrix(roles, permission, model_roles, expected):
    assert p.allowed(roles, permission, model_roles) is expected


def test_who_sees_every_model():
    assert p.sees_every_model(["super-admin"])
    assert not any(p.sees_every_model([r]) for r in ("user", "it-admin", "keycloak-admin", "user-admin", "model-creator"))


def test_test_users_cover_every_role():
    keycloak = {role.removeprefix("eax-") for _u, role, _m in p.TEST_USERS}
    on_models = {r for _u, _r, models in p.TEST_USERS for roles in models.values() for r in roles}
    assert keycloak == set(p.GLOBAL_ROLES) and on_models == set(p.MODEL_ROLES)


def test_one_person_different_roles_on_different_models_and_several_on_one():
    users = {u: m for u, _r, m in p.TEST_USERS}
    assert {"model-admin", "architect"} <= {r for roles in users["user_model_admin"].values() for r in roles}
    assert any(len(roles) > 1 for roles in users["user_architect"].values())


def test_break_glass_token_is_a_super_admin(monkeypatch):
    monkeypatch.setenv("EAX_BREAK_GLASS_PASSWORD", "a-sealed-password")
    token = auth.make_break_glass_token()
    user = auth.user_from_claims(auth.decode_token(token), {})
    assert user.username == "break-glass" and user.break_glass and user.roles == ["super-admin"]


def test_break_glass_token_dies_with_the_password(monkeypatch):
    monkeypatch.setenv("EAX_BREAK_GLASS_PASSWORD", "first")
    token = auth.make_break_glass_token()
    monkeypatch.setenv("EAX_BREAK_GLASS_PASSWORD", "changed")
    with pytest.raises(jwt.InvalidSignatureError):
        auth.decode_token(token)


def test_break_glass_session_does_not_expire(monkeypatch):
    monkeypatch.setenv("EAX_BREAK_GLASS_PASSWORD", "a-sealed-password")
    claims = auth.decode_token(auth.make_break_glass_token())
    assert "exp" not in claims     # D100: until sign-out or a password change
