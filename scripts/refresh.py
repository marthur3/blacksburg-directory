#!/usr/bin/env python3
"""Rebuilds data/businesses.json from Overture Places plus overrides.csv.

Usage:
  python scripts/refresh.py                  # latest Overture release
  python scripts/refresh.py --release 2026-10-21.0
  python scripts/refresh.py --source tests/fixture.parquet   # offline test
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from groups import GROUPS, group_for  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text())
OUT = ROOT / "data" / "businesses.json"
CHANGES = ROOT / "data" / "changes.md"
OVERRIDES = ROOT / "overrides.csv"


def latest_release() -> str:
    """Overture's STAC catalog publishes `latest` (e.g. 2026-11-18.0)."""
    req = urllib.request.Request(
        CONFIG["releases_url"],
        headers={"User-Agent": "blacksburg-directory/1.0"},
    )
    payload = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            wait = 2 ** attempt
            print(f"STAC catalog HTTP 429, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
        except urllib.error.URLError as e:
            if attempt == 4:
                raise
            wait = 2 ** attempt
            print(f"STAC catalog {e.reason}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    latest = payload.get("latest")
    if not latest:
        raise SystemExit(f"No 'latest' release in {CONFIG['releases_url']}")
    return latest


def flatten(value) -> str:
    """Category structs vary by schema version; reduce any shape to plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(flatten(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(flatten(v) for v in value)
    return str(value)


def first(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


TOWN_FIX = {
    "blacksburg": "Blacksburg",
    "christiansburg": "Christiansburg",
    "christianburg": "Christiansburg",
    "christiansbrg": "Christiansburg",
}


def normalize_town(town: str) -> str:
    town = (town or "").strip()
    return TOWN_FIX.get(town.lower(), town)


# Landmarks Overture files under places; a business directory has no use for them.
NOT_BUSINESSES = {"mountain", "river", "bridge", "geographic entities", "hot springs", "atm"}


def pull(source: str) -> list[dict]:
    con = duckdb.connect()
    if source.startswith("s3://"):
        con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    rel = f"read_parquet('{source}', hive_partitioning=1)"
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()}

    # Select only columns this release has; the places schema changes between releases.
    optional = ["confidence", "basic_category", "taxonomy", "categories", "operating_status",
                "addresses", "websites", "phones", "socials", "brand"]
    select = ["id", "names", "bbox"] + [c for c in optional if c in cols]
    b = CONFIG["bbox"]
    sql = f"""
        SELECT {", ".join(select)} FROM {rel}
        WHERE bbox.xmin BETWEEN {b["west"]} AND {b["east"]}
          AND bbox.ymin BETWEEN {b["south"]} AND {b["north"]}
    """
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def to_record(row: dict) -> dict | None:
    name = (row.get("names") or {}).get("primary")
    if not name:
        return None
    if (row.get("confidence") or 1) < CONFIG["min_confidence"]:
        return None
    status = row.get("operating_status") or "open"
    if "closed" in status:
        return None

    basic = row.get("basic_category") or ""
    if str(basic).replace("_", " ") in NOT_BUSINESSES:
        return None
    taxonomy = row.get("taxonomy") if isinstance(row.get("taxonomy"), dict) else {}
    tax_primary = (taxonomy or {}).get("primary") or ""
    tax_text = " ".join([flatten(row.get("taxonomy")), flatten(row.get("categories"))])
    category = basic or tax_primary or (row.get("categories") or {}).get("primary") or ""
    addr = first(row.get("addresses")) or {}
    street = addr.get("freeform") or ""
    town = normalize_town(addr.get("locality") or "")
    return {
        "id": row["id"],
        "name": name.strip(),
        "group": group_for(str(category), tax_text, name),
        "category": str(category).replace("_", " "),
        "address": street,
        "town": town,
        "lat": round(row["bbox"]["ymin"], 6),
        "lng": round(row["bbox"]["xmin"], 6),
        "website": first(row.get("websites")) or "",
        "phone": first(row.get("phones")) or "",
        "social": first(row.get("socials")) or "",
        "google_place_id": "",
        "notes": "",
        "flag": "",
        "conf": round(row.get("confidence") or 0, 2),
        "source": "overture",
    }


def read_overrides() -> list[tuple[int, str, str, dict]]:
    """Returns (line, action, id, fields). A field value of "-" clears that field."""
    if not OVERRIDES.exists():
        return []
    rows = []
    with OVERRIDES.open(newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            action = (row.get("action") or "").strip().lower()
            if not action or action.startswith("#"):
                continue
            fields = {k: ("" if v.strip() == "-" else v.strip()) for k, v in row.items()
                      if k and k not in ("action", "id") and v and v.strip()}
            for k in ("lat", "lng"):
                if fields.get(k):
                    fields[k] = float(fields[k])
            rows.append((i, action, (row.get("id") or "").strip(), fields))
    return rows


def apply_overrides(records: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """overrides.csv always wins over the feed. Returns (hidden listings, kind rules).

    Listing actions: add | edit | hide. Kind rules: rule-group | rule-hide, keyed on the
    category column, apply to every listing of that kind. A listing row beats a kind rule.
    """
    rows = read_overrides()
    feed_group = {rid: r["group"] for rid, r in records.items()}
    hidden: dict[str, dict] = {}
    rules: list[dict] = []

    for i, action, _, fields in rows:
        if action not in ("rule-group", "rule-hide"):
            continue
        kind = (fields.get("category") or "").lower()
        if not kind:
            print(f"overrides.csv line {i}: {action} needs a category", file=sys.stderr)
            continue
        matches = [rid for rid, r in records.items() if r["category"].lower() == kind]
        if action == "rule-group":
            if fields.get("group") not in GROUPS:
                print(f"overrides.csv line {i}: unknown group {fields.get('group')!r}", file=sys.stderr)
                continue
            for rid in matches:
                records[rid]["group"] = fields["group"]
            rules.append({"kind": kind, "group": fields["group"]})
        else:
            for rid in matches:
                hidden[rid] = {**records.pop(rid), "hidden_by": "kind", "hidden_reason": fields.get("notes", "")}
            rules.append({"kind": kind, "hide": True})

    for i, action, rid, fields in rows:
        if action in ("rule-group", "rule-hide"):
            continue
        if action == "hide":
            rec = records.pop(rid, None) or hidden.get(rid)
            if rec:
                hidden[rid] = {**rec, "hidden_by": "listing", "hidden_reason": fields.get("notes", "")}
        elif action == "edit":
            if rid in hidden and hidden[rid]["hidden_by"] == "kind":
                rec = hidden.pop(rid)
                rec.pop("hidden_by"), rec.pop("hidden_reason")
                records[rid] = rec
            if rid in records:
                records[rid].update(fields)
                if records[rid]["source"] == "overture":
                    records[rid]["source"] = "overture+edit"
            else:
                print(f"overrides.csv line {i}: edit target {rid} not in feed", file=sys.stderr)
        elif action == "add":
            missing = [k for k in ("name", "lat", "lng") if k not in fields]
            if missing:
                print(f"overrides.csv line {i}: add needs {missing}", file=sys.stderr)
                continue
            rid = rid or "manual-" + re.sub(r"[^a-z0-9]+", "-", fields["name"].lower()).strip("-")
            base = {"id": rid, "group": "Other", "category": "", "address": "", "town": "",
                    "website": "", "phone": "", "social": "", "google_place_id": "",
                    "notes": "", "flag": "", "source": "manual"}
            base.update(fields)
            if base["group"] not in GROUPS:
                print(f"overrides.csv line {i}: unknown group {base['group']!r}", file=sys.stderr)
            records[rid] = base
        else:
            print(f"overrides.csv line {i}: unknown action {action!r}", file=sys.stderr)

    # was_group records what the feed rules chose, so the page can spot patterns in corrections.
    for rid, rec in list(records.items()) + list(hidden.items()):
        if rid in feed_group and rec["group"] != feed_group[rid]:
            rec["was_group"] = feed_group[rid]
    return sorted(hidden.values(), key=lambda r: r["name"].lower()), rules


def write_changes(old: dict[str, dict], new: dict[str, dict], release: str) -> None:
    added = [new[k] for k in new.keys() - old.keys()]
    removed = [old[k] for k in old.keys() - new.keys()]
    lines = [f"# Changes in {release} ({dt.date.today().isoformat()})", "",
             f"{len(new)} listed, {len(added)} new, {len(removed)} dropped.", ""]
    for title, rows in (("New", added), ("Dropped", removed)):
        lines.append(f"## {title}")
        lines += [f"- {r['name']} ({r['group']}) {r['address']}".rstrip()
                  for r in sorted(rows, key=lambda r: r["name"].lower())] or ["- none"]
        lines.append("")
    CHANGES.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release")
    ap.add_argument("--source", help="local parquet path, skips the S3 pull")
    args = ap.parse_args()

    if args.source:
        release, source = "local", args.source
    else:
        release = args.release or latest_release()
        source = f"{CONFIG['bucket']}/{release}/theme=places/type=place/*"
    print(f"Pulling {source}")

    records: dict[str, dict] = {}
    for row in pull(source):
        rec = to_record(row)
        if rec:
            records[rec["id"]] = rec
    hidden, rules = apply_overrides(records)

    old = {}
    if OUT.exists():
        old = {r["id"]: r for r in json.loads(OUT.read_text()).get("businesses", [])}
    # Listings absent from the previous run are stamped; the page uses this for "New".
    today = dt.date.today().isoformat()
    for rid, rec in records.items():
        rec["first_seen"] = old[rid].get("first_seen", "") if rid in old else (today if old else "")
    write_changes(old, records, release)

    businesses = sorted(records.values(), key=lambda r: r["name"].lower())
    OUT.write_text(json.dumps({
        "release": release,
        "updated": dt.date.today().isoformat(),
        "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "groups": GROUPS,
        "businesses": businesses,
        "hidden": hidden,
        "rules": rules,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(businesses)} businesses to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
