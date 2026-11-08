"""The review of 7 Nov 2026 (before the owner's test of phase 13.0.6): the bugs found and fixed."""

import inspect
from pathlib import Path

from eax import project_work as pw
from eax import projects as pj

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_next_version_keeps_the_prefix():
    assert pj.next_version("Version 1.0") == "Version 1.1"
    assert pj.next_version("0.3 draft") == "0.4"
    assert pj.next_version("v2") == "v3"
    assert pj.next_version("") == "0.1"


def test_repository_rebuilds_asked_during_a_build():
    sql = (ROOT / "migrations" / "sql" / "0028_repository_table.sql").read_text()
    assert "ADD COLUMN repo_again boolean" in sql
    assert "repo_again = (repo_state = 'building')" in inspect.getsource(pj.queue_rebuild)
    b = inspect.getsource(pj.build_repository)
    assert "CASE WHEN repo_again THEN 'pending' ELSE 'ready' END" in b
    assert "AND repo_state <> 'building'" in b                      # a library still loading does not take a running build
    assert 'p["mayan_cabinet_id"]' in b and "rename_cabinet(pc, p[\"name\"])" in b   # a renamed project keeps its folder
    assert "repo_started_at = now() WHERE id" in b                  # a long build is not taken for a stale one


def test_sign_off_and_documents():
    assert "FOR UPDATE OF r" in inspect.getsource(pw._request)          # two decisions at once are both counted
    assert "FOR UPDATE" in inspect.getsource(pw.raise_signoff)          # one open request per document
    assert "FROZEN" in inspect.getsource(pw.decide_signoff)
    assert "d.deleted_at IS NULL" in inspect.getsource(pw.signoffs)
    co = inspect.getsource(pj.check_out)
    assert "checked_out_by IS NULL RETURNING id" in co and "mayan.check_in(d[\"mayan_document_id\"])" in co
    assert 'next_version(d.get("user_version") or d.get("out_version"))' in inspect.getsource(pj.check_in)


def test_finish_and_merge():
    f = inspect.getsource(pw.finish)
    assert "get_projects_engine().begin()" in f and "mayan.trash(mid)" in f
    assert "d.archived_at IS NULL AND d.deleted_at IS NULL" in inspect.getsource(pw._finish)


def test_wizard_keeps_steps_added_meanwhile():
    assert "own_steps_seen" in inspect.getsource(pw.update)
    assert "own_steps_seen" in (WEB / "Projects.jsx").read_text()


def test_screens():
    js = (WEB / "Projects.jsx").read_text()
    for s in ("<ProjectPage key=", "Remove these goals", "useEffect(() => { setFtype(\"\"); setQ(\"\"); }, [phase]);", "const typed = add.trim()",
              "Clear the filters", 'f.status === "archived"', 'aria-label="Quorum"'):
        assert s in js
    tabs = (WEB / "ProjectTabs.jsx").read_text()
    assert "export function RestoreDialog" in tabs and "data?.may_manage" in tabs and "fmtStamp(" in tabs
    assert "RestoreDialog" in (WEB / "Backups.jsx").read_text()
    ops = (ROOT.parent / "ops" / "ops.py").read_text()
    assert '"files": {"config": False, "dbs": ["mayan"], "only": True' in ops
