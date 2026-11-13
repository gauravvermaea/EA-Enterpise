"""R2.47 (the release and build at the top left), R2.34 (the bell on the right), R2.38 (the guide for contributors)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_the_api_says_its_build(monkeypatch):
    import eax
    monkeypatch.delenv("EAX_BUILD", raising=False)
    assert eax.build()["build"] == "dev"
    monkeypatch.setenv("EAX_BUILD", "4f2a9c1")
    monkeypatch.setenv("EAX_BUILT_AT", "2026-11-13T07:00:00+02:00")
    b = eax.build()
    assert b["build"] == "4f2a9c1" and b["built_at"].startswith("2026-11-13")
    assert "**build()" in (REPO / "services/api/eax/api/heartbeat.py").read_text()
    compose = (REPO / "docker-compose.yml").read_text()
    assert "EAX_BUILD: ${EAX_BUILD:-dev}" in compose and "EAX_BUILT_AT: ${EAX_BUILT_AT:-}" in compose


def test_every_form_of_eax_sets_the_build_and_status_shows_it():
    sh, ps1 = (REPO / "eax.sh").read_text(), (REPO / "eax.ps1").read_text()
    core, main = (REPO / "eaxcli/core.py").read_text(), (REPO / "eaxcli/main.py").read_text()
    assert "export EAX_BUILD EAX_COMMIT EAX_BUILT_AT" in sh and 'status)  heading "EA Explorer $(release), build $(build_id)"' in sh
    assert "$env:EAX_BUILD = Get-BuildId" in ps1 and "build $(Get-BuildId)" in ps1
    assert "_build_env()" in core and "build {_core.build_id()}" in main
    for src in (sh, ps1, core):                      # the commit's own time, never "now": up keeps the container
        assert "%cI" in src
    assert "First the release and its build" in (REPO / "eaxcli/help.txt").read_text()


def test_the_top_bar_shows_the_version_and_the_bell_sits_with_the_person():
    app = (REPO / "services/web/src/App.jsx").read_text()
    assert "<VersionTag version={version} build={build} />" in app
    left = app.index('className="brand"')
    user = app.index('<div className="user">')
    bell = app.index("<Bell route={route} />")
    assert left < user < bell                        # R2.34: the bell is in the person's own corner
    assert app.count("<Bell route={route} />") == 1


def test_the_contributor_guide():
    guide = (REPO / "CONTRIBUTING.md").read_text()
    for must in ("AGPL-3.0", "Signed-off-by", "Developer Certificate of Origin", "Open an issue first", "D599", "D248",
                 "D114", "D331", "50 MB", "CODE_OF_CONDUCT.md", "SECURITY.md"):
        assert must in guide, must
    assert "Contributor Covenant" in (REPO / "CODE_OF_CONDUCT.md").read_text()
    assert "do not open a public issue" in (REPO / "SECURITY.md").read_text()
    for f in (".github/ISSUE_TEMPLATE/bug_report.md", ".github/ISSUE_TEMPLATE/feature_request.md",
              ".github/pull_request_template.md"):
        assert (REPO / f).is_file(), f
    assert "## Contributing" in (REPO / "README.md").read_text()
