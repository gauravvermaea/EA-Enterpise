# Build phase 10: administration console and application settings

Goal: one place for administrators, and the settings the whole application follows. Version **0.10.0**, migration
`0016_settings`. Decisions D156, D182, D183, D184.

## Status: accepted and closed (5 Nov 2026)

## What phase 10 delivers

- **Administration** (top menu) replaces Users, Heartbeat and SQL. Tabs, each for the roles that may use it (the others
  greyed out with the role needed):
  - **Application settings** (everyone sees; Super Admins change): base currency and symbol, country or region, time
    zone, date format, decimal and thousands separators, first day of the week, the month the financial year starts.
    Saved changes apply at once, everywhere. A line shows how dates, numbers and money will look.
  - **System settings** (IT Admins and Super Admins see; Super Admins change): largest upload (MB), how long change
    log entries are kept (removed automatically every hour; 0 keeps them for ever), signed out after idle (minutes),
    longest session (hours). Applied at once: the upload limit by the API, the session time-outs written to Keycloak.
    Below them every **start-up setting** of the config file, grouped, secrets masked; editing them and rotating
    passwords and secrets from the console come with phase 36 (D183).
  - **Restart the system** (Super Admins, type RESTART): every service of this installation restarts through the
    **operations helper**; the page waits and says when the system is back.
  - **Users** (User Admins): people, roles, Keycloak role mapping, as before.
  - **Health**: the heartbeat, and for IT Admins the containers with their state.
  - **SQL** (IT Admins), as before.
  - **Licences**: the products and libraries EA Explorer runs and their licences.
- **Formats everywhere (D182):** every date and time on every screen follows the installation's time zone and date
  format (not the browser's); numbers and money follow its separators and currency symbol.
- **Operations helper** (`services/ops`, container `ops`): a very small service with access to the Docker engine,
  only on the internal network (no published port). It answers only *status*, *restart everything* and *restart one
  service*, only with the shared secret `EAX_OPS_TOKEN`, and only for this installation's containers (by their Compose
  project). Always on (D183). A server must set its own `EAX_OPS_TOKEN` (the setup refuses the laptop value there).
