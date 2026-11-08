"""EA Explorer MCP server: lets your own language model (Claude, ChatGPT, a local model...) read
the repository through the Model Context Protocol.

Runs inside the api container next to the REST API (see entrypoint.sh):
    uvicorn eax.mcp_server:app --host 0.0.0.0 --port 8001
Endpoint: /mcp (Streamable HTTP), reached through nginx: https://<host>/mcp, and on a laptop also
http://localhost/mcp (D107).

Sign-in: every request carries "Authorization: Bearer <token>", either
  * a Keycloak access token for the eax-api audience (the same token the REST API takes), or
  * on a laptop only, the development token EAX_MCP_DEV_TOKEN from work/eaexplorer.env.

The tools call eax.repository, the same code as the REST API, so every build phase that adds a
repository function adds the matching tool here. Read only until build phase 6.
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

from . import __version__, audit, model_ops, permissions
from . import repository as repo
from .auth import decode_token, user_from_claims
from .config import get_settings
from .db import get_engine
from .logging_setup import configure_logging
from .metamodel_edit import EditError

configure_logging()
log = logging.getLogger("eax.mcp")
_actor: ContextVar[str] = ContextVar("eax_mcp_actor", default="unknown")

INSTRUCTIONS = """EA Explorer is an enterprise architecture repository (ArchiMate 4 metamodel).
A model holds a metamodel (layers, entity types, attributes, relationship types, allowed
relationships) and content (entities and relationships). Template models hold a metamodel only.
Start with list_models, then get_metamodel or list_entities for a model. Models, entity types and
entities can be given by guid or by name. check_entities shows what breaks the validation rules;
get_entity_history shows who changed what. You see only the models your roles and model
assignments allow. You may draft metamodels, read your notifications and requests, and send requests
to other people (list_my_notifications, list_my_requests, send_request).
You can also BUILD: make models (empty, a copy, a copy at a tag, a child), add entities and relationships, and set up
and run architecture projects (TOGAF ADM: steps, document classes, approvals). Call how_to_build first, and always
get the person's yes before creating models or projects."""

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
    if permissions.current.get() is None:  # fail closed: never read without knowing who asks
        return {"error": "Sign in required."}

    def work():
        engine = get_engine()
        with (engine.begin() if begin else engine.connect()) as conn:
            return fn(conn, *args, **kwargs)
    try:
        result = _clean(await anyio.to_thread.run_sync(work))
    except (repo.NotFound, EditError) as exc:
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
async def get_report_catalogue(model: str) -> Any:
    """What can be reported on for a model: the standard reports (SR-01 to SR-15, model overview,
    pick-list heatmaps) with their dashboard links, every entity type and attribute with the report
    view and column it is in (rpt.t_<type>, for SQL or BI tools on the read-only report login), and
    which types count as applications, capabilities and so on in the standard reports."""
    from . import reports
    return await _run(reports.model_reports, model)


@mcp.tool()
async def list_library() -> Any:
    """The model library: read-only reference models (for example the Insurance reference model)
    with their industry, version, description and how many entities of each type they hold.
    Reference models are locked; use list_entities or get_entity to read their content."""
    return await _run(repo.get_library)


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
    """One entity with every attribute of its type (and its value and rule results), its relationships
    in both directions, its parent and its parts, the model it is part of, and its lineage (the entity
    it was copied from, the template type it came from, its copies in other models).
    `entity` is a guid, display ID (APP-0002) or name."""
    return await _run(repo.get_entity_detail, model, entity)


@mcp.tool()
async def get_entity_table(model: str, entity_type: str, name: str | None = None) -> Any:
    """Entities of one type as a table with one column per attribute (what the SQL function
    eax.get_entity returns), plus their relationships. Give `name` for a single entity."""
    actor = _actor.get()
    return await _run(repo.get_entities, model, entity_type, name, 500, actor=actor, begin=True)


@mcp.tool()
async def list_relationships(model: str, relationship_type: str | None = None) -> Any:
    """Every relationship of a model, or of one relationship type (name, code or verb): source
    entity, relationship type, target entity, and whether the metamodel allows it."""
    return await _run(repo.list_relationships, model, relationship_type)


@mcp.tool()
async def list_relationship_types(model: str) -> Any:
    """The relationship types of a model with how often each is used, how many type pairs the
    metamodel allows for it, and how many of its relationships fall outside those rules."""
    return await _run(repo.relationship_type_summary, model)


