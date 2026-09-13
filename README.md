# Airbnb Lite

Airbnb Lite is a FastAPI and Next.js application for browsing real
Inside Airbnb listings, viewing real guest reviews, and generating
per-market pricing recommendations.

The local Inside Airbnb archives are the only listing and review source:

```text
listings*.csv.gz + reviews*.csv.gz
                |
                v
insideairbnb_loader.py
                |
                v
PostgreSQL (airbnb_lite)
                |
                v
FastAPI (main.py) <---- Next.js frontend
```

The browser never reads the compressed archives directly. The loader imports
them into PostgreSQL, and the frontend consumes the API.

## Requirements

- Python 3.11+ (Python 3.14 also works)
- PostgreSQL
- Node.js and npm
- The local `listings*.csv.gz` and `reviews*.csv.gz` archives in this folder

Install the Python dependencies:

```powershell
python -m pip install fastapi uvicorn sqlalchemy psycopg2-binary `
  scikit-learn joblib pandas numpy requests python-dotenv
```

Install the frontend dependencies:

```powershell
npm install
```

## Environment variables (set once, not every session)

Copy `.env.example` to `.env` and fill in real values:

```powershell
copy .env.example .env
```

`.env` is gitignored (the repo's `.env*` rule, same as `.env.local`), so it's
never committed - only `.env.example` (the template, with no real values) is.
`db.py` and `external_signals.py` both call `python-dotenv`'s `load_dotenv()`
before reading any of `DATABASE_URL`, `PREDICTHQ_API_KEY`, or `NEWSAPI_KEY`,
so once `.env` exists, every entry point (`uvicorn`, `insideairbnb_loader.py`,
`reset_and_reload_sample.py`, `pricing_engine.py`, ...) picks them up
automatically - no more `$env:DATABASE_URL = "..."` in every new terminal. An
explicit `$env:` (or `export`) in your shell still overrides whatever is in
`.env`, so this doesn't get in the way of temporarily testing a different
value.

The Next.js frontend already works this way on its own - it auto-loads
`NEXT_PUBLIC_API_URL` from `.env.local` without any extra code - `.env.example`
lists it too just so every variable this project uses lives in one reference
file.

## PostgreSQL setup

Create a database named `airbnb_lite`, then put the connection string in
`.env` (see above) as `DATABASE_URL`:

```
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/airbnb_lite
```

The schema is created or extended automatically when the loader/API starts.
Inside Airbnb listing and host IDs use `BIGINT`, because they can exceed the
32-bit PostgreSQL integer range.

The 10 `markets` rows themselves (name, country, currency, and approximate
city-center coordinates) are also created automatically the first time
`insideairbnb_loader.py` or `reset_and_reload_sample.py` runs against an
empty database (`ensure_markets()` in `insideairbnb_loader.py`) - you do not
need to seed them by hand, and it's safe even if they already exist (it only
ever inserts a row that's missing, never touches one that's already there).

## Local archive mapping

`insideairbnb_loader.py` maps the repository archives to these markets:

| Market | Listings archive | Reviews archive |
| --- | --- | --- |
| Bangkok | `listings(1).csv.gz` | `reviews(9).csv.gz` |
| Cape Town | `listings(2).csv.gz` | `reviews(8).csv.gz` |
| Hong Kong | `listings(3).csv.gz` | `reviews(7).csv.gz` |
| Istanbul | `listings(10).csv.gz` | `reviews(6).csv.gz` |
| Mexico City | `listings(4).csv.gz` | `reviews(5).csv.gz` |
| New York | `listings(5).csv.gz` | `reviews(4).csv.gz` |
| Paris | `listings(6).csv.gz` | `reviews(3).csv.gz` |
| Rio de Janeiro | `listings(7).csv.gz` | `reviews(2).csv.gz` |
| Rome | `listings(8).csv.gz` | `reviews(1).csv.gz` |
| Sydney | `listings(9).csv.gz` | `reviews.csv.gz` |

Keep these archives local. They are intentionally ignored by Git because they
are large data files.

**Fixed 2026-09-11:** the Paris/Rio de Janeiro/Rome/Sydney reviews archives
were cyclically swapped (Paris<->Sydney via `reviews.csv.gz`/`reviews(3).csv.gz`,
Rio<->Rome via `reviews(1).csv.gz`/`reviews(2).csv.gz`), so each of those 4
markets matched ~0% of its listings against a real review while the other 6
matched 60-95% as expected. `diagnose_review_mapping.py` confirmed the
correct pairing by actual `listing_id` overlap (tens of thousands of matches
per market once corrected) and the table above and `LOCAL_REVIEW_FILES` in
`insideairbnb_loader.py` now reflect it. If you ever add a new archive and
see a market matching ~0% of its listings again, rerun
`python diagnose_review_mapping.py --data-dir .` to re-check the mapping.

Each imported listing keeps its own archive `picture_url`. The search cards,
guest detail page, and host listing console render that URL, so listings do not
share generated stock images. If a source row has no picture URL, the UI
shows `No photo available`; image files are not downloaded or committed to the
repository.

Guest discovery uses one deterministic representative (the lowest internal
listing ID) for each distinct non-empty image URL. Duplicate archive rows and
rows without images remain in PostgreSQL for backend integrity, but they are
excluded from guest search results and market listing counts.

## Loading listings and reviews: sampled vs. full

Loading the **full** archives works, but it is a lot of real data - about
280,000 listings and 270,000+ review excerpts across the 10 markets - and
performance-sensitive parts of the pipeline scale directly with that count:
a year-ahead pricing run prices every listing x every night, so at full scale
that's tens of millions of `calendar_days` rows, and each market's
RandomForest retrain, the review-theme pass, and every paginated frontend
page load all get slower too.

For fast local development and demoing, load a **sample** instead: still
real, unmodified Inside Airbnb rows (not synthetic data), just fewer of
them per market, picked deterministically (`random_state=42`) so repeated
loads are stable.

**First time, or moving from a full load down to a sample** - use
`reset_and_reload_sample.py`. Re-running `insideairbnb_loader.py` alone with
`--sample-per-market` does **not** shrink an already-fully-loaded database:
existing rows are upserted by `source_listing_id`, so a resample only
touches rows that already exist and leaves everything else in place.
`reset_and_reload_sample.py` clears the old rows first, then reloads the
sample, retrains each market's pricing model on the smaller listing set (the
old `models/market_<id>.joblib` files were fit on the old rows), and
regenerates a year of calendar pricing:

```powershell
$env:DATABASE_URL = "postgresql://<user>:<password>@localhost:5432/airbnb_lite"
python reset_and_reload_sample.py --data-dir . --sample-per-market 500

