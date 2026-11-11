"""eax deploy (phase 36, D498, D500 to D506): a deployment wizard, in the console or in a local web page, with the same
questions and steps in both.

Where to deploy (the five kinds, D416, D457):
  laptop        this computer, Docker Desktop
  server        a Linux server, run on the server itself or from here over SSH; Docker is installed if it is missing
  aws           an EC2 machine (created from the person's credentials, or one that exists) running our Docker stack
  azure         an Azure VM (created or existing), the same
  digitalocean  a Droplet (created or existing), the same

The wizard asks its questions (QUESTIONS, shown only when they apply), makes the steps for the answers (steps_for) and
runs them one by one. Every step is logged (work/logs/eax-<time>-deploy.log, passwords masked). A step that fails
stops and asks: Retry, Back (to the answers, kept) or Quit. --plan prints every step and every command it would run,
and runs nothing. Cloud credentials are used for this run only, unless the person asks to keep them
(work/deploy-credentials.env, readable by the owner only).

Command line: eax deploy [--console|--web] [--kind K] [--answers file.json] [--set key=value ...] [--plan] [--yes]
"""

from __future__ import annotations

import json
import os
import re
import secrets as _secrets
import shlex
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .core import EAX, ROOT, WINDOWS, WORK, Failure, log_only, say

KINDS = {
    "laptop": "This computer (a laptop or desktop with Docker Desktop)",
    "server": "A Linux server (one you have: this one, or one reached over SSH)",
    "aws": "Amazon Web Services (an EC2 machine running our Docker stack)",
    "azure": "Microsoft Azure (a virtual machine running our Docker stack)",
    "digitalocean": "DigitalOcean (a Droplet running our Docker stack)",
}
CLOUDS = ("aws", "azure", "digitalocean")
INSTALL_FILE = WORK / "install.json"            # written by the installer: where this copy came from (D502)
CREDENTIALS_FILE = WORK / "deploy-credentials.env"
SECRET_KEYS = ("aws_secret_access_key", "do_token", "spaces_secret", "az_client_secret", "first_admin_password")


# ---------------------------------------------------------------- the questions
@dataclass
class Question:
    key: str
    text: str
    default: str | Callable[[dict], str] = ""
    choices: dict[str, str] | None = None
    when: Callable[[dict], bool] = lambda a: True
    help: str = ""
    secret: bool = False
    required: bool = True

    def default_for(self, answers: dict) -> str:
        return self.default(answers) if callable(self.default) else self.default

    def as_dict(self, answers: dict) -> dict:
        return {"key": self.key, "text": self.text, "default": self.default_for(answers), "choices": self.choices,
                "help": self.help, "secret": self.secret, "required": self.required}