@mcp.tool()
async def check_entities(model: str, entity_type: str) -> Any:
    """The entities of one type with their attribute values and validation results: for each, the
    number of errors and warnings and their messages (missing required values, values out of range,
    duplicate names and so on). Use it to find what needs fixing in a model."""
    return await _run(repo.type_table, model, entity_type)


@mcp.tool()
async def get_entity_rules(model: str, entity: str) -> Any:
    """Every rule applied to one entity: required values, pick lists, patterns, ranges, dates,
    duplicates and the relationships it must have, each passed, failed or not applicable, plus each of
    its relationships checked against the metamodel. Use it to explain what is wrong with an entity."""
    return await _run(repo.get_entity_rules, model, entity)


@mcp.tool()
async def get_entity_history(model: str, entity: str) -> Any:
    """Every recorded change to an entity, its attribute values and its relationships, newest first:
    when, who, and each field's old and new value."""
    return await _run(repo.get_entity_history, model, entity)


@mcp.tool()
async def get_neighbourhood(model: str, entity: str, depth: int = 1, direction: str = "both",
                            relationship_types: list[str] | None = None) -> Any:
    """An entity and everything connected to it within `depth` steps, through relationships and the
    parent hierarchy: the entities (nodes, each with its distance) and the lines between them (edges).
    direction "out" follows lines from source to target only (impact: what this leads to or uses),
    "in" follows them backwards (dependencies: what leads to or uses this), "split" does both (in has
    negative distances); up to 6 steps then, otherwise 1 to 3. relationship_types keeps only those (names or codes; "Parent" for the hierarchy)."""
    return await _run(repo.entity_graph, model, entity, None, depth, 300, direction, relationship_types)


@mcp.tool()
async def find_paths(model: str, source: str, target: str, max_steps: int = 6,
                     relationship_types: list[str] | None = None) -> Any:
    """The shortest chains connecting two entities (for example how a role connects to a capability),
    through relationships in either direction and the parent hierarchy, up to `max_steps` steps:
    the chains as lists of entity guids, and the entities and lines on them."""
    return await _run(repo.entity_paths, model, source, target, max_steps, 10, relationship_types)


@mcp.tool()
async def get_family_tree(model: str, entity: str, levels: int = 4) -> Any:
    """An entity's place in its hierarchy: every parent up to the top and its parts down `levels`
    levels (for example a capability within the capability map). Distance is negative for parents."""
    return await _run(repo.entity_graph, model, entity, None, levels, 500, "tree", None)


@mcp.tool()
async def get_entity_as_of(model: str, entity: str, event: int | None = None, at: str | None = None) -> Any:
    """An entity as it was at one point in its history: just after a history event (`event`, an id
    from get_entity_history) or at a time (`at`, ISO date and time). Each field, attribute value and
    relationship then, beside its value now, marked changed or not."""
    return await _run(repo.get_entity_as_of, model, entity, event, at)


@mcp.tool()
async def get_metamodel_history(model: str) -> Any:
    """Every change to a model's metamodel, grouped by the version it was published in (newest first):
    what was added, changed, retired or removed (entity types, attributes, pick lists, relationship
    types, mappings, rules), with old and new values, who and when."""
    return await _run(repo.metamodel_history, model)


@mcp.tool()
async def compare_metamodel_versions(model: str, from_version: int, to_version: int | None = None) -> Any:
    """What differs between two versions of a model's metamodel (to_version: the current one when left
    out): items added, removed, retired and changed with their old and new values."""
    return await _run(repo.metamodel_compare, model, from_version, to_version)


@mcp.tool()
async def list_failing_checks(model: str, entity_type: str | None = None) -> Any:
    """Every entity of a model that fails a check (missing mandatory values, rule failures, duplicates,
    relationships outside the metamodel), one row per failure with its rule, severity and message,
    plus counts by type, rule and severity. Use it to find what needs fixing."""
    return await _run(repo.failing_checks, model, entity_type)


@mcp.tool()
async def search_entities(text: str, model: str | None = None, entity_type: str = "", attribute: str = "",
                          tag: str = "") -> Any:
    """Search every model you may read (or one) for entities whose name, display ID, description, tags or any
    attribute value contains the text; optionally only one entity type, only values of one attribute (for
    example Vendor) or only entities with a tag. Each result says where the text was found."""
    from . import workspace
    return await _run(workspace.search, text, model, entity_type, attribute, tag)


