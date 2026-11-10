"""Sample surveys and maturity assessments (owner, 9 Nov 2026, phases 38.1 and 40, D449, D453): laptop only, made once
(a survey with the same title is left alone). Every name is invented.

Between them they show every state: a draft with sections and conditions; an open survey (some people answered, one
started, the rest asked and reminded, a closing date and automatic reminders); a closed one with its answers; an
anonymous one with enough answers to show results; and three maturity assessments: two closed (so the trend has two
points, each with its evidence and scores kept) and one open with some answers.
"""

from __future__ import annotations

from sqlalchemy import text

SA, MC, LA = "user_super_admin", "user_model_creator", "user_library_admin"
PEOPLE = ["user_architect", "user_model_admin", "user_committer", "user_lead_architect", "user_model_sub_admin",
          "user_global_architect", "user_project_admin"]


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def _u(names):
    return [{"kind": "user", "value": n} for n in names]


USAGE = {"sections": [
    {"key": "use", "title": "How you use it", "questions": [
        {"key": "uses", "kind": "yes_no", "text": "Do you use the architecture repository in your work?", "required": True},
        {"key": "how_often", "kind": "single", "text": "How often?", "required": True,
         "options": ["Every day", "Every week", "Every month", "Less often"], "condition": {"question": "uses", "op": "equals", "value": "true"}},
        {"key": "why_not", "kind": "long_text", "text": "What keeps you from using it?",
         "condition": {"question": "uses", "op": "equals", "value": "false"}},
    ]},
    {"key": "parts", "title": "The parts you use", "condition": {"question": "uses", "op": "equals", "value": "true"}, "questions": [
        {"key": "which", "kind": "multi", "text": "Which parts do you use?", "options": ["Data entry and grids", "Views and maps",
                                                                                      "Drawn views", "Reports", "Projects and sign-off"]},
        {"key": "useful", "kind": "rating", "text": "How useful is it to you?", "min": 1, "max": 5, "required": True,
         "low_label": "not at all", "high_label": "very"},
        {"key": "hours", "kind": "number", "text": "About how many hours a week?", "min": 0, "max": 60},
        {"key": "wish", "kind": "text", "text": "One thing you would change"},
    ]},
]}
USAGE_ANSWERS = {
    "user_architect": {"uses": True, "how_often": "1", "which": ["1", "2", "3"], "useful": 5, "hours": 12, "wish": "Faster grids on big models"},
    "user_model_admin": {"uses": True, "how_often": "2", "which": ["1", "4"], "useful": 4, "hours": 5, "wish": "More report filters"},
    "user_committer": {"uses": True, "how_often": "1", "which": ["1"], "useful": 3, "hours": 8},
    "user_lead_architect": {"uses": False, "why_not": "I work mostly in the project pages and documents."},
}
BOARD = {"sections": [{"key": "meeting", "title": "The board meeting", "questions": [
    {"key": "clear", "kind": "rating", "text": "How clear were the papers sent before the meeting?", "min": 1, "max": 5, "required": True},
    {"key": "decided", "kind": "yes_no", "text": "Were the decisions you needed made?", "required": True},
    {"key": "missing", "kind": "long_text", "text": "What was missing?", "condition": {"question": "decided", "op": "equals", "value": "false"}},
    {"key": "length", "kind": "single", "text": "The meeting was…", "options": ["Too short", "About right", "Too long"]},
    {"key": "next", "kind": "date", "text": "When would suit you for the next one?"},
]}]}
BOARD_ANSWERS = {
    "user_architect": {"clear": 4, "decided": True, "length": "2", "next": "2026-12-03"},
    "user_model_admin": {"clear": 3, "decided": False, "missing": "A decision on the claims hub vendor shortlist.", "length": "3"},
    "user_lead_architect": {"clear": 5, "decided": True, "length": "2", "next": "2026-12-10"},
}
PULSE = {"sections": [{"key": "pulse", "title": "The practice today", "questions": [
    {"key": "valued", "kind": "rating", "text": "Do people outside IT value architecture work?", "min": 1, "max": 5, "required": True},
    {"key": "heard", "kind": "single", "text": "Are architects involved early enough in change?", "required": True,
     "options": ["Almost never", "Sometimes", "Usually", "Always"]},
    {"key": "one_thing", "kind": "long_text", "text": "One thing that would make the practice better"},
]}]}
PULSE_ANSWERS = [
    {"valued": 3, "heard": "2", "one_thing": "Shorter documents, more pictures."},
    {"valued": 2, "heard": "1", "one_thing": "Being asked before projects are funded."},
    {"valued": 4, "heard": "3"},
    {"valued": 3, "heard": "2", "one_thing": "A clear way to ask for help from the architects."},
    {"valued": 4, "heard": "3", "one_thing": "Keep the board meetings short."},
]
DRAFT = {"sections": [
    {"key": "tools", "title": "Tools", "questions": [
        {"key": "tool", "kind": "single", "text": "Which drawing tool do you use most?", "options": ["draw.io in EA Explorer", "A desktop drawing tool",
                                                                                                   "Slides", "Paper or whiteboard"], "other": True},
        {"key": "why", "kind": "text", "text": "Why that one?", "condition": {"question": "tool", "op": "answered"}},
    ]},
    {"key": "training", "title": "Training", "questions": [
        {"key": "want", "kind": "multi", "text": "Which training would help?", "options": ["ArchiMate", "TOGAF ADM", "Data modelling", "EA Explorer itself"]},
        {"key": "when", "kind": "single", "text": "When suits you?", "options": ["Mornings", "Afternoons"],
         "condition": {"question": "want", "op": "answered"}},
    ]},
]}
# maturity answers: (element level answers per person); each assessment shows growth
MAT_MAY = {"user_architect": [2, 2, 1, 1, 1, 1, 2, 1, 1], "user_model_admin": [1, 2, 2, 1, 1, 2, 2, 2, 1],
           "user_lead_architect": [2, 1, 1, 2, 1, 1, 3, 1, 0], "user_project_admin": [1, 1, 1, 1, 2, 1, 2, 1, 1]}
