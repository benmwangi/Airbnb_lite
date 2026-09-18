"""
FastAPI service for Airbnb-lite.

Run: uvicorn main:app --reload
Docs: http://localhost:8000/docs

This is the layer that removes the "Airbnb won't let a third party write live
prices" constraint: bookings and calendar prices live in this app's own
database, so the pricing engine can write to them directly - no channel
manager or partner API needed. See README.md for what changes if you ever
point this at a real, live Airbnb listing instead.
"""
import datetime
import hmac
import os
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, select

from db import init_db, get_session, Listing, CalendarDay, Market, MarketComparison, ReviewInsight, ReviewExcerpt, User
import auth
from pricing_engine import run_pricing_cycle, price_listing_for_date, price_single_listing
from pricing_model import train_all_markets, predict_base_price, load_market_model, MODEL_DIR

app = FastAPI(title="Airbnb-lite Dynamic Pricing API")
MAX_HOST_CALENDAR_DAYS = 365
# A demo login's /listings/{id}/price-year calls are capped to this many
# days, matching the nightly cron's pre-warmed signal window (14 days - see
# claude/deployment-scheduling-guide.md and pricing_engine.py's
# run_pricing_cycle). Demo credentials (seed_demo_accounts.py /
# seed_feedback_demo_accounts.py) are published in the repo so anyone can
# log in as them, and they sit on real archive-backed listings - capping to
# the already-cached window means a demo login's price-year call can never
# touch a market/date the nightly job hasn't already fetched, so it can't
# trigger the kind of external-API burst described in external_signals.py's
# module docstring.
DEMO_PRICE_YEAR_MAX_DAYS = 14
_markets_cache: tuple[float, list[dict]] | None = None
# Shared secret the scheduled maintenance cron authenticates with (see
# claude/deployment-scheduling-guide.md) - unset locally, where this endpoint
# simply isn't callable rather than silently open.
CRON_SECRET = os.environ.get("CRON_SECRET")


def _require_cron_secret(authorization: Optional[str]):
    """Shared guard for the two cron-only endpoints. Uses hmac.compare_digest
    rather than `!=` so a timing attack can't be used to guess CRON_SECRET one
    byte at a time - a plain string comparison short-circuits on the first
    mismatched byte, which leaks how many leading characters were correct via
    response timing. Requires CRON_SECRET to be set at all: if it's unset
    (e.g. a misconfigured deploy), this endpoint must stay closed rather than
    accept any/no Authorization header."""
    if not CRON_SECRET:
        raise HTTPException(401, "Not authorized")
    expected = f"Bearer {CRON_SECRET}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(401, "Not authorized")


def _unique_image_listing_ids(session, market_id: Optional[int] = None):
    query = select(func.min(Listing.id)).where(
        Listing.picture_url.isnot(None),
        Listing.picture_url != "",
    )
    if market_id:
        query = query.where(Listing.market_id == market_id)
    return query.group_by(Listing.picture_url)

# Allows the Next.js dev server (a different origin: localhost:3000 vs this
# API's localhost:8000) to actually read responses from this API. Without
# this, the browser's own CORS policy silently blocks every fetch() call from
# the frontend - the API still runs and answers fine (curl works), but the
# browser refuses to hand the response to the page's JavaScript, which is
# exactly what "Can't reach the API" looks like from the frontend's side.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    # Vercel gives every deployment its own subdomain - the production one
    # (e.g. airbnb-lite.vercel.app) plus a fresh one for every preview build
    # (airbnb-lite-<hash>-<team>.vercel.app). A fixed allow_origins list can't
    # keep up with preview URLs, so this regex covers any *.vercel.app origin
    # in addition to the explicit localhost entries above.
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    # Render's free web service tier wipes the local filesystem on every
    # spin-down (see claude/deployment-scheduling-guide.md), which deletes
    # these joblib files along with everything else on disk - without this,
    # the first request after a cold start that needs a price prediction
    # would 500 with "No trained model for market X." Only retrains when a
    # model is actually missing, so local dev (where models/ already exists
    # on disk from a previous run) isn't slowed down by retraining on every
    # --reload restart.
    session = get_session()
    market_ids = [m.id for m in session.query(Market).all()]
    session.close()
    missing = [
        mid for mid in market_ids
        if not os.path.exists(os.path.join(MODEL_DIR, f"market_{mid}.joblib"))
    ]
    if missing:
        train_all_markets()


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str  # "guest" or "host"


