# Releasing EA Explorer (8.5, D513 to D515)

How a version gets from `main` to the installations, what the owner runs, and which versions are supported. The owner
runs git; nothing here pushes on its own.

## The branches and the channels (D417)

| Channel | Branch | Tags | Installations see it |
|---|---|---|---|
| **Prod** | `release` | `vX.Y.Z` | always |
| **RC** | `rc` | `vX.Y.Z-rc.N` | once a Super Admin or IT Admin enables RC |
| **Latest** | `main` | none (each commit) | once enabled; untested between releases |

Installations list the **tags** of the repository (Prod: `vX.Y.Z` only; RC: the RCs and the releases) and the commits of
`main` (Latest). The branches `release` and `rc` show where each channel stands; the tags are what is offered.

## Setting it up, once (the owner)

1. Make the repository public (installations read it without credentials).
2. Create the two branches from `main` and push them:

   ```
   git checkout main
   git pull
   git branch release
   git branch rc
   git push origin release rc
   ```

3. Give the repository link to each installation: System admin › Updates › Change… (or
   `eax update --url https://github.com/<owner>/<repository>.git`, or `EAX_UPDATE_GIT_URL` in work/eaexplorer.env).

## Releasing a version

1. On `main`, with every test green, set the version in `services/api/version.toml` (e.g. `0.19.0`).
2. Write the notes: `python tools/release.py notes 0.19.0` makes `releases/0.19.0.md` from the commits since the last
   release. Edit it: two or three lines on what people will notice, then anything to check before updating.
3. Print the git commands: `python tools/release.py commands 0.19.0`. For the first release they are:

   ```
   git checkout main
   git pull
   git add releases/0.19.0.md services/api/version.toml
   git commit -m "Release 0.19.0"
   git push origin main

   git checkout release
   git merge --ff-only main
   git tag -a v0.19.0 -m "EA Explorer 0.19.0"
   git push origin release v0.19.0
   git checkout main
   ```

4. CI runs on the tag: the API tests and lint, the web build, the compose files and images (built to test them, not
   published), then `tools/release.py check` (the tag, version.toml and the notes agree) and the GitHub release with the
   notes. Installations on Prod now offer 0.19.0.

**A release candidate** is the same with `-rc.N` and the `rc` branch: `python tools/release.py notes 0.20.0-rc.1`
(optional: without its own file an RC shows `releases/0.20.0.md` once that exists), then
`python tools/release.py commands 0.20.0-rc.1` (`git checkout rc`, `git merge --ff-only main`,
`git tag -a v0.20.0-rc.1 …`, `git push origin rc v0.20.0-rc.1`). Installations with RC enabled see it.

**Latest** needs nothing: every push to `main` is offered to installations with Latest enabled, with the commits'
one-line messages as its notes.

## Release notes (D510)

`releases/<version>.md` in the repository, read at the tag. An RC without its own file shows its release's file. Latest
shows the one-line messages of the commits since the installed commit. Installations show the notes when choosing a
version, and to everyone once afterwards as **What's new**.

## Images (D514)

Not published. D373 asked for published images; D417 (later) builds every version **on the installation's own host**
from the repository, with no registry, so an update needs nothing but the public repository. CI still builds every image
on every change, to prove they build. If a registry is wanted later (air-gapped sites, faster updates), CI can push the
images it already builds; nothing in the updater depends on it.

## Supported versions (D515)

- The **newest release line** (X.Y) and **the one before** are supported: e.g. with 0.21.x out, 0.21.x and 0.20.x.
- A **release candidate** is supported until its release is out; a **Latest** build only until the next release.
- Within a line, only its newest patch gets fixes: update to it.

Installations check once a day (with a repository link set) and tell their Super Admins and IT Admins, once per version,
when the installed version is out of support, with the version to update to.

## Alerts to operations (D515)

The Super Admins and IT Admins are told (the bell, and the webhooks) when an update fails (needs action: Retry or Roll
back), finishes, is rolled back or does not start, and when the installed version is out of support. CI failures are
GitHub's own notifications to the owner.