def _installed() -> dict:
    try:
        return json.loads(INSTALL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ssh_key_default(_a: dict) -> str:
    home = Path.home() / ".ssh"
    for name in ("id_ed25519", "id_rsa", "id_ecdsa"):
        if (home / name).exists():
            return str(home / name)
    return str(home / "id_ed25519")


def _remote(a: dict) -> bool:
    """The installation is on another machine, reached over SSH."""
    return a.get("kind") in CLOUDS or (a.get("kind") == "server" and a.get("where") == "ssh")


def _create(a: dict) -> bool:
    return a.get("kind") in CLOUDS and a.get("cloud_mode", "create") == "create"


def _server_like(a: dict) -> bool:
    return a.get("kind") in ("server", *CLOUDS)


def _suffix(a: dict) -> str:
    return re.sub(r"[^a-z0-9]", "", a.get("name", "eaexplorer").lower())[:20] or "eaexplorer"


QUESTIONS: list[Question] = [
    Question("kind", "Where do you want EA Explorer?", "laptop", KINDS),
    Question("where", "Run on this server, or set up another server from here over SSH?", "here",
             {"here": "This machine is the server (Linux)", "ssh": "Another server, reached over SSH from here"},
             when=lambda a: a.get("kind") == "server"),
    Question("cloud_mode", "Create the machine in the cloud, or use one you already have?", "create",
             {"create": "Create it for me (from my cloud credentials)", "existing": "Use a machine I already have (over SSH)"},
             when=lambda a: a.get("kind") in CLOUDS),
    Question("name", "A short name for this installation (used to name the cloud resources)", "eaexplorer",
             when=lambda a: _create(a)),
    # --- AWS
    Question("aws_profile", "AWS CLI profile to use (leave empty to type an access key below)", "default",
             when=lambda a: _create(a) and a["kind"] == "aws", required=False),
    Question("aws_access_key_id", "AWS access key ID (only if no profile; used for this run only)", "",
             when=lambda a: _create(a) and a["kind"] == "aws" and not a.get("aws_profile"), required=False),
    Question("aws_secret_access_key", "AWS secret access key", "", secret=True,
             when=lambda a: _create(a) and a["kind"] == "aws" and not a.get("aws_profile") and a.get("aws_access_key_id")),
    Question("aws_region", "AWS region", "af-south-1", when=lambda a: _create(a) and a["kind"] == "aws",
             help="af-south-1 is Cape Town; any region works."),
    Question("aws_instance_type", "EC2 instance type (16 GB of memory or more)", "t3.xlarge",
             when=lambda a: _create(a) and a["kind"] == "aws"),
    Question("aws_zone_id", "Route 53 hosted zone ID for the DNS names (leave empty to set DNS yourself)", "",
             when=lambda a: _create(a) and a["kind"] == "aws", required=False),
    # --- Azure
    Question("az_subscription", "Azure subscription (name or ID; empty: the current one of az account show)", "",
             when=lambda a: _create(a) and a["kind"] == "azure", required=False),
    Question("az_client_id", "Service principal's application (client) ID (empty: the az login already on this computer)", "",
             when=lambda a: _create(a) and a["kind"] == "azure", required=False,
             help="Needed when deploying from the System admin > Deploy page (no az login there)."),
    Question("az_client_secret", "Service principal's secret", "", secret=True,
             when=lambda a: _create(a) and a["kind"] == "azure" and a.get("az_client_id")),
    Question("az_tenant", "Tenant ID", "", when=lambda a: _create(a) and a["kind"] == "azure" and a.get("az_client_id")),
    Question("az_location", "Azure region", "southafricanorth", when=lambda a: _create(a) and a["kind"] == "azure"),
    Question("az_group", "Resource group (created if missing)", lambda a: f"{_suffix(a)}-rg",
             when=lambda a: _create(a) and a["kind"] == "azure"),
    Question("az_size", "VM size (16 GB of memory or more)", "Standard_D4s_v5", when=lambda a: _create(a) and a["kind"] == "azure"),
    Question("az_dns_zone", "Azure DNS zone for the names, and its resource group as zone/group (leave empty to set DNS yourself)",
             "", when=lambda a: _create(a) and a["kind"] == "azure", required=False),
    # --- DigitalOcean
    Question("do_token", "DigitalOcean API token (empty: doctl's current context; used for this run only)", "", secret=True,
             when=lambda a: _create(a) and a["kind"] == "digitalocean", required=False),
    Question("do_region", "DigitalOcean region", "lon1", when=lambda a: _create(a) and a["kind"] == "digitalocean"),
    Question("do_size", "Droplet size (16 GB of memory or more)", "s-8vcpu-16gb", when=lambda a: _create(a) and a["kind"] == "digitalocean"),
    Question("do_domain", "DigitalOcean domain for the DNS names (leave empty to set DNS yourself)", "",
             when=lambda a: _create(a) and a["kind"] == "digitalocean", required=False),
    Question("do_load_balancer", "Put a DigitalOcean load balancer in front (for more Droplets later)?", "no",
             {"no": "No: one Droplet", "yes": "Yes: a load balancer passing https through to the Droplet"},
             when=lambda a: _create(a) and a["kind"] == "digitalocean"),
    Question("spaces_key", "Spaces access key, for off-site backups (empty: skip off-site backups)", "",
             when=lambda a: _create(a) and a["kind"] == "digitalocean", required=False),
    Question("spaces_secret", "Spaces secret key", "", secret=True,
             when=lambda a: _create(a) and a["kind"] == "digitalocean" and a.get("spaces_key")),
    # --- all clouds that are created
    Question("disk_gb", "Data disk size in GB (databases, documents, backups)", "100", when=_create),
    Question("admin_cidr", "Address range allowed to use SSH (your address, e.g. 196.25.1.10/32)", "0.0.0.0/0", when=_create,
             help="0.0.0.0/0 lets anyone try SSH (keys only); your own address is safer."),
    Question("offsite_backups", "Copy the nightly backups to the cloud's storage (S3, Blob storage, Spaces)?", "yes",
             {"yes": "Yes: a bucket or container is made and backups are copied every night", "no": "No"}, when=_create),
    # --- SSH
    Question("ssh_target", "The server to set up, as user@address", "", when=lambda a: _remote(a) and not _create(a),
             help="A user who may use sudo, e.g. ubuntu@203.0.113.10"),
    Question("ssh_key", "SSH private key to sign in with", _ssh_key_default, when=_remote,
             help="For a machine created here, its public key (.pub beside it) is put on the machine."),
    Question("ssh_port", "SSH port", "22", when=_remote),
    # --- the installation
    Question("hostname", "The address people will open (a DNS name)", lambda a: "ea.example.org", when=_server_like,
             help="https://<this>; reports.<this> and docs.<this> are used too: three DNS names pointing at the server."),
    Question("org_name", "Your organisation's name", "My organisation", when=_server_like),
    Question("admin_email", "The first EA Explorer administrator's email", lambda a: f"eaadmin@{a.get('hostname', 'example.org')}",
             when=_server_like),
    Question("tls", "Certificate", "self-signed",
             {"self-signed": "A self-signed certificate made at the first start (browsers warn until it is trusted)",
              "own": "My organisation's certificate (a folder here with tls.crt and tls.key)"}, when=_server_like),
    Question("tls_dir", "Folder (on this computer) holding tls.crt and tls.key", "", when=lambda a: _server_like(a) and a.get("tls") == "own"),
    Question("install_dir", "Installation folder on the server", "/opt/eaexplorer", when=_server_like),
    Question("data_dir", "Data folder on the server (databases, documents, imports, exports, certificate)", "/srv/eax", when=_server_like),
    Question("repo", "Repository link (the public git URL EA Explorer comes from)", lambda a: _installed().get("repo", "") or "https://github.com/gauravvermaea/EA-Enterpise",
             when=_remote, help="The same link the installer used; the server downloads the release from there."),
    Question("ref", "Version to install (a tag such as v0.19.0, or a branch)", lambda a: _installed().get("ref", "release"),
             when=_remote),
    Question("move_from", "Start empty, or move an existing installation here?", "empty",
             {"empty": "Start empty", "backup": "Move an existing installation: restore one of its infrastructure backups"}),
    Question("backup_dir", "The infrastructure backup's folder on this computer (from the old installation's work/backups/infrastructure)",
             "", when=lambda a: a.get("move_from") == "backup"),
    Question("vault", "Keep the passwords in a key vault too?", "none",
             {"none": "No: only in the config file (readable by its owner only)",
              "file": "A file outside the installation (e.g. /etc/eaexplorer/secrets.env)",
              "aws": "AWS Secrets Manager", "azure": "Azure Key Vault",
              "digitalocean": "DigitalOcean: a file on the Droplet, readable by root only"},
             when=_server_like),
    Question("vault_name", "The vault: a file path, a Secrets Manager secret name, or a Key Vault name",
             lambda a: {"file": "/etc/eaexplorer/secrets.env", "aws": f"{_suffix(a)}/eaexplorer",
                        "azure": f"{_suffix(a)}-kv", "digitalocean": "/etc/eaexplorer/secrets.env"}.get(a.get("vault"), ""),
             when=lambda a: _server_like(a) and a.get("vault", "none") != "none"),
    Question("keep_credentials", "Keep the cloud credentials for next time (in work/deploy-credentials.env)?", "no",
             {"no": "No: used for this run only", "yes": "Yes: kept on this computer, readable by me only"},
             when=lambda a: _create(a) and bool(a.get("aws_access_key_id") or a.get("do_token") or a.get("spaces_key")
                                                 or a.get("az_client_id"))),
]
BY_KEY = {q.key: q for q in QUESTIONS}


def visible(answers: dict) -> list[Question]:
    """The questions that apply to these answers, in order."""
    return [q for q in QUESTIONS if q.when(answers)]


def complete(answers: dict) -> dict:
    """The answers with every applicable question filled (defaults for the unanswered); unknown choices refused."""
    out = dict(answers)
    for _ in range(3):                              # a later answer can make earlier defaults apply (kind first)
        for q in visible(out):
            if q.key not in out or out[q.key] is None:
                out[q.key] = q.default_for(out)
    problems = []
    for q in visible(out):
        v = str(out.get(q.key, "")).strip()
        out[q.key] = v
        if q.choices and v not in q.choices:
            problems.append(f"{q.key}: one of {', '.join(q.choices)} (not {v!r})")
        elif q.required and not v and not q.secret:
            problems.append(f"{q.key}: {q.text}")
    if problems:
        raise Failure("Answers missing or not allowed:\n  " + "\n  ".join(problems))
    return out


# ---------------------------------------------------------------- the config file for a server or a cloud machine
def password(length: int = 28) -> str:
    """A long random password of letters and digits only (no $, quotes or URL characters to escape)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(_secrets.choice(alphabet) for _ in range(length))


def server_config(answers: dict, template: Path | None = None) -> tuple[str, dict[str, str]]:
    """work/eaexplorer.env for a server from deploy/templates/eaexplorer.server.env: every change-me password
    generated, the site, the folders and the certificate folder set. Returns (text, the generated secrets)."""
    template = template or ROOT / "deploy" / "templates" / "eaexplorer.server.env"
    data = answers.get("data_dir", "/srv/eax").rstrip("/")
    sets = {
        "EAX_HOSTNAME": answers["hostname"],
        "EAX_ORG_NAME": answers.get("org_name", "My organisation"),
        "EAX_FIRST_ADMIN_EMAIL": answers.get("admin_email", f"eaadmin@{answers['hostname']}"),
        "EAX_DATA_DIR": f"{data}/postgres", "EAX_DOCS_DIR": f"{data}/documents",
        "EAX_IMPORT_DIR": f"{data}/imports", "EAX_EXPORT_DIR": f"{data}/exports", "EAX_TLS_DIR": f"{data}/tls",
        "EAX_DEPLOYMENT": "server",
    }
    if answers.get("vault", "none") != "none":
        sets["EAX_SECRETS_FROM"] = f"{'file' if answers['vault'] == 'digitalocean' else answers['vault']}:{answers.get('vault_name', '')}"
    made: dict[str, str] = {}
    lines = []
    seen = set()
    for line in template.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m:
            key, value = m.groups()
            seen.add(key)
            if key in sets:
                v = sets[key]
                line = f"{key}='{v}'" if (" " in v or "$" in v) else f"{key}={v}"
            elif value.startswith("change-me"):
                base = key.removesuffix("_URLENC")
                made.setdefault(base, password(40 if "SECRET" in key or "KEY" in key else 28))
                made[key] = made[base]           # the URL-encoded copy: letters and digits need no encoding
                line = f"{key}={made[key]}"
        lines.append(line)
    for key, v in sets.items():
        if key not in seen:
            lines.append(f"{key}={v}")
    text = "\n".join(lines) + "\n"
    if re.search(r"^[A-Z0-9_]+=['\"]?change-me", text, re.MULTILINE):
        raise Failure("The config still has a change-me value (the template changed?).")
    return text, made


def secret_values(env_text: str) -> dict[str, str]:
    """The passwords and keys of a config file (every key the server template holds as change-me)."""
    template = (ROOT / "deploy" / "templates" / "eaexplorer.server.env").read_text(encoding="utf-8")
    keys = {m.group(1) for m in re.finditer(r"^([A-Z0-9_]+)=change-me", template, re.MULTILINE)}
    out = {}
    for m in re.finditer(r"^([A-Z0-9_]+)=(.*)$", env_text, re.MULTILINE):
        if m.group(1) in keys:
            out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


# ---------------------------------------------------------------- where the release comes from (D417, D502)
def archive_url(repo: str, ref: str) -> str:
    """The address of a release archive (.tar.gz) of a repository at a tag, branch or commit, without git.
    GitHub and GitLab are known; anything else needs EAX_ARCHIVE_URL (e.g. https://host/{repo}/{ref}.tar.gz) or git."""
    template = os.environ.get("EAX_ARCHIVE_URL", "")
    repo = repo.strip().removesuffix("/").removesuffix(".git")
    if template:
        return template.replace("{repo}", repo).replace("{ref}", ref)
    m = re.match(r"^(?:https?://|git@)(github\.com|gitlab\.com)[/:]([^/]+)/([^/]+)$", repo)
    if not m:
        return ""
    host, owner, name = m.groups()
    if host == "github.com":
        if re.fullmatch(r"[0-9a-f]{7,40}", ref):
            return f"https://github.com/{owner}/{name}/archive/{ref}.tar.gz"
        kind = "tags" if re.match(r"^v\d", ref) else "heads"
        return f"https://github.com/{owner}/{name}/archive/refs/{kind}/{ref}.tar.gz"
    return f"https://gitlab.com/{owner}/{name}/-/archive/{ref}/{name}-{ref}.tar.gz"


def fetch_script(repo: str, ref: str, folder: str) -> str:
    """Shell lines that put the release into folder on a Linux machine: the archive with curl, or a shallow clone."""
    url = archive_url(repo, ref)
    q = shlex.quote
    if url:
        return (f"sudo mkdir -p {q(folder)} && curl -fsSL {q(url)} -o /tmp/eaexplorer.tar.gz && "
                f"sudo tar -xzf /tmp/eaexplorer.tar.gz -C {q(folder)} --strip-components=1 && rm -f /tmp/eaexplorer.tar.gz")
    return (f"(command -v git >/dev/null || (sudo apt-get update -y && sudo apt-get install -y git)) && "
            f"sudo rm -rf /tmp/eaexplorer-src && git clone --depth 1 --branch {q(ref)} {q(repo)} /tmp/eaexplorer-src && "
            f"sudo mkdir -p {q(folder)} && sudo cp -a /tmp/eaexplorer-src/. {q(folder)}/ && sudo rm -rf /tmp/eaexplorer-src")


# ---------------------------------------------------------------- running steps
class StepFailed(Exception):
    pass


@dataclass
class Ctx:
    answers: dict
    plan: bool = False
    values: dict = field(default_factory=dict)          # what earlier steps found out (an instance ID, an address)
    printed: list = field(default_factory=list)          # the plan, line by line
    mask: set = field(default_factory=set)               # values never written to the log
    env: dict = field(default_factory=dict)              # extra environment for the cloud CLIs (credentials)
    out: Callable[[str], None] = print
    reveal: bool = True                                  # the first password shown once on screen (never from the page)

    def hide(self, text: str) -> str:
        for m in sorted(self.mask, key=len, reverse=True):
            if m and len(m) >= 4:
                text = text.replace(m, "********")
        return text

    def note(self, text: str) -> None:
        text = self.hide(text)
        if self.plan:
            self.printed.append(text)
        self.out(text)
        log_only(text)

    def get(self, key: str, placeholder: str = "") -> str:
        return self.values.get(key) or placeholder or f"<{key}>"

    def run(self, argv: list[str], what: str = "", input_text: str | None = None, ok_codes: tuple = (0,),
            capture: bool = True, attach: bool = False) -> str:
        """One command here. In plan mode it is only printed."""
        shown = " ".join(shlex.quote(a) for a in argv)
        self.note(f"    $ {shown}" if not what else f"    $ {shown}    # {what}")
        if self.plan:
            return ""
        exe = shutil.which(argv[0]) or argv[0]
        env = {**os.environ, **self.env}
        if attach:
            code = subprocess.run([exe, *argv[1:]], env=env, input=input_text, text=True, check=False).returncode
            out = ""
        else:
            p = subprocess.run([exe, *argv[1:]], env=env, input=input_text, text=True, capture_output=True, check=False)
            code, out = p.returncode, (p.stdout or "")
            log_only(self.hide((p.stdout or "")[-4000:] + (p.stderr or "")[-4000:]))
            if code not in ok_codes:
                raise StepFailed(self.hide(f"{argv[0]} failed (exit {code}): {(p.stderr or p.stdout or '').strip()[-800:]}"))
        if attach and code not in ok_codes:
            raise StepFailed(f"{argv[0]} failed (exit {code})")
        return out if capture else ""

    def ssh_argv(self) -> list[str]:
        a = self.answers
        target = self.values.get("ssh_target") or a.get("ssh_target") or "<user@address>"
        return ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                "-i", a.get("ssh_key", ""), "-p", str(a.get("ssh_port", "22")), target]

    def remote(self, script: str, what: str = "", input_text: str | None = None) -> str:
        """Shell lines on the server, over SSH (or here, when this machine is the server)."""
        if not _remote(self.answers):
            return self.run(["bash", "-c", script], what, input_text)
        return self.run([*self.ssh_argv(), script], what, input_text)

    def upload(self, local: Path | str, remote_path: str, what: str = "") -> None:
        if not _remote(self.answers):
            self.run(["sudo", "cp", str(local), remote_path], what)
            return
        a = self.answers
        target = self.values.get("ssh_target") or a.get("ssh_target") or "<user@address>"
        self.run(["scp", "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-i", a.get("ssh_key", ""),
                  "-P", str(a.get("ssh_port", "22")), str(local), f"{target}:{remote_path}"], what)

    def wait(self, what: str, test: Callable[[], bool], minutes: float = 10, every: float = 10) -> None:
        self.note(f"    (wait until {what}, at most {minutes:g} minutes)")
        if self.plan:
            return
        end = time.monotonic() + minutes * 60
        while time.monotonic() < end:
            try:
                if test():
                    return
            except (StepFailed, OSError):
                pass
            time.sleep(every)
        raise StepFailed(f"Gave up waiting until {what} ({minutes:g} minutes).")


@dataclass
class Step:
    title: str
    fn: Callable[[Ctx], None]


def jget(text: str, *path, default: str = "") -> str:
    """A value from a CLI's JSON output (plan mode: the default)."""
    try:
        v = json.loads(text)
        for p in path:
            v = v[p]
        return str(v)
    except (ValueError, KeyError, IndexError, TypeError):
        return default


# ---------------------------------------------------------------- the steps of each kind
def steps_for(a: dict) -> list[Step]:
    kind = a["kind"]
    if kind == "laptop":
        return laptop_steps(a)
    steps: list[Step] = []
    if kind == "aws" and _create(a):
        steps += aws_steps(a)
    elif kind == "azure" and _create(a):
        steps += azure_steps(a)
    elif kind == "digitalocean" and _create(a):
        steps += do_steps(a)
    steps += server_steps(a)
    return steps


def laptop_steps(a: dict) -> list[Step]:
    from .main import run_self

    def docker(ctx: Ctx):
        ctx.run(["docker", "version", "--format", "Docker {{.Server.Version}}"], "Docker Desktop is running")

    def config(ctx: Ctx):
        env = WORK / "eaexplorer.env"
        if env.exists():
            ctx.note(f"    work/eaexplorer.env exists: kept (to start again from scratch: {EAX} clean-restart)")
            return
        ctx.note(f"    $ {EAX} init laptop")
        if not ctx.plan and run_self(["init", "laptop"]) != 0:
            raise StepFailed(f"{EAX} init laptop failed")

    def up(ctx: Ctx):
        ctx.note(f"    $ {EAX} up")
        if not ctx.plan and run_self(["up"]) != 0:
            raise StepFailed(f"{EAX} up failed: see its log in work/logs")

    def healthy(ctx: Ctx):
        ctx.wait("https://localhost/api/health answers", lambda: _http_ok("https://localhost/api/health"), minutes=10)

    def done(ctx: Ctx):
        ctx.note("    EA Explorer is at https://localhost (run trust once so the browser stops warning).")
        ctx.note(f"    $ {EAX} url")
        if not ctx.plan:
            run_self(["url"])
        for line in check_hint():
            ctx.note(line)

    steps = [Step("Check that Docker Desktop is running", docker), Step("Make the config file (laptop)", config),
             Step("Start EA Explorer", up), Step("Check that it is healthy", healthy)]
    if a.get("move_from") == "backup":
        steps.append(Step("Move the old installation here: restore its backup", restore_local))
    steps.append(Step("Show the address and the logins", done))
    return steps


def check_hint(address: str = "https://localhost") -> list[str]:
    """The three lines shown when a deployment is done (and on the first start): how to check the installation."""
    return ["    Check your installation: System admin > Self-test > Build the test runner, then Smoke test > Start;",
            f"      or {EAX} test --smoke here; or from another machine {EAX} testbench --target {address} --i-own-this --smoke.",
            "      Results: Self-test > History (and the report). Steps: docs/deployment.md, \"Check your installation\"."]


def _http_ok(url: str) -> bool:
    import ssl
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, timeout=10, context=ctx) as r:
            return r.status == 200
    except OSError:
        return False


