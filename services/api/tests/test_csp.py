"""The screens' Content-Security-Policy at the front door (R3.12, D672; moved from R2.24 part 3): what it allows, that
the other headers are still sent with it, the one inline script allowed by its hash, the switch to report-only, and the
self-test's check of it."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

import yaml

from eax.testing import security

REPO = Path(__file__).resolve().parents[3]
TEMPLATE = (REPO / "deploy/proxy/templates/default.conf.template").read_text()


def _screens_location() -> str:
    main = TEMPLATE[TEMPLATE.index("listen 443 ssl default_server;"):]
    start = main.index("    location / {")
    return main[start:main.index("\n    }\n", start)]


def _policy() -> str:
    m = re.search(r'add_header \$\{EAX_CSP_HEADER\} "([^"]+)" always;', _screens_location())
    assert m, "no CSP on the screens' location"
    return m.group(1)


def test_the_policy_is_strict_where_it_matters():
    assert security.csp_problems(_policy()) == []
    p = _policy()
    for d in ("default-src 'self'", "object-src 'none'", "base-uri 'self'", "frame-ancestors 'self'", "form-action 'self'",
              "frame-src 'self'", "worker-src 'self' blob:", "connect-src 'self'"):
        assert d in p, d
    assert "'unsafe-eval'" not in p and "script-src 'self' 'sha256-" in p


def test_the_one_inline_script_is_allowed_by_its_hash():
    html = (REPO / "services/web/public/silent-check-sso.html").read_text()
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(scripts) == 1
    want = base64.b64encode(hashlib.sha256(scripts[0].encode()).digest()).decode()
    assert f"'sha256-{want}'" in _policy()
    index = (REPO / "services/web/index.html").read_text()
    assert not re.search(r"<script>(?!\s*</script>)", index)               # no other inline script in the screens


def test_the_other_headers_still_come_with_it():
    """nginx sends a location's own headers only: without repeating them the screens would lose nosniff and the rest."""
    loc = _screens_location()
    for h in ("X-Content-Type-Options nosniff", "Referrer-Policy", "X-Frame-Options SAMEORIGIN", 'Strict-Transport-Security "${EAX_HSTS}"'):
        assert h in loc, h


def test_draw_io_the_api_and_sign_in_keep_their_own():
    main = TEMPLATE[TEMPLATE.index("listen 443 ssl default_server;"):]
    for loc in ("location /drawio/ {", "location /api/ {", "location /auth/ {"):
        block = main[main.index(loc):main.index("\n    }\n", main.index(loc))]
        assert "EAX_CSP_HEADER" not in block, loc
    assert TEMPLATE.count("add_header ${EAX_CSP_HEADER}") == 1              # Reports and Documents too


def test_it_can_be_switched_to_report_only():
    env = yaml.safe_load((REPO / "docker-compose.yml").read_text())["services"]["proxy"]["environment"]
    assert env["EAX_CSP_HEADER"] == "${EAX_CSP_HEADER:-Content-Security-Policy}"
    for f in ("eaexplorer.laptop.env", "eaexplorer.server.env"):
        assert "EAX_CSP_HEADER=Content-Security-Policy\n" in (REPO / "deploy/templates" / f).read_text()


def test_the_self_test_checks_it():
    got = []
    rec = lambda name, outcome, detail, ms: got.append((name, outcome, detail))  # noqa: E731
    base = {"x-content-type-options": "nosniff", "referrer-policy": "x", "x-frame-options": "SAMEORIGIN",
            "strict-transport-security": "max-age=1"}
    security.check_headers({**base, "content-security-policy": _policy()}, "front door", rec)
    assert ("front door: header content-security-policy", "passed") in [(n, o) for n, o, _d in got]
    got.clear()
    security.check_headers(base, "front door", rec)
    assert ("front door: header content-security-policy", "failed") in [(n, o) for n, o, _d in got]
    got.clear()
    security.check_headers({**base, "content-security-policy-report-only": _policy()}, "front door", rec)
    assert ("front door: header content-security-policy", "warning") in [(n, o) for n, o, _d in got]
    got.clear()
    security.check_headers({**base, "content-security-policy": "script-src * 'unsafe-eval'"}, "front door", rec)
    out = next(d for n, o, d in got if n.endswith("content-security-policy"))
    assert "script-src allows *" in out and "unsafe-eval" in out and "object-src" in out


def test_weak_policies_are_named():
    assert "no default-src" in security.csp_problems("script-src 'self'")
    assert "script-src allows 'unsafe-inline'" in security.csp_problems("default-src 'self' 'unsafe-inline'; object-src 'none'")
    assert "frame-ancestors lets other sites frame the screens" in security.csp_problems("default-src 'self'; frame-ancestors *")


def test_the_page_sweep_and_journeys_fail_a_page_the_policy_breaks():
    from eax.testing import ui_pages
    assert ui_pages.csp_blocked("error", "Refused to load the script 'https://x' because it violates the following "
                                         "Content Security Policy directive: \"script-src 'self'\"")
    assert not ui_pages.csp_blocked("warning", "Content Security Policy")
    assert not ui_pages.csp_blocked("error", "Failed to fetch")
    assert 'page.on("console"' in (REPO / "services/api/eax/testing/ui_pages.py").read_text()
    assert "_csp(m.type, m.text)" in (REPO / "services/api/eax/testing/ui_journeys.py").read_text()
