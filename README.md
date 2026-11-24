# Blacksburg Business Directory

Map and filterable list of businesses in Blacksburg and Christiansburg. Static site, no server, no API keys.

## Parts

| File | Purpose |
|---|---|
| `index.html` | Map, search, group chips, town filter, shareable links (`#food-drink`) |
| `data/businesses.json` | Generated. Do not edit by hand |
| `data/changes.md` | Generated. New and dropped businesses since the last refresh |
| `overrides.csv` | Your edits. Always wins over the feed |
| `scripts/refresh.py` | Pulls Overture Places for the bbox in `config.json`, applies overrides |
| `scripts/groups.py` | Keyword rules that sort categories into groups |
| `.github/workflows/refresh.yml` | Runs the refresh monthly, on demand, and when `overrides.csv` changes |

## Setup

1. Create the repo and push.
   ```
   gh repo create blacksburg-directory --public --source . --push
   ```
2. In the repo, set Settings > Actions > General > Workflow permissions to "Read and write".
3. Set Settings > Pages to deploy from `main`, root folder.
4. Run the "Refresh directory data" workflow once from the Actions tab.

The site is then live at `https://<user>.github.io/blacksburg-directory/`. Cloudflare Pages also works with no build command.

## Editing

Add rows to `overrides.csv`. Editing the file on github.com triggers a rebuild.

| action | Needs | Effect |
|---|---|---|
| `add` | name, lat, lng | Adds a business the feed lacks |
| `edit` | id | Overwrites any filled column, e.g. `group`, `notes`, `google_place_id` |
| `hide` | id | Removes a listing |

Ids come from `data/businesses.json`. Valid groups are listed in `scripts/groups.py`.

## Local run

```
pip install duckdb
python scripts/refresh.py
python -m http.server 8000
```

## Data and terms

- Places come from the Overture Maps Foundation monthly release. Keep the footer attribution.
- Map tiles come from OpenStreetMap's public tile server, which is meant for light traffic. Switch the tile URL in `index.html` if the directory gets busy.
- Google data is never stored. Each listing links out to Google Maps, using `google_place_id` when you have filled one in.

## Status

- Tested: refresh logic, overrides, grouping, and the page UI against a synthetic fixture (`tests/`).
- Not yet run: the live Overture pull. The build environment could not reach Overture's bucket, so the first workflow run is the first real test. `refresh.py` reads the release's column list before selecting, which covers schema changes between releases.
