# Phase 13.0.7: content framework, architecture repository link, project organisation (version 0.14.7, D299, D301, D302)

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
