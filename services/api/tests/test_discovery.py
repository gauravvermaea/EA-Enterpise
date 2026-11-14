"""Data discovery and ingestion (the Release 3 epic, D670): reading OData feeds, discovering sets, keys and links,
suggesting the mapping, only what changed, renames, confirmed matches, the delivery in the CSV format, pushes and the
AI engine. The whole cycle was run against a real database on 13 Nov 2026 (an OData source on a model: delivered,
previewed, accepted and committed; unchanged proposes nothing; a change proposes one; a near name suggested at 96%; a
push; an AI source with a fake engine); the self-test's API matrix calls every endpoint."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from eax import discovery as dc
from eax.metamodel_edit import EditError

REPO = Path(__file__).resolve().parents[3]
ROOT = "http://feed.test/odata/"


def feed_pages():
    return {
        ROOT: {"value": [{"name": "Applications", "url": "Applications", "kind": "EntitySet"},
                         {"name": "Servers", "url": "Servers", "kind": "EntitySet"},
                         {"name": "Lookup", "url": "F()", "kind": "FunctionImport"}]},
        ROOT + "Applications": {"value": [{"Id": "A1", "Name": "Claims Portal", "Description": "claims", "HostId": "S1",
                                           "Owner": "Ann", "@odata.etag": "W/1"},
                                          {"Id": "A2", "Name": "Policy Admin", "HostId": "S2", "Tags": ["x"]}],
                                "@odata.nextLink": "Applications?$skip=2"},
        ROOT + "Applications?$skip=2": {"value": [{"Id": "A3", "Name": "Billing", "HostId": "S1"}]},
        ROOT + "Servers": {"value": [{"Id": "S1", "Name": "srv-01"}, {"Id": "S2", "Name": "srv-02"}]},
    }


def getter(pages):
    asked = []

    def get(url, headers):
        asked.append((url, headers))
        return json.loads(json.dumps(pages[url]))
    get.asked = asked
    return get


TYPES = {"ApplicationComponent": {"code": "ApplicationComponent", "name": "Application Component",
                                  "attributes": [{"code": "Owner", "name": "Owner"}, {"code": "Cost", "name": "Annual cost"}]},
         "Device": {"code": "Device", "name": "Device", "attributes": []},
         "Node": {"code": "Node", "name": "Node", "attributes": []}}
RTS = [{"code": "Serving", "name": "Serving"}, {"code": "Assignment", "name": "Assignment"}]


# ---------------------------------------------------------------- reading
def test_a_service_document_is_followed_set_by_set_and_page_by_page():
    get = getter(feed_pages())
    feed = dc.read_feed(ROOT, {"Authorization": "x"}, get)
    assert sorted(feed) == ["Applications", "Servers"]                         # the function import is not a set
    assert [r["Id"] for r in feed["Applications"]] == ["A1", "A2", "A3"]
    assert all(h == {"Authorization": "x"} for _u, h in get.asked)


def test_one_entity_set_and_its_pages():
    pages = feed_pages()
    feed = dc.read_feed(ROOT + "Applications", {}, getter(pages))
    assert list(feed) == ["Applications"] and len(feed["Applications"]) == 3


def test_reading_refuses_what_is_not_a_feed():
    with pytest.raises(EditError, match="http"):
        dc.read_feed("ftp://x", {}, getter({}))
    with pytest.raises(EditError, match="value list"):
        dc._records("http://x/Set", {}, getter({"http://x/Set": {"oops": 1}}))


def test_a_page_limit_stops_endless_paging(monkeypatch):
    monkeypatch.setattr(dc, "MAX_PAGES", 3)
    pages = {"http://x/S": {"value": [{"Id": 1}], "@odata.nextLink": "http://x/S"}}
    assert len(dc._records("http://x/S", {}, getter(pages))) == 3


def test_pushed_payloads():
    assert dc.as_feed({"value": [{"a": 1}, 2], "set": "Apps"}) == {"Apps": [{"a": 1}]}
    assert dc.as_feed({"Apps": [{"a": 1}], "Servers": [], "note": "x"}) == {"Apps": [{"a": 1}], "Servers": []}
    assert dc.as_feed([{"a": 1}]) == {"records": [{"a": 1}]}
    for bad in ("text", {"note": "x"}):
        with pytest.raises(EditError):
            dc.as_feed(bad)


def test_the_sign_in_comes_from_a_setting_never_the_database(monkeypatch):
    assert dc.headers_for({"auth_ref": ""}) == {}
    monkeypatch.setenv("EAX_SOURCE_CMDB", "Bearer abc")
    assert dc.headers_for({"auth_ref": "EAX_SOURCE_CMDB"}) == {"Authorization": "Bearer abc"}
    monkeypatch.delenv("EAX_SOURCE_CMDB")
    with pytest.raises(EditError, match="not in the config file"):
        dc.headers_for({"auth_ref": "EAX_SOURCE_CMDB"})


def test_a_failing_feed_says_why(monkeypatch):
    import urllib.error
    import urllib.request

    def refuse(*a, **k):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", refuse)
    monkeypatch.setenv("EAX_DISCOVERY_ALLOWED_HOSTS", "127.0.0.1")       # IT allowed it: then it is tried
    with pytest.raises(EditError, match="could not be reached"):
        dc.http_get("http://127.0.0.1:1/x", {})


# ---------------------------------------------------------------- discovering and mapping
def test_discover_finds_keys_names_and_links():
    found = {d["set"]: d for d in dc.discover(dc.read_feed(ROOT, {}, getter(feed_pages())))}
    a = found["Applications"]
    assert a["count"] == 3 and a["key"] == "Id" and a["name"] == "Name" and a["description"] == "Description"
    assert "Tags" not in a["fields"] and "@odata.etag" not in a["fields"]            # lists and annotations are not fields
    assert a["links"] == {"HostId": "Servers"} and found["Servers"]["links"] == {}


def test_singular_and_type_score():
    assert [dc.singular(w) for w in ("Applications", "Capabilities", "Processes", "Boxes", "Data")] == \
        ["Application", "Capability", "Process", "Box", "Data"]
    assert dc.type_score("Application", TYPES["ApplicationComponent"]) >= 0.9
    assert dc.type_score("Server", {"code": "PhysicalServer", "name": "Physical Server"}) >= 0.9
    assert dc.type_score("Banana", TYPES["Device"]) < 0.8


def test_the_mapping_suggested_and_a_saved_one_kept():
    found = dc.discover(dc.read_feed(ROOT, {}, getter(feed_pages())))
    mp = dc.suggest(found, list(TYPES.values()), RTS)
    assert mp["Applications"]["entity_type"] == "ApplicationComponent" and mp["Applications"]["attributes"] == {"Owner": "Owner"}
    assert mp["Servers"]["entity_type"] == ""                                       # not obvious: a person chooses
    assert mp["Applications"]["links"] == {"HostId": ""}
    kept = dc.suggest(found, list(TYPES.values()), RTS, {"Servers": {"entity_type": "Device"}})
    assert kept["Servers"] == {"entity_type": "Device"}


MAPPING = {"Applications": {"entity_type": "ApplicationComponent", "key": "Id", "name": "Name", "description": "Description",
                            "attributes": {"Owner": "Owner"}, "links": {"HostId": "Serving"}},
           "Servers": {"entity_type": "Device", "key": "Id", "name": "Name", "description": "", "attributes": {}, "links": {}}}


def test_build_delivers_everything_the_first_time():
    feed = dc.read_feed(ROOT, {}, getter(feed_pages()))
    out = dc.build(feed, MAPPING, {}, {}, TYPES)
    assert out["counts"] == {"found": 5, "changed": 5, "unchanged": 0, "unmapped": 0, "no_key": 0, "relationships": 3}
    assert out["entities"]["ApplicationComponent"][0] == {"name": "Claims Portal", "description": "claims", "Owner": "Ann"}
    assert {"source": "Billing", "relationship_type": "Serving", "target": "srv-01"} in out["relationships"]
    assert set(out["seen"]) == {("Applications", "A1"), ("Applications", "A2"), ("Applications", "A3"), ("Servers", "S1"), ("Servers", "S2")}


def test_only_what_changed_and_renames_listed():
    pages = feed_pages()
    first = dc.build(dc.read_feed(ROOT, {}, getter(pages)), MAPPING, {}, {}, TYPES)
    seen = first["seen"]
    again = dc.build(dc.read_feed(ROOT, {}, getter(pages)), MAPPING, seen, {}, TYPES)
    assert again["counts"]["changed"] == 0 and again["counts"]["unchanged"] == 5 and not again["entities"]
    pages[ROOT + "Servers"]["value"][0]["Name"] = "srv-01b"
    third = dc.build(dc.read_feed(ROOT, {}, getter(pages)), MAPPING, seen, {}, TYPES)
    assert third["counts"]["changed"] == 1 and third["entities"]["Device"] == [{"name": "srv-01b"}]
    assert third["renamed"] == [{"entity_type": "Device", "key": "S1", "old": "srv-01", "new": "srv-01b"}]
    full = dc.build(dc.read_feed(ROOT, {}, getter(pages)), MAPPING, seen, {}, TYPES, full=True)
    assert full["counts"]["changed"] == 5


def test_a_confirmed_match_delivers_under_the_elements_name_and_unmapped_sets_are_counted():
    feed = dc.read_feed(ROOT, {}, getter(feed_pages()))
    out = dc.build(feed, {"Applications": MAPPING["Applications"]}, {}, {("ApplicationComponent", "billing"): "Billing System"}, TYPES)
    assert [r["name"] for r in out["entities"]["ApplicationComponent"]] == ["Claims Portal", "Policy Admin", "Billing System"]
    assert out["counts"]["unmapped"] == 2 and out["relationships"] == []          # the servers are not mapped: no ends
    no_key = dc.build({"Applications": [{"Id": "", "Name": ""}]}, MAPPING, {}, {}, TYPES)
    assert no_key["counts"]["no_key"] == 1


def test_the_delivery_is_the_published_csv_format():
    from eax import sheets as sh
    feed = dc.read_feed(ROOT, {}, getter(feed_pages()))
    out = dc.build(feed, MAPPING, {}, {}, TYPES)
    raw = dc.csv_set(out["entities"], out["relationships"], TYPES)
    names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
    assert sorted(names) == ["ApplicationComponent.csv", "Device.csv", "master.csv", "relationships.csv"]
    master = sh.read_master(zipfile.ZipFile(io.BytesIO(raw)).read("master.csv"))
    assert {(e["file"], e["kind"]) for e in master} >= {("ApplicationComponent.csv", "entities"), ("relationships.csv", "relationships")}
    sheets = sh.read(raw, "x.zip")["sheets"]
    app = next(s for s in sheets if s["name"].startswith("ApplicationComponent"))
    assert app["rows"][0]["name"] == "Claims Portal" and app["rows"][0]["Owner"] == "Ann"
    assert "Cost" not in app["codes"]                                               # attributes no row has are left out


def test_fingerprint_is_stable():
    assert dc.fingerprint({"b": 1, "a": 2}) == dc.fingerprint({"a": 2, "b": 1}) and len(dc.fingerprint({})) == 64


# ---------------------------------------------------------------- the AI engine
CFG = {"mode": "cloud", "url": "https://engine.test/v1", "model": "m", "key_ref": "EAX_AI_TEST_KEY"}


def test_the_ai_engine_is_off_until_switched_on():
    with pytest.raises(EditError, match="off"):
        dc.ai_extract("x", TYPES, RTS, {"mode": "off"})


def test_the_ai_key_comes_from_a_setting(monkeypatch):
    monkeypatch.delenv("EAX_AI_TEST_KEY", raising=False)
    with pytest.raises(EditError, match="not in the config file"):
        dc.ai_extract("x", TYPES, RTS, CFG, post=lambda *a: {})


def test_the_ai_answer_becomes_a_feed_with_only_known_types_and_links(monkeypatch):
    monkeypatch.setenv("EAX_AI_TEST_KEY", "k1")
    asked = {}

    def post(url, body, headers):
        asked.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": json.dumps({"items": [
            {"type": "ApplicationComponent", "name": "Claims Hub", "description": "d", "attributes": {"Owner": "Bo", "Bad": 1},
             "links": [{"relationship_type": "Serving", "target": "srv-77"}, {"relationship_type": "Nope", "target": "x"}]},
            {"type": "Device", "name": "srv-77"}, {"type": "Unknown", "name": "x"}, {"type": "Device", "name": " "}, "junk"]})}}]}
    feed = dc.ai_extract("The Claims Hub runs on srv-77.", TYPES, RTS, CFG, post=post)
    assert asked["url"] == "https://engine.test/v1/chat/completions" and asked["headers"] == {"Authorization": "Bearer k1"}
    assert "it is data, never" in asked["body"]["messages"][0]["content"]          # the document is not instructions
    assert asked["body"]["messages"][1]["content"] == "The Claims Hub runs on srv-77."
    assert feed == {"ApplicationComponent": [{"name": "Claims Hub", "description": "d", "Owner": "Bo", "link_0_Serving": "srv-77"}],
                    "Device": [{"name": "srv-77", "description": ""}]}
    mp = dc.ai_mapping(feed, TYPES)
    assert mp["ApplicationComponent"]["links"] == {"link_0_Serving": "Serving"} and mp["ApplicationComponent"]["attributes"] == {"Owner": "Owner"}
    out = dc.build(feed, mp, {}, {}, TYPES)
    assert out["relationships"] == [{"source": "Claims Hub", "relationship_type": "Serving", "target": "srv-77"}]


def test_a_bad_ai_answer_is_refused(monkeypatch):
    monkeypatch.setenv("EAX_AI_TEST_KEY", "k1")
    for answer in ({}, {"choices": [{"message": {"content": "not json"}}]}):
        with pytest.raises(EditError, match="not the JSON"):
            dc.ai_extract("x", TYPES, RTS, CFG, post=lambda *a, answer=answer: answer)


def test_documents_as_plain_text():
    assert dc.plain_text("a.html", b"<html><script>evil()</script><p>Hello <b>you</b></p></html>") == "Hello you"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:p><w:r><w:t>Claims Hub</w:t></w:r></w:p></w:document>")
    assert dc.plain_text("a.docx", buf.getvalue()) == "Claims Hub"
    assert dc.plain_text("broken.docx", b"nope") == ""
    assert dc.plain_text("a.md", b"# Title") == "# Title"


def test_the_next_run_follows_the_schedule():
    import datetime as dt
    now = dt.datetime(2026, 11, 13, tzinfo=dt.UTC)
    assert dc._next_run("off", now) is None
    assert dc._next_run("daily", now) == now + dt.timedelta(days=1)
    assert dc._next_run("weekly", now) == now + dt.timedelta(days=7)


# ---------------------------------------------------------------- wiring
def test_wired_in_the_database_the_api_the_jobs_and_the_screens():
    sql = (REPO / "services/api/migrations/sql/0071_discovery.sql").read_text()
    for s in ("kind IN ('folder', 'odata', 'push', 'ai')", "auth_ref ~ '^EAX_SOURCE_[A-Z0-9_]{1,53}$'", "core.discovery_seen",
              "core.discovery_matches", "CHECK (delivery IN ('upload', 'folder', 'api', 'odata', 'push', 'ai'))"):
        assert s in sql, s
    assert "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()           # D248
    api = (REPO / "services/api/eax/api/discovery.py").read_text()
    for r in ('"/models/<uuid:model_id>/discovery-sources"', '"/discovery-sources/<source_id>/look"', '"/discovery-sources/<source_id>/run"',
              '"/discovery-sources/<source_id>/matches"', '"/import-sources/<source_id>/push"', '"/admin/ai-engine"'):
        assert r in api, r
    assert "from .api.discovery import blp as discovery_blp" in (REPO / "services/api/eax/app.py").read_text()
    jobs = (REPO / "services/api/eax/jobs.py").read_text()
    assert '@app.periodic(cron="*/10 * * * *")\n@app.task(name="eax.discovery_scheduler"' in jobs and "dc.run_due(get_engine())" in jobs
    web = (REPO / "services/web/src/Discovery.jsx").read_text()
    for s in ("/discovery-sources", "/look", "/run", "/matches", "/admin/ai-engine"):
        assert s in web, s


# ---------------------------------------------------------------- the self-test's black-box check
def _fake_api(broken: str = ""):
    calls, state = [], {"seen": set()}

    def send(base, method, path, token, raw):
        body = json.loads(raw) if raw else None
        calls.append((method, path, token, body))
        if token == "viewer":
            return 403, '{"message": "no"}'
        if method == "post" and path.endswith("/discovery-sources"):
            return 201, json.dumps({"id": "s1", "push": "/api/v1/import-sources/s1/push"})
        if path.endswith("/push"):
            recs = body["apps"]
            new = [r for r in recs if (r["id"], r["name"]) not in state["seen"]]
            state["seen"] |= {(r["id"], r["name"]) for r in recs}
            sug = [{"candidate": "Self-test application 2", "confidence": 96}] if any("aplication" in r["name"] for r in recs) else []
            if broken == "suggest":
                sug = []
            return 202, json.dumps({"load": {"id": "l1"} if new else None, "counts": {"changed": len(new), "unchanged": len(recs) - len(new)},
                                    "suggestions": sug, "message": "ok"})
        if method == "get":
            return 200, json.dumps({"last_run": {"at": "now", "message": "ok"}})
        return 500, "?"
    return send, calls


def test_the_self_test_check_passes_on_a_working_api():
    from eax.testing import discovery_check
    send, calls = _fake_api()
    got = []
    counts = discovery_check.run("http://api", {"super-admin": "admin", "report-viewer": "viewer"}, {"model": "m1", "sid": "7"},
                                 lambda name, outcome, *a, **k: got.append((name, outcome)), send=send)
    assert counts == {"passed": 6, "failed": 0, "skipped": 0}, got
    assert calls[0][3]["mapping"] == discovery_check.MAPPING and calls[0][3]["kind"] == "push"
    assert [n for n, _o in got] == ["discovery: a push source is set up", "discovery: a push becomes a delivery",
                                    "discovery: only what changed", "discovery: a near name is suggested",
                                    "discovery: refused without the right", "discovery: the source says how it went"]


def test_the_self_test_check_fails_when_a_part_breaks():
    from eax.testing import discovery_check
    send, _calls = _fake_api(broken="suggest")
    got = []
    discovery_check.run("http://api", {"super-admin": "admin"}, {"model": "m1"},
                        lambda name, outcome, *a, **k: got.append((name, outcome, k)), send=send)
    out = dict((n, o) for n, o, _k in got)
    assert out["discovery: a near name is suggested"] == "failed" and out["discovery: refused without the right"] == "skipped"
    failed = next(k for n, o, k in got if o == "failed")
    assert failed["request"] and failed["response"]
    got.clear()
    assert discovery_check.run("http://api", {}, {}, lambda *a, **k: got.append(a[1]), send=send)["skipped"] == 1


def test_the_check_runs_in_the_full_api_suite():
    run_py = (REPO / "services/api/eax/testing/run.py").read_text()
    assert "discovery_check.run(API, tokens, ids, r.recorder(\"api\"))" in run_py


# ---------------------------------------------------------------- R3.12: what an attacker with write access could try
def _resolve(table):
    def resolve(host, port, proto=None):
        if host not in table:
            raise OSError("unknown")
        return [(2, 1, 6, "", (ip, port)) for ip in table[host]]
    return resolve


DNS = {"feed.example.com": ["93.184.216.34"], "inside.example.com": ["10.0.0.5"], "meta.example.com": ["169.254.169.254"],
       "loop.example.com": ["127.0.0.1"], "v6.example.com": ["::1"], "mixed.example.com": ["93.184.216.34", "192.168.1.2"]}


def test_a_source_may_not_send_another_setting_of_the_installation(monkeypatch):
    """Without the fix a source named EAX_DB_PASSWORD (or any secret) as its sign-in and pointed at its own server."""
    monkeypatch.setenv("EAX_DB_PASSWORD", "the-database-password")
    with pytest.raises(EditError, match="may not be sent") as exc:
        dc.headers_for({"auth_ref": "EAX_DB_PASSWORD"})
    assert exc.value.status == 403
    monkeypatch.setenv("EAX_SOURCE_CMDB", "Bearer t")
    assert dc.headers_for({"auth_ref": "EAX_SOURCE_CMDB"}) == {"Authorization": "Bearer t"}
    assert dc.SOURCE_REF.match("EAX_SOURCE_X") and not dc.SOURCE_REF.match("EAX_SOURCE_") and not dc.SOURCE_REF.match("EAX_AI_KEY")


def test_the_ai_engine_may_only_send_its_own_key(monkeypatch):
    monkeypatch.setenv("EAX_KEYCLOAK_ADMIN_PASSWORD", "secret")
    with pytest.raises(EditError, match="may not be sent"):
        dc.ai_extract("x", TYPES, RTS, {**CFG, "key_ref": "EAX_KEYCLOAK_ADMIN_PASSWORD"}, post=lambda *a: {})


def test_internal_and_private_addresses_are_refused(monkeypatch):
    """Without the fix a feed at http://db:5432, http://ops:9000, the machine or cloud metadata was read (SSRF)."""
    monkeypatch.delenv("EAX_DISCOVERY_ALLOWED_HOSTS", raising=False)
    r = _resolve(DNS)
    assert dc.check_url("https://feed.example.com/odata/", resolve=r) == ""
    for url in ("http://db:5432/", "http://ops:9000/backups", "http://api:8000/api/v1/admin/sql", "http://localhost/x",
                "http://127.0.0.1/", "http://[::1]/", "http://169.254.169.254/latest/meta-data/", "http://10.1.2.3/",
                "http://inside.example.com/", "http://meta.example.com/", "http://loop.example.com/", "http://v6.example.com/",
                "http://mixed.example.com/", "http://host.docker.internal/", "http://printer.local/", "ftp://feed.example.com/",
                "file:///etc/passwd", "http://nowhere.example.com/"):
        assert dc.check_url(url, resolve=r), url


