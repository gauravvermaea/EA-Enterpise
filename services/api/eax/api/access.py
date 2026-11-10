"""Roles, people and model assignments (build phase 3.1).

Roles are given in Keycloak (D92); here EA Explorer only maps Keycloak roles to its own eight roles,
lists people with what their Keycloak roles give them, and assigns people to models (D59), which is
EA Explorer's own business. Every change is audited; the database enforces who may make it.
"""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from .. import audit, permissions
from .. import keycloak_admin as kc
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine

blp = Blueprint("access", __name__, url_prefix="/api/v1",
                description="Roles (mapped from Keycloak), people and who is assigned to which model")
SECURITY = [{"bearerAuth": []}]


class AppRoleOut(Schema):
    code = fields.String()
    name = fields.String()
    scope = fields.String(metadata={"description": "global (given in Keycloak) or model (given per model here)"})
    description = fields.String()
    keycloak_roles = fields.List(fields.String(), metadata={"description": "Keycloak roles that give it"})


class MappingIn(Schema):
    keycloak_role = fields.String(required=True)
    app_role = fields.String(required=True, metadata={"description": "A global role: super-admin, it-admin, user-admin, "
                                                                      "keycloak-admin, model-creator or user"})


class RoleQuery(Schema):
    role = fields.String(load_default=None, metadata={"description": "The model role to take away (all when left out)"})


class MappingOut(Schema):
    id = fields.UUID()
    keycloak_role = fields.String()
    app_role = fields.String()
    created_at = fields.DateTime()
    created_by = fields.String()


class KeycloakRoleOut(Schema):
    name = fields.String()
    description = fields.String()
    app_roles = fields.List(fields.String())


class PersonOut(Schema):
    id = fields.String(metadata={"description": "Keycloak user id"})
    username = fields.String()
    name = fields.String(allow_none=True)
    email = fields.String(allow_none=True)
    enabled = fields.Boolean()
    keycloak_roles = fields.List(fields.String())
    roles = fields.List(fields.String(), metadata={"description": "The global EA Explorer roles they give"})
    models = fields.List(fields.Dict(), metadata={"description": "Models where they have a role: id, name, role"})
    keycloak_url = fields.String(metadata={"description": "Where to change their roles in Keycloak"})


class PeopleQuery(Schema):
    search = fields.String(load_default=None)


class AssigneeIn(Schema):
    username = fields.String(required=True)
    role = fields.String(required=True, metadata={"description": "model-admin, architect, model-sub-admin or report-viewer"})


class AssigneeOut(Schema):
    username = fields.String()
    role = fields.String()
    created_at = fields.DateTime()
    created_by = fields.String()


def _audit(conn, action: str, object_type: str, object_id: str, details: dict) -> None:
    audit.record(conn, actor=g.user.username, action=action, object_type=object_type, object_id=object_id,
                 details=details, source="api", request_id=getattr(g, "request_id", None))