# ---------------------------------------------------------------- viewpoints and maps (build phase 8.2, D161)
@mcp.tool()
async def list_viewpoints(model: str | None = None) -> Any:
    """The viewpoints: VP-01 to VP-25 from the ArchiMate 4 Specification (their "source" says so), VP-26 Gap (EA
    Explorer's own) and the organisation's own: concerns, stakeholders, element and relationship types; with a model,
    how many of its entities each viewpoint shows."""
    from . import viewpoints
    return await _run(viewpoints.list_viewpoints, model)


@mcp.tool()
async def view_through_viewpoint(model: str, viewpoint: str) -> Any:
    """A model through one viewpoint (for example VP-11 Application Cooperation): its elements with every
    attribute value, and the relationships between them that the viewpoint shows."""
    from . import viewpoints
    return await _run(viewpoints.model_viewpoint, model, viewpoint)


@mcp.tool()
async def value_stream_map(model: str) -> Any:
    """A model's value streams, their stages in order and the capabilities that enable each stage, with the
    capabilities' attribute values (maturity, criticality...)."""
    from . import viewpoints
    return await _run(viewpoints.value_stream_map, model)


@mcp.tool()
async def roadmap(model: str) -> Any:
    """A model's work packages, deliverables and plateaus with their start and end dates and what each delivers."""
    from . import viewpoints
    return await _run(viewpoints.roadmap, model)


# ---------------------------------------------------------------- tags, comparison, gap analyses (phase 8.3, D172)
@mcp.tool()
async def list_model_tags(model: str) -> Any:
    """A model's tags (named, frozen snapshots of its metamodel and content): name, when, by whom, commit, locked."""
    from . import tags
    return await _run(tags.list_tags, model)


@mcp.tool()
async def compare_models(left: str, right: str, left_tag: str = "", right_tag: str = "") -> Any:
    """Compares two models, or tags of them (give the tag's id to compare a tag instead of the model as it is now):
    per entity type how many elements are kept, changed, new and eliminated, the first 200 differences with the
    fields that changed, relationship totals and metamodel differences. Default fields: name, description, parent
    and every attribute."""
    from . import compare

    def run(conn):
        lft = compare.load_side(conn, {"kind": "tag", "id": left_tag} if left_tag else {"kind": "model", "id": left})
        rgt = compare.load_side(conn, {"kind": "tag", "id": right_tag} if right_tag else {"kind": "model", "id": right})
        res = compare.compare(lft, rgt)
        return {**{k: res[k] for k in ("left", "right", "totals", "relationship_totals", "summary")},
                "differences": [i for i in res["items"] if i["status"] != "kept"][:200], "metamodel": res["metamodel"][:100]}
    return await _run(run)


@mcp.tool()
async def list_gap_analyses(model: str = "") -> Any:
    """The TOGAF gap analyses you may see (each stored in a model; optionally only those stored in one model): baseline
    and target (any models or their tags), template, when compared, how many gaps are open."""
    from . import gaps
    return await _run(gaps.list_analyses, model or None)


@mcp.tool()
async def gap_analysis(analysis: str) -> Any:
    """One gap analysis: the model it is stored in, its baseline and target (models or tags, commits, metamodel versions),
    when compared, and every gap (kept, changed, new, eliminated) with the fields that changed, its note, resolution and
    work packages."""
    from . import gaps

    def run(conn):
        return gaps.get(conn, gaps.model_of(conn, analysis), analysis)
    return await _run(run)


# ---------------------------------------------------------------- sign-in
# ---------------------------------------------------------------- metamodel drafts (build phase 4, D115, D120)
# Your language model drafts a metamodel here; a person reviews and applies it in the screens (Models >
# Metamodel drafts). Nothing here changes a model. Build it step by step (draft_set_item / draft_remove_item)
# or all at once (draft_replace), whichever suits; every change is checked and the findings come back.

def _drafting(fn, action: str, *args):
    def run(conn):
        who = permissions.current.get()
        out = fn(conn, who, *args)
        audit.record(conn, actor=who.username, action=action, object_type="draft",
                     object_id=str(out.get("id", "")) if isinstance(out, dict) else "", source="mcp")
        return out
    return run


