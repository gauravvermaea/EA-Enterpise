"""EA Explorer MCP server: lets your own language model (Claude, ChatGPT, a local model...) read
the repository through the Model Context Protocol.

Runs inside the api container next to the REST API (see entrypoint.sh):
    uvicorn eax.mcp_server:app --host 0.0.0.0 --port 8001
Endpoint: /mcp (Streamable HTTP). On a laptop also http://localhost:8001/mcp directly.

Sign-in: every request carries "Authorization: Bearer <token>", either
  * a Keycloak access token for the eax-api audience (the same token the REST API takes), or
  * on a laptop only, the development token EAX_MCP_DEV_TOKEN from work/eaexplorer.env.

The tools call eax.repository, the same code as the REST API, so every build phase that adds a
repository function adds the matching tool here. Build phase 1: read only.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from contextvars import ContextVar
from typing import Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import __version__
from . import repository as repo
from .auth import decode_token, user_from_claims
from .db import get_engine
from .logging_setup import configure_logging

configure_logging()
log = logging.getLogger("eax.mcp")
_actor: ContextVar[str] = ContextVar("eax_mcp_actor", default="unknown")

INSTRUCTIONS = """EA Explorer is an enterprise architecture repository (ArchiMate 4 metamodel).
A model holds a metamodel (layers, entity types, attributes, relationship types, allowed
relationships) and content (entities and relationships). Template models hold a metamodel only.
Start with list_models, then get_metamodel or list_entities for a model. Models, entity types and
entities can be given by guid or by name. Read only in this build."""

mcp = MCPServer(name="EA Explorer", instructions=INSTRUCTIONS, version=__version__)


# ---------------------------------------------------------------- helpers
def _clean(value: Any) -> Any:
    """JSON-safe output: guids, dates and decimals as text; internal bigint keys removed."""
    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items() if not k.startswith("_")}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v
    return json.loads(json.dumps(strip(value), default=str))


async def _run(fn, *args, begin: bool = False, **kwargs) -> Any:
    """Runs a repository function in a worker thread (the database driver is synchronous)."""
    def work():
        engine = get_engine()
        with (engine.begin() if begin else engine.connect()) as conn:
            return fn(conn, *args, **kwargs)
    try:
        result = _clean(await anyio.to_thread.run_sync(work))
    except repo.NotFound as exc:
        return {"error": str(exc)}
    # one JSON document per call: lists are wrapped, so clients get them in one piece
    return {"count": len(result), "items": result} if isinstance(result, list) else result


# ---------------------------------------------------------------- tools (build phase 1: read only)
@mcp.tool()
async def list_models() -> Any:
    """List every model you may read: templates (metamodel only), reference models and project models,
    with the model each merges into (parent) and was created from (source), and counts."""
    return await _run(repo.list_models)


@mcp.tool()
async def get_metamodel(model: str) -> Any:
    """The metamodel of a model: its layers with their entity types (and how many entities each has),
    and its relationship types. `model` is the model's guid or name."""
    return await _run(repo.get_metamodel, model)


@mcp.tool()
async def describe_entity_type(model: str, entity_type: str) -> Any:
    """One entity type: its attributes (data type, required, pick-list values), validation rules, and
    the relationships it may have to and from other types. `entity_type` is a guid, name
    (Application Component), code (ApplicationComponent) or table name (application_component)."""
    return await _run(repo.get_entity_type, model, entity_type)


@mcp.tool()
async def allowed_relationships(model: str, source_type: str, target_type: str) -> Any:
    """Which relationship types the metamodel allows from one entity type to another, for example
    from Application Component to Capability."""
    return await _run(repo.allowed_relationships, model, source_type, target_type)


