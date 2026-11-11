"""D584 (owner, 11 Nov 2026): up / clean-restart prepare everything, and a test prepares its runner: no extra steps.

The pack step (eaxcli/packs.py auto) runs before every full start in every form; it copies what is new or changed from
the pack sources, is quick when nothing changed and does nothing when no source is there. Every test run builds the
runner first.
"""

import io
import json
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from eaxcli import packs as K  # noqa: E402


def _install(tmp_path, monkeypatch, sources=None):
    root = tmp_path / "install"
    (root / "work").mkdir(parents=True)
    monkeypatch.setenv("EAX_PERSIST_DIR", str(root / "persist"))
    monkeypatch.delenv("EAX_PACKS_SOURCE", raising=False)
    monkeypatch.setattr(K, "default_sources", lambda: [tmp_path / "nowhere"])
    if sources is not None:
        K.set_sources([str(s) for s in sources], root=root)
    return root


def _source(tmp_path):
    src = tmp_path / "Industry Specific Guidance"
    (src / "Retail").mkdir(parents=True)
    (src / "Retail" / "Retail - the architecture workbook.pdf").write_bytes(b"%PDF-1.4 retail workbook")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Banking/Banking_TOGAF_Metamodel.xlsx", b"PK banking metamodel")
        z.writestr("Banking/Retail copy.pdf", b"%PDF-1.4 retail workbook")       # the same bytes: kept once
    (src / "Banking").mkdir()
    (src / "Banking" / "Banking starter pack - complete set.zip").write_bytes(buf.getvalue())
    return src


def test_no_source_does_nothing_and_never_fails(tmp_path, monkeypatch):
    root = _install(tmp_path, monkeypatch)
    out = K.auto(root, quiet=True)
    assert out["state"] == "none"
    assert not (root / "library" / "industry-packs").exists()


def test_source_copies_unzips_and_skips_duplicates_then_is_quick(tmp_path, monkeypatch):
    src = _source(tmp_path)
    root = _install(tmp_path, monkeypatch, [src])
    dest = root / "library" / "industry-packs"
    out = K.auto(root, quiet=True)
    assert out["state"] == "copied"
    files = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
    assert any(f.startswith("Banking/") and f.endswith(".xlsx") for f in files)             # opened from the zip
    assert sum(1 for f in files if f.endswith(".pdf")) == 1                                 # the same file once
    cache = json.loads((root / "persist" / "packs-cache.json").read_text())
    assert cache["signature"] == K.signature([src])                                         # the fingerprint survives resets
    assert K.auto(root, quiet=True)["state"] == "same"                                      # quick: nothing re-read
    (src / "Retail" / "Retail - read me.pdf").write_bytes(b"%PDF-1.4 new readme")           # a change is picked up
    out = K.auto(root, quiet=True)
    assert out["state"] == "copied" and any("read me" in c.lower() for c in out["copied"])


def test_sources_come_from_persist_then_the_config_then_the_defaults(tmp_path, monkeypatch):
    root = _install(tmp_path, monkeypatch)
    assert K.configured_sources(root)[1] == "the default folders"
    (root / "work" / "eaexplorer.env").write_text("EAX_PACKS_SOURCE=D:/a;D:/b\n", encoding="utf-8")
    srcs, where = K.configured_sources(root)
    assert where == "EAX_PACKS_SOURCE" and [s.name for s in srcs] == ["a", "b"]
    K.set_sources(["E:/packs"], root=root)
    srcs, where = K.configured_sources(root)
    assert where == "persist/settings.json" and srcs[0].name == "packs"
    K.set_sources([], clear=True, root=root)
    assert K.configured_sources(root)[1] == "EAX_PACKS_SOURCE"


def test_every_form_runs_the_pack_step_before_a_full_start():
    ps1 = (REPO / "eax.ps1").read_text(encoding="utf-8")
    sh = (REPO / "eax.sh").read_text(encoding="utf-8")
    py = (REPO / "eaxcli" / "main.py").read_text(encoding="utf-8")
    assert ps1.count('"eaxpy.ps1") packs auto') == 2                                       # up and debug
    assert sh.count("./eaxpy.sh packs auto || true") == 2
    assert py.count("_packs_auto()") >= 2
    # restart and the clean-* commands end in up (or debug), so they run it too
    assert re.search(r'\$steps = @\(@\("cleanup", "--all", "--yes"\), @\("init", \$kind\), \$finish\)', ps1)


def test_every_test_run_builds_the_runner_first_in_every_form():
    ps1 = (REPO / "eax.ps1").read_text(encoding="utf-8")
    sh = (REPO / "eax.sh").read_text(encoding="utf-8")
    py = (REPO / "eaxcli" / "main.py").read_text(encoding="utf-8")
    for text in (ps1, sh, py):
        assert "Preparing the test runner..." in text
    i = ps1.index("Preparing the test runner...")
    assert ps1.index('"build", "testrunner"', i) < ps1.index('"/app/ops.py", "test"', i)
    i = sh.index("Preparing the test runner...")
    assert sh.index("build testrunner", i) < sh.index("ops.py test", i)
    i = py.index("Preparing the test runner...")
    assert py.index('"build", "testrunner"', i) < py.index('[*ops, "test"]', i)
    api = (REPO / "services/api/eax/api/platform_tests.py").read_text(encoding="utf-8")
    assert 'data.get("build_first", True) is not False' in api                             # the page: always prepared


def test_the_runner_image_is_tagged_by_version():
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert "image: eaexplorer/testrunner:${EAX_VERSION:-dev}" in compose
    t = (REPO / "services/ops/testruns.py").read_text(encoding="utf-8")
    assert "def runner_image" in t and "default = True" in t                               # auto-build on everywhere


def test_the_testbench_prepares_its_data_and_browsers(monkeypatch):
    from testbench import prepare as P
    from testbench.data import build as B
    said, calls = [], []
    monkeypatch.setattr(B, "check", lambda: ["deliveries/good.xlsx"])
    monkeypatch.setattr(B, "build", lambda: calls.append("build"))

    class R:
        returncode = 0
        stdout = stderr = ""

    def runner(cmd, **_k):
        calls.append(cmd[-2:])
        return R()
    assert P.data(said.append) == ["deliveries/good.xlsx"] and calls == ["build"]
    out = P.browsers(["chromium", "firefox", "msedge"], said.append, runner=runner)
    assert out == {"chromium": "ok", "firefox": "ok", "msedge": "edge"} and calls[-1] == ["chromium", "firefox"]
    assert "prepare.everything(browsers" in (REPO / "testbench" / "cli.py").read_text(encoding="utf-8")