MAT_OCT = {"user_architect": [3, 3, 2, 2, 2, 2, 3, 3, 2], "user_model_admin": [3, 2, 2, 2, 2, 3, 3, 2, 1],
           "user_lead_architect": [3, 3, 2, 3, 2, 2, 3, 3, 2], "user_project_admin": [2, 2, 2, 2, 2, 2, 3, 2, 2],
           "user_global_architect": [3, 3, 3, 2, 2, 2, 2, 3, 2]}
MAT_NOV = {"user_architect": [3, 3, 3, 3, 2, 3, 3, 3, 2], "user_lead_architect": [4, 3, 3, 3, 2, 3, 4, 3, 2]}
# comments and evidence differ by person (D456): some give both, some one, some none
COMMENTS = {
    "user_lead_architect": {"architecture_process": "Projects follow the ADM steps in EA Explorer; small changes skip it.",
                            "governance": "Decisions are logged per project; the board meets monthly.",
                            "investment": "Large purchases come to the board, small ones do not."},
    "user_architect": {"architecture_development": "The demo estate is current; two older models are not.",
                       "it_security": "Security standards are in the library but not always checked."},
    "user_model_admin": {"business_linkage": "Capability heat maps are used in planning this year."},
}
EVIDENCE = {
    "user_lead_architect": {"architecture_process": [{"address": "#/work?tab=projects", "note": "Projects and their ADM steps"}],
                            "governance": [{"address": "#/repository/decisions", "note": "Decision log"},
                                           {"address": "https://intranet.example.org/ea/board-terms", "note": "Board terms of reference v1.2"}]},
    "user_architect": {"architecture_development": [{"address": "https://intranet.example.org/ea/landscape", "note": "Landscape pages"}],
                       "it_security": [{"address": "\\\\fileserver\\security\\standards.docx", "note": "Security standards (shared drive)"}]},
    "user_model_admin": {"business_linkage": [{"address": "#/repository", "note": "Capability map in the repository"}]},
}


