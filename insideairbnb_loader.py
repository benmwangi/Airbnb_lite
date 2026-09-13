"""Load current Inside Airbnb listings and review insights into PostgreSQL."""
import argparse
import os
from math import atan2, cos, radians, sin, sqrt

import pandas as pd
from sqlalchemy import func, text

from db import Listing, Market, ReviewExcerpt, ReviewInsight, engine, get_session, init_db
from review_insights_loader import analyze_comments, clean_review_text


MARKETS = {
    "Bangkok": ("thailand/central-thailand/bangkok/2026-06-29"),
    "Cape Town": ("south-africa/wc/cape-town/2026-06-29"),
    "Hong Kong": ("china/hk/hong-kong/2026-06-27"),
    "Istanbul": ("turkey/marmara/istanbul/2026-06-30"),
    "Mexico City": ("mexico/df/mexico-city/2026-06-15"),
    "New York": ("united-states/ny/new-york-city/2026-06-14"),
    "Paris": ("france/ile-de-france/paris/2026-06-16"),
    "Rio de Janeiro": ("brazil/rj/rio-de-janeiro/2026-06-24"),
    "Rome": ("italy/lazio/rome/2026-06-20"),
    "Sydney": ("australia/nsw/sydney/2026-06-16"),
}
LOCAL_REVIEW_FILES = {
    # Paris/Rio de Janeiro/Rome/Sydney corrected 2026-09-11 by
    # diagnose_review_mapping.py: the previous mapping had these four files
    # in a cyclic swap (Paris<->Sydney via reviews.csv.gz/reviews(3).csv.gz,
    # Rio<->Rome via reviews(1).csv.gz/reviews(2).csv.gz) - each market
    # matched ~0 of its own listings against its assigned file's listing
    # ids. This mapping was verified by actual listing_id overlap (tens of
    # thousands of matches per market), not guessed.
    "Paris": "reviews(3).csv.gz",
    "Rio de Janeiro": "reviews(2).csv.gz",
    "Rome": "reviews(1).csv.gz",
    "Sydney": "reviews.csv.gz",
    "Bangkok": "reviews(9).csv.gz",
    "Cape Town": "reviews(8).csv.gz",
    "Hong Kong": "reviews(7).csv.gz",
    "Istanbul": "reviews(6).csv.gz",
    "Mexico City": "reviews(5).csv.gz",
    "New York": "reviews(4).csv.gz",
}
LOCAL_LISTING_FILES = {
    "Bangkok": "listings(1).csv.gz",
    "Cape Town": "listings(2).csv.gz",
    "Hong Kong": "listings(3).csv.gz",
    "Mexico City": "listings(4).csv.gz",
    "New York": "listings(5).csv.gz",
    "Paris": "listings(6).csv.gz",
    "Rio de Janeiro": "listings(7).csv.gz",
    "Rome": "listings(8).csv.gz",
    "Sydney": "listings(9).csv.gz",
    "Istanbul": "listings(10).csv.gz",
}
ROOM_TYPES = {
    "Entire home/apt": "Entire place",
    "Private room": "Private room",
    "Shared room": "Shared room",
    "Hotel room": "Hotel room",
}

# Real host_ids backing the seeded demo accounts (see seed_demo_accounts.py and
# seed_feedback_demo_accounts.py). A --sample-per-market draw is random, so
# without pinning these, a resample can silently empty a demo host's "My
# Listings" page. Every id here is a real Inside Airbnb host_id those seed
# scripts already use - nothing fabricated.
PINNED_HOST_IDS = {218745884, 344804377, 33174397}

