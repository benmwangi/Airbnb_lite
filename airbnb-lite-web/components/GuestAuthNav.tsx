"use client";

import { useCurrentUser, logout } from "@/lib/auth";

export function GuestAuthNav() {
  const { user, status } = useCurrentUser();

  if (status === "loading") return null;

  if (status === "authenticated" && user) {
    return (
      <div className="flex items-center gap-3 text-sm">
        <span className="text-[var(--lp-text-muted)]">Hi, {user.name}</span>
        <button onClick={logout} className="text-[var(--lp-text-muted)] underline">Log out</button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      <a href="/login?role=guest" className="text-[var(--lp-text)]">Log in</a>
      <a
        href="/signup?role=guest"
        className="rounded-full border border-[var(--lp-border)] px-4 py-1.5 transition hover:shadow-[0_1px_4px_rgba(34,32,27,0.08)]"
      >
        Sign up
      </a>
    </div>
  );
}
