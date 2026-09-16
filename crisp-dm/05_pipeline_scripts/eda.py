import pandas as pd, numpy as np, json, base64, io, sys, time
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

t0 = time.time()

MARKET_METADATA = {
    "Bangkok": ("Thailand", "THB", 13.7563, 100.5018),
    "Cape Town": ("South Africa", "ZAR", -33.9249, 18.4241),
    "Hong Kong": ("China", "HKD", 22.3193, 114.1694),
    "Istanbul": ("Turkey", "TRY", 41.0082, 28.9784),
    "Mexico City": ("Mexico", "MXN", 19.4326, -99.1332),
    "New York": ("United States", "USD", 40.7128, -74.0060),
    "Paris": ("France", "EUR", 48.8566, 2.3522),
    "Rio de Janeiro": ("Brazil", "BRL", -22.9068, -43.1729),
    "Rome": ("Italy", "EUR", 41.9028, 12.4964),
    "Sydney": ("Australia", "AUD", -33.8688, 151.2093),
}
LOCAL_LISTING_FILES = {
    "Bangkok": "listings(1).csv.gz",
    "Cape Town": "listings(2).csv.gz",
    "Hong Kong": "listings(3).csv.gz",
    "Mexico City": "listings(4).csv.gz",
    "New York": "listings(5).csv.gz",
    "Paris": "listings(6).csv.gz",
    "Rio de Janeiro": "listings(7).csv.gz",
    "Rome": "listings(8).csv.gz",
    "Sydney": "listings(9).csv.gz",
    "Istanbul": "listings(10).csv.gz",
}

DATA_DIR = "/sessions/rcw-01jyuqu5tlpqne8rwvuhnaz8/mnt/files"
USECOLS = ["id","price","room_type","property_type","accommodates","bedrooms",
           "bathrooms","beds","latitude","longitude","host_since","host_is_superhost",
           "host_listings_count","number_of_reviews","review_scores_rating",
           "minimum_nights","maximum_nights","availability_365",
           "neighbourhood_cleansed","amenities","instant_bookable"]

def clean_price(s):
    return pd.to_numeric(s.astype(str).str.replace(r"[\$,]", "", regex=True), errors="coerce")

frames = {}
for market, fname in LOCAL_LISTING_FILES.items():
    path = f"{DATA_DIR}/{fname}"
    df = pd.read_csv(path, usecols=lambda c: c in USECOLS, low_memory=False)
    df["market"] = market
    df["price_raw"] = df["price"]
    df["price"] = clean_price(df["price"])
    df["n_amenities"] = df["amenities"].astype(str).apply(lambda x: x.count(",") + 1 if x not in ("nan","[]") else 0)
    if "host_since" in df.columns:
        df["host_since"] = pd.to_datetime(df["host_since"], errors="coerce")
    frames[market] = df
    print(f"{market:15s} rows={len(df):6d} price_notnull={df['price'].notna().sum():6d} t={time.time()-t0:.1f}s", flush=True)

print("TOTAL rows:", sum(len(d) for d in frames.values()))
print("load done at", time.time()-t0, "s")

import pickle
with open(f"{__import__('os').environ['HOME']}/crispdm_work/frames.pkl", "wb") as f:
    pickle.dump(frames, f, protocol=4)
print("pickled frames at", time.time()-t0, "s")
