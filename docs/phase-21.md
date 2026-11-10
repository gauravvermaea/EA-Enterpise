# Phase 21: dedupe within a model (D361, D426 to D428)

Release 0.17.0, migration 0034 (with phases 19 and 20).

## Status: built (10 Nov 2026, batch 1, D421), waiting for the owner's test

## What it delivers
- **Find** (a model's Quality tab › Duplicates): likely duplicates of every type, or one type, by name: the same once
  case, spaces and punctuation are ignored, or very close, close or loosely alike (names whose numbers differ are
  versions, not duplicates); and, for one type, by the **same values in chosen attributes** (for example the same vendor
  and version), with or without names. Matches that overlap are one group; each says why and how alike.
- **Compare and merge**: a pair or group side by side, every field with each entity's value and which differ; untick any
  to leave out; choose the **one kept** and, field by field, **whose value it takes**. The others' relationships move to
  it (one it has already, or one between the entities merged, is dropped) and they are removed.
- **The person's own change** (anyone who may change the model): committed at once as one commit when they may commit
  (rolled back from Changes › Commits), else left as their changes for a committer.
- **Old IDs still find the survivor** (D427): a link to a merged entity opens the one kept with a note; search finds it by
  the old display ID or name.
- **Data entry warns** as a name is typed when it looks like an existing one (links to them); it never blocks.
- API: `GET /models/<m>/duplicates?type=&attributes=&closeness=&names=`, `POST /models/<m>/duplicates/compare`,
  `POST /models/<m>/duplicates/merge` (with `choices`), `GET /models/<m>/content/similar`; rules in eax/dedupe.py;
  table `core.entity_aliases` (rows only, D248).

## Demo (laptop, Protea Insurance (demo estate))
- Quality › Duplicates: "Claims Platfrom" beside Claims Platform, "Quote-Engine" beside Quote Engine; choose Application
  Component and tick Vendor and Version to find "Payments Gateway" beside the Payments Hub.
- "Mobile Claims App" was merged into the Mobile App by user_committer (commit in Changes); its old ID APP-0032 still
  finds the app. "Document Store" was merged into Document Management by user_architect: their uncommitted changes.
- Data entry › Application Component › + In a form, type "Claims Platfrm": the form says it looks like Claims Platform.

## Checks
tests/test_merge_back.py (closeness, grouping, relationships moved and dropped, the screens, the seed); tried on a fresh
test database (find, compare, merge as committer and as architect, the alias).

## Not in this phase
Aliases are not carried in a model's own backup package (the infrastructure backup carries them). No MCP tool.

## As built: a tab of its own (0.19.0, 10 Nov 2026, D541, D542)
Duplicates is now its own tab on the model page (Quality › Duplicates, `#/metamodel/<m>/duplicates`; the old
`quality/duplicates` link opens it). The person chooses the entity type (typed, with near spellings), how close the names
must be and any attributes, then presses **Find duplicates**; nothing is looked for before. Nothing found says **No likely
duplicates found** with what was searched. **⬇ Excel** downloads the result (`GET /models/<m>/duplicates/xlsx`, same
arguments): sheet Duplicates, one row per entity of each group with a link back; sheet About. Tests:
tests/test_dedupe_xlsx.py, tests/test_drawn_view_screens.py::test_type_dropdowns_search_and_duplicates_tab.
