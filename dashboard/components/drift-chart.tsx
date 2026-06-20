"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { DriftPoint } from "@/lib/mock-data";

interface DriftChartProps {
  data: DriftPoint[];
}

interface TooltipPayload {
  active?: boolean;
  payload?: Array<{ dataKey: string; value: number }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: TooltipPayload) {
  if (!active || !payload?.length) return null;
  const score = payload.find((p) => p.dataKey === "driftScore")?.value ?? 0;
  return (
    <div
      className="rounded-lg border border-slate-700 px-3 py-2 text-xs"
      style={{ backgroundColor: "#0f172a" }}
    >
      <p className="mb-1 font-medium text-slate-300">{label}</p>
      <p className="text-slate-400">
        Drift Score:{" "}
        <span className="font-semibold text-slate-200">{score.toFixed(3)}</span>
      </p>
    </div>
  );
}

export function DriftChart({ data }: DriftChartProps) {
  const threshold = data[0]?.threshold ?? 0.5;

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart
        data={data}
        margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
      >
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="#334155"
          vertical={false}
        />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: "#64748b" }}
          tickLine={false}
          axisLine={false}
          interval={6}
        />
        <YAxis
          domain={[0, 1]}
          tick={{ fontSize: 10, fill: "#64748b" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => v.toFixed(1)}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine
          y={threshold}
          stroke="#d97706"
          strokeDasharray="4 3"
          strokeWidth={1.5}
          label={{
            value: "Alarm threshold",
            position: "right",
            fontSize: 9,
            fill: "#d97706",
          }}
        />
        <Line
          type="monotone"
          dataKey="driftScore"
          stroke="#94a3b8"
          strokeWidth={1.75}
          dot={false}
          activeDot={{ r: 3, fill: "#e2e8f0" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
