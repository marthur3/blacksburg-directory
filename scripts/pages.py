#!/usr/bin/env python3
"""Build static event, town, and guide pages from businesses.json and events.json.

Usage:
  python scripts/pages.py
"""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import sys
from collections import Counter
from urllib.parse import quote

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from groups import GROUPS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
BIZ_PATH = ROOT / "data" / "businesses.json"
EVENTS_PATH = ROOT / "events.json"

FEATURED_SKIP = {"joesdiner"}
BANNED = re.compile(r"\bfree\b|2080loyalty|boomerangme|\brichie\b|passkit", re.I)
ALWAYS_KINDS = {"coffee-shops", "restaurants"}
MIN_KIND = 4
MIN_GROUP = 8
MIN_HOOD = 15
JSONLD_CAP = 50

KINDS = [
    {"slug": "coffee-shops", "label": "coffee shops", "categories": ["coffee shop", "cafe"]},
    {"slug": "restaurants", "label": "restaurants", "categories": ["restaurant", "casual eatery"]},
    {"slug": "bars", "label": "bars", "categories": ["bar"]},
    {"slug": "breweries", "label": "breweries", "categories": ["brewery"]},
    {"slug": "parks", "label": "parks", "categories": ["park"]},
    {"slug": "gyms", "label": "gyms and rec spots", "categories": ["gym", "sport or fitness facility"]},
    {"slug": "hotels", "label": "places to stay", "categories": ["hotel", "lodging", "motel"]},
    {"slug": "salons", "label": "salons and spas", "categories": ["personal or beauty service", "wellness service"]},
    {"slug": "dentists", "label": "dentists", "categories": ["dental clinic"]},
    {"slug": "pet-care", "label": "pet care", "categories": ["animal or pet service"]},
    {"slug": "churches", "label": "churches", "categories": ["christian place of worship"]},
    {"slug": "museums", "label": "museums", "categories": ["museum"]},
    {"slug": "theaters", "label": "theaters", "categories": ["movie theater", "theatre venue"]},
    {"slug": "farmers-markets", "label": "farmers markets", "categories": ["farmers market"]},
]

TOWNS = ["Blacksburg", "Christiansburg"]
GENERATED_DIRS = ("best", "blacksburg", "christiansburg", "events", "newsletter")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def street_num(address: str) -> int | None:
    m = re.match(r"(\d+)", address or "")
    return int(m.group(1)) if m else None


def neighborhood_for(b: dict) -> str:
    """Street and campus cues, not a legal map. Empty if we are not sure."""
    town = b.get("town") or ""
    addr = (b.get("address") or "").lower()
    cat = (b.get("category") or "").lower()
    blob = f"{addr} {cat} {(b.get('name') or '').lower()}"
    num = street_num(b.get("address") or "")

    if town == "Blacksburg":
        if any(k in blob for k in ("hethwood", "heather dr", "warm hearth")):
            return "Hethwood"
        if "prices fork" in addr:
            return "Prices Fork"
        if "university city" in addr:
            return "University City"
        if any(k in blob for k in (
            "drillfield", "alumni mall", "west campus", "squires",
            "campus building", "campus dining",
        )):
            return "Virginia Tech"
        if cat in ("college university", "campus building", "campus dining"):
            return "Virginia Tech"
        if any(k in addr for k in ("college ave", "draper rd", "draper road")):
            return "Downtown"
        if "roanoke st" in addr and (num is None or num < 500):
            return "Downtown"
        if any(k in addr for k in ("jackson st", "church st", "gilbert st", "clay st")):
            return "Downtown"
        if "s main" in addr or "south main" in addr:
            return "Downtown" if (num is None or num < 400) else "South Main"
        if "n main" in addr or "north main" in addr:
            return "Downtown" if (num is None or num < 450) else "North Main"
        if "washington st" in addr and (num is None or num < 300):
            return "Downtown"
        return ""

    if town == "Christiansburg":
        if "peppers" in addr:
            return "Peppers Ferry"
        if "cambria" in addr or "depot st" in addr:
            return "Cambria"
        if any(k in addr for k in ("e main", "w main", "east main", "west main")):
            return "Downtown"
        if "franklin" in addr and (num is None or num < 150):
            return "Downtown"
        return ""
    return ""


def site_url(cfg: dict) -> str:
    if cfg.get("site_url"):
        return str(cfg["site_url"]).rstrip("/")
    repo = cfg.get("repo") or ""
    if "/" in repo:
        user, name = repo.split("/", 1)
        return f"https://{user}.github.io/{name}"
    return ""


def abs_url(cfg: dict, path: str) -> str:
    base = site_url(cfg)
    path = path.lstrip("/")
    return f"{base}/{path}" if base else f"/{path}"


def site_name(cfg: dict) -> str:
    return cfg.get("site_name") or "Blacksburg Connect"


def pretty_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    d = re.sub(r"^1(?=\d{10}$)", "", d)
    if len(d) == 10:
        return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    return p


def featured_listings(rows: list[dict], limit: int = 4) -> list[dict]:
    """A short 'on the radar' set. Not a ranking. Never includes skipped names."""
    counts = Counter(norm_name(b.get("name") or "") for b in rows)
    out = []
    for b in rows:
        key = norm_name(b.get("name") or "")
        if not key or key in FEATURED_SKIP:
            continue
        if counts[key] >= 3:
            continue
        if not str(b.get("website") or "").startswith("http"):
            continue
        out.append(b)
        if len(out) >= limit:
            break
    return out


