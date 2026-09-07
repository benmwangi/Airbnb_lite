"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { api, CalendarNight, ListingSummary } from "@/lib/api";
import { Gallery } from "@/components/listing/Gallery";
import { HostCard, AmenityGrid, HouseRules, ReviewsSection } from "@/components/listing/InfoSections";
import { GuestBookingPanel } from "@/components/listing/GuestBookingPanel";
import { hostNameForHost } from "@/lib/hosts";

export default function ListingPage() {
  return (
    <Suspense fallback={null}>
      <ListingPageInner />
    </Suspense>
  );
}

function daysNeeded(checkoutParam: string | null): number {
  if (!checkoutParam) return 30; // no dates chosen yet - give a reasonable default browsing window
  const checkout = new Date(checkoutParam + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.ceil((checkout.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
  return Math.min(400, Math.max(30, diffDays + 7)); // pad a week past checkout, cap at ~13 months
}

function ListingPageInner() {
  const params = useParams();
  const searchParams = useSearchParams();
  const listingId = Number(params.id);

  const [listing, setListing] = useState<ListingSummary | null>(null);
  const [nights, setNights] = useState<CalendarNight[]>([]);
  const [error, setError] = useState<string | null>(null);

  const checkinParam = searchParams.get("checkin");
  const checkoutParam = searchParams.get("checkout");

  useEffect(() => {
    if (!listingId) return;
    api.listing(listingId).then(setListing).catch(() => setError("api"));
    api.calendar(listingId, daysNeeded(checkoutParam)).then(setNights).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listingId, checkoutParam]);

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center text-center">
        <div>
          <p className="text-lg">Can&apos;t reach the pricing API.</p>
          <p className="mt-1 text-sm text-[var(--lp-text-muted)]">Start it with: uvicorn main:app --reload</p>
        </div>
      </div>
    );
  }

  if (!listing) return null;

  const hostName = hostNameForHost(listing.host_id);

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
          </a>
          <a href="/host" className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 text-sm">Switch to hosting</a>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <p className="font-display text-3xl">Sun-filled entire home with terrace, {listing.market}</p>
        <p className="mt-1 text-sm text-[var(--lp-text-muted)]">
          &#9733; {(listing.review_scores_rating / 20).toFixed(1)} &middot; {listing.review_scores_rating >= 99 ? "Superhost" : "Host"} &middot; {listing.market}
        </p>

        <div className="mt-5">
          <Gallery listingId={listingId} />
        </div>

        <div className="mt-10 grid grid-cols-1 gap-10 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <div className="border-b border-[var(--lp-border)] pb-6">
              <p className="text-lg font-medium">Entire home hosted by {hostName} &middot; {listing.accommodates} guests</p>
              <p className="mt-0.5 text-sm text-[var(--lp-text-muted)]">{listing.room_type} &middot; {listing.accommodates} guests</p>
            </div>

            <div className="border-b border-[var(--lp-border)] py-6">
              <HostCard name={hostName} superhost={listing.host_is_superhost} city={listing.market} />
            </div>

            <div className="border-b border-[var(--lp-border)] py-6 text-sm leading-relaxed text-[var(--lp-text-muted)]">
              A bright, quiet home a few minutes from the center of {listing.market}. Wake up to
              morning light on the terrace, cook in a fully-stocked kitchen, and settle in for the
              evening in a space designed for both short stays and longer ones. Close to local
              cafes, transit, and the neighborhood&apos;s best walking streets.
            </div>

            <div className="border-b border-[var(--lp-border)] py-6">
              <p className="mb-4 text-lg font-medium">What this place offers</p>
              <AmenityGrid />
            </div>

            <div className="border-b border-[var(--lp-border)] py-6">
              <ReviewsSection listingId={listingId} rating={listing.review_scores_rating} count={listing.review_scores_rating >= 99 ? 47 : 12} />
            </div>

            <div className="py-6">
              <p className="mb-4 text-lg font-medium">Things to know</p>
              <HouseRules minFloor={listing.min_floor} maxCeiling={listing.max_ceiling} currency={listing.currency} />
            </div>
          </div>

          <div>
            <GuestBookingPanel
              listingId={listingId}
              currency={listing.currency}
              nights={nights}
              checkin={checkinParam}
              checkout={checkoutParam}
              initialAdults={Number(searchParams.get("adults") ?? "1")}
              initialChildren={Number(searchParams.get("children") ?? "0")}
              initialInfants={Number(searchParams.get("infants") ?? "0")}
              maxGuests={listing.accommodates}
              floorPrice={listing.min_floor}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
