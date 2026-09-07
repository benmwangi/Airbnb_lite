"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { ListingSummary } from "@/lib/api";
import { photosForListing, stockPhotoSrc } from "@/lib/photos";
import { hostNameForHost } from "@/lib/hosts";

export function ListingCard({
  listing,
  nightlyPrice,
}: {
  listing: ListingSummary;
  nightlyPrice: number | null;
}) {
  const photos = photosForListing(listing.id);
  const [index, setIndex] = useState(0);
  const searchParams = useSearchParams();

  function go(delta: number, e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIndex((i) => (i + delta + photos.length) % photos.length);
  }

  // Carry the guest's search criteria (dates, guest counts) through to the
  // listing page - without this, clicking through from search results
  // silently drops everything the guest already told us and the listing
  // page falls back to defaults instead of reflecting their actual search.
  const forwardedParams = new URLSearchParams();
  ["checkin", "checkout", "adults", "children", "infants"].forEach((key) => {
    const value = searchParams.get(key);
    if (value) forwardedParams.set(key, value);
  });
  const query = forwardedParams.toString();
  const href = `/listing/${listing.id}${query ? `?${query}` : ""}`;

  return (
    <a href={href} className="group block">
      <div className="relative overflow-hidden rounded-xl">
        <img
          src={stockPhotoSrc(photos[index].id, 500)}
          alt={photos[index].label}
          className="h-56 w-full object-cover"
          loading="lazy"
        />

        {/* Hover affordance - the whole card already links to the listing page
            (including a click anywhere on the image), so this is purely a
            visual cue making that discoverable. pointer-events-none so it
            never intercepts clicks meant for the carousel arrows/dots below. */}
        <div className="pointer-events-none absolute inset-0 flex items-end justify-center bg-black/25 pb-7 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
          <span className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-[var(--lp-text)] shadow-md">
            Click to view more
          </span>
        </div>

        {photos.length > 1 && (
          <>
            <button
              onClick={(e) => go(-1, e)}
              aria-label="Previous photo"
              className="absolute left-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 text-[var(--lp-text)] opacity-0 shadow transition group-hover:opacity-100"
            >
              &lsaquo;
            </button>
            <button
              onClick={(e) => go(1, e)}
              aria-label="Next photo"
              className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 text-[var(--lp-text)] opacity-0 shadow transition group-hover:opacity-100"
            >
              &rsaquo;
            </button>

            <div className="absolute bottom-2 left-1/2 flex -translate-x-1/2 gap-1">
              {photos.map((p, i) => (
                <span
                  key={p.id}
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: i === index ? "white" : "rgba(255,255,255,0.5)" }}
                />
              ))}
            </div>
          </>
        )}
      </div>

      <div className="mt-2.5 flex items-start justify-between gap-2">
        <p className="text-sm font-medium leading-snug">
          {listing.room_type} in {listing.market}
        </p>
        <span className="shrink-0 text-sm">&#9733; {(listing.review_scores_rating / 20).toFixed(1)}</span>
      </div>
      <p className="text-sm text-[var(--lp-text-muted)]">Hosted by {hostNameForHost(listing.host_id)}</p>
      <p className="text-sm text-[var(--lp-text-muted)]">Sleeps {listing.accommodates}{listing.host_is_superhost ? " \u00B7 Superhost" : ""}</p>
      {nightlyPrice != null && (
        <p className="mt-1 text-sm">
          <span className="font-medium">{listing.currency} {Math.round(nightlyPrice).toLocaleString()}</span>
          <span className="text-[var(--lp-text-muted)]"> night</span>
        </p>
      )}
    </a>
  );
}
