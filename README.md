# google-play-api-unofficial

A small Python library and CLI for reading public data from the Google Play Store. No API keys, no auth, no third-party services. Works as a command-line tool for quick lookups, or as an importable library for scripts and pipelines.

Unofficial — not affiliated with or endorsed by Google.

It covers three levels of detail:

- **Autocomplete** — what the Play Store search box would suggest for a half-query
- **Search results** — the top 30 apps matching a query (title, rating, installs, etc.)
- **App details** — full metadata for one app (description, release date, reviews, install counts, developer contact, screenshots)

## Install

```bash
pip install google-play-api-unofficial
```

That's it. The `google-play-api-unofficial` command is now on your PATH. Python 3.9+, zero runtime dependencies (stdlib only).

To install from the repo (for development):

```bash
git clone https://github.com/tejmagar/google-play-api-unofficial
cd google-play-api-unofficial
python -m venv venv
source venv/bin/activate
pip install -e .
```

---

## Table of contents

- [Quick start (CLI)](#quick-start-cli)
- [CLI reference](#cli-reference)
  - [`suggest`](#suggest--autocomplete)
  - [`search`](#search--top-30-apps)
  - [`search --with-details`](#search---with-details)
  - [`details`](#details--rich-per-app-data)
  - [`all`](#all--suggest--search)
  - [Global flags](#global-flags)
- [Programmatic usage](#programmatic-usage)
  - [Quick start](#programmatic-quick-start)
  - [`fetch_suggestions`](#fetch_suggestionsquery-filterfilterapps-timeout10)
  - [`fetch_apps`](#fetch_appsquery-timeout15)
  - [`fetch_app_details`](#fetch_app_detailspackage_id-timeout15)
  - [Field reference](#field-reference)
  - [Error handling](#error-handling)
- [Recipes](#recipes)
  - [Expand a half-query into related terms](#expand-a-half-query-into-related-terms)
  - [Find established apps in a category](#find-established-apps-in-a-category)
  - [Compare two apps side by side](#compare-two-apps-side-by-side)
  - [Collect apps across related queries](#collect-apps-across-related-queries)
  - [Rank apps by review-to-install ratio](#rank-apps-by-review-to-install-ratio)
- [Limits and errors](#limits-and-errors)
- [License](#license)

---

## Quick start (CLI)

```bash
google-play-api-unofficial suggest vpn
google-play-api-unofficial search "habit tracker"
google-play-api-unofficial search "habit tracker" --with-details
google-play-api-unofficial details com.duolingo
google-play-api-unofficial all "vpn" "habit tracker"
```

Add `--json` to any command for machine-readable output.

---

## CLI reference

The command has four subcommands plus global flags.

### `suggest` — autocomplete

Fetches what the Play Store search box would suggest for a half-query. Useful for finding related terms and similar apps.

```bash
google-play-api-unofficial suggest vpn
google-play-api-unofficial suggest "habit"
google-play-api-unofficial suggest "puzzle" --filter games
google-play-api-unofficial suggest vpn "habit" workout --json
```

Use `--filter` to include games or all types (default: `apps`).

Output:
```
=== vpn ===
  Suggestions (5):
    - vpn
    - vpn and proxy tools
    - vpn 1111
    - vpn india
    - vpnify
```

### `search` — top 30 apps

Fetches the top 30 apps matching a query. Each result has: `title`, `package`, `rating`, `category`, `developer`, `installs`, `icon`, `url`, `featured` (`True` when Play promotes the app in the featured hero card above the organic results).

```bash
google-play-api-unofficial search "habit tracker"
google-play-api-unofficial search vpn "habit tracker" --json
```

Output:
```
=== habit tracker ===

  Apps (30):
    - Loop Habit Tracker  4.6*  5,000,000+  [Productivity]
        org.isoron.uhabits
    - Disciplined - Habit Tracker  4.6*  500,000+  [Productivity]
        app.disciplined.productive.structured.habit.tracker
    ...
```

You can pass multiple queries — they're run sequentially:

```bash
google-play-api-unofficial search "habit tracker" "daily habit" "routine planner"
```

### `search --with-details`

Enriches every result with the full details payload (description, release date, reviews count, etc.). Slower — one extra request per app, 200ms between requests to avoid 429s.

```bash
google-play-api-unofficial search "habit tracker" --with-details
```

Output (per app, indented under "Apps"):
```
=== habit tracker ===

  Apps (30):
  Title:       Loop Habit Tracker
  Package:     org.isoron.uhabits
  Score:       4.6  (43,000 ratings, 2,200 reviews)
  Installs:    5,000,000+
  Released:    Jan 15, 2016
  Updated:     May 12, 2026
  ...
  Description:
    A beautiful, open source habit tracker...
```

### `details` — rich per-app data

Fetches description, release date, last updated, score, ratings count, reviews count, star histogram, install count (with real number), content rating, developer + id, developer website/email, IAP price range, and all screenshot URLs.

```bash
google-play-api-unofficial details com.duolingo
google-play-api-unofficial details ch.protonvpn.android com.nordvpn.android com.duolingo
google-play-api-unofficial details com.duolingo --json
```

Multiple packages are fetched sequentially with 200ms between requests.

### `all` — suggest + search

Runs both `suggest` and `search` for one or more queries.

```bash
google-play-api-unofficial all "habit tracker"
google-play-api-unofficial all vpn "habit" --json
```

Output:
```
=== vpn ===

  Suggestions (5):
    - vpn
    - vpn and proxy tools
    ...

  Apps (30):
    - Turbo VPN - Secure VPN Proxy  ...
        free.vpn.unblock.proxy.turbovpn
    ...
```

### Global flags

| Flag | Applies to | Effect |
|---|---|---|
| `--json` | all | Output JSON instead of formatted text |
| `--filter {apps,games,all}` | `suggest` | Restrict the type of apps included (default: `apps`) |
| `--with-details` | `search` | Enrich each result with full details |

### JSON output shapes

**`suggest`:**
```json
{ "vpn": ["vpn", "vpn and proxy tools", "vpn 1111"] }
```

**`search`:**
```json
{
  "habit tracker": {
    "apps": [
      {
        "package": "org.isoron.uhabits",
        "title": "Loop Habit Tracker",
        "rating": "4.6",
        "category": "Productivity",
        "developer": "Alkaline Software",
        "installs": "5,000,000+",
        "icon": "https://play-lh.googleusercontent.com/...",
        "url": "https://play.google.com/store/apps/details?id=org.isoron.uhabits"
      }
    ]
  }
}
```

**`details`:**
```json
{
  "com.duolingo": {
    "package": "com.duolingo",
    "title": "Duolingo: Language Lessons",
    "score": "4.7",
    "ratings_count": "45,891,296",
    "reviews_count": "943,469",
    "histogram": [[5, 949035], [4, 380492], [3, 1042115], [2, 5598924], [1, 37920696]],
    "installs": "500,000,000+",
    "installs_min": 500000000,
    "installs_real": 919061546,
    "released": "May 29, 2013",
    "updated": "Jun 2, 2026",
    "content_rating": "Everyone",
    "developer": "Duolingo",
    "developer_id": "6957685454452609502",
    "developer_email": "super-support@duolingo.com",
    "developer_website": "https://www.duolingo.com/help/support-request",
    "iap_range": "$0.99 - $239.99 per item",
    "short_description": "Lessons to learn Spanish, French, German, English, Online Chess, Math & Music",
    "description": "Learn a new language, chess & more with the world's most downloaded education app!...",
    "icon": "https://play-lh.googleusercontent.com/...",
    "screenshots": ["https://play-lh.googleusercontent.com/...", "..."],
    "url": "https://play.google.com/store/apps/details?id=com.duolingo"
  }
}
```

**`all`:**
```json
{
  "vpn": {
    "suggestions": ["vpn", "vpn and proxy tools"],
    "apps": [{ "package": "...", "title": "...", "rating": "4.6" }]
  }
}
```

---

## Programmatic usage

The same three functions are importable as a library.

### Programmatic quick start

```python
from google_play_api_unofficial import fetch_suggestions, fetch_apps, fetch_app_details

# Autocomplete
sugs = fetch_suggestions("vpn")
# -> ["vpn", "vpn and proxy tools", "vpn 1111", "vpn india", "vpnify"]

# Top 30 apps
apps = fetch_apps("habit tracker")
# -> [{"package": "org.isoron.uhabits", "title": "Loop Habit Tracker", ...}, ...]

# Full details for one app
d = fetch_app_details("com.duolingo")
# -> {"package": "com.duolingo", "title": "Duolingo: ...", "score": "4.7", ...}
```

All three are blocking, synchronous, and use `urllib.request` under the hood. They raise on network errors (catch with `try`/`except`) and return `[]` / `None` for empty results.

### `fetch_suggestions(query, filter=Filter.APPS, timeout=10)`

Fetch Play Store autocomplete suggestions for a half-query.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `query` | `str` | required | The half-query to complete |
| `filter` | `Filter` | `Filter.APPS` | `Filter.APPS`, `Filter.GAMES`, or `Filter.ALL` |
| `timeout` | `int` | `10` | HTTP timeout in seconds |

Returns: `list[str]` — the suggestions (already stripped and length-filtered to 3-100 chars). Empty list if the RPC returns nothing or fails to parse.

```python
from google_play_api_unofficial import fetch_suggestions, Filter

# Default: apps-only suggestions
sugs = fetch_suggestions("vpn")

# Include games in the suggestions
sugs = fetch_suggestions("puzzle", filter=Filter.GAMES)

# All types
sugs = fetch_suggestions("tracker", filter=Filter.ALL)
```

### `fetch_apps(query, timeout=15)`

Fetch the top 30 apps matching a query. The Play Store HTML endpoint caps each query at 30 results; run additional queries with different angles to get more.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `query` | `str` | required | Search query |
| `timeout` | `int` | `15` | HTTP timeout in seconds |

Returns: `list[dict]` — each dict has the shape:

```python
{
    "package":    "org.isoron.uhabits",   # str — app id (use this for fetch_app_details)
    "title":      "Loop Habit Tracker",
    "rating":     "4.6",                   # str — the average star rating, or None
    "category":   "Productivity",
    "developer":  "Alkaline Software",
    "installs":   "5,000,000+",            # str — the display bucket
    "icon":       "https://play-lh.googleusercontent.com/...",
    "url":        "https://play.google.com/store/apps/details?id=org.isoron.uhabits",
}
```

Empty list if the search page can't be parsed (rare).

```python
from google_play_api_unofficial import fetch_apps

apps = fetch_apps("habit tracker")
for app in apps:
    print(app["title"], app["package"], app["installs"])
```

### `fetch_app_details(package_id, timeout=15)`

Fetch rich details for one app by package id.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `package_id` | `str` | required | e.g. `"com.duolingo"` |
| `timeout` | `int` | `15` | HTTP timeout in seconds |

Raises:
- `AppNotFoundError` — package id does not exist on the Play Store (HTTP 404). The exception's `.package_id` attribute holds the id.
- `urllib.error.HTTPError` — for other HTTP errors (e.g. 429 rate limit). Catch if you need to retry.
- Other network errors (e.g. `urllib.error.URLError`).

Returns: `dict` with the full details, or `None` if the page was fetched but the data could not be parsed. See the [field reference](#field-reference) for the complete shape.

```python
from google_play_api_unofficial import fetch_app_details, AppNotFoundError

try:
    d = fetch_app_details("com.duolingo")
except AppNotFoundError:
    print("No such app")
else:
    print(d["title"], d["score"], d["installs"], d["released"])
```

### Field reference

Output of `fetch_app_details` (and the enriched results from `search --with-details`):

| Field | Type | Notes |
|---|---|---|
| `package` | `str or None` | App id (e.g. `com.duolingo`) |
| `title` | `str or None` | App name |
| `score` | `str or None` | Average star rating (e.g. `"4.7"`) |
| `ratings_count` | `str or None` | Total number of ratings (e.g. `"45,891,296"`) |
| `reviews_count` | `str or None` | Number of written reviews (e.g. `"943,469"`) |
| `histogram` | `list[tuple[int, int]]` | `[(stars, count), ...]` from 5★ down to 1★ |
| `installs` | `str or None` | Display bucket (e.g. `"500,000,000+"`) |
| `installs_min` | `int or None` | Lower bound of the bucket (e.g. `500_000_000`) |
| `installs_real` | `int or None` | Approximate actual install count (e.g. `919_061_546`) |
| `released` | `str or None` | First release date (e.g. `"May 29, 2013"`) |
| `updated` | `str or None` | Last update date (e.g. `"Jun 2, 2026"`) |
| `content_rating` | `str or None` | PEGI/ESRB-style age rating (e.g. `"Everyone"`) |
| `category` | `None` | Not in the details payload; populated by `search` if you join the two |
| `developer` | `str or None` | Developer name |
| `developer_id` | `str or None` | Play Store dev id (e.g. `"6957685454452609502"`) |
| `developer_email` | `str or None` | Support email |
| `developer_website` | `str or None` | Website URL |
| `developer_address` | `str or None` | Physical address |
| `iap_range` | `str or None` | In-app purchase price range (e.g. `"$0.99 - $239.99 per item"`) |
| `short_description` | `str or None` | One-line tagline |
| `description` | `str or None` | Full description, HTML stripped, `<br>` → newlines |
| `icon` | `str or None` | App icon URL |
| `screenshots` | `list[str]` | URLs of all screenshots (and the feature graphic at index 0) |
| `url` | `str or None` | Play Store URL |

Output of `fetch_apps`:

| Field | Type | Notes |
|---|---|---|
| `package` | `str` | App id |
| `title` | `str` | App name |
| `rating` | `str or None` | Average star rating |
| `category` | `str or None` | App category |
| `developer` | `str or None` | Developer name |
| `installs` | `str or None` | Display install bucket |
| `icon` | `str or None` | App icon URL |
| `url` | `str or None` | Play Store URL |
| `featured` | `bool` | `True` when Play promotes the app in the featured hero card (`apps_mdp_search_results_cluster`) above the organic results. The featured card is not part of the organic list, so its app is prepended to the results. |

### Error handling

- `fetch_suggestions` and `fetch_apps` can raise `urllib.error.HTTPError` (rate limits, etc.) or `urllib.error.URLError` (network problems). They return `[]` if the page was fetched but could not be parsed.
- `fetch_app_details` raises `AppNotFoundError` on 404 and propagates other `HTTPError`s. It returns `None` only when the page was fetched but couldn't be parsed.
- The CLI catches `AppNotFoundError` and prints `! app not found: <pkg>` to stderr, then continues with the next package.

```python
import urllib.error
from google_play_api_unofficial import fetch_apps, fetch_app_details, AppNotFoundError

# fetch_apps returns [] on parse failure but raises on network errors
try:
    apps = fetch_apps("habit tracker")
except urllib.error.HTTPError as e:
    if e.code == 429:
        print("Rate limited — try again in a minute")
    else:
        raise

# fetch_app_details raises AppNotFoundError for 404
try:
    d = fetch_app_details("ch.protonvpn.android")
except AppNotFoundError as e:
    print(f"No such app: {e.package_id}")
except urllib.error.HTTPError as e:
    if e.code == 429:
        print("Rate limited — try again in a minute")
    else:
        raise

# Multi-app loop with a small sleep to avoid 429s
import time
results = []
for pkg in ["com.duolingo", "com.busuu", "com.babbel"]:
    try:
        results.append(fetch_app_details(pkg))
    except AppNotFoundError:
        print(f"skipped (not found): {pkg}")
        results.append(None)
    except urllib.error.HTTPError as e:
        print(f"skipped {pkg}: {e}")
        results.append(None)
    time.sleep(0.2)
```

---

## Recipes

### Expand a half-query into related terms

```bash
google-play-api-unofficial suggest "habit" --json | jq -r '.["habit"][]'
```

### Find established apps in a category

```bash
google-play-api-unofficial search "habit tracker" --json \
  | jq -r '.["habit tracker"].apps[] | "\(.installs)\t\(.rating)\t\(.package)\t\(.title)"' \
  | sort -rn
```

Sort by installs to find incumbents; by rating to find quality outliers.

In Python:

```python
apps = fetch_apps("habit tracker")
for a in sorted(apps, key=lambda a: a.get("installs") or "", reverse=True):
    print(a["installs"], a["rating"], a["package"], a["title"])
```

### Compare two apps side by side

CLI:
```bash
google-play-api-unofficial details com.duolingo com.busuu --json \
  | jq 'to_entries | map({pkg: .key, released: .value.released, installs: .value.installs, score: .value.score, reviews: .value.reviews_count, iap: .value.iap_range})'
```

Python:
```python
import json
a = fetch_app_details("com.duolingo")
b = fetch_app_details("com.busuu")
for d in (a, b):
    print(f"{d['package']}: {d['title']}")
    print(f"  released: {d['released']}, updated: {d['updated']}")
    print(f"  score: {d['score']} ({d['ratings_count']} ratings, {d['reviews_count']} reviews)")
    print(f"  installs: {d['installs']} (~{d['installs_real']:,} real)")
    print(f"  iap: {d['iap_range']}")
```

### Collect apps across related queries

Loop 3-5 different seed queries, collect package ids, dedupe, then optionally fetch details for the most promising:

```python
queries = ["habit tracker", "daily routine", "streak app", "todo planner"]
seen = set()
all_apps = []
for q in queries:
    for app in fetch_apps(q):
        if app["package"] not in seen:
            seen.add(app["package"])
            all_apps.append(app)

print(f"Found {len(all_apps)} unique apps across {len(queries)} queries")

# Now enrich top N with details
import time
for app in all_apps[:20]:
    try:
        d = fetch_app_details(app["package"])
        app.update({k: v for k, v in d.items() if v not in (None, [], "")})
    except Exception as e:
        print(f"  skipped {app['package']}: {e}")
    time.sleep(0.2)
```

### Rank apps by review-to-install ratio

The reviews-to-installs ratio is a strong signal: an app with a small install count but a high ratio is getting unusual engagement.

```python
candidates = []
for app in fetch_apps("fitness coach"):
    try:
        d = fetch_app_details(app["package"])
    except Exception:
        continue
    if not d or not d.get("installs_real") or not d.get("reviews_count"):
        continue
    real = d["installs_real"]
    # reviews_count is a formatted string like "1,234"
    reviews = int(d["reviews_count"].replace(",", ""))
    engagement = reviews / real  # reviews per install
    candidates.append((engagement, d))
    time.sleep(0.2)

candidates.sort(reverse=True)
for engagement, d in candidates[:20]:
    print(f"{engagement*100:.3f}%  {d['package']}  {d['title']}  reviews={d['reviews_count']}  installs={d['installs']}")
```

CLI equivalent:
```bash
google-play-api-unofficial search "fitness coach" --with-details --json \
  | jq -r '.["fitness coach"].apps[] | select(.installs_real != null and .reviews_count != null) | "\(.reviews_count)\t\(.installs_real)\t\(.package)"' \
  | sort -rn | head -20
```

---

## Limits and errors

- **Search results:** 30 per query (Play Store HTML cap; the public endpoint does not paginate via `&start=N`. To get more, use multiple seed queries and dedupe by `package`.)
- **Suggestions:** 10 per query (Play Store cap)
- **Rate limits:** Play Store returns HTTP 429 after sustained scraping. The CLI sleeps 200ms between detail requests. If you hit 429, wait a minute and retry. Multi-second sleeps are safer for bulk jobs.
- **HTTP 404** — package id is no longer in the Play Store (deleted, renamed, or never existed). The library raises `AppNotFoundError`; the CLI catches it and prints `! app not found: <pkg>` to stderr.
- **No results** — Play Store returned a page without the expected data chunks. Usually transient; retry.

## License

MIT
