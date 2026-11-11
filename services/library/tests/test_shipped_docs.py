"""The "EA Explorer documentation" folder (D552): what it holds, from a set of shipped documents (no database needed)."""
from pathlib import Path

from libsvc import shipped_docs as S


def _ship(tmp: Path) -> Path:
    (tmp / "docs" / "requirements").mkdir(parents=True)
    (tmp / "eaxcli").mkdir()
    (tmp / "releases").mkdir()
    (tmp / "README.md").write_text("# EA Explorer\nHello", encoding="utf-8")
    (tmp / "eaxcli" / "help.txt").write_text("eax help", encoding="utf-8")
    (tmp / "releases" / "0.19.0.md").write_text("# EA Explorer 0.19.0\n", encoding="utf-8")
    (tmp / "releases" / "README.md").write_text("# About release notes\n", encoding="utf-8")
    (tmp / "version.toml").write_text('version = "0.19.0"\n', encoding="utf-8")
    for name, text in {"capabilities.md": "# What it does\n", "deployment.md": "# Deploying\n", "phase-24.md": "# Phase 24\n",
                       "todo.md": "# Working notes\n", "mcp.md": "# MCP server\n"}.items():
        (tmp / "docs" / name).write_text(text, encoding="utf-8")
    (tmp / "docs" / "requirements" / "x.md").write_text("# hidden\n", encoding="utf-8")
    return tmp


def test_the_folder_holds_every_shipped_document_in_its_group(tmp_path):
    items = {i["key"]: i for i in S.plan(_ship(tmp_path))}
    assert set(items) == {"readme", "command-line-help", "releases~0.19.0", "capabilities", "deployment", "phase-24", "mcp"}
    assert items["readme"]["group"] == "Getting started" and items["deployment"]["group"] == "Administration and operations"
    assert items["phase-24"]["group"] == "Design and decisions" and items["mcp"]["group"] == "Reference"
    assert items["capabilities"]["title"] == "What it does" and items["command-line-help"]["file_name"] == "eax-commands.txt"
    assert items["releases~0.19.0"]["file_name"] == "release-0.19.0.md"
    assert S.version(tmp_path) == "0.19.0"
    assert all(g in S.GROUPS for g in (i["group"] for i in items.values()))
