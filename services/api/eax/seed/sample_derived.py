"""Laptop sample data for derived entity types (R2.9, D629): a small model whose metamodel has Server, Windows Server
derived from it, and Database Server derived from that, with an attribute that came down two levels and one retired
when the base dropped it. Made once (invented names only)."""

from __future__ import annotations

from sqlalchemy import text

from .. import metamodel_edit as me
from .. import model_ops as mo
from .. import repository as repo
from ..db import get_engine

NAME = "Derived types example (sample)"
ACTOR = "user_super_admin"


def run() -> list[str]:
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("SELECT set_config('eax.actor', :a, true), set_config('eax.user_roles', 'super-admin', true)"), {"a": ACTOR})
        conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
        have = conn.execute(text("SELECT guid::text FROM core.models WHERE name = :n AND NOT is_deleted"), {"n": NAME}).scalar()
        conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
        if have and _done(conn, have):
            return [f"sample derived types: {NAME} is there already"]
        guid = have or str(mo.create_model(conn, ACTOR, {"kind": "project", "name": NAME, "source": "ArchiMate 4", "copy": "metamodel",
                                                        "description": "Server, Windows Server and Database Server: a type "
                                                                       "derived from another (R2.9)"})["model"]["id"])
        domain = conn.execute(text("""SELECT l.code FROM core.layers l JOIN core.models m ON m.id = l.model_id
                                       WHERE m.guid = CAST(:g AS uuid) AND NOT l.is_deleted
                                       ORDER BY (lower(l.name) LIKE '%technolog%') DESC, l.sort_order LIMIT 1"""), {"g": guid}).scalar()

        def go(op, p):
            return me.apply(conn, guid, op, p, ACTOR)
        go("entity_type.create", {"name": "Server", "domain": domain, "id_prefix": "SRV"})
        go("attribute.create", {"entity_type": "Server", "name": "Operating system", "data_type": "text"})
        go("attribute.create", {"entity_type": "Server", "name": "Rack position", "data_type": "text"})
        go("entity_type.create", {"name": "Windows Server", "domain": domain, "id_prefix": "WIN", "base": "Server"})
        go("attribute.create", {"entity_type": "Windows Server", "name": "Domain joined", "data_type": "boolean"})
        go("entity_type.create", {"name": "Database Server", "domain": domain, "id_prefix": "DBS", "base": "Windows Server"})
        rack = [a for a in repo.get_entity_type(conn, guid, "Server")["attributes"] if a["name"] == "Rack position"]
        if rack:                 # the base drops it: kept, retired, on the derived types with their values
            go("attribute.remove", {"item": str(rack[0]["item_id"])})
    return [f"sample derived types: {NAME} (Server > Windows Server > Database Server)"]


def _done(conn, guid: str) -> bool:
    try:
        return bool(repo.get_entity_type(conn, guid, "Database Server").get("base_name"))
    except Exception:  # noqa: BLE001 - not made yet
        return False
