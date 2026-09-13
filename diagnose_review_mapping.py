"""
Diagnostic for insideairbnb_loader.LOCAL_REVIEW_FILES: checks whether each
market's mapped reviews*.csv.gz archive actually contains reviews for that
market's listings.

Why this exists: a --sample-per-market load on 2026-09-11 showed Bangkok,
Cape Town, Hong Kong, Istanbul, Mexico City, and New York matching 60-95% of
their priced listings against a real review (as expected), while Paris, Rio
de Janeiro, Rome, and Sydney matched effectively 0%. A real Inside Airbnb
listing_id is globally unique - a correct listings/reviews pairing for a
whole city should match a large fraction of priced listings, and a WRONG
pairing should match approximately nothing (two different cities' id sets
don't meaningfully overlap by chance). A clean 0% for 4 of 10 markets while
the other 6 look normal points at those 4 reviews*.csv.gz files being
mismatched in LOCAL_REVIEW_FILES, not at a code bug.

Note this predates --sample-per-market: a FULL load (no --sample-per-market)
never filters on review presence, so it would silently import these 4
markets' listings with review_excerpts/review_insights effectively empty,
without ever surfacing as a hard error - the sampler's "has review" filter
is just what turned it into a visible 0-candidates symptom.

This script reads every listings*.csv.gz file's `id` column and every
reviews*.csv.gz file's `listing_id` column (only those two columns, to keep
it reasonably fast, but each archive is still decompressed and parsed in
full once), then reports, for each market x each review file, how many of
that market's real listing ids appear as a listing_id in that review file.

Run this locally (not through any bridge) - it reads on the order of 1.5GB
of archives, which is fast on local disk/CPU but slow to ship anywhere else.

Usage:
    python diagnose_review_mapping.py --data-dir .

    # Narrow to just the suspect markets/files to run faster:
    python diagnose_review_mapping.py --data-dir . \\
        --markets "Paris,Rio de Janeiro,Rome,Sydney" \\
        --review-files "reviews.csv.gz,reviews(1).csv.gz,reviews(2).csv.gz,reviews(3).csv.gz"
"""
import argparse
import os
import pandas as pd

from insideairbnb_loader import MARKETS, LOCAL_LISTING_FILES, LOCAL_REVIEW_FILES


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=".")
    parser.add_argument("--markets", default=None,
                         help="Comma-separated market names to check (default: all 10)")
    parser.add_argument("--review-files", default=None,
                         help="Comma-separated review archive filenames to check against "
                              "(default: every distinct file currently used in LOCAL_REVIEW_FILES)")
    args = parser.parse_args()

    markets = [m.strip() for m in args.markets.split(",")] if args.markets else list(MARKETS)
    review_files = (
        [f.strip() for f in args.review_files.split(",")]
        if args.review_files else sorted(set(LOCAL_REVIEW_FILES.values()))
    )

    print(f"Reading listing ids for {len(markets)} market(s)...")
    market_ids = {}
    for name in markets:
        path = os.path.join(args.data_dir, LOCAL_LISTING_FILES[name])
        ids = pd.read_csv(path, usecols=["id"])["id"].dropna().astype("int64")
        market_ids[name] = set(ids)
        print(f"  {name}: {len(market_ids[name])} listing ids from {LOCAL_LISTING_FILES[name]}")

    print(f"\nReading review listing_ids for {len(review_files)} review file(s) "
          f"(slow part - full decompress + parse of each file)...")
    review_ids = {}
    for filename in review_files:
        path = os.path.join(args.data_dir, filename)
        if not os.path.exists(path):
            print(f"  {filename}: MISSING - skipped")
            continue
        ids = pd.read_csv(path, usecols=["listing_id"])["listing_id"].dropna().astype("int64")
        review_ids[filename] = set(ids)
        print(f"  {filename}: {len(review_ids[filename])} distinct reviewed listing ids")

    print("\nMatch matrix (rows = market, columns = review file; value = how many of that "
          "market's real listing ids show up as a listing_id in that review file):")
    present_files = [f for f in review_files if f in review_ids]
    header = "market".ljust(20) + "".join(f.rjust(22) for f in present_files)
    print(header)
    best = {}
    for name in markets:
        row = []
        for filename in present_files:
            row.append(len(market_ids[name] & review_ids[filename]))
        print(name.ljust(20) + "".join(str(v).rjust(22) for v in row))
        if row:
            best_idx = max(range(len(row)), key=lambda i: row[i])
            best[name] = (present_files[best_idx], row[best_idx])

    print("\nBest match per market (compare against insideairbnb_loader.LOCAL_REVIEW_FILES):")
    for name in markets:
        current = LOCAL_REVIEW_FILES.get(name, "?")
        if name not in best:
            continue
        recommended, count = best[name]
        flag = "  <-- update LOCAL_REVIEW_FILES to this" if recommended != current else "  (matches current mapping - OK)"
        print(f"  {name}: currently -> {current}; best match -> {recommended} ({count} overlapping ids){flag}")


if __name__ == "__main__":
    main()
