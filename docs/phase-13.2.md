# Phase 13.2 — Tracking sheets (requested, for later)

Status: **requested for later** (owner, 8 Nov 2026). Not designed or built yet; discuss before building.

## The ask, in the owner's words (summarised)
People sometimes want to keep data in a sheet, an application portfolio for example, without the rigour of a
metamodel. These sheets:

- live at **project level** and at **organisation level**;
- are **defined**, **uploaded** from Excel and **downloaded** as Excel;
- have **no hard schema rules**: the sheet's columns are whatever was uploaded, and fields can be **added on the fly**;
- are **saved in the database**, and can be **edited in place** or downloaded;
- have **basic filters** in the web: filter the rows by column values (owner, 8 Nov 2026);
- **do not affect quality** (no validation rules, no data-quality scores);
- may later be **promoted to metamodel entities** (not part of this ask: "nothing more for now").

## Questions to settle when it is built
- Who may create, change and delete a sheet at each level (project roles; Super Admin at organisation level)?
- Does a re-upload replace the rows, add to them, or match rows by a key column?
- Filters: a text filter per column and a pick of a column's values; sorting by a column; does a download take the
  filtered rows or all of them?
- Column types: all text, or types guessed from the upload (number, date) and changeable?
- Several tabs in one workbook: one sheet each, or one sheet with tabs?
- History: keep earlier versions of a sheet, or only the latest?
- Where they show: a tab on the project, an item under Architecture work or the Enterprise Repository (13.0.9)?
- Promotion to metamodel entities later: map columns to an entity type's attributes (a separate phase).

## Not in this request
- Promoting rows to metamodel entities.
- Quality rules, checks or scores on sheets.
