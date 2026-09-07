// Deterministic per-HOST name, so the same host shows the same name across
// every listing they own - keyed by host_id, not listing id. A host with
// multiple listings (e.g. this project's demo host account) must show one
// consistent name everywhere; keying by listing id instead was the bug that
// made a single host appear under a different name on each of their own
// properties. Fictional names for a fictional demo host roster - not tied to
// any real person.
const HOST_NAMES = [
  "Thandiwe", "Marco", "Aisha", "Lena", "Kwame", "Priya", "Noah", "Farida",
  "Diego", "Yuki", "Sipho", "Elena", "Rafael", "Mei", "Oliver", "Zanele",
];

export function hostNameForHost(hostId: number) {
  return HOST_NAMES[hostId % HOST_NAMES.length];
}