def _answers(mt, levels: list[int], who: str = "") -> dict:
    out = {}
    for (key, *_r), lv in zip(mt.ELEMENTS, levels, strict=False):
        out[f"{key}_level"] = str(lv)
        if key in COMMENTS.get(who, {}):
            out[f"{key}_comment"] = COMMENTS[who][key]
        if key in EVIDENCE.get(who, {}):
            out[f"{key}_evidence"] = EVIDENCE[who][key]
    return out


def _age(conn, guid: str, sent_days: int, closed_days: int | None = None) -> None:
    """Moves a sample survey's dates into the past, so the screens show a history."""
    conn.execute(text("""UPDATE core.surveys SET created_at = now() - make_interval(days => :s + 2), opened_at = now() - make_interval(days => :s),
                                updated_at = now() - make_interval(days => COALESCE(:c, 0)),
                                closed_at = CASE WHEN :c IS NULL THEN NULL ELSE now() - make_interval(days => :c) END
                          WHERE guid = CAST(:g AS uuid)"""), {"s": sent_days, "c": closed_days, "g": guid})
    conn.execute(text("""UPDATE core.survey_recipients SET added_at = now() - make_interval(days => :s),
                                answered_at = CASE WHEN answered_at IS NULL THEN NULL
                                                   ELSE now() - make_interval(days => GREATEST(:s - 2, COALESCE(:c, 0) + 1)) END
                          WHERE survey_guid = CAST(:g AS uuid)"""), {"s": sent_days, "c": closed_days, "g": guid})
    conn.execute(text("""UPDATE core.survey_responses SET started_at = now() - make_interval(days => :s - 1),
                                submitted_at = CASE WHEN submitted_at IS NULL THEN NULL
                                                    ELSE now() - make_interval(days => GREATEST(:s - 2, COALESCE(:c, 0) + 1)) END
                          WHERE survey_guid = CAST(:g AS uuid)"""), {"s": sent_days, "c": closed_days, "g": guid})


