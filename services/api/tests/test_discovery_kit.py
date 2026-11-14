"""The Python kit of a Push source (D674): the samples a push maps by itself, the script's call to EA Explorer, the zip,
the user name and password sign-in of the push endpoint, and the Discovery tab. The whole path was also run against a
real database on 14 Nov 2026 (ArchiMate 4 model: the kit's 48 sample files read by the script with pandas and pushed: 96
records and 96 relationships of six relationship types delivered, every set mapped by its name; the same push again:
nothing new)."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import sys
import types as pytypes
import zipfile
from pathlib import Path

import pytest

from eax import discovery as dc
from eax import discovery_kit as kit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "eax" / "discovery_kit" / "push_to_eax.py"

TYPES = [
    {"code": "ApplicationComponent", "name": "Application Component",
     "attributes": [{"code": "owner", "name": "Owner"}, {"code": "lifecycle", "name": "Lifecycle"}]},
    {"code": "BusinessProcess", "name": "Business Process", "attributes": [{"code": "owner", "name": "Owner"}]},
    {"code": "BusinessActor", "name": "Business Actor", "attributes": []},
    {"code": "Node", "name": "Node", "attributes": []},
]
RTS = [{"code": "serving", "name": "Serving"}, {"code": "realization", "name": "Realization"}]
ALLOWED = [
    {"source": "ApplicationComponent", "target": "BusinessActor", "relationship": "serving", "relationship_name": "Serving"},
    {"source": "ApplicationComponent", "target": "BusinessProcess", "relationship": "serving", "relationship_name": "Serving"},
    {"source": "Node", "target": "ApplicationComponent", "relationship": "realization", "relationship_name": "Realization"},
]


def _frames(files: dict[str, str]) -> dict[str, list[dict]]:
    return {name[:-4]: list(csv.DictReader(io.StringIO(body))) for name, body in files.items()}


# ---------------------------------------------------------------- the samples
def test_a_sample_file_for_every_entity_type():
    files = kit.samples(TYPES, ALLOWED)
    assert sorted(files) == ["Application Component.csv", "Business Actor.csv", "Business Process.csv", "Node.csv"]
    rows = _frames(files)
    assert all(len(r) == kit.SAMPLE_ROWS for r in rows.values())
    assert [r["id"] for r in rows["Node"]] == ["Node-1", "Node-2"]                    # the type's code: unique across files
    assert list(rows["Application Component"][0]) == ["id", "name", "description", "Owner", "Lifecycle", "Serving"]
    assert all(r["Owner"] == "" for r in rows["Application Component"])            # attributes shown, left empty


def test_each_file_shows_a_relationship_the_metamodel_allows():
    rows = _frames(kit.samples(TYPES, ALLOWED))
    assert [r["Serving"] for r in rows["Application Component"]] == ["BusinessProcess-1", "BusinessProcess-2"]  # serving a process first
    assert [r["Realization"] for r in rows["Node"]] == ["ApplicationComponent-1", "ApplicationComponent-2"]
    assert list(rows["Business Actor"][0]) == ["id", "name", "description"]         # nothing allowed from it: no column
    found = kit.links(TYPES, ALLOWED)
    assert found == {"ApplicationComponent": {"relationship": "serving", "relationship_name": "Serving", "target": "BusinessProcess"},
                     "Node": {"relationship": "realization", "relationship_name": "Realization", "target": "ApplicationComponent"}}


def test_association_is_the_last_choice_and_targets_are_spread():
    allowed = [{"source": "ApplicationComponent", "target": "Node", "relationship": "association", "relationship_name": "Association"},
               {"source": "ApplicationComponent", "target": "Node", "relationship": "flow", "relationship_name": "Flow"},
               {"source": "BusinessActor", "target": "Node", "relationship": "flow", "relationship_name": "Flow"},
               {"source": "BusinessActor", "target": "BusinessProcess", "relationship": "flow", "relationship_name": "Flow"}]
    found = kit.links(TYPES, allowed)
    assert found["ApplicationComponent"]["relationship"] == "flow"
    assert found["BusinessActor"]["target"] == "BusinessProcess"                      # Node has one pointing at it already


def test_a_push_of_the_samples_maps_itself_and_delivers_every_relationship():
    feed = _frames(kit.samples(TYPES, ALLOWED))
    rts = RTS + [{"code": "flow", "name": "Flow"}]
    mapping = dc.suggest(dc.discover(feed), TYPES, rts)
    assert {s: mp["entity_type"] for s, mp in mapping.items()} == {
        "Application Component": "ApplicationComponent", "Business Actor": "BusinessActor",
        "Business Process": "BusinessProcess", "Node": "Node"}
    assert mapping["Application Component"]["links"] == {"Serving": "serving"}
    assert mapping["Node"]["links"] == {"Realization": "realization"}
    assert mapping["Application Component"]["attributes"] == {"Owner": "owner", "Lifecycle": "lifecycle"}
    out = dc.build(feed, mapping, {}, {}, {t["code"]: t for t in TYPES})
    assert out["counts"]["changed"] == 8 and out["counts"]["unmapped"] == 0 and out["counts"]["relationships"] == 4
    assert {"source": "Sample Node 1", "relationship_type": "realization", "target": "Sample Application Component 1"} in out["relationships"]


def test_the_readme_lists_the_relationships_published():
    text = kit.relationships_text(TYPES, ALLOWED)
    assert "| `Application Component.csv` | `Serving` | Application Component *serving* Business Process | `BusinessProcess-1` in `Business Process.csv` |" in text
    assert "| `Node.csv` | `Realization` |" in text
    ex = kit.example_text(TYPES, ALLOWED)
    assert "`Application Component.csv` has a `Serving` column" in ex and "`BusinessProcess-1`" in ex
    assert "allows none" in kit.example_text(TYPES, []) and "allows no relationship" in kit.relationships_text(TYPES, [])


def test_one_type_without_relationships_and_nothing_without_types():
    files = kit.samples(TYPES, [])
    assert len(files) == 4 and all("Serving" not in body.splitlines()[0] for body in files.values())
    assert kit.samples([], []) == {}


def test_a_type_a_push_would_not_map_back_is_not_used():
    clash = [{"code": "A", "name": "Server", "attributes": []}, {"code": "B", "name": "Servers", "attributes": []}]
    assert kit.maps_to_itself(clash[0], clash)                 # "Servers" is read as "Server": the first type
    assert not kit.maps_to_itself(clash[1], clash)
    assert list(kit.samples(clash, [])) == ["Server.csv"]
    assert "No sample file for Servers" in kit.relationships_text(clash, [])


def test_singular_keeps_words_that_already_are_one():
    assert [dc.singular(w) for w in ("Business Process", "Status", "Analysis", "Processes", "Nodes")] == \
        ["Business Process", "Status", "Analysis", "Process", "Node"]


def test_file_and_kit_names():
    assert kit.file_name("Data/Object") == "Data-Object" and kit.file_name("Plan: A?") == "Plan- A-"
    assert kit.file_name("..") == "records"
    assert kit.kit_name({"name": "ArchiMate 4"}, {"name": "CMDB push"}) == "eax-push-archimate-4-cmdb-push"


# ---------------------------------------------------------------- the zip and the code shown
SRC = {"guid": "1df76e91-2b74-41c7-a3f0-4d65cfe37768", "name": "CMDB push", "kind": "push"}
MODEL = {"name": "ArchiMate 4", "_id": 1}


@pytest.fixture
def fake_source(monkeypatch):
    monkeypatch.setattr(kit, "_source", lambda conn, user, source: (SRC, MODEL))
    monkeypatch.setattr(kit, "_metamodel", lambda conn, m: (TYPES, ALLOWED))


def test_the_kit_zip_holds_the_script_requirements_readme_and_samples(fake_source):
    name, data = kit.kit(None, None, SRC["guid"], "https://ea.example/")
    z = zipfile.ZipFile(io.BytesIO(data))
    root = "eax-push-archimate-4-cmdb-push"
    assert name == f"{root}.zip"
    assert sorted(z.namelist()) == sorted([f"{root}/push_to_eax.py", f"{root}/requirements.txt", f"{root}/README.md"]
                                          + [f"{root}/samples/{t}.csv" for t in
                                             ("Application Component", "Business Actor", "Business Process", "Node")])
    assert z.read(f"{root}/push_to_eax.py").decode() == SCRIPT.read_text(encoding="utf-8")
    readme = z.read(f"{root}/README.md").decode()
    assert "https://ea.example/api/v1/import-sources/1df76e91-2b74-41c7-a3f0-4d65cfe37768/push" in readme
    assert "ArchiMate 4" in readme and "CMDB push" in readme and "{" not in readme.replace("{set", "")
    assert "## How relationships are published" in readme and "| `Node.csv` | `Realization` |" in readme
    assert "`Application Component.csv` has a `Serving` column" in readme
    assert "python -m venv .venv" in readme and ".venv\\Scripts\\Activate.ps1" in readme and "source .venv/bin/activate" in readme
    assert "pip install -r requirements.txt" in readme
    for way in ("Active Directory", "single sign-on", "--token eaxt_", "--token eaxk_", "--cert client.pem", ":9443"):
        assert way in readme, way


def test_the_code_shown_on_the_tab(fake_source):
    c = kit.code(None, None, SRC["guid"], "https://ea.example")
    assert c["script"].startswith('"""Push CSV files to an EA Explorer model')
    assert c["command"] == ("python push_to_eax.py --url https://ea.example/api/v1/import-sources/"
                            "1df76e91-2b74-41c7-a3f0-4d65cfe37768/push --user <your user name>")
    assert set(c["samples"]) == {"Application Component.csv", "Business Actor.csv", "Business Process.csv", "Node.csv"}
    assert "*serving* Business Process" in c["relationships"]
    assert "pandas" in c["requirements"] and "requests" in c["requirements"]


