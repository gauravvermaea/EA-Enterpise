"""Releases of EA Explorer from its git repository (phase 36, D417, D498). Standard library and the git command only.

Shared by the updater (eaxcli/updater.py, `eax update`), the operations helper's listing of versions and `eax deploy`
(phase 36, D498): one place that knows the channels, how versions are named and compared, which versions a channel
offers, the release notes, and how to fetch one version's files.

Channels (D417):
  prod    branch `release`, tags vX.Y.Z               on by default
  rc      branch `rc`,      tags vX.Y.Z-rc.N          off until a Super Admin or IT Admin enables it
  latest  branch `main`,    each commit               off until enabled

Release notes (D510): `releases/<version>.md` in the repository at that version's tag (e.g. releases/0.19.0.md,
releases/0.19.0-rc.2.md), written by tools/release.py when the tag is made. An RC without its own file shows its
release's file (releases/0.19.0.md) when there is one. Latest (untagged commits) shows the commits' one-line messages
since the installed commit, newest first.

Forward only: a channel never offers a version lower than (or equal to) the installed one; on Latest only commits that
come after the installed commit. Several releases behind (D417): the update goes one release after another, in order.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

CHANNELS = {
    "prod": {"label": "Prod", "branch": "release", "default": True,
             "about": "Released versions (tags vX.Y.Z on the release branch). Recommended."},
    "rc": {"label": "RC", "branch": "rc", "default": False,
           "about": "Release candidates (tags vX.Y.Z-rc.N) and releases: try a version before it is released."},
    "latest": {"label": "Latest", "branch": "main", "default": False,
               "about": "Every commit on main, untested between releases. For trying changes only."},
}
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?$")
NOTES_DIR = "releases"
LATEST_DEPTH = 200          # commits of main looked at for Latest


class ReleaseError(RuntimeError):
    """Something about the repository or a version that the person must hear in plain words."""


# ---------------------------------------------------------------- versions
def parse(version: str) -> tuple[int, int, int, int, int] | None:
    """'0.19.0' or 'v0.19.0-rc.2' -> a key that sorts versions: a release sorts after its RCs. None if not a version."""
    m = TAG.match(version if version.startswith("v") else f"v{version}")
    if not m:
        return None
    major, minor, patch, rc = m.groups()
    return (int(major), int(minor), int(patch), 0 if rc else 1, int(rc or 0))


def base(version: str) -> str:
    """'0.19.0-rc.2' -> '0.19.0'."""
    return version.lstrip("v").split("-")[0]


def is_rc(version: str) -> bool:
    return "-rc." in version


def newer(a: str, b: str) -> bool:
    """Is version a newer than version b? (unknown versions are never newer)"""
    ka, kb = parse(a), parse(b)
    return bool(ka and kb and ka > kb)


def name_of(tag: str) -> str:
    return tag.lstrip("v")


@dataclass
class Version:
    """One version a channel offers."""
    channel: str
    version: str             # 0.19.0, 0.19.0-rc.2, or for Latest the version.toml at that commit
    ref: str                 # the tag (v0.19.0) or, for Latest, the commit id
    commit: str = ""
    date: str = ""
    title: str = ""          # Latest: the commit's one-line message
    notes: str = ""
    steps: list[str] = field(default_factory=list)   # filled by plan(): the versions gone through, in order

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- git
def git(*args: str, cwd: str | os.PathLike | None = None, timeout: int = 300, check: bool = True) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo")
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except FileNotFoundError as exc:
        raise ReleaseError("git is not installed here.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ReleaseError(f"git {args[0]} took longer than {timeout} s.") from exc
    if check and r.returncode:
        msg = (r.stderr or r.stdout).strip().splitlines()
        raise ReleaseError(f"git {args[0]} failed: {msg[-1] if msg else r.returncode}")
    return r.stdout


def check_url(url: str) -> str:
    """The repository link as given, checked a little (https, http, ssh, git, or a local path for tests)."""
    url = (url or "").strip()
    if not url:
        raise ReleaseError("No repository link is set: System admin > Updates (or EAX_UPDATE_GIT_URL in the config file).")
    if not re.match(r"^(https?://|ssh://|git@|git://|file://|/)", url) and not Path(url).exists():
        raise ReleaseError(f"{url} does not look like a git repository link (https://...).")
    return url


def remote_refs(url: str) -> dict[str, str]:
    """Every tag and branch head of the repository: {'refs/tags/v0.19.0': commit, 'refs/heads/main': commit}."""
    out = git("ls-remote", "--tags", "--heads", check_url(url), timeout=60)
    refs: dict[str, str] = {}
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.endswith("^{}"):          # an annotated tag: the commit it points at
            refs[ref[:-3]] = sha
        else:
            refs.setdefault(ref, sha)
    return refs


def tags(url: str) -> dict[str, str]:
    """The version tags: {'v0.19.0': commit, 'v0.19.0-rc.1': commit}."""
    return {r[len("refs/tags/"):]: s for r, s in remote_refs(url).items()
            if r.startswith("refs/tags/") and TAG.match(r[len("refs/tags/"):])}


def cache_repo(folder: str | os.PathLike) -> Path:
    """A bare repository kept to read notes and commits without touching the installation (work/updates/cache.git)."""
    p = Path(folder)
    if not (p / "HEAD").exists():
        p.mkdir(parents=True, exist_ok=True)
        git("init", "--bare", "--quiet", str(p))
    return p


def fetch(cache: str | os.PathLike, url: str, ref: str, depth: int = 1) -> str:
    """Fetches one tag or branch into the cache repository; its commit."""
    spec = f"+refs/tags/{ref}:refs/tags/{ref}" if TAG.match(ref) else f"+refs/heads/{ref}:refs/remotes/origin/{ref}"
    git("fetch", "--quiet", "--no-tags", *(["--depth", str(depth)] if depth else []), check_url(url), spec, cwd=cache)
    local = f"refs/tags/{ref}" if TAG.match(ref) else f"refs/remotes/origin/{ref}"
    return git("rev-parse", f"{local}^{{commit}}", cwd=cache).strip()


def show(cache: str | os.PathLike, commit: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=cache, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def version_at(cache: str | os.PathLike, commit: str) -> str:
    """The version (services/api/version.toml) at a commit."""
    text = show(cache, commit, "services/api/version.toml") or ""
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else ""


def notes_for(cache: str | os.PathLike, commit: str, version: str) -> str:
    """The release notes file at that commit: releases/<version>.md, or for an RC its release's file."""
    for v in (version, base(version)):
        text = show(cache, commit, f"{NOTES_DIR}/{v}.md")
        if text:
            return text.strip()
    return ""


