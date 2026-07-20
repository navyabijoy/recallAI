"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { authFetch, useCurrentUser } from "@/lib/auth";

const GraphViz = dynamic(() => import("../components/GraphViz"), { ssr: false });

// ── Types ──────────────────────────────────────────────────────────────
interface GraphNode {
  id: string; stability: number; difficulty: number;
  retrievability: number; forgetting_risk: number;
  last_review: string; practice_count: number;
}
interface Stats {
  health_score: number; decayed_topics_count: number; nodes_count: number;
}
interface DecayAlert {
  trigger: boolean; days_inactive: number;
  current_health: number; previous_health: number;
  decayed_topics: string[]; estimated_review_time_min: number;
}
interface SessionItem { topic: string; duration_min: number; focus: string; }
interface AgentResult {
  plan: { sessions: SessionItem[] };
  reasoning: string; trace: any[]; model_used: string;
}

const TOPICS = ["Arrays","Sliding Window","Binary Search","Heap","Trie","Graphs","Union Find","Dynamic Programming"];
const GRADES = [
  { val: "AGAIN", label: "Again",  sub: "Forgot"    },
  { val: "HARD",  label: "Hard",   sub: "Struggled" },
  { val: "GOOD",  label: "Good",   sub: "Correct"   },
  { val: "EASY",  label: "Easy",   sub: "Trivial"   },
];

// ── Inline style constants ─────────────────────────────────────────────
const S = {
  shell: {
    display: "grid" as const,
    gridTemplateColumns: "220px 1fr",
    gridTemplateRows: "1fr 24px",
    height: "100vh",
    width: "100vw",
    background: "#0d0d0d",
    fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
    overflow: "hidden",
  },
  sidebar: {
    gridRow: "1",
    gridColumn: "1",
    background: "#111111",
    borderRight: "1px solid rgba(255,255,255,0.06)",
    display: "flex",
    flexDirection: "column" as const,
    overflow: "hidden",
    color: "#909090",
    fontSize: 13,
  },
  main: {
    gridRow: "1",
    gridColumn: "2",
    display: "flex",
    flexDirection: "column" as const,
    overflow: "hidden",
    background: "#0d0d0d",
    minWidth: 0,
  },
  statusbar: {
    gridRow: "2",
    gridColumn: "1 / -1",
    background: "rgba(124,111,205,0.07)",
    borderTop: "1px solid rgba(124,111,205,0.18)",
    display: "flex",
    alignItems: "center",
    padding: "0 12px",
    gap: 16,
    fontFamily: "'JetBrains Mono', ui-monospace, monospace",
    fontSize: 10,
    color: "#5a5a5a",
  },
  topbar: {
    height: 38,
    borderBottom: "1px solid rgba(255,255,255,0.05)",
    display: "flex",
    alignItems: "center",
    padding: "0 14px",
    gap: 8,
    background: "#111111",
    flexShrink: 0,
    fontSize: 13,
    color: "#c8c8c8",
    fontWeight: 500,
  },
};

// ── Tiny SVG icons ─────────────────────────────────────────────────────
const Icons = {
  graph:   <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="3.5" cy="4" r="1.5"/><circle cx="12.5" cy="4" r="1.5"/><circle cx="8" cy="12" r="1.5"/><path d="M5 4h6M4.2 5.5 8 11M11.8 5.5 8 11"/></svg>,
  clock:   <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 5v3.5l2.5 1.5"/></svg>,
  book:    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 2h7a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3V2z"/><path d="M11 6h2v7h-2"/></svg>,
  chat:    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 3h12v8H9l-3 2V11H2V3z"/></svg>,
  refresh: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M13 8A5 5 0 1 1 8 3c1.3 0 2.5.5 3.5 1.3L14 2"/><path d="M14 2v4h-4"/></svg>,
  term:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M5 6l2.5 2L5 10M9 10h2"/></svg>,
  warn:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 2L1 14h14L8 2z"/><line x1="8" y1="7" x2="8" y2="10"/><circle cx="8" cy="12" r=".6" fill="currentColor"/></svg>,
};

