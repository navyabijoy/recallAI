"use client";

import React, { useEffect } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  Position,
  MarkerType,
  Handle,
  Node,
  Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

// Obsidian-like fixed layout for our 8 DSA topics
const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  "Arrays":               { x: 80,  y: 200 },
  "Sliding Window":       { x: 300, y: 80  },
  "Binary Search":        { x: 300, y: 300 },
  "Heap":                 { x: 520, y: 300 },
  "Graphs":               { x: 80,  y: 420 },
  "Union Find":           { x: 300, y: 440 },
  "Trie":                 { x: 80,  y: 600 },
  "Dynamic Programming":  { x: 520, y: 530 },
};

interface KnowledgeNodeData {
  [key: string]: unknown;
  label: string;
  risk: number;        // 0–1
  stability: number;
  difficulty: number;
  practiceCount: number;
}

// Color purely determined by forgetting risk — de-saturated like Obsidian nodes
function riskColor(risk: number): { fill: string; stroke: string } {
  if (risk > 0.4)  return { fill: "rgba(139,58,58,0.18)",  stroke: "#6b2d2d" };
  if (risk > 0.15) return { fill: "rgba(176,125,58,0.15)", stroke: "#7a5a28" };
  return               { fill: "rgba(74,156,109,0.14)",  stroke: "#2d6648" };
}

// Minimal Obsidian-style node: small orb + label below
const ObsidianNode = ({ data }: { data: KnowledgeNodeData }) => {
  const { fill, stroke } = riskColor(data.risk);
  const riskPct = Math.round(data.risk * 100);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 5,
        userSelect: "none",
      }}
    >
      <Handle type="target" position={Position.Left}  style={{ opacity: 0 }} />

      {/* Node orb */}
      <div
        style={{
          width: 38,
          height: 38,
          borderRadius: "50%",
          background: fill,
          border: `1.5px solid ${stroke}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 10,
          fontWeight: 500,
          color: stroke,
          transition: "border-color 0.15s",
        }}
      >
        {riskPct}%
      </div>

      {/* Label */}
      <span
        style={{
          fontFamily: "'Inter', sans-serif",
          fontSize: 11,
          fontWeight: 500,
          color: "#999999",
          whiteSpace: "nowrap",
          textAlign: "center",
          maxWidth: 110,
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {data.label}
      </span>

      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
};

const nodeTypes = { obsidian: ObsidianNode };

interface GraphVizProps {
  nodesData: Array<{
    id: string;
    stability: number;
    difficulty: number;
    retrievability: number;
    forgetting_risk: number;
    last_review: string;
    practice_count: number;
  }>;
  edgesData: Array<{ id: string; source: string; target: string }>;
  onNodeClick?: (topicName: string) => void;
}

export default function GraphViz({ nodesData, edgesData, onNodeClick }: GraphVizProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    const flowNodes: Node[] = nodesData.map((n) => ({
      id: n.id,
      type: "obsidian",
      position: NODE_POSITIONS[n.id] ?? { x: 150, y: 150 },
      data: {
        label: n.id,
        risk: n.forgetting_risk,
        stability: n.stability,
        difficulty: n.difficulty,
        practiceCount: n.practice_count,
      } as KnowledgeNodeData,
    }));

    const flowEdges: Edge[] = edgesData.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      style: { stroke: "rgba(255,255,255,0.10)", strokeWidth: 1 },
      markerEnd: {
        type: MarkerType.Arrow,
        color: "rgba(255,255,255,0.15)",
        width: 12,
        height: 12,
      },
    }));

    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [nodesData, edgesData, setNodes, setEdges]);

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onNodeClick?.(node.id)}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        minZoom={0.4}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Controls showInteractive={false} />
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="rgba(255,255,255,0.04)" />
      </ReactFlow>
    </div>
  );
}
