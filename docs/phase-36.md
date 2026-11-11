# Phase 36 — Deployment (as built, 10 Nov 2026)

Status: **built, to be accepted** (the last set, D421; version 0.19.0, migration 0043, which only records the version).
Decisions D500 to D506, building on D372, D416, D457 and D498. The updates part of phase 36 is
[phase-36-updates.md](phase-36-updates.md) (D417, D510 onwards). How to use it: [deployment.md](deployment.md).

## What was built
- **`eax deploy`** (D498, D500): one Python program for every eax form (eax.ps1 and eax.sh hand it to eaxpy).
  - It asks **console or web page** first; `--console` and `--web` skip that.
  - The questions are shown only when they apply. The same steps run in both forms.
  - Five kinds: **laptop**; **server** (this one, or over SSH; Docker installed if missing); **AWS**, **Azure**
    and **DigitalOcean**, each creating the machine or using an existing one.
  - `--plan` prints every command and runs nothing. `--answers file.json`, `--set key=value` and `--yes` run it
    without questions.
  - Files: `eaxcli/deploy.py` (questions, the config, the steps of each kind, running them),
    `eaxcli/deploy_web.py` and `eaxcli/deploy.html` (the local page).
- **The cloud steps** (D501), with each cloud's own CLI:
  - a machine with a separate data disk;
  - a firewall and a fixed address;
  - off-site backup storage, written by the machine's own role or identity (or a Spaces key on the Droplet), with a
    nightly copy of work/backups;
  - DNS names;
  - a DigitalOcean load balancer.
- **The installer** (D502): `eax-deploy.ps1` with `eax-deploy.cmd` for Windows, and `eax-deploy.sh`.
  - It asks for the repository link and the channel, lists the versions, and downloads the release archive (or a
    shallow clone when git is there).
  - It checks the download, writes `work/install.json` and runs `eax deploy`.
- **Directory groups mapped to roles** (D503):
  - The realm's sign-in clients send a `groups` claim.
  - `permissions.group_keys` turns it into `group:<name>` keys, which map through core.role_mappings like Keycloak
    roles.
  - The role mapping screen offers "Directory group" beside "Keycloak role".
- **Passwords from a key vault** (D504):
  - `eaxcli/secrets.py` and `eax secrets` (show, push, pull), for a file, AWS Secrets Manager or Azure Key Vault.
  - The wizard can push the generated passwords once.
- **Moving an installation** (D505): restore an infrastructure backup of the old installation onto the new one,
  databases then files; the config file stays the new one's.
- **Safe running** (D506): masked logs, Retry/Back/Quit, credentials kept only on request, and an existing server
  config never replaced.

## Deploy from the application (D555 to D557)
- **System admin › Deploy:** `services/web/src/Deploy.jsx`, the API `/api/v1/deploys` (system.operate), and the
  history in core.deployments (migration 0043).
- **The operations helper:** `services/ops/deploys.py` and `eaxcli/deploy_runner.py`.
- **The deployer image:** `deploy/deployer/Dockerfile`.
- **Not offered there:** the laptop, and "this machine is the server". Fleets are R2.
- **Tests:** `test_deploy_page.py`. The self-test's smoke run checks the Deploy questions and refuses others.

## Tests
- `services/api/tests/test_deploy.py`:
  - the questions and the server config;
  - where releases come from;
  - every kind's plan, checking that no command runs and no secret shows;
  - moving and the vault in the plan;
  - a failing step answered retry, back or quit;
  - the vault's commands;
  - directory groups;
  - the realm mapper;
  - the installer (bash: against a fake archive, and a local git repository with tags; PowerShell when EAX_PWSH is
    set);
  - the web wizard's key and its plan.
- `test_eax_help.py` checks that `deploy` and `secrets` are in the help and accepted by every form.

## Only on real machines
These could not be run here, only planned:
- creating machines in AWS, Azure and DigitalOcean;
- installing Docker on a real server;
- the first start on a server;
- the nightly off-site copies;
- signing in with an Active Directory or Entra ID group.

Run `eax deploy --plan` first to see every command.
