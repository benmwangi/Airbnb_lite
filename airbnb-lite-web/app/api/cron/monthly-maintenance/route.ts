import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Fired monthly by vercel.json's cron entry (0 20 1 * * - 8pm UTC on the 1st
// of each month). Unlike nightly-pricing, this hits an authenticated backend
// endpoint: retraining is materially more expensive than a pricing run and
// rewrites model files on disk, so it isn't left open the way /pricing/run
// is. The same CRON_SECRET used to authenticate THIS route (via Vercel's
// own cron-secret mechanism) is forwarded as the bearer token the backend
// checks - see main.py's retrain_and_fix_guardrails.
//
// Deliberately not nightly: nothing about the pricing model changes between
// calls unless it's retrained, so running this every night would just
// recompute identical guardrails for no benefit. See
// claude/deployment-scheduling-guide.md for the full reasoning.
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
