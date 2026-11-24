# Blacksburg Business Directory

Map and filterable list of businesses in Blacksburg and Christiansburg. Static site, no server, no API keys.

## Parts

| File | Purpose |
|---|---|
| `index.html` | Map, search, group chips, town filter, shareable links (`?g=food-drink`) |
| `data/businesses.json` | Generated. Do not edit by hand |
| `data/changes.md` | Generated. New and dropped businesses since the last refresh |
| `overrides.csv` | Your edits. Always wins over the feed |
| `scripts/refresh.py` | Pulls Overture Places for the bbox in `config.json`, applies overrides |
| `scripts/groups.py` | Keyword rules that sort categories into groups |
| `.github/workflows/refresh.yml` | Runs the refresh monthly, on demand, and when `overrides.csv` changes |
| `.github/workflows/test.yml` | Offline fixture + grouping checks on every push |

## Run locally

The page loads `data/businesses.json` with `fetch()`, so it has to be served over HTTP. Opening `index.html` as a file will not show listings.

```
python3 -m pip install -r requirements.txt
python3 tests/test_pipeline.py          # optional, no S3
python3 scripts/refresh.py              # pulls Overture Places, writes data/
python3 -m http.server 8000
```

Then open http://localhost:8000. Search the list, click a category chip, or pick a town. Marker clicks scroll the matching row.

`refresh.py` needs outbound HTTPS to `stac.overturemaps.org` and Amazon S3 (`s3://overturemaps-us-west-2`). A first pull for this bbox takes a few seconds.

## Deploy (GitHub Pages)

This is a static site: `index.html`, `config.json`, and `data/`. No build step.

1. Push to GitHub (already done for this repo).
2. Repo **Settings → Actions → General → Workflow permissions**: Read and write (so the monthly refresh can commit `data/`).
3. Repo **Settings → Pages**: Deploy from **branch `main`**, folder **`/` (root)**. GitHub Pages is not on until you flip this switch; the site files are otherwise ready.
4. The directory is then at `https://<user>.github.io/blacksburg-directory/`.

Cloudflare Pages also works: no build command, output directory `/`.

Until Pages is enabled, clone the repo and use the local commands above. The first GitHub Actions refresh failed because it still pointed at a retired Overture releases URL; that is fixed, and `data/businesses.json` is populated from the 2026-11-18.0 Places release.

## Editing

Add rows to `overrides.csv`. Editing the file on github.com (on `main`) triggers a rebuild.

| action | Needs | Effect |
|---|---|---|
| `add` | name, lat, lng | Adds a business the feed lacks |
| `edit` | id | Overwrites any filled column, e.g. `group`, `notes`, `google_place_id` |
| `hide` | id | Removes a listing |

Ids come from `data/businesses.json`. Valid groups are listed in `scripts/groups.py`.

## Data and terms

- Places come from the Overture Maps Foundation monthly release. Keep the footer attribution.
- Map tiles come from OpenFreeMap (Positron), falling back to OpenStreetMap's public raster tiles. Switch the tile URL in `index.html` if the directory gets busy.
- Google data is never stored. Each listing links out to Google Maps, using `google_place_id` when you have filled one in.

## Status

- Refresh reads the latest release from Overture's STAC catalog (`https://stac.overturemaps.org/catalog.json`).
- Grouping rules keep the "Other" bucket under 15% of listings.
- Offline tests cover the synthetic fixture in `tests/` (`python tests/test_pipeline.py`).

## Page features

- Group legend with live counts, plus the top kinds inside the chosen group (coffee shop, bar, brewery).
- A to Z rail for jumping through the index, or sort by nearest to the map center.
- Clustered vector map (MapLibre with the OpenFreeMap basemap, OpenStreetMap raster tiles as fallback).
- Shareable links: `?g=food-drink&c=coffee-shop`, `?q=main+st`, `?id=<listing id>`. Add `&embed=1` to hide the title for iframes.
- "New listings" appears once a refresh finds places the previous run did not have (`first_seen` in the data).
- Set `"suggest_url"` in `config.json` to a form or email link to show "Suggest a correction" on every listing.

## Owner edit mode

Open the site with `?edit=1` (not linked from the public page). Visitors who do not open that URL never load the editor, and even then they cannot write without their own GitHub token.

- Open a listing to change its group or kind, add a note, toggle flags, or hide it with a reason.
- Changes stage in the browser first. "Save to directory" writes them to `overrides.csv` as one commit, and the refresh workflow rebuilds the data.
- Saving needs a fine-grained GitHub token for this repo only, with Contents set to read and write. The token is kept in this browser's localStorage and sent only to `api.github.com` as an `Authorization` header (never in a URL, log, or git commit). Revoke it if you used a shared computer. Other GitHub Pages sites on the same `*.github.io` origin can read localStorage — do not store a token if you host untrusted Pages on this account.
- After moving or hiding a listing, the bar offers the same action for every listing of that kind. Accepting adds a `rule-group` or `rule-hide` row.
- "Patterns" lists kinds you have corrected twice or more, and checks whether low source confidence predicts the listings you hid as closed.
- "Least certain first" sorts by Overture's confidence score, which puts likely-closed listings at the top.

Notes show on the public listing. Flags and hide reasons are not shown on the page, but the repo and data file are public.

### overrides.csv actions

| action | Key column | Effect |
|---|---|---|
| `add` | name, lat, lng | Adds a listing |
| `edit` | id | Overwrites filled columns. `-` clears a column |
| `hide` | id | Hides one listing. `notes` holds the reason |
| `rule-group` | category | Moves every listing of that kind to `group` |
| `rule-hide` | category | Hides every listing of that kind |

A listing row beats a kind rule. Delete a rule row to undo it.

## Grouping

`scripts/groups.py` trusts sources in this order: the exact-category map `KIND_GROUP`, keyword rules on the category, keyword rules on the taxonomy, then the listing name.
