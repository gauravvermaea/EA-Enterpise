"""The views service's wiring into EA Explorer (phase 28, D405 to D409): the client, the start-up files, the junction gap."""

from pathlib import Path

import pytest

from eax import views_client as vc

REPO = Path(__file__).resolve().parents[3]


def test_client_says_when_the_views_service_is_off(monkeypatch):
    monkeypatch.setenv("EAX_SERVICE_VIEWS", "off")
    with pytest.raises(vc.ViewsDown):
        vc.export_model("m")


def test_client_paths(monkeypatch):
    sent = {}
    monkeypatch.setattr(vc, "_call", lambda method, path, body=None, query=None: sent.update(m=method, path=path, body=body) or {})
    vc.copy_model("a", "b", "ann", {"x": "y"}, {})
    assert sent["path"] == "/internal/models/a/copy-to/b" and sent["body"]["ent_map"] == {"x": "y"}
    vc.delete_model("a", "ann")
    assert sent["m"] == "DELETE" and sent["path"] == "/internal/models/a"
    vc.hold_for_tag("a", "t")
    assert sent["path"] == "/internal/models/a/tags/t"


def test_start_up_files_know_the_views_service():
    import yaml
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    v = compose["services"]["views"]
    assert v["build"]["context"] == "./services/views" and "healthcheck" in v and "8110" in str(v["healthcheck"])
    proxy = (REPO / "deploy/proxy/templates/default.conf.template").read_text()
    assert proxy.count("location /api/views/") == 2 and "http://${EAX_VIEWS_UPSTREAM}" in proxy \
        and "EAX_VIEWS_UPSTREAM: ${EAX_VIEWS_UPSTREAM:-views:8110}" in (REPO / "docker-compose.yml").read_text()   # D521
    for f in ("eax.ps1", "eax.sh", "eaxcli/stack.py", "services/ops/ops.py", "services/api/eax/services.py"):
        assert "EAX_SERVICE_VIEWS" in (REPO / f).read_text(), f
    for kind in ("laptop", "server"):
        env = (REPO / f"deploy/templates/eaexplorer.{kind}.env").read_text()
        assert "EAX_VIEWS_DB_PASSWORD=" in env and "EAX_VIEWS_KEY=" in env and "EAX_SERVICE_VIEWS=on" in env
    for f in ("eax.ps1", "eax.sh", "eaxcli/info.py", "services/api/eax/setup/__main__.py"):
        assert "eax_views" in (REPO / f).read_text(), f
    assert "EAX_VIEWS_KEY is still the laptop value" in (REPO / "services/api/eax/setup/__main__.py").read_text()
    for f in ("health.py", "startup_status.py", "admin_check.py"):
        assert "check_views" in (REPO / "services/api/eax" / f).read_text(), f
    # the infra backup dumps every database on the server, eaxviews among them
    assert "FROM pg_database" in (REPO / "services/backup/backup.sh").read_text()


def test_junctions_are_not_elements():
    """D397 gap: the junction type is left out of type lists, counts, quality figures and catalogue reports."""
    api = REPO / "services/api/eax"
    for f, x in (("repository.py", "NOT t.is_connector) AS entity_type_count"), ("quality.py", "AND NOT is_connector"),
                 ("content.py", "AND NOT t.is_connector"), ("grids.py", "AND NOT is_connector"), ("reports.py", "t.is_connector")):
        assert x in (api / f).read_text(), f
    web = REPO / "services/web/src"
    assert "!t.is_connector" in (web / "elements.js").read_text()
    for f in ("DataEntry.jsx", "EntityGraph.jsx", "GridPages.jsx", "HierarchyMap.jsx", "RelationMatrix.jsx", "ModelViews.jsx", "Views.jsx"):
        assert "elementTypes(" in (web / f).read_text(), f
