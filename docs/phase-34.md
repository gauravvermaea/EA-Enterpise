# Build phase 34 and 34.1: published import formats and deliveries; a model from a metamodel workbook

Version **0.18.0** (batch 2, D421), migration `0042_import_formats`. Decisions D370, D378, D385, D419, D462 to D468.
The formats themselves, with examples: [import-formats.md](import-formats.md).

## Status: built, to be accepted (10 Nov 2026)

## What it delivers

- **Published formats** (D370, D378): the Excel format (today's import sheets) and the CSV format (one CSV per sheet plus
  `master.csv`). A CSV set downloaded from EA Explorer now carries its master file; sets without one load as before. Empty
  templates of both for any model, made on the fly (Download and upload › Empty template). The ArchiMate 4 exchange
  format is refused with its reason until it is published (D385, D467).
- **Import sources** (D462): Import and export › **Deliveries**: each system that delivers to the model, its folder,
  whether its values win, who is told, the service account that sends it, on or off (Model Admins).
- **Delivering** (D466): files dropped in the source's folder and taken on request (the API, Take dropped files, or
  `eax import` in all four forms), sent to the API by a service account, or uploaded on the tab.
- **Review** (D463 to D465): matched by type and name; only adds and changes; values in EA Explorer kept unless the
  source's win (each kept value shown); previewed and waiting; accepted by a Committer as their committed load (undo as
  any load) or declined.
- **A model from a metamodel workbook** (D419, D468): Models › Model from a metamodel workbook: template (empty or any
  model's metamodel, round trip), check, then make a project model blank or added to an existing model.

## Demo (laptop, after `.\eax clean-restart`)

1. As `user_committer`, Protea Insurance (demo estate) › Manage › Import and export › **Deliveries**: two deliveries wait.
   Open *cmdb-2026-11-10.zip* (from the Configuration database, sent by svc-cmdb-sync): Quote Optimiser new with its
   Link, Broker Portal changed (an empty Documents field filled), CRM's vendor **kept**, Actuarial Modelling asking to be
   deleted (a problem), a row with no name, a relationship by names, one whose end is not found. **Accept and commit**.
2. *finance-2026-11.zip* (Finance system, its values win): Billing Engine's and CRM's costs change. Earlier deliveries:
   one accepted, one accepted then undone, one declined with its reason.
3. The Configuration database shows **1 file dropped, not taken yet**: **Take dropped files** makes it a delivery.
4. As `user_model_admin`: **+ Add a source**; Change a source (values win, on or off).
5. Download and upload: tick Application Component, **Empty template**, CSV set: the zip has `master.csv`.
6. On the host: `.\eax import` lists the sources; `.\eax import "Configuration database"` takes what is in its folder.
7. As `user_model_creator` (or Super Admin), Models › **Model from a metamodel workbook**: download *Its metamodel* for
   ArchiMate 4 and upload it back on ArchiMate 4: nothing added or changed. The sample **Reinsurance programme (from a
   workbook)** was made from one: Treaty, Cedent and Work package, a Documents Link, Treaty Covers Cedent 0..* to 1..*.

## Checks

- `pytest tests/test_import_formats.py`: the migration, master files, the exchange format refused, safe folder names,
  machine-access areas, reading a filled workbook, adding to a base never takes away, who may create, the delivery rules,
  `eax import` in every form and the help.
- Run on a fresh test database through the preview: a delivery previewed (new, changed, kept, problems), accepted and
  committed, the same file from a values-win source, declined, folder collection with a CSV set and a refused `.xml`, the
  round trip of ArchiMate 4's workbook (no changes) and two models made from a workbook (blank and on ArchiMate 4).

## Not in phase 34

- Connectors to particular products: they write these formats when they are built.
- Watching the folder: files are taken on request (D466).
- Sources and deliveries in a model's package: they are in the database's backups, like loads.