def test_it_lists_the_hosts_it_may_read_inside(monkeypatch):
    r = _resolve(DNS)
    monkeypatch.setenv("EAX_DISCOVERY_ALLOWED_HOSTS", "cmdb, inside.example.com")
    assert dc.check_url("http://cmdb/odata", resolve=r) == "" and dc.check_url("http://inside.example.com/", resolve=r) == ""
    assert dc.check_url("http://db/", resolve=r)
    monkeypatch.setenv("EAX_DISCOVERY_ALLOWED_HOSTS", "*")
    assert dc.check_url("http://db/", resolve=r) == ""


def test_reading_refuses_before_any_request_and_on_a_redirect(monkeypatch):
    import urllib.request
    monkeypatch.delenv("EAX_DISCOVERY_ALLOWED_HOSTS", raising=False)
    opened = []
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", lambda *a, **k: opened.append(a) or (_ for _ in ()).throw(AssertionError))
    with pytest.raises(EditError, match="not read") as exc:
        dc.http_get("http://169.254.169.254/latest/meta-data/", {})
    assert exc.value.status == 403 and not opened
    handler = dc._Checked()
    with pytest.raises(EditError, match="redirected"):
        handler.redirect_request(urllib.request.Request("https://feed.example.com/"), None, 302, "Found", {},
                                 "http://127.0.0.1:8000/api/v1/admin/sql")


def test_a_push_is_limited(monkeypatch):
    monkeypatch.setattr(dc, "MAX_RECORDS", 3)
    with pytest.raises(EditError, match="At most 3"):
        dc.as_feed({"a": [{}, {}], "b": [{}, {}]})
    assert len(dc.as_feed({"x" * 500: [{}]})) == 1 and len(next(iter(dc.as_feed({"x" * 500: [{}]})))) == 200


def test_the_database_holds_the_same_rule():
    sql = (REPO / "services/api/migrations/sql/0071_discovery.sql").read_text()
    assert "auth_ref = '' OR auth_ref ~ '^EAX_SOURCE_[A-Z0-9_]{1,53}$'" in sql
