"""The rest of the Windows Explorer style file explorer (R3.5): choosing several, cut, copy and paste, drag and drop,
keys, views and a preview pane, Properties, several in one zip, read-only mounts, and Mounts opened in the same
explorer."""

from __future__ import annotations

import base64
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
WEB = REPO / "services" / "web" / "src"


@pytest.fixture()
def hw(tmp_path):
    sys.path.insert(0, str(REPO / "services" / "ops"))
    spec = importlib.util.spec_from_file_location("hostwatch_r35", REPO / "services" / "ops" / "hostwatch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.hooks.update(values=lambda: {}, console_on=lambda: True, token="t")
    return mod


# ---------------------------------------------------------------- the logic of the screen, run with node
def _node(expr: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node here")
    script = f"import({json.dumps((WEB / 'fileOps.js').as_uri())}).then(m => console.log(JSON.stringify({expr})))"
    out = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


LIST = "[{path:'/a'},{path:'/b'},{path:'/c'},{path:'/d'}]"


def test_choosing_one_several_and_a_range():
    got = _node(f"""[
      m.choose({LIST}, ['/a'], '/a', '/c', {{}}),
      m.choose({LIST}, ['/a'], '/a', '/c', {{ctrl: true}}),
      m.choose({LIST}, ['/a', '/c'], '/c', '/c', {{ctrl: true}}),
      m.choose({LIST}, ['/b'], '/b', '/d', {{shift: true}}),
      m.choose({LIST}, ['/d'], '/d', '/b', {{shift: true}}),
      m.choose({LIST}, ['/a'], '/b', '/c', {{shift: true, ctrl: true}}),
    ]""")
    assert got[0] == {"chosen": ["/c"], "anchor": "/c"}
    assert got[1]["chosen"] == ["/a", "/c"]
    assert got[2]["chosen"] == ["/a"]                                    # Ctrl+click again takes it away
    assert got[3]["chosen"] == ["/b", "/c", "/d"] and got[3]["anchor"] == "/b"
    assert got[4]["chosen"] == ["/b", "/c", "/d"]                        # a range upwards too
    assert got[5]["chosen"] == ["/a", "/b", "/c"]                        # Shift+Ctrl adds the range


def test_paste_moves_or_copies_by_name_and_never_into_itself():
    got = _node("""[
      m.pasteOps({mode: 'cut', paths: ['/x/one.txt', '/x/dir']}, '/y'),
      m.pasteOps({mode: 'copy', paths: ['/y/one.txt']}, '/y'),
      m.pasteOps({mode: 'cut', paths: ['/x/dir']}, '/x/dir/inner'),
      m.pasteOps({mode: 'cut', paths: ['/x/dir']}, '/x/directory'),
    ]""")
    assert got[0]["ops"] == [{"op": "move", "path": "/x/one.txt", "to": "/y/one.txt"}, {"op": "move", "path": "/x/dir", "to": "/y/dir"}]
    assert got[1] == {"ops": [], "skipped": ["one.txt: already here"]}
    assert got[2] == {"ops": [], "skipped": ["dir: not into itself"]}
    assert got[3]["ops"] == [{"op": "move", "path": "/x/dir", "to": "/x/directory/dir"}]     # a name that only starts the same


def test_drop_uploads_files_and_moves_or_copies_items():
    got = _node("""[
      m.dropPlan({files: [1, 2], dragged: ['/a']}, '/t'),
      m.dropPlan({dragged: ['/a/f']}, '/t'),
      m.dropPlan({dragged: ['/a/f'], copy: true}, '/t'),
      m.dropPlan({}, '/t'),
    ]""")
    assert got[0] == {"upload": {"path": "/t", "count": 2}}
    assert got[1]["ops"] == [{"op": "move", "path": "/a/f", "to": "/t/f"}]
    assert got[2]["ops"] == [{"op": "copy", "path": "/a/f", "to": "/t/f"}]
    assert got[3] is None


def test_the_keys():
    got = _node("""[
      {key: 'Enter'}, {key: 'F2'}, {key: 'Delete'}, {key: 'c', ctrlKey: true}, {key: 'X', ctrlKey: true},
      {key: 'v', metaKey: true}, {key: 'a', ctrlKey: true}, {key: 'Backspace'}, {key: 'ArrowUp', altKey: true},
      {key: 'ArrowLeft', altKey: true}, {key: 'ArrowRight', altKey: true}, {key: 'F5'}, {key: 'Escape'}, {key: 'q'},
      {key: 'c', ctrlKey: true, altKey: true},
    ].map(m.keyAction)""")
    assert got == ["open", "rename", "delete", "copy", "cut", "paste", "all", "up", "up", "back", "forward", "refresh",
                   "none", None, None]


def test_delete_asks_for_the_path_or_for_delete():
    got = _node("[m.deleteAsk(['/a/b']), m.deleteAsk(['/a', '/b']), m.deleteAsk([])]")
    assert got[0]["expect"] == "/a/b" and "Type its full path" in got[0]["prompt"]
    assert got[1]["expect"] == "DELETE" and "these 2 items" in got[1]["prompt"]
    assert got[2] is None


def test_views_preview_and_icons():
    got = _node("""[m.VIEWS, m.previewable({name: 'a.txt', bytes: 10}), m.previewable({name: 'big', bytes: 9e9}),
                    m.previewable({dir: true}), m.iconOf({dir: true}), m.iconOf({name: 'x.log'}), m.iconOf({name: 'x.png'}),
                    m.crumbs('/usr/lib'), m.baseName('/a/b/'), m.parentOf('/a'), m.joinPath('/a/', 'b')]""")
    assert [v[1] for v in got[0]] == ["Details", "List", "Large icons"]
    assert got[1:4] == [True, False, False]
    assert got[4:7] == ["📁", "📝", "🖼"]
    assert got[7:] == [["/", "/usr", "/usr/lib"], "b", "/", "/a/b"]


# ---------------------------------------------------------------- the helper: properties, several in one zip, mounts
def test_properties_of_a_folder_and_a_file(hw, monkeypatch, tmp_path):
    (tmp_path / "f" / "sub").mkdir(parents=True)
    (tmp_path / "f" / "a.txt").write_text("hello")
    (tmp_path / "f" / "sub" / "b.txt").write_text("x" * 5000)
    monkeypatch.setattr(hw, "_cid", lambda s: "c1")
    monkeypatch.setattr(hw, "_exec", lambda cid, *cmd, **k: subprocess.run(list(cmd), capture_output=True, text=True).stdout)
    p = hw.files_properties("api", str(tmp_path / "f"))
    assert p["folder"] and p["kind"] == "folder" and p["files"] == 2 and p["folders"] == 1 and p["bytes"] >= 5000
    assert p["owner"] and p["permissions"].startswith("d") and p["modified"] > 0
    f = hw.files_properties("api", str(tmp_path / "f" / "a.txt"))
    assert not f["folder"] and f["bytes"] == 5 and f["files"] is None and f["name"] == "a.txt"
    with pytest.raises(FileNotFoundError):
        hw.files_properties("api", str(tmp_path / "nothing"))
    with pytest.raises(PermissionError):
        hw.files_properties("api", "/run/secrets/db")


def _tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_several_in_one_zip_without_secrets(hw, monkeypatch):
    monkeypatch.setattr(hw, "_cid", lambda s: "c1")
    given = {"/etc/app.conf": _tar({"app.conf": b"a=1"}),
             "/data/dir": _tar({"dir/one.txt": b"1", "dir/credentials.json": b"no", "dir/deeper/two.txt": b"2"})}
    monkeypatch.setattr(hw, "_cp_out", lambda cid, p: given[p])
    out = hw.files_download_many("api", ["/etc/app.conf", "/data/dir", "/run/secrets/x"])
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(out["content"])))
    assert sorted(z.namelist()) == ["app.conf", "dir/deeper/two.txt", "dir/one.txt"] and out["name"] == "files.zip"


