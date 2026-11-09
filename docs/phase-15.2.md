# Phase 15.2 — The library: organisation and project libraries with pages

Status: **built (owner, 9 Nov 2026, D346 to D351), in release 0.15.1.** Replaces the earlier idea of integrating an
open-source wiki (D334): EA Explorer builds the library itself, as a separate service.

## What it is — keep it simple (owner, 9 Nov 2026)
People make **simple pages, or tables, full of links**: to documents, to models and projects, to web pages. Writing
long text and uploading files is not the point; **finding things (search) is**.
- **Two kinds of library**: the **enterprise library** (Enterprise library on the menu, `#/enterprise-library`) and
  each **project's library** (the project's **Library** tab). The model library (`#/library`) is a different thing.
- A library is a **folder tree** of any shape holding:
  - **pages**: headings, text, bulleted lists, **tables** and lists of **links** (no images, no layout, no page
    templates). Links are written `[words](address)` anywhere, or chosen with **🔗 Insert a link**;
  - **links**: to a web address, or into EA Explorer: a model, a project, a project's document (downloaded), a
    Business Model Canvas, a viewpoint, a reference library entry or another library page;
  - **files**: an upload is allowed (at most `EAX_LIBRARY_MAX_FILE_MB`, 25 MB by default) but is not the main use.
- **Search is the centre of it**: one box over titles, descriptions, tags, the words of pages, link names, the text
  inside uploaded files (PDF, Word, PowerPoint, Excel, text) and folder names; whole words and the start of words,
  then parts of words; results grouped by library, with the matching words marked. In the enterprise library it also
  covers the project libraries shown there.
- **A project's library can be shown in the enterprise library** (read only there, under Project libraries).

Links into EA Explorer are kept as `ea:` addresses by ID (`ea:model:<model>`, `ea:project:<project>`,
`ea:entity:<model>:<entity>`, `ea:viewpoint:<model>:<code>`, `ea:document:<project>:<document>`,
`ea:canvas:<project>:<canvas>`, `ea:reference:<entry>`, `ea:page:<library>:<entry>`), so a rename shows at once.
Anything else (`javascript:` and the like) is refused.

## A pluggable module (owner, 9 Nov 2026, D350)
An organisation may keep its library somewhere of its own (an intranet or document site) instead of ours. One
organisation-wide setting (System admin › System settings › Enterprise library) says which:
- **ours** (the default): everything on this page.
- **link**: a web address (`Enterprise library link`) and, if the site has one, a search address with `{q}` for the
  words (`Enterprise library search link`). The Enterprise library menu opens that address in a new tab; the page
  offers a search box that passes the words on.
- **off**: no enterprise library.

**Each project keeps its own library whichever is chosen.** A project admin may give the project an address of its own
instead (⚙ Library settings on the Library tab); the tab then opens it, and what was in the library here is kept.

The service itself has a switch like Reports and Documents (`EAX_SERVICE_LIBRARY`, `.\eax service library off`): off,
the library pages say so and its content is kept.

## Who changes what — light moderation (owner, 9 Nov 2026, D349)
- **Project library**: any project member changes it (not while the project is frozen); it shows at once.
- **Enterprise library**: anyone signed in changes it; **it shows at once**. Nothing waits for approval.
- Every change is kept (who, when, before and after): **🕘 Recent changes** for a library, **History** for an entry,
  with **Before and after** for a change.
- **Undo**: Library Admins and Super Admins in the enterprise library; the project's admins in a project library.
  An undo is itself a change, kept in the history. Removing a folder removes what is in it; its undo brings both back.
- A page being edited is held for its editor (others see who) until they save or cancel, or for 30 minutes.
- **Shown in the enterprise library**: the project admin switches it on or off; it shows at once, read only.

## Why built and not a wiki container (agreed)
Permissions that follow project membership and links into EA Explorer that survive renames are not in the
open-source wikis that fit the stack (as found on 9 Nov 2026); they would be built around a wiki anyway, and a wiki
would add a second sign-in and permission model, a second search, a second store for files and one more database to
back up. The ready-made parts a wiki would save (an editor, page history, a page tree) are small beside that.

