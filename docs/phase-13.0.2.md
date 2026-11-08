# Build phase 13.0.2: every slow button as a background task

Goal: no button that may take long on a large model keeps the person waiting or fails because the request outlived
the gateway (a merge on a large model gave a 500). The work runs in the background, and the person can see it from
any page. Version **0.14.1**, migration `0023_background`. Decision **D273**, agreed with the owner on 6 Nov 2026
before building. It extends D192, under which tagging, sheets and backups already ran in the background.

## Status: built, waiting for the owner's test

## What it delivers

### Slow actions run in the background

Each of these now answers at once with a task. The job runner then does the work as the person who asked, with the
same rights checks as before.

| Where | Action | Task kind |
|---|---|---|
| Merge tab | plan a merge (another model, or an uploaded package) | `merge.analyse` |
| Merge tab | apply a merge | `merge.apply` |
| Merge tab | the merge test file, another model's package | `merge.sample`, `model.downloaded` |
| Actions > Upload | check a package | `package.analyse` |
| Actions > Upload | upload a package | `package.uploaded` |
| Actions > Download | a model package (Excel or zip) | `model.downloaded` |
| Compare | compare two sides | `compare.run` |
| Compare | the comparison as Excel | `compare.download` |
| Gap analyses | make one | `gap.create` |
| Gap analyses | compare again | `gap.refresh` |
| Gap analyses | Excel or Word | `gap.download` |
| Gap analyses | two results compared (Excel or CSV) | `gap.runs_compare` |
| Tags | download a tag | `tag.download` |
| Tags | restore a tag as the latest | `tag.restore` |
| Actions | move a model to another framework | `model.framework_moved` |
| Actions | promote into the library (with its copy) | `library.promoted` |
| Metamodel drafts | apply a draft | `draft.applied` |
| Push down | push the metamodel down | `pushdown.push` |
| Push down | accept or reject a push | `pushdown.decide` |
| Quality | Recheck all (every entity of a type) | `quality.recheck_type` |
| Change log | export as CSV or Excel | `changelog.export` |
| Projects | create a project, with its model copies (D267) | `project.created` |
| Projects | download a template library as a zip | `project.library_zip` |

These already ran in the background (D192) and now use the same drawer and notifications: tagging, building sheets,
previewing and adding a load, and backups and restores.

- **The API.** A slow route answers `{"task": {...}}`.
  - Add `?wait=true` to do the work in the request, as before (for scripts).
  - The file routes (GET) still answer the file; `?background=true` makes the file in the background instead.
  - Follow a task with `GET /tasks/<id>`. `GET /tasks?active=true` lists yours: the running ones, and those that
    finished in the last 24 hours.
  - Get a task's file with `GET /tasks/<id>/file`.
- **Quick checks still answer at once**, before anything is queued. For example, the wizard still says straight away
  that a project name is taken, or that the template library setup is not finished.
- **Progress.** A task can say how far it is (`tasks.progress(pct, note)`), and the drawer shows a bar. Rechecking
  data quality reports a percentage; project creation reports its steps (creating, copying model 2 of 3, ...). Other
  tasks show a moving bar with what they are doing.

### The task drawer

- A slim **Tasks** tab on the right edge of every page.
  - While tasks run, it shows a spinner and their count.
  - When one finishes while you are on the site, it turns green with a count.
  - It is hidden when you have no tasks.
- Clicking it opens the **drawer**, the list of your tasks. Each shows:
  - **Running**, with a progress bar and what it is doing;
  - **Completed**, with what happened, **Open** (the screen that asked) and **⬇ Download** if it made a file;
  - or **Failed**, with the reason in words.
- ✕ dismisses a finished task, and **Clear the finished ones** clears them all. Escape closes the drawer.
- The server keeps the list, so it survives a reload and shows in every browser tab. Dismissing is per browser.
- It replaces the top bar of D192.

### The Background tasks tab in Notifications

- Each task that ends sends a notification (category **task**) to the person who asked:
  - **Done: …** or **Failed: …**, with the message;
  - the link to the screen that asked;
  - **⬇ the file** while it is kept.
- They appear on the new **Background tasks** tab of Notifications (with the unread count) and in the main list.
- The bell counts them like other notifications.
- Webhooks do not get them.

### Files: downloaded at once, kept 24 hours

- If the page that asked is still open, the file downloads by itself when the task is done. This includes moving to
  other pages of EA Explorer; it does not include closing the tab.
- The file can be downloaded again for **24 hours** from three places:
  - the drawer;
  - the notification;
  - the page that asked, which lists its recent files. The merge test files and packages are on the Merge tab, tags
    on the Tags tab, the comparison on Compare, gap analyses and the change log on their own pages.
- After 24 hours the job removes the file. A file uploaded with a request (a package, a merge file) is removed as soon
  as its task ends.

### Coming back to a page

- **Merge tab.** A plan made while you were away is offered: "The merge plan made in the background is ready … Open
  it". While a plan or an apply runs, the tab says so.
- **Compare.** Offers your last comparison: "Show it".
- **Dialogs.** The upload, framework move, promote, metamodel draft, gap analysis and project wizard only move you
  to the new model or project if you are still on that page.

## How to check it (after `.\eax clean-restart`)

1. **Merge** (the 500 before): open a project model > Merge, choose another model, press *Read and compare*.
   - The page says it is working in the background, and the Tasks tab on the right shows a spinner.
   - Open the drawer: *Plan a merge … Waiting to start / Running*, then *Completed* with "Merge plan ready: …".
   - The plan appears on the page. Merge it: *Apply a merge* runs in the drawer the same way.
2. **Leave and come back.** Start a merge plan, go to another page, then come back to the Merge tab before it ends.
   When it is done, the tab offers "Open it".
3. **Download a package:** Actions > Download > Excel.
   - The dialog closes at once.
   - The file downloads when ready.
   - The drawer and Notifications > Background tasks show ⬇ with the file name.
4. **Compare and gaps:** compare two models, then press ⬇ Excel. Make a gap analysis, then press *Compare again* and
   ⬇ Word.
5. **Data quality:** Quality tab > Recheck all. The drawer shows the percentage.
6. **Project:** create a project in the wizard. You can leave while it is created. The drawer says when it is
   created, and Open goes to Projects.
7. **Failure:** for example, upload a damaged package. The drawer and the notification say *Failed* with the reason.
8. **Notifications > Background tasks:** every task above is listed, with its link and file.
9. **After 24 hours** a finished task leaves the drawer, and its file is gone.

## Not in this phase

- Stopping a running task.
- Retrying a failed task from the drawer (run the action again).
- Pushing a task's end to the browser at once (the drawer asks every 2 seconds while a task runs, and every 30 seconds
  otherwise).
- These stay as they were:
  - single-entity actions (an edit, a recheck of one entity, a document check-in), which are quick;
  - the TOGAF zip upload and adding a template library, which already load in the background (D264).
