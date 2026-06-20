/**
 * Transforms the live API response (LiveReport) into the UI types used by
 * the dashboard components (GraphNode[], GraphEdge[], DriftPoint[], etc.).
 */

import type { LiveReport, LiveTopologyContributor, LiveNewGraphNode, BaselineStreamData } from "./api-client";
import type { GraphNode, GraphEdge, DriftPoint, AlertLevel, NodeType } from "./mock-data";

// ── Alert level ───────────────────────────────────────────────────────────────

export function alertLevelFor(score: number): AlertLevel {
  if (score >= 0.75) return "Critical";
  if (score >= 0.5) return "Medium";
  return "Low";
}

// ── Node type normalisation ───────────────────────────────────────────────────

function normalizeNodeType(raw: string): NodeType {
  switch (raw.toLowerCase()) {
    case "person":       return "person";
    case "company":      return "company";
    case "subsidiary":   return "subsidiary";
    case "jurisdiction": return "jurisdiction";
    default:
      return raw.toLowerCase().includes("person") ? "person" : "company";
  }
}

// ── Automatic graph layout ────────────────────────────────────────────────────

/**
 * Builds a ReactFlow-compatible node/edge graph from the topology section of a
 * live report.  Top contributors are placed in a top arc; dynamically
 * discovered nodes (from the Sentinel LLM) appear in a bottom row.
 */
export function buildGraphFromReport(report: LiveReport): {
  nodes: GraphNode[];
  edges: GraphEdge[];
} {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];

  const contributors = report.topology.top_contributors;

  // Collect unique dynamic nodes discovered during event processing
  const seenDynIds = new Set<string>();
  const dynNodes: LiveNewGraphNode[] = [];
  for (const ev of report.events) {
    if (!ev.triaged_in || !ev.new_graph_nodes) continue;
    for (const n of ev.new_graph_nodes) {
      if (!seenDynIds.has(n.node_id)) {
        seenDynIds.add(n.node_id);
        dynNodes.push(n);
      }
    }
  }

  // ── Layout constants ──────────────────────────────────────────────────────

  const totalTopNodes = Math.max(contributors.length, 1);
  const canvasWidth   = Math.max(640, totalTopNodes * 170 + 80);
  const centerX       = canvasWidth / 2;
  const companyY      = 220;
  const topRowY       = 50;
  const dynRowY       = 400;

  const hSpacing      = Math.min(220, (canvasWidth - 100) / totalTopNodes);

  // ── Central company node ──────────────────────────────────────────────────

  const companyNodeId = "node_company";
  nodes.push({
    id: companyNodeId,
    label: report.client.legal_name,
    type: "company",
    intrinsicRisk: report.decision.max_combined_risk,
    position: { x: Math.round(centerX - 55), y: companyY },
  });

  // ── Contributor nodes (top arc) ───────────────────────────────────────────

  const topStart =
    contributors.length === 1
      ? centerX - 55
      : centerX - (hSpacing * (contributors.length - 1)) / 2 - 55;

  contributors.forEach((c, i) => {
    const nodeId = `node_c${i}`;
    nodes.push({
      id: nodeId,
      label: c.name,
      type: normalizeNodeType(c.type),
      intrinsicRisk: c.intrinsic_risk,
      position: {
        x: Math.round(topStart + i * hSpacing),
        y: topRowY,
      },
    });
    edges.push({
      id: `edge_c${i}`,
      source: nodeId,
      target: companyNodeId,
      label: c.relation.replace(/_/g, " "),
    });
  });

  // ── Dynamic nodes (bottom row, from Sentinel LLM) ────────────────────────
  // Skip any dynamic node whose name already appears as a contributor to
  // avoid the same entity appearing twice in the graph.

  const contributorLabels = new Set(
    contributors.map((c) => c.name.toLowerCase())
  );
  const uniqueDynNodes = dynNodes.filter(
    (n) => !contributorLabels.has(n.name.toLowerCase())
  );

  const dynStart =
    uniqueDynNodes.length === 1
      ? centerX - 55
      : centerX - (hSpacing * (uniqueDynNodes.length - 1)) / 2 - 55;

  uniqueDynNodes.forEach((n, i) => {
    const nodeId = `node_d${i}`;
    nodes.push({
      id: nodeId,
      label: n.name,
      type: normalizeNodeType(n.type),
      intrinsicRisk: n.intrinsic_risk,
      position: {
        x: Math.round(dynStart + i * hSpacing),
        y: dynRowY,
      },
    });
    edges.push({
      id: `edge_d${i}`,
      source: nodeId,
      target: companyNodeId,
      label: n.relation.replace(/_/g, " "),
    });
  });

  return { nodes, edges };
}

// ── Business Model Drift series ───────────────────────────────────────────────

/**
 * Generates a 30-day simulated drift time series that ends at the actual
 * semantic statistic reported by the pKYC engine.  The series is deterministic
 * within a session (seed = company legal name hash).
 */
