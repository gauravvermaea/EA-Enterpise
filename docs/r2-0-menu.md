# R2.0: a usable UI with a simple menu

The owner's direction (11 Nov 2026): a menu-driven interface, simple, with nine areas; a "/" search for functionality
and content. Built 11 Nov 2026 (D586–D590), placed again the same evening after the owner tried it (D591); to be accepted. Answers:

| Question | Answer |
|---|---|
| What "User" holds (Profile is separate) | My home and my work |
| How the menu looks | One **top menu bar**: the nine areas across the top, each a drop-down of its items |
| The navigation styles Classic, Menu, Grouped and the first-login chooser (D478–481) | The left-menu style and the first-login chooser **removed**; in the new menu style page tabs show grouped (as Grouped did). **Classic stays for now** (owner, 20:52): anyone can switch between the new top menu (the default) and Classic with a setting at the top right; the owner says when to remove Classic |
| Areas or items a person may not use | **Hidden** |
| Where everything goes | The proposal below, accepted as it is ("Yes, build it this way") |
| Wizards | **Sub-menus** in Model Admin and Project Admin (and System Admin), opening the wizard |
| Work-related items | Take you to Architecture Work |
| After trying it (21:41) | Wizards opens its wizards page when clicked; Last model and Last project side by side; Repository & Content Framework holds the Architecture Repository and the Content framework (and on a project, the two tabs sit together); Documentation on the right as **?**; User and Profile one menu on the right under the person's name, with Sign out; Farm Admin a site picker pinned at the top left (● Local); Menu or Classic a toggle button |
| Nothing left out | Every feature reachable: a test checks it (below) |

## "/" search

Press **/** anywhere (Ctrl+K too) for one box that finds **functionality** (every menu item, screen, tab, wizard and
action, by name and by its on-screen help) and **content** (entities, models, projects, views, documents, people), and
goes straight there.

## The menu (every screen built in Release 1, placed once; as built, D591)

**Top left: ● Local** (the site picker; Super Admins): Local (this site), Sites (Farm Admin), Connect to a site

**Architecture Work**: My projects (yours, when opened), My models (yours, when opened), Compare and analyse (Compare
models, Gap analysis, Common analysis), Merge requests, Change log, Model library, Project library (these two for everyone, admin or not: D594)

**Model Admin**: Wizards (click: the wizards page; or Start a model, Copy and derive, Merge and propagate, Data and
quality, Metamodel, Lifecycle, Library and publishing, People and family, Packages › each wizard), Models, Model
hierarchy, Metamodel drafts, Model library (every library model, external reference models)

**Project Admin**: Wizards (click: the wizards page; or New project, On a project › each wizard, Template libraries, A
new model for a project), Projects, Project bases, Templates and libraries (Project library, Project templates, Project
content template library, Template setup), Principles, Surveys and maturity

**Repository & Content Framework**: Architecture Repository (click: the repository; or The Architecture Repository, Architecture landscape,
Reference architectures, Governance log, Architecture capability › each part), Content framework (click: the content
metamodel; or Content metamodel, Model hierarchy, Metamodel drafts), Libraries (Reference library, Enterprise library,
Model library, External reference models, Project library)

**System Admin**: Wizards (click: the wizards page; or each wizard), Settings (Application, System, Banner, Licences),
Users and roles, Running (Health, Containers, Scaling, Operations, Data quality), Backups and restores, Updates and
deploy, Tools (Command centre, SQL, Self-test), Machine access, AI activity (MCP)

**Top right**: the **Menu | Classic** toggle; **your name and role** (Home, My tasks › Requests to me, Requests I sent,
New request, Background tasks, Merge requests; Surveys to answer; Notifications; Recent and pinned; Search everything; My
profile and skills; My tokens and keys; Sign out); **?** (Help for this page, Documentation: every document, Getting
started, What EA Explorer does, Release notes, Command line, Connect your AI assistant (MCP), API)

On a **project page** the Architecture group starts with the project's Repository and its Content framework, side by
side.

## As built

- **The menu**: services/web/src/menu.js (the nine areas, their items and sub-menus, who may see each); the bar:
  TopMenu.jsx (click or hover opens; Esc closes; ↑ ↓ → ← move; a sub-menu near the right edge opens to the left).
- **Wizards**: services/web/src/wizardLists.js holds the Model, Project and System Admin wizards for the pages and the
  menu; a menu item opens the page with `?wizard=<k>` and the wizard opens (D587).
- **Hidden when not allowed** (D588); an empty sub-menu or area is hidden too.
- **Menu | Classic**, a toggle button at the top right in both styles (D589, D591); Classic shows the two rows of 1.0 and every page tab in one row.
- **Find** (D590): / or Ctrl+K, or the box at the top.
- **The site picker, ● Local** (Farm Admin, Super Admins), pinned at the top left: Sites and Connect to a site say what R2.1 and R2.2 bring and what can be done today.
- **Nothing left out**: services/api/tests/test_menu_reachable.py fails when an address any screen links to is neither in
  the menu nor listed as opened from a page in it; and checks every System Admin tab, Project Admin tab, Repository
  part, notification tab, the 1.0 areas and Classic menu items, and the wizard sub-menus.
- Differences from the first proposal: *My uncommitted changes* and *Notification settings* under Profile are not
  there: uncommitted changes are on each model's Changes tab (My models › a model), and there are no notification
  settings to show yet. *Reports* is on each model's page (My models › a model › Reports) and under Repository ›
  Governance log › Performance measurement.
