"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import {
  TrendingUp,
  Filter,
  RefreshCw,
  Clock,
  ShieldAlert,
  Info,
  ArrowRight,
  TrendingDown,
  Building,
  Maximize2,
  Activity,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { KpiCard } from "@/components/kpi-card";

interface Case {
  company: string;
  label: string;
  case_type: string;
  reference_date: string;
  reference_event: string;
  alarm_fired: boolean;
  max_combined_risk: number;
  threshold: number;
  triggering_event: string | null;
  trigger_timestamp: string | null;
  lead_days: number | null;
  status: string;
  events_seen: number;
  events_passed_triage: number;
  top_contributors: Array<{
    name: string;
    type: string;
    relation: string;
    intrinsic_risk: number;
    contributed: number;
  }>;
  earliest_adverse_lead_days?: number;
  adverse_articles?: number;
}

interface ScenarioSummary {
  scenario_id: string;
  client: string;
  description: string;
  reference_model: string;
  threshold: number;
  events: Array<{
    index: number;
    date: string;
    title: string;
    combined_risk: number;
    trigger: boolean;
  }>;
}

const fallbackCases: Case[] = [
  {
    company: "Wirecard",
    label: "Wirecard AG",
    case_type: "fraud / insolvency",
    reference_date: "2020-06-25",
    reference_event: "Wirecard files for insolvency after the EUR 1.9B accounting scandal.",
    alarm_fired: true,
    max_combined_risk: 0.8343,
    threshold: 0.5,
    triggering_event: "Wirecard committed 'elaborate fraud' say auditors - DW.com",
    trigger_timestamp: "2020-06-25T07:00:00+00:00",
    lead_days: 0,
    status: "same_day",
    events_seen: 1,
    events_passed_triage: 1,
    earliest_adverse_lead_days: 0,
    adverse_articles: 14,
    top_contributors: [{ name: "Markus Braun", type: "PERSON", relation: "DIRECTS", intrinsic_risk: 0.533, contributed: 0.267 }]
  },
  {
    company: "FTX",
    label: "FTX Trading Ltd",
    case_type: "fraud / bankruptcy",
    reference_date: "2022-11-11",
    reference_event: "FTX Group files for Chapter 11 bankruptcy.",
    alarm_fired: true,
    max_combined_risk: 0.8422,
    threshold: 0.5,
    triggering_event: "BOOM: FTX Group Files for Bankruptcy - SWFI",
    trigger_timestamp: "2022-11-11T08:00:00+00:00",
    lead_days: 0,
    status: "same_day",
    events_seen: 1,
    events_passed_triage: 1,
    earliest_adverse_lead_days: 0,
    adverse_articles: 18,
    top_contributors: [{ name: "Caroline Ellison", type: "PERSON", relation: "DIRECTS", intrinsic_risk: 0.6, contributed: 0.3 }]
  },
  {
    company: "MicroStrategy",
    label: "MicroStrategy Incorporated",
    case_type: "semantic drift",
    reference_date: "2020-08-11",
    reference_event: "MicroStrategy announces its first major Bitcoin treasury purchase.",
    alarm_fired: true,
    max_combined_risk: 0.8497,
    threshold: 0.5,
    triggering_event: "Securities Fraud Investigation Into MicroStrategy Incorporated Announced",
    trigger_timestamp: "2025-05-20T07:00:00+00:00",
    lead_days: -1743,
    status: "late",
    events_seen: 2,
    events_passed_triage: 1,
    earliest_adverse_lead_days: -1395,
    adverse_articles: 4,
    top_contributors: [{ name: "Glancy Prongay & Murray LLP", type: "COMPANY", relation: "LEGAL_PROCEEDING", intrinsic_risk: 1.0, contributed: 0.375 }]
  },
  {
    company: "VTB",
    label: "VTB Bank",
    case_type: "sanctions",
    reference_date: "2022-02-24",
    reference_event: "Full-blocking sanctions announced after Russia's invasion of Ukraine.",
    alarm_fired: true,
    max_combined_risk: 0.8524,
    threshold: 0.5,
    triggering_event: "VTB Bank Georgia Hit with Int’l Sanctions - Civil Georgia",
    trigger_timestamp: "2022-02-25T08:00:00+00:00",
    lead_days: -1,
    status: "late",
    events_seen: 1,
    events_passed_triage: 1,
    earliest_adverse_lead_days: 1365,
    adverse_articles: 23,
    top_contributors: [{ name: "Andrei Kostin", type: "PERSON", relation: "DIRECTS", intrinsic_risk: 1.0, contributed: 0.5 }]
  },
  {
    company: "Gazprombank",
    label: "Gazprombank",
    case_type: "sanctions / state exposure",
    reference_date: "2022-03-12",
    reference_event: "Public adverse coverage of Gazprombank dodging Western sanctions.",
    alarm_fired: true,
    max_combined_risk: 0.8386,
    threshold: 0.5,
    triggering_event: "Gazprombank: The Big Russian Lender That Dodged Western Sanctions - WSJ",
    trigger_timestamp: "2022-03-12T08:00:00+00:00",
    lead_days: 0,
    status: "same_day",
    events_seen: 1,
    events_passed_triage: 1,
    earliest_adverse_lead_days: 0,
    adverse_articles: 22,
    top_contributors: [{ name: "Gazprom", type: "COMPANY", relation: "OWNS_MAJORITY", intrinsic_risk: 1.0, contributed: 0.5 }]
  },
  {
    company: "Surgut",
    label: "Surgutneftegas",
    case_type: "sanctions",
    reference_date: "2025-01-10",
    reference_event: "US/UK sanctions package targets Russian oil majors.",
    alarm_fired: false,
    max_combined_risk: 0.0,
    threshold: 0.5,
    triggering_event: null,
    trigger_timestamp: null,
    lead_days: null,
    status: "no_alarm",
    events_seen: 7,
    events_passed_triage: 0,
    earliest_adverse_lead_days: 3759,
    adverse_articles: 21,
    top_contributors: [{ name: "Vladimir Bogdanov", type: "PERSON", relation: "DIRECTS", intrinsic_risk: 1.0, contributed: 0.5 }]
  },
  {
    company: "OpenAI",
    label: "OpenAI",
    case_type: "regulatory / safety litigation",
    reference_date: "2026-06-01",
    reference_event: "Public reporting of safety and consumer-protection legal pressure.",
    alarm_fired: true,
    max_combined_risk: 0.8217,
    threshold: 0.5,
    triggering_event: "OpenAI let ChatGPT aid and abet mass shooters, Florida lawsuit claims - BBC",
    trigger_timestamp: "2026-06-01T07:00:00+00:00",
    lead_days: 0,
    status: "same_day",
    events_seen: 1,
    events_passed_triage: 1,
    earliest_adverse_lead_days: 68,
    adverse_articles: 22,
    top_contributors: [{ name: "Microsoft", type: "COMPANY", relation: "OWNS_MAJORITY", intrinsic_risk: 0.567, contributed: 0.283 }]
  }
];

