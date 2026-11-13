"""Writes docs/estate.md, docs/estate/logical.drawio and docs/estate/physical.drawio from docker-compose.yml (R2.33).
Run it after changing docker-compose.yml: python tools/build_estate_diagrams.py (a test checks the files are current)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eaxcli import estate  # noqa: E402


def build() -> dict[str, str]:
    items = estate.from_compose(yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8")))
    return {"docs/estate.md": estate.markdown(items),
            "docs/estate/logical.drawio": estate.to_drawio("EA Explorer: logical", *estate.logical()),
            "docs/estate/physical.drawio": estate.to_drawio("EA Explorer: physical", *estate.physical(items))}


if __name__ == "__main__":
    for rel, text in build().items():
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {rel}")
