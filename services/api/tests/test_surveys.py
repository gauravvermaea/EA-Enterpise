"""Surveys (phase 38.1, D446 to D449) and EA capability maturity (phase 40, D450 to D453). No database needed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from eax import change_log as cl
from eax import maturity as mt
from eax import org_backup as ob
from eax import permissions as perms
from eax import surveys as sv
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "migrations" / "sql" / "0037_surveys_maturity.sql").read_text()


def _spec():
    return sv.clean_spec({"sections": [
        {"title": "About you", "questions": [
            {"key": "uses", "kind": "yes_no", "text": "Do you use the repository?", "required": True},
            {"key": "how_often", "kind": "single", "text": "How often?", "required": True,
             "options": ["Daily", "Weekly", "Monthly"], "condition": {"question": "uses", "op": "equals", "value": "true"}},
            {"key": "why_not", "kind": "long_text", "text": "Why not?", "condition": {"question": "uses", "op": "equals", "value": "false"}},
        ]},
        {"title": "Tools", "condition": {"question": "uses", "op": "equals", "value": "true"}, "questions": [
            {"key": "parts", "kind": "multi", "text": "Which parts?", "options": ["Grids", "Views", "Reports"]},
            {"key": "rating", "kind": "rating", "text": "How useful?", "min": 1, "max": 5, "required": True},
            {"key": "hours", "kind": "number", "text": "Hours a week", "min": 0, "max": 80},
            {"key": "since", "kind": "date", "text": "Since when?"},
        ]},
    ]})


def test_the_questions_are_checked():
    s = _spec()
    assert [q["key"] for q in sv.questions(s)] == ["uses", "how_often", "why_not", "parts", "rating", "hours", "since"]
    assert s["sections"][0]["questions"][1]["options"][0] == {"value": "1", "label": "Daily"}
    with pytest.raises(EditError, match="come before"):
        sv.clean_spec({"sections": [{"questions": [{"kind": "text", "text": "A", "condition": {"question": "b"}},
                                                   {"key": "b", "kind": "text", "text": "B"}]}]})
    with pytest.raises(EditError, match="2 to"):
        sv.clean_spec({"sections": [{"questions": [{"kind": "single", "text": "A", "options": ["only"]}]}]})
    with pytest.raises(EditError, match="kind"):
        sv.clean_spec({"sections": [{"questions": [{"kind": "slider", "text": "A"}]}]})
    with pytest.raises(EditError, match="wording"):
        sv.clean_spec({"sections": [{"questions": [{"kind": "text", "text": " "}]}]})
    dup = sv.clean_spec({"sections": [{"questions": [{"key": "a", "kind": "text", "text": "A"}, {"key": "a", "kind": "text", "text": "B"}]}]})
    assert [q["key"] for q in sv.questions(dup)] == ["a", "a_"]


def test_conditions_show_and_hide_sections_and_questions():
    s = _spec()
    assert sv.visible(s, {}) == {"uses"}
    assert sv.visible(s, {"uses": True}) == {"uses", "how_often", "parts", "rating", "hours", "since"}
    assert sv.visible(s, {"uses": False}) == {"uses", "why_not"}
    # an answer to a hidden question is dropped; required ones only when shown
    got = sv.check_answers(s, {"uses": "no", "why_not": "Too slow", "rating": 4}, final=True)
    assert got == {"uses": False, "why_not": "Too slow"}
    with pytest.raises(EditError, match="required"):
        sv.check_answers(s, {"uses": "yes", "how_often": "2"}, final=True)
    ok = sv.check_answers(s, {"uses": True, "how_often": "2", "rating": "5", "parts": ["3", "1"], "hours": "7.5",
                              "since": "2025-03-01T00:00"}, final=True)
    assert ok == {"uses": True, "how_often": "2", "rating": 5, "parts": ["1", "3"], "hours": 7.5, "since": "2025-03-01"}
    assert sv.check_answers(s, {"uses": True}, final=False) == {"uses": True}       # saving as you go
    for bad, msg in (({"uses": True, "rating": 9}, "from 1 to 5"), ({"uses": True, "how_often": "9"}, "options"),
                     ({"uses": True, "hours": "lots"}, "number"), ({"uses": "maybe"}, "yes or no"),
                     ({"uses": True, "since": "soon"}, "date")):
        with pytest.raises(EditError, match=msg):
            sv.check_answers(s, bad, final=False)


def test_includes_and_answered_conditions():
    s = sv.clean_spec({"sections": [{"questions": [
        {"key": "p", "kind": "multi", "text": "Parts", "options": [{"value": "g", "label": "Grids"}, {"value": "v", "label": "Views"}]},
        {"key": "v", "kind": "text", "text": "Which views?", "condition": {"question": "p", "op": "includes", "value": "v"}},
        {"key": "c", "kind": "text", "text": "Comment", "condition": {"question": "p", "op": "answered"}},
        {"key": "n", "kind": "text", "text": "Not grids", "condition": {"question": "p", "op": "not_equals", "value": "g"}}]}]})
    assert sv.visible(s, {"p": ["g", "v"]}) == {"p", "v", "c", "n"}
    assert sv.visible(s, {"p": ["g"]}) == {"p", "c"}
    assert sv.visible(s, {}) == {"p", "n"}


def test_results_by_question():
    s = _spec()
    resp = [{"respondent": "thandi", "answers": {"uses": True, "how_often": "1", "rating": 4, "parts": ["1", "2"], "hours": 10}},
            {"respondent": "sipho", "answers": {"uses": True, "how_often": "1", "rating": 2, "parts": ["1"], "hours": 4}},
            {"respondent": "naledi", "answers": {"uses": False, "why_not": "We use spreadsheets"}}]
    r = {x["key"]: x for x in sv.summarise(s, resp)}
    assert [(o["label"], o["count"], o["share"]) for o in r["uses"]["options"]] == [("Yes", 2, 67), ("No", 1, 33)]
    assert r["how_often"]["options"][0]["count"] == 2 and r["how_often"]["answered"] == 2 and r["how_often"]["of"] == 3
    assert r["rating"]["mean"] == 3 and r["rating"]["median"] == 3 and [o["count"] for o in r["rating"]["options"]] == [0, 1, 0, 1, 0]
    assert [o["count"] for o in r["parts"]["options"]] == [2, 1, 0]
    assert r["hours"]["min"] == 4 and r["hours"]["max"] == 10
    assert r["why_not"]["answers"] == [{"by": "naledi", "text": "We use spreadsheets"}]


def test_recipients():
    rec = sv.clean_recipients([{"kind": "user", "value": "Thandi"}, {"kind": "role", "value": "library-admin"},
                               {"kind": "model", "value": "abc", "role": "architect"}, {"kind": "project", "value": "p1"},
                               {"kind": "user", "value": "thandi"}])
    assert rec[0] == {"kind": "user", "value": "thandi"} and len(rec) == 4
    for bad in ([{"kind": "team", "value": "x"}], [{"kind": "role", "value": "boss"}], [{"kind": "model", "value": "m", "role": "boss"}]):
        with pytest.raises(EditError):
            sv.clean_recipients(bad)


def test_who_makes_surveys_and_runs_maturity():
    class U:
        def __init__(self, roles, name="someone"):
            self.roles, self.username = roles, name
    assert sv.may_create(U({perms.SUPER_ADMIN})) and sv.may_create(U({perms.MODEL_CREATOR})) and sv.may_create(U({perms.LIBRARY_ADMIN}))
    assert not sv.may_create(U({perms.USER}))
    assert mt.may_manage(U({perms.SUPER_ADMIN})) and not mt.may_manage(U({perms.MODEL_CREATOR, perms.LIBRARY_ADMIN}))
    s = {"owner": "thandi"}
    assert sv._runs(s, U({perms.USER}, "Thandi")) and sv._runs(s, U({perms.SUPER_ADMIN})) and not sv._runs(s, U({perms.MODEL_CREATOR}))


def test_maturity_questions_and_scores():
    spec = mt.default_spec()
    assert len(spec["sections"]) == 9 and len(mt.LEVELS) == 6
    q = spec["sections"][0]["questions"][0]
    assert q["element"] == "architecture_process" and [o["score"] for o in q["options"]] == [0, 1, 2, 3, 4, 5]
    # every level of every element has a description and examples, in our own words (D456)
    for sec in spec["sections"]:
        lv = sec["questions"][0]
        assert len(lv["options"]) == 6 and all(o.get("description") and len(o.get("examples", [])) >= 2 for o in lv["options"])
        assert [x["kind"] for x in sec["questions"]] == ["single", "long_text", "links"]      # value, comment, evidence
        assert not any(x["required"] for x in sec["questions"][1:])
    text = " ".join(f"{o['label']} {o.get('description', '')} {' '.join(o.get('examples', []))}"
                    for s in spec["sections"] for qq in s["questions"] for o in qq.get("options", []))
    assert "objective" not in text.lower() and "togaf" not in text.lower()
    s = {"spec": spec, "maturity": {"targets": {"architecture_process": 4}, "weights": {"governance": 2}}}
    resp = [{"answers": {"architecture_process_level": "2", "governance_level": "3"}},
            {"answers": {"architecture_process_level": "3", "governance_level": "4"}},
            {"answers": {"architecture_process_level": "1"}}]
    sc = mt.scores(s, resp)
    ap = next(e for e in sc["elements"] if e["element"] == "architecture_process")
    gv = next(e for e in sc["elements"] if e["element"] == "governance")
    assert ap["mean"] == 2 and ap["target"] == 4 and ap["gap"] == 2 and ap["level"] == "Under development"
    assert ap["at_or_above"] == {"1": 100, "2": 67, "3": 33, "4": 0, "5": 0} and ap["spread"]["2"] == 1
    assert gv["mean"] == 3.5 and gv["gap"] == 0 and gv["weight"] == 2
    assert sc["overall"] == round((2 * 1 + 3.5 * 2) / 3, 2) and sc["responses"] == 3
    empty = next(e for e in sc["elements"] if e["element"] == "investment")
    assert empty["mean"] is None and empty["gap"] is None
    st = mt.clean_settings({"targets": {"governance": 9}, "weights": {"investment": -1}})
    assert st["targets"]["governance"] == 5 and st["weights"]["investment"] == 0 and st["targets"]["it_security"] == 3


def test_the_migration_is_rows_only_and_backed_up():
    assert "CREATE TRIGGER" not in SQL and "CREATE FUNCTION" not in SQL and "CREATE OR REPLACE FUNCTION" not in SQL   # D248
    for t in ("core.surveys", "core.survey_recipients", "core.survey_responses"):
        assert f"CREATE TABLE {t}" in SQL
        assert t.split(".")[1] in ob.CORE_TABLES and ob.CORE_TABLES[t.split(".")[1]][1] == "guid"
    assert list(ob.CORE_TABLES).index("surveys") < list(ob.CORE_TABLES).index("survey_responses")
    assert re.search(r"survey_guid\s+uuid NOT NULL REFERENCES core.surveys \(guid\)", SQL)
    assert "respondent   text CHECK (respondent IS NULL" in SQL           # anonymous answers carry no name
    v = (ROOT / "migrations" / "versions" / "0037_surveys_maturity.py").read_text()
    assert 'revision = "0037_surveys_maturity"' in v and 'down_revision = "0036_machine_access_ops"' in v


def test_wiring():
    api = (ROOT / "eax" / "api" / "surveys.py").read_text()
    for path in ('"/surveys"', '"/surveys/people"', '"/surveys/<string:sid>"', '"/surveys/<string:sid>/answer"',
                 '"/surveys/<string:sid>/results"', '"/surveys/<string:sid>/xlsx"', '"/maturity"', '"/maturity/<string:sid>"'):
        assert path in api, path
    for name in ("copy", "send", "recipients", "remind", "close", "reopen"):
        assert f'_action("{name}"' in api
    assert "surveys_blp" in (ROOT / "eax" / "app.py").read_text()
    jobs = (ROOT / "eax" / "jobs.py").read_text()
    assert 'name="eax.surveys"' in jobs and "sv.housekeeping(conn)" in jobs
    for a in ("survey.create", "survey.send", "survey.close", "survey.answer", "maturity.create"):
        assert a in cl.ACTIONS
    assert "surveys.create" in perms.GLOBAL_PERMISSIONS and perms.GLOBAL_PERMISSIONS["maturity.manage"] == set()
    # delivered through the task list (a notification needing action) and a link, never email
    src = (ROOT / "eax" / "surveys.py").read_text()
    assert "needs_action=True" in src and 'ref_kind="survey_recipient"' in src and "smtp" not in src.lower()
    # answers never change a model (D375)
    assert "core.entities" not in src and "core.attribute_values" not in src


def test_the_screens_are_there():
    web = ROOT.parents[0] / "web" / "src"
    jsx = (web / "Surveys.jsx").read_text()
    for x in ("export default function SurveysPage", "function Designer", "function AnswerPage", "function ResultsPage",
              "function MaturityPage", "/api/v1/surveys", "/api/v1/maturity"):
        assert x in jsx, x
    assert "#/surveys" in (web / "App.jsx").read_text()


def test_evidence_links_and_each_persons_answers():
    spec = mt.default_spec()
    got = sv.check_answers(spec, {"governance_level": "3", "governance_comment": "Monthly board",
                                  "governance_evidence": "#/repository/decisions | Decision log\njavascript:alert(1)"}, final=False)
    assert got["governance_evidence"] == [{"address": "#/repository/decisions", "note": "Decision log"},
                                          {"address": "javascript:alert(1)", "note": ""}]          # kept as typed (D418)
    s = {"spec": spec, "maturity": {}}
    who = mt.respondents(s, [{"respondent": "thandi", "answers": got, "submitted_at": None},
                             {"respondent": None, "answers": {"governance_level": "1"}, "submitted_at": None}])
    assert who[0]["who"] == "thandi" and who[0]["elements"]["governance"]["level"]["score"] == 3
    assert who[0]["elements"]["governance"]["comment"] == "Monthly board" and len(who[0]["elements"]["governance"]["evidence"]) == 2
    assert who[1]["who"] == "Respondent 2"
    r = {x["key"]: x for x in sv.summarise(spec, [{"respondent": "thandi", "answers": got}])}
    assert r["governance_evidence"]["links"][0]["by"] == "thandi"
    opt = sv.clean_spec({"sections": [{"questions": [{"kind": "single", "text": "Q", "options": [
        {"label": "A", "description": "d", "examples": "one\n\ntwo"}, {"label": "B"}]}]}]})["sections"][0]["questions"][0]["options"][0]
    assert opt["description"] == "d" and opt["examples"] == ["one", "two"]
