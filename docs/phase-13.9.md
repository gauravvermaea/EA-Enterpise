# Phase 13.9 — The eax command in Python, run by uv (D331)

**Accepted and closed by the owner, 8 Nov 2026 (D337).**

Status: **built 8 Nov 2026** as `eaxpy` beside the old `eax`; to test (checks below). Both are kept, and every change to
eax goes into both, until the owner says to switch.

## Why
eax.ps1 (Windows) and eax.sh (Linux, macOS) hold the same commands twice, about 1,500 lines, and drift apart. One
Python program is written and tested once, with the rest of the code's tests.

## How
- **uv** (one small program) fetches the right Python and runs `eax` on the computer itself: native paths, so Docker
  Compose sees the work folder as today.
- `eax.ps1`, `eax.cmd` and `eax.sh` become **launchers** of a few lines: find uv, run the Python eax with the arguments.
- **Command by command** against a checklist, each behaving as today: the logs, diagnostics, the two-tier start, the
  restore prompts, the clean-* commands, the console.
- The **old scripts stay** beside it until the owner has compared both on Windows and Linux; then they go.
- Windows-only parts (trusting the certificate in the Windows store) run through Windows' own tools from Python.

## Settled with the owner (8 Nov 2026)
- **Getting uv**: the launcher fetches it the first time into `work/tools` (uv 0.9.5, pinned; `EAX_UV_VERSION` for
  another), and uv fetches Python 3.12 there too (`work/tools/python`). Nothing is installed elsewhere. `cleanup` keeps
  `work/tools` (the old scripts too). Without internet: put uv into `work/tools`, or set `EAX_UV` to a uv program.
- **Side by side**: `.\eax` stays the PowerShell / bash script; the Python one is `.\eaxpy` (Windows: `eaxpy.cmd` /
  `eaxpy.ps1`) and `./eaxpy.sh` (Linux, macOS), until the owner says to switch.

## What it is
- `eaxpy.py` and the package `eaxcli/` (standard library only): `core.py` (folders, the log, the config file, docker
  compose, diagnostics), `stack.py` (optional services, the two-tier start, API servers, disks, maintenance),
  `info.py` (addresses, logins, the TOGAF hint, the certificate on Windows, macOS and Linux, following logs),
  `main.py` (help, the commands, cleanup and clean-*, init, check, the console loop).
- The help text is the same as `eax.ps1`'s (a test checks both list the same commands, and that every command of
  `eax.ps1` is handled).
- Windows' certificate store is reached through PowerShell from Python (`trust`); macOS through `security`; Linux says
  what to run, as before.

## Checks (Windows first, then Linux)
1. `.\eaxpy help`: the same commands as `.\eax help`. The first run says it fetches uv (once).
2. `.\eaxpy clean-restart`: the same steps and output as `.\eax clean-restart` (down, cleanup, init, the core first,
   ready, the rest in the background); `work\tools` is still there afterwards.
3. `.\eaxpy status`, `logs api`, `services`, `service drawio off` / `on`, `servers 2` / `servers 1`, `url`, `logins`.
4. `.\eaxpy backup test`, `backups`, `restore` (choose, then stop at the RESTORE question), `restores`.
5. `.\eaxpy maintenance on` / `off`; `.\eaxpy diag`: the log has the diagnostics.
6. `.\eaxpy trust`: Windows asks to confirm; `.\eaxpy trust --remove` takes it out.
7. `.\eaxpy console`: the menu (13.5) works the same as from `.\eax console`.
8. On Linux: `./eaxpy.sh clean-restart`, `status`, `cleanup --yes` (the backups written as root are removed too).
