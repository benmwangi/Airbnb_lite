"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/auth";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const intendedRole = searchParams.get("role"); // "guest" | "host" | null - just for messaging/redirect
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await login(email, password);
      router.push(user.role === "host" ? "/host" : "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  function fillDemo(role: "guest" | "host") {
    setEmail(role === "host" ? "host@airbnblite.demo" : "guest@airbnblite.demo");
    setPassword("demo12345");
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

        <p className="mb-1 text-center font-display text-2xl">Log in</p>
        <p className="mb-6 text-center text-sm text-[var(--lp-text-muted)]">
          {intendedRole === "host" ? "Log in as a host to manage your listings." : "Log in to book and track your trips."}
        </p>

        <form onSubmit={submit} className="space-y-3 rounded-2xl border border-[var(--lp-border)] bg-[var(--lp-surface)] p-6">
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
              type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--lp-border)] px-3 py-2 text-sm outline-none focus:border-[var(--lp-teal)]"
            />
          </label>

          {error && <p className="text-xs text-[#e2604f]">{error}</p>}

          <button
            type="submit" disabled={loading}
            className="w-full rounded-lg bg-[var(--lp-terracotta)] py-2.5 text-sm font-medium text-white transition hover:brightness-105 disabled:opacity-40"
          >
            {loading ? "Logging in\u2026" : "Log in"}
          </button>

          <div className="flex items-center gap-2 pt-1">
            <button type="button" onClick={() => fillDemo("guest")} className="flex-1 rounded-lg border border-[var(--lp-border)] py-1.5 text-xs text-[var(--lp-text-muted)] hover:text-[var(--lp-text)]">
              Use demo guest
            </button>
            <button type="button" onClick={() => fillDemo("host")} className="flex-1 rounded-lg border border-[var(--lp-border)] py-1.5 text-xs text-[var(--lp-text-muted)] hover:text-[var(--lp-text)]">
              Use demo host
            </button>
          </div>
        </form>

        <p className="mt-4 text-center text-sm text-[var(--lp-text-muted)]">
          No account? <a href={`/signup${intendedRole ? `?role=${intendedRole}` : ""}`} className="text-[var(--lp-teal)] underline">Sign up</a>
        </p>
      </div>
    </div>
  );
}