@mcp.tool()
async def get_metamodel_spec(model: str) -> Any:
    """A model's whole metamodel as one JSON document (format eax-metamodel/1): layers, pick_lists,
    attributes (code, name, data_type, pick_list, unit), entity_types (code, name, layer, id_prefix,
    attributes: [{attribute, required, section, default, help}]), relationship_types (code, name, verb,
    directed), allowed ({source, relationship, target}) and rules ({entity_type, attribute | field,
    rule_type, param1, param2, severity, message}). Use it as the pattern for drafts."""
    return await _run(model_ops.metamodel_spec, model)


@mcp.tool()
async def start_metamodel_draft(name: str, kind: str = "root", base: str | None = None, target: str | None = None,
                                version: str = "", note: str = "", spec: dict | None = None) -> Any:
    """Start a metamodel draft. kind "root": a new root metamodel called `name`, empty or starting as a copy
    of `base` (a root such as ArchiMate 4; see list_library). kind "changes": changes to `target`, a model
    you are Model Admin of (starts as its metamodel). Put what you were asked for in `note`. Give `spec` (a
    whole eax-metamodel/1 document) to submit everything at once. Returns the draft with its checks."""
    return await _run(_drafting(model_ops.draft_create, "draft.created",
                                {"kind": kind, "name": name, "base": base, "target": target, "version": version, "note": note,
                                 "spec": spec}, "mcp"), begin=True)


@mcp.tool()
async def draft_set_item(draft: str, section: str, item: dict) -> Any:
    """Add an item to a draft, or replace the one with the same code. section: layers {code, name, colour
    (six hex digits)}, pick_lists {code, name, values: [..]}, attributes {code, name, data_type (text,
    long_text, integer, decimal, currency, percent, date, boolean, list, url, email, entity_ref),
    pick_list (for list), unit}, entity_types {code, name, layer, id_prefix (capitals), description,
    attributes: [{attribute, required, section}]}, relationship_types {code, name, verb, directed},
    allowed {source, relationship, target} or rules {entity_type, attribute | field (name, description,
    display_id), rule_type (mandatory, min_length, max_length, min_value, max_value, range, regex,
    date_range, date_order, required_if, unique, has_relationship), param1, param2, severity, message}.
    Returns the draft's checks: fix every error before a person can apply it."""
    return await _run(_drafting(model_ops.draft_edit, "draft.changed", draft, "set", section, item), begin=True)


@mcp.tool()
async def draft_remove_item(draft: str, section: str, code: str) -> Any:
    """Take an item out of a draft: by its code, or for allowed and rules by its position (0, 1, ...)."""
    return await _run(_drafting(model_ops.draft_edit, "draft.changed", draft, "remove", section, None, code), begin=True)


@mcp.tool()
async def draft_replace(draft: str, spec: dict) -> Any:
    """Replace a draft's whole metamodel document (eax-metamodel/1) at once; it is checked again."""
    return await _run(_drafting(model_ops.draft_edit, "draft.changed", draft, "replace", None, None, None, spec), begin=True)


@mcp.tool()
async def get_metamodel_draft(draft: str) -> Any:
    """A draft: its metamodel document, its checks (errors and warnings), what it changes against the model
    it starts from, its review comments (open ones say what to fix, on the whole draft or on an item by
    section and code), what changed since the last review, and its history. Applying it is done by a
    person in the screens."""
    return await _run(lambda conn: model_ops.draft_get(conn, permissions.current.get(), draft))


@mcp.tool()
async def list_metamodel_drafts(status: str | None = None) -> Any:
    """Your metamodel drafts, and those you review: status draft (waiting for review), returned (sent back
    for changes: read its comments with get_metamodel_draft and fix it), applied or rejected."""
    return await _run(lambda conn: model_ops.draft_list(conn, permissions.current.get(), status))


@mcp.tool()
async def comment_on_metamodel_draft(draft: str, body: str, section: str | None = None, code: str | None = None) -> Any:
    """Add a comment to a draft, on the whole draft or on one item (section and code), for example to say
    how a reviewer's comment was dealt with."""
    return await _run(_drafting(model_ops.draft_comment, "draft.commented", draft, body, section, code), begin=True)


@mcp.tool()
async def resolve_draft_comment(draft: str, comment: str, resolved: bool = True) -> Any:
    """Mark a review comment fixed once the draft deals with it (or open again with resolved false)."""
    return await _run(_drafting(model_ops.draft_resolve_comment, "draft.comment_resolved", draft, comment, resolved), begin=True)


