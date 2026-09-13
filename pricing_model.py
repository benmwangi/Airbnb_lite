"""
Per-market structural base price model.

One model is trained PER MARKET. Each model only ever sees listings from
its own currency and local price distribution, so predictions are directly
usable as that market's price basis - no cross-market leakage possible.

Feature columns are computed PER MARKET and saved alongside each model, because
real-world room_type categories differ by city (e.g. "Hotel room" appears in
some cities and not others) - a fixed global column list would silently break.
"""
import os
from functools import lru_cache
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

from db import get_session, Listing, Market

MODEL_DIR = "models"
BASE_NUMERIC_COLUMNS = [
    "accommodates", "bedrooms", "bathrooms", "dist_to_center_km",
    "host_is_superhost", "review_scores_rating", "num_reviews",
]


def _listing_frame(session, market_id):
    rows = session.query(Listing).filter(
        Listing.market_id == market_id, Listing.price.isnot(None), Listing.price > 0,
    ).all()
    df = pd.DataFrame([{
        "accommodates": r.accommodates, "bedrooms": r.bedrooms, "bathrooms": r.bathrooms,
        "dist_to_center_km": r.dist_to_center_km, "host_is_superhost": int(r.host_is_superhost),
        "review_scores_rating": r.review_scores_rating, "num_reviews": r.num_reviews,
        "room_type": r.room_type, "price": r.price, "listing_id": r.id,
    } for r in rows])
    if df.empty:
        # No priced listings for this market yet (e.g. a --sample-per-market load whose
        # candidate pool came up empty - see diagnose_review_mapping.py). pd.DataFrame([])
        # has no columns at all, so get_dummies(columns=["room_type"]) below would raise
        # KeyError on an empty frame. Return as-is; train_all_markets()'s own
        # `len(df) < 10` check already skips a market with too few rows to train on.
        return df
    df = pd.get_dummies(df, columns=["room_type"], prefix="room_type")
    return df


def train_all_markets():
    os.makedirs(MODEL_DIR, exist_ok=True)
    session = get_session()
    markets = session.query(Market).all()
    results = {}

    for market in markets:
        df = _listing_frame(session, market.id)
        if len(df) < 10:
            print(f"Skipping {market.name}: not enough priced listings ({len(df)})")
            continue

        # Real-world Airbnb prices have extreme outliers within a single market (a
        # handful of listings at 100-1000x the median) - clip to the 1st-99th
        # percentile before training, or a few outliers dominate the loss and the
        # model stops fitting the bulk of ordinary listings. This is the fix for
        # the "no outlier handling" issue flagged against the original notebook.
        lo, hi = df["price"].quantile([0.01, 0.99])
        df = df[(df["price"] >= lo) & (df["price"] <= hi)].copy()

        dummy_cols = sorted(c for c in df.columns if c.startswith("room_type_"))
        feature_columns = BASE_NUMERIC_COLUMNS + dummy_cols

        X = df[feature_columns]
        # train on log1p(price): price is right-skewed within every market, and a
        # log target keeps a $2,000/night outlier from dragging the fit around the
        # way a raw-price MAE loss would.
        y_log = np.log1p(df["price"])
        X_train, X_test, y_train_log, y_test_log = train_test_split(X, y_log, test_size=0.2, random_state=42)

        model = RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
        model.fit(X_train, y_train_log)

        preds = np.expm1(model.predict(X_test))
        y_test = np.expm1(y_test_log)
        mae = mean_absolute_error(y_test, preds)
        r2 = r2_score(y_test, preds)

        joblib.dump({"model": model, "columns": feature_columns},
                    os.path.join(MODEL_DIR, f"market_{market.id}.joblib"))
        results[market.name] = {"mae": round(mae, 2), "r2": round(r2, 3), "n": len(df), "currency": market.currency}
        print(f"{market.name:15s} ({market.currency}): MAE={mae:9.2f}  R2={r2:.3f}  n={len(df)}")

    session.close()
    return results


@lru_cache(maxsize=None)
def load_market_model(market_id):
    """Cached per process - a pricing run over thousands of listings in the same
    market would otherwise re-read the same joblib file from disk on every call."""
    path = os.path.join(MODEL_DIR, f"market_{market_id}.joblib")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No trained model for market {market_id}. Run train_all_markets() first.")
    return joblib.load(path)


def predict_base_price(listing) -> float:
    bundle = load_market_model(listing.market_id)
    model, feature_columns = bundle["model"], bundle["columns"]

    row = pd.DataFrame([{
        "accommodates": listing.accommodates, "bedrooms": listing.bedrooms, "bathrooms": listing.bathrooms,
        "dist_to_center_km": listing.dist_to_center_km, "host_is_superhost": int(listing.host_is_superhost),
        "review_scores_rating": listing.review_scores_rating, "num_reviews": listing.num_reviews,
        "room_type": listing.room_type,
    }])
    row = pd.get_dummies(row, columns=["room_type"], prefix="room_type")
    for col in feature_columns:
        if col not in row.columns:
            row[col] = 0
    log_pred = model.predict(row[feature_columns])[0]
    return float(np.expm1(log_pred))


if __name__ == "__main__":
    train_all_markets()
