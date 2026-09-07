"""
Pricing decision engine. Combines:
  - the per-market structural base price (pricing_model.py)
  - event and news modifiers (external_signals.py)
  - a seasonality modifier (weekend/summer lift)
  - host-configured floor/ceiling guardrails
  - a rate-of-change limit versus yesterday's price (fixes the "price can jump
    arbitrarily night to night" gap in the original pipeline.py)

Weights below are illustrative starting points, not backtested. Before trusting
them on real bookings, validate them against historical revenue outcomes -
see the README "Next steps" section.
"""
import datetime
import numpy as np
import pandas as pd
from db import get_session, Listing, CalendarDay, Market, ExternalSignalCache
from pricing_model import predict_base_price, load_market_model, BASE_NUMERIC_COLUMNS
from external_signals import fetch_event_signal, fetch_news_signal

WEIGHTS = {"event": 0.30, "news": 0.15, "seasonality": 0.20}
MAX_NIGHT_OVER_NIGHT_CHANGE_PCT = 0.15   # guardrail: no more than +/-15% vs previous night's price


def seasonality_modifier(date: datetime.date) -> float:
    weekend_lift = 0.07 if date.weekday() in (4, 5) else 0.0   # Fri/Sat
    summer_lift = 0.08 if date.month in (6, 7, 8) else 0.0
    return weekend_lift + summer_lift


def get_or_fetch_signals(session, market: Market, date: datetime.date):
    cached = session.query(ExternalSignalCache).filter_by(market_id=market.id, date=date).first()
    if cached:
        return cached

    event = fetch_event_signal(market.name, market.center_lat, market.center_lng, date)
    news = fetch_news_signal(market.name, date)
    cached = ExternalSignalCache(
        market_id=market.id, date=date,
        event_lift_pct=event["lift_pct"], event_summary=event["summary"],
        news_lift_pct=news["lift_pct"], news_summary=news["summary"],
        source=f'{event["source"]}+{news["source"]}',
    )
    session.add(cached)
    session.flush()
    return cached


def _apply_rate_of_change_guardrail(target_price, previous_price):
    if previous_price is None:
        return target_price
    lo = previous_price * (1 - MAX_NIGHT_OVER_NIGHT_CHANGE_PCT)
    hi = previous_price * (1 + MAX_NIGHT_OVER_NIGHT_CHANGE_PCT)
    return max(lo, min(target_price, hi))


def batch_predict_base_prices(session, market_id: int) -> dict:
    """Predicts base price for every listing in a market with ONE model.predict()
    call instead of one per listing. This is the fix for the real bottleneck found
    when timing the engine against the real dataset: per-listing inference (each
    building its own single-row DataFrame) was the dominant cost, not the DB.
    Returns {listing_id: base_price}."""
    bundle = load_market_model(market_id)
    model, feature_columns = bundle["model"], bundle["columns"]

    listings = session.query(Listing).filter(Listing.market_id == market_id).all()
    if not listings:
        return {}

    rows = pd.DataFrame([{
        "listing_id": l.id, "accommodates": l.accommodates, "bedrooms": l.bedrooms,
        "bathrooms": l.bathrooms, "dist_to_center_km": l.dist_to_center_km,
        "host_is_superhost": int(l.host_is_superhost), "review_scores_rating": l.review_scores_rating,
        "num_reviews": l.num_reviews, "room_type": l.room_type,
    } for l in listings])

    dummies = pd.get_dummies(rows, columns=["room_type"], prefix="room_type")
    for col in feature_columns:
        if col not in dummies.columns:
            dummies[col] = 0

    preds = np.expm1(model.predict(dummies[feature_columns]))
    return dict(zip(rows["listing_id"], preds))


def price_listing_for_date(session, listing: Listing, date: datetime.date, base_price: float = None) -> CalendarDay:
    if base_price is None:
        base_price = predict_base_price(listing)
    signals = get_or_fetch_signals(session, listing.market, date)
    season_mod = seasonality_modifier(date)
    aggressiveness_scale = 0.5 + listing.aggressiveness

    # Compute each component's ACTUAL contribution (after weighting and the
    # host's aggressiveness setting) separately, so the explanation can report
    # the real effective percentage for each reason - not the raw signal.
    event_contrib = signals.event_lift_pct * WEIGHTS["event"] * aggressiveness_scale
    news_contrib = signals.news_lift_pct * WEIGHTS["news"] * aggressiveness_scale
    season_contrib = season_mod * WEIGHTS["seasonality"] * aggressiveness_scale
    net_modifier = event_contrib + news_contrib + season_contrib

    target = base_price * (1 + net_modifier)

    previous_day = session.query(CalendarDay).filter(
        CalendarDay.listing_id == listing.id,
        CalendarDay.date == date - datetime.timedelta(days=1),
    ).first()
    previous_price = previous_day.recommended_price if previous_day else None

    target = _apply_rate_of_change_guardrail(target, previous_price)
    final_price = round(max(listing.min_floor, min(target, listing.max_ceiling)), 2)
    clamped = final_price in (listing.min_floor, listing.max_ceiling)

    explanation = build_explanation(
        market_name=listing.market.name, currency=listing.market.currency,
        base_price=base_price, event_contrib=event_contrib, event_summary=signals.event_summary,
        news_contrib=news_contrib, news_summary=signals.news_summary, season_contrib=season_contrib,
        date=date, clamped=clamped, floor=listing.min_floor, ceiling=listing.max_ceiling,
    )

    existing = session.query(CalendarDay).filter_by(listing_id=listing.id, date=date).first()
    status = "auto_applied" if listing.auto_apply else "pending_approval"
    if existing:
        existing.base_model_price = base_price
        existing.event_modifier_pct = signals.event_lift_pct
        existing.news_modifier_pct = signals.news_lift_pct
        existing.seasonal_modifier_pct = season_mod
        existing.recommended_price = final_price
        existing.explanation = explanation
        if listing.auto_apply:
            existing.live_price = final_price
            existing.status = "auto_applied"
        row = existing
    else:
        row = CalendarDay(
            listing_id=listing.id, date=date, base_model_price=base_price,
            event_modifier_pct=signals.event_lift_pct, news_modifier_pct=signals.news_lift_pct,
            seasonal_modifier_pct=season_mod, recommended_price=final_price,
            live_price=final_price if listing.auto_apply else None,
            status=status, explanation=explanation,
        )
        session.add(row)
    return row


