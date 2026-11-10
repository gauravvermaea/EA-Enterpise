# EA Explorer's published import formats

Other systems send data to EA Explorer by writing these formats (D370). EA Explorer is not an ETL tool: it publishes the
formats, and whatever produces the data (a configuration database, a finance system, a script, a future connector) writes
them. Phase 34 and 34.1; decisions D370, D378, D385, D462 to D468.

| Format | What it is | File |
|---|---|---|
| **Excel format** | The import and export sheets of phase 10.1: one sheet per entity type, a Relationships sheet, drop-downs | `.xlsx` (or `.xlsm`) |
| **CSV format** | The Excel format as separate files: one CSV per sheet, plus `master.csv` saying which file holds what (D378) | a `.zip`, or the CSVs and `master.csv` dropped in a folder |
| **ArchiMate 4 exchange format** | Accepted once The Open Group publishes it (D385). Until then an `.xml` delivery is refused with that reason | `.xml` |

The empty template of either format for any model is made on the fly: the model's **Import and export** tab ›
Download and upload › choose the types › tick **Empty template** › Excel or CSV set. It has exactly the columns and
drop-down values that model accepts. (API: `POST /api/v1/models/<model>/sheets` with `{"types": [...], "format": "xlsx"|"zip", "blank": true}`.)

## The Excel format

One sheet per entity type, named by the type. Row 1: the column names (`*` marks a required one); row 2: the field codes
(hidden; this is how EA Explorer knows each column); data from row 3.

| Column code | Meaning |
|---|---|
| `guid`, `display_id` | EA Explorer's own keys. In an upload they match rows; **in a delivery they are ignored** (D463) |
| `name` | The entity's name: **how a delivery is matched**, with the type |
| `description`, `parent`, `tags` | As in the screens (`parent` by name or ID; tags comma-separated) |
| one column per attribute code | Values as text: dates `YYYY-MM-DD`, Yes/No, numbers with a point, a pick list's value. A Link attribute holds one link a line, `address | note` |
| `delete` | Yes deletes in an upload. **A delivery never deletes** (it is shown as a problem) |

The **Relationships** sheet: `source`, `relationship_type` (code or name), `target`, `name`, `delete`. Ends are given by
name, display ID, or the provisional ID of a new row in the same file (`NEW-APP-0001`).

## The CSV format

The same columns, one CSV per sheet, first line the field codes. UTF-8 (with or without BOM; Windows-1252 is read too),
comma, semicolon or tab. `master.csv` lists the files:

```csv
file,kind,entity_type,entity_type_name
applications.csv,entities,ApplicationComponent,Application Component
technology.csv,entities,Node,Node
relationships.csv,relationships,,
```

`kind` is `entities` (with the type's code or name in `entity_type`) or `relationships`. Only the files it names are
read. Example `applications.csv`:

```csv
name,Vendor,Version,Hosting,Url
Quote Optimiser,Kestrel Labs,1.4,SaaS,https://quote.example.org | product page
Broker Portal,,,,https://portal.example.org/help | broker help
```

and `relationships.csv`:

```csv
source,relationship_type,target,name
Container Platform,Serving,Quote Optimiser,hosts
```

## Delivering

A **source** is set up once per system on the model's **Import and export › Deliveries** (Model Admins): its name, its
folder, whether its values win, who is told, and optionally the service account that sends it. A delivery arrives in one
of three ways:

1. **A folder.** Drop the files in the source's folder, `deliveries/<model id>/<source folder>/incoming` in EA Explorer's
   import folder (the `eax-imports` volume, or the folder `EAX_IMPORT_DIR` names, which IT may map or mount to SFTP or a
   share; D378). Then ask for them to be taken: `POST /api/v1/import-sources/<source id>/collect`, **Take dropped
   files** on the Deliveries tab, or `eax import <source>` on the host. A CSV set is taken once `master.csv` and every
   file it names are there; each workbook, `.zip` or single CSV is a delivery of its own. Taken files move to
   `done/<when>/`, refused ones to `failed/<when>/` with a `.why.txt`.
2. **The API.** `POST /api/v1/import-sources/<source id>/deliveries` with the file as multipart field `file`, signed in
   as the source's service account (System admin › Machine access: a token or API key with read-write on the Models area)
   or anyone who may load into the model:
   ```
   curl -H "Authorization: Bearer eaxt_..." -F file=@cmdb.zip https://ea.example.org/api/v1/import-sources/<id>/deliveries
   ```
3. **An upload** on the Deliveries tab (Upload a delivery).

## What happens to a delivery

- It is **matched by type and name only** (D463): an entity of that type with that name is updated; none makes a new
  one; several with that name is a problem. Renaming at the source makes a new entity.
- It **only adds and changes**: it never deletes entities or removes relationships, and an empty cell leaves the value.
- Unless the source's **values win**, values already in EA Explorer stay and only empty fields are filled; the preview
  lists each value kept (D464).
- It is previewed (new, changed, kept, unchanged, problems) and **waits for review**. The source's contact and the
  model's Committers and Model Admins are told.
- A Committer, Model Sub Admin or Model Admin **accepts** it: its rows become their changes, committed at once as their
  load (undo it on the load page like any load), or **declines** it (D465).

## A model from a metamodel workbook (D419, D468)

A different workbook: the **metamodel only** (no data). Models › **Model from a metamodel workbook**: download the empty
template or any model's metamodel in the same layout, change it in Excel, upload it, check what it would make, and make a
project model, either blank (the workbook is the whole metamodel) or added to an existing model (it adds and updates,
never takes away). Sheets, row 1 the field codes:

| Sheet | Columns |
|---|---|
| Model | `field`, `value`: name, framework, version, description |
| Domains | `code`, `name`, `colour` (six hex digits), `description` |
| Pick lists | `code`, `name`, `description`, `values` (one a line in the cell) |
| Attributes | `code`, `name`, `data_type` (drop-down; `url` is a Link), `pick_list`, `unit`, `description`, `quality_weight` |
| Types | `code`, `name`, `domain`, `id_prefix`, `aspect`, `description`, `notation`, `fill_colour` |
| Type attributes | `type` (an entity or relationship type's code), `attribute`, `required` (Yes/No), `section`, `default`, `help`, `quality_weight` |
| Relationship types | `code`, `name`, `verb`, `category`, `directed` (Yes/No), `description` |
| Allowed relationships | `source`, `relationship`, `target`, `source_multiplicity`, `target_multiplicity` (`1`, `0..1`, `1..*`, `0..*`, `2..5`), `note` |
| Rules | `entity_type`, `attribute`, `field`, `rule_type` (drop-down), `param1`, `param2`, `severity` (error or warning), `message` |

API: `GET /api/v1/metamodel-workbooks/template[?model=<id>]`, `POST /api/v1/metamodel-workbooks/preview` and
`POST /api/v1/metamodel-workbooks` (multipart `file`, `name`, `base`, `description`).