def restore_local(ctx: Ctx) -> None:
    """Moving an installation (D505): the old installation's infrastructure backup is put into this one's
    work/backups/infrastructure and restored: every database, then the files (documents, certificate, reports, imports,
    exports). The config file is not restored: this installation keeps its own address and passwords (the database
    logins already here are kept, D410)."""
    from .main import run_self
    src = Path(ctx.answers["backup_dir"]).expanduser()
    name = src.name
    dest = WORK / "backups" / "infrastructure" / name
    ctx.note(f"    copy {src} -> {dest}")
    if not ctx.plan:
        if not (src / "manifest.json").exists() and not any(src.glob("*.json")):
            raise StepFailed(f"{src} does not look like an infrastructure backup (no manifest).")
        shutil.copytree(src, dest, dirs_exist_ok=True)
    for what in ("db", "files"):
        ctx.note(f"    $ {EAX} restore {name} --what {what} --yes")
        if not ctx.plan and run_self(["restore", name, "--what", what, "--yes"]) != 0:
            raise StepFailed(f"{EAX} restore {name} --what {what} failed: see its log in work/logs")


DOCKER_INSTALL = ("if ! command -v docker >/dev/null 2>&1; then curl -fsSL https://get.docker.com -o /tmp/get-docker.sh "
                  "&& sudo sh /tmp/get-docker.sh && sudo systemctl enable --now docker; fi; "
                  "sudo usermod -aG docker \"$(id -un)\" || true; docker --version || sudo docker --version; "
                  "sudo docker compose version")


