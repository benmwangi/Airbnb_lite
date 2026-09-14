"use client";

import { useEffect, useState } from "react";
import { api, ReviewExcerpt } from "@/lib/api";

export function HostCard({ name, superhost, city, hostLocation }: { name: string; superhost: boolean; city: string; hostLocation: string | null }) {
  return (
    <div className="flex items-center gap-4">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--lp-terracotta-dim)] font-display text-xl text-[var(--lp-terracotta)]">
        {name.charAt(0)}
      </div>
      <div>
        <p className="font-medium">Hosted by {name}</p>
        <p className="text-sm text-[var(--lp-text-muted)]">
          {superhost ? "Superhost · " : ""}Based in {hostLocation || city}
        </p>
      </div>
    </div>
  );
}

const AMENITIES = [
  "Fast wifi", "Fully-equipped kitchen", "Free parking on premises", "Air conditioning",
  "Washer & dryer", "Dedicated workspace", "Pool access", "Smoke alarm",
];

export function AmenityGrid({ amenities }: { amenities: string | null | undefined }) {
  const values = amenities
    ? amenities.replace(/[{}"]/g, "").split(",").map((value) => value.trim()).filter(Boolean)
    : [];
  return (
    <div className="grid grid-cols-2 gap-y-3 text-sm">
      {values.length ? values.map((a) => (
        <div key={a} className="flex items-center gap-3">
          <span className="text-[var(--lp-teal)]">✓</span>
          <span>{a}</span>
        </div>
      )) : <p className="text-[var(--lp-text-muted)]">Amenities are not available for this listing.</p>}
    </div>
  );
}

export function HouseRules({ minFloor, maxCeiling, currency, rules, minimumNights, maximumNights }: { minFloor: number; maxCeiling: number; currency: string; rules: string | null | undefined; minimumNights: number | null | undefined; maximumNights: number | null | undefined }) {
  return (
    <div className="grid grid-cols-2 gap-6 text-sm">
      <div>
        <p className="text-[var(--lp-text-muted)]">Check-in</p>
        <p className="mt-0.5 font-medium">{minimumNights ? `${minimumNights} night minimum` : "Not specified"}</p>
      </div>
      <div>
        <p className="text-[var(--lp-text-muted)]">Checkout</p>
        <p className="mt-0.5 font-medium">{maximumNights ? `${maximumNights} night maximum` : "Not specified"}</p>
      </div>
      <div className="col-span-2">
        <p className="text-[var(--lp-text-muted)]">House rules</p>
        <ul className="mt-1 space-y-1 font-medium">
          <li className="whitespace-pre-line">{rules || "No house rules provided"}</li>
        </ul>
      </div>
      <div className="col-span-2 rounded-lg border border-[var(--lp-border)] bg-[var(--lp-teal-dim)] px-4 py-3">
        <p className="text-[var(--lp-text-muted)]">Pricing guardrail</p>
        <p className="mt-0.5 font-medium text-[var(--lp-teal)]">
          Nightly rate never set below {currency} {minFloor.toLocaleString()} or above {currency} {maxCeiling.toLocaleString()}, host-configured.
        </p>
      </div>
    </div>
  );
}

export function ReviewsSection({ listingId, rating, count }: { listingId: number; rating: number; count: number }) {
  const [reviews, setReviews] = useState<ReviewExcerpt[]>([]);
  const [available, setAvailable] = useState(true);

  useEffect(() => {
    api.reviews(listingId).then((data) => {
      setReviews(data.reviews);
      setAvailable(data.available);
    }).catch(() => {
      setReviews([]);
      setAvailable(false);
    });
  }, [listingId]);

  return (
    <div>
      <p className="font-display text-xl">★ {(rating / 20).toFixed(1)} · {count} reviews</p>
      {available ? (
        <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-3">
          {reviews.map((review) => (
            <div key={`${review.reviewer_name}-${review.date ?? review.comments}`}>
              <p className="text-sm font-medium">{review.reviewer_name}</p>
              <p className="mt-1 text-sm leading-relaxed text-[var(--lp-text-muted)] whitespace-pre-line">{review.comments}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-[var(--lp-text-muted)]">
          Real review excerpts are not available for this listing yet.
        </p>
      )}
    </div>
  );
}
