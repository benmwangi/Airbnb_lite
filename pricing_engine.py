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

PERFORMANCE NOTE: run_pricing_cycle batches its database reads per-market
instead of per (listing, date) pair. For N listings priced over D days, the
original code issued O(N*D) queries - a signals lookup, a "yesterday's price"
lookup, and an existence check, all inside price_listing_for_date, once per
listing-night. This version issues O(D) signal lookups plus a handful of
bulk CalendarDay/previous-price queries per market, then walks listings and
dates entirely in memory. price_listing_for_date() still supports being
called standalone (as price_single_listing() does) by falling back to its
original per-call lookups when the batched inputs aren't supplied, so
behavior for that caller is unchanged.
"""
import time
import datetime
from functools import lru_cache
import numpy as np
import pandas as pd
from db import get_session, Listing, CalendarDay, Market, ExternalSignalCache
from pricing_model import predict_base_price, load_market_model, BASE_NUMERIC_COLUMNS
from external_signals import fetch_event_signal, fetch_news_signal, OPENWEBNINJA_API_KEY, NEWSAPI_KEY

WEIGHTS = {"event": 0.30, "news": 0.15, "seasonality": 0.20}
MAX_NIGHT_OVER_NIGHT_CHANGE_PCT = 0.15   # guardrail: no more than +/-15% vs previous night's price

# Delay before each REAL (non-cached) OpenWeb Ninja call after the first one in
# a get_or_fetch_signals_batch run. A host's full-year price view can trigger
# up to 365 of these in a single request with nothing else pacing them - on
# 2026-09-14/15 that burst tripped OpenWeb Ninja's rate limit (429, then
# read timeouts) even on the Pro plan's 10,000-requests/month quota, because a
# generous monthly ceiling doesn't by itself prevent a per-minute/per-second
# burst limit from being hit. This keeps a 365-call batch under ~3.3
# requests/sec, which is the cheap, proactive half of the fix;
# external_signals.py's _request_with_retry is the reactive half for whatever
# still slips through despite the pacing.
EVENT_FETCH_PACING_SECONDS = 0.3

# After this many CONSECUTIVE OpenWeb Ninja failures within one
# get_or_fetch_signals_batch run, stop calling it for the rest of that
# batch's stale dates - see 2026-09-15's production crash: with retries (up
# to 3 attempts x 15s timeout each) paid on EVERY stale date while the
# endpoint was fully down, a run with several stale dates held its one DB
# session open for minutes doing nothing but timing out, long enough that
# Neon killed the idle connection out from under it (pool_pre_ping/
# pool_recycle in db.py only protect a connection being freshly checked OUT
# of the pool - not one already checked out and just sitting idle mid-batch)
# and the eventual flush crashed with "SSL connection has been closed
# unexpectedly". Tripping the breaker after 2 straight failures bounds a
# fully-down run to roughly 2 dates' worth of retry time instead of
# len(dates) x worst-case, at the cost of a few dates staying "..._error"
# for one extra pricing run before being retried (see _cache_is_stale - they
# ARE retried next time, this isn't a permanent skip).
EVENT_CIRCUIT_BREAKER_THRESHOLD = 2

# Flush every this-many real fetches within one batch, instead of only once
# at the very end - so a batch that does eventually hit the same dead-
# connection failure loses at most this many rows' worth of work, not the
# whole run, and so the DB connection gets touched periodically rather than
# sitting untouched for the entire batch.
SIGNAL_BATCH_FLUSH_EVERY = 5


def seasonality_modifier(date: datetime.date) -> float:
    weekend_lift = 0.07 if date.weekday() in (4, 5) else 0.0   # Fri/Sat
    summer_lift = 0.08 if date.month in (6, 7, 8) else 0.0
    return weekend_lift + summer_lift


def _cache_is_stale(cached: ExternalSignalCache) -> bool:
    """A row cached before OPENWEBNINJA_API_KEY/NEWSAPI_KEY were configured
    would otherwise be reused forever - `source` records exactly what
    fetch_event_signal/fetch_news_signal used at fetch time (see
    _create_signal_cache_row: "{event_source}+{news_source}"), so comparing
    it against whichever keys are CURRENTLY set tells us whether a key was
    added since this row was cached and it needs a real fetch now. Also
    catches rows cached back when this used PredictHQ (source starting with
    "predicthq") - those are stale under an OpenWeb Ninja key too, since
    that key was never used to produce them."""
    event_source, _, news_source = cached.source.partition("+")
    event_stale = bool(OPENWEBNINJA_API_KEY) and event_source != "openwebninja"
    news_stale = bool(NEWSAPI_KEY) and news_source != "newsapi"
    return event_stale or news_stale


def get_or_fetch_signals(session, market: Market, date: datetime.date):
    """Single-date lookup, kept for callers (like price_single_listing) that
    only ever need one date at a time. run_pricing_cycle uses
    get_or_fetch_signals_batch instead to avoid one query per date per
    listing."""
    cached = session.query(ExternalSignalCache).filter_by(market_id=market.id, date=date).first()
    if cached and not _cache_is_stale(cached):
        return cached
    return _create_signal_cache_row(session, market, date, existing=cached)


@lru_cache(maxsize=256)
def _cached_news_signal(market_id: int, market_name: str, as_of: datetime.date):
    """Wraps fetch_news_signal so it's called AT MOST ONCE per (market, day)
    for the life of this process, no matter how many pricing dates or
    listings end up asking for it. See fetch_news_signal's docstring: the
    underlying NewsAPI query is the same regardless of which future night is
    being priced, so calling it once per date - as this used to do inside
    _create_signal_cache_row - would multiply API usage by the number of
    nights/listings involved (e.g. price_single_listing's 365-night year view
    would otherwise fire 365 separate calls for one listing) and blow well
    past NewsAPI's 100-requests/day free-tier limit. The cache key naturally
    "expires" as `as_of` changes day to day, and clears on process restart -
    no manual invalidation needed."""
    return fetch_news_signal(market_name, as_of)


def get_or_fetch_signals_batch(session, market: Market, dates: list):
    """Returns {date: ExternalSignalCache} for every date in `dates`, issuing
    ONE query for all already-cached rows instead of one query per date.
    Only dates missing from the cache, or whose cached row is stale (see
    _cache_is_stale), trigger a fetch_event_signal call for that date (real
    events genuinely vary night to night) plus a _cached_news_signal call
    (memoized per market per day - see its docstring for why news does NOT
    vary per date the way events do), and those rows are flushed every
    SIGNAL_BATCH_FLUSH_EVERY real fetches (plus once more at the end for the
    remainder) rather than one flush per row or only one for the whole batch.

    A real fetch_event_signal call is paced EVENT_FETCH_PACING_SECONDS apart
    from the previous one in this same batch (see that constant's comment) -
    a large batch (e.g. a host's 365-night year view) would otherwise fire
    every OpenWeb Ninja call back-to-back with nothing throttling it, which is
    what tripped a 429 in production even on a generous monthly quota.

    If OpenWeb Ninja fails EVENT_CIRCUIT_BREAKER_THRESHOLD times in a row
    within this batch, the breaker trips: remaining stale dates skip the real
    fetch entirely (see _create_signal_cache_row's skip_event_fetch) instead
    of each paying the full retry+backoff cost against an endpoint that's
    already shown it's down. See that constant's comment for the production
    incident this fixes - a fully-down endpoint with retries enabled could
    previously hold this function's one DB session open for minutes doing
    nothing but timing out, long enough for Neon to close the idle
    connection out from under it."""
    existing = {
        row.date: row
        for row in session.query(ExternalSignalCache).filter(
            ExternalSignalCache.market_id == market.id,
            ExternalSignalCache.date.in_(dates),
        ).all()
    }
    result = {}
    fetch_count = 0
    unflushed_count = 0
    consecutive_event_failures = 0
    for date in dates:
        cached = existing.get(date)
        if cached is not None and not _cache_is_stale(cached):
            result[date] = cached
            continue

        breaker_tripped = consecutive_event_failures >= EVENT_CIRCUIT_BREAKER_THRESHOLD
        if fetch_count > 0 and not breaker_tripped:
            # Not the first real fetch in this batch - pace it behind the
            # previous one instead of firing every call back-to-back. No
            # point pacing a call the breaker is about to skip anyway.
            time.sleep(EVENT_FETCH_PACING_SECONDS)

        row = _create_signal_cache_row(
            session, market, date, flush=False, existing=cached,
            skip_event_fetch=breaker_tripped,
        )
        result[date] = row
        fetch_count += 1
        unflushed_count += 1

        event_source = row.source.partition("+")[0]
        if not breaker_tripped:
            # Only a REAL attempt updates the streak - a skipped date is
            # already-known-bad, not a new data point about OpenWeb Ninja's
            # current state.
            consecutive_event_failures = (
                consecutive_event_failures + 1 if event_source != "openwebninja" else 0
            )

        if unflushed_count >= SIGNAL_BATCH_FLUSH_EVERY:
            session.flush()
            unflushed_count = 0
    if unflushed_count > 0:
        session.flush()
    return result


def _create_signal_cache_row(session, market: Market, date: datetime.date, flush: bool = True,
                              existing: ExternalSignalCache = None, skip_event_fetch: bool = False):
    if skip_event_fetch:
        # Circuit breaker is open for this batch (see get_or_fetch_signals_batch) -
        # OpenWeb Ninja has already failed EVENT_CIRCUIT_BREAKER_THRESHOLD times in a
        # row, so don't pay another full retry+backoff cost finding that out again for
        # this date. Tagged "openwebninja_error" (not a new "circuit_open" tag) so
        # _cache_is_stale still treats this row as needing a real fetch on the NEXT
        # pricing run rather than getting stuck.
        event = {"lift_pct": 0.0,
                 "summary": "Skipped: OpenWeb Ninja failed repeatedly earlier in this run; no lift applied.",
                 "source": "openwebninja_error"}
    else:
        event = fetch_event_signal(market.name, market.center_lat, market.center_lng, date)
    # News is fetched via _cached_news_signal (memoized per market per day), not
    # fetch_news_signal directly - see that helper's docstring for why: news
    # isn't meaningfully different from one pricing date to the next the way a
    # real event is, and fetching it fresh per date would multiply NewsAPI
    # calls by the number of dates/listings being priced.
    news = _cached_news_signal(market.id, market.name, datetime.date.today())
    if existing is not None:
        # Refreshing a stale cached row in place, rather than inserting a second
        # row for the same (market_id, date) - that pair is UNIQUE-indexed (see
        # db.py), so a plain insert here would fail.
        existing.event_lift_pct = event["lift_pct"]
        existing.event_summary = event["summary"]
        existing.news_lift_pct = news["lift_pct"]
        existing.news_summary = news["summary"]
        existing.source = f'{event["source"]}+{news["source"]}'
        existing.fetched_at = datetime.datetime.utcnow()
        cached = existing
    else:
        cached = ExternalSignalCache(
            market_id=market.id, date=date,
            event_lift_pct=event["lift_pct"], event_summary=event["summary"],
            news_lift_pct=news["lift_pct"], news_summary=news["summary"],
            source=f'{event["source"]}+{news["source"]}',
        )
        session.add(cached)
    if flush:
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
    call instead of one per listing. Returns {listing_id: base_price}."""
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
    # dict(zip(...)) directly on the pandas Series / numpy array would keep
    # numpy.int64 keys and numpy.float64 values. psycopg2 has no adapter
    # registered for either by default - it silently stringifies the value
    # as "np.float64(...)" and inlines that INTO the SQL text rather than
    # binding it as a parameter, which Postgres then fails to parse (seen as
    # `InvalidSchemaName: schema "np" does not exist`). predict_base_price(),
    # the single-listing sibling of this function, already casts with
    # float(...) for the same reason - this just applies it batch-wide.
    return {int(listing_id): float(price) for listing_id, price in zip(rows["listing_id"], preds)}


def price_listing_for_date(
    session, listing: Listing, date: datetime.date, base_price: float = None,
    signals=None, previous_price=None, existing_row=None, _skip_lookups=False,
) -> CalendarDay:
    """Computes and persists the recommended price for one listing-night.

    signals / previous_price / existing_row are optional pre-fetched inputs
    used by run_pricing_cycle's batched path to avoid a query per call. When
    they're not supplied and _skip_lookups is False (the default, and what
    price_single_listing uses), this falls back to the original per-call
    lookups so standalone behavior is unchanged.
    """
    if base_price is None:
        base_price = predict_base_price(listing)
    base_price = float(base_price)  # defensive: guarantees a native float regardless of
    # caller - run_pricing_cycle passes base_prices.get(listing.id) from
    # batch_predict_base_prices() (see the fix there for why this matters),
    # and every arithmetic step below (target, final_price) inherits
    # base_price's type, so this one cast is enough to keep numpy scalars
    # out of the CalendarDay row psycopg2 ends up binding.

    if signals is None:
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

    if previous_price is None and not _skip_lookups:
        previous_day = session.query(CalendarDay).filter(
            CalendarDay.listing_id == listing.id,
            CalendarDay.date == date - datetime.timedelta(days=1),
        ).first()
        previous_price = previous_day.recommended_price if previous_day else None

    target = _apply_rate_of_change_guardrail(target, previous_price)
    # float(...) here too: Python's built-in round()/min()/max() preserve whatever
    # numeric type they're handed (round(numpy.float64, 2) is still numpy.float64),
    # so without base_price already being native (see the cast above) this could
    # still hand psycopg2 a numpy scalar even though it looks like an ordinary
    # round()/min()/max() expression.
    final_price = float(round(max(listing.min_floor, min(target, listing.max_ceiling)), 2))
    clamped = final_price in (listing.min_floor, listing.max_ceiling)

    explanation = build_explanation(
        market_name=listing.market.name, currency=listing.market.currency,
        base_price=base_price, event_contrib=event_contrib, event_summary=signals.event_summary,
        news_contrib=news_contrib, news_summary=signals.news_summary, season_contrib=season_contrib,
        date=date, clamped=clamped, floor=listing.min_floor, ceiling=listing.max_ceiling,
    )

    if existing_row is None and not _skip_lookups:
        existing_row = session.query(CalendarDay).filter_by(listing_id=listing.id, date=date).first()

    status = "auto_applied" if listing.auto_apply else "pending_approval"
    if existing_row:
        existing_row.base_model_price = base_price
        existing_row.event_modifier_pct = signals.event_lift_pct
        existing_row.news_modifier_pct = signals.news_lift_pct
        existing_row.seasonal_modifier_pct = season_mod
        existing_row.recommended_price = final_price
        existing_row.explanation = explanation
        if listing.auto_apply:
            existing_row.live_price = final_price
            existing_row.status = "auto_applied"
        row = existing_row
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
        sentences.append(
            f"Due to the event signal ({clean_summary}), it is recommended to {verb} the "
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
    """Prices every listing for the next `days_ahead` nights.

    Batches per-market work that used to happen per (listing, date):
      - base-price inference: one model.predict() call (already batched)
      - signal lookups: one query for the whole date range instead of one
        per listing-night (get_or_fetch_signals_batch)
      - "yesterday's price" lookups: one query per market for the day
        before the window starts, then tracked in memory while iterating
        forward through dates for each listing
      - existing CalendarDay rows: one bulk query per market for the whole
        window, used to decide insert vs. update without a query per night

    For N listings over D days this cuts DB round trips from roughly
    O(N*D) down to O(D) plus a few bulk queries per market.
    """
    session = get_session()
    market_q = session.query(Market)
    if market_id is not None:
        market_q = market_q.filter(Market.id == market_id)
    markets = market_q.all()
    today = datetime.date.today()
    dates = [today + datetime.timedelta(days=offset) for offset in range(days_ahead)]
    total = 0

    for market in markets:
        base_prices = batch_predict_base_prices(session, market.id)
        listings = session.query(Listing).filter(Listing.market_id == market.id).all()
        if not listings:
            continue
        listing_ids = [l.id for l in listings]

        # One query for every date's signal row instead of one per listing-night.
        signals_by_date = get_or_fetch_signals_batch(session, market, dates)

        # One query for "yesterday's" price per listing, instead of a
        # CalendarDay lookup inside every single price_listing_for_date call.
        day_before_window = dates[0] - datetime.timedelta(days=1)
        previous_prices = dict(
            session.query(CalendarDay.listing_id, CalendarDay.recommended_price)
            .filter(
                CalendarDay.listing_id.in_(listing_ids),
                CalendarDay.date == day_before_window,
            )
            .all()
        )

        # One bulk query for any CalendarDay rows that already exist in this
        # window, so each night is an in-memory insert-or-update decision
        # instead of a per-night existence check.
        existing_rows = {
            (row.listing_id, row.date): row
            for row in session.query(CalendarDay).filter(
                CalendarDay.listing_id.in_(listing_ids),
                CalendarDay.date.in_(dates),
            ).all()
        }

        for listing in listings:
            base_price = base_prices.get(listing.id)
            running_previous_price = previous_prices.get(listing.id)
            for date in dates:
                row = price_listing_for_date(
                    session, listing, date, base_price=base_price,
                    signals=signals_by_date[date],
                    previous_price=running_previous_price,
                    existing_row=existing_rows.get((listing.id, date)),
                    _skip_lookups=True,
                )
                running_previous_price = row.recommended_price
                total += 1

        session.commit()
        print(f"{market.name}: priced {len(listings)} listings x {days_ahead} nights")

    session.close()
    print(f"Priced {total} listing-nights total.")


def price_single_listing(listing_id: int, days_ahead: int = 365, start_date: datetime.date = None):
    """Prices ONE listing across a long horizon (a full year by default) - used
    by the host year-calendar view, where a host wants to see pricing across
    the whole year for just their own property, not every listing in the
    market. Computes the base price once (not per night) for speed.

    Uses the same batched signal-cache path as run_pricing_cycle (one cache
    query plus one flush for the whole date range, instead of one query and
    one flush per night) rather than the original per-date
    get_or_fetch_signals lookups. This is the only caller that can put up to
    `days_ahead` nights through a single request synchronously - run_pricing_cycle
    never prices more than 14 nights at a time - so the per-date DB round
    trips that were fine at 14 nights added real latency (and load on the
    Postgres connection pool) at 365. Note this does NOT reduce how many
    dates need a fresh fetch_event_signal call - a real per-night event
    check is inherent to covering new future dates - it only removes the
    redundant DB queries/flushes around it. A date range far beyond what's
    already cached can still hit the event API's rate limit partway through;
    that shows up as event_source "openwebninja_error" (lift_pct 0.0) on the
    affected nights rather than a full-request failure."""
    session = get_session()
    listing = session.query(Listing).get(listing_id)
    if not listing:
        session.close()
        raise ValueError(f"No listing with id {listing_id}")

    base_price = predict_base_price(listing)
    start = start_date or datetime.date.today()
    dates = [start + datetime.timedelta(days=offset) for offset in range(days_ahead)]

    signals_by_date = get_or_fetch_signals_batch(session, listing.market, dates)

    previous_day = session.query(CalendarDay).filter(
        CalendarDay.listing_id == listing.id,
        CalendarDay.date == dates[0] - datetime.timedelta(days=1),
    ).first()
    previous_price = previous_day.recommended_price if previous_day else None

    existing_rows = {
        row.date: row
        for row in session.query(CalendarDay).filter(
            CalendarDay.listing_id == listing.id,
            CalendarDay.date.in_(dates),
        ).all()
    }

    for date in dates:
        row = price_listing_for_date(
            session, listing, date, base_price=base_price,
            signals=signals_by_date[date],
            previous_price=previous_price,
            existing_row=existing_rows.get(date),
            _skip_lookups=True,
        )
        previous_price = row.recommended_price

    session.commit()
    session.close()
    print(f"Priced listing {listing_id} for {days_ahead} nights starting {start}.")


if __name__ == "__main__":
    run_pricing_cycle()
