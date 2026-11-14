"""Install and upgrade tests (D582): EA Explorer's own tools, driven from outside, then checked through the API.

  install   eax deploy --console --answers <file> --yes in an installation folder (this checkout, or a version exported
            into a new folder with eaxcli/releases.export), then waits for /api/health, then the caller runs the suites;
  upgrade   the --from version installed as above (a fresh folder), its state noted (version, database migration, row
            counts), then the D417 updater (eax update --to <version> [--url <repo>] --yes) moves it to --to, and the
            state is checked again: the version is the new one, the migration is the new code's head, and no count
            went down. Then the caller runs the suites on the upgraded installation.

Every outside command goes through `sh(argv, cwd) -> exit code`, and every wait through `sleep`, so the tests run all of
it with fakes (tests/test_testbench.py)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from pathlib import Path

from . import shared
from .target import Client

Sh = Callable[[list[str], Path], int]


def real_sh(argv: list[str], cwd: Path) -> int:
    print("$ " + " ".join(str(a) for a in argv), flush=True)
    return subprocess.call([str(a) for a in argv], cwd=str(cwd))


def launcher(folder: Path) -> list[str]:
    """The installation's own eax, as the person runs it there."""
    return ["cmd", "/c", str(folder / "eax.cmd")] if os.name == "nt" else ["bash", str(folder / "eax.sh")]


