"""
Seeds markets + listings.

IMPORTANT: The real Maven Analytics "Airbnb Listings & Reviews" CSVs (listings.csv,
reviews.csv) are not present in this environment - they live wherever you originally
downloaded them. This script generates realistic PER-MARKET synthetic listings,
calibrated to the same cities and roughly the same price/room-type/currency patterns
as the real dataset, so the pipeline is demonstrably real end to end.

TO USE YOUR REAL DATA INSTEAD:
Replace the body of `generate_market_listings()` with a load of your actual
listings.csv, filtered to `city == market.name`, mapped onto the Listing columns
below. Everything downstream (per-market model training, pricing engine, API,
dashboard) works unchanged either way - it only cares about the Listing table.
"""
import random
import numpy as np
from db import init_db, get_session, Market, Listing

random.seed(42)
np.random.seed(42)

# Cities present in the real Maven Airbnb dataset, with approximate real-world
# nightly-rate ranges and currencies used for calibration.
MARKETS = [
    {"name": "New York", "country": "United States", "currency": "USD",
     "center_lat": 40.7128, "center_lng": -74.0060, "price_base": 175, "price_spread": 90},
    {"name": "Paris", "country": "France", "currency": "EUR",
     "center_lat": 48.8566, "center_lng": 2.3522, "price_base": 130, "price_spread": 70},
    {"name": "Rome", "country": "Italy", "currency": "EUR",
     "center_lat": 41.9028, "center_lng": 12.4964, "price_base": 105, "price_spread": 55},
    {"name": "Sydney", "country": "Australia", "currency": "AUD",
     "center_lat": -33.8688, "center_lng": 151.2093, "price_base": 190, "price_spread": 100},
    {"name": "Amsterdam", "country": "Netherlands", "currency": "EUR",
     "center_lat": 52.3676, "center_lng": 4.9041, "price_base": 150, "price_spread": 75},
]

ROOM_TYPES = ["Entire home/apt", "Private room", "Shared room"]
ROOM_TYPE_WEIGHTS = [0.62, 0.34, 0.04]
ROOM_TYPE_MULTIPLIER = {"Entire home/apt": 1.35, "Private room": 0.75, "Shared room": 0.45}

LISTINGS_PER_MARKET = 60


def haversine_km(lat1, lng1, lat2, lng2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def generate_market_listings(market_row, market_id):
    rows = []
    for i in range(LISTINGS_PER_MARKET):
        # scatter listings within ~8km of the market center
        lat = market_row["center_lat"] + np.random.uniform(-0.08, 0.08)
        lng = market_row["center_lng"] + np.random.uniform(-0.08, 0.08)
        dist = haversine_km(market_row["center_lat"], market_row["center_lng"], lat, lng)

        room_type = np.random.choice(ROOM_TYPES, p=ROOM_TYPE_WEIGHTS)
        accommodates = int(np.clip(np.random.poisson(3) + 1, 1, 10))
        bedrooms = max(1.0, round(accommodates / 2))
        bathrooms = max(1.0, round(bedrooms * np.random.choice([1.0, 1.0, 1.5])))
        superhost = np.random.rand() < 0.22
        review_score = float(np.clip(np.random.normal(4.6, 0.35), 2.5, 5.0))
        num_reviews = int(np.clip(np.random.exponential(40), 0, 400))

        # price driven by realistic structural relationships, not randomness alone
        size_factor = 0.55 + 0.15 * accommodates
        location_factor = max(0.7, 1.25 - dist / 20)
        quality_factor = 0.9 + (review_score - 4.0) * 0.08 + (0.05 if superhost else 0)
        room_factor = ROOM_TYPE_MULTIPLIER[room_type]

        price = (market_row["price_base"] * size_factor * location_factor
                 * quality_factor * room_factor / 2.0)
        price += np.random.normal(0, market_row["price_spread"] * 0.12)
        price = round(max(20, price), 2)

        rows.append(Listing(
            market_id=market_id,
            host_id=1000 + i,
            room_type=room_type,
            accommodates=accommodates,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            latitude=lat,
            longitude=lng,
            dist_to_center_km=round(dist, 2),
            host_is_superhost=bool(superhost),
            review_scores_rating=round(review_score, 2),
            num_reviews=num_reviews,
            price=price,
            min_floor=round(price * 0.65, 2),
            max_ceiling=round(price * 1.8, 2),
            aggressiveness=round(np.random.uniform(0.3, 0.7), 2),
            auto_apply=False,
        ))
    return rows


def seed():
    init_db()
    session = get_session()

    if session.query(Market).count() > 0:
        print("Already seeded - skipping. Delete airbnb_lite.db to reseed.")
        return

    for m in MARKETS:
        market = Market(
            name=m["name"], country=m["country"], currency=m["currency"],
            center_lat=m["center_lat"], center_lng=m["center_lng"],
        )
        session.add(market)
        session.flush()  # get market.id

        listings = generate_market_listings(m, market.id)
        session.add_all(listings)
        print(f"Seeded {len(listings)} listings for {m['name']} ({m['currency']})")

    session.commit()
    session.close()
    print("Done.")


if __name__ == "__main__":
    seed()
