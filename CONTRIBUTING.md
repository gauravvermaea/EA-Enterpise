# Contributing to EA Explorer

Thank you for wanting to help. EA Explorer is an open-source enterprise architecture repository, licensed under the
GNU Affero General Public License v3.0 (AGPL-3.0, see [LICENSE](LICENSE)). This guide says what to expect and what we
ask of every change. Please read it before you open an issue or a pull request.

## In short

1. **Open an issue first.** Say what you want to change and why. Wait until the approach is agreed.
2. **Then a pull request** from a branch of your own fork, with its tests and documents, linked to the issue.
3. **Sign off every commit** (`git commit -s`): the Developer Certificate of Origin, below.
4. **Keep the rules** below (they are the same rules the maintainers and the AI agents follow, [AGENTS.md](AGENTS.md)).
5. **Be kind**: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Licence and sign-off

Everything you contribute is under AGPL-3.0, the licence of the project. Anyone who runs a changed EA Explorer for
others over a network must offer them its source; your contribution is covered by the same terms.

Each commit carries a `Signed-off-by:` line with your real name and e-mail, which `git commit -s` adds. By adding it you
certify the [Developer Certificate of Origin 1.1](https://developercertificate.org/): in short, that you wrote the
change or otherwise have the right to submit it under the project's licence, and that you understand it is public and
kept with your sign-off. Pull requests with unsigned commits cannot be merged.

## Raising an issue

Use the issue templates. A good bug report has:

- the version (top left of the screens, System Admin › System, or `eax status`);
- the output of `eax diag` (it masks secrets; check it before you attach it);
- the steps that show it, what you expected and what happened;
- screenshots, and the request id of a server error when the screen shows one.

A security problem is never an issue: see [SECURITY.md](SECURITY.md).

## Setting up for development

You need Docker (Docker Desktop on Windows and macOS) and Git. Everything else runs in containers.

```
git clone <your fork>
cd EA-Enterpise
./eax.sh up            # Windows: .\eax up
```

`eax help` lists every command; [docs/command-line-and-console.md](docs/command-line-and-console.md) explains them.
`eax clean-restart` starts again from empty databases with the sample data.

How the code is laid out: [docs/architecture.md](docs/architecture.md). In short: `services/api` (the Flask API, job
runner and MCP server, Python), `services/web` (the React screens), `services/ops` (the operations helper),
`services/backup`, `eaxcli` and `eax.*` (the command line), `deploy` (configuration), `docs` (documents and decisions),
`releases` (release notes).

## Tests

- **Unit and API tests**: `cd services/api && python -m pytest -q`. Lint: `ruff check eax tests`.
- **The self-test** runs inside an installation: `eax test` (smoke) or `eax test full`, or System Admin › Self-test.
  It checks every endpoint as every role, every page and the main journeys in a browser, the database and security.

## The rules every change keeps

A change is **done** only when (decision D550):

- the **tests** are updated: unit and API tests, the self-test where there is a screen or an endpoint, and the help
  catalogue test;
- the **documents** are current: the phase document, [docs/capabilities.md](docs/capabilities.md), a decision in
  [docs/decisions.md](docs/decisions.md) (the next D number), the eax help (`eaxcli/help.txt`), the on-screen help
  catalogue and the release notes (`releases/<version>.md`);
- **sample data** shows it (each state of a new feature, in the laptop sample data);
- **no file is over 50 MB** (no Git LFS).

And always:

- **Every bug fixed gets a test that fails without the fix** and names the bug (D599).
- **No logic in the database** (D248): rules, calculations and checks are in Python. Constraints and indexes are fine;
  no new triggers or database functions.
- **No other enterprise architecture platform or vendor product is named** anywhere: code, screens, documents,
  workbooks, tests (D114).
- **No copyrighted text** from standards or books in code, data or documents, and no licensed template files committed.
- **Never a real secret** in seed data, tests or examples.
- **The eax command is kept in step in every form** (D331): `eax.ps1` with `eax.cmd`, `eax.sh`, and the Python
  `eaxcli/` with its launchers; the help and `docs/command-line-and-console.md` with it.
- **Permissions are checked in the API** (`require_auth` on every route) and every endpoint is in Swagger.
- Nothing is published but through the front door (nginx); no other port.
- **Plain language** in screens, messages and documents, **British spelling**.

## Style

- Python: as the code around it; `ruff` clean; short functions with a docstring that says what and why.
- React: JSX only in `.jsx` files; dates and numbers through `fmt.js`; help for every screen part in the help catalogue.
- Messages say what happened and what to do next, in words a business user understands.
- Documents: short sentences, the reason given, decisions referred to by their number.

## Decisions and reviews

Each design decision is recorded in [docs/decisions.md](docs/decisions.md) with its number, and stories and their state
in [docs/build-phases.md](docs/build-phases.md). The maintainer reviews every pull request; a change that alters what
people see or how the installation behaves is agreed in its issue first. Releases are cut by the maintainer, with
release notes in `releases/`.

Thank you.
