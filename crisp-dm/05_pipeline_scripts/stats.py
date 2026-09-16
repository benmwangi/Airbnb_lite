import pandas as pd, numpy as np, json, pickle, os

HOME = os.environ["HOME"]
with open(f"{HOME}/crispdm_work/frames.pkl", "rb") as f:
    frames = pickle.load(f)

MARKET_CURRENCY = {
    "Bangkok": "THB", "Cape Town": "ZAR", "Hong Kong": "HKD", "Istanbul": "TRY",
    "Mexico City": "MXN", "New York": "USD", "Paris": "EUR",
    "Rio de Janeiro": "BRL", "Rome": "EUR", "Sydney": "AUD",
}
KEY_COLS = ["bedrooms", "bathrooms", "beds", "review_scores_rating", "host_since",
            "host_is_superhost", "n_amenities"]

summary = {}
for m, df in frames.items():
    s = df["price"].dropna()
    s_pos = s[s > 0]
    q1, q3 = s_pos.quantile(0.25), s_pos.quantile(0.75)
    iqr = q3 - q1
    upper_fence = q3 + 3 * iqr
    n_outliers = int((s_pos > upper_fence).sum())
    n_zero_or_neg = int((s <= 0).sum())
    missing_pct = {c: round(100 * df[c].isna().mean(), 1) for c in KEY_COLS if c in df.columns}
    summary[m] = {
        "currency": MARKET_CURRENCY[m],
        "n_rows": int(len(df)),
        "n_price_missing": int(df["price"].isna().sum()),
        "price_missing_pct": round(100 * df["price"].isna().mean(), 1),
        "n_price_zero_or_negative": n_zero_or_neg,
        "price_mean": round(float(s_pos.mean()), 2),
        "price_median": round(float(s_pos.median()), 2),
        "price_std": round(float(s_pos.std()), 2),
        "price_min": round(float(s_pos.min()), 2),
        "price_max": round(float(s_pos.max()), 2),
        "price_q1": round(float(q1), 2),
        "price_q3": round(float(q3), 2),
        "price_skew": round(float(s_pos.skew()), 2),
        "n_extreme_outliers_gt_q3plus3iqr": n_outliers,
        "outlier_fence_value": round(float(upper_fence), 2),
        "missing_pct_other_features": missing_pct,
        "n_after_dropping_missing_price": int(len(df) - df["price"].isna().sum() - n_zero_or_neg),
    }

with open(f"{HOME}/crispdm_work/market_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

for m, v in summary.items():
    print(m, "|", v["currency"], "| rows", v["n_rows"], "| price_missing%", v["price_missing_pct"],
          "| median", v["price_median"], "| outliers>Q3+3IQR", v["n_extreme_outliers_gt_q3plus3iqr"],
          "| skew", v["price_skew"])
