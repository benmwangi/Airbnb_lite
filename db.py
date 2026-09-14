"""
Database layer for Airbnb-lite.

Defaults to SQLite for zero-setup local demos. For Postgres (recommended for
the real deployment - concurrent writes from the pricing engine, the API, and
the dashboard all at once), set the DATABASE_URL environment variable, e.g.:

    export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/airbnb_lite

Rather than exporting that in every new shell, put it in a `.env` file in the
project root (see `.env.example`) - load_dotenv() below reads it into
os.environ automatically before DATABASE_URL is read, in every entry point
that imports this module (main.py, insideairbnb_loader.py,
reset_and_reload_sample.py, pricing_engine.py, ...), so it only needs to be
set once. `.env` is already covered by the repo's `.env*` .gitignore rule -
same as `.env.local` already is for the Next.js frontend - so it's never
committed. An explicit `$env:DATABASE_URL = "..."` in the shell still wins:
load_dotenv()'s default `override=False` never replaces a variable that's
already set in the environment.

No other code in this project changes - every module imports `engine` /
`get_session` from here.
"""
import os
import datetime
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Boolean, DateTime,
    ForeignKey, Date, Text, BigInteger, Index
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./airbnb_lite.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping: issues a cheap "SELECT 1" before handing out any pooled
# connection and transparently reconnects if that fails, instead of raising
# on the caller's real query. Needed because Neon's free tier auto-suspends
# its compute after a few minutes idle, which closes the TCP/SSL connection
# from the DB side - the app's connection pool doesn't find out until it
# tries to reuse that now-dead connection, which failed as:
#   sqlalchemy.exc.OperationalError: (psycopg2.OperationalError)
#   SSL connection has been closed unexpectedly
# pool_recycle proactively discards any pooled connection older than 280s
# (just under Neon's ~5min default suspend window) so a connection is
# rarely old enough to have gone stale in the first place - pre_ping is
# the safety net for whatever recycle doesn't catch. Both are no-ops for
# the local SQLite fallback (single file handle, nothing to go stale), so
# they're left on unconditionally rather than branched on DATABASE_URL.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, pool_recycle=280)
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
    listing_count = Column(Integer, default=0, nullable=False)

    listings = relationship("Listing", back_populates="market")


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        Index("ix_listings_market_id_id", "market_id", "id"),
        Index("ix_listings_market_picture_id", "market_id", "picture_url", "id"),
        Index("ix_listings_host_id", "host_id"),
    )

    id = Column(Integer, primary_key=True)
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=False)
    source_listing_id = Column(BigInteger, nullable=True, index=True)  # the real Maven/Inside
    # Airbnb listing_id this row was loaded from - needed to join back to real,
    # per-listing data (like actual review text) that isn't stored on this row
    # itself. Nullable because rows loaded before this column existed won't
    # have it until backfilled - see backfill_source_listing_id.py.
    host_id = Column(BigInteger, nullable=False)
    host_name = Column(String, nullable=True)
    name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    host_since = Column(Date, nullable=True)
    host_location = Column(String, nullable=True)
    neighbourhood = Column(String, nullable=True)
    property_type = Column(String, nullable=True)
    amenities = Column(Text, nullable=True)
    house_rules = Column(Text, nullable=True)
    picture_url = Column(String, nullable=True)
    minimum_nights = Column(Integer, nullable=True)
    maximum_nights = Column(Integer, nullable=True)
    instant_bookable = Column(Boolean, nullable=True)
    review_scores_cleanliness = Column(Float, nullable=True)
    review_scores_checkin = Column(Float, nullable=True)
    review_scores_communication = Column(Float, nullable=True)
    review_scores_location = Column(Float, nullable=True)
    review_scores_value = Column(Float, nullable=True)
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
    __table_args__ = (
        Index("ix_calendar_days_listing_date", "listing_id", "date"),
    )

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
    guest_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # who booked, if logged in

    listing = relationship("Listing", back_populates="calendar_days")


class ExternalSignalCache(Base):
    """Cache of fetched event/news signals per market per day, so we don't
    re-hit external APIs on every pricing run. Looked up (and, since
    pricing_engine.py's batched run_pricing_cycle, bulk-looked-up) by
    market_id + date, so that pair is indexed together rather than relying
    on the implicit primary-key index alone - without this, the WHERE
    market_id = ... AND date IN (...) query that run_pricing_cycle issues
    once per market degrades to a sequential scan as this table grows."""
    __tablename__ = "external_signal_cache"
    __table_args__ = (
        Index("ix_external_signal_cache_market_date", "market_id", "date", unique=True),
    )

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
    specific_details = Column(String, nullable=True)  # e.g. "towels, coffee maker" - specific
                                                        # items/locations extracted from the
                                                        # matching reviews themselves, when found
    sample_review = Column(Text, nullable=True)  # one real matching review's text (truncated),
                                                   # shown to the host as the evidence behind
                                                   # the recommendation - not just an assertion
    source = Column(String, default="insideairbnb")
    fetched_at = Column(DateTime, default=datetime.datetime.utcnow)