def test_a_read_only_mount_is_read_only_in_the_explorer(hw, monkeypatch, tmp_path):
    (tmp_path / "data" / "sub").mkdir(parents=True)
    monkeypatch.setattr(hw, "_cid", lambda s: "c1")
    monkeypatch.setattr(hw, "_exec", lambda cid, *cmd, **k: subprocess.run(list(cmd), capture_output=True, text=True).stdout)
    hw.hooks["docker"] = lambda *a, **k: json.dumps([{"Mounts": [
        {"Destination": str(tmp_path / "data"), "Source": "/host/data", "RW": False}]}])
    out = hw.files_list("library", str(tmp_path / "data" / "sub"))
    assert out["inside_mount"]["source"] == "/host/data" and out["inside_mount"]["read_only"]
    assert "mounted read only" in out["read_only_reason"]
    hw.hooks["docker"] = lambda *a, **k: json.dumps([{"Mounts": [
        {"Destination": str(tmp_path / "data"), "Source": "/host/data", "RW": True}]}])
    assert hw.files_list("library", str(tmp_path / "data" / "sub"))["read_only_reason"] == ""
    assert hw.mount_of("/data2/x", {"/data": {"read_only": True}}) is None
    assert hw.mount_of("/data/x", {"/data": {"a": 1}, "/data/x": {"b": 2}})[0] == "/data/x"     # the deepest


def test_wired_through_the_helper_the_api_and_the_screens():
    ops = (REPO / "services/ops/ops.py").read_text()
    assert "/files(/content|/download|/properties)?$" in ops and "hostwatch.files_download_many" in ops
    api = (REPO / "services/api/eax/api/admin.py").read_text()
    assert '@blp.route("/admin/containers/<service>/files/properties")' in api and 'request.args.getlist("path")' in api
    fx = (WEB / "FileExplorer.jsx").read_text()
    for s in ('menuButton("edit", "Edit", editItems)', 'menuButton("view", "View", viewItems)', 'Preview pane`', "onContextMenu",
              "onDragStart", "onDrop", "keyAction(e)", "/properties", '"New file"', "fx-icons", "fx-compact",
              "start = \"/\""):
        assert s in fx, s
    hosts = (WEB / "Hosts.jsx").read_text()
    assert "Open in the explorer" in hosts and "<FileExplorer service={explorerFor(browse).service} start={explorerFor(browse).path} />" in hosts
    assert "export function explorerFor(m)" in hosts and '!String(u.service).startsWith("ops")' in hosts
