"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Building2,
  Clock,
  Eye,
  EyeOff,
  ArrowRight,
  Play,
  RefreshCw,
  Wifi,
  WifiOff,
  Loader2,
  CalendarClock,
  CheckCircle2,
} from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { KpiCard } from "@/components/kpi-card";
import { AlertBadge } from "@/components/alert-badge";
import {
  listCompanies,
  analyzeCompany,
  getCachedReport,
  getCachedAnalysis,
  checkHealth,
  getSchedulerStatus,
  type CompanyListItem,
  type LiveReport,
  type SchedulerStatus,
} from "@/lib/api-client";
import { alertLevelFor, triggerReasonFor } from "@/lib/build-from-api";

// ── Per-row state ─────────────────────────────────────────────────────────────

type RowState =
  | { status: "idle" }
  | { status: "analyzing" }
  | { status: "done"; report: LiveReport }
  | { status: "error"; message: string };

function formatTimestamp(iso: string) {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ControlRoom() {
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [companies, setCompanies] = useState<CompanyListItem[]>([]);
  const [rowStates, setRowStates] = useState<Record<number, RowState>>({});
  const [maskedIds, setMaskedIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);

  // ── Bootstrap ─────────────────────────────────────────────────────────────

  useEffect(() => {
    (async () => {
      const online = await checkHealth();
      setBackendOnline(online);

      try {
        const [list, sched] = await Promise.all([
          listCompanies(),
          getSchedulerStatus().catch(() => null),
        ]);
        setCompanies(list);
        setScheduler(sched);

        // Pre-populate rows with any results already in the session cache
        const initial: Record<number, RowState> = {};
        for (const c of list) {
          const cached = getCachedReport(c.id);
          initial[c.id] = cached ? { status: "done", report: cached } : { status: "idle" };
        }
        setRowStates(initial);

        // Automatically fetch already-calculated reports from backend or static cache in background
        await Promise.all(
          list.map(async (c) => {
            if (!initial[c.id] || initial[c.id].status === "idle") {
              try {
                const report = await getCachedAnalysis(c.id);
                if (report) {
                  setRowStates((prev) => ({
                    ...prev,
                    [c.id]: { status: "done", report },
                  }));
                }
              } catch (err) {
                console.debug(`No cached analysis for client ${c.id}:`, err);
              }
            }
          })
        );
      } catch (err) {
        console.error("Failed to load companies:", err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // ── Analyze one company ────────────────────────────────────────────────────

  const runAnalysis = useCallback(async (id: number) => {
    setRowStates((prev) => ({ ...prev, [id]: { status: "analyzing" } }));
    try {
      const report = await analyzeCompany(id, { max_events: 5 });
      setRowStates((prev) => ({ ...prev, [id]: { status: "done", report } }));
    } catch (err) {
      setRowStates((prev) => ({
        ...prev,
        [id]: { status: "error", message: String(err) },
      }));
    }
  }, []);

  const runAll = useCallback(() => {
    for (const c of companies) {
      const state = rowStates[c.id];
      if (!state || state.status === "idle" || state.status === "error") {
        runAnalysis(c.id);
      }
    }
  }, [companies, rowStates, runAnalysis]);

  function toggleMask(id: number) {
    setMaskedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  // ── Derived KPIs ──────────────────────────────────────────────────────────

  const doneReports = Object.values(rowStates)
    .filter((s): s is Extract<RowState, { status: "done" }> => s.status === "done")
    .map((s) => s.report);

  const criticalCount = doneReports.filter(
    (r) => r.decision.alarm_fired && alertLevelFor(r.decision.max_combined_risk) === "Critical"
  ).length;

  const analyzingCount = Object.values(rowStates).filter(
    (s) => s.status === "analyzing"
  ).length;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="px-8 py-8">
      {/* Page header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-200">Control Room</h1>
          <p className="mt-1 text-sm text-slate-500">
            Real-time KYC drift monitoring &amp; alert triage — AMINA Bank
            Compliance Operations
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Backend status pill */}
          {backendOnline !== null && (
            <span
              className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium border ${
                backendOnline
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : "bg-rose-500/10 text-rose-400 border-rose-500/20"
              }`}
            >
              {backendOnline ? (
                <Wifi className="h-3 w-3" />
              ) : (
                <WifiOff className="h-3 w-3" />
              )}
              {backendOnline ? "Engine online" : "Engine offline"}
            </span>
          )}
          {backendOnline && companies.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 border-slate-700 bg-slate-800 text-sm text-slate-200 hover:bg-slate-700 hover:text-white transition-colors"
              onClick={runAll}
              disabled={analyzingCount > 0}
            >
              {analyzingCount > 0 ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              {analyzingCount > 0
                ? `Analyzing ${analyzingCount}…`
                : "Analyze All"}
            </Button>
          )}
        </div>
      </div>

      {/* KPI cards */}
      <div className="mb-5 grid grid-cols-3 gap-3">
        <KpiCard
          title="Critical Alerts"
          value={backendOnline === false ? "—" : criticalCount}
          subtitle={
            doneReports.length > 0
              ? `from ${doneReports.length} analyzed entities`
              : "Run analysis to populate"
          }
          icon={AlertTriangle}
          accent="red"
        />
        <KpiCard
          title="Entities Monitored"
          value={companies.length || "—"}
          subtitle="Registered in pKYC engine database"
          icon={Building2}
          accent="slate"
        />
        <KpiCard
          title="Analyses Running"
          value={analyzingCount || (doneReports.length > 0 ? "Complete" : "—")}
          subtitle={
            doneReports.length > 0
              ? `${doneReports.length} / ${companies.length} complete`
              : "Click Analyze to start"
          }
          icon={Clock}
          accent={analyzingCount > 0 ? "amber" : "emerald"}
        />
      </div>

      {/* Scheduled monitoring panel */}
      {backendOnline && scheduler && (
        <div className="mb-5 flex items-center justify-between border border-slate-800 bg-slate-900 px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-800 border border-slate-700">
              <CalendarClock className="h-4 w-4 text-slate-400" strokeWidth={1.75} />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-200">Automated Monitoring Schedule</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {scheduler.schedule}
                {scheduler.next_run && (
                  <> · Next run:{" "}
                    <span className="font-medium text-slate-300">
                      {new Date(scheduler.next_run).toLocaleString("en-GB", {
                        day: "2-digit", month: "short", year: "numeric",
                        hour: "2-digit", minute: "2-digit", timeZoneName: "short",
                      })}
                    </span>
                  </>
                )}
                {scheduler.last_run && (
                  <> · Last sweep:{" "}
                    <span className="font-medium text-slate-300">
                      {new Date(scheduler.last_run).toLocaleString("en-GB", {
                        day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
                      })}
                    </span>
                  </>
                )}
                {!scheduler.last_run && (
                  <span className="text-slate-600"> · No automated sweep run yet this session</span>
                )}
              </p>
            </div>
          </div>
          <div className="shrink-0">
            {scheduler.run_in_progress ? (
              <span className="flex items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-400">
                <Loader2 className="h-3 w-3 animate-spin" />
                Sweep in progress…
              </span>
            ) : scheduler.last_run ? (
              <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Last sweep complete
              </span>
            ) : null}
          </div>
        </div>
      )}

      {/* Offline banner */}
      {backendOnline === false && (
        <div className="mb-6 rounded-lg border border-rose-500/20 bg-rose-500/10 px-5 py-4 flex items-start gap-3">
          <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
          <div>
            <p className="text-sm font-semibold text-rose-300">
              pKYC Engine is not reachable
            </p>
            <p className="mt-0.5 text-xs text-rose-400/80">
              Start the FastAPI server:{" "}
              <code className="rounded bg-rose-500/10 border border-rose-500/20 px-1.5 py-0.5 font-mono text-rose-300">
                uvicorn src.api:app --reload --port 8000
              </code>
            </p>
          </div>
        </div>
      )}

      {/* Alert inbox table */}
      <div className="border border-slate-800 bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">
              Real-Time Alert Inbox
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {loading
                ? "Loading company list…"
                : companies.length === 0 && backendOnline
                ? "No companies found in the database"
                : "Showing only entities with active alerts — analyse entities from Client Dossiers"}
            </p>
          </div>
          {criticalCount > 0 && (
            <span className="rounded-full border border-rose-500/20 bg-rose-500/10 px-3 py-1 text-xs font-semibold text-rose-400">
              {criticalCount} Critical
            </span>
          )}
        </div>

        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent border-b border-slate-800">
              {["Client ID", "Entity Name", "Alert Level", "Trigger Reason", "Detected", "Action"].map(
                (h) => (
                  <TableHead
                    key={h}
                    className="text-xs font-semibold uppercase tracking-wider text-slate-500"
                  >
                    {h}
                  </TableHead>
                )
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && (
              <TableRow>
                <TableCell colSpan={6} className="py-12 text-center">
                  <Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-500" />
                  <p className="mt-2 text-sm text-slate-500">
                    Connecting to pKYC engine…
                  </p>
                </TableCell>
              </TableRow>
            )}

            {!loading && (() => {
              // Keep only alarming rows, in-progress rows, and errors.
              // Clean entities (no alarm) and unanalysed idle entities are hidden.
              const visibleCompanies = [...companies]
                .filter((c) => {
                  const s = rowStates[c.id];
                  if (!s || s.status === "idle") return false;
                  if (s.status === "done" && !s.report.decision.alarm_fired) return false;
                  return true;
                })
                .sort((a, b) => {
                  const riskOf = (id: number) => {
                    const s = rowStates[id];
                    return s?.status === "done" ? s.report.decision.max_combined_risk : -1;
                  };
                  return riskOf(b.id) - riskOf(a.id);
                });

              if (visibleCompanies.length === 0) {
                return (
                  <TableRow>
                    <TableCell colSpan={6} className="py-12 text-center">
                      <CheckCircle2 className="mx-auto h-7 w-7 text-emerald-400 mb-2" />
                      <p className="text-sm font-medium text-slate-400">No active alerts</p>
                      <p className="mt-1 text-xs text-slate-500">
                        All analysed entities are within normal risk parameters
                      </p>
                    </TableCell>
                  </TableRow>
                );
              }

              return visibleCompanies.map((company) => {
                const state = rowStates[company.id] ?? { status: "idle" };
                const isMasked = maskedIds.has(company.id);

                if (state.status === "done") {
                  const r = state.report;
                  const level = alertLevelFor(r.decision.max_combined_risk);
                  const riskPct = Math.round(r.decision.max_combined_risk * 100);
                  const auditTs = r.governance?.audit_trail[0]?.timestamp;

                  return (
                    <TableRow
                      key={company.id}
                      className="border-b border-slate-800 hover:bg-slate-800/50"
                    >
                      <TableCell className="font-mono text-xs text-slate-500">
                        #{String(company.id).padStart(3, "0")}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-slate-200">
                            {isMasked ? r.security.company_token : r.client.legal_name}
                          </span>
                          <button
                            onClick={() => toggleMask(company.id)}
                            className="text-slate-500 hover:text-slate-300 transition-colors"
                            title={isMasked ? "Reveal identity" : "Mask identity"}
                          >
                            {isMasked ? (
                              <EyeOff className="h-3.5 w-3.5" />
                            ) : (
                              <Eye className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </div>
                        <p className="font-mono text-xs text-slate-500 mt-0.5">
                          {riskPct}% combined risk
                        </p>
                      </TableCell>
                      <TableCell>
                        {r.decision.alarm_fired ? (
                          <AlertBadge level={level} />
                        ) : (
                          <Badge
                            variant="outline"
                            className="border-emerald-500/20 bg-emerald-500/10 text-emerald-400 text-xs"
                          >
                            Clear
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-slate-400 max-w-xs">
                        {r.decision.alarm_fired
                          ? triggerReasonFor(r)
                          : "No drift detected"}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-slate-500 tabular-nums">
                        {auditTs ? formatTimestamp(auditTs) : "—"}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Link
                            href={`/client/${company.id}`}
                            className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:border-slate-600 transition-colors"
                          >
                            Investigate
                            <ArrowRight className="h-3 w-3" />
                          </Link>
                          <button
                            onClick={() => runAnalysis(company.id)}
                            title="Re-run analysis"
                            className="text-slate-500 hover:text-slate-300 transition-colors"
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                }

                // idle / analyzing / error rows
                return (
                  <TableRow
                    key={company.id}
                    className="border-b border-slate-800 hover:bg-slate-800/50"
                  >
                    <TableCell className="font-mono text-xs text-slate-500">
                      #{String(company.id).padStart(3, "0")}
                    </TableCell>
                    <TableCell className="text-sm font-medium text-slate-300">
                      {company.legal_name}
                    </TableCell>
                    <TableCell>
                      {state.status === "analyzing" ? (
                        <span className="flex items-center gap-1.5 text-xs text-slate-400">
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-400" />
                          Analyzing…
                        </span>
                      ) : state.status === "error" ? (
                        <Badge
                          variant="outline"
                          className="border-rose-500/20 bg-rose-500/10 text-rose-400 text-xs"
                        >
                          Error
                        </Badge>
                      ) : (
                        <span className="text-xs text-slate-600 italic">
                          Not analyzed
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-slate-500 italic">
                      {state.status === "error"
                        ? state.message.slice(0, 60)
                        : state.status === "analyzing"
                        ? "Running pKYC pipeline…"
                        : "—"}
                    </TableCell>
                    <TableCell />
                    <TableCell>
                      {state.status !== "analyzing" && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1.5 border-slate-700 bg-slate-800 text-xs font-medium text-slate-200 hover:bg-slate-700 transition-colors"
                          onClick={() => runAnalysis(company.id)}
                        >
                          <Play className="h-3 w-3" />
                          Analyze
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              });
            })()}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
