"use client";

import { reviewsForListing } from "@/lib/reviews";

export function HostCard({ name, superhost, city }: { name: string; superhost: boolean; city: string }) {
  return (
    <div className="flex items-center gap-4">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--lp-terracotta-dim)] font-display text-xl text-[var(--lp-terracotta)]">
        {name.charAt(0)}
      </div>
      <div>
        <p className="font-medium">Hosted by {name}</p>
        <p className="text-sm text-[var(--lp-text-muted)]">
          {superhost ? "Superhost · " : ""}Based in {city} · Hosting since 2022
        </p>
      </div>
    </div>
  );
}

const AMENITIES = [
  "Fast wifi", "Fully-equipped kitchen", "Free parking on premises", "Air conditioning",
  "Washer & dryer", "Dedicated workspace", "Pool access", "Smoke alarm",
];

export function AmenityGrid() {
  return (
    <div className="grid grid-cols-2 gap-y-3 text-sm">
      {AMENITIES.map((a) => (
        <div key={a} className="flex items-center gap-3">
          <span className="text-[var(--lp-teal)]">✓</span>
          <span>{a}</span>
        </div>
      ))}
    </div>
  );
}

export function HouseRules({ minFloor, maxCeiling, currency }: { minFloor: number; maxCeiling: number; currency: string }) {
  return (
    <div className="grid grid-cols-2 gap-6 text-sm">
      <div>
        <p className="text-[var(--lp-text-muted)]">Check-in</p>
        <p className="mt-0.5 font-medium">After 3:00 PM</p>
      </div>
      <div>
        <p className="text-[var(--lp-text-muted)]">Checkout</p>
        <p className="mt-0.5 font-medium">Before 11:00 AM</p>
      </div>
      <div className="col-span-2">
        <p className="text-[var(--lp-text-muted)]">House rules</p>
        <ul className="mt-1 space-y-1 font-medium">
          <li>No smoking</li>
          <li>No parties or events</li>
          <li>Pets considered on request</li>
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
  const reviews = reviewsForListing(listingId);
  return (
    <div>
      <p className="font-display text-xl">★ {(rating / 20).toFixed(1)} · {count} reviews</p>
      <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-3">
        {reviews.map((r) => (
          <div key={r.name}>
            <p className="text-sm font-medium">{r.name}</p>
            <p className="mt-1 text-sm leading-relaxed text-[var(--lp-text-muted)]">{r.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
