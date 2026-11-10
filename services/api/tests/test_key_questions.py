"""Key questions and placeholder views (owner, 9 Nov 2026): what they promise, without a database."""
import io
import zipfile
from pathlib import Path

import pytest

from eax import blank_files, key_questions, project_backup

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


@pytest.mark.parametrize("kind", sorted(blank_files.TYPES))
def test_every_placeholder_file_type_is_made(kind):
    data = blank_files.make(kind, "Impact of removing <an> app & co")
    assert data
    if kind in ("docx", "pptx", "xlsx"):
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert "[Content_Types].xml" in names
        if kind == "pptx":
            assert {"ppt/presentation.xml", "ppt/slides/slide1.xml", "ppt/theme/theme1.xml",
                    "ppt/slideMasters/slideMaster1.xml", "ppt/slideLayouts/slideLayout1.xml"} <= set(names)
    if kind == "pdf":
        assert data.startswith(b"%PDF")


def test_unknown_file_type_is_refused():
    with pytest.raises(ValueError):
        blank_files.make("exe", "x")


def test_file_names_are_safe():
    assert blank_files.file_name("PH-01 a/b:c*?", "docx") == "PH-01 abc.docx"
    assert blank_files.file_name("", "md") == "Placeholder.md"


def test_tables_are_backed_up_and_in_the_release():
    tables = [t for t, _w, _m in project_backup.TABLES]
    assert tables.index("placeholder_views") > tables.index("documents")
    assert tables.index("question_views") > tables.index("key_questions")
    sql = (ROOT / "migrations" / "sql" / "0032_repository_tags.sql").read_text()
    for t in ("key_questions", "placeholder_views", "question_views"):
        assert f"CREATE TABLE proj.{t}" in sql
    assert "proj.key_questions" in (ROOT / "migrations" / "versions" / "0032_repository_tags.py").read_text()


def test_the_wizard_and_tab_use_them():
    wiz = (WEB / "Projects.jsx").read_text()
    assert '"Key questions", "Views"' in wiz and "<QuestionMapping" in wiz and "makePlaceholderFiles" in wiz
    kq = (WEB / "KeyQuestions.jsx").read_text()
    for t in blank_files.TYPES:
        assert f"{t}:" in kq.split("FILE_TYPES = {")[1].split("};")[0]
    assert key_questions.from_wizard.__doc__ and "own:<key>" in key_questions.from_wizard.__doc__


def test_answers_are_rich_text_and_cleaned():
    assert key_questions._rich("One.\n\nTwo <b>x</b>") == "<p>One.</p><p>Two &lt;b&gt;x&lt;/b&gt;</p>"
    out = key_questions._rich('<p onclick="x()">Hi <script>bad()</script><b>there</b></p>')
    assert "script" not in out and "onclick" not in out and "<b>there</b>" in out
    assert key_questions._plain("<p>&nbsp;</p>") == ""


class _User:
    def __init__(self, name, roles=("user",)):
        self.username, self.roles = name, roles


def test_only_stakeholders_accept_in_the_application(monkeypatch):
    from eax import projects as pj
    from eax.metamodel_edit import EditError
    monkeypatch.setattr(pj, "project_row", lambda c, x: {"id": 1, "guid": "g", "name": "P", "status": "active"})
    monkeypatch.setattr(key_questions.pw, "need", lambda *a: set())
    monkeypatch.setattr(pj, "my_roles", lambda *a: {"architect"})
    with pytest.raises(EditError) as e:
        key_questions.decide(None, "g", _User("ann"), "q", "accepted")
    assert "stakeholders" in str(e.value)


def test_statuses_and_tables():
    assert key_questions.STATUSES == ("open", "answered", "accepted")
    sql = (ROOT / "migrations" / "sql" / "0032_repository_tags.sql").read_text()
    for t in ("question_events", "question_links"):
        assert f"CREATE TABLE proj.{t}" in sql
        assert t in [x for x, _w, _m in project_backup.TABLES]
    assert "CHECK (status IN ('open', 'answered', 'accepted'))" in sql


def test_every_sample_project_kind_has_questions():
    from eax.seed import sample_projects, sample_questions
    kinds = {code for code, *_ in sample_projects.SAMPLES}
    assert kinds <= set(sample_questions.BY_TEMPLATE)
    states = {q[4] for qs in sample_questions.BY_TEMPLATE.values() for q in qs}
    assert {"open", "answered", "accepted", "recorded", "rejected", "reopened"} <= states
    for qs in sample_questions.BY_TEMPLATE.values():
        for q in qs:
            assert q[4] == "open" or q[5], q[0]          # an answered one has its answer
    tab = (WEB / "Projects.jsx").read_text()
    assert '["questions", "Key questions"]' in tab and "<KeyQuestionsPanel" in tab
