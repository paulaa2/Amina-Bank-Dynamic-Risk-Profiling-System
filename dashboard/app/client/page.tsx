"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Building2,
  Flag,
  AlertTriangle,
  Search,
  X,
  Loader2,
  WifiOff,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { AlertBadge } from "@/components/alert-badge";
import {
  listCompanies,
  getCachedReport,
  checkHealth,
  type CompanyListItem,
  type LiveReport,
} from "@/lib/api-client";
import { alertLevelFor } from "@/lib/build-from-api";
import { cn } from "@/lib/utils";

function riskColor(pct: number) {
  if (pct >= 75) return "text-rose-400";
  if (pct >= 50) return "text-amber-400";
  return "text-emerald-400";
}

export default function ClientDossiers() {
  const [query, setQuery] = useState("");
  const [companies, setCompanies] = useState<CompanyListItem[]>([]);
  const [cachedReports, setCachedReports] = useState<Record<number, LiveReport>>({});
  const [loading, setLoading] = useState(true);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => {
      const online = await checkHealth();
      setBackendOnline(online);
      if (!online) { setLoading(false); return; }

      try {
        const list = await listCompanies();
        const sorted = [...list].sort((a, b) =>
          a.legal_name.localeCompare(b.legal_name)
        );
        setCompanies(sorted);

        // Pick up any reports already analyzed in this session
        const cached: Record<number, LiveReport> = {};
        for (const c of sorted) {
          const r = getCachedReport(c.id);
          if (r) cached[c.id] = r;
        }
        setCachedReports(cached);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return companies;
    return companies.filter((c) => c.legal_name.toLowerCase().includes(q));
  }, [query, companies]);

  return (
    <div className="px-8 py-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-200">Client Dossiers</h1>
        <p className="mt-1 text-sm text-slate-500">
          {companies.length > 0
            ? `${companies.length} entities in the pKYC database — open a dossier to run a live analysis`
            : "Loading entity registry…"}
        </p>
      </div>

      {/* Offline notice */}
      {backendOnline === false && (
        <div className="mb-6 rounded-lg border border-rose-500/20 bg-rose-500/10 px-5 py-4 flex items-center gap-3">
          <WifiOff className="h-5 w-5 shrink-0 text-rose-400" />
          <p className="text-sm text-rose-300">
            Engine offline — start the server:{" "}
            <code className="font-mono text-xs bg-rose-500/10 border border-rose-500/20 px-1.5 py-0.5 rounded text-rose-300">
              uvicorn src.api:app --reload --port 8000
            </code>
          </p>
        </div>
      )}

      {/* Search */}
      <div className="relative mb-6">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
        <Input
          type="text"
          placeholder="Search companies…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-10 pr-10 h-10 text-sm border-slate-800 bg-slate-900 text-slate-200 placeholder:text-slate-600 focus:border-slate-700"
        />
        {query && (
          <button
            onClick={() => setQuery("")}
            className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {query && (
        <p className="mb-4 text-sm text-slate-500">
          {filtered.length === 0
            ? "No companies match your search."
            : `Showing ${filtered.length} of ${companies.length} companies`}
        </p>
      )}

      {/* List */}
      <div className="flex flex-col gap-3">
        {loading && (
          <div className="flex items-center justify-center gap-2 py-20 text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-sm">Connecting to pKYC engine…</span>
          </div>
        )}

        {!loading &&
          filtered.map((company) => {
            const report = cachedReports[company.id];
            const riskPct = report
              ? Math.round(report.decision.max_combined_risk * 100)
              : null;
            const level = riskPct !== null ? alertLevelFor(riskPct / 100) : null;

            return (
              <Card
                key={company.id}
                className="w-full border-slate-800 bg-slate-900 shadow-none hover:border-slate-700 transition-colors"
              >
                <CardContent className="p-0">
                  <div className="flex items-center gap-5 px-6 py-5">
                    {/* Icon */}
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-800 border border-slate-700">
                      <Building2 className="h-5 w-5 text-slate-400" strokeWidth={1.75} />
                    </div>

                    {/* Left: identity */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2.5 mb-0.5">
                        <h2 className="text-xl font-bold text-slate-200 leading-tight truncate">
                          {company.legal_name}
                        </h2>
                        <span className="font-mono text-xs text-slate-500 shrink-0">
                          #{String(company.id).padStart(3, "0")}
                        </span>
                      </div>
                      {report ? (
                        <p className="text-base text-slate-400 leading-snug line-clamp-1 mb-2">
                          {report.client.expected_business_model}
                        </p>
                      ) : (
                        <p className="text-sm text-slate-600 italic mb-2">
                          Open dossier to run analysis
                        </p>
                      )}
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="flex items-center gap-1 text-sm text-slate-500">
                          <Flag className="h-3.5 w-3.5 text-slate-600" />
                          {report?.client.jurisdiction ?? company.country}
                        </span>
                        <Separator orientation="vertical" className="h-4 bg-slate-700" />
                        <span className="text-sm text-slate-500">{company.country}</span>
                        {report && report.warnings.length > 0 && (
                          <>
                            <Separator orientation="vertical" className="h-4 bg-slate-700" />
                            <span className="flex items-center gap-1 text-sm font-medium text-amber-400">
                              <AlertTriangle className="h-3.5 w-3.5" />
                              {report.warnings.length} warning
                              {report.warnings.length > 1 ? "s" : ""}
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Right: risk % + badge + button */}
                    <div className="flex items-center gap-4 shrink-0">
                      {riskPct !== null ? (
                        <div className="text-right">
                          <p className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-0.5">
                            Current Risk
                          </p>
                          <p className={cn("text-2xl font-bold tabular-nums leading-none font-mono", riskColor(riskPct))}>
                            {riskPct}%
                          </p>
                        </div>
                      ) : (
                        <div className="text-right">
                          <p className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-0.5">
                            Baseline Risk
                          </p>
                          <Badge
                            variant="outline"
                            className="text-xs border-slate-700 text-slate-400 bg-slate-800"
                          >
                            {company.baseline_risk_rating}
                          </Badge>
                        </div>
                      )}

                      {level !== null && report?.decision.alarm_fired ? (
                        <AlertBadge level={level} />
                      ) : riskPct !== null ? (
                        <Badge
                          variant="outline"
                          className="border-emerald-500/20 bg-emerald-500/10 text-emerald-400 text-xs"
                        >
                          ✓ Clear
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="border-slate-700 text-slate-500 bg-slate-800 text-xs">
                          Not analyzed
                        </Badge>
                      )}

                      <Separator orientation="vertical" className="h-8 bg-slate-700" />

                      <Link
                        href={`/client/${company.id}`}
                        className={buttonVariants({
                          size: "sm",
                          variant: "outline",
                          className:
                            "gap-1.5 border-slate-700 bg-slate-800 text-sm font-medium text-slate-200 hover:bg-slate-700 hover:border-slate-600 transition-colors",
                        })}
                      >
                        Open Dossier
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}

        {!loading && filtered.length === 0 && query && (
          <div className="flex flex-col items-center gap-3 py-20 text-slate-500">
            <Search className="h-10 w-10 opacity-25" />
            <p className="text-base font-medium text-slate-400">
              No results for &ldquo;{query}&rdquo;
            </p>
            <button
              onClick={() => setQuery("")}
              className="text-sm underline underline-offset-2 hover:text-slate-200"
            >
              Clear search
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
