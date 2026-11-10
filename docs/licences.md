# Licences

EA Explorer's own code (web, api, backup, setup, scripts) is licensed under AGPL-3.0.

The products it runs are used unmodified, as separate programs:

| Product | Image | Licence |
| --- | --- | --- |
| nginx | nginx, nginxinc/nginx-unprivileged | BSD-2-Clause |
| PostgreSQL | postgres | PostgreSQL Licence |
| Valkey | valkey/valkey | BSD-3-Clause |
| Keycloak | quay.io/keycloak/keycloak | Apache-2.0 |
| Apache Superset | apache/superset (plus psycopg2, Authlib, redis drivers) | Apache-2.0 |
| Mayan EDMS | mayanedms/mayanedms | GPL-2.0 |
| draw.io | jgraph/drawio (our image `eaexplorer/drawio` adds EA Explorer's plugin for drawn views) | Apache-2.0 |
| Apache Hop (from phase 34.1, D128) | apache/hop, apache/hop-web | Apache-2.0 |

Main libraries in our code: Flask (BSD-3), flask-smorest (MIT), SQLAlchemy (MIT), Alembic (MIT),
psycopg (LGPL-3.0), Procrastinate (MIT), PyJWT (MIT), openpyxl (MIT, Excel packages), ReportLab (BSD-3-Clause, data quality PDFs), cryptography (Apache-2.0/BSD), gunicorn
(MIT), React (MIT), keycloak-js (Apache-2.0), elkjs (EPL-2.0, diagram layout, used unchanged), xterm.js (MIT, the terminal in Administration > Containers, D214), Vite (MIT). The operations
helper (phase 10) runs the Docker CLI (Apache-2.0). The administration console's Licences tab shows this list
(services/api/eax/licences.json: keep it in step with this page).
