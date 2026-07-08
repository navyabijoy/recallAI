"use client";

import React, { useRef, useEffect, useState } from "react";
import Link from "next/link";

// ─── Knowledge Graph Data ─────────────────────────────────────────────────────
const TOPICS = [
  { label: "Arrays",               health: 0.85, theta: 0.4,  phi: 1.1  },
  { label: "Sliding Window",       health: 0.72, theta: 1.4,  phi: 0.7  },
  { label: "Binary Search",        health: 0.65, theta: 2.2,  phi: 1.3  },
  { label: "Heap",                 health: 0.44, theta: 3.1,  phi: 0.9  },
  { label: "Trie",                 health: 0.28, theta: 4.0,  phi: 1.6  },
  { label: "Graphs",               health: 0.40, theta: 0.9,  phi: 1.8  },
  { label: "Union Find",           health: 0.55, theta: 5.1,  phi: 1.2  },
  { label: "Dynamic Programming",  health: 0.18, theta: 3.7,  phi: 0.5  },
];

const EDGES: [number, number][] = [
  [0, 1], [0, 2], [2, 3], [5, 6], [5, 7], [4, 7],
];

function healthColor(h: number): string {
  if (h > 0.65) return "#4a9c6d";
  if (h > 0.40) return "#b07d3a";
  return "#8b3a3a";
}
function healthColorRgb(h: number): string {
  if (h > 0.65) return "74,156,109";
  if (h > 0.40) return "176,125,58";
  return "139,58,58";
}