def kind_rows(businesses: list[dict], town: str, kind: dict) -> list[dict]:
    cats = set(kind["categories"])
    rows = [b for b in businesses if b.get("town") == town and (b.get("category") or "") in cats]
    rows.sort(key=lambda b: (b.get("name") or "").lower())
    return rows


def group_rows(businesses: list[dict], town: str, group: str) -> list[dict]:
    rows = [b for b in businesses if b.get("town") == town and b.get("group") == group]
    rows.sort(key=lambda b: (b.get("name") or "").lower())
    return rows


def include_kind(kind: dict, n: int) -> bool:
    return n >= MIN_KIND or kind["slug"] in ALWAYS_KINDS


def load() -> tuple[dict, dict, dict]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    biz = json.loads(BIZ_PATH.read_text(encoding="utf-8"))
    events = json.loads(EVENTS_PATH.read_text(encoding="utf-8")) if EVENTS_PATH.exists() else {"events": []}
    return cfg, biz, events


def rel(depth: int, path: str) -> str:
    return ("../" * depth) + path.lstrip("/")


def nav_html(cfg: dict, depth: int, current: str) -> str:
    name = esc(site_name(cfg))
    items = [
        ("directory", "Directory", rel(depth, "index.html")),
        ("events", "Events", rel(depth, "events/")),
        ("guides", "Guides", rel(depth, "best/")),
        ("newsletter", "Newsletter", rel(depth, "newsletter/")),
    ]
    links = []
    for key, label, href in items:
        cur = ' aria-current="page"' if key == current else ""
        links.append(f'<a href="{esc(href)}"{cur}>{label}</a>')
    return f'<nav class="site-nav"><a class="brand" href="{esc(rel(depth, "index.html"))}">{name}</a>{"".join(links)}</nav>'


def crumbs_html(items: list[tuple[str, str]]) -> str:
    parts = []
    for i, (label, href) in enumerate(items):
        if i == len(items) - 1 or not href:
            parts.append(esc(label))
        else:
            parts.append(f'<a href="{esc(href)}">{esc(label)}</a>')
    return '<p class="crumbs">' + " / ".join(parts) + "</p>"


def breadcrumb_ld(cfg: dict, items: list[tuple[str, str]]) -> dict:
    els = []
    for i, (label, path) in enumerate(items, start=1):
        node = {"@type": "ListItem", "position": i, "name": label}
        if path:
            node["item"] = abs_url(cfg, path)
        els.append(node)
    return {"@type": "BreadcrumbList", "itemListElement": els}


def newsletter_cta(cfg: dict, depth: int) -> str:
    href = cfg.get("newsletter_url") or rel(depth, "newsletter/")
    return f'''<aside class="cta">
  <h2>Blacksburg Connect</h2>
  <p>Local stories, events, and places worth knowing. In your inbox.</p>
  <a class="btn" href="{esc(href)}">Get the newsletter</a>
</aside>'''


def local_business_ld(b: dict, cfg: dict) -> dict:
    obj: dict = {
        "@type": "LocalBusiness",
        "name": b.get("name") or "",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": b.get("address") or "",
            "addressLocality": b.get("town") or "",
            "addressRegion": "VA",
            "addressCountry": "US",
        },
        "url": abs_url(cfg, f"index.html?id={quote(b.get('id') or '')}"),
    }
    if b.get("lat") is not None and b.get("lng") is not None:
        obj["geo"] = {"@type": "GeoCoordinates", "latitude": b["lat"], "longitude": b["lng"]}
    if b.get("phone"):
        obj["telephone"] = b["phone"]
    if str(b.get("website") or "").startswith("http"):
        obj["sameAs"] = b["website"]
    return obj


def itemlist_ld(cfg: dict, name: str, rows: list[dict], page_url: str) -> dict:
    els = []
    for i, b in enumerate(rows[:JSONLD_CAP], start=1):
        els.append({"@type": "ListItem", "position": i, "item": local_business_ld(b, cfg)})
    return {
        "@type": "ItemList",
        "name": name,
        "numberOfItems": len(rows),
        "url": page_url,
        "itemListElement": els,
    }


def event_ld(ev: dict, cfg: dict, page_path: str) -> dict:
    desc = ev.get("description") or ""
    if ev.get("example") and "sample listing" not in desc.lower():
        desc = "Sample listing. Not a real event. " + desc
    loc = {
        "@type": "Place",
        "name": ev.get("venue") or ev.get("town") or "Blacksburg, VA",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": ev.get("address") or "",
            "addressLocality": ev.get("town") or "",
            "addressRegion": "VA",
            "addressCountry": "US",
        },
    }
    obj = {
        "@type": "Event",
        "name": ev.get("title") or "",
        "description": desc,
        "startDate": ev.get("start") or "",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": loc,
        "url": abs_url(cfg, page_path),
        "organizer": {
            "@type": "Organization",
            "name": ev.get("organizer") or site_name(cfg),
            "url": site_url(cfg) or None,
        },
    }
    if ev.get("end"):
        obj["endDate"] = ev["end"]
    return obj


def jsonld_script(blocks: list[dict]) -> str:
    payload = [{"@context": "https://schema.org", **b} for b in blocks]
    if not payload:
        return ""
    blob = json.dumps(payload if len(payload) > 1 else payload[0], ensure_ascii=False, separators=(",", ":"))
    return f'<script type="application/ld+json">{blob}</script>'


