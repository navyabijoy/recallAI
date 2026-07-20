"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

interface AgentLogSummary {
  id: string;
  timestamp: string;
  reasoning: string;
  tool_call_count: number;
  session_count: number;
}

interface TraceStep {
  step: number;
  tool: string;
  arguments: Record<string, unknown>;
  result: unknown;
}

interface AgentLogDetail {
  id: string;
  timestamp: string;
  reasoning: string;
  final_plan: { sessions: Array<{ topic: string; duration_min: number; focus: string }> };
  trace: TraceStep[];
  calendar_context: { free_blocks: Array<{ date: string; start: string; end: string }>; busy_blocks: Array<{ date: string; start: string; end: string }> } | null;
  deadline_context: { deadlines: Array<{ event_title: string; date: string; related_topics: string[] }> } | null;
}

const TOOL_COLORS: Record<string, string> = {
  get_forgetting_scores: "#7c6fcd",
  get_topic_history: "#4a9c6d",
  get_related_concepts: "#b07d3a",
  get_available_time: "#5a8db5",
  check_plan_fits_budget: "#8b5a9c",
  log_recommendation: "#4a9c6d",
  get_calendar_availability: "#3a8b8b",
  get_upcoming_deadlines: "#c0643a",
};

const TOOL_ICONS: Record<string, string> = {
  get_forgetting_scores: "📉",
  get_topic_history: "📊",
  get_related_concepts: "🕸",
  get_available_time: "⏱",
  check_plan_fits_budget: "✅",
  log_recommendation: "💾",
  get_calendar_availability: "📅",
  get_upcoming_deadlines: "🔴",
};

function timeAgo(isoStr: string) {
  const diff = (Date.now() - new Date(isoStr).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function truncate(s: string, n = 180) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function ToolBadge({ name }: { name: string }) {
  const color = TOOL_COLORS[name] ?? "#909090";
  const icon = TOOL_ICONS[name] ?? "🔧";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      fontFamily: "var(--font-mono)", fontSize: 11, padding: "2px 8px",
      borderRadius: 20, border: `1px solid ${color}44`,
      background: `${color}14`, color,
    }}>
      {icon} {name}
    </span>
  );
}

function TraceCard({ step }: { step: TraceStep }) {
  const [expanded, setExpanded] = useState(false);
  const resultStr = JSON.stringify(step.result, null, 2);
  const argsStr = JSON.stringify(step.arguments);

  return (
    <div style={{
      borderLeft: `2px solid ${TOOL_COLORS[step.tool] ?? "var(--border-normal)"}`,
      paddingLeft: 14, marginBottom: 10,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-faint)", minWidth: 24 }}>
          #{step.step}
        </span>
        <ToolBadge name={step.tool} />
        {argsStr !== "{}" && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-faint)" }}>
            ({truncate(argsStr, 60)})
          </span>
        )}
      </div>
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          cursor: "pointer",
          background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
          borderRadius: 4, padding: "5px 10px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-faint)" }}>
            {expanded ? "▼" : "▶"} result
          </span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-faint)" }}>
            {typeof step.result === "object" ? (Array.isArray(step.result) ? `[${(step.result as unknown[]).length} items]` : "{ object }") : String(step.result)}
          </span>
        </div>
        {expanded && (
          <pre style={{
            fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-normal)",
            marginTop: 6, overflowX: "auto", whiteSpace: "pre-wrap", maxHeight: 260,
          }}>
            {resultStr}
          </pre>
        )}
      </div>
    </div>
  );
}

