"use client";

import { useEffect, useState } from "react";
import { api, ListingSummary } from "@/lib/api";
import { photosForListing, stockPhotoSrc } from "@/lib/photos";
import { hostNameForHost } from "@/lib/hosts";

export default function HostListingsPage() {
  const [listings, setListings] = useState<ListingSummary[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.myListings().then(setListings).catch(() => setError(true));
  }, []);

  return (
    <div className="listing-page">
      <header className="border-b border-[var(--lp-border)]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <a href="/" className="flex items-center gap-2">
            <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
              <circle cx="13" cy="13" r="12" stroke="#c9714a" strokeWidth="1.5" />
              <path d="M13 6 L19 18 H7 Z" fill="#21867a" opacity="0.85" />
            </svg>
            <span className="font-display text-xl italic">airbnb lite</span>
            <span className="ml-1 rounded-full border border-[var(--lp-teal)]/40 px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--lp-teal)]">Host console</span>
          </a>
          <a href="/" className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 text-sm transition hover:shadow-[0_1px_4px_rgba(34,32,27,0.08)]">
            View live site
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <p className="font-display text-3xl">Your listings</p>
        <p className="mt-1 text-sm text-[var(--lp-text-muted)]">Every property you host, across every market. Select one to manage its pricing.</p>

        {error && (
          <p className="mt-6 text-sm text-[var(--lp-text-muted)]">Can&apos;t reach the pricing API. Start it with: uvicorn main:app --reload</p>
        )}

        {listings && listings.length === 0 && (
          <p className="mt-6 text-sm text-[var(--lp-text-muted)]">No listings found for this host account.</p>
        )}

        <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {listings?.map((l) => {
            const photo = photosForListing(l.id)[0];
            return (
              <a
                key={l.id}
                href={`/host/listings/${l.id}`}
                className="block overflow-hidden rounded-xl border border-[var(--lp-border)] bg-[var(--lp-surface)] transition hover:shadow-[0_4px_16px_rgba(34,32,27,0.08)]"
              >
                <img src={stockPhotoSrc(photo.id, 500)} alt={photo.label} className="h-36 w-full object-cover" loading="lazy" />
                <div className="p-4">
                  <p className="text-sm font-medium">{l.room_type} &middot; {l.market}</p>
                  <p className="mt-0.5 text-xs text-[var(--lp-text-muted)]">
                    Sleeps {l.accommodates} &middot; Hosted by {hostNameForHost(l.host_id)}{l.host_is_superhost ? " · Superhost" : ""}
                  </p>
                  <p className="mt-2 font-mono text-xs text-[var(--lp-teal)]">
                    {l.currency} {l.min_floor.toLocaleString()}&ndash;{l.max_ceiling.toLocaleString()} range
                  </p>
                </div>
              </a>
            );
          })}
        </div>
      </main>
    </div>
  );
}