def place_card(b: dict, depth: int, heading: str = "h3") -> str:
    where = ", ".join(x for x in (b.get("address"), b.get("town")) if x)
    cat = (b.get("category") or b.get("group") or "").capitalize() if b.get("category") else (b.get("group") or "")
    href = rel(depth, f"index.html?id={quote(b.get('id') or '')}")
    extra = []
    if b.get("phone"):
        extra.append(pretty_phone(b["phone"]))
    bits = " · ".join(x for x in (cat, where, *extra) if x)
    return f'''<a class="place-card" href="{esc(href)}">
  <{heading}>{esc(b.get("name"))}</{heading}>
  <p>{esc(bits)}</p>
</a>'''


def listing_section(title: str, rows: list[dict], depth: int, cls: str = "place-list") -> str:
    cards = "\n".join(place_card(b, depth) for b in rows)
    return f'<section class="{cls}"><h2>{esc(title)}</h2>\n{cards}</section>'


def related_html(title: str, links: list[tuple[str, str]]) -> str:
    if not links:
        return ""
    items = "".join(f'<li><a href="{esc(href)}">{esc(label)}</a></li>' for label, href in links)
    return f'<nav class="related"><h2>{esc(title)}</h2><ul>{items}</ul></nav>'


def shell(cfg: dict, *, title: str, description: str, canonical: str, depth: int,
          current: str, body: str, jsonld: list[dict] | None = None, extra_js: str = "") -> str:
    assert_copy(title, description)
    name = site_name(cfg)
    foot_src = ""
    if depth >= 0:
        foot_src = ('Listings from <a href="https://overturemaps.org" target="_blank" rel="noopener">'
                    "Overture Maps Foundation</a>, with local corrections. ")
    js = jsonld_script(jsonld or [])
    extra = f'<script src="{esc(extra_js)}" defer></script>' if extra_js else ""
    css = rel(depth, "site.css")
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap">
<link rel="stylesheet" href="{esc(css)}">
{js}
{extra}
</head>
<body>
<!-- Generated by scripts/pages.py. Do not edit. -->
{nav_html(cfg, depth, current)}
{body}
<footer class="site">{foot_src}{esc(name)} is the local newsletter for Blacksburg and Christiansburg.</footer>
</body>
</html>
'''


def assert_copy(*chunks: str) -> None:
    text = "\n".join(chunks)
    m = BANNED.search(text)
    if m:
        raise SystemExit(f"banned copy {m.group(0)!r} in generated page")


def event_submit_url(cfg: dict) -> str:
    if cfg.get("event_submit_url"):
        return str(cfg["event_submit_url"])
    repo = cfg.get("repo") or ""
    if repo:
        return f"https://github.com/{repo}/issues/new?template=submit-event.md"
    return ""


def parse_event_start(iso: str) -> dt.datetime | None:
    if not iso:
        return None
    try:
        return dt.datetime.fromisoformat(iso)
    except ValueError:
        return None


def _fmt_day(d: dt.datetime) -> str:
    return f"{d.strftime('%A, %B')} {d.day}, {d.year}"


def _fmt_time(d: dt.datetime) -> str:
    h, am = d.hour % 12 or 12, "AM" if d.hour < 12 else "PM"
    return f"{h}:{d.minute:02d} {am}"


def format_when(ev: dict) -> str:
    start = parse_event_start(ev.get("start") or "")
    end = parse_event_start(ev.get("end") or "")
    if not start:
        return ""
    date = _fmt_day(start)
    if "T" not in str(ev.get("start")):
        return date
    t1 = _fmt_time(start)
    if end and "T" in str(ev.get("end")):
        return f"{date}, {t1} – {_fmt_time(end)}"
    return f"{date}, {t1}"


def meta_kind(label: str, town: str, n: int) -> str:
    return (f"{n} {label} in {town}, VA. Addresses and map pins from the Blacksburg Connect "
            f"directory, plus a path to this month's local events.")


def lead_kind(label: str, town: str, n: int) -> str:
    return (f"{n} {label} in {town}, pulled from the Blacksburg Connect directory. "
            f"This is the list we have, not a contest. Open a name for the map pin, "
            f"or skip over to the events calendar.")


def lead_group(group: str, town: str, n: int) -> str:
    return (f"{n} {group.lower()} listings in {town}. Same groups as the map, written out "
            f"so a search can land here.")


def lead_hood(hood: str, town: str, n: int) -> str:
    return (f"{n} listings the directory files near {hood} in {town}. We go by street names, "
            f"so a place on the edge may sit on a neighbor page.")


def collect_kind_pages(businesses: list[dict]) -> list[tuple[str, dict, list[dict]]]:
    """(town, kind, rows) for every kind page we publish."""
    out = []
    for town in TOWNS:
        for kind in KINDS:
            rows = kind_rows(businesses, town, kind)
            if include_kind(kind, len(rows)) and rows:
                out.append((town, kind, rows))
    return out


def collect_group_pages(businesses: list[dict]) -> list[tuple[str, str, list[dict]]]:
    out = []
    for town in TOWNS:
        for group in GROUPS:
            rows = group_rows(businesses, town, group)
            if len(rows) >= MIN_GROUP:
                out.append((town, group, rows))
    return out


def collect_hood_pages(businesses: list[dict]) -> list[tuple[str, str, list[dict]]]:
    buckets: dict[tuple[str, str], list[dict]] = {}
    for b in businesses:
        hood = neighborhood_for(b)
        town = b.get("town") or ""
        if hood and town in TOWNS:
            buckets.setdefault((town, hood), []).append(b)
    out = []
    for (town, hood), rows in sorted(buckets.items()):
        if len(rows) >= MIN_HOOD:
            rows = sorted(rows, key=lambda r: (r.get("name") or "").lower())
            out.append((town, hood, rows))
    return out


def write_page(written: set[pathlib.Path], path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    written.add(path.resolve())


def town_kind_path(town: str, kind_slug: str) -> str:
    return f"{slug(town)}/{kind_slug}/"


def best_path(town: str, kind_slug: str) -> str:
    return f"best/{kind_slug}-{slug(town)}/"


def group_path(town: str, group: str) -> str:
    return f"{slug(town)}/{slug(group)}/"


def hood_path(town: str, hood: str) -> str:
    return f"{slug(town)}/{slug(hood)}/"


def kind_map_category(kind: dict) -> str:
    cats = kind.get("categories") or []
    return cats[0] if len(cats) == 1 else ""


def map_href(depth: int, group: str = "", category: str = "", town: str = "") -> str:
    q = []
    if group:
        q.append(f"g={slug(group)}")
    if category:
        q.append(f"c={slug(category)}")
    if town:
        q.append(f"t={quote(town)}")
    qs = "&".join(q)
    return rel(depth, "index.html" + (f"?{qs}" if qs else ""))


def build_events(cfg: dict, events_doc: dict, businesses: list[dict], written: set[pathlib.Path]) -> None:
    by_id = {b["id"]: b for b in businesses}
    raw = [e for e in events_doc.get("events") or [] if e.get("title") and e.get("start")]
    raw.sort(key=lambda e: str(e.get("start")))
    for ev in raw:
        if not ev.get("slug"):
            ev["slug"] = slug(ev.get("id") or ev["title"])
        if ev.get("listing_id") and ev["listing_id"] in by_id and not ev.get("address"):
            b = by_id[ev["listing_id"]]
            ev.setdefault("address", b.get("address") or "")
            ev.setdefault("town", b.get("town") or "")
            ev.setdefault("venue", b.get("name") or "")

    # Calendar
    depth = 1
    items = []
    for ev in raw:
        when = format_when(ev)
        badge = '<span class="badge">Sample</span>' if ev.get("example") else ""
        items.append(f'''<li>
          <a class="event-card" href="{esc(ev['slug'])}/">
            <h3>{esc(ev['title'])}{badge}</h3>
            <p>{esc(" · ".join(x for x in (when, ev.get("venue"), ev.get("town"), ev.get("category")) if x))}</p>
          </a>
        </li>''')
    submit = rel(depth, "events/submit/")
    body = f'''<main class="wrap wide">
  <header class="page-head">
    {crumbs_html([("Home", rel(depth, "index.html")), ("Events", "")])}
    <h1>What's on in Blacksburg</h1>
    <p class="lede">A simple calendar for town, campus, and Christiansburg. Sample rows are marked so they are not mistaken for real dates.</p>
  </header>
  <p><a class="btn primary" href="{esc(submit)}">Submit an event</a></p>
  {newsletter_cta(cfg, depth)}
  <div id="calendar" data-src="{esc(rel(depth, "events.json"))}">
    <ul class="event-list">{"".join(items) or '<li class="empty">No events yet. Submit one and it will show up here.</li>'}</ul>
  </div>
