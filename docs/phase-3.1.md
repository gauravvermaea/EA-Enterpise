# Build phase 3.1: roles and permissions

Goal: everyone gets exactly what their role allows, in the screens, the REST API, MCP and the
database itself, before anyone can change content. Version **0.3.1**, migration `0006_roles`.
Decisions D58, D59, D60, D80, D89, D90, D92 to D98, D100 to D102, D107, D109, D110, D113, and part of D81. Migrations `0006_roles` and `0007_relationship_rules`.

## Status: accepted (4 Nov 2026)

## What phase 3.1 delivers

- **Two kinds of role (D96).**
  - **Global roles** are given in **Keycloak** (D92). EA Explorer maps Keycloak roles to them
    (defaults `eax-super-admin` and so on; any Keycloak role can be mapped; directory groups, when
    they come, are mapped in Keycloak, D93):

    | Global role | What it is |
    | --- | --- |
    | Super Admin | Everything, everywhere: every model and every setting. |
    | IT Admin | Runs the installation: heartbeat, jobs, audit log, backups, the SQL window (read only), Superset and Mayan administration. No model content. |
    | User Admin | Looks after people: sees everyone, their global roles and which models they have roles on, and maps Keycloak roles to global roles. Reads no model and gives no model roles. |
    | Keycloak Admin | Administers Keycloak itself (users, roles, identity providers) through its console. |
    | Model Creator | Creates new models and becomes the Model Admin of each model they create. |
    | User | May sign in. Sees only the models they have a role on (and the library). Every new Keycloak user gets it. |

  - **Model roles** are given **per model**, in EA Explorer, by that model's Model Admin (its
    *People* tab). One person can be Architect on one model and Model Admin on another, and hold
    several roles on the same model:

    | Model role | What it is, on that model |
    | --- | --- |
    | Model Admin | Owns the model: changes its metamodel, locks it, gives people roles on it, changes its content, derives models from it; commits once the commits phase arrives. |
    | Model Sub Admin | The Model Admin's deputy for content: changes the content; in the commits phase reviews and commits other people's changes. Not the metamodel or people. |
    | Architect | Works on the content: reads and changes entities, relationships and values (changes go for review once commits exist). |
    | Report Viewer | Reads the model: screens, pictures, reports and exports. Changes nothing. |

- **What everyone reads.** The models they have a role on, the models those come from (read only,
  D60), and the **library** (templates and reference models), which is open to everyone signed in
  because models are created from it (D98). Super Admins read everything.
- **Creating models (D97).** Model Creators (and Super Admins) create models; a Model Admin may
  derive a model from theirs. Whoever creates a model becomes its Model Admin. Roles are **not
  copied** to a derived model; its people can read the model it comes from. (Creating models on
  screen arrives in phase 4; the rule is in the database now.)
- **One check, enforced twice.** `eax/permissions.py` is the one permission check for the screens,
  REST and MCP (403 with a clear message). Every database connection the API opens is told who is
  asking (`eax.actor`, `eax.user_roles`). The database then enforces the same rules whatever the route:
  row-level security on models, entities, relationships and attribute values, and triggers that refuse
  changes the person's roles on that model do not allow. The installer, the seed, the job runner and an
  administrator's own `psql` (no user set) are not restricted.
- **Users page** (User Admins and Super Admins; *Users* in the top bar): every person in Keycloak with
  their Keycloak roles, the global roles those give and their roles on models, with a search, a role
  filter, CSV and *Change in Keycloak*. Second tab: **Keycloak role mapping**: add or remove a mapping;
  it takes effect within 30 seconds. Every change is audited.
- **People tab** on every working model: who has which roles there, as check boxes per role; the
  model's Model Admins give and take roles and find people in Keycloak.
- **Menus and buttons follow the roles**: the SQL window for IT and Super Admins, Users for User and
  Super Admins, the Keycloak tile for Keycloak and Super Admins; on a model, the metamodel edit buttons
  and the lock control for its Model Admins ("Read-only for you" otherwise), and "You: ..." beside the
  model name showing your roles there.
- **Finding a model's parents**: the model list has a *Comes from* column (merges into, created
  from) with links, and a **Hierarchy** tab that draws every model you may read as a tree of boxes
  under the model it merges into (solid line) or was created from (dashed line): top down or left to
  right, pan and zoom, highlight by name, click a box to open the model, save as .drawio, SVG or PNG. On a model page, the breadcrumb walks up the hierarchy (Models /
  ArchiMate 4 / Insurance reference model / Fynbos Mutual (group) / Fynbos Life) and the summary line
  links to the parent.
- **The top of the hierarchy (D81, built early)**: a read-only model called **Root** (no types) is the top of every tree;
  **ArchiMate 4** (kind *Root metamodel*) is created from it. **Lean EA metamodel 1.0** is a sample root built from
  scratch (three domains, five types, four relationship types, a pick list), not locked, so its Model Admin can change its
  metamodel; **Karoo Digital (lean)** is a project model built on it. ArchiMate 5, or any organisation's own root, sits
  beside ArchiMate 4 the same way.
