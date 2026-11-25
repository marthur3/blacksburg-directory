#!/usr/bin/env python3
"""Checks for guide/event page generation. Uses the committed businesses.json, no S3."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pages import (  # noqa: E402
    BANNED, FEATURED_SKIP, KINDS, build, collect_hood_pages, collect_kind_pages,
    event_submit_url, featured_listings, format_when, include_kind,
    neighborhood_for, norm_name,
)


def test_featured_skips_joes_diner():
    rows = [
        {"name": "Joe's Diner", "website": "https://www.joesdinerva.com/"},
        {"name": "Gillie's", "website": "https://example.com/gillies"},
        {"name": "Boudreaux's", "website": "https://boudreauxs.com"},
    ]
    out = featured_listings(rows, limit=4)
    names = {norm_name(b["name"]) for b in out}
    assert "joesdiner" in FEATURED_SKIP
    assert "joesdiner" not in names
    assert "gillies" in names


def test_featured_skips_chain_clutter():
    rows = [{"name": "Starbucks", "website": "https://starbucks.com"}] * 3
    rows.append({"name": "Idego Coffee", "website": "https://example.com/idego"})
    out = featured_listings(rows, limit=4)
    assert [b["name"] for b in out] == ["Idego Coffee"]


def test_neighborhoods_known_streets():
    assert neighborhood_for({
        "town": "Blacksburg", "address": "135 College Ave", "category": "movie theater", "name": "Lyric"
    }) == "Downtown"
    assert neighborhood_for({
        "town": "Blacksburg", "address": "800 Drillfield Dr", "category": "event venue", "name": "Burruss"
    }) == "Virginia Tech"
    assert neighborhood_for({
        "town": "Christiansburg", "address": "4 E Main St", "category": "museum", "name": "Montgomery"
    }) == "Downtown"
    assert neighborhood_for({
        "town": "Christiansburg", "address": "895 Peppers Ferry Rd NW", "category": "store", "name": "X"
    }) == "Peppers Ferry"


def test_format_when():
    s = format_when({"start": "2026-12-03T19:00:00-05:00", "end": "2026-12-03T21:30:00-05:00"})
    assert "December 3, 2026" in s
    assert "7:00 PM" in s
    assert "9:30 PM" in s


def test_event_submit_fallback():
    url = event_submit_url({"repo": "marthur3/blacksburg-directory"})
    assert "issues/new" in url
    assert "submit-event.md" in url
    assert event_submit_url({"event_submit_url": "mailto:x@y.z"}) == "mailto:x@y.z"


def test_always_kinds_even_when_small():
    coffee = next(k for k in KINDS if k["slug"] == "coffee-shops")
    bars = next(k for k in KINDS if k["slug"] == "bars")
    assert include_kind(coffee, 2)
    assert not include_kind(bars, 1)


def test_build_writes_required_routes():
    paths = set(build())
    needed = {
        "events/index.html",
        "events/submit/index.html",
        "events/example-saturday-market/index.html",
        "best/index.html",
        "best/coffee-shops-blacksburg/index.html",
        "christiansburg/restaurants/index.html",
        "blacksburg/index.html",
        "christiansburg/index.html",
        "newsletter/index.html",
        "sitemap.xml",
        "robots.txt",
        "404.html",
    }
    missing = needed - paths
    assert not missing, missing


def test_copy_rules_and_jsonld():
    html = (ROOT / "best" / "coffee-shops-blacksburg" / "index.html").read_text(encoding="utf-8")
    rest = (ROOT / "christiansburg" / "restaurants" / "index.html").read_text(encoding="utf-8")
    ev = (ROOT / "events" / "example-lyric-evening" / "index.html").read_text(encoding="utf-8")
    cal = (ROOT / "events" / "index.html").read_text(encoding="utf-8")
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")

    def authored(blob: str) -> str:
        bits = re.findall(r"<title>(.*?)</title>", blob)
        bits += re.findall(r'name="description" content="(.*?)"', blob)
        bits += re.findall(r'class="lede">(.*?)</p>', blob, re.S)
        bits += re.findall(r'class="cta">(.*?)</aside>', blob, re.S)
        bits += re.findall(r"<h1>(.*?)</h1>", blob, re.S)
        bits += re.findall(r"example-banner.*?>(.*?)</p>", blob, re.S)
        return "\n".join(bits)

    for blob in (html, rest, ev, cal):
        chrome = authored(blob)
        assert not BANNED.search(chrome), chrome
        assert "2080loyalty" not in blob.lower()
        assert "Get the newsletter" in blob or "calendar" in blob.lower()

    assert 'type="application/ld+json"' in html
    assert "ItemList" in html
    assert "LocalBusiness" in html
    assert "Coffee shops in Blacksburg" in html
    assert "a local guide" in html
    town_page = (ROOT / "blacksburg" / "coffee-shops" / "index.html").read_text(encoding="utf-8")
    best_title = re.search(r"<title>(.*?)</title>", html).group(1)
    town_title = re.search(r"<title>(.*?)</title>", town_page).group(1)
    assert best_title != town_title
    spot = html.split('class="spotlight"', 1)[1].split("</section>", 1)[0]
    assert "Joe" not in spot and "Diner" not in spot

    assert "Restaurants in Christiansburg" in rest
    assert 'type="application/ld+json"' in rest

    assert "Sample listing" in ev
    assert '"@type":"Event"' in ev.replace(" ", "") or '"@type": "Event"' in ev
    assert "Example: An evening at the Lyric" in ev

    assert "Submit an event" in cal
    assert "example-saturday-market" in cal

    assert "best/coffee-shops-blacksburg" in sm
    assert "christiansburg/restaurants" in sm
    assert "events/" in sm
    assert "Sitemap:" in robots


def test_example_events_are_marked():
    data = json.loads((ROOT / "events.json").read_text(encoding="utf-8"))
    assert data["events"], "seed events missing"
    for ev in data["events"]:
        assert ev.get("example") is True, ev
        assert str(ev.get("title", "")).startswith("Example:"), ev
        assert "not a real" in (ev.get("description") or "").lower()
        assert "joe" not in (ev.get("venue") or "").lower()


def test_kind_pages_use_real_counts():
    biz = json.loads((ROOT / "data" / "businesses.json").read_text(encoding="utf-8"))["businesses"]
    pages = collect_kind_pages(biz)
    coffee_bb = next((rows for t, k, rows in pages if t == "Blacksburg" and k["slug"] == "coffee-shops"), [])
    rest_cb = next((rows for t, k, rows in pages if t == "Christiansburg" and k["slug"] == "restaurants"), [])
    assert len(coffee_bb) >= 10
    assert len(rest_cb) >= 20
    hoods = collect_hood_pages(biz)
    names = {(t, h) for t, h, _ in hoods}
    assert ("Blacksburg", "Downtown") in names


def test_index_nav_points_at_new_routes():
    src = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'href="events/"' in src
    assert 'href="best/"' in src
    assert 'href="newsletter/"' in src


JOE_ID = "503dc8cb-13f9-4b0a-a2ed-65e8d9e7aefe"
JOE_NEEDLES = ("Joe's Diner", "Joe&#x27;s Diner", JOE_ID, "joesdinerva")


def test_joes_diner_absent_from_site():
    biz = json.loads((ROOT / "data" / "businesses.json").read_text(encoding="utf-8"))
    for bucket in ("businesses", "hidden"):
        for b in biz.get(bucket) or []:
            assert b.get("id") != JOE_ID, bucket
            assert norm_name(b.get("name") or "") != "joesdiner", b.get("name")
    for ev in json.loads((ROOT / "events.json").read_text(encoding="utf-8")).get("events") or []:
        assert ev.get("listing_id") != JOE_ID
        assert norm_name(ev.get("venue") or "") != "joesdiner"
    roots = [ROOT / "best", ROOT / "blacksburg", ROOT / "christiansburg", ROOT / "events", ROOT / "newsletter"]
    files = [ROOT / "sitemap.xml", ROOT / "index.html"]
    for folder in roots:
        files.extend(folder.rglob("*.html"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        for needle in JOE_NEEDLES:
            assert needle not in text, f"{path} still has {needle}"


if __name__ == "__main__":
    tests = [
        test_featured_skips_joes_diner, test_featured_skips_chain_clutter,
        test_neighborhoods_known_streets, test_format_when, test_event_submit_fallback,
        test_always_kinds_even_when_small, test_build_writes_required_routes,
        test_copy_rules_and_jsonld, test_example_events_are_marked,
        test_kind_pages_use_real_counts, test_index_nav_points_at_new_routes,
        test_joes_diner_absent_from_site,
    ]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    print("all passed")
