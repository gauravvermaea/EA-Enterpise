"""R2.46 (owner, 12 Nov 2026, screenshot): an on-demand infrastructure backup failed with only "tar: error exit delayed
from previous errors", which says neither which file set nor which file. Each set is now archived by tarset
(services/backup/tarset.sh): a file that changed while it was read is a warning; one that could not be read fails the
backup with tar's own lines and a last line naming the set (the line the Backups page shows)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TARSET = REPO / "services" / "backup" / "tarset.sh"
pytestmark = pytest.mark.skipif(not shutil.which("sh"), reason="needs a POSIX shell")


def _run(tmp_path: Path, code: int, lines: str) -> subprocess.CompletedProcess:
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    fake = bin_ / "tar"
    fake.write_text(f"#!/bin/sh\nprintf '%s' '{lines}' >&2\nexit {code}\n")
    fake.chmod(0o755)
    (tmp_path / "src").mkdir()
    script = f'set -eu\n. "{TARSET}"\ntarset reports "{tmp_path}/src" "{tmp_path}/reports.tar.gz" --exclude=./x\necho after\n'
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True,
                          env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"})


def test_an_unreadable_file_names_the_set_and_the_file(tmp_path):
    r = _run(tmp_path, 2, "tar: ./superset.db-journal: Cannot open: Permission denied\ntar: Exiting with failure status due to previous errors\ntar: error exit delayed from previous errors\n")
    assert r.returncode == 2 and "after" not in r.stdout                    # the backup stops
    last = r.stderr.strip().splitlines()[-1]                               # what the Backups page shows
    assert last.startswith("files reports (") and "superset.db-journal: Cannot open: Permission denied" in last
    assert "error exit delayed" not in last
    assert not (tmp_path / "reports.tar.gz.err").exists()


def test_a_file_changed_while_read_is_a_warning(tmp_path):
    r = _run(tmp_path, 1, "tar: ./log/app.log: file changed as we read it\n")
    assert r.returncode == 0 and "after" in r.stdout and "warning" in r.stdout and "app.log" in r.stdout


def test_backup_sh_uses_it_for_every_set():
    src = (REPO / "services" / "backup" / "backup.sh").read_text()
    assert ". /usr/local/bin/tarset.sh" in src and "tarset documents" in src and 'tarset "$NAME"' in src
    assert "-czf \"$TARGET/files" not in src                               # no bare tar left
