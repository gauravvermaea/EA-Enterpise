"""The rest of the MCP capability list (phases 26/27, D459, D486 to D488): writing reports into a project, projects and
governance help, surveys and maturity, administration questions, and the guided prompts.

The server ships no language model (D2): where a capability is mostly the assistant's own reasoning (reading a strategy
and building a model, drawing a view from a question, planning an ADM project, checking a change against principles),
the server gives the data tools and a guided prompt with the order of work. Credentials, roles and service accounts are
never made through MCP.
"""

from __future__ import annotations

import io
import re
from typing import Any

from sqlalchemy import text

from . import mcp_ops, permissions
from . import repository as repo
from .mcp_build import _proj
from .mcp_server import _run, mcp
from .metamodel_edit import EditError


def _who():
    return permissions.current.get()


# ================================================================ writing: a report as a project document (Word)
def docx_from_markdown(title: str, body: str) -> bytes:
    """A plain Word document from simple Markdown: # headings, - bullets, 1. numbers, | tables |, **bold**, paragraphs.
    No branding (the TOGAF documents rule); the person edits it in Word."""
    from docx import Document
    doc = Document()
    doc.add_heading(title.strip() or "Report", 0)
    table_rows: list[list[str]] = []

    def flush_table():
        rows = [r for r in table_rows if not all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in r)]
        if rows:
            t = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
            t.style = "Table Grid"
            for i, r in enumerate(rows):
                for j, c in enumerate(r):
                    t.cell(i, j).text = c.strip()
        table_rows.clear()

    def runs(p, line: str):
        for k, part in enumerate(re.split(r"\*\*", line)):
            p.add_run(part).bold = bool(k % 2)

    for raw in (body or "").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("|") and line.strip().endswith("|"):
            table_rows.append(line.strip().strip("|").split("|"))
            continue
        if table_rows:
            flush_table()
        if not line.strip():
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            doc.add_heading(m.group(2).strip(), min(len(m.group(1)), 4))
        elif re.match(r"^\s*[-*]\s+", line):
            runs(doc.add_paragraph(style="List Bullet"), re.sub(r"^\s*[-*]\s+", "", line))
        elif re.match(r"^\s*\d+[.)]\s+", line):
            runs(doc.add_paragraph(style="List Number"), re.sub(r"^\s*\d+[.)]\s+", "", line))
        else:
            runs(doc.add_paragraph(), line)
    if table_rows:
        flush_table()
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _file_name(title: str) -> str:
    base = re.sub(r"[^\w .-]+", "", title).strip() or "Report"
    return base[:120] + ".docx"


@mcp.tool()
async def save_report_document(project: str, title: str, markdown: str, confirm: str = "", why: str = "") -> Any:
    """Write a report into a project as a Word document for the person to review (D459): an architecture definition
    section, a current-state summary, a roadmap narrative, an executive summary of a comparison, gap analysis or merge
    request, release notes of a model. Write it from the model's own facts (with their links) in simple Markdown (#
    headings, - bullets, | tables |, **bold**); it is kept on the project's Repository tab as an artifact. Needs the right
    to contribute to the project. First call: a preview and a confirm token; call again with confirm=<token>."""
    from . import project_work as pw
    from . import projects as pj
    if not title.strip() or not markdown.strip():
        return {"error": "Give a title and the text."}
    args = {"project": project, "title": title, "markdown": markdown}
    data = docx_from_markdown(title, markdown)

    def preview(conn, user):
        with pj.connections(False) as pc:
            p = pj.project_row(pc, project)
            pw.need(pc, p, user, "contribute")
        heads = re.findall(r"^#{1,4}\s+(.*)$", markdown, re.M)
        return {"project": p["name"], "file": _file_name(title), "size_kb": round(len(data) / 1024, 1), "headings": heads[:40],
                "will": f"Keep {_file_name(title)} on {p['name']}'s Repository tab (an artifact), uploaded by you."}

    def apply(conn, user):
        with pj.connections(True) as pc:
            out = pw.upload_project_file(pc, project, user, _file_name(title), data)
            p = pj.project_row(pc, project)
        return {**out, "project": p["name"], "link": f"/#/projects/{p['guid']}/repository" if p.get("guid") else "",
                "message": f"{_file_name(title)} is on {p['name']}'s Repository tab."}
    return await mcp_ops.operate("save_report_document", args, confirm, preview, apply, label="report document")


