"""Phase 13.0.2 (D273): every slow button is a background task, the task drawer and the task notifications (no database
needed: the work itself is checked against a database by hand, see docs/phase-13.0.2.md)."""

import re
from pathlib import Path

from eax import background as bg
from eax import notify
from eax import tasks as tk

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"
API = ROOT / "eax" / "api"


def test_migration_and_version():
    sql = (ROOT / "migrations" / "sql" / "0023_background.sql").read_text()
    assert "'0.14.1'" in sql and "'0023_background'" in sql
    assert "ADD COLUMN link" in sql and "ADD COLUMN progress " in sql and "ADD COLUMN role" in sql
    assert "'task'" in sql and "notifications_category_check" in sql
    assert "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()     # no logic in the database (D248)
    ver = (ROOT / "migrations" / "versions" / "0023_background.py").read_text()
    assert 'down_revision = "0022_projects"' in ver and 'revision = "0023_background"' in ver
    assert (ROOT / "migrations" / "sql" / "0023_background.sql").exists()


def test_every_kind_is_registered_with_a_label():
    for kind, fn in bg.WORK.items():
        assert tk.WORK[kind] is fn
        assert tk.KINDS[kind]
    for kind in ("merge.analyse", "merge.apply", "package.uploaded", "compare.run", "gap.create", "model.framework_moved",
                 "library.promoted", "pushdown.push", "draft.applied", "quality.recheck_type", "changelog.export",
                 "project.created", "project.library_zip", "tag.download", "tag.restore"):
        assert kind in tk.WORK


def test_routes_queue_the_slow_work():
    """Each slow route answers with a task (start) unless ?wait=true, or for a file with ?background=true."""
    src = "".join(p.read_text() for p in API.glob("*.py"))
    queued = set(re.findall(r'start\("([a-z_.]+)"', src))
    assert set(bg.WORK) <= queued, set(bg.WORK) - queued
    assert "def waiting()" in (API / "tasks.py").read_text()


def test_task_category_and_file_rules():
    assert "task" in notify.CATEGORIES
    assert tk.FILE_HOURS == 24
    src = (ROOT / "eax" / "tasks.py").read_text()
    assert "role = 'result'" in src and "_notify(conn, t, actor, True" in src and "_notify(conn, t, actor, False" in src
    assert "task_files_cleanup" in (ROOT / "eax" / "jobs.py").read_text()


def test_progress_outside_a_task_does_nothing():
    tk.progress(50, "no task running")      # no database, no error


def test_the_web_drawer_and_tab():
    assert not (WEB / "TaskBar.jsx").exists()
    drawer = (WEB / "TaskDrawer.jsx").read_text()
    assert "task-tab" in drawer and "task-drawer" in drawer and "Completed" in drawer and "⬇ Download" in drawer
    assert "<TaskDrawer />" in (WEB / "App.jsx").read_text()
    js = (WEB / "tasks.js").read_text()
    for name in ("export async function runTask", "export async function downloadTask", "export async function startDownload",
                 "export function dismissTask"):
        assert name in js
    notes = (WEB / "Notifications.jsx").read_text()
    assert '["tasks", `Background tasks' in notes and '<Inbox fixed="task" />' in notes
    # the slow buttons go through the tasks module
    for f, call in (("Merge.jsx", "runTask(post(`/api/v1/models/${model}/merges"), ("Versions.jsx", 'runTask(post("/api/v1/compare"'),
                    ("ModelOps.jsx", 'runTask(apiUpload("/api/v1/packages/import"'), ("Projects.jsx", 'runTask(apiFetch("/api/v1/projects"'),
                    ("ChangeLog.jsx", "downloadTask(`/api/v1/change-log/export"), ("QualityBits.jsx", "runTask(ask(")):
        assert call in (WEB / f).read_text(), f


def test_no_import_cycle_between_models_and_tasks():
    """api/tasks.py imports Free from api/models.py, so api/models.py must not import api/tasks.py when it loads
    (7 Nov 2026: that cycle stopped the API and the job runner starting)."""
    src = (Path(__file__).resolve().parents[1] / "eax" / "api" / "models.py").read_text(encoding="utf-8")
    assert not re.search(r"^from \.tasks import", src, re.M)


def test_task_history_kept_until_deleted_and_drawer_pinned():
    root = Path(__file__).resolve().parents[1]
    src = (root / "eax" / "tasks.py").read_text(encoding="utf-8")
    assert "def delete_history" in src and "status IN ('done', 'failed')" in src     # running tasks are never deleted
    api = (root / "eax" / "api" / "tasks.py").read_text(encoding="utf-8")
    assert 'request.args.get("history") == "true"' in api and "def delete(self, data)" in api
    web = (root.parent / "web" / "src" / "TaskDrawer.jsx").read_text(encoding="utf-8")
    assert "function TaskHistory" in web and "eax-tasks-pinned" in web and "tasks-pinned" in web
