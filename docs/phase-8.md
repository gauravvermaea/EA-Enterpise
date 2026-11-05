# Build phase 8: commits, drafts, approvals and merges

Goal: content changes stay private to their author until someone with the right role commits them; draft models are
approved or rejected; another model can be merged into a model with every conflict decided. Version **0.8.3**,
migration `0013_commits` (8.2 took 0.8.2 because it was built first, D161). Decisions D151, D165, D166, D167.

## Status: built, waiting for the owner's test

## What phase 8 delivers

- **Uncommitted changes (project models).** Every content change (new entity, change, retire, restore, delete,
  relationship added or removed) made on any screen (Data entry, the entity page and its edit form, the Grid,
  and later the draw.io diagrams through `POST /models/<model>/changes/batch`, D167) is kept as **your uncommitted
  change**. You see the model with your changes on top, marked *✎ changed, uncommitted*; nobody else does. The core
  tables, the history, the reports, graphs and MCP hold committed content only. Root metamodels and library models
  are not committed: their changes apply at once, as before. Existing content counts as committed.
- **Two new model roles** (People tab): **Committer** commits changes, their own and those others ask to commit;
  **History Viewer** sees everyone's commits (D151; others see their own). Model Admins and Model Sub Admins also commit.
- **Changes tab** on every project model, with the number waiting:
  - *My uncommitted changes*, by change set: each change with what it changes (before → after); choose rows or all;
    **Commit** (if you may), **Ask for a commit** (with a note), **Withdraw the request**, **Discard**; what was
    decided on your changes in the last 30 days (committed in commit N, or rejected with the reason).
  - *Waiting for a commit* (committers): each person's request with their note; clashes with content committed since
    are marked; **Commit** all or the chosen changes, **Reject** (with the reason the author sees) or **Send back**
    (with what to change).
  - *Commits*: the model's commits, newest first, yours or everyone's (History Viewer, Model Admin) with a person
    filter and *My changes*; open one to see each item before and after; **Roll back** the whole commit or chosen
    items, as a new commit. If a later commit changed the same thing you are told what and may roll back anyway.
- **Conflicts at commit.** When the content changed since a change was made, the commit stops and shows each clash:
  the field, what it was, theirs (committed since) and mine; choose mine, theirs or another value per field, or skip
  the change; **All mine** and **All theirs** settle the rest. A deleted target can only be skipped.
- **The entity page and its edit form** show your uncommitted changes to that entity: the changed fields are
  highlighted with the committed value they replace (*was ..., uncommitted*), with **Commit** (if you may),
  **Ask for a commit** (only these changes) and **Discard** right there (D167). A committer sees when others' changes
  to it wait for a commit.
- **Failing rules are shown before committing.** Each uncommitted change lists the rules its entity fails with it
  (for example *Owner is required*), on the Changes tab, in a committer's requests, and on the entity page and its
  edit form (*With your changes ... fails 2 rules*). A failing rule never stops a save or a commit (D48); the entity
  stays flagged until it is fixed, or a committer sends the change back to fix first.
- **Live updates** (E37): an open project model checks every 20 seconds; when someone else commits, a banner says who
  and offers **Reload**.
- **Draft models.** Creating, copying or deriving a model makes a draft (D131) that only people with a role on it see
  and work in. Its Model Admin asks for publishing; an approver (the creator, the Model Admins of the model it comes
  from or merges into, a Super Admin, or a Library Admin for library models) **approves**, **sends back** or now
  **rejects** it with a reason: it is archived and its Model Admin can **open it again**. The Models list shows
  *Draft models waiting for your approval*.
- **Every change and commit item links to its entity** (*Open entity ↗*, a new browser tab; a relationship opens its
  source entity), on the Changes tab, in a committer's requests, in the conflicts at commit and in a commit's items, so
  a reviewer can look at the entity before deciding.
- **Merge tab**, a screen of its own on every project model (not on the commit screen): 1 choose **with data** (the
  metamodel parts the data needs, and the entities, values and relationships) or **without
  data** (only the entity types, attributes and relationship types the model lacks, added by a Model Admin as one new
  metamodel version at once; the metamodel is not committed) and where from: **a model here** (read straight from
  it, no file to download and upload) or **a file** (a package from another installation, or edited in Excel),
  Merge or not, nothing in between (D169): a merge takes everything the other model has, metamodel parts included,
  so only a Model Admin merges, and only into a project model that is not read-only and has no lock of any kind.
  Otherwise the tab says why and offers nothing; the server checks again when the merge is read and when it is applied.
  2 see
  what merging would do, with a tab each for the conflicts (to decide), the new entities, the empty fields it fills
  and the new relationships, filtered by entity type or text; each matched entity links to its page; 3 merge.
  Upload a model package (Excel or zip from *Actions > Download*). To try it, the tab offers a **merge test file**
  (Excel or zip) made from the model itself: some descriptions and values changed (conflicts), empty fields filled,
  four new entities with relationships and two attributes the metamodel lacks; each download is different, so it can be
  tried again and again. With *without data* chosen the downloads hold the metamodel only. Any other model you may open
  can be downloaded there too, with or without data.
  Entities are matched by type and name; new ones are added, empty fields filled, relationships added; every field
  where both have a different value is listed to decide: mine, theirs or another value per row, or in bulk for the
  ticked rows, the rows the filter shows, or all of them (the same three choices, with one value typed for all);
  *Only those not decided* shows what is left. Types, attributes or
  relationship types the model lacks are added as one metamodel version. The
  merge is **committed at once as one commit** (D170: no commit step, as a merge is a thought-through Model Admin
  activity); everyone sees it straight away, and it is rolled back from *Changes > Commits* like any other commit.
