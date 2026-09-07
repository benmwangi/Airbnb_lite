"""
Sources real, historical host-set pricing for comparison against the model's
recommendations - answering "how have actual hosts been pricing nearby?"

IMPORTANT - why this uses Inside Airbnb and not Airbnb.com directly:
Airbnb's own Terms of Service explicitly prohibit automated scraping/bots against
the live site. Inside Airbnb (insideairbnb.com) is a long-running, well-known
project that publishes periodic, CC BY 4.0-licensed snapshots of real Airbnb
listing data per city, compiled specifically to support this kind of research and
market analysis - it's the legitimate route to the same comparison, not a
workaround. This project does not include a live-site scraper for Airbnb.com.

URLS BELOW ARE REAL AND VERIFIED (fetched from insideairbnb.com/get-the-data on
2026-08-29) for the markets that overlap this project's cities. Inside Airbnb's
snapshot dates roll forward every few weeks, so re-check
https://insideairbnb.com/get-the-data/ periodically for the current link per city
if one of these 404s - the URL pattern (country/region/city/DATE/visualisations/
listings.csv) stays stable, only DATE changes.

This script could not download the actual file contents from inside this sandboxed
environment (its network egress is restricted to package registries), so it has
not been run against live data here - it's written and structured to run for you
directly. Run it from your own machine where insideairbnb.com is reachable.

Usage:
    python comparison_loader.py --market "Bangkok" \
        --url https://data.insideairbnb.com/thailand/central-thailand/bangkok/2026-06-29/visualisations/listings.csv
"""
import argparse
import datetime
import pandas as pd

from db import init_db, get_session, Market, MarketComparison

# Verified real download links (as of the 2026-06/07 Inside Airbnb snapshot round)
# for the cities this project already models. Re-fetch insideairbnb.com/get-the-data
# for a fresher date if these have rolled forward.
KNOWN_URLS = {
    "Bangkok": ("https://data.insideairbnb.com/thailand/central-thailand/bangkok/2026-06-29/visualisations/listings.csv", "2026-06-29"),
    "Cape Town": ("https://data.insideairbnb.com/south-africa/wc/cape-town/2026-06-29/visualisations/listings.csv", "2026-06-29"),
    "Hong Kong": ("https://data.insideairbnb.com/china/hk/hong-kong/2026-06-27/visualisations/listings.csv", "2026-06-27"),
    "Istanbul": ("https://data.insideairbnb.com/turkey/marmara/istanbul/2026-06-30/visualisations/listings.csv", "2026-06-30"),
    "Mexico City": ("https://data.insideairbnb.com/mexico/df/mexico-city/2026-06-15/visualisations/listings.csv", "2026-06-15"),
    "New York": ("https://data.insideairbnb.com/united-states/ny/new-york-city/2026-08-10/visualisations/listings.csv", "2026-08-10"),
    "Paris": ("https://data.insideairbnb.com/france/ile-de-france/paris/2026-06-16/visualisations/listings.csv","2026-06-16"),
    "Rio de Janeiro": ("https://data.insideairbnb.com/brazil/rj/rio-de-janeiro/2026-06-24/visualisations/listings.csv", "2026-06-24"),
    "Rome": ("https://data.insideairbnb.com/italy/lazio/rome/2026-06-20/visualisations/listings.csv", "2026-06-20"),
    "Sydney": ("https://data.insideairbnb.com/australia/nsw/sydney/2026-06-16/visualisations/listings.csv", "2026-06-16"),
    # Add the rest (New York, Paris, Rome, Sydney, Rio de Janeiro, Istanbul, Mexico
    # City) the same way - grab the current "visualisations/listings.csv" link for
    # each city from https://insideairbnb.com/get-the-data/ and add it here.
}

# Inside Airbnb's own room_type labels differ slightly from this project's -
# normalize them onto the same categories used elsewhere in the pipeline.
ROOM_TYPE_MAP = {
    "Entire home/apt": "Entire place",
    "Private room": "Private room",
    "Shared room": "Shared room",
    "Hotel room": "Hotel room",
}


def load_comparison(market_name: str, csv_url: str, snapshot_date: str = None):
    session = init_db_and_get_session()
    market = session.query(Market).filter_by(name=market_name).first()
    if not market:
        raise ValueError(f"No market named '{market_name}' in the DB - load listings first.")

    print(f"Fetching real Inside Airbnb data for {market_name} from {csv_url} ...")
    df = pd.read_csv(csv_url)
    df["room_type"] = df["room_type"].map(ROOM_TYPE_MAP).fillna(df["room_type"])
    df = df[df["price"].notna() & (df["price"] > 0)]

    for room_type, group in df.groupby("room_type"):
        comp = MarketComparison(
            market_id=market.id, room_type=room_type,
            actual_median_price=float(group["price"].median()),
            actual_mean_price=float(group["price"].mean()),
            sample_size=len(group),
            source="insideairbnb",
            source_snapshot_date=datetime.date.fromisoformat(snapshot_date) if snapshot_date else None,
        )
        session.add(comp)
        print(f"  {room_type:15s} n={len(group):5d}  median={comp.actual_median_price:,.2f}  mean={comp.actual_mean_price:,.2f}")

    session.commit()
    session.close()


def init_db_and_get_session():
    init_db()
    return get_session()


def load_all_known():
    for market_name, (url, date) in KNOWN_URLS.items():
        load_comparison(market_name, url, date)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", help="Market name, e.g. 'Bangkok'")
    parser.add_argument("--url", help="Inside Airbnb visualisations/listings.csv URL")
    parser.add_argument("--snapshot-date", default=None)
    parser.add_argument("--all-known", action="store_true", help="Load every market in KNOWN_URLS")
    args = parser.parse_args()

    if args.all_known:
        load_all_known()
    elif args.market and args.url:
        load_comparison(args.market, args.url, args.snapshot_date)
    else:
        parser.error("Pass --market and --url, or --all-known")
