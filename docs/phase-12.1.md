# Build phase 12.1: start-up in two tiers, open pictures in draw.io

Goal: sign in within a minute or two of starting instead of five to seven, see what is still starting, and open
pictures straight in the platform's draw.io. Version **0.13.1**, migration `0021_startup`. Decisions D255 (start-up in
two tiers), D256 (open in draw.io) and D257 (the grid's commit icon), agreed with the owner on 6 Nov 2026 before building.

## Status: built, waiting for the owner's test

## What phase 12.1 delivers

### Start-up in two tiers (D255)

- **The core starts first**: `db`, `setup`, `proxy`, `web`, `keycloak` and `api` (every copy). Before the API starts it
  applies the database upgrade and loads only the built-in models (ArchiMate 4, the insurance reference model, the
  viewpoints and audiences, the laptop test users' roles). Keycloak now has a health check (it answers a realm).
- `eax up` (and `run`, `debug`, `clean-*`) waits until the API and Keycloak are **healthy**, showing each change, then
  says **"EA Explorer is ready after N s: you can sign in."**
- **The rest starts after it, in the background**: `reports-init` and `reports`, `dms-broker` and `dms`, `drawio`,
  `backup` and `ops`, in a hidden `eax start-later` with its own log (`work/logs/eax-<time>-start-later.log`). The
  window is free at once.
- **Inside the API, after it has started** (eax/seed/later.py, one step at a time, each its own transaction): the sample
  insurance model; on a laptop the test models (Fynbos Mutual group, Fynbos Life and Commercial, Karoo Re and its rules,
  the Lean EA metamodel with Karoo Digital and a model in each state, Protea Insurance, the data quality samples), the
  History tab samples, icons, roles and report views, the demo estate's tags, gap analyses and sheets; then **each
  model's first data quality measurement** (models never measured), so the highlights show from the start. Each model
  appears as soon as its step is done. A failed step is shown in red and the others carry on; the next start tries it
  again (steps already loaded are skipped). With several API servers one runs it, the others skip it.
- **Reports** wait for the sample data before adding their typed datasets (up to 15 minutes).
- **`--wait-all`** on `up`, `run`, `debug`, `clean-run`, `clean-debug` and `clean-restart`: starts the rest in the same
  window and waits until everything is up (up to 30 minutes), showing each change.

### The start-up status (D255)

- **In the header, for everyone**: each part still starting or down with its colour and word (*Reports starting*,
  *Documents down*, *Diagrams starting*, *Sample data loading 3 of 9*); a single green **All up** once everything is up.
  Green up, amber starting (pulsing), red down, grey off. It is read every 8 seconds while anything is starting, every
  minute after.
- **Click it** for every part with what it is doing (e.g. *reports-init: setting up*, *dms: Exited (1)*) and
  **↻ Check again**; IT and Super Admins also get **Every container →**.
- **Administration > Containers**: a line with every part at the top; each container in the list with its start-up
  colour and word; the summary table has a **Start-up** column (up, starting, down, off, and **1st** for the core or
  **2nd** for after it).
- How it is worked out (eax/startup_status.py): a part that answers its health check is up; otherwise its container's
  Docker state says starting (created, restarting, health starting, set-up running) or down (exited with an error,
  unhealthy); switched off is off. Without the operations helper the first 15 minutes count as starting. The sample
  data's progress is kept in `core.startup_parts`. Kept 8 seconds, so many screens cost one check.
- `GET /api/v1/startup` (signed in; containers for IT and Super Admins), `GET /api/startup` (no sign-in; the parts'
  states only, used by the Reports set-up).

### Open pictures in draw.io (D256)

- Every **.drawio** button is now **Open in draw.io**: the ER diagram, the entity graph, the hierarchy map, the model
  tree, the relation matrix, the value stream map, the roadmap, and the viewpoint heat map and matrix.
- The picture opens in a **new tab** in the platform's draw.io (`/drawio/`), named after the picture. The diagram travels
  in the address after `#` (compressed the way draw.io does it; that part never leaves the browser), so nothing is
  downloaded. Edit it there; save or export it with draw.io's **File > Save as** or **File > Export as** (.drawio, PNG,
  SVG, PDF...).
- While draw.io is starting, down or off, the new tab says so (try again in a moment, or ask an administrator to switch
  it on).
- Saving a diagram back into the model is phases 28-29 (D174).

### The grid's commit on the left (D257)

- After a row is saved, one icon **⇪** shows on the left after its number: commit that row now (Committers, Model Sub
  Admins, Model Admins) or ask a committer to (purple). Hover shows how many changes.
- The Uncommitted column is gone; right-click a row for **Discard this row's uncommitted changes**. Commit all and
  Discard all stay on the toolbar.

## Demo

1. `.\eax clean-restart`. Watch the window: *Starting the core first*, the API and Keycloak going from *starting* to
   *healthy*, then **EA Explorer is ready after N s: you can sign in** and *Reports, documents, draw.io... start now in
   the background*. The window is free.
2. Sign in at once as `user_super_admin`. The header shows amber parts (*Reports starting*, *Diagrams starting*,
   *Sample data loading 2 of 11*...). Open **Models**: the sample and test models appear one by one as the sample data
   loads.
3. Click the status: each part with what it is doing. **Every container →**: Administration > Containers with the
   Start-up column (1st and 2nd) and the line at the top.
4. Wait: the parts turn green one by one, then the header shows **All up**.
5. Protea Insurance > **ER diagram** > **Open in draw.io**: a new tab opens draw.io with the diagram, named
   *Protea Insurance (demo estate) - metamodel.drawio*. **File > Export as > PNG** downloads a picture.
6. Grid of Role: change a description, ✓ to save the row; **⇪** shows on the left; click it: *Committed*.
7. `.\eax down`, then `.\eax up --wait-all`: the window waits until everything is up and says *Everything is up after
   N s*.

## Checks

| # | Check | How | Expected |
| --- | --- | --- | --- |
| 1 | Sign in early | `.\eax clean-restart`; sign in when it says ready | within about two minutes of the core starting; Reports and the sample data still amber |
| 2 | Background log | `work\logs\eax-*-start-later.log` | the second tier's `docker compose up`, then *Everything is started* |
| 3 | Sample data | header and Models while loading | *loading n of m*, models appearing; then green |
| 4 | First quality measurement | a project model's Quality tab after *All up* | a measurement by *system*; highlights on the grid |
| 5 | Down shows red | `docker stop eaexplorer-drawio-1` | header *Diagrams down* in red within a minute; Open in draw.io says it is not running; `.\eax up drawio` turns it green |
| 6 | Off shows grey | Administration > System settings > Services: draw.io off | the header leaves it out of *All up* (grey in the details) |
| 7 | `--wait-all` | `.\eax up --wait-all` | waits, shows each change, ends with *Everything is up after N s* |
| 8 | Open in draw.io | every picture's **Open in draw.io** | a new tab with the picture in draw.io; nothing downloaded |
| 9 | Grid commit | save a row, then ⇪ | committed; right-click discards instead |
| 10 | Several servers | `.\eax servers 2`, then `.\eax down` and `.\eax up` | one server's log says it loads the rest, the other *another server runs later; skipped here* |
