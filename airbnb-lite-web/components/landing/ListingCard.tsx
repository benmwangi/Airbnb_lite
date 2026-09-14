"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ListingSummary } from "@/lib/api";

export function ListingCard({
  listing,
  nightlyPrice,
  onPhotoUnavailable,
}: {
  listing: ListingSummary;
  nightlyPrice: number | null;
  // Notifies the parent (search results grid) that this card has no photo to
  // show - either it never had one, or (same reasoning as Gallery.tsx) a
  // real archive picture_url turned out to be a dead link - so it can be
  // swapped out for a spare listing instead of leaving a photo-less card in
  // the results. Optional: other callers (e.g. a future non-search use of
  // this card) aren't required to handle backfill.
  onPhotoUnavailable?: (listingId: number) => void;
}) {
  const searchParams = useSearchParams();
  const [imageFailed, setImageFailed] = useState(false);
  const showPlaceholder = !listing.picture_url || imageFailed;

  useEffect(() => {
    // Fires at most once per card: either immediately on mount (no
    // picture_url at all) or the one time imageFailed flips true (onError) -
    // it never flips back, so this never double-reports the same listing.
    if (showPlaceholder) onPhotoUnavailable?.(listing.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showPlaceholder]);

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
        {showPlaceholder ? (
          <div className="flex h-56 w-full items-center justify-center bg-[var(--lp-teal-dim)] text-sm text-[var(--lp-teal)]">
            No photo available
          </div>
        ) : (
          <Image
            src={listing.picture_url as string}
            alt={listing.name || `${listing.room_type} in ${listing.market}`}
            width={640}
            height={448}
            className="h-56 w-full object-cover"
            loading="lazy"
            onError={() => setImageFailed(true)}
          />
        )}

        {/* Hover affordance - the whole card already links to the listing page
            (including a click anywhere on the image), so this is purely a
            visual cue making that discoverable. pointer-events-none so it
            never intercepts clicks meant for the carousel arrows/dots below. */}
        <div className="pointer-events-none absolute inset-0 flex items-end justify-center bg-black/25 pb-7 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
          <span className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-[var(--lp-text)] shadow-md">
            Click to view more
          </span>
        </div>

      </div>

      <div className="mt-2.5 flex items-start justify-between gap-2">
        <p className="text-sm font-medium leading-snug">
          {listing.name || `${listing.room_type} in ${listing.market}`}
        </p>
        <span className="shrink-0 text-sm">&#9733; {(listing.review_scores_rating / 20).toFixed(1)}</span>
      </div>
      <p className="text-sm text-[var(--lp-text-muted)]">{listing.property_type || listing.room_type} · {listing.neighbourhood || listing.market}</p>
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
