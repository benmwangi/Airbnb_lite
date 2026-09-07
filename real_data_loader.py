"""
Loads the REAL Maven Analytics "Airbnb Listings & Reviews" dataset into the
same per-market schema seed_data.py builds synthetically. Run this instead of
seed_data.py - nothing else in the pipeline changes; pricing_model.py,
pricing_engine.py, main.py and dashboard.py all work unchanged either way,
since they only depend on the Listing/Market table shape.

Usage:
    python real_data_loader.py --listings /path/to/listings.csv \
                                --reviews /path/to/reviews.csv \
                                --sample-per-market 3000

Notes on this specific dataset:
  - `price` is documented as being in each listing's own country's currency -
    this is exactly why a per-market model is required, not optional. Mixing
    Bangkok (THB, thousands) with Paris (EUR, hundreds) in one global model
    would make the model mostly learn "which city", not real pricing signal.
  - The dataset has no `bathrooms` or `num_reviews` column. `num_reviews` is
    derived by counting rows per listing_id in reviews.csv. `bathrooms` isn't
    present at all, so it's approximated from `bedrooms` - flagged clearly
    below; treat it as a rough stand-in feature, not a real fact about the
    listing.
  - `review_scores_rating` is out of 100 here (vs. a 0-5 scale you might
    expect) - that's fine for the model (it's just a numeric feature learned
    per-market) but worth knowing if you inspect the numbers directly.
  - Rows with price <= 0 or missing are dropped - a $0/night listing is either
    a data error or an inactive listing, and would corrupt a price model.
"""
import argparse
from math import radians, sin, cos, sqrt, atan2
import numpy as np
import pandas as pd

from db import init_db, get_session, Market, Listing

# ISO currency per city, since the dataset doesn't include one directly.
CITY_CURRENCY = {
    "Paris": "EUR", "Rome": "EUR",
    "New York": "USD",
    "Sydney": "AUD",
    "Rio de Janeiro": "BRL",
    "Istanbul": "TRY",
    "Mexico City": "MXN",
    "Bangkok": "THB",
    "Cape Town": "ZAR",
    "Hong Kong": "HKD",
}


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def load(listings_path: str, reviews_path: str, sample_per_market: int = 3000, seed: int = 42):
    print(f"Reading {listings_path} ...")
    listings = pd.read_csv(listings_path, encoding="ISO-8859-1", low_memory=False)

    print(f"Reading {reviews_path} for review counts ...")
    review_counts = (
        pd.read_csv(reviews_path, usecols=["listing_id"])
        .groupby("listing_id").size().rename("num_reviews")
    )
    listings = listings.merge(review_counts, left_on="listing_id", right_index=True, how="left")
    listings["num_reviews"] = listings["num_reviews"].fillna(0).astype(int)

    # clean
    listings = listings[listings["price"].notna() & (listings["price"] > 0)].copy()
    listings["host_is_superhost"] = listings["host_is_superhost"].map({"t": True, "f": False}).fillna(False)
    listings["bedrooms"] = listings["bedrooms"].fillna(listings.groupby("city")["bedrooms"].transform("median"))
    listings["bedrooms"] = listings["bedrooms"].fillna(1.0)
    listings["review_scores_rating"] = listings["review_scores_rating"].fillna(
        listings.groupby("city")["review_scores_rating"].transform("mean")
    )
    listings["review_scores_rating"] = listings["review_scores_rating"].fillna(
        listings["review_scores_rating"].mean()
    )
    # bathrooms isn't in this dataset - approximate from bedrooms and flag it clearly
    listings["bathrooms_approx"] = np.maximum(1.0, np.round(listings["bedrooms"]))

    init_db()
    session = get_session()

    if session.query(Market).count() > 0:
        print("DB already has markets - delete airbnb_lite.db first if you want a clean reload.")
        return

    rng = np.random.default_rng(seed)

    for city, city_df in listings.groupby("city"):
        currency = CITY_CURRENCY.get(city)
        if currency is None:
            print(f"Skipping unrecognized city '{city}' (no currency mapping) - add it to CITY_CURRENCY.")
            continue

        center_lat, center_lng = city_df["latitude"].median(), city_df["longitude"].median()
        market = Market(name=city, country="", currency=currency, center_lat=center_lat, center_lng=center_lng)
        session.add(market)
        session.flush()

        if len(city_df) > sample_per_market:
            city_df = city_df.sample(sample_per_market, random_state=seed)

        rows = []
        for _, r in city_df.iterrows():
            dist = haversine_km(center_lat, center_lng, r["latitude"], r["longitude"])
            floor = max(10.0, round(r["price"] * 0.65, 2))
            ceiling = round(r["price"] * 1.8, 2)
            rows.append(Listing(
                market_id=market.id,
                host_id=int(r["host_id"]) if pd.notna(r["host_id"]) else 0,
                room_type=str(r["room_type"]),
                accommodates=int(r["accommodates"]) if pd.notna(r["accommodates"]) else 1,
                bedrooms=float(r["bedrooms"]),
                bathrooms=float(r["bathrooms_approx"]),
                latitude=float(r["latitude"]), longitude=float(r["longitude"]),
                dist_to_center_km=round(dist, 2),
                host_is_superhost=bool(r["host_is_superhost"]),
                review_scores_rating=float(r["review_scores_rating"]),
                num_reviews=int(r["num_reviews"]),
                price=float(r["price"]),
                min_floor=floor, max_ceiling=ceiling,
                aggressiveness=float(rng.uniform(0.3, 0.7)),
                auto_apply=False,
            ))
        session.add_all(rows)
        print(f"{city:15s} ({currency}): loaded {len(rows)} of {len(listings[listings['city'] == city])} listings")

    session.commit()
    session.close()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--listings", default="listings.csv")
    parser.add_argument("--reviews", default="reviews.csv")
    parser.add_argument("--sample-per-market", type=int, default=3000,
                         help="Cap listings per city for faster local training. Use a large number (e.g. 1000000) to load everything.")
    args = parser.parse_args()
    load(args.listings, args.reviews, args.sample_per_market)
