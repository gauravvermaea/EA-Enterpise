# Phase 13.0.9: the Architecture Repository structure (planned, D301)

**Accepted and closed by the owner, 8 Nov 2026 (D337).**

**State:** built (8 Nov 2026, D324), waiting for the owner's test.

## What the owner asked for
EA Explorer to hold the organisation's **Architecture Repository** in the structure TOGAF gives it, with the
outside parties it deals with. The parts (in our words):

| Part | Holds | What EA Explorer has today |
| --- | --- | --- |
| Architecture Framework | the method and the content metamodel | the project library (phases, steps, document types); the models' metamodels; the content framework view on each project (13.0.7) |
| Architecture Landscape | strategic, segment and transition architectures | models (current, target, transition and scenario roles in projects); project states |
| Reference Library | foundation, common systems, industry and the organisation's own architectures; external reference models adopted | the model library (root and reference models); the organisation's reference library (13.0.8); each project's Reference area |
| Standards Information Base | business, data, application and technology standards; external standards adopted | not as such: standards documents could sit in the reference library; principles per project |
| Governance Log | decision log, compliance assessments, capability assessments, calendar, project portfolio, performance measurement | the change log, sign-off, governance documents in projects (decision log, dispensations, compliance), Architecture work |
| Architecture Capability | skills, organisation structure, architecture charter | users and roles; the EA capability documents of the Preliminary phase |
| Architecture Board (outside the repository) | steers the capability; visibility and escalation | sign-off people per project; the Architecture Board terms of reference as a document |

## To settle in its design session (one question at a time)
1. Is the repository one screen (a clickable map of the parts, as with the content framework in 13.0.7) leading
   to what each part holds across all projects and models, or a new store of its own?
2. The landscape: how a model or project is marked strategic, segment or transition (a model role, a tag, a field).
3. The Standards Information Base: its own register (standard, domain, status: adopted, emerging, retired, its
   reference implementation) or documents in the reference library with a standards domain.
4. The Governance Log across projects: which records (decisions, dispensations, compliance assessments,
   capability assessments) become rows of their own rather than documents, and the calendar.
5. Performance measurement: which measures, from where.
6. Architecture Capability: skills repository (people and skills) and the charter: rows or documents.
7. The Architecture Board: members, meetings, escalations from projects.
8. Who reads and who changes each part.
9. External reference models and external standards: how one is "adopted by the enterprise" and recorded.

## Owner's notes (8 Nov 2026)
- A top-level *Architecture repository* link and a project tab exist (phase 13.0.7). The top-level map's links are a
  first guess and **not correct yet**: where each item points is to be discussed in this phase's session. The project
  tab shows the structure empty.
- Architecture work has a *Repository* view for projects, empty until this phase.

## Answers so far (design session started 8 Nov 2026, to continue when this phase is built)
1. Organisation and project: **flat structures, both** (nothing rolls up). A project's repository (Project Scope) shows
   the items in its scope; the organisation's shows everything.
2. Filing: **mapped by type, with an override**: models, document types, principles, standards and governance records each
   have a default part (as with the content framework); anyone who contributes can move an item to another part.
3. Landscape: **the model's role plus a level field**: a project model gets a landscape level (Strategic, Segment,
   Capability), set when it joins a project and changeable; its role (current, target, transition) shows within it.
The other questions (standards register, governance log across projects, calendar, performance measures, capability,
the board, external models and standards, who reads and changes) wait for the build.
4. Where each link of the organisation's map goes (8 Nov 2026, D318): each opens an **existing screen**; see D318 for the
   full list. Read-only views across projects (decisions, compliance and capability assessments, people, skills) show the
   projects the person is on. Within a project every link stays in the project, except the reference library and model
   library ones, which offer the project's and the organisation's.
5. A model's landscape level is **taken from its project's depth** (the wizard's Scope step); Architecture work › Models
   has a level filter and a **By level** view.
6. The **Repository Area** is set on the entity type and the document class (not each entity), with built-in defaults.

## To discuss when the reference library is built (owner, 8 Nov 2026)
- Where Foundation, Common systems, Industry and the Organisation's own architectures sit in the reference library's
  structure, and how the model library's root and reference models relate to them (for now all four open the Reference
  library).
- The Standards Information Base: business, data, application and technology standards (for now the Reference library).
- An External standards folder, and how an external standard or reference model is adopted.

## Answers, 8 Nov 2026 (continued)
7. **Calendar**: simple and static. A project calendar kept by the project's members, and an organisation calendar kept
   by Super Admins. An event is a date, a time and a topic, once or recurring. All project members are taken as invited
   to a project event, everyone in the organisation to an organisation event. Views by month, week and day; each calendar
   can be downloaded and subscribed to over https from any calendar application (iCalendar).
8. **Architecture Board**: the owner said "anything": members, its meetings (on the organisation calendar), and agendas
   of records waiting for approval with each item's outcome. To confirm when this phase is built.
9. **Performance measurement**: the organisation's view gets a tab for each of project completion, governance health
   (records waiting for approval and for how long, dispensations expiring or overdue, non-compliant assessments),
   sign-off turnaround (how long documents and records wait, by project and by person) and repository coverage (how
   much of the content framework each project has filled), beside the models' data quality.
10. **Standards Information Base**: the Organisation base's Standards (by group, mandatory below it) are the SIB; the
    documents behind a standard are linked from the reference library; an external standard is a standard whose source
    says where it comes from. The map's standards items open the Organisation base's Standards on that group.
11. **Reference library structure**: Foundation architectures are the root metamodels (model library); Common systems
    and Industry architectures are reference models in the model library (with an industry: Industry; without: Common
    systems); the Organisation's own are reference models the organisation made; the reference library has fixed top
    folders with the same four names for documents and links. Each map item opens a page listing both.
12. **Architecture Board**: members only (Super Admins name them); the map's item opens the list.
13. **Calendar repeats and rights**: once, daily, weekly (chosen weekdays), monthly or yearly, until a date or a number of
    times; one occurrence can be skipped. Changed or deleted by whoever made it, a Project Admin or Lead Architect (a
    project's) or a Super Admin (the organisation's).
14. **Subscribing**: a private https link per person and calendar (a long random token), renewable to stop the old one;
    it shows only what that person may see.

## Built (8 Nov 2026, D324)
Calendars (`eax/calendars.py`, `Calendar.jsx`; tables proj.cal_events, proj.cal_feeds), the Architecture Board
(proj.board_members), performance measurement and the reference library's parts (`eax/org_repository.py`), the
organisation's and the project's maps (`ArchitectureRepository.jsx`). Migration 0032.

### Test steps
1. `.\eax clean-restart`, Ctrl+F5.
2. A project › **Calendar**: ＋ Event (a weekly meeting on Monday and Thursday, 10 times); it shows in Month, Week and Day.
   Open one occurrence › Skip it; open the event › change the time; Delete. As another member, try to change it: refused
   unless you are the Project Admin or Lead Architect.
3. ⬇ .ics opens in a calendar application; 🔗 Subscribe… gives your link: add it in Outlook or Google Calendar; Renew
   the link and the old one stops working.
4. Repository › Governance log › **Calendar**: the organisation's calendar; only a Super Admin can add to it.
5. Repository › **Architecture board**: as a Super Admin add two members with a role; take one off.
6. Repository › **Performance measurement**: each tab (data quality, completion, governance health, sign-off turnaround,
   repository coverage).
7. Repository › Reference library › each of the four parts: its library models and its folder; Standards information
   base › Business standards opens the Organisation base's standards on Business; External standards: the external ones.
8. Inside a project, Enterprise Repository › Calendar opens the project's calendar.
