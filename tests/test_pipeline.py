#!/usr/bin/env python3
"""Offline checks for grouping, overrides, and the fixture pull. No S3."""
import json
import sys
import urllib.request
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


def test_latest_release_url():
    assert "stac.overturemaps.org" in CONFIG["releases_url"]
    with urllib.request.urlopen(CONFIG["releases_url"], timeout=30) as r:
        payload = json.load(r)
    assert payload.get("latest"), payload
    assert latest_release() == payload["latest"]


if __name__ == "__main__":
    tests = [test_groups, test_fixture_pull, test_overrides_add_and_hide, test_latest_release_url]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    print("all passed")