</main>'''
    canonical = abs_url(cfg, "events/")
    page = shell(cfg, title=f"Events in Blacksburg and Christiansburg | {site_name(cfg)}",
                 description="Local events in Blacksburg and Christiansburg. Month and list views, with a form to send us a date.",
                 canonical=canonical, depth=depth, current="events", body=body,
                 jsonld=[breadcrumb_ld(cfg, [("Home", "index.html"), ("Events", "events/")])],
                 extra_js=rel(depth, "events.js"))
    write_page(written, ROOT / "events" / "index.html", page)

    # Individual events
    for ev in raw:
        depth = 2
        path = f"events/{ev['slug']}/"
        when = format_when(ev)
        example = ""
        if ev.get("example"):
            example = ('<p class="example-banner"><strong>Sample listing.</strong> '
                       "This is not a real event. It is here so the calendar has a shape. "
                       "Replace the row in events.json.</p>")
        venue_link = ""
        lid = ev.get("listing_id") or ""
        if lid and lid in by_id:
            venue_link = f'<a href="{esc(rel(depth, "index.html?id=" + quote(lid)))}">{esc(ev.get("venue") or by_id[lid]["name"])}</a>'
        elif ev.get("venue"):
            venue_link = esc(ev["venue"])
        rows = [
            ("When", esc(when)),
            ("Where", venue_link or esc(ev.get("address") or "")),
            ("Town", esc(ev.get("town") or "")),
            ("Category", esc(ev.get("category") or "")),
        ]
        if ev.get("url"):
            rows.append(("Link", f'<a href="{esc(ev["url"])}" rel="noopener">{esc(ev["url"])}</a>'))
        dl = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows if v)
        desc = f'<p>{esc(ev.get("description") or "")}</p>' if ev.get("description") else ""
        body = f'''<main class="wrap">
  <header class="page-head">
    {crumbs_html([("Home", rel(depth, "index.html")), ("Events", rel(depth, "events/")), (ev["title"], "")])}
    <h1>{esc(ev["title"])}</h1>
    <p class="lede">{esc(when)}</p>
  </header>
  {example}
  <dl class="dl">{dl}</dl>
  {desc}
  {newsletter_cta(cfg, depth)}
  <p><a href="{esc(rel(depth, "events/"))}">Back to the calendar</a> · <a href="{esc(rel(depth, "events/submit/"))}">Submit an event</a></p>
