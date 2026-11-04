"""MCP sign-in: the laptop development token is accepted on laptops only, as a Super Admin."""

import pytest

pytest.importorskip("mcp")


def test_dev_token_on_laptop_only(monkeypatch):
    from eax import mcp_server

    monkeypatch.setenv("EAX_MCP_DEV_TOKEN", "P^55w0rd1234&")
    monkeypatch.setenv("EAX_DEPLOYMENT", "laptop")
    who = mcp_server._authenticate("Bearer P^55w0rd1234&")
    assert who.username == "mcp-dev" and who.roles == ("super-admin",)
    assert mcp_server._authenticate("Bearer wrong") is None
    assert mcp_server._authenticate("") is None
    monkeypatch.setenv("EAX_DEPLOYMENT", "server")
    assert mcp_server._authenticate("Bearer P^55w0rd1234&") is None


def test_lists_are_wrapped():
    from eax import mcp_server

    assert mcp_server._clean([{"id": 1, "_id": 2}]) == [{"id": 1}]


def test_tools_refuse_without_a_person():
    import anyio

    from eax import mcp_server, permissions

    assert permissions.current.get() is None
    assert anyio.run(mcp_server._run, lambda conn: 1) == {"error": "Sign in required."}
