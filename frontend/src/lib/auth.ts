"use client";

import { useEffect, useState } from "react";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const TOKEN_KEY = "recallai_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export function googleLoginUrl(): string {
  return `${API}/api/auth/google/login`;
}

export function logout() {
  clearToken();
  if (typeof window !== "undefined") window.location.href = "/login";
}

/**
 * fetch wrapper that attaches the Bearer token, sets JSON content-type when a
 * body is present, and bounces to /login on 401. `path` is API-relative
 * (e.g. "/api/me/revision-queue").
 */
export async function authFetch(path: string, opts: RequestInit = {}): Promise<Response> {
  const headers = new Headers(opts.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (opts.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    clearToken();
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }
  return res;
}

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  preferences?: Record<string, unknown> | null;
}

/**
 * Loads the logged-in user; redirects to /login if there's no token.
 * Returns { user, loading } for page guards.
 */
export function useCurrentUser() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      if (typeof window !== "undefined") window.location.href = "/login";
      return;
    }
    authFetch("/api/auth/me")
      .then(async (r) => {
        if (r.ok) setUser(await r.json());
      })
      .finally(() => setLoading(false));
  }, []);

  return { user, loading };
}
