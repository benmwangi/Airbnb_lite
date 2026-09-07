# Airbnb-lite dynamic pricing

An end-to-end demo of the architecture discussed: own-marketplace listings/calendar/bookings,
per-market pricing models, an event/news-aware decision engine with guardrails, and a
host approval dashboard.

## Run it

```bash
pip install fastapi uvicorn sqlalchemy scikit-learn joblib pandas numpy requests streamlit

# Option A: real Maven Airbnb dataset (recommended - this is what's tested below)
python real_data_loader.py --listings listings.csv --reviews reviews.csv --sample-per-market 400

# Option B: synthetic data, if you don't have the CSVs
python seed_data.py

python pricing_model.py    # trains one model PER MARKET, saves to models/
python pricing_engine.py   # prices the next N nights for every listing, batched per market

uvicorn main:app --reload  # API on http://localhost:8000  (docs at /docs)