def server_steps(a: dict) -> list[Step]:
    """A Linux server (this one, or over SSH; a cloud machine just made): Docker, the release, the config, start,
    health, off-site backups, the key vault, and moving an old installation here."""
    folder, data = a["install_dir"].rstrip("/"), a["data_dir"].rstrip("/")
    q = shlex.quote
    steps: list[Step] = []

    def reach(ctx: Ctx):
        if _remote(ctx.answers):
            ctx.wait("the server answers over SSH", lambda: bool(ctx.remote("echo ok", "sign in over SSH").strip()) or ctx.plan,
                     minutes=8, every=15)
        ctx.remote("uname -sm; . /etc/os-release 2>/dev/null && echo \"$PRETTY_NAME\"; free -g | awk '/Mem/{print $2\" GB memory\"}'",
                   "what the server is")

    def docker(ctx: Ctx):
        ctx.remote(DOCKER_INSTALL, "Docker and Docker Compose (installed from get.docker.com if missing)")

    def disk(ctx: Ctx):
        dev = ctx.values.get("data_device", "")
        if not dev:
            ctx.remote(f"sudo mkdir -p {q(data)}", "the data folder")
            return
        ctx.remote(f"set -e; D={q(dev)}; for i in $(seq 1 30); do [ -e \"$D\" ] && break; sleep 5; done; "
                   f"sudo blkid \"$D\" >/dev/null 2>&1 || sudo mkfs.ext4 -q \"$D\"; sudo mkdir -p {q(data)}; "
                   f"U=$(sudo blkid -s UUID -o value \"$D\"); grep -q \"$U\" /etc/fstab || "
                   f"echo \"UUID=$U {data} ext4 defaults,nofail 0 2\" | sudo tee -a /etc/fstab >/dev/null; "
                   f"mountpoint -q {q(data)} || sudo mount {q(data)}",
                   f"the data disk ({dev}) formatted once and mounted at {data}")

    def release(ctx: Ctx):
        if not _remote(ctx.answers):
            ctx.note(f"    this copy of EA Explorer ({ROOT}) is used on this server")
            ctx.values["folder"] = str(ROOT)
            return
        ctx.remote(fetch_script(a["repo"], a["ref"], folder), f"EA Explorer {a['ref']} from {a['repo']}")
        ctx.remote(f"test -f {q(folder)}/eax.sh && test -f {q(folder)}/docker-compose.yml && sudo chmod +x {q(folder)}/eax.sh "
                   f"{q(folder)}/eaxpy.sh && grep -m1 '^version' {q(folder)}/services/api/version.toml", "check the release")

    def config(ctx: Ctx):
        where = ctx.values.get("folder", folder)
        found = ctx.remote(f"test -f {q(where)}/work/eaexplorer.env && echo exists || true", "a config file there already?")
        if "exists" in found:
            ctx.note("    the server has a config file already: kept as it is (its passwords match its databases)")
            ctx.values["config_text"] = ctx.remote(f"sudo cat {q(where)}/work/eaexplorer.env", "read it (for the key vault)") \
                if ctx.answers.get("vault", "none") != "none" else ""
            return
        text, made = server_config(ctx.answers)
        ctx.mask.update(made.values())
        ctx.values["first_admin_password"] = made.get("EAX_FIRST_ADMIN_PASSWORD", "")
        ctx.values["config_text"] = text
        ctx.note(f"    config: {len(made)} passwords and keys generated; site https://{a['hostname']}; data in {data}")
        tmp = WORK / "deploy" / "eaexplorer.env"
        if not ctx.plan:
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text, encoding="utf-8", newline="\n")
            _owner_only(tmp)
        ctx.upload(tmp, "/tmp/eaexplorer.env", "the config file")
        ctx.remote(f"sudo mkdir -p {q(where)}/work/logs {q(where)}/work/backups {q(where)}/work/proxy && "
                   f"for d in postgres documents imports exports tls; do sudo mkdir -p {q(data)}/$d; done && "
                   f"sudo install -m 600 /tmp/eaexplorer.env {q(where)}/work/eaexplorer.env && rm -f /tmp/eaexplorer.env",
                   "put it in place, readable by its owner only")
        if not ctx.plan:
            tmp.unlink(missing_ok=True)

    def certificate(ctx: Ctx):
        src = Path(a.get("tls_dir", "")).expanduser()
        for f in ("tls.crt", "tls.key"):
            if not ctx.plan and not (src / f).exists():
                raise StepFailed(f"{src / f} is missing.")
            ctx.upload(src / f, f"/tmp/{f}", f"your certificate's {f}")
        ctx.remote(f"sudo install -m 644 /tmp/tls.crt {q(data)}/tls/tls.crt && sudo install -m 600 /tmp/tls.key {q(data)}/tls/tls.key "
                   f"&& rm -f /tmp/tls.crt /tmp/tls.key", "into the certificate folder")

    def vault(ctx: Ctx):
        from . import secrets as vault_
        provider, name = (ctx.answers["vault"], ctx.answers["vault_name"])
        values = secret_values(ctx.values.get("config_text", ""))
        ctx.mask.update(values.values())
        if ctx.plan and not values:
            values = {k: "<generated>" for k in secret_values((ROOT / "deploy" / "templates" / "eaexplorer.server.env")
                                                              .read_text(encoding="utf-8").replace("=change-me", "=x"))}
        for where_, what, *rest in vault_.push_commands(provider, name, values, ctx.answers):
            if where_ == "remote":
                ctx.remote(what, rest[0], input_text=rest[1] if len(rest) > 1 else None)
            elif where_ == "file":
                path, body = what, rest[0]
                ctx.note(f"    write {path} (readable by you only, deleted after the next command)")
                if not ctx.plan:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    Path(path).write_text(body, encoding="utf-8")
                    _owner_only(Path(path))
            elif where_ == "delete":
                if not ctx.plan:
                    Path(what).unlink(missing_ok=True)
            else:
                ctx.run(what, rest[0], ok_codes=tuple(rest[1]) if len(rest) > 1 else (0,))

    def start(ctx: Ctx):
        where = ctx.values.get("folder", folder)
        ctx.remote(f"cd {q(where)} && sudo ./eax.sh up", "start EA Explorer (the first start builds the images: 10 to 20 minutes)")

    def healthy(ctx: Ctx):
        url = "https://localhost/api/health"
        ctx.wait("EA Explorer answers on the server",
                 lambda: "ok" in ctx.remote(f"curl -fsk -o /dev/null -w ok -H 'Host: {a['hostname']}' {url}", "health"),
                 minutes=20, every=20)

    def restore(ctx: Ctx):
        src = Path(a["backup_dir"]).expanduser()
        where = ctx.values.get("folder", folder)
        name = src.name
        if not ctx.plan and not src.is_dir():
            raise StepFailed(f"{src} is not a folder.")
        archive = WORK / "deploy" / f"{name}.tar.gz"
        ctx.note(f"    pack {src} -> {archive}")
        if not ctx.plan:
            archive.parent.mkdir(parents=True, exist_ok=True)
            import tarfile
            with tarfile.open(archive, "w:gz") as t:
                t.add(src, arcname=name)
        ctx.upload(archive, f"/tmp/{name}.tar.gz", "the backup")
        ctx.remote(f"sudo mkdir -p {q(where)}/work/backups/infrastructure && sudo tar -xzf /tmp/{q(name)}.tar.gz "
                   f"-C {q(where)}/work/backups/infrastructure && rm -f /tmp/{q(name)}.tar.gz", "unpack it")
        for what in ("db", "files"):
            ctx.remote(f"cd {q(where)} && sudo ./eax.sh restore {q(name)} --what {what} --yes",
                       f"restore {'every database' if what == 'db' else 'the files'} (the config file stays this server's)")
        if not ctx.plan:
            archive.unlink(missing_ok=True)

    def offsite(ctx: Ctx):
        line = ctx.values.get("offsite_cron", "")
        if not line:
            ctx.note("    no off-site storage was made: skipped")
            return
        ctx.remote(f"echo {q(line)} | sudo tee /etc/cron.d/eaexplorer-offsite >/dev/null && sudo chmod 644 /etc/cron.d/eaexplorer-offsite",
                   "a nightly copy of work/backups to the cloud's storage (03:30)")

    def done(ctx: Ctx):
        pw = ctx.values.get("first_admin_password", "")
        ctx.note(f"    EA Explorer is at https://{a['hostname']}  (reports: https://reports.{a['hostname']}, "
                 f"documents: https://docs.{a['hostname']})")
        ip = ctx.values.get("public_ip", "")
        if ip:
            ctx.note(f"    The server's public address is {ip}: the three DNS names must point at it.")
        ctx.note(f"    First sign-in: eaadmin, with the password in {folder}/work/eaexplorer.env (EAX_FIRST_ADMIN_PASSWORD); "
                 "Keycloak asks for a new one at the first sign-in.")
        if pw and not ctx.plan and ctx.reveal:
            ctx.out(f"    (this time only, on screen and not in the log: the first password is {pw})")
        for line in check_hint(f"https://{a['hostname']}"):
            ctx.note(line)

    steps.append(Step("Reach the server", reach))
    steps.append(Step("Docker on the server (installed if missing)", docker))
    steps.append(Step("The data folder" + (" and its disk" if _create(a) else ""), disk))
    steps.append(Step("Download EA Explorer onto the server" if _remote(a) else "Use this copy of EA Explorer", release))
    steps.append(Step("Make the config file: the site, the folders, every password generated", config))
    if a.get("tls") == "own":
        steps.append(Step("Your certificate", certificate))
    if a.get("vault", "none") != "none":
        steps.append(Step(f"Keep the passwords in the key vault ({a['vault']})", vault))
    steps.append(Step("Start EA Explorer", start))
    steps.append(Step("Check that it is healthy", healthy))
    if a.get("move_from") == "backup":
        steps.append(Step("Move the old installation here: restore its backup", restore))
    if _create(a) and a.get("offsite_backups") == "yes":
        steps.append(Step("Copy the backups off the machine every night", offsite))
    steps.append(Step("The address and the first sign-in", done))
    return steps


