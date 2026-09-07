"""
Database layer for Airbnb-lite.

Defaults to SQLite for zero-setup local demos. For Postgres (recommended for
the real deployment - concurrent writes from the pricing engine, the API, and
the dashboard all at once), set the DATABASE_URL environment variable, e.g.:

    export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/airbnb_lite

No other code in this project changes - every module imports `engine` /
`get_session` from here.
"""
import os
import datetime
from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Boolean, DateTime,
    ForeignKey, Date, Text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./airbnb_lite.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Market(Base):
    """A pricing market - normally one city/metro. Models are trained per-market,
    not globally, so currency and local price dynamics never get blended together."""
    __tablename__ = "markets"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)          # e.g. "Cape Town"
    country = Column(String, nullable=False)
    currency = Column(String, nullable=False)                    # ISO code, e.g. "ZAR"
    center_lat = Column(Float, nullable=False)
    center_lng = Column(Float, nullable=False)

    listings = relationship("Listing", back_populates="market")


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=False)
    source_listing_id = Column(Integer, nullable=True, index=True)  # the real Maven/Inside
    # Airbnb listing_id this row was loaded from - needed to join back to real,
    # per-listing data (like actual review text) that isn't stored on this row
    # itself. Nullable because rows loaded before this column existed won't
    # have it until backfilled - see backfill_source_listing_id.py.
    host_id = Column(Integer, nullable=False)
    room_type = Column(String, nullable=False)                   # Entire home, Private room, Shared room
    accommodates = Column(Integer, nullable=False)
    bedrooms = Column(Float, nullable=False)
    bathrooms = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    dist_to_center_km = Column(Float, nullable=False)
    host_is_superhost = Column(Boolean, default=False)
    review_scores_rating = Column(Float, default=4.5)
    num_reviews = Column(Integer, default=0)
    price = Column(Float, nullable=True)  # observed/training-target nightly price, in market currency

    # host-configured guardrails and control settings (host control layer)
    min_floor = Column(Float, nullable=False)
    max_ceiling = Column(Float, nullable=False)
    aggressiveness = Column(Float, default=0.5)                  # 0 = stable, 1 = volatile
    auto_apply = Column(Boolean, default=False)                  # if False, host must approve

    market = relationship("Market", back_populates="listings")
    calendar_days = relationship("CalendarDay", back_populates="listing")


class CalendarDay(Base):
    """One row per listing per night. This is what the pricing engine writes to,
    and what generates the feedback-loop data once a booking happens."""
    __tablename__ = "calendar_days"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False)
    date = Column(Date, nullable=False)

    base_model_price = Column(Float)          # per-market model's structural estimate
    event_modifier_pct = Column(Float, default=0.0)
    news_modifier_pct = Column(Float, default=0.0)
    seasonal_modifier_pct = Column(Float, default=0.0)
    recommended_price = Column(Float)         # engine output before host approval
    live_price = Column(Float)                # price actually shown to guests
    status = Column(String, default="pending_approval")  # pending_approval, approved, auto_applied
    explanation = Column(Text)                # human-readable "why this price" string

    is_booked = Column(Boolean, default=False)
    booked_price = Column(Float)              # price at time of booking, for the feedback loop

    listing = relationship("Listing", back_populates="calendar_days")


class ExternalSignalCache(Base):
    """Cache of fetched event/news signals per market per day, so we don't
    re-hit external APIs on every pricing run."""
    __tablename__ = "external_signal_cache"

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=False)
    date = Column(Date, nullable=False)
    event_lift_pct = Column(Float, default=0.0)
    event_summary = Column(Text)
    news_lift_pct = Column(Float, default=0.0)
    news_summary = Column(Text)
    fetched_at = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String, default="synthetic")  # "predicthq", "newsapi", or "synthetic"


class MarketComparison(Base):
    """Aggregated real-world host pricing for a market, sourced from Inside Airbnb
    (CC BY 4.0 licensed public data - not scraped live from Airbnb) and grouped by
    room_type, so the dashboard can show 'here's what real hosts nearby actually
    charge' next to the model's recommendation."""
    __tablename__ = "market_comparisons"

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=False)
    room_type = Column(String, nullable=False)
    actual_median_price = Column(Float, nullable=False)
    actual_mean_price = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=False)
    source = Column(String, default="insideairbnb")
    source_snapshot_date = Column(Date)
    fetched_at = Column(DateTime, default=datetime.datetime.utcnow)


class ReviewInsight(Base):
    """A detected theme in a listing's real guest reviews, with a host-facing
    recommendation - e.g. multiple reviews mentioning outdated decor becomes
    a suggestion to modernize. Sourced from real Inside Airbnb review text
    (the Maven review export has no review text at all, only IDs/dates), so
    this table is only populated for listings with a source_listing_id that
    was found in a real Inside Airbnb reviews.csv.gz file."""
    __tablename__ = "review_insights"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False)
    theme = Column(String, nullable=False)
    mention_count = Column(Integer, nullable=False)
    total_reviews_scanned = Column(Integer, nullable=False)
    recommendation = Column(Text, nullable=False)
    source = Column(String, default="insideairbnb")
    fetched_at = Column(DateTime, default=datetime.datetime.utcnow)


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
