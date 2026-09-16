import pandas as pd, numpy as np, json, base64, io, time, pickle, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

t0 = time.time()
HOME = os.environ["HOME"]
with open(f"{HOME}/crispdm_work/frames.pkl", "rb") as f:
    frames = pickle.load(f)
MARKETS = list(frames.keys())

def fig_to_b64(fig, dpi=90):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
am_pooled, rev_pooled = [], []
for m in MARKETS:
    d = frames[m].copy()
    d = d[d["price"] > 0]
    mu, sd = d["price"].mean(), d["price"].std()
    d["price_z"] = (d["price"] - mu) / sd
    am_pooled.append(d[["price_z", "n_amenities"]])
    rev_pooled.append(d[["price_z", "review_scores_rating"]])
am_pooled = pd.concat(am_pooled, ignore_index=True)
rev_pooled = pd.concat(rev_pooled, ignore_index=True)

am_pooled["am_bin"] = pd.cut(am_pooled["n_amenities"], bins=[0,5,10,15,20,30,40,60,1000],
                              labels=["1-5","6-10","11-15","16-20","21-30","31-40","41-60","60+"])
am_means = am_pooled.groupby("am_bin", observed=True)["price_z"].mean()
axes[0].plot(am_means.index.astype(str), am_means.values, marker="o", color="#990011")
axes[0].set_xlabel("number of amenities (binned)"); axes[0].set_ylabel("mean price z-score (within-market)")
axes[0].set_title("Price vs. amenities count (pooled, all markets)")
axes[0].tick_params(axis="x", rotation=30)

rev_pooled = rev_pooled.dropna(subset=["review_scores_rating"])
rev_pooled["rev_bin"] = pd.cut(rev_pooled["review_scores_rating"], bins=[0,3.5,4.0,4.5,4.7,4.85,4.95,5.01],
                                labels=["<3.5","3.5-4.0","4.0-4.5","4.5-4.7","4.7-4.85","4.85-4.95","4.95-5.0"])
rev_means = rev_pooled.groupby("rev_bin", observed=True)["price_z"].mean()
rev_counts = rev_pooled.groupby("rev_bin", observed=True)["price_z"].count()
axes[1].plot(rev_means.index.astype(str), rev_means.values, marker="o", color="#2F3C7E")
axes[1].set_xlabel("review_scores_rating (binned)"); axes[1].set_ylabel("mean price z-score (within-market)")
axes[1].set_title("Price vs. review score (pooled, all markets)\n(host_since was 100% missing in this archive, so host\ntenure could not be used — review score used instead)")
axes[1].tick_params(axis="x", rotation=30)
fig.tight_layout()
b64 = fig_to_b64(fig)
print("fig6 fixed done", time.time()-t0)

with open(f"{HOME}/crispdm_work/figures_part2.json") as f:
    part2 = json.load(f)
part2["figures"]["amenities_and_reviewscore_vs_price"] = b64
part2["figures"].pop("amenities_and_tenure_vs_price", None)
with open(f"{HOME}/crispdm_work/figures_part2.json", "w") as f:
    json.dump(part2, f)
print("saved, keys now:", list(part2["figures"].keys()))
