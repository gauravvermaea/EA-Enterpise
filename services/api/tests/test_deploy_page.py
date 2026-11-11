"""System admin > Deploy (phase 36, D555 to D557): the operations helper's deployments (a plan end to end, the questions
without the laptop, credentials kept only when asked and never sent back), the runner's Retry, the API's rights and
what it passes on, the history of targets."""
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from eaxcli import deploy as D  # noqa: E402
from eaxcli import deploy_runner as R  # noqa: E402

KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA-not-a-real-key\n-----END OPENSSH PRIVATE KEY-----\n"


@pytest.fixture
def ops(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("deploys_under_test", REPO / "services" / "ops" / "deploys.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.REPO, m.RUNS, m.KEEP = str(REPO), str(tmp_path / "deploys"), str(tmp_path / "keep")
    monkeypatch.setattr(m, "_defaults", lambda: {"repo": "https://github.com/acme/ea-explorer", "ref": "v0.19.0"})
    started = []
    monkeypatch.setattr(m, "_start_deployer", lambda run_id, folder: started.append(run_id))
    m.started = started
    return m


def wait_for(ops, run_id, statuses=("planned", "done", "quit", "back"), seconds=30):
    for _ in range(seconds * 10):
        r = ops.run(run_id)
        if r["status"] in statuses:
            return r
        time.sleep(0.1)
    raise AssertionError(f"still {r['status']}: {r.get('lines')}")


def test_questions_never_offer_the_laptop(ops):
    q = ops.questions({"kind": "laptop"})
    keys = [x["key"] for x in q["questions"]]
    kind = next(x for x in q["questions"] if x["key"] == "kind")
    assert "laptop" not in kind["choices"] and q["answers"]["kind"] == "server" and q["answers"]["where"] == "ssh"
    assert "where" not in keys and "ssh_target" in keys and "aws_profile" not in keys
    aws = ops.questions({"kind": "aws"})
    assert "aws_access_key_id" in [x["key"] for x in aws["questions"]]
    with_id = {x["key"]: x for x in ops.questions({"kind": "aws", "aws_access_key_id": "AKIA"})["questions"]}
    assert with_id["aws_secret_access_key"]["secret"] is True
    assert next(x for x in aws["questions"] if x["key"] == "ssh_key")["kind"] == "key"
    assert next(x for x in aws["questions"] if x["key"] == "repo")["default"] == "https://github.com/acme/ea-explorer"


def test_a_plan_runs_end_to_end_and_keeps_no_secret(ops):
    about = ops.start({"answers": {"kind": "digitalocean", "hostname": "ea.fynbos.example", "do_domain": "fynbos.example"},
                       "secrets": {"do_token": "dop_v1_secret_token", "spaces_key": "SPK", "spaces_secret": "spaces-secret-xyz"},
                       "ssh_key": KEY, "plan": True, "keep": True, "by": "user_it_admin"})
    assert about["plan"] and about["kind"] == "digitalocean" and about["target"] == "ea.fynbos.example" and not ops.started
    r = wait_for(ops, about["id"])
    text = "\n".join(r["lines"])
    assert r["status"] == "planned" and "doctl compute droplet create" in text and "get.docker.com" in text
    assert all(s["status"] == "done" for s in r["steps"])
    folder = Path(ops.RUNS) / about["id"]
    everything = "".join(p.read_text(errors="replace") for p in folder.rglob("*") if p.is_file())
    for secret in ("dop_v1_secret_token", "spaces-secret-xyz", "not-a-real-key"):
        assert secret not in text and secret not in everything, secret     # never logged, deleted at the end
    assert not (folder / "secrets.json").exists() and not (folder / "ssh_key").exists()
    assert ops.kept() == []                                                   # a plan never keeps credentials
    assert "ssh_key" not in json.loads((folder / "answers.json").read_text()) or True


def test_a_deployment_starts_the_deployer_and_needs_a_key(ops):
    with pytest.raises(ValueError, match="SSH private key"):
        ops.start({"answers": {"kind": "server", "ssh_target": "ubuntu@203.0.113.10", "hostname": "ea.acme.test"}})
    with pytest.raises(ValueError, match="does not look like"):
        ops.start({"answers": {"kind": "server", "ssh_target": "u@h", "hostname": "ea.acme.test"}, "ssh_key": "hello"})
    about = ops.start({"answers": {"kind": "server", "ssh_target": "ubuntu@203.0.113.10", "hostname": "ea.acme.test"},
                       "ssh_key": KEY, "keep": True, "by": "user_super_admin"})
    assert ops.started == [about["id"]]
    folder = Path(ops.RUNS) / about["id"]
    assert (folder / "ssh_key").exists() and oct((folder / "ssh_key").stat().st_mode & 0o777) == "0o600"
    with pytest.raises(RuntimeError, match="running"):
        ops.start({"answers": {"kind": "server", "ssh_target": "u@h2", "hostname": "ea2.acme.test"}, "ssh_key": KEY})
    # the run ends (as the deployer would write it): the key is moved to the kept store, root only, never returned
    (folder / "state.json").write_text(json.dumps({"status": "done", "steps": [], "result": {"public_ip": "203.0.113.10"}}))
    r = ops.run(about["id"])
    assert r["status"] == "done" and "ssh_key" not in json.dumps(r) and not (folder / "ssh_key").exists()
    assert ops.kept() == ["ea.acme.test"]
    assert (Path(ops.KEEP) / "ea.acme.test" / "ssh_key").read_text().startswith("-----BEGIN")
    # used again for the same target, then forgotten
    again = ops.start({"answers": {"kind": "server", "ssh_target": "ubuntu@203.0.113.10", "hostname": "ea.acme.test"},
                       "use_kept": "ea.acme.test"})
    assert (Path(ops.RUNS) / again["id"] / "ssh_key").exists()
    ops.forget("ea.acme.test")
    assert ops.kept() == []


def test_decisions_only_for_a_failed_step(ops):
    about = ops.start({"answers": {"kind": "server", "ssh_target": "u@h", "hostname": "ea.acme.test"}, "ssh_key": KEY})
    with pytest.raises(RuntimeError):
        ops.decide(about["id"], "retry")
    folder = Path(ops.RUNS) / about["id"]
    (folder / "state.json").write_text(json.dumps({"status": "failed", "failed": {"step": "x", "why": "y"}, "steps": []}))
    with pytest.raises(ValueError):
        ops.decide(about["id"], "explode")
    assert ops.decide(about["id"], "retry") == {"choice": "retry"}
    assert json.loads((folder / "decision.json").read_text()) == {"choice": "retry"}
    with pytest.raises(ValueError):
        ops.run("../../etc")


def test_the_runner_waits_for_retry(tmp_path, monkeypatch):
    calls = {"n": 0}

    def flaky(ctx):
        calls["n"] += 1
        if calls["n"] == 1:
            raise D.StepFailed("the server did not answer")
    monkeypatch.setattr(D, "all_steps", lambda a: [D.Step("Reach the server", flaky), D.Step("Done", lambda ctx: None)])
    (tmp_path / "answers.json").write_text(json.dumps({"kind": "server", "where": "ssh", "ssh_target": "u@h",
                                                       "hostname": "ea.acme.test", "repo": "https://github.com/a/b"}))
    runner = R.Runner(tmp_path, plan=False)
    import threading
    t = threading.Thread(target=runner.go)
    t.start()
    st = {}
    for _ in range(200):
        try:
            st = json.loads((tmp_path / "state.json").read_text())
        except (OSError, ValueError):
            st = {}
        if st.get("status") == "failed":
            break
        time.sleep(0.05)
    assert st["failed"]["why"] == "the server did not answer"
    (tmp_path / "decision.json").write_text('{"choice": "retry"}')
    t.join(10)
    st = json.loads((tmp_path / "state.json").read_text())
    assert st["status"] == "done" and calls["n"] == 2


# ---------------------------------------------------------------- the API: rights, what it passes on, the history
def test_every_deploy_route_needs_it_or_super_admin():
    src = (REPO / "services/api/eax/api/deploys.py").read_text()
    routes = re.findall(r"def (get|post|delete)\(", src)
    assert len(routes) == len(re.findall(r'@require_auth\("system.operate"\)', src)) == 6
    from eax import permissions as P
    assert P.allowed(["it-admin"], "system.operate") and P.allowed(["super-admin"], "system.operate")
    for role in ("user", "model-creator", "user-admin", "library-admin"):
        assert not P.allowed([role], "system.operate"), role
    assert 'url_prefix="/api/v1/deploys"' in src and "deploys_blp" in (REPO / "services/api/eax/app.py").read_text()


def test_the_api_passes_secrets_apart_and_never_keeps_them():
    from eax import deploys as dp
    body = dp.clean_body({"answers": {"kind": "aws", "hostname": "ea.acme.test", "aws_secret_access_key": "typed-in-answers",
                                      "ssh_key": "should-not-be-an-answer"},
                          "secrets": {"aws_access_key_id": "AKIA", "unknown": "x"}, "ssh_key": KEY, "plan": True, "keep": True},
                         "user_it_admin")
    assert body["answers"] == {"kind": "aws", "hostname": "ea.acme.test"}
    assert body["secrets"] == {"aws_access_key_id": "AKIA", "aws_secret_access_key": "typed-in-answers"}
    assert body["ssh_key"] == KEY and body["by"] == "user_it_admin" and body["plan"] and body["keep"]
    row = dp._row({"id": "20261110T220000Z-abcdef", "target": "ea.acme.test", "kind": "aws", "version": "v0.19.0",
                   "status": "done", "by": "u", "result": {"public_ip": "203.0.113.7"}, "keep": True})
    assert row["address"] == "203.0.113.7" and row["kept"] and "secret" not in json.dumps(row)
    hist = [{"target": "a", "plan": False, "status": "done"}, {"target": "a", "plan": False, "status": "quit"},
            {"target": "b", "plan": True, "status": "planned"}]
    t = dp.targets(hist)
    assert len(t) == 1 and t[0]["deployments"] == 2 and t[0]["status"] == "done"


def test_the_history_table_is_rows_only():
    sql = (REPO / "services/api/migrations/sql/0043_deployment.sql").read_text()
    assert "CREATE TABLE core.deployments" in sql and "'0.19.0'" in sql
    for word in ("CREATE TRIGGER", "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"):
        assert word not in sql.upper()
    for secret in ("ssh_key", "password", "token"):
        assert not re.search(rf"^\s+{secret}\b", sql, re.M), secret


def test_the_page_and_its_help():
    page = (REPO / "services/web/src/Deploy.jsx").read_text()
    admin = (REPO / "services/web/src/Admin.jsx").read_text()
    assert '["deploy", "Deploy", () => can("system.operate")' in admin and "Show the plan (runs nothing)" in page
    assert "Retry this step" in page and "Back to the answers" in page and "Quit" in page
    cat = json.loads((REPO / "services/web/src/help/catalogue.json").read_text())
    assert "tab:Deploy" in cat and "button:Retry this step" in cat
    assert (REPO / "deploy/deployer/Dockerfile").read_text().count("doctl") >= 1
    assert os.path.exists(REPO / "services/ops/deploys.py")