- **Also in this build:**
  - **Hierarchy tab** on every model: where the model comes from (each model up to the root it was created from or
    merges into) and the models made from it, drawn as the model tree with this model outlined.
  - **VP-26 Gap**, a view of our own (D185): Gap entities with the elements they are about and the work packages
    and plateaus that close them, coloured by gap status; also a dashboard.
  - **Gap reports fixed** (D185): GR-01 to GR-05 failed with *permission denied for schema core*; their views now read
    through definer functions like the other report views. Every report view was run as the report login, and every
    chart's columns checked against its view.
  - **About this report** (D186): every report opens with a section saying what it shows, how to use it and how to
    read it.
  - Tables: numbers line up under their headings, and rows are shaded alternately.
  - **Gap analysis results** (Compare > Gap analyses, D189): a list of every result with a filter on its name and model;
    tick two (A and B) and **Compare** shows them side by side on screen (what moved, new gaps, gaps closed, status or
    resolution changed), with Excel and CSV downloads; **Delete** removes a result at once together with the Gap
    entities made from it (no draft; Model Admin when it has Gap entities). A deleted result's number is never reused.
  - Favourites and recently opened are off the start page, the Search page and the entity, model and view pages, until
    the start page is redesigned (phase 37); the favourites API stays.
  - **Services on and off** (D191): reports, documents, diagrams (draw.io), the MCP server, the change log and backups,
    each `EAX_SERVICE_*=on|off` in the config file (all on by default). `eax services` lists them; `eax service reports
    off` switches one (a dated copy of the config file is kept in `work/config-history` first). In the console:
    Administration > System settings > **Services** (Super Admin), and **Copies of the config file** with Restore (the
    switches in a copy apply at once, other settings at the next `eax up`). Switched-off containers are created but
    not started; screens hide or grey what is off; Health shows it as off. **Log level** is a system setting.
  - **Services console** (D199): every service, the core ones too, in one table like the Windows services console: a
    gear icon with a running / stopped / off badge, status, startup type (Always on, On, Off), its address (a link
    while it runs) and the buttons Start, Stop and Restart, greyed out where they cannot apply (a core service never
    starts or stops, only restarts; a running one cannot start). Stop switches the service off in the config file;
    Start switches it on again and starts it in seconds (the reports set-up is not run again once it has finished).
  - **The config file on screen** (D199, D200; IT and Super Admins): View the config file now or any dated copy, in clear
    text (passwords and secrets too); compare any two setting by setting (added, removed, changed, in clear text);
    **Make a copy now** with a few words of why; **Edit** the config file: Check changes lists problems (lines that
    are not NAME=value, a setting twice, a setting EA Explorer cannot start without) and every setting that would
    change, with warnings (a database password changed here is not changed in the database; a new realm name means a
    new realm); Save keeps the file as it was as a dated copy first. Changed service switches apply at once, every
    other setting at the next `eax up`. Restore is open to IT Admins too. Every view, copy and save is in the audit
    trail (saves with the names of the settings changed). The start-up settings list is in clear text too.
  - **Each service is switched on its own** (D200): starting or stopping one greys out only its own row; the others can
    be started, stopped or restarted meanwhile. A restore or a saved config file waits until nothing else is applying.
  - **Tagging runs in the background** (D192): the dialog and the Tags tab answer at once; a bar at the top follows the
    tag and says when it is made (or why not), with a link to it. API: `POST /models/<m>/tags` answers with a task;
    `GET /tasks/<id>`; `?wait=true` tags in the request.
  - **Entity History tab** no longer goes blank, and shows the commit each change came in with and its message (D195);
    the Change log shows them too, and its export has Commit and Commit message columns.
  - **Rules checked as you type** in the entity form (D194): each failing rule under its field and a summary at the top,
    before saving; still never blocking (D48).
  - **Deleting a gap analysis** deletes its Gap entities too (D193).
  - **Super Admins lift anyone's model lock** ("Unlock (Super Admin)", D196).
  - **Keycloak realm name chosen at the first install** (D187): `EAX_KEYCLOAK_REALM` in the config file (default
    `eaexplorer`); the setup checks it, and Keycloak, the API, the web app, Superset, Mayan and the MCP server all use it.
- **API** (Swagger, tag *admin*): `GET /settings` (application settings, everyone), `GET|PUT /admin/settings`,
  `GET /admin/licences`, `GET /admin/containers`, `POST /admin/restart` (`{service}` for one).

## Demo

1. `.\eax clean-restart`. As `user_super_admin`: **Administration > Application settings**: date format
   *DD MMM YYYY*, thousands separator *,*, save. Dates on the Change log and models pages change at once.
2. **System settings**: largest upload 1 MB, save; upload a model package bigger than that: refused with the limit.
   Set it back. The start-up settings show, passwords masked.
3. **Restart the system...**, type RESTART: the page waits, then *The system is back*.
4. **Health**: the containers. **Licences**. As `user_architect`: Administration shows Application settings (read only),
   Health and Licences; the others are greyed out.
5. A model's **Hierarchy** tab; **Views > VP-26 Gap** on Protea Insurance; **Reports > Gap analyses > GR-01**
   opens without errors.

## Checks

- `tests/sql/phase10_checks.sql` (as the API's login): ends with "phase 10 checks passed". Earlier phases' checks pass.
- `pytest services/api/tests`: `test_admin.py` (settings checked, Super Admin only, secrets never shown, licences, the
  helper, the console), `test_reports.py` (every report says how to use and read it), `test_views.py` (VP-26).

## Upgrading from 9

`.\eax clean-restart` (the new `ops` image is built). An existing `work/eaexplorer.env` without `EAX_OPS_TOKEN` uses
the laptop value.

## Not in phase 10

- Editing start-up settings, rotating passwords and secrets, and updates from GitHub or the registry: phase 36 (D183, D184).
- The home dashboard and the start page clean-up: phase 37. The first-run wizard: phase 16.3.
- Superset charts formatted with the installation's separators: the report views already read `core.settings`; the
  chart number formats follow with the report designer (phase 24).
