import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  accent?: "red" | "amber" | "emerald" | "slate";
}

const ACCENT_MAP = {
  red: {
    icon: "text-rose-400",
    bg:   "bg-rose-500/10",
    border: "border-rose-500/20",
    value: "text-rose-400",
  },
  amber: {
    icon: "text-amber-400",
    bg:   "bg-amber-500/10",
    border: "border-amber-500/20",
    value: "text-amber-400",
  },
  emerald: {
    icon: "text-emerald-400",
    bg:   "bg-emerald-500/10",
    border: "border-emerald-500/20",
    value: "text-emerald-400",
  },
  slate: {
    icon: "text-slate-400",
    bg:   "bg-slate-800",
    border: "border-slate-800",
    value: "text-slate-200",
  },
};

export function KpiCard({
  title,
  value,
  subtitle,
  icon: Icon,
  accent = "slate",
}: KpiCardProps) {
  const colors = ACCENT_MAP[accent];
  return (
    <Card className={cn("border shadow-none bg-slate-900", colors.border)}>
      <CardContent className="flex items-start gap-4 p-5">
        <div className={cn("rounded-lg p-2.5", colors.bg)}>
          <Icon className={cn("h-5 w-5", colors.icon)} strokeWidth={1.75} />
        </div>
        <div className="flex flex-col gap-0.5">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">
            {title}
          </p>
          <p className={cn("text-2xl font-semibold tabular-nums", colors.value)}>
            {value}
          </p>
          {subtitle && (
            <p className="text-xs text-slate-500">{subtitle}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