def _owner_only(path: Path) -> None:
    if not WINDOWS:
        os.chmod(path, 0o600)


def _pubkey(a: dict) -> Path:
    return Path(a["ssh_key"] + ".pub").expanduser()


def _need_cli(ctx: Ctx, name: str, how: str) -> None:
    if ctx.plan:
        return
    if not shutil.which(name):
        raise StepFailed(f"The {name} command is not installed here. {how}")


def _dns_names(a: dict) -> list[str]:
    h = a["hostname"]
    return [h, f"reports.{h}", f"docs.{h}"]


# --- AWS: a key pair, a security group, an EC2 machine with a data disk, an Elastic IP, an S3 bucket, Route 53
def aws_steps(a: dict) -> list[Step]:
    n, region = _suffix(a), a["aws_region"]

    def cli(ctx: Ctx, args: list[str], what: str = "") -> str:
        base = ["aws", "--region", region, "--output", "json"]
        if ctx.answers.get("aws_profile"):
            base += ["--profile", ctx.answers["aws_profile"]]
        return ctx.run([*base, *args], what)

    def creds(ctx: Ctx):
        _need_cli(ctx, "aws", "Install the AWS CLI (https://aws.amazon.com/cli/) and run this again.")
        if ctx.answers.get("aws_access_key_id"):
            ctx.env.update(AWS_ACCESS_KEY_ID=ctx.answers["aws_access_key_id"],
                           AWS_SECRET_ACCESS_KEY=ctx.answers.get("aws_secret_access_key", ""))
            ctx.mask.add(ctx.answers.get("aws_secret_access_key", ""))
        cli(ctx, ["sts", "get-caller-identity"], "who these credentials are")

    def network(ctx: Ctx):
        key = f"{n}-key"
        cli(ctx, ["ec2", "import-key-pair", "--key-name", key, "--public-key-material", f"fileb://{_pubkey(a)}"],
            "your SSH public key")
        sg = jget(cli(ctx, ["ec2", "create-security-group", "--group-name", f"{n}-sg",
                            "--description", "EA Explorer: https, http (redirect), client certificates, SSH"]),
                  "GroupId", default="<security-group-id>")
        ctx.values["sg"] = sg
        for port, cidr in (("443", "0.0.0.0/0"), ("80", "0.0.0.0/0"), ("9443", "0.0.0.0/0"), ("22", a["admin_cidr"])):
            cli(ctx, ["ec2", "authorize-security-group-ingress", "--group-id", sg, "--protocol", "tcp", "--port", port,
                      "--cidr", cidr], f"open {port}")

    def machine(ctx: Ctx):
        image = "resolve:ssm:/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
        disks = json.dumps([{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 40, "VolumeType": "gp3"}},
                            {"DeviceName": "/dev/sdf", "Ebs": {"VolumeSize": int(a["disk_gb"]), "VolumeType": "gp3",
                                                                "DeleteOnTermination": False}}])
        out = cli(ctx, ["ec2", "run-instances", "--image-id", image, "--instance-type", a["aws_instance_type"],
                        "--key-name", f"{n}-key", "--security-group-ids", ctx.get("sg", "<security-group-id>"),
                        "--block-device-mappings", disks, "--metadata-options", "HttpTokens=required",
                        "--tag-specifications", f"ResourceType=instance,Tags=[{{Key=Name,Value={n}}},{{Key=app,Value=eaexplorer}}]"],
                  "an Ubuntu 24.04 machine with a data disk")
        ctx.values["instance"] = jget(out, "Instances", 0, "InstanceId", default="<instance-id>")
        cli(ctx, ["ec2", "wait", "instance-running", "--instance-ids", ctx.get("instance")], "until it runs")
        alloc = jget(cli(ctx, ["ec2", "allocate-address", "--domain", "vpc"], "a fixed public address (Elastic IP)"),
                     "AllocationId", default="<allocation-id>")
        ip = jget(cli(ctx, ["ec2", "describe-addresses", "--allocation-ids", alloc]), "Addresses", 0, "PublicIp", default="<public-ip>")
        cli(ctx, ["ec2", "associate-address", "--instance-id", ctx.get("instance"), "--allocation-id", alloc], "give it the address")
        ctx.values.update(public_ip=ip, ssh_target=f"ubuntu@{ip}", data_device="/dev/nvme1n1")

    def storage(ctx: Ctx):
        bucket = f"{n}-backups-{_secrets.token_hex(3)}"
        args = ["s3api", "create-bucket", "--bucket", bucket]
        if region != "us-east-1":
            args += ["--create-bucket-configuration", f"LocationConstraint={region}"]
        cli(ctx, args, "the bucket for off-site backups")
        cli(ctx, ["s3api", "put-public-access-block", "--bucket", bucket, "--public-access-block-configuration",
                  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"], "never public")
        role = f"{n}-backup-role"
        trust = json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"},
                                                                    "Action": "sts:AssumeRole"}]})
        policy = json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["s3:PutObject", "s3:ListBucket"],
                                                                     "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"]}]})
        cli(ctx, ["iam", "create-role", "--role-name", role, "--assume-role-policy-document", trust], "a role the machine uses")
        cli(ctx, ["iam", "put-role-policy", "--role-name", role, "--policy-name", "eaexplorer-backups", "--policy-document", policy],
            "it may only write to the bucket")
        cli(ctx, ["iam", "create-instance-profile", "--instance-profile-name", role])
        cli(ctx, ["iam", "add-role-to-instance-profile", "--instance-profile-name", role, "--role-name", role])
        time.sleep(0 if ctx.plan else 10)                 # IAM is eventually consistent
        cli(ctx, ["ec2", "associate-iam-instance-profile", "--instance-id", ctx.get("instance"), "--iam-instance-profile", f"Name={role}"])
        ctx.values["offsite_cron"] = (f"30 3 * * * root command -v aws >/dev/null || snap install aws-cli --classic; "
                                      f"aws s3 sync {a['install_dir'].rstrip('/')}/work/backups s3://{bucket}/ --only-show-errors")

    def dns(ctx: Ctx):
        changes = {"Changes": [{"Action": "UPSERT", "ResourceRecordSet": {"Name": name, "Type": "A", "TTL": 300,
                                                                          "ResourceRecords": [{"Value": ctx.get("public_ip")}]}}
                               for name in _dns_names(a)]}
        cli(ctx, ["route53", "change-resource-record-sets", "--hosted-zone-id", a["aws_zone_id"], "--change-batch", json.dumps(changes)],
            "the three DNS names")

    steps = [Step("Check the AWS credentials", creds), Step("Key pair and security group", network),
             Step("The machine, its data disk and a fixed address", machine)]
    if a.get("offsite_backups") == "yes":
        steps.append(Step("An S3 bucket for off-site backups", storage))
    if a.get("aws_zone_id"):
        steps.append(Step("DNS names in Route 53", dns))
    return steps


