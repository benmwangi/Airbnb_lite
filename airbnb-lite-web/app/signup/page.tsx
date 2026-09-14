"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signup } from "@/lib/auth";

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupPageInner />
    </Suspense>
  );
}

function SignupPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [role, setRole] = useState<"guest" | "host">(
    searchParams.get("role") === "host" ? "host" : "guest"
  );
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await signup(email, password, name, role);
      router.push(user.role === "host" ? "/host" : "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="listing-page flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center justify-center gap-2">
          <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
            <circle cx="13" cy="13" r="12" stroke="#c9714a" strokeWidth="1.5" />
            <path d="M13 6 L19 18 H7 Z" fill="#21867a" opacity="0.85" />
          </svg>
          <span className="font-display text-xl italic">airbnb lite</span>
        </div>

        <p className="mb-1 text-center font-display text-2xl">Sign up</p>
        <p className="mb-6 text-center text-sm text-[var(--lp-text-muted)]">
          {role === "host" ? "Create a host account to list and price your own properties." : "Create a guest account to book and track your trips."}
        </p>

        <div className="mb-4 flex rounded-full border border-[var(--lp-border)] p-1 text-sm">
          <button
            type="button"
            onClick={() => setRole("guest")}
            className={`flex-1 rounded-full py-1.5 transition ${role === "guest" ? "bg-[var(--lp-text)] text-[var(--lp-bg)]" : "text-[var(--lp-text-muted)]"}`}
          >
            I&apos;m a guest
          </button>
          <button
            type="button"
            onClick={() => setRole("host")}
            className={`flex-1 rounded-full py-1.5 transition ${role === "host" ? "bg-[var(--lp-text)] text-[var(--lp-bg)]" : "text-[var(--lp-text-muted)]"}`}
          >
            I&apos;m a host
          </button>
        </div>

        <form onSubmit={submit} className="space-y-3 rounded-2xl border border-[var(--lp-border)] bg-[var(--lp-surface)] p-6">
          <label className="block">
            <span className="block text-xs font-medium">Name</span>
            <input
              type="text" required value={name} onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--lp-border)] px-3 py-2 text-sm outline-none focus:border-[var(--lp-teal)]"
            />
          </label>
          <label className="block">
            <span className="block text-xs font-medium">Email</span>
            <input
              type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--lp-border)] px-3 py-2 text-sm outline-none focus:border-[var(--lp-teal)]"
            />
          </label>
          <label className="block">
            <span className="block text-xs font-medium">Password</span>
            <input
              type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--lp-border)] px-3 py-2 text-sm outline-none focus:border-[var(--lp-teal)]"
            />
            <span className="mt-1 block text-[11px] text-[var(--lp-text-muted)]">At least 8 characters</span>
          </label>

          {role === "host" && (
            <p className="rounded-lg border border-dashed border-[var(--lp-border)] px-3 py-2 text-[11px] text-[var(--lp-text-muted)]">
              A new host account starts with no listings yet, since it isn&apos;t linked to any existing property. To explore the host console with real, pre-populated listings, use the demo host account on the login page instead.
            </p>
          )}

          {error && <p className="text-xs text-[#e2604f]">{error}</p>}

          <button
            type="submit" disabled={loading}
            className="w-full rounded-lg bg-[var(--lp-terracotta)] py-2.5 text-sm font-medium text-white transition hover:brightness-105 disabled:opacity-40"
          >
            {loading ? "Creating account\u2026" : "Sign up"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-[var(--lp-text-muted)]">
          Already have an account? <a href={`/login${role ? `?role=${role}` : ""}`} className="text-[var(--lp-teal)] underline">Log in</a>
        </p>
      </div>
    </div>
  );
}
