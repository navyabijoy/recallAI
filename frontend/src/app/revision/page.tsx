"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

interface QueueProblem {
  id: string;
  title: string;
  url: string | null;
  platform: string;
  last_recall_strength: number | null;
}

interface QueueItem {
  topic: string;
  priority: number;
  forgetting_risk: number;
  stability_days: number;
  difficulty: number;
  practice_count: number;
  last_review: string;
  deadline_driven: boolean;
  reinforces_weak_dependents: number;
  problems: QueueProblem[];
}

interface RevisionQueue {
  decay_exponent: number;
  personalized: boolean;
  attempts_observed: number;
  queue: QueueItem[];
}

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

function daysAgo(iso: string) {
  const d = (Date.now() - new Date(iso).getTime()) / 86400000;
  if (d < 1) return "today";
  const n = Math.round(d);
  return `${n}d ago`;
}

const PLATFORM_ICONS: Record<string, string> = { leetcode: "🟡", codeforces: "🔵", github: "⚫" };

export default function RevisionPage() {
  const [data, setData] = useState<RevisionQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await authFetch(`/api/me/revision-queue`);
      if (!res.ok) throw new Error("Failed to load revision queue");
      setData(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "40px 24px", minHeight: "100vh" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 600, color: "var(--text-title)", marginBottom: 4 }}>
            Revision Queue
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>
            Ranked by <em>your</em> forgetting curve, prerequisites, and upcoming deadlines.
          </p>
        </div>
        <button className="btn" onClick={load}>Refresh</button>
      </div>

      {data && (
        <div style={{
          display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap",
          background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
          borderRadius: 8, padding: "12px 16px", margin: "16px 0 24px",
        }}>
          <span style={{ fontSize: 12, color: "var(--text-normal)" }}>
            {data.personalized ? (
              <>🧠 <strong style={{ color: "var(--accent)" }}>Personalized</strong> — model fit to your last {data.attempts_observed} solves</>
            ) : (
              <>⏳ <strong>Warming up</strong> — {data.attempts_observed}/8 solves until the model personalizes to you</>
            )}
          </span>
          <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-faint)" }}>
            decay exponent w = {data.decay_exponent.toFixed(3)}
          </span>
        </div>
      )}

      {loading && <p style={{ color: "var(--text-faint)", fontSize: 13 }}>Loading…</p>}
      {error && <p style={{ color: "var(--risk-high)", fontSize: 13 }}>{error}</p>}

      {data && data.queue.map((item, i) => (
        <div key={item.topic} style={{
          background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
          borderRadius: 8, padding: "16px 20px", marginBottom: 12,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-faint)", width: 22 }}>
                #{i + 1}
              </span>
              <span style={{ fontSize: 15, fontWeight: 600, color: "var(--text-title)" }}>{item.topic}</span>
              {item.deadline_driven && (
                <span className="tag" style={{ borderColor: "var(--risk-high)", color: "var(--risk-high)" }}>
                  ⏰ deadline
                </span>
              )}
              {item.reinforces_weak_dependents > 0 && (
                <span className="tag">🔗 unblocks {item.reinforces_weak_dependents}</span>
              )}
            </div>
            <span className={`tag risk-low`} style={{ borderColor: riskColor(item.forgetting_risk), color: riskColor(item.forgetting_risk), background: "transparent" }}>
              {riskLabel(item.forgetting_risk)}
            </span>
          </div>

          {/* forgetting-risk bar */}
          <div style={{ margin: "12px 0 10px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 11, color: "var(--text-faint)" }}>forgetting risk</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: riskColor(item.forgetting_risk) }}>
                {Math.round(item.forgetting_risk * 100)}%
              </span>
            </div>
            <div style={{ height: 5, background: "var(--bg-tertiary)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${item.forgetting_risk * 100}%`, background: riskColor(item.forgetting_risk), borderRadius: 3, transition: "width 0.6s ease" }} />
            </div>
          </div>

          <div style={{ display: "flex", gap: 18, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-faint)", flexWrap: "wrap" }}>
            <span>priority {item.priority.toFixed(3)}</span>
            <span>stability {item.stability_days.toFixed(1)}d</span>
            <span>difficulty {item.difficulty.toFixed(1)}</span>
            <span>{item.practice_count} solves</span>
            <span>last {daysAgo(item.last_review)}</span>
          </div>

          {item.problems.length > 0 && (
            <div style={{ marginTop: 12, borderTop: "1px solid var(--border-faint)", paddingTop: 10 }}>
              <p style={{ fontSize: 10, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
                Revisit these
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {item.problems.map((p) => (
                  <a key={p.id} href={p.url ?? "#"} target="_blank" rel="noreferrer"
                     style={{ fontSize: 12, color: "var(--text-normal)", textDecoration: "none", display: "flex", gap: 8, alignItems: "center" }}>
                    <span>{PLATFORM_ICONS[p.platform] ?? "•"}</span>
                    <span style={{ flex: 1 }}>{p.title}</span>
                    {p.last_recall_strength != null && (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: riskColor(1 - p.last_recall_strength) }}>
                        recall {Math.round(p.last_recall_strength * 100)}%
                      </span>
                    )}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}

      {data && data.queue.length === 0 && !loading && (
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
          No topics yet. Solve a few problems with the extension to build your queue.
        </p>
      )}
    </div>
  );
}
