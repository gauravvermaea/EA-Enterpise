# Finding your way: navigation styles, actions, right-click and quick jump

Release 0.18.0 (D478–D481, owner 10 Nov 2026). Model pages had 21 tabs and project pages 26 in one row; now each person
chooses how they are shown. No tab was added or taken away, and every `#/…` link works in every style.

## Choosing a style
Beside your name in the top bar (▦) or on **My profile**: **Grouped**, **Menu** or **Classic**. It is kept in your
browser, per person.

| Style | What you see |
|---|---|
| **Grouped** (default) | A breadcrumb, then about six **groups**, then the group's **tabs**, then the tab's own **sub-tabs** (e.g. Views › Custom views \| Standard views). A group opens on the tab you last used in it. Counts (Sign-off, Key questions, Changes) show on the group too. |
| **Menu** | A menu down the left: groups and their tabs, the one shown highlighted. « folds it to icons, » opens it. Narrow screens put it above the page. |
| **Classic** | Every tab in one row, as before. |

On **first sign-in**, a person who has not chosen yet is asked once, before the page: the three styles side by side,
each with a small sketch and one line, Grouped marked *Recommended*. Choosing one saves it; **Esc** or **Skip** keeps
Grouped and does not ask again. Automated browsers (Playwright and the tests, `navigator.webdriver`) never see it;
add `?welcome=1` to the address (before the `#`) to show it on purpose, e.g. for a screenshot.

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

## Quick jump (Ctrl+K)
Ctrl+K (⌘K on a Mac), or ⌘K beside your name: type to go to a tab or action of the page you are on, a part of EA
Explorer, a model or a project. Near spellings work ("fynbos comm" finds Fynbos Commercial). ↑ ↓ choose, Enter goes,
Esc closes.

## Screens that are tabs (0.19.0, D542)
A screen used to be reachable only through ⋯ Actions or a tile is a tab of its own, in every style:
model page **Quality › Duplicates**, **Reports › Report designer**, **Reports › Power BI and Excel** (the OData address),
**Manage › Merge requests** (project models); Model admin **Changes › Send for merge** (a child project model). Old links
(`#/metamodel/<m>/quality/duplicates`, `#/metamodel/<m>/reports/designer`) open the new tabs. ⋯ Actions keeps the things
that do something (add, load, export, record).
