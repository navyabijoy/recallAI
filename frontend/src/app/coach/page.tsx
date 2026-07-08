"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const USER_ID = "demo-user-id";

interface Message {
  role: "user" | "assistant";
  content: string;
  trace?: Array<{ step: number; tool: string; arguments: any; result: any }>;
}

const SUGGESTIONS = [
  "What are my top 3 decayed topics?",
  "Why is Dynamic Programming scheduled?",
  "What are prerequisites for Union Find?",
  "Summarize my knowledge health",
];

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
    gridRow: "1", gridColumn: "1",
    background: "#111111",
    borderRight: "1px solid rgba(255,255,255,0.06)",
    display: "flex", flexDirection: "column" as const,
    overflow: "hidden", color: "#909090", fontSize: 13,
  },
  main: {
    gridRow: "1", gridColumn: "2",
    display: "flex", flexDirection: "column" as const,
    overflow: "hidden", background: "#0d0d0d", minWidth: 0,
  },
  statusbar: {
    gridRow: "2", gridColumn: "1 / -1",
    background: "rgba(124,111,205,0.07)",
    borderTop: "1px solid rgba(124,111,205,0.18)",
    display: "flex", alignItems: "center",
    padding: "0 12px", gap: 16,
    fontFamily: "'JetBrains Mono', ui-monospace, monospace",
    fontSize: 10, color: "#5a5a5a",
  },
};