@mcp.tool()
async def get_metamodel_diagram(model: str, layers: list[str] | None = None, entity_type: str | None = None,
                                relationship_types: list[str] | None = None, include_generic: bool = False,
                                include_connected: bool = False, with_attributes: bool = True) -> Any:
    """The metamodel as a Mermaid ER diagram (erDiagram text you can render or show the user).
    Give `entity_type` to focus on one type and the types it may connect to, or `layers` (names) for
    those layers only; with neither you get every layer, which is large. Relationship types default
    to all but Association and Specialization (`include_generic` adds them). `include_connected`
    adds the types in other layers that the chosen layers connect to."""
    return await _run(repo.metamodel_mermaid, model, layers=layers, entity_type=entity_type,
                      relationship_types=relationship_types, include_generic=include_generic,
                      include_connected=include_connected, with_attributes=with_attributes)


@mcp.tool()
async def list_entities(model: str, entity_type: str | None = None) -> Any:
    """Every entity of a model, or only those of one entity type: guid, display ID, name, type,
    layer and number of relationships."""
    return await _run(repo.list_entities, model, entity_type)


@mcp.tool()
async def get_entity(model: str, entity: str) -> Any:
    """One entity with every attribute of its type (and its value), its relationships in both
    directions, its parent and its parts. `entity` is a guid, display ID (APP-0002) or name."""
    return await _run(repo.get_entity_detail, model, entity)


@mcp.tool()
async def get_entity_table(model: str, entity_type: str, name: str | None = None) -> Any:
    """Entities of one type as a table with one column per attribute (what the SQL function
    eax.get_entity returns), plus their relationships. Give `name` for a single entity."""
    actor = _actor.get()
    return await _run(repo.get_entities, model, entity_type, name, 500, actor=actor, begin=True)


@mcp.tool()
async def list_relationships(model: str) -> Any:
    """Every relationship of a model: source entity, relationship type and target entity."""
    return await _run(repo.list_relationships, model)


@mcp.tool()
async def search_entities(text: str, model: str | None = None) -> Any:
    """Find entities whose name, display ID or description contains the text, in one model or in
    every model you may read."""
    return await _run(repo.search_entities, text, model)


# ---------------------------------------------------------------- sign-in
def _authenticate(header: str) -> str | None:
    """The user name for a bearer token, or None."""
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    dev = os.environ.get("EAX_MCP_DEV_TOKEN", "").strip().strip("'\"")
    if dev and os.environ.get("EAX_DEPLOYMENT", "laptop") == "laptop" and hmac.compare_digest(token, dev):
        return "mcp-dev"
    try:
        return user_from_claims(decode_token(token)).username
    except Exception:  # invalid, expired or wrong audience
        return None


class BearerAuth:
    """ASGI middleware: every HTTP request needs a valid bearer token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":  # lifespan events pass through
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        user = await anyio.to_thread.run_sync(_authenticate, headers.get("authorization", ""))
        if not user:
            body = json.dumps({"error": "Sign in required: send Authorization: Bearer <token> "
                                        "(a Keycloak access token, or EAX_MCP_DEV_TOKEN on a laptop)."}).encode()
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"www-authenticate", b'Bearer realm="eaexplorer"')]})
            await send({"type": "http.response.body", "body": body})
            return
        token = _actor.set(user)
        try:
            return await self.app(scope, receive, send)
        finally:
            _actor.reset(token)


def _transport_security() -> TransportSecuritySettings:
    """Accept requests for this installation's host names only (DNS-rebinding protection)."""
    host = os.environ.get("EAX_HOSTNAME", "localhost").strip()
    hosts = sorted({host, "localhost", "127.0.0.1", "api"})
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{h}:*" for h in hosts] + hosts,
        allowed_origins=[f"{scheme}://{h}:*" for h in hosts for scheme in ("http", "https")]
                        + [f"https://{h}" for h in hosts],
    )


app = BearerAuth(mcp.streamable_http_app(stateless_http=True, json_response=True,
                                         transport_security=_transport_security()))
log.info("EA Explorer MCP server %s ready at /mcp", __version__)
