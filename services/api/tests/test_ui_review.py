"""R2.12 (owner, 13 Nov 2026: the self-test takes the screenshots; "I am happy with the UI as it is discuss before you
make changes"): `eax test ui-review` makes screenshots and notes only, as each role at three widths."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_routes_widths_and_the_review_page():
    from eax.testing import ui_review as uv
    ids = {"model": "m-1", "project": "p-1"}
    rs = uv.routes(ids)
    assert "#/" in rs and "#/projects/p-1" in rs and "#/admin/footprint" in rs and not any(r.startswith("#/search") for r in rs)
    assert [w for w, _, _ in uv.WIDTHS] == ["laptop", "large", "narrow"] and uv.WIDTHS[2][1] == 390
    page = uv.to_html([
        {"role": "architect", "width": "laptop", "route": "#/", "file": "architect/laptop/home.jpg", "title": "Home", "notes": []},
        {"role": "architect", "width": "narrow", "route": "#/", "file": "architect/narrow/home.jpg", "title": "Home",
         "notes": ["wider than the window (520 px in 390 px)"]}])
    assert "2 screenshots, 1 with notes" in page and "wider than the window" in page and "no notes" in page
    assert "Nothing has been changed" in page and "ui-review/architect/narrow/home.jpg" in page
    for look in ("wider than the window", "no page title", "screen reader", "with no label", "no alt text", "long block"):
        assert look in uv.LOOK_JS


def test_only_the_review_runs_and_it_never_fails_a_run():
    run = (REPO / "services/api/eax/testing/run.py").read_text()
    assert 'a.add_argument("--ui-review"' in run and "ui_review.run(ids, ticket, r.dir" in run
    src = (REPO / "services/api/eax/testing/ui_review.py").read_text()
    assert '"passed", f"{n} screenshots' in src and '"failed"' not in src
    ops = (REPO / "services/ops/testruns.py").read_text()
    assert 'if args[:1] == ["ui-review"]:' in ops and 'cmd.append("--ui-review")' in ops
    assert "ui-review" in (REPO / "eaxcli/help.txt").read_text().split("### test", 1)[1][:200]
