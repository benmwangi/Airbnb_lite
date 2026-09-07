import { CalendarNight } from "./api";

// The three distinct price concepts, kept explicit everywhere rather than
// collapsing them into one number:
//   - base price: the per-market model's structural estimate, before any
//     modifiers or host action
//   - recommended price: the engine's full recommendation (base + event/news/
//     seasonality modifiers + guardrails) - what the algorithm suggests
//   - live/set price: what a guest would actually pay right now - only set
//     once a host approves, overrides, or the listing is on auto-apply.
//     Null means nothing is live yet (pending review, or rejected).

export function effectiveGuestPrice(night: CalendarNight): number {
  // Used on the HOST side (the year calendar heatmap): the live price if set,
  // otherwise the recommendation as a provisional preview - a host benefits
  // from seeing where the algorithm is heading even before approving it.
  return night.live_price ?? night.recommended_price;
}

export function resolvedGuestPrice(night: CalendarNight, floorPrice: number): number {
  // Used on the GUEST side: a guest should never be shown the algorithm's
  // unconfirmed recommendation as if it were a real price. If the host has
  // approved or set a price, use that. Otherwise fall back to the host's own
  // floor price - a safe, host-configured lower bound - rather than a
  // recommendation that could still change before the host acts on it.
  return night.live_price ?? floorPrice;
}

export function nightsInStayRange(nights: CalendarNight[], checkin: string, checkout: string): CalendarNight[] {
  // Standard "nights stayed" convention: includes the check-in date, excludes
  // the checkout date itself (you don't pay for the night you leave).
  return nights.filter((n) => n.date >= checkin && n.date < checkout);
}

export function isLive(night: CalendarNight): boolean {
  return night.live_price != null;
}
