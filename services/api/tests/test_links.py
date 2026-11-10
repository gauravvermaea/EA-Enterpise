"""Link attributes (data type code url, D418): one or more {address, note}; people enter anything."""

from eax import content, links, rules
from eax.seed import archimate4 as A
from eax.seed import build
from eax.seed import demo_estate as D


def test_a_plain_old_address_is_one_link():
    assert links.parse("https://docs.example.com/a.pdf") == [{"address": "https://docs.example.com/a.pdf", "note": ""}]


def test_lines_with_notes_round_trip():
    v = "https://x.example.com/a.pdf | v2.1\nftp://f.example.com/b.zip\n#/metamodel/m/entity/e | the plateau"
    got = links.parse(v)
    assert [x["note"] for x in got] == ["v2.1", "", "the plateau"]
    assert links.store(got) == v
    assert links.text(v).startswith("https://x.example.com/a.pdf (v2.1); ftp://")


def test_anything_is_accepted_and_kept():
    """Owner, 10 Nov 2026: no validation of what people enter."""
    for v in ["javascript:alert(1)", "data:text/html,hi", "file:///c:/x", "see the shared drive", "\\\\server\\share\\doc"]:
        assert links.store(v) == v
        assert content._coerce({"data_type": "url", "name": "Documents"}, v) == v


def test_forms_and_api_give_rows_or_text():
    rows = [{"address": " https://a.example.com ", "note": " v1 "}, {"address": "", "note": "no address: left out"},
            {"address": "#/x"}]
    assert content._coerce({"data_type": "url", "name": "D"}, rows) == "https://a.example.com | v1\n#/x"
    assert content._coerce({"data_type": "url", "name": "D"}, "  \n | only a note") is None
    assert content._coerce({"data_type": "url", "name": "D"}, []) is None
    assert links.parse('[{"address": "https://a.example.com", "note": "v3"}]') == [{"address": "https://a.example.com", "note": "v3"}]


def test_plain_field_limits_trim_never_refuse():
    many = "\n".join(f"https://a.example.com/{i}" for i in range(30))
    assert len(links.parse(many)) == links.MAX_LINKS
    long = links.parse("https://a.example.com/" + "x" * 3000 + " | " + "n" * 500)[0]
    assert len(long["address"]) == links.MAX_ADDRESS and len(long["note"]) == links.MAX_NOTE


def test_only_safe_addresses_are_clickable():
    for a in ["https://a.example.com", "HTTP://a", "ftp://f.example.com/x", "ftps://f", "#/metamodel/m",
              "ea:entity:m:e", "ea:view:m:V1"]:
        assert links.clickable(a), a
    for a in ["javascript:alert(1)", "data:text/html,x", "file:///c:/x", "vbscript:x", "plain words", "//evil", "ea:nothing"]:
        assert not links.clickable(a), a
    assert links.clickable("//eax.example.org/x", host="eax.example.org")


def test_required_needs_one_link_with_an_address():
    a = {"code": "Documents", "name": "Documents", "data_type": "url", "is_required": True}
    assert rules._missing({**a, "value": None}) and rules._missing({**a, "value": " | a note only"})
    assert not rules._missing({**a, "value": "see the shared drive"})
    assert not rules._missing({**a, "value": "https://a.example.com | v1"})


def test_demo_estate_shows_each_state():
    """AGENTS.md: one link; several with notes; a repository document; an EA Explorer entity; the rest empty."""
    assert next(x for x in A.ATTRS if x[0] == "Url")[1:3] == ("Documents", "URL")
    for t in ("WorkPackage", "Requirement"):
        assert ("Url", "N", "Links") in A.MAP[t]
    assert not any(r[0] == "Url" for r in A.RULES), "no check on what people enter (owner, 10 Nov 2026)"
    docs = {name: attrs["Url"] for _t, name, _d, _p, attrs in D.E if "Url" in attrs}
    vals = list(docs.values())
    assert any(len(links.parse(v)) == 1 and not links.parse(v)[0]["note"] for v in vals)
    assert any(len(links.parse(v)) >= 3 and all(x["note"] for x in links.parse(v)) for v in vals)
    assert any(v.startswith("#/reference-library") for v in vals)
    assert any("{entity:" in v for v in vals)
    assert any(t == "WorkPackage" and "Url" not in attrs for t, _n, _d, _p, attrs in D.E)
    sql = build.demo_estate_sql()
    assert "{entity:" not in sql and "/entity/" in sql
