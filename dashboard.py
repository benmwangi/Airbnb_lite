"""
Host control layer dashboard.

Run: streamlit run dashboard.py

Shows, per listing: the recommended price, why it was recommended (the
explanation the pricing engine wrote), and lets the host approve, override,
or reject before it goes live - the visibility + control piece that was
missing from the original CSV-driven app.py.
"""
import datetime
import streamlit as st
import pandas as pd
import requests

API = "http://localhost:8000"

st.set_page_config(page_title="Host pricing control", layout="wide")
st.title("Host pricing control")

try:
    markets = requests.get(f"{API}/markets", timeout=5).json()
except requests.RequestException:
    st.error("API not reachable. Start it with: uvicorn main:app --reload")
    st.stop()

market_names = {m["id"]: f'{m["name"]} ({m["currency"]}) - {m["listing_count"]} listings' for m in markets}
market_id = st.selectbox("Market", options=list(market_names.keys()), format_func=lambda i: market_names[i])

listings = requests.get(f"{API}/listings", params={"market_id": market_id}).json()
listing_labels = {l["id"]: f'#{l["id"]} - {l["room_type"]}, sleeps {l["accommodates"]}' for l in listings}
listing_id = st.selectbox("Listing", options=list(listing_labels.keys()), format_func=lambda i: listing_labels[i])

col1, col2 = st.columns([1, 3])
with col1:
    if st.button("Run pricing engine for this market", type="primary"):
        requests.post(f"{API}/pricing/run", params={"days_ahead": 14})
        st.success("Pricing cycle complete.")
        st.rerun()

calendar = requests.get(f"{API}/listings/{listing_id}/calendar", params={"days": 14}).json()
if not calendar:
    st.info("No priced nights yet - click 'Run pricing engine' above.")
    st.stop()

df = pd.DataFrame(calendar)

st.subheader("Recommended vs live price, next 14 nights")
chart_df = df[["date", "base_model_price", "recommended_price", "live_price"]].set_index("date")
st.line_chart(chart_df)

st.subheader("Approve or override each night")
for row in calendar:
    with st.expander(f'{row["date"]}  ·  recommended {row["recommended_price"]:.2f}  ·  status: {row["status"]}'):
        st.write(row["explanation"])
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Approve", key=f'approve_{row["date"]}'):
                requests.post(f"{API}/pricing/approve", json={
                    "listing_id": listing_id, "date": row["date"], "approve": True,
                })
                st.rerun()
        with c2:
            override = st.number_input("Override price", value=float(row["recommended_price"]),
                                        key=f'override_val_{row["date"]}')
            if st.button("Apply override", key=f'override_btn_{row["date"]}'):
                requests.post(f"{API}/pricing/approve", json={
                    "listing_id": listing_id, "date": row["date"], "approve": True,
                    "override_price": override,
                })
                st.rerun()
        with c3:
            if st.button("Reject", key=f'reject_{row["date"]}'):
                requests.post(f"{API}/pricing/approve", json={
                    "listing_id": listing_id, "date": row["date"], "approve": False,
                })
                st.rerun()
