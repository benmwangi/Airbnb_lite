"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "airbnb_lite_token";

export type AuthUser = {
  id: number;
  email: string;
  name: string;
  role: "guest" | "host";
  host_id: number | null;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function logout() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.location.href = "/";
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Login failed");
  }
  const data = await res.json();
  setToken(data.token);
  return data.user;
}

export async function signup(email: string, password: string, name: string, role: "guest" | "host"): Promise<AuthUser> {
  const res = await fetch(`${API_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name, role }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Signup failed");
  }
  const data = await res.json();
  setToken(data.token);
  return data.user;
}

// Hook for pages that need to know who's logged in. `status` starts as
// "loading" so pages can avoid a flash of logged-out content, then resolves
// to "authenticated" or "unauthenticated".
export function useCurrentUser() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<"loading" | "authenticated" | "unauthenticated">("loading");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setStatus("unauthenticated");
      return;
    }
    fetch(`${API_URL}/auth/me`, { headers: authHeaders() })
      .then((res) => {
        if (!res.ok) throw new Error();
        return res.json();
      })
      .then((u) => {
        setUser(u);
        setStatus("authenticated");
      })
      .catch(() => {
        window.localStorage.removeItem(TOKEN_KEY);
        setStatus("unauthenticated");
      });
  }, []);

  return { user, status };
}
