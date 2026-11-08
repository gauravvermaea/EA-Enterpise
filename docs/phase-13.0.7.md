# Phase 13.0.7: content framework, architecture repository link, project organisation (version 0.14.7, D299, D301, D302)

## Status: accepted and closed by the owner (8 Nov 2026, D322)

Migration `0029_content_framework`. Rebuild with `.\eax clean-restart`.

## What it delivers
- **Content framework tab on each project (D299).** A map of the content framework's fixed areas in ArchiMate's colours
  with, for each, how many entity types and entities, document types and documents sit there. A click opens the area
  as a tree: Metamodels › each project model › its entity types placed there › their entities; Documents › the
  document types placed there › their documents (every state, latest version). Entities and entity types open on their
  model; document types and documents open on Home › Documents, highlighted. "Not placed yet" lists what sits nowhere.
- **Where things sit.** An entity type: *Change entity type › Content framework area* in the metamodel editor (also on
  new types; copied with the model). A document type or a document: on the content framework tree (contributors). The
  shipped entity types and all the library's document types are placed by default (`eax/seed/content_framework_map.json`).
- **Architecture repository (D301).** A top-level area and menu link (*Architecture repository*, `#/repository`) and a
  project tab: the repository's parts as a map, each leading to what EA Explorer holds for it today; parts still to come
  are grey (their design and build is phase 13.0.9).
- **Organisation tab on each project (D302).** Who works on the project and their role on it, flat (no hierarchy): typed
  in, optionally linked to a user; the project's members and the stakeholder matrix added in one click; list or by role.
- **Stakeholders into the architecture (D302).** On the Stakeholders tab: *⇢ Organisation* lists them in the project's
  organisation; *⇢ Into the model* makes each a Stakeholder entity in a chosen project model (again: brought up to date).
- **Tasks tab (D298)**, built just before: a scratchpad of tasks per project.

## Checks
1. Open a sample project › Content framework: the map shows numbers; click *Logical Application Components*: the
   models' Application Component types and their entities; click an entity: its page opens.
2. Click a document type in an area: Home › Documents opens on its phase with the row highlighted.
3. In a model's metamodel, change an entity type's Content framework area; the project's map moves it.
4. Place a document type elsewhere from the tree; put it back (*Its default place*).
5. *Architecture repository* in the top menu and as a project tab: each white box opens the right page.
6. Organisation: add a person with a role; *＋ The project's members*; *＋ Stakeholders*; switch to *By role*.
7. Stakeholders: *⇢ Into the model*; the model has Stakeholder entities tagged with the project; run it again: no copies.
8. Back up the project and restore it as new: tasks, organisation and stakeholder links come back.

## Tagging to the content framework (D317, 8 Nov 2026; migration 0032)
**Accepted by the owner (8 Nov 2026)**, with D318 to D320 (Repository Area, the repository's links, the organisation
charter, project scope, project Quality tab, every user for admins).

Defaults are set by admins and inherited: built in › admin › parent project › the project.
- **Project admin › Template setup** (Super and Library Admins): *Deliverables and artifacts* (each one's areas, back to
  built in) and *Templates* (per library: each template's class areas, dashed, and areas of its own; **⬆ Upload a
  template…** into a library other than EA Explorer's own: the file, the deliverable or artifact it is for, that class's
  areas for every project, and the template's own areas).
- **Entity types**: Model admin › the model › Metamodel › Change entity type › Content framework areas (as before).
- **An entity**: ✎ Edit › Content framework (empty: as its type). A copy or child of the model inherits it.
- **A project**: the wizard's Documents table for its classes; **Content framework › 🏷 Tag items** for deliverables and
  artifacts, documents, entity types and entities (this project only), one by one or many at once; the Map's boxes have
  a ＋ that opens Tag items for that area, and an area's tree has "＋ Tag more items here".
- The **Repository Area** attribute no longer counts towards data quality (weight 0).

### Test steps
1. `.\eax clean-restart`, then Ctrl+F5.
2. Project admin › Template setup: change *Business model canvas* to two areas; Templates › TOGAF 10 › ⬆ Upload a
   template… for *Architecture Vision* with an area of its own.
3. Open a model entity › ✎ Edit › Content framework › Place it on its own… › an area; save.
4. As a Super Admin, Organisation base › Content framework › Tag items › Metamodel entity types: place *Capability*
   in another area. In the sample project the same type (in each of its models) shows that area, "from parent:
   Organisation base".
5. Sample project › Content framework › Map: press ＋ on a box, tick two rows, ＋ Add area to ticked… ; the Map's counts
   change and the area's tree shows them. ↺ Back to default puts them back.
6. Entities tab: place one entity elsewhere; it leaves its type's area and appears under "Entities placed here on their
   own" in the new one.
7. A Stakeholder sees the tags but cannot change them.
8. An entity's edit form no longer marks Repository Area as missing data quality.

## Repository Area and the repository map (D318, 8 Nov 2026)
9. Project admin › Template setup: each deliverable and artifact shows its **Repository area** (built in); choose another
   for one and put it back.
10. Model admin › a model › Metamodel › Change entity type: the content framework areas show ticked as built in, and a
    **Repository area** field (built in shown first). An entity's ✎ Edit shows its type's Repository area (no more
    Repository Area attribute on each entity).
11. Repository (top menu): click every item; each opens its screen. Decision log, Compliance and Capability assessments,
    Skills and Organisation structure are read-only lists of the projects you are on.
12. Architecture work › Models › 🗺 By level, and the level filter: models under Strategic, Segment, Capability (from their
    project's depth) and Transition (their role).
13. A project › Enterprise Repository (Project Scope): every item stays in the project; Foundation, Common systems,
    Industry, Organisation's own, External reference models and External standards open a menu with the project's and
    the organisation's choice.
14. Content framework › Tag items shows a Repository area column.
15. Project admin › Wizards: "The organisation's architecture charter" (Draft) › Review and approve… opens the Organisation
    base's charter, filled in; approve it. A new project's charter starts from it.
16. A project › Quality: its models' data quality only.
17. Repository (top menu): switch to "This project" and click Decision log: it opens the project's Governance log on
    Decisions. The landscape items open Models in tiles, filtered by level.
18. As a Super Admin or User Admin: Repository › Organisation structure opens on **Every user** (roles, projects, models);
    as an architect: only the people on your projects. Decision log and assessments: admins see every project.
