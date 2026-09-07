"use client";

import { photosForListing, stockPhotoSrc } from "@/lib/photos";

export function Gallery({ listingId }: { listingId: number }) {
  const photos = photosForListing(listingId);

  return (
    <div className="grid grid-cols-4 grid-rows-2 gap-2 overflow-hidden rounded-2xl" style={{ height: 420 }}>
      <div className="photo-tile col-span-2 row-span-2">
        <img src={stockPhotoSrc(photos[0].id, 1000)} alt={photos[0].label} className="h-full w-full object-cover" loading="eager" />
        <span>{photos[0].label}</span>
      </div>
      {photos.slice(1).map((t) => (
        <div key={t.id} className="photo-tile">
          <img src={stockPhotoSrc(t.id, 500)} alt={t.label} className="h-full w-full object-cover" loading="lazy" />
          <span>{t.label}</span>
        </div>
      ))}
    </div>
  );
}
