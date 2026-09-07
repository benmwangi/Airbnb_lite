"use client";

import { useEffect, useState } from "react";
import { api, Market } from "@/lib/api";
import { SearchBar } from "@/components/landing/SearchBar";
import { photoForListing, stockPhotoSrc } from "@/lib/photos";

export default function LandingPage() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.markets().then(setMarkets).catch(() => setError(true));
  }, []);

  return (
    <div className="listing-page">
      <header className="border-b border-[var(--lp-border)]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
              <circle cx="13" cy="13" r="12" stroke="#c9714a" strokeWidth="1.5" />
              <path d="M13 6 L19 18 H7 Z" fill="#21867a" opacity="0.85" />
            </svg>
            <span className="font-display text-xl italic">airbnb lite</span>
          </div>
          <a href="/host" className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 text-sm transition hover:shadow-[0_1px_4px_rgba(34,32,27,0.08)]">
            Switch to hosting
          </a>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-6 pb-6 pt-14 text-center">
        <p className="font-display text-4xl leading-tight">Find your next stay</p>
        <p className="mt-2 text-[var(--lp-text-muted)]">Real listings, priced dynamically by market conditions.</p>

        <div className="mx-auto mt-8 max-w-3xl">
          {error ? (
            <p className="text-sm text-[var(--lp-text-muted)]">Can&apos;t reach the pricing API. Start it with: uvicorn main:app --reload</p>
          ) : (
            <SearchBar markets={markets} />
          )}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-10">
        <p className="mb-5 text-lg font-medium">Explore by destination</p>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {markets.map((m) => {
            const photo = photoForListing(m.id);
            return (
              <a key={m.id} href={`/search?market=${m.id}`} className="group block">
                <div className="overflow-hidden rounded-xl">
                  <img
                    src={stockPhotoSrc(photo.id, 400)}
                    alt={m.name}
                    className="h-32 w-full object-cover transition duration-300 group-hover:scale-105"
                    loading="lazy"
                  />
                </div>
                <p className="mt-2 text-sm font-medium">{m.name}</p>
                <p className="text-xs text-[var(--lp-text-muted)]">{m.listing_count} stays &middot; {m.currency}</p>
              </a>
            );
          })}
        </div>
      </section>
    </div>
  );
}