export default function TracePage() {
  const [logs, setLogs] = useState<AgentLogSummary[]>([]);
  const [selected, setSelected] = useState<AgentLogDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);

  async function loadLogs() {
    setLoading(true);
    try {
      const res = await authFetch(`/api/me/agent-logs`);
      if (!res.ok) throw new Error("Failed to load agent logs");
      const data = await res.json();
      setLogs(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(id: string) {
    setDetailLoading(true);
    try {
      const res = await authFetch(`/api/me/agent-logs/${id}`);
      if (!res.ok) throw new Error("Failed to load trace detail");
      const data = await res.json();
      setSelected(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setDetailLoading(false);
    }
  }

  async function triggerPlan() {
    setTriggering(true);
    try {
      const res = await authFetch(`/api/me/plan`);
      if (!res.ok) throw new Error("Failed to trigger plan");
      await loadLogs();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setTriggering(false);
    }
  }

  useEffect(() => { loadLogs(); }, []);

  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg-base)",
      fontFamily: "var(--font-sans)", display: "flex", flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{
        borderBottom: "1px solid var(--border-faint)",
        padding: "12px 24px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "var(--bg-primary)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <a href="/" style={{ color: "var(--text-faint)", textDecoration: "none", fontSize: 12 }}>← back</a>
          <div style={{ width: 1, height: 14, background: "var(--border-subtle)" }} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--accent)" }}>agent</span>
          <span style={{ color: "var(--border-normal)" }}>/</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-bright)" }}>trace</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={loadLogs} disabled={loading}>
            ↺ Refresh
          </button>
          <button className="btn btn-accent" onClick={triggerPlan} disabled={triggering}>
            {triggering ? "Planning…" : "▶ Run Agent"}
          </button>
        </div>
      </div>

      {/* Body */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* Left panel — log list */}
        <div style={{
          width: 340, flexShrink: 0,
          borderRight: "1px solid var(--border-faint)",
          overflowY: "auto",
          background: "var(--bg-primary)",
        }}>
          <div style={{ padding: "12px 16px 8px" }}>
            <p className="section-label">Planning Runs</p>
          </div>

          {loading && (
            <div style={{ padding: "24px 16px", textAlign: "center", color: "var(--text-faint)", fontSize: 12 }}>
              Loading…
            </div>
          )}

          {!loading && logs.length === 0 && (
            <div style={{ padding: "24px 16px", textAlign: "center" }}>
              <p style={{ color: "var(--text-faint)", fontSize: 12 }}>No agent runs yet.</p>
              <p style={{ color: "var(--text-muted)", fontSize: 11, marginTop: 6 }}>Click "Run Agent" to trigger a plan.</p>
            </div>
          )}

          {logs.map(log => (
            <div
              key={log.id}
              onClick={() => loadDetail(log.id)}
              style={{
                padding: "10px 16px",
                cursor: "pointer",
                borderBottom: "1px solid var(--border-faint)",
                background: selected?.id === log.id ? "var(--bg-active)" : "transparent",
                transition: "background 80ms",
              }}
              onMouseEnter={e => { if (selected?.id !== log.id) (e.currentTarget as HTMLElement).style.background = "var(--bg-hover)"; }}
              onMouseLeave={e => { if (selected?.id !== log.id) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--accent)" }}>
                  run #{log.id.slice(0, 8)}
                </span>
                <span style={{ fontSize: 10, color: "var(--text-faint)" }}>{timeAgo(log.timestamp)}</span>
              </div>
              <p style={{ fontSize: 12, color: "var(--text-bright)", marginBottom: 6 }}>
                {truncate(log.reasoning, 90)}
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                <span className="tag">{log.tool_call_count} tools</span>
                <span className="tag">{log.session_count} sessions</span>
              </div>
            </div>
          ))}
        </div>

        {/* Right panel — trace detail */}
        <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
          {!selected && !detailLoading && (
            <div style={{
              height: "100%", display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 12,
            }}>
              <div style={{ fontSize: 32 }}>🔍</div>
              <p style={{ color: "var(--text-normal)", fontSize: 13 }}>Select a planning run to inspect</p>
              <p style={{ color: "var(--text-faint)", fontSize: 11 }}>
                The agent's full reasoning, tool calls, and calendar context will appear here
              </p>
            </div>
          )}

          {detailLoading && (
            <div style={{ textAlign: "center", color: "var(--text-faint)", paddingTop: 60 }}>Loading trace…</div>
          )}

          {selected && !detailLoading && (
            <div style={{ maxWidth: 800 }}>
              {/* Run header */}
              <div style={{ marginBottom: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--accent)" }}>
                    run #{selected.id.slice(0, 8)}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--text-faint)" }}>
                    {new Date(selected.timestamp).toLocaleString()}
                  </span>
                </div>
                <h2 style={{ fontSize: 16, color: "var(--text-title)", marginBottom: 4 }}>Agent Reasoning</h2>
                <p style={{ fontSize: 13, color: "var(--text-bright)", lineHeight: 1.6 }}>{selected.reasoning}</p>
              </div>

              {/* Final plan */}
              <div style={{ marginBottom: 24 }}>
                <p className="section-label">Final Study Plan</p>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {selected.final_plan?.sessions?.map((s, i) => (
                    <div key={i} style={{
                      display: "flex", alignItems: "flex-start", gap: 12,
                      padding: "10px 14px",
                      background: "var(--bg-secondary)", border: "1px solid var(--border-faint)", borderRadius: 6,
                    }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: 6,
                        background: "var(--accent-dim)", border: "1px solid var(--accent-border)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--accent)", flexShrink: 0,
                      }}>
                        {s.duration_min}m
                      </div>
                      <div>
                        <p style={{ fontSize: 13, color: "var(--text-bright)", fontWeight: 500 }}>{s.topic}</p>
                        <p style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 2 }}>{s.focus}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Calendar context */}
              {selected.calendar_context && (
                <div style={{ marginBottom: 24 }}>
                  <p className="section-label">📅 Calendar Context</p>
                  <div style={{
                    background: "var(--bg-secondary)", border: "1px solid var(--border-faint)",
                    borderRadius: 6, padding: 12,
                  }}>
                    <p style={{ fontSize: 12, color: "var(--text-normal)", marginBottom: 8 }}>
                      <strong style={{ color: "var(--text-bright)" }}>Free blocks:</strong>{" "}
                      {selected.calendar_context.free_blocks.length} available
                    </p>
                    {selected.deadline_context?.deadlines && selected.deadline_context.deadlines.length > 0 && (
                      <>
                        <p style={{ fontSize: 12, color: "var(--text-normal)", marginBottom: 6 }}>
                          <strong style={{ color: "#c0643a" }}>🔴 Upcoming deadlines:</strong>
                        </p>
                        {selected.deadline_context.deadlines.map((dl, i) => (
                          <div key={i} style={{
                            display: "flex", alignItems: "center", gap: 10,
                            padding: "5px 0", borderBottom: "1px solid var(--border-faint)",
                          }}>
                            <span style={{ fontSize: 11, color: "var(--text-faint)", minWidth: 90, fontFamily: "var(--font-mono)" }}>
                              {dl.date}
                            </span>
                            <span style={{ fontSize: 12, color: "var(--text-bright)" }}>{dl.event_title}</span>
                            {dl.related_topics.length > 0 && (
                              <div style={{ display: "flex", gap: 4, marginLeft: "auto" }}>
                                {dl.related_topics.map(t => (
                                  <span key={t} className="tag">{t}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                </div>
              )}

              {/* Tool call trace */}
              <div>
                <p className="section-label">Execution Trace ({selected.trace.length} steps)</p>
                {selected.trace.map((step, i) => (
                  <TraceCard key={i} step={step} />
                ))}
              </div>
            </div>
          )}

          {error && (
            <div style={{
              margin: 20, padding: "8px 14px",
              background: "rgba(139,58,58,0.08)", border: "1px solid rgba(139,58,58,0.22)",
              borderRadius: 4, fontSize: 12, color: "var(--risk-high)",
            }}>
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
