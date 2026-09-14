"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { api, Market } from "@/lib/api";
import { SearchBar } from "@/components/landing/SearchBar";
import { GuestAuthNav } from "@/components/GuestAuthNav";

const LANDING_MARKET_LIMIT = 10;
const CITY_IMAGES: Record<string, string> = {
  Bangkok: "https://images.unsplash.com/photo-1508009603885-50cf7c579365?auto=format&fit=crop&w=400&q=60",
  "Cape Town": "https://images.unsplash.com/photo-1580060839134-75a5edca2e99?auto=format&fit=crop&w=400&q=60",
  "Hong Kong": "https://images.unsplash.com/photo-1536599018102-9f803c140fc1?auto=format&fit=crop&w=400&q=60",
  Istanbul: "https://images.unsplash.com/photo-1524231757912-21f4fe3a7200?auto=format&fit=crop&w=400&q=60",
  "Mexico City": "https://images.unsplash.com/photo-1518659526054-190340b32735?auto=format&fit=crop&w=400&q=60",
  "New York": "https://images.unsplash.com/photo-1485871981521-5b1fd3805eee?auto=format&fit=crop&w=400&q=60",
  Paris: "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=400&q=60",
  "Rio de Janeiro": "https://images.unsplash.com/photo-1483729558449-99ef09a8c325?auto=format&fit=crop&w=400&q=60",
  Rome: "https://images.unsplash.com/photo-1529260830199-42c24126f198?auto=format&fit=crop&w=400&q=60",
  Sydney: "https://images.unsplash.com/photo-1528072164453-f4e8ef0d475a?auto=format&fit=crop&w=400&q=60",
};

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
          <div className="flex items-center gap-4">
            <GuestAuthNav />
            <a href="/host" className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 text-sm transition hover:shadow-[0_1px_4px_rgba(34,32,27,0.08)]">
              Switch to hosting
            </a>
          </div>
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
          {markets.slice(0, LANDING_MARKET_LIMIT).map((m, index) => (
              <a key={m.id} href={`/search?market=${m.id}`} className="group block">
                <div className="relative h-32 overflow-hidden rounded-xl bg-[var(--lp-teal-dim)]">
                  <Image
                    src={CITY_IMAGES[m.name]}
                    alt={`${m.name} cityscape`}
                    fill
                    sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
                    className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
                    priority={index === 0}
                    loading={index === 0 ? "eager" : "lazy"}
                  />
                  <div className="absolute inset-0 bg-black/25" />
                  <span className="absolute inset-0 flex items-center justify-center text-sm font-medium text-white drop-shadow">
                    {m.name}
                  </span>
                </div>
                <p className="mt-2 text-sm font-medium">{m.name}</p>
                <p className="text-xs text-[var(--lp-text-muted)]">{m.listing_count} stays &middot; {m.currency}</p>
              </a>
          ))}
        </div>
      </section>
    </div>
  );
}
