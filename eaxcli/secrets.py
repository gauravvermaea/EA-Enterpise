"""Passwords from a key vault (phase 36, D504).

The passwords and keys of an installation (every value the server template holds as change-me) can be kept in a
key vault as well as in work/eaexplorer.env:
  file:<path>      a file outside the installation (e.g. /etc/eaexplorer/secrets.env), readable by its owner only;
                   on DigitalOcean the same, on the Droplet
  aws:<name>       AWS Secrets Manager: one secret holding them all as JSON
  azure:<vault>    Azure Key Vault: one secret per value (EAX_DB_PASSWORD -> eax-db-password)
The config file says where (EAX_SECRETS_FROM). Docker Compose still reads the values from the config file when it
starts, so the vault is the copy to keep and to restore from:
  eax secrets              where they are kept, and which values
  eax secrets push [--to provider:name]   the config file's values into the vault (eax deploy does this once)
  eax secrets pull [--from provider:name] the vault's values into the config file (a dated copy of it first,
                                          in work/config-history), e.g. after rebuilding a server or rotating a password
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .core import EAX, ENV_FILE, ENV_REL, WORK, Failure, say

PROVIDERS = ("file", "aws", "azure", "digitalocean")


def kv_name(key: str) -> str:
    """Azure Key Vault names allow letters, digits and dashes."""
    return key.lower().replace("_", "-")


def env_lines(values: dict[str, str]) -> str:
    return "".join(f"{k}={v}\n" for k, v in sorted(values.items()))


def push_commands(provider: str, name: str, values: dict[str, str], answers: dict | None = None) -> list[tuple]:
    """What eax deploy runs to keep the values in the vault: ("remote", script, what, stdin) on the server,
    ("local", argv, what[, ok codes]) here, ("file", path, body) a temporary file here, ("delete", path)."""
    answers = answers or {}
    body = env_lines(values)
    if provider in ("file", "digitalocean"):
        folder = str(Path(name).parent).replace("\\", "/")
        return [("remote", f"sudo mkdir -p {shlex.quote(folder)} && sudo install -m 600 /dev/stdin {shlex.quote(name)}",
                 f"the passwords into {name}, readable by root only", body)]
    tmp = str(WORK / "deploy" / "vault.json")
    if provider == "aws":
        region = ["--region", answers["aws_region"]] if answers.get("aws_region") else []
        profile = ["--profile", answers["aws_profile"]] if answers.get("aws_profile") else []
        return [("file", tmp, json.dumps(values, indent=1)),
                ("local", ["aws", *region, *profile, "secretsmanager", "create-secret", "--name", name,
                           "--description", "EA Explorer passwords (eax secrets)", "--secret-string", f"file://{tmp}"],
                 f"the passwords as one secret, {name}", [0, 254, 255]),
                ("local", ["aws", *region, *profile, "secretsmanager", "put-secret-value", "--secret-id", name,
                           "--secret-string", f"file://{tmp}"], "its value (when it existed already)"),
                ("delete", tmp)]
    if provider == "azure":
        out: list[tuple] = []
        if answers.get("az_group") and answers.get("az_location"):
            out.append(("local", ["az", "keyvault", "create", "--name", name, "--resource-group", answers["az_group"],
                                  "--location", answers["az_location"], "--enable-rbac-authorization", "false"],
                        f"the Key Vault {name} (kept if it exists)", [0, 1]))
        for key, value in sorted(values.items()):
            out.append(("file", tmp, value))
            out.append(("local", ["az", "keyvault", "secret", "set", "--vault-name", name, "--name", kv_name(key),
                                  "--file", tmp, "--output", "none"], key))
        out.append(("delete", tmp))
        return out
    raise Failure(f"Unknown key vault {provider!r}: one of {', '.join(PROVIDERS)}")


def _cli(argv: list[str]) -> str:
    exe = shutil.which(argv[0])
    if not exe:
        raise Failure(f"The {argv[0]} command is not installed here.")
    p = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise Failure(f"{argv[0]} failed: {(p.stderr or p.stdout).strip()[-500:]}")
    return p.stdout


def fetch(provider: str, name: str, keys: list[str]) -> dict[str, str]:
    """The values kept in the vault (only the keys asked for)."""
    if provider in ("file", "digitalocean"):
        try:
            text = Path(name).read_text(encoding="utf-8")
        except OSError as exc:
            raise Failure(f"Could not read {name}: {exc} (it is readable by root only: sudo {EAX} secrets pull)") from exc
        out = {}
        for line in text.splitlines():
            k, _, v = line.partition("=")
            if k in keys:
                out[k] = v
        return out
    if provider == "aws":
        data = json.loads(_cli(["aws", "secretsmanager", "get-secret-value", "--secret-id", name,
                                "--query", "SecretString", "--output", "text"]))
        return {k: str(v) for k, v in data.items() if k in keys}
    if provider == "azure":
        out = {}
        for key in keys:
            try:
                out[key] = _cli(["az", "keyvault", "secret", "show", "--vault-name", name, "--name", kv_name(key),
                                 "--query", "value", "--output", "tsv"]).strip()
            except Failure:
                pass
        return out
    raise Failure(f"Unknown key vault {provider!r}: one of {', '.join(PROVIDERS)}")


def where(env_text: str) -> tuple[str, str]:
    m = re.search(r"^EAX_SECRETS_FROM=['\"]?([a-z]+):([^'\"\n]+)", env_text, re.MULTILINE)
    return (m.group(1), m.group(2).strip()) if m else ("", "")


def replace_values(env_text: str, values: dict[str, str]) -> tuple[str, list[str]]:
    changed = []

    def sub(m: re.Match) -> str:
        k, v = m.group(1), m.group(2)
        if k in values and values[k] != v.strip("'\""):
            changed.append(k)
            return f"{k}={values[k]}"
        return m.group(0)
    return re.sub(r"^([A-Z0-9_]+)=(.*)$", sub, env_text, flags=re.MULTILINE), changed


def main(options: list[str]) -> int:
    from .deploy import secret_values
    if not ENV_FILE.exists():
        raise Failure(f"No {ENV_REL} yet: run {EAX} init or {EAX} deploy first.")
    text = ENV_FILE.read_text(encoding="utf-8")
    values = secret_values(text)
    action = options[0] if options else "show"
    rest = options[1:]
    target = ""
    for flag in ("--to", "--from"):
        if flag in rest and rest.index(flag) + 1 < len(rest):
            target = rest[rest.index(flag) + 1]
    provider, name = (target.split(":", 1) + [""])[:2] if target else where(text)
    if action == "show":
        if provider:
            say(f"The passwords are kept in: {provider}:{name} (EAX_SECRETS_FROM in {ENV_REL})")
        else:
            say(f"No key vault is set: the passwords are only in {ENV_REL}. {EAX} secrets push --to file:/etc/eaexplorer/secrets.env "
                "(or aws:<secret name>, azure:<vault name>) keeps them in one.")
        say(f"{len(values)} passwords and keys: {', '.join(sorted(values))}")
        return 0
    if not provider:
        raise Failure(f"Where? --to (or --from) file:<path>, aws:<secret name> or azure:<vault name>, or set EAX_SECRETS_FROM in {ENV_REL}.")
    if provider not in PROVIDERS:
        raise Failure(f"Unknown key vault {provider!r}: one of {', '.join(PROVIDERS)}")
    if action == "push":
        for step in push_commands(provider, name, values):
            kind = step[0]
            if kind == "remote":         # on this machine (eax secrets runs on the installation itself)
                Path(name).parent.mkdir(parents=True, exist_ok=True)
                Path(name).write_text(step[3], encoding="utf-8")
                Path(name).chmod(0o600)
            elif kind == "file":
                Path(step[1]).parent.mkdir(parents=True, exist_ok=True)
                Path(step[1]).write_text(step[2], encoding="utf-8")
                Path(step[1]).chmod(0o600)
            elif kind == "delete":
                Path(step[1]).unlink(missing_ok=True)
            else:
                ok = step[3] if len(step) > 3 else [0]
                exe = shutil.which(step[1][0])
                if not exe:
                    raise Failure(f"The {step[1][0]} command is not installed here.")
                code = subprocess.run([exe, *step[1][1:]], capture_output=True, text=True, check=False).returncode
                if code not in ok:
                    raise Failure(f"{step[1][0]} failed (exit {code}) while keeping {step[2]}")
        if not where(text)[0]:
            ENV_FILE.write_text(text.rstrip("\n") + f"\nEAX_SECRETS_FROM={provider}:{name}\n", encoding="utf-8", newline="\n")
        say(f"{len(values)} passwords and keys kept in {provider}:{name}.")
        return 0
    if action == "pull":
        got = fetch(provider, name, list(values))
        if not got:
            raise Failure(f"Nothing found in {provider}:{name}.")
        new, changed = replace_values(text, got)
        if not changed:
            say(f"{ENV_REL} already holds the vault's values ({len(got)} checked).")
            return 0
        history = WORK / "config-history"
        history.mkdir(parents=True, exist_ok=True)
        copy = history / f"eaexplorer.env.{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}"
        copy.write_text(text, encoding="utf-8", newline="\n")
        ENV_FILE.write_text(new, encoding="utf-8", newline="\n")
        say(f"{len(changed)} values taken from {provider}:{name} into {ENV_REL} (the old file: {copy}): {', '.join(changed)}")
        say(f"Restart to use them: {EAX} restart. A database password changed here must match the database's own login.")
        return 0
    raise Failure(f"{EAX} secrets [show|push|pull] [--to|--from provider:name]")
