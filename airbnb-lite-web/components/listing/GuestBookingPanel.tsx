"use client";

import { useState } from "react";
import { api, CalendarNight } from "@/lib/api";
import { resolvedGuestPrice, nightsInStayRange } from "@/lib/pricing-display";
import { GuestPicker, GuestCounts } from "@/components/landing/GuestPicker";

export function GuestBookingPanel({
  listingId,
  currency,
  nights,
  checkin,
  checkout,
  initialAdults,
  initialChildren,
  initialInfants,
  maxGuests,
  floorPrice,
}: {
  listingId: number;
  currency: string;
  nights: CalendarNight[];
  checkin: string | null;
  checkout: string | null;
  initialAdults: number;
  initialChildren: number;
  initialInfants: number;
  maxGuests: number;
  floorPrice: number;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [selectedCheckin, setSelectedCheckin] = useState(checkin ?? nights[0]?.date ?? "");
  const [selectedCheckout, setSelectedCheckout] = useState(checkout ?? nights[nights.length - 1]?.date ?? "");
  const [guests, setGuests] = useState<GuestCounts>({
    adults: Math.max(1, initialAdults || 1),
    children: initialChildren || 0,
    infants: initialInfants || 0,
  });

  const checkinInRange = nights.some((n) => n.date === selectedCheckin);
  const checkoutInRange = nights.some((n) => n.date === selectedCheckout);
  const totalGuestsForCapacity = guests.adults + guests.children;
  const overCapacity = totalGuestsForCapacity > maxGuests;

  // The actual nights being booked, priced using only what's real to a guest:
  // an approved or host-set price, or the host's floor price as a safe
  // fallback - never the algorithm's unconfirmed recommendation.
  const stayNights = selectedCheckin && selectedCheckout && selectedCheckout > selectedCheckin
    ? nightsInStayRange(nights, selectedCheckin, selectedCheckout)
    : [];
  const nightlyPrices = stayNights.map((n) => resolvedGuestPrice(n, floorPrice));
  const totalPrice = nightlyPrices.reduce((s, p) => s + p, 0);
  const avgNightly = stayNights.length ? totalPrice / stayNights.length : floorPrice;
  const someUnconfirmed = stayNights.some((n) => n.live_price == null);
  const validRange = stayNights.length > 0;

  async function reserve() {
    if (!stayNights.length) return;
    try {
      // Approve every night in the stay so each has a real live_price before booking
      await Promise.all(stayNights.map((n) => api.approve(listingId, n.date)));
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/bookings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ listing_id: listingId, date: stayNights[0].date }),
      });
      if (res.ok) setConfirmed(true);
    } catch {
      // demo booking; ignore network errors here
    }
  }

  return (
    <div className="sticky top-6 rounded-2xl border border-[var(--lp-border)] bg-[var(--lp-surface)] p-6 shadow-[0_1px_2px_rgba(0,0,0,0.04),0_8px_24px_rgba(34,32,27,0.06)]">
      <p className="font-display text-2xl">
        {currency} {Math.round(avgNightly).toLocaleString()}
        <span className="ml-1 text-sm font-normal text-[var(--lp-text-muted)]">/ night</span>
      </p>
      <p className="mt-0.5 text-xs text-[var(--lp-text-muted)]">
        {someUnconfirmed
          ? "Some nights use this listing's floor price until the host confirms a final rate"
          : "Reflects the host's approved or set price for these dates"}
      </p>

      <div className="mt-4 rounded-lg border border-[var(--lp-border)] divide-y divide-[var(--lp-border)]">
        <div className="grid grid-cols-2 divide-x divide-[var(--lp-border)]">
          <label className="px-3 py-2">
            <span className="block text-[10px] uppercase text-[var(--lp-text-muted)]">Check-in</span>
            <select
              value={selectedCheckin}
              onChange={(e) => setSelectedCheckin(e.target.value)}
              className="w-full bg-transparent text-sm outline-none"
            >
              {!checkinInRange && selectedCheckin && (
                <option value={selectedCheckin}>{selectedCheckin} (unavailable)</option>
              )}
              {nights.map((n) => <option key={n.date} value={n.date}>{n.date}</option>)}
            </select>
          </label>
          <label className="px-3 py-2">
            <span className="block text-[10px] uppercase text-[var(--lp-text-muted)]">Checkout</span>
            <select
              value={selectedCheckout}
              onChange={(e) => setSelectedCheckout(e.target.value)}
              className="w-full bg-transparent text-sm outline-none"
            >
              {!checkoutInRange && selectedCheckout && (
                <option value={selectedCheckout}>{selectedCheckout} (unavailable)</option>
              )}
              {nights.map((n) => <option key={n.date} value={n.date}>{n.date}</option>)}
            </select>
          </label>
        </div>

        <GuestPicker value={guests} onChange={setGuests} />
      </div>

      {(!checkinInRange || !checkoutInRange) && selectedCheckin && (
        <p className="mt-2 text-xs text-[var(--lp-terracotta)]">
          Your searched dates aren&apos;t priced yet for this listing &mdash; showing the closest available range instead.
        </p>
      )}
      {!validRange && selectedCheckin && (
        <p className="mt-2 text-xs text-[var(--lp-terracotta)]">Checkout must be after check-in.</p>
      )}
      {overCapacity && (
        <p className="mt-2 text-xs text-[var(--lp-terracotta)]">
          This place fits up to {maxGuests} guests &mdash; you&apos;ve selected {totalGuestsForCapacity}.
        </p>
      )}

      {validRange && (
        <div className="mt-4 space-y-1.5 border-t border-[var(--lp-border)] pt-4 text-sm">
          <div className="flex justify-between text-[var(--lp-text-muted)]">
            <span>{currency} {Math.round(avgNightly).toLocaleString()} &times; {stayNights.length} night{stayNights.length !== 1 ? "s" : ""}</span>
            <span>{currency} {Math.round(totalPrice).toLocaleString()}</span>
          </div>
          <div className="flex justify-between font-medium">
            <span>Total for {totalGuestsForCapacity} guest{totalGuestsForCapacity !== 1 ? "s" : ""}{guests.infants > 0 ? `, ${guests.infants} infant${guests.infants !== 1 ? "s" : ""}` : ""}</span>
            <span>{currency} {Math.round(totalPrice).toLocaleString()}</span>
          </div>
        </div>
      )}

      {confirmed ? (
        <div className="mt-4 rounded-lg border border-[var(--lp-teal)]/30 bg-[var(--lp-teal-dim)] px-4 py-3 text-center text-sm text-[var(--lp-teal)]">
          Reservation request sent &mdash; {stayNights.length} night{stayNights.length !== 1 ? "s" : ""}, {currency} {Math.round(totalPrice).toLocaleString()} total.
        </div>
      ) : (
        <>
          <button
            onClick={reserve}
            disabled={overCapacity || !validRange}
            className="mt-4 w-full rounded-lg bg-[var(--lp-terracotta)] py-2.5 text-sm font-medium text-white transition hover:brightness-105 disabled:opacity-40"
          >
            Reserve
          </button>
          <p className="mt-2 text-center text-xs text-[var(--lp-text-muted)]">You won&apos;t be charged yet</p>
        </>
      )}
    </div>
  );
}
