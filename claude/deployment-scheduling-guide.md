# Airbnblite — free deployment & overnight scheduling guide

_A concrete, step-by-step plan for deploying Airbnblite on free infrastructure with all
background maintenance jobs running automatically. Captures the reasoning from a Sept 2026
planning conversation — see that thread for the underlying research on why each platform
was chosen over its free-tier alternatives. **Status: implemented** — `vercel.json`, both
cron routes, and the `main.py` changes below are already in the repo, not just drafts._

## The stack

| Piece | Where | Why |
|---|---|---|
| Next.js frontend | Vercel (Hobby, free) | Native fit for Next.js; also doubles as the free cron trigger |
| FastAPI backend | Render (free Web Service) | Free, but spins down after 15 min idle (~1 min cold start) and wipes local disk on every spin-down |
| PostgreSQL | Neon (free) | Never pauses/deletes the database on inactivity — only suspends compute, resumes in milliseconds. Render's own free Postgres expires 30 days after creation and is deleted after a 14-day grace period; Supabase pauses whole projects after 7 days of low activity |
| Scheduling | Vercel Cron Jobs (free, Hobby) | Up to 100 cron jobs/project, minimum interval once/day, ±59 min timing window on Hobby — fine for overnight jobs |

Env vars needed: `DATABASE_URL` (Neon connection string) on Render; `NEXT_PUBLIC_API_URL`
(Render's URL) and `CRON_SECRET` (a random 16+ char string) on Vercel; the same `CRON_SECRET`
value also set on Render so the backend can verify calls came from the real cron, not a
stranger who found the URL.

**Render cold-start gotcha specific to this project:** trained models
(`models/market_<id>.joblib`) live on local disk, which Render's free tier wipes on every
spin-down. Fixed in `main.py`'s `@app.on_event("startup")` hook: it now checks whether every
market's joblib file is still on disk, and only calls `train_all_markets()` when one is
actually missing — so a Render cold start retrains transparently, while local dev (where
`models/` already exists from a previous run) isn't slowed down by retraining on every
`--reload` restart.

## What actually needs to run overnight — and what doesn't

Only one job genuinely needs to run every night: **bulk pricing refresh**
(`run_pricing_cycle`, already exposed as `POST /pricing/run?days_ahead=14`). Guest search and
card pricing only ever look 7 days ahead, so 14 days is a comfortable buffer — no need to
regenerate a full year for every listing nightly (that's the exact blow-up the README warns
about at full-archive scale).

**Guardrail correction** (`fix_guardrails.py`) and **model retraining**
(`pricing_model.train_all_markets`) are a different kind of task. Guardrails only go stale
when the model's predicted base price changes, and nothing in this deployment retrains the
model on its own — so putting them on the same nightly clock as pricing would just recompute
identical numbers every night for no reason. The honest schedule: bundle retrain + guardrail
fix into one much less frequent job (monthly is a reasonable default, or purely on-demand if
you never plan to retrain on fresh data), and only if you actually want the model to adapt
over time.

**Review insights** (`review_insights_loader`/`insideairbnb_loader.py`) aren't a time-based
job at all in this project — they're derived from the static Inside Airbnb archive snapshot,
so they only need to rerun when you load a newer archive export, not on any recurring clock.

**External signal cache** (event/news modifiers) needs no separate schedule either — the
nightly pricing run already calls `get_or_fetch_signals_batch` internally, which keeps it
warm as a side effect.

## Setting it up

### 1. `vercel.json` (two cron entries, one nightly, one monthly)

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "crons": [
    { "path": "/api/cron/nightly-pricing", "schedule": "0 20 * * *" },
    { "path": "/api/cron/monthly-maintenance", "schedule": "0 20 1 * *" }
  ]
}
```

Both run at 8pm UTC (`0 20 * * *`) — the monthly one additionally only on the 1st of the
month. Vercel may invoke anywhere within that hour on Hobby (per their own docs), so treat
it as "sometime between 20:00 and 20:59 UTC" rather than exact. Convert 20:00 UTC to your
own local time zone if you want to reason about it as "overnight" there.

Because both crons can legitimately land in the same hour on the 1st of the month, there's
no guaranteed ordering between them — but it doesn't matter here: the maintenance endpoint
(below) already reprices at the end of its own run, so whichever one fires "first" doesn't
leave stale guardrails sitting around until the next night.

### 2. `app/api/cron/nightly-pricing/route.ts`

```ts
import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const cronSecret = process.env.CRON_SECRET;
  if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
    return new NextResponse("Unauthorized", { status: 401 });
  }

  const res = await fetch(`${API_URL}/pricing/run?days_ahead=14`, { method: "POST" });
  if (!res.ok) {
    return NextResponse.json({ error: `pricing run failed: ${res.status}` }, { status: 502 });
  }
  return NextResponse.json(await res.json());
}
```

This follows Vercel's own documented cron-security pattern: set `CRON_SECRET` as an env var
and Vercel automatically sends it as `Authorization: Bearer <CRON_SECRET>` when it invokes
the route, so the route can verify the call is really from Vercel's scheduler.

`run_pricing_cycle` already upserts by `(listing_id, date)`, so this is safely idempotent —
important because Vercel's own docs are explicit that cron delivery is best-effort: a run can
occasionally be skipped or (rarely) invoked twice, and cron jobs should tolerate both without
side effects. Nothing extra is needed here to satisfy that; the existing upsert behavior
already covers it.

### 3. `app/api/cron/monthly-maintenance/route.ts`

Same shape, pointed at a new backend endpoint (below) instead of `/pricing/run`:

```ts
import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const cronSecret = process.env.CRON_SECRET;
  if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
    return new NextResponse("Unauthorized", { status: 401 });
  }

  const res = await fetch(`${API_URL}/admin/retrain-and-fix-guardrails`, {
    method: "POST",
    headers: { Authorization: `Bearer ${cronSecret}` },
  });
  if (!res.ok) {
    return NextResponse.json({ error: `maintenance run failed: ${res.status}` }, { status: 502 });
  }
  return NextResponse.json(await res.json());
}
```

### 4. New backend endpoint — now in `main.py`

`/pricing/run` already existed and needed no change. `main.py` now also has
`POST /admin/retrain-and-fix-guardrails`, which retrains every market
(`pricing_model.train_all_markets`), recomputes every listing's floor/ceiling from the
freshly retrained model (same 0.65x/1.8x rule as `fix_guardrails.py`), and finishes by
repricing the near-term calendar (`run_pricing_cycle(days_ahead=14)`) so guests see the new
guardrails immediately rather than waiting on the separate nightly cron to happen to fire
after this one.

One subtlety that would have been a real bug: `pricing_model.load_market_model` is
`@lru_cache`'d per worker process. Without clearing that cache right after
`train_all_markets()` writes the new joblib files, `predict_base_price` would keep quietly
returning predictions from the *old* model object still sitting in memory — completely
defeating the point of retraining first. The endpoint calls
`load_market_model.cache_clear()` between the two steps to avoid that.

Guarded by the same `CRON_SECRET` (checked as a bearer token), unlike `/pricing/run` which
is left open — retraining is materially more expensive and rewrites files on disk, so it
shouldn't be triggerable by anyone who finds the URL.

## Operational notes

- **Duration limits**: Vercel Hobby functions have a default execution cap well under a
  minute. At `--sample-per-market` scale (the mode this project's README already recommends
  for anything short of the full archive), a 14-day bulk pricing run across ~5,000 listings
  should finish well within that; if you ever load the full archive, budget for a longer
  `maxDuration` in `vercel.json`'s `functions` config, or split the cron into
  per-market calls.
- **No retries**: Vercel does not retry a failed cron invocation. Check the Cron Jobs logs
  in the Vercel dashboard occasionally, or add basic alerting (even a Slack webhook on the
  `502` branch above) if this needs to run unattended for a long stretch.
- **Concurrency**: both jobs are safe to double-fire (pricing upserts; the maintenance
  endpoint just recomputes the same numbers again), so no distributed lock is needed at this
  scale.