# ================================================================ projects and governance
@mcp.tool()
async def principles_and_standards(project: str) -> Any:
    """A project's principles (statement, rationale, implications) and standards (by area, status, mandatory), and its
    governance log: to check a proposed change against them ("which does it follow or break?"). Read the entities
    involved with get_entity, then say per principle and standard whether the change follows it, breaks it, or does not
    apply, with the reason."""
    from . import governance, standards
    from . import projects as pj

    def run(pc, user):
        p = pj.project_row(pc, project)
        pj._need(pc, p, user, "read")
        prin = [dict(r._mapping) for r in pc.execute(text(
            """SELECT code, name, statement, rationale, implications FROM proj.principles WHERE project_id = :p ORDER BY code, name"""),
            {"p": p["id"]})]
        try:
            log = governance.listing(pc, project, user)
        except EditError:
            log = None
        return {"project": p["name"], "principles": prin, "standards": standards.listing(pc, project, user).get("standards"),
                "governance_log": (log or {}).get("records", (log or {}).get("items", []))[:100] if isinstance(log, dict) else []}
    return await _proj(run)


# ================================================================ surveys and maturity (38.1, 40)
@mcp.tool()
async def list_surveys() -> Any:
    """Surveys for you: to answer, answered, and those you run (Super Admins: every survey)."""
    from . import surveys
    return await _run(lambda conn: surveys.listing(conn, _who()))


@mcp.tool()
async def create_survey(title: str, sections: list[dict], recipients: list[dict] | None = None, description: str = "",
                        anonymous: bool = False, remind_every_days: int = 0, closes_at: str = "", confirm: str = "",
                        why: str = "") -> Any:
    """Make a survey from plain words, as a DRAFT (send it with survey_action): sections = [{title, text?, questions:
    [{key?, text, kind (single, multi, yes_no, rating, text, long_text, number, date, links), options?: [..], required?}]}];
    recipients = [{kind: user|role|model|project, value, role?}]. Delivered through the task list and a link, never
    email; answers never change a model. Needs the Super Admin, Model Creator or Library Admin role. First call: a preview
    and a confirm token; call again with confirm=<token>."""
    from . import surveys
    d = {"title": title, "description": description, "spec": {"sections": sections}, "recipients": recipients or [],
         "anonymous": anonymous, "remind_every_days": remind_every_days or None, "closes_at": closes_at or None}
    args = {"title": title, "sections": sections, "recipients": recipients or [], "description": description,
            "anonymous": anonymous, "remind_every_days": remind_every_days, "closes_at": closes_at}

    def preview(conn, user):
        if not surveys.may_create(user):
            raise EditError("Making surveys needs the Super Admin, Model Creator or Library Admin role.", 403)
        spec = surveys.clean_spec(d["spec"])
        rec = surveys.clean_recipients(d["recipients"])
        return {"title": title, "questions": len(surveys.questions(spec)), "sections": [s["title"] for s in spec["sections"]],
                "recipients": rec, "people": len(surveys.resolve(conn, rec)) if rec else 0, "anonymous": anonymous,
                "will": f"Make the draft survey '{title}' (not sent yet)."}
    return await mcp_ops.operate("create_survey", args, confirm, preview, lambda conn, user: surveys.create(conn, user, d), label="survey made")


