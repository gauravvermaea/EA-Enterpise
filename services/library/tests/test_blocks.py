"""The library's page blocks, links and search words (no database needed)."""
import pytest

from libsvc import blocks as bk
from libsvc import library as L


def test_clean_keeps_known_blocks_and_checks_links():
    out = bk.clean([{"type": "heading", "text": " Cloud "}, {"type": "text", "text": "See [model](ea:model:abc-1) and [site](https://x.org)"},
                    {"type": "list", "items": ["a", "", "[b](ea:project:p1)"]}, {"type": "table", "rows": [["A", "B"], ["1"]]},
                    {"type": "links", "items": [{"label": "", "href": "https://y.org"}, {"label": "x", "href": ""}]}, {"type": "text", "text": ""}])
    assert [b["type"] for b in out] == ["heading", "text", "list", "table", "links"]
    assert out[3]["rows"][1] == ["1", ""] and out[4]["items"] == [{"label": "https://y.org", "href": "https://y.org"}]
    for bad in ([{"type": "script"}], [{"type": "text", "text": "[x](javascript:alert(1))"}], [{"type": "links", "items": [{"href": "ftp://a"}]}]):
        with pytest.raises(bk.Bad):
            bk.clean(bad)


def test_ea_links():
    for good in ("ea:model:1f2e", "ea:entity:m1:e2", "ea:view:m1:VP-19", "ea:document:p1:d1", "ea:page:abc", "https://a.b/c", "mailto:a@b.c"):
        assert bk.good_href(good), good
    for bad in ("ea:nothing:1", "ea:model:", "data:text/html,x", "//evil", "ea:model:a b"):
        assert not bk.good_href(bad), bad


def test_plain_words_and_links():
    b = [{"type": "text", "text": "Read [the guide](https://g.org) first"}, {"type": "table", "rows": [["[Hub](ea:model:1)", "spoke"]]},
         {"type": "links", "items": [{"label": "Board", "href": "https://b.org"}]}]
    assert bk.plain(b) == "Read the guide first\nHub spoke\nBoard"
    assert ("Hub", "ea:model:1") in bk.links(b) and ("Board", "https://b.org") in bk.links(b)


def test_search_words_match_the_start_of_words():
    assert L._tsquery("Cap map!") == "cap:* & map:*"
    assert L._tsquery("  ") == ""
