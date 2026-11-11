# Phases 28 and 29 — Drawn views in draw.io (back end built in 0.16.0; the web to build)

Status: **design agreed with the owner, 9 Nov 2026 (D354, D355); the spike is done (9 Nov 2026); the draw.io plugin and the back end (API, MCP, migration 0033, release 0.16.0, D401 to D404) are built (10 Nov 2026); the web page is next.** The repository is the truth; a drawn
view only shows it. draw.io is how a view looks and how it is laid out, never where entities are made.

## The rules (owner, 9 Nov 2026)
1. **Entities are made in the platform, never on the canvas.** A dropped type is only a placeholder until it is
   realised as an existing entity (D388); attributes cannot be edited on the canvas. *Amended (D413, 10 Nov 2026):* the
   model's **committers** may edit a bound entity (**Edit** in the properties panel: its form in a pop-up, **Save and
   commit**) or create one from a placeholder (**Create a new <type>…**), each committed at once from the drawing;
   everyone else only realises a placeholder with an entity that exists.
2. **Only relationships are added from draw.io**, and only the ArchiMate relationship types the metamodel allows
   between the two types. Adding one opens a form (the type and a name). *Amended (D413):* it goes into the model **at
   once**, created and committed as the person ("Drawn on view <name>"), for anyone who may change the model, and shows
   solid; junctions too. Older pending ones still show dashed until committed from **Uncommitted changes**.
3. **Deleting** an object removes it from the view only, never the entity. *Amended (D413):* deleting a line **asks**:
   *Hide in this view* (the hidden list), or *Delete from the model* (for someone who may change the model; committed at
   once, "Deleted on drawn view <name>"; other views show it red when next opened).
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
8. **Look**: shapes show the **name only**, as the ArchiMate notation does (D389): the type is told by the shape and its small icon, never as "Clerk (Role)"; our extension types and other specialisations show «Value Stream Stage» above the name, as ArchiMate marks specialisations; a placeholder shows its type name in italics, dashed, until realised. in the type's **standard ArchiMate colour and icon** (or the entity's own icon, when it has one). People change layout
   only (move, resize, align, fonts, line routing), not colour or icon. A view may switch to a **heat map** by one
   attribute (pick-list values or number ranges) with a legend.
9. **Resync**: a button brings the view up to date with the repository (names, new relationships between objects on
   the view, deleted entities and relationships marked). *Amended (D413):* a view opened is brought up to date at once,
   with a dismissable note "Updated since last saved: …" (unsaved only when something changed); while it is open, a
   banner with Resync says when the model changes (checked every 30 seconds and when the tab comes back).
10. **Same entity twice** on one view is allowed.

## Where views live
- A drawn view **lives in the model it was made in**, on that model's **Views** tab, beside the views generated from
  the model. A project shows the views of its models.
- It holds **only its own model's entities**; relationships drawn are saved in that model.
- **A new view offers every entity type and relationship type** of the model. Or **copy** an existing view (a standard
  view generated from the model, or another drawn view), rename it and change it: every generated picture (network,
  domains, capability map, the standard views) gets *Save as a drawn view*, keeping its layout.
- **Versions**: each save is kept as a version of the view; **last save wins** (a save warns when someone saved since
  you opened it). Views **travel with the model**: a tag keeps them as they were, a copy or child gets copies bound to
  its own entities, a merge brings new views across.
- **Who**: anyone who may change the model (Architects, Model Sub Admins, Model Admins) draws and saves; everyone who
  can read the model opens views read only and exports them.

## Entity types get a look (points 9 to 12)
- Every entity type gets a **fill colour** and an **icon** (the ArchiMate shape). The ArchiMate 4 types and the
  EA Explorer extensions come set to the standard notation; a new type defaults to its **domain's ArchiMate colour**
  (strategy, business, application, technology, physical, motivation, implementation and migration).