# --- Azure: a resource group, a VM with a data disk and a DNS label, the ports, a storage account, Azure DNS
def azure_steps(a: dict) -> list[Step]:
    n, group, loc = _suffix(a), a["az_group"], a["az_location"]

    def az(ctx: Ctx, args: list[str], what: str = "") -> str:
        base = ["az", *args, "--output", "json"]
        if ctx.answers.get("az_subscription") and args[0] not in ("account",):
            base += ["--subscription", ctx.answers["az_subscription"]]
        return ctx.run(base, what)

    def creds(ctx: Ctx):
        _need_cli(ctx, "az", "Install the Azure CLI (https://aka.ms/azure-cli), run az login, and run this again.")
        if ctx.answers.get("az_client_id"):
            ctx.mask.add(ctx.answers.get("az_client_secret", ""))
            ctx.run(["az", "login", "--service-principal", "--username", ctx.answers["az_client_id"],
                     "--password", ctx.answers.get("az_client_secret", ""), "--tenant", ctx.answers.get("az_tenant", ""),
                     "--output", "none"], "sign in as the service principal")
        az(ctx, ["account", "show"], "signed in (az login first if this fails)")

    def machine(ctx: Ctx):
        az(ctx, ["group", "create", "--name", group, "--location", loc], "the resource group")
        out = az(ctx, ["vm", "create", "--resource-group", group, "--name", n, "--image", "Ubuntu2404", "--size", a["az_size"],
                       "--admin-username", "eaxadmin", "--ssh-key-values", str(_pubkey(a)), "--public-ip-sku", "Standard",
                       "--public-ip-address-dns-name", n, "--data-disk-sizes-gb", a["disk_gb"], "--assign-identity",
                       "--os-disk-size-gb", "64"], "an Ubuntu 24.04 VM with a data disk")
        ip = jget(out, "publicIpAddress", default="<public-ip>")
        ctx.values.update(public_ip=ip, ssh_target=f"eaxadmin@{ip}", data_device="/dev/disk/azure/scsi1/lun0",
                          principal=jget(out, "identity", "systemAssignedIdentity", default=jget(out, "identity", "principalId", default="<principal-id>")))
        az(ctx, ["vm", "open-port", "--resource-group", group, "--name", n, "--port", "80,443,9443", "--priority", "900"],
           "open https, http (redirect) and client certificates")
        if a["admin_cidr"] != "0.0.0.0/0":
            az(ctx, ["network", "nsg", "rule", "update", "--resource-group", group, "--nsg-name", f"{n}NSG",
                     "--name", "default-allow-ssh", "--source-address-prefixes", a["admin_cidr"]], "SSH only from your address")

    def storage(ctx: Ctx):
        account = re.sub(r"[^a-z0-9]", "", f"{n}bk{_secrets.token_hex(3)}")[:24]
        out = az(ctx, ["storage", "account", "create", "--name", account, "--resource-group", group, "--location", loc,
                       "--sku", "Standard_ZRS", "--min-tls-version", "TLS1_2", "--allow-blob-public-access", "false"],
                 "a storage account for off-site backups")
        scope = jget(out, "id", default="<storage-account-id>")
        az(ctx, ["storage", "container", "create", "--account-name", account, "--name", "backups", "--auth-mode", "login"])
        az(ctx, ["role", "assignment", "create", "--assignee", ctx.get("principal", "<principal-id>"),
                 "--role", "Storage Blob Data Contributor", "--scope", scope], "the VM may write there")
        ctx.values["offsite_cron"] = (f"30 3 * * * root command -v azcopy >/dev/null || (curl -fsSL https://aka.ms/downloadazcopy-v10-linux "
                                      f"| tar -xz -C /tmp && cp /tmp/azcopy_linux_amd64_*/azcopy /usr/local/bin/); "
                                      f"azcopy login --identity && azcopy sync {a['install_dir'].rstrip('/')}/work/backups "
                                      f"https://{account}.blob.core.windows.net/backups --recursive")

    def dns(ctx: Ctx):
        zone, _, zgroup = a["az_dns_zone"].partition("/")
        for name in _dns_names(a):
            rel = name.removesuffix("." + zone) if name.endswith("." + zone) else name
            az(ctx, ["network", "dns", "record-set", "a", "add-record", "--resource-group", zgroup or group, "--zone-name", zone,
                     "--record-set-name", rel, "--ipv4-address", ctx.get("public_ip")], f"{name}")

    steps = [Step("Check the Azure sign-in", creds), Step("The resource group, the VM, its data disk and ports", machine)]
    if a.get("offsite_backups") == "yes":
        steps.append(Step("A storage account for off-site backups", storage))
    if a.get("az_dns_zone"):
        steps.append(Step("DNS names in Azure DNS", dns))
    return steps


