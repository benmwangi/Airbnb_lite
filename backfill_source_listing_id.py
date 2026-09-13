"""
Backfills source_listing_id on listings that were loaded before that column
existed. Needed to enable review-insights (which requires joining back to a
real Inside Airbnb reviews export by listing_id).

How it works: matches existing rows against the local Inside Airbnb listing
archive by source listing ID.
used (same random_state, same per-city groupby order), then pairs each
resampled row with an existing DB listing in the same market, matched by
insertion order. Every pairing is VALIDATED before being trusted - it compares
accommodates, room_type, and price, and only backfills when they match. This
is a best-effort reconstruction, not a guaranteed one: if your database was
loaded with a different --sample-per-market than you pass here, or listings.csv
has changed, pairings will fail validation and get skipped and reported,
rather than silently backfilling a wrong ID.

Usage:
    python backfill_source_listing_id.py --listings listings.csv --sample-per-market 400
(use the SAME --sample-per-market value you originally loaded with)
"""
import argparse
import pandas as pd
from sqlalchemy import text

from db import get_session, Market, Listing, engine

PRICE_TOLERANCE = 0.01  # allow tiny float rounding differences


def ensure_column_exists():
    """SQLAlchemy's create_all() only creates missing TABLES, not missing
    COLUMNS on tables that already exist - a database from before
    source_listing_id was added to the schema needs this run once."""
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE listings ADD COLUMN source_listing_id INTEGER"))
            conn.commit()
            print("Added source_listing_id column to listings table.")
        except Exception:
            pass  # already exists - fine, both SQLite and Postgres raise here identically enough to just ignore


def backfill(listings_path: str, sample_per_market: int, seed: int = 42):
    ensure_column_exists()
    print(f"Reading {listings_path} ...")
    listings = pd.read_csv(listings_path, encoding="ISO-8859-1", low_memory=False)
    listings = listings[listings["price"].notna() & (listings["price"] > 0)].copy()

    session = get_session()
    total_matched, total_skipped = 0, 0

    for city, city_df in listings.groupby("city"):
        market = session.query(Market).filter_by(name=city).first()
        if not market:
            continue  # this market isn't in the DB - nothing to backfill

        if len(city_df) > sample_per_market:
            city_df = city_df.sample(sample_per_market, random_state=seed)
        city_df = city_df.reset_index(drop=True)

        db_listings = (
            session.query(Listing)
            .filter_by(market_id=market.id)
            .order_by(Listing.id)
            .all()
        )

        if len(db_listings) != len(city_df):
            print(f"{city}: DB has {len(db_listings)} listings but resampling gives "
                  f"{len(city_df)} - sample-per-market probably doesn't match the "
                  f"original load. Skipping this market entirely.")
            total_skipped += len(db_listings)
            continue

        matched = 0
        for db_row, (_, csv_row) in zip(db_listings, city_df.iterrows()):
            same_room_type = db_row.room_type == str(csv_row["room_type"])
            same_accommodates = db_row.accommodates == int(csv_row["accommodates"])
            same_price = db_row.price is not None and abs(db_row.price - float(csv_row["price"])) < PRICE_TOLERANCE
            if same_room_type and same_accommodates and same_price:
                db_row.source_listing_id = int(csv_row["listing_id"])
                matched += 1
            else:
                total_skipped += 1

        session.commit()
        print(f"{city}: backfilled {matched} of {len(db_listings)} listings")
        total_matched += matched

    session.close()
    print(f"\nDone. {total_matched} listings backfilled, {total_skipped} could not be "
          f"confidently matched and were left as-is.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--listings", default="listings.csv")
    parser.add_argument("--sample-per-market", type=int, required=True,
                         help="Must match the --sample-per-market value you originally loaded with.")
    args = parser.parse_args()
    backfill(args.listings, args.sample_per_market)
