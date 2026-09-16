"""
Per-market structural base price model.

One model is trained PER MARKET, and PER MARKET the best-performing algorithm
is picked automatically by test-set R2 - see train_all_markets() below. Each
model only ever sees listings from its own currency and local price
distribution, so predictions are directly usable as that market's price basis
- no cross-market leakage possible.

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
from xgboost import XGBRegressor

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

        # Two candidates, trained on the SAME train/test split so their R2s are
        # directly comparable - not two separate random splits that could favor
        # one by luck. Only these two: crisp-dm/05_full_archive_model_selection.ipynb
        # showed Linear/Ridge regression dominated by 15-30+ R2 points in every one
        # of the 10 markets on the full Inside Airbnb archive, so they aren't worth
        # the extra training time in a path that runs synchronously inside an HTTP
        # request (/admin/retrain-and-fix-guardrails). That notebook also found
        # XGBoost won on R2 in 9/10 markets there and Random Forest won the 10th
        # (Mexico City) - but it trained on a much larger, different sample (the
        # full archive) than this function's live `Listing` table, so the winner
        # is decided fresh here, per retrain, against whatever's actually in the
        # DB right now, rather than hardcoding that notebook's specific mapping.
        candidates = {
            "RandomForest": RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1),
            "XGBoost": XGBRegressor(n_estimators=200, max_depth=5, learning_rate=0.08, random_state=42,
                                     n_jobs=-1, verbosity=0),
        }
        y_test = np.expm1(y_test_log)
        scored = {}
        for name, candidate in candidates.items():
            candidate.fit(X_train, y_train_log)
            preds = np.expm1(candidate.predict(X_test))
            scored[name] = {
                "model": candidate,
                "mae": mean_absolute_error(y_test, preds),
                "r2": r2_score(y_test, preds),
            }

        best_name = max(scored, key=lambda name: scored[name]["r2"])
        model, mae, r2 = scored[best_name]["model"], scored[best_name]["mae"], scored[best_name]["r2"]

        joblib.dump({"model": model, "columns": feature_columns, "algorithm": best_name},
                    os.path.join(MODEL_DIR, f"market_{market.id}.joblib"))
        results[market.name] = {
            "algorithm": best_name, "mae": round(mae, 2), "r2": round(r2, 3), "n": len(df),
            "currency": market.currency,
            "r2_by_algorithm": {name: round(s["r2"], 3) for name, s in scored.items()},
        }
        comparison = "  ".join(f"{name}={s['r2']:.3f}" for name, s in scored.items())
        print(f"{market.name:15s} ({market.currency}): winner={best_name:12s} MAE={mae:9.2f}  R2={r2:.3f}  "
              f"[{comparison}]  n={len(df)}")

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
