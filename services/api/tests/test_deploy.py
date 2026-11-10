"""eax deploy (phase 36, D498, D500 to D506): the questions, the config a server gets, where releases come from, every
kind's plan (nothing run), failing steps (retry, back), the key vault, directory groups, the installer and the web
wizard."""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from eaxcli import deploy as D  # noqa: E402
from eaxcli import secrets as V  # noqa: E402
from eaxcli.core import Failure  # noqa: E402


@pytest.fixture
def nothing_runs(monkeypatch):
    """A plan must never run a command."""
    def boom(*a, **k):
        raise AssertionError(f"a command ran in plan mode: {a}")
    monkeypatch.setattr(D.subprocess, "run", boom)


def plan(answers: dict) -> list[str]:
    lines: list[str] = []
    assert D.run(answers, True, lambda s, w: "quit", out=lines.append) == "done", "\n".join(lines)
    return lines


KEY = str(REPO / "README.md")         # any existing file stands in for an SSH key in a plan


# ---------------------------------------------------------------- questions
def test_questions_follow_the_answers():
    keys = [q.key for q in D.visible({"kind": "laptop"})]
    assert keys[:1] == ["kind"] and "ssh_target" not in keys and "hostname" not in keys
    aws = [q.key for q in D.visible({"kind": "aws", "cloud_mode": "create"})]
    assert {"aws_region", "aws_instance_type", "disk_gb", "admin_cidr", "hostname", "vault"} <= set(aws)
    assert "ssh_target" not in aws                          # a machine made here: its address is found out
    existing = [q.key for q in D.visible({"kind": "aws", "cloud_mode": "existing"})]
    assert "ssh_target" in existing and "aws_region" not in existing
    here = [q.key for q in D.visible({"kind": "server", "where": "here"})]
    assert "ssh_target" not in here and "repo" not in here and "hostname" in here


def test_complete_fills_defaults_and_refuses_bad_choices():
    a = D.complete({"kind": "digitalocean", "ssh_key": KEY, "hostname": "ea.example.org", "repo": "https://github.com/a/b"})
    assert a["cloud_mode"] == "create" and a["do_size"] == "s-8vcpu-16gb" and a["install_dir"] == "/opt/eaexplorer"
    with pytest.raises(Failure, match="kind"):
        D.complete({"kind": "mainframe"})
    with pytest.raises(Failure, match="ssh_target"):
        D.complete({"kind": "server", "where": "ssh", "ssh_target": ""})


# ---------------------------------------------------------------- the config a server gets
def test_server_config_generates_every_password():
    text, made = D.server_config({"hostname": "ea.acme.test", "org_name": "Acme Mutual", "data_dir": "/data/eax/",
                                  "admin_email": "it@acme.test", "vault": "aws", "vault_name": "acme/eax"})
    assert not re.search(r"^[A-Z0-9_]+=change-me", text, re.M) and "EAX_HOSTNAME=ea.acme.test" in text and "EAX_ORG_NAME='Acme Mutual'" in text
    assert "EAX_DATA_DIR=/data/eax/postgres" in text and "EAX_TLS_DIR=/data/eax/tls" in text
    assert "EAX_SECRETS_FROM=aws:acme/eax" in text and "EAX_FIRST_ADMIN_EMAIL=it@acme.test" in text
    assert made["EAX_DMS_BROKER_PASSWORD_URLENC"] == made["EAX_DMS_BROKER_PASSWORD"]
    assert all(len(v) >= 28 and v.isalnum() for v in made.values())
    assert len(set(made.values())) == len({k.removesuffix("_URLENC") for k in made})    # each password its own
    assert set(D.secret_values(text)) == set(made)
    again, _ = D.server_config({"hostname": "ea.acme.test"})
    assert again != text                                      # new passwords every time


# ---------------------------------------------------------------- where releases come from
def test_archive_urls(monkeypatch):
    monkeypatch.delenv("EAX_ARCHIVE_URL", raising=False)
    gh = "https://github.com/acme/ea-explorer.git"
    assert D.archive_url(gh, "v0.19.0") == "https://github.com/acme/ea-explorer/archive/refs/tags/v0.19.0.tar.gz"
    assert D.archive_url(gh, "release") == "https://github.com/acme/ea-explorer/archive/refs/heads/release.tar.gz"
    assert D.archive_url(gh, "1a2b3c4d") == "https://github.com/acme/ea-explorer/archive/1a2b3c4d.tar.gz"
    assert D.archive_url("https://gitlab.com/acme/eax", "v1.0.0") == "https://gitlab.com/acme/eax/-/archive/v1.0.0/eax-v1.0.0.tar.gz"
    assert D.archive_url("https://git.acme.test/eax", "v1.0.0") == ""
    assert "git clone --depth 1 --branch v1.0.0" in D.fetch_script("https://git.acme.test/eax", "v1.0.0", "/opt/eax")
    monkeypatch.setenv("EAX_ARCHIVE_URL", "https://mirror.acme.test/{ref}.tar.gz")
    assert D.archive_url("anything", "v2") == "https://mirror.acme.test/v2.tar.gz"


