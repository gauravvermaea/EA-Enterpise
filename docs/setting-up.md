# Setting up an environment: laptop, server, cloud

Every EA Explorer installation has one config file, `work/eaexplorer.env`, made from a template for its kind of
environment. This page gives the commands for each kind. The same is in the README; every command in detail:
[command-line-and-console.md](command-line-and-console.md); deployments step by step: [deployment.md](deployment.md).

**`clean-run` and `clean-restart` make it themselves** (they delete the old one first), for a **laptop** unless you
name another kind. To make it on its own, without starting anything, use `init`; it never overwrites a config file
that is there (run `cleanup` first to start again).

**Laptop** (the default; every password is the known laptop one, `eax logins` prints them):

```powershell
.\eax init laptop          # the config file only (the same as .\eax init)
.\eax up                   # build and start
# or both in one step, from scratch:
.\eax clean-run            # = cleanup --all, init laptop, up
```

**Server** (this machine is the server; Linux shown, `.\eax` on Windows Server works the same):

```bash
./eax.sh init server        # the server template; asks for the backups folder (a mounted share or volume, EAX_BACKUP_DIR)
nano work/eaexplorer.env    # replace EVERY change-me value: EAX_HOSTNAME, the passwords, the certificate settings
./eax.sh check              # Docker, the config file and the compose files are valid; starts nothing
./eax.sh up                 # build and start
# or from scratch in one step (then edit the config file and run ./eax.sh restart):
./eax.sh clean-run server
./eax.sh clean-restart server   # the same while it is running
```

**Another server over SSH, or a new machine in AWS, Azure or DigitalOcean** (the guided deployment: it makes the config
file with every password generated, installs Docker when missing, starts EA Explorer and checks it):

```powershell
.\eax deploy --plan                           # shows every step and command, runs nothing
.\eax deploy                                  # asks: console or web page, then where
.\eax deploy --kind server                    # a server you reach over SSH
.\eax deploy --kind aws                       # also azure, digitalocean (a new machine from your credentials)
```

The same from the screens: the site picker (top left) › **Deploy EA Explorer**; the new site is added to **Sites**
when it is ready. On a machine without EA Explorer yet, `eax-deploy.cmd` (Windows) or `eax-deploy.sh` (Linux, macOS)
downloads the version you choose and then runs `eax deploy`. Every step in detail: [docs/deployment.md](deployment.md).

**A container platform** (Docker Swarm or another orchestrator, no Docker socket and no local disk): start from the
server template, then set `EAX_PLATFORM=managed` (self-tests go to the always-on test runner service) and
`EAX_FILE_STORE=database` (the self-test's files and exports kept in the database), and give the passwords as Docker
secrets if you like (D635):

```bash
./eax.sh init server
# in work/eaexplorer.env: EAX_PLATFORM=managed, EAX_FILE_STORE=database, EAX_BACKUP_DIR=<a mounted volume>
```

**Changing the kind later** (a laptop config to a server one): `init` will not overwrite, so keep a copy, then
`.\eax cleanup` (deletes the work folder, keeps the databases unless `--all`) and `.\eax init server`.

## Which to use

| You want | Run |
|---|---|
| Try EA Explorer, or develop and test, on your own computer | `.\eax clean-run` (laptop) |
| Test a new version on the laptop, from empty databases | `.\eax clean-restart` |
| Start again the next day, keeping your data | `.\eax run` |
| Install on the server you are on | `./eax.sh init server`, edit the config file, `./eax.sh up` |
| Install on another server, or a new cloud machine | `.\eax deploy` (or Sites › Deploy EA Explorer) |
| Run on Docker Swarm or another platform | `init server`, then `EAX_PLATFORM=managed` and `EAX_FILE_STORE=database` |