- **Model library redesigned (D101)**: a browser on the left (root metamodels, then the reference models on each root,
  with a search and a Root / Reference filter), and the chosen model on the right: what it is built on, its domains, types
  and counts, its pack and the library models built on it. Each has its own address (`#/library/<id>`). The buttons for
  creating a model from it, downloading or uploading a library package and promoting a model arrive in phase 4.
- **Model marks (D102)**: every list, tree, switcher and model page marks a model the same way, with a legend: ◆ root
  metamodel, ▣ reference model, ● project model; 📚 in the library; 👁 read-only (for everyone, or for you: the tooltip
  says which); 🔒 locked by a Model Admin (the tooltip says who and why).
- **HTTPS everywhere (D107)**: every screen, the API with Swagger and the MCP server go through nginx on
  `https://localhost`. EA Explorer makes a local certificate authority (its key is thrown away; it may
  vouch only for localhost and EAX_HOSTNAME) and signs the site certificate with it. Optionally run **`.\eax trust`**
  once and the browser stops warning (without it, accept the warning once per name, as before; laptops
  send no HSTS header so that always works); `clean-run` keeps the certificate (`work\data\tls`), so once is
  enough (`cleanup --certificate` deletes it). The direct ports 8000 and 8001 are gone. On a laptop the API
  (`http://localhost/api/docs`) and the MCP server (`http://localhost/mcp`) also answer on plain http, from
  this computer only; on a server plain http only redirects.
- **Start page shows what is coming (D109)**: a card for everything agreed, grouped (models and the library,
  architecture projects and repository, working together, diagrams and reports, data exchange, language
  models, platform), each with the build phase that delivers it.
- **What a change did, in an entity's history (D110)**: pick a moment on an entity's History tab and the
  values that change set are highlighted ("changed here") and the Then column shows them as old → new
  (the old value in red, struck through; the new value in bold); Now shows the current value, shaded
  where it differs. Relationships it added are green and those it removed red. The line above says what the change did, for example "changed 2 values, added 1 relationship".
  The timeline labels each change: created, set (a first value), changed, cleared, added, removed. On a
  laptop the seed saves four versions of *Customer Portal* (and three of *Policy Administration System*)
  in the Sample insurance model, by different test users a moment apart, to try it on.
- **Rules tab on every entity (D113)**: every rule applied to the entity, each **passed**, **failed**
  (error or warning) or **not applicable** (no value to check, or a condition that does not hold), with
  the value checked, what the rule asks and why it failed; failed first, a filter and CSV. Below it, each
  of the entity's relationships checked against the metamodel. The tab's label says how many fail
  ("Rules (4 failing)", or "Rules ✓").
- **Rules that an entity has a relationship (D113)**: a new rule type, *Has relationship*: at least one
  relationship of a type (or any) to or from an entity of a type (or any). Add it on an entity type's
  page (*+ Rule*, Checks: Relationships). Like every rule it warns and never blocks, and failures show in
  Failing checks. On a laptop, **Karoo Re** has four such rules (applications realise a capability and
  serve something, capabilities are realised by an application, requirements realise a goal) and six
  entities that break rules: *Legacy Claims Spreadsheet* (no owner, criticality 7, bad version and URL,
  negative cost, retiring with no date, no relationships), two *Broker Portal*s (same name; one went
  live in 1985 and retired before that), *Fraud Detection* (level 6, nothing realises it), *Paperless
  claims* (realises no goal) and *Data Centre Exit* (ends before it starts).
- **Break-glass account (D80)** for when Keycloak is down: the start page offers *Break-glass sign-in*;
  the password is `EAX_BREAK_GLASS_PASSWORD` in the config file (on a server, generate a long one,
  seal it and keep it outside the product). It gives a Super Admin session with a red banner that lasts until you sign out or the password is changed (D100).
  Every sign-in, failed attempt and call is audited; five failures lock it for 15 minutes. After a
  use the heartbeat warns until the password is changed (config file and restart), which also ends
  every break-glass session.
- **Test users on laptops**, printed with their passwords by `eax init`, `eax up` and `eax logins`
  (password: the laptop password):

  | User | Global role | Roles on models |
  | --- | --- | --- |
  | user_super_admin | Super Admin | (every model) |
  | user_it_admin | IT Admin | none |
  | user_keycloak_admin | Keycloak Admin | none |
  | user_user_admin | User Admin | none |
  | user_model_creator | Model Creator | Model Admin: Karoo Re, Lean EA metamodel, Karoo Digital (lean) |
  | user_model_admin | User | Model Admin: Fynbos Mutual (group), Fynbos Life; Architect: Sample |
  | user_architect | User | Architect: Sample, Fynbos Life; Model Sub Admin and Report Viewer: Fynbos Commercial |
  | user_model_sub_admin | User | Model Sub Admin: Sample, Fynbos Life, Fynbos Commercial, Karoo Re |
  | user_report_viewer | User | Report Viewer: Fynbos Mutual (group), Sample |
  | user_global_architect | User | Architect on every model |