# ---------------------------------------------------------------- each kind's plan
def test_laptop_plan(nothing_runs):
    text = "\n".join(plan({"kind": "laptop"}))
    assert "docker version" in text and "up" in text and "https://localhost/api/health" in text


def test_server_over_ssh_plan(nothing_runs):
    text = "\n".join(plan({"kind": "server", "where": "ssh", "ssh_target": "ubuntu@203.0.113.10", "ssh_key": KEY,
                           "hostname": "ea.acme.test", "repo": "https://github.com/acme/ea-explorer", "ref": "v0.19.0"}))
    assert "ubuntu@203.0.113.10" in text and "get.docker.com" in text
    assert "archive/refs/tags/v0.19.0.tar.gz" in text and "eaexplorer.env" in text and "./eax.sh up" in text
    assert "EA Explorer is at https://ea.acme.test" in text


def test_server_here_uses_this_copy(nothing_runs):
    text = "\n".join(plan({"kind": "server", "where": "here", "hostname": "ea.acme.test"}))
    assert "ssh " not in text and "this copy of EA Explorer" in text and "get.docker.com" in text


def test_aws_plan(nothing_runs):
    text = "\n".join(plan({"kind": "aws", "ssh_key": KEY, "hostname": "ea.acme.test", "aws_zone_id": "Z123",
                           "aws_access_key_id": "AKIAEXAMPLE", "aws_secret_access_key": "very-secret-value",
                           "repo": "https://github.com/acme/ea-explorer", "ref": "v0.19.0", "admin_cidr": "196.25.1.10/32"}))
    for part in ("ec2 import-key-pair", "create-security-group", "--port 443", "196.25.1.10/32", "ec2 run-instances",
                 "ubuntu/server/24.04", "allocate-address", "s3api create-bucket", "LocationConstraint=af-south-1",
                 "iam create-role", "route53 change-resource-record-sets", "reports.ea.acme.test", "mkfs.ext4",
                 "/dev/nvme1n1", "eaexplorer-offsite"):
        assert part in text, part
    assert "very-secret-value" not in text                   # never shown or logged


def test_azure_plan(nothing_runs):
    text = "\n".join(plan({"kind": "azure", "ssh_key": KEY, "hostname": "ea.acme.test", "az_dns_zone": "acme.test/dns-rg",
                           "repo": "https://github.com/acme/ea-explorer", "ref": "v0.19.0"}))
    for part in ("az account show", "group create", "vm create", "Ubuntu2404", "--data-disk-sizes-gb 100", "vm open-port",
                 "storage account create", "Storage Blob Data Contributor", "dns record-set a add-record", "--record-set-name reports.ea",
                 "/dev/disk/azure/scsi1/lun0", "azcopy"):
        assert part in text, part


def test_digitalocean_plan(nothing_runs):
    text = "\n".join(plan({"kind": "digitalocean", "ssh_key": KEY, "hostname": "ea.acme.test", "do_domain": "acme.test",
                           "do_load_balancer": "yes", "spaces_key": "SPACESKEY", "spaces_secret": "spaces-secret-xyz",
                           "do_token": "dop_v1_token_value", "repo": "https://github.com/acme/ea-explorer", "ref": "v0.19.0"}))
    for part in ("doctl account get", "ssh-key import", "droplet create", "ubuntu-24-04-x64", "volume create", "volume-action attach",
                 "firewall create", "digitaloceanspaces.com", "domain records create", "load-balancer create", "root@",
                 "scsi-0DO_Volume_eaexplorer-data", "Spaces key on the Droplet"):
        assert part in text, part
    assert "spaces-secret-xyz" not in text and "dop_v1_token_value" not in text


def test_existing_cloud_machine_is_the_server_over_ssh(nothing_runs):
    text = "\n".join(plan({"kind": "azure", "cloud_mode": "existing", "ssh_target": "eaxadmin@198.51.100.7", "ssh_key": KEY,
                           "hostname": "ea.acme.test", "repo": "https://github.com/acme/ea-explorer", "ref": "v0.19.0"}))
    assert "az " not in text and "eaxadmin@198.51.100.7" in text and "get.docker.com" in text


def test_moving_an_installation_restores_databases_then_files(nothing_runs):
    text = "\n".join(plan({"kind": "server", "where": "ssh", "ssh_target": "u@h", "ssh_key": KEY, "hostname": "ea.acme.test",
                           "repo": "https://github.com/acme/ea-explorer", "ref": "v0.19.0", "move_from": "backup",
                           "backup_dir": "/backups/20261110T020000Z-nightly"}))
    assert text.index("--what db") < text.index("--what files") and "--what full" not in text
    assert "20261110T020000Z-nightly" in text


