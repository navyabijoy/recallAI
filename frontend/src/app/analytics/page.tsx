"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

interface RetentionEntry {
  topic: string;
  retrievability: number;
  forgetting_risk: number;
  stability: number;
  difficulty: number;
  practice_count: number;
  last_review: string;
}

interface AccuracyEntry {
  topic: string;
  total_attempts: number;
  success_rate: number;
}

interface SyncHealthEntry {
  id: string;
  platform: string;
  status: string;
  last_synced_at: string | null;
  events_count: number;
}

interface AnalyticsData {
  overall_health: number;
  total_topics: number;
  retention_breakdown: RetentionEntry[];
  accuracy_by_topic: AccuracyEntry[];
  sync_health: SyncHealthEntry[];
}

interface SyncSource {
  id: string;
  platform: string;
  status: string;
  last_synced_at: string | null;
}

interface SolveAttemptEntry {
  id: string;
  problem: string | null;
  platform: string | null;
  difficulty: string | null;
  time_to_understand_s: number | null;
  time_to_write_s: number | null;
  num_submissions: number;
  hints_used: number;
  verdict: string;
  recall_strength: number | null;
  perceived_difficulty: number | null;
  source: string;
  submitted_at: string;
}

function fmtSecs(s: number | null): string {
  if (s == null) return "–";
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem ? `${m}m ${rem}s` : `${m}m`;
}

const PLATFORM_ICONS: Record<string, string> = {
  leetcode: "🟡",
  github: "⚫",
  codeforces: "🔵",
};

const PLATFORM_COLORS: Record<string, string> = {
  leetcode: "#f0a500",
  github: "#c8c8c8",
  codeforces: "#3a78b5",
};

function riskColor(risk: number) {
  if (risk < 0.2) return "var(--risk-low)";
  if (risk < 0.5) return "var(--risk-mid)";
  return "var(--risk-high)";
}

function riskLabel(risk: number) {
  if (risk < 0.2) return "Stable";
  if (risk < 0.5) return "At Risk";
  return "Critical";
}