def _direction_words(pct: float) -> tuple:
    """Returns (verb, magnitude_pct) - handles both increases and decreases,
    even though today's signals are mostly positive-only, so the wording stays
    correct if a future signal source ever returns a negative modifier."""
    return ("increase", pct) if pct >= 0 else ("decrease", -pct)


def build_explanation(market_name, currency, base_price, event_contrib, event_summary,
                       news_contrib, news_summary, season_contrib, date, clamped, floor, ceiling) -> str:
    """Builds a plain-English, reason-first explanation for the recommended price -
    e.g. 'Due to a nearby event, it is recommended to increase the nightly price by
    4.2%.' rather than a terse 'Events: +4.2%' fragment."""
    sentences = [f"This listing's typical nightly value in {market_name} is {currency} {base_price:,.2f}."]

    if abs(event_contrib) >= 0.001:
        verb, pct = _direction_words(event_contrib)
        clean_summary = event_summary.split(":", 1)[-1].strip().rstrip(".") if event_summary else "a nearby event"
        clean_summary = clean_summary[:1].lower() + clean_summary[1:]
        if "nearby" not in clean_summary.lower():
            clean_summary += " nearby"
        sentences.append(
            f"Due to {clean_summary}, it is recommended to {verb} the "
            f"nightly price by {pct*100:.1f}%."
        )

    if abs(news_contrib) >= 0.001:
        verb, pct = _direction_words(news_contrib)
        sentences.append(
            f"Travel-related news activity in {market_name} right now points to {'higher' if verb == 'increase' else 'lower'} "
            f"demand, so it is recommended to {verb} the nightly price by {pct*100:.1f}%."
        )

    if abs(season_contrib) >= 0.001:
        verb, pct = _direction_words(season_contrib)
        season_reason = "weekend" if date.weekday() in (4, 5) else "peak summer season"
        sentences.append(
            f"At this time of year ({season_reason}), bookings around {market_name} tend to "
            f"{'increase' if verb == 'increase' else 'slow down'}. It is recommended to {verb} the nightly "
            f"price by {pct*100:.1f}%."
        )

    if len(sentences) == 1:
        sentences.append(
            f"No unusual demand signals were found for this date, so the recommended price reflects "
            f"this listing's typical structural value."
        )

    if clamped:
        sentences.append(
            f"This recommendation was capped by your guardrail range ({currency} {floor:,.2f}"
            f"\u2013{currency} {ceiling:,.2f})."
        )

    return " ".join(sentences)


def run_pricing_cycle(days_ahead: int = 14, market_id: int = None):
    """Prices every listing for the next `days_ahead` nights. Batches base-price
    inference per market (see batch_predict_base_prices) so this scales to a real
    multi-thousand-listing dataset instead of only a single host's handful of
    listings. Pass market_id to price just one market (e.g. for an interactive
    dashboard 'run for this market' button)."""
    session = get_session()
    market_q = session.query(Market)
    if market_id is not None:
        market_q = market_q.filter(Market.id == market_id)
    markets = market_q.all()
    today = datetime.date.today()
    total = 0

    for market in markets:
        base_prices = batch_predict_base_prices(session, market.id)
        listings = session.query(Listing).filter(Listing.market_id == market.id).all()
        for listing in listings:
            base_price = base_prices.get(listing.id)
            for offset in range(days_ahead):
                date = today + datetime.timedelta(days=offset)
                price_listing_for_date(session, listing, date, base_price=base_price)
                total += 1
        session.commit()
        print(f"{market.name}: priced {len(listings)} listings x {days_ahead} nights")

    session.close()
    print(f"Priced {total} listing-nights total.")


def price_single_listing(listing_id: int, days_ahead: int = 365, start_date: datetime.date = None):
    """Prices ONE listing across a long horizon (a full year by default) - used
    by the host year-calendar view, where a host wants to see pricing across
    the whole year for just their own property, not every listing in the
    market. Computes the base price once (not per night) for speed."""
    session = get_session()
    listing = session.query(Listing).get(listing_id)
    if not listing:
        session.close()
        raise ValueError(f"No listing with id {listing_id}")

    base_price = predict_base_price(listing)
    start = start_date or datetime.date.today()
    for offset in range(days_ahead):
        date = start + datetime.timedelta(days=offset)
        price_listing_for_date(session, listing, date, base_price=base_price)
    session.commit()
    session.close()
    print(f"Priced listing {listing_id} for {days_ahead} nights starting {start}.")


if __name__ == "__main__":
    run_pricing_cycle()
