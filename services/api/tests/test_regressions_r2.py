"""One check for each bug fixed in R2.0.1 that has no test of its own (D599: every bug fixed gets a test that keeps it
fixed). Each names the bug and the day it was seen."""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
API = REPO / "services" / "api"


def _read(*p: str) -> str:
    return REPO.joinpath(*p).read_text(encoding="utf-8")


def test_r2_20_reports_init_has_no_health_check():
    """R2.20: the Superset image's own health check ran in the one-shot set-up, which then showed "unhealthy"."""
    compose = yaml.safe_load(_read("docker-compose.yml"))
    assert compose["services"]["reports-init"]["healthcheck"] == {"disable": True}


def test_d596_a_server_error_answers_with_its_kind_and_request_id():
    """12 Nov 2026: two bare "Internal Server Error" pages in the full run, with nothing to go on."""
    app = _read("services", "api", "eax", "app.py")
    assert "@app.errorhandler(Exception)" in app and '"request_id": rid' in app and "log.exception(" in app
    assert "isinstance(exc, HTTPException)" in app                 # an abort still answers as itself


def test_d596_requests_may_take_two_minutes_and_four_jobs_run_at_once():
    """12 Nov 2026: gunicorn's own 30 seconds ended a project's download and a slow page with a server error; two jobs at
    once held a delivery preview up behind the long ones."""
    entry = _read("services", "api", "entrypoint.sh")
    assert '--timeout "${EAX_API_TIMEOUT:-120}"' in entry
    assert '--concurrency "${EAX_JOB_CONCURRENCY:-4}"' in entry


def test_d596_the_test_bench_state_counts_each_table_on_its_own():
    """12 Nov 2026: one slow count gave IT Admin a server error for the whole answer. (13 Nov 2026: the counts moved to
    eax/testbench_state.py, within a 30-second budget; tests/test_testbench.py.)"""
    tb = _read("services", "api", "eax", "testbench_state.py")
    assert "SET LOCAL statement_timeout = {ms}" in tb and 'problems.append(' in tb


def test_d596_the_front_door_hides_its_version_and_refuses_framing_by_others():
    conf = _read("deploy", "proxy", "templates", "default.conf.template")
    assert "server_tokens off;" in conf and conf.index("server_tokens off;") < conf.index("server {")
    assert "add_header X-Frame-Options SAMEORIGIN always;" in conf


def test_d596_the_self_test_does_not_download_a_project_repository():
    """12 Nov 2026: GET /projects/{p}/repo-zip took longer than a request may."""
    from eax.testing import api_matrix
    assert api_matrix.HEAVY.search("/api/v1/projects/{project}/repo-zip")


def test_d596_journeys_wait_for_what_a_slow_laptop_shows_later():
    """12 Nov 2026 (the laptop's runs): a click lost while the page settled, a field not there yet, a schedule's name in
    the page's own "removed" message, a merge or a preview slower than the test allowed."""
    from eax.testing import ui_flows
    steps = [s for j in ui_flows.JOURNEYS for s in j["steps"]]
    assert {"click": "+ In a form", "opens": ui_flows.DIALOG} in steps
    assert {"expect": "self_test_{sid} schedule {role}: removed."} in steps
    assert not any(s.get("expect_not") == "self_test_{sid} schedule {role}" for s in steps)
    assert any(s.get("expect") == "Accept and commit" and s.get("timeout", 0) >= 240000 for s in steps)
    src = _read("services", "api", "eax", "testing", "ui_flows.py")
    assert 'if s.get("opens"):' in src and "while el is None and time.time() < end:" in src


def test_d596_the_runner_mounts_test_data_beside_work_on_windows():
    """12 Nov 2026: C:\\...\\work became "...\\work/testbench/data", an empty folder (covered in test_testing too)."""
    src = _read("services", "ops", "testruns.py")
    assert re.search(r"def test_data_folder\(work: str\) -> str:", src)


def test_d602_standard_views_first_and_by_default():
    """Owner, 12 Nov 2026: "standard views should be the first tab drawn the next one"."""
    views = _read("services", "web", "src", "Views.jsx")
    assert 'const VIEW_TABS = [["standard", "Standard views"], ["custom", "Custom views"]];' in views
    assert 'const tab = asked || "standard";' in views