@mcp.tool()
async def survey_action(survey: str, action: str, confirm: str = "", why: str = "") -> Any:
    """Send, remind, close or reopen a survey you run (action: send | remind | close | reopen). First call: a preview and
    a confirm token; call again with confirm=<token>."""
    from . import surveys
    if action not in ("send", "remind", "close", "reopen"):
        return {"error": "action is send, remind, close or reopen."}
    fn = {"send": surveys.send, "remind": surveys.remind, "close": surveys.close, "reopen": surveys.reopen}[action]
    args = {"survey": survey, "action": action}

    def preview(conn, user):
        s = surveys.get(conn, user, survey)
        return {"survey": s.get("title"), "status": s.get("status"), "progress": s.get("progress"),
                "will": f"{action.capitalize()} '{s.get('title')}'."}
    return await mcp_ops.operate("survey_action", args, confirm, preview, lambda conn, user: fn(conn, user, survey), label=f"survey: {action}")


@mcp.tool()
async def survey_results(survey: str) -> Any:
    """A survey's results by question and who has answered (names hidden when anonymous; shown once enough people have
    answered): to summarise them."""
    from . import surveys
    return await _run(lambda conn: surveys.results(conn, _who(), survey))


@mcp.tool()
async def maturity_overview(assessment: str = "") -> Any:
    """EA capability maturity (Super Admins only): the assessments with their trend, or one assessment's scores per
    element (mean, target, gap), the overall weighted score, the evidence EA Explorer measures, and each person's
    answers: to summarise the gaps against target and suggest next steps."""
    from . import maturity
    if assessment:
        return await _run(lambda conn: maturity.result(conn, _who(), assessment))
    return await _run(lambda conn: maturity.overview(conn, _who()))


# ================================================================ administration (Super Admins and IT Admins)
def _operator(user) -> None:
    if not (permissions.allowed(user.roles, "system.operate") or permissions.SUPER_ADMIN in (user.roles or ())):
        raise EditError("This is for Super Admins and IT Admins.", 403)


@mcp.tool()
async def usage_insight(days: int = 30) -> Any:
    """Who uses what and how often, models' use and size, idle models, stale uncommitted work, old loads and credentials
    (Super Admins and IT Admins): for questions such as "which models have not been used this quarter?"."""
    from . import operations as ops

    def run(conn):
        _operator(_who())
        try:
            ops.flush(conn)
        except Exception:  # noqa: BLE001 - counts not yet written are only a little late
            pass
        return ops.insight(conn, days)
    return await _run(run)


@mcp.tool()
async def housekeeping_dry_run() -> Any:
    """Run a housekeeping dry run (Super Admins and IT Admins): what the retention rules would archive or remove now,
    rule by rule. Nothing is removed; confirming stays in the screens (System admin > Operations)."""
    from . import operations as ops

    def run(conn):
        user = _who()
        _operator(user)
        return ops.run(conn, user.username, True)
    return await _run(run, begin=True)


@mcp.tool()
async def add_own_kpi(model: str, name: str, kind: str, entity_type: str, attribute: str = "", filter_attribute: str = "",
                      filter_op: str = "", filter_value: str = "", confirm: str = "", why: str = "") -> Any:
    """Track a KPI of your own on a model (Model Admins; phase 24): kind "count" (entities of a type) or "sum" (a number
    attribute), with one filter (filter_op: equals, not-equals, contains, empty, not-empty, more-than, less-than), e.g.
    "the number of applications on Windows Server 2012". Kept monthly and at every tag from now on. First call: a preview
    and a confirm token; call again with confirm=<token>."""
    from . import kpis
    body = {"name": name, "kind": kind, "entity_type": entity_type, "attribute": attribute, "filter_attribute": filter_attribute,
            "filter_op": filter_op, "filter_value": filter_value}
    args = {"model": model, **body}

    def preview(conn, user):
        m = repo.get_model(conn, model)
        if kind not in kpis.KINDS:
            raise EditError(f"kind is one of {', '.join(kpis.KINDS)}.")
        if filter_op not in kpis.OPS:
            raise EditError(f"filter_op is one of {', '.join(k for k in kpis.OPS if k)} (or empty).")
        return {"model": m["name"], "kpi": body, "will": f"Track '{name}' on {m['name']}, monthly and at every tag."}
    return await mcp_ops.operate("add_own_kpi", args, confirm, preview, lambda conn, user: kpis.add_definition(conn, model, user, body),
                         label="own KPI added")


