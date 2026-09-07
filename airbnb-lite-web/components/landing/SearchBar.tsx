"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Market } from "@/lib/api";
import { GuestPicker, GuestCounts } from "./GuestPicker";

export function SearchBar({ markets }: { markets: Market[] }) {
  const router = useRouter();
  const [marketId, setMarketId] = useState<number | "">("");
  const [checkin, setCheckin] = useState("");
  const [checkout, setCheckout] = useState("");
  const [guests, setGuests] = useState<GuestCounts>({ adults: 1, children: 0, infants: 0 });

  function search() {
    const params = new URLSearchParams();
    if (marketId !== "") params.set("market", String(marketId));
    if (checkin) params.set("checkin", checkin);
    if (checkout) params.set("checkout", checkout);
    params.set("adults", String(guests.adults));
    params.set("children", String(guests.children));
    params.set("infants", String(guests.infants));
    router.push(`/search?${params.toString()}`);
  }

  return (
    <div className="flex items-stretch divide-x divide-[var(--lp-border)] rounded-full border border-[var(--lp-border)] bg-[var(--lp-surface)] shadow-[0_2px_6px_rgba(34,32,27,0.06)]">
      <div className="flex flex-1 flex-col justify-center px-5 py-2">
        <label className="text-xs font-medium text-[var(--lp-text)]">Where</label>
        <select
          value={marketId}
          onChange={(e) => setMarketId(e.target.value === "" ? "" : Number(e.target.value))}
          className="bg-transparent text-sm text-[var(--lp-text)] outline-none"
        >
          <option value="">Search destinations</option>
          {markets.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
      </div>

      <div className="flex flex-1 flex-col justify-center px-5 py-2">
        <label className="text-xs font-medium text-[var(--lp-text)]">Check-in</label>
        <input
          type="date"
          value={checkin}
          onChange={(e) => setCheckin(e.target.value)}
          className="bg-transparent text-sm text-[var(--lp-text)] outline-none"
        />
      </div>

      <div className="flex flex-1 flex-col justify-center px-5 py-2">
        <label className="text-xs font-medium text-[var(--lp-text)]">Checkout</label>
        <input
          type="date"
          value={checkout}
          onChange={(e) => setCheckout(e.target.value)}
          className="bg-transparent text-sm text-[var(--lp-text)] outline-none"
        />
      </div>

      <div className="flex flex-1 items-stretch">
        <GuestPicker value={guests} onChange={setGuests} />
        <div className="flex items-center pr-2">
          <button
            onClick={search}
            className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--lp-terracotta)] text-white transition hover:brightness-105"
            aria-label="Search"
          >
            &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}
