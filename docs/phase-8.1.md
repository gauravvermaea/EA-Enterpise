# Build phase 8.1: actions, alerts and workflows

Goal: people are told what has changed and asked to act, and every request is tracked to an outcome. Version
**0.11.0**, migration `0018_notifications`. Decisions D84, D86, D209 (the design session of 6 Nov 2026).

## Status: accepted and closed (6 Nov 2026)

## What phase 8.1 delivers

- **Notifications** (bell, page, home tile, API, MCP to read):
  - A **bell** in the top bar with the number of unread notifications and open requests for you; the count is read
    when a page opens (no live push, D209).
  - **Notifications and requests** page (`#/notifications`): filter by open, waiting for action, resolved or all, by
    kind (commits, metamodel, requests, model events) and by text; opening the page marks them read.
  - **Kinds**: commits and review (changes waiting for a committer; committed, rejected, sent back, withdrawn, rolled
    back), metamodel changes (offered, made, rejected, failed, pass it on), requests, and model events (locked,
    unlocked, tagged, a sheet loaded, merged, copied, archived, reactivated, published).
  - **Who gets them**: everyone with a role on the model (D209). The person who did it is left out, except where they
    must act themselves.
  - **Needing action or not**: those that need action (changes waiting for a committer, a metamodel package offered,
    one that failed, passing a package on, a request sent to you) stay open until someone **resolves** them with a note
    of what was done, once for everyone who got them; some resolve themselves (a commit request is resolved when the
    changes are committed, rejected, sent back or withdrawn; an offered package when it is accepted or rejected; a
    request when it is done or declined). Information notifications are read or **dismissed** by each person.
  - Most come from the audit trail (`notify.on_audit`), so the screens, the API and MCP notify alike.
- **Requests between people** (like tickets, WF-016): anyone sends another user a **subject and a body** (no
  attachments, no links to models or items). The receiver moves it **open → in progress → done or declined** (done
  and declined need a note); either may comment; a closed one can be opened again. The other person is told at each
  step. A request is **private** to its two people. Raised in the screens, the API or through MCP (`send_request`).
- **Webhooks** (installation-wide, IT and Super Admins; Administration > System settings > Webhooks): an address, the
  kinds it receives and a secret. Every notification of those kinds is sent as one plain JSON format, signed with
  HMAC-SHA256 of the body (`X-EAX-Signature: sha256=<hex>`), retried with back-off for about two hours, with a delivery
  log, a **Send test** button, switch off and new secret. **Never email**, anywhere in the product (D209).
- **Metamodel versions pushed down the hierarchy** (D84; the model tab **Push down**):
  - Every change made in the metamodel editor or the grids is kept with its metamodel version
    (`core.metamodel_version_changes`). The versions made since the last push go to the models **directly under** the
    model as **one package**, **forced** (made in each at once, with the defaults of new attributes filled in if
    chosen) or **offered** (each model's Model Admin **accepts** or **rejects** the whole package; rejecting needs a
    note and leaves the model diverged from its parent, kept in its lineage).
  - A model that has a package made in it gets a new metamodel version of its own; its Model Admin is asked whether
    to **pass it on** to the models under it, forced or offered, in the same way.
  - Forced is done with the parent's authority: the parent's Model Admin need not have a role on the models below.
  - A change that cannot be made in a model below (it removed the item, a lock, ...) makes the package **fail** there,
    saying why, and the model's Model Admins are told; nothing of it is kept in that model.
  - Versions made another way (a metamodel draft applied, a package uploaded) are listed but not pushed.
- **Change documents** (WF-018; model tab **Change documents**, and `#/change-documents/<n>`): a page for every change
  accepted into a model, a pushed metamodel package, a commit or a merge, with each change, its old and new values,
  defaults filled and who did it. Everyone on the model is notified with a link. On screen only (no download).
- **A request to yourself** is a note or a to-do (owner, 6 Nov 2026, D211): only you see it, nobody is notified, and it
  moves along like any request.
- **Super Admins** get every model's notifications, although they have no role on the models (D211).
- **MCP**: `list_my_notifications`, `list_my_requests`, `get_request`, `send_request` (resolving stays in the screens).
- **Change log** entries: requests sent and moved along, notifications resolved, pushes made, accepted and rejected,
  webhooks added, changed and deleted.

## Added after the first test (D211)

- **Administration > Services > Health now**: one green, amber or red verdict per service with its reasons, and in
  columns of their own the health check's response time, the container's state and Docker health (with the exit code
  and out of memory when it stopped), how long it has been up and its restarts. A summary of problems, warnings and
  healthy services at the top; anything the operations helper could not read is shown.
