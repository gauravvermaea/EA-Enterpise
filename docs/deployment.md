# Deploying EA Explorer

EA Explorer runs as one Docker stack. There are five deployment kinds (D416, D457), and each can be done **guided**
or from the **command line**:

| Kind | Where it runs | What `eax deploy` does |
|---|---|---|
| **laptop** | this computer, with Docker Desktop | makes the config file if there is none, starts, checks, shows the logins |
| **server** | a Linux server you have: this one, or another reached over SSH | installs Docker if missing, downloads the release, makes the config (every password generated), starts, checks |
| **aws** | an EC2 machine | creates it (or uses one you have), then as server |
| **azure** | an Azure VM | creates it (or uses one you have), then as server |
| **digitalocean** | a Droplet | creates it (or uses one you have), then as server |

Updating an installation to a newer release is a separate story: [phase-36-updates.md](phase-36-updates.md).

## 1. Get EA Explorer (no repository needed)

You don't need a copy of the repository. The **installer** is one small file. It asks for the **repository link**
and the **channel** (Prod: released versions; RC: release candidates; Latest: the newest commit of main), lists the
versions, downloads the one you choose, checks it, and runs the deployment wizard.

- It downloads the release archive with no git needed. If git is installed, it uses a shallow clone instead.
- It writes `work/install.json` (where this copy came from), which the wizard and updates read.

**Windows** (PowerShell):

```powershell
iwr https://raw.githubusercontent.com/<owner>/<repo>/release/eax-deploy.ps1 -OutFile eax-deploy.ps1
.\eax-deploy.cmd            # or: powershell -NoProfile -ExecutionPolicy Bypass -File .\eax-deploy.ps1
```

**Linux and macOS**:

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/release/eax-deploy.sh -o eax-deploy.sh && bash eax-deploy.sh
```

**Options** (each is asked when not given):

| Windows | Linux and macOS | What it sets |
|---|---|---|
| `-Repo` | `--repo` | the repository link |
| `-Channel prod\|rc\|latest` | `--channel prod\|rc\|latest` | the channel |
| `-Version v0.19.0` | `--version v0.19.0` | a tag, branch or commit |
| `-Folder` | `--folder` | where to put it (default: `eaexplorer` in your home folder) |
| `-NoDeploy` | `--no-deploy` | download only |
| `-WizardArgs "--web"` | `-- --web` | passed to the wizard |

GitHub and GitLab addresses download without git. For any other host, git is needed, or set `EAX_ARCHIVE_URL`
(e.g. `https://host/{repo}/{ref}.tar.gz`).

If you already have a copy, skip the installer and run `.\eax deploy` (Windows) or `./eax.sh deploy` there.

## 2. The wizard: `eax deploy`

`eax deploy` first asks: **continue in the console, or in a web page?** `--console` and `--web` skip the question.

- **Web:** a small page served by eax itself on this computer (`127.0.0.1`, a free port, a random key in the
  address), before EA Explorer is up.
- **Console:** the same questions and steps, in the terminal.
- **Commands, Console and History tabs (web page, D554):** after the wizard, the page also runs any eax command with a
  guided form, takes eax commands as typed in a Console (and `console` for its numbered menu), and lists every run.
  They run on this machine through eaxcli, or, once the wizard has set up a server over SSH, on that server in its
  installation folder over the same SSH connection. Only eax commands run; the delete-everything commands need the
  installation's name, "I understand" and a backup first, as in EA Explorer's Command centre. Every run is in
  `work/commands` and `work/logs`.

Both forms behave the same way:
- **Questions:** only the ones that apply are asked, each with a sensible default.
- **Before running:** **Show the plan** (or `--plan`) lists every step and every command it would run, and runs
  nothing.
- **Logging:** every step is logged to `work/logs/eax-<time>-deploy.log`, with passwords masked.
- **When a step fails:** it stops and asks **Retry**, **Back** (to the answers, which are kept) or **Quit**.
- **Cloud credentials:** used for this run only. Asked to keep them, the wizard writes them to
  `work/deploy-credentials.env`, readable by you only; delete that file to forget them.

**Command-line examples** (all four eax forms, D331):

```
eax deploy                                    # asks console or web, then everything
eax deploy --web
eax deploy --console --kind laptop
eax deploy --console --kind aws --plan        # what it would create, nothing run
eax deploy --console --kind server --set where=ssh --set ssh_target=ubuntu@203.0.113.10 --set hostname=ea.acme.example
eax deploy --console --answers deploy.json --yes   # no questions: every answer from the file or its default
```

