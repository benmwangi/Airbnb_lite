"""
One-time data-quality fix: floor/ceiling guardrails were originally set from
each listing's raw historical price at data-load time
(insideairbnb_loader.py),
but the per-market model's own prediction for that listing can differ
substantially given real-world R2 of ~0.18-0.48. When the model's prediction
falls outside the historical-price-based floor/ceiling, EVERY recommendation
gets clamped to one edge - discovered by pricing listing #423 for a full year
and finding 370/370 days clamped to the same flat floor price, which would
make the new year-calendar feature meaningless.

Fix: recompute floor/ceiling from the model's own predicted base price per
listing, so guardrails bound the recommendation the model actually produces.
"""
from db import init_db, get_session, Listing, Market
from pricing_model import predict_base_price

# Every other entry point (main.py's startup hook, insideairbnb_loader.py's
# main()) calls init_db() before querying, which runs the _ensure_column /
# _ensure_index migrations that bring an older local database up to the
# current schema. This script queries directly without that step, so it
# breaks on any database created before a column (e.g. Market.listing_count)
# or index was added to the models - hence calling it here too.
init_db()

session = get_session()
markets = session.query(Market).all()
fixed = 0

for market in markets:
    listings = session.query(Listing).filter_by(market_id=market.id).all()
    for listing in listings:
        base = predict_base_price(listing)
        listing.min_floor = round(base * 0.65, 2)
        listing.max_ceiling = round(base * 1.8, 2)
        fixed += 1
    session.commit()
    print(f"{market.name}: recomputed guardrails for {len(listings)} listings")

session.close()
print(f"Fixed {fixed} listings total.")
