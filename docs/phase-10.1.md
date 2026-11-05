# Build phase 10.1: import and export sheets

Goal: get data in and out of a model in bulk, with spreadsheets people already know. Version **0.10.1**, migration
`0017_sheets`. Decisions D77, D78, D88, D192, D197.

## Status: accepted and closed (5 Nov 2026)

## What phase 10.1 delivers

A **Import and export** tab on every model that holds content, with four parts:

- **Download and upload** (one screen):
  - **Download**: choose entity types (by layer, filter, or every type with entities) and a format; the workbook is
    built on the fly from the metamodel: one sheet per type with every entity and its values, and a **Relationships**
    sheet with the relationships between the chosen types (it comes automatically). One download is both an export and
    the template to fill in.
  - The sheets: GUID and ID (display ID) columns are visible; columns marked * are required; pick lists, Yes/No, Parent
    ID, Delete and both ends and the type of a relationship are drop-downs. Empty rows below the data are ready to fill:
    a new row gets a provisional ID (`NEW-APP-0029`) as soon as it has a name, so a relationship can point to it before
    it is loaded. A row with no GUID is accepted.
  - Formats: **Excel (.xlsx)** with formulas and no macros; **Excel with macro (.xlsm)**, the same plus a macro that
    writes a GUID into each new row (Excel asks to allow macros); **CSV set (.zip)**, one CSV per type plus
    relationships.csv, for feeds and other tools.
  - **Upload**: an EA Explorer workbook or CSV set, or a CSV or workbook from another system. A **preview** comes first,
    worked out in the background: each row new, changed (field by field, old struck through), unchanged, to delete
    (Delete = Yes), or a problem (a value that is not a number or date, a new row without a name, a relationship end
    not found...). Rules give warnings as everywhere (D48). **Correct** a row on screen; the preview is worked out
    again. **Add to my uncommitted changes**: the rows become your own changes (D165), which you commit (or ask a
    committer to) on the Changes tab.
  - **Matching**: by GUID, then by ID; a row with neither (another system's file, a feed) by type and name when exactly
    one entity has that name (the preview says "by name"); otherwise it is new. A relationship to a row that has no ID
    yet is a problem: load the entities, then load again.
- **Loads**: every load you may see (yours; everyone's for committers and Model Admins), with its status. **Undo the
  load**: its uncommitted changes are discarded, committed ones rolled back as a new commit.
- **Saved column mappings** are listed under Loads.
- Building sheets, previews and adding a load run as **background tasks** with the bar at the top (D192).

## Demo

1. `.\eax clean-restart`. As `user_architect`, Protea Insurance (demo estate) > **Import and export**: tick Application Component
   and Capability, **Build and download**. Open it: the two type sheets, Relationships, drop-downs, the green ID cells.
2. Change a description, type a name in an empty row (its ID appears), add a relationship from that ID on the
   Relationships sheet, put Yes in Delete on another row. Save, **Upload and preview**: 1 changed, 1 new, 1 to delete,
   1 new relationship. **Add**: the bar says when done; the Changes tab lists them. **Undo the load** discards them.
3. **Loads** already has *Protea application review (sample)*, previewed. Upload `deploy/samples/cmdb-applications.csv`:
   map its columns (or choose the saved mapping *CMDB applications*): 3 applications found by name, 2 new.
4. Download the .xlsm, open it in Excel, allow macros, type a name in an empty row: a GUID appears in column A.

## Checks

- `tests/sql/phase10_1_checks.sql` (as the API's login): ends with "phase 10.1 checks passed".
- `pytest`: `test_sheets.py` (CSV dialects, matching values, the VBA project read back as a compound file, the .xlsm
  parts, API and screens).

## Not in phase 10.1

- The .xlsm was checked against the published formats here, not in Excel: if Excel reports a problem with it, the .xlsx
  works the same without the macro.
- Collection sets, feeds and scheduled exports: phase 34, after a design session on protocols (D198). Survey sheets: phase 38.1.