def test_vault_in_the_plan(nothing_runs):
    text = "\n".join(plan({"kind": "server", "where": "ssh", "ssh_target": "u@h", "ssh_key": KEY, "hostname": "ea.acme.test",
                           "repo": "https://github.com/acme/ea-explorer", "ref": "v0.19.0", "vault": "file"}))
    assert "/etc/eaexplorer/secrets.env" in text and "install -m 600" in text


# ---------------------------------------------------------------- a failing step: retry, back, quit
def test_a_failing_step_asks(monkeypatch):
    calls = {"n": 0}

    def flaky(ctx):
        calls["n"] += 1
        if calls["n"] < 3:
            raise D.StepFailed("not yet")
    monkeypatch.setattr(D, "all_steps", lambda a: [D.Step("Flaky", flaky), D.Step("Last", lambda ctx: None)])
    asked = []
    assert D.run({"kind": "laptop"}, False, lambda s, w: asked.append(w) or "retry", out=lambda t: None) == "done"
    assert asked == ["not yet", "not yet"] and calls["n"] == 3
    calls["n"] = 0
    assert D.run({"kind": "laptop"}, False, lambda s, w: "back", out=lambda t: None) == "back"
    assert D.run({"kind": "laptop"}, False, lambda s, w: "quit", out=lambda t: None) == "quit"


# ---------------------------------------------------------------- the key vault
def test_vault_commands():
    values = {"EAX_DB_PASSWORD": "abc123", "EAX_OPS_TOKEN": "tok"}
    f = V.push_commands("file", "/etc/eaexplorer/secrets.env", values)
    assert f[0][0] == "remote" and "install -m 600" in f[0][1] and "EAX_DB_PASSWORD=abc123" in f[0][3]
    a = V.push_commands("aws", "acme/eax", values, {"aws_region": "af-south-1"})
    assert [c[0] for c in a] == ["file", "local", "local", "delete"] and "create-secret" in a[1][1]
    assert json.loads(a[0][2]) == values and "abc123" not in " ".join(a[1][1])     # the value goes by file, not the command line
    z = V.push_commands("azure", "acme-kv", values)
    assert any("eax-db-password" in c[1] for c in z if c[0] == "local")
    assert V.where("X=1\nEAX_SECRETS_FROM=azure:acme-kv\n") == ("azure", "acme-kv")
    text, changed = V.replace_values("EAX_DB_PASSWORD=old\nEAX_OPS_TOKEN=tok\n", values)
    assert changed == ["EAX_DB_PASSWORD"] and "EAX_DB_PASSWORD=abc123" in text


# ---------------------------------------------------------------- directory groups (D503)
def test_directory_groups_map_to_roles():
    from eax import permissions as P
    keys = P.group_keys(["/Acme/EA Architects", "it-admins", "1b2c-object-id"])
    assert {"group:/acme/ea architects", "group:ea architects", "group:it-admins", "group:1b2c-object-id"} == set(keys)
    mapping = {"group:ea architects": {"model-creator"}, "eax-user": {"user"}}
    assert P.app_roles(["eax-user", *keys], mapping) == ["model-creator", "user"] or \
        set(P.app_roles(["eax-user", *keys], mapping)) == {"model-creator", "user"}
    from eax.auth import user_from_claims
    u = user_from_claims({"preferred_username": "Thandi", "realm_access": {"roles": ["eax-user"]},
                          "groups": ["EA Architects"]}, mapping)
    assert "model-creator" in u.roles and "user" in u.roles


def test_the_realm_sends_the_groups_claim():
    text = (REPO / "deploy" / "keycloak" / "realm-eaexplorer.json.tmpl").read_text(encoding="utf-8")
    assert text.count('"oidc-group-membership-mapper"') >= 4 and '"claim.name": "groups"' in text


# ---------------------------------------------------------------- the installer, against a fake repository
def _fake_release(tmp: Path) -> Path:
    src = tmp / "src" / "ea-explorer-v9.9.9"
    for f in ("eax.sh", "eaxpy.sh", "eax.ps1", "eax.cmd", "eaxpy.ps1", "docker-compose.yml", "eaxcli/deploy.py",
              "deploy/templates/eaexplorer.server.env", "eax-deploy.sh"):
        (src / f).parent.mkdir(parents=True, exist_ok=True)
        (src / f).write_text("#\n", encoding="utf-8")
    (src / "services/api").mkdir(parents=True, exist_ok=True)
    (src / "services/api/version.toml").write_text('version = "9.9.9"\n', encoding="utf-8")
    archive = tmp / "v9.9.9.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        t.add(src, arcname=src.name)
    return archive


