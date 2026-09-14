"""
Sources the two external factors identified: nearby events and relevant news.

Real integrations:
  - Events: OpenWeb Ninja's Real-Time Events Search API
    (https://www.openwebninja.com/api/real-time-events-search). Previously this
    used PredictHQ (https://www.predicthq.com), which returned a predicted
    attendance/spend/rank per event; that key is no longer active, so PredictHQ
    has been removed rather than kept as a dead fallback. OpenWeb Ninja is a
    Google Events scrape instead: you search by free-text query ("Events in
    Austin") rather than a geo radius, and it returns no rank or
    predicted-attendance figure the way PredictHQ did.
    Get a key at openwebninja.com and set OPENWEBNINJA_API_KEY. Note that on
    that site each individual API needs its own subscription even though the
    key itself is account-wide - visit the API's page and subscribe (a free
    tier covers this) or every call 403s with "You are not subscribed to this
    API" regardless of how valid the key is.
    VERIFIED LIVE (2026-09-14, one real call against "Events in Paris"): the
    response envelope is a top-level `data` list, as assumed. However, every
    sampled event's `venue.latitude`/`venue.longitude` came back null - this
    API does not expose raw venue coordinates (only `full_address` and a
    Google `cid`/`map_link`). Earlier versions of this integration tried to
    haversine-filter events against the market's lat/lng using those fields;
    since they're always null, that filter would have silently discarded
    every real event and always fallen through to "no events found," with no
    error to reveal it. Proximity is therefore left entirely to the query
    text's own city-level scoping - coarser than PredictHQ's 5km radius, but
    it's what this data source can actually support. `lat`/`lng` stay as
    parameters (for call-site and synthetic-fallback signature compatibility)
    but are not used to filter results.
  - News/demand volume: NewsAPI.org - headline search by keyword over a rolling
    recent-days window, NOT per future night (see fetch_news_signal's
    docstring for why a per-date query can't work for a date that hasn't
    happened yet). Get a key at https://newsapi.org/register. Set NEWSAPI_KEY.

If no key is set (the default for this demo), each function falls back to a
seeded-but-deterministic synthetic signal so the rest of the pipeline still runs
end to end. The `source` field on every result tells you which path was used -
check that field before trusting a number in a real deployment.
"""
import os
import hashlib
import datetime
import requests
from dotenv import load_dotenv

# Loaded here too (not just in db.py) so this module reads the right keys
# even if something ever imports it before db.py - see db.py's own
# load_dotenv() comment for the full explanation and the .env.example file
# for what to put in .env. override=False (the default) means an explicit
# `$env:OPENWEBNINJA_API_KEY = "..."` in the shell always still wins.
load_dotenv()

OPENWEBNINJA_API_KEY = os.environ.get("OPENWEBNINJA_API_KEY", "")
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

OPENWEBNINJA_EVENTS_URL = "https://api.openwebninja.com/realtime-events-data/search-events"
NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"

# Used only by fetch_event_signal's synthetic fallback (no OPENWEBNINJA_API_KEY set)
# to name what KIND of event triggered a price lift, instead of one generic
# "high-impact event" phrase for every synthetic hit. See the fallback's own
# comment for why these are event categories rather than invented specific
# event/venue names.
SYNTHETIC_EVENT_TYPES = [
    "a simulated major concert",
    "a simulated large sports event",
    "a simulated citywide festival",
    "a simulated big conference",
    "a simulated public holiday weekend",
    "a simulated large trade show",
]


def _deterministic_unit(*parts) -> float:
    """Deterministic pseudo-random float in [0, 1) from arbitrary string parts,
    so synthetic fallback signals are stable across runs for the same market/date."""
    key = "|".join(str(p) for p in parts).encode()
    return int(hashlib.sha256(key).hexdigest(), 16) % 10_000 / 10_000


