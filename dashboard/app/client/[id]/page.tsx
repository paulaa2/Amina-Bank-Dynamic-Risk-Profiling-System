"use client";

import { use, useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Flag,
  Network,
  TrendingUp,
  ShieldAlert,
  CircleCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  User,
  Loader2,
  RefreshCw,
  Zap,
  Newspaper,
  ScanSearch,
  TriangleAlert,
  BadgeCheck,
  Building2 as BuildingIcon,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { AlertBadge } from "@/components/alert-badge";
import { GovernanceBadge } from "@/components/governance-badge";
import { DriftChart } from "@/components/drift-chart";
import { CorporateGraph } from "@/components/corporate-graph";
import { ComplianceReport } from "@/components/compliance-report";
import {
  analyzeCompanyStream,
  takeGovernanceAction,
  type LiveReport,
  type GovernanceAction,
  type BaselineStreamData,
  type RiskStreamData,
} from "@/lib/api-client";
import {
  alertLevelFor,
  buildBaselineGraph,
  buildGraphFromReport,
  buildDriftSeries,
  addDynamicNodesToGraph,
  updateGraphNodeRisks,
} from "@/lib/build-from-api";
import type { GraphNode, GraphEdge, AlertLevel } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Stream phase + terminal log types
// ─────────────────────────────────────────────────────────────────────────────

type StreamPhase = "connecting" | "streaming" | "complete" | "error";

// ── Activity feed types ───────────────────────────────────────────────────────

type FindingCategory = "entity" | "risk" | "score";
type StatusCategory  = "complete" | "error";

interface MetricPill {
  label: string;
  value: string;
  level: "low" | "moderate" | "high";
}

interface ArticleFinding {
  id: number;
  category: FindingCategory;
  title: string;
  detail?: string;
  metrics?: MetricPill[];
}

interface ArticleActivity {
  id: number;
  ts: string;
  articleTitle: string;
  source: string;
  adverseScore: number;
  findings: ArticleFinding[];
}

type FeedEntry =
  | { type: "article"; data: ArticleActivity }
  | { type: "status";  id: number; ts: string; category: StatusCategory; title: string; detail?: string };

let _feedCounter = 0;

function nowTs(): string {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

const FINDING_STYLES: Record<FindingCategory, { icon: React.ElementType; iconClass: string; titleClass: string }> = {
  entity: { icon: BuildingIcon,  iconClass: "text-violet-400", titleClass: "text-violet-300" },
  risk:   { icon: TriangleAlert, iconClass: "text-rose-400",   titleClass: "text-rose-300"   },
  score:  { icon: TrendingUp,    iconClass: "text-amber-400",  titleClass: "text-amber-300"  },
};

const STATUS_STYLES: Record<StatusCategory, { icon: React.ElementType; iconClass: string; titleClass: string }> = {
  complete: { icon: BadgeCheck, iconClass: "text-emerald-400", titleClass: "text-emerald-300" },
  error:    { icon: XCircle,    iconClass: "text-rose-500",    titleClass: "text-rose-400"    },
};

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function formatTs(iso: string) {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function StreamGauge({
  label, description, statistic, threshold, triggered,
}: {
  label: string; description: string;
  statistic: number; threshold: number; triggered: boolean;
}) {
  const pct = Math.min(100, (statistic / Math.max(threshold * 1.5, 0.01)) * 100);
  return (
    <div className={cn(
      "flex flex-col gap-3 rounded-xl border p-5",
      triggered ? "border-rose-500/20 bg-rose-500/5" : "border-slate-800 bg-slate-800/40"
    )}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-slate-200">{label}</p>
          <p className="mt-0.5 text-xs text-slate-500 leading-snug">{description}</p>
        </div>
        {triggered ? (
          <Badge variant="outline" className="shrink-0 border-rose-500/20 bg-rose-500/10 text-rose-400 text-xs font-semibold">⚠ Alarm</Badge>
        ) : (
          <Badge variant="outline" className="shrink-0 border-emerald-500/20 bg-emerald-500/10 text-emerald-400 text-xs">✓ Normal</Badge>
        )}
      </div>
      <p className={cn("text-3xl font-bold tabular-nums tracking-tight leading-none font-mono", triggered ? "text-rose-400" : "text-emerald-400")}>
        {statistic.toFixed(3)}
      </p>
      <Progress
        value={pct}
        className="[&_[data-slot=progress-track]]:h-2 [&_[data-slot=progress-track]]:bg-emerald-500 [&_[data-slot=progress-indicator]]:bg-rose-500 [&_[data-slot=progress-indicator]]:transition-all [&_[data-slot=progress-indicator]]:duration-700"
      />
      <p className="font-mono text-xs text-slate-600 tabular-nums">
        Score <span className="font-medium text-slate-400">{statistic.toFixed(3)}</span>
        {" · "}
        Threshold <span className="font-medium text-slate-400">{threshold.toFixed(3)}</span>
      </p>
    </div>
  );
}

function AuditTrailCollapsible({ governance }: { governance: NonNullable<LiveReport["governance"]> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 shadow-none overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-slate-800/50 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <Clock className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
          <span className="text-base font-semibold text-slate-200">Audit Trail</span>
          <GovernanceBadge status={governance.status} />
          <span className="text-xs text-slate-500">
            {governance.audit_trail.length} entr{governance.audit_trail.length === 1 ? "y" : "ies"}
          </span>
        </div>
        <svg className={cn("h-4 w-4 text-slate-500 transition-transform duration-200", open && "rotate-180")}
          viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="border-t border-slate-800 px-6 py-5 space-y-5">
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: "Alert ID",         value: governance.alert_id,                                                                 mono: true  },
              { label: "Assigned Analyst", value: governance.assigned_analyst           ?? "Pending",                                  mono: false },
              { label: "Approver",         value: governance.compliance_approver        ?? "Pending",                                  mono: false },
              { label: "Proposed Action",  value: governance.proposed_mitigation_action?.replace(/_/g, " ") ?? "Awaiting decision",    mono: false },
            ].map(({ label, value, mono }) => (
              <div key={label}>
                <p className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-1">{label}</p>
                <p className={cn("text-sm font-semibold text-slate-200", mono && "font-mono")}>{value}</p>
              </div>
            ))}
          </div>
          <Separator className="bg-slate-800" />
          <ol className="relative ml-3 border-l border-slate-800 space-y-5 pl-6">
            {governance.audit_trail.map((entry, i) => (
              <li key={i} className="relative">
                <span className="absolute -left-[25px] flex h-4 w-4 items-center justify-center rounded-full bg-slate-900 border-2 border-slate-700">
                  <User className="h-2.5 w-2.5 text-slate-500" />
                </span>
                <p className="font-mono text-xs text-slate-500 mb-1">{formatTs(entry.timestamp)} · {entry.user}</p>
                <p className="text-sm font-medium text-slate-200">{entry.action}</p>
                <GovernanceBadge status={entry.resulting_status} className="mt-1.5" />
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export default function ClientDossierPage({ params }: { params: Promise<{ id: string }> }) {
  const { id }      = use(params);
  const companyId   = parseInt(id, 10);

  // ── Stream state ────────────────────────────────────────────────────────────
  const [phase,             setPhase]             = useState<StreamPhase>("connecting");
  const [baseline,          setBaseline]          = useState<BaselineStreamData | null>(null);
  const [graph,             setGraph]             = useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>({ nodes: [], edges: [] });
  const [liveStreams,       setLiveStreams]        = useState<RiskStreamData | null>(null);
  const [lastEventTitle,    setLastEventTitle]     = useState<string | null>(null);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [report,            setReport]            = useState<LiveReport | null>(null);
  const [error,             setError]             = useState<string | null>(null);
  const [actionLoading,     setActionLoading]     = useState(false);
  const [feedEntries,       setFeedEntries]       = useState<FeedEntry[]>([]);

  // Holds the AbortController for the currently active stream so we can cancel
  // it if the user clicks Refresh before the stream completes.
  const controllerRef = useRef<AbortController | null>(null);
  const logRef        = useRef<HTMLDivElement>(null);

  // Auto-scroll feed on new entries
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [feedEntries]);

  // ── Kick off streaming analysis ─────────────────────────────────────────────

  function startStream(forceRefresh = false) {
    if (isNaN(companyId)) { setError("Invalid company ID"); return () => {}; }

    // Abort any in-flight stream before starting a new one
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setPhase("connecting");
    setBaseline(null);
    setGraph({ nodes: [], edges: [] });
    setLiveStreams(null);
    setLastEventTitle(null);
    setIsGeneratingReport(false);
    setReport(null);
    setError(null);
    setFeedEntries([]);

    // Helpers ─────────────────────────────────────────────────────────────────

    const pushArticle = (article: Omit<ArticleActivity, "id">) =>
      setFeedEntries((prev) => [
        ...prev,
        { type: "article", data: { id: _feedCounter++, ...article } },
      ]);

    // Append findings to the most-recent article entry
    const appendFindings = (findings: ArticleFinding[]) =>
      setFeedEntries((prev) => {
        const updated = [...prev];
        let lastIdx = -1;
        for (let i = updated.length - 1; i >= 0; i--) {
          if (updated[i].type === "article") { lastIdx = i; break; }
        }
        if (lastIdx < 0) return prev;
        const entry = updated[lastIdx] as { type: "article"; data: ArticleActivity };
        updated[lastIdx] = {
          type: "article",
          data: { ...entry.data, findings: [...entry.data.findings, ...findings] },
        };
        return updated;
      });

    const pushStatus = (category: StatusCategory, title: string, detail?: string) =>
      setFeedEntries((prev) => [
        ...prev,
        { type: "status", id: _feedCounter++, ts: nowTs(), category, title, detail },
      ]);

    // ─────────────────────────────────────────────────────────────────────────

    analyzeCompanyStream(
      companyId,
      (evt) => {
        if (evt.event === "baseline") {
          setBaseline(evt.data);
          const g = buildBaselineGraph(evt.data);
          setGraph(g);
          setPhase("streaming");
          return;
        }

        if (evt.event === "extraction") {
          setGraph((prev) =>
            addDynamicNodesToGraph(prev.nodes, prev.edges, evt.data.new_nodes)
          );
          setLastEventTitle(evt.data.event_title);
          pushArticle({
            ts: nowTs(),
            articleTitle: evt.data.event_title,
            source: evt.data.source,
            adverseScore: evt.data.adverse_score,
            findings: evt.data.new_nodes.map((n) => ({
              id: _feedCounter++,
              category: "entity" as FindingCategory,
              title: n.name,
              detail: n.relation
                ? `Identified as: ${n.relation.replace(/_/g, " ")}`
                : "New entity identified",
            })),
          });
          return;
        }

        if (evt.event === "risk_calculated") {
          setLiveStreams(evt.data);
          setLastEventTitle(evt.data.event_title);
          setGraph((prev) => ({
            nodes: updateGraphNodeRisks(prev.nodes, evt.data.contributors, evt.data.r_combined),
            edges: prev.edges,
          }));
          const rPct = Math.round(evt.data.r_combined * 100);
          const streamLabels: Record<string, string> = {
            semantic:      "Business Model Drift",
            topology:      "Third-Party Exposure",
            behavioral_tx: "Transaction Anomalies",
          };
          const firedAlarms = Object.entries(evt.data.alarms).filter(([, fired]) => fired);

          function signalLevel(v: number, t1: number, t2: number): "low" | "moderate" | "high" {
            return v >= t2 ? "high" : v >= t1 ? "moderate" : "low";
          }
          function fmtVal(v: number) { return v.toFixed(3); }

          const metrics: MetricPill[] = [
            {
              label: "Business Drift",
              value: fmtVal(evt.data.semantic),
              level: signalLevel(evt.data.semantic, 0.2, 0.35),
            },
            {
              label: "Network Exposure",
              value: fmtVal(evt.data.topology),
              level: signalLevel(evt.data.topology, 0.15, 0.4),
            },
            {
              label: "Transactions",
              value: fmtVal(evt.data.behavioral_tx),
              level: signalLevel(evt.data.behavioral_tx, 0.3, 0.6),
            },
          ];

          const newFindings: ArticleFinding[] = [
            ...firedAlarms.map(([key]) => ({
              id: _feedCounter++,
              category: "risk" as FindingCategory,
              title: streamLabels[key] ?? key,
              detail: "Alert threshold exceeded — flagged for review",
            })),
            {
              id: _feedCounter++,
              category: "score" as FindingCategory,
              title: firedAlarms.length > 0
                ? `Combined score: ${rPct}% — alarm triggered`
                : `Combined score: ${rPct}%`,
              detail: firedAlarms.length > 0 ? undefined : "Within normal parameters",
              metrics,
            },
          ];
          appendFindings(newFindings);
          return;
        }

        if (evt.event === "report_generating") {
          setIsGeneratingReport(true);
          return;
        }

        if (evt.event === "complete") {
          const finalGraph = buildGraphFromReport(evt.data);
          setGraph(finalGraph);
          setReport(evt.data);
          setIsGeneratingReport(false);
          setPhase("complete");
          const finalPct = Math.round(evt.data.decision.max_combined_risk * 100);
          pushStatus(
            "complete",
            evt.data.decision.alarm_fired
              ? "Alert triggered — compliance action required"
              : "No issues detected",
            `Final risk score: ${finalPct}%`,
          );
          return;
        }

        if (evt.event === "error") {
          setError(evt.data.message);
          setPhase("error");
          pushStatus("error", "Analysis could not be completed", evt.data.message);
        }
      },
      controller.signal,
      forceRefresh,
    ).catch((err: unknown) => {
      if (!controller.signal.aborted) {
        setError(String(err));
        setPhase("error");
      }
    });

    return () => controller.abort();
  }

  useEffect(() => {
    startStream();
    return () => controllerRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  // ── Connecting phase ─────────────────────────────────────────────────────────

  if (phase === "connecting") {
    return (
      <div className="flex flex-col min-h-screen">
        <div className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md px-8 py-3.5">
          <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm", className: "gap-1.5 text-slate-400 hover:text-slate-200 -ml-2" })}>
            <ArrowLeft className="h-3.5 w-3.5" /> Control Room
          </Link>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4">
            <Loader2 className="h-8 w-8 animate-spin text-slate-500 mx-auto" />
            <p className="text-sm font-medium text-slate-400">Connecting to pKYC engine…</p>
            <p className="font-mono text-xs text-slate-600">Preparing analysis for entity #{id.padStart(3, "0")}</p>
          </div>
        </div>
      </div>
    );
  }

  // ── Error phase ──────────────────────────────────────────────────────────────

  if (phase === "error") {
    return (
      <div className="flex flex-col min-h-screen">
        <div className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md px-8 py-3.5">
          <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm", className: "gap-1.5 text-slate-400 hover:text-slate-200 -ml-2" })}>
            <ArrowLeft className="h-3.5 w-3.5" /> Control Room
          </Link>
        </div>
        <div className="flex-1 flex items-center justify-center px-8 py-16">
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-8 max-w-md text-center">
            <AlertTriangle className="h-10 w-10 text-rose-400 mx-auto mb-4 opacity-70" />
            <p className="text-base font-semibold text-rose-300 mb-2">Analysis Failed</p>
            <p className="text-sm text-rose-400/80 mb-6">{error}</p>
            <div className="flex items-center justify-center gap-3">
              <Button size="sm" variant="outline" className="gap-1.5 border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700" onClick={() => startStream(true)}>
                <RefreshCw className="h-3.5 w-3.5" /> Retry
              </Button>
              <p className="text-xs text-rose-400/60">
                Is <code className="font-mono bg-rose-500/10 border border-rose-500/20 px-1 py-0.5 rounded">uvicorn src.api:app</code> running?
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Streaming + complete phases ──────────────────────────────────────────────

  const isComplete    = phase === "complete";
  const isStreaming   = phase === "streaming";

  // Derive display values from whichever data source is available
  const clientInfo    = report?.client    ?? baseline?.client;
  const securityInfo  = report?.security  ?? baseline?.security;
  const topologyInfo  = report?.topology  ?? baseline?.topology;
  const governance    = report?.governance ?? null;

  const rCombined   = isComplete
    ? report!.decision.max_combined_risk
    : (liveStreams?.r_combined ?? 0);
  const riskPct     = Math.round(rCombined * 100);
  const level       = alertLevelFor(rCombined);
  const gaugeColor  = riskPct >= 75 ? "#fb7185" : riskPct >= 50 ? "#fbbf24" : "#34d399";
  const alarmFired  = isComplete ? report!.decision.alarm_fired : (liveStreams ? Object.values(liveStreams.alarms).some(Boolean) : false);

  // Streams display (use real thresholds after complete, approximate during streaming)
  const streams = isComplete
    ? report!.streams
    : {
        bonferroni_scale: 1,
        semantic:      { last_statistic: liveStreams?.semantic      ?? 0, threshold: Math.max((liveStreams?.semantic      ?? 0) * 1.5, 0.5) },
        topology:      { last_statistic: liveStreams?.topology      ?? 0, threshold: Math.max((liveStreams?.topology      ?? 0) * 1.5, 0.5), observed_exposure: liveStreams?.topology ?? 0 },
        behavioral_tx: { last_statistic: liveStreams?.behavioral_tx ?? 0, threshold: Math.max((liveStreams?.behavioral_tx ?? 0) * 1.5, 0.5) },
      };

  const contributors = isComplete
    ? report!.topology.top_contributors
    : (liveStreams?.contributors ?? topologyInfo?.top_contributors ?? []);

  const driftData = isComplete ? buildDriftSeries(report!) : null;

  // ── Governance actions ───────────────────────────────────────────────────────

  async function handleAction(action: GovernanceAction) {
    setActionLoading(true);
    try {
      const updated = await takeGovernanceAction(companyId, action);
      setReport(updated);
    } catch (err) {
      console.error("Governance action failed:", err);
    } finally {
      setActionLoading(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col min-h-screen">

      {/* ── Sticky header ─────────────────────────────────────────────────── */}
      <div className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
        <div className="flex items-center justify-between px-8 py-3.5">
          <div className="flex items-center gap-3">
            <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm", className: "gap-1.5 text-slate-400 hover:text-slate-200 -ml-2 shrink-0" })}>
              <ArrowLeft className="h-3.5 w-3.5" /> Control Room
            </Link>
            <Separator orientation="vertical" className="h-5 bg-slate-800" />
            <h1 className="text-base font-semibold text-slate-200">
              {clientInfo?.legal_name ?? `Entity #${id.padStart(3, "0")}`}
            </h1>
            <span className="font-mono text-sm text-slate-500">#{id.padStart(3, "0")}</span>
            {isStreaming && (
              <span className="flex items-center gap-1.5 text-xs font-medium text-amber-400">
                <Zap className="h-3.5 w-3.5 animate-pulse" />
                Live analysis
              </span>
            )}
            {isComplete && alarmFired && <AlertBadge level={level} />}
            {isComplete && governance && <GovernanceBadge status={governance.status} />}
          </div>
          <div className="flex items-center gap-3">
            {clientInfo && (
              <div className="flex items-center gap-1.5 text-sm text-slate-500">
                <Flag className="h-3.5 w-3.5" />
                {clientInfo.jurisdiction} · {clientInfo.country}
              </div>
            )}
            {isComplete && (
              <button
                onClick={() => startStream(true)}
                title="Re-run analysis"
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-200 transition-colors"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Refresh
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Body ──────────────────────────────────────────────────────────── */}
      <div className="flex-1 px-8 py-7 space-y-6">

        {/* ── Graph + Live Terminal ──────────────────────────────────────── */}
        <div className="grid grid-cols-3 gap-5 items-stretch">

          {/* Corporate graph — col-span-2 */}
          <Card className="col-span-2 border-slate-800 bg-slate-900 shadow-none">
            <CardHeader className="border-b border-slate-800 px-6 py-4">
              <CardTitle className="flex items-center gap-2.5 text-base font-semibold text-slate-200">
                <Network className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
                Corporate Relationship Map
                {isStreaming && graph.nodes.length > 0 && (
                  <span className="text-xs font-normal text-amber-400 ml-1 animate-pulse">
                    {graph.nodes.length} nodes · building…
                  </span>
                )}
                {isComplete && (report?.topology?.circular_ownership_detected) && (
                  <Badge variant="outline" className="ml-1 border-rose-500/20 bg-rose-500/10 text-rose-400 text-xs">
                    Circular Ownership Detected
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3">
              {graph.nodes.length > 0 ? (
                <CorporateGraph nodes={graph.nodes} edges={graph.edges} height={540} />
              ) : (
                <div className="flex items-center justify-center" style={{ height: 540 }}>
                  <div className="text-center space-y-2">
                    <Loader2 className="h-6 w-6 animate-spin text-slate-600 mx-auto" />
                    <p className="text-xs text-slate-500">Loading graph…</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Activity feed — col-span-1 */}
          <div className="col-span-1 flex flex-col rounded-xl border border-slate-800 bg-slate-900 overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800 shrink-0">
              <div className="flex items-center gap-2">
                <ScanSearch className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
                <span className="text-sm font-semibold text-slate-200">Analysis Activity</span>
              </div>
              {isStreaming ? (
                <span className="flex items-center gap-1.5 text-xs text-amber-400 font-medium">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
                  Scanning…
                </span>
              ) : isComplete ? (
                <span className="text-xs text-emerald-400 font-medium">Complete</span>
              ) : null}
            </div>

            {/* Feed entries */}
            <div ref={logRef} className="flex-1 overflow-y-auto">
              {feedEntries.length === 0 && (
                <div className="flex flex-col items-center justify-center gap-2 py-16 text-slate-600">
                  <ScanSearch className="h-7 w-7 opacity-30" />
                  <p className="text-xs">Waiting for analysis to start…</p>
                </div>
              )}

              {feedEntries.map((entry) => {
                // ── Status row (complete / error) ────────────────────────────
                if (entry.type === "status") {
                  const s = STATUS_STYLES[entry.category];
                  const Icon = s.icon;
                  return (
                    <div key={entry.id} className="flex items-start gap-3 px-5 py-3 border-t border-slate-800/60 bg-slate-800/20">
                      <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", s.iconClass)} strokeWidth={1.75} />
                      <div className="flex-1 min-w-0">
                        <p className={cn("text-sm font-semibold leading-snug", s.titleClass)}>{entry.title}</p>
                        {entry.detail && <p className="mt-0.5 text-xs text-slate-500">{entry.detail}</p>}
                      </div>
                      <span className="font-mono text-[10px] text-slate-600 shrink-0 mt-0.5">{entry.ts}</span>
                    </div>
                  );
                }

                // ── Article group ────────────────────────────────────────────
                const { data } = entry;
                const adverseColor = data.adverseScore >= 0.6
                  ? "text-rose-400"
                  : data.adverseScore >= 0.3
                    ? "text-amber-400"
                    : "text-slate-500";
                const adverseLbl = data.adverseScore >= 0.6
                  ? "High-risk"
                  : data.adverseScore >= 0.3
                    ? "Moderate"
                    : "Low-risk";

                return (
                  <div key={data.id} className="border-t border-slate-800/60 px-5 pt-3.5 pb-2">
                    {/* Article header */}
                    <div className="flex items-start gap-3">
                      <Newspaper className="h-4 w-4 mt-0.5 text-sky-400 shrink-0" strokeWidth={1.75} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-sky-300 leading-snug">{data.articleTitle}</p>
                        <p className="mt-0.5 text-xs text-slate-500">
                          {data.source}
                          {" · "}
                          <span className={adverseColor}>{adverseLbl}</span>
                        </p>
                      </div>
                      <span className="font-mono text-[10px] text-slate-600 shrink-0 mt-0.5">{data.ts}</span>
                    </div>

                    {/* Findings threaded below, connected by a left border */}
                    {data.findings.length > 0 && (
                      <div className="ml-[1.35rem] mt-2 mb-0.5 pl-4 border-l-2 border-slate-700/70 space-y-2">
                        {data.findings.map((f) => {
                          const fs = FINDING_STYLES[f.category];
                          const FIcon = fs.icon;
                          return (
                            <div key={f.id} className="flex items-start gap-2">
                              <FIcon className={cn("h-3.5 w-3.5 mt-0.5 shrink-0", fs.iconClass)} strokeWidth={1.75} />
                              <div className="min-w-0 flex-1">
                                <p className={cn("text-xs font-medium leading-snug", fs.titleClass)}>{f.title}</p>
                                {f.detail && <p className="text-[11px] text-slate-600 leading-snug">{f.detail}</p>}
                                {f.metrics && (
                                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                                    {f.metrics.map((m) => (
                                      <span
                                        key={m.label}
                                        className={cn(
                                          "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-mono font-medium border",
                                          m.level === "high"
                                            ? "bg-rose-500/10 text-rose-300 border-rose-500/20"
                                            : m.level === "moderate"
                                              ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
                                              : "bg-slate-800 text-slate-500 border-slate-700",
                                        )}
                                      >
                                        <span className="text-slate-500 font-sans not-italic">{m.label}</span>
                                        <span>{m.value}</span>
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}

              {isStreaming && (
                <div className="flex items-center gap-3 px-5 py-3 border-t border-slate-800/60">
                  <Loader2 className="h-4 w-4 text-slate-600 animate-spin shrink-0" />
                  <p className="text-xs text-slate-600 italic">Processing next article…</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Warnings */}
        {isComplete && report!.warnings.length > 0 && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-5 py-4 flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
            <div className="space-y-1">
              {report!.warnings.map((w, i) => (
                <p key={i} className="text-sm font-medium text-amber-300">{w}</p>
              ))}
            </div>
          </div>
        )}

        {/* ── ROW 1: Triggering Event card + Gauge ──────────────────────── */}
        <div className="grid grid-cols-3 gap-5">

          {/* Triggering Event / Analysis Status */}
          <Card className="col-span-2 shadow-none border-slate-800 bg-slate-900">
            <CardContent className="p-6 flex flex-col gap-5 h-full justify-between">
              <div className="flex items-start justify-between gap-4">
                <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">
                  {isStreaming ? "Live Analysis" : alarmFired ? "Triggering Event" : "Current Status"}
                </p>
                {isComplete && alarmFired && governance && (
                  <div className="flex flex-wrap gap-1.5">
                    {governance.trigger_streams.map((s) => {
                      const labels: Record<string, string> = {
                        semantic: "Business Model Drift",
                        topology: "Third-Party Exposure",
                        behavioral_tx: "Transaction Anomalies",
                      };
                      return (
                        <Badge key={s} variant="outline" className="border-rose-500/20 bg-rose-500/10 text-rose-400 text-xs">
                          {labels[s] ?? s}
                        </Badge>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Content varies by phase */}
              {isStreaming && (
                <div className="flex items-start gap-3">
                  <Loader2 className="mt-1 h-5 w-5 shrink-0 text-amber-400 animate-spin" />
                  <div>
                    <p className="text-base font-semibold text-slate-200">
                      {isGeneratingReport ? "Generating AML forensic report…" : "Processing news events…"}
                    </p>
                    {lastEventTitle && (
                      <p className="mt-1 text-sm text-slate-400 leading-relaxed line-clamp-2">
                        {lastEventTitle}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {isComplete && alarmFired && (
                <div className="flex items-start gap-3">
                  <AlertTriangle className="mt-1 h-5 w-5 shrink-0 text-amber-400" />
                  <p className="text-lg font-medium text-amber-200 leading-relaxed">
                    {report!.decision.triggering_event}
                  </p>
                </div>
              )}

              {isComplete && !alarmFired && (
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="h-6 w-6 shrink-0 text-emerald-400" />
                  <p className="text-base font-medium text-emerald-300">
                    No active alerts — entity within normal risk parameters
                  </p>
                </div>
              )}

              <div className="flex items-center gap-3 pt-1 border-t border-slate-800">
                <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Combined Risk</span>
                <span
                  className="text-2xl font-bold tabular-nums font-mono transition-all duration-700"
                  style={{ color: gaugeColor }}
                >
                  {riskPct}%
                </span>
                <Separator orientation="vertical" className="h-5 mx-1 bg-slate-800" />
                <AlertBadge level={level} />
              </div>
            </CardContent>
          </Card>

          {/* Gauge */}
          <Card className="border-slate-800 bg-slate-900 shadow-none">
            <CardContent className="p-6 flex flex-col items-center justify-center gap-4 h-full">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Unified Alert Level</p>
              <div className="relative flex h-32 w-32 items-center justify-center">
                <svg viewBox="0 0 100 60" className="absolute inset-0 h-full w-full">
                  <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke="#1e293b" strokeWidth="9" strokeLinecap="round" />
                  <path
                    d="M 10 55 A 40 40 0 0 1 90 55"
                    fill="none"
                    stroke={gaugeColor}
                    strokeWidth="9"
                    strokeLinecap="round"
                    strokeDasharray={`${(riskPct / 100) * 125.66} 125.66`}
                    style={{ transition: "stroke-dasharray 0.7s ease, stroke 0.5s ease" }}
                  />
                </svg>
                <div className="mt-5 text-center">
                  <p
                    className="text-3xl font-bold tabular-nums font-mono leading-none transition-colors duration-500"
                    style={{ color: gaugeColor }}
                  >
                    {riskPct}%
                  </p>
                </div>
              </div>
              <AlertBadge level={level} className="text-sm px-3 py-1" />
              {isStreaming ? (
                <p className="text-center text-xs text-amber-400 font-medium animate-pulse">Updating live…</p>
              ) : (
                <p className={cn("text-center text-xs leading-snug px-2", alarmFired ? "text-rose-400 font-semibold" : "text-slate-500")}>
                  {alarmFired ? "Threshold exceeded — alarm active" : "Within normal parameters"}
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── ROW 2: Entity Profile ──────────────────────────────────────── */}
        {clientInfo && securityInfo && (
          <Card className="border-slate-800 bg-slate-900 shadow-none">
            <CardContent className="p-6">
              <div className="flex items-start justify-between gap-6">
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Entity Profile</p>
                  <h2 className="mt-1.5 text-xl font-semibold text-slate-200 leading-snug">{clientInfo.legal_name}</h2>
                  <p className="mt-1 text-sm text-slate-400 leading-relaxed max-w-xl">{clientInfo.expected_business_model}</p>
                </div>
                <div className="flex items-center gap-8 shrink-0 flex-wrap justify-end">
                  {[
                    { label: "Country",        value: clientInfo.country },
                    { label: "Jurisdiction",   value: clientInfo.jurisdiction },
                    { label: "Graph Nodes",    value: clientInfo.known_graph_nodes },
                    { label: "Masked Entities", value: securityInfo.masked_entities },
                  ].map(({ label, value }) => (
                    <div key={label} className="text-center">
                      <p className="text-xs text-slate-500 uppercase tracking-wider">{label}</p>
                      <p className="mt-0.5 text-base font-semibold text-slate-200">{value}</p>
                    </div>
                  ))}
                  <Separator orientation="vertical" className="h-10 mx-1 bg-slate-800" />
                  <div>
                    <p className="text-xs text-slate-500 uppercase tracking-wider mb-0.5">Baseline Risk</p>
                    <Badge variant="outline" className={cn("text-sm font-semibold px-3 py-1",
                      clientInfo.baseline_risk_rating === "CRITICAL" && "border-rose-500/20 bg-rose-500/10 text-rose-400",
                      clientInfo.baseline_risk_rating === "HIGH"     && "border-amber-500/20 bg-amber-500/10 text-amber-400",
                      clientInfo.baseline_risk_rating === "MEDIUM"   && "border-yellow-500/20 bg-yellow-500/10 text-yellow-400",
                      clientInfo.baseline_risk_rating === "LOW"      && "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
                    )}>
                      {clientInfo.baseline_risk_rating}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 uppercase tracking-wider mb-0.5">GDPR Token</p>
                    <p className="font-mono text-sm font-medium text-slate-400">{securityInfo.company_token}</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── Detection Streams ──────────────────────────────────────────── */}
        <Card className="border-slate-800 bg-slate-900 shadow-none">
          <CardHeader className="border-b border-slate-800 px-6 py-4">
            <CardTitle className="flex items-center gap-2.5 text-base font-semibold text-slate-200">
              <ShieldAlert className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
              Detection Streams
              <span className="ml-1 text-sm font-normal text-slate-500">
                {isComplete
                  ? `Bonferroni correction ${streams.bonferroni_scale.toFixed(2)}×`
                  : "Live — updating…"}
              </span>
              {isStreaming && (
                <span className="ml-auto flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-amber-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-6 py-5 grid grid-cols-3 gap-5">
            <StreamGauge
              label="Business Model Drift"
              description="Semantic distance from expected business model over time"
              statistic={streams.semantic.last_statistic}
              threshold={streams.semantic.threshold}
              triggered={liveStreams?.alarms?.["semantic"] ?? (streams.semantic.last_statistic >= streams.semantic.threshold)}
            />
            <StreamGauge
              label="Third-Party Exposure"
              description="Risk contagion from directors, shareholders, and subsidiaries"
              statistic={streams.topology.last_statistic}
              threshold={streams.topology.threshold}
              triggered={liveStreams?.alarms?.["topology"] ?? (streams.topology.last_statistic >= streams.topology.threshold)}
            />
            <StreamGauge
              label="Transaction Anomalies"
              description="Abnormal patterns in transaction volume and frequency"
              statistic={streams.behavioral_tx.last_statistic}
              threshold={streams.behavioral_tx.threshold}
              triggered={liveStreams?.alarms?.["behavioral_tx"] ?? (streams.behavioral_tx.last_statistic >= streams.behavioral_tx.threshold)}
            />
          </CardContent>
        </Card>

        {/* ── Drift chart + Top contributors ──────────────────────────────── */}
        <div className="grid grid-cols-5 gap-5">
          {/* Drift chart */}
          <Card className="col-span-3 border-slate-800 bg-slate-900 shadow-none">
            <CardHeader className="border-b border-slate-800 px-6 py-4">
              <CardTitle className="flex items-center gap-2.5 text-base font-semibold text-slate-200">
                <TrendingUp className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
                Business Model Drift — 30d
              </CardTitle>
            </CardHeader>
            <CardContent className="px-3 py-4">
              {isComplete && driftData ? (
                <DriftChart data={driftData} />
              ) : (
                <div className="h-[160px] flex items-center justify-center">
                  <p className="text-xs text-slate-500">Available after analysis completes</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Top contributors */}
          <Card className="col-span-2 border-slate-800 bg-slate-900 shadow-none">
            <CardHeader className="border-b border-slate-800 px-6 py-4">
              <CardTitle className="text-base font-semibold text-slate-200">Top Risk Contributors</CardTitle>
            </CardHeader>
            <CardContent className="px-6 py-4 space-y-3">
              {contributors.length === 0 ? (
                <p className="text-sm text-slate-500 py-2">
                  {isStreaming ? "Resolving entities…" : "No high-risk contributors identified"}
                </p>
              ) : (
                contributors.map((c, i) => (
                  <div key={i} className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-base">{c.type.toLowerCase() === "person" ? "👤" : "🏢"}</span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-200 truncate">{c.name}</p>
                        <p className="text-xs text-slate-500">{c.relation.replace(/_/g, " ")}</p>
                      </div>
                    </div>
                    <span className={cn(
                      "text-base font-bold tabular-nums font-mono shrink-0",
                      c.intrinsic_risk >= 0.75 ? "text-rose-400" :
                      c.intrinsic_risk >= 0.4  ? "text-amber-400" : "text-emerald-400"
                    )}>
                      {(c.intrinsic_risk * 100).toFixed(0)}%
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Agent Forensic Report ──────────────────────────────────────── */}
        {isComplete && !isGeneratingReport ? (
          <ComplianceReport markdown={report!.report_markdown} />
        ) : (
          <Card className="border-slate-800 bg-slate-900 shadow-none">
            <CardHeader className="border-b border-slate-800 px-6 py-4">
              <CardTitle className="text-base font-semibold text-slate-200">Agent Forensic Report</CardTitle>
            </CardHeader>
            <CardContent className="px-6 py-8">
              {isGeneratingReport ? (
                <div className="flex items-center gap-4">
                  <Loader2 className="h-5 w-5 animate-spin text-amber-400 shrink-0" />
                  <div className="flex-1 space-y-3">
                    <div className="h-3 bg-slate-800 rounded animate-pulse w-3/4" />
                    <div className="h-3 bg-slate-800 rounded animate-pulse w-full" />
                    <div className="h-3 bg-slate-800 rounded animate-pulse w-5/6" />
                    <div className="h-3 bg-slate-800 rounded animate-pulse w-2/3" />
                    <p className="text-xs text-slate-500 pt-1">Groq LLM is drafting the AML forensic report…</p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  {isStreaming
                    ? "Report will be generated once risk threshold is breached and events are processed."
                    : "No active alert — forensic report not generated."}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* ── Audit Trail ───────────────────────────────────────────────── */}
        {isComplete && governance ? (
          <AuditTrailCollapsible governance={governance} />
        ) : (
          <div className="rounded-xl border border-slate-800 bg-slate-900 px-6 py-5 flex items-center gap-3">
            <CheckCircle2 className="h-5 w-5 opacity-40 text-slate-500" />
            <div>
              <p className="text-sm font-medium text-slate-400">
                {isStreaming ? "Governance workflow pending analysis completion" : "No governance workflow active"}
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                {isStreaming ? "Available once the analysis stream completes." : "Entity is within normal risk parameters."}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── Sticky bottom — Governance actions ──────────────────────────── */}
      {isComplete && alarmFired && governance && (() => {
        const pendingStatuses = ["DETECTED", "UNDER_REVIEW", "FOUR_EYES_PENDING"];
        const isPending  = pendingStatuses.includes(governance.status);
        const isResolved = governance.status === "RESOLVED_MITIGATED";
        const isDismissed = governance.status === "RESOLVED_FALSE_POSITIVE";

        return (
          <div className="sticky bottom-0 z-30 border-t border-slate-800 bg-slate-950/80 backdrop-blur-md px-8 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <ShieldAlert className="h-4 w-4 text-amber-400" />
                Four-Eyes Governance — Alert{" "}
                <span className="font-mono font-semibold text-slate-300">{governance.alert_id}</span>
              </div>

              {isPending && (
                <div className="flex items-center gap-3">
                  <Button variant="outline" size="sm" disabled={actionLoading}
                    className="gap-2 border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm"
                    onClick={() => handleAction("DISMISS_FALSE_POSITIVE")}>
                    {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                    Dismiss False Positive
                  </Button>
                  <Button variant="outline" size="sm" disabled={actionLoading}
                    className="gap-2 border-amber-500/20 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 text-sm"
                    onClick={() => handleAction("APPROVE_ENHANCED_DD")}>
                    {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CircleCheck className="h-4 w-4" />}
                    Enhanced Due Diligence
                  </Button>
                  <Button size="sm" disabled={actionLoading}
                    className="gap-2 bg-rose-600 hover:bg-rose-700 text-white border-0 text-sm font-semibold px-4"
                    onClick={() => handleAction("APPROVE_FREEZE")}>
                    {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CircleCheck className="h-4 w-4" />}
                    Approve — Freeze Assets
                  </Button>
                </div>
              )}

              {isResolved && (
                <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
                  <CheckCircle2 className="h-4 w-4" />
                  Asset freeze executed — case closed
                </div>
              )}

              {isDismissed && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <CheckCircle2 className="h-4 w-4" />
                  Dismissed as false positive — case closed
                </div>
              )}

              {!isPending && !isResolved && !isDismissed && (
                <div className="flex items-center gap-2 text-sm text-amber-400">
                  <Clock className="h-4 w-4" />
                  Awaiting compliance approval — status: {governance.status}
                </div>
              )}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
