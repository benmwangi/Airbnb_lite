"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const THEME_LABELS: Record<string, string> = {
  outdated_decor: "Decor",
  misleading_photos: "Photos",
  cleanliness: "Cleanliness",
  noise: "Noise",
  wifi: "WiFi",
  communication: "Communication",
  checkin_process: "Check-in",
  value_for_price: "Value",
  missing_amenities: "Amenities",
};

export function ReviewInsights({ listingId }: { listingId: number }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.reviewInsights>> | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    api.reviewInsights(listingId).then(setData).catch(() => setData(null));
    setExpanded({});
  }, [listingId]);

  if (!data) {
    return (
      <div className="rounded-lg border border-dashed border-[var(--lp-border)] px-4 py-3 text-xs text-[var(--lp-text-muted)]">
        Loading guest feedback insights&hellip;
      </div>
    );
  }

  if (!data.available) {
    return (
      <div className="rounded-lg border border-dashed border-[var(--lp-border)] px-4 py-3 text-xs text-[var(--lp-text-muted)]">
        {data.reason}
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {data.insights.map((insight) => {
        const details = insight.specific_details
          ? insight.specific_details.split(",").map((d) => d.trim()).filter(Boolean)
          : [];
        const isOpen = !!expanded[insight.theme];

        return (
          <div key={insight.theme} className="rounded-lg border border-[var(--lp-border)] bg-[var(--lp-surface)] px-4 py-3">
            <div className="mb-1 flex items-center justify-between">
              <span className="rounded-full bg-[var(--lp-terracotta-dim)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--lp-terracotta)]">
                {THEME_LABELS[insight.theme] ?? insight.theme}
              </span>
              <span className="text-[11px] text-[var(--lp-text-muted)]">
                {insight.mention_count} of {insight.total_reviews_scanned} reviews
              </span>
            </div>

            <p className="text-sm leading-relaxed">{insight.recommendation}</p>

            {details.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {details.map((d) => (
                  <span
                    key={d}
                    className="rounded-full border border-[var(--lp-teal)]/30 bg-[var(--lp-teal-dim)] px-2 py-0.5 text-[11px] text-[var(--lp-teal)]"
                  >
                    {d}
                  </span>
                ))}
              </div>
            )}

            {insight.sample_review && (
              <div className="mt-2">
                <button
                  onClick={() => setExpanded((e) => ({ ...e, [insight.theme]: !e[insight.theme] }))}
                  className="text-xs text-[var(--lp-text-muted)] underline"
                >
                  {isOpen ? "Hide sample review" : "See a sample review"}
                </button>
                {isOpen && (
                  <blockquote className="mt-1.5 border-l-2 border-[var(--lp-border)] pl-3 text-xs italic leading-relaxed text-[var(--lp-text-muted)] whitespace-pre-line">
                    &ldquo;{insight.sample_review}&rdquo;
                  </blockquote>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
