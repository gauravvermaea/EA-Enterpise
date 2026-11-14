"""The estate diagrams are clean (R3.4; owner, 13 Nov 2026: "estate diagrams are not clean"): every line at right angles
between box edges, around the boxes, with its own lane, an arrowhead and a label; text inside its box; each folder once in
the host's own form, single files apart, anonymous volumes named, ports once, finished one-shot containers aside."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from eaxcli import estate as E  # noqa: E402

ANON = "3f" * 32


def _inspect(name, image, nets, ports=None, mounts=(), state="running", restart="unless-stopped"):
    return {"Name": f"/eax-{name}-1", "Config": {"Image": image, "Labels": {"com.docker.compose.service": name}},
            "State": {"Status": state}, "HostConfig": {"RestartPolicy": {"Name": restart}},
            "NetworkSettings": {"Networks": {f"eaexplorer_{n}": {} for n in nets}, "Ports": ports or {}},
            "Mounts": [dict(m) for m in mounts]}


WINDOWS = [   # what the owner's laptop gave (13 Nov 2026): one folder in two forms, a file, an anonymous volume, IPv4 and 6
    _inspect("proxy", "nginx", ["frontend", "terminal"], {"443/tcp": [{"HostIp": "0.0.0.0", "HostPort": "443"},
                                                                     {"HostIp": "::", "HostPort": "443"}]},
             [{"Type": "bind", "Source": "/host_mnt/c/Users/gaura/Github/EA-Enterpise/deploy", "Destination": "/a"}]),
    _inspect("api", "eaexplorer/api", ["frontend", "backend"], mounts=[
        {"Type": "bind", "Source": "C:\\Users\\gaura\\Github\\EA-Enterpise\\deploy", "Destination": "/b"},
        {"Type": "bind", "Source": "/run/desktop/mnt/host/c/Users/gaura/Github/EA-Enterpise/README.md", "Destination": "/r"},
        {"Type": "volume", "Name": ANON, "Destination": "/tmp/x"},
        {"Type": "volume", "Name": "eax-pgdata", "Destination": "/v"},
        {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock"}]),
    _inspect("db", "postgres", ["backend"], mounts=[{"Type": "volume", "Name": "eax-pgdata", "Destination": "/var/lib/pg"}]),
    _inspect("setup", "eaexplorer/setup", [], state="exited", restart="no"),
]


def _compose():
    yaml = pytest.importorskip("yaml")
    return E.from_compose(yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8")))


def _diagrams():
    return {"logical": E.logical(), "physical (compose)": E.physical(_compose()),
            "physical (Windows)": E.physical(E.from_inspect(WINDOWS))}


def test_no_line_crosses_a_box_and_no_text_overflows():
    for name, (nodes, edges) in _diagrams().items():
        assert E.crossings(nodes, edges) == [], name
        assert E.overflows(nodes) == [], name


def test_every_line_is_at_right_angles_from_edge_to_edge_with_an_arrow_and_a_label():
    for name, (nodes, edges) in _diagrams().items():
        by = {n["id"]: n for n in nodes}
        for e in edges:
            pts = e["points"]
            assert len(pts) >= 2, (name, e)
            for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False):
                assert x1 == x2 or y1 == y2, (name, e["source"], e["target"])          # right angles only
            a, b = by[e["source"]], by[e["target"]]
            assert pts[0][1] in (a["y"], a["y"] + a["h"]) and a["x"] < pts[0][0] < a["x"] + a["w"], (name, e)
            assert pts[-1][1] in (b["y"], b["y"] + b["h"]) and b["x"] < pts[-1][0] < b["x"] + b["w"], (name, e)
            assert e.get("arrow") is not False and e["label"] and e["short"], (name, e)


def test_no_two_lines_share_a_lane():
    for name, (_nodes, edges) in _diagrams().items():
        seen = {}
        for e in edges:
            pts = e["points"]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False):
                if x1 == x2 and y1 != y2:
                    key = ("v", x1)
                    span = (min(y1, y2), max(y1, y2))
                elif y1 == y2 and x1 != x2:
                    key = ("h", y1)
                    span = (min(x1, x2), max(x1, x2))
                else:
                    continue
                for other, (lo, hi) in seen.get(key, []):
                    assert other == id(e) or hi <= span[0] or lo >= span[1], (name, e["source"], e["target"], key)
                seen.setdefault(key, []).append((id(e), span))


def test_one_line_per_pair_and_ports_on_a_box_spread():
    for name, (_nodes, edges) in _diagrams().items():
        pairs = [(e["source"], e["target"]) for e in edges]
        assert len(pairs) == len(set(pairs)), name
        ends = [tuple(e["points"][0]) for e in edges] + [tuple(e["points"][-1]) for e in edges]
        assert len(ends) == len(set(ends)), name


def test_windows_folders_once_in_the_hosts_form_files_apart_volumes_named_ports_once():
    items = E.from_inspect(WINDOWS)
    st = E.stores([it for it in items if not it["one_shot"]])
    labels = [s["label"] for s in st]
    assert labels.count("C:\\Users\\gaura\\Github\\EA-Enterpise\\deploy") == 1
    assert not any(x.startswith("/host_mnt") or x.startswith("/run/desktop") for x in labels)
    assert {s["kind"] for s in st if s["label"].endswith("README.md")} == {"file"}
    assert "anonymous volume (used by api)" in labels and ANON not in " ".join(labels)
    assert next(s for s in st if s["label"] == "eax-pgdata")["users"] == [("api", "/v"), ("db", "/var/lib/pg")]
    proxy = next(it for it in items if it["service"] == "proxy")
    assert proxy["ports"] == ["443:443"]
    nodes, _edges = E.physical(items)
    ids = {n["id"] for n in nodes}
    assert "c_setup" not in ids and "finished" in ids                       # a finished one-shot is listed apart
    assert next(n for n in nodes if n["id"] == "finished")["sub"] == "setup (exited)"
    assert {n["label"] for n in nodes if n.get("container")} >= {"Files on the host", "Folders on the host", "Docker volumes"}


def test_host_paths_and_files():
    assert E.host_path("/host_mnt/c/Users/me/x/") == "C:\\Users\\me\\x"
    assert E.host_path("/run/desktop/mnt/host/d/data") == "D:\\data"
    assert E.host_path("c:/Users/me") == "C:\\Users\\me"
    assert E.host_path("./work/") == "./work" and E.host_path("/srv/eax") == "/srv/eax"
    for f in ("./README.md", "./docker-compose.yml", "./eaxcli/help.txt", "./services/api/version.toml"):
        assert E.is_file(f), f
    for d in ("./deploy", "./work/tests", "./.git", "/var/run/docker.sock"):
        assert not E.is_file(d), d
    assert E.port("0.0.0.0:80:80") == "80:80" and E.port(":::443:443") == "443:443" and E.port("443:443") == "443:443"


def test_compose_one_shots_and_balanced_logical_columns():
    items = {it["service"]: it for it in _compose()}
    assert items["setup"]["one_shot"] and items["reports-init"]["one_shot"]
    assert not items["testrunner"]["one_shot"] and not items["api"]["one_shot"]
    nodes, _ = E.logical()
    groups = [n for n in nodes if n.get("container")]
    assert len({g["h"] for g in groups}) == 1                               # level columns
    per_column = {}
    for n in nodes:
        if not n.get("container"):
            per_column[n["x"]] = per_column.get(n["x"], 0) + 1
    assert max(per_column.values()) <= E.ROWS                              # no column stacked longer than the rest
    api = next(n for n in nodes if n["id"] == "api")
    assert "MCP" not in api["sub"]                                          # the MCP server is its own box only


def test_wrap_keeps_lines_inside_and_marks_what_is_cut():
    lines = E.wrap("one database: the repository and its schemas (tests, operations, archive, personal)", 188, 10, 2)
    assert len(lines) == 2 and lines[-1].endswith("…") and all(E.text_width(t, 10) <= 188 for t in lines)
    assert E.wrap("short", 188) == ["short"]
    assert E.wrap("C:\\Users\\gaura\\Github\\EA-Enterpise\\work\\data\\exports", 120, 11, 3)[0].endswith("\\")


def test_drawio_keeps_the_route_and_the_files_are_current():
    nodes, edges = E.logical()
    x = E.to_drawio("t", nodes, edges)
    assert x.count("<Array as=\"points\">") >= len(edges) - 5 and "exitPerimeter=0" in x and "endArrow=block" in x
    for f in ("docs/estate/logical.drawio", "docs/estate/physical.drawio", "docs/estate.md"):
        assert (REPO / f).exists(), f
    yaml = pytest.importorskip("yaml")
    items = E.from_compose(yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8")))
    assert (REPO / "docs/estate/physical.drawio").read_text(encoding="utf-8") == E.to_drawio("EA Explorer: physical", *E.physical(items))


def test_the_page_draws_routed_lines_with_arrowheads():
    js = (REPO / "services/web/src/exporting.js").read_text()
    assert '<marker id="arrow"' in js and "polyline points=" in js and "e.label_at" in js and "function waypoints(" in js