</main>'''
        title = f"{ev['title']} | {site_name(cfg)}"
        description = (ev.get("description") or f"{ev['title']} in {ev.get('town') or 'Blacksburg'}.")[:160]
        page = shell(cfg, title=title, description=description, canonical=abs_url(cfg, path),
                     depth=depth, current="events", body=body,
                     jsonld=[
                         breadcrumb_ld(cfg, [("Home", "index.html"), ("Events", "events/"), (ev["title"], path)]),
                         event_ld(ev, cfg, path),
                     ])
        write_page(written, ROOT / "events" / ev["slug"] / "index.html", page)

    # Submit
    depth = 2
    dest = event_submit_url(cfg)
    dest_js = json.dumps(dest)
    body = f'''<main class="wrap">
  <header class="page-head">
    {crumbs_html([("Home", rel(depth, "index.html")), ("Events", rel(depth, "events/")), ("Submit", "")])}
    <h1>Submit an event</h1>
    <p class="lede">Send a date for Blacksburg or Christiansburg. A person adds it to the calendar. Sample rows stay marked as samples until you replace them.</p>
  </header>
  <form class="stack" id="event-form">
    <label>Event name <input name="title" required maxlength="120"></label>
    <label>Date <input name="date" type="date" required></label>
    <label>Start time <input name="start" type="time"></label>
    <label>End time <input name="end" type="time"></label>
    <label>Venue <input name="venue" maxlength="120"></label>
    <label>Town
      <select name="town">
        <option>Blacksburg</option>
        <option>Christiansburg</option>
      </select>
    </label>
    <label>Category
      <select name="category">
        <option>Community</option>
        <option>Arts</option>
        <option>Food</option>
        <option>Campus</option>
        <option>Sports</option>
        <option>Family</option>
      </select>
    </label>
    <label>Website <input name="url" type="url" placeholder="https://"></label>
    <label>Short description <textarea name="description" maxlength="600"></textarea></label>
    <p><button class="btn primary" type="submit">Send</button></p>
  </form>
    <p class="meta">This opens a GitHub issue or an email, depending on how config.json is set.</p>
</main>
<script>
(function () {{
  const dest = {dest_js};
  const form = document.getElementById("event-form");
  form.addEventListener("submit", function (e) {{
    e.preventDefault();
    if (!dest) {{ form.querySelector("button").textContent = "Set event_submit_url in config.json"; return; }}
    const fd = new FormData(form);
    const lines = [];
    fd.forEach((v, k) => {{ if (v) lines.push("**" + k + ":** " + v); }});
    const title = "Event: " + (fd.get("title") || "");
    const body = lines.join("\\n\\n");
    if (dest.indexOf("mailto:") === 0) {{
      const base = dest.split("?")[0];
      location.href = base + "?subject=" + encodeURIComponent(title) + "&body=" + encodeURIComponent(body);
      return;
    }}
    const join = dest.indexOf("?") >= 0 ? "&" : "?";
    location.href = dest + join + "title=" + encodeURIComponent(title) + "&body=" + encodeURIComponent(body);
  }});
}})();
</script>'''
    page = shell(cfg, title=f"Submit an event | {site_name(cfg)}",
                 description="Send a Blacksburg or Christiansburg event to the calendar.",
                 canonical=abs_url(cfg, "events/submit/"), depth=depth, current="events", body=body,
                 jsonld=[breadcrumb_ld(cfg, [("Home", "index.html"), ("Events", "events/"), ("Submit", "events/submit/")])])
    write_page(written, ROOT / "events" / "submit" / "index.html", page)


def related_for_kind(town: str, kind: dict, kind_index: set, group: str) -> list[tuple[str, str]]:
    links = []
    other = "Christiansburg" if town == "Blacksburg" else "Blacksburg"
    if (other, kind["slug"]) in kind_index:
        links.append((f"{kind['label'].capitalize()} in {other}", rel(2, town_kind_path(other, kind["slug"]))))
    links.append((f"Guide: {kind['label']} in {town}", rel(2, best_path(town, kind["slug"]))))
    if group:
        links.append((f"{group} in {town}", rel(2, group_path(town, group))))
    links.append((f"{town} hub", rel(2, f"{slug(town)}/")))
    links.append(("Events calendar", rel(2, "events/")))
    links.append(("Full directory map", map_href(2, group=group, category=kind_map_category(kind), town=town)))
    return links[:8]


def kind_group(kind: dict) -> str:
    # Best-effort group for map deep links.
    food = {"coffee-shops", "restaurants", "bars", "breweries", "farmers-markets"}
    if kind["slug"] in food:
        return "Food & Drink"
    mapping = {
        "parks": "Fitness & Recreation", "gyms": "Fitness & Recreation",
        "hotels": "Lodging", "salons": "Beauty & Personal Care",
        "dentists": "Health & Medical", "pet-care": "Pets",
        "churches": "Community & Civic", "museums": "Arts & Entertainment",
        "theaters": "Arts & Entertainment",
    }
    return mapping.get(kind["slug"], "")


def build_kind_and_best(cfg: dict, businesses: list[dict], written: set[pathlib.Path],
                        kind_pages) -> None:
    kind_index = {(t, k["slug"]) for t, k, _ in kind_pages}
    for town, kind, rows in kind_pages:
        group = kind_group(kind)
        n = len(rows)
        label = kind["label"]
        # Town kind page
        depth = 2
        path = town_kind_path(town, kind["slug"])
        spotlight = featured_listings(rows)
        spot_html = ""
        if spotlight:
            cards = "\n".join(place_card(b, depth) for b in spotlight)
            spot_html = f'<section class="spotlight"><h2>On the radar</h2>\n<div class="grid">{cards}</div></section>'
        rest = [b for b in rows if b not in spotlight]
        body = f'''<main class="wrap">
  <header class="page-head">
    {crumbs_html([("Home", rel(depth, "index.html")), (town, rel(depth, slug(town) + "/")), (label.capitalize(), "")])}
    <h1>{esc(label.capitalize())} in {esc(town)}</h1>
    <p class="lede">{esc(lead_kind(label, town, n))}</p>
    <p class="meta">{n} listings · <a href="{esc(map_href(depth, group=group, category=kind_map_category(kind), town=town))}">Open on the map</a></p>
  </header>
  {newsletter_cta(cfg, depth)}
  {spot_html}
  {listing_section("All listings", rest or rows, depth)}
  {related_html("Also nearby", related_for_kind(town, kind, kind_index, group))}
