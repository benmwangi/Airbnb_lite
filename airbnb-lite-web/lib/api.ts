const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Market = {
  id: number;
  name: string;
  country: string;
  currency: string;
  listing_count: number;
};

export type ListingSummary = {
  id: number;
  host_id: number;
  market: string;
  currency: string;
  room_type: string;
  accommodates: number;
  host_is_superhost: boolean;
  review_scores_rating: number;
  min_floor: number;
  max_ceiling: number;
  auto_apply: boolean;
};

export type CalendarNight = {
  date: string;
  base_model_price: number;
  event_modifier_pct: number;
  news_modifier_pct: number;
  seasonal_modifier_pct: number;
  recommended_price: number;
  live_price: number | null;
  status: "pending_approval" | "approved" | "host_override" | "rejected" | "auto_applied";
  explanation: string;
  is_booked: boolean;
};

export type MarketComparison = {
  listing_id: number;
  room_type: string;
  currency: string;
  model_recommended_price: number | null;
  actual_median_price: number | null;
  actual_mean_price: number | null;
  sample_size: number;
  source: string | null;
  available: boolean;
};

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status} on ${path}`);
  return res.json();
}

export const api = {
  markets: () => getJSON<Market[]>("/markets"),
  reviewInsights: (listingId: number) =>
    getJSON<{ available: boolean; reason?: string; insights: { theme: string; mention_count: number; total_reviews_scanned: number; recommendation: string }[] }>(
      `/listings/${listingId}/review-insights`
    ),
  listings: (marketId: number) => getJSON<ListingSummary[]>(`/listings?market_id=${marketId}`),
  listing: (listingId: number) => getJSON<ListingSummary & { id: number }>(`/listings/${listingId}`),
  myListings: () => getJSON<ListingSummary[]>("/host/my-listings"),
  priceYear: (listingId: number, daysAhead = 365) =>
    fetch(`${API_URL}/listings/${listingId}/price-year?days_ahead=${daysAhead}`, { method: "POST" }),
  calendar: (listingId: number, days = 14) =>
    getJSON<CalendarNight[]>(`/listings/${listingId}/calendar?days=${days}`),
  comparison: (listingId: number) =>
    getJSON<MarketComparison>(`/listings/${listingId}/market-comparison`),
  runPricing: (daysAhead = 14) =>
    fetch(`${API_URL}/pricing/run?days_ahead=${daysAhead}`, { method: "POST" }),
  approve: (listingId: number, date: string, overridePrice?: number) =>
    fetch(`${API_URL}/pricing/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        listing_id: listingId, date, approve: true,
        override_price: overridePrice ?? null,
      }),
    }),
  reject: (listingId: number, date: string) =>
    fetch(`${API_URL}/pricing/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ listing_id: listingId, date, approve: false }),
    }),
};
