"""EA Explorer's test bench (D579 to D582): the self-test's tests, run from OUTSIDE the platform.

The self-test (System admin > Self-test, `eax test`; services/api/eax/testing/) runs inside the installation it tests.
The test bench runs the same tests from any machine against any EA Explorer address, so it also covers what an inside
test cannot:

  * the platform is broken: it still starts and reports what does not answer (the anonymous checks need nothing);
  * other browsers: Chromium, Firefox, WebKit (Safari's engine) and Edge;
  * install and upgrade: a fresh install, and an upgrade from an earlier release, then the full suite;
  * load: response times under many people at once (k6);
  * independence: its own report (HTML, JSON, JUnit for CI), its own exit code.

The tests are written once, in services/api/eax/testing/ (imported, never copied: shared.py); the data they need is in
testbench/data/ (built by `python -m testbench.data build`), the same files the inside self-test reads.

Run with `eax testbench ...` (every form, D331) or `python -m testbench ...`. Never against an installation without
`--target <address> --i-own-this`. docs/testbench.md has everything."""

__all__ = ["SUITES", "LEVELS"]

SUITES = ("api", "ui", "db", "security")      # the self-test's suites (services/api/eax/testing/__init__.py)
LEVELS = ("smoke", "detailed")
