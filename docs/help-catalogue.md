# On-screen help: the help catalogue (D497, D530–D532)

Every page, tab, sub-tab, pop-up, wizard step, field and button of EA Explorer has on-screen help, from **one
catalogue**: `services/web/src/help/catalogue.json`. A test fails the build when anything on a screen has no entry.

## What people see
- **? Help** in the top bar, or **F1** anywhere, opens the help panel beside the page. It shows the help for what is on
  the screen, most specific first: the pop-up open, the wizard step, the sub-tab, the tab, then the page. Each entry
  says what it is for, how to use it and gives a short example. A search box finds help on any screen.
- **?** in the head of every pop-up opens the panel at that pop-up's help.
- **Tooltips**: resting the mouse on (or tabbing to) any button, tab, label or field shows a short tip. Elements that
  already carry their own `title` keep it; everything else gets its tip from the catalogue.

## The catalogue
One JSON object. Keys:

| Key | What | Entry |
|---|---|---|
| `page:#/route` | a top-level route in App.jsx | `{title, what, how[], example?}` |
| `tab:Label` | a tab or sub-tab, by its label (any tab bar) | `{what, how[], example?}` |
| `popup:Title` | a pop-up by its title; dynamic parts written `*` (`Merge duplicates: *`) | `{what, how[], example?}` |
| `step:Label` | a wizard step | `{what, how[]}` |
| `field:Label` | a field by its label (or aria-label, or placeholder when it has no label) | tooltip text |
| `button:Text` | a button without its own `title`, by its words (or aria-label for ✕, ▶...) | tooltip text |

Write plainly and briefly: what it is for, how to use it, a small example with invented names. Never the word
"objective" (use Outcome). Never name other products' vendors.

## Adding help for a new screen
1. Build the screen as usual.
2. Run `python3 tools/help_inventory.py --missing`: it reads the web sources and lists every route, tab, pop-up, step,
   field and button that has no help yet.
3. Add an entry for each to `services/web/src/help/catalogue.json` (a button or field that has its own `title=` needs
   none).
4. `services/api/tests/test_help_catalogue.py` passes when nothing is missing.

How the matching works at runtime (`help/help.js`): exact key first; then pop-up titles with `*` as patterns (the one
with the most fixed text wins); then, for buttons, fields and tabs, the longest key the words start with (so
`button:Add these (` covers "Add these (3)").

## Files
- `services/web/src/help/catalogue.json` — the catalogue
- `services/web/src/help/help.js` — lookups (exact, pattern, prefix), page help, search
- `services/web/src/help/HelpPanel.jsx` — the panel, F1, the ? Help button and the tooltips
- `services/web/src/ModelOps.jsx` — `Modal` has the ? button
- `tools/help_inventory.py` — what the screens need
- `services/api/tests/test_help_catalogue.py` — the build check

The usage guides are written separately, after the new UI (D496).
