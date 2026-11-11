# ADM iteration types on projects (version 0.19.0)

Built 11 Nov 2026; to be accepted. Decisions D571 to D574; migration 0048.

## What it is

TOGAF groups the ADM phases into iteration cycles. A project's current ADM cycle is one of them, and the iteration
decides which phases are **enabled**. The others are **frozen**: read only, never hidden and never deleted. Choosing
another iteration opens them again exactly as they were.

| Iteration | Phases enabled |
| --- | --- |
| Full cycle | Preliminary, A, B, C, D, E, F, G, H |
| Architecture Capability iteration | Preliminary, A |
| Architecture Development iteration | B, C, D |
| Transition Planning iteration | E, F |
| Architecture Governance iteration | G, H |
| Custom iteration | the phases ticked (at least one) |

Requirements Management and work across the cycle are enabled in every iteration. Phase C's data and application parts
follow C. The owner first proposed Architecture Development as A to F and Architecture Capability as the Preliminary
phase only, and accepted TOGAF's mapping instead (D571).

## On the project page

- Creating a project is unchanged.
- Under the project's title: **ADM iteration:** with its label, for example *Transition Planning iteration (E, F)*,
  then **🔒 frozen:** with the phases left out, **Change…** and **Iteration history (n)**.
- Until someone chooses, the cycle runs as a Full cycle and the page asks **Which iteration is this?** with **Choose…**.
- **Change…** opens the **ADM iteration** pop-up: one radio button per iteration; for Custom, a checkbox per phase
  (Preliminary, Phase A to Phase H); the frozen phases as they will be; an optional note; **Save**.
- **Any user who can open the project** may change it, at any time, except while the project is finishing, frozen,
  merged or closed. Every change is kept per ADM cycle: when, who, from, to and the note; a new cycle starts unchosen.
- The **ADM wheel** greys frozen petals and shows 🔒; Requirements Management stays live.
- **Plan › Phases**: frozen phase tabs show 🔒; open one and everything is there, read only, under the note
  "Phase B isn't part of this Transition Planning iteration. Change the iteration to work on it."
- **Tasks** in a frozen phase show **⏸ paused**; the **content framework** marks frozen phases 🔒; the **project
  report** gives the iteration and marks phases "(frozen in this iteration)".

## In the API (D573)

The rules are in Python (`services/api/eax/iterations.py`, D248); `services/web/src/iterations.js` is its twin for the
screens. Every change in a frozen phase is refused with **409** and the message above: marking a phase, steps and sub
steps, choosing or adding documents, from templates, uploads, files, titles, accepting, hiding, check out and check in,
offering a template, raising and deciding sign-offs and a document's kind. Reading and downloading are never refused.

| Call | What |
| --- | --- |
| `GET /api/v1/projects/<project>/iteration` | `{iteration, iterations, history}` |
| `POST /api/v1/projects/<project>/iteration` | `{iteration, phases?, note?}`; `phases` only for `custom` |

The project's detail also carries `iteration` (with `frozen_phases` and `may_change`), `iteration_history` and the
catalogue `iterations`. A change is in the change log as "Changed a project's ADM iteration".

## Stored

`proj.iteration_changes` (migration 0048): project, ADM cycle, iteration, phases enabled, the previous iteration and
phases, who, when and a note. The latest row of the current cycle is the project's iteration; no row means a Full
cycle, not chosen. Rows only: no database logic (D248).

## Carried everywhere (D574)

- **MCP**: `project_iteration(project)` reads it; `set_project_iteration(project, iteration, phases, note, confirm)`
  previews the change and makes it on confirm.
- **Project backups** include the iteration history. **Project templates** may set an iteration
  (`"iteration": {"code": "custom", "phases": ["A", "B"]}`); a template made from a project keeps its chosen one.
- **Self-test** smoke check: reads the iteration, sets Transition Planning, checks a change in Phase B is refused (409),
  then sets a Full cycle.
- **Sample data** (`seed/sample_iterations.py`): Protea Target Architecture 2028, a Full cycle; Protea Claims
  Transformation 2028, Architecture Development then Transition Planning (two changes); Karoo Operations architecture
  health check, Architecture Governance; Protea broker portal, Custom (A, B, E); Karoo Re as-is documentation, none
  chosen, so its page asks.

## Tests

`services/api/tests/test_iterations.py`: the mapping, the enabled phases of every iteration, custom checks, labels, the
guard's 409, that every phase-changing API function guards, the migration, the web twin and screens, and that backups,
seed and MCP carry it. On-screen help: the ADM iteration pop-up, its note and the Iteration history button.
