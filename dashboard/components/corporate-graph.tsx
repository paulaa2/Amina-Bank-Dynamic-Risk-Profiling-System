"use client";

import { useCallback, useEffect } from "react";
import ReactFlow, {
  Node,
  Edge,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  NodeProps,
  Handle,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import { cn } from "@/lib/utils";
import type { GraphNode, GraphEdge, NodeType } from "@/lib/mock-data";

// ── Node colour palette (dark) ────────────────────────────────────────────────

function riskColor(score: number): string {
  if (score >= 0.75) return "#fb7185"; // rose-400
  if (score >= 0.4)  return "#fbbf24"; // amber-400
  return "#34d399";                     // emerald-400
}

// ── Custom node component ─────────────────────────────────────────────────────

function RiskNode({ data }: NodeProps) {
  const borderColor = riskColor(data.intrinsicRisk);
  const isHighRisk  = data.intrinsicRisk >= 0.75;
  const isDiscovered = Boolean(data.discoveredDuringRun);
  const isNewDiscovery = Boolean(data.isNewDiscovery);

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div
        className={cn(
          "graph-node-enter",
          "rounded-lg border-2 px-3 py-2 text-center min-w-[110px] max-w-[140px]",
          "bg-slate-900",
          isHighRisk && "shadow-[0_0_15px_rgba(251,113,133,0.35)]",
          isDiscovered && !isHighRisk && "shadow-[0_0_12px_rgba(251,191,36,0.25)]"
        )}
        style={{
          borderColor: isDiscovered && !isHighRisk ? "#fbbf24" : borderColor,
          borderStyle: isNewDiscovery ? "dashed" : "solid",
          transition: "border-color 1s ease, box-shadow 1s ease",
        }}
      >
        {isDiscovered && (
          <p className="mb-0.5 text-[9px] font-semibold uppercase tracking-wide text-amber-400">
            {isNewDiscovery ? "New entity" : "New link"}
          </p>
        )}
        <p className="text-[11px] font-semibold text-slate-200 leading-tight break-words">
          {data.label}
        </p>
        <p
          className="mt-0.5 text-[10px] font-medium font-mono"
          style={{ color: isDiscovered && !isHighRisk ? "#fbbf24" : borderColor, transition: "color 1s ease" }}
        >
          {(data.intrinsicRisk * 100).toFixed(0)}%
        </p>
      </div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </>
  );
}

const nodeTypes = { riskNode: RiskNode };

// ── Conversion helpers ────────────────────────────────────────────────────────

function toFlowNodes(nodes: GraphNode[]): Node[] {
  return nodes.map((n) => ({
    id:       n.id,
    type:     "riskNode",
    position: n.position,
    data: {
      label:         n.label,
      intrinsicRisk: n.intrinsicRisk,
      nodeType:      n.type,
      discoveredDuringRun: n.discoveredDuringRun ?? false,
      isNewDiscovery:      n.isNewDiscovery ?? false,
    },
    draggable: true,
  }));
}

function toFlowEdges(
  edges: GraphEdge[],
  highRiskIds: Set<string>,
  discoveredIds: Set<string> = new Set(),
): Edge[] {
  return edges.map((e) => {
    const isHighRisk = highRiskIds.has(e.source);
    const isDiscovered = discoveredIds.has(e.source);
    const stroke = isHighRisk ? "#fb7185" : isDiscovered ? "#fbbf24" : "#475569";
    return {
      id:     e.id,
      source: e.source,
      target: e.target,
      label:  e.label,
      labelStyle:     { fontSize: 9, fill: "#ffffff" },
      labelBgPadding: [4, 2] as [number, number],
      labelBgStyle:   { fill: "#0f172a", stroke: "#334155", strokeWidth: 1 },
      animated:       isHighRisk || isDiscovered,
      markerEnd:      { type: MarkerType.ArrowClosed, color: stroke },
      style:          { stroke, strokeWidth: isHighRisk || isDiscovered ? 2 : 1.5 },
    };
  });
}

// ── Main component ────────────────────────────────────────────────────────────

interface CorporateGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  height?: number;
}

export function CorporateGraph({ nodes, edges, height = 480 }: CorporateGraphProps) {
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<Node[]>([]);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<Edge[]>([]);

  const onInit = useCallback(() => {}, []);

  useEffect(() => {
    const incoming = toFlowNodes(nodes);
    setFlowNodes((prev) => {
      const posMap = new Map(prev.map((n) => [n.id, n.position]));
      return incoming.map((n) => ({
        ...n,
        position: posMap.get(n.id) ?? n.position,
      }));
    });
  }, [nodes, setFlowNodes]);

  useEffect(() => {
    const highRiskIds = new Set(
      nodes.filter((n) => n.intrinsicRisk >= 0.75).map((n) => n.id)
    );
    const discoveredIds = new Set(
      nodes.filter((n) => n.discoveredDuringRun).map((n) => n.id)
    );
    setFlowEdges(
      toFlowEdges(edges, highRiskIds, discoveredIds)
    );
  }, [edges, nodes, setFlowEdges]);

  return (
    <div style={{ height: `${height}px` }} className="w-full rounded-lg border border-slate-800 overflow-hidden bg-slate-950">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onInit={onInit}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          color="#334155"
          gap={20}
          size={1}
          variant={BackgroundVariant.Dots}
        />
        <Controls
          showInteractive={false}
          style={{
            background: "#0f172a",
            border: "1px solid #334155",
            borderRadius: 8,
          }}
        />
        <MiniMap
          nodeColor={(n) => riskColor(n.data?.intrinsicRisk ?? 0)}
          style={{
            background: "#0f172a",
            border: "1px solid #334155",
            borderRadius: 8,
          }}
          maskColor="rgba(15,23,42,0.6)"
          zoomable
          pannable
        />
      </ReactFlow>
    </div>
  );
}
