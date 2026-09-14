"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, CalendarNight, HOST_CALENDAR_DAYS, ListingSummary } from "@/lib/api";
import { MonthCalendar } from "@/components/host/MonthCalendar";
import { ReviewInsights } from "@/components/host/ReviewInsights";
import { useCurrentUser, logout } from "@/lib/auth";

export default function ManageListingPage() {
  const params = useParams();
  const router = useRouter();
  const listingId = Number(params.id);
  const { user, status } = useCurrentUser();

  const [listing, setListing] = useState<ListingSummary | null>(null);
  const [nights, setNights] = useState<CalendarNight[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [comparison, setComparison] = useState<Awaited<ReturnType<typeof api.comparison>> | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(false);
  const generatedForListing = useRef<number | null>(null);

  async function refresh() {
    const c = await api.calendar(listingId, HOST_CALENDAR_DAYS);
    if (
      c.length < HOST_CALENDAR_DAYS &&
      generatedForListing.current !== listingId
    ) {
      generatedForListing.current = listingId;
      setGenerating(true);
      await api.priceYear(listingId, HOST_CALENDAR_DAYS);
      setGenerating(false);
      return refresh();
    }
    setNights(c);
    if (c.length && !selectedDate) setSelectedDate(c[0].date);
  }

  function loadCalendar() {
    refresh().catch(() => {
      setGenerating(false);
      setError(true);
    });
  }

  useEffect(() => {
    generatedForListing.current = null;
  }, [listingId]);

  function setCalendar(c: CalendarNight[]) {
      setNights(c);
      if (c.length && !selectedDate) setSelectedDate(c[0].date);
  }

  function refreshWithoutGeneration() {
    api.calendar(listingId, HOST_CALENDAR_DAYS).then(setCalendar).catch(() => setError(true));
  }

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login?role=host");
      return;
    }
    if (status === "authenticated" && user?.role !== "host") {
      router.push("/");
      return;
    }
    if (!listingId || status !== "authenticated") return;
    api.listing(listingId).then((l) => {
      if (l.host_id !== user?.host_id) {
        router.push("/host"); // logged in as a different host - not their listing
        return;
      }
      setListing(l);
    }).catch(() => setError(true));
    api.comparison(listingId).then(setComparison).catch(() => setComparison(null));
    loadCalendar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listingId, status, user]);

  async function generateYear() {
    // Guard against an accidental click: this recomputes recommendations for
    // every night in the horizon, and for an auto-apply listing that means
    // the live price guests see updates immediately, not just the
    // recommendation - so make sure that's what the host actually meant to do.
    const isRegenerate = nights.length > 30;
    const confirmed = window.confirm(
      isRegenerate
        ? `Regenerate pricing for the next ${HOST_CALENDAR_DAYS} nights? This recalculates every night's recommended price.${
            listing?.auto_apply
              ? " Auto-apply is on for this listing, so the live price guests see will update immediately."
              : " Prices you've already approved or set stay live - only the recommendation changes."
          }`
        : `Generate a year of pricing for this listing? This computes a recommended price for the next ${HOST_CALENDAR_DAYS} nights.`
    );
    if (!confirmed) return;

    setGenerating(true);
    await api.priceYear(listingId, HOST_CALENDAR_DAYS);
    refreshWithoutGeneration();
    setGenerating(false);
  }

  async function approve() {
    if (!selectedDate) return;
    await api.approve(listingId, selectedDate);
    refreshWithoutGeneration();
  }
  async function override(price: number) {
    if (!selectedDate || Number.isNaN(price)) return;
    await api.approve(listingId, selectedDate, price);
    refreshWithoutGeneration();
  }
  async function reject() {
    if (!selectedDate) return;
    await api.reject(listingId, selectedDate);
    refreshWithoutGeneration();
  }

  const night = nights.find((n) => n.date === selectedDate);
  const [overrideValue, setOverrideValue] = useState("");

  if (error) {
    return (
      <div className="listing-page flex h-screen items-center justify-center text-center">
        <div>
          <p className="text-lg">Can&apos;t reach the pricing API.</p>
          <p className="mt-1 text-sm text-[var(--lp-text-muted)]">Start it with: uvicorn main:app --reload</p>
        </div>
      </div>
    );
  }
  if (status === "loading" || status === "unauthenticated" || (user && user.role !== "host")) {
    return null;
  }
  if (!listing) return null;

  return (
    <div className="listing-page">
      <header className="border-b border-[var(--lp-border)]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <a href="/host" className="flex items-center gap-2">
              <svg width="24" height="24" viewBox="0 0 26 26" fill="none">
                <circle cx="13" cy="13" r="12" stroke="#c9714a" strokeWidth="1.5" />
                <path d="M13 6 L19 18 H7 Z" fill="#21867a" opacity="0.85" />
              </svg>
              <span className="font-display text-lg italic">airbnb lite</span>
            </a>
            <span className="text-[var(--lp-border)]">|</span>
            <a href="/host" className="text-sm text-[var(--lp-text-muted)] transition hover:text-[var(--lp-text)]">&larr; Your listings</a>
          </div>
          <div className="flex items-center gap-3">
            <a
              href={`/listing/${listingId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 text-sm transition hover:shadow-[0_1px_4px_rgba(34,32,27,0.08)]"
            >
              View live listing &#8599;
            </a>
            <button onClick={logout} className="text-sm text-[var(--lp-text-muted)] underline">Log out</button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <p className="font-display text-2xl">{listing.room_type} in {listing.market}</p>
            <p className="mt-1 text-sm text-[var(--lp-text-muted)]">
              {listing.name || listing.room_type} &middot; Sleeps {listing.accommodates} &middot;{" "}
              Guardrail {listing.currency} {listing.min_floor.toLocaleString()}&ndash;{listing.max_ceiling.toLocaleString()}
            </p>
          </div>
          <button
            onClick={generateYear}
            disabled={generating}
            className="rounded-lg border border-[var(--lp-terracotta)] px-4 py-2 text-sm text-[var(--lp-terracotta)] transition hover:bg-[var(--lp-terracotta-dim)] disabled:opacity-40"
          >
            {generating ? "Generating\u2026" : nights.length > 30 ? "Regenerate year of pricing" : "Generate year of pricing"}
          </button>
        </div>

        {nights.length === 0 ? (
          <p className="text-sm text-[var(--lp-text-muted)]">No pricing generated yet for this listing &mdash; click &ldquo;Generate year of pricing&rdquo; above.</p>
        ) : (
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
            <div className="rounded-xl border border-[var(--lp-border)] bg-[var(--lp-surface)] p-5 lg:col-span-2">
              <MonthCalendar nights={nights} currency={listing.currency} selectedDate={selectedDate} onSelect={setSelectedDate} />
            </div>

            <div className="rounded-xl border border-[var(--lp-border)] bg-[var(--lp-surface)] p-5">
              {night ? (
                <>
                  <p className="text-xs uppercase tracking-wide text-[var(--lp-text-muted)]">
                    {new Date(night.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
                  </p>

                  <div className="mt-2 space-y-2 rounded-lg border border-[var(--lp-border)] p-3">
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs text-[var(--lp-text-muted)]">Base price (model estimate)</span>
                      <span className="font-mono text-sm text-[var(--lp-text-muted)]">{listing.currency} {night.base_model_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                    </div>
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs text-[var(--lp-text-muted)]">Recommended price</span>
                      <span className="font-mono text-sm">{listing.currency} {night.recommended_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                    </div>
                    {comparison?.available && comparison.actual_median_price != null && (
                      <div className="rounded-md border border-[var(--lp-border)] bg-[var(--lp-teal-dim)] px-2.5 py-2 text-[11px] leading-relaxed text-[var(--lp-text)]">
                        <span className="font-medium text-[var(--lp-teal)]">Inside Airbnb:</span>{" "}
                        {listing.currency} {Math.round(comparison.model_recommended_price ?? night.recommended_price).toLocaleString()} recommended vs {listing.currency} {Math.round(comparison.actual_median_price).toLocaleString()} nearby median
                        {comparison.actual_mean_price != null && ` (mean ${listing.currency} ${Math.round(comparison.actual_mean_price).toLocaleString()})`}
                      </div>
                    )}
                    <div className="flex items-baseline justify-between border-t border-[var(--lp-border)] pt-2">
                      <span className="text-xs font-medium">Set price (live to guests)</span>
                      <span className={`font-mono text-base font-semibold ${night.live_price != null ? "text-[var(--lp-terracotta)]" : "text-[var(--lp-text-muted)]"}`}>
                        {night.live_price != null
                          ? `${listing.currency} ${night.live_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                          : "Not set"}
                      </span>
                    </div>
                  </div>

                  <p className={`mt-2 text-xs capitalize ${
                    night.status === "rejected" ? "text-[#e2604f]"
                    : night.status === "host_override" ? "text-[var(--lp-terracotta)]"
                    : night.status === "pending_approval" ? "text-[var(--lp-text-muted)]"
                    : "text-[var(--lp-teal)]"
                  }`}>
                    &#9679; {night.status.replace(/_/g, " ")}
                  </p>

                  <div className="mt-3 rounded-lg bg-[var(--lp-bg)] px-3 py-2.5 text-sm leading-relaxed text-[var(--lp-text)]">
                    {night.explanation}
                  </div>

                  <div className="mt-4 flex flex-col gap-2">
                    <button onClick={approve} className="w-full rounded-lg bg-[var(--lp-terracotta)] px-4 py-2 text-sm font-medium text-white hover:brightness-105">
                      Approve &mdash; set live price to recommended
                    </button>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        value={overrideValue}
                        onChange={(e) => setOverrideValue(e.target.value)}
                        placeholder="Set your own"
                        className="w-full rounded-lg border border-[var(--lp-border)] bg-transparent px-3 py-1.5 font-mono text-sm outline-none focus:border-[var(--lp-teal)]"
                      />
                      <button onClick={() => override(parseFloat(overrideValue))} className="shrink-0 rounded-lg border border-[var(--lp-teal)] px-3 py-1.5 text-sm text-[var(--lp-teal)] hover:bg-[var(--lp-teal-dim)]">
                        Set
                      </button>
                    </div>
                    <button onClick={reject} className="text-xs text-[#e2604f]">Reject &mdash; clear the live price for this night</button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-[var(--lp-text-muted)]">Select a day on the calendar to manage its price.</p>
              )}
            </div>
          </div>
        )}

        <div className="mt-8">
          <p className="mb-1 font-display text-xl">Guest feedback insights</p>
          <p className="mb-4 text-sm text-[var(--lp-text-muted)]">
            Recommendations derived from patterns in this listing&apos;s real guest reviews.
          </p>
          <ReviewInsights listingId={listingId} />
        </div>
      </main>
    </div>
  );
}
