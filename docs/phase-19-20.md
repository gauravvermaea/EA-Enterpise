# Phases 19 and 20: merging a child into its parent (D359, D422 to D425)

Release 0.17.0, migration 0034 (with phase 21).

## Status: built (10 Nov 2026, batch 1, D421), waiting for the owner's test

## What it delivers
One merge-to-parent wizard in four steps:

1. **Send** (Model admin › a child › Wizards › *Send for merge into the parent*, the child's Model Admin): the changes
   are worked out three-way and shown before anything is sent; a note for the reviewers; one request open at a time.
   The parent's Model Admins and Committers get a notification that needs action.
2. **Review** (`#/merge-requests/<id>`): each change with its value at the start, in the child and in the parent now;
   pre-accepted, accepted, rejected (with a reason, required) or to decide; filters for conflicts, rejected and each kind.
   Metamodel additions are decided by a Model Admin of the parent. The sender may withdraw the request while it waits.
3. **Merge** (a reviewer, once every conflict is decided; a background task): the parent is tagged first, metamodel
   additions become one new metamodel version, everything else is **one commit** (rolled back from Changes › Commits).
   The child's new entities now point at their copies in the parent (so later merges and refreshes find them). The
   **merge report** (accepted, rejected with the reasons, anything not applied, the commit and the tag) is kept with the
   request and downloads as a Word document.
4. **Afterwards** the child's Model Admin (told by a notification) chooses: **freeze** it, or **refresh** it from the
   parent: it becomes what the parent holds now, all content, as one commit (tagged first), with a new starting point.

### Three-way (D423)
A child's **starting point** is a tag of kind *start*, taken when the child is made from its parent (with or without
content) and when it is refreshed. Against it: only the child changed a field → pre-accepted; only the parent → left
alone; both → a **conflict**. Added or removed in the child → a change; removed in one and changed in the other → a
conflict. A new entity is matched to one of the same type and name in the parent before it is added. Without a starting
point (children made before 0.17.0, or moved under the parent later) every difference is a conflict.

### Where
- Model admin › *Merge requests* tab on every project model: sent (as a child) and received (as a parent).
- `#/merge-requests`: the requests waiting for me (to review, or to freeze or refresh).
- API: `/api/v1/models/<m>/merge-requests[/preview]`, `/api/v1/merge-requests/waiting`, `/api/v1/merge-requests/<r>`
  and its `/decisions`, `/merge`, `/withdraw`, `/finish`, `/report` (eax/api/merge_back.py); rules in eax/merge_back.py;
  background kinds `mergeback.send`, `mergeback.merge`, `mergeback.finish`.
- Tables (rows only, D248): `core.merge_requests`; tags of kind `start` in `core.model_tags`.

### Replaced and dropped
The two "merge into the parent" wizards (choose by type and by item) are replaced by *Send for merge* (partial merges are
dropped, D359); the propagate wizards (parent into child, into a chosen child) stay as they were.

## Demo (laptop, after a clean restart)
- **Fynbos Commercial** sent to Fynbos Mutual (group), waiting for review, one conflict (Claim Payment's description).
- **Fynbos Life** merged: a conflict decided for the child, a relationship rejected with its reason; waiting for its Model
  Admin (user_model_admin) to freeze or refresh it. Download its report.
- **Karoo Digital refresh 2027** merged and refreshed; **Fynbos group operating model target** merged and frozen;
  **Protea claims transition 2027** withdrawn.
- Try it: change something in *Protea claims target 2028*, then its Wizards › Send for merge into the parent.

## Checks
- tests/test_merge_back.py: the three-way rules (each case), decisions, the migration, the wiring, the screens, the seed.
- Tried end to end on a fresh test database: send, decide, merge (one commit), report, refresh (the child equals the parent
  after it, and a new preview finds nothing).

## Upgrading
Migration 0034 adds the tables and the *start* tag kind. Children made before it have no starting point: their first
merge asks about every difference; after a refresh they have one.

## Not in this phase
Nothing of a merge request goes into a model's own backup package (they span two models; the infrastructure backup
carries them). No MCP tools for merge requests.
