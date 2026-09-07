"""
Sources the two external factors identified: nearby events and relevant news.

Real integrations:
  - Events: PredictHQ Events API (https://www.predicthq.com) - purpose-built for
    demand/pricing use cases, not just a raw event calendar: it returns predicted
    attendance, spend and a relevance rank per event, which is what turns "there's
    a concert nearby" into an actual price modifier.
    Get a key at https://control.predicthq.com -> API Keys. Set PREDICTHQ_API_KEY.
  - News/demand volume: NewsAPI.org - simple headline search by keyword + date.
    Get a key at https://newsapi.org/register. Set NEWSAPI_KEY.

If no key is set (the default for this demo), each function falls back to a
seeded-but-deterministic synthetic signal so the rest of the pipeline still runs
end to end. The `source` field on every result tells you which path was used -
check that field before trusting a number in a real deployment.
"""
import os
import hashlib
import datetime
import requests

PREDICTHQ_API_KEY = os.environ.get("PREDICTHQ_API_KEY","HX4mqQ6Q7IvTulPKLapDTRjeAjT5L7e8kCxSfY0M")
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY","a15b328e-a1d3-4cbf-8ebf-08940044e50d")

PREDICTHQ_EVENTS_URL = "https://api.predicthq.com/v1/events/"
NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"


def _deterministic_unit(*parts) -> float:
    """Deterministic pseudo-random float in [0, 1) from arbitrary string parts,
    so synthetic fallback signals are stable across runs for the same market/date."""
    key = "|".join(str(p) for p in parts).encode()
    return int(hashlib.sha256(key).hexdigest(), 16) % 10_000 / 10_000


def fetch_event_signal(market_name: str, lat: float, lng: float, date: datetime.date) -> dict:
    """Returns {'lift_pct': float, 'summary': str, 'source': str}"""
    if PREDICTHQ_API_KEY:
        try:
            resp = requests.get(
                PREDICTHQ_EVENTS_URL,
                headers={"Authorization": f"Bearer {PREDICTHQ_API_KEY}"},
                params={
                    "within": f"5km@{lat},{lng}",
                    "active.gte": date.isoformat(),
                    "active.lte": date.isoformat(),
                    "rank.gte": 50,          # only events PredictHQ ranks as meaningfully impactful
                    "sort": "rank",
                    "limit": 5,
                },
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return {"lift_pct": 0.0, "summary": "No high-impact events nearby.", "source": "predicthq"}
            top = results[0]
            rank = top.get("rank", 50)
            lift = min(0.30, (rank - 50) / 150)  # scale PredictHQ rank into a price-lift cap
            names = ", ".join(e.get("title", "event") for e in results[:3])
            return {"lift_pct": round(lift, 3), "summary": f"Nearby: {names}", "source": "predicthq"}
        except requests.RequestException as e:
            return {"lift_pct": 0.0, "summary": f"PredictHQ fetch failed ({e}); no lift applied.",
                    "source": "predicthq_error"}

    # Synthetic fallback: deterministic per market/date, occasional larger "event weekend" spikes
    u = _deterministic_unit("events", market_name, date.isoformat())
    if u > 0.85:
        return {"lift_pct": round(0.12 + (u - 0.85) * 1.2, 3),
                "summary": "Synthetic: simulated high-impact event nearby.", "source": "synthetic"}
    return {"lift_pct": 0.0, "summary": "Synthetic: no notable event.", "source": "synthetic"}


def fetch_news_signal(market_name: str, date: datetime.date) -> dict:
    """Returns {'lift_pct': float, 'summary': str, 'source': str}"""
    if NEWSAPI_KEY:
        try:
            resp = requests.get(
                NEWSAPI_EVERYTHING_URL,
                params={
                    "q": f'"{market_name}" AND (tourism OR travel OR visitors)',
                    "from": date.isoformat(),
                    "to": date.isoformat(),
                    "language": "en",
                    "sortBy": "relevancy",
                    "apiKey": NEWSAPI_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            total = resp.json().get("totalResults", 0)
            # more travel-relevant coverage that day -> small positive demand signal
            lift = min(0.06, total / 500)
            return {"lift_pct": round(lift, 3), "summary": f"{total} relevant articles.", "source": "newsapi"}
        except requests.RequestException as e:
            return {"lift_pct": 0.0, "summary": f"NewsAPI fetch failed ({e}); no lift applied.",
                    "source": "newsapi_error"}

    u = _deterministic_unit("news", market_name, date.isoformat())
    lift = round(max(0.0, (u - 0.6) * 0.1), 3)
    return {"lift_pct": lift, "summary": "Synthetic: baseline news/demand volume.", "source": "synthetic"}