# ================================================================ guided prompts (the order of work)
PROMPTS = {
    "copy_and_clean_up": """Copy a model and clean it up, then let it override its parent (D458).
1. copy_model(model, name, linked=true): preview, show the person, confirm. Note the new model's name.
2. find_duplicates on the copy (try closeness 0.85, and attributes such as Vendor and Version for applications).
   For each group decide which to keep (compare_duplicates shows every field; keep the one with most relationships and
   values unless a field says otherwise) and whose values win. Explain your choices in a line each.
3. merge_duplicates with all groups: preview, show the person, confirm.
4. Optionally tidy_names and find_orphans; apply what the person agrees with change_entities.
5. When the person says so, override_parent(copy): preview (counts, conflicts), confirm. Cite the links.""",
    "build_from_material": """Build model content from a document, pasted text or a table.
1. get_metamodel and describe_entity_type for the target model: use only its entity types, attribute codes and
   allowed_relationships. Map the material to them; list what does not fit instead of forcing it.
2. Show the person the entities (by type) and relationships you would add, with the sentence or row each comes from.
3. add_entities (by type, many at once), then add_relationships. They are the person's uncommitted changes.
4. For a whole new metamodel from a description, use start_metamodel_draft and draft_set_item (a draft to review),
   or describe it as a metamodel workbook (Types, Attributes, Allowed relationships) for the person to load.
5. Never invent values the material does not give; say what is missing.""",
    "analyse_a_model": """Answer an analysis question about a model with its facts.
- Impact of retiring or replacing something: impact_analysis.  - Overlaps and TIME: application_rationalisation.
- Cost by capability or value stream: cost_rollup_analysis.     - End-of-life risk: technology_risk_analysis.
- Single points of failure: single_points_of_failure.           - Heat maps: heat_map_data, then create_drawn_view.
- What changed: what_changed (since a tag or date).              - KPI trends: kpi_trend.
State the numbers, explain how they were worked out (each tool says how), cite the links, and say what the model
does not hold (empty attributes, missing relationships) that would change the answer.""",
    "draw_a_view": """Draw a view from a question ("draw the claims landscape with its technology").
1. search_entities and get_neighbourhood to find the entities that answer the question; keep it to what matters
   (about 10 to 40 elements). 2. Tell the person what you will show and why.
3. create_drawn_view(model, name, entities, include_relationships=true): it is laid out tidily and opens in draw.io.
4. To explain a view in words, get_drawn_view and describe it domain by domain.""",
    "write_a_report": """Write a report from the model into a project (Word).
1. Gather the facts with the reading and analysis tools; keep their links.
2. Write it in plain Markdown: a short summary first, then sections; tables for lists; no branding.
3. save_report_document(project, title, markdown): preview, show the person, confirm.""",
    "governance_check": """Check a proposed change against the project's principles and standards.
1. principles_and_standards(project). 2. get_entity / get_neighbourhood for what the change touches.
3. For each principle and standard: follows, breaks, or does not apply, with the reason in a line.
4. Summarise the risks; suggest a governance log entry or a change request when something breaks.""",
    "plan_an_adm_project": """Plan an architecture project (TOGAF ADM).
1. list_project_templates; pick with the person. 2. Propose phases, deliverables and steps (who, when), and the models
it needs. 3. create_project after the person's yes; then add_project_step for each step.""",
    "survey_from_words": """Make a survey from plain words.
1. Turn the request into sections and questions (kinds: single, multi, yes_no, rating, text, long_text, number,
date); keep it short. 2. create_survey (a draft): preview, show the person, confirm. 3. survey_action send when the
person says so. 4. Later, survey_results and summarise; for maturity assessments maturity_overview (Super Admins).""",
}


def _register_prompts() -> None:
    for name, body in PROMPTS.items():
        def make(b=body):
            def prompt() -> str:
                return b
            return prompt
        fn = make()
        fn.__name__ = name
        fn.__doc__ = body.splitlines()[0]
        mcp.prompt(name=name)(fn)


_register_prompts()
