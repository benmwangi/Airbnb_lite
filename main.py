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
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import init_db, get_session, Listing, CalendarDay, Market, MarketComparison, ReviewInsight
from pricing_engine import run_pricing_cycle, price_listing_for_date, price_single_listing

app = FastAPI(title="Airbnb-lite Dynamic Pricing API")

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
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/markets")
def list_markets():
    session = get_session()
    markets = session.query(Market).all()
    out = [{"id": m.id, "name": m.name, "country": m.country, "currency": m.currency,
            "listing_count": len(m.listings)} for m in markets]
    session.close()
    return out


@app.get("/host/my-listings")
def my_listings(host_id: int = 175128252):
    """Returns every listing owned by a given host_id, across all markets - the
    'my listings' portfolio view. Defaults to a real host_id from the Maven
    dataset (175128252) who genuinely owns 3 listings spanning 2 real markets
    (Cape Town and Sydney) - a real, not fabricated, multi-listing/multi-market
    host, used here as the demo logged-in host."""
    session = get_session()
    listings = session.query(Listing).filter_by(host_id=host_id).all()
    out = [{
        "id": l.id, "host_id": l.host_id, "market": l.market.name, "market_id": l.market_id, "currency": l.market.currency,
        "room_type": l.room_type, "accommodates": l.accommodates, "host_is_superhost": l.host_is_superhost,
        "review_scores_rating": l.review_scores_rating, "min_floor": l.min_floor, "max_ceiling": l.max_ceiling,
        "auto_apply": l.auto_apply,
    } for l in listings]
    session.close()
    return out


@app.post("/listings/{listing_id}/price-year")
def price_year(listing_id: int, days_ahead: int = 365):
    """Prices a single listing across a long horizon (a full year by default) -
    used by the host year-calendar view. Runs synchronously; ~3s for 365
    nights for one listing (verified), since base-price inference happens once
    per call rather than once per night."""
    try:
        price_single_listing(listing_id, days_ahead=days_ahead)
    except ValueError:
        raise HTTPException(404, "Listing not found")
    return {"status": "ok", "listing_id": listing_id, "days_ahead": days_ahead}


@app.get("/listings/{listing_id}")
def get_listing(listing_id: int):
    session = get_session()
    l = session.query(Listing).get(listing_id)
    if not l:
        session.close()
        raise HTTPException(404, "Listing not found")
    out = {
        "id": l.id, "host_id": l.host_id, "market": l.market.name, "currency": l.market.currency,
        "room_type": l.room_type, "accommodates": l.accommodates, "bedrooms": l.bedrooms,
        "bathrooms": l.bathrooms, "dist_to_center_km": l.dist_to_center_km,
        "host_is_superhost": l.host_is_superhost, "review_scores_rating": l.review_scores_rating,
        "num_reviews": l.num_reviews, "min_floor": l.min_floor, "max_ceiling": l.max_ceiling,
        "auto_apply": l.auto_apply,
    }
    session.close()
    return out


@app.get("/listings")
def list_listings(market_id: Optional[int] = None):
    session = get_session()
    q = session.query(Listing)
    if market_id:
        q = q.filter(Listing.market_id == market_id)
    listings = q.all()
    out = [{
        "id": l.id, "host_id": l.host_id, "market": l.market.name, "currency": l.market.currency,
        "room_type": l.room_type, "accommodates": l.accommodates,
        "host_is_superhost": l.host_is_superhost, "review_scores_rating": l.review_scores_rating,
        "min_floor": l.min_floor, "max_ceiling": l.max_ceiling, "auto_apply": l.auto_apply,
    } for l in listings]
    session.close()
    return out


@app.get("/listings/{listing_id}/calendar")
def listing_calendar(listing_id: int, days: int = 14):
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
def trigger_pricing_run(days_ahead: int = 14):
    run_pricing_cycle(days_ahead=days_ahead)
    return {"status": "ok", "days_ahead": days_ahead}


class ApprovalRequest(BaseModel):
    listing_id: int
    date: datetime.date
    approve: bool
    override_price: Optional[float] = None


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
def approve_price(req: ApprovalRequest):
    """Host control layer: approve, reject, or override a single night's recommended price."""
    session = get_session()
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
def create_booking(req: BookingRequest):
    """Simulates a guest booking a night at the current live price - this is what
    generates real feedback-loop data for retraining/backtesting."""
    session = get_session()
    row = session.query(CalendarDay).filter_by(listing_id=req.listing_id, date=req.date).first()
    if not row or row.live_price is None:
        session.close()
        raise HTTPException(400, "No live price set for this listing/date yet")

    row.is_booked = True
    row.booked_price = row.live_price
    session.commit()
    result = {"listing_id": req.listing_id, "date": req.date.isoformat(), "booked_price": row.booked_price}
    session.close()
    return result
