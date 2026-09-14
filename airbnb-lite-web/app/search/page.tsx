"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ListingSummary, Market } from "@/lib/api";
import { SearchBar } from "@/components/landing/SearchBar";
import { ListingCard } from "@/components/landing/ListingCard";
import { GuestAuthNav } from "@/components/GuestAuthNav";

const MAX_RESULTS = 12;
// Some archive picture_url values are dead links (scraped years ago), only
// detectable once the browser actually tries to load the image. Rather than
// leaving a "No photo available" card sitting in the results grid, this page
// over-fetches a handful of spares up front and swaps one in whenever a
// shown card's photo turns out to be missing or broken - see
// visibleResults/handlePhotoUnavailable below. A fixed, modest buffer (not a
// second network round-trip) keeps this from turning one page load into
// many: most listings' photos DO work, so a small reserve is normally more
// than enough, and the "stays found" count always reflects what's actually
// shown, never the larger fetched pool.
const RESULTS_BUFFER = 6;

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
  // The full over-fetched batch (MAX_RESULTS + RESULTS_BUFFER candidates),
  // not just what's currently shown - failedIds/visibleResults (below) pick
  // the first MAX_RESULTS of these that actually have a photo, backfilling
  // from the spares as failures come in.
  const [allResults, setAllResults] = useState<ListingSummary[]>([]);
  const [failedIds, setFailedIds] = useState<Set<number>>(new Set());
  const [prices, setPrices] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [marketName, setMarketName] = useState<string>("");

  const visibleResults = allResults.filter((l) => !failedIds.has(l.id)).slice(0, MAX_RESULTS);

  function handlePhotoUnavailable(listingId: number) {
    setFailedIds((prev) => (prev.has(listingId) ? prev : new Set(prev).add(listingId)));
  }

  useEffect(() => {
    api.markets().then(setMarkets).catch(() => {});
  }, []);

  useEffect(() => {
    if (marketId == null) {
      setAllResults([]);
      setFailedIds(new Set());
      setLoading(false);
      return;
    }
    setLoading(true);
    let cancelled = false;
    api.searchCards(marketId, totalGuests, MAX_RESULTS + RESULTS_BUFFER).then((cards) => {
      setMarketName(cards[0]?.market ?? "");
      const filtered = cards.map(({ nightly_price, ...listing }) => listing);
      if (cancelled) return;
      setAllResults(filtered);
      setFailedIds(new Set());

      const priceMap: Record<number, number> = {};
      cards.forEach((card) => {
        if (card.nightly_price != null) priceMap[card.id] = card.nightly_price;
      });
      setPrices(priceMap);
      setLoading(false);
    }).catch(() => setLoading(false));
    return () => { cancelled = true; };
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
            <div className="flex items-center gap-4">
              <GuestAuthNav />
              <a href="/host" className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 text-sm">Switch to hosting</a>
            </div>
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
              {" \u00B7 "}{visibleResults.length} stay{visibleResults.length !== 1 ? "s" : ""} found
            </p>

            {loading ? (
              <p className="text-sm text-[var(--lp-text-muted)]">Loading stays\u2026</p>
            ) : allResults.length === 0 ? (
              <p className="text-sm text-[var(--lp-text-muted)]">No stays match that many guests in this destination \u2014 try fewer guests or a different destination.</p>
            ) : (
              <div className="grid grid-cols-2 gap-x-6 gap-y-8 sm:grid-cols-3 lg:grid-cols-4">
                {visibleResults.map((l) => (
                  <ListingCard key={l.id} listing={l} nightlyPrice={prices[l.id] ?? null} onPhotoUnavailable={handlePhotoUnavailable} />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
