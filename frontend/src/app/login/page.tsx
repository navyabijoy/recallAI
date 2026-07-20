"use client";

import { useEffect, useState } from "react";
import { googleLoginUrl, getToken } from "@/lib/auth";

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Already signed in? go home.
    if (getToken()) window.location.href = "/";
    const params = new URLSearchParams(window.location.search);
    if (params.get("error")) setError(params.get("error"));
  }, []);

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--bg-base)", fontFamily: "var(--font-sans)", padding: 24,
    }}>
      <div style={{
        width: "100%", maxWidth: 380, textAlign: "center",
        background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
        borderRadius: 12, padding: "40px 32px",
      }}>
        <div style={{ fontSize: 30, marginBottom: 8 }}>🧠</div>
        <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--text-title)", marginBottom: 6 }}>recallAI</h1>
        <p style={{ fontSize: 13, color: "var(--text-faint)", marginBottom: 28 }}>
          Revise DSA based on how <em>your</em> memory actually works.
        </p>

        {error && (
          <div style={{
            marginBottom: 16, padding: "8px 12px", borderRadius: 6, fontSize: 12,
            background: "rgba(139,58,58,0.08)", border: "1px solid rgba(139,58,58,0.22)",
            color: "var(--risk-high)",
          }}>
            Sign-in failed ({error}). Please try again.
          </div>
        )}

        <a
          href={googleLoginUrl()}
          style={{
            display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
            padding: "11px 16px", borderRadius: 8, textDecoration: "none",
            background: "#fff", color: "#1f1f1f", fontSize: 14, fontWeight: 500,
            border: "1px solid #dadce0",
          }}
        >
          <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          Sign in with Google
        </a>

        <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 20 }}>
          Your solves stay private to your account.
        </p>
      </div>
    </div>
  );
}
