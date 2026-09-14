"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ListingSummary } from "@/lib/api";
import { useCurrentUser, logout } from "@/lib/auth";

// Real archive picture_url values can be dead links (scraped years ago;
// Airbnb's CDN doesn't keep them working forever) as well as simply missing.
// A plain <img> doesn't stop rendering on its own when the request 404s, so
// this needs its own onError-tracked state - one per card, hence its own
// component rather than a single boolean on the page.
function ListingThumb({ pictureUrl, alt }: { pictureUrl: string | null; alt: string }) {
  const [failed, setFailed] = useState(false);
  if (!pictureUrl || failed) {
    return <div className="flex h-36 items-center justify-center bg-[var(--lp-teal-dim)] text-sm text-[var(--lp-teal)]">No photo available</div>;
  }
  return <img src={pictureUrl} alt={alt} className="h-36 w-full object-cover" loading="lazy" onError={() => setFailed(true)} />;
}

export default function HostListingsPage() {
  const router = useRouter();
  const { user, status } = useCurrentUser();
  const [listings, setListings] = useState<ListingSummary[] | null>(null);
  const [error, setError] = useState(false);

  // Tallies listings per market so the host can see at a glance where their
  // portfolio actually is, without counting cards in the grid below -
  // useful once a host has listings spread across more than one of the 10
  // markets this app covers.
  const marketCounts = (listings ?? []).reduce<Record<string, number>>((acc, l) => {
    acc[l.market] = (acc[l.market] ?? 0) + 1;
    return acc;
  }, {});
  const marketEntries = Object.entries(marketCounts).sort((a, b) => b[1] - a[1]);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login?role=host");
      return;
    }
    if (status === "authenticated" && user?.role !== "host") {
      router.push("/"); // logged in, but as a guest - this console isn't for them
      return;
    }
    if (status === "authenticated") {
      api.myListings().then(setListings).catch(() => setError(true));
    }
  }, [status, user, router]);

  if (status === "loading" || status === "unauthenticated" || (user && user.role !== "host")) {
    return null; // avoids a flash of the host console before the redirect above runs
  }

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
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--lp-text-muted)]">{user?.name}</span>
            <a href="/" className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 text-sm transition hover:shadow-[0_1px_4px_rgba(34,32,27,0.08)]">
              View live site
            </a>
            <button onClick={logout} className="text-sm text-[var(--lp-text-muted)] underline">Log out</button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <p className="font-display text-3xl">Your listings</p>
        <p className="mt-1 text-sm text-[var(--lp-text-muted)]">Every property you host, across every market. Select one to manage its pricing.</p>

        {listings && listings.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-sm text-[var(--lp-text-muted)]">
              {listings.length} listing{listings.length !== 1 ? "s" : ""} across {marketEntries.length} market{marketEntries.length !== 1 ? "s" : ""}:
            </span>
            {marketEntries.map(([market, count]) => (
              <span
                key={market}
                className="rounded-full border border-[var(--lp-teal)]/30 bg-[var(--lp-teal-dim)] px-2.5 py-0.5 text-xs text-[var(--lp-teal)]"
              >
                {market} &middot; {count}
              </span>
            ))}
          </div>
        )}

        {error && (
          <p className="mt-6 text-sm text-[var(--lp-text-muted)]">Can&apos;t reach the pricing API. Start it with: uvicorn main:app --reload</p>
        )}

        {listings && listings.length === 0 && (
          <p className="mt-6 text-sm text-[var(--lp-text-muted)]">
            No listings with a photo found for this host account. (Listings without an archive photo aren&apos;t shown here, since guests wouldn&apos;t see them in search either.)
          </p>
        )}

        <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {listings?.map((l) => (
              <div
                key={l.id}
                className="group relative overflow-hidden rounded-xl border border-[var(--lp-border)] bg-[var(--lp-surface)] transition hover:shadow-[0_4px_16px_rgba(34,32,27,0.08)]"
              >
                <a href={`/host/listings/${l.id}`} className="block">
                  <ListingThumb pictureUrl={l.picture_url ?? null} alt={l.name || l.room_type} />
                  <div className="p-4">
                    <p className="text-sm font-medium">{l.name || `${l.room_type} · ${l.market}`}</p>
                    <p className="mt-0.5 text-xs text-[var(--lp-text-muted)]">
                      Sleeps {l.accommodates}{l.host_is_superhost ? " · Superhost" : ""}
                    </p>
                    <p className="mt-2 font-mono text-xs text-[var(--lp-teal)]">
                      {l.currency} {l.min_floor.toLocaleString()}&ndash;{l.max_ceiling.toLocaleString()} range
                    </p>
                  </div>
                </a>
                {/* Sibling of the card's main link (not nested inside it - nested <a> tags
                    aren't valid HTML), absolutely positioned over the photo so it still
                    reads as part of the card. Opens the specific guest-facing listing page
                    in a new tab so the host doesn't lose their place in this grid. */}
                <a
                  href={`/listing/${l.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="absolute right-2 top-2 z-10 rounded-full bg-black/60 px-2.5 py-1 text-xs text-white opacity-0 backdrop-blur transition group-hover:opacity-100 hover:bg-black/75"
                >
                  View live &#8599;
                </a>
              </div>
          ))}
        </div>
      </main>
    </div>
  );
}
