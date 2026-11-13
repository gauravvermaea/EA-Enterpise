"""R2.33 (owner, 12 Nov 2026: "Logical and physical diagram with softwares, components physical network etc of
estate"): eaxcli/estate.py draws both, from docker-compose.yml (docs/estate.md and its .drawio files, kept current by a
test) and from the running containers (System Admin › Estate)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def test_every_container_network_port_and_mount_is_drawn():
    from eaxcli import estate as E
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    items = E.from_compose(compose)
    assert {i["service"] for i in items} == set(compose["services"])
    proxy = next(i for i in items if i["service"] == "proxy")
    assert "443:443" in proxy["ports"] and "frontend" in proxy["networks"]
    db = next(i for i in items if i["service"] == "db")
    assert {"source": "eax-pgdata", "target": "/var/lib/postgresql/data", "kind": "volume"} in db["mounts"]
    nodes, edges = E.physical(items)
    ids = {n["id"] for n in nodes}
    assert {f"c_{s}" for s in compose["services"]} <= ids and {"net_frontend", "net_backend", "published"} <= ids
    assert "s_eax-pgdata" in ids and any(e["source"] == "c_db" and e["target"] == "s_eax-pgdata" for e in edges)
    assert next(n for n in nodes if n["id"] == "c_testrunner")["dashed"]               # on demand (profile test)
    ln, le = E.logical()
    assert {i for i, *_ in E.LOGICAL} <= {n["id"] for n in ln}
    assert all(a in {n["id"] for n in ln} and b in {n["id"] for n in ln} for a, b, _ in E.FLOWS)
    assert E.to_drawio("x", nodes, edges).startswith("<mxfile")


def test_the_running_installation():
    from eaxcli import estate as E
    items = E.from_inspect([{"Name": "/eax-db-1", "Config": {"Image": "postgres:17-alpine", "Labels": {"com.docker.compose.service": "db"}},
                             "State": {"Status": "running"}, "NetworkSettings": {"Networks": {"eaexplorer_backend": {}},
                             "Ports": {"5432/tcp": None}}, "Mounts": [{"Type": "volume", "Name": "eaexplorer_eax-pgdata",
                                                                       "Destination": "/var/lib/postgresql/data"}]}])
    assert items == [{"service": "db", "image": "postgres:17-alpine", "networks": ["backend"], "ports": [],
                      "mounts": [{"source": "eaexplorer_eax-pgdata", "target": "/var/lib/postgresql/data", "kind": "volume"}],
                      "profiles": [], "state": "running"}]


def test_the_repository_documents_are_current():
    spec = importlib.util.spec_from_file_location("build_estate", REPO / "tools/build_estate_diagrams.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    for rel, text in b.build().items():
        assert (REPO / rel).read_text(encoding="utf-8") == text, f"{rel} is stale: run python tools/build_estate_diagrams.py"


def test_the_page():
    assert 'self.path == "/estate"' in (REPO / "services/ops/ops.py").read_text()
    assert "COPY estate_ops.py /app/estate_ops.py" in (REPO / "services/ops/Dockerfile").read_text()
    assert '@blp.route("/admin/estate")' in (REPO / "services/api/eax/api/admin.py").read_text()
    assert '["estate", "Estate"' in (REPO / "services/web/src/Admin.jsx").read_text()
