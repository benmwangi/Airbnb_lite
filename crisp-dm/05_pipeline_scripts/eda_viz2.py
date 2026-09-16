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

# ---- Fig 4: geographic scatter, colored by within-market price percentile ----
fig, axes = plt.subplots(2, 5, figsize=(20, 8))
rng = np.random.default_rng(42)
for ax, m in zip(axes.flat, MARKETS):
    d = frames[m][["latitude", "longitude", "price"]].dropna()
    d = d[d["price"] > 0]
    if len(d) > 6000:
        d = d.sample(6000, random_state=42)
    pct = d["price"].rank(pct=True)
    sc = ax.scatter(d["longitude"], d["latitude"], c=pct, cmap="viridis", s=4, alpha=0.5)
    ax.set_title(f"{m}", fontsize=9)
    ax.tick_params(labelsize=6)
fig.suptitle("Listing locations colored by within-market price percentile (yellow = most expensive)", fontsize=12)
fig.tight_layout()
figures["geographic_price_percentile"] = fig_to_b64(fig)
print("fig4 done", time.time()-t0)

# ---- Fig 5: price vs accommodates and bedrooms (pooled, z-scored price) ----
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
pooled = []
for m in MARKETS:
    d = frames[m].copy()
    d = d[d["price"] > 0]
    mu, sd = d["price"].mean(), d["price"].std()
    d["price_z"] = (d["price"] - mu) / sd
    pooled.append(d[["price_z", "accommodates", "bedrooms"]])
pooled = pd.concat(pooled, ignore_index=True)

acc_grp = pooled.dropna(subset=["accommodates"]).copy()
acc_grp["accommodates_capped"] = acc_grp["accommodates"].clip(upper=8)
means = acc_grp.groupby("accommodates_capped")["price_z"].mean()
counts = acc_grp.groupby("accommodates_capped")["price_z"].count()
axes[0].bar(means.index.astype(str), means.values, color="#028090")
for i, (idx, v) in enumerate(means.items()):
    axes[0].text(i, v, f"n={counts[idx]:,}", ha="center", va="bottom", fontsize=7, rotation=90)
axes[0].set_xlabel("accommodates (capped at 8+)"); axes[0].set_ylabel("mean price z-score (within-market)")
axes[0].set_title("Price vs. accommodates (pooled, all markets)")

bed_grp = pooled.dropna(subset=["bedrooms"]).copy()
bed_grp["bedrooms_capped"] = bed_grp["bedrooms"].clip(upper=5)
means2 = bed_grp.groupby("bedrooms_capped")["price_z"].mean()
counts2 = bed_grp.groupby("bedrooms_capped")["price_z"].count()
axes[1].bar(means2.index.astype(str), means2.values, color="#02C39A")
for i, (idx, v) in enumerate(means2.items()):
    axes[1].text(i, v, f"n={counts2[idx]:,}", ha="center", va="bottom", fontsize=7, rotation=90)
axes[1].set_xlabel("bedrooms (capped at 5+)"); axes[1].set_ylabel("mean price z-score (within-market)")
axes[1].set_title("Price vs. bedrooms (pooled, all markets)")
fig.tight_layout()
figures["price_vs_accommodates_bedrooms"] = fig_to_b64(fig)
print("fig5 done", time.time()-t0)

# ---- Fig 6: amenities count vs price, host tenure vs price ----
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
am_pooled = []
tenure_pooled = []
for m in MARKETS:
    d = frames[m].copy()
    d = d[d["price"] > 0]
    mu, sd = d["price"].mean(), d["price"].std()
    d["price_z"] = (d["price"] - mu) / sd
    am_pooled.append(d[["price_z", "n_amenities"]])
    if "host_since" in d.columns:
        ref = pd.Timestamp("2026-01-01")
        d["host_tenure_years"] = (ref - d["host_since"]).dt.days / 365.25
        tenure_pooled.append(d[["price_z", "host_tenure_years"]])
am_pooled = pd.concat(am_pooled, ignore_index=True)
tenure_pooled = pd.concat(tenure_pooled, ignore_index=True)

am_pooled["am_bin"] = pd.cut(am_pooled["n_amenities"], bins=[0,5,10,15,20,30,40,60,1000],
                              labels=["1-5","6-10","11-15","16-20","21-30","31-40","41-60","60+"])
am_means = am_pooled.groupby("am_bin", observed=True)["price_z"].mean()
axes[0].plot(am_means.index.astype(str), am_means.values, marker="o", color="#990011")
axes[0].set_xlabel("number of amenities (binned)"); axes[0].set_ylabel("mean price z-score")
axes[0].set_title("Price vs. amenities count (pooled)")
axes[0].tick_params(axis="x", rotation=30)

tenure_pooled = tenure_pooled.dropna()
tenure_pooled = tenure_pooled[(tenure_pooled["host_tenure_years"] >= 0) & (tenure_pooled["host_tenure_years"] <= 18)]
tenure_pooled["tenure_bin"] = pd.cut(tenure_pooled["host_tenure_years"], bins=[0,1,2,3,5,8,12,18],
                                      labels=["0-1","1-2","2-3","3-5","5-8","8-12","12-18"])
tenure_means = tenure_pooled.groupby("tenure_bin", observed=True)["price_z"].mean()
axes[1].plot(tenure_means.index.astype(str), tenure_means.values, marker="o", color="#2F3C7E")
axes[1].set_xlabel("host tenure, years (binned)"); axes[1].set_ylabel("mean price z-score")
axes[1].set_title("Price vs. host tenure (pooled)")
fig.tight_layout()
figures["amenities_and_tenure_vs_price"] = fig_to_b64(fig)
print("fig6 done", time.time()-t0)

# ---- Fig 7: per-market median price + IQR (own currency, explicitly labeled) ----
fig, ax = plt.subplots(figsize=(11, 5))
meds = []
for m in MARKETS:
    s = frames[m]["price"].dropna()
    s = s[s > 0]
    meds.append((m, s.median(), s.quantile(0.25), s.quantile(0.75), MARKET_CURRENCY[m]))
meds.sort(key=lambda x: x[1])
labels = [f"{m}\n({c})" for m, med, q1, q3, c in meds]
medians = [med for m, med, q1, q3, c in meds]
err_low = [med - q1 for m, med, q1, q3, c in meds]
err_high = [q3 - med for m, med, q1, q3, c in meds]
ax.bar(labels, medians, yerr=[err_low, err_high], color="#1E2761", capsize=4)
ax.set_ylabel("nightly price (LOCAL CURRENCY — not directly comparable across markets)")
ax.set_title("Median nightly price by market ± IQR\n(each market in its own currency — see labels)")
ax.tick_params(axis="x", labelsize=8)
fig.tight_layout()
figures["median_price_per_market"] = fig_to_b64(fig)
print("fig7 done", time.time()-t0)

with open(f"{HOME}/crispdm_work/figures_part2.json", "w") as f:
    json.dump({"figures": figures}, f)
print("saved part2", time.time()-t0)
