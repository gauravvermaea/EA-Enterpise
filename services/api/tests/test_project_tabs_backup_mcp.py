"""Owner, 7 Nov 2026 (evening): the project's Viewpoints, Reports, Gaps and Compare tabs; backing up and restoring a project
with its models and documents; Build now as a background task; MCP tools to build models and projects."""

from pathlib import Path

from eax import background as bg
from eax import project_backup as pb
from eax import project_work as pw

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_viewpoints_have_phases():
    for code in ("VP-05", "VP-19", "VP-24", "VP-16"):
        assert pw.VIEWPOINT_PHASE[code]
    src = (ROOT / "eax" / "project_work.py").read_text()
    assert "def set_viewpoint_phase" in src and '"models": per_model' in src
    assert "/viewpoints/<string:code>/phase" in (ROOT / "eax" / "api" / "projects.py").read_text()
    assert "ALTER TABLE proj.project_viewpoints ADD COLUMN phase text" in (ROOT / "migrations" / "sql" / "0028_repository_table.sql").read_text()


def test_project_tabs():
    js = (WEB / "Projects.jsx").read_text()
    for t in ('["viewpoints", "Viewpoints"]', '["reports", "Model reports"]', '["analysis", "Gaps and comparison"]', '["stakeholders", "Stakeholders"]', "<ProjectBackupPanel"):
        assert t in js
    tabs = (WEB / "ProjectTabs.jsx").read_text()
    for s in ("export function ViewpointsByPhase", "export function ProjectReports", "export function ProjectGaps", "export function ProjectCompare",
              "<NewGapDialog", "<ModelReports", "export function RestoreProjectFile", "Restore as a new project"):
        assert s in tabs
    assert "export function NewGapDialog" in (WEB / "Versions.jsx").read_text()


def test_backup_restore_and_tasks():
    for k in ("project.backup", "project.restore", "project.repository"):
        assert k in bg.WORK and k in bg.KINDS
    assert pb.FORMAT == "eax-project-backup/2" and pb.SUFFIX == ".eaxproject.zip"
    tables = [t for t, _w, _m in pb.TABLES]
    for t in ("members", "items", "steps", "documents", "document_events", "signoff_requests", "signoff_decisions"):
        assert t in tables
    remap = dict((t, m) for t, _w, m in pb.TABLES)
    assert remap["documents"]["item_id"] == "items" and remap["steps"]["parent_step_id"] == "steps"
    assert remap["documents"]["mayan_document_id"] is None          # made again in Documents
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    for r in ('"/projects/<string:project>/backups"', '"/projects/<string:project>/backups/<string:file>/restore"', '"/projects/restore"',
              'start("project.repository"'):
        assert r in api
    for bad in ("../x.eaxproject.zip", "x.zip"):
        try:
            pb.path_of("p", bad)
            raise AssertionError("refused")
        except Exception as exc:  # noqa: BLE001
            assert "No such backup" in str(exc)


def test_mcp_build_tools():
    src = (ROOT / "eax" / "mcp_build.py").read_text()
    for t in ("async def how_to_build", "async def create_model", "async def add_entities", "async def add_relationships",
              "async def commit_my_changes", "async def create_project", "async def get_project", "async def complete_project_step",
              "async def accept_document", "def build_a_project", "def fill_a_model"):
        assert t in src
    assert "from . import mcp_build" in (ROOT / "eax" / "mcp_server.py").read_text()
    assert "how_to_build" in (ROOT / "eax" / "mcp_server.py").read_text()
