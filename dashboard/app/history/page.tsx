"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { ArrowRight, Clock, Inbox, WifiOff, RefreshCw } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { GovernanceBadge } from "@/components/governance-badge";
import {
  getAllCachedReports,
  checkHealth,
  getBackendCacheStatus,
  getCachedAnalysis,
  type LiveReport,
} from "@/lib/api-client";

function formatTs(iso: string) {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

interface HistoryRow {
  timestamp: string;
  user: string;
  action: string;
  resultingStatus: string;
  companyId: string;
  companyName: string;
  alertId: string;
  riskScore: number;
}

function buildRows(reports: LiveReport[]) {
  const entries: HistoryRow[] = [];

  for (const r of reports) {
    if (!r.governance?.audit_trail) continue;
    for (const entry of r.governance.audit_trail) {
      entries.push({
        timestamp:       entry.timestamp,
        user:            entry.user,
        action:          entry.action,
        resultingStatus: entry.resulting_status,
        companyId:       r.id,
        companyName:     r.client.legal_name,
        alertId:         r.governance.alert_id,
        riskScore:       r.governance.risk_score,
      });
    }
  }

  entries.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  return entries;
}

export default function AuditHistory() {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  const loadData = useCallback(async () => {
    const online = await checkHealth();
    setBackendOnline(online);

    let reports = getAllCachedReports();
    if (online) {
      try {
        const cache = await getBackendCacheStatus();
        const backendReports = (
          await Promise.all(
            cache.cached_ids.map((id) =>
              getCachedAnalysis(Number(id)).catch(() => null)
            )
          )
        ).filter((report): report is LiveReport => report !== null);
        if (backendReports.length > 0) {
          reports = backendReports;
        }
      } catch {
        // Keep the session cache fallback if the backend cache endpoint is unavailable.
      }
    }

    setRows(buildRows(reports));
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadData();
  }, [loadData]);

  return (
    <div className="px-8 py-8">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-200">Audit History</h1>
          <p className="mt-1 text-sm text-slate-500">
            Immutable four-eyes governance trail — all compliance actions recorded
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-200 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {backendOnline === false && (
        <div className="mb-6 rounded-lg border border-rose-500/20 bg-rose-500/10 px-5 py-4 flex items-center gap-3">
          <WifiOff className="h-5 w-5 shrink-0 text-rose-400" />
          <p className="text-sm text-rose-300">
            Engine offline — start the server to run analyses and generate audit trails.
          </p>
        </div>
      )}

      {rows.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 flex flex-col items-center justify-center py-20 gap-4">
          <Inbox className="h-12 w-12 opacity-20 text-slate-500" />
          <div className="text-center">
            <p className="text-base font-medium text-slate-400">No audit entries yet</p>
            <p className="mt-1 text-sm text-slate-500">
              Run analyses from the{" "}
              <Link href="/" className="underline underline-offset-2 text-slate-400 hover:text-slate-200">
                Control Room
              </Link>{" "}
              to populate the audit trail.
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-slate-800 bg-slate-900 shadow-none overflow-hidden">
          <div className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-slate-500" />
              <span className="text-sm font-semibold text-slate-200">Compliance Audit Trail</span>
            </div>
            <span className="font-mono text-xs text-slate-500">{rows.length} entries from {getAllCachedReports().length} analyses</span>
          </div>

          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent border-b border-slate-800">
                {["Timestamp", "Entity", "Alert", "Risk Score", "Actor", "Action Taken", "Resulting Status", ""].map((h) => (
                  <TableHead key={h} className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    {h}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, i) => {
                return (
                  <TableRow key={i} className="border-b border-slate-800 hover:bg-slate-800/50">
                    <TableCell className="font-mono text-xs text-slate-500 tabular-nums whitespace-nowrap">
                      {formatTs(row.timestamp)}
                    </TableCell>
                    <TableCell>
                      <p className="text-sm font-medium text-slate-200">{row.companyName}</p>
                      <p className="font-mono text-xs text-slate-500">#{row.companyId.padStart(3, "0")}</p>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-slate-500">{row.alertId}</TableCell>
                    <TableCell>
                      <span className={`font-mono text-sm font-bold tabular-nums ${
                        row.riskScore >= 0.75 ? "text-rose-400"
                        : row.riskScore >= 0.5 ? "text-amber-400"
                        : "text-emerald-400"
                      }`}>
                        {(row.riskScore * 100).toFixed(0)}%
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-slate-400">{row.user}</TableCell>
                    <TableCell className="text-sm text-slate-300 max-w-xs leading-snug">{row.action}</TableCell>
                    <TableCell>
                      <GovernanceBadge status={row.resultingStatus} />
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/client/${row.companyId}`}
                        className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-200 transition-colors"
                      >
                        Dossier <ArrowRight className="h-3 w-3" />
                      </Link>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
