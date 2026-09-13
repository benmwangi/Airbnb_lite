"""
One-shot reset: replaces whatever is currently loaded (e.g. a full
279,724-listing Inside Airbnb archive import) with a fast, deterministic
REAL-DATA SAMPLE, then rebuilds everything downstream of the listing set so
nothing is left stale.

Why this exists: run_pricing_cycle() prices every listing x days_ahead
nights. At full-archive scale (hundreds of thousands of listings) that's
tens of millions of calendar_days rows, and the per-market RandomForest
retrain, review-theme pass, and every frontend page load scale with it too.
insideairbnb_loader.py already supports --sample-per-market for exactly
this - it's still real Inside Airbnb data, just fewer rows - but simply
re-running it does not shrink a database that was already fully loaded:
existing rows are upserted by source_listing_id, so a resample only touches
rows that happen to already exist and leaves the rest in place. This script
actually clears the old rows first.

Steps:
  1. Delete review_insights, review_excerpts, calendar_days, and listings
     for the selected market(s) - children before parents, since none of
     these foreign keys cascade in db.py.
  2. Reload listings + reviews via insideairbnb_loader.load_market with
     --sample-per-market. Real host_ids backing the seeded demo accounts
     are pinned automatically (see PINNED_HOST_IDS in
     insideairbnb_loader.py), so host@airbnblite.demo,
     positivehost@airbnblite.demo, and negativehost@airbnblite.demo keep
     working after the resample.
  3. Retrain each market's pricing model (models/market_<id>.joblib) on the
     new, smaller listing set - the old joblib files were fit on the old
     rows and are stale the moment the listing set changes.
  4. Regenerate calendar pricing (recommended/live prices) for the new
     listings, --days-ahead nights ahead.

market_comparisons and external_signal_cache are left untouched: neither
depends on which listings are loaded (comparisons come from the full
external Inside Airbnb CSV per market via comparison_loader.py; the signal
cache is keyed by market + date, not by listing).

Usage (run from the project root, same as insideairbnb_loader.py):
    $env:DATABASE_URL = "postgresql://<user>:<password>@localhost:5432/airbnb_lite"
    python reset_and_reload_sample.py --data-dir . --sample-per-market 500

    # One market only:
    python reset_and_reload_sample.py --data-dir . --sample-per-market 500 --market Bangkok

    # Skip the pricing run (do it later / separately):
    python reset_and_reload_sample.py --data-dir . --sample-per-market 500 --skip-pricing-run
"""
import argparse
import os
import time

from sqlalchemy import func

from db import init_db, get_session, engine, Market, Listing, CalendarDay, ReviewExcerpt, ReviewInsight
from insideairbnb_loader import MARKETS, LOCAL_LISTING_FILES, LOCAL_REVIEW_FILES, load_market, ensure_markets
from pricing_model import train_all_markets
from pricing_engine import run_pricing_cycle


def reset_market_data(session, market_id: int) -> int:
    """Deletes review_insights, review_excerpts, calendar_days, and listings
    for one market, children before parents (same bulk-delete style already
    used inside insideairbnb_loader.load_market for per-market reloads).
    Returns how many listings were removed."""
    listing_ids = [
        row[0] for row in session.query(Listing.id).filter(Listing.market_id == market_id)
    ]
    if not listing_ids:
        return 0
    session.query(ReviewInsight).filter(ReviewInsight.listing_id.in_(listing_ids)).delete(synchronize_session=False)
    session.query(ReviewExcerpt).filter(ReviewExcerpt.listing_id.in_(listing_ids)).delete(synchronize_session=False)
    session.query(CalendarDay).filter(CalendarDay.listing_id.in_(listing_ids)).delete(synchronize_session=False)
    removed = session.query(Listing).filter(Listing.market_id == market_id).delete(synchronize_session=False)
    session.commit()
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=".", help="Folder with the local listings*.csv.gz / reviews*.csv.gz archives")
    parser.add_argument("--sample-per-market", type=int, default=500, help="Real listings to keep per market (default: 500)")
    parser.add_argument("--market", choices=list(MARKETS), help="Reset/reload only this one market instead of all 10")
    parser.add_argument("--skip-pricing-run", action="store_true",
                         help="Skip regenerating calendar pricing (faster; run `python pricing_engine.py` yourself later)")
    parser.add_argument("--days-ahead", type=int, default=365,
                         help="Nights to price per listing after reload (default: 365, matches MAX_HOST_CALENDAR_DAYS in main.py)")
    args = parser.parse_args()

    if engine.dialect.name != "postgresql":
        print("WARNING: DATABASE_URL is not set to a postgresql:// URL, so this will run "
              "against SQLite instead. Set DATABASE_URL first if that's not what you want.\n")

    init_db()
    session = get_session()
    markets = {args.market: MARKETS[args.market]} if args.market else MARKETS

    t0 = time.monotonic()
    created = ensure_markets(session, markets.keys())
    if created:
        print(f"Step 0/4: created Market row(s) for: {', '.join(created)} (brand-new database - "
              f"nothing to reset for these yet)")

    print("Step 1/4: clearing previously-loaded listings (and their reviews/calendar rows)...")
    for name in markets:
        market = session.query(Market).filter_by(name=name).first()
        removed = reset_market_data(session, market.id)
        print(f"  {name}: removed {removed} listings")

    print(f"\nStep 2/4: reloading a {args.sample_per_market}-per-market real-data sample...")
    for name, snapshot_path in markets.items():
        listing_path = os.path.join(args.data_dir, LOCAL_LISTING_FILES[name])
        review_path = os.path.join(args.data_dir, LOCAL_REVIEW_FILES[name])
        if not os.path.exists(listing_path) or not os.path.exists(review_path):
            print(f"  {name}: skipped - missing {listing_path} or {review_path}")
            continue
        added, insights, available = load_market(
            session, name, snapshot_path, listing_path, review_path,
            load_reviews=True, sample_per_market=args.sample_per_market,
        )
        print(f"  {name}: loaded {added} of {available} candidate listings; created {insights} review insights")

    for market in session.query(Market).all():
        market.listing_count = session.query(
            func.count(func.distinct(Listing.picture_url))
        ).filter(
            Listing.market_id == market.id,
            Listing.picture_url.isnot(None),
            Listing.picture_url != "",
        ).scalar() or 0
    session.commit()
    session.close()
    print(f"\nReload done in {time.monotonic() - t0:.1f}s.")

    print("\nStep 3/4: retraining pricing models on the new listing set...")
    train_all_markets()

    if args.skip_pricing_run:
        print("\nStep 4/4: skipped (--skip-pricing-run). Run `python pricing_engine.py` when you're ready.")
    else:
        print(f"\nStep 4/4: generating {args.days_ahead} days of calendar pricing for the new listings...")
        run_pricing_cycle(days_ahead=args.days_ahead)

    print(f"\nAll done in {time.monotonic() - t0:.1f}s total.")
    print("Demo accounts (host@airbnblite.demo, positivehost@airbnblite.demo, negativehost@airbnblite.demo) "
          "still work - their host_ids are pinned in insideairbnb_loader.PINNED_HOST_IDS, so the resample "
          "always keeps at least one listing per demo host.")


if __name__ == "__main__":
    main()