@mcp.tool()
async def resubmit_metamodel_draft(draft: str, note: str = "") -> Any:
    """Send a draft that was sent back for changes to its reviewer again, once the comments are dealt with
    and its checks show no errors: a new review round. `note` says what was changed."""
    def run(conn):
        who = permissions.current.get()
        out = model_ops.draft_resubmit(conn, who, draft, who.username, note)
        audit.record(conn, actor=who.username, action="draft.resubmitted", object_type="draft", object_id=str(out.get("id", "")),
                     source="mcp")
        return out
    return await _run(run, begin=True)


# ---------------------------------------------------------------- notifications and requests (build phase 8.1, D209)
# Read your notifications and requests, and raise a request on your behalf. Resolving notifications and moving
# requests along stay in the screens.

@mcp.tool()
async def list_my_notifications(show: str = "open", category: str = "", model: str = "") -> Any:
    """Your notifications. show: open (action ones not resolved and information ones not dismissed), actions,
    resolved or all; category: commit, metamodel, request or model; model: a model's guid. Action ones (needs_action)
    wait for someone to resolve them in the screens with a note."""
    from . import notify
    return await _run(lambda conn: notify.listing(conn, permissions.current.get().username, show=show, category=category,
                                                  model=model))


@mcp.tool()
async def list_my_requests(box: str = "received", status: str = "active") -> Any:
    """Requests sent to you (box received) or by you (box sent); status active (open and in progress), closed (done
    and declined), all, or one of open, in_progress, done, declined. Requests are private to their two people."""
    from . import tickets
    return await _run(lambda conn: tickets.listing(conn, permissions.current.get().username, box, status))


@mcp.tool()
async def get_request(request: str) -> Any:
    """One of your requests (its number, e.g. 1004, or id) with its comments and status trail."""
    from . import tickets

    def run(conn):
        try:
            return tickets.get(conn, permissions.current.get().username, request)
        except tickets.RequestError as exc:
            return {"error": str(exc)}
    return await _run(run)


@mcp.tool()
async def send_request(to: str, subject: str, body: str = "") -> Any:
    """Send a request to another person on your behalf, like a ticket: `to` is their username, a subject (under 200
    characters) and a body; no attachments or links. They are notified and move it along (in progress, done or
    declined) in the screens; you are told at each step. Say exactly what you ask for."""
    from . import tickets

    def run(conn):
        who = permissions.current.get()
        try:
            out = tickets.send(conn, who.username, to, subject, body, via="mcp")
        except tickets.RequestError as exc:
            return {"error": str(exc)}
        audit.record(conn, actor=who.username, action="request.send", object_type="request", object_id="",
                     details={"number": out["number"], "to": out["receiver"]}, source="mcp")
        return out
    return await _run(run, begin=True)


# ---------------------------------------------------------------- data quality (build phase 12, D239)
@mcp.tool()
async def quality_summary(model: str) -> Any:
    """A model's data quality as last measured (D245; measurements run in the background): its score (by default half
    completeness, almost a third rules passed, a fifth freshness), completeness, how many entities are incomplete, fail
    rules, are stale or orphans, the seals, the weakest entity types and owners, and when it was measured. Use it for
    questions like 'how good is the data in this model?'."""
    from . import quality
    from . import repository as repo

    def run(conn):
        d = quality.kept(conn, repo.get_model(conn, model))
        if not d:
            return {"model": model, "measured": False,
                    "message": "Not measured yet: ask a person to press Measure now on the model's Quality tab."}
        return {"model": d["model"], "measured_at": d["measured_at"], "summary": d["summary"], "by_type": d["by_type"][:15],
                "by_owner": d["by_owner"][:15]}
    return await _run(run)