# Country/currency/approximate city-center coordinates for each market - real
# geography and ISO currency data, not derived from the archives. Needed to
# CREATE each Market row: this loader only ever updates an existing market's
# listings (load_market below looks it up with .one() and errors if it's
# missing), it never creates one. A brand-new database - one that was never
# seeded via migrate_sqlite_to_postgres.py from an existing airbnb_lite.db -
# has no Market rows at all, so ensure_markets() below must run first.
MARKET_METADATA = {
    "Bangkok": ("Thailand", "THB", 13.7563, 100.5018),
    "Cape Town": ("South Africa", "ZAR", -33.9249, 18.4241),
    "Hong Kong": ("China", "HKD", 22.3193, 114.1694),
    "Istanbul": ("Turkey", "TRY", 41.0082, 28.9784),
    "Mexico City": ("Mexico", "MXN", 19.4326, -99.1332),
    "New York": ("United States", "USD", 40.7128, -74.0060),
    "Paris": ("France", "EUR", 48.8566, 2.3522),
    "Rio de Janeiro": ("Brazil", "BRL", -22.9068, -43.1729),
    "Rome": ("Italy", "EUR", 41.9028, 12.4964),
    "Sydney": ("Australia", "AUD", -33.8688, 151.2093),
}


def ensure_markets(session, market_names=None) -> list:
    """Creates any Market row from MARKET_METADATA that doesn't exist yet.
    Safe to call repeatedly and safe alongside an already-populated database:
    it only ever INSERTs a missing row, never touches one that already
    exists, so it can't clobber a listing_count or a center point a real
    load has since computed. Returns the list of market names it created."""
    names = market_names or MARKET_METADATA.keys()
    created = []
    for name in names:
        if session.query(Market).filter_by(name=name).first():
            continue
        country, currency, lat, lng = MARKET_METADATA[name]
        session.add(Market(
            name=name, country=country, currency=currency,
            center_lat=lat, center_lng=lng, listing_count=0,
        ))
        created.append(name)
    if created:
        session.commit()
    return created


def _url(path: str, kind: str) -> str:
    return f"https://data.insideairbnb.com/{path}/data/{kind}.csv.gz"


def _read_columns(source, columns):
    available = set(pd.read_csv(source, nrows=0).columns)
    selected = [column for column in columns if column in available]
    frame = pd.read_csv(source, usecols=selected, low_memory=False)
    for column in columns:
        if column not in frame:
            frame[column] = None
    return frame


def _distance(lat1, lng1, lat2, lng2):
    radius = 6371
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * radius * atan2(sqrt(a), sqrt(1 - a))


