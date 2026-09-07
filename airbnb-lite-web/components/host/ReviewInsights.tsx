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

  useEffect(() => {
    api.reviewInsights(listingId).then(setData).catch(() => setData(null));
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
      {data.insights.map((insight) => (
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
        </div>
      ))}
    </div>
  );
}