def run() -> list[str]:
    from .. import maturity as mt
    from .. import permissions as perms
    from .. import surveys as sv
    from ..db import get_engine

    said: list[str] = []
    sa, mc, la = _p(SA, ("super-admin",)), _p(MC, ("model-creator",)), _p(LA, ("library-admin",))
    token = perms.current.set(sa)
    try:
        with get_engine().begin() as conn:
            def made(title: str) -> bool:
                return bool(conn.execute(text("SELECT 1 FROM core.surveys WHERE title = :t"), {"t": title}).scalar())

            def answer(sid: str, who: str, ans: dict, submit: bool = True) -> None:
                sv.answer(conn, _p(who), sid, ans, submit)

            # a draft, with sections and conditions, not sent
            t = "Drawing tools and training (draft)"
            if not made(t):
                sv.create(conn, mc, {"title": t, "description": "Which tools you draw with, and what training would help (sample).",
                                     "spec": DRAFT, "recipients": [{"kind": "role", "value": "user", "label": "Everyone who is User"}]})
                said.append(f"survey: {t}")

            # open: some answered, one started, the rest asked and reminded
            t = "How do you use the architecture repository?"
            if not made(t):
                protea = conn.execute(text("SELECT guid::text FROM core.models WHERE name = 'Protea Insurance (demo estate)'")).scalar()
                rec = _u(["user_lead_architect", "user_global_architect", "user_project_admin"])
                if protea:
                    rec.append({"kind": "model", "value": protea, "label": "Everyone on Protea Insurance (demo estate)"})
                s = sv.create(conn, mc, {"title": t, "description": "Five minutes on how the repository helps you, and what to change (sample).",
                                         "spec": USAGE, "recipients": rec, "remind_every_days": 7,
                                         "closes_at": conn.execute(text("SELECT (now() + interval '14 days')::date::text")).scalar()})
                sv.send(conn, mc, s["id"])
                for who, ans in USAGE_ANSWERS.items():
                    try:
                        answer(s["id"], who, ans)
                    except Exception as exc:  # noqa: BLE001 - one person not asked (no demo estate): skip them
                        said.append(f"  {who}: {exc}")
                try:
                    answer(s["id"], "user_global_architect", {"uses": True, "how_often": "2"}, submit=False)     # started, not sent
                except Exception:  # noqa: BLE001
                    pass
                sv.remind(conn, mc, s["id"])
                _age(conn, s["id"], 9)
                conn.execute(text("UPDATE core.surveys SET last_reminded_at = now() - interval '2 days' WHERE guid = CAST(:g AS uuid)"),
                             {"g": s["id"]})
                conn.execute(text("""UPDATE core.survey_recipients SET reminded_at = now() - interval '2 days'
                                      WHERE survey_guid = CAST(:g AS uuid) AND reminded_at IS NOT NULL"""), {"g": s["id"]})
                said.append(f"survey: {t} (open)")

            # closed, with answers
            t = "Architecture board meeting feedback, October"
            if not made(t):
                s = sv.create(conn, la, {"title": t, "description": "How the October board meeting went (sample).", "spec": BOARD,
                                         "recipients": _u(["user_architect", "user_model_admin", "user_lead_architect", "user_committer"])})
                sv.send(conn, la, s["id"])
                for who, ans in BOARD_ANSWERS.items():
                    answer(s["id"], who, ans)
                sv.close(conn, la, s["id"])
                _age(conn, s["id"], 30, 20)
                said.append(f"survey: {t} (closed)")

            # anonymous, open, with enough answers to show results
            t = "Architecture practice pulse (anonymous)"
            if not made(t):
                s = sv.create(conn, mc, {"title": t, "description": "Three questions; your name is not kept with your answers (sample).",
                                         "spec": PULSE, "anonymous": True, "open_link": True, "recipients": _u(PEOPLE)})
                sv.send(conn, mc, s["id"])
                for who, ans in zip(PEOPLE, PULSE_ANSWERS, strict=False):
                    answer(s["id"], who, ans)
                _age(conn, s["id"], 5)
                said.append(f"survey: {t} (anonymous)")

            # maturity: two closed (a trend), one open with some answers
            for title, answers, sent, closed in (("EA capability maturity, May 2026", MAT_MAY, 190, 170),
                                                 ("EA capability maturity, October 2026", MAT_OCT, 35, 20),
                                                 ("EA capability maturity, November 2026", MAT_NOV, 3, None)):
                if made(title):
                    continue
                targets = {k: (4 if k in ("governance", "architecture_process") else 3) for k, *_r in mt.ELEMENTS}
                weights = {k: (2 if k in ("governance", "business_linkage") else 1) for k, *_r in mt.ELEMENTS}
                people = sorted(set(answers) | {"user_model_admin", "user_project_admin", "user_global_architect"})
                s = mt.create(conn, sa, {"title": title, "recipients": _u(people), "targets": targets, "weights": weights,
                                         "remind_every_days": 7 if closed is None else None})
                sv.send(conn, sa, s["id"])
                for who, levels in answers.items():
                    answer(s["id"], who, _answers(mt, levels, who))
                if closed is not None:
                    sv.close(conn, sa, s["id"])
                _age(conn, s["id"], sent, closed)
                if closed is not None:       # the evidence was kept when it closed
                    conn.execute(text("""UPDATE core.surveys SET maturity = jsonb_set(maturity, '{evidence_at}', to_jsonb(closed_at::text))
                                          WHERE guid = CAST(:g AS uuid)"""), {"g": s["id"]})
                said.append(f"maturity assessment: {title}")
    finally:
        perms.current.reset(token)
    return said
