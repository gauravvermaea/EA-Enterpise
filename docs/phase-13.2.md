# Phase 13.2: tracking sheets (D325)

**Accepted and closed by the owner, 8 Nov 2026 (D337).**

## Status: built (8 Nov 2026), waiting for the owner's test

Light sheets kept without the rigour of a metamodel: an application portfolio, vendors, costs. `eax/tracking_sheets.py`
(not `eax/sheets.py`, which is the metamodel's import and export sheets of phase 10.1), `TrackingSheets.jsx`; tables
proj.sheets and proj.sheet_rows (migration 0032); routes `/api/v1/tracking-sheets/<org|project>...`.

## Decided (owner, 8 Nov 2026)
- A **Sheets** tab on each project (anyone who contributes creates, edits and deletes) and the organisation's sheets on
  Repository › tracking sheets (Super Admins and Library Admins; everyone reads).
- Uploading again: chosen each time: replace every row, add the rows, or update the rows matched on a key column (the
  others added). Columns in the file the sheet lacks are added.
- Every value is text; only the first tab of a workbook is read; only the latest version is kept.
- Filters: a filter and a pick of values per column, a search over every column, sorting by a column; the download is
  every row or the filtered ones.
- No data quality; not promoted to entities (later, if asked).

## Test steps
1. `.\eax clean-restart`, Ctrl+F5.
2. Karoo Re cloud migration (sample) › **Sheets**: open *Application portfolio (working list)*: filter TIME = Migrate,
   type in a column's filter, sort by Annual cost, search; ⬇ Filtered rows and ⬇ Excel.
3. Edit a cell (saved when you leave it), ＋ Row, ＋ Column, a column's ⋯ (rename, move, remove), tick rows › Delete.
4. ⬆ Upload… a workbook: Add, then Update on the Application column, then Replace.
5. ⬆ From Excel or CSV… makes a new sheet from a file.
6. Repository › tracking sheets: *Vendor contracts*; as an architect you can read it but not change it.
7. As a Stakeholder on the project, the sheets are read only.
