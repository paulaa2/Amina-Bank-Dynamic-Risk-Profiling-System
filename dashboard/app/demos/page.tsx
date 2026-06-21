"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ExternalLink,
  FileText,
  GitBranch,
  History,
  Loader2,
  Network,
  Play,
  RefreshCw,
  ShieldAlert,
  X,
  Zap,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CorporateGraph } from "@/components/corporate-graph";
import {
  listGlobalScenarios,
  listReplayScenarios,
  replayScenario,
  runGlobalScenario,
  type GlobalContagionEvent,
  type GlobalDemoResult,
  type GlobalScenarioItem,
  type LiveEvent,
  type LiveReport,
  type ReplayScenarioItem,
} from "@/lib/api-client";
import { alertLevelFor } from "@/lib/build-from-api";
import type { GraphEdge, GraphNode } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

type DemoMode = "replay" | "contagion";

function pct(value: number | undefined | null): string {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function eventDate(event: LiveEvent): string | null {
  if (!event.date) return null;
  return new Date(event.date).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function eventTone(event: LiveEvent, threshold: number) {
  if (event.combined_risk > threshold) return "text-rose-300";
  if (event.combined_risk >= 0.4) return "text-amber-300";
  return "text-emerald-300";
}

function decodeEntities(text: string): string {
  return text
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&apos;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">");
}

function cleanEvidenceText(value: string | null | undefined): string {
  if (!value) return "";
  return decodeEntities(
    value
      .replace(/<a\s+[^>]*>([\s\S]*?)<\/a>/gi, "$1")
      .replace(/<font\s+[^>]*>([\s\S]*?)<\/font>/gi, " $1")
      .replace(/<br\s*\/?>/gi, " ")
      .replace(/<[^>]+>/g, " ")
  )
    .replace(/\s+/g, " ")
    .trim();
}

function evidenceUrl(event: LiveEvent): string | null {
  const href = event.evidence?.match(/href=["']([^"']+)["']/i)?.[1];
  return href ? decodeEntities(href) : event.url || null;
}

function FullEvidenceModal({
  event,
  onClose,
}: {
  event: LiveEvent | null;
  onClose: () => void;
}) {
  if (!event) return null;
  const body = cleanEvidenceText(event.evidence) || event.extracted_fact || "No full evidence text was returned for this event.";
  const url = evidenceUrl(event);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-6 backdrop-blur-[2px]">
      <div className="max-h-[86vh] w-full max-w-4xl overflow-hidden rounded-lg border border-slate-700/80 bg-slate-950/90 shadow-2xl backdrop-blur-xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-800 px-6 py-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              {eventDate(event) && <span>{eventDate(event)}</span>}
              {event.source && <span>{event.source}</span>}
              <span>{pct(event.combined_risk)} combined risk</span>
            </div>
            <h2 className="mt-2 text-lg font-semibold leading-snug text-slate-100">
              {event.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-100"
            aria-label="Close full evidence"
          >
            <X className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </div>
        <div className="max-h-[62vh] overflow-y-auto px-6 py-5">
          <p className="whitespace-pre-wrap text-sm leading-7 text-slate-300">
            {body}
          </p>
          {event.extracted_fact && event.extracted_fact !== body && (
            <div className="mt-5 rounded-lg border border-slate-800 bg-slate-900 p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Extracted fact
              </p>
              <p className="mt-2 text-sm leading-relaxed text-slate-300">
                {event.extracted_fact}
              </p>
            </div>
          )}
        </div>
        {url && (
          <div className="border-t border-slate-800 px-6 py-4">
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-300 hover:text-slate-100"
            >
              Open original source
              <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} />
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

function contagionCopy(event: GlobalContagionEvent): { title: string; detail: string; icon: React.ElementType; tone: string } {
  if (event.type === "published") {
    return {
      title: `${event.source ?? "Client"} publishes shared threat`,
      detail: `${event.entity ?? "Entity"} entered shared memory at ${pct(event.risk)} risk.`,
      icon: Zap,
      tone: "text-slate-300",
    };
  }
  if (event.type === "inherited") {
    return {
      title: `${event.target ?? "Client"} inherits cross-client risk`,
      detail: `${event.entity ?? "Entity"} was elevated to ${pct(event.risk)} before local news was processed.`,
      icon: GitBranch,
      tone: "text-cyan-300",
    };
  }
  if (event.type === "frozen") {
    return {
      title: `${event.target ?? "Client"} enters alert state`,
      detail: `Processing stopped for this client after reaching ${pct(event.risk)} combined risk.`,
      icon: ShieldAlert,
      tone: "text-rose-300",
    };
  }
  return {
    title: event.trigger ? `${event.target ?? "Client"} event triggered alert` : `${event.target ?? "Client"} event processed`,
    detail: `${event.title ?? "News event"} - combined risk ${pct(event.risk)}.`,
    icon: History,
    tone: event.trigger ? "text-rose-300" : "text-slate-400",
  };
}

function safeGraphId(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

function findGlobalLiveEvent(
  result: GlobalDemoResult | null,
  event: GlobalContagionEvent | undefined,
): LiveEvent | null {
  if (!result || !event?.title || !event.target) return null;
  const report = result.clients[event.target];
  if (!report) return null;
  const title = event.title.toLowerCase();
  return report.events.find((candidate) => {
    const candidateTitle = candidate.title.toLowerCase();
    return candidateTitle.includes(title) || title.includes(candidateTitle.slice(0, 80));
  }) ?? null;
}

function buildContagionGraph(
  result: GlobalDemoResult,
  visibleEvents: GlobalContagionEvent[],
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const companyCount = Math.max(result.companies.length, 1);
  const canvasWidth = Math.max(720, companyCount * 230);
  const centerX = canvasWidth / 2;

  const latestClientRisk = new Map<string, number>();
  for (const company of result.companies) latestClientRisk.set(company, 0.05);
  for (const event of visibleEvents) {
    if ((event.type === "event" || event.type === "frozen") && event.target) {
      latestClientRisk.set(event.target, event.risk ?? latestClientRisk.get(event.target) ?? 0.05);
    }
  }

  const companyStart = centerX - ((companyCount - 1) * 220) / 2 - 55;
  result.companies.forEach((company, index) => {
    nodes.push({
      id: `client_${safeGraphId(company)}`,
      label: company,
      type: "company",
      intrinsicRisk: latestClientRisk.get(company) ?? 0.05,
      position: {
        x: Math.round(companyStart + index * 220),
        y: 300,
      },
    });
  });

  const shared = new Map<string, number>();
  for (const event of visibleEvents) {
    if ((event.type === "published" || event.type === "inherited") && event.entity) {
      shared.set(event.entity, Math.max(shared.get(event.entity) ?? 0, event.risk ?? 0));
    }
  }

  const sharedEntries = [...shared.entries()];
  const sharedStart = centerX - ((sharedEntries.length - 1) * 190) / 2 - 55;
  sharedEntries.forEach(([entity, risk], index) => {
    nodes.push({
      id: `shared_${safeGraphId(entity)}`,
      label: entity,
      type: "company",
      intrinsicRisk: risk,
      position: {
        x: Math.round(sharedStart + index * 190),
        y: 80,
      },
      discoveredDuringRun: true,
      isNewDiscovery: true,
    });
  });

  const edgeKeys = new Set<string>();
  for (const [index, event] of visibleEvents.entries()) {
    if (event.type === "published" && event.source && event.entity) {
      const source = `client_${safeGraphId(event.source)}`;
      const target = `shared_${safeGraphId(event.entity)}`;
      const id = `${source}_${target}_published`;
      if (!edgeKeys.has(id)) {
        edgeKeys.add(id);
        edges.push({ id: `${id}_${index}`, source, target, label: "published risk" });
      }
    }
    if (event.type === "inherited" && event.target && event.entity) {
      const source = `shared_${safeGraphId(event.entity)}`;
      const target = `client_${safeGraphId(event.target)}`;
      const id = `${source}_${target}_inherited`;
      if (!edgeKeys.has(id)) {
        edgeKeys.add(id);
        edges.push({ id: `${id}_${index}`, source, target, label: "inherited risk" });
      }
    }
  }

  return { nodes, edges };
}

function ReplayEvidenceList({
  report,
  onOpenEvidence,
}: {
  report: LiveReport;
  onOpenEvidence: (event: LiveEvent) => void;
}) {
  const threshold = report.decision.threshold;
  return (
    <div className="space-y-3">
      {report.events.map((event, index) => {
        const alarm = event.combined_risk > threshold;
        const cleanEvidence = cleanEvidenceText(event.evidence);
        const url = evidenceUrl(event);
        return (
          <article
            key={`${event.title}-${index}`}
            className="rounded-lg border border-slate-800 bg-slate-900 p-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-slate-500">
                  <span>Step {index + 1}</span>
                  {eventDate(event) && <span>{eventDate(event)}</span>}
                  {event.source && <span>{event.source}</span>}
                </div>
                <h3 className="mt-2 text-sm font-semibold leading-snug text-slate-100">
                  {event.title}
                </h3>
              </div>
              <div className="shrink-0 text-right">
                <p className={cn("font-mono text-xl font-bold tabular-nums", eventTone(event, threshold))}>
                  {pct(event.combined_risk)}
                </p>
                <p className="text-[10px] uppercase tracking-wider text-slate-600">
                  combined risk
                </p>
              </div>
            </div>

            {event.evidence && (
              <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300">
                  <FileText className="h-3.5 w-3.5 text-slate-500" strokeWidth={1.75} />
                  Full news evidence
                </div>
                <p className="line-clamp-4 text-xs leading-relaxed text-slate-400">{cleanEvidence}</p>
              </div>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge
                variant="outline"
                className={cn(
                  "border-slate-700 bg-slate-950 text-slate-400",
                  alarm && "border-rose-500/20 bg-rose-500/10 text-rose-300",
                )}
              >
                {alarm ? "Scenario alarm" : "Below threshold"}
              </Badge>
              {event.new_graph_nodes.length > 0 && (
                <Badge variant="outline" className="border-amber-500/20 bg-amber-500/10 text-amber-300">
                  {event.new_graph_nodes.length} graph update{event.new_graph_nodes.length === 1 ? "" : "s"}
                </Badge>
              )}
              {url && (
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-auto inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-slate-100"
                >
                  Source
                  <ExternalLink className="h-3 w-3" strokeWidth={1.75} />
                </a>
              )}
              {(event.evidence || event.extracted_fact) && (
                <button
                  type="button"
                  onClick={() => onOpenEvidence(event)}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-slate-100"
                >
                  Read full text
                  <ArrowRight className="h-3 w-3" strokeWidth={1.75} />
                </button>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function SharedThreatGraph({ result }: { result: GlobalDemoResult }) {
  const published = result.contagion_events.filter((event) => event.type === "published");
  const inherited = result.contagion_events.filter((event) => event.type === "inherited");
  const threats = Object.entries(result.shared_threat_memory);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Network className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
            Shared threat graph
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Visual path of what gets published globally and which client inherits it.
          </p>
        </div>
        <Badge variant="outline" className="border-slate-700 bg-slate-950 text-slate-400">
          {threats.length} shared node{threats.length === 1 ? "" : "s"}
        </Badge>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr_1fr]">
        <div className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Publishers</p>
          {result.companies.map((company) => {
            const didPublish = published.some((event) => event.source === company);
            return (
              <div
                key={company}
                className={cn(
                  "rounded-lg border px-3 py-3",
                  didPublish ? "border-slate-600 bg-slate-800/50" : "border-slate-800 bg-slate-950",
                )}
              >
                <p className="text-sm font-semibold text-slate-100">{company}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {didPublish ? "Published risk to shared memory" : "No shared publication detected"}
                </p>
              </div>
            );
          })}
        </div>

        <div className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Shared memory</p>
          {threats.length ? threats.map(([entity, risk]) => (
            <div key={entity} className="rounded-lg border border-slate-700 bg-slate-950 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-sm font-semibold text-slate-100">{entity}</p>
                <span className="font-mono text-sm font-bold text-slate-300">{pct(risk)}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                <div className="h-full rounded-full bg-slate-400" style={{ width: pct(risk) }} />
              </div>
            </div>
          )) : (
            <div className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-sm text-slate-500">
              No shared threat has been published in this run.
            </div>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Inheritors</p>
          {result.companies.map((company) => {
            const inheritedEvents = inherited.filter((event) => event.target === company);
            return (
              <div
                key={company}
                className={cn(
                  "rounded-lg border px-3 py-3",
                  inheritedEvents.length ? "border-sky-500/20 bg-sky-500/10" : "border-slate-800 bg-slate-950",
                )}
              >
                <p className="text-sm font-semibold text-slate-100">{company}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {inheritedEvents.length
                    ? `Inherited ${inheritedEvents.map((event) => event.entity).join(", ")}`
                    : "No inherited risk detected"}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ContagionTimeline({ events }: { events: GlobalContagionEvent[] }) {
  if (!events.length) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-6 text-sm text-slate-500">
        Run a global demo to see the orchestrator trace.
      </div>
    );
  }

  return (
    <ol className="space-y-3">
      {events.map((event, index) => {
        const copy = contagionCopy(event);
        const Icon = copy.icon;
        return (
          <li key={`${event.type}-${index}`} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-800 bg-slate-950">
                <Icon className={cn("h-4 w-4", copy.tone)} strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-100">{copy.title}</h3>
                  <span className="font-mono text-[11px] text-slate-600">#{index + 1}</span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">{copy.detail}</p>
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function ClientOutcomeGrid({ result }: { result: GlobalDemoResult }) {
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {Object.entries(result.clients).map(([name, report]) => {
        const level = alertLevelFor(report.decision.max_combined_risk);
        const id = result.company_ids[name] ?? Number(report.id);
        return (
          <div key={name} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-slate-100">{name}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {report.events.length} events processed
                </p>
              </div>
              <Badge
                variant="outline"
                className={cn(
                  "border-slate-700 bg-slate-950 text-slate-400",
                  report.decision.alarm_fired && "border-rose-500/20 bg-rose-500/10 text-rose-300",
                )}
              >
                {level}
              </Badge>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Peak risk</p>
                <p className="mt-1 font-mono text-xl font-bold text-slate-100">
                  {pct(report.decision.max_combined_risk)}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Graph risk</p>
                <p className="mt-1 font-mono text-xl font-bold text-slate-100">
                  {pct(report.topology.company_exposure)}
                </p>
              </div>
            </div>
            {id ? (
              <Link
                href={`/client/${id}`}
                className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-slate-100"
              >
                Open dossier
                <ArrowRight className="h-3 w-3" strokeWidth={1.75} />
              </Link>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export default function DemoStudioPage() {
  const [mode, setMode] = useState<DemoMode>("replay");
  const [replays, setReplays] = useState<ReplayScenarioItem[]>([]);
  const [globalScenarios, setGlobalScenarios] = useState<GlobalScenarioItem[]>([]);
  const [selectedReplayId, setSelectedReplayId] = useState<string | null>(null);
  const [selectedGlobalId, setSelectedGlobalId] = useState<string | null>(null);
  const [replayReport, setReplayReport] = useState<LiveReport | null>(null);
  const [globalResult, setGlobalResult] = useState<GlobalDemoResult | null>(null);
  const [loadingReplay, setLoadingReplay] = useState(false);
  const [loadingGlobal, setLoadingGlobal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedEvent, setExpandedEvent] = useState<LiveEvent | null>(null);
  const [contagionStep, setContagionStep] = useState(-1);

  useEffect(() => {
    (async () => {
      try {
        const [replayList, globalList] = await Promise.all([
          listReplayScenarios(),
          listGlobalScenarios(),
        ]);
        setReplays(replayList);
        setGlobalScenarios(globalList);
        setSelectedReplayId(replayList[0]?.scenario_id ?? null);
        setSelectedGlobalId(globalList[0]?.id ?? null);
      } catch (err) {
        setError(String(err));
      }
    })();
  }, []);

  const selectedReplay = useMemo(
    () => replays.find((item) => item.scenario_id === selectedReplayId) ?? null,
    [replays, selectedReplayId],
  );
  const selectedGlobal = useMemo(
    () => globalScenarios.find((item) => item.id === selectedGlobalId) ?? null,
    [globalScenarios, selectedGlobalId],
  );
  const visibleContagionEvents = useMemo(
    () => globalResult
      ? globalResult.contagion_events.slice(0, Math.max(0, contagionStep + 1))
      : [],
    [globalResult, contagionStep],
  );
  const selectedContagionEvent =
    globalResult && contagionStep >= 0
      ? globalResult.contagion_events[contagionStep]
      : undefined;
  const contagionGraph = useMemo(
    () => globalResult ? buildContagionGraph(globalResult, visibleContagionEvents) : null,
    [globalResult, visibleContagionEvents],
  );
  const selectedGlobalLiveEvent = useMemo(
    () => findGlobalLiveEvent(globalResult, selectedContagionEvent),
    [globalResult, selectedContagionEvent],
  );

  async function loadReplay(forceRefresh = false) {
    if (!selectedReplayId) return;
    setLoadingReplay(true);
    setError(null);
    try {
      setReplayReport(await replayScenario(selectedReplayId, { force_refresh: forceRefresh }));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoadingReplay(false);
    }
  }

  async function loadGlobal(forceRefresh = false) {
    if (!selectedGlobalId) return;
    setLoadingGlobal(true);
    setError(null);
    try {
      const result = await runGlobalScenario(selectedGlobalId, { force_refresh: forceRefresh });
      setGlobalResult(result);
      setContagionStep(Math.max(-1, result.contagion_events.length - 1));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoadingGlobal(false);
    }
  }

  return (
    <div className="risk-workspace min-h-screen space-y-5 px-7 py-6">
      <header className="flex flex-col gap-4 border-b border-slate-800 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Demo Studio
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-100">
            Evidence-backed pKYC demonstrations
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-500">
            Present the two strongest proof points separately: temporal risk drift inside one client, and cross-client contagion through shared graph entities.
          </p>
        </div>
        <div className="flex rounded-lg border border-slate-800 bg-slate-900 p-1">
          {[
            { id: "replay" as const, label: "Historical replay", icon: History },
            { id: "contagion" as const, label: "Network contagion", icon: Network },
          ].map((item) => {
            const Icon = item.icon;
            const active = mode === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setMode(item.id)}
                className={cn(
                  "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold transition-colors",
                  active ? "bg-slate-800 text-slate-100" : "text-slate-500 hover:text-slate-200",
                )}
              >
                <Icon className="h-4 w-4" strokeWidth={1.75} />
                {item.label}
              </button>
            );
          })}
        </div>
      </header>

      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.75} />
          <span>{error}</span>
        </div>
      )}

      {mode === "replay" ? (
        <main className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
          <aside className="space-y-3">
            {replays.map((scenario) => {
              const active = scenario.scenario_id === selectedReplayId;
              return (
                <button
                  key={scenario.scenario_id}
                  onClick={() => {
                    setSelectedReplayId(scenario.scenario_id);
                    setReplayReport(null);
                  }}
                  className={cn(
                    "w-full rounded-lg border p-4 text-left transition-colors",
                    active
                      ? "border-slate-600 bg-slate-900"
                      : "border-slate-800 bg-slate-950 hover:border-slate-700 hover:bg-slate-900",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-100">{scenario.client}</p>
                      <p className="mt-1 text-xs text-slate-500">{scenario.event_count} replay steps</p>
                    </div>
                    <BarChart3 className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
                  </div>
                  <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-slate-500">
                    {scenario.description}
                  </p>
                </button>
              );
            })}
          </aside>

          <section className="space-y-4">
            <div className="rounded-lg border border-slate-800 bg-slate-950 p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
                    <History className="h-4 w-4" strokeWidth={1.75} />
                    Curated historical replay
                  </div>
                  <h2 className="mt-2 text-lg font-semibold text-slate-100">
                    {selectedReplay?.client ?? "Select a replay"}
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-500">
                    {selectedReplay?.description ?? "Choose a curated scenario to load the full step-by-step evidence trail."}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {selectedReplay?.company_id && (
                    <Link
                      href={`/client/${selectedReplay.company_id}`}
                      className={buttonVariants({ variant: "outline" })}
                    >
                      Open dossier
                      <ArrowRight data-icon="inline-end" className="h-4 w-4" />
                    </Link>
                  )}
                  <Button onClick={() => loadReplay(false)} disabled={!selectedReplayId || loadingReplay}>
                    {loadingReplay ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    Load replay
                  </Button>
                  <Button variant="outline" onClick={() => loadReplay(true)} disabled={!selectedReplayId || loadingReplay}>
                    <RefreshCw className={cn("h-4 w-4", loadingReplay && "animate-spin")} />
                    Refresh
                  </Button>
                </div>
              </div>
            </div>

            {replayReport ? (
              <>
                <div className="grid gap-3 md:grid-cols-4">
                  {[
                    { label: "Client", value: replayReport.client.legal_name },
                    { label: "Peak risk", value: pct(replayReport.decision.max_combined_risk) },
                    {
                      label: "Evidence processed",
                      value: `${replayReport.scenario?.processed_event_count ?? replayReport.events.length}/${replayReport.scenario?.curated_event_count ?? replayReport.events.length}`,
                    },
                    { label: "Graph updates", value: String(replayReport.events.reduce((sum, event) => sum + event.new_graph_nodes.length, 0)) },
                  ].map((item) => (
                    <div key={item.label} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">{item.label}</p>
                      <p className="mt-1 truncate text-sm font-semibold text-slate-100">{item.value}</p>
                    </div>
                  ))}
                </div>
                {replayReport.scenario?.curated_event_count &&
                  replayReport.scenario.curated_event_count > replayReport.events.length && (
                    <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
                      The scenario contains {replayReport.scenario.curated_event_count} curated evidence items; the engine processed {replayReport.events.length} before early-stop because the alert threshold was reached.
                    </div>
                  )}
                <ReplayEvidenceList report={replayReport} onOpenEvidence={setExpandedEvent} />
              </>
            ) : (
              <div className="rounded-lg border border-dashed border-slate-800 bg-slate-950 p-8 text-center">
                <FileText className="mx-auto h-7 w-7 text-slate-600" strokeWidth={1.75} />
                <p className="mt-3 text-sm font-semibold text-slate-300">Load a replay to show the full news trail.</p>
                <p className="mt-1 text-xs text-slate-500">Each step will show the source, full evidence, risk movement and graph mutations.</p>
              </div>
            )}
          </section>
        </main>
      ) : (
        <main className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
          <aside className="space-y-3">
            {globalScenarios.map((scenario) => {
              const active = scenario.id === selectedGlobalId;
              return (
                <button
                  key={scenario.id}
                  onClick={() => {
                    setSelectedGlobalId(scenario.id);
                    setGlobalResult(null);
                    setContagionStep(-1);
                  }}
                  className={cn(
                    "w-full rounded-lg border p-4 text-left transition-colors",
                    active
                      ? "border-slate-600 bg-slate-900"
                      : "border-slate-800 bg-slate-950 hover:border-slate-700 hover:bg-slate-900",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-100">{scenario.name}</p>
                      <p className="mt-1 text-xs text-slate-500">{scenario.companies.join(" / ")}</p>
                    </div>
                    <Network className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
                  </div>
                  <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-slate-500">
                    {scenario.description}
                  </p>
                  <p className="mt-3 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                    Expected: {scenario.expected_contagion}
                  </p>
                </button>
              );
            })}
          </aside>

          <section className="space-y-4">
            <div className="rounded-lg border border-slate-800 bg-slate-950 p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
                    <Network className="h-4 w-4" strokeWidth={1.75} />
                    Cross-client contagion
                  </div>
                  <h2 className="mt-2 text-lg font-semibold text-slate-100">
                    {selectedGlobal?.name ?? "Select a global demo"}
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-500">
                    {selectedGlobal?.description ?? "Choose a network scenario to run the discrete-event global demo."}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => loadGlobal(false)} disabled={!selectedGlobalId || loadingGlobal}>
                    {loadingGlobal ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    Run demo
                  </Button>
                  <Button variant="outline" onClick={() => loadGlobal(true)} disabled={!selectedGlobalId || loadingGlobal}>
                    <RefreshCw className={cn("h-4 w-4", loadingGlobal && "animate-spin")} />
                    Refresh
                  </Button>
                </div>
              </div>
            </div>

            {globalResult ? (
              <>
                <div className="grid gap-3 md:grid-cols-4">
                  {[
                    { label: "Clients", value: globalResult.companies.join(" / ") },
                    { label: "Shared threats", value: String(Object.keys(globalResult.shared_threat_memory).length) },
                    { label: "Trace events", value: String(globalResult.contagion_events.length) },
                    { label: "Expected path", value: globalResult.expected_contagion },
                  ].map((item) => (
                    <div key={item.label} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">{item.label}</p>
                      <p className="mt-1 truncate text-sm font-semibold text-slate-100">{item.value}</p>
                    </div>
                  ))}
                </div>

                <ClientOutcomeGrid result={globalResult} />

                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="rounded-lg border border-slate-800 bg-slate-900">
                    <div className="flex flex-col gap-3 border-b border-slate-800 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
                      <div>
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                          <Network className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
                          Contagion graph
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          Step {contagionStep < 0 ? "baseline" : contagionStep + 1} of {globalResult.contagion_events.length}; shared entities appear when published or inherited.
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setContagionStep(-1)}
                          disabled={contagionStep < 0}
                        >
                          Baseline
                        </Button>
                        <Button
                          variant="outline"
                          size="icon-sm"
                          onClick={() => setContagionStep((step) => Math.max(-1, step - 1))}
                          disabled={contagionStep < 0}
                          aria-label="Previous contagion step"
                        >
                          <ArrowRight className="h-4 w-4 rotate-180" />
                        </Button>
                        <Button
                          variant="outline"
                          size="icon-sm"
                          onClick={() => setContagionStep((step) => Math.min(globalResult.contagion_events.length - 1, step + 1))}
                          disabled={contagionStep >= globalResult.contagion_events.length - 1}
                          aria-label="Next contagion step"
                        >
                          <ArrowRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    <div className="p-3">
                      {contagionGraph && (
                        <CorporateGraph
                          key={`${globalResult.scenario_id}-${contagionStep}-${contagionGraph.nodes.map((node) => node.id).join("|")}`}
                          nodes={contagionGraph.nodes}
                          edges={contagionGraph.edges}
                          height={520}
                        />
                      )}
                    </div>
                  </div>

                  <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
                    <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                      Event Review
                    </p>
                    {selectedContagionEvent ? (
                      <div className="mt-3 space-y-4">
                        {(() => {
                          const copy = contagionCopy(selectedContagionEvent);
                          const Icon = copy.icon;
                          return (
                            <div>
                              <div className="flex items-start gap-3">
                                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-800 bg-slate-950">
                                  <Icon className={cn("h-4 w-4", copy.tone)} strokeWidth={1.75} />
                                </div>
                                <div className="min-w-0">
                                  <h3 className="text-sm font-semibold leading-snug text-slate-100">{copy.title}</h3>
                                  <p className="mt-1 text-xs leading-relaxed text-slate-500">{copy.detail}</p>
                                </div>
                              </div>
                            </div>
                          );
                        })()}

                        {selectedGlobalLiveEvent && (
                          <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">
                              Source item
                            </p>
                            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] font-medium text-slate-500">
                              {eventDate(selectedGlobalLiveEvent) && <span>{eventDate(selectedGlobalLiveEvent)}</span>}
                              {selectedGlobalLiveEvent.source && <span>{selectedGlobalLiveEvent.source}</span>}
                            </div>
                            <p className="mt-2 text-sm font-semibold leading-snug text-slate-100">
                              {selectedGlobalLiveEvent.title}
                            </p>
                            <p className="mt-2 line-clamp-4 text-xs leading-relaxed text-slate-300">
                              {cleanEvidenceText(selectedGlobalLiveEvent.evidence) || selectedGlobalLiveEvent.extracted_fact}
                            </p>
                            <div className="mt-3 flex flex-wrap items-center gap-3">
                              <button
                                type="button"
                                onClick={() => setExpandedEvent(selectedGlobalLiveEvent)}
                                className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-300 hover:text-slate-100"
                              >
                                Read full text
                                <ArrowRight className="h-3 w-3" strokeWidth={1.75} />
                              </button>
                              {evidenceUrl(selectedGlobalLiveEvent) && (
                                <a
                                  href={evidenceUrl(selectedGlobalLiveEvent) ?? undefined}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-100"
                                >
                                  Open source
                                  <ExternalLink className="h-3 w-3" strokeWidth={1.75} />
                                </a>
                              )}
                            </div>
                          </div>
                        )}

                        <div className="space-y-3">
                          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">
                            Effect on network
                          </p>
                          <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                            <div
                              className={cn(
                                "h-full rounded-full transition-all",
                                (selectedContagionEvent.risk ?? 0) >= 0.75
                                  ? "bg-rose-400"
                                  : (selectedContagionEvent.risk ?? 0) >= 0.4
                                    ? "bg-amber-400"
                                    : "bg-emerald-400",
                              )}
                              style={{ width: pct(selectedContagionEvent.risk) }}
                            />
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Risk</p>
                            <p className="mt-1 font-mono text-lg font-bold text-slate-100">{pct(selectedContagionEvent.risk)}</p>
                          </div>
                          <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Type</p>
                            <p className="mt-1 text-sm font-semibold capitalize text-slate-100">{selectedContagionEvent.type.replace(/_/g, " ")}</p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950 p-4">
                        <p className="text-sm font-semibold text-slate-200">Baseline graph</p>
                        <p className="mt-1 text-xs leading-relaxed text-slate-500">
                          Only client pipelines are visible. Shared threat entities appear as the orchestrator publishes or inherits risk.
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                <SharedThreatGraph result={globalResult} />

                <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
                  <div>
                    <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
                      <GitBranch className="h-4 w-4 text-slate-500" strokeWidth={1.75} />
                      Orchestrator trace
                    </div>
                    <ContagionTimeline events={globalResult.contagion_events} />
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" strokeWidth={1.75} />
                      What this demonstrates
                    </div>
                    <div className="mt-4 space-y-4 text-xs leading-relaxed text-slate-500">
                      <p>
                        One client&apos;s adverse evidence can publish a risky shared entity into global memory.
                      </p>
                      <p>
                        A second isolated client can inherit that risk before its own local news creates an alert.
                      </p>
                      <p>
                        The UI now shows the causal path, final client outcomes and the dossier links for drill-down.
                      </p>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="rounded-lg border border-dashed border-slate-800 bg-slate-950 p-8 text-center">
                <Network className="mx-auto h-7 w-7 text-slate-600" strokeWidth={1.75} />
                <p className="mt-3 text-sm font-semibold text-slate-300">Run a global demo to show network propagation.</p>
                <p className="mt-1 text-xs text-slate-500">First run can take a while because it executes multiple client pipelines.</p>
              </div>
            )}
          </section>
        </main>
      )}
      <FullEvidenceModal event={expandedEvent} onClose={() => setExpandedEvent(null)} />
    </div>
  );
}
