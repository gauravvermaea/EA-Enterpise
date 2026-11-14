# Smaller images: the proposal (R3.6)

The owner, 13 Nov 2026: "Before we do this I want to understand how slim they will get and its impact. Then we will
decide." This is that proposal: per image, what would change, roughly how much smaller it gets, and what is lost. Nothing
here is built yet.

**The figures are estimates** from the Dockerfiles and the usual sizes of the base images; they are not measurements of
your laptop. To measure before deciding: `.\eax footprint before-slim` now (System Admin › Footprint shows it), and the
same after any change, so each step is shown with its real before and after (D620).

## Quick wins (no loss)

These change nothing anyone uses and are worth doing whatever else is decided.

| Image | Change | Saves (estimate) | Impact |
|---|---|---|---|
| api, library, views (python:3.12-slim) | `pip install --no-cache-dir` (today pip keeps its download cache in the image) | 20 to 60 MB each | none |
| api, library, views | `apt-get upgrade` then remove the package lists in the same layer (today the upgrade's leftovers stay in a layer) | 5 to 20 MB each | none |
| api (also operations, personal, setup) | `coverage` installed only in the test runner, not in the running API | about 5 MB | none: coverage is measured by the test runner |
| ops (docker:29-cli) | `git` only where updates need it: kept (updates need it); nothing removed | 0 | none |
| every image | a `.dockerignore` for the images that have none (ops, backup, superset) | small, and faster builds | none |

## Bigger steps (each with a cost)

| Image | Change | Saves (estimate) | What is lost |
|---|---|---|---|
| api, library, views | multi-stage build: packages built in one stage, only the installed files copied to a clean `python:3.12-slim` | 50 to 120 MB each (compilers and headers that some packages pull in) | nothing at run time; builds a little slower |
| library, views | their own small requirements (already separate: 4 packages each) instead of the API's 16: already done | 0 | none |
| api, library, views | a distroless Python base instead of slim | another 40 to 70 MB each | **no shell**: the container's Terminal tab (R2.15) and `docker exec ... sh` stop working for these; debugging gets harder. Not recommended (the owner asked to keep things inspectable) |
| reports (apache/superset:4.1.2, the largest by far, 1.5 to 2 GB) | a newer Superset release on a slimmer base; drop the example data and unused database drivers | 300 MB to 1 GB | the Superset examples; a Superset upgrade to test (all reports re-checked, R4.1). Its 598 findings (R3.12) shrink with it |
| drawio (jgraph/drawio, Tomcat on Ubuntu, about 600 MB) | none of ours; a newer tag when it is smaller | depends on the upstream image | none |
| documents (Mayan) and keycloak | none of ours; upstream images | 0 | none |
| test runner (about 1.5 GB: Chromium and the scanners) | stays as it is: built only for tests, not part of the running installation | 0 | none |

## At run time (memory and CPU, not image size)

Memory and CPU limits per container in the config file (sized for laptop and server), fewer API workers when idle on a
laptop, log size and rotation limits: these need the measured figures (`eax footprint` while the self-test runs) to set
sensible numbers, so they come after the measurement.

## Recommendation

1. Do the quick wins now (no loss).
2. Measure (`eax footprint before-slim` and after the quick wins).
3. Multi-stage builds for api, library and views (no loss at run time).
4. Reports: decide separately, with R4.1 (detailed report testing) in place first, since it changes the Superset version.
5. Keep a shell in every image (no distroless), so the Terminal tab keeps working.
