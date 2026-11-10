# Phase 13.1: project bases, standards, governance log, charter (versions 0.15.0 and 0.15.1, D303 to D314)

## Status: accepted and closed (8 Nov 2026, D315)

Migration `0031_project_bases` (after 0029 content framework and 0030 the reference library's tables). Rebuild with
`.\eax clean-restart`. (The earlier plan's "13.1 approvals" was built in 13.0.1 to 13.0.6.)

## What it delivers
- **The TOGAF 10 content metamodel (D303)**: a new built-in root metamodel (from Root, read-only): 38 entity types from
  motivation and strategy to technology and governance, each placed in the content framework; 8 relationship types and
  50 allowed relationships. "Outcome" stands where TOGAF says objective.
- **Project bases (D303)**: a hierarchy like the models': **Empty project › TOGAF 10 project › Organisation base ›
  every project**. The first two are read-only for everyone; the Organisation base is changed by Super Admins. The TOGAF
  10 project holds every ADM step (116), every document type (171) with the shared template libraries, the TOGAF 10
  metamodel, 28 principles and 27 standards and a charter; the Organisation base starts as a copy. Every project derives
  from the Organisation base (existing ones are put under it); a Super Admin may put a library project under the Empty
  project or the Organisation base (project Base tab).
- **Offered down (D304)**: a new project takes its base's principles, standards, steps and charter at once. A running
  project's **Base tab** lists what is new or changed in its base; a Project Admin or Lead Architect takes or skips each
  (or everything). Principles and standards from the base are **mandatory**: not changed, removed or skipped (🔒); a
  project adds its own and asks for a dispensation in its governance log.
- **Principles and standards by group (D305)**: principles named after TOGAF 10's examples plus security ones, in our
  own words; standards for business, data, application, technology and security. Groups are open: add an "AI" group by
  typing it. A **Standards** tab beside Principles.
- **Governance log (D306)**: decisions, dispensations, compliance assessments, risks and issues, each a tab, plus kinds
  of the project's own (name, prefix, statuses). Records have a reference (DEC-001), status, owner, dates, the principle
  or standard they concern, related items and rich-text detail.
- **Architecture charter (D307)**: a page of sections (purpose, scope, authority, governance and board, principles and
  standards applied, roles, method, compliance and review), from the base; a Project Admin or Lead Architect changes and
  approves it (a change after approval makes it a draft).
- **Skills** as tags on the Organisation tab (filter by skill). *Changed 9 Nov 2026 (D353): each user adds their own skills on My profile; the Organisation tab shows a linked user's skills from there.*
- **Project admin › Project bases**: the hierarchy drawn as a tree like the model hierarchy (graph, or a list); choose a base or project to see its principles, standards, steps,
  document types with templates, and charter in one place.
- **Architecture work**: Tiles, List and **Hierarchy** (a drawn tree, or indented) for projects and models; a **Repository** view for projects,
  empty until phase 13.0.9.

- **Last model and last project** at the top right, one above the other: the model or project you are in, or the last
  one opened; changing project keeps the tab.
- The project tab **Enterprise Repository (Project Scope)** (was Architecture repository): this project's own repository, empty until 13.0.9.
- The shipped samples keep **Meridian**, a fictitious company (owner, 8 Nov 2026).

- **Project admin › Project templates**: *Open* a template to read what it decides (purpose, depth, domains, phases,
  models by role, goals, views, steps left out, stakeholders, reference links, finish); *＋ New project* (on the row
  or in the template) starts the wizard from it.

- **Documents (D308)**: a document's name apart from its file (Business Model Canvas, file questions_for_bmc.xlsx); a
  document with no file yet (*Add it, file later*, then *⬆ Add the file…*), also in the wizard for your own classes;
  each document a Deliverable, an Artifact or neither (no approval; click its D/A/– badge to change); *Rename…* in ⋯.
  A class in use with no document shows "no document yet". Check-in fixed for Mayan 4 (action_name).
- **Completion (D308)**: phases only. *Mark the phase complete* / *Reopen the phase* on Home's phase view; *✔ Mark the
  project complete* / *↺ Reopen the project* in the project's header (Project Admin, Lead Architect).
- **Project report** is a project tab of its own (no longer inside Home).
- **Base tab** draws the chain of bases as a small tree.
- **A model's Metamodel tab**: *Find an entity by name*; on an entity type, *▦ Open the … entities (grid)*.

## Checks
1. Project admin › Project bases: Empty › TOGAF 10 › Organisation base, the projects under it. Click each base: its
   principles, standards, steps, document types and charter.
2. Open the TOGAF 10 project as a Super Admin: nothing can be changed. Open the Organisation base: add a standard.
3. A sample project: the banner says what its base offers; Base tab › Take everything. The new standard appears.
4. Principles and Standards: base items show 🔒 and cannot be changed; add your own, also under a new group "AI".
5. Governance log: log a decision and a dispensation against a standard; add a kind "Assumption" and log one.
6. Charter: change a section, approve, change again (draft again).
7. Organisation: the linked users' skills (from My profile, D353); filter by skill.
8. Architecture work: Hierarchy for projects and for models; Repository shows the empty placeholder.
9. Make a new project: it is under the Organisation base with its principles, standards and charter.
10. Back up a project and restore it as new: standards, governance log, charter and its base come back.

## Documents in the wizard, several content framework areas (D309, D310)
- Wizard › Phase by phase: each phase has **Steps** and **Documents** tabs. Documents is a table: document type, D/A,
  description, templates (library › file, or Blank), content framework areas, Take out. **Not added** below lists the
  library's document types not in the project, each with ＋ Add. "📚 Browse the libraries…" adds any template of any
  library the person may use; its library joins the project's libraries. Own document types have the same columns.
- Content framework: an entity type, document type or document may sit in several areas (stored as codes joined by
  commas). The metamodel editor ticks areas; the Content framework tab's "Areas…" picker; Home › Documents › # (tags)
  also places a document; its areas show as chips next to its tags.

To test:
11. Edit a project › Phase by phase › Documents: change a description, D/A, add a template by browsing, take a template
    out (Blank), tick two content framework areas, take a document type out and add it back from Not added. Save; on
    the Content framework tab the document type shows in both areas.
12. Home › Documents › # on a document: add tags and tick two areas; the chips show; the Content framework shows it in
    both areas.
13. Metamodel › change an entity type: tick two areas; the Content framework shows the type in both.

## The documents table and repository tags (D312, version 0.15.1, migration 0032)
- Home › Documents: a table of document classes. ▸ opens a class: tabs **Documents** and **Templates**. ▸ on a document
  shows its versions only (each with ⬇ Download). ⋯ › "Everything that happened to it…" keeps the full log.
- Templates tab: download, "＋ New document from it", "📚 Add a template from a library…", "Take off" for added ones.
- Toolbar: **🏷 Repository tags…** (tag now; download as at a tag; bring the repository back to a tag), **⬇ Download all**
  (a zip, a folder per class); per class ⬇ Download.

To test:
14. Open a class: Documents and Templates tabs; add a template from a library; make a document from it.
15. Check a document out and in twice; open it (▸): three versions, each downloads.
16. Repository tags: tag "T1"; change a document and add one; Download as at T1 (zip has the old version); Bring the
    repository back to T1: a tag "before application of tag T1" appears, the changed document has a new version copied
    from T1, the new one is archived.

More to test (D313, D314):
17. Home: the cycle and About; click a phase, Open phase →. Phases tab: Documents, Not added / won't need, Steps, Views.
18. Mark a class "won't need": it moves to Not added / won't need; ↺ Bring it back. With a document checked out it is refused.
19. A document: 🕘 History shows its versions; ⋯ closes when clicking elsewhere.
20. Check in the same file again: refused ("nothing changed").
21. New project wizard › Charter: change a section; the project's Charter tab shows it as a draft.
22. Architecture work: ☆ Pin a project and a model (also on their own pages); "pinned only".
23. A link to another project's document: clicking it opens that project's phase with the document highlighted.

## Not in this phase
- The Architecture Repository's own design (13.0.9): where each part points is to be discussed (owner, 8 Nov 2026).
- The organisation's reference library screens (13.0.8).

## Added after closing: governance approval (D321, 8 Nov 2026; migration 0032)
Test steps:
1. A project › Governance log › ＋ Log a decision: it shows **Draft**.
2. Open it › Send for approval… › Send: it shows **Waiting for approval**; the sign-off people get a notification and see
   "Waiting for your approval" on the Governance log; each approves or rejects (a rejection needs a comment). Approved
   when the project's quorum approves; one rejection rejects it.
3. Another record › Approve with evidence…: give a reason or attach a file (or both) › Mark approved. The file is in
   Documents › Sign-off evidence.
4. Change an approved record: it is a Draft again; 🕘 History shows every step and the record as it was.
5. Repository (top menu) › Decision log: the Approval column and filter, across your projects (admins: all).
