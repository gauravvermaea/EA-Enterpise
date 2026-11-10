# Phases 35 and 35.1 — Operations insight and housekeeping

Status: **built, to be accepted** (release 0.17.0, migration 0036). Design agreed 9 Nov 2026 (D371); as built 10 Nov 2026
(D442 to D445).

Screen: **System admin › Operations** (IT Admins and Super Admins): Usage, Housekeeping, Archive, Database health, Metrics.

## Usage (D442)
The API counts every signed-in call (people, service accounts, credentials) per day, person, area, part and model, in
memory, written about once a minute (core.usage_daily). The Usage page, over 7, 30, 90 or 365 days:
- totals, calls per day, and each **person or account**: calls, days active, the areas they use most, last seen
- the **parts used**: each area and part, calls, people
- each **model**: entities, relationships, history versions, calls, people, last used, last changed
- **idle models**: no call about them for 180 days (counted only once the record goes back that far). **A report only:**
  nobody is told and nothing happens to them
- **stale work**: uncommitted changes older than 30 days (per model and person) and loads not added after 14 days
- **credentials**: live, expiring within two weeks, not used for 90 days

## Prometheus metrics (D443)
`GET /api/metrics`, the Prometheus text format, read with a token or API key that may **read Administration** and belongs
to an IT Admin (or a service account with the IT Admin role). The Metrics view shows the scrape configuration. Metrics:
`eax_info`, `eax_up`, `eax_models`, `eax_entities`, `eax_relationships`, `eax_people_active`, `eax_api_calls_today`,
`eax_uncommitted_changes`, `eax_jobs`, `eax_backup_last_success_age_seconds`, `eax_machine_credentials`,
`eax_database_size_bytes`, `eax_housekeeping_last_run_age_seconds`.

## Housekeeping (D444, D445)
Retention rules for what grows, each **keep**, **archive** or **delete** after N days:

| Rule | Default | Allowed |
|---|---|---|
| Loads (added, undone or failed, with their file) | archive after 90 days | keep, archive, delete |
| Task files | archive after 90 days | keep, archive, delete |
| Notifications (no action needed, or resolved) | archive after a year | keep, archive, delete |
| Old history versions | **off**: a Super Admin sets an age in years (at least one) to remove older ones (D445) | keep, remove |
| Webhook deliveries (sent or failed) | keep | keep, archive, delete |
| Discarded and rejected changes | keep | keep, archive, delete |
| Usage counts | keep | keep, delete |
| Housekeeping runs | keep | keep, delete |

- **Nothing is deleted until an admin says so.**
- A job runs **every night at 02:40**. It acts only when a **dry run of the rules as they are now has been confirmed**;
  otherwise it does a dry run, once, and waits. On the screen: *Dry run now*, look at what it would do, *Confirm*. After
  that the nightly run acts, and *Run now* is allowed. **Changing a rule asks for a new dry run.**
- At most 5,000 records per rule per run; the rest goes next time.
- **Old history versions** (D445): off until a Super Admin sets an age in years. Removed (not archived) only after a
  confirmed dry run, which lists the count per model and warns that the model's states before then can no longer be
  viewed or compared. Never removed: the current version of anything, the version current at any tag (baselines and a
  child's merge starting point included) or drawn view evidence, and any version of a principle or standard a governance
  record names. History stays append-only for everything else: the job lifts the guard only inside its own transaction,
  as the table's owner, and checks it is back on before committing. At most 50,000 versions a run.
- Every rule change, dry run, confirmation and run is in the change log.

## Archive
Archived records go to core.archived_items: the record as it was (JSON) and, for loads and task files, the file. Searched
on request on the Archive view (words, kind); each can be looked at, and a file downloaded.

## Database health
The database's size and connections, the **largest tables** (size with indexes, rows, dead rows, when last tidied and
analysed), and the **slowest queries** when the database records them (the `pg_stat_statements` extension); without it,
the queries running for more than a second now.

## Sample data (laptop)
Usage over 200 days (one model idle for more than 180 days), an uncommitted change left 45 days, retention rules with one
changed by an IT Admin (webhook deliveries deleted after 180 days), a confirmed dry run and a run 40 days ago that
archived a load and two notifications, and a new dry run waiting to be confirmed because rules changed since:
a Super Admin set old history versions to be removed after a year, and the dry run shows the 60 older sample versions (two
and three years old, on 30 demo-estate entities) it would remove.

## Built
- `services/api/eax/operations.py`, `eax/api/operations.py` (`/api/v1/operations/...`), `/api/metrics` and the call
  counting in `eax/app.py`, the nightly job in `eax/jobs.py`
- migration `0036_machine_access_ops` (core.usage_daily, core.retention_rules, core.housekeeping_runs, core.archived_items)
- web: `Operations.jsx`; seed `eax/seed/sample_machine_ops.py`; tests `test_operations.py`