- **Administration > Containers** (IT and Super Admins): a **Summary** first, every container in one table with its
  health (green, amber, red), state, Docker health, CPU, memory and its share of the limit, processes, disk of its own
  layer and its volumes, up for and restarts, and a **total** row at the bottom; then for one container, its state, health check and its last
  results, what it uses now (CPU, memory, processes, network, disk), image, command, user, limits, mounts, ports,
  networks, environment (clear text) and labels; its **logs** (last 100 to 5,000 lines, filter, refresh); a
  **Terminal** (D214): a real interactive shell in the browser (vi, top, psql, tab completion, Ctrl+C), opened with a
  one-time ticket over a WebSocket to the operations helper, ending with exit, End session or leaving the page, or
  after `EAX_TERMINAL_IDLE_MINUTES` (15) without typing, its start and end in the audit trail; and **Run a command**
  (one command at a time, `cd` carries over, 60 seconds, in the audit trail as `container.exec`). Both are for IT and
  Super Admins and are switched off with `EAX_CONTAINER_CONSOLE=off`, the default for servers.
- **SQL**: the database is chosen from a list of the server's databases; **Keep the changes (commit)** commits the run
  (asked to confirm; audited), otherwise it is rolled back as before (D52 replaced).

- **Sign-in check for IT and Super Admins** (D215, after closing): when one signs in, the installation is checked in the
  background (containers, services, backups, the site certificate, versions, laptop default passwords on a server)
  and, if anything needs attention, one notification needing action lists every problem (red first) with a link to
  Administration > Services. Their previous open one is resolved by the new check; the webhooks hear it only when the
  list has changed.

## Demo

1. `.\eax clean-restart`. As `user_model_admin` (Model Admin of Fynbos Mutual (group) and Fynbos Life), open Fynbos
   Mutual (group) > **Metamodel** and add a mandatory attribute **Owner Unit** (text, default `Group IT`) to
   **Capability**.
2. **Push down** tab: the new version is listed with Fynbos Commercial and Fynbos Life below. Choose **Offer it**, tick
   **Fill existing entities with the default**, write a reason, **Push**.
3. The bell shows a notification; **Notifications**: "Fynbos Mutual (group) offers metamodel changes to Fynbos Life",
   needing action. Open Fynbos Life > **Push down**: **Accept**. The attribute is in Fynbos Life's metamodel, its
   556 Capabilities have `Group IT`, the notification is resolved ("Accepted by ...") and a change document is
   listed on **Change documents**.
4. As a Super Admin, Fynbos Commercial > **Push down**: **Reject** with a note. Fynbos Mutual's people get
   "Fynbos Commercial rejected ..." and the push shows rejected with the note.
5. Back in Fynbos Mutual (group), add a pick list and **Force** it: it is made in both models below at once; the
   Commercial one too, although `user_model_admin` has no role there.
6. As `user_architect`, **Notifications > New request** to `user_model_admin`: "Add a Hosting Tier attribute to Service". As
   `user_model_admin`: **Requests to me** > the request > **Start**, a comment, **Done** with a note. As
   `user_architect` the bell shows each step; the trail shows the comments and status changes.
7. Make an entity change as `user_architect` and ask for a commit: everyone on the model gets "asked for changes to be
   committed", needing action. Commit it as `user_model_admin`: the request notification is resolved ("Committed by
   ..."), everyone gets "committed changes" with a link to the change document (field, old, new).
8. As an IT Admin, Administration > System settings > **Webhooks**: add one pointing at a test receiver, **Send test**,
   then send a request; the delivery log shows it sent (or retried while the receiver is down). The receiver checks the
   signature with the secret.
9. Administration > Services: **Health now** green, amber or red per service. Administration > **Containers** > api >
   Logs, then **Terminal**: `cd eax`, `ls`, `top` (q to leave), `exit`; the audit trail shows the terminal opened and
   ended. Run a command: `id`, `df -h`. SQL: choose **keycloak** from Database; run an `UPDATE` with **Keep the
   changes** ticked and see it kept.
10. **New request** > **Note to myself**: a note only you see.
11. From your language model (MCP): `send_request` to someone, then `list_my_requests box=sent`.

## Checks

- `tests/sql/phase8_1_checks.sql` (as the API's login): tables, version, request and notification rules, the push-down
  setting kept to the metamodel of one model, nothing in reports.
- `pytest`: `tests/test_notifications.py` (routes, sign-in on every route, audit actions known, webhook signature, no
  email, MCP tools).

## Notes

- A package is replayed in each model below by translating every item it names to that model's copy (`origin_guid`,
  set when the model was created from its parent, and here for the items a package makes).
- Notifications and requests are never in the report views (`eax_report`).
- The webhook job runs every minute in the job runner (`eax.deliver_webhooks`).
