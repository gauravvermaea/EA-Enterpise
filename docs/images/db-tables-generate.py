"""Regenerates the table diagram (names and joins only) from the running database's catalog.

Run from the repository root while the stack is up, then render with the Mermaid CLI:
    python docs/images/db-tables-generate.py
    mmdc -i docs/images/db-tables.mmd -o services/web/public/db-tables.svg -b white
    mmdc -i docs/images/db-tables.mmd -o docs/images/db-tables.png -b white -s 2
The SVG is the picture on the SQL window; do this after any migration that adds or renames tables.
"""
import os
import shlex
import subprocess

PSQL = shlex.split(os.environ.get(
    "EAX_PSQL", "docker compose --env-file work/eaexplorer.env exec -T db psql -U postgres -d eaexplorer")
) + ["-At", "-F", "|", "-c"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db-tables.mmd")
fks = [l.split("|") for l in subprocess.run(PSQL + ["""
    SELECT c.conrelid::regclass, a.attname, c.confrelid::regclass
      FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
     WHERE c.contype = 'f' AND c.connamespace::regnamespace::text IN ('core','history','audit','staging')
     ORDER BY 3, 1, 2"""], capture_output=True, text=True, check=True).stdout.split()]
tables = subprocess.run(PSQL + ["""SELECT table_schema || '.' || table_name FROM information_schema.tables
    WHERE table_schema IN ('core','history','audit','staging') AND table_type = 'BASE TABLE' ORDER BY 1"""],
    capture_output=True, text=True, check=True).stdout.split()
# model_id and status_code are on (nearly) every table: drawn only for the main tables, noted in the title
MAIN_MODEL = {"core.layers", "core.relationship_types", "core.pick_lists", "core.attribute_types",
              }
ident = lambda t: t.replace(".", "_")
out = ["---", "title: \"EA Explorer tables (every core table also has model_id -> core.models.id and status_code -> core.item_statuses.code)\"",
       "config:", "  theme: neutral", "  themeVariables:", "    fontSize: 22px", "  er:", "    fontSize: 22", "---", "erDiagram"]
for t in tables:
    out.append(f'    {ident(t)}["{t}"]')
for child, col, parent in fks:
    if col == "status_code":
        continue
    if col == "model_id" and child not in MAIN_MODEL:
        continue
    out.append(f'    {ident(parent)} ||--o{{ {ident(child)} : "{col}"')
# not foreign keys, but the joins people write most
out.append('    core_entities ||..o{ history_row_versions : "row_id (table_name)"')
open(OUT, "w").write("\n".join(out) + "\n")
print(len(tables), "tables,", len(out), "lines")