def fetch_event_signal(market_name: str, lat: float, lng: float, date: datetime.date) -> dict:
    """Returns {'lift_pct': float, 'summary': str, 'source': str}

    lat/lng are accepted for call-site compatibility (pricing_engine.py passes
    market.center_lat/center_lng, same as the old PredictHQ integration used)
    but are NOT used to filter OpenWeb Ninja results - see the module
    docstring for why: that API never returns real venue coordinates, so a
    distance filter against them can't actually work.
    """
    if OPENWEBNINJA_API_KEY:
        try:
            resp = requests.get(
                OPENWEBNINJA_EVENTS_URL,
                headers={"x-api-key": OPENWEBNINJA_API_KEY},
                # Location lives in the query text (Google Events-style search), not a
                # radius param - this is what scopes results to market_name at all.
                params={"query": f"Events in {market_name}"},
                timeout=10,
            )
            resp.raise_for_status()
            events = resp.json().get("data", [])  # confirmed live - see module docstring

            matching_on_date = []
            for event in events:
                start_raw = event.get("start_time") or event.get("start_time_utc") or ""
                try:
                    event_date = datetime.date.fromisoformat(start_raw[:10])
                except ValueError:
                    continue  # unparseable date - skip rather than guess it's a match
                if event_date == date:
                    matching_on_date.append(event)

            if not matching_on_date:
                return {"lift_pct": 0.0, "summary": "No events found.", "source": "openwebninja"}

            # No rank/predicted-attendance field like PredictHQ used to give us, so the
            # lift scales off how many qualifying events land on this date instead -
            # capped at 0.30, matching the old PredictHQ integration's cap so
            # pricing_engine.py sees the same range of values as before.
            lift = min(0.30, 0.10 * len(matching_on_date))
            names = ", ".join(e.get("name", "event") for e in matching_on_date[:3])
            return {"lift_pct": round(lift, 3), "summary": f"Nearby: {names}", "source": "openwebninja"}
        except requests.RequestException as e:
            return {"lift_pct": 0.0, "summary": f"OpenWeb Ninja fetch failed ({e}); no lift applied.",
                    "source": "openwebninja_error"}

    # Synthetic fallback: deterministic per market/date, occasional larger "event weekend" spikes.
    # A second, independently-salted deterministic draw ("event_type" vs. "events") picks which
    # KIND of event to name, so the same market/date always gets the same specific label instead
    # of every synthetic hit sharing one generic "high-impact event" phrase. Deliberately a
    # category ("a simulated major concert"), not an invented specific event/venue name - naming
    # a fake concert as if it were real would be misleading; naming the kind of event stays
    # specific while staying honest that it's simulated (see `source` on the returned dict).
    u = _deterministic_unit("events", market_name, date.isoformat())
    if u > 0.85:
        event_type_index = int(_deterministic_unit("event_type", market_name, date.isoformat()) * len(SYNTHETIC_EVENT_TYPES))
        event_type = SYNTHETIC_EVENT_TYPES[min(event_type_index, len(SYNTHETIC_EVENT_TYPES) - 1)]
        return {"lift_pct": round(0.12 + (u - 0.85) * 1.2, 3),
                "summary": f"Synthetic: {event_type} nearby.", "source": "synthetic"}
    return {"lift_pct": 0.0, "summary": "Synthetic: no notable event.", "source": "synthetic"}


NEWS_LOOKBACK_DAYS = 7  # how many trailing days of coverage fetch_news_signal looks at


def fetch_news_signal(market_name: str, as_of: datetime.date = None) -> dict:
    """Returns {'lift_pct': float, 'summary': str, 'source': str}

    Unlike fetch_event_signal, this is NOT meant to be called once per
    pricing date. NewsAPI's `from`/`to` filter by an article's PUBLICATION
    date, not by what date the article is "about" - so "how much travel news
    is there for night X" only makes sense when X is today or earlier.
    run_pricing_cycle prices nights from today out to `days_ahead` in the
    FUTURE, so a per-future-date query would be asking for articles published
    on dates that haven't happened yet - it can never return anything real.
    (The Developer/free plan also delays even TODAY's articles by ~24 hours,
    so "today" isn't fully reliable either.) Callers should fetch this ONCE
    per market (see pricing_engine.py's _cached_news_signal) and apply the
    same lift to every date being priced, rather than once per date - besides
    matching what this data source can actually answer, that also keeps
    usage well under NewsAPI's 100-requests/day free-tier limit (calling it
    per date per listing could otherwise mean hundreds of calls for a single
    pricing run).

    as_of defaults to today; accepted as a parameter (rather than this
    function always calling datetime.date.today() itself) so a caller or
    test can pin a specific "now" instead of it silently drifting with
    wall-clock time.
    """
    as_of = as_of or datetime.date.today()
    if NEWSAPI_KEY:
        try:
            window_start = as_of - datetime.timedelta(days=NEWS_LOOKBACK_DAYS)
            resp = requests.get(
                NEWSAPI_EVERYTHING_URL,
                params={
                    "q": f'"{market_name}" AND (tourism OR travel OR visitors)',
                    "from": window_start.isoformat(),
                    "to": as_of.isoformat(),
                    "language": "en",
                    "sortBy": "relevancy",
                    "apiKey": NEWSAPI_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            total = resp.json().get("totalResults", 0)
            # more travel-relevant coverage recently -> small positive demand signal
            lift = min(0.06, total / 500)
            return {"lift_pct": round(lift, 3),
                    "summary": f"{total} relevant articles in the last {NEWS_LOOKBACK_DAYS} days.",
                    "source": "newsapi"}
        except requests.RequestException as e:
            return {"lift_pct": 0.0, "summary": f"NewsAPI fetch failed ({e}); no lift applied.",
                    "source": "newsapi_error"}

    u = _deterministic_unit("news", market_name, as_of.isoformat())
    lift = round(max(0.0, (u - 0.6) * 0.1), 3)
    return {"lift_pct": lift, "summary": "Synthetic: baseline news/demand volume.", "source": "synthetic"}