</main>'''
        title = f"{label.capitalize()} in {town}, VA | {site_name(cfg)}"
        page = shell(cfg, title=title, description=meta_kind(label, town, n),
                     canonical=abs_url(cfg, path), depth=depth, current="guides", body=body,
                     jsonld=[
                         breadcrumb_ld(cfg, [("Home", "index.html"), (town, f"{slug(town)}/"), (label.capitalize(), path)]),
                         itemlist_ld(cfg, f"{label.capitalize()} in {town}", rows, abs_url(cfg, path)),
                     ])
        write_page(written, ROOT / slug(town) / kind["slug"] / "index.html", page)

        # /best/kind-town
        depth = 2
        bpath = best_path(town, kind["slug"])
        other = "Christiansburg" if town == "Blacksburg" else "Blacksburg"
        related = [
            (f"All {label} in {town}", rel(2, path)),
            (f"{label.capitalize()} in {other}", rel(2, best_path(other, kind["slug"]))) if (other, kind["slug"]) in kind_index else None,
            (f"{town} directory hub", rel(2, f"{slug(town)}/")),
            ("Events this month", rel(2, "events/")),
            ("Full map", map_href(2, group=group, category=kind_map_category(kind), town=town)),
        ]
        related = [x for x in related if x]
        spot_html = ""
        if spotlight:
            cards = "\n".join(place_card(b, depth) for b in spotlight)
            spot_html = f'<section class="spotlight"><h2>On the radar</h2>\n<div class="grid">{cards}</div></section>'
        intro = (f"A {town} guide from Blacksburg Connect. {n} {label} from the directory map, "
                 f"with a short list up top so you can scan. The full set is below, A to Z.")
        body = f'''<main class="wrap">
  <header class="page-head">
    {crumbs_html([("Guides", rel(depth, "best/")), (f"{label.capitalize()} in {town}", "")])}
    <h1>{esc(label.capitalize())} in {esc(town)}</h1>
    <p class="lede">{esc(intro)}</p>
    <p class="meta">{n} listings · <a href="{esc(rel(depth, path))}">Complete list</a> · <a href="{esc(map_href(depth, group=group, category=kind_map_category(kind), town=town))}">Map</a></p>
  </header>
  {newsletter_cta(cfg, depth)}
  {spot_html}
  {listing_section("The rest of the list", rest or rows, depth)}
  {related_html("Keep looking", related)}
</main>'''
        title = f"{label.capitalize()} in {town}, a local guide | {site_name(cfg)}"
        desc = (f"A Blacksburg Connect guide to {label} in {town}, VA. {n} listings from the "
                f"local directory, with events and the newsletter close at hand.")
        page = shell(cfg, title=title, description=desc, canonical=abs_url(cfg, bpath),
                     depth=depth, current="guides", body=body,
                     jsonld=[
                         breadcrumb_ld(cfg, [("Home", "index.html"), ("Guides", "best/"), (f"{label.capitalize()} in {town}", bpath)]),
                         itemlist_ld(cfg, f"{label.capitalize()} in {town}", rows, abs_url(cfg, bpath)),
                     ])
        write_page(written, ROOT / "best" / f"{kind['slug']}-{slug(town)}" / "index.html", page)


def build_groups_and_hoods(cfg: dict, written: set[pathlib.Path], group_pages, hood_pages) -> None:
    for town, group, rows in group_pages:
        depth = 2
        path = group_path(town, group)
        n = len(rows)
        body = f'''<main class="wrap">
  <header class="page-head">
    {crumbs_html([(town, rel(depth, slug(town) + "/")), (group, "")])}
    <h1>{esc(group)} in {esc(town)}</h1>
    <p class="lede">{esc(lead_group(group, town, n))}</p>
    <p class="meta">{n} listings · <a href="{esc(map_href(depth, group=group, town=town))}">Open on the map</a></p>
  </header>
  {newsletter_cta(cfg, depth)}
  {listing_section("All listings", rows, depth)}
  {related_html("Also", [
      (f"{town} hub", rel(2, slug(town) + "/")),
      ("Guides", rel(2, "best/")),
      ("Events", rel(2, "events/")),
  ])}
