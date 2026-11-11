# Industry packs (phase 39; D546 to D549)

Each industry reference model in the library has a **pack**: the owner's own files for that industry. People download
them from tiles on the library's **Pack** tab (Library › a reference model › Pack), also reached from a reference
model's page ("its industry pack").

| Tile | What |
|---|---|
| Read me first | What is in the pack and where to start |
| The book | The learner guide: a starter pack for enterprise architects in this industry |
| The workbook | Exercises and worked answers to go with the book |
| Metamodel Excel to study | The populated worked example the reference model was built from (`<Industry>_TOGAF_Metamodel.xlsx`) |
| Metamodel template | The same workbook, empty, to fill in for your own organisation |
| ArchiMate 4 views | The worked example's views, as PowerPoint |
| Excel templates | Comparison tool, maturity assessment, principles and standards, transcription forms, workshop capture |
| PowerPoints | Executive briefing, view templates, workshop pack, how-to-use decks |

Government, Logistics, Minerals and Mining and Telecommunications have only the metamodel Excel and the ArchiMate 4
views (D548): their packs show those two tiles. A tile with no file shows "Not loaded yet".

## Where the files are
- **In the repository**: `library/industry-packs/<Industry>/`, one folder per industry (Banking, Government, Healthcare,
  Insurance, Logistics, Manufacturing, Minerals_and_Mining, Pharmaceuticals, Retail, Telecommunications). The "complete
  set" zips are opened and each file kept once (by checksum). A file over 50 MB is kept as parts below 45 MB
  (`<name>.part01`, `.part02`...) with `<name>.parts.json` (name, parts, size, sha256), joined again when loaded: no Git
  LFS. These are the owner's own packs, committed at his request (the "never commit template files" rule is about the
  TOGAF templates).
- **In the API container**: mounted read-only at `/data/industry-packs` (docker-compose), not baked into the image.
- **In Documents (Mayan)**: a cabinet "EA Explorer industry packs" with a cabinet per industry, one document per file.
  `core.industry_pack_files` says which document holds which file, with its checksum.

## How they get into Documents
- **At every start** (a later step of the seed, every deployment): new or changed files only (by checksum; a changed
  file becomes a new version of its document). Unchanged files are skipped, so it is quick after the first start.
- If Documents is off or still starting, a job looks every 10 minutes and loads them once it answers.
- **By hand**: `eax packs load` (or `eax packs reload`) loads the shipped packs now; `eax packs load "<folder>"` loads
  another folder on this computer (copied into the api container first); `eax packs status` lists each pack. A Library
  Admin or Super Admin can also click **Load packs from the folder on the server** on the Pack tab.

## Bringing the owner's files into the repository
**Nothing to run by hand** (D584): every `eax up`, `run`, `restart`, `clean-restart` and `clean-run` copies what is
new or changed in the pack sources into `library/industry-packs` first (`eax packs auto`; quick when nothing changed;
nothing to do when no source folder is there), and EA Explorer loads them into Documents as it starts (the start-up
status shows "Industry packs loading n of N"). The sources: `eax packs source <folder...>` (kept in
`persist/settings.json`, so it survives resets), else `EAX_PACKS_SOURCE` in the config (several separated by `;`), else
the owner's folders in the home folder (`Enterprise_Architecture\Industry Specific Guidance`,
`Sample_Repo\Metamodels_And_Views_by_Industry`, `Sample_Repo\MetaModel_And_Views`).

`eax packs collect` (optional) does the copy now, ready to commit:

```
.\eax packs collect
.\eax packs collect "C:\Users\gaura\Enterprise_Architecture\Industry Specific Guidance" "C:\Users\gaura\Enterprise_Architecture\Sample_Repo\Metamodels_And_Views_by_Industry"
```

Without folders it reads `Enterprise_Architecture\Industry Specific Guidance`, `Sample_Repo\Metamodels_And_Views_by_Industry`
and `Sample_Repo\MetaModel_And_Views` in the home folder. It opens the zips, keeps each file once, leaves out (and lists)
any file marked not for AI use, splits files over 50 MB, and prints the total. Then commit `library/industry-packs`
and run `.\eax packs reload` (or restart).

## The rule on AI use (D547)
Every file is checked for "NOT FOR AI USE OR AUTOMATED PROCESSING" or an AI USE RESTRICTION clause (in the text of
Office files and PDFs) before it is copied and again before it is loaded; a marked file is never copied or loaded,
only listed.

## The reference models built from the packs
`tools/build_industry_models.py` (default folder: `library/industry-packs`) writes `services/api/eax/seed/industry_<code>.py`
from each `<Industry>_TOGAF_Metamodel.xlsx`; the seed loads any that is missing at start-up. Meridian Assurance's
workbook has its own layout and its own reader (D549).
