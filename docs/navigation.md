# Finding your way: the menu bar, actions, right-click and Find

Release 0.18.0 (D478–D481, owner 10 Nov 2026). Model pages had 21 tabs and project pages 26 in one row; now each person
chooses how they are shown. No tab was added or taken away, and every `#/…` link works in every style.

## The menu bar and the menu style (R2.0, D586–D591)
Since R2.0 the top bar is two rows: the site picker (● Local), EA Explorer, Find, the bell, Last model and Last
project; then **Architecture Work, Model Admin, Project Admin, Repository & Content Framework, System Admin**, each a drop-down with
sub-menus, and on the right your own menu (your name: your work, your profile, Sign out)
and **?** (help and documentation). Wizards in Model, Project and System Admin open their wizards page when clicked, or
one wizard from the sub-menu. What you may not use is not shown. Where everything is: [r2-0-menu.md](r2-0-menu.md).

Each page's tabs are **grouped**: a breadcrumb, then about six **groups**, then the group's **tabs**, then the tab's own
**sub-tabs** (e.g. Views › Standard views | Custom views). A group opens on the tab you last used in it. Counts (Sign-off,
Key questions, Changes) show on the group too. The Classic style (the menus of 1.0 and every tab in one row) is gone: its
button first (D603), then its screens (owner, 12 Nov 2026, R2.25, D606); every address it had is in the menu bar.

The left-menu page-tab style and the first sign-in question of 0.18.0 are gone (D589).

## The groups
**Model page**

| Group | Tabs |
|---|---|
| Content | Data entry · Grid · Hierarchy · Graph · Changes |
| Views | Views · Business views |
| Quality | Quality · Failing checks |
| Reports | Reports · KPIs |
| Metamodel | Entity types · Relationship types · Metamodel · ER diagram |
| Manage (More for those who don't administer the model) | Tags · Merge · Push down · Change documents · Import and export · People · Backups |

Tabs that only some kinds of model have (Quality, KPIs, Changes, Merge, Push down, People, Backups) keep their rules.

**Project page**

| Group | Tabs |
|---|---|
| Overview | Home · Project report · Tasks · Calendar · Sign-off |
| Plan | Phases · Charter · Base · Content framework |
| Business | Organisation · Stakeholders · Key questions · Business model canvas · Business artifacts |
| Architecture | Models · Enterprise Repository (project scope) · Views · Model reports · Quality · Gaps and comparison |
| Governance | Principles · Standards · Governance log |
| Documents | Library · Other views and documents · Sheets |

**Model admin**: Wizards · Changes (Merge, Merge requests, Push down, Change documents) · Admin (Metamodel, People,
Tags, Backups, Family).

A tab added later that no group names shows under **Other** until it is given a group (PageNav.jsx).

## ⋯ Actions
At the right of the tab row (top right of the page in the Menu style): the actions that make sense on that tab and that
you may do, then the page's own (Model wizards, Edit the project, Project wizards…). Keyboard: Down or Enter opens,
arrows move, Esc closes. Tabs add their actions in one place, `services/web/src/navActions.js`:

```js
registerActions("model", "grid", (ctx) => [
  { label: "Load from Excel or CSV", href: `#/metamodel/${ctx.id}/import`, ok: canOn(ctx.id, "model.content") },
  { label: "Something", run: () => { /* … */ } },
]);
```
`page` is `model`, `project` or `admin`; tab `"*"` adds to every tab of the page; `ok: false` hides an item.

## Right-click on an entity
On any row, card or link that leads to one entity: Open, Edit…, Show in a graph, History, Related entities, Where it
sits (tree), Add to a view…, Compare with earlier versions, Delete…. Edit and Delete appear only for those who may
change the model, and the server checks again. Shift + right-click gives the browser's own menu; text boxes and the
drawing keep theirs.

## Find: / or Ctrl+K (D481, D590)
**/** anywhere outside a text box or a grid, **Ctrl+K** (⌘K on a Mac), or **Find a function or
content** at the top: type to find
- a **function**: every menu item you may use, shown with where it is in the menu (e.g. *Backups · System Admin ›
  Backups and restores*); the tabs and actions of the page you are on; the on-screen help's pages, found by what they do;
- **content**: models, projects, and entities as you type (from search), with their type and model;
- the last line, **Search everything** for the words.

Near spellings work ("fynbos comm" finds Fynbos Commercial). ↑ ↓ choose, Enter goes, Esc closes.

## Screens that are tabs (0.19.0, D542)
A screen used to be reachable only through ⋯ Actions or a tile is a tab of its own, in every style:
model page **Quality › Duplicates**, **Reports › Report designer**, **Reports › Power BI and Excel** (the OData address),
**Manage › Merge requests** (project models); Model admin **Changes › Send for merge** (a child project model). Old links
(`#/metamodel/<m>/quality/duplicates`, `#/metamodel/<m>/reports/designer`) open the new tabs. ⋯ Actions keeps the things
that do something (add, load, export, record).
