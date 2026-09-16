import pandas as pd, numpy as np, json, base64, io, time, pickle, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

t0 = time.time()
HOME = os.environ["HOME"]
with open(f"{HOME}/crispdm_work/frames.pkl", "rb") as f:
    frames = pickle.load(f)

MARKET_CURRENCY = {
    "Bangkok": "THB", "Cape Town": "ZAR", "Hong Kong": "HKD", "Istanbul": "TRY",
    "Mexico City": "MXN", "New York": "USD", "Paris": "EUR",
    "Rio de Janeiro": "BRL", "Rome": "EUR", "Sydney": "AUD",
}
MARKETS = list(frames.keys())

def fig_to_b64(fig, dpi=90):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")

# ---- confirm + document fully-missing columns across the whole archive ----
ALL_COLS = ["host_since","host_is_superhost","instant_bookable","host_listings_count",
            "review_scores_rating","minimum_nights","maximum_nights","bedrooms",
            "bathrooms","beds","n_amenities"]
missing_pct_table = {}
for m, d in frames.items():
    missing_pct_table[m] = {c: round(100*(1 - d[c].notna().mean()), 1) for c in ALL_COLS if c in d.columns}

fully_missing_everywhere = [c for c in ALL_COLS
                             if all(missing_pct_table[m].get(c, 100) == 100.0 for m in MARKETS)]
print("Columns 100% missing in EVERY market (archive-wide data-quality gap):", fully_missing_everywhere)

# Missingness heatmap (nature-of-the-data EDA figure)
mm = pd.DataFrame(missing_pct_table).T[ALL_COLS]
fig, ax = plt.subplots(figsize=(10, 6))
im = ax.imshow(mm.values, cmap="Reds", vmin=0, vmax=100, aspect="auto")
ax.set_xticks(range(len(mm.columns))); ax.set_xticklabels(mm.columns, rotation=45, ha="right", fontsize=8)
ax.set_yticks(range(len(mm.index))); ax.set_yticklabels(mm.index, fontsize=8)
for i in range(mm.shape[0]):
    for j in range(mm.shape[1]):
        ax.text(j, i, f"{mm.values[i,j]:.0f}", ha="center", va="center", fontsize=7,
                color="white" if mm.values[i, j] > 55 else "black")
ax.set_title("Missing data (%) by feature and market\n(host_since & instant_bookable are 100% missing in this archive export)", fontsize=10)
fig.colorbar(im, ax=ax, shrink=0.8, label="% missing")
fig.tight_layout()
missingness_fig = fig_to_b64(fig)
print("missingness fig done", time.time()-t0)

REF_DATE = pd.Timestamp("2026-01-01")
DROP_COLS_ARCHIVE_WIDE = fully_missing_everywhere  # e.g. ['host_since', 'instant_bookable']

def prepare_market(df, market):
    d = df.copy()
    before_n = len(d)
    d = d[d["price"].notna() & (d["price"] > 0)]
    after_price_drop = len(d)
    q1, q3 = d["price"].quantile(0.25), d["price"].quantile(0.75)
    iqr = q3 - q1
    fence = q3 + 3 * iqr
    n_capped = int((d["price"] > fence).sum())
    d["price_capped"] = d["price"].clip(upper=fence)
    d["log_price"] = np.log1p(d["price_capped"])
    for col in ["bedrooms", "bathrooms", "beds", "review_scores_rating"]:
        if col in d.columns:
            d[f"{col}_missing"] = d[col].isna().astype(int)
            d[col] = d[col].fillna(d[col].median())
    d["host_is_superhost"] = (d["host_is_superhost"] == "t").astype(int)
    if "host_listings_count" in d.columns:
        d["host_listings_count"] = d["host_listings_count"].fillna(d["host_listings_count"].median())
    for col, cap in [("accommodates", 16), ("bedrooms", 10), ("beds", 16)]:
        if col in d.columns:
            d[col] = d[col].clip(upper=cap)
    d = d.drop(columns=[c for c in DROP_COLS_ARCHIVE_WIDE if c in d.columns])
    d["market"] = market
    return d, {
        "before_n": before_n, "after_price_drop": after_price_drop,
        "n_dropped_missing_or_nonpositive_price": before_n - after_price_drop,
        "n_capped_outliers": n_capped, "outlier_fence": round(float(fence), 2),
    }

prepared, prep_log = {}, {}
for m in MARKETS:
    prepared[m], prep_log[m] = prepare_market(frames[m], m)

prep_log["_archive_wide_dropped_columns"] = DROP_COLS_ARCHIVE_WIDE
prep_log["_archive_wide_dropped_reason"] = "100% missing (NaN) in every one of the 10 markets in this Inside Airbnb export snapshot; imputing would fabricate signal, so the columns (and the host-tenure feature that depends on host_since) are dropped rather than imputed."

with open(f"{HOME}/crispdm_work/prepared.pkl", "wb") as f:
    pickle.dump(prepared, f, protocol=4)
with open(f"{HOME}/crispdm_work/prep_log.json", "w") as f:
    json.dump(prep_log, f, indent=2)

# ---- before/after prep visual: price distribution, raw vs cleaned+capped+logged ----
fig, axes = plt.subplots(2, 5, figsize=(20, 8))
for ax, m in zip(axes.flat, MARKETS):
    raw = frames[m]["price"].dropna()
    raw = raw[raw > 0]
    cleaned_log = prepared[m]["log_price"]
    ax.hist(np.log1p(raw), bins=40, alpha=0.5, label="raw (log1p)", color="#B85042", density=True)
    ax.hist(cleaned_log, bins=40, alpha=0.5, label="cleaned+capped (log1p)", color="#028090", density=True)
    ax.set_title(f"{m}\ncapped {prep_log[m]['n_capped_outliers']} of {prep_log[m]['after_price_drop']}", fontsize=8)
    ax.tick_params(labelsize=6)
    if m == MARKETS[0]:
        ax.legend(fontsize=6)
fig.suptitle("Effect of data preparation: price distribution before vs. after outlier capping (log1p scale)", fontsize=12)
fig.tight_layout()
before_after_fig = fig_to_b64(fig)
print("before/after fig done", time.time()-t0)

with open(f"{HOME}/crispdm_work/figures_part3.json", "w") as f:
    json.dump({"figures": {"missingness_heatmap": missingness_fig,
                            "price_before_after_prep": before_after_fig},
               "missing_pct_table": missing_pct_table,
               "fully_missing_everywhere": fully_missing_everywhere}, f)
print("saved part3", time.time()-t0)
for m in MARKETS:
    print(m, prep_log[m])
