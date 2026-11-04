"""Phase 7: grids, search and saved views (no database needed)."""

import pathlib
import re

from eax import grids
from eax.metamodel_edit import OPS

API = (pathlib.Path(__file__).resolve().parent.parent / "eax" / "api" / "grids.py").read_text(encoding="utf-8")
WEB = pathlib.Path(__file__).resolve().parents[2] / "web" / "src" / "GridPages.jsx"


def test_every_metamodel_grid_is_routed():
    route = re.search(r"any\(([a-z_,]+)\):kind", API).group(1).split(",")
    assert set(route) == set(grids.KINDS)


def test_the_grids_only_send_known_metamodel_changes():
    ops = set(re.findall(r'op: "([a-z_.]+)"', WEB.read_text(encoding="utf-8")))
    assert ops, "no metamodel changes found in GridPages.jsx"
    assert ops <= set(OPS), ops - set(OPS)


def test_batch_is_one_version():
    from eax import metamodel_edit
    src = pathlib.Path(metamodel_edit.__file__).read_text(encoding="utf-8")
    body = src[src.index("def apply_many"):]
    assert body.count("publish_metamodel_version") == 1
