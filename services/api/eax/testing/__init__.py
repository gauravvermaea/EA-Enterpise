"""The self-test (phase 36.1, D367, D522 to D529): automated tests of the live installation, run in its own fixtures.

Started from System admin > Self-test or `eax test` (all four forms, D331), at once (never scheduled), or in CI; both
use one runner (a container of its own, services/api/Dockerfile.test, started by the operations helper) and one results
store (core.test_runs, core.test_results, core.test_fixtures), so a run started in either place shows in both.

Levels:
  smoke     a few minutes: every test role signs in, every main area answers, the key journeys work once
  detailed  the suites chosen:
              api       every endpoint, with no token and as every role: allowed and refused, never a server error; a
                        model's content refused to someone with no role on it (cross-user)
              ui        the main journeys in a real browser: headless (Chromium in the runner) or watched in the admin's
                        own browser (Self-test > Watch it in this browser)
              db        read-only database checks
              security  headers and cookies, the Python dependencies (pip-audit), an OWASP ZAP baseline scan and Trivy
                        image scans (run by the operations helper next to the runner)
Filters: one role, one API area.

Each run has a guid; everything it needs it makes itself, named self_test_<first 12 of the guid>_<n> (models, a project)
and svc-self-test-<id>-<role> (one service account and one-day token per role), recorded in core.test_fixtures. It never
changes anything it did not make; standard screens and lists are only read. Its tokens are revoked when it ends. The
fixtures stay until an admin purges them (Self-test > Test fixtures, `eax test --clean`): a hard delete of only what the
run recorded (fixtures.py). The report (HTML and Excel) stays after the purge, marked "fixtures removed".
"""

SUITES = ("api", "ui", "db", "security")
