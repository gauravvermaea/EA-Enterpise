"""Update history sample data (phase 36, D417, D516; AGENTS.md: every state shown): laptop only, made once.

System admin > Updates shows an update that succeeded (0.16.0 to 0.17.0), one that failed and was rolled back (an RC),
one that did not start (the backup container was off) and one scheduled. They are marked sample: nobody is told about
them and the real record of updates (work/updates on the host) is not touched.
"""

from __future__ import annotations


def run() -> list[str]:
    from .. import updates as up
    from ..db import get_engine
    with get_engine().begin() as conn:
        return up.sample(conn)