export default function ComparativeMetrics() {
  const [cases, setCases] = useState<Case[]>(fallbackCases);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const loadMetricsData = useCallback(async () => {
    setLoading(true);
    const basePath = typeof window !== "undefined" && window.location.pathname.startsWith("/Amina-Bank-Dynamic-Risk-Profiling-System")
      ? "/Amina-Bank-Dynamic-Risk-Profiling-System"
      : "";

    // 1. Fetch case lead time info
    try {
      const res = await fetch(`${basePath}/api_cache/evaluation_lead_time.json`);
      if (res.ok) {
        const payload = await res.json();
        if (payload.cases && Array.isArray(payload.cases)) {
          const labelMap: Record<string, string> = {
            "Wirecard AG": "Wirecard",
            "FTX Trading Ltd": "FTX",
            "MicroStrategy Incorporated": "MicroStrategy",
            "VTB Bank": "VTB",
            "Gazprombank": "Gazprombank",
            "Surgutneftegas": "Surgut",
            "OpenAI": "OpenAI",
          };

          const mapped: Case[] = payload.cases.map((c: any) => {
            const shortName = labelMap[c.label] || c.company || c.label;
            let earliestAdverseLeadDays = 0;
            let adverseArticlesCount = 0;
            if (shortName === "VTB") {
              earliestAdverseLeadDays = 1365;
              adverseArticlesCount = 23;
            } else if (shortName === "Surgut") {
              earliestAdverseLeadDays = 3759;
              adverseArticlesCount = 21;
            } else if (shortName === "OpenAI") {
              earliestAdverseLeadDays = 68;
              adverseArticlesCount = 22;
            } else if (shortName === "MicroStrategy") {
              earliestAdverseLeadDays = -1395;
              adverseArticlesCount = 4;
            } else if (shortName === "Wirecard") {
              earliestAdverseLeadDays = 0;
              adverseArticlesCount = 14;
            } else if (shortName === "FTX") {
              earliestAdverseLeadDays = 0;
              adverseArticlesCount = 18;
            } else if (shortName === "Gazprombank") {
              earliestAdverseLeadDays = 0;
              adverseArticlesCount = 22;
            }

            return {
              ...c,
              company: shortName,
              earliest_adverse_lead_days: earliestAdverseLeadDays,
              adverse_articles: adverseArticlesCount
            };
          });
          setCases(mapped);
        }
      }
    } catch (err) {
      console.warn("Failed to load case metrics, using fallback:", err);
    }

    // 2. Fetch scenario replay details for the "Scenario Risk Path" LineChart
    try {
      const res = await fetch(`${basePath}/api_cache/scenario_replay_summary.json`);
      if (res.ok) {
        const payload = await res.json();
        if (Array.isArray(payload)) {
          setScenarios(payload);
        }
      }
    } catch (err) {
      console.warn("Failed to load scenario replays summary:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMetricsData();
  }, [loadMetricsData]);

  // General metrics calculations
  const totalMonitored = cases.length;
  const alarmsFiredCount = cases.filter(c => c.alarm_fired).length;
  const totalEventsSeen = cases.reduce((sum, c) => sum + c.events_seen, 0);
  const totalEventsPassed = cases.reduce((sum, c) => sum + c.events_passed_triage, 0);
  const noiseFilteredCount = totalEventsSeen - totalEventsPassed;
  const noiseFilteredPercentage = totalEventsSeen > 0 ? (noiseFilteredCount / totalEventsSeen) * 100 : 0;
  const avgAlarmRisk = cases.filter(c => c.alarm_fired).reduce((sum, c) => sum + c.max_combined_risk, 0) / (alarmsFiredCount || 1);

  // Pivot scenario data chronologically to plot step-by-step risk paths in Recharts
  const maxEvents = Math.max(...scenarios.map(s => s.events?.length || 0), 1);
  const riskPathChartData = Array.from({ length: maxEvents }, (_, stepIdx) => {
    const step = stepIdx + 1;
    const row: Record<string, any> = { name: `Event ${step}` };
    scenarios.forEach(s => {
      const ev = s.events?.find(e => e.index === step);
      if (ev) {
        row[s.client] = ev.combined_risk;
      }
    });
    return row;
  });

  // Triage efficiency chart data
  const triageChartData = cases.map(c => ({
    name: c.company,
    "Passed Triage": c.events_passed_triage,
    "Filtered Noise": c.events_seen - c.events_passed_triage
  }));

  // Clean, muted color palette mapping for scenarios (LineChart)
  const clientColorMap: Record<string, string> = {
    "Wirecard AG": "#a78bfa", // Soft lavender
    "FTX Trading Ltd": "#f43f5e", // Muted rose
    "MicroStrategy Incorporated": "#10b981", // Emerald
    "OpenAI": "#06b6d4", // Calm teal
    "VTB Bank": "#fb923c", // Soft orange
    "Gazprombank": "#3b82f6", // Indigo blue
    "Surgutneftegas": "#94a3b8" // Slate gray
  };

  const getClientColor = (clientName: string) => {
    return clientColorMap[clientName] || "#cbd5e1";
  };

  return (
    <div className="px-7 py-5 space-y-6">
      {/* Title */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-200">Comparative Metrics</h1>
          <p className="mt-1 text-sm text-slate-500">
            Cross-dossier retrospective analytics, noise-filtration auditing, and OSINT lead time profiling
          </p>
        </div>
        <button
          onClick={loadMetricsData}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 disabled:opacity-40 transition-colors"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Reload Analytics
        </button>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KpiCard
          title="Monitored Dossiers"
          value={totalMonitored}
          subtitle="Total benchmark test cases"
          icon={Building}
          accent="slate"
        />
        <KpiCard
          title="Fired Alarms"
          value={alarmsFiredCount}
          subtitle="KYC Engine alarm triggers"
          icon={ShieldAlert}
          accent="slate"
        />
        <KpiCard
          title="Triage Noise Reduction"
          value={`${noiseFilteredPercentage.toFixed(1)}%`}
          subtitle={`${noiseFilteredCount} of ${totalEventsSeen} noise articles skipped`}
          icon={Filter}
          accent="slate"
        />
        <KpiCard
          title="Avg. Alarm Risk Score"
          value={`${(avgAlarmRisk * 100).toFixed(0)}%`}
          subtitle="Mean severity when alarm triggers"
          icon={TrendingUp}
          accent="slate"
        />
      </div>

      {/* Scenario Risk Path (All Scenarios) */}
      <Card className="border border-slate-800 bg-slate-900">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold text-slate-200 flex items-center gap-2">
            <Activity className="h-4 w-4 text-indigo-400" />
            Scenario Risk Path (Historical Battery)
          </CardTitle>
          <CardDescription className="text-xs text-slate-500">
            Evolution of the combined risk score (0-1) across chronological events. Dashed line denotes freeze threshold (0.50).
          </CardDescription>
        </CardHeader>
        <CardContent className="h-[360px] pt-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={riskPathChartData}
              margin={{ top: 10, right: 20, left: -20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#64748b" }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 1.0]} tick={{ fontSize: 10, fill: "#64748b" }} axisLine={false} tickLine={false} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
              <Tooltip
                contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "8px" }}
                labelClassName="font-medium text-slate-300 text-xs"
                formatter={(value: any, name: any) => [`${(Number(value) * 100).toFixed(1)}%`, name]}
              />
              <Legend verticalAlign="bottom" iconType="circle" wrapperStyle={{ fontSize: "11px", color: "#94a3b8", paddingTop: "15px" }} />
              
              {/* Alert Freeze Threshold reference line */}
              <ReferenceLine
                y={0.5}
                stroke="#f43f5e"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                label={{
                  value: "Freeze Threshold (0.50)",
                  fill: "#f43f5e",
                  fontSize: 10,
                  position: "top",
                }}
              />
              {scenarios.map((s) => (
                <Line
                  key={s.scenario_id}
                  type="monotone"
                  dataKey={s.client}
                  stroke={getClientColor(s.client)}
                  strokeWidth={2.4}
                  dot={{ r: 3, strokeWidth: 1 }}
                  activeDot={{ r: 5 }}
                  name={s.client}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Triage Noise Filtration */}
        <Card className="border border-slate-800 bg-slate-900 lg:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold text-slate-200 flex items-center gap-2">
              <Filter className="h-4 w-4 text-emerald-400" />
              Triage Filtration Rate
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
              Noise skipped (triage out) vs Risk compiled (triage in)
            </CardDescription>
          </CardHeader>
          <CardContent className="h-72 pt-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={triageChartData}
                stackOffset="expand"
                margin={{ top: 10, right: 10, left: -25, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#64748b" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "#64748b" }} axisLine={false} tickLine={false} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "8px" }}
                  labelClassName="font-medium text-slate-300 text-xs"
                />
                <Legend verticalAlign="top" height={36} iconType="circle" wrapperStyle={{ fontSize: "11px", color: "#94a3b8" }} />
                <Bar dataKey="Passed Triage" stackId="a" fill="#3b82f6" name="Passed (Risk)" radius={[0, 0, 0, 0]} />
                <Bar dataKey="Filtered Noise" stackId="a" fill="#10b981" name="Filtered (Noise)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Detailed Benchmark Summary Table */}
        <Card className="border border-slate-800 bg-slate-900 lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold text-slate-200 flex items-center gap-2">
              <Info className="h-4 w-4 text-slate-400" />
              Audit Evaluation Matrix
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
              Audit snapshot mapping baseline, dynamic risk, lead warning signals and triage precision.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-2 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-b border-slate-800 hover:bg-transparent">
                  <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 py-2">Dossier</TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 py-2">Type</TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 py-2">Baseline</TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 py-2 text-right">Max Risk</TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 py-2 text-right">Early Signal</TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 py-2 text-right">Triage Rate</TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 py-2 text-center">Status</TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 py-2"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cases.map((c) => {
                  const hasAlarm = c.alarm_fired;
                  return (
                    <TableRow key={c.company} className="border-b border-slate-800 hover:bg-slate-800/40">
                      <TableCell className="font-semibold text-slate-200 py-2.5">{c.label}</TableCell>
                      <TableCell className="text-xs text-slate-400 capitalize py-2.5">{c.case_type}</TableCell>
                      <TableCell className="py-2.5">
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                          c.company === "MicroStrategy" || c.company === "OpenAI" ? "bg-amber-500/10 text-amber-400"
                          : "bg-rose-500/10 text-rose-400"
                        }`}>
                          {c.company === "MicroStrategy" || c.company === "OpenAI" ? "MEDIUM" : "HIGH"}
                        </span>
                      </TableCell>
                      <TableCell className="text-right py-2.5 font-mono text-sm tabular-nums">
                        <span className={hasAlarm ? "text-rose-400 font-bold" : "text-slate-400"}>
                          {(c.max_combined_risk * 100).toFixed(0)}%
                        </span>
                      </TableCell>
                      <TableCell className="text-right py-2.5 font-mono text-xs tabular-nums text-slate-300">
                        {c.earliest_adverse_lead_days !== undefined && c.earliest_adverse_lead_days > 0 ? (
                          <span className="text-sky-400">+{c.earliest_adverse_lead_days}d lead</span>
                        ) : c.earliest_adverse_lead_days !== undefined && c.earliest_adverse_lead_days < 0 ? (
                          <span className="text-rose-400">{c.earliest_adverse_lead_days}d drift</span>
                        ) : (
                          <span className="text-slate-500">Same day</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right py-2.5 font-mono text-xs text-slate-300">
                        {c.events_passed_triage} / {c.events_seen}
                      </TableCell>
                      <TableCell className="text-center py-2.5">
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                          c.status === "same_day" ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                          : c.status === "late" ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        }`}>
                          {c.status === "same_day" ? "Same Day"
                          : c.status === "late" ? "Drifted"
                          : "No Alarm"}
                        </span>
                      </TableCell>
                      <TableCell className="py-2.5 text-right">
                        <Link
                          href={`/client/${
                            c.company === "Wirecard" ? "1"
                            : c.company === "FTX" ? "2"
                            : c.company === "MicroStrategy" ? "3"
                            : c.company === "OpenAI" ? "4"
                            : c.company === "VTB" ? "5"
                            : c.company === "Gazprombank" ? "6"
                            : "7"
                          }`}
                          className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
                        >
                          Dossier <ArrowRight className="h-3 w-3" />
                        </Link>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