- **API** (Swagger at `/api/docs`, tag *commits*): `/models/<m>/changes` (`?entity=` one entity),
  `changes/request|withdraw|commit|reject|send-back|discard|batch`, `/models/<m>/commits[/latest|/<id>]`,
  `/commits/<id>/roll-back`, `/models/<m>/merges[/<id>/apply|cancel]`, `/models/<m>/reject-publish`,
  `/models/<m>/reopen`, `/drafts/waiting`.

## Demo

1. `.\eax clean-restart` (new migration; new test users `user_committer` and `user_history_viewer`).
2. As `user_architect`, **Protea Insurance (demo estate)**: open *Claims Platform*, **Edit**, change Owner and the
   description, save. The page marks the changed fields (*was ..., uncommitted*). Add a new Application Component
   in **Data entry**. The **Changes (n)** tab lists them; **Ask for a commit** with a note.
3. As `user_committer` (another browser or incognito window): Claims Platform still shows the old values. Change its
   Owner yourself and **Commit** it from the entity page. Then **Changes > Waiting for a commit**: the architect's
   Owner change clashes; **Commit all**, choose *theirs* or *mine*, commit. The architect's open page shows the
   *committed changes, Reload* banner within 20 seconds.
4. **Changes > Commits**: open the commit, **Roll back** one item.
5. As `user_model_admin`: **Merge** tab, **Merge test file (Excel)**, then choose the downloaded file and **Read and
   compare**: decide the conflicts (or *Take theirs for all*), merge (the two new attributes are added to the
   metamodel); the content is committed at once (commit N in *Changes > Commits*). Try the zip, and *From a model here: Sample insurance model*.
   As `user_architect` the Merge tab says it needs the Model Admin role; with a lock set, that it is locked.
6. As `user_model_admin`: create a model from Protea (**Actions > Create a model from this**), **Request publishing**;
   the Models list shows it waiting for your approval; **Reject** it with a reason, then **Open the rejected draft again**.
7. As `user_history_viewer`: **Changes > Commits** shows everyone's commits; as `user_architect` only your own.

## Checks

- `tests/sql/phase8_checks.sql` (as the API's login). Ends with "phase 8 checks passed". Earlier phases' checks pass
  (3.1 now expects six model roles and the Committer in its messages).
- `pytest services/api/tests`: `test_commits.py` (roles and permissions, which fields a change touches, conflict
  resolutions, every content write goes through commits including the batch endpoint, the web Changes tab).
- Tried here against a database built from the migrations: record, overlay, request, commit, a conflict resolved
  per field, roll back of a commit with a delete in it (the relationships come back), discard, reject, request and
  commit of one entity's changes, merges from the zip and the Excel package, the draft reject and reopen.

## Upgrading from 8.2

`.\eax clean-restart`. Content already in models counts as committed.

## Not in phase 8

- Change history pages by person, and the full history view over commits: phase 9 (history and change log, D151).
- draw.io diagrams that create and change content: phases 28 to 29; they save through the batch endpoint, so they
  are committed like every other change (D167).
- Notifications by email or chat when a commit is requested: with notifications (phase 21).

## Test checklist (for the end-to-end testing phase, 36.1)

- [ ] Uncommitted changes are invisible to another user, in every screen, report and MCP tool, until committed.
- [ ] Commit, partial commit, reject, send back, withdraw and discard; the author sees each decision.
- [ ] Conflicts: mine, theirs, another value, skip; all mine and all theirs.
- [ ] Roll back whole and by item, also after a later commit (force); a deleted entity comes back with its relationships.
- [ ] Entity page and edit form: highlighted fields, commit and ask for a commit of only that entity's changes.
- [ ] Merge from zip and Excel, with and without missing metamodel parts, as Model Admin and as Architect.
- [ ] Draft models: approve, send back, reject, reopen; waiting list for each kind of approver.
- [ ] Live update banner when another person commits.