@pytest.mark.skipif(not shutil.which("bash") or not shutil.which("curl"), reason="needs bash and curl")
def test_installer_sh_downloads_checks_and_records(tmp_path):
    archive = _fake_release(tmp_path)
    folder = tmp_path / "install"
    env = {**os.environ, "EAX_NO_GIT": "1", "EAX_ARCHIVE_URL": f"file://{archive.parent}/{{ref}}.tar.gz"}
    r = subprocess.run(["bash", str(REPO / "eax-deploy.sh"), "--repo", "https://git.acme.test/eax", "--version", "v9.9.9",
                        "--folder", str(folder), "--no-deploy"], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    info = json.loads((folder / "work" / "install.json").read_text())
    assert info["ref"] == "v9.9.9" and info["version"] == "9.9.9" and info["channel"] == "prod" and info["method"].startswith("archive")
    again = subprocess.run(["bash", str(REPO / "eax-deploy.sh"), "--repo", "x", "--version", "v9.9.9", "--folder", str(folder),
                            "--no-deploy"], env=env, capture_output=True, text=True, timeout=60)
    assert again.returncode == 1 and "holds EA Explorer already" in again.stdout


@pytest.mark.skipif(not shutil.which("bash") or not shutil.which("git"), reason="needs bash and git")
def test_installer_sh_lists_the_channel_and_clones(tmp_path):
    archive = _fake_release(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    with tarfile.open(archive) as t:
        t.extractall(tmp_path / "x", filter="data")
    shutil.copytree(next((tmp_path / "x").iterdir()), repo, dirs_exist_ok=True)
    g = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run([*g, "add", "-A"], check=True)
    subprocess.run([*g, "commit", "-qm", "one"], check=True)
    for tag in ("v1.9.0", "v1.10.0", "v1.11.0-rc.1"):
        subprocess.run([*g, "tag", tag], check=True)
    folder = tmp_path / "install"
    env = {k: v for k, v in os.environ.items() if k not in ("EAX_NO_GIT", "EAX_ARCHIVE_URL")}
    r = subprocess.run(["bash", str(REPO / "eax-deploy.sh"), "--repo", str(repo), "--channel", "prod", "--folder", str(folder),
                        "--no-deploy"], env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1  v1.10.0" in r.stdout and "v1.11.0-rc.1" not in r.stdout      # newest first; rc tags only on rc
    assert json.loads((folder / "work" / "install.json").read_text())["ref"] == "v1.10.0"


PWSH = os.environ.get("EAX_PWSH") or shutil.which("pwsh")


@pytest.mark.skipif(not PWSH or not shutil.which("tar"), reason="no PowerShell here (set EAX_PWSH)")
def test_installer_ps1_downloads_checks_and_records(tmp_path):
    archive = _fake_release(tmp_path)
    folder = tmp_path / "install"
    env = {**os.environ, "EAX_NO_GIT": "1", "EAX_ARCHIVE_URL": f"file://{archive.parent}/{{ref}}.tar.gz"}
    r = subprocess.run([PWSH, "-NoProfile", "-File", str(REPO / "eax-deploy.ps1"), "-Repo", "https://git.acme.test/eax",
                        "-Version", "v9.9.9", "-Folder", str(folder), "-NoDeploy"], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    info = json.loads((folder / "work" / "install.json").read_text(encoding="utf-8"))
    assert info["ref"] == "v9.9.9" and info["version"] == "9.9.9"


# ---------------------------------------------------------------- the web wizard
def test_web_wizard_needs_its_key_and_plans(monkeypatch):
    from eaxcli import deploy_web as W
    state = W.State({}, plan=False)
    stop = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", 0), W.make_handler(state, "k3y", stop))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None, key="k3y"):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"X-Deploy-Key": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:      # noqa: S310 - the test's own server
            return json.loads(r.read())
    try:
        page = urllib.request.urlopen(base + "/", timeout=10).read().decode()       # noqa: S310
        assert "Deploy EA Explorer" in page and "k3y" in page
        with pytest.raises(urllib.error.HTTPError) as e:
            call("/api/state", key="wrong")
        assert e.value.code == 403
        qs = call("/api/questions", {"answers": {"kind": "aws"}})["questions"]
        assert any(q["key"] == "aws_region" for q in qs)
        monkeypatch.setattr(D.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
        assert call("/api/plan", {"answers": {"kind": "server", "where": "here", "hostname": "ea.acme.test"}})["ok"]
        for _ in range(50):
            s = call("/api/state")
            if s["status"] != "running":
                break
            threading.Event().wait(0.1)
        assert s["status"] == "planned" and any("get.docker.com" in line for line in s["lines"])
        assert all(st["status"] == "done" for st in s["steps"])
    finally:
        server.shutdown()