export default function CoachPage() {
  const [messages, setMessages] = useState<Message[]>([{
    role: "assistant",
    content: "RecallAI Coach — I have live access to your FSRS knowledge graph.\n\nAsk me about decay rates, topic dependencies, or why sessions are scheduled the way they are.",
  }]);
  const [input, setInput]           = useState("");
  const [sending, setSending]       = useState(false);
  const [activeTrace, setActiveTrace] = useState<Message["trace"] | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async (text: string) => {
    const msg = text.trim();
    if (!msg || sending) return;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: msg }]);
    setSending(true);
    try {
      const r = await fetch(`${API}/api/users/${USER_ID}/coach/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      if (r.ok) {
        const d = await r.json();
        setMessages(prev => [...prev, { role: "assistant", content: d.reply, trace: d.trace }]);
        if (d.trace?.length) setActiveTrace(d.trace);
      } else {
        setMessages(prev => [...prev, { role: "assistant", content: "Backend error — check FastAPI is running on port 8000." }]);
      }
    } catch {
      setMessages(prev => [...prev, { role: "assistant", content: `Could not reach ${API}` }]);
    } finally { setSending(false); }
  };

  return (
    <div style={S.shell}>

      {/* ── Sidebar ── */}
      <div style={S.sidebar}>
        {/* Logo */}
        <Link href="/landing" style={{ display:"flex", alignItems:"center", gap:8, padding:"13px 14px 11px", borderBottom:"1px solid rgba(255,255,255,0.05)", textDecoration:"none" }}>
          <div style={{ width:20, height:20, borderRadius:4, background:"rgba(124,111,205,0.12)", border:"1px solid rgba(124,111,205,0.28)", display:"grid", placeItems:"center", fontFamily:"'JetBrains Mono',monospace", fontSize:11, fontWeight:700, color:"#7c6fcd", flexShrink:0 }}>R</div>
          <span style={{ fontSize:13, fontWeight:600, color:"#c8c8c8" }}>RecallAI</span>
          <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:9, color:"#3d3d3d", marginLeft:"auto" }}>v1.0</span>
        </Link>

        {/* Nav */}
        <div style={{ padding:"10px 8px 4px" }}>
          <div style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:9, fontWeight:500, letterSpacing:"0.12em", textTransform:"uppercase", color:"#3d3d3d", padding:"0 8px 7px" }}>Views</div>
          <Link href="/" className="nav-item">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="3.5" cy="4" r="1.5"/><circle cx="12.5" cy="4" r="1.5"/><circle cx="8" cy="12" r="1.5"/><path d="M5 4h6M4.2 5.5 8 11M11.8 5.5 8 11"/></svg>
            Knowledge Map
          </Link>
          <Link href="/coach" className="nav-item active">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 3h12v8H9l-3 2V11H2V3z"/></svg>
            AI Coach
          </Link>
        </div>

        {/* Tool Trace in sidebar */}
        <div style={{ flex:1, overflow:"hidden", display:"flex", flexDirection:"column", borderTop:"1px solid rgba(255,255,255,0.04)", marginTop:6 }}>
          <div style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:9, fontWeight:500, letterSpacing:"0.12em", textTransform:"uppercase", color:"#3d3d3d", padding:"8px 14px 6px" }}>Tool Trace</div>
          <div style={{ flex:1, overflowY:"auto", padding:"0 8px 8px" }}>
            {activeTrace ? (
              activeTrace.map((t, i) => (
                <div key={i} style={{ padding:"6px 8px", borderBottom:"1px solid rgba(255,255,255,0.04)", fontFamily:"'JetBrains Mono',monospace", fontSize:10 }}>
                  <div><span style={{ color:"#7c6fcd" }}>{t.tool}</span><span style={{ color:"#5a5a5a" }}>({Object.keys(t.arguments ?? {}).join(", ")})</span></div>
                  <div style={{ color:"#909090", marginTop:2, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", fontSize:9 }}>
                    → {JSON.stringify(t.result)}
                  </div>
                </div>
              ))
            ) : (
              <div style={{ padding:"10px 8px", color:"#3d3d3d", fontFamily:"'JetBrains Mono',monospace", fontSize:10 }}>
                No trace yet
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Main ── */}
      <div style={S.main}>
        {/* Topbar */}
        <div style={{ height:38, borderBottom:"1px solid rgba(255,255,255,0.05)", display:"flex", alignItems:"center", padding:"0 14px", gap:8, background:"#111111", flexShrink:0 }}>
          <span style={{ fontSize:13, fontWeight:500, color:"#c8c8c8" }}>AI Learning Coach</span>
          <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:10, color:"#3d3d3d", marginLeft:4 }}>
            FSRS tool-calling agent · {activeTrace ? activeTrace.length + " calls" : "idle"}
          </span>
        </div>

        {/* Messages */}
        <div style={{ flex:1, overflowY:"auto", padding:16, display:"flex", flexDirection:"column", gap:10 }}>
          {messages.map((m, i) => (
            <div key={i} style={{ display:"flex", gap:8, flexDirection: m.role === "user" ? "row-reverse" : "row" }}>
              <div style={{
                width:22, height:22, borderRadius:3, flexShrink:0,
                background: m.role === "user" ? "rgba(124,111,205,0.10)" : "#1c1c1c",
                border: m.role === "user" ? "1px solid rgba(124,111,205,0.28)" : "1px solid rgba(255,255,255,0.09)",
                display:"grid", placeItems:"center",
                fontFamily:"'JetBrains Mono',monospace", fontSize:10,
                color: m.role === "user" ? "#7c6fcd" : "#5a5a5a",
              }}>
                {m.role === "user" ? "U" : "AI"}
              </div>
              <div>
                <div className={`chat-bubble${m.role === "user" ? " user" : ""}`}>{m.content}</div>
                {m.trace && m.trace.length > 0 && (
                  <button onClick={() => setActiveTrace(m.trace!)} style={{ marginTop:4, paddingLeft:4, display:"flex", alignItems:"center", gap:4, fontFamily:"'JetBrains Mono',monospace", fontSize:10, color:"#5a5a5a", cursor:"pointer", background:"none", border:"none" }}>
                    <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M5 6l2.5 2L5 10M9 10h2"/></svg>
                    {m.trace.length} tool calls — view trace
                  </button>
                )}
              </div>
            </div>
          ))}
          {sending && (
            <div style={{ display:"flex", gap:8 }}>
              <div style={{ width:22, height:22, borderRadius:3, background:"#1c1c1c", border:"1px solid rgba(255,255,255,0.09)", display:"grid", placeItems:"center", fontFamily:"'JetBrains Mono',monospace", fontSize:10, color:"#5a5a5a", flexShrink:0 }}>AI</div>
              <div style={{ padding:"7px 10px", borderRadius:4, border:"1px solid rgba(255,255,255,0.09)", background:"#161616", fontFamily:"'JetBrains Mono',monospace", fontSize:11, color:"#5a5a5a" }}>
                calling tools…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Suggestion chips */}
        <div style={{ padding:"0 14px 8px", display:"flex", flexWrap:"wrap", gap:5 }}>
          {SUGGESTIONS.map((s, i) => (
            <button key={i} onClick={() => send(s)} className="chip">{s}</button>
          ))}
        </div>

        {/* Input bar */}
        <form onSubmit={e => { e.preventDefault(); send(input); }} style={{ padding:"8px 14px 12px", display:"flex", gap:8, borderTop:"1px solid rgba(255,255,255,0.05)", background:"#111111", flexShrink:0 }}>
          <input
            className="form-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask about knowledge state, decay rates, topic dependencies…"
            disabled={sending}
            style={{ flex:1 }}
          />
          <button type="submit" disabled={sending || !input.trim()} className="btn btn-accent">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2L2 7.5l5 1.5 1.5 5L14 2z"/></svg>
            Send
          </button>
        </form>
      </div>

      {/* ── Status bar ── */}
      <div style={S.statusbar}>
        <span style={{ display:"flex", alignItems:"center", gap:5 }}>
          <span style={{ width:6, height:6, borderRadius:"50%", background:"#4a9c6d", display:"inline-block" }} />
          Coach online
        </span>
        <span style={{ marginLeft:"auto" }}>OpenRouter · FSRS tools</span>
      </div>
    </div>
  );
}
