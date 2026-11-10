"""Versioned releases with notes (8.5, D513): makes the notes file of a release and prints the git commands that release
it. It never commits, tags or pushes: the owner runs git (docs/release-process.md).

  python tools/release.py notes 0.19.0            writes releases/0.19.0.md from the commits since the last release
                                                  (edit it before committing); -rc.N for a release candidate
  python tools/release.py commands 0.19.0         the git commands for a release (or 0.20.0-rc.1 for an RC)
  python tools/release.py check v0.19.0           CI on a tag: the tag, services/api/version.toml and the notes agree

Channels (D417): a release is tagged vX.Y.Z on the `release` branch; a release candidate vX.Y.Z-rc.N on `rc`; `main`
is Latest. Installations list the tags and read releases/<version>.md at the tag (eaxcli/releases.py).
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = re.compile(r"^v?(\d+\.\d+\.\d+)(?:-rc\.(\d+))?$")


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def toml_version() -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "services" / "api" / "version.toml").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else ""


def split(v: str) -> tuple[str, str]:
    m = TAG.match(v)
    if not m:
        raise SystemExit(f"{v} is not a version: 0.19.0 or 0.19.0-rc.1")
    return m.group(1), m.group(2) or ""


def last_tag() -> str:
    tags = [t for t in git("tag", "--list", "v*", "--sort=-v:refname").splitlines() if TAG.match(t)]
    return tags[0] if tags else ""


def notes(v: str) -> Path:
    base, rc = split(v)
    name = f"{base}-rc.{rc}" if rc else base
    path = ROOT / "releases" / f"{name}.md"
    if path.exists():
        print(f"{path.relative_to(ROOT)} exists; edit it by hand.")
        return path
    since = last_tag()
    log = git("log", "--format=- %s", f"{since}..HEAD" if since else "-50")
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        f"# EA Explorer {name}\n\n"
        f"{'Release candidate' if rc else 'Release'} of {date.today().isoformat()}"
        f"{f', since {since}' if since else ''}.\n\n"
        "## What is new\n\n(Write the two or three things people will notice. The changes below are the commits.)\n\n"
        "## Changes\n\n" + (log or "- (no commits found)") + "\n\n"
        "## Before you update\n\n- A full backup is taken first, and the update goes one release at a time.\n"
        "- Read any notes above about settings to check after the update.\n",
        encoding="utf-8", newline="\n")
    print(f"Wrote {path.relative_to(ROOT)}: edit it, then run: python tools/release.py commands {v}")
    return path


def commands(v: str) -> None:
    base, rc = split(v)
    tag = f"v{base}-rc.{rc}" if rc else f"v{base}"
    branch = "rc" if rc else "release"
    note = f"releases/{base}-rc.{rc}.md" if rc else f"releases/{base}.md"
    if toml_version() != base:
        print(f"Note: services/api/version.toml says {toml_version()}, not {base}: change it first (in the same commit).")
    print(f"""# On main, with the notes written ({note}) and every test green:
git checkout main
git pull
git add {note} services/api/version.toml
git commit -m "Release {tag[1:]}"
git push origin main

# Move the {branch} branch to this commit and tag it ({'release candidate' if rc else 'release'}):
git checkout {branch}
git merge --ff-only main
git tag -a {tag} -m "EA Explorer {tag[1:]}"
git push origin {branch} {tag}
git checkout main
# CI checks the tag and makes the GitHub release with the notes; installations see {tag} on the {'RC' if rc else 'Prod'} channel.""")


def check(ref: str) -> int:
    base, rc = split(ref)
    problems = []
    if toml_version() != base:
        problems.append(f"services/api/version.toml says {toml_version()}, the tag {ref}")
    files = [ROOT / "releases" / f"{base}-rc.{rc}.md", ROOT / "releases" / f"{base}.md"] if rc else [ROOT / "releases" / f"{base}.md"]
    if not any(f.exists() for f in files):
        problems.append(f"no release notes: {', '.join(str(f.relative_to(ROOT)) for f in files)}")
    for p in problems:
        print(f"release check: {p}")
    if not problems:
        print(f"release check: {ref} is consistent")
    return 1 if problems else 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "notes":
        notes(argv[1])
        return 0
    if len(argv) == 2 and argv[0] == "commands":
        commands(argv[1])
        return 0
    if len(argv) == 2 and argv[0] == "check":
        return check(argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