# ---------------------------------------------------------------- what a channel offers
def available(url: str, channel: str, installed: dict, cache: str | os.PathLike, with_notes: bool = True) -> list[Version]:
    """The versions the channel offers above the installed one, oldest first (forward only, D417).
    installed: {'version': '0.18.0', 'commit': '...'}."""
    if channel not in CHANNELS:
        raise ReleaseError(f"Unknown channel {channel}: prod, rc or latest.")
    cache = cache_repo(cache)
    have = installed.get("version") or "0.0.0"
    if channel == "latest":
        return _latest(url, installed, cache, with_notes)
    out = []
    for tag, sha in tags(url).items():
        v = name_of(tag)
        if channel == "prod" and is_rc(v):
            continue
        if not newer(v, have):
            continue
        out.append(Version(channel=channel, version=v, ref=tag, commit=sha))
    out.sort(key=lambda x: parse(x.version))
    if with_notes:
        for x in out:
            try:
                fetch(cache, url, x.ref)
                x.notes = notes_for(cache, x.commit, x.version)
                x.date = git("log", "-1", "--format=%cI", x.commit, cwd=cache).strip()
            except ReleaseError:
                pass
    return out


def _latest(url: str, installed: dict, cache: Path, with_notes: bool) -> list[Version]:
    head = fetch(cache, url, CHANNELS["latest"]["branch"], depth=LATEST_DEPTH)
    mine = installed.get("commit") or ""
    rows = git("log", "--format=%H%x09%cI%x09%s", f"-{LATEST_DEPTH}", head, cwd=cache).splitlines()
    commits = [r.split("\t", 2) for r in rows if r.count("\t") >= 2]
    found = next((i for i, c in enumerate(commits) if mine and c[0].startswith(mine)), None)
    newer_ones = commits[:found] if found is not None else commits[:1]   # unknown installed commit: the newest only
    have = installed.get("version") or "0.0.0"
    out = []
    for sha, date, title in newer_ones:
        v = version_at(cache, sha)
        if v and parse(v) and parse(have) and parse(v) < parse(have):
            continue                     # a commit whose version is lower than the installed one: never backwards
        out.append(Version(channel="latest", version=v, ref=sha, commit=sha, date=date, title=title))
    out.reverse()                        # oldest first, like the other channels
    if with_notes and out:
        rng = [f"{commits[found][0]}..{head}"] if found is not None else ["-20", head]
        since = git("log", "--format=- %h %s", *rng, cwd=cache, check=False)
        for x in out:
            x.notes = ("Commits since the installed version (newest first):\n" + since.strip()) if since.strip() else x.title
    return out


