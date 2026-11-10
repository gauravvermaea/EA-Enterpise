# Phase 25 — Machine access

Status: **built, to be accepted** (release 0.17.0, migration 0036). Design agreed 9 Nov 2026 (D366, D378); as built
10 Nov 2026 (D438 to D441).

## What it is
Other systems, scripts, Excel and Power BI (the OData feed) and MCP clients sign in to EA Explorer without a person at a
browser, with a **token**, an **API key** or a **client certificate**. Each belongs to a person (their own) or to a
**service account**, works as its owner (never with more than the owner may do), only in the **areas** it is given, until
it **expires** or is **revoked**. Every call it makes is in the change log.

Screen: **System admin › Machine access** (everyone sees their own; Super Admins and IT Admins see everything).

| | Token | API key | Client certificate |
|---|---|---|---|
| For | a person's scripts, MCP clients, Excel and Power BI | other systems | other systems that use mutual TLS |
| Looks like | `eaxt_...` | `eaxk_...` | a certificate (self-signed is fine) |
| Sent as | `Authorization: Bearer eaxt_...` | `X-API-Key: eaxk_...` (or Bearer) | presented on the machine-access port |
| Made by | anyone, for themselves; admins for service accounts | the same | Super Admins and IT Admins (uploaded) |
| Lives | 90 days unless asked, up to a year | a year unless asked, up to two | a year unless asked, up to two, never past the certificate's own expiry |

- A secret is **shown once** and kept only as a SHA-256 hash; the screen shows its first characters to recognise it.
- An expiry can be brought forward, never pushed back: make a new one for longer.
- The OData feed's Basic sign-in (Excel, Power BI) takes a token or API key as the **password** (any user name).

## Areas (D439)
Each credential is given **read** (GET only) or **read and write** on each area; an area not given is refused (403 with
why). Who am I (`/api/v1/me`) and the heartbeat always answer. The Areas and addresses view lists every address in each.

| Area | Holds |
|---|---|
| Models and content | models, entities, relationships, changes and commits, tags, views, sheets and loads, search |
| Metamodel | entity and relationship types, attributes, rules, metamodel versions, drafts and push-down |
| Projects | architecture projects, their steps, governance, the repository, tracking sheets, calendars, surveys |
| Documents | project documents and files, change documents |
| Reports | reports, quality, comparisons, gap analyses, common analysis, maps, KPI trends, the OData feed |
| Library | the model library, the project library and the reference library |
| Change log | the change log |
| Administration | settings, users and roles, backups, jobs, the audit log, operations, metrics |
| MCP | the MCP server; read allows only the tools that read |

A credential can be limited to **some models** or **some projects**: a call whose address is about another one is
refused; lists still show what the owner sees.

**Never more than the owner:** a person's credential acts with the global roles the API last saw that person sign in with
and their model roles now (someone who loses a role loses it on their credentials too); a service account's with the
roles it was given. The database's row-level security applies as for any call.

## Service accounts (D441)
`svc-<name>`, made by Super Admins and IT Admins with global roles (user, model creator, library admin, IT admin; Super
Admin only by a Super Admin). Their model roles are given on each model's People tab like anyone's. Disabling one stops
all its credentials at once.

## Client certificates (D440)
The proxy listens on **a port of its own for mutual TLS** (`EAX_MTLS_PORT`, 9443 unless set, in `work/eaexplorer.env`),
so browsers on the main site are never asked for a certificate. It accepts any certificate there and passes it to the API
and the MCP server, which trust only a certificate uploaded on the Machine access screen (by its SHA-256 fingerprint).
Everywhere else the proxy clears that header.

    curl --cert system.crt --key system.key https://ea.example.org:9443/api/v1/models/

## Recorded (D441)
Each call updates the credential's last use (when, from where, which address, how many calls) and is written to the audit
trail as `machine.call` (refused ones too), so it appears in the change log. Making, changing and revoking credentials and
service accounts are in the change log too. Credentials are managed only by a person signed in, never with a credential.

## Sample data (laptop)
Three service accounts (one disabled), eight credentials covering every state: active, expiring within two weeks,
expired, revoked, never used, limited to the demo estate, a client certificate. Their secrets are random and were thrown
away: make your own to try it.

## Built
- `services/api/eax/machine_access.py` (areas, checks, credentials, service accounts), `eax/api/machine_access.py`
  (`/api/v1/machine-access/...`), the hook in `eax/auth.py` (every route) and `eax/mcp_server.py`, the OData Basic check
- migration `0036_machine_access_ops` (core.service_accounts, core.machine_credentials)
- proxy: `deploy/proxy/templates/default.conf.template` (port 9443), `docker-compose.yml`, the env templates
- web: `MachineAccess.jsx`; seed `eax/seed/sample_machine_ops.py`; tests `test_machine_access.py`

## To check on the laptop
The mutual TLS port needs the real proxy: `.\eax clean-restart`, upload a self-signed certificate, then call
`https://localhost:9443/api/v1/me` with it (curl `--cert/--key`, `-k` for the laptop certificate).
