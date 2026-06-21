"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LiveReport } from "@/lib/api-client";

interface ScenarioRiskPathProps {
  report: LiveReport;
  selectedIndex: number;
}

interface RiskPoint {
  step: number;
  label: string;
  risk: number;
  threshold: number;
}

interface TooltipPayload {
  active?: boolean;
  payload?: Array<{ dataKey: string; value: number; payload: RiskPoint }>;
}

function CustomTooltip({ active, payload }: TooltipPayload) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="border border-slate-700 bg-slate-950 px-3 py-2 text-xs">
      <p className="font-semibold text-slate-200">{point.label}</p>
      <p className="mt-1 text-slate-400">
        Combined risk:{" "}
        <span className="font-mono font-semibold text-slate-100">
          {Math.round(point.risk * 100)}%
        </span>
      </p>
    </div>
  );
}

export function ScenarioRiskPath({ report, selectedIndex }: ScenarioRiskPathProps) {
  const threshold = report.decision.threshold;
  const data: RiskPoint[] = [
    { step: 0, label: "Baseline", risk: 0, threshold },
    ...report.events.map((event, index) => ({
      step: index + 1,
      label: `Event ${index + 1}`,
      risk: event.combined_risk,
      threshold,
    })),
  ];
  const selectedStep = selectedIndex + 1;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 12, right: 18, left: -18, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 10, fill: "#64748b" }}
          tickLine={false}
          axisLine={false}
          interval={0}
        />
        <YAxis
          domain={[0, 1]}
          tick={{ fontSize: 10, fill: "#64748b" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(value) => `${Math.round(Number(value) * 100)}%`}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine
          y={0.5}
          stroke="#f43f5e"
          strokeDasharray="4 4"
          strokeWidth={1.5}
          label={{
            value: "Freeze Threshold (0.50)",
            fill: "#f43f5e",
            fontSize: 10,
            position: "top",
          }}
        />
        <ReferenceLine
          x={data[Math.max(0, selectedStep)]?.label}
          stroke="#a78bfa"
          strokeWidth={1.5}
        />
        <Line
          type="monotone"
          dataKey="risk"
          stroke="#a78bfa"
          strokeWidth={2.25}
          dot={({ cx, cy, payload }) => {
            const active = payload.step === selectedStep;
            return (
              <circle
                cx={cx}
                cy={cy}
                r={active ? 5 : 3}
                fill={active ? "#c4b5fd" : "#64748b"}
                stroke="#0f172a"
                strokeWidth={active ? 2 : 1}
              />
            );
          }}
          activeDot={{ r: 5, fill: "#ddd6fe", stroke: "#0f172a", strokeWidth: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
