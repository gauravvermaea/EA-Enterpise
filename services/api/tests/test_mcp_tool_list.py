"""R2.54 (owner, 13 Nov 2026: "list all MCP tools and what they do on the MCP page and nothing else"): the MCP page's
Tools tab lists every tool, read from the tools' own code, so it cannot fall behind."""

from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "eax"
REPO = API.parents[2]


def test_every_tool_is_listed_with_what_it_does():
    from eax import mcp_catalogue as mc
    tools = mc.tools()
    declared = sum(len(re.findall(r"^@mcp\.tool\(\)", f.read_text(), re.M)) for f in API.glob("mcp_*.py"))
    assert len(tools) == declared and declared > 100
    assert len({t["name"] for t in tools}) == len(tools)
    assert all(t["what"] for t in tools), [t["name"] for t in tools if not t["what"]]     # every tool says what it does
    by = {t["name"]: t for t in tools}
    assert not by["impact_analysis"]["changes"] and by["create_model"]["changes"] and by["create_project"]["changes"]
    assert {p["name"] for p in by["impact_analysis"]["params"]} >= {"model", "entity"}
    assert set(mc.AREAS) == {f.stem for f in API.glob("mcp_*.py") if re.search(r"^@mcp\.tool\(\)", f.read_text(), re.M)}


def test_the_page_reads_the_list():
    api = (API / "api" / "mcp_activity.py").read_text()
    assert '@blp.route("/tools")' in api and "mcp_catalogue.tools()" in api
    web = (REPO / "services/web/src/Mcp.jsx").read_text()
    assert 'useApi("/api/v1/mcp/tools")' in web and "const TOOLS = [" not in web and "const GROUPS = [" not in web
