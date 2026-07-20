"use client";

import { useEffect, useState } from "react";
import { setToken } from "@/lib/auth";

export default function AuthCallbackPage() {
  const [msg, setMsg] = useState("Signing you in…");

  useEffect(() => {
    // The backend redirects here with the JWT in the URL fragment: #token=...
    const hash = window.location.hash.startsWith("#")
      ? window.location.hash.slice(1)
      : window.location.hash;
    const token = new URLSearchParams(hash).get("token");
    if (token) {
      setToken(token);
      window.location.replace("/");
    } else {
      setMsg("No token received. Redirecting to login…");
      setTimeout(() => window.location.replace("/login?error=no_token"), 1200);
    }
  }, []);

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--bg-base)", color: "var(--text-faint)", fontSize: 13,
      fontFamily: "var(--font-sans)",
    }}>
      {msg}
    </div>
  );
}