## Architecture
- **A separate microservice** (`services/library`, container `library`, port 8100): **its own database
  (`eaxlibrary`), schema (`lib`), login (`eax_library`), migrations (`libsvc/migrations`) and API**
  (`/api/library/v1/...`), behind the same proxy (`location /api/library/`). No other service reads its database.
- On start it makes its login and database when missing (as the PostgreSQL superuser), then runs its migrations, each
  once (`lib.schema_versions`).
- **Laptop and single-server installs**: its database runs on the **same PostgreSQL server** (separate database,
  schema and login); `EAX_LIBRARY_DB_HOST` moves it. **Production: its own PostgreSQL container or server**
  ([story-load-balancing.md](story-load-balancing.md)).
- Python and Flask, like the main API. Rules in Python, none in the database (D248).
- **Sign-in**: the same Keycloak token. The service asks the main API who the person is (`/api/v1/me`) and their
  roles in a project (`/api/v1/projects/<p>`), kept for a minute.
- **For the main API only** (`/internal`, with `EAX_LIBRARY_KEY`): a project's library out of and into a project
  backup, and the sample libraries.
- **Screens** are in the EA Explorer web app (`Libraries.jsx`) and call the library API.
- **Backups**: infrastructure backups dump every database, this one too. A **project backup** holds the project's
  library (`library/library.json`); restoring it puts the library back, with its links moved to the restored
  project's documents and canvases. The library off or down never stops a backup or restore: it says what was left out.
- **eax**: `service library on|off`, `logs library`, health and the passwords list, in all four forms (D331).
- **Health**: the Library row on Heartbeat › Services and the start-up status.

### Settings (work/eaexplorer.env)
| Setting | What |
|---|---|
| `EAX_SERVICE_LIBRARY` | on (default) or off |
| `EAX_LIBRARY_DB_PASSWORD` | the `eax_library` login's password (a laptop config file from before 0.15.1 falls back to `EAX_DB_PASSWORD`) |
| `EAX_LIBRARY_KEY` | the main API's key for `/internal` (laptop: `eax-library-laptop`; setup refuses that on a server) |
| `EAX_LIBRARY_DB_HOST`, `_PORT`, `_NAME`, `_USER` | where its database is (default: the main PostgreSQL server, `eaxlibrary`, `eax_library`) |
| `EAX_LIBRARY_MAX_FILE_MB` | the largest upload (25) |

## Technology (as built, D351)
| Part | Technology |
|---|---|
| Folders, entries, history | PostgreSQL (`eaxlibrary`), rules in Python (D248) |
| Files (the occasional upload) | Kept in the library's own database (with their text, for search), so the service needs nothing else |
| Page editor | A simple blocks editor of our own (heading, text, list, table, links; move up and down), with a picker for links into EA Explorer |
| Page storage | The blocks as JSON (the master) and their plain words for search |
| Search | PostgreSQL full text (`simple` dictionary, prefix matching) with an excerpt, then trigram matching for parts of words |
| History and undo | Every change kept with its before and after; undo puts the before back |

## Sample data (AGENTS.md)
Made once on a laptop, after the sample projects and canvases (`seed/sample_library.py`, run by the library service):
- the **enterprise library**: folders (one inside another), a *Start here* page with a table of models and a list of
  projects, a principles table, links to reference library entries, a review checklist, a file, useful web links,
  and history (a page changed, a link added and removed, to undo);
- **three project libraries** with an overview page linking the project's models, documents and canvases; the first
  is shown in the enterprise library;
- a project (**Fynbos Board reporting pack**) whose library is at its own address.

## Left out to keep it simple
Comments, page templates, images in pages, co-editing, export of a folder, and moving the organisation reference
library (13.0.8) and the projects' Reference areas into the service (they stay as they are; a library page links to them).
