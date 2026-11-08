# Phase 13.7 — Real-time PostgreSQL mirrors and mirrors of the other servers (requested, for later)

Status: **requested for later** (owner, 8 Nov 2026). Not designed or built yet; discuss before building.

## The ask
**Real-time mirrors** of PostgreSQL, and of the other kinds of server EA Explorer runs, so that a failed server is taken
over by its mirror without losing data.

## Questions to settle when it is built
- PostgreSQL: streaming replication to one or more standbys (synchronous, so nothing committed is lost, or
  asynchronous, faster); automatic failover (for example Patroni with etcd, or the platform's managed PostgreSQL);
  reads sent to a standby (reports, Superset) or all to the primary.
- Every database on the server mirrors: the repository (core), the projects' database when it is separate (proj),
  the change log, Keycloak's, Mayan's, Superset's.
- Documents (Mayan): its database is mirrored; its stored files on shared or replicated storage (object storage, or a
  replicated volume).
- Keycloak: several nodes sharing its (mirrored) database.
- The background job queue lives in PostgreSQL: it follows the primary on failover.
- The application connects to whichever server is primary (one address that moves, or a connection proxy).
- Mirrors are not backups: the nightly backups stay (a mistake is mirrored at once).
- Where: a server install only (the laptop stays one of each); other sites (a second data centre) or the same one.
- How it is tested: a failover drill, and what the screens show while it happens.
- Fits with 13.6 (scaling the application servers) and the backup phases.
