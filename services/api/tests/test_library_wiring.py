"""The library service's wiring into EA Explorer (phase 15.2, D346 to D350): settings, the client, the start-up files."""

from pathlib import Path

import pytest

from eax import library_client as lc
from eax import settings as st
from eax.metamodel_edit import EditError

REPO = Path(__file__).resolve().parents[3]


def test_library_settings_are_checked():
    assert st.check("library_mode", "link") == "link"
    with pytest.raises(EditError):
        st.check("library_mode", "sharepoint")
    assert st.check("library_link", " https://intranet.example.org/library ") == "https://intranet.example.org/library"
    assert st.check("library_link", "") == ""
    with pytest.raises(EditError):
        st.check("library_link", "javascript:alert(1)")
    with pytest.raises(EditError):
        st.check("library_search_link", "https://intranet.example.org/search")          # no {q}
    assert "{q}" in st.check("library_search_link", "https://intranet.example.org/search?q={q}")


def test_library_mode(monkeypatch):
    base = {k: v[3] for k, v in st.REGISTRY.items()}
    monkeypatch.setattr(st, "parts", lambda conn=None: {"projects": True, "repository": True, "references": True})
    monkeypatch.setattr(st, "values", lambda conn=None: {**base, "library_mode": "link", "library_link": ""})
    assert st.library()["mode"] == "ours"                                              # link without an address: ours
    monkeypatch.setattr(st, "values", lambda conn=None: {**base, "library_mode": "link", "library_link": "https://x.example.org"})
    assert st.library()["link"] == "https://x.example.org"
    monkeypatch.setenv("EAX_SERVICE_LIBRARY", "off")
    assert st.library()["service"] is False
    monkeypatch.setattr(st, "parts", lambda conn=None: {"projects": False, "repository": False, "references": False})
    assert st.library()["mode"] == "off"


def test_client_moves_links_to_the_restored_project(monkeypatch):
    sent = {}
    monkeypatch.setattr(lc, "_call", lambda method, path, body=None: sent.update(path=path, body=body) or {"entries": 1})
    data = {"format": "eax-library-project/1", "entries": [{"blocks": [{"type": "text", "text": "[doc](ea:document:old-p:old-d)"}]}]}
    lc.import_project("new-p", "Restored", data, "ann", guid_map={"old-p": "new-p", "old-d": "new-d"})
    assert sent["path"] == "/internal/projects/new-p/import"
    assert sent["body"]["library"]["entries"][0]["blocks"][0]["text"] == "[doc](ea:document:new-p:new-d)"


def test_client_says_when_the_library_is_off(monkeypatch):
    monkeypatch.setenv("EAX_SERVICE_LIBRARY", "off")
    with pytest.raises(lc.LibraryDown):
        lc.export_project("p")


def test_start_up_files_know_the_library():
    import yaml
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    lib = compose["services"]["library"]
    assert lib["build"]["context"] == "./services/library" and "healthcheck" in lib
    proxy = (REPO / "deploy/proxy/templates/default.conf.template").read_text()
    assert proxy.count("location /api/library/") == 2 and "http://library:8100" in proxy
    for f in ("eax.ps1", "eax.sh", "eaxcli/stack.py", "services/ops/ops.py", "services/api/eax/services.py"):
        assert "EAX_SERVICE_LIBRARY" in (REPO / f).read_text(), f
    for kind in ("laptop", "server"):
        env = (REPO / f"deploy/templates/eaexplorer.{kind}.env").read_text()
        assert "EAX_LIBRARY_DB_PASSWORD=" in env and "EAX_LIBRARY_KEY=" in env