# One market only:
python reset_and_reload_sample.py --data-dir . --sample-per-market 500 --market Bangkok

# Skip the pricing run (do it later, or with a shorter horizon):
python reset_and_reload_sample.py --data-dir . --sample-per-market 500 --skip-pricing-run
```

The seeded demo accounts (`host@airbnblite.demo`, `positivehost@airbnblite.demo`,
`negativehost@airbnblite.demo`) keep working after a resample - their real
host_ids are pinned in `insideairbnb_loader.PINNED_HOST_IDS`, so the random
draw always keeps at least one listing per demo host.

Run these commands from the project root:

```powershell
# Import or refresh listing metadata without reading review text
python insideairbnb_loader.py --data-dir . --listings-only

# Refresh up to three recent real review excerpts per listing
# without rerunning the expensive theme analysis
python insideairbnb_loader.py --data-dir . --excerpts-only

# Refresh listings, review excerpts, and summarized review insights
python insideairbnb_loader.py --data-dir .

# Demo-scale load/refresh instead of the full archive (see reset_and_reload_sample.py
# above if a full archive is already loaded and you want to shrink it)
python insideairbnb_loader.py --data-dir . --sample-per-market 500
```

To process one market instead of all ten:

```powershell
python insideairbnb_loader.py --market Bangkok --data-dir . --listings-only
python insideairbnb_loader.py --market Bangkok --data-dir . --excerpts-only
```

The loader:

- stores the original archive listing ID as `source_listing_id`;
- updates existing archive-backed rows instead of duplicating them;
- derives `num_reviews` by counting matching review rows;
- stores listing names, descriptions, host metadata, amenities, house rules,
  photos, stay limits, booking flags, and review subscores when available;
- stores bounded guest-facing excerpts in `review_excerpts`;
- generates host-facing review themes in `review_insights`;
- with `--sample-per-market`, always keeps any listing whose `host_id` is in
  `PINNED_HOST_IDS` (the seeded demo accounts), regardless of the random draw.

Some values are derived because the archives do not provide them directly:
`bathrooms` falls back to a bedroom-based approximation, and market center
distance is calculated from listing coordinates. Missing archive values remain
unavailable rather than being replaced with fictional data.

Review theme analysis is substantially slower than listing import. Prefer
`--excerpts-only` when the guest UI needs refreshed excerpts but host insights
do not need to be recalculated.

## Start the application

Start the FastAPI service (with `.env` set up per above, `DATABASE_URL` no
longer needs to be exported here each time):

```powershell
uvicorn main:app --reload
```

The API runs at `http://localhost:8000`; interactive API documentation is at
`http://localhost:8000/docs`.