// ─── Animated Sphere Canvas ───────────────────────────────────────────────────
function KnowledgeSphere() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let rotation = 0;

    const dpr = window.devicePixelRatio || 1;

    function resize() {
      const w = canvas!.offsetWidth;
      const h = canvas!.offsetHeight;
      canvas!.width = w * dpr;
      canvas!.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener("resize", resize);

    const startTime = performance.now();

    interface Particle {
      edgeIdx: number;
      t: number;
      speed: number;
      color: string;
    }
    const particles: Particle[] = [];
    let lastSpawn = 0;

    function draw(now: number) {
      const elapsed = now - startTime;
      const buildProgress = Math.min(elapsed / 4000, 1);
      rotation += 0.0025;

      const W = canvas!.offsetWidth;
      const H = canvas!.offsetHeight;
      const CX = W / 2;
      const CY = H / 2 + H * 0.04;
      const R = Math.min(W, H) * 0.3;
      const FOV = 700;

      ctx.clearRect(0, 0, W, H);

      function spherePt(theta: number, phi: number, rot: number) {
        const x3 = R * Math.sin(phi) * Math.cos(theta + rot);
        const y3 = R * Math.cos(phi);
        const z3 = R * Math.sin(phi) * Math.sin(theta + rot);
        return { x3, y3, z3 };
      }

      function project(x3: number, y3: number, z3: number) {
        const scale = FOV / (FOV + z3 + R * 0.5);
        return { x: CX + x3 * scale, y: CY + y3 * scale, scale, depth: (z3 + R) / (2 * R) };
      }

      // Sphere dot grid
      const PHI_G = (1 + Math.sqrt(5)) / 2;
      const DOT_COUNT = 280;
      for (let i = 0; i < DOT_COUNT; i++) {
        const lat = Math.acos(1 - (2 * i) / DOT_COUNT);
        const lon = (2 * Math.PI * i) / PHI_G;
        const pt = spherePt(lon, lat, rotation * 0.6);
        const proj = project(pt.x3, pt.y3, pt.z3);
        const alpha = Math.max(0, proj.depth - 0.1) * 0.18 * buildProgress;
        ctx.beginPath();
        ctx.arc(proj.x, proj.y, proj.scale * 1.1, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(124,111,205,${alpha.toFixed(3)})`;
        ctx.fill();
      }

      // Project all topic nodes
      const projected = TOPICS.map((t, i) => {
        const reveal = Math.min(Math.max((buildProgress - i * 0.07) / 0.12, 0), 1);
        const pt = spherePt(t.theta, t.phi, rotation);
        const proj = project(pt.x3, pt.y3, pt.z3);
        return { ...proj, reveal, topic: t, idx: i };
      });

      // Edges
      for (const [ai, bi] of EDGES) {
        const a = projected[ai];
        const b = projected[bi];
        const rev = Math.min(a.reveal, b.reveal);
        if (rev <= 0) continue;
        const depthAvg = (a.depth + b.depth) / 2;
        const alpha = rev * depthAvg * 0.55;
        const mx = (a.x + b.x) / 2 + (b.y - a.y) * 0.12;
        const my = (a.y + b.y) / 2 - (b.x - a.x) * 0.12;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(mx, my, b.x, b.y);
        ctx.strokeStyle = `rgba(124,111,205,${alpha.toFixed(3)})`;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }

      // Particle signals
      if (buildProgress > 0.85 && now - lastSpawn > 500) {
        const ei = Math.floor(Math.random() * EDGES.length);
        const [ai, bi] = EDGES[ei];
        particles.push({
          edgeIdx: ei, t: 0,
          speed: 0.004 + Math.random() * 0.003,
          color: healthColorRgb(TOPICS[Math.random() > 0.5 ? ai : bi].health),
        });
        lastSpawn = now;
      }

      for (let i = particles.length - 1; i >= 0; i--) {
        particles[i].t += particles[i].speed;
        if (particles[i].t >= 1) { particles.splice(i, 1); continue; }
        const { edgeIdx, t, color } = particles[i];
        const [ai, bi] = EDGES[edgeIdx];
        const a = projected[ai];
        const b = projected[bi];
        const mx = (a.x + b.x) / 2 + (b.y - a.y) * 0.12;
        const my = (a.y + b.y) / 2 - (b.x - a.x) * 0.12;
        const px = (1 - t) * (1 - t) * a.x + 2 * (1 - t) * t * mx + t * t * b.x;
        const py = (1 - t) * (1 - t) * a.y + 2 * (1 - t) * t * my + t * t * b.y;
        const depth = a.depth + (b.depth - a.depth) * t;
        const grd = ctx.createRadialGradient(px, py, 0, px, py, 8);
        grd.addColorStop(0, `rgba(${color},${depth.toFixed(2)})`);
        grd.addColorStop(1, `rgba(${color},0)`);
        ctx.beginPath();
        ctx.arc(px, py, 8, 0, Math.PI * 2);
        ctx.fillStyle = grd;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(px, py, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${color},${Math.min(depth * 1.4, 1).toFixed(2)})`;
        ctx.fill();
      }

      // Nodes (sorted back-to-front)
      const sorted = [...projected].sort((a, b) => a.depth - b.depth);
      for (const node of sorted) {
        if (node.reveal <= 0) continue;
        const col = healthColor(node.topic.health);
        const rgb = healthColorRgb(node.topic.health);
        const baseSize = 5 + node.topic.health * 5;
        const size = baseSize * node.scale * node.reveal;
        const pulse = 1 + 0.18 * Math.sin(now * 0.0018 + node.idx * 1.3);
        const depthAlpha = Math.max(0, node.depth * 0.7 + 0.3) * node.reveal;

        const glowR = size * 3.2 * pulse;
        const grd = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, glowR);
        grd.addColorStop(0, `rgba(${rgb},${(depthAlpha * 0.35).toFixed(3)})`);
        grd.addColorStop(1, `rgba(${rgb},0)`);
        ctx.beginPath();
        ctx.arc(node.x, node.y, glowR, 0, Math.PI * 2);
        ctx.fillStyle = grd;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(node.x, node.y, size, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.globalAlpha = depthAlpha;
        ctx.fill();
        ctx.globalAlpha = 1;

        ctx.beginPath();
        ctx.arc(node.x, node.y, size * 1.7, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${rgb},${(depthAlpha * 0.4).toFixed(3)})`;
        ctx.lineWidth = 0.8;
        ctx.stroke();

        if (node.depth > 0.38 && node.reveal > 0.7) {
          const labelAlpha = Math.min(1, (node.depth - 0.38) * 2.5 * node.reveal);
          const fontSize = Math.max(9, Math.round(11 * node.scale));
          ctx.font = `500 ${fontSize}px 'Inter', sans-serif`;
          ctx.textAlign = "center";
          ctx.fillStyle = `rgba(228,228,228,${(labelAlpha * 0.9).toFixed(3)})`;
          ctx.fillText(node.topic.label, node.x, node.y - size - 8);
          ctx.font = `${Math.max(8, Math.round(9 * node.scale))}px 'JetBrains Mono', monospace`;
          ctx.fillStyle = `rgba(${rgb},${(labelAlpha * 0.85).toFixed(3)})`;
          ctx.fillText(`${Math.round(node.topic.health * 100)}%`, node.x, node.y - size - 20);
        }
      }

      raf = requestAnimationFrame(draw);
    }

    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />;
}

// ─── Hero dot-grid texture ────────────────────────────────────────────────────
function DotGrid() {
  return (
    <div
      style={{
        position: "absolute", inset: 0, overflow: "hidden",
        backgroundImage: "radial-gradient(circle, rgba(124,111,205,0.25) 1px, transparent 1px)",
        backgroundSize: "28px 28px",
        maskImage: "radial-gradient(ellipse 80% 80% at 50% 50%, black 30%, transparent 100%)",
        WebkitMaskImage: "radial-gradient(ellipse 80% 80% at 50% 50%, black 30%, transparent 100%)",
        opacity: 0.45,
      }}
    />
  );
}

// ─── Landing Page ─────────────────────────────────────────────────────────────
export default function LandingPage() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    // Add landing class to allow page scrolling
    document.documentElement.classList.add("landing");
    if (document.body) document.body.classList.add("landing");

    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => {
      document.documentElement.classList.remove("landing");
      if (document.body) document.body.classList.remove("landing");
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  return (
    <div
      style={{
        background: "#0d0d0d",
        minHeight: "100vh",
        fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
        color: "#c8c8c8",
        overflowX: "hidden",
        overflowY: "auto",
      }}
    >
      {/* ── Navbar ─────────────────────────────────────────────────────── */}
      <nav
        style={{
          position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
          height: 52,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 28px",
          background: scrolled ? "rgba(13,13,13,0.92)" : "transparent",
          backdropFilter: scrolled ? "blur(12px)" : "none",
          borderBottom: scrolled ? "1px solid rgba(124,111,205,0.12)" : "1px solid transparent",
          transition: "all 0.25s ease",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 26, height: 26, borderRadius: 6,
              background: "rgba(124,111,205,0.12)",
              border: "1.5px solid rgba(124,111,205,0.35)",
              display: "grid", placeItems: "center",
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 13, fontWeight: 700, color: "#7c6fcd",
            }}
          >
            R
          </div>
          <span style={{ fontSize: 15, fontWeight: 600, color: "#e4e4e4", letterSpacing: "-0.01em" }}>
            RecallAI
          </span>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 9,
              color: "#3d3d3d", background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.07)",
              padding: "1px 6px", borderRadius: 3, marginLeft: 2,
            }}
          >
            v1.0
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {[
            { label: "Knowledge Map", href: "/" },
            { label: "AI Coach", href: "/coach" },
          ].map((l) => (
            <Link
              key={l.href}
              href={l.href}
              style={{
                padding: "5px 12px", borderRadius: 5,
                color: "#909090", fontSize: 13, fontWeight: 500,
                textDecoration: "none",
                transition: "color 0.15s, background 0.15s",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.color = "#e4e4e4";
                (e.currentTarget as HTMLAnchorElement).style.background = "rgba(255,255,255,0.05)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.color = "#909090";
                (e.currentTarget as HTMLAnchorElement).style.background = "transparent";
              }}
            >
              {l.label}
            </Link>
          ))}
          <Link
            href="/"
            style={{
              marginLeft: 8, padding: "6px 14px", borderRadius: 6,
              background: "#7c6fcd", color: "#fff",
              fontSize: 13, fontWeight: 600, textDecoration: "none",
              transition: "background 0.15s, transform 0.1s",
              letterSpacing: "-0.01em",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.background = "#9080e0";
              (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(-1px)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.background = "#7c6fcd";
              (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(0)";
            }}
          >
            Open Dashboard →
          </Link>
        </div>
      </nav>

      {/* ── HERO SECTION ───────────────────────────────────────────────── */}
      <section
        style={{
          margin: "0 16px", marginTop: 64,
          borderRadius: 18, overflow: "hidden", position: "relative",
          minHeight: "88vh", display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          background: "#111111",
          border: "1px solid rgba(124,111,205,0.15)",
        }}
      >
        <DotGrid />

        {/* Purple glow at bottom */}
        <div
          style={{
            position: "absolute", bottom: "-10%", left: "50%",
            transform: "translateX(-50%)",
            width: "70%", height: "55%",
            background: "radial-gradient(ellipse at center bottom, rgba(124,111,205,0.28) 0%, rgba(124,111,205,0.08) 45%, transparent 70%)",
            pointerEvents: "none",
          }}
        />

        {/* Top shimmer */}
        <div
          style={{
            position: "absolute", top: 0, left: 0, right: 0, height: 1,
            background: "linear-gradient(90deg, transparent, rgba(124,111,205,0.5), transparent)",
          }}
        />

        {/* Hero content */}
        <div
          style={{
            position: "relative", zIndex: 2,
            display: "flex", flexDirection: "column",
            alignItems: "center", textAlign: "center",
            padding: "0 24px", maxWidth: 720,
          }}
        >
          {/* Badge */}
          <div
            style={{
              display: "inline-flex", alignItems: "center", gap: 7,
              padding: "5px 14px", borderRadius: 20,
              border: "1px solid rgba(124,111,205,0.35)",
              background: "rgba(124,111,205,0.08)",
              color: "#9080e0", fontSize: 12,
              fontFamily: "'JetBrains Mono', monospace",
              marginBottom: 28, letterSpacing: "0.02em",
            }}
          >
            <span
              style={{
                width: 6, height: 6, borderRadius: "50%",
                background: "#7c6fcd",
                boxShadow: "0 0 6px rgba(124,111,205,0.8)",
                display: "inline-block",
              }}
            />
            FSRS · Knowledge Graph · AI Agents · v1.0
          </div>

          {/* Headline */}
          <h1
            style={{
              fontSize: "clamp(36px, 5.5vw, 68px)", fontWeight: 700,
              color: "#f0f0f0", lineHeight: 1.08,
              letterSpacing: "-0.035em", marginBottom: 22,
            }}
          >
            Your knowledge,{" "}
            <span
              style={{
                background: "linear-gradient(135deg, #7c6fcd 0%, #9d8fe8 50%, #c4b8ff 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              never forgotten
            </span>
          </h1>

          <p
            style={{
              fontSize: 17, lineHeight: 1.65,
              color: "#7a7a8a", maxWidth: 540,
              marginBottom: 36, fontWeight: 400,
            }}
          >
            An agentic AI system that models your memory decay using FSRS, maps
            topic dependencies, and builds your optimal daily study schedule.
          </p>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "center" }}>
            <Link
              href="/"
              style={{
                padding: "11px 24px", borderRadius: 8,
                background: "#7c6fcd", color: "#fff",
                fontSize: 14, fontWeight: 600, textDecoration: "none",
                boxShadow: "0 0 24px rgba(124,111,205,0.3)",
                transition: "all 0.15s", letterSpacing: "-0.01em",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.background = "#9080e0";
                (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(-2px)";
                (e.currentTarget as HTMLAnchorElement).style.boxShadow = "0 8px 32px rgba(124,111,205,0.45)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.background = "#7c6fcd";
                (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(0)";
                (e.currentTarget as HTMLAnchorElement).style.boxShadow = "0 0 24px rgba(124,111,205,0.3)";
              }}
            >
              Open Dashboard →
            </Link>
            <Link
              href="/coach"
              style={{
                padding: "11px 24px", borderRadius: 8,
                border: "1px solid rgba(124,111,205,0.3)",
                background: "rgba(124,111,205,0.07)",
                color: "#9080e0", fontSize: 14, fontWeight: 600,
                textDecoration: "none", transition: "all 0.15s",
                letterSpacing: "-0.01em",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.background = "rgba(124,111,205,0.14)";
                (e.currentTarget as HTMLAnchorElement).style.borderColor = "rgba(124,111,205,0.5)";
                (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(-2px)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLAnchorElement).style.background = "rgba(124,111,205,0.07)";
                (e.currentTarget as HTMLAnchorElement).style.borderColor = "rgba(124,111,205,0.3)";
                (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(0)";
              }}
            >
              Chat with AI Coach
            </Link>
          </div>

          {/* Tech pills */}
          <div
            style={{
              marginTop: 36,
              display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center",
            }}
          >
            {["FastAPI", "Next.js", "FSRS Algorithm", "OpenRouter LLM", "SQLModel"].map((t) => (
              <span
                key={t}
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10, padding: "3px 9px",
                  border: "1px solid rgba(255,255,255,0.09)",
                  borderRadius: 4, color: "#5a5a5a",
                  background: "rgba(255,255,255,0.03)",
                }}
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── KNOWLEDGE SPHERE SECTION ────────────────────────────────────── */}
      <section style={{ padding: "80px 16px 0" }}>
        <div style={{ textAlign: "center", marginBottom: 8 }}>
          <p
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11, letterSpacing: "0.12em",
              textTransform: "uppercase", color: "#7c6fcd", marginBottom: 14,
            }}
          >
            Knowledge Architecture
          </p>
          <h2
            style={{
              fontSize: "clamp(28px, 4vw, 48px)", fontWeight: 700,
              color: "#e4e4e4", letterSpacing: "-0.03em",
              lineHeight: 1.1, marginBottom: 16,
            }}
          >
            Your Mind as a Living Graph
          </h2>
          <p style={{ color: "#5a5a7a", fontSize: 15, maxWidth: 520, margin: "0 auto" }}>
            Every topic is a node. Every dependency is an edge.
            Memory health is tracked in real-time — and FSRS decides what you need to review today.
          </p>
        </div>

        {/* Canvas container */}
        <div
          style={{
            position: "relative", height: "68vh",
            borderRadius: "18px 18px 0 0", overflow: "hidden",
            background: "#0d0d0d",
            border: "1px solid rgba(124,111,205,0.12)", borderBottom: "none",
          }}
        >
          <div
            style={{
              position: "absolute", top: 0, left: 0, right: 0, height: 80, zIndex: 2,
              background: "linear-gradient(to bottom, #0d0d0d, transparent)",
              pointerEvents: "none",
            }}
          />

          <KnowledgeSphere />

          {/* Canvas overlay label */}
          <div
            style={{
              position: "absolute", top: 24, left: 28, zIndex: 3,
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11, color: "#5a5a5a",
            }}
          >
            <span style={{ color: "#7c6fcd" }}>FSRS</span>
            {" "}· knowledge sphere · live decay simulation
          </div>

          {/* Legend */}
          <div
            style={{
              position: "absolute", top: 24, right: 28, zIndex: 3,
              display: "flex", flexDirection: "column", gap: 6,
            }}
          >
            {[
              { label: "Strong (>65%)",    color: "#4a9c6d" },
              { label: "Fading (40–65%)", color: "#b07d3a" },
              { label: "Decayed (<40%)",  color: "#8b3a3a" },
            ].map((l) => (
              <div
                key={l.label}
                style={{
                  display: "flex", alignItems: "center", gap: 7,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10, color: "#5a5a5a",
                }}
              >
                <span
                  style={{
                    width: 8, height: 8, borderRadius: "50%",
                    background: l.color,
                    boxShadow: `0 0 6px ${l.color}80`,
                    display: "inline-block",
                  }}
                />
                {l.label}
              </div>
            ))}
          </div>
        </div>

        {/* Feature cards */}
        <div
          style={{
            display: "grid", gridTemplateColumns: "repeat(3, 1fr)",
            border: "1px solid rgba(124,111,205,0.12)",
            borderTop: "1px solid rgba(124,111,205,0.18)",
            borderRadius: "0 0 18px 18px", overflow: "hidden",
          }}
        >
          {[
            {
              icon: (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7c6fcd" strokeWidth="1.5">
                  <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/>
                  <path d="M12 6v6l4 2"/>
                </svg>
              ),
              title: "Spaced Repetition via FSRS",
              body: "The Free Spaced Repetition Scheduler calculates memory stability, difficulty, and retrievability — scheduling reviews at exactly the right moment before forgetting.",
            },
            {
              icon: (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7c6fcd" strokeWidth="1.5">
                  <circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/>
                  <circle cx="12" cy="18" r="2"/>
                  <path d="M7 6h10M6 8l5 8M18 8l-5 8"/>
                </svg>
              ),
              title: "Dependency-Aware Scheduling",
              body: "Topics form a directed knowledge graph. Decayed prerequisites block advanced topics — so you never review Union Find before your Graphs foundation is solid.",
            },
            {
              icon: (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7c6fcd" strokeWidth="1.5">
                  <path d="M12 2l2 7h7l-5.5 4 2 7L12 16l-5.5 4 2-7L3 9h7z"/>
                </svg>
              ),
              title: "Dual AI Agent System",
              body: "The Planning Agent crafts your daily schedule within your time budget. The Coach Agent answers any question about your knowledge state — grounded in live FSRS metrics.",
            },
          ].map((card, i) => (
            <div
              key={i}
              style={{
                padding: "28px 28px 32px",
                borderRight: i < 2 ? "1px solid rgba(124,111,205,0.1)" : "none",
                background: "#0d0d0d",
                transition: "background 0.2s", cursor: "default",
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#111111"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#0d0d0d"; }}
            >
              <div
                style={{
                  width: 38, height: 38, borderRadius: 8,
                  background: "rgba(124,111,205,0.08)",
                  border: "1px solid rgba(124,111,205,0.2)",
                  display: "grid", placeItems: "center", marginBottom: 16,
                }}
              >
                {card.icon}
              </div>
              <h3
                style={{
                  fontSize: 14, fontWeight: 600,
                  color: "#e4e4e4", marginBottom: 10,
                  letterSpacing: "-0.01em",
                }}
              >
                {card.title}
              </h3>
              <p style={{ fontSize: 13, lineHeight: 1.65, color: "#5a5a7a" }}>{card.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── HOW IT WORKS (Agent Loop) ───────────────────────────────────── */}
      <section style={{ padding: "90px 16px 80px", maxWidth: 900, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 52 }}>
          <p
            style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
              letterSpacing: "0.12em", textTransform: "uppercase",
              color: "#7c6fcd", marginBottom: 14,
            }}
          >
            Agent Loop
          </p>
          <h2
            style={{
              fontSize: "clamp(24px, 3.5vw, 40px)", fontWeight: 700,
              color: "#e4e4e4", letterSpacing: "-0.03em",
            }}
          >
            How the Planning Agent thinks
          </h2>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {[
            {
              step: "01", tool: "get_forgetting_scores()",
              title: "Fetch decay scores",
              desc: "The agent queries all topic KnowledgeNodes and computes current retrievability via FSRS. Topics with highest forgetting risk surface first.",
            },
            {
              step: "02", tool: "get_topic_history()",
              title: "Analyze practice history",
              desc: "For high-risk topics, the agent inspects past sessions — success rates, average mistakes, grade distribution — to calibrate review intensity.",
            },
            {
              step: "03", tool: "get_related_concepts()",
              title: "Traverse the knowledge graph",
              desc: "Prerequisites and dependents are fetched from the graph. If a prerequisite is also decayed, it gets promoted in the schedule before advanced topics.",
            },
            {
              step: "04", tool: "check_plan_fits_budget()",
              title: "Validate time budget",
              desc: "The draft plan is checked against your daily study limit. If it overflows, the agent drops lower-priority topics and re-validates until it fits perfectly.",
            },
            {
              step: "05", tool: "log_recommendation()",
              title: "Persist and explain",
              desc: "The final plan and reasoning are saved to the database. Ask the Coach Agent at any time why a session was scheduled.",
            },
          ].map((s, i) => (
            <div
              key={i}
              style={{ display: "grid", gridTemplateColumns: "52px 1fr", gap: 0, position: "relative" }}
            >
              {i < 4 && (
                <div
                  style={{
                    position: "absolute", left: 25, top: 44,
                    width: 1, height: "calc(100% - 8px)",
                    background: "linear-gradient(to bottom, rgba(124,111,205,0.3), rgba(124,111,205,0.05))",
                  }}
                />
              )}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 4 }}>
                <div
                  style={{
                    width: 34, height: 34, borderRadius: "50%",
                    border: "1.5px solid rgba(124,111,205,0.4)",
                    background: "rgba(124,111,205,0.08)",
                    display: "grid", placeItems: "center",
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 11, fontWeight: 600, color: "#7c6fcd",
                  }}
                >
                  {s.step}
                </div>
              </div>
              <div style={{ paddingBottom: 36, paddingLeft: 16 }}>
                <div
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 11, color: "#7c6fcd", marginBottom: 6,
                  }}
                >
                  {s.tool}
                </div>
                <h4
                  style={{
                    fontSize: 15, fontWeight: 600,
                    color: "#e4e4e4", marginBottom: 8,
                    letterSpacing: "-0.01em",
                  }}
                >
                  {s.title}
                </h4>
                <p style={{ fontSize: 13, lineHeight: 1.7, color: "#5a5a7a" }}>{s.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── ROADMAP / UPCOMING FEATURES ───────────────────────────────── */}
      <section style={{ padding: "0 16px 80px", maxWidth: 900, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 44 }}>
          <p
            style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
              letterSpacing: "0.12em", textTransform: "uppercase",
              color: "#7c6fcd", marginBottom: 14,
            }}
          >
            v2.0 Roadmap
          </p>
          <h2
            style={{
              fontSize: "clamp(24px, 3.5vw, 40px)", fontWeight: 700,
              color: "#e4e4e4", letterSpacing: "-0.03em",
            }}
          >
            What's coming next
          </h2>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {[
            {
              version: "v2.1",
              title: "LeetCode & Codeforces Sync",
              desc: "Auto-sync solved problems. Submit a solution on LeetCode or Codeforces, and RecallAI instantly imports your submission speed, mistakes, and runtime percentile to update FSRS decay curves.",
            },
            {
              version: "v2.2",
              title: "Developer Activity Heatmaps",
              desc: "Visualize your learning stats with interactive calendars, study streaks, and GitHub-style heatmaps that map memory strength and stability index across each DSA topic.",
            },
            {
              version: "v2.3",
              title: "Adaptive DSA Mock Exams",
              desc: "Generate timed mock interviews using real past LeetCode and Codeforces problems matched specifically to your currently decayed knowledge nodes.",
            },
            {
              version: "v2.4",
              title: "Dynamic Revision Playlists",
              desc: "Generate smart problem sheets and review lists tailored to your target company (e.g., Google, Meta) and current prerequisite memory stability.",
            },
          ].map((item, i) => (
            <div
              key={i}
              style={{
                padding: "20px 24px",
                borderRadius: 12,
                background: "rgba(255,255,255,0.02)",
                border: "1px solid rgba(124,111,205,0.12)",
                position: "relative",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  position: "absolute", top: 12, right: 16,
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
                  color: "rgba(124,111,205,0.5)",
                }}
              >
                {item.version}
              </div>
              <h3 style={{ fontSize: 14, fontWeight: 600, color: "#e4e4e4", marginBottom: 8 }}>
                {item.title}
              </h3>
              <p style={{ fontSize: 12, lineHeight: 1.6, color: "#5a5a7a" }}>
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── FOOTER CTA ─────────────────────────────────────────────────── */}
      <div
        style={{
          margin: "0 16px 32px", borderRadius: 18,
          border: "1px solid rgba(124,111,205,0.2)",
          background: "linear-gradient(135deg, rgba(124,111,205,0.07) 0%, rgba(124,111,205,0.02) 100%)",
          padding: "52px 32px", textAlign: "center",
          position: "relative", overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute", top: "50%", left: "50%",
            transform: "translate(-50%, -50%)",
            width: 400, height: 400,
            background: "radial-gradient(circle, rgba(124,111,205,0.12) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />
        <div style={{ position: "relative", zIndex: 1 }}>
          <h2
            style={{
              fontSize: "clamp(24px, 3.5vw, 40px)", fontWeight: 700,
              color: "#e4e4e4", letterSpacing: "-0.03em", marginBottom: 16,
            }}
          >
            Stop forgetting what you learn
          </h2>
          <p style={{ color: "#5a5a7a", fontSize: 15, marginBottom: 28 }}>
            Open the dashboard and let the agent plan your first session.
          </p>
          <Link
            href="/"
            style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              padding: "12px 28px", borderRadius: 8,
              background: "#7c6fcd", color: "#fff",
              fontSize: 14, fontWeight: 600, textDecoration: "none",
              boxShadow: "0 0 32px rgba(124,111,205,0.35)",
              transition: "all 0.15s", letterSpacing: "-0.01em",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.background = "#9080e0";
              (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(-2px)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.background = "#7c6fcd";
              (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(0)";
            }}
          >
            Launch RecallAI Dashboard
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 8h10M9 4l4 4-4 4"/>
            </svg>
          </Link>
        </div>
      </div>

      {/* ── Status footer bar ───────────────────────────────────────────── */}
      <div
        style={{
          height: 36, display: "flex", alignItems: "center",
          justifyContent: "space-between", padding: "0 28px",
          borderTop: "1px solid rgba(124,111,205,0.1)",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 10, color: "#3d3d3d",
          background: "rgba(124,111,205,0.03)",
        }}
      >
        <span>RecallAI · v1.0 · FSRS + Agentic Planner</span>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              width: 6, height: 6, borderRadius: "50%",
              background: "#4a9c6d",
              boxShadow: "0 0 6px rgba(74,156,109,0.6)",
              display: "inline-block",
            }}
          />
          All systems online
        </span>
      </div>
    </div>
  );
}
