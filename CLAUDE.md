# Project brief

Static business directory for Blacksburg, VA. See README.md for layout.

## First tasks
1. Run `python scripts/refresh.py`. Fix any Overture schema mismatch in `pull()` / `to_record()`.
2. Review group counts in `data/businesses.json`. Tune `scripts/groups.py` until "Other" is under 15%.
3. Spot-check 20 downtown listings against reality and add `overrides.csv` rows for misses.

## Rules
- Never store Google Places content. Only `google_place_id` may be saved.
- `data/` is generated. Manual changes go in `overrides.csv`.
- Keep the site static with no build step.