def version_of(folder: Path) -> str:
    try:
        return tomllib.loads((folder / "services" / "api" / "version.toml").read_text(encoding="utf-8"))["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return ""


def migration_head(folder: Path) -> str:
    """The newest database migration in a code tree: the revision no other revision names as its down_revision."""
    revs, downs = set(), set()
    for p in (folder / "services" / "api" / "migrations" / "versions").glob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        r = re.search(r'^revision\s*=\s*["\']([^"\']+)', text, re.M)
        d = re.search(r'^down_revision\s*=\s*(.+)$', text, re.M)
        if r:
            revs.add(r.group(1))
        if d:
            downs.update(re.findall(r'["\']([^"\']+)["\']', d.group(1)))
    heads = sorted(revs - downs)
    return heads[-1] if heads else ""


def wait_healthy(target: str, minutes: float = 20, sleep=time.sleep, clock=time.time, client_of=Client) -> bool:
    t0 = clock()
    while clock() - t0 < minutes * 60:
        s, _ = client_of(target).get("/api/health", timeout=15)
        if s == 200:
            return True
        sleep(10)
    return False


def export(ref: str, dest: Path, url: str) -> str:
    """A version's files into dest (no git history), with eaxcli/releases.py, as `eax deploy` does."""
    sys.path.insert(0, str(shared.ROOT)) if str(shared.ROOT) not in sys.path else None
    from eaxcli import releases  # noqa: PLC0415
    return releases.export(url, ref, dest)


def install(run, folder: Path, answers: Path, target: str, sh: Sh = real_sh, sleep=time.sleep, clock=time.time,
            client_of=Client, minutes: float = 30) -> bool:
    rec = run.recorder("install")
    t0 = clock()
    code = sh([*launcher(folder), "deploy", "--console", "--answers", str(answers.resolve()), "--yes"], folder)
    rec("eax deploy with the answers file", "passed" if code == 0 else "failed", f"exit code {code}; folder {folder}",
        int((clock() - t0) * 1000))
    if code != 0:
        return False
    ok = wait_healthy(target, minutes, sleep, clock, client_of)
    rec("EA Explorer is healthy after the install (/api/health)", "passed" if ok else "failed",
        "" if ok else f"{target}/api/health did not answer within {int(minutes)} minutes", int((clock() - t0) * 1000))
    return ok


def state(client: Client) -> dict:
    """version, migration and counts: the bench's state endpoint (0.19.0 on), else the API description and the model list."""
    s, a = client.get("/api/v1/admin/testbench/state")
    if s == 200 and isinstance(a, dict):
        return a
    out: dict = {"counts": {}, "migration": None, "version": ""}
    s, spec = client.get("/api/openapi.json")
    if s == 200 and isinstance(spec, dict):
        out["version"] = str((spec.get("info") or {}).get("version") or "")
    s, models = client.get("/api/v1/models")
    if s == 200:
        items = models if isinstance(models, list) else (models.get("items") or models.get("models") or []) if isinstance(models, dict) else []
        out["counts"]["models"] = len(items)
    out["note"] = "this version has no test bench state endpoint (0.19.0 on): its version and model count only"
    return out


def compare(rec, before: dict, after: dict, to_version: str, to_head: str) -> None:
    v = after.get("version", "")
    rec("the version after the upgrade", "passed" if v == to_version else "failed",
        f"{before.get('version') or '?'} -> {v or '?'} (expected {to_version})", 0)
    m = after.get("migration")
    if m is None:
        rec("the database migration after the upgrade", "skipped", "the target did not say (no state endpoint)", 0)
    else:
        rec("the database migration after the upgrade", "passed" if not to_head or m == to_head else "failed",
            f"{before.get('migration') or '?'} -> {m} (the new code's head: {to_head or '?'})", 0)
    for name, n in (before.get("counts") or {}).items():
        if n is None:
            continue
        a = (after.get("counts") or {}).get(name)
        rec(f"data kept: {name}", "passed" if a is not None and a >= n else "failed", f"{n} before, {a} after", 0)


def upgrade(run, from_ref: str, to: str, folder: Path, answers: Path, target: str, login: Callable[[], Client],
            url: str = "", sh: Sh = real_sh, sleep=time.sleep, clock=time.time, client_of=Client,
            exporter=export, seed: Callable[[Client], None] | None = None, rollback: bool = True) -> bool:
    """from_ref: a tag or version (exported into folder); to: a tag or version, or a code folder (its version and its
    migrations; the updater takes it with --url). login() gives a Super Admin client once the installation answers.
    Then (R3.11) the updater's own backup is checked and, unless rollback is False, `eax rollback` is run and checked."""
    rec = run.recorder("upgrade")
    to_path = Path(to) if Path(to).is_dir() else None
    to_version = version_of(to_path) if to_path else to.lstrip("v")
    if not folder.joinpath("eax.sh").exists():
        try:
            sha = exporter(from_ref if from_ref.startswith("v") or not from_ref[:1].isdigit() else f"v{from_ref}", folder, url)
            rec(f"version {from_ref} fetched", "passed", f"commit {str(sha)[:12]} into {folder}", 0)
        except Exception as exc:  # noqa: BLE001
            rec(f"version {from_ref} fetched", "failed", str(exc)[:500], 0)
            return False
    if not install(run, folder, answers, target, sh, sleep, clock, client_of):
        return False
    client = login()
    if seed:
        seed(client)
    before = state(client)
    rec("the state before the upgrade", "passed", f"version {before.get('version')}, migration {before.get('migration')}, "
        f"counts {before.get('counts')}" + (f"; {before['note']}" if before.get("note") else ""), 0)
    argv = [*launcher(folder), "update", "--to", to_version, "--yes"]
    if to_path or url:
        argv[-1:-1] = ["--url", str(to_path or url)]
    t0 = clock()
    code = sh(argv, folder)
    rec(f"eax update --to {to_version} (the D417 updater)", "passed" if code == 0 else "failed", f"exit code {code}",
        int((clock() - t0) * 1000))
    if code != 0:
        return False
    ok = wait_healthy(target, 30, sleep, clock, client_of)
    rec("EA Explorer is healthy after the upgrade", "passed" if ok else "failed", "", int((clock() - t0) * 1000))
    if not ok:
        return False
    client = login()
    after = state(client)
    code_tree = to_path or (shared.ROOT if version_of(shared.ROOT) == to_version else None)
    compare(rec, before, after, to_version, migration_head(code_tree) if code_tree else "")
    pre_upgrade_backup(rec, client)
    if rollback:
        roll_back(rec, folder, before, target, login, sh, sleep, clock, client_of)
    return not any(r.outcome == "failed" for r in run.results if r.suite == "upgrade")


def pre_upgrade_backup(rec, client: Client) -> None:
    """The updater took its full backup first (R3.11: "backup ... roll back"): a pinned infrastructure backup of kind
    before-upgrade is listed."""
    s, b = client.get("/api/v1/admin/backups")
    rows = (((b or {}).get("infrastructure") or {}).get("infrastructure") or []) if s == 200 and isinstance(b, dict) else []
    mine = [x for x in rows if x.get("kind") == "before-upgrade"]
    rec("a full backup was taken before the upgrade", "passed" if mine else "failed",
        f"{mine[0].get('name')} ({'pinned' if mine[0].get('pinned') else 'not pinned'})" if mine else
        (f"none listed (GET /admin/backups: {s})" if s != 200 else "no before-upgrade backup listed"), 0)


def roll_back(rec, folder: Path, before: dict, target: str, login: Callable[[], Client], sh: Sh = real_sh,
              sleep=time.sleep, clock=time.time, client_of=Client) -> bool:
    """`eax rollback --yes` after the upgrade (R3.11): back to the version before, its data as at the update."""
    t0 = clock()
    code = sh([*launcher(folder), "rollback", "--yes"], folder)
    rec("eax rollback (back to the version before)", "passed" if code == 0 else "failed", f"exit code {code}",
        int((clock() - t0) * 1000))
    if code != 0:
        return False
    ok = wait_healthy(target, 30, sleep, clock, client_of)
    rec("EA Explorer is healthy after the roll back", "passed" if ok else "failed", "", int((clock() - t0) * 1000))
    if not ok:
        return False
    back = state(login())
    v_ok = back.get("version") == before.get("version")
    rec("the version after the roll back", "passed" if v_ok else "failed",
        f"{back.get('version') or '?'} (expected {before.get('version') or '?'})", 0)
    for name, n in (before.get("counts") or {}).items():
        if n is None:
            continue
        a = (back.get("counts") or {}).get(name)
        rec(f"data kept after the roll back: {name}", "passed" if a is not None and a >= n else "failed",
            f"{n} before the upgrade, {a} after the roll back", 0)
    return v_ok
