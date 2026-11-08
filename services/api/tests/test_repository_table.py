"""Phase 13.0.6 (D290): the project repository as a table, by phase, with versions you give at every check-out and check-in."""

import re
from pathlib import Path

import pytest

from eax import projects as pj
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_version_label_and_the_one_put_in():
    assert pj._version_label("  0.3 draft ", True, "check-in") == "0.3 draft"
    assert pj._version_label("", False, "check-out") == ""      # check-out asks for no version (owner)
    with pytest.raises(EditError):
        pj._version_label("", True, "check-in")
    with pytest.raises(EditError):
        pj._version_label("x" * 41, False, "check-in")
    # left empty at check-in, the next one is put in
    assert [pj.next_version(v) for v in ("0.3 draft", "1.0", "v2", "", None, "final")] == ["0.4", "1.1", "v3", "0.1", "0.1", "0.1"]


def test_migration():
    sql = (ROOT / "migrations" / "sql" / "0028_repository_table.sql").read_text()
    for t in ("user_version", "out_version", "tags         text[]", "not_needed_reason", "not_needed_by", "added_by", "'0.14.6'"):
        assert t in sql
    assert re.search(r'version = "0\.1[4-9]\.\d+"', (ROOT / "version.toml").read_text())


def test_routes_and_screen():
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    assert '"/projects/<string:project>/items"' in api and "/not-needed" in api and "user_version" in api and "/documents/<string:doc>/tags" in api
    js = (WEB / "Projects.jsx").read_text()
    for s in ("function RepoTable", "function AddDocDialog", "function AddClassDialog", "function NotNeededDialog", "function TagsDialog",
              "function CheckInDialog", "export function nextVersion", "document_tags", "Your version", "System version", "Won't need", "Needed again", "＋ A new class…", "<RepoTable key={sel} p={p} codes={codes} phase={sel} />"):
        assert s in js
    assert "function CheckOutDialog" not in js       # check-out is one click: no version asked for


def test_tags_are_checked():
    src = (ROOT / "eax" / "projects.py").read_text()
    assert "def set_tags" in src and "TAG_MAX = 40" in src and 'out["document_tags"]' in src


def test_quorum_and_rejection():
    from eax import project_work as pw
    assert pw.quorum_of({}, 5) == 3 and pw.quorum_of({}, 2) == 2 and pw.quorum_of({"signoff_quorum": 9}, 3) == 3
    assert pw.quorum_of({"signoff_quorum": 1}, 4) == 1
    assert pw.settle_state(["approved"], 2) == "open"
    assert pw.settle_state(["approved", "approved"], 2) == "approved"
    assert pw.settle_state(["approved", "approved", "rejected"], 2) == "rejected"     # any rejection rejects it (owner)


def test_accept_archive_delete_and_file_types():
    src = (ROOT / "eax" / "projects.py").read_text()
    for s in ("def accept", "def set_hidden", "def set_quorum", "Say what changed in this version.", "(d.deleted_at IS NULL OR :del)"):
        assert s in src
    sql = (ROOT / "migrations" / "sql" / "0028_repository_table.sql").read_text()
    for s in ("accepted_note", "archived_at", "deleted_at", "signoff_quorum", "'Accepted'", "documents_live"):
        assert s in sql
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    assert "/accept" in api and "<any(archive,delete):how>" in api and "?show=archived,deleted" in api
    js = (WEB / "Projects.jsx").read_text()
    for s in ("function AcceptDialog", "Send for approval", "Show deleted (", "Show archived", "Delete with all versions",
              "function Quorum", "File type", "export const fileType", '"What changed" hint="(required)"'):
        assert s in js