def test_r2_7_a_models_picture_in_drawio_has_read_only_panels():
    """R2.7 (owner, 11 Nov 2026; read-only panels chosen 12 Nov): no object explorer or properties on a picture opened in
    draw.io. The self-test journey "a model's picture in draw.io" and the plugin's read-only check cover it in a browser."""
    scratch = _read("services", "web", "src", "ScratchDrawio.jsx")
    drawn = _read("services", "web", "src", "DrawnView.jsx")
    assert "export function PicturePanels(" in drawn and "Objects on this picture" in drawn and "readOnly" in drawn
    assert '<PicturePanels model={model} setup={setup} xml={pic.xml} selected={selected} post={post} />' in scratch
    assert 'case "eax-selected":' in scratch and "!pic.plain" in scratch
    from eax.testing import ui_flows
    assert any(j["name"].startswith("a model's picture in draw.io") for j in ui_flows.JOURNEYS)
    assert "read only: an object chosen in EA Explorer is selected and reported" in _read("deploy", "drawio", "tests", "tests.cjs")


def test_r2_24_the_last_critical_findings_in_backup_and_reports():
    """The full self-test, 12 Nov 2026: gosu's Go standard library in the backup image; Brotli, PyJWT and certifi in the
    Reports image."""
    backup = _read("services", "backup", "Dockerfile")
    assert "rm -f /usr/local/bin/gosu" in backup and "gosu" not in _read("services", "backup", "entrypoint.sh")
    superset = _read("deploy", "superset", "Dockerfile")
    for x in ('"Brotli>=1.2.1"', '"PyJWT>=2.14.0,<3"', '"certifi>=2026.10.18"'):
        assert x in superset, x


def test_the_child_merge_journey_waits_for_the_merge_to_finish():
    """The full self-test, 12 Nov 2026: "What happens to …" shows only once the background merge has finished."""
    from eax.testing import ui_flows
    j = next(x for x in ui_flows.JOURNEYS if x["name"].startswith("child merge"))
    assert {"open": "#/merge-requests/{$mr}", "expect": "What happens to", "reload": True, "timeout": 180000} in j["steps"]


class _ReloadPage:
    """A page whose text shows only after it has really been reloaded n times; opening the same address again (a
    #fragment move) changes nothing, as in a browser."""

    def __init__(self, shows_after: int):
        self.reloads, self.shows_after, self.opened = 0, shows_after, []

    def reload(self, **_kw):
        self.reloads += 1

    def wait_for_timeout(self, _ms):
        pass

    def locator(self, _sel):
        page = self

        class L:
            first = None

            def wait_for(self, **_kw):
                if page.reloads < page.shows_after:
                    raise TimeoutError("Locator.wait_for: Timeout 8000ms exceeded.")
        loc = L()
        loc.first = loc
        return loc


def test_a_step_that_waits_for_a_background_task_really_reloads_the_page():
    """Full self-test, 13 Nov 2026: child merge, step 18 (open #/merge-requests/{$mr}): 180 seconds and the merged request
    never showed. Opening the same address again only moved to its #fragment, so nothing was fetched again; the step now
    reloads the page between looks."""
    from eax.testing import ui_flows as uf
    page = _ReloadPage(shows_after=2)
    why = uf.step(page, {"open": "#/merge-requests/x", "expect": "What happens to", "reload": True, "timeout": 180000},
                  lambda route, role=None: page.opened.append((route, role)), {"vars": {}, "role": "super-admin"})
    assert why == "" and page.reloads == 2 and page.opened == [("#/merge-requests/x", "super-admin")]


def test_a_failed_journey_step_says_what_the_page_showed():
    from eax.testing import ui_flows as uf

    class P:
        def evaluate(self, _js):
            return {"at": "#/merge-requests/x", "h1": ["Merge request 3"], "status": ["Waiting for review"]}
    said = uf._page_says(P())
    assert said == ' · the page showed: at #/merge-requests/x, heading "Merge request 3", "Waiting for review"'
    src = (Path(uf.__file__)).read_text()
    assert "{why}{_page_says(state.get('tab') or page)}" in src


def test_the_iteration_shows_at_once_after_saving():
    """Full self-test, 13 Nov 2026: "project: iteration, frozen phase, back" as architect, step 8 (expect Transition
    Planning): saving said "Now a Transition Planning iteration", the dialog closed, and the page still showed the old
    iteration until the project's data came back. What saving gave is shown at once, until the refreshed data is as new."""
    src = _read("services", "web", "src", "IterationControl.jsx")
    assert "const [saved, setSaved] = useState(null);" in src
    assert "p.iteration.at >= saved.at" in src and "onSaved={setSaved}" in src
    assert "if (onSaved && r.iteration) onSaved({ ...r.iteration, frozen_phases: r.frozen || [] });" in src
    it = _read("services", "api", "eax", "iterations.py")
    assert 'return {"iteration": now, "frozen": frozen,' in it                 # what saving answers carries both
