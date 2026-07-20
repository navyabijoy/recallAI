"use client";

import { useEffect, useState } from "react";
import { authFetch, useCurrentUser, logout, API } from "@/lib/auth";

interface ApiKeyRow {
  id: string;
  label: string;
  masked_key: string;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
}

export default function SettingsPage() {
  const { user, loading } = useCurrentUser();
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState(false);

  async function loadKeys() {
    const r = await authFetch("/api/me/api-keys");
    if (r.ok) setKeys(await r.json());
  }

  useEffect(() => {
    if (user) loadKeys();
  }, [user]);

  async function createKey() {
    setCreating(true);
    setNewKey(null);
    try {
      const r = await authFetch("/api/me/api-keys", {
        method: "POST",
        body: JSON.stringify({ label: "browser-extension" }),
      });
      if (r.ok) {
        const data = await r.json();
        setNewKey(data.key);
        await loadKeys();
      }
    } finally {
      setCreating(false);
    }
  }

  function copyKey() {
    if (!newKey) return;
    navigator.clipboard.writeText(newKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (loading || !user) {
    return <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-faint)" }}>Loading…</div>;
  }

  const card: React.CSSProperties = {
    background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
    borderRadius: 8, padding: "18px 20px", marginBottom: 16,
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "40px 24px", minHeight: "100vh", fontFamily: "var(--font-sans)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <a href="/" style={{ color: "var(--text-faint)", textDecoration: "none", fontSize: 12 }}>← back</a>
          <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--text-title)" }}>Settings</h1>
        </div>
        <button className="btn" onClick={logout}>Log out</button>
      </div>

      {/* Account */}
      <div style={card}>
        <p style={{ fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Account</p>
        <p style={{ fontSize: 14, color: "var(--text-title)" }}>{user.name}</p>
        <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{user.email}</p>
      </div>

      {/* Extension key */}
      <div style={card}>
        <p style={{ fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Browser Extension</p>
        <p style={{ fontSize: 12, color: "var(--text-normal)", marginBottom: 14, lineHeight: 1.5 }}>
          Generate an API key, then paste it (with the backend URL below) into the RecallAI
          extension popup. The extension posts your solve telemetry to your account.
        </p>
        <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-faint)", marginBottom: 14 }}>
          Backend URL: <span style={{ color: "var(--text-normal)" }}>{API}</span>
        </div>

        <button className="btn btn-accent" onClick={createKey} disabled={creating}>
          {creating ? "Generating…" : "+ Generate new key"}
        </button>

        {newKey && (
          <div style={{
            marginTop: 14, padding: "12px 14px", borderRadius: 6,
            background: "var(--bg-tertiary)", border: "1px solid var(--accent-border)",
          }}>
            <p style={{ fontSize: 11, color: "var(--accent)", marginBottom: 6 }}>
              Copy this now — it won't be shown again:
            </p>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <code style={{ flex: 1, fontSize: 12, color: "var(--text-bright)", wordBreak: "break-all" }}>{newKey}</code>
              <button className="btn" onClick={copyKey}>{copied ? "✓ Copied" : "Copy"}</button>
            </div>
          </div>
        )}

        {keys.length > 0 && (
          <div style={{ marginTop: 18 }}>
            <p style={{ fontSize: 10, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Existing keys</p>
            {keys.map((k) => (
              <div key={k.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-faint)", padding: "5px 0", borderTop: "1px solid var(--border-faint)" }}>
                <span style={{ fontFamily: "var(--font-mono)" }}>{k.masked_key}</span>
                <span>{k.label}{k.last_used_at ? " · used" : " · unused"}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
