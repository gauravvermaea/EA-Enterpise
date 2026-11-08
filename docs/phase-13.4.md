# Phase 13.4 — Reference library with pages: an open-source wiki (requested, for later)

Status: **requested for later** (owner, 8 Nov 2026). Not designed or built yet; choose the wiki and discuss before building.

## The ask
The organisation's reference library (13.0.8) holds links and documents today. It should also hold **pages**
(wiki pages written in EA Explorer), so pages, links and documents sit together in one library: browsed, searched and
picked from a project in one place. Integrate an existing open-source wiki rather than writing one.

## Candidates (to check again when the phase starts; facts as found on 8 Nov 2026)
| Wiki | Licence | Database | API | Sign-in | Notes |
|---|---|---|---|---|---|
| Wiki.js (2.x) | AGPL-3.0 | PostgreSQL (fits our stack) | GraphQL | OIDC (Keycloak) | Mature 2.x; its 3.0 rewrite has been long in coming |
| Docmost | AGPL-3.0 | PostgreSQL + Redis | basic REST | OIDC, SAML, LDAP | Newer; real-time editing; some features in a paid edition |
| BookStack | MIT | MySQL/MariaDB only | REST | OIDC, SAML, LDAP | Would add a second database engine; one maintainer |
| Outline | Business Source License (not OSI open source) | PostgreSQL + Redis + S3 storage | full REST | OIDC required | Licence does not fit an open-source product |
| XWiki | LGPL-2.1 | PostgreSQL | REST | OIDC | Java, heavy for a laptop install |

Also to weigh: **pages of our own** (rich-text pages stored in the reference library, using the editor EA Explorer
already has): no new service, one search, one permission model; but no wiki features (page tree, page history, links
between pages) unless built.

## Questions to settle when it is built
- Which wiki (or our own pages); runs as one more container behind the same sign-in (Keycloak)?
- Where pages live: in the wiki, with the reference library holding an entry that points to each page (title, tags,
  folders, search text kept in step), or pages shown inside EA Explorer?
- Who writes pages (Super Admin only, as for the library today, or more people)?
- Project-level pages too, or only the organisation's library?
- Search across pages, links and documents in one box.
- Backup and restore of the wiki's content with the rest (application backup).
- Fits with 13.3 (turning References off turns the wiki off too).
