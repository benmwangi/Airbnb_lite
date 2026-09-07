// Pool of (reviewer name, review text) pairs. Fictional reviewers for a
// fictional demo listing - three are picked deterministically per listing so
// different listings show different reviewers and different review text,
// instead of one hardcoded set everywhere.
const REVIEW_POOL = [
  { name: "Marco", text: "Beautifully kept, exactly as described, and the host was quick to respond to every question." },
  { name: "Aisha", text: "The location made it easy to get everywhere. Would book again without hesitation." },
  { name: "Lena", text: "Spacious, clean, and the terrace view in the evening was a highlight of the trip." },
  { name: "Julien", text: "Check-in was seamless and the neighborhood felt safe even late at night." },
  { name: "Sara", text: "Photos undersell it, honestly. Everything was bigger and brighter in person." },
  { name: "Tomás", text: "Great value for the space. Kitchen had everything we needed for a home-cooked breakfast." },
  { name: "Ingrid", text: "Quiet street, comfortable bed, and walking distance to the best coffee shop nearby." },
  { name: "Hassan", text: "Host left a thoughtful welcome note with local recommendations - made the stay feel personal." },
  { name: "Camille", text: "Perfect for a short trip. Everything was spotless and check-out was hassle-free." },
  { name: "Ben", text: "Loved the natural light in the mornings. Would happily stay again on a future visit." },
  { name: "Naledi", text: "Well-equipped and thoughtfully decorated. Felt more like a home than a rental." },
  { name: "Piotr", text: "Responsive host, easy self check-in, and the area exceeded our expectations." },
  { name: "Priya", text: "Lovely stay overall, but the decor felt a little outdated - some fresh paint and new linens would go a long way." },
  { name: "Owen", text: "The listing photos really don't do the space justice online. It's much nicer in person, but I almost booked elsewhere because of the pictures." },
  { name: "Fatima", text: "Wifi was spotty most evenings, which made working remotely tricky. Everything else was great." },
  { name: "Liam", text: "Could hear a lot of street noise at night. Earplugs would have been a nice touch." },
  { name: "Ana", text: "Arrived to find the bathroom wasn't as clean as I'd hoped. The host was quick to send someone to fix it though." },
  { name: "Kofi", text: "Took a while to hear back from the host about check-in instructions, which was stressful after a long flight." },
  { name: "Greta", text: "Kitchen was missing basic things like a can opener and coffee filters - had to buy our own." },
  { name: "Noor", text: "Check-in was a bit confusing without clearer directions - we circled the block twice looking for the entrance." },
];

export function reviewsForListing(listingId: number) {
  const start = (listingId * 3) % REVIEW_POOL.length;
  const picks = [];
  for (let i = 0; i < 3; i++) {
    picks.push(REVIEW_POOL[(start + i) % REVIEW_POOL.length]);
  }
  return picks;
}