@mcp.tool()
async def quality_findings(model: str, kind: str = "", entity_type: str = "", owner: str = "", responsible: str = "",
                           limit: int = 100) -> Any:
    """The data quality problems of a model, worst kinds first: kind incomplete (a weighted item missing), rule (a failing
    rule, with its severity), stale (not changed or confirmed within the stale period), orphan (connected to nothing),
    seal-broken or seal-expired, as last measured (D245). Filter by kind, entity type (code or name), owner text or the
    responsible username (for 'what are my gaps?'). Each row names the entity, what is wrong and who should fix it."""
    from . import quality
    from . import repository as repo

    def run(conn):
        d = quality.kept(conn, repo.get_model(conn, model))
        rows = d["findings"] if d else []
        t, o, r = entity_type.lower(), owner.lower(), responsible.lower()
        rows = [f for f in rows if (not kind or f["kind"] == kind) and (not t or t in (f["type"].lower(), f["type_name"].lower()))
                and (not o or o in (f["owner"] or "").lower()) and (not r or r in [x.lower() for x in f["responsible"]])]
        return {"count": len(rows), "findings": rows[:max(1, min(int(limit), 500))]}
    return await _run(run)


@mcp.tool()
async def suggest_quality_fix(model: str, entity: str, values: dict | None = None, description: str | None = None,
                              note: str = "") -> Any:
    """Suggest a fix for an entity's data quality gap as YOUR uncommitted change (nothing is committed): values is
    {attribute code: value}, description a new description. Only the person you act for sees it until a committer
    commits it on the model's Changes tab; say so to the person, and never guess values you were not given or cannot
    justify from the model."""
    from . import commits

    def run(conn):
        who = permissions.current.get()
        data = {}
        if values:
            data["values"] = values
        if description is not None:
            data["description"] = description
        if not data:
            return {"error": "Give values or a description to suggest."}
        m = repo.get_model(conn, model)
        e = repo.get_entity_detail(conn, str(m["id"]), entity)
        out = commits.record(conn, m["id"], who.username, "entity.update", {"entity": str(e["id"]), "data": data})
        audit.record(conn, actor=who.username, action="quality.suggest", object_type="entity", object_id=str(e["id"]),
                     details={"note": note[:300]}, source="mcp")
        return {"pending": True, "change": out.get("change"), "label": out.get("change_label"), "note": out.get("note")}
    return await _run(run, begin=True)


@mcp.tool()
async def draft_quality_rule(model: str, code: str, name: str, kind: str, entity_type: str, spec: dict,
                             severity: str = "warning", message: str = "", save: bool = False) -> Any:
    """Draft a data quality rule from plain words and see what it would find now. kind: relationship (spec:
    relationship_type, direction out|in|any, other_type, min, max), attribute (spec: when {attribute, op, value} optional,
    then {attribute, op, value}), consistency (spec: when optional, via {relationship_type, direction, other_type}, other
    {attribute, op, value}, must none|all) or naming (spec: pattern, unique, scope type|model). ops: filled, empty, equals,
    not_equals, in, not_in, matches, at_least, at_most, before_today, after_today. severity error blocks commits, warning
    does not. With save=false (the default) nothing is kept: show the person the rule and what it finds. With save=true
    the rule is saved as the person: a Model Admin's waits for a Super Admin's approval."""
    from . import quality
    rule = {"code": code, "name": name, "kind": kind, "entity_type": entity_type, "spec": spec, "severity": severity,
            "message": message, "enabled": True}

    def run(conn):
        prev = quality.preview_rule(conn, model, rule)
        if not save:
            return {**prev, "saved": False}
        out = quality.change(conn, model, permissions.current.get(), "rule", rule, "Drafted with Claude (MCP)")
        return {**prev, "saved": True, **out}
    return await _run(run, begin=save)


def _authenticate(header: str) -> permissions.Principal | None:
    """Who a bearer token belongs to, with their EA Explorer roles (mapped from Keycloak's), or None.
    The laptop development token is a Super Admin."""
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    dev = os.environ.get("EAX_MCP_DEV_TOKEN", "").strip().strip("'\"")
    if dev and os.environ.get("EAX_DEPLOYMENT", "laptop") == "laptop" and hmac.compare_digest(token, dev):
        return permissions.Principal("mcp-dev", (permissions.SUPER_ADMIN,))
    try:
        user = user_from_claims(decode_token(token))
    except Exception:  # invalid, expired or wrong audience
        return None
    return permissions.Principal(user.username, tuple(user.roles), user.break_glass)


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
                                    (b"www-authenticate", f'Bearer realm="{get_settings().realm}"'.encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        token, who = _actor.set(user.username), permissions.current.set(user)
        try:
            return await self.app(scope, receive, send)
        finally:
            permissions.current.reset(who)
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


# the tools to build with (projects, models, content) and their prompts (owner, 7 Nov 2026)
from . import mcp_build  # noqa: E402,F401
