"use client";

import Image from "next/image";
import { useState } from "react";

export function Gallery({ pictureUrl, name }: { pictureUrl: string | null; name: string }) {
  // Two distinct reasons a listing has no photo to show: the archive row
  // never had a picture_url (pictureUrl is null), or it did but the URL
  // itself is dead - these are real photo links scraped years ago, and
  // Airbnb's CDN doesn't keep them working forever. Both end up at the same
  // placeholder; `failed` tracks the second case, since <Image> doesn't stop
  // rendering on its own just because the request 404s.
  const [failed, setFailed] = useState(false);

  if (!pictureUrl || failed) {
    return <div className="flex h-[420px] items-center justify-center rounded-2xl bg-[var(--lp-teal-dim)] text-sm text-[var(--lp-text-muted)]">No listing photo available</div>;
  }

  return (
    <div className="relative overflow-hidden rounded-2xl" style={{ height: 420 }}>
      <Image src={pictureUrl} alt={name} fill priority sizes="(max-width: 1024px) 100vw, 66vw" className="object-cover" onError={() => setFailed(true)} />
    </div>
  );
}
