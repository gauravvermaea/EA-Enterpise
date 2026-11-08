# Build phase 13.0.5: common analysis

Goal: the counterpart of gap analysis. It finds what two or more models have in common, for example:
- capabilities, applications and processes shared across business units;
- what two companies both have after a merger;
- what is common enough to become a reference model.

- Version **0.14.5**, migration `0027_common_analysis`.
- Decision **D286**, from the owner's answers of 7 Nov 2026.
- It is architecture work, so it is a screen (D284): **Architecture work › Compare › Common analyses** (`#/compare/common`).

## Status: built, waiting for the owner's test

## Setting one up (everything is the person's choice)

1. **The models.** Two or more (up to 12), each as it is now or at one of its tags.
2. **What counts.**
   - **Common means in:** all of them, or at least N of them.
   - **Compare values:** for each common element, which fields agree and which differ.
   - **Compare relationships:** the same link between matched elements, and which models have it.
   - **Match by display ID too:** off by default. Models made apart often reuse IDs (CAP-001) for different things.
   - **Entity types:** the types at least two models have are ticked. **+ fields** chooses each type's fields, and you can
     also choose relationship types.
3. **Name it and choose where it is stored:** a project model you may change. Its people can open the analysis and record
   decisions.

**Matching**
- An element matches its counterpart when one is a copy of the other, or when they have the same type and name. Case,
  spaces and punctuation are ignored.
- Close names that did not match (Claims Assessment and Claim Assessment) are **suggested**:
  - confirm one and it becomes a hand-made match, kept for later runs;
  - reject one and it is never suggested again.
- Names that differ only in a number (Windows 2016 and 2022) are not suggested.

## The result

- **Tiles:** common elements (at the threshold), in all, common but values differ, in only one, common relationships.
- **Elements:**
  - One row per element, with a column per model (✓ links to the entity, or – where the model lacks it).
  - Filters: common, common with values that differ, not common, all; plus type and name.
  - Click an element to see its differing values side by side.
  - A decision and a note on each row, or on many ticked rows at once.
- **By entity type:** elements, common, values differ, and how many are in N models.
- **Relationships:** each link and which models have it.
- **Close names:** confirm or reject, then it compares again.
- **Results:** every run, with its totals.

**Actions:**
- **What counts…** compares again with changed settings. **Compare again** uses the same settings. Both keep the notes and
  decisions.
- **Tag the common elements:** in each model compared as it is now, the common (or ticked) elements get the tag
  `common: <name>`. That is one commit per model; a model you may not change is skipped and listed.
- **Make a model of the common elements:** a new project model copied from one of the models, holding the common (or
  ticked) elements and the relationships between them. Promote it to the library with the Model admin wizard.
- **Excel** (summary, elements, values that differ, relationships) and **Word**.
- **Delete:** the tags it added stay.

Making, comparing again, matching, tagging, making a model and the downloads run in the background (D273).

## API

| Method | Route | What it does |
|---|---|---|
| POST | `/commons/preview` | The set-up screen for the models chosen |
| GET / POST | `/commons` | List · make one (`store_in`, `name`, `sides`, `settings`) |
| GET / DELETE | `/commons/<a>` | One · delete it |
| POST | `/commons/<a>/refresh` | Compare again (with new `settings`) |
| POST | `/commons/<a>/suggestions` | `confirm` and `reject` close names |
| POST | `/commons/<a>/items` | A decision or note for elements |
| POST | `/commons/<a>/tag` · `/make-model` | Tag the common elements · a model of them |
| GET | `/commons/<a>/download?format=xlsx\|docx` | Excel or Word |

## How to check it (after `.\eax clean-restart`)

1. **Set it up.** Compare › Common analyses › + New. Choose Protea, Fynbos Commercial and Karoo Digital, then Next.
   - The types two of them have are ticked.
   - Set **at least 2 of 3**, store it in Protea and make it.
2. **Common elements.** Capabilities in both Protea and Fynbos show 2/3. Open "Common, values differ" and click an element:
   its owners and descriptions are shown side by side.
3. **Close names.** Confirm "Claims Assessment / Claim Assessment" and reject another. After comparing again, the first is
   one element and the second is not suggested again.
4. **Decisions.** Tick three rows and set **Standardise**. Then **What counts…**, set "all 3" and compare again: the
   decisions are still there.
5. **Tag.** Search Protea for the tag `common: <name>`.
6. **Make a model.** Make one of the common elements, copied from Protea, then open it in Model admin.
7. **Download.** Excel and Word.

## Not in this phase (to-do list)

- Comparing two results of a common analysis side by side.
- Saving its settings as a named profile.
