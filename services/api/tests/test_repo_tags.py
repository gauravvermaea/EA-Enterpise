"""The project's documents table, its versions and tags on the whole repository (owner, 8 Nov 2026, D312)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_migration():
    sql = (ROOT / "migrations/sql/0032_repository_tags.sql").read_text(encoding="utf-8")
    for x in ("CREATE TABLE proj.repo_tags", "CREATE TABLE proj.repo_tag_docs", "offered_templates bigint[]", "'0.15.1'"):
        assert x in sql, x
    assert "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()          # D248: no logic in the database
    assert 'version = "0.15.1"' in (ROOT / "version.toml").read_text()
    v = (ROOT / "migrations/versions/0032_repository_tags.py").read_text(encoding="utf-8")
    assert 'down_revision = "0031_project_bases"' in v


def test_server():
    src = (ROOT / "eax/repo_tags.py").read_text(encoding="utf-8")
    for x in ("def add", "def revert", "def zip_documents", "before application of tag", "Checked out now"):
        assert x in src, x
    pj = (ROOT / "eax/projects.py").read_text(encoding="utf-8")
    for x in ("def versions", "def download_version", "def class_templates", "def offer_template", "VERSION_ACTIONS"):
        assert x in pj, x
    api = (ROOT / "eax/api/projects.py").read_text(encoding="utf-8")
    for x in ("/repo-tags", "/repo-tags/<string:tag>/revert", "/repo-zip", "/versions/<int:version>", "/items/<string:item>/templates"):
        assert x in api, x
    bg = (ROOT / "eax/background.py").read_text(encoding="utf-8")
    assert '"project.repo_zip": project_repo_zip' in bg and '"project.repo_revert": project_repo_revert' in bg
    backup = (ROOT / "eax/project_backup.py").read_text(encoding="utf-8")
    assert '("repo_tags", "project_id = :p", {})' in backup and '"repo_tag_docs"' in backup


def test_screen():
    js = (ROOT.parent / "web/src/Projects.jsx").read_text(encoding="utf-8")
    for x in ("function ClassDocs", "function DocVersions", "function ClassTemplates", "function RepoTagsDialog", "function RevertDialog",
              "Documents <span", "Templates <span", "⬇ Download as at this tag", "Bring the repository back to it"):
        assert x in js, x


def test_phases_tab_and_tree():
    """Home keeps the cycle and About; a Phases tab has a tab per phase with Documents, Not added, Steps, Viewpoints; the
    template library is browsed folder after folder, with a tick on what was picked (owner, 8 Nov 2026)."""
    js = (ROOT.parent / "web/src/Projects.jsx").read_text(encoding="utf-8")
    for x in ('["phases", "Phases"]', "function PhasesTab", "function NotAddedClasses", "Templates/documents not in use <span", "/phases?phase=${sel}"):
        assert x in js, x
    tb = (ROOT.parent / "web/src/TemplateBrowser.jsx").read_text(encoding="utf-8")
    assert "function tree(files)" in tb and "✓ added" in tb and "＋ again" in tb
    bases = (ROOT / "eax/project_bases.py").read_text(encoding="utf-8")
    assert "def under_org" in bases and "Every project comes from the Organisation base" in bases


def test_wizard_charter_step():
    js = (ROOT.parent / "web/src/Projects.jsx").read_text(encoding="utf-8")
    assert '"Principles", "Charter",' in js and "function CharterStep" in js and "charter: Object.keys(d.charter" in js
    assert "def charter_from_wizard" in (ROOT / "eax/governance.py").read_text(encoding="utf-8")
    assert 'gov.charter_from_wizard(conn, p, user, d.get("charter"))' in (ROOT / "eax/projects.py").read_text(encoding="utf-8")


def test_review_fixes():
    """The documents review (8 Nov 2026): versions stay in step with Documents' files; the build copies a template once;
    the revert reads before it writes; a not-needed class with a checked-out document is refused."""
    src = (ROOT / "eax/projects.py").read_text(encoding="utf-8")
    for x in ("nothing changed. Choose the changed file", "copied_t", "template_id", "has versions 1 to", "Checked out now: "):
        assert x in src, x
    rt = (ROOT / "eax/repo_tags.py").read_text(encoding="utf-8")
    assert "files[d[\"id\"]] = mayan.download_version" in rt and "held <= d[\"versions\"]" in rt
    assert "ADD COLUMN template_id bigint" in (ROOT / "migrations/sql/0032_repository_tags.sql").read_text(encoding="utf-8")
    js = (ROOT.parent / "web/src/PinButton.jsx").read_text(encoding="utf-8")
    assert "☆ Pin" in js


def test_step_dates():
    """Steps and sub steps keep when they were opened and closed, and their history (owner, 8 Nov 2026)."""
    sql = (ROOT / "migrations/sql/0032_repository_tags.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE proj.step_events" in sql and "ALTER COLUMN added_at SET DEFAULT now()" in sql
    src = (ROOT / "eax/projects.py").read_text(encoding="utf-8")
    assert "def _step_event" in src and '"open_date"' in src
    js = (ROOT.parent / "web/src/Projects.jsx").read_text(encoding="utf-8")
    assert "function StepHistory" in js and "Opened on" in js
