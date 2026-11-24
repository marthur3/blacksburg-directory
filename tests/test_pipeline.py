#!/usr/bin/env python3
"""Offline checks for grouping, overrides, and the fixture pull. No S3."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from groups import GROUPS, assign_group  # noqa: E402
from refresh import apply_overrides, latest_release, pull, to_record  # noqa: E402

CONFIG = json.loads((ROOT / "config.json").read_text())


def test_groups():
    assert assign_group("coffee_shop") == "Food & Drink"
    assert assign_group("barber") == "Beauty & Personal Care"
    assert assign_group("veterinarian") == "Pets"
    assert assign_group("auto_parts_store") == "Auto"
    assert assign_group("christian place of worship") == "Community & Civic"
    assert assign_group("historic site") == "Arts & Entertainment"
    assert assign_group("zzz_unknown") == "Other"
    assert "Other" in GROUPS


def test_fixture_pull():
    rows = pull(str(ROOT / "tests/fixture.parquet"))
    recs = [to_record(r) for r in rows]
    kept = {r["id"]: r for r in recs if r}
    assert "t5" not in kept, "permanently_closed should be dropped"
    assert "t6" not in kept, "low confidence should be dropped"
    assert "t7" not in kept, "outside bbox should not be pulled"
    assert set(kept) == {"t1", "t2", "t3", "t4", "t8", "t9"}
    assert kept["t1"]["group"] == "Food & Drink"
    assert kept["t2"]["group"] == "Beauty & Personal Care"
    assert kept["t3"]["group"] == "Food & Drink"
    assert kept["t4"]["group"] == "Auto"
    assert kept["t8"]["group"] == "Pets"
    assert kept["t9"]["group"] == "Other"
    assert kept["t1"]["town"] == "Blacksburg"
    assert kept["t4"]["town"] == "Christiansburg"


def test_overrides_add_and_hide(tmp_path=None):
    import refresh as refresh_mod
    csv_path = ROOT / "tests" / "_overrides_tmp.csv"
    csv_path.write_text(
        "action,id,name,group,category,address,town,lat,lng,website,phone,google_place_id,notes\n"
        "hide,gone,,,,,,,,,,\n"
        "add,manual-cafe,Test Added Cafe,Food & Drink,cafe,1 Main,Blacksburg,37.23,-80.41,,,,\n",
        encoding="utf-8",
    )
    old = refresh_mod.OVERRIDES
    refresh_mod.OVERRIDES = csv_path
    try:
        records = {
            "gone": {"id": "gone", "name": "Drop me", "group": "Other"},
            "keep-me": {"id": "keep-me", "name": "Stay", "group": "Other"},
        }
        apply_overrides(records)
        assert "gone" not in records
        assert "keep-me" in records
        assert records["manual-cafe"]["name"] == "Test Added Cafe"
        assert records["manual-cafe"]["group"] == "Food & Drink"
    finally:
        refresh_mod.OVERRIDES = old
        csv_path.unlink(missing_ok=True)


def test_drop_landmarks():
    row = {
        "id": "mtn",
        "names": {"primary": "Brush Mountain"},
        "confidence": 1,
        "operating_status": "open",
        "basic_category": "mountain",
        "taxonomy": {},
        "categories": {},
        "addresses": [{"freeform": "x", "locality": "Blacksburg"}],
        "bbox": {"ymin": 37.2, "xmin": -80.4},
        "websites": [],
        "phones": [],
        "socials": [],
    }
    assert to_record(row) is None
    row["basic_category"] = "coffee_shop"
    rec = to_record(row)
    assert rec and rec["group"] == "Food & Drink"


def test_kind_rules_flags_and_history():
    import refresh as refresh_mod
    from groups import group_for
    assert group_for("hardware_home_and_garden_store", "", "Bed Bath & Beyond") == "Shopping"
    assert group_for("wellness_service") == "Beauty & Personal Care"
    assert group_for("", "", "Test Pizza Place") == "Food & Drink"

    csv_path = ROOT / "tests" / "_overrides_tmp.csv"
    csv_path.write_text(
        "action,id,name,group,category,address,town,lat,lng,website,phone,google_place_id,notes,flag\n"
        "rule-group,,,Community & Civic,historic site,,,,,,,,,\n"
        "rule-hide,,,,parking,,,,,,,,not useful,\n"
        "edit,h2,,Lodging,,,,,,,,,B&B in a historic house,follow up\n"
        "edit,p2,,,,,,,,,,,,\n"
        "edit,n1,,,,,,,,,,,-,\n"
        "hide,h3,,,,,,,,,,,closed,\n",
        encoding="utf-8",
    )
    def rec(rid, cat, group, notes=""):
        return {"id": rid, "name": rid, "group": group, "category": cat, "notes": notes,
                "flag": "", "source": "overture"}
    old = refresh_mod.OVERRIDES
    refresh_mod.OVERRIDES = csv_path
    try:
        records = {r["id"]: r for r in [
            rec("h1", "historic site", "Arts & Entertainment"),
            rec("h2", "historic site", "Arts & Entertainment"),
            rec("h3", "historic site", "Arts & Entertainment"),
            rec("p1", "parking", "Other"), rec("p2", "parking", "Other"),
            rec("n1", "bar", "Food & Drink", notes="old note"),
        ]}
        hidden, rules = apply_overrides(records)
        assert records["h1"]["group"] == "Community & Civic"      # kind rule
        assert records["h1"]["was_group"] == "Arts & Entertainment"
        assert records["h2"]["group"] == "Lodging"                 # listing beats rule
        assert records["h2"]["flag"] == "follow up"
        assert "p1" not in records and "p2" in records             # listing edit restores
        assert records["n1"]["notes"] == ""                        # "-" clears
        by = {h["id"]: h for h in hidden}
        assert by["p1"]["hidden_by"] == "kind" and by["h3"]["hidden_by"] == "listing"
        assert by["h3"]["hidden_reason"] == "closed"
        assert {"kind": "parking", "hide": True} in rules
        assert {"kind": "historic site", "group": "Community & Civic"} in rules
    finally:
        refresh_mod.OVERRIDES = old
        csv_path.unlink(missing_ok=True)


def test_latest_release_url():
    # Stay offline in CI. Two jobs hitting STAC at once got HTTP 429 on pull_request.
    assert CONFIG["releases_url"] == "https://stac.overturemaps.org/catalog.json"
    assert latest_release.__doc__
    src = Path(latest_release.__code__.co_filename).read_text(encoding="utf-8")
    start = src.index("def latest_release")
    body = src[start:src.index("\ndef ", start + 1)]
    assert "429" in body
    assert "retrying" in body


if __name__ == "__main__":
    tests = [test_groups, test_fixture_pull, test_overrides_add_and_hide, test_kind_rules_flags_and_history,
             test_drop_landmarks, test_latest_release_url]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    print("all passed")