# --- DigitalOcean: an SSH key, a Droplet, a volume, a cloud firewall, a Spaces bucket, DNS, a load balancer
def do_steps(a: dict) -> list[Step]:
    n, region = _suffix(a), a["do_region"]

    def doctl(ctx: Ctx, args: list[str], what: str = "") -> str:
        return ctx.run(["doctl", *args, "--output", "json"], what)

    def creds(ctx: Ctx):
        _need_cli(ctx, "doctl", "Install doctl (https://docs.digitalocean.com/reference/doctl/how-to/install/) and run this again.")
        if ctx.answers.get("do_token"):
            ctx.env["DIGITALOCEAN_ACCESS_TOKEN"] = ctx.answers["do_token"]
            ctx.mask.add(ctx.answers["do_token"])
        doctl(ctx, ["account", "get"], "the account")

    def machine(ctx: Ctx):
        key = jget(doctl(ctx, ["compute", "ssh-key", "import", f"{n}-key", "--public-key-file", str(_pubkey(a))], "your SSH public key"),
                   0, "fingerprint", default="<key-fingerprint>")
        out = doctl(ctx, ["compute", "droplet", "create", n, "--image", "ubuntu-24-04-x64", "--size", a["do_size"],
                          "--region", region, "--ssh-keys", key, "--tag-names", "eaexplorer", "--enable-monitoring", "--wait"],
                    "an Ubuntu 24.04 Droplet")
        droplet = jget(out, 0, "id", default="<droplet-id>")
        ip = "<public-ip>"
        try:
            ip = next(x["ip_address"] for x in json.loads(out)[0]["networks"]["v4"] if x["type"] == "public")
        except (ValueError, KeyError, IndexError, StopIteration, TypeError):
            pass
        ctx.values.update(droplet=droplet, public_ip=ip, ssh_target=f"root@{ip}")
        vol = jget(doctl(ctx, ["compute", "volume", "create", f"{n}-data", "--region", region, "--size", f"{a['disk_gb']}GiB",
                               "--fs-type", "ext4"], "the data volume"), 0, "id", default="<volume-id>")
        doctl(ctx, ["compute", "volume-action", "attach", vol, droplet, "--wait"], "attach it")
        ctx.values["data_device"] = f"/dev/disk/by-id/scsi-0DO_Volume_{n}-data"
        rules = (f"protocol:tcp,ports:22,address:{a['admin_cidr']} protocol:tcp,ports:443,address:0.0.0.0/0,address:::/0 "
                 "protocol:tcp,ports:80,address:0.0.0.0/0,address:::/0 protocol:tcp,ports:9443,address:0.0.0.0/0,address:::/0")
        doctl(ctx, ["compute", "firewall", "create", "--name", f"{n}-fw", "--droplet-ids", droplet, "--inbound-rules", rules,
                    "--outbound-rules", "protocol:tcp,ports:all,address:0.0.0.0/0,address:::/0 protocol:udp,ports:all,address:0.0.0.0/0,address:::/0"],
              "the cloud firewall")

    def storage(ctx: Ctx):
        bucket = f"{n}-backups-{_secrets.token_hex(3)}"
        endpoint = f"https://{region}.digitaloceanspaces.com"
        ctx.mask.add(a.get("spaces_secret", ""))
        env = {"AWS_ACCESS_KEY_ID": a["spaces_key"], "AWS_SECRET_ACCESS_KEY": a.get("spaces_secret", "")}
        old = dict(ctx.env)
        ctx.env.update(env)
        try:
            _need_cli(ctx, "aws", "Spaces buckets are made with the AWS CLI (S3-compatible): install it and run this again.")
            ctx.run(["aws", "s3api", "create-bucket", "--bucket", bucket, "--endpoint-url", endpoint, "--region", "us-east-1"],
                    "a Spaces bucket for off-site backups (S3-compatible)")
        finally:
            ctx.env = old
        creds_file = "/etc/eaexplorer/spaces.env"     # put on the Droplet later (_spaces_key_step), once it is reachable
        ctx.values["spaces_env"] = (creds_file, a["spaces_key"], a.get("spaces_secret", ""))
        ctx.values["offsite_cron"] = (f"30 3 * * * root command -v aws >/dev/null || snap install aws-cli --classic; "
                                      f"set -a; . {creds_file}; aws s3 sync {a['install_dir'].rstrip('/')}/work/backups "
                                      f"s3://{bucket}/ --endpoint-url {endpoint} --only-show-errors")

    def dns(ctx: Ctx):
        dom = a["do_domain"]
        for name in _dns_names(a):
            rel = name.removesuffix("." + dom) if name.endswith("." + dom) else "@" if name == dom else name
            doctl(ctx, ["compute", "domain", "records", "create", dom, "--record-type", "A", "--record-name", rel,
                        "--record-data", ctx.get("public_ip"), "--record-ttl", "300"], name)

    def balancer(ctx: Ctx):
        doctl(ctx, ["compute", "load-balancer", "create", "--name", f"{n}-lb", "--region", region, "--droplet-ids", ctx.get("droplet"),
                    "--forwarding-rules", ("entry_protocol:tcp,entry_port:443,target_protocol:tcp,target_port:443 "
                                           "entry_protocol:tcp,entry_port:80,target_protocol:tcp,target_port:80"),
                    "--health-check", "protocol:tcp,port:443"], "https passed through to the Droplet")

    steps = [Step("Check the DigitalOcean token", creds), Step("The Droplet, its volume and the cloud firewall", machine)]
    if a.get("offsite_backups") == "yes" and a.get("spaces_key"):
        steps.append(Step("A Spaces bucket for off-site backups", storage))
    if a.get("do_domain"):
        steps.append(Step("DNS names in DigitalOcean", dns))
    if a.get("do_load_balancer") == "yes":
        steps.append(Step("A load balancer", balancer))
    return steps


def _spaces_key_step(a: dict) -> Step:
    def put(ctx: Ctx):
        f, key, secret = ctx.values.get("spaces_env", ("/etc/eaexplorer/spaces.env", "<key>", "<secret>"))
        ctx.mask.add(secret)
        ctx.remote(f"sudo mkdir -p /etc/eaexplorer && sudo install -m 600 /dev/stdin {f}", "the Spaces key on the Droplet (root only)",
                   input_text=f"AWS_ACCESS_KEY_ID={key}\nAWS_SECRET_ACCESS_KEY={secret}\n")
    return Step("The Spaces key on the Droplet, for the nightly copy", put)


def all_steps(a: dict) -> list[Step]:
    steps = steps_for(a)
    if a.get("kind") == "digitalocean" and _create(a) and a.get("offsite_backups") == "yes" and a.get("spaces_key"):
        i = next(i for i, s in enumerate(steps) if s.title.startswith("Copy the backups"))
        steps.insert(i, _spaces_key_step(a))
    return steps


