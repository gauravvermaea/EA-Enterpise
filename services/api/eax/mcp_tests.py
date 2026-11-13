"""MCP: the platform's own test results (phase 36.1, D367, D525): read only, Super Admins and IT Admins.

So an assistant can answer "did the last test run pass, and what failed?" and help fix it. Starting a run stays in the
screens (System admin > Health > Tests) and `eax test`."""

from __future__ import annotations

from typing import Any

from . import permissions
from .mcp_server import _run, mcp
from .metamodel_edit import EditError
from .testing import store


def _operator() -> None:
    user = permissions.current.get()
    if not user or not (permissions.allowed(user.roles, "system.operate") or permissions.SUPER_ADMIN in (user.roles or ())):
        raise EditError("Test results are for Super Admins and IT Admins.", 403)


@mcp.tool()
async def test_results(run: int = 0, outcome: str = "failed", suite: str = "", limit: int = 10) -> Any:
    """The platform's automated test runs (API, browser journeys, database and security checks, run on a separate test
    database). Without run: the most recent runs with their counts. With run: that run's results, filtered by outcome
    (failed, warning, skipped, passed, or empty for all) and suite (api, ui, db, security). Super Admins and IT Admins."""
    def go(conn):
        _operator()
        with store.tests(conn) as tc:                # the runs are in the tests database (R2.28)
            if not run:
                return {"runs": store.runs(tc, limit)}
            d = store.run_detail(tc, run, outcome if outcome in store.OUTCOMES else "", suite)
        if not d:
            raise EditError(f"No test run {run}.", 404)
        d["results"] = d["results"][:500]
        return d
    return await _run(go)
