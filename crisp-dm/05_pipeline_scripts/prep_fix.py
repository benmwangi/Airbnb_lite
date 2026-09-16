import pandas as pd, numpy as np, json, pickle, os

HOME = os.environ["HOME"]
with open(f"{HOME}/crispdm_work/prepared.pkl", "rb") as f:
    prepared = pickle.load(f)
with open(f"{HOME}/crispdm_work/prep_log.json") as f:
    prep_log = json.load(f)

MAXNIGHTS_SENTINEL_CAP = 365  # values above this are Airbnb "effectively unlimited" placeholders
                               # (365, 1125, 9999, 2147483647=int32 max all seen in this archive)
HOSTLISTINGS_CAP = 100         # above this = professional property-management accounts, a
                                # different population than individual hosts; capped not dropped
BATHROOMS_CAP = 10             # values of 15-50 are almost certainly bathrooms_text parsing
                                # artifacts / data-entry errors for single listings

sentinel_report = {}
for m, d in prepared.items():
    n_sentinel = int((d["maximum_nights"] >= MAXNIGHTS_SENTINEL_CAP).sum())
    sentinel_report[m] = {
        "max_maximum_nights_before_cap": float(d["maximum_nights"].max()),
        "n_rows_at_or_above_sentinel_cap": n_sentinel,
        "pct_rows_at_or_above_sentinel_cap": round(100 * n_sentinel / len(d), 1),
        "max_host_listings_count_before_cap": float(d["host_listings_count"].max()),
        "max_bathrooms_before_cap": float(d["bathrooms"].max()),
    }
    d["has_no_real_max_nights"] = (d["maximum_nights"] >= MAXNIGHTS_SENTINEL_CAP).astype(int)
    d["maximum_nights"] = d["maximum_nights"].clip(upper=MAXNIGHTS_SENTINEL_CAP)
    d["host_listings_count"] = d["host_listings_count"].clip(upper=HOSTLISTINGS_CAP)
    d["bathrooms"] = d["bathrooms"].clip(upper=BATHROOMS_CAP)
    prepared[m] = d

prep_log["_sentinel_value_fix"] = {
    "issue": "maximum_nights contains Airbnb's 'no real maximum' placeholder values (365/1125/9999/2147483647 "
             "= int32 max), which massively distort feature scale for linear models (Ridge CV R2 went to "
             "-198830 on Mexico City before this fix). host_listings_count and bathrooms also had a handful "
             "of extreme outliers (professional management accounts, and apparent data-entry errors up to "
             "50 bathrooms) that needed capping for the same reason.",
    "fix": f"capped maximum_nights at {MAXNIGHTS_SENTINEL_CAP} (added binary flag has_no_real_max_nights), "
           f"host_listings_count at {HOSTLISTINGS_CAP}, bathrooms at {BATHROOMS_CAP}.",
    "per_market": sentinel_report,
}

with open(f"{HOME}/crispdm_work/prepared.pkl", "wb") as f:
    pickle.dump(prepared, f, protocol=4)
with open(f"{HOME}/crispdm_work/prep_log.json", "w") as f:
    json.dump(prep_log, f, indent=2, default=str)

for m, v in sentinel_report.items():
    print(m, v)