The answers' names are listed by the wizard before it starts (e.g. `kind`, `where`, `cloud_mode`, `hostname`,
`ssh_target`, `ssh_key`, `aws_region`, `az_location`, `do_region`, `disk_gb`, `admin_cidr`, `tls`, `vault`,
`move_from`, `backup_dir`).

### 2.1 Laptop
1. The wizard checks that Docker Desktop is running.
2. It makes `work/eaexplorer.env` from the laptop template, if there is none.
3. It starts EA Explorer (`eax up`) and waits until `https://localhost/api/health` answers.
4. It shows the address and the logins. Run `eax trust` once so the browser stops warning.

### 2.2 Server
A Linux server with 16 GB of memory or more; Ubuntu 22.04 or 24.04 is tested by its users. Two ways:

- **On the server itself:** copy EA Explorer there (the installer), then `./eax.sh deploy` and choose *This machine
  is the server*.
- **From your laptop over SSH:** choose *Another server, reached over SSH*. Give `user@address`, the SSH key, and the
  repository link and version: the server downloads the release itself. The user must be allowed to use `sudo`.

The steps:
1. Reach the server.
2. Install **Docker and Docker Compose if missing** (from get.docker.com).
3. Make the data folder (default `/srv/eax`).
4. Download the release (default `/opt/eaexplorer`).
5. Make the **config file**: your address, every `change-me` password generated (letters and digits, 28 to 40
   characters), the data folders, and your certificate or a self-signed one. It is readable by its owner only.
   - An existing config file on the server is kept as it is, because its passwords match its databases.
6. Start EA Explorer (`sudo ./eax.sh up`; the first start builds the images, 10 to 20 minutes).
7. Wait until it answers.
8. Show the address and the first sign-in: user `eaadmin` with the generated `EAX_FIRST_ADMIN_PASSWORD`, shown once
   on screen and never logged. Keycloak asks for a new one at the first sign-in.

**DNS:** point three names at the server: `<address>`, `reports.<address>` and `docs.<address>`.

### 2.3 AWS
Needs the **AWS CLI** on this computer, with a profile, or an access key typed in the wizard (used for this run only).
**Creating** makes:

| What | How |
|---|---|
| Your SSH public key | as a key pair |
| Security group | 443, 80 (redirects to https) and 9443 (client certificates, D366) from anywhere; 22 from your address range |
| Machine | Ubuntu 24.04 (default `t3.xlarge`, 16 GB) with a 40 GB system disk and a separate **gp3 data disk** (default 100 GB, kept if the machine is deleted), formatted once and mounted at `/srv/eax` |
| Fixed address | an Elastic IP |
| Off-site backups | when chosen: an **S3 bucket**, never public, and a role that lets the machine only write to it; a nightly job (03:30) copies `work/backups` there |
| DNS | when a Route 53 hosted zone is given: the three names |

It then continues as a server over SSH (user `ubuntu`). **Existing machine:** give `user@address` and it continues
as a server.

### 2.4 Azure
Needs the **Azure CLI** (`az login` first). **Creating** makes:

| What | How |
|---|---|
| Resource group | in your region (default `southafricanorth`) |
| VM | Ubuntu 24.04 (default `Standard_D4s_v5`) with a **data disk** and a public address with a DNS label (`<name>.<region>.cloudapp.azure.com`) |
| Ports | 80, 443 and 9443 open; SSH limited to your address range when you give one |
| Off-site backups | when chosen: a **storage account** with a `backups` container, written by the VM's own identity (Storage Blob Data Contributor); a nightly `azcopy sync` |
| DNS | when an Azure DNS zone is given (`zone/resource-group`): the three names |

It then continues as a server over SSH (user `eaxadmin`).

### 2.5 DigitalOcean
Needs **doctl**, with an API token: typed in the wizard, or doctl's current context. **Creating** makes:

| What | How |
|---|---|
| Your SSH key | imported |
| Droplet | Ubuntu 24.04 (default `s-8vcpu-16gb`) with monitoring |
| Data volume | a **block-storage volume** for data, mounted at `/srv/eax` |
| Firewall | a **cloud firewall**: 443, 80 and 9443 open; 22 from your address range |
| Off-site backups | when a Spaces key is given: a **Spaces bucket**, made with the AWS CLI because Spaces is S3-compatible; the key is kept on the Droplet in `/etc/eaexplorer/spaces.env`, root only; a nightly copy |
| DNS | when a DigitalOcean domain is given: the three names |
| Load balancer | when asked: passes https through to the Droplet, for adding Droplets later (scaling out: 36.3) |

It then continues as a server over SSH (user `root`).

## 3. Moving an installation

