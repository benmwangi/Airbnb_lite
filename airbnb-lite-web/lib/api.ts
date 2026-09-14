const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const HOST_CALENDAR_DAYS = 365;

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
  host_name?: string | null;
  name: string | null;
  description?: string | null;
  host_location?: string | null;
  neighbourhood?: string | null;
  property_type?: string | null;
  amenities?: string | null;
  house_rules?: string | null;
  picture_url?: string | null;
  minimum_nights?: number | null;
  maximum_nights?: number | null;
  instant_bookable?: boolean | null;
  market: string;
  currency: string;
  room_type: string;
  accommodates: number;
  host_is_superhost: boolean;
  review_scores_rating: number;
  num_reviews: number;
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

export type ReviewExcerpt = {
  reviewer_name: string;
  date: string | null;
  comments: string;
  source: string;
};

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status} on ${path}`);
  return res.json();
}

async function getJSONAuth<T>(path: string): Promise<T> {
  const { authHeaders } = await import("./auth");
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", headers: authHeaders() });
  if (!res.ok) throw new Error(`API error ${res.status} on ${path}`);
  return res.json();
}

let marketsCache: { value: Market[]; expiresAt: number } | null = null;
let marketsRequest: Promise<Market[]> | null = null;

export const api = {
  markets: () => {
    if (marketsCache && marketsCache.expiresAt > Date.now()) {
      return Promise.resolve(marketsCache.value);
    }
    if (!marketsRequest) {
      marketsRequest = getJSON<Market[]>("/markets")
        .then((value) => {
          marketsCache = { value, expiresAt: Date.now() + 30_000 };
          return value;
        })
        .finally(() => {
          marketsRequest = null;
        });
    }
    return marketsRequest;
  },
  reviewInsights: (listingId: number) =>
    getJSON<{ available: boolean; reason?: string; insights: { theme: string; mention_count: number; total_reviews_scanned: number; recommendation: string; specific_details: string | null; sample_review: string | null }[] }>(
      `/listings/${listingId}/review-insights`
    ),
  reviews: (listingId: number, limit = 3) =>
    getJSON<{ available: boolean; reviews: ReviewExcerpt[] }>(
      `/listings/${listingId}/reviews?limit=${limit}`
    ),
  listings: (marketId: number, limit = 24, offset = 0) =>
    getJSON<ListingSummary[]>(`/listings?market_id=${marketId}&limit=${limit}&offset=${offset}`),
  cardPrices: (listingIds: number[], days = 7) =>
    getJSON<Record<string, number>>(`/listings/card-prices?listing_ids=${listingIds.join(",")}&days=${days}`),
  searchCards: (marketId: number, guests: number, limit = 12, offset = 0) =>
    getJSON<(ListingSummary & { nightly_price: number | null })[]>(
      `/search-cards?market_id=${marketId}&guests=${guests}&limit=${limit}&offset=${offset}`
    ),
  listing: (listingId: number) => getJSON<ListingSummary & { id: number }>(`/listings/${listingId}`),
  myListings: () => getJSONAuth<ListingSummary[]>("/host/my-listings"),
  myTrips: () => getJSONAuth<{ listing_id: number; market: string; currency: string; room_type: string; date: string; booked_price: number }[]>("/guest/my-trips"),
  priceYear: async (listingId: number, daysAhead = HOST_CALENDAR_DAYS) => {
    const { authHeaders } = await import("./auth");
    const response = await fetch(`${API_URL}/listings/${listingId}/price-year?days_ahead=${daysAhead}`, {
      method: "POST", headers: authHeaders(),
    });
    if (!response.ok) throw new Error(`API error ${response.status} while generating pricing`);
    return response;
  },
  calendar: (listingId: number, days = HOST_CALENDAR_DAYS) =>
    getJSON<CalendarNight[]>(`/listings/${listingId}/calendar?days=${days}`),
  comparison: (listingId: number) =>
    getJSON<MarketComparison>(`/listings/${listingId}/market-comparison`),
  runPricing: (daysAhead = 14) =>
    fetch(`${API_URL}/pricing/run?days_ahead=${daysAhead}`, { method: "POST" }),
  approve: async (listingId: number, date: string, overridePrice?: number) => {
    const { authHeaders } = await import("./auth");
    return fetch(`${API_URL}/pricing/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        listing_id: listingId, date, approve: true,
        override_price: overridePrice ?? null,
      }),
    });
  },
  reject: async (listingId: number, date: string) => {
    const { authHeaders } = await import("./auth");
    return fetch(`${API_URL}/pricing/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ listing_id: listingId, date, approve: false }),
    });
  },
};
