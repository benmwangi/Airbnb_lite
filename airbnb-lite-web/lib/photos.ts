// Real stock photos (Unsplash License - free for commercial use, no attribution
// required), reused across the gallery and listing cards. Standing in for real
// listing photos purely to demonstrate look and feel - a real host would upload
// their own.
export const STOCK_PHOTOS = [
  { label: "Living room", id: "photo-1755264785187-021213668e14" },
  { label: "Main bedroom", id: "photo-1757344454333-cc666252e596" },
  { label: "Kitchen", id: "photo-1766430953522-34c4fdc1cec1" },
  { label: "Terrace view", id: "photo-1493246318656-5bfd4cfb29b8" },
  { label: "Bathroom", id: "photo-1776482128011-c707121f081a" },
];

export const stockPhotoSrc = (id: string, w: number) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${w}&q=80`;

// Deterministic pick so the same listing always shows the same card photo.
export function photoForListing(listingId: number) {
  return STOCK_PHOTOS[listingId % STOCK_PHOTOS.length];
}

// Full rotation of all photos for a listing, starting at a different offset
// per listing, so consecutive listings in a grid don't all lead with the same
// image - every card gets a genuinely different starting photo, and each
// card's carousel cycles through every photo either way.
export function photosForListing(listingId: number) {
  const offset = listingId % STOCK_PHOTOS.length;
  return [...STOCK_PHOTOS.slice(offset), ...STOCK_PHOTOS.slice(0, offset)];
}