class ReviewExcerpt(Base):
    """A small, recent sample of real review text for guest-facing listing pages."""
    __tablename__ = "review_excerpts"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False, index=True)
    reviewer_name = Column(String, nullable=True)
    review_date = Column(Date, nullable=True)
    comments = Column(Text, nullable=False)
    source = Column(String, default="insideairbnb")
    fetched_at = Column(DateTime, default=datetime.datetime.utcnow)


class User(Base):
    """A login account, either a guest or a host. Passwords are never stored
    in plain text - see auth.py for hashing. A host account's `host_id` links
    to the numeric host_id already used on Listing rows (real Maven/Inside
    Airbnb host IDs), so logging in as a host scopes /host/my-listings to
    the listings that host actually owns instead of a hardcoded default.
    Guest accounts leave host_id null."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "guest" or "host"
    host_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Session(Base):
    """A logged-in session, identified by an opaque bearer token the client
    stores and sends back on every request. Deliberately simple (no JWT) so
    a session can be revoked server-side just by deleting its row."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


def init_db():
    Base.metadata.create_all(engine)
    _sync_postgres_sequences()
    _ensure_column("calendar_days", "guest_user_id", "INTEGER")
    _ensure_column("markets", "listing_count", "INTEGER NOT NULL DEFAULT 0")
    for column, sql_type in {
        "host_name": "TEXT", "name": "TEXT", "description": "TEXT", "host_since": "DATE",
        "host_location": "TEXT", "neighbourhood": "TEXT", "property_type": "TEXT",
        "amenities": "TEXT", "house_rules": "TEXT", "picture_url": "TEXT",
        "minimum_nights": "INTEGER", "maximum_nights": "INTEGER",
        "instant_bookable": "BOOLEAN", "review_scores_cleanliness": "DOUBLE PRECISION",
        "review_scores_checkin": "DOUBLE PRECISION", "review_scores_communication": "DOUBLE PRECISION",
        "review_scores_location": "DOUBLE PRECISION", "review_scores_value": "DOUBLE PRECISION",
    }.items():
        _ensure_column("listings", column, sql_type)
    # create_all() only creates indexes when it creates the TABLE itself - a
    # database whose external_signal_cache table predates this index needs
    # it added directly, same reasoning as _ensure_column above.
    _ensure_index(
        "external_signal_cache", "ix_external_signal_cache_market_date",
        "market_id, date", unique=True,
    )


def _sync_postgres_sequences():
    """Keep serial identity sequences ahead of rows imported with explicit IDs."""
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        for table in ("external_signal_cache",):
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                f"(SELECT COUNT(*) > 0 FROM {table}))"
            ))


def _ensure_column(table: str, column: str, sql_type: str):
    """create_all() only creates missing TABLES, not missing COLUMNS on tables
    that already exist - a database created before this column was added to
    the model needs it added directly. Safe to call repeatedly."""
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
            conn.commit()
        except Exception:
            pass  # column already exists - fine


def _ensure_index(table: str, index_name: str, columns: str, unique: bool = False):
    """create_all() only creates indexes on tables it creates itself - a
    table that already existed before this index was added to the model
    needs it added directly, same as _ensure_column(). Safe to call
    repeatedly: CREATE [UNIQUE] INDEX IF NOT EXISTS is supported identically
    by both SQLite and Postgres, so no dialect branching is needed here.

    Note: if duplicate (market_id, date) rows already exist in
    external_signal_cache (e.g. from a race between concurrent pricing
    runs before this index existed), creating a UNIQUE index will fail and
    this silently no-ops, same as an already-existing column would. Run a
    manual dedup (keep the newest `fetched_at` per market_id/date) first if
    that's a concern for your database."""
    from sqlalchemy import text
    unique_kw = "UNIQUE " if unique else ""
    with engine.connect() as conn:
        try:
            conn.execute(text(f"CREATE {unique_kw}INDEX IF NOT EXISTS {index_name} ON {table} ({columns})"))
            conn.commit()
        except Exception:
            pass  # duplicates present, or already exists - fine, same tolerance as _ensure_column


def get_session():
    return SessionLocal()
