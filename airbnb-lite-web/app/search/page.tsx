"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ListingSummary, Market } from "@/lib/api";
import { SearchBar } from "@/components/landing/SearchBar";
import { ListingCard } from "@/components/landing/ListingCard";
import { resolvedGuestPrice } from "@/lib/pricing-display";

const MAX_RESULTS = 24;

export default function SearchPage() {
  return (
    <Suspense fallback={null}>
      <SearchPageInner />
    </Suspense>
  );
}

function SearchPageInner() {
  const params = useSearchParams();
  const marketId = params.get("market") ? Number(params.get("market")) : null;
  const adults = Number(params.get("adults") ?? "1");
  const children = Number(params.get("children") ?? "0");
  const checkin = params.get("checkin");
  const checkout = params.get("checkout");
  const totalGuests = adults + children;

  const [markets, setMarkets] = useState<Market[]>([]);
  const [results, setResults] = useState<ListingSummary[]>([]);
  const [prices, setPrices] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [marketName, setMarketName] = useState<string>("");

  useEffect(() => {
    api.markets().then(setMarkets).catch(() => {});
  }, []);

  useEffect(() => {
    if (marketId == null) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    api.listings(marketId).then(async (all) => {
      setMarketName(all[0]?.market ?? "");
      const filtered = all.filter((l) => l.accommodates >= totalGuests).slice(0, MAX_RESULTS);
      setResults(filtered);

      const priceEntries = await Promise.all(
        filtered.map(async (l) => {
          try {
            const cal = await api.calendar(l.id, 7);
            const avg = cal.length ? cal.reduce((s, n) => s + resolvedGuestPrice(n, l.min_floor), 0) / cal.length : null;
            return [l.id, avg] as const;
          } catch {
            return [l.id, null] as const;
          }
        })
      );
      const priceMap: Record<number, number> = {};
      priceEntries.forEach(([id, p]) => { if (p != null) priceMap[id] = p; });
      setPrices(priceMap);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [marketId, totalGuests]);

  return (
    <div className="listing-page">
      <header className="border-b border-[var(--lp-border)]">
        <div className="mx-auto max-w-6xl px-6 py-4">
          <div className="mb-4 flex items-center justify-between">
            <a href="/" className="flex items-center gap-2">
              <svg width="24" height="24" viewBox="0 0 26 26" fill="none">
                <circle cx="13" cy="13" r="12" stroke="#c9714a" strokeWidth="1.5" />
                <path d="M13 6 L19 18 H7 Z" fill="#21867a" opacity="0.85" />
              </svg>
              <span className="font-display text-lg italic">airbnb lite</span>
            </a>
            <a href="/host" className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 text-sm">Switch to hosting</a>
          </div>
          <SearchBar markets={markets} />
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {marketId == null ? (
          <p className="text-[var(--lp-text-muted)]">Pick a destination above to see stays.</p>
        ) : (
          <>
            <p className="mb-1 font-display text-2xl">{marketName || "Stays"}</p>
            <p className="mb-6 text-sm text-[var(--lp-text-muted)]">
              {totalGuests} guest{totalGuests !== 1 ? "s" : ""}
              {checkin && checkout ? ` \u00B7 ${checkin} \u2192 ${checkout}` : ""}
              {" \u00B7 "}{results.length} stay{results.length !== 1 ? "s" : ""} found
            </p>

            {loading ? (
              <p className="text-sm text-[var(--lp-text-muted)]">Loading stays\u2026</p>
            ) : results.length === 0 ? (
              <p className="text-sm text-[var(--lp-text-muted)]">No stays match that many guests in this destination \u2014 try fewer guests or a different destination.</p>
            ) : (
              <div className="grid grid-cols-2 gap-x-6 gap-y-8 sm:grid-cols-3 lg:grid-cols-4">
                {results.map((l) => (
                  <ListingCard key={l.id} listing={l} nightlyPrice={prices[l.id] ?? null} />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