class LoginRequest(BaseModel):
    email: str
    password: str


def _user_out(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role,
            "host_id": user.host_id, "is_demo": user.is_demo}


@app.post("/auth/signup")
def signup(req: SignupRequest):
    if req.role not in ("guest", "host"):
        raise HTTPException(400, "role must be 'guest' or 'host'")
    if len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    session = get_session()
    if session.query(User).filter_by(email=req.email).first():
        session.close()
        raise HTTPException(409, "An account with this email already exists")

    password_hash, salt = auth.hash_password(req.password)
    # A fresh host account starts with no real listings (host_id is a new,
    # unused number) - that's expected, not a bug. The seeded demo host
    # account (see seed_demo_accounts.py) is the one pre-linked to a real,
    # populated host_id for immediate demoing.
    new_host_id = None
    if req.role == "host":
        max_existing = session.query(Listing.host_id).order_by(Listing.host_id.desc()).first()
        new_host_id = (max_existing[0] + 1) if max_existing else 1

    user = User(email=req.email, password_hash=password_hash, password_salt=salt,
                name=req.name, role=req.role, host_id=new_host_id)
    session.add(user)
    session.commit()
    token = auth.create_session(session, user)
    result = {"token": token, "user": _user_out(user)}
    session.close()
    return result


@app.post("/auth/login")
def login(req: LoginRequest):
    session = get_session()
    user = session.query(User).filter_by(email=req.email).first()
    if not user or not auth.verify_password(req.password, user.password_hash, user.password_salt):
        session.close()
        raise HTTPException(401, "Incorrect email or password")
    token = auth.create_session(session, user)
    result = {"token": token, "user": _user_out(user)}
    session.close()
    return result


@app.get("/auth/me")
def me(authorization: Optional[str] = Header(None)):
    user = auth.get_user_from_token(auth.extract_bearer_token(authorization))
    if not user:
        raise HTTPException(401, "Not logged in")
    return _user_out(user)


@app.get("/markets")
def list_markets():
    global _markets_cache
    if _markets_cache and _markets_cache[0] > time.monotonic():
        return _markets_cache[1]
    session = get_session()
    markets = session.query(Market).all()
    out = [{"id": m.id, "name": m.name, "country": m.country, "currency": m.currency,
            "listing_count": m.listing_count} for m in markets]
    session.close()
    _markets_cache = (time.monotonic() + 60, out)
    return out


@app.get("/host/my-listings")
def my_listings(authorization: Optional[str] = Header(None)):
    """Returns every listing owned by the LOGGED-IN host's host_id, across all
    markets - the 'my listings' portfolio view. Requires a host session;
    host_id is taken from the authenticated user, not a hardcoded default,
    so this genuinely reflects whoever is logged in rather than always
    showing the same demo host regardless of who's signed in."""
    user = auth.get_user_from_token(auth.extract_bearer_token(authorization))
    if not user or user.role != "host":
        raise HTTPException(401, "Host login required")

    session = get_session()
    # Excludes listings with no picture_url in the archive, matching what
    # guest search already does (_unique_image_listing_ids, above) - a host
    # shouldn't see pricing controls for a listing that's invisible to guests
    # anyway. Deliberately NOT the same query as guest search though: this
    # only checks picture_url is present, it doesn't dedupe by distinct URL
    # like guest search does - a host's own listings that happen to share a
    # photo are still real, separate listings and should all show up here.
    listings = session.query(Listing).filter(
        Listing.host_id == user.host_id,
        Listing.picture_url.isnot(None),
        Listing.picture_url != "",
    ).all()
    out = [{
        "id": l.id, "host_id": l.host_id, "market": l.market.name, "market_id": l.market_id, "currency": l.market.currency,
        "name": l.name, "picture_url": l.picture_url, "property_type": l.property_type,
        "neighbourhood": l.neighbourhood,
        "room_type": l.room_type, "accommodates": l.accommodates, "host_is_superhost": l.host_is_superhost,
        "review_scores_rating": l.review_scores_rating, "min_floor": l.min_floor, "max_ceiling": l.max_ceiling,
        "auto_apply": l.auto_apply,
    } for l in listings]
    session.close()
    return out


