"use client";

import { useCurrentUser, logout } from "@/lib/auth";

export function GuestAuthNav() {
  const { user, status } = useCurrentUser();

  if (status === "loading") return null;

  // Hosts get a link back to their console instead of the guest auth controls -
  // and, importantly, no "switch to hosting" prompt, since they already have one.
  if (status === "authenticated" && user?.role === "host") {
    return (
      <div className="flex items-center gap-3 text-sm">
        <span className="text-[var(--lp-text-muted)]">Hi, {user.name}</span>
        <a
          href="/host"
          className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 transition hover:shadow-[0_1px_4px_rgba(34,32,27,0.08)]"
        >
          Host console
        </a>
        <button onClick={logout} className="text-[var(--lp-text-muted)] underline">Log out</button>
      </div>
    );
  }

  // Logged-in guests: no "switch to hosting" prompt either - hosting is a
  // separate account type they haven't signed up for, and the /host console
  // redirects them straight back out if they land on it anyway.
  if (status === "authenticated" && user) {
    return (
      <div className="flex items-center gap-3 text-sm">
        <span className="text-[var(--lp-text-muted)]">Hi, {user.name}</span>
        <button onClick={logout} className="text-[var(--lp-text-muted)] underline">Log out</button>
      </div>
    );
  }

  // Logged-out visitors: show guest auth links plus an invite to hosting,
  // since we don't yet know which kind of account they want.
  return (
    <div className="flex items-center gap-3 text-sm">
      <a href="/login?role=guest" className="text-[var(--lp-text)]">Log in</a>
      <a
        href="/signup?role=guest"
        className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 transition hover:shadow-[0_1px_4px_rgba(34,32,27,0.08)]"
      >
        Sign up
      </a>
      <a
        href="/host"
        className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 transition hover:shadow-[0_1px_4px_rgba(34,32,27,0.08)]"
      >
        Switch to hosting
      </a>
    </div>
  );
}
