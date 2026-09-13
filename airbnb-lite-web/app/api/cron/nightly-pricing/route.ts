import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Fired nightly by vercel.json's cron entry (0 20 * * * - 8pm UTC, ±59min on
// the Hobby plan). Just proxies to the backend's existing /pricing/run,
// which prices every listing across every market for the next 14 nights -
// enough to cover guest search/booking (which only ever look 7 days ahead;
// see main.py's search_cards/listing_card_prices), without regenerating a
// full year for every listing the way the host console's on-demand
// price-year view does. run_pricing_cycle upserts by (listing_id, date), so
// this route is safe to fire more than once if Vercel's best-effort cron
// delivery ever double-invokes it.
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
