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

figures = {}

# ---- Fig 1: price distribution per market (raw, before any outlier removal) ----
fig, axes = plt.subplots(2, 5, figsize=(20, 7))
for ax, m in zip(axes.flat, MARKETS):
    s = frames[m]["price"].dropna()
    s = s[s > 0]
    ax.hist(np.log1p(s), bins=40, color="#1C7293", edgecolor="none")
    ax.set_title(f"{m} ({MARKET_CURRENCY[m]})\nn={len(s):,}", fontsize=9)
    ax.set_xlabel("log(1+price)", fontsize=8)
    ax.tick_params(labelsize=7)
fig.suptitle("Raw nightly price distribution per market (log scale) — before cleaning", fontsize=13)
fig.tight_layout()
figures["price_distributions_raw"] = fig_to_b64(fig)
print("fig1 done", time.time()-t0)

# ---- Fig 2: price by room_type, per market ----
fig, axes = plt.subplots(2, 5, figsize=(20, 8))
for ax, m in zip(axes.flat, MARKETS):
    d = frames[m][["price", "room_type"]].dropna()
    d = d[d["price"] > 0]
    order = d["room_type"].value_counts().index
    data = [np.log1p(d.loc[d["room_type"] == rt, "price"].values) for rt in order]
    ax.boxplot(data, labels=[o[:10] for o in order], showfliers=False)
    ax.set_title(f"{m} ({MARKET_CURRENCY[m]})", fontsize=9)
    ax.tick_params(axis="x", labelsize=6, rotation=30)
    ax.tick_params(axis="y", labelsize=7)
fig.suptitle("log(1+price) by room type, per market", fontsize=13)
fig.tight_layout()
figures["price_by_room_type"] = fig_to_b64(fig)
print("fig2 done", time.time()-t0)

# ---- Fig 3: correlation heatmap (pooled, price z-scored within market) ----
num_cols = ["price_z", "accommodates", "bedrooms", "bathrooms", "beds",
            "number_of_reviews", "review_scores_rating", "n_amenities",
            "minimum_nights", "availability_365", "host_listings_count"]
pooled = []
for m in MARKETS:
    d = frames[m].copy()
    d = d[d["price"] > 0]
    mu, sd = d["price"].mean(), d["price"].std()
    d["price_z"] = (d["price"] - mu) / sd
    pooled.append(d[num_cols])
pooled = pd.concat(pooled, ignore_index=True)
corr = pooled.corr(numeric_only=True)
fig, ax = plt.subplots(figsize=(8, 7))
im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
ax.set_xticks(range(len(corr.columns))); ax.set_xticklabels(corr.columns, rotation=60, ha="right", fontsize=8)
ax.set_yticks(range(len(corr.columns))); ax.set_yticklabels(corr.columns, fontsize=8)
for i in range(len(corr)):
    for j in range(len(corr)):
        ax.text(j, i, f"{corr.values[i,j]:.2f}", ha="center", va="center", fontsize=6,
                color="white" if abs(corr.values[i, j]) > 0.5 else "black")
fig.colorbar(im, ax=ax, shrink=0.8)
ax.set_title("Correlation matrix — pooled across markets\n(price z-scored within market to make it currency-comparable)", fontsize=10)
fig.tight_layout()
figures["correlation_heatmap"] = fig_to_b64(fig)
print("fig3 done", time.time()-t0)
corr_with_price = corr["price_z"].drop("price_z").sort_values(ascending=False).to_dict()

fig.savefig  # no-op keep ref
with open(f"{HOME}/crispdm_work/figures_part1.json", "w") as f:
    json.dump({"figures": figures, "corr_with_price": corr_with_price}, f)
print("saved part1", time.time()-t0)