def test_only_a_push_source_has_a_kit(monkeypatch):
    from eax import deliveries as dv
    from eax import repository as repo
    from eax.metamodel_edit import EditError
    monkeypatch.setattr(dv, "_source", lambda conn, s: {**SRC, "kind": "odata", "model_guid": "m"})
    monkeypatch.setattr(repo, "get_model", lambda conn, m: MODEL)
    monkeypatch.setattr(dc, "_may_write", lambda conn, user, m: None)
    with pytest.raises(EditError) as e:
        kit._source(None, None, SRC["guid"])
    assert e.value.status == 409


# ---------------------------------------------------------------- the script itself
def _load_script(monkeypatch, sent):
    """push_to_eax.py with stand-ins for pandas and requests: what it would send is recorded."""
    fake_pd = pytypes.ModuleType("pandas")
    fake_requests = pytypes.ModuleType("requests")

    class Answer:
        status_code = 202

        def json(self):
            return {"message": "5 new or changed found"}

    def post(url, json=None, verify=True, timeout=None, **signed):
        sent.append({"url": url, "json": json, "verify": verify, **signed})
        return Answer()
    fake_requests.post = post
    monkeypatch.setitem(sys.modules, "pandas", fake_pd)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    spec = importlib.util.spec_from_file_location("push_to_eax_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def fillna(self, value):
        return FakeFrame([{k: (value if v is None else v) for k, v in r.items()} for r in self.rows])

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows

    def __len__(self):
        return len(self.rows)


def test_push_dataframe_posts_one_set_with_basic_sign_in(monkeypatch):
    sent = []
    s = _load_script(monkeypatch, sent)
    answer = s.push_dataframe("https://ea/x/push", FakeFrame([{"id": "A1", "name": "CRM", "Owner": None}]), "gaurav", "pw",
                              set_name="Application Component")
    assert answer == {"message": "5 new or changed found"}
    assert sent == [{"url": "https://ea/x/push", "auth": ("gaurav", "pw"), "verify": True,
                     "json": {"Application Component": [{"id": "A1", "name": "CRM", "Owner": ""}]}}]


def test_push_dataframes_sends_related_sets_in_one_call(monkeypatch):
    sent = []
    s = _load_script(monkeypatch, sent)
    s.push_dataframes("https://ea/x/push", {"A": FakeFrame([{"id": "1"}]), "B": FakeFrame([{"id": "2"}])}, "u", "p", verify=False)
    assert len(sent) == 1 and set(sent[0]["json"]) == {"A", "B"} and sent[0]["verify"] is False


def test_every_way_of_signing_in(monkeypatch):
    sent = []
    s = _load_script(monkeypatch, sent)
    df = FakeFrame([{"id": "1"}])
    s.push_dataframe("https://ea/x/push", df, token="eaxt_abc")                       # single sign-on users, API keys
    s.push_dataframe("https://ea:9443/x/push", df, cert=("c.pem", "c.key"))           # a client certificate
    s.push_dataframe("https://ea/x/push", df, "ad.user", "pw")                         # an EA Explorer or AD account
    assert sent[0]["headers"] == {"Authorization": "Bearer eaxt_abc"} and "auth" not in sent[0]
    assert sent[1]["cert"] == ("c.pem", "c.key") and "auth" not in sent[1] and "headers" not in sent[1]
    assert sent[2]["auth"] == ("ad.user", "pw")
    assert s.sign_in(token="t", cert="c") == {"headers": {"Authorization": "Bearer t"}}       # a token first


def test_main_with_a_token_or_a_certificate_asks_for_no_password(monkeypatch):
    sent = []
    s = _load_script(monkeypatch, sent)
    monkeypatch.setattr(s, "read_folder", lambda folder: {"Node": FakeFrame([])})
    monkeypatch.setattr(s.getpass, "getpass", lambda prompt: pytest.fail("asked for a password"))
    monkeypatch.setattr(sys, "argv", ["p", "--url", "https://ea/x/push", "--token", "eaxk_1"])
    s.main()
    monkeypatch.setattr(sys, "argv", ["p", "--url", "https://ea:9443/x/push", "--cert", "c.pem", "--key", "c.key"])
    s.main()
    monkeypatch.setattr(sys, "argv", ["p", "--url", "https://ea:9443/x/push", "--cert", "both.pem"])
    s.main()
    assert sent[0]["headers"]["Authorization"] == "Bearer eaxk_1"
    assert sent[1]["cert"] == ("c.pem", "c.key") and sent[2]["cert"] == "both.pem"


def test_main_reads_the_folder_and_asks_for_the_password_when_left_out(monkeypatch, capsys):
    sent = []
    s = _load_script(monkeypatch, sent)
    monkeypatch.setattr(s, "read_folder", lambda folder: {"Node": FakeFrame([{"id": "N1", "name": "Server 1"}])})
    monkeypatch.setattr(s.getpass, "getpass", lambda prompt: "typed")
    monkeypatch.setattr(sys, "argv", ["push_to_eax.py", "--url", "https://ea/x/push", "--user", "gaurav", "--no-verify"])
    s.main()
    assert sent[0]["auth"] == ("gaurav", "typed") and sent[0]["verify"] is False
    out = capsys.readouterr().out
    assert "Node: 1 records" in out and "EA Explorer answered 202" in out and "5 new or changed found" in out


def test_read_folder_reads_every_value_as_text(tmp_path):
    try:
        import pandas  # noqa: F401 - the real pandas, when this machine has a working one
    except ImportError:
        pytest.skip("pandas is not installed here")
    (tmp_path / "Node.csv").write_text("id,name,Owner\n007,Server 1,\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("push_to_eax_real", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError:
        pytest.skip("requests or pandas not installed here")
    frames = mod.read_folder(tmp_path)
    assert frames["Node"].fillna("").to_dict(orient="records") == [{"id": "007", "name": "Server 1", "Owner": ""}]


def test_the_script_stays_simple_and_documented():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "def push_dataframe(url, df, username=None, password=None" in src and "def sign_in(" in src and "def push_dataframes(" in src
    assert src.count('"""') >= 8                                # the module and every function documented
    imports = {line.split()[1] for line in src.splitlines() if line.startswith(("import ", "from "))}
    assert imports == {"argparse", "getpass", "pathlib", "pandas", "requests"}
    req = (ROOT / "eax" / "discovery_kit" / "requirements.txt").read_text()
    assert [r.split(">=")[0] for r in req.splitlines() if r and not r.startswith("#")] == ["pandas", "requests"]


# ---------------------------------------------------------------- the push endpoint's sign-in
def test_the_push_endpoint_takes_a_user_name_and_password_or_a_token(monkeypatch):
    flask = pytest.importorskip("flask")
    from eax.api import discovery as api
    seen = []
    monkeypatch.setattr(api, "require_auth", lambda *a: (lambda view: lambda *x, **k: ("token", view(*x, **k))))
    from eax import odata_auth
    monkeypatch.setattr(odata_auth, "user", lambda: pytypes.SimpleNamespace(username="gaurav", roles=[], break_glass=False))
    monkeypatch.setattr(api, "_test_lock", lambda u: seen.append(("locked?", u.username)))

    @api.basic_or_token
    def view():
        return "pushed"
    app = flask.Flask("t")
    with app.test_request_context(headers={"Authorization": "Basic Z2F1cmF2OnB3"}):
        assert view() == "pushed" and seen == [("locked?", "gaurav")]
    with app.test_request_context(headers={"Authorization": "Bearer eyJ"}):
        assert view() == ("token", "pushed")


def test_wired_in_the_api_and_the_discovery_tab():
    api = (ROOT / "eax" / "api" / "discovery.py").read_text(encoding="utf-8")
    assert '@blp.route("/discovery-sources/<source_id>/kit")' in api and '@blp.route("/discovery-sources/<source_id>/kit/code")' in api
    assert "@basic_or_token\n    def post(self, source_id):" in api
    jsx = (ROOT.parent / "web" / "src" / "Discovery.jsx").read_text(encoding="utf-8")
    for s in ("function PythonKit", "/kit/code`", "/kit`, k.zip", "Download the Python kit (zip)", "Copy the code",
              'src.kind === "push" && <PythonKit'):
        assert s in jsx, s
    assert json.loads(json.dumps(kit.FILES)) == ["push_to_eax.py", "requirements.txt", "README.md"]