</main>'''
        title = f"{group} in {town}, VA | {site_name(cfg)}"
        desc = f"{n} {group.lower()} listings in {town}, VA, from the Blacksburg Connect directory."
        page = shell(cfg, title=title, description=desc, canonical=abs_url(cfg, path),
                     depth=depth, current="guides", body=body,
                     jsonld=[
                         breadcrumb_ld(cfg, [("Home", "index.html"), (town, f"{slug(town)}/"), (group, path)]),
                         itemlist_ld(cfg, f"{group} in {town}", rows, abs_url(cfg, path)),
                     ])
        write_page(written, ROOT / slug(town) / slug(group) / "index.html", page)

    for town, hood, rows in hood_pages:
        depth = 2
        path = hood_path(town, hood)
        n = len(rows)
        body = f'''<main class="wrap">
  <header class="page-head">
    {crumbs_html([(town, rel(depth, slug(town) + "/")), (hood, "")])}
    <h1>{esc(hood)}, {esc(town)}</h1>
    <p class="lede">{esc(lead_hood(hood, town, n))}</p>
    <p class="meta">{n} listings</p>
  </header>
  {newsletter_cta(cfg, depth)}
  {listing_section("Places in this pocket of town", rows, depth)}
  {related_html("Also", [
      (f"{town} hub", rel(2, slug(town) + "/")),
      ("Guides", rel(2, "best/")),
      ("Events", rel(2, "events/")),
  ])}
</main>'''
        title = f"{hood} in {town}, VA | {site_name(cfg)}"
        desc = f"Places in {hood}, {town}, VA, from the Blacksburg Connect directory. {n} listings."
        page = shell(cfg, title=title, description=desc, canonical=abs_url(cfg, path),
                     depth=depth, current="guides", body=body,
                     jsonld=[
                         breadcrumb_ld(cfg, [("Home", "index.html"), (town, f"{slug(town)}/"), (hood, path)]),
                         itemlist_ld(cfg, f"{hood}, {town}", rows, abs_url(cfg, path)),
                     ])
        write_page(written, ROOT / slug(town) / slug(hood) / "index.html", page)


def build_hubs(cfg: dict, businesses: list[dict], written: set[pathlib.Path],
               kind_pages, group_pages, hood_pages) -> None:
    # Town hubs
    for town in TOWNS:
        depth = 1
        n = sum(1 for b in businesses if b.get("town") == town)
        kinds = [(k, rows) for t, k, rows in kind_pages if t == town]
        groups = [(g, rows) for t, g, rows in group_pages if t == town]
        hoods = [(h, rows) for t, h, rows in hood_pages if t == town]
        kind_links = "".join(
            f'<a href="{esc(kind["slug"] + "/")}"><span>{esc(kind["label"].capitalize())}</span><span class="n">{len(rows)}</span></a>'
            for kind, rows in kinds
        )
        group_links = "".join(
            f'<a href="{esc(slug(g) + "/")}"><span>{esc(g)}</span><span class="n">{len(rows)}</span></a>'
            for g, rows in groups
        )
        hood_links = "".join(
            f'<a href="{esc(slug(h) + "/")}"><span>{esc(h)}</span><span class="n">{len(rows)}</span></a>'
            for h, rows in hoods
        )
        hood_sec = f'<h2>Pockets of town</h2><div class="guide-index">{hood_links}</div>' if hood_links else ""
        body = f'''<main class="wrap">
  <header class="page-head">
    {crumbs_html([("Home", rel(depth, "index.html")), (town, "")])}
    <h1>{esc(town)}</h1>
    <p class="lede">{n} listings in {esc(town)}, grouped for search and for people who want a page, not only a map.</p>
  </header>
  {newsletter_cta(cfg, depth)}
  <h2>By kind</h2>
  <div class="guide-index">{kind_links}</div>
  <h2>By directory group</h2>
  <div class="guide-index">{group_links}</div>
  {hood_sec}
  <p><a href="{esc(rel(depth, "index.html?t=" + quote(town)))}">Open {esc(town)} on the map</a></p>
</main>'''
        path = f"{slug(town)}/"
        page = shell(cfg, title=f"{town}, VA business directory | {site_name(cfg)}",
                     description=f"Businesses in {town}, VA, by kind, group, and pocket of town. From Blacksburg Connect.",
                     canonical=abs_url(cfg, path), depth=depth, current="guides", body=body,
                     jsonld=[breadcrumb_ld(cfg, [("Home", "index.html"), (town, path)])])
        write_page(written, ROOT / slug(town) / "index.html", page)

    # Guides hub
    depth = 1
    links = []
    for town, kind, rows in kind_pages:
        href = f"{kind['slug']}-{slug(town)}/"
        links.append(f'<a href="{esc(href)}"><span>{esc(kind["label"].capitalize())} in {esc(town)}</span><span class="n">{len(rows)}</span></a>')
    body = f'''<main class="wrap">
  <header class="page-head">
    {crumbs_html([("Home", rel(depth, "index.html")), ("Guides", "")])}
    <h1>Local guides</h1>
    <p class="lede">Pages for the searches people actually type. Each one is built from the directory, then points back to the map and the calendar.</p>
  </header>
  {newsletter_cta(cfg, depth)}
  <div class="guide-index">{"".join(links)}</div>
  <p><a href="{esc(rel(depth, "blacksburg/"))}">Blacksburg hub</a> · <a href="{esc(rel(depth, "christiansburg/"))}">Christiansburg hub</a></p>