# ---------------------------------------------------------------- running a whole deployment
RESULT_KEYS = ("public_ip", "ssh_target", "instance", "droplet", "folder")


def run(answers: dict, plan: bool, on_fail: Callable[[Step, str], str], out: Callable[[str], None] = print,
        progress: Callable[[int, int, str, str], None] | None = None, result: dict | None = None,
        reveal: bool = True) -> str:
    """Every step in order. on_fail(step, why) answers retry, back or quit. Returns done, back or quit.
    result (when given) gets what the steps found out that may be shown (an address, a machine's ID), never secrets."""
    a = complete(answers)
    ctx = Ctx(a, plan=plan, out=out, reveal=reveal)
    if result is not None:
        result["_ctx"] = ctx
    ctx.mask.update(str(a.get(k, "")) for k in SECRET_KEYS)
    steps = all_steps(a)
    out(f"{'The plan' if plan else 'Deploying'}: {KINDS[a['kind']]} ({len(steps)} steps)")
    i = 0
    while i < len(steps):
        step = steps[i]
        out("")
        out(f"[{i + 1}/{len(steps)}] {step.title}")
        log_only(f"--- step {i + 1}: {step.title}  {datetime.now().astimezone().isoformat()}")
        if progress:
            progress(i, len(steps), step.title, "running")
        try:
            step.fn(ctx)
        except (StepFailed, Failure, OSError, subprocess.SubprocessError) as exc:
            why = ctx.hide(str(exc))
            log_only(f"FAILED: {why}")
            if progress:
                progress(i, len(steps), step.title, "failed")
            choice = "quit" if plan else on_fail(step, why)
            if choice == "retry":
                continue
            return choice
        if progress:
            progress(i, len(steps), step.title, "done")
        i += 1
    if result is not None:
        result.pop("_ctx", None)
        result.update({k: v for k, v in ctx.values.items() if k in RESULT_KEYS and v})
    if a.get("keep_credentials") == "yes" and not plan and reveal:
        keep_credentials(a)
    out("")
    out("The plan above runs nothing; without --plan it is carried out." if plan else "Done.")
    return "done"


def keep_credentials(a: dict) -> None:
    """Only when asked (D506): the cloud credentials, for the next run, readable by this user only."""
    keys = ("aws_access_key_id", "aws_secret_access_key", "do_token", "spaces_key", "spaces_secret", "az_client_id",
            "az_client_secret", "az_tenant")
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text("".join(f"{k}={a[k]}\n" for k in keys if a.get(k)), encoding="utf-8", newline="\n")
    _owner_only(CREDENTIALS_FILE)
    say(f"The cloud credentials are kept in {CREDENTIALS_FILE} (readable by you only); delete it to forget them.")


def kept_credentials() -> dict:
    out = {}
    try:
        for line in CREDENTIALS_FILE.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k and v:
                out[k] = v
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- the console wizard
def ask(q: Question, answers: dict) -> str:
    default = q.default_for(answers)
    if q.help:
        print(f"  ({q.help})")
    if q.choices:
        keys = list(q.choices)
        for i, (k, label) in enumerate(q.choices.items(), 1):
            print(f"  {i}  {label}{'   [default]' if k == default else ''}")
        while True:
            raw = input(f"{q.text} [{keys.index(default) + 1 if default in keys else ''}]: ").strip()
            if not raw and default in keys:
                return default
            if raw.isdigit() and 1 <= int(raw) <= len(keys):
                return keys[int(raw) - 1]
            if raw in keys:
                return raw
            print("  Choose one of the numbers.")
    if q.secret:
        import getpass
        return getpass.getpass(f"{q.text}: ").strip()
    while True:
        raw = input(f"{q.text}{f' [{default}]' if default else ''}: ").strip()
        value = raw or default
        if value or not q.required:
            return value
        print("  This one is needed.")


def console(answers: dict, plan: bool, yes: bool) -> int:
    say("")
    say("EA Explorer deployment (eax deploy, D498). Enter keeps the [default]; Ctrl+C stops.", "cyan")
    answers = {**kept_credentials(), **answers}
    while True:
        for q in visible(answers):
            if q.key in answers and answers[q.key] not in (None, ""):
                continue
            answers[q.key] = ask(q, answers)
        try:
            a = complete(answers)
        except Failure as exc:
            say(str(exc), "red")
            for line in str(exc).splitlines()[1:]:
                answers.pop(line.strip().split(":")[0], None)
            continue
        say("")
        say("Your answers:", "cyan")
        for q in visible(a):
            v = a.get(q.key, "")
            say(f"  {q.key:<20} {'********' if q.secret and v else v}")
        if not yes:
            choice = input("Go ahead? (y = yes, p = show the plan first, c = change an answer, q = quit) [y]: ").strip().lower() or "y"
            if choice == "q":
                say("Nothing was changed.")
                return 0
            if choice == "c":
                key = input("Which one (its name above)? ").strip()
                if key in BY_KEY:
                    answers.pop(key, None)
                continue
            if choice == "p":
                run(a, True, lambda s, w: "quit")
                if input("Carry it out now? [y/N]: ").strip().lower() != "y":
                    continue
        if plan:
            run(a, True, lambda s, w: "quit")
            return 0

        def on_fail(step: Step, why: str) -> str:
            say(f"This step failed: {step.title}", "red")
            say(f"  {why}", "red")
            while True:
                c = input("r = retry, b = back to the answers, q = quit [r]: ").strip().lower() or "r"
                if c in ("r", "b", "q"):
                    return {"r": "retry", "b": "back", "q": "quit"}[c]
        result = run(a, False, on_fail, out=say)
        if result == "back":
            answers = dict(a)
            yes = False
            continue
        return 0 if result == "done" else 1


# ---------------------------------------------------------------- the command
def parse(options: list[str]) -> tuple[str, dict, bool, bool]:
    mode, answers, plan, yes = "", {}, False, False
    it = iter(options)
    for o in it:
        if o in ("--console", "--web"):
            mode = o[2:]
        elif o == "--plan":
            plan = True
        elif o in ("--yes", "-y"):
            yes = True
        elif o == "--kind":
            answers["kind"] = next(it, "")
        elif o == "--answers":
            path = Path(next(it, ""))
            try:
                answers.update({k: str(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()})
            except (OSError, ValueError) as exc:
                raise Failure(f"Could not read the answers file {path}: {exc}") from exc
        elif o == "--set":
            k, _, v = next(it, "").partition("=")
            if k not in BY_KEY:
                raise Failure(f"--set {k}: no such answer. The answers: {', '.join(BY_KEY)}")
            answers[k] = v
        elif o.startswith("--") and o[2:].replace("-", "_") in BY_KEY:
            answers[o[2:].replace("-", "_")] = next(it, "")
        else:
            raise Failure(f"Unknown option {o}. Run {EAX} help deploy")
    if answers.get("kind") and answers["kind"] not in KINDS:
        raise Failure(f"--kind is one of {', '.join(KINDS)}")
    return mode, answers, plan, yes


def main(options: list[str]) -> int:
    from .core import start_log, stop_log
    mode, answers, plan, yes = parse(options)
    if not mode:
        if yes or plan:
            mode = "console"
        else:
            raw = input("Deploy (1) here in the console, or (2) in a web page in your browser? [1/2] ").strip()
            mode = "web" if raw in ("2", "w", "web") else "console"
    start_log("deploy", [o for o in options if not any(s in o for s in ("token", "secret"))])
    try:
        if mode == "web":
            from . import deploy_web
            return deploy_web.serve(answers, plan)
        if yes:
            a = complete({**kept_credentials(), **answers})
            result = run(a, plan, lambda s, w: "quit", out=say)
            return 0 if result == "done" else 1
        return console(answers, plan, yes)
    except (Failure, KeyboardInterrupt) as exc:
        say(f"ERROR: {exc}" if isinstance(exc, Failure) else "Stopped.", "red")
        return 1
    finally:
        stop_log()