export function buildDriftSeries(report: LiveReport, days = 30): DriftPoint[] {
  const finalScore = report.streams.semantic.last_statistic;
  const threshold  = report.streams.semantic.threshold;
  const points: DriftPoint[] = [];
  const now = new Date();

  // Simple seeded pseudo-random (deterministic per run)
  let seed = report.client.legal_name
    .split("")
    .reduce((acc, c) => acc + c.charCodeAt(0), 0);
  function rand(): number {
    seed = (seed * 1664525 + 1013904223) & 0xffffffff;
    return ((seed >>> 0) / 0xffffffff);
  }

  for (let i = days; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const progress = (days - i) / days;
    // Sigmoid-ish growth curve towards the actual final score
    const trend  = finalScore * (1 / (1 + Math.exp(-10 * (progress - 0.6))));
    const noise  = (rand() - 0.5) * 0.035;
    const score  = Math.min(1, Math.max(0, trend + noise));
    points.push({
      date: d.toISOString().slice(0, 10),
      driftScore: parseFloat(score.toFixed(3)),
      threshold,
    });
  }
  return points;
}

// ── Streaming graph helpers ───────────────────────────────────────────────────

/**
 * Build an initial ReactFlow graph from a `baseline` SSE event.
 * The company node starts with 0 risk; contributor nodes use their known scores.
 * No dynamic (Sentinel-discovered) nodes yet.
 */
export function buildBaselineGraph(baseline: BaselineStreamData): {
  nodes: GraphNode[];
  edges: GraphEdge[];
} {
  const partial = {
    client:   baseline.client,
    topology: baseline.topology,
    decision: { max_combined_risk: 0, alarm_fired: false, threshold: 0, triggering_event: null },
    events:   [],
  } as unknown as LiveReport;
  return buildGraphFromReport(partial);
}

/**
 * Incrementally add newly discovered nodes from an `extraction` SSE event to
 * an existing graph.  Skips nodes whose label already exists; preserves all
 * existing node positions so the user's layout stays stable.
 */
export function addDynamicNodesToGraph(
  existingNodes: GraphNode[],
  existingEdges: GraphEdge[],
  newApiNodes:   LiveNewGraphNode[],
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const companyNode = existingNodes.find((n) => n.id === "node_company");
  const centerX     = (companyNode?.position.x ?? 320) + 55;
  const dynRowY     = 400;
  const hSpacing    = 200;

  const existingDynCount = existingNodes.filter((n) => n.id.startsWith("node_d")).length;
  const nodes = [...existingNodes];
  const edges = [...existingEdges];

  // Build a lowercase set of all labels already present for fast dedup.
  const existingLabels = new Set(nodes.map((e) => e.label.toLowerCase()));

  let added = 0;
  for (const n of newApiNodes) {
    if (existingLabels.has(n.name.toLowerCase())) continue;

    const totalDyn = existingDynCount + (newApiNodes.length - added);
    const startX   = centerX - (hSpacing * (totalDyn - 1)) / 2 - 55;
    const nodeId   = `node_d${existingDynCount + added}`;

    nodes.push({
      id:           nodeId,
      label:        n.name,
      type:         normalizeNodeType(n.type),
      intrinsicRisk: n.intrinsic_risk,
      position: {
        x: Math.round(startX + (existingDynCount + added) * hSpacing),
        y: dynRowY,
      },
    });
    edges.push({
      id:     `edge_d${existingDynCount + added}`,
      source: nodeId,
      target: "node_company",
      label:  n.relation.replace(/_/g, " "),
    });
    added++;
  }

  return { nodes, edges };
}

/**
 * Update node `intrinsicRisk` values based on the latest `risk_calculated` data.
 * The company node gets the current `r_combined` score to drive the gauge colour.
 * Contributor nodes are matched by name substring and get their contributor score.
 */
export function updateGraphNodeRisks(
  nodes:        GraphNode[],
  contributors: LiveTopologyContributor[],
  rCombined:    number,
): GraphNode[] {
  return nodes.map((node) => {
    if (node.id === "node_company") {
      return { ...node, intrinsicRisk: rCombined };
    }
    const match = contributors.find(
      (c) =>
        node.label.toLowerCase().includes(c.name.toLowerCase()) ||
        c.name.toLowerCase().includes(node.label.toLowerCase()),
    );
    return match ? { ...node, intrinsicRisk: match.intrinsic_risk } : node;
  });
}

// ── Trigger reason ────────────────────────────────────────────────────────────

export function triggerReasonFor(report: LiveReport): string {
  if (!report.decision.alarm_fired || !report.governance) {
    return "No active alert";
  }
  const map: Record<string, string> = {
    semantic:     "Business Model Drift",
    topology:     "Third-Party Exposure",
    behavioral_tx: "Transaction Anomalies",
  };
  return (
    report.governance.trigger_streams
      .map((s) => map[s] ?? s)
      .join(", ") || "Combined Risk Score"
  );
}