def _kc(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except kc.KeycloakError as exc:
        abort(503, message=str(exc))


# ---------------------------------------------------------------- roles and the Keycloak mapping
@blp.route("/roles")
class Roles(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, AppRoleOut(many=True))
    @require_auth()
    def get(self):
        """EA Explorer's roles: global ones (and which Keycloak roles give each) and model ones"""
        with get_engine().connect() as conn:
            rows = conn.execute(text("""
                SELECT r.code, r.name, r.scope, r.description,
                       coalesce(array_agg(m.keycloak_role ORDER BY m.keycloak_role) FILTER (WHERE m.id IS NOT NULL), '{}') AS keycloak_roles
                  FROM core.app_roles r LEFT JOIN core.role_mappings m ON m.app_role = r.code
                 GROUP BY r.code ORDER BY min(r.sort_order)""")).mappings().all()
        return [dict(r) for r in rows]


@blp.route("/role-mappings")
class Mappings(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, MappingOut(many=True))
    @require_auth("users.read")
    def get(self):
        """Which Keycloak role gives which EA Explorer role"""
        with get_engine().connect() as conn:
            return [dict(r) for r in conn.execute(text(
                "SELECT guid AS id, keycloak_role, app_role, created_at, created_by FROM core.role_mappings "
                "ORDER BY app_role, keycloak_role")).mappings()]

    @blp.doc(security=SECURITY)
    @blp.arguments(MappingIn)
    @blp.response(201, MappingOut)
    @require_auth("roles.map")
    def post(self, body):
        """Map a Keycloak role to a global EA Explorer role (everyone holding the Keycloak role gets it)"""
        if body["app_role"] not in permissions.GLOBAL_ROLES:
            abort(400, message=f"{body['app_role']!r} is not a global role (one of {', '.join(permissions.GLOBAL_ROLES)}); "
                               "model roles are given per model on the model's People tab.")
        kc_role = body["keycloak_role"].strip()
        if kc_role.lower().startswith(permissions.GROUP_PREFIX):     # a directory group (phase 36, D503)
            name = kc_role[len(permissions.GROUP_PREFIX):].strip()
            kc_role = permissions.GROUP_PREFIX + name if name else ""
        if not kc_role:
            abort(400, message="Give the Keycloak role or the directory group.")
        with get_engine().begin() as conn:
            try:
                row = conn.execute(text("""INSERT INTO core.role_mappings (keycloak_role, app_role) VALUES (:k, :a)
                                           RETURNING guid AS id, keycloak_role, app_role, created_at, created_by"""),
                                   {"k": kc_role, "a": body["app_role"]}).mappings().one()
            except IntegrityError:
                abort(409, message=f"{kc_role} already gives {body['app_role']}.")
            _audit(conn, "role-mapping.add", "role_mapping", str(row["id"]), {"keycloak_role": kc_role, "app_role": body["app_role"]})
        permissions.forget_role_map()
        return dict(row)


@blp.route("/role-mappings/<uuid:mapping_id>")
class Mapping(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(204)
    @require_auth("roles.map")
    def delete(self, mapping_id):
        """Remove a mapping (people holding only that Keycloak role lose the EA Explorer role at once)"""
        with get_engine().begin() as conn:
            row = conn.execute(text("DELETE FROM core.role_mappings WHERE guid = :g RETURNING keycloak_role, app_role"),
                               {"g": str(mapping_id)}).mappings().first()
            if not row:
                abort(404, message="No such mapping.")
            if row["app_role"] == permissions.SUPER_ADMIN and not conn.execute(text(
                    "SELECT 1 FROM core.role_mappings WHERE app_role = 'super-admin'")).first():
                abort(409, message="This is the last mapping to Super Admin: add another first.")
            _audit(conn, "role-mapping.remove", "role_mapping", str(mapping_id), dict(row))
        permissions.forget_role_map()


@blp.route("/keycloak-roles")
class KeycloakRoles(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, KeycloakRoleOut(many=True))
    @require_auth("users.read")
    def get(self):
        """The realm roles in Keycloak and the EA Explorer roles each gives"""
        mapping = permissions.role_map()
        return [{**r, "app_roles": permissions.app_roles([r["name"]], mapping)} for r in _kc(kc.realm_roles)]


# ---------------------------------------------------------------- people
@blp.route("/people")
class People(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(PeopleQuery, location="query")
    @blp.response(200, PersonOut(many=True))
    @require_auth()
    def get(self, query):
        """People in Keycloak (first 100 matching), their Keycloak roles, the global roles those give, and
        their roles on models. Global roles are changed in Keycloak (keycloak_url). User Admins see
        everything; a Model Admin of any model can search people (to give them a role on their model) and
        sees only their names."""
        with get_engine().connect() as conn:
            full = g.user.can("users.read")
            if not full and not permissions.is_model_admin_anywhere(conn, g.user.username):
                abort(403, message="Not allowed: finding people needs the User Admin role, or the Model Admin role on a model.")
            assigned: dict[str, list] = {}
            if full:
                for r in conn.execute(text("SELECT username, model_guid, model_name, role FROM core.assignments()")).mappings():
                    mine = assigned.setdefault(r["username"], [])
                    found = next((x for x in mine if x["id"] == str(r["model_guid"])), None)
                    if found is None:
                        found = {"id": str(r["model_guid"]), "name": r["model_name"], "roles": []}
                        mine.append(found)
                    found["roles"].append(r["role"])
                for mine in assigned.values():
                    for x in mine:
                        x["roles"].sort(key=permissions.APP_ROLES.index)
                        x["role"] = x["roles"][0]
        people = _kc(kc.users, query["search"])
        mapping = permissions.role_map()
        if not full:
            return [{"id": p["id"], "username": p["username"], "name": p["name"], "enabled": p["enabled"]} for p in people]
        return [{**p, "roles": permissions.app_roles(p["keycloak_roles"], mapping),
                 "models": assigned.get(p["username"], []), "keycloak_url": kc.console_url(p["id"])} for p in people]


# ---------------------------------------------------------------- who is assigned to a model
@blp.route("/models/<uuid:model_id>/people")
class ModelPeople(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, AssigneeOut(many=True))
    @require_auth()
    def get(self, model_id):
        """The people with a role on the model (anyone who may read the model may see who works on it)"""
        with get_engine().connect() as conn:
            try:
                m = repo.get_model(conn, model_id)
            except repo.NotFound as exc:
                abort(404, message=str(exc))
            return [dict(r) for r in conn.execute(text("""SELECT username, role, created_at, created_by FROM core.model_users
                                                          WHERE model_id = :m ORDER BY username"""), {"m": m["_id"]}).mappings()]

    @blp.doc(security=SECURITY)
    @blp.arguments(AssigneeIn)
    @blp.response(201, AssigneeOut)
    @require_auth("model.people")
    def post(self, body, model_id):
        """Give a person a role on the model (the model's Model Admin). A person may hold several roles on
        one model; giving a role they already have changes nothing."""
        username = body["username"].strip().lower()
        if not username:
            abort(400, message="Give the person's user name.")
        if body["role"] not in permissions.MODEL_ROLES:
            abort(400, message=f"{body['role']!r} is not a model role: one of {', '.join(permissions.MODEL_ROLES)}.")
        with get_engine().begin() as conn:
            try:
                m = repo.get_model(conn, model_id)
                conn.execute(text("""INSERT INTO core.model_users (model_id, username, role) VALUES (:m, :u, :r)
                                     ON CONFLICT (model_id, username, role) DO NOTHING"""),
                             {"m": m["_id"], "u": username, "r": body["role"]})
                row = conn.execute(text("""SELECT username, role, created_at, created_by FROM core.model_users
                                            WHERE model_id = :m AND username = :u AND role = :r"""),
                                   {"m": m["_id"], "u": username, "r": body["role"]}).mappings().one()
            except repo.NotFound as exc:
                abort(404, message=str(exc))
            except DBAPIError as exc:
                abort(403, message=str(getattr(exc, "orig", exc)).split("\n")[0])
            _audit(conn, "model.role", "model", str(model_id), {"username": username, "role": body["role"]})
        return dict(row)


@blp.route("/models/<uuid:model_id>/people/<string:username>")
class ModelPerson(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(204)
    @blp.arguments(RoleQuery, location="query")
    @require_auth("model.people")
    def delete(self, query, model_id, username):
        """Take a person's role on the model away (`role`), or all their roles on it (no `role`)"""
        with get_engine().begin() as conn:
            try:
                m = repo.get_model(conn, model_id)
            except repo.NotFound as exc:
                abort(404, message=str(exc))
            try:
                gone = conn.execute(text("""DELETE FROM core.model_users WHERE model_id = :m AND username = lower(:u)
                                               AND (CAST(:r AS text) IS NULL OR role = :r) RETURNING id"""),
                                    {"m": m["_id"], "u": username, "r": query.get("role")}).first()
            except DBAPIError as exc:
                abort(403, message=str(getattr(exc, "orig", exc)).split("\n")[0])
            if not gone:
                abort(404, message=f"{username} has no {query.get('role') or 'role'} on this model.")
            _audit(conn, "model.unassign", "model", str(model_id), {"username": username.lower(), "role": query.get("role")})