// ── Component ──────────────────────────────────────────────────────────
export default function Dashboard() {
  const { user, loading: authLoading } = useCurrentUser();
  const [graphData, setGraphData]     = useState<{ nodes: GraphNode[]; edges: any[] } | null>(null);
  const [stats, setStats]             = useState<Stats | null>(null);
  const [alert, setAlert]             = useState<DecayAlert | null>(null);
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [showTrace, setShowTrace]     = useState(false);
  const [activeTab, setActiveTab]     = useState<"graph"|"plan"|"log">("graph");

  // Log form
  const [logTopic, setLogTopic]         = useState("Arrays");
  const [logGrade, setLogGrade]         = useState("GOOD");
  const [logDuration, setLogDuration]   = useState(30);
  const [logMistakes, setLogMistakes]   = useState(0);
  const [loggingEvent, setLoggingEvent] = useState(false);
  const [logFeedback, setLogFeedback]   = useState("");

  // Sim
  const [simDays, setSimDays]       = useState(14);
  const [simulating, setSimulating] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [g, s, a] = await Promise.all([
        authFetch(`/api/me/graph`).then(r => r.ok ? r.json() : null),
        authFetch(`/api/me/stats`).then(r => r.ok ? r.json() : null),
        authFetch(`/api/me/decay-alert`).then(r => r.ok ? r.json() : null),
      ]);
      if (g) setGraphData(g);
      if (s) setStats(s);
      if (a) setAlert(a);
    } catch { /* server starting up */ }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const planSession = async () => {
    setLoadingPlan(true);
    try {
      const r = await authFetch(`/api/me/plan`);
      if (r.ok) { setAgentResult(await r.json()); setActiveTab("plan"); }
    } finally { setLoadingPlan(false); }
  };

  const logEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoggingEvent(true); setLogFeedback("");
    try {
      const r = await authFetch(`/api/me/event`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic_name: logTopic, difficulty: logGrade, duration_min: logDuration, mistakes: logMistakes }),
      });
      if (r.ok) { setLogFeedback(`✓ Logged ${logTopic}`); fetchAll(); }
    } finally { setLoggingEvent(false); }
  };

  const simulate = async () => {
    setSimulating(true);
    try {
      await authFetch(`/api/me/simulate-inactivity?days=${simDays}`, { method: "POST" });
      fetchAll(); setAgentResult(null);
    } finally { setSimulating(false); }
  };

  const health   = stats?.health_score ?? 100;
  const decayed  = stats?.decayed_topics_count ?? 0;
  const hColor   = health < 70 ? "#8b3a3a" : health < 85 ? "#b07d3a" : "#4a9c6d";
  const queue    = graphData ? [...graphData.nodes].sort((a,b) => b.forgetting_risk - a.forgetting_risk).slice(0,7) : [];

  // ── Sidebar ────────────────────────────────────────────────────────
  const sidebar = (
    <div style={S.sidebar}>
      {/* Logo */}
      <Link href="/landing" style={{ display:"flex", alignItems:"center", gap:8, padding:"13px 14px 11px", borderBottom:"1px solid rgba(255,255,255,0.05)", textDecoration:"none" }}>
        <div style={{ width:20, height:20, borderRadius:4, background:"rgba(124,111,205,0.12)", border:"1px solid rgba(124,111,205,0.28)", display:"grid", placeItems:"center", fontFamily:"'JetBrains Mono',monospace", fontSize:11, fontWeight:700, color:"#7c6fcd", flexShrink:0 }}>R</div>
        <span style={{ fontSize:13, fontWeight:600, color:"#c8c8c8", letterSpacing:"-0.01em" }}>RecallAI</span>
        <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:9, color:"#3d3d3d", marginLeft:"auto" }}>v1.0</span>
      </Link>

      {/* Nav */}
      <div style={{ padding:"10px 8px 4px" }}>
        <div style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:9, fontWeight:500, letterSpacing:"0.12em", textTransform:"uppercase", color:"#3d3d3d", padding:"0 8px 7px" }}>Views</div>
        {([
          { key:"graph", icon: Icons.graph, label:"Knowledge Map" },
          { key:"plan",  icon: Icons.clock, label:"Session Plan"  },
          { key:"log",   icon: Icons.book,  label:"Log Practice"  },
        ] as const).map(item => (
          <button key={item.key} onClick={() => setActiveTab(item.key)} className={`nav-item${activeTab === item.key ? " active" : ""}`}>
            {item.icon}{item.label}
          </button>
        ))}
        <Link href="/coach" className="nav-item">{Icons.chat}AI Coach</Link>
      </div>

      <div style={{ height:1, background:"rgba(255,255,255,0.04)", margin:"4px 16px" }} />

      {/* Review queue */}
      <div style={{ padding:"8px 8px 4px", flex:1, overflow:"hidden", display:"flex", flexDirection:"column" }}>
        <div style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:9, fontWeight:500, letterSpacing:"0.12em", textTransform:"uppercase", color:"#3d3d3d", padding:"0 8px 7px" }}>Review Queue</div>
        <div style={{ flex:1, overflowY:"auto" }}>
          {queue.map(n => {
            const r = n.forgetting_risk;
            const c = r > 0.4 ? "#8b3a3a" : r > 0.15 ? "#b07d3a" : "#4a9c6d";
            return (
              <div key={n.id} className="queue-item" onClick={() => { setLogTopic(n.id); setActiveTab("log"); }}>
                <div style={{ width:6, height:6, borderRadius:"50%", background:c, flexShrink:0 }} />
                <span style={{ flex:1, fontSize:12, color:"#c8c8c8", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{n.id}</span>
                <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:10, color:"#5a5a5a" }}>{Math.round(r*100)}%</span>
              </div>
            );
          })}
          {!graphData && <div style={{ padding:"8px 8px", color:"#3d3d3d", fontSize:11 }}>—</div>}
        </div>
      </div>

      {/* Stats */}
      <div style={{ borderTop:"1px solid rgba(255,255,255,0.05)", padding:"10px 14px" }}>
        <div className="metric-row">
          <span style={{ fontSize:12, color:"#5a5a5a" }}>Health</span>
          <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:12, fontWeight:500, color:hColor }}>{health}%</span>
        </div>
        <div style={{ marginTop:5 }}>
          <div className="progress-bar">
            <div className={`progress-fill${health < 70 ? " warn" : " good"}`} style={{ width:`${health}%` }} />
          </div>
        </div>
        <div className="metric-row" style={{ marginTop:8 }}>
          <span style={{ fontSize:12, color:"#5a5a5a" }}>Decayed</span>
          <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:12, fontWeight:500, color:"#c8c8c8" }}>{decayed}</span>
        </div>
        <div className="metric-row">
          <span style={{ fontSize:12, color:"#5a5a5a" }}>Nodes</span>
          <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:12, fontWeight:500, color:"#c8c8c8" }}>{stats?.nodes_count ?? 0}</span>
        </div>
      </div>
    </div>
  );

  // ── Topbar ─────────────────────────────────────────────────────────
  const tabLabels: Record<string, string> = { graph:"Knowledge Map", plan:"Session Plan", log:"Log Practice" };
  const topbar = (
    <div style={S.topbar}>
      <span>{tabLabels[activeTab]}</span>
      {alert?.trigger && (
        <span style={{ display:"inline-flex", alignItems:"center", gap:4, color:"#b07d3a", fontSize:11, fontFamily:"'JetBrains Mono',monospace" }}>
          {Icons.warn} {alert.days_inactive}d inactive · health {alert.current_health}%
        </span>
      )}
      <div style={{ marginLeft:"auto", display:"flex", gap:6 }}>
        <button onClick={fetchAll} className="btn" style={{ padding:"3px 8px" }}>{Icons.refresh}</button>
        <button onClick={planSession} disabled={loadingPlan} className="btn btn-accent">
          {loadingPlan ? "Planning…" : "Plan Session"}
        </button>
      </div>
    </div>
  );

  // ── Decay alert ────────────────────────────────────────────────────
  const decayBanner = alert?.trigger && (
    <div className="decay-alert">
      <span style={{ color:"#b07d3a", fontWeight:600, display:"inline-flex", alignItems:"center", gap:5 }}>
        {Icons.warn} {alert.days_inactive} days away
      </span>
      <span style={{ color:"#909090" }}>
        Health <span style={{ fontFamily:"'JetBrains Mono',monospace" }}>{alert.previous_health}%</span>
        {" → "}
        <span style={{ fontFamily:"'JetBrains Mono',monospace", color:"#b07d3a" }}>{alert.current_health}%</span>
        {" · "}Affected: {alert.decayed_topics.join(", ")}
      </span>
      <button onClick={planSession} disabled={loadingPlan} className="btn btn-accent" style={{ marginLeft:"auto" }}>
        Generate Rescue Plan ({alert.estimated_review_time_min}m)
      </button>
    </div>
  );

  // ── Graph tab ──────────────────────────────────────────────────────
  const graphTab = (
    <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden", minHeight:0 }}>
      <div style={{ padding:"7px 14px", borderBottom:"1px solid rgba(255,255,255,0.05)", background:"#111111", display:"flex", alignItems:"center", justifyContent:"space-between", flexShrink:0 }}>
        <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:10, letterSpacing:"0.1em", textTransform:"uppercase", color:"#5a5a5a" }}>DSA prerequisite graph</span>
        <div style={{ display:"flex", gap:6, alignItems:"center" }}>
          <span className="tag risk-low">mastered</span>
          <span className="tag risk-mid">decaying</span>
          <span className="tag risk-high">forgotten</span>
        </div>
      </div>
      <div style={{ flex:1, minHeight:0, position:"relative" }}>
        <div style={{ position:"absolute", inset:0 }}>
          {graphData
            ? <GraphViz nodesData={graphData.nodes} edgesData={graphData.edges} onNodeClick={(n) => { setLogTopic(n); setActiveTab("log"); }} />
            : <div style={{ height:"100%", display:"grid", placeItems:"center", color:"#3d3d3d", fontFamily:"'JetBrains Mono',monospace", fontSize:12 }}>connecting to backend…</div>
          }
        </div>
      </div>
    </div>
  );

  // ── Plan tab ───────────────────────────────────────────────────────
  const planTab = (
    <div style={{ flex:1, overflowY:"auto", display:"flex", flexDirection:"column" }}>
      <div style={{ padding:"7px 14px", borderBottom:"1px solid rgba(255,255,255,0.05)", background:"#111111", display:"flex", alignItems:"center", justifyContent:"space-between", flexShrink:0 }}>
        <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:10, letterSpacing:"0.1em", textTransform:"uppercase", color:"#5a5a5a" }}>agent session plan</span>
        <button onClick={planSession} disabled={loadingPlan} className="btn btn-accent">
          {loadingPlan ? "Running agent loop…" : "Run Planning Agent"}
        </button>
      </div>
      <div style={{ padding:16, flex:1 }}>
        {!agentResult ? (
          <div style={{ color:"#3d3d3d", fontFamily:"'JetBrains Mono',monospace", fontSize:12, paddingTop:32, textAlign:"center" }}>
            No plan generated yet — click &ldquo;Run Planning Agent&rdquo;
          </div>
        ) : (
          <>
            {/* Reasoning */}
            <div style={{ marginBottom:16 }}>
              <div className="section-label">Agent Reasoning</div>
              <p style={{ fontSize:12, color:"#c8c8c8", lineHeight:1.65, fontStyle:"italic" }}>
                &ldquo;{agentResult.reasoning}&rdquo;
              </p>
              <span className="tag" style={{ marginTop:6, display:"inline-flex", gap:4 }}>
                {Icons.term} {agentResult.model_used}
              </span>
            </div>
            <div className="divider" />
            {/* Sessions table */}
            <div style={{ marginBottom:16 }}>
              <div className="section-label">Scheduled Sessions</div>
              <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                <thead>
                  <tr style={{ borderBottom:"1px solid rgba(255,255,255,0.06)" }}>
                    {["Topic","Duration","Focus"].map(h => (
                      <th key={h} style={{ textAlign:"left", padding:"4px 8px", fontFamily:"'JetBrains Mono',monospace", fontSize:10, fontWeight:500, textTransform:"uppercase", letterSpacing:"0.08em", color:"#5a5a5a" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {agentResult.plan.sessions.map((s, i) => (
                    <tr key={i} style={{ borderBottom:"1px solid rgba(255,255,255,0.04)" }}>
                      <td style={{ padding:"8px 8px", color:"#e4e4e4", fontWeight:500 }}>{s.topic}</td>
                      <td style={{ padding:"8px 8px", fontFamily:"'JetBrains Mono',monospace", color:"#909090" }}>{s.duration_min} min</td>
                      <td style={{ padding:"8px 8px", color:"#5a5a5a" }}>{s.focus}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="divider" />
            {/* Trace */}
            <div>
              <button onClick={() => setShowTrace(!showTrace)} className="btn" style={{ marginBottom:8 }}>
                {Icons.term} {showTrace ? "Hide" : "Show"} tool-call trace ({agentResult.trace?.length ?? 0} steps)
              </button>
              {showTrace && (
                <div style={{ background:"#0d0d0d", border:"1px solid rgba(255,255,255,0.05)", borderRadius:4, maxHeight:260, overflowY:"auto" }}>
                  {agentResult.trace?.map((t, i) => (
                    <div key={i} className="trace-entry">
                      <div><span className="trace-fn">{t.tool}</span><span className="trace-args">({JSON.stringify(t.arguments ?? {})})</span></div>
                      <div className="trace-result">→ {JSON.stringify(t.result)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );

  // ── Log tab ────────────────────────────────────────────────────────
  const logTab = (
    <div style={{ flex:1, overflowY:"auto" }}>
      <div style={{ padding:"7px 14px", borderBottom:"1px solid rgba(255,255,255,0.05)", background:"#111111", flexShrink:0 }}>
        <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:10, letterSpacing:"0.1em", textTransform:"uppercase", color:"#5a5a5a" }}>log practice session</span>
      </div>
      <div style={{ padding:16, maxWidth:500 }}>
        <form onSubmit={logEvent} style={{ display:"flex", flexDirection:"column", gap:14 }}>
          <div>
            <label className="form-label">Topic</label>
            <select className="form-input" value={logTopic} onChange={e => setLogTopic(e.target.value)}>
              {TOPICS.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">Recall Quality (FSRS Grade)</label>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:6 }}>
              {GRADES.map(g => (
                <button key={g.val} type="button" onClick={() => setLogGrade(g.val)} style={{
                  padding:"8px 6px", borderRadius:4,
                  border: logGrade === g.val ? "1px solid rgba(124,111,205,0.28)" : "1px solid rgba(255,255,255,0.09)",
                  background: logGrade === g.val ? "rgba(124,111,205,0.10)" : "#161616",
                  color: logGrade === g.val ? "#7c6fcd" : "#909090",
                  cursor:"pointer", display:"flex", flexDirection:"column", alignItems:"center", gap:2,
                }}>
                  <span style={{ fontSize:12, fontWeight:500 }}>{g.label}</span>
                  <span style={{ fontSize:10, color:"#5a5a5a" }}>{g.sub}</span>
                </button>
              ))}
            </div>
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10 }}>
            <div>
              <label className="form-label">Duration (min)</label>
              <input type="number" min={1} max={300} value={logDuration} onChange={e => setLogDuration(+e.target.value)} className="form-input mono" />
            </div>
            <div>
              <label className="form-label">Mistakes</label>
              <input type="number" min={0} max={100} value={logMistakes} onChange={e => setLogMistakes(+e.target.value)} className="form-input mono" />
            </div>
          </div>
          <div>
            <button type="submit" disabled={loggingEvent} className="btn btn-accent">
              {loggingEvent ? "Saving…" : "Log Session"}
            </button>
            {logFeedback && <span style={{ marginLeft:10, fontFamily:"'JetBrains Mono',monospace", fontSize:11, color:"#4a9c6d" }}>{logFeedback}</span>}
          </div>
        </form>

        <div className="divider" style={{ marginTop:28 }} />

        {/* Re-activation Simulator */}
        <div>
          <div className="section-label">Re-activation Simulator</div>
          <p style={{ fontSize:11, color:"#5a5a5a", marginBottom:12, lineHeight:1.6 }}>
            Shift all FSRS <code style={{ fontFamily:"'JetBrains Mono',monospace", color:"#7c6fcd" }}>last_review</code> timestamps backward to simulate knowledge decay and trigger the welcome-back alert.
          </p>
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:10 }}>
            <span className="form-label" style={{ marginBottom:0, whiteSpace:"nowrap" }}>Simulate</span>
            <input type="range" min={3} max={60} value={simDays} onChange={e => setSimDays(+e.target.value)} style={{ flex:1, accentColor:"#8b3a3a" }} />
            <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:11, color:"#8b3a3a", minWidth:48 }}>{simDays} days</span>
          </div>
          <button onClick={simulate} disabled={simulating} className="btn btn-danger">
            {simulating ? "Applying…" : `Simulate ${simDays}-Day Absence`}
          </button>
        </div>
      </div>
    </div>
  );

  // ── Auth guard ─────────────────────────────────────────────────────
  if (authLoading || !user) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-faint)", fontSize: 13 }}>
        Loading…
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div style={S.shell}>
      {/* Sidebar */}
      {sidebar}

      {/* Main */}
      <div style={S.main}>
        {topbar}
        {decayBanner}
        <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden", minHeight:0 }}>
          {activeTab === "graph" && graphTab}
          {activeTab === "plan"  && planTab}
          {activeTab === "log"   && logTab}
        </div>
      </div>

      {/* Status bar */}
      <div style={S.statusbar}>
        <span style={{ display:"flex", alignItems:"center", gap:5 }}>
          <span style={{ width:6, height:6, borderRadius:"50%", background:hColor, display:"inline-block" }} />
          Health {health}%
        </span>
        <span>Decay &gt;15%: {decayed}</span>
        <span>Nodes: {stats?.nodes_count ?? 0}</span>
        <span style={{ marginLeft:"auto" }}>FSRS · SQLite · OpenRouter</span>
      </div>
    </div>
  );
}