def load_market(
    session,
    market_name: str,
    snapshot_path: str,
    listings_source=None,
    reviews_source=None,
    load_reviews=True,
    sample_per_market=None,
):
    listings_url = listings_source or _url(snapshot_path, "listings")
    reviews_url = reviews_source or _url(snapshot_path, "reviews")
    columns = [
        "id", "name", "description", "host_id", "host_name", "host_since", "host_location",
        "room_type", "property_type", "neighbourhood", "accommodates", "bedrooms",
        "bathrooms", "latitude", "longitude", "price", "amenities", "house_rules",
        "picture_url", "minimum_nights", "maximum_nights", "instant_bookable",
        "host_is_superhost", "review_scores_rating", "review_scores_cleanliness",
        "review_scores_checkin", "review_scores_communication", "review_scores_location",
        "review_scores_value",
    ]
    listings = _read_columns(listings_url, columns)
    listings["source_listing_id"] = pd.to_numeric(listings["id"], errors="coerce")
    listings["host_since"] = pd.to_datetime(listings["host_since"], errors="coerce")
    listings["price"] = pd.to_numeric(
        listings["price"].astype(str).str.replace(r"[^0-9.-]", "", regex=True), errors="coerce"
    )
    listings = listings[listings["source_listing_id"].notna() & listings["price"].gt(0)].copy()

    # Computed here (rather than later, where it used to live) so it's
    # available for the demo quality filter below, and reused as-is for the
    # num_reviews column further down - no second pass over reviews_url.
    review_counts = _read_columns(reviews_url, ["listing_id"]).groupby("listing_id").size()

    # DEMO SAMPLING: cap how many real, priced listings get imported for this
    # market. This is a subset of the real archive, not synthetic data - the
    # untouched full archive stays on disk (or at its source URL) and can be
    # loaded later by re-running this loader for the same market without
    # --sample-per-market (existing rows are upserted by source_listing_id,
    # see the `existing` lookup below, so a later full load adds the rest
    # rather than duplicating what the demo already imported).
    # random_state=42 makes the sample deterministic: re-running with the
    # same --sample-per-market against an unchanged archive file picks the
    # same rows, so repeated demo loads stay stable rather than swapping in
    # a different random subset each time.
    if sample_per_market:
        # Pull out rows belonging to the pinned demo host_ids BEFORE the
        # photo/review quality filter and the random draw, from the full
        # priced pool - so a resample never drops the one thing the seed
        # scripts depend on (those host_ids owning at least one listing),
        # even if a pinned row happens to lack a photo or a review.
        pinned_mask = pd.to_numeric(listings["host_id"], errors="coerce").isin(PINNED_HOST_IDS)
        pinned = listings[pinned_mask].copy()

        # Demo listings should look complete in the UI: a real photo (guest
        # search already hides picture-less listings, but the host console
        # doesn't) and at least one real review (so review excerpts and
        # review-insight recommendations have something to show instead of
        # an empty state). This is a quality filter on the CANDIDATE pool
        # for sampling, not a general-purpose rule - a full load (no
        # --sample-per-market) still imports every priced listing regardless
        # of photo/review presence, same as before.
        has_photo = listings["picture_url"].notna() & (listings["picture_url"].astype(str).str.strip() != "")
        has_review = listings["source_listing_id"].isin(review_counts.index)
        qualifying = listings[has_photo & has_review]
        print(f"  {market_name}: {len(qualifying)} of {len(listings)} priced listings have "
              f"both a photo and at least one review (demo candidate pool).")
        if len(pinned):
            print(f"  {market_name}: {len(pinned)} listing(s) belong to pinned demo host_ids "
                  f"and will be kept regardless of the random draw.")
        listings = qualifying

    available_before_sample = len(listings)
    if sample_per_market and available_before_sample > sample_per_market:
        non_pinned_pool = (
            listings[~listings["source_listing_id"].isin(pinned["source_listing_id"])]
            if len(pinned) else listings
        )
        remaining_slots = max(sample_per_market - len(pinned), 0)
        sampled = (
            non_pinned_pool.sample(min(remaining_slots, len(non_pinned_pool)), random_state=42)
            if remaining_slots and len(non_pinned_pool) else non_pinned_pool.iloc[0:0]
        )
        listings = pd.concat([pinned, sampled]).drop_duplicates(subset="source_listing_id").reset_index(drop=True)
        print(f"  {market_name}: sampling {len(listings)} of {available_before_sample} "
              f"priced listings for the demo (seed=42) - rerun without --sample-per-market "
              f"later to load the rest.")
    elif sample_per_market and len(pinned):
        # Nothing needed trimming above, but a pinned listing might still be
        # missing if it didn't pass the photo/review filter - union it back
        # in rather than leaving that demo host's portfolio empty.
        missing_pinned = pinned[~pinned["source_listing_id"].isin(listings["source_listing_id"])]
        if len(missing_pinned):
            listings = pd.concat([listings, missing_pinned]).reset_index(drop=True)
            print(f"  {market_name}: added {len(missing_pinned)} pinned demo listing(s) that "
                  f"didn't pass the photo/review filter.")

    for column in ["latitude", "longitude", "bedrooms", "bathrooms", "accommodates", "review_scores_rating"]:
        listings[column] = pd.to_numeric(listings[column], errors="coerce")
    for column in ["minimum_nights", "maximum_nights"]:
        listings[column] = pd.to_numeric(listings[column], errors="coerce")
    for column in ["review_scores_cleanliness", "review_scores_checkin",
                   "review_scores_communication", "review_scores_location", "review_scores_value"]:
        listings[column] = pd.to_numeric(listings[column], errors="coerce")
    listings["bedrooms"] = listings["bedrooms"].fillna(1.0)
    listings["bathrooms"] = listings["bathrooms"].fillna(listings["bedrooms"].clip(lower=1.0)).fillna(1.0)
    listings["accommodates"] = listings["accommodates"].fillna(1).clip(lower=1).astype(int)
    listings["review_scores_rating"] = (listings["review_scores_rating"].fillna(0) * 20).clip(upper=100)
    listings["host_is_superhost"] = listings["host_is_superhost"].eq("t")
    listings = listings.dropna(subset=["latitude", "longitude"])

    listings["num_reviews"] = listings["source_listing_id"].map(review_counts).fillna(0).astype(int)
    market = session.query(Market).filter_by(name=market_name).one()
    center_lat, center_lng = listings["latitude"].median(), listings["longitude"].median()
    existing = {
        int(row.source_listing_id): row for row in session.query(Listing)
        .filter(Listing.market_id == market.id, Listing.source_listing_id.isnot(None)).all()
    }
    new_rows = []
    for row in listings.itertuples(index=False):
        source_id = int(row.source_listing_id)
        price = float(row.price)
        values = dict(
            market_id=market.id, source_listing_id=source_id,
            host_id=int(row.host_id) if pd.notna(row.host_id) else 0,
            host_name=str(row.host_name) if pd.notna(row.host_name) else None,
            # name/description/house_rules go through clean_review_text() -
            # these are the free-text fields that come with <br/> tags and
            # HTML-entity-encoded punctuation in the raw archive (see that
            # function's docstring). amenities is left alone: it's a
            # Postgres-array-literal-style string ("{Wifi,Kitchen,...}"),
            # not HTML, and AmenityGrid on the frontend already parses that
            # format directly.
            name=clean_review_text(row.name) if pd.notna(row.name) else None,
            description=clean_review_text(row.description) if pd.notna(row.description) else None,
            host_since=row.host_since.date() if pd.notna(row.host_since) else None,
            host_location=str(row.host_location) if pd.notna(row.host_location) else None,
            neighbourhood=str(row.neighbourhood) if pd.notna(row.neighbourhood) else None,
            property_type=str(row.property_type) if pd.notna(row.property_type) else None,
            amenities=str(row.amenities) if pd.notna(row.amenities) else None,
            house_rules=clean_review_text(row.house_rules) if pd.notna(row.house_rules) else None,
            picture_url=str(row.picture_url) if pd.notna(row.picture_url) else None,
            minimum_nights=int(row.minimum_nights) if pd.notna(row.minimum_nights) else None,
            maximum_nights=int(row.maximum_nights) if pd.notna(row.maximum_nights) else None,
            instant_bookable=str(row.instant_bookable).lower() in {"t", "true", "1"},
            review_scores_cleanliness=float(row.review_scores_cleanliness) if pd.notna(row.review_scores_cleanliness) else None,
            review_scores_checkin=float(row.review_scores_checkin) if pd.notna(row.review_scores_checkin) else None,
            review_scores_communication=float(row.review_scores_communication) if pd.notna(row.review_scores_communication) else None,
            review_scores_location=float(row.review_scores_location) if pd.notna(row.review_scores_location) else None,
            review_scores_value=float(row.review_scores_value) if pd.notna(row.review_scores_value) else None,
            room_type=ROOM_TYPES.get(str(row.room_type), str(row.room_type)),
            accommodates=int(row.accommodates), bedrooms=float(row.bedrooms),
            bathrooms=float(max(1, row.bathrooms)), latitude=float(row.latitude),
            longitude=float(row.longitude),
            dist_to_center_km=round(_distance(center_lat, center_lng, row.latitude, row.longitude), 2),
            host_is_superhost=bool(row.host_is_superhost),
            review_scores_rating=float(row.review_scores_rating), num_reviews=int(row.num_reviews),
            price=price, min_floor=max(10, round(price * 0.65, 2)),
            max_ceiling=round(price * 1.8, 2), aggressiveness=0.5, auto_apply=False,
        )
        if source_id in existing:
            for key, value in values.items():
                setattr(existing[source_id], key, value)
        else:
            new_rows.append(Listing(**values))
    session.add_all(new_rows)
    session.flush()
    by_source = {row.source_listing_id: row for row in new_rows}

    if not load_reviews:
        session.commit()
        return len(new_rows), 0, len(listings)

    reviews = _read_columns(reviews_url, ["listing_id", "date", "reviewer_name", "comments"])
    reviews = reviews[reviews["comments"].notna()]
    # Cleaned once here (see clean_review_text's docstring) so both the guest-
    # facing excerpts below AND analyze_comments (theme matching, its
    # "sample_review" and "specific_details" output) already work from
    # human-readable text - no raw <br/> tags or HTML entities left in either.
    reviews["comments"] = reviews["comments"].map(clean_review_text)
    # When sampling, don't run theme analysis (analyze_comments, below) over
    # review text for listings that weren't imported this run - restricting
    # to the sampled source_listing_ids first keeps demo loads fast even
    # though reviews.csv.gz itself is read in full.
    if sample_per_market:
        sampled_source_ids = set(listings["source_listing_id"].astype("int64"))
        reviews = reviews[reviews["listing_id"].isin(sampled_source_ids)]
    reviews["date"] = pd.to_datetime(reviews["date"], errors="coerce")
    session.query(ReviewInsight).filter(
        ReviewInsight.listing_id.in_(
            row[0] for row in session.query(Listing.id).filter(Listing.market_id == market.id)
        )
    ).delete(synchronize_session=False)
    session.query(ReviewExcerpt).filter(
        ReviewExcerpt.listing_id.in_(
            row[0] for row in session.query(Listing.id).filter(Listing.market_id == market.id)
        )
    ).delete(synchronize_session=False)
    insight_count = 0
    for source_id, group in reviews.groupby("listing_id"):
        listing = by_source.get(int(source_id))
        if listing is None:
            listing = session.query(Listing).filter_by(
                market_id=market.id, source_listing_id=int(source_id)
            ).first()
        if listing is None:
            continue
        for row in group.sort_values("date", ascending=False).head(3).itertuples(index=False):
            session.add(ReviewExcerpt(
                listing_id=listing.id,
                reviewer_name=str(row.reviewer_name) if pd.notna(row.reviewer_name) else None,
                review_date=row.date.date() if pd.notna(row.date) else None,
                comments=str(row.comments),
                source="insideairbnb",
            ))
        for result in analyze_comments(group["comments"].tolist()):
            session.add(ReviewInsight(listing_id=listing.id, source="insideairbnb", **result))
            insight_count += 1
    session.commit()
    return len(new_rows), insight_count, len(listings)