function RetentionBar({ value, label }: { value: number; label: string }) {
  const color = riskColor(1 - value);
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <span style={{ fontSize: 12, color: "var(--text-bright)" }}>{label}</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color }}>
          {Math.round(value * 100)}%
        </span>
      </div>
      <div style={{ height: 5, background: "var(--bg-tertiary)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{
          height: "100%", width: `${value * 100}%`,
          background: color, borderRadius: 3,
          transition: "width 0.6s ease",
        }} />
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color }: {
  label: string; value: string | number; sub?: string; color?: string;
}) {
  return (
    <div style={{
      background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
      borderRadius: 8, padding: "16px 20px",
    }}>
      <p style={{ fontSize: 11, color: "var(--text-faint)", fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
        {label}
      </p>
      <p style={{ fontSize: 28, fontWeight: 600, color: color ?? "var(--text-title)", lineHeight: 1 }}>{value}</p>
      {sub && <p style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 5 }}>{sub}</p>}
    </div>
  );
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [sources, setSources] = useState<SyncSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [addPlatform, setAddPlatform] = useState<string>("");
  const [addCred, setAddCred] = useState<string>("");
  const [addMode, setAddMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [solves, setSolves] = useState<SolveAttemptEntry[]>([]);
  const [activeSection, setActiveSection] = useState<"retention" | "accuracy" | "solves" | "sync">("retention");

  async function loadData() {
    setLoading(true);
    try {
      const [analyticsRes, sourcesRes, solvesRes] = await Promise.all([
        authFetch(`/api/me/analytics`),
        authFetch(`/api/me/sync-sources`),
        authFetch(`/api/me/solve-attempts`),
      ]);
      if (!analyticsRes.ok) throw new Error("Failed to load analytics");
      setData(await analyticsRes.json());
      if (sourcesRes.ok) setSources(await sourcesRes.json());
      if (solvesRes.ok) setSolves(await solvesRes.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function manualSync(sourceId: string) {
    setSyncing(sourceId);
    try {
      await authFetch(`/api/me/sync-sources/${sourceId}/sync`, { method: "POST" });
      await loadData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(null);
    }
  }

  async function disconnectSource(sourceId: string) {
    try {
      await authFetch(`/api/me/sync-sources/${sourceId}`, { method: "DELETE" });
      await loadData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Disconnect failed");
    }
  }

  async function connectPlatform() {
    if (!addPlatform) return;
    try {
      await authFetch(`/api/me/sync-sources`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform: addPlatform, credential: addCred || "mock" }),
      });
      setAddMode(false);
      setAddPlatform("");
      setAddCred("");
      await loadData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Connection failed");
    }
  }

  useEffect(() => { loadData(); }, []);

  const healthColor = data
    ? data.overall_health >= 80 ? "var(--risk-low)"
    : data.overall_health >= 60 ? "var(--risk-mid)"
    : "var(--risk-high)"
    : "var(--text-faint)";

  const tabs = [
    { id: "retention" as const, label: "Memory Retention" },
    { id: "accuracy" as const, label: "Practice Accuracy" },
    { id: "solves" as const, label: "Solve Telemetry" },
    { id: "sync" as const, label: "Sync Connections" },
  ];

  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg-base)",
      fontFamily: "var(--font-sans)",
      overflowY: "auto",
    }}>
      {/* Header */}
      <div style={{
        borderBottom: "1px solid var(--border-faint)",
        padding: "12px 24px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "var(--bg-primary)", position: "sticky", top: 0, zIndex: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <a href="/" style={{ color: "var(--text-faint)", textDecoration: "none", fontSize: 12 }}>← back</a>
          <div style={{ width: 1, height: 14, background: "var(--border-subtle)" }} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--accent)" }}>analytics</span>
          <span style={{ color: "var(--border-normal)" }}>/</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-bright)" }}>dashboard</span>
        </div>
        <button className="btn" onClick={loadData} disabled={loading}>
          ↺ Refresh
        </button>
      </div>

      {loading && (
        <div style={{ textAlign: "center", paddingTop: 80, color: "var(--text-faint)" }}>Loading analytics…</div>
      )}

      {error && (
        <div style={{
          margin: "20px 24px", padding: "8px 14px",
          background: "rgba(139,58,58,0.08)", border: "1px solid rgba(139,58,58,0.22)",
          borderRadius: 4, fontSize: 12, color: "var(--risk-high)",
        }}>
          {error}
        </div>
      )}

      {data && !loading && (
        <div style={{ maxWidth: 960, margin: "0 auto", padding: "24px 24px 60px" }}>

          {/* Stat cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, marginBottom: 28 }}>
            <StatCard
              label="Overall Memory Health"
              value={`${data.overall_health.toFixed(0)}%`}
              sub="Average FSRS retrievability"
              color={healthColor}
            />
            <StatCard
              label="Topics Tracked"
              value={data.total_topics}
              sub={`${data.retention_breakdown.filter(r => r.forgetting_risk > 0.2).length} at risk`}
            />
            <StatCard
              label="Platforms Connected"
              value={data.sync_health.filter(s => s.status === "active").length}
              sub={`${data.sync_health.filter(s => s.events_count > 0).reduce((a, s) => a + s.events_count, 0)} events synced total`}
            />
          </div>

          {/* Tab navigation */}
          <div style={{ display: "flex", gap: 2, marginBottom: 20, borderBottom: "1px solid var(--border-faint)" }}>
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveSection(tab.id)}
                style={{
                  padding: "7px 16px",
                  background: "none", border: "none",
                  borderBottom: `2px solid ${activeSection === tab.id ? "var(--accent)" : "transparent"}`,
                  cursor: "pointer",
                  fontFamily: "var(--font-sans)", fontSize: 12,
                  color: activeSection === tab.id ? "var(--text-title)" : "var(--text-faint)",
                  marginBottom: -1, transition: "color 80ms, border-color 80ms",
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Memory Retention */}
          {activeSection === "retention" && (
            <div>
              <p style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 16 }}>
                FSRS-calculated memory retrievability per topic. Lower bars indicate higher forgetting risk.
              </p>
              <div style={{
                background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
                borderRadius: 8, padding: "20px 24px", marginBottom: 24,
              }}>
                {data.retention_breakdown.map((r, i) => (
                  <RetentionBar key={i} value={r.retrievability} label={r.topic} />
                ))}
              </div>

              {/* Topic detail table */}
              <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-faint)", borderRadius: 8, overflow: "hidden" }}>
                <div style={{
                  display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr",
                  padding: "8px 16px", borderBottom: "1px solid var(--border-faint)",
                  background: "var(--bg-tertiary)",
                }}>
                  {["Topic", "Status", "Stability (d)", "Difficulty", "Sessions"].map(h => (
                    <span key={h} style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-faint)", textTransform: "uppercase" }}>
                      {h}
                    </span>
                  ))}
                </div>
                {data.retention_breakdown.map((r, i) => (
                  <div key={i} style={{
                    display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr",
                    padding: "9px 16px", borderBottom: "1px solid var(--border-faint)",
                    alignItems: "center",
                  }}>
                    <span style={{ fontSize: 12, color: "var(--text-bright)" }}>{r.topic}</span>
                    <span style={{ fontSize: 11 }}>
                      <span style={{
                        padding: "1px 7px", borderRadius: 10, fontSize: 10,
                        background: `${riskColor(r.forgetting_risk)}18`,
                        border: `1px solid ${riskColor(r.forgetting_risk)}44`,
                        color: riskColor(r.forgetting_risk),
                      }}>
                        {riskLabel(r.forgetting_risk)}
                      </span>
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-normal)" }}>
                      {r.stability.toFixed(1)}d
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-normal)" }}>
                      {r.difficulty.toFixed(1)} / 10
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)" }}>
                      {r.practice_count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Practice Accuracy */}
          {activeSection === "accuracy" && (
            <div>
              <p style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 16 }}>
                Pass/fail ratios computed from your synced LeetCode, Codeforces, and manual practice events.
              </p>
              {data.accuracy_by_topic.length === 0 ? (
                <div style={{
                  textAlign: "center", padding: 40,
                  background: "var(--bg-secondary)", border: "1px solid var(--border-faint)", borderRadius: 8,
                }}>
                  <p style={{ color: "var(--text-faint)", fontSize: 13 }}>No practice events logged yet.</p>
                  <p style={{ color: "var(--text-muted)", fontSize: 11, marginTop: 6 }}>
                    Connect a platform and sync, or log events manually.
                  </p>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {data.accuracy_by_topic.sort((a, b) => b.success_rate - a.success_rate).map((a, i) => (
                    <div key={i} style={{
                      background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
                      borderRadius: 8, padding: "12px 16px",
                      display: "flex", alignItems: "center", gap: 16,
                    }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                          <span style={{ fontSize: 13, color: "var(--text-bright)", fontWeight: 500 }}>{a.topic}</span>
                          <span style={{
                            fontFamily: "var(--font-mono)", fontSize: 12,
                            color: a.success_rate >= 0.7 ? "var(--risk-low)" : a.success_rate >= 0.4 ? "var(--risk-mid)" : "var(--risk-high)",
                          }}>
                            {(a.success_rate * 100).toFixed(0)}% success
                          </span>
                        </div>
                        <div style={{ height: 6, background: "var(--bg-tertiary)", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{
                            height: "100%", borderRadius: 3,
                            width: `${a.success_rate * 100}%`,
                            background: a.success_rate >= 0.7 ? "var(--risk-low)" : a.success_rate >= 0.4 ? "var(--risk-mid)" : "var(--risk-high)",
                            transition: "width 0.6s ease",
                          }} />
                        </div>
                      </div>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)", minWidth: 60, textAlign: "right" }}>
                        {a.total_attempts} attempts
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Solve Telemetry */}
          {activeSection === "solves" && (
            <div>
              <p style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 16 }}>
                Per-solve signals captured by the browser extension — how long you spent
                understanding vs. writing each solution, and the recall strength derived from it.
              </p>
              {solves.length === 0 ? (
                <div style={{
                  textAlign: "center", padding: 40,
                  background: "var(--bg-secondary)", border: "1px solid var(--border-faint)", borderRadius: 8,
                }}>
                  <p style={{ color: "var(--text-faint)", fontSize: 13 }}>No solves captured yet.</p>
                  <p style={{ color: "var(--text-muted)", fontSize: 11, marginTop: 6 }}>
                    Install the RecallAI extension and solve a problem on LeetCode or Codeforces.
                  </p>
                </div>
              ) : (
                <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-faint)", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{
                    display: "grid", gridTemplateColumns: "2fr 1fr 1fr 0.8fr 0.8fr 1fr",
                    padding: "8px 16px", borderBottom: "1px solid var(--border-faint)", background: "var(--bg-tertiary)",
                  }}>
                    {["Problem", "Understand", "Write", "Attempts", "Verdict", "Recall"].map(h => (
                      <span key={h} style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-faint)", textTransform: "uppercase" }}>
                        {h}
                      </span>
                    ))}
                  </div>
                  {solves.map((s) => {
                    const recall = s.recall_strength ?? 0;
                    const ok = s.verdict.toLowerCase() === "accepted" || s.verdict.toLowerCase() === "ok";
                    return (
                      <div key={s.id} style={{
                        display: "grid", gridTemplateColumns: "2fr 1fr 1fr 0.8fr 0.8fr 1fr",
                        padding: "9px 16px", borderBottom: "1px solid var(--border-faint)", alignItems: "center",
                      }}>
                        <span style={{ fontSize: 12, color: "var(--text-bright)", display: "flex", alignItems: "center", gap: 6 }}>
                          <span>{PLATFORM_ICONS[s.platform ?? ""] ?? "•"}</span>
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {s.problem ?? "unknown"}
                          </span>
                        </span>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-normal)" }}>{fmtSecs(s.time_to_understand_s)}</span>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-normal)" }}>{fmtSecs(s.time_to_write_s)}</span>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: s.num_submissions > 1 ? "var(--risk-mid)" : "var(--text-faint)" }}>
                          {s.num_submissions}{s.hints_used > 0 ? ` · ${s.hints_used}💡` : ""}
                        </span>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: ok ? "var(--risk-low)" : "var(--risk-high)" }}>
                          {ok ? "✓" : "✗"}
                        </span>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: riskColor(1 - recall) }}>
                          {Math.round(recall * 100)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Sync Connections */}
          {activeSection === "sync" && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                  Platform connections that auto-sync your submissions into RecallAI.
                </p>
                <button className="btn btn-accent" onClick={() => setAddMode(m => !m)}>
                  {addMode ? "× Cancel" : "+ Connect Platform"}
                </button>
              </div>

              {addMode && (
                <div style={{
                  background: "var(--bg-secondary)", border: "1px solid var(--accent-border)",
                  borderRadius: 8, padding: 16, marginBottom: 16,
                  display: "flex", flexDirection: "column", gap: 10,
                }}>
                  <p className="section-label">Add Platform</p>
                  <div>
                    <label className="form-label">Platform</label>
                    <select
                      value={addPlatform}
                      onChange={e => setAddPlatform(e.target.value)}
                      className="form-input"
                      style={{ background: "var(--bg-base)" }}
                    >
                      <option value="">Select platform…</option>
                      <option value="leetcode">LeetCode</option>
                      <option value="github">GitHub</option>
                      <option value="codeforces">Codeforces</option>
                    </select>
                  </div>
                  <div>
                    <label className="form-label">Username / Handle (leave blank for mock)</label>
                    <input
                      className="form-input"
                      placeholder="e.g. navyabijoy"
                      value={addCred}
                      onChange={e => setAddCred(e.target.value)}
                    />
                  </div>
                  <button className="btn btn-accent" onClick={connectPlatform} style={{ alignSelf: "flex-start" }}>
                    Connect
                  </button>
                </div>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {data.sync_health.map(s => (
                  <div key={s.id} style={{
                    background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
                    borderRadius: 8, padding: "14px 18px",
                    display: "flex", alignItems: "center", gap: 14,
                  }}>
                    <span style={{ fontSize: 24 }}>{PLATFORM_ICONS[s.platform] ?? "🔗"}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                        <span style={{
                          fontSize: 13, fontWeight: 500,
                          color: PLATFORM_COLORS[s.platform] ?? "var(--text-bright)",
                          textTransform: "capitalize",
                        }}>{s.platform}</span>
                        <span style={{
                          fontSize: 10, padding: "1px 7px", borderRadius: 10,
                          background: s.status === "active" ? "rgba(74,156,109,0.12)" : "rgba(139,58,58,0.08)",
                          border: `1px solid ${s.status === "active" ? "rgba(74,156,109,0.3)" : "rgba(139,58,58,0.22)"}`,
                          color: s.status === "active" ? "var(--risk-low)" : "var(--risk-high)",
                        }}>
                          {s.status}
                        </span>
                      </div>
                      <p style={{ fontSize: 11, color: "var(--text-faint)" }}>
                        {s.events_count} events synced
                        {s.last_synced_at
                          ? ` · last sync ${new Date(s.last_synced_at).toLocaleString()}`
                          : " · never synced"}
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button
                        className="btn btn-accent"
                        onClick={() => manualSync(s.id)}
                        disabled={syncing === s.id}
                      >
                        {syncing === s.id ? "Syncing…" : "↺ Sync"}
                      </button>
                      <button
                        className="btn btn-danger"
                        onClick={() => disconnectSource(s.id)}
                      >
                        Disconnect
                      </button>
                    </div>
                  </div>
                ))}

                {data.sync_health.length === 0 && (
                  <div style={{
                    textAlign: "center", padding: 40,
                    background: "var(--bg-secondary)", border: "1px solid var(--border-faint)", borderRadius: 8,
                  }}>
                    <p style={{ color: "var(--text-faint)", fontSize: 13 }}>No platforms connected.</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
