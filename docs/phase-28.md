# Phases 28 and 29 — Drawn views in draw.io (design agreed, to build)

Status: **design agreed with the owner, 9 Nov 2026 (D354, D355); not built yet.** The repository is the truth; a drawn
view only shows it. draw.io is how a view looks and how it is laid out, never where entities are made.

## The rules (owner, 9 Nov 2026)
1. **Entities are made in the platform, never on the canvas.** A shape that is not bound to an entity cannot be added
   as an element; attributes cannot be edited on the canvas.
2. **Only relationships are added from draw.io**, and only the ArchiMate relationship types the metamodel allows
   between the two types. Adding one opens a form for its attributes (required ones checked). It becomes the person's
   **uncommitted change**, like every edit (shown dashed until committed).
3. **Deleting** an object removes it from the view only, never the entity. Deleting a line **hides** it in this view;
   relationships are never deleted from a canvas.
4. **Hide and show**: right-click a line, *Hide*; right-click an object, *Show hidden relationships*. The hidden list is
   kept with the view.
5. **Relationships are drawn automatically**: placing an entity draws every relationship in the model between it and
   the objects already on the view (except hidden ones); a parent-child link shows as a line only when the child is not
   nested in its parent.
6. **Nesting must match a relationship**: an object placed inside another needs a composition, aggregation,
   assignment or realization (or the parent hierarchy) between them; if none exists, the person picks an allowed one to
   create (an uncommitted change). The nested line is not drawn, as ArchiMate does.
7. **Decoration is free**: text boxes, comments, groups and lines for readability live on the diagram only, never in
   the model.
8. **Look**: shapes show the **name only**, in the type's **standard ArchiMate colour and icon** (or the entity's own icon, when it has one). People change layout
   only (move, resize, align, fonts, line routing), not colour or icon. A view may switch to a **heat map** by one
   attribute (pick-list values or number ranges) with a legend.
9. **Resync**: a button brings the view up to date with the repository (names, new relationships between objects on
   the view, deleted entities and relationships marked). A view opens **exactly as saved**; a banner says when the
   model has changed since.
10. **Same entity twice** on one view is allowed.

## Where views live
- A drawn view **lives in the model it was made in**, on that model's **Views** tab, beside the views generated from
  the model. A project shows the views of its models.
- It holds **only its own model's entities**; relationships drawn are saved in that model.
- **A new view offers every entity type and relationship type** of the model. Or **copy** an existing view (a standard
  view generated from the model, or another drawn view), rename it and change it: every generated picture (network,
  layers, capability map, the standard views) gets *Save as a drawn view*, keeping its layout.
- **Versions**: each save is kept as a version of the view; **last save wins** (a save warns when someone saved since
  you opened it). Views **travel with the model**: a tag keeps them as they were, a copy or child gets copies bound to
  its own entities, a merge brings new views across.
- **Who**: anyone who may change the model (Architects, Model Sub Admins, Model Admins) draws and saves; everyone who
  can read the model opens views read only and exports them.

## Entity types get a look (points 9 to 12)
- Every entity type gets a **fill colour** and an **icon** (the ArchiMate shape). The ArchiMate 4 types and the
  EA Explorer extensions come set to the standard notation; a new type defaults to its **layer's ArchiMate colour**
  (strategy, business, application, technology, physical, motivation, implementation and migration).
- The icon is picked from the **ArchiMate set only** (every element's box-with-icon and shape forms).
- **An entity may have its own icon** (owner, 9 Nov 2026): when creating an entity (or changing it later in the
  platform), a person may upload a custom icon (SVG or PNG, small); views then show that entity with it, in its type's
  colour. Removing it brings back the type's icon.
- Changed on the metamodel (and in metamodel drafts), versioned like the rest of the metamodel.

## The screen
- The drawn view opens **inside EA Explorer** (draw.io in embed mode, with an EA Explorer plugin in our own draw.io
  container), not in a separate tab. draw.io's general shape libraries are switched off.
- **Left, the stencil**: the model's entity types by layer, each in its ArchiMate shape and colour; open a type to
  see its entities, with search. Drag an entity in, or drag a type and pick the instance.
- **Right, properties**: the selected object's attributes and relationships, read only, with a link to the entity.
- **Toolbar**: save, resync, heat map, export (`.drawio`, PNG, SVG, PDF), show hidden relationships.

## With the rest of EA Explorer
- **Views as project evidence**: from a project, pick a drawn view as a deliverable's artifact or a key question's
  answer (a link, plus a PNG or PDF snapshot in the project's repository).
- **AI**: MCP tools so an assistant can make a drawn view from chosen entities, laid out automatically, as the person.
- **"View" everywhere (D355)**: the word *viewpoint* becomes *view* in every screen, document and tool name, built
  together with this phase.

## To prove first (a spike)
Our draw.io container must load our plugin (a setting in our own copy) and talk to the page in embed mode: placing a
bound shape, refusing an unbound one, the relationship menu, hide and show, and saving the file with the bindings.
