"""EA Explorer's own documentation (D550): the Documentation page's list, rendering and search, the Enterprise library's
documentation folder, no file needing Git LFS, and the documents kept current with each version."""

import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

from eax import __version__
from eax import shipped_docs as D

REPO = Path(__file__).resolve().parents[3]
LIMIT = 50 * 1024 * 1024


@pytest.fixture(autouse=True)
def _repo_docs(monkeypatch):
    monkeypatch.setenv("EAX_DOCS_DIR", str(REPO))


def test_the_list_has_every_shipped_document_grouped():
    out = D.listing()
    assert out["version"] == __version__
    keys = {d["key"] for d in out["documents"]}
    assert {"readme", "command-line-help", "capabilities", "decisions", "build-phases", "navigation"} <= keys
    assert "todo" not in keys                                     # working notes are hidden
    assert all(d["group"] in out["groups"] for d in out["documents"])
    every_md = {p.relative_to(REPO / "docs").as_posix()[:-3].replace("/", "~") for p in (REPO / "docs").rglob("*.md")
                if p.name not in D.HIDDEN and not p.relative_to(REPO / "docs").as_posix().startswith(("requirements/", "drafts/"))}
    assert every_md <= keys                                       # a new document appears without a code change
    assert {d["group"] for d in out["documents"] if d["key"] in ("readme", "capabilities", "deployment", "decisions", "mcp")} == {
        "Getting started", "Using EA Explorer", "Administration and operations", "Design and decisions", "Reference"}


def test_rendering_is_safe_and_keeps_tables_code_and_links():
    html = D.render("# Title\n<script>alert(1)</script> and <img src=x onerror=alert(2)>\n\n"
                    "Read [the phase](phase-24.md#as-built), [the readme](../README.md), [a site](https://x.org) and "
                    "[bad](javascript:alert(3)) or [data](data:text/html,x).\n\n"
                    "| A | B |\n|---|---|\n| 1 | `x <b>` |\n\n```\n<div>code</div>\n```\n\n- one\n  - two\n- **three**")
    assert "<script" not in html and "&lt;script&gt;" in html
    assert "<img" not in html and "onerror" in html                 # shown as text, never as a tag
    assert 'href="#/documentation/phase-24?at=as-built"' in html and 'href="#/documentation/readme"' in html
    assert 'href="https://x.org" target="_blank" rel="noopener noreferrer"' in html
    assert "javascript:" not in html.split("href=")[-1] and 'href="javascript' not in html and 'href="data:' not in html
    assert "<table>" in html and "<code>x &lt;b&gt;</code>" in html and "<pre><code>&lt;div&gt;code&lt;/div&gt;</code></pre>" in html
    assert "<ul>" in html and "<strong>three</strong>" in html and '<h1 id="doc-title">Title</h1>' in html


def test_every_document_renders_and_the_command_line_is_shown_as_text():
    for d in D.listing()["documents"]:
        out = D.document(d["key"])
        assert out["version"] == __version__ and out["html"]
        assert "<script" not in out["html"].lower()
    assert D.document("command-line-help")["html"].startswith('<pre class="doc-help">')
    with pytest.raises(LookupError):
        D.document("../../etc/passwd")


def test_search_finds_documents_holding_every_word():
    hits = D.search("housekeeping dry run")
    assert hits and all({"key", "title", "snippet"} <= set(h) for h in hits)
    assert not D.search("zzzz-no-such-word-anywhere")
    assert D.search("") == []


def _libsvc_docs():
    spec = importlib.util.spec_from_file_location("libsvc_shipped_docs", REPO / "services/library/libsvc/shipped_docs.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_library_folder_holds_the_same_documents_in_the_same_groups():
    L = _libsvc_docs()
    items = L.plan(REPO)
    assert L.FOLDER == "EA Explorer documentation" and L.GROUPS == D.GROUPS
    assert {i["key"] for i in items} == {d["key"] for d in D.listing()["documents"]}
    for i in items:
        assert i["group"] == D.group_of(i["key"]), i["key"]
        assert len(i["content"]) < 25 * 1024 * 1024                # the library's file limit
    assert len({i["file_name"] for i in items}) == len(items)      # one file name per document
    assert L.version(REPO) == __version__


def _tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True, timeout=60).stdout
        files = [REPO / f for f in out.decode().split("\0") if f]
        if files:
            return files
    except (OSError, subprocess.SubprocessError):
        pass
    skip = {"node_modules", "work", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "out"}
    found = []
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in skip]
        found += [Path(dirpath) / f for f in filenames]
    return found


def test_no_file_needs_git_lfs():
    """Nothing in the repository is over 50 MB; a larger file is split into name.partNN pieces with a manifest."""
    big = [(p, p.stat().st_size) for p in _tracked_files() if p.is_file() and p.stat().st_size > LIMIT]
    assert not big, f"over 50 MB (split them into parts with a manifest): {big}"
    for part in [p for p in _tracked_files() if re.search(r"\.part\d{2,}$", p.name)]:
        base = re.sub(r"\.part\d{2,}$", "", part.name)
        manifests = list(part.parent.glob(base + ".manifest*")) + list(part.parent.glob("*.manifest.json"))
        assert manifests, f"{part} has no manifest beside it"


def test_documents_stay_current_with_the_version():
    """D550: built or accepted phases link to their document; capabilities names every main screen and the version;
    the running version has its release notes."""
    phases = (REPO / "docs/build-phases.md").read_text(encoding="utf-8")
    for line in phases.splitlines():
        if re.match(r"^\| [0-9]", line) and re.search(r"accepted and closed|to be accepted", line, re.I):
            links = re.findall(r"\]\(([^)#\s]+\.md)", line)
            assert links, f"no document linked: {line[:60]}"
            for link in links:
                assert (REPO / "docs" / link).exists(), f"{link} missing ({line[:40]})"
    cap = (REPO / "docs/capabilities.md").read_text(encoding="utf-8")
    assert f"(version {__version__})" in cap.splitlines()[0], "capabilities.md's title names the running version"
    areas = re.findall(r'name: "([^"]+)"', (REPO / "services/web/src/Areas.jsx").read_text(encoding="utf-8"))
    app = (REPO / "services/web/src/App.jsx").read_text(encoding="utf-8")
    subnav = app[app.index('className="subnav"'):]
    subnav = subnav[:subnav.index("</nav>")]
    screens = set(areas) | {s.strip() for s in re.findall(r">([A-Z][A-Za-z ]+?)(?: ↗)?</a>", subnav)} | {"Documentation"}
    missing = [s for s in sorted(screens) if s.lower() not in cap.lower()]
    assert not missing, f"capabilities.md does not mention: {missing}"
    assert (REPO / "releases" / f"{__version__}.md").exists(), f"releases/{__version__}.md is missing"