- The icon is picked from the **ArchiMate set only** (every element's box-with-icon and shape forms), **ArchiMate 4 only**.
  The stencil is generated from the metamodel and reuses **draw.io's built-in ArchiMate shape drawings** for the glyphs
  (Apache 2.0, already in our draw.io container; no ArchiMate 4 library exists), in ArchiMate 4 names and colours; the
  elements ArchiMate 4 removed are never offered and draw.io's own ArchiMate 3 library stays off (D396). We draw a shape
  only where ArchiMate 4 has no older glyph.
- **Box or shape** (D398): an object shows as the box with its icon by default; a person may switch one object to the
  shape form (kept with the view, as layout).
- **An entity may have its own icon** (owner, 9 Nov 2026): when creating an entity (or changing it later in the
  platform), a person may upload a custom icon (SVG or PNG, small); views then show that entity with it, in its type's
  colour. Removing it brings back the type's icon.
- Changed on the metamodel (and in metamodel drafts), versioned like the rest of the metamodel.

## The screen
- The drawn view opens **inside EA Explorer** (draw.io in embed mode, with an EA Explorer plugin in our own draw.io
  container), not in a separate tab. draw.io's general shape libraries are switched off.
- **Left, the stencil** (owner, 9 Nov 2026, D387): the model's **metamodel**, not its entities: every entity type by domain in
  its ArchiMate 4 shape and colour, and the relationship types. Two ways to put an entity on the view:
  1. **Drag a type; realise it when ready** (D388): the stencil mimics the metamodel. A dropped type is a dashed
     placeholder ("Role: not yet realised"); no picker pops up. The person binds it whenever they decide (right-click
     *Choose instance*, a search against the model, e.g. "clerk"; later *Change instance*). **A view may be saved with
     unrealised placeholders**; they live on the diagram only, never in the model, and are listed on the view (with a
     count) so they are not forgotten. Relationships can only be added between realised objects.
  2. **The search panel** (D390): search the model's objects by name, filtered by type; the results list under the
     search box, each in its shape; drag a result straight onto the canvas as a realised object, or onto a
     placeholder to realise it.
- **Right, properties**: the selected object's attributes and relationships, read only, with a link to the entity.
- **Toolbar**: save, resync, heat map, export (`.drawio`, PNG, SVG, PDF), show hidden relationships.

## With the rest of EA Explorer
- **Views as project evidence**: from a project, pick a drawn view as a deliverable's artifact or a key question's
  answer (a link, plus a PNG or PDF snapshot in the project's repository).
- **AI**: MCP tools so an assistant can make a drawn view from chosen entities, laid out automatically, as the person.
- **"View" everywhere (D355)**: done in 0.15.1, ahead of this phase (D399): the word *viewpoint* became *view* in every
  screen, document, API path and MCP tool name, outright (D382). The generated views are on a model's **Views** tab,
  where drawn views will join them.

## ArchiMate 4 groundwork: done in 0.15.1, not with this phase (D392 to D395)
- **"Layer" became "domain"** everywhere (screens, metamodel editor, Excel, API, MCP, docs), outright.
- **The domain colours** are the ArchiMate 4 notation's (D392); the allowed relationships follow the owner's ArchiMate 4
  guide (D393).
- **Relationship multiplicity** (D395): n, `*` or n..m at each end of an allowed relationship, set on a type's page (#),
  in the Grids and in Excel; checked by the quality checks (a warning) and shown on the metamodel diagram's lines.
- **Still with this phase: junctions** (And, Or) on drawn views (D394). A junction is a **repository object of the
  model** (D397): the relationships through it are real relationships of one type, each checked as if it ran directly
  from source to target (a junction never makes a relationship allowed); no multiplicity at a junction's end; reports,
  other views and the quality checks see them.

## The spike: done and tried by the owner (9 Nov 2026)
Proved with draw.io 24.7.17 (Playwright; the tests are now [deploy/drawio/tests](../deploy/drawio/tests/README.md)):
- **Our own draw.io image** (`deploy/drawio/Dockerfile`): the published image plus `plugins/eax.js`, loaded from
  `index.html` (the image's start script rewrites `PostConfig.js`) and acting only in embed mode with `eax=1` (same origin, so draw.io's content security policy allows it). The
  `drawio` service is built from it (`eaexplorer/drawio`).
- **The plugin** (`deploy/drawio/eax-plugin.js`) and EA Explorer talk in JSON messages beside draw.io's own embed protocol:
  `eax-setup` (the metamodel: types with their ArchiMate shape and domain colour, allowed relationships, line styles),
  `eax-place`, `eax-bind`, `eax-rel`; and back `eax-ready`, `eax-relationship`, `eax-refused`, `eax-hidden`, `eax-shown`,
  `eax-choose`, `eax-open`, and draw.io's `save` with the file.
- **Checked:** the stencil is the metamodel only (draw.io's libraries, scratchpad and *More shapes* gone); realised
  shapes carry `ea_id` and `ea_type`; relationships the model has are drawn when an entity is placed; a line to a
  placeholder, or one no rule allows, is taken away again with the reason; an allowed one asks which type (only the
  allowed ones) and becomes an uncommitted relationship, dashed; deleting a line hides it (the hidden list is kept in the
  file), *Show hidden relationships* brings it back; a placeholder is realised from outside; the saved file carries every
  binding and the hidden list.
- **Found, to handle in the build:** draw.io's Style panel and *Edit Data* can change colours and the `ea_` attributes
  (to be locked for EA objects: layout only); dragging a connection arrow onto empty canvas copies the shape (a copy of a
  realised entity is allowed, D354 rule 10; its lines are checked like any other); junctions not tried yet.
- **Owner's test (9 Nov 2026):** works; making a relationship by hand is not obvious (only by dragging an object's hover
  arrow onto another). The build adds the relationship types to the stencil (drag a type of line between two objects)
  and *Add a relationship...* on an object's right-click menu (pick the other object and an allowed type).
- **The hand-test page was removed** (owner, 10 Nov 2026: "lets build the final thing now"): the owner tests drawn views
  in EA Explorer itself; the automated tests stay, outside the image.

## As built: the plugin protocol (phases 28 and 29, 10 Nov 2026)
`deploy/drawio/eax-plugin.js`, in our draw.io image (`plugins/eax.js`, loaded from `index.html`). It acts only when
draw.io is opened in embed mode with `eax=1`: `/drawio/index.html?embed=1&proto=json&configure=1&eax=1&spin=1&libraries=1&noExitBtn=1`
(add a changing parameter such as `&eaxv=<time>` so a browser never reuses an old copy). Messages are JSON strings over
`postMessage`; EA Explorer's carry `"eax": "<name>"`, the plugin's carry `"event": "eax-<name>"`. The plugin only
listens to its parent window and makes no network calls. draw.io's own embed protocol runs beside it: EA Explorer answers
`{event:"configure"}` with `{action:"configure", config:{defaultLibraries:"", enabledLibraries:[], compressXml:false}}`,
`{event:"init"}` with `{action:"load", xml}`, and receives `{event:"save", xml}` (the person pressed Save) and
`{event:"export", data}` (after `{action:"export", format:"png"|"xmlpng"|"svg"|"xmlsvg"}`: draw.io's embed export has no
PDF, so a PDF is made by EA Explorer from the PNG or SVG).

**The cells** (attributes of the cell's `object`, saved in the file):
| On | Attributes |
|---|---|
| a realised object | `ea_id` (the entity's GUID), `ea_type` (type code), `label` (its name), `ea_form="shape"` when shown as shape, `ea_deleted="1"` when the entity was deleted from the model |
| a placeholder | `ea_type`, `ea_placeholder="1"` (diagram only, never in the model) |
| a junction | `ea_junction_kind` (`and` or `or`), `ea_junction` (its id in the model, once EA Explorer has made it) |
| a relationship's line | `ea_rel` (type code), `ea_rel_id` (GUID), `ea_uncommitted="1"` while it is a pending change, `ea_nested="1"` when not drawn because one end is nested in the other, `ea_deleted="1"` |
| a line from the stencil, not yet joined | `ea_rel_type` (the type chosen) |
| a line waiting for its placeholder (D420) | `ea_rel_type`, `ea_waiting="1"` (drawn faint grey, dotted); from *Allowed relationships*; never checked as a drawn line |
| a decoration line (D414) | `ea_decor="1"`: from draw.io's General, Misc or Basic palette, or to or from a decoration shape; never a relationship |
| the diagram (cell 0) | `ea_hidden`: JSON list of `{rel, id, source, target}` hidden in this view |

**EA Explorer to the plugin**
| Message | Fields | What happens |
|---|---|---|
| `setup` | `types: {code: {name, domain, colour (hex), box (draw.io style, box form), shape (style, shape form; optional)}}`, `allowed: [[source code, relationship code, target code]]`, `relationshipTypes: {code: {name, style?}}` (default: ArchiMate's line notation), `readOnly`, `entityIcons: {entity id: data URI}`, `title` (the view's or picture's name: the .drawio file's, D585), `keepLook` and `plainLabels` (a picture opened in draw.io, D585: no restyling; labels as made) | builds the stencil (types by domain, a Relationships palette of the types `allowed` uses, the two junctions; draw.io's libraries, scratchpad and *More shapes* removed); restyles what the file holds (not with `keepLook`); read only: no stencil, nothing moves, no lines; answers `eax-setup-done {types, readOnly}` |
| `place` | `entity {id, name, type, icon?}`, `at {x, y}`, `relationships [{id, type, source, target, pending}]` | a realised object, and lines for the relationships it has with what is on the view (not hidden ones); `eax-placed {cell, entity}` |
| `place-at-pointer` | `entity`, `clientX`, `clientY` (relative to the frame), `relationships` | dropped from the search panel: onto a placeholder of the same type it realises it (`eax-bound`), else placed there (`eax-placed`) |
| `bind` | `cell`, `entity` | a placeholder (or *Change instance*) realised; `eax-bound {cell, entity}` |
| `rel` | `cell`, `type`, `id`, `pending` (default true; EA Explorer sends false since D413, the relationship being committed) | the line becomes that relationship (dashed blue while pending) |
| `rel-cancel` | `cell` | the line is taken away |
| `rel-create` | `source`, `target` (cells), `type`, `id`, `pending` | after *Add a relationship...*: draws it |
| `add-relationship` | `cell` or `entity` | as the right-click item (EA Explorer's own button) |
| `junction-bound` | `cell`, `id` | the junction is in the model |
| `nest-ok` / `nest-refused` | `cell`, `reason` | nesting accepted (the nested relationship's line is not drawn) or refused (moved back where it was; `eax-unnested`) |
| `resync` | `entities {id: {name, type, icon?}}`, `deleted [ids]`, `relationships [{id, type, source, target, pending}]`, `deletedRelationships [ids]` | names, types and icons brought up to date; missing relationships between objects on the view drawn (not hidden ones); pending ones dashed, committed solid; deleted entities and relationships marked (red dashed), not removed; `eax-resynced {added, renamed, deleted, committed, auto}` (`auto: true` on the `resync` when the view is opened, D413; `committed`: pending lines now solid) |
| `heat` / `heat-off` | `colours {entity id: hex}` | part 2: objects painted on screen only (objects without a value pale grey); never saved; exports made while it is on show it. The legend is EA Explorer's, beside the view; `eax-heat-on {count}` / `eax-heat-off` |
| `icons` | `icons {entity id: data URI or null}` | part 2: an entity's own icon (box form: top right, in the type's colour, instead of the type's glyph); null brings the glyph back |
| `placeholders` | | `eax-placeholders {list [{cell, type}]}` |
| `hidden` | | `eax-hidden-list {hidden}` |
| `select` | `entity` | selects and shows it |
| `line-hide` / `line-restore` / `line-removed` | `id` (the relationship) | the answer to `eax-line-deleted` (D413): hidden in this view (the hidden list; `eax-hidden`), drawn again (cancelled), or deleted from the model (the line stays away, not hidden) |
| `placeholder-type` | `cell`, `type` | a placeholder shown as another type (the properties panel's type list, D413); answered by `eax-selected` |
| `stencil-panel` | `open`, `width` | D420: the stencil (draw.io's left sidebar) shown at that width, or folded away (unpinned) |
| `add-related` | `cell` (the selected object) or `near` (its entity), `entity {id, name, type, icon?}`, `relationship {id, type, source, target, name, pending}`, `relationships` (the entity's with what is on the view) | D420, the Relationships tab: the entity placed somewhere free next to the object with the line; on the view already, only the line (off the hidden list); both there, the line selected. `eax-related-added {cell, line, already, entity}` |
| `add-allowed` | `cell` or `near`, `type`, `types` (all the rule allows), `rel`, `outgoing` | D420, the Allowed relationships tab: a placeholder of `type` somewhere free next to the object, a waiting line between them; answered by `eax-dropped {cell, type, types, rel, line, via: "allowed"}` |
| `waiting-cancel` | `cell` (the line) | the relationship could not be made: the waiting line goes, the placeholder stays |

**The plugin to EA Explorer** (besides the answers above)
| Event | Fields | When |
|---|---|---|
| `eax-ready` | `version` | the plugin is loaded (send `setup` then) |
| `eax-relationship` | `cell`, `source`, `target` (entity ids, or a junction id), `options` (allowed types; one when a type was chosen from the stencil), `junction` (its id) and `through` (entity ids on its other side) for a line at a junction | a line was drawn: EA Explorer asks which type and its attributes, then answers `rel` or `rel-cancel` |
| `eax-refused` | `reason` | a line or change was taken away or put back (show the reason) |
| `eax-add-relationship` | `cell`, `entity`, `type`, `candidates [{cell, entity, type, name}]` | *Add a relationship...*: EA Explorer offers the other object and an allowed type, then answers `rel-create` |
| `eax-junction-new` | `cell`, `kind` | a junction was dropped: EA Explorer makes it in the model, answers `junction-bound` |
| `eax-nest` | `cell`, `entity`, `parentCell`, `parent` | an object was dropped into another: EA Explorer checks (or offers to create) a relationship, answers `nest-ok` or `nest-refused` |
| `eax-hidden` / `eax-shown` | `relationship` / `entity, count` | a line hidden (*Hide*, or *Hide in this view* after a delete) / brought back |
| `eax-line-deleted` | `relationship {rel, id, source, target, name, pending}` | a relationship's line was deleted (not with its object): EA Explorer asks, then answers `line-hide`, `line-restore` or `line-removed` (D413) |
| `eax-choose` | `cell`, `type` | *Choose instance...* or *Change instance...*: EA Explorer's search, then `bind` |
| `eax-open` | `entity` | *Open in EA Explorer* |
| `eax-form` | `cell`, `entity`, `form` | box or shape changed (layout) |
| `eax-selected` | `entity`, `relationship`, `cell` | the selection changed (for the properties panel) |
| `eax-changed` | `dirty`, `placeholders`, `unboundJunctions` | the drawing changed (debounced): unsaved, and how many placeholders are not realised |
| `eax-dropped` | `cell`, `type` (and from `add-allowed`: `types`, `rel`, `line`, `via`) | D420: one placeholder dropped (or clicked in) from the stencil: EA Explorer's pop-up asks what it is (bind, create, leave) |
| `eax-waiting-line` | `cell`, `source`, `target` (entity ids), `type` | D420: a placeholder with a waiting line was bound (or created and bound) and both ends are real: EA Explorer makes the relationship (committed at once) and answers `rel`, or `waiting-cancel` |
| `eax-stencil-width` | `width` | D420: the person dragged the stencil's edge (kept for them) |
| `eax-canvas-click` | | D420: a click on the drawing (EA Explorer folds away an unpinned panel it opened) |

**Locked to layout (D354 rule 8).** On EA objects and relationship lines a person may move, resize, align, change fonts
(size, style, family) and route lines; anything else (colours including font colour, shape, opacity, dashes, the name, the
`ea_` attributes, a relationship's ends) is put back at once, with `eax-refused` for a moved end. In-place label editing,
*Edit Data*, *Edit Style*, *Edit Tooltip*, *Edit Link* and *Edit Shape* are refused on EA cells. Text, notes and other
decoration stay free. Objects are containers (`container=1`), so one can be dropped into another, which `eax-nest` checks.

**Tested** (`deploy/drawio/tests`, 53 checks against draw.io 24.7.17). **Limits:** junction lines are checked as if direct
against the objects already on the junction's other side (EA Explorer checks again when it makes the relationship); a
heat map shows in exports made while it is on; a copy made by dragging a hover arrow onto empty canvas is a second
instance of the same entity (allowed, rule 10).

## Views service (10 Nov 2026, D405 to D409)

Drawn views and the models' own generated views are kept by a service of their own, like the library (D405):
`services/views` (package `viewsvc`, container `views`, port 8110), database `eaxviews`, schema `views`, login
`eax_views`, behind the proxy at `/api/views/v1`. It takes the same Keycloak token, asks the main API who the person is
(`/api/v1/me`, kept a minute) and, on every call, their rights on the model and its last change
(`GET /api/v1/models/<m>/drawn-views/access`); on create and save it asks whether the view's objects are the model's own
(`POST /api/v1/models/<m>/drawn-views/check`). Settings: EAX_SERVICE_VIEWS, EAX_VIEWS_DB_PASSWORD, EAX_VIEWS_KEY (setup
refuses the laptop value on a server), EAX_VIEWS_DB_HOST/_PORT/_NAME/_USER, EAX_VIEWS_KEEP_VERSIONS, EAX_VIEWS_URL (the
main API's address for it).

**API split (as built).** The screens call the views service for storage:

| Method and path (`/api/views/v1`) | What |
| --- | --- |
| GET, POST `/models/<m>/drawn-views` | the model's drawn views (with `may_draw`); a new one {name, description, xml?, source?, copy_from?, copy_version?} |
| GET, PUT, PATCH, DELETE `/models/<m>/drawn-views/<v>` | one view (`?version=`, `?xml=0`); save {xml, base_version, note?, force?}: 409 `errors.conflict` when someone saved since (D404); rename; remove |
| GET `/models/<m>/drawn-views/<v>/versions` | every version, and which a tag holds |
| GET, POST `/models/<m>/own-views`; GET, PUT, DELETE `/models/<m>/own-views/<v>` | the model's own generated views (D406), by guid, code MV-n or name |
| `/internal/...` (the `X-Views-Key` header) | for the main API: list, get, create, save; hold a tag's versions and read one; export and import a model's views; copy to another model (rebound to its entities, D354); remove a model's |

The main API keeps what needs the model's data: setup, resync, relationships-of, allowed, generate, heat map, icons,
junction rules, evidence, and `POST /api/v1/models/<m>/views/render` (the model through a view definition: an own view's
picture, drawn each time, never stored). It reaches the service with `eax/views_client.py` for tags, copies and child
models, merges (views the target lacks), packages (`views/drawn_views.json` in the zip), a model's removal, the MCP
tools and the sample data; the service being off or down never stops those: they say what was left out.

**Every view is a draw.io file (D408).** Every generated picture offers *Save as a drawn view* (its layout tidied:
boxes on the grid, the entities in their type's ArchiMate notation and bound to them, containers round their parts,
lines bound to the relationships) and downloads (.drawio, PNG, SVG); the model and project trees, no one model's,
offer the downloads only. "Open in draw.io" is gone. Project evidence is a link only: the model, the view and, if
chosen, one version (read only); opening it opens the view. The editor's Export is a download.

**Any view can be copied (D407):** a drawn view (any version) into a new drawn view; a generated picture into a drawn
view; a standard view's definition into the model's own view (*Copy as my model's view*; anyone who may change the
model makes, changes and removes them).

**The stencil (D409):** every type of the metamodel by domain, the relationship types and the junctions. The editor's
*Stencil* button shows or hides each group, remembered per person in the browser (try/catch), never in the view: the
host sends `{eax: "palettes", show: {group: true|false}}`, the plugin answers `eax-palettes` {groups, hidden};
`eax-setup-done` carries `groups`.

## As built: API (release 0.16.0, migration 0033, 10 Nov 2026; D401 to D404)

Everything is under `/api/v1`, signed in. Reads need read access to the model; the writes marked **(content)** need a
role on the model that may change its content (`model.content`), and a frozen, archived, locked-content, maintenance or
template model refuses them (409). Errors are `{message}` (and `errors` where said). `<m>` is a model id, `<v>` a view's
id (or its name), `<e>` an entity's id (or display id). Code: `eax/drawn_views.py`, `eax/api/drawn_views.py`,
`eax/notation.py`, `eax/junctions.py`.

**Entity type looks** (`GET /models/<m>/metamodel`, each entity type): `notation` (the ArchiMate 4 element whose
shape it shows, or `""` for a plain rounded box; `"Junction"` for the junction type), `fill_colour` (`RRGGBB` or `""`:
the domain's), `is_connector` (the junction type), and `drawio: {box, shape, colour}` (the styles the plugin's `setup`
wants). Changed with the metamodel editor: `entity_type.update {type, notation?, fill_colour?}` (and on `entity_type.create`).
`notation` must be one of the 42 ArchiMate 4 element codes or `Junction`; a bad value is a 400.

**Views**
| Call | Body / query | Answer |
|---|---|---|
| `GET /models/<m>/drawn-views` | | `{model {id, name}, views [{id, name, description, source, version, saved_by, saved_at, objects, placeholders, model_changed_since}]}` |
| `POST /models/<m>/drawn-views` (content) | `{name, description?, xml?, source? (new, generated), source_note?, copy_from? (view id), copy_version?}` | the view as `GET` gives it, with `message`; 400 when the name is taken in the model, or the file holds another model's entities |
| `GET /models/<m>/drawn-views/<v>` | `?version=n` (default: the latest), `?xml=0` to leave the file out | `{id, name, description, source, source_note, created_by, created_at, modified_by, modified_at, version, latest_version, saved_by, saved_at, model_changed_since, summary {entities, missing_entities, deleted_entities, relationships, uncommitted_relationships, hidden_relationships, placeholders}, xml}` |
| `PUT /models/<m>/drawn-views/<v>` (content) | `{xml, base_version, note?, force?}` | `{id, version, summary, warning, message}`; **409** when someone saved after `base_version`: `errors.conflict {version, saved_by, saved_at}`; send again with `force: true` to save anyway (the last save wins, theirs stays in the versions, D404) |
| `PATCH /models/<m>/drawn-views/<v>` (content) | `{name?, description?}` | `{id, name, description, message}` |
| `DELETE /models/<m>/drawn-views/<v>` (content) | | `{id, message}` (the versions are kept) |
| `GET /models/<m>/drawn-views/<v>/versions` | | `{id, name, versions [{version, note, saved_by, saved_at, size}]}`, newest first |
| `GET /models/<m>/tags/<t>/drawn-views/<v>` | `?version=n` | `{tag, id, name, version, saved_by, saved_at, xml, read_only: true}`: the view as the tag keeps it; `GET /models/<m>/tags/<t>` lists them in `drawn_views [{id, name, versions, version}]` |

**Drawing**
| Call | Body / query | Answer |
|---|---|---|
| `GET /models/<m>/drawn-views/setup` | `?view=<v>` (for its entities' own icons) | the plugin's `setup` message, ready to post: `{eax: "setup", types {code: {name, domain, colour, box, shape}}, allowed [[source, relationship, target]], relationshipTypes {code: {name, style}}, readOnly, entityIcons {entity id: data URI}}` (`readOnly` is true for someone who may not draw, or a model that may not change; the junction type is left out: the plugin offers the junctions) |
| `POST /models/<m>/drawn-views/resync` | `{view}` or `{xml}` (the file as it is in the editor) | `{entities {id: {id, name, display_id, deleted, type, type_name, domain, look {box, shape, colour}, icon (data URI or null), junction ("And"/"Or", junctions only)}}, missing_entities [ids], deleted_entities [ids], relationships [{id, type, type_name, source, target, committed}], new_relationships [...], gone_relationships [ids], others_uncommitted [ids]}`. `relationships` are those among the objects as **this person** sees the model (theirs uncommitted: `committed: false`); `new_relationships` are not on the view yet and not hidden (draw them); `gone_relationships` were deleted (mark them); `others_uncommitted` are someone else's pending lines (leave them as they are) |
| `POST /models/<m>/drawn-views/relationships-of` | `{entity, others [entity ids on the view]}` | `{entity {...as above}, relationships [{id, type, source, target, committed}]}`: for `place` |
| `GET /models/<m>/drawn-views/allowed` | `?source=&target=` (entity ids; or type codes) | `{source_type, target_type, allowed [{code, name, verb, source_multiplicity, target_multiplicity, note}]}`; through a junction only the types its rules leave (D397, D402) |
| `POST /models/<m>/drawn-views/generate` | `{entities [ids], include_relationships?}` | `{xml}`: a view of those entities laid out by domain (motivation and strategy on top, then business, application, technology, implementation and migration), for "Save as a drawn view" of a generated picture (`POST drawn-views` with `source: "generated"`) |
| `POST /models/<m>/content/relationships` | `{source, target, relationship_type, name?, allow_outside?}` (existing) | the relationship as an **uncommitted change** (`pending: true`, its `id` is the GUID to put in `ea_rel_id`); a relationship to or from a junction is checked by the junction rules (409 with the reason) |
| `POST /models/<m>/content/entities` | `{entity_type: "Junction", name, values: {JunctionKind: "And" or "Or"}}` (existing) | a junction in the model (answer `junction-bound` with its id) |

**Part 2**
| Call | Body / query | Answer |
|---|---|---|
| `GET /models/<m>/heat-map` | `?attribute=<code or name>`, `?ranges=lo:hi,lo:hi` (numbers; default five equal bands from the lowest to the highest value) | `{attribute {code, name, data_type}, legend [{label, colour, from?, to?}], colours {entity id: hex}, values {entity id: value}, no_value: "EEEEEE"}`; pick lists and text get a colour per value, numbers a band; dates and yes/no are refused (400) |
| `GET /models/<m>/entities/<e>/icon` | | the SVG or PNG (with a strict content security policy); 404 when it has none |
| `POST /models/<m>/entities/<e>/icon` (content) | multipart `file` (SVG or PNG, at most 64 KB) | `{entity, content_type, message}`; 400 for an SVG with scripts, links, styles, embedded images or content, event attributes or urls (D403); 413 when too large |
| `DELETE /models/<m>/entities/<e>/icon` (content) | | `{entity, message}` |
| `GET /projects/<p>/view-evidence` | | `{evidence [{id, item, item_name, question, question_text, model, model_name, view, view_name, view_removed, version, document, file_name, note, added_by, added_at, link}]}` |
| `POST /projects/<p>/view-evidence` (a contributor) | multipart or JSON: `model, view, version?, item` (a deliverable's id) **or** `question` (a key question's id), `snapshot_item?` (where a question's snapshot is kept), `note?`, `file?` (the PNG or PDF snapshot) | `{id, message}`; the snapshot goes into the project's repository; a question's answer gets a link to the view (`#/metamodel/<m>/drawn-views/<v>?version=n`) |
| `DELETE /projects/<p>/view-evidence/<id>` (a contributor) | | `{message}` (the snapshot stays) |

**The cells the back end reads and writes** are the plugin's (above): `ea_id`, `ea_type`, `ea_placeholder`, `ea_rel`,
`ea_rel_id`, `ea_uncommitted`, `ea_junction`, `ea_junction_kind`, and `ea_hidden` on cell 0. A save is refused (400)
when an object is bound to something that is not an entity id, or to another model's entity or relationship. Files may
be compressed (draw.io's default) or not; at most 5 M characters.

**MCP** (82 tools): `list_drawn_views(model)`, `get_drawn_view(model, view, version?, with_xml?)` (with the entities and
relationships on it as they are now) and `create_drawn_view(model, name, entities, include_relationships?, description?)`
(entities by name, display id or id; laid out by domain; saved as the person, source `mcp`).

**What travels with the model**
* **Tags** keep every view with every version (read only through the tag).
* **A copy or a child** (with content) gets each view's latest version, bound to its own entities by origin; an
  entity it does not have becomes a placeholder, a relationship it does not have loses its id (the line stays). Entity
  icons are copied too.
* **A merge** from another model in the installation brings across the views the target does not have (by name).
* **Not carried (gaps):** a merge from an uploaded package or another installation (packages hold no views yet); a
  project backup (it holds the project's own tables; the views are the model's, in the repository's database and its
  backups); models made before 0.16.0 have no junction type until a metamodel admin adds one.

**Sample data** (laptop, `eax.seed.sample_drawn_views`, once): on Protea Insurance (demo estate): *Claims application
landscape* (tidy, two versions, the second by another person hides one relationship), *Claims target sketch* (a
placeholder and the architect's uncommitted relationship), *Online claim channels* (an Or junction in the model),
*Customer channels (before the app was renamed)* (saved before a model change: `model_changed_since`); the Mobile App
has its own icon; in *Protea Claims Transformation 2028 (sample)* the landscape (version 2) is evidence for the
deliverable *Application communication diagram* and the sketch for the key question *What is the impact of removing the
legacy claims application?*


## As built: the screens (release 0.16.0, 10 Nov 2026)
`services/web/src/DrawnView.jsx`, wired into the model page, the Views tab, the entity page, the metamodel editor, the
generated pictures and the project's Views tab.
- **Model › Views › Drawn views**: the list (name, version, saved by and when, objects, *model changed since*, placeholders),
  **+ New drawn view** (empty, or a copy of a view at any version), Copy, Rename, Delete (the versions are kept),
  Versions. Read only for someone who may not change the model, and on a frozen, archived or locked model.
- **The editor** `#/metamodel/<m>/drawn-views/<v>` (`?version=n` opens an older version read only, with *Restore as a new
  version*): draw.io in a frame with the plugin; left, **Find in the model** (by name or ID and type; drag a result onto the
  drawing, or onto a placeholder of its type to realise it, or press Place; the relationships it has with what is on the
  view come with it); right, **Properties** of the selection (attributes, relationships, a link to the entity), the
  placeholders still to realise and the hidden relationships. Toolbar: **Save** (draw.io's Save too; a save after someone
  else's shows who and when, with *Save anyway* or *Reload theirs*), **Resync**, **Heat map** (an attribute; numbers in
  ranges; the legend beside the view), **Hidden relationships**, **Export** (PNG, SVG, a one-page PDF made in the browser
  from the PNG, the .drawio file; the heat map is left out unless *as shown*), **Versions**, **Use as project evidence…**.
  A banner says when the model changed since the version was saved. Leaving with unsaved changes asks first.
- **Its own tab, full screen (D411)**: every way into a drawn view (the Views tab's list, a new one or a copy, *Save as
  a drawn view*, Versions, project evidence) opens it in a new browser tab with none of EA Explorer's header or menus:
  a slim bar (the model › Drawn views › the view, its version, *not saved*, the toolbar and **Close**) and below it the
  search, draw.io and the properties panel at the window's full height. The address stays bookmarkable; closing the tab
  with changes not saved asks first. **Properties** shows, for an object, every attribute of its type in order (empty
  ones as —) and every relationship, grouped by type and direction with the other end's type (one on the view is a
  link that selects it), *Change instance…* and *Open the entity ↗*; for a line, its type, both ends, name, status,
  committed or pending. A **placeholder** (a type dragged from the stencil) shows **Realise this <type>**: a type-ahead
  list of the model's entities of that type (and types specialising it), by name, those already on the view marked;
  choosing one binds it, drops the placeholder's dashed look and draws its relationships with what is on the view, as
  placing does. Right-click *Choose instance…* focuses the same list. The plugin's `eax-selected` says
  `{cell, entity, type, placeholder, junction}` for an object and `{cell, relationship, relType, source, target,
  pending}` for a line; `{eax: "bind"}` takes `relationships`, and a rebind removes the old entity's lines.
- **Lines and nesting**: a line drawn (stencil, hover arrow or *Add a relationship...*) opens a form with only the
  allowed types and an optional name, and becomes the person's uncommitted change; a line for a relationship the model
  already has shows that one. Dropping one object into another needs a composition, aggregation, assignment or
  realization: an existing one is accepted, else the person picks an allowed one to make, or the object moves back out.
  A junction dropped on the view is made in the model at once (And or Or).
- **Save as a drawn view** on every picture drawn by the graph (the Graph tab's network, by domain, impact, both ways,
  family tree, paths, as of; an entity's Graph tab; a generated view's diagram): the picture's layout is kept.
- **An entity's own icon** (the entity page, under its description): upload an SVG or PNG (at most 64 KB), replace,
  remove.
- **The look of a type** (metamodel editor, entity type): its ArchiMate element and an optional fill colour; the type's page
  shows the look.
- **Evidence**: *Use as project evidence…* in the editor (a saved version, a deliverable or a key question, a PNG
  snapshot); the project's **Views** tab lists its drawn views as evidence, each opening that version.
- **After the owner's try-out (D412)**: the **Views** tab has two sub-tabs, *Custom views* and *Standard views*
  (`#/metamodel/<m>/views/custom|standard`; with none named, Custom views when the model has any, else Standard views;
  the older `views/drawn` and `views/own` land on Custom views). **Custom views** is one list of the model's own views,
  whoever made them: its drawn views and its copies of generated views (MV-n), with a **Kind** column (Drawn, Generated)
  and each kind's actions (a drawn one: Open ↗ in its own tab, Versions, Copy, Rename, Delete; a generated one: Open,
  Diagram, and changing or deleting it on its page); *+ New drawn view* is there. **Standard views** is the
  organisation's VP-n with *+ New standard view*; copying one lands in Custom views. A relationship's **name is shown on
  its line** (white behind the text; no name, no label): from the form when drawn, and from the model when placed,
  realised or resynced (Resync renames it). The label cannot be edited on the view but may be moved along the line.
  **Commit** sits next to Save: *Commit 2 relationships* commits the person's uncommitted relationships and junctions on
  this view, and nothing else of theirs, with a commit message (`POST /drawn-views/pending {targets}` finds them; then
  `/changes/commit`); it saves first, is disabled when there is nothing, and for someone who may not commit it is *Ask to
  commit* (`/changes/request`). The lines turn solid after. **Stencil size** Small / Medium / Large (medium, about twice
  the old size, by default; remembered in this browser for the person): `{eax: "stencil-size", size}` rebuilds the
  palettes, answered by `eax-stencil-size`; draw.io's hover preview is kept. **The stencil's order** is ArchiMate's: the
  domains Motivation, Strategy, Common, Business, Application, Technology, Implementation & Migration (a TOGAF-metamodel
  model: Motivation, Strategy, Business, Data, Application, Technology, Implementation and Migration, Governance; any
  other after, alphabetically), then Relationships (Composition, Aggregation, Assignment, Realization; Serving, Access,
  Influence, Association; Triggering, Flow; Specialization), then Junctions. Each domain's types follow the metamodel's
  order, extensions last, marked *(extension)*. The setup message says the order (`domains`; `types` in order;
  `extension: true`) and the plugin keeps the same lists; the show/hide list and the search panel's type filter (grouped
  by domain) follow it.
- **Two-way sync (D413)**: *Relationships*: every line drawn (stencil, hover arrow, *Add a relationship…*, nesting, lines at a
  junction) and every junction is made through `POST /api/v1/models/<m>/drawn-views/change {op: "relationship.create",
  args: {data}, view_name}`: recorded as the person's change and committed in the same transaction
  (`commits.commit(relationships_only=True)` lets anyone who may change the model commit their own relationships and
  junctions; `commits.drawn_free` says which), never outside the metamodel; a library model being built saves it straight
  away. The line is solid at once. *Entities*: the model's committers get **Edit** on a bound object (the data entry form,
  `EntityFormDialog` with `commit={view}`: the button is **Save and commit**, a commit message prefilled "Changed on drawn
  view <name>", the required attributes must be filled; `op: "entity.update"`) and, on a placeholder, a **type** list (the
  dropped type and the types specialising it; `{eax: "placeholder-type"}`), the type's entities to realise it with and
  **Create a new <type>…** (`op: "entity.create"`; then bound and its relationships drawn). Anyone else sees why not; the
  API refuses them (403). *Deleting a line* asks (`eax-line-deleted`): **Hide in this view**, **Delete from the model**
  (`op: "relationship.delete"`, "Deleted on drawn view <name>"; a never-committed line's pending change is discarded
  instead) or Cancel (the line comes back). *Uncommitted changes* (next to Save; the count of the person's uncommitted
  changes in the model, from `GET /changes`): a pop-up listing them all (label, rules failed, when), each with **Edit** (an
  entity's: its form, kept as an uncommitted change) and **Discard**, a commit message, **Commit selected** and **Commit
  all** (`POST /drawn-views/commit {changes, message}`; relationships and junctions need no committer, the rest is offered
  only to committers). *Model to view*: when a view opens it is resynced (`{eax: "resync", auto: true}`), and a note says
  what changed ("Updated since last saved: 1 renamed, 2 relationships drawn, 1 now committed"), marking the view unsaved only
  then; while it is open `GET /drawn-views/access` is asked for the model's last change every 30 seconds and when the tab
  comes back, and a change by someone else shows the banner with Resync. Seed: the sketch keeps its pending relationship
  and the architect also has an uncommitted change to the Payments Hub (the Uncommitted changes list).
- **Decoration (D414)**: after Junctions, draw.io's **General**, **Misc** and **Basic** palettes (collapsed), each in the
  Stencil list. The plugin wraps the sidebar so their items' lines carry `ea_decor="1"`; `checkEdge` leaves those alone, and
  a line to or from a shape with no `ea_` attributes is marked decoration too. Never draw.io's ArchiMate libraries, never
  More Shapes. Plugin tests: 94 checks (`deploy/drawio/tests`).
- **The working space (D420)**: the editor is the stencil on the left, the drawing, and a **bottom panel** with tabs
  *Find in the model* (the search, its results in columns), *Properties* (every attribute in columns, the placeholders
  and hidden lists; the relationships moved to their own tab), *Relationships (n)*, *Allowed relationships* and
  *Uncommitted changes (n)* (the former pop-up, with the commit message and Commit selected / Commit all at its foot; the
  button next to Save opens it). The panel is resized by dragging its top edge (120 px to 70% of the window). Each of the
  stencil and the panel has a 📌: **pinned** it takes its space; **unpinned** it folds to a thin labelled strip (the
  stencil's on the left edge, the panel's at the bottom with its tab names), and a click opens it (the panel over the
  drawing, the stencil beside it) until a click on the drawing (`eax-canvas-click`) folds it away again. **Layout** in
  the toolbar: *Drawing* (stencil pinned, panel unpinned), *Editing* (both pinned; the default) and *Canvas only*
  (both unpinned); the choice, pins, the panel's height and the stencil's width are kept in the browser for the person
  (`eax.drawn.layout.<user>`). **Dropping a type** from the stencil (or clicking it in) opens *What is this <type>?*:
  the type list (its family), a type-ahead list of the model's entities of that type (those on the view marked) to bind
  it to, **Create a new <type>…** for committers (the form, Save and commit, then bound), and **Leave as a placeholder**
  (also Esc and ✕). **Relationships** groups the selected entity's relationships by type and direction (columns), marks
  "✓ on the view" or "on the view, line not drawn", and a click places the related entity next to it with the line
  (`add-related`; the free spot is right, below, left, above, then further out, never on another object), draws only the
  line, or selects it. **Allowed relationships** lists, per relationship type and direction, the other types (as chips in
  their domain colour, with multiplicity; `setup.allowed` rows now carry `[source, relationship, target, source
  multiplicity, target multiplicity]`): a chip adds a placeholder of that type, the row's name one whose type the pop-up
  asks first; the placeholder is joined by a waiting line (`ea_waiting`), and once bound or created the relationship is
  made with `relationship.create` and committed at once ("Drawn on view <name>"); bound to an entity already on the view,
  the line moves to that object and the placeholder goes. **draw.io's Format panel** (right) is gone: the plugin keeps
  `toggleFormatPanel` closed, hides its button and the full-screen button (which reopened it), and disables the *format*
  action (View › Format, Ctrl+Shift+P); the right-click and Arrange menus keep alignment, distribution, order and size.
  Plugin tests: 113 checks.
- **Names already in the model (D454, 0.17.0)**: creating from the drawing (the drop pop-up, Allowed relationships, a
  placeholder's *Create*) lists *Already in the model* as the name is typed (`/content/similar?all_types=1&limit=10`,
  the dedupe matcher: the same name, the same words in another order, near spellings), its own type first with **Use this
  one** (binds the shape; nothing is created), other types marked and not usable. *Save and commit* with the same name and
  type asks *Use the existing one / Create another / Back to the form*. The Bind, choose and Find searches match near
  spellings and word order (`names.js`, `fuzzyFilter`).
- **Labels, the same entity twice, undo and redo (D460, 0.17.0; the owner's tests on the laptop)**: the canvas shows an
  entity as **"<name> : <Entity Type>"** (the name bold, the type italic and 0.85em, on a second line when the shape is narrow; both escaped, so "<script>" or "A & B" show as text; editing in place starts from the plain name (`getEditingValue`); a placeholder as
  "(unbound) : <Entity Type>") and a relationship's line with its **name, or its type** when it has none. This is the
  plugin's display only (`graph.convertValueToString`): the file keeps the name alone in `label`, so loaded, copied and
  resynced views show the same, and renaming changes the name part only. Before, a relationship with no name had no
  label at all, which is why the lines looked unnamed. **A line drawn between two entities that already have a
  relationship** (e.g. at a second copy of one of them) shows that relationship: with only one type possible it is bound
  at once ("Shown the existing relationship."); with several, the pop-up offers the existing one first (*Show the existing
  relationship*); the model never gets a second one. The Relationships tab draws the line at the very shape selected (a
  relationship may have a line at each copy); Allowed relationships binds to the existing one too. **Undo and redo**
  (Ctrl+Z, Ctrl+Y, Ctrl+Shift+Z, the toolbar) cover what the person does on the drawing; what the plugin does for EA
  Explorer (setup, resync, binds, a relationship's id, icons) is kept out of the undo history, so an undo never puts the
  view out of step with the model. Undoing a committed relationship's line takes it **off the view only** (the hidden
  list; "Still in the model; delete the line to remove it from the model."), never the delete question; undoing an object
  takes the shape off the view only; redo brings either back, bound (an object's lines are drawn again). A relationship
  deleted from the model never comes back by undo. The keys work when the focus is in EA Explorer's page too (forwarded
  as `undo` / `redo`), except while typing in a field or with a pop-up open. Plugin tests: 130 checks.
- **Not done**: *Save as a drawn view* for the capability and hierarchy maps (they are laid out as page blocks, not as a
  picture with positions); a project can only pick a drawn view from the editor, not from a deliverable's own page.

## As built: type drop-downs you can type in (0.19.0, 10 Nov 2026, D540)
Every type drop-down of the drawn view is a searchable picker (services/web/src/SearchSelect.jsx): Find's type, a
placeholder's type (Properties and the drop pop-up, including the other end's type from Allowed relationships), the
relationship type when a line is drawn or added, and a nesting's relationship. Typing filters with near spellings
("aplication comp" finds Application Component); with nothing typed the whole list shows, grouped by domain in the
stencil's order. ↑ ↓ move, Enter chooses, Esc closes the list (a second Esc reaches the pop-up). The Stencil dialog has a
search over its groups and the types in them. The plugin is unchanged.

## As built: relationship attributes and line labels (0.19.0, 11 Nov 2026; D563 to D565)
- A selected line's **Properties** shows From, To, its status, its **Name** and one **key : value** row per attribute of its relationship type and allowed relationship (pick lists as drop-downs; required ones marked). **Save and commit** commits at once as the person (D413).
- Line label: `name (Type) [key:value key:value]`, the name bold, the type italic and smaller, the values grey; no name: `(Type)`; more than 3 values: the first 3 and `+n`. Display only: the file's `label` keeps the name, so in-place editing (`getEditingValue`) starts from the plain name and renaming never touches the type.
- Toolbar **Line labels: name and type / with attributes** (message `line-labels` to the plugin), remembered per person in the browser.
- Plugin tests cover the format, escaping, `+n`, the plain-name edit and the toggle (141 pass).

## As built: everything opens in our draw.io (0.19.0, 11 Nov 2026; D585, amends D408)
- **Open in draw.io** replaces the `.drawio` download on every picture of a model (`PictureActions`: the ER and metamodel diagram, entity graph, hierarchy map, relation matrix, value stream map, roadmap, view heat map and matrix), on a Business Model Canvas (**Export… Open in draw.io**, from the server's draw.io export) and on a `.drawio` project or library document (`openFile` in `drawioScratch.js`). Pictures of no one model (model tree, project tree) keep the plain `.drawio` download.
- `drawioScratch.js` `openInDrawio({model, title, xml, plain})` puts the picture in localStorage under a one-time key and opens `#/drawio/open/<key>` (never the picture in the address). The new tab (`ScratchDrawio.jsx`, routed in `App.jsx` beside drawn views, full screen) takes it out at once and keeps it in its sessionStorage: a reload shows it again. Too big for localStorage (about 5 MB): handed over through `window.opener`, and the tab says a reload would lose it. Keys older than a day are swept.
- The scratch view loads our draw.io (`embed=1`, plugin, `noSaveBtn=1`) with the model's setup (a minimal one for no model) and `readOnly: true, keepLook: true`, `plainLabels` for boxes that are not entities (metamodel types, a canvas, a document). Nothing on it can change the model (D408, D413).
- Its bar: **Save as a drawn view** (those who may draw: `NewDrawnView` with `sameTab`, so the tab becomes the new drawn view), **Download .drawio**, **PNG**, **SVG**, **PDF** (draw.io's export, as a drawn view's), **Close**. Close, leaving by address or closing the tab asks *Leave without saving? This picture isn't kept.*
- **File › Export as › .drawio file...** (plugin action `eaxExportDrawio`, first in the menu, the rest kept): the current diagram, uncompressed (`Graph.compressXml` off for it), named after setup's `title` (unsafe characters replaced), downloaded inside the frame; the plugin also posts `eax-exported-drawio {name, size}`. A heat map is on screen only, so never in the file. Offered on read-only views too.
- Existing drawn views were checked: every list, version, evidence and MCP link is `#/metamodel/<m>/drawn-views/<v>` (our draw.io tab); none downloads.
- Checks: plugin tests (150 pass: the menu item and its order, the file's name and content, heat never in it, read only, `keepLook`, `plainLabels`); API test `test_drawn_view_screens` (the D585 rules); a self-test journey (headless; the new step `popup` follows the new tab): open the metamodel diagram in draw.io, read only, `.drawio file` offered, Download .drawio, Save as a drawn view.
