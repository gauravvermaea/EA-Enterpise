# Build phase 13.0.4: admin by wizards, architecture on screens, five areas

Goal: every admin task (one that changes a model's, a project's or the system's shape, life or access) is a wizard, and the
architect's daily work stays on the model and project pages. The application is reorganised into five areas.

- Version **0.14.4**, migration `0026_model_wizards` (frozen_at, frozen_by and frozen_note on core.models).
- Decisions **D283** (model wizards), **D284** (admin by wizards, architecture on screens) and **D285** (five areas), from the
  owner's answers of 7 Nov 2026.

## Status: accepted and closed by the owner (8 Nov 2026, D323)

## The five areas (D285)

The start page shows five tiles, and the top menu shows the same five. A tile you have no role for is greyed out with the
reason.

| Area | Where | What is in it |
|---|---|---|
| **System admin** | `#/admin` | **Wizards** (new first tab), then settings, users, health, containers, backups, restores, quality, SQL, licences |
| **Model admin** | `#/model-admin` | The model list, hierarchy and metamodel drafts, with + New model and Upload. Pick a model to open its admin page: Wizards, Metamodel, People, Tags, Merge, Push down, Change documents, Backups, Family |
| **Project admin** | `#/project-admin` | + New project (the gallery), the projects you run, and the project library and templates. Pick a project to open its wizards |
| **Architecture work** | `#/work` | Your projects and your models side by side, most recently changed first. Each opens the project page or the model page |
| **Everything else** | `#/more` | Search, notifications, change log, model library, MCP, API, and every product tile |

- The model page has **no Actions menu and no admin tabs**. Its Model Admins get one link, **⚙ Administer this model**.
- Old links still work: `#/metamodel/<m>/metamodel`, `/people`, `/tags`, `/merge`, `/pushdown`, `/documents`, `/backups` and
  `#/metamodel/drafts` open in Model admin.
- On the work page the "+ Entity type", "+ Relationship type" and "+ Mapping" buttons are gone: they change the metamodel,
  which is done in Model admin.
- The project page has one link, **⚙ Administer this project**. Edit, Finish, Save as a template and Build the repository
  moved to Project admin.
- `#/admin/projects` moved to `#/project-admin/library`.

## Model wizards (D283)

These are on Model admin › a model › **Wizards**. Each card says what it does, or why you may not use it.

| Group | Wizards |
|---|---|
| Copy and derive | Copy with the parent-child link · Copy without the link · Copy from the library · **Split** part into a new model (by type, then by item; a child or separate; copied or moved) |
| Merge and propagate | **Merge into the parent and freeze** · Merge into the parent, keep working · **Propagate changes from the parent** · Propagate to a child |
| Metamodel | **Extend from another model** (entity types, relationship types, attributes) · Upgrade to another framework (ArchiMate 5) |
| Lifecycle | Lock or unlock (temporary) · **Freeze** (final; only a Super Admin unfreezes) · Tag it now · Restore a tag · Archive · Delete |
| Library and publishing | Promote · Request publishing · Approve and publish (or send back, reject) · Open a rejected draft again · Withdraw or restore |
| People and family | **Hand over** (Model Admins in and out, the owner) · **Detach or reparent** |
| Packages | Download · Download the metamodel · Upload a model |

**The merge wizards have five steps:**
1. **What and how.** Tag the target first (on by default), and freeze the source afterwards (for "merge and freeze").
2. **By type.** Entity types, relationship types and the metamodel parts the target lacks. Untick one to leave it out.
3. **By item.** Single entities and relationships. Relationships to an entity left out are left out too.
4. **Conflicts.** One winner for all of them, or decide one by one.
5. **Confirm.** Merging runs in the background (task `wizard.merge`) as one commit, which can be rolled back.

**Freezing**
- A frozen model cannot be locked or unlocked. The database lock under it goes only when a Super Admin unfreezes it.
- **Finishing a project** now offers, for each model: keep it, merge it into its parent, **merge it into its parent and
  freeze it**, or **freeze it**. A merge tags the parent first.

**The project's new-model step** gains **Copy from the library**: a new model from a library model, with its content or its
metamodel only.

## Architecture screens (D284)

- **Quality › Duplicates** (`#/metamodel/<m>/quality/duplicates`) finds entities of the same type whose names are the same,
  or very close. Names that differ only in a number (Windows 2016 and 2022) are not duplicates.
- Pick the entity to keep and tick the ones to merge into it, as one commit.

## System wizards (D284)

These are on System admin › **Wizards**:
- **Give a person access:** a person, then a role on one or more models.
- **Take a person's access away:** every model role they hold, then tick the ones to take away.
- **Back up now:** the whole installation, or every model.
- **Restore:** one model, every model, or the whole installation. Then pick the backup and confirm.
- Links to the backup schedules, the services and the restart.

Global roles stay in Keycloak; the wizards link there.

## API

| Method | Route | What it does |
|---|---|---|
| GET | `/models/<m>/wizards/family` | Parent, children, where it came from, frozen or locked |
| POST | `/models/<m>/wizards/tag-first` | Tag before a change |
| POST | `/models/<m>/wizards/merge` | Merge with what was chosen (background). Plan it first with `POST /models/<m>/merges` |
| POST | `/models/<m>/freeze` · `/unfreeze` | Freeze (Model Admin) · Unfreeze (Super Admin) |
| POST | `/models/<m>/detach` · `/reparent` | The parent-child link |
| POST | `/models/<m>/split` | Into a new model (background) |
| GET / POST | `/models/<m>/extend-preview` · `/extend` | Metamodel parts from another model (background) |
| GET / POST | `/models/<m>/duplicates` · `/duplicates/merge` | Likely duplicates; merge them |
| POST | `/models/<m>/hand-over` | Model Admins in and out, the owner |

## How to check it (after `.\eax clean-restart`)

1. **Start page:** five tiles. Sign in as user_architect: Model admin shows greyed out unless they are a Model Admin.
2. **Architecture work:** your projects and models. Open Protea: no Actions menu, and **⚙ Administer this model** is there.
3. **Model admin › Protea › Wizards › Split:** tick Capability, untick two capabilities, child, copy. The new child appears.
4. **On the child, add an entity, then Merge into the parent and freeze:** step 2 lists the types and step 3 the items.
   Untick one item and merge. The parent has the rest, a tag "Before merging…" exists, and the child is frozen (Lock is
   refused).
5. **Unfreeze it** as Super Admin. Then **Propagate changes from the parent**.
6. **Extend from another model:** take a type the model lacks. A new metamodel version is made.
7. **Hand over:** add user_architect; try to take everyone out (refused).
8. **Protea › Quality › Duplicates:** merge Fraud Scoring and Fraud Screening Service.
9. **Project admin:** + New project. A new model can now start "Copy from the library". Finish a project with "merge into its
   parent and freeze it".
10. **System admin › Wizards:** give user_architect Architect on two models at once, then take one away. Back up now. Restore
    one model as a new model.

## Not in this phase

- The new-view and new-report wizards (later; D284).
- The architecture screens themselves, to be designed with the owner (D284).
- Stopping a merge that is running.