def plan(offered: list[Version], target: str = "") -> Version:
    """The version to move to and the versions gone through on the way (D417: one release at a time).
    target: a version (0.19.0, 0.19.0-rc.2) or, on Latest, a commit; empty: the newest offered."""
    if not offered:
        raise ReleaseError("Nothing newer on this channel: the installed version is the newest.")
    if target:
        pick = next((x for x in offered if x.version == target.lstrip("v") or x.ref == target
                     or (x.commit and target and x.commit.startswith(target))), None)
        if not pick:
            raise ReleaseError(f"{target} is not offered: it is not on this channel, or not newer than the installed "
                               "version (updates only go forward).")
    else:
        pick = offered[-1]
    if pick.channel == "latest":
        pick.steps = [pick.ref]
        return pick
    upto = [x for x in offered if parse(x.version) <= parse(pick.version)]
    by_release: dict[str, Version] = {}
    for x in upto:                       # each release once: its final version if offered, else its newest RC
        b = base(x.version)
        if b not in by_release or parse(x.version) > parse(by_release[b].version):
            by_release[b] = x
    by_release[base(pick.version)] = pick
    pick.steps = [by_release[b].ref for b in sorted(by_release, key=lambda v: parse(v))]
    return pick


# ---------------------------------------------------------------- a version's files (eax deploy, non-git installs)
def export(url: str, ref: str, dest: str | os.PathLike, cache: str | os.PathLike | None = None) -> str:
    """Writes the files of one version (a tag, branch or commit) into dest, without git history; its commit.
    Used by `eax deploy` (D498) and by updates of an installation that is not a git checkout."""
    tmp = None
    if cache is None:
        tmp = tempfile.mkdtemp(prefix="eax-release-")
        cache = Path(tmp) / "cache.git"
    try:
        c = cache_repo(cache)
        try:
            sha = fetch(c, url, ref)
        except ReleaseError:
            git("fetch", "--quiet", "--depth", "1", check_url(url), ref, cwd=c)   # a commit id
            sha = git("rev-parse", "FETCH_HEAD", cwd=c).strip()
        Path(dest).mkdir(parents=True, exist_ok=True)
        archive = Path(tempfile.mkdtemp(prefix="eax-archive-")) / "v.tar"
        git("archive", "--format=tar", "-o", str(archive), sha, cwd=c)
        with tarfile.open(archive) as t:
            t.extractall(dest, filter="data")
        shutil.rmtree(archive.parent, ignore_errors=True)
        return sha
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- supported versions (8.5, D514)
def supported(installed: str, releases: list[str]) -> tuple[bool, str]:
    """The supported-versions policy (docs/release-process.md): the newest release line (X.Y) and the one before are
    supported; a release candidate or a Latest build only until its release is out."""
    finals = sorted({base(r) for r in releases if not is_rc(r) and parse(r)}, key=parse)
    if not finals or not parse(installed):
        return True, ""
    lines = []
    for f in reversed(finals):
        line = ".".join(f.split(".")[:2])
        if line not in lines:
            lines.append(line)
    keep = lines[:2]
    mine = ".".join(base(installed).split(".")[:2])
    if is_rc(installed) and base(installed) in finals:
        return False, f"{installed} is a release candidate of {base(installed)}, which is now released: update to it."
    if mine in keep or newer(installed, finals[-1]):
        return True, ""
    return False, (f"{installed} is no longer supported: the supported release lines are {', '.join(keep)}. "
                   f"Update to {finals[-1]}.")


def main(argv: list[str]) -> int:
    """python3 releases.py list <url> <channel> <installed-version> [<installed-commit>] [--cache <folder>]
    Prints the versions offered as JSON (used by the operations helper, which has no internet itself)."""
    if len(argv) >= 4 and argv[0] == "list":
        cache = argv[argv.index("--cache") + 1] if "--cache" in argv else tempfile.mkdtemp(prefix="eax-cache-")
        rest = [a for i, a in enumerate(argv) if a != "--cache" and (i == 0 or argv[i - 1] != "--cache")]
        installed = {"version": rest[3], "commit": rest[4] if len(rest) > 4 else ""}
        try:
            got = available(rest[1], rest[2], installed, cache)
            print(json.dumps({"versions": [v.as_dict() for v in got]}))
            return 0
        except ReleaseError as exc:
            print(json.dumps({"error": str(exc)}))
            return 1
    print(main.__doc__)
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