In another terminal, start Next.js (it reads `NEXT_PUBLIC_API_URL` from
`.env.local` on its own):

```powershell
npm run dev
```

The frontend runs at `http://localhost:3000`.

For a production frontend build:

```powershell
npm run build
npm start
```

## Frontend behavior

The Next.js app uses real API data for:

- market and listing search;
- listing names, descriptions, location, property type, amenities, house
  rules, photos, stay limits, booking flags, and review counts;
- real review excerpts from `reviews*.csv.gz`;
- summarized host review insights;
- calendar prices and market comparison data;
- authenticated host listing management and guest bookings.

If an archive does not contain a field, the UI shows an unavailable state
instead of inventing a value.

## API endpoints used by the frontend

- `GET /markets`
- `GET /listings?market_id=<id>`
- `GET /listings/{id}`
- `GET /listings/{id}/reviews?limit=3`
- `GET /listings/{id}/review-insights`
- `GET /listings/{id}/market-comparison`
- `GET /listings/{id}/calendar`
- `POST /bookings`
- Authenticated host pricing and approval endpoints under `/pricing` and
  `/listings/{id}/price-year`

Guest search requests 24 listings at a time by default. The API supports
`limit` values from 1 to 100 plus an `offset` for pagination, so the browser
does not download an entire market before rendering the first page.

## Pricing engine

`pricing_model.py` trains one model per market using the imported listing
features and local currency. `pricing_engine.py` applies event, news, and
seasonality modifiers, then enforces host-configured floor/ceiling and
night-over-night change guardrails. Hosts approve, override, or reject
recommendations through the Next.js host console.

Optional event/news integrations use `PREDICTHQ_API_KEY` and `NEWSAPI_KEY`
(set them in `.env` - see "Environment variables" above). Without those keys,
the pricing engine uses its configured deterministic fallback signals; this
does not change the listing or review source. Each market/date's signal
lookup is cached in `external_signal_cache` so it isn't re-fetched on every
pricing run; adding a key after some dates are already cached still works -
`_cache_is_stale()` in `pricing_engine.py` detects that a cached row predates
the key and refetches it for real instead of reusing the old synthetic
value.

## Data and secrets

Do not commit:

- `.env` or `.env.local` files (`.env.example`, the no-secrets template, is
  the one file in this family that IS meant to be committed);
- PostgreSQL passwords;
- `listings*.csv.gz` or `reviews*.csv.gz`;
- `airbnb_lite.db`;
- `node_modules`, `.next`, `__pycache__`, or generated model artifacts.

PostgreSQL is the runtime source of truth. The SQLite file is not required for
the current application workflow.

## Validation

```powershell
python -m py_compile db.py insideairbnb_loader.py main.py reset_and_reload_sample.py
npm run build
```

The database is expected to hold a real-data sample rather than the full
archives after running `reset_and_reload_sample.py` - by default 500 listings
per market (~5,000 total) instead of the full 279,724. Counts change with
whatever `--sample-per-market` value you choose, or after a full (non-sampled)
`insideairbnb_loader.py` run.