def _require_listing_owner(session, listing_id: int, authorization: Optional[str]):
    """Confirms the request carries a valid host session AND that host
    actually owns this listing, before allowing a pricing mutation. Without
    this, any client could set or approve prices on a listing that isn't
    theirs just by knowing its numeric id.

    Returns (listing, user) - callers that need to further restrict what a
    demo login (user.is_demo) can do use the returned user instead of
    re-authenticating themselves. See /pricing/approve and
    /listings/{id}/price-year for how each uses it."""
    user = auth.get_user_from_token(auth.extract_bearer_token(authorization))
    if not user or user.role != "host":
        raise HTTPException(401, "Host login required")
    listing = session.query(Listing).get(listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.host_id != user.host_id:
        raise HTTPException(403, "You don't own this listing")
    return listing, user


@app.post("/listings/{listing_id}/price-year")
def price_year(listing_id: int, days_ahead: int = MAX_HOST_CALENDAR_DAYS, authorization: Optional[str] = Header(None)):
    """Prices a single listing across a long horizon (a full year by default) -
    used by the host year-calendar view. Runs synchronously; ~3s for 365
    nights for one listing (verified), since base-price inference happens once
    per call rather than once per night.

    A demo login (user.is_demo - see seed_demo_accounts.py) has its
    days_ahead silently capped to DEMO_PRICE_YEAR_MAX_DAYS. These are shared,
    publicly-documented credentials sitting on real archive-backed listings,
    and an uncapped call here can fire hundreds of live external event/news
    API calls (see external_signals.py's module docstring, which documents a
    real production incident caused by exactly this call pattern) for date
    ranges the nightly cron hasn't warmed yet. The response's days_ahead and
    demo_capped fields reflect what was actually applied, so a capped call
    is visible to the caller rather than silently different from what was
    requested."""
    if not 1 <= days_ahead <= MAX_HOST_CALENDAR_DAYS:
        raise HTTPException(400, f"days_ahead must be between 1 and {MAX_HOST_CALENDAR_DAYS}")
    session = get_session()
    listing, user = _require_listing_owner(session, listing_id, authorization)
    session.close()
    demo_capped = user.is_demo and days_ahead > DEMO_PRICE_YEAR_MAX_DAYS
    if user.is_demo:
        days_ahead = min(days_ahead, DEMO_PRICE_YEAR_MAX_DAYS)
    try:
        price_single_listing(listing_id, days_ahead=days_ahead)
    except ValueError:
        raise HTTPException(404, "Listing not found")
    return {"status": "ok", "listing_id": listing_id, "days_ahead": days_ahead, "demo_capped": demo_capped}


@app.get("/listings/card-prices")
def listing_card_prices(listing_ids: str, days: int = 7):
    """Returns guest-safe average prices for several listing cards at once."""
    if not 1 <= days <= 14:
        raise HTTPException(400, "days must be between 1 and 14")
    try:
        ids = [int(value) for value in listing_ids.split(",") if value.strip()]
    except ValueError:
        raise HTTPException(400, "listing_ids must be a comma-separated list of integers")
    if not ids or len(ids) > 100:
        raise HTTPException(400, "listing_ids must contain between 1 and 100 IDs")

    session = get_session()
    today = datetime.date.today()
    rows = session.query(CalendarDay, Listing.min_floor).join(
        Listing, Listing.id == CalendarDay.listing_id
    ).filter(
        CalendarDay.listing_id.in_(ids),
        CalendarDay.date >= today,
        CalendarDay.date < today + datetime.timedelta(days=days),
    ).all()
    prices: dict[int, list[float]] = {listing_id: [] for listing_id in ids}
    for row, floor in rows:
        prices[row.listing_id].append(row.live_price if row.live_price is not None else floor)
    session.close()
    return {
        str(listing_id): sum(values) / len(values)
        for listing_id, values in prices.items()
        if values
    }


@app.get("/listings/{listing_id}")
def get_listing(listing_id: int):
    session = get_session()
    l = session.query(Listing).get(listing_id)
    if not l:
        session.close()
        raise HTTPException(404, "Listing not found")
    out = {
        "id": l.id, "host_id": l.host_id, "host_name": l.host_name, "market": l.market.name, "currency": l.market.currency,
        "name": l.name, "description": l.description, "host_location": l.host_location,
        "neighbourhood": l.neighbourhood, "property_type": l.property_type,
        "amenities": l.amenities, "house_rules": l.house_rules, "picture_url": l.picture_url,
        "minimum_nights": l.minimum_nights, "maximum_nights": l.maximum_nights,
        "instant_bookable": l.instant_bookable,
        "room_type": l.room_type, "accommodates": l.accommodates, "bedrooms": l.bedrooms,
        "bathrooms": l.bathrooms, "dist_to_center_km": l.dist_to_center_km,
        "host_is_superhost": l.host_is_superhost, "review_scores_rating": l.review_scores_rating,
        "num_reviews": l.num_reviews, "min_floor": l.min_floor, "max_ceiling": l.max_ceiling,
        "auto_apply": l.auto_apply,
    }
    session.close()
    return out


@app.get("/listings")
def list_listings(market_id: Optional[int] = None, limit: int = 24, offset: int = 0):
    if not 1 <= limit <= 100:
        raise HTTPException(400, "limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(400, "offset must be non-negative")
    session = get_session()
    q = session.query(Listing).filter(Listing.id.in_(_unique_image_listing_ids(session, market_id)))
    if market_id:
        q = q.filter(Listing.market_id == market_id)
    listings = q.order_by(Listing.id).offset(offset).limit(limit).all()
    out = [{
        "id": l.id, "host_id": l.host_id, "host_name": l.host_name, "market": l.market.name, "currency": l.market.currency,
        "name": l.name, "property_type": l.property_type, "neighbourhood": l.neighbourhood,
        "picture_url": l.picture_url, "room_type": l.room_type, "accommodates": l.accommodates,
        "host_is_superhost": l.host_is_superhost, "review_scores_rating": l.review_scores_rating,
        "num_reviews": l.num_reviews, "min_floor": l.min_floor, "max_ceiling": l.max_ceiling, "auto_apply": l.auto_apply,
    } for l in listings]
    session.close()
    return out


@app.get("/search-cards")
def search_cards(market_id: int, guests: int = 1, limit: int = 12, offset: int = 0):
    """Returns filtered guest cards and their safe display prices in one read."""
    if guests < 1 or not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(400, "invalid guest, limit, or offset")
    session = get_session()
    listings = session.query(Listing).filter(
        Listing.id.in_(_unique_image_listing_ids(session, market_id)),
        Listing.market_id == market_id,
        Listing.accommodates >= guests,
    ).order_by(Listing.id).offset(offset).limit(limit).all()
    ids = [listing.id for listing in listings]
    today = datetime.date.today()
    rows = session.query(CalendarDay, Listing.min_floor).join(
        Listing, Listing.id == CalendarDay.listing_id
    ).filter(
        CalendarDay.listing_id.in_(ids or [-1]),
        CalendarDay.date >= today,
        CalendarDay.date < today + datetime.timedelta(days=7),
    ).all()
    prices: dict[int, list[float]] = {listing_id: [] for listing_id in ids}
    for row, floor in rows:
        prices[row.listing_id].append(row.live_price if row.live_price is not None else floor)
    out = [{
        "id": listing.id, "host_id": listing.host_id, "host_name": listing.host_name,
        "market": listing.market.name, "currency": listing.market.currency,
        "name": listing.name, "property_type": listing.property_type,
        "neighbourhood": listing.neighbourhood, "picture_url": listing.picture_url,
        "room_type": listing.room_type, "accommodates": listing.accommodates,
        "host_is_superhost": listing.host_is_superhost,
        "review_scores_rating": listing.review_scores_rating, "num_reviews": listing.num_reviews,
        "min_floor": listing.min_floor, "max_ceiling": listing.max_ceiling,
        "auto_apply": listing.auto_apply,
        "nightly_price": sum(prices[listing.id]) / len(prices[listing.id])
        if prices[listing.id] else None,
    } for listing in listings]
    session.close()
    return out


@app.get("/listings/{listing_id}/calendar")
def listing_calendar(listing_id: int, days: int = MAX_HOST_CALENDAR_DAYS):
    if not 1 <= days <= MAX_HOST_CALENDAR_DAYS:
        raise HTTPException(400, f"days must be between 1 and {MAX_HOST_CALENDAR_DAYS}")
    session = get_session()
    listing = session.query(Listing).get(listing_id)
    if not listing:
        session.close()
        raise HTTPException(404, "Listing not found")

    today = datetime.date.today()
    rows = session.query(CalendarDay).filter(
        CalendarDay.listing_id == listing_id,
        CalendarDay.date >= today,
        CalendarDay.date < today + datetime.timedelta(days=days),
    ).order_by(CalendarDay.date).all()

    out = [{
        "date": r.date.isoformat(), "base_model_price": r.base_model_price,
        "event_modifier_pct": r.event_modifier_pct, "news_modifier_pct": r.news_modifier_pct,
        "seasonal_modifier_pct": r.seasonal_modifier_pct, "recommended_price": r.recommended_price,
        "live_price": r.live_price, "status": r.status, "explanation": r.explanation,
        "is_booked": r.is_booked,
    } for r in rows]
    session.close()
    return out


@app.post("/pricing/run")
def trigger_pricing_run(days_ahead: int = 14, authorization: Optional[str] = Header(None)):
    """Runs a pricing cycle across every listing/market. Guarded by
    CRON_SECRET like /admin/retrain-and-fix-guardrails below - this was
    previously left open, callable by anyone who found the URL, and with no
    bound on days_ahead a single unauthenticated request could force a full
    365-day repricing across every listing. Default dropped from 365 to 14 to
    match what the nightly cron actually asks for (see
    nightly-pricing/route.ts); the host year-view has its own dedicated,
    ownership-checked endpoint (/listings/{id}/price-year) for the 365-day
    case."""
    _require_cron_secret(authorization)
    if not 1 <= days_ahead <= MAX_HOST_CALENDAR_DAYS:
        raise HTTPException(400, f"days_ahead must be between 1 and {MAX_HOST_CALENDAR_DAYS}")
    run_pricing_cycle(days_ahead=days_ahead)
    return {"status": "ok", "days_ahead": days_ahead}


@app.post("/admin/retrain-and-fix-guardrails")
def retrain_and_fix_guardrails(authorization: Optional[str] = Header(None)):
    """Retrains each market's pricing model on current listing data, then
    recomputes every listing's floor/ceiling guardrail from the freshly
    retrained model's own predicted base price (same 0.65x/1.8x rule as
    fix_guardrails.py), then reprices the near-term calendar so guests see
    the new guardrails right away instead of waiting on the next nightly
    /pricing/run to happen to fire after this one.

    Deliberately NOT on the nightly schedule: nothing about the model
    changes between calls unless it's retrained, so running this nightly
    would just recompute identical guardrails for no benefit. Meant to be
    triggered monthly (or on demand) - see claude/deployment-scheduling-guide.md.

    Guarded by CRON_SECRET, same as /pricing/run - retraining is materially
    more expensive than a normal pricing run (refits a RandomForest per
    market) and rewrites model files on disk, so it's worth keeping this
    behind the same check even though both endpoints are now locked down."""
    _require_cron_secret(authorization)

    # Returns {market_name: {"algorithm": "RandomForest"|"XGBoost", "r2": ..., "mae": ...,
    # "r2_by_algorithm": {...}, ...}} - train_all_markets() now fits both candidates per
    # market and keeps whichever wins on test-set R2 (see pricing_model.py), so this
    # response is how to see which one won without digging through Render's logs.
    training_results = train_all_markets()
    # load_market_model() is cached per worker process (see pricing_model.py's
    # @lru_cache) - without clearing it here, predict_base_price below would
    # keep returning predictions from the model loaded before this retrain,
    # silently defeating the point of retraining first.
    load_market_model.cache_clear()

    session = get_session()
    fixed = 0
    for market in session.query(Market).all():
        listings = session.query(Listing).filter_by(market_id=market.id).all()
        for listing in listings:
            base = predict_base_price(listing)
            listing.min_floor = round(base * 0.65, 2)
            listing.max_ceiling = round(base * 1.8, 2)
            fixed += 1
        session.commit()
    session.close()

    run_pricing_cycle(days_ahead=14)
    return {"status": "ok", "listings_fixed": fixed, "training_results": training_results}


class ApprovalRequest(BaseModel):
    listing_id: int
    date: datetime.date
    approve: bool
    override_price: Optional[float] = None


@app.get("/listings/{listing_id}/reviews")
def listing_reviews(listing_id: int, limit: int = 3):
    """Real guest-facing review excerpts (db.ReviewExcerpt) for the listing
    detail page - distinct from /review-insights below, which is the
    host-facing theme summary derived from the same underlying review text.
    This endpoint was missing entirely (the frontend has always called it,
    per lib/api.ts's `reviews()`, but there was no matching route here), so
    every listing page's fetch 404'd, was caught, and silently rendered
    "Real review excerpts are not available for this listing yet." even for
    listings with real stored excerpts. Returns available=False (not a 404)
    when a listing genuinely has zero stored excerpts - not every listing's
    reviews are present in the local Inside Airbnb snapshot, which is an
    expected data gap, not an error."""
    if not 1 <= limit <= 20:
        raise HTTPException(400, "limit must be between 1 and 20")
    session = get_session()
    listing = session.query(Listing).get(listing_id)
    if not listing:
        session.close()
        raise HTTPException(404, "Listing not found")

    rows = session.query(ReviewExcerpt).filter_by(listing_id=listing_id).order_by(
        ReviewExcerpt.review_date.desc()
    ).limit(limit).all()
    out = {
        "available": len(rows) > 0,
        "reviews": [{
            "reviewer_name": r.reviewer_name or "Guest",
            "date": r.review_date.isoformat() if r.review_date else None,
            "comments": r.comments,
            "source": r.source,
        } for r in rows],
    }
    session.close()
    return out


@app.get("/listings/{listing_id}/review-insights")
def review_insights(listing_id: int):
    """Host-facing recommendations derived from this listing's REAL guest
    review text (Inside Airbnb, not the Maven review export - which has no
    review text at all). Returns available=False with a clear reason when
    there's nothing to show, rather than fabricating a recommendation."""
    session = get_session()
    listing = session.query(Listing).get(listing_id)
    if not listing:
        session.close()
        raise HTTPException(404, "Listing not found")

    if listing.source_listing_id is None:
        session.close()
        return {
            "available": False,
            "reason": "This listing has no source_listing_id on file, so it can't be linked to real "
                      "review text. Run backfill_source_listing_id.py to enable this for existing listings.",
            "insights": [],
        }

    insights = session.query(ReviewInsight).filter_by(listing_id=listing_id).order_by(ReviewInsight.mention_count.desc()).all()
    if not insights:
        session.close()
        return {
            "available": False,
            "reason": "No review-based recommendations found. Either review_insights_loader.py hasn't been "
                      "run yet, or this listing's reviews didn't surface any common theme above the threshold.",
            "insights": [],
        }

    result = {
        "available": True,
        "insights": [{
            "theme": i.theme, "mention_count": i.mention_count,
            "total_reviews_scanned": i.total_reviews_scanned, "recommendation": i.recommendation,
            "specific_details": i.specific_details, "sample_review": i.sample_review,
        } for i in insights],
    }
    session.close()
    return result


@app.get("/listings/{listing_id}/market-comparison")
def market_comparison(listing_id: int):
    """Real historical host pricing (Inside Airbnb) for this listing's market and
    room type, alongside the model's current recommendation - answers 'how does
    this compare to what hosts have actually been charging nearby?'"""
    session = get_session()
    listing = session.query(Listing).get(listing_id)
    if not listing:
        session.close()
        raise HTTPException(404, "Listing not found")

    comp = session.query(MarketComparison).filter_by(
        market_id=listing.market_id, room_type=listing.room_type,
    ).first()

    latest_calendar = session.query(CalendarDay).filter(
        CalendarDay.listing_id == listing_id, CalendarDay.date >= datetime.date.today(),
    ).order_by(CalendarDay.date).first()

    result = {
        "listing_id": listing_id, "room_type": listing.room_type, "currency": listing.market.currency,
        "model_recommended_price": latest_calendar.recommended_price if latest_calendar else None,
        "actual_median_price": comp.actual_median_price if comp else None,
        "actual_mean_price": comp.actual_mean_price if comp else None,
        "sample_size": comp.sample_size if comp else 0,
        "source": comp.source if comp else None,
        "available": comp is not None,
    }
    session.close()
    return result


@app.post("/pricing/approve")
def approve_price(req: ApprovalRequest, authorization: Optional[str] = Header(None)):
    """Host control layer: approve, reject, or override a single night's recommended
    price. Requires a host session that actually owns this listing - now that
    guest bookings resolve their own price independently (see /bookings), this
    endpoint is exclusively a host action and is locked down accordingly.

    Demo logins (user.is_demo - see seed_demo_accounts.py) are blocked here
    entirely, rather than capped like /listings/{id}/price-year above: this
    endpoint WRITES the guest-facing live price for a real archive-backed
    listing, and demo credentials are published in the repo so anyone can
    log in as them. A cap doesn't fix that kind of exposure - only refusing
    the mutation does."""
    session = get_session()
    listing, user = _require_listing_owner(session, req.listing_id, authorization)
    if user.is_demo:
        session.close()
        raise HTTPException(403, "Demo accounts are read-only - pricing approvals are disabled for demo logins.")

    row = session.query(CalendarDay).filter_by(listing_id=req.listing_id, date=req.date).first()
    if not row:
        session.close()
        raise HTTPException(404, "Calendar day not found")

    if req.approve:
        row.live_price = req.override_price if req.override_price is not None else row.recommended_price
        row.status = "approved" if req.override_price is None else "host_override"
    else:
        row.status = "rejected"
        row.live_price = None  # a rejected night has no live/set price - a stale approval or
                                # override from before must not linger and look "live" to guests

    session.commit()
    result = {"date": row.date.isoformat(), "status": row.status, "live_price": row.live_price}
    session.close()
    return result


class BookingRequest(BaseModel):
    listing_id: int
    date: datetime.date


@app.post("/bookings")
def create_booking(req: BookingRequest, authorization: Optional[str] = Header(None)):
    """Books a night at its resolved guest-facing price: the host's approved
    or set price if one exists, otherwise the host's own floor price - same
    approved/set/floor rule the rest of the guest UI uses (never an
    unconfirmed recommendation).

    Requires a logged-in guest session. This previously allowed anonymous
    booking ("keeps the demo frictionless" per the original design), but
    that meant anyone with no account at all could POST any listing_id/date
    pair and mark it booked - listing IDs are sequential and enumerable via
    /listings, so this was scriptable into marking every night of every
    listing "booked" site-wide with zero credentials, a real denial-of-
    availability risk against the core product. Guest login is required now
    so a booking is at minimum tied to an accountable identity, and a night
    that's already booked can no longer be silently overwritten by a second
    request (see the is_booked check below) - previously a second POST for
    the same listing/date would quietly steal or corrupt an existing
    booking's guest_user_id and booked_price."""
    user = auth.get_user_from_token(auth.extract_bearer_token(authorization))
    if not user or user.role != "guest":
        raise HTTPException(401, "Guest login required to book")
    if req.date < datetime.date.today():
        raise HTTPException(400, "Cannot book a date in the past")

    session = get_session()
    row = session.query(CalendarDay).filter_by(listing_id=req.listing_id, date=req.date).first()
    if not row:
        session.close()
        raise HTTPException(404, "No pricing found for this listing/date - has it been priced yet?")
    if row.is_booked:
        session.close()
        raise HTTPException(409, "This night is already booked")

    resolved_price = row.live_price if row.live_price is not None else row.listing.min_floor
    row.is_booked = True
    row.booked_price = resolved_price
    row.guest_user_id = user.id
    session.commit()
    result = {"listing_id": req.listing_id, "date": req.date.isoformat(), "booked_price": row.booked_price}
    session.close()
    return result


@app.get("/guest/my-trips")
def my_trips(authorization: Optional[str] = Header(None)):
    """Every booking made by the logged-in guest - the real, visible payoff of
    guest login: without it, a booking is anonymous and can't be looked back
    up anywhere in the product."""
    user = auth.get_user_from_token(auth.extract_bearer_token(authorization))
    if not user or user.role != "guest":
        raise HTTPException(401, "Guest login required")

    session = get_session()
    bookings = session.query(CalendarDay).filter_by(guest_user_id=user.id, is_booked=True).order_by(CalendarDay.date).all()
    out = [{
        "listing_id": b.listing_id, "market": b.listing.market.name, "currency": b.listing.market.currency,
        "room_type": b.listing.room_type, "date": b.date.isoformat(), "booked_price": b.booked_price,
    } for b in bookings]
    session.close()
    return out
