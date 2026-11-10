"""`eax import` (phase 34, D466): take what other systems dropped in their delivery folders, or list the sources.

    python -m eax.deliveries_cli                       list every import source, its folder and what waits for review
    python -m eax.deliveries_cli <source> [--as user]  take the files in that source's folder (name or id); previews run
    python -m eax.deliveries_cli --all [--as user]     every active source

Run inside the api container (the eax scripts do this). Deliveries still wait for a person to accept them in the screens.
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from . import deliveries as dv
from . import permissions as perms
from .db import get_engine
from .metamodel_edit import EditError


def _sources(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(text("""SELECT s.guid::text AS id, s.name, s.folder, s.active, m.guid::text AS model, m.name AS model_name,
                                                         (SELECT count(*) FROM core.loads l WHERE l.source_id = s.id
                                                           AND l.status IN ('uploaded', 'mapping', 'previewed')) AS waiting
                                                    FROM core.import_sources s JOIN core.models m ON m.id = s.model_id
                                                   ORDER BY m.name, s.name""")).mappings().all()]


def main(argv: list[str]) -> int:
    who = "system:eax-import"
    if "--as" in argv:
        i = argv.index("--as")
        who = argv[i + 1] if i + 1 < len(argv) else who
        argv = argv[:i] + argv[i + 2:]
    user = perms.Principal(who, (perms.SUPER_ADMIN,))      # on the host: whoever runs eax may take deliveries
    with get_engine().connect() as conn:
        sources = _sources(conn)
    if not argv:
        if not sources:
            print("No import sources yet: add one on a model's Import and export tab > Deliveries.")
        for s in sources:
            print(f"{s['model_name']} / {s['name']}{'' if s['active'] else ' (off)'}: {s['waiting']} waiting; "
                  f"folder deliveries/{s['model']}/{s['folder']}/incoming")
        return 0
    want = sources if argv[0] == "--all" else [s for s in sources if argv[0].lower() in (s["id"], s["name"].lower(), s["folder"])]
    if not want:
        print(f"No import source {argv[0]!r}. Run eax import to list them.")
        return 1
    rc = 0
    for s in want:
        if not s["active"]:
            continue
        try:
            with get_engine().connect() as conn, conn.begin():
                out = dv.collect(conn, user, s["id"])
            print(f"{s['model_name']} / {s['name']}: {out['message']}")
            for f in out["failed"]:
                print(f"  could not take {f['file']}: {f['why']}")
            if out["loads"]:
                from . import loads as ld
                for load in out["loads"]:          # previewed here, so they are ready to review in the screens
                    with get_engine().connect() as conn, conn.begin():
                        print(f"  {load['file_name']}: {ld.preview(conn, load['id'], user).get('message', '')}")
        except EditError as exc:
            print(f"{s['name']}: {exc}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