Choose *Move an existing installation* and give the folder of one of the old installation's **infrastructure
backups**: `work/backups/infrastructure/<name>`, copied from the old server (D410). After the new installation is up
and healthy, the wizard:
1. copies the backup there;
2. restores **every database**, then **the files** (documents, certificate, reports, imports, exports).

The new installation keeps **its own config file** (its address and passwords); the database logins made at its
first start are kept (D410). If the address changed, put the new certificate in the certificate folder and restart.

## 4. Passwords from a key vault (D504)

Choose a vault in the wizard, or later use `eax secrets`. The passwords and keys are then kept in the vault as well:

| Vault | What is kept |
|---|---|
| `file:<path>` | a file outside the installation, e.g. `/etc/eaexplorer/secrets.env`, readable by root only; on DigitalOcean this is the choice, on the Droplet |
| `aws:<secret name>` | AWS Secrets Manager: one secret holding them all as JSON |
| `azure:<vault name>` | Azure Key Vault: one secret each (`EAX_DB_PASSWORD` → `eax-db-password`); the vault is created when the wizard created the VM |

The config file records where (`EAX_SECRETS_FROM`). Docker Compose still reads the values from the config file when
it starts, so the vault is the copy you keep and restore from:

```
eax secrets                      # where they are kept, and which values
eax secrets push --to aws:acme/eaexplorer
eax secrets pull                 # the vault's values into the config file (a dated copy first, in work/config-history)
```

## 5. Active Directory groups mapped to roles (D503)

People sign in through Keycloak. Directory groups reach Keycloak in either of two ways:

- **Active Directory or LDAP:** Keycloak's admin console (`https://<address>/auth/admin`) › realm `eaexplorer` › User
  federation › Add LDAP provider. Give the server, bind user and users DN, then add a **group-ldap-mapper** (Mappers ›
  Add mapper › group-ldap-mapper) with the groups DN, so AD groups become Keycloak groups.
- **Entra ID:** Identity providers › Microsoft (or OpenID Connect) with the app registration's group claims switched
  on, plus a mapper that puts the `groups` claim on the user. Entra ID sends group object IDs unless the app
  registration sends names.

EA Explorer's sign-in clients send a **`groups`** claim (the "directory groups" mapper in the realm). Then, in
**Administration › Users › Keycloak role mapping**, choose **Directory group**, type the group's name (or its Entra
object ID), and choose the global role it gives. Everyone in the group gets the role at their next sign-in.

- Group names are matched without regard to case.
- A path such as `/EA/Architects` also matches `Architects`.
- Roles on a model are still given on each model's People tab.

## 6. Deploying from the running application: System admin › Deploy (D555 to D557)

An installation that is already running (your laptop, say) can deploy EA Explorer **to another place** from its
screens. Open System admin › **Deploy**; it is for Super Admins and IT Admins.

**Where it can deploy:**
- **a server reached over SSH**, with Docker installed if it is missing;
- **AWS, Azure or DigitalOcean**, creating the machine or using one that exists.

The laptop kind and "this machine is the server" are not offered, because this installation is already running.
To move an installation or to use your own certificate, run `eax deploy` on the target instead.

**How to use it:**
1. **Answer the questions:** the same ones as `eax deploy`, with this installation's repository link and version as
   the defaults.
2. **Paste the SSH private key, or choose its file.** For a machine that is created, its public key is put on it.
3. **Give the cloud credentials** when a machine is to be created: an AWS access key, a DigitalOcean token (and a
   Spaces key for off-site backups), or, for Azure, a **service principal** (client ID, secret and tenant), because
   there is no `az login` there.
4. **Show the plan**, which runs nothing, then **Deploy**.
5. **Follow the steps and the log.** A step that fails waits for **Retry**, **Back to the answers** or **Quit**. You
   can leave the page and come back: the run goes on in the operations helper.

**Where it runs:**
- A **plan** runs in the operations helper itself.
- A **deployment** runs in a short-lived **deployer** container with ssh, git, and the aws, az and doctl tools. It is
  built from `deploy/deployer` the first time, which takes 5 to 10 minutes, and has only its run folder
  (`work/deploys/<id>`) and this release's `eaxcli` and templates mounted.

**Credentials** reach the operations helper only:
- They are written into the run folder readable by root only, and **deleted when the run ends**.
- Tick **Keep**, and they are moved to `work/deploy-keep/<target>` instead (root only), to be chosen again for that
  target; **Forget credentials** removes them.
- They are never shown again, on any page or in any log.

**History:** every plan and deployment is kept: the target, kind, version, who, when, how it ended and the address
found. The page shows the **targets** deployed to and **every deployment**.

Managing many installations together (a fleet or farm: one dashboard, pushing updates to them) is **release 2**.