- **Laptop test models (D95)**: *Fynbos Mutual (group)*, a fictitious insurer created from the
  Insurance reference model; *Fynbos Life* and *Fynbos Commercial*, lines of business derived from the
  group; *Karoo Re (independent)*, created from ArchiMate 4 with sample content; *Lean EA metamodel*, a root built from scratch, and *Karoo Digital (lean)*, a project model on it.
- **Superset** maps the global Keycloak roles to its own (Admin for Super and IT Admins, Gamma for
  everyone else); model roles in Superset arrive with the report views. Rows by model in Superset
  arrive with the report views (phase 5); Mayan cabinets by model with the Mayan phase (13).
- **API**: `GET /api/v1/me` (roles, Keycloak roles, permissions, models), `GET /roles`,
  `GET/POST /role-mappings`, `DELETE /role-mappings/<id>`, `GET /keycloak-roles`, `GET /people`,
  `GET/POST /models/<m>/people`, `DELETE /models/<m>/people/<user>`, `GET /break-glass/status`,
  `POST /break-glass/sign-in`. The MCP server applies the same permissions to every tool, and refuses
  to answer when it cannot tell who is asking.

## Demo

1. `.\eax clean-run`, then optionally `.\eax trust` (Windows asks you to confirm). The console lists the test users;
   `https://localhost` opens without a certificate warning, and the start page shows what is coming.
2. Sign in as `user_architect`: Sample, Fynbos Life and Fynbos Commercial, plus the models they come
   from and the library (read only). "You: Architect" on Fynbos Life; "You: Model Sub Admin, Report
   Viewer" on Fynbos Commercial. The Metamodel tab says *Read-only for you*.
3. Sign in as `user_model_admin`: Fynbos Life > People: tick *Report Viewer* for `user_report_viewer`;
   sign in as them and see Fynbos Life appear. The metamodel edit buttons and *Lock...* are there on
   Fynbos Life, but not on Sample (where they are only Architect).
4. Sign in as `user_user_admin`: *Users* lists everyone with their global roles and roles on models; no
   model content. *Keycloak role mapping*: map a new Keycloak role to Model Creator.
5. Open **Library**: the browser on the left; pick *Insurance reference model* and see it is built on ArchiMate 4; on
   **Models > Hierarchy** see Root at the top with ArchiMate 4 and Lean EA metamodel under it, and the marks on each box.
   Sign in as `user_model_creator` and open *Lean EA metamodel*: its metamodel edit buttons are there (an organisation's own root).
6. Sign in as `user_it_admin`: the SQL window and the library, no working models.
7. Swagger as `user_architect`: `POST .../metamodel/changes` on Fynbos Life gets 403.
8. Sign in as `user_model_creator`, open **Karoo Re** > Entity types > Application Component > *Legacy
   Claims Spreadsheet* > **Rules**: 3 errors and 5 warnings, the rest passed or not applicable. Then the
   model's **Failing checks** tab: the six demo entities and their failures.
9. `docker compose --env-file work/eaexplorer.env stop keycloak`, open the start page, *Break-glass
   sign-in* with the break-glass password: a red banner; the heartbeat warns. Start Keycloak again.

## Checks

- `tests/sql/phase3_1_checks.sql`, run as the API's login (it owns the tables, so row-level security
  applies; a superuser would bypass it). Ends with "phase 3.1 checks passed". Rolled back.
  ```powershell
  Get-Content services/api/tests/sql/phase3_1_checks.sql | docker compose --env-file work/eaexplorer.env exec -T db psql -U eax_app -d eaexplorer -v ON_ERROR_STOP=1
  ```
- `phase1_checks.sql`, `phase2_checks.sql`, `phase2_installer_check.sql` and `phase3_checks.sql` still pass.
- `pytest services/api/tests/test_permissions.py test_auth.py test_mcp_auth.py`: role mapping,
  permissions, break-glass tokens, MCP sign-in.

## Upgrading from phase 3

`.\eax clean-run` (D54), then `.\eax trust` once. New settings: `EAX_HTTP_BIND` and `EAX_HTTP_API_MCP` (D107); `EAX_KC_SERVICE_SECRET` (the API's Keycloak client, which
reads people and roles) and `EAX_BREAK_GLASS_PASSWORD`; the laptop template has both. The Keycloak
realm is new (new roles, the `eax-admin` client, test users), so Keycloak's database must start empty.

## Not in phase 3.1

- Superset rows by model (phase 5) and Mayan cabinets by model (phase 13).
- Commit rights (Model Sub Admin, Model Admin): the commits phase.
- Building roots on screen, creating and copying models, and library models (create as library, promote, package download and upload): phase 4 (D81, D101).
- Notifications for the break-glass alert: the actions, alerts and workflows phase (8.1); until then
  the heartbeat and the audit log carry it.