def load_local_reviews(session, reviews_dir: str, load_insights=True, market_names=None):
    """Refresh review insights from repository archives whose IDs match listings."""
    refreshed = []
    selected_markets = market_names or LOCAL_REVIEW_FILES.keys()
    for market_name in selected_markets:
        filename = LOCAL_REVIEW_FILES[market_name]
        path = os.path.join(reviews_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing local review archive: {path}")
        market = session.query(Market).filter_by(name=market_name).one()
        source_to_listing = {
            int(source_id): listing_id
            for source_id, listing_id in session.query(Listing.source_listing_id, Listing.id)
            .filter(Listing.market_id == market.id, Listing.source_listing_id.isnot(None))
            .all()
        }
        reviews = _read_columns(path, ["listing_id", "date", "reviewer_name", "comments"])
        reviews = reviews[reviews["comments"].notna()]
        # Cleaned once here (see clean_review_text's docstring) so both the
        # guest-facing excerpts below AND analyze_comments (theme matching,
        # its "sample_review"/"specific_details" output) already work from
        # human-readable text - no raw <br/> tags or HTML entities left in
        # either. Replaces the old ad-hoc ".replace('<br/>', ' ')", which only
        # handled that one literal tag spelling and never decoded entities.
        reviews["comments"] = reviews["comments"].map(clean_review_text)
        reviews["date"] = pd.to_datetime(reviews["date"], errors="coerce")
        if load_insights:
            session.query(ReviewInsight).filter(
                ReviewInsight.listing_id.in_(source_to_listing.values())
            ).delete(synchronize_session=False)
        session.query(ReviewExcerpt).filter(
            ReviewExcerpt.listing_id.in_(source_to_listing.values())
        ).delete(synchronize_session=False)
        count = 0
        excerpt_count = 0
        for source_id, group in reviews.groupby("listing_id"):
            listing_id = source_to_listing.get(int(source_id))
            if listing_id is None:
                continue
            excerpts = group.sort_values("date", ascending=False).head(3)
            for row in excerpts.itertuples(index=False):
                session.add(ReviewExcerpt(
                    listing_id=listing_id,
                    reviewer_name=str(row.reviewer_name) if pd.notna(row.reviewer_name) else None,
                    review_date=row.date.date() if pd.notna(row.date) else None,
                    comments=str(row.comments),
                    source="insideairbnb",
                ))
                excerpt_count += 1
            if load_insights:
                for result in analyze_comments(group["comments"].tolist()):
                    session.add(ReviewInsight(
                        listing_id=listing_id, source="insideairbnb", **result
                    ))
                    count += 1
        session.commit()
        refreshed.append((market_name, len(source_to_listing), excerpt_count if not load_insights else count))
    return refreshed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=list(MARKETS))
    parser.add_argument("--data-dir", help="Use repository listings*.csv.gz and reviews*.csv.gz archives")
    parser.add_argument("--listings-only", action="store_true", help="Import local listings without reprocessing reviews")
    parser.add_argument("--excerpts-only", action="store_true", help="Refresh guest-facing review excerpts without reprocessing insights")
    parser.add_argument(
        "--sample-per-market", type=int, default=None,
        help="Demo mode: only import up to this many real, priced listings per market "
             "(deterministic sample, seed=42) instead of the full archive. The rest of "
             "the archive is left on disk/at its source URL - rerun later without this "
             "flag (or with a larger number) to load more; existing listings are "
             "upserted by source_listing_id, so nothing gets duplicated.",
    )
    args = parser.parse_args()
    init_db()
    if engine.dialect.name == "postgresql":
        # These statements only make sense against Postgres: SQLite has no
        # ALTER COLUMN TYPE, no "IF NOT EXISTS" clause on ADD COLUMN, and no
        # pg_get_serial_sequence()/setval() (SQLite auto-tracks its next
        # rowid off whatever the highest existing id is, even after rows
        # were inserted with explicit ids, so there's no separate sequence
        # object to resync). On SQLite this whole block is also unnecessary
        # in the first place: init_db(), just above, already creates
        # listings.source_listing_id from the current model definition via
        # Base.metadata.create_all() on any table it creates from scratch -
        # this block exists only to patch existing Postgres databases that
        # predate that column/type.
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE listings ADD COLUMN IF NOT EXISTS source_listing_id BIGINT"))
            connection.execute(text("ALTER TABLE listings ALTER COLUMN source_listing_id TYPE BIGINT"))
            connection.execute(text("ALTER TABLE listings ALTER COLUMN host_id TYPE BIGINT"))
            connection.execute(text(
                "SELECT setval(pg_get_serial_sequence('listings', 'id'), "
                "COALESCE((SELECT MAX(id) FROM listings), 1), true)"
            ))
            connection.execute(text(
                "SELECT setval(pg_get_serial_sequence('review_insights', 'id'), "
                "COALESCE((SELECT MAX(id) FROM review_insights), 1), true)"
            ))
    session = get_session()
    markets = {args.market: MARKETS[args.market]} if args.market else MARKETS
    created = ensure_markets(session, markets.keys())
    if created:
        print(f"Created Market row(s) for: {', '.join(created)}")
    try:
        if args.data_dir and args.excerpts_only:
            refreshed = load_local_reviews(
                session, args.data_dir, load_insights=False, market_names=markets
            )
            for name, listings, excerpts in refreshed:
                print(f"{name}: matched {listings} listings; refreshed {excerpts} review excerpts")
            return
        if args.data_dir:
            for name, snapshot_path in markets.items():
                listing_path = os.path.join(args.data_dir, LOCAL_LISTING_FILES[name])
                review_path = os.path.join(args.data_dir, LOCAL_REVIEW_FILES[name])
                if not os.path.exists(listing_path) or not os.path.exists(review_path):
                    raise FileNotFoundError(f"Missing local data for {name}")
                added, insights, available = load_market(
                    session, name, snapshot_path, listing_path, review_path,
                    load_reviews=not args.listings_only,
                    sample_per_market=args.sample_per_market,
                )
                print(f"{name}: added {added} of {available} listings; created {insights} review insights")
            return
        for name, path in markets.items():
            added, insights, available = load_market(session, name, path, sample_per_market=args.sample_per_market)
            print(f"{name}: added {added} of {available} listings; created {insights} review insights")
    finally:
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


if __name__ == "__main__":
    main()
