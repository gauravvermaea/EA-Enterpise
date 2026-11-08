# Phase 13.8: sample content (D326)

**Accepted and closed by the owner, 8 Nov 2026 (D337).**

## Status: built (8 Nov 2026), waiting for the owner's test

Seed data only (owner: "sample projects as projects, no guides"), laptop only, made once at start-up after the sample
projects (`eax/seed/sample_content.py`, a step in `eax/seed/later.py`). Everything is invented.

- **Karoo Re cloud migration (sample)**, mid-way: governance records in every approval state (a decision approved by
  the sign-off people, one approved with a reason, a dispensation waiting, an issue rejected, a risk in draft, a
  compliance and a capability assessment approved); its charter approved; six people with skills on the Organisation
  tab; a weekly sync, a phase gate, a walkthrough and a rehearsal on its calendar; phases P and A complete and steps of B
  done; the Architecture Vision deliverable also in Stakeholders; two sheets: an application portfolio (15 rows) and
  migration costs.
- **Protea build or buy (sample)**: complete, every phase complete.
- **Fynbos Pet Insurance launch (sample)**: as just set up.
- **The organisation**: four Architecture Board members, the board's monthly meetings and reviews on its calendar, a link
  in each of the reference library's four folders, a vendor contracts sheet.

## Test steps
1. `.\eax clean-restart`, Ctrl+F5 (the content loads in the background after the sample projects).
2. Karoo Re cloud migration (sample): Governance log (every approval state), Organisation, Calendar, Phases, Sheets,
   Charter (approved).
3. Repository: Decision log, Organisation structure, Skills, Calendar, Architecture board, Performance measurement
   (governance health and sign-off turnaround now have figures), the reference library's four parts.
4. Architecture work › Projects: Protea build or buy (sample) at 100%.

## Also in this release: principles (D327)

Checks:

1. As a Super Admin, open Project admin › **Principles**: the Organisation base's principles, a grid per area with
   name, statement, rationale, implications and "Below" (🔒 enforced, or optional).
2. **＋ Add an area** (say AI): the empty area shows with "remove the area"; it cannot be removed once it has principles.
3. **＋ Add a principle** with "Enforced" ticked, and another unticked; **Enforce / Make optional** flips one.
4. On a row, **＋ Refine it**: the new principle is shown nested under its parent (▾ / ▸ collapses); in another area it
   says "refines X (area)". A principle cannot refine itself.
5. Create a project: it has every principle of the base. Enforced ones are locked (🔒); an optional one can be **taken
   out**, and the Base tab does not offer it again. Nesting is kept in the project.
6. In the project, add a principle of its own that refines an enforced one: nested under it, never enforced.
7. A project backup carries the principles' areas and refinements.

## Also in this release: upgrading a backup on restore (D328)

Checks:

1. Back up a project: its list shows nothing about upgrading (it is the current format, 2).
2. Restore a project backup made before 0.15.1 (format 1): the message says "The file is from EA Explorer before
   0.15.1 (project backup format 1); upgraded: ..." and lists what was filled in: the steps' opened and closed dates,
   governance records as Draft with a history, principle areas.
3. In the restored project: the governance log's records are Draft (they can be sent for approval), the steps show
   when they were opened and closed, and the Principles tab shows the areas.
4. A backup file from a newer EA Explorer is refused with "Upgrade EA Explorer first" (project and model backups).
5. A project with calendar events backs up and restores with its events (times kept).

