# Phase 13.0.8: the organisation's reference library (version 0.14.8, D300)

**State:** built (8 Nov 2026), waiting for the owner's test. Migration 0030; `eax/reference_library.py`,
`eax/text_extract.py` (PDF through pypdf, added to requirements), `ReferenceLibrary.jsx`; routes `/api/v1/reference-library...`.

## What it is
One reference library for the whole organisation, beside each project's own Reference area (D296, which stays as it is).

- **Content:** documents (files) and links (web addresses).
- **Structure:** a free folder tree made by Super Admins; each entry also has a title, a description, its source
  (a standards body, a regulator, a team) and tags.
- **Search:** titles, descriptions, sources, tags *and the text inside documents* (PDF, Word, PowerPoint, Excel,
  OpenDocument, plain text and HTML; read by the application when a file is uploaded; a scanned PDF has no text).
- **Versions:** uploading a new file keeps the earlier versions (each is its own document in Documents) and any
  version can be downloaded.
- **Who:** everyone signed in reads it; Super Admins add, change, move and delete.
- **Where:** its own area tile and menu, **Reference library**, beside Architecture work.
- **Projects:** a project's Reference tab can pick an entry of the organisation's library and add it as a link;
  the link always opens the library's current version.

## Where
- Its own area tile and the menu (*References*; *Reference library* in the second menu): `#/reference-library`.
- A project's Reference tab: a tab *📚 Enterprise reference library* and a button *📚 From the enterprise library* that
  links entries into the project's Reference area (the link opens the library's entry).

## Checks (when built)
1. As a Super Admin make folders, upload a PDF and a Word file, add a link; tag them.
2. As any other user: browse, filter by tag, search for a word that is only inside the PDF; open and download.
3. Upload a new version; download the earlier one.
4. As a non Super Admin: no add, change or delete buttons, and the API refuses them.
5. In a project's Reference tab, link an entry from the organisation's library; open it.