</main>'''
    page = shell(cfg, title=f"Local guides to Blacksburg and Christiansburg | {site_name(cfg)}",
                 description="Guides to coffee, restaurants, and more in Blacksburg and Christiansburg, from the Blacksburg Connect directory.",
                 canonical=abs_url(cfg, "best/"), depth=depth, current="guides", body=body,
                 jsonld=[breadcrumb_ld(cfg, [("Home", "index.html"), ("Guides", "best/")])])
    write_page(written, ROOT / "best" / "index.html", page)

    # Newsletter
    depth = 1
    href = cfg.get("newsletter_url") or ""
    if href:
        signup = f'<p><a class="btn primary" href="{esc(href)}">Get the newsletter</a></p>'
        lede = "Local stories, events, and places worth knowing. One letter, written for this town."
    else:
        signup = ("<p>The signup link is not connected yet. Browse the calendar and the directory "
                  "in the meantime.</p>")
        lede = "Local stories, events, and places worth knowing. One letter, written for this town."
    body = f'''<main class="wrap">
  <header class="page-head">
    {crumbs_html([("Home", rel(depth, "index.html")), ("Newsletter", "")])}
    <h1>Blacksburg Connect</h1>
    <p class="lede">{esc(lede)}</p>
  </header>
  {signup}
  <p><a href="{esc(rel(depth, "events/"))}">See what's on</a> · <a href="{esc(rel(depth, "best/"))}">Browse the guides</a> · <a href="{esc(rel(depth, "index.html"))}">Open the map</a></p>
</main>'''
    page = shell(cfg, title=f"Newsletter | {site_name(cfg)}",
                 description="Blacksburg Connect, the local newsletter for Blacksburg and Christiansburg.",
                 canonical=abs_url(cfg, "newsletter/"), depth=depth, current="newsletter", body=body,
                 jsonld=[breadcrumb_ld(cfg, [("Home", "index.html"), ("Newsletter", "newsletter/")])])
    write_page(written, ROOT / "newsletter" / "index.html", page)

    # 404
    depth = 0
    body = f'''<main class="wrap">
  <header class="page-head">
    <h1>That page is not here</h1>
    <p class="lede">Try the directory map, the events calendar, or the guides.</p>
  </header>
  <p><a href="{esc(rel(depth, "index.html"))}">Directory</a> · <a href="{esc(rel(depth, "events/"))}">Events</a> · <a href="{esc(rel(depth, "best/"))}">Guides</a></p>
</main>'''
    page = shell(cfg, title=f"Page not found | {site_name(cfg)}",
                 description="That page is not on Blacksburg Connect.",
                 canonical=abs_url(cfg, "404.html"), depth=depth, current="", body=body)
    write_page(written, ROOT / "404.html", page)


def build_sitemap(cfg: dict, written: set[pathlib.Path], extra_paths: list[str]) -> None:
    urls = ["index.html"] + extra_paths
    # HTML pages we wrote, as URL paths
    for p in sorted(written):
        try:
            rel_p = p.relative_to(ROOT)
        except ValueError:
            continue
        if rel_p.suffix != ".html":
            continue
        if rel_p.name == "index.html" and rel_p.parent != ROOT:
            urls.append(str(rel_p.parent).replace("\\", "/") + "/")
        elif rel_p.name == "404.html":
            continue
        else:
            urls.append(str(rel_p).replace("\\", "/"))
    # unique, stable
    seen = []
    for u in urls:
        if u not in seen:
            seen.append(u)
    chunks = []
    for u in seen:
        loc = abs_url(cfg, u)
        chunks.append(f"  <url><loc>{esc(loc)}</loc></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(chunks) + "\n</urlset>\n"
    write_page(written, ROOT / "sitemap.xml", xml)
    robots = f"User-agent: *\nAllow: /\n\nSitemap: {abs_url(cfg, 'sitemap.xml')}\n"
    write_page(written, ROOT / "robots.txt", robots)


def sweep_stale(written: set[pathlib.Path]) -> None:
    keep_names = {"events.js"}
    for folder in GENERATED_DIRS:
        base = ROOT / folder
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.name in keep_names:
                continue
            if p.suffix in {".html", ".xml", ".txt"} and p.resolve() not in written:
                p.unlink()
        # remove empty dirs, deepest first
        for p in sorted(base.rglob("*"), key=lambda x: len(x.parts), reverse=True):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()


def build() -> list[str]:
    cfg, biz_doc, events_doc = load()
    businesses = biz_doc.get("businesses") or []
    written: set[pathlib.Path] = set()
    kind_pages = collect_kind_pages(businesses)
    group_pages = collect_group_pages(businesses)
    hood_pages = collect_hood_pages(businesses)
    build_events(cfg, events_doc, businesses, written)
    build_kind_and_best(cfg, businesses, written, kind_pages)
    build_groups_and_hoods(cfg, written, group_pages, hood_pages)
    build_hubs(cfg, businesses, written, kind_pages, group_pages, hood_pages)
    build_sitemap(cfg, written, [])
    sweep_stale(written)
    paths = sorted(str(p.relative_to(ROOT)) for p in written)
    return paths


def main() -> None:
    paths = build()
    print(f"Wrote {len(paths)} files")
    for p in paths:
        if p.endswith("index.html") and any(x in p for x in ("coffee-shops", "restaurants", "events/")):
            print(" ", p)


if __name__ == "__main__":
    main()
