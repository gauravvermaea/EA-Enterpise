"""The test data (D580), shared by the outside test bench and the inside self-test: deliveries (Excel and CSV: good,
with errors, values win), a metamodel workbook, Word/PDF/PNG uploads and their replacements, a survey, a drawn view,
entities, relationships and attributes, a credentials template and the expected results. manifest.json lists them.

    python -m testbench.data build     make the files again (the same bytes every time)
    python -m testbench.data check     say whether the files on disk are as built
    python -m testbench.data list      what each file is and who uses it

In code: path("deliveries/good.xlsx"), expected("deliveries/good.xlsx"). Inside the test runner the folder is
/testdata (EAX_TEST_DATA)."""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def folder() -> Path:
    return Path(os.environ.get("EAX_TEST_DATA") or HERE)


def manifest() -> dict:
    return json.loads((folder() / "manifest.json").read_text(encoding="utf-8"))


def path(name: str) -> Path:
    p = folder() / name
    if name not in manifest()["files"] or not p.exists():
        raise FileNotFoundError(f"No test data file {name}: python -m testbench.data build")
    return p


def expected(name: str) -> dict:
    return json.loads((folder() / "expected" / "expected.json").read_text(encoding="utf-8")).get(name, {})
