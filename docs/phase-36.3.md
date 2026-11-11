# Phase 36.3: Scaling out (version 0.19.0)

Built 10 Nov 2026; to be accepted. Decisions D520, D521 and D526 to D528.

## What it is

Scaling out is **Docker Compose on one or more hosts** (the server kind, D416). Kubernetes was dropped with the
deployment kinds, and Docker Swarm is not needed (D520). One host scales the API by running more copies of it behind
nginx; more hosts are added with small compose overlays.

| Part | How |
| --- | --- |
| API and job servers | More copies of the api container behind nginx (D249). Set on **System admin, Scaling**: fixed, or by rules |
| Scaling rules | Fewest and most servers, people per server, CPU above and below, for how many minutes, then a cool-down (D526) |
| Database standby | Optional `standby` overlay: a second PostgreSQL kept up to date by streaming replication; promoted by hand (D527) |
| Shared storage | Optional `shared-storage` overlay: the work folder on NFS, for more than one host (D528) |
| Library on its own server | `library-host` on that host, `library-elsewhere` on the main one; the proxy's upstreams are settings (D521) |

## Scaling on the web page

**System admin, Scaling** (Super Admins and IT Admins) shows how many servers run, how many are wanted, the
average CPU and the people active in the last 15 minutes.

- **Fixed**: the number set on Containers or with `eax servers <n>` (`EAX_API_SERVERS`).
- **By rules**: the operations helper looks every minute. It wants one server for every *people per server* active people,
  and adds one when the average CPU stays above the upper limit for the set minutes, or removes one below the lower.
  It changes one server at a time, never outside fewest and most, and then waits for the cool-down.

Every change is logged with its reason (work/logs/scaling.jsonl) and listed on the page. The settings are kept in the
config file: `EAX_SCALE_MODE` (fixed or auto), `EAX_SCALE_MIN`, `EAX_SCALE_MAX`, `EAX_SCALE_USERS_PER_SERVER`,
`EAX_SCALE_CPU_UP`, `EAX_SCALE_CPU_DOWN`, `EAX_SCALE_MINUTES`, `EAX_SCALE_COOLDOWN`.

## The overlays

Overlays live in `deploy/compose/scale/` and are listed, comma-separated, in `EAX_COMPOSE_EXTRA` in the config file.
`eax` (all four forms) adds `-f deploy/compose/scale/docker-compose.<name>.yml` for each to every compose command.

| Overlay | Use it on | What it does |
| --- | --- | --- |
| `standby` | the main host, or a second host with `primary` on the first | Runs `db-standby`, a streaming replica |
| `primary` | the main host when the standby is on another host | Publishes PostgreSQL on `EAX_PRIVATE_BIND` for the standby |
| `shared-storage` | every host | Puts the work folder on NFS (`EAX_NFS_SERVER`, `EAX_NFS_PATH`) |
| `api-host` | an extra API host | Runs only api copies, pointed at the main database |
| `library-host` | the library's own host | Runs only the library service and its database |
| `library-elsewhere` | the main host | Stops the local library; the proxy uses `EAX_LIBRARY_UPSTREAM` |

The proxy reads `EAX_API_UPSTREAM`, `EAX_LIBRARY_UPSTREAM` and `EAX_VIEWS_UPSTREAM` (defaults: the local containers),
so API copies on other hosts and the library elsewhere are reached the same way.

## The database standby

1. Set `EAX_REPLICATION_PASSWORD` in the config file and add `standby` to `EAX_COMPOSE_EXTRA`.
2. `eax up`. The standby copies the database with `pg_basebackup` (slot `eax_standby`, role `eax_replicator`) and then
   follows it.
3. `eax standby status` shows whether it is following and how far behind it is.

To switch over when the main database is lost:

1. `eax standby promote`: the standby stops following and accepts changes.
2. Set `EAX_DB_HOST=db-standby` in the config file and run `eax restart`.
3. Make a new standby later from a fresh copy (take the old primary out of service first, so there are never two).

There is no automatic failover (D380).

## Shared storage

With more than one host, uploads, exports, backups and test results must be seen by all of them: set `EAX_NFS_SERVER`
and `EAX_NFS_PATH` and add `shared-storage` on every host. A single host does not need it.

## Needs on the owner's side

Docker on each host; for several hosts, a private network between them, an NFS export, and the firewall open for
PostgreSQL between the primary and the standby host only.
