import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AlertLevel } from "@/lib/mock-data";

interface AlertBadgeProps {
  level: AlertLevel;
  className?: string;
}

const CONFIG: Record<AlertLevel, { label: string; className: string; dot: string }> = {
  Critical: {
    label: "Critical",
    className: "border-rose-500/20 bg-rose-500/10 text-rose-400 hover:bg-rose-500/10",
    dot: "bg-rose-400",
  },
  Medium: {
    label: "Medium",
    className: "border-amber-500/20 bg-amber-500/10 text-amber-400 hover:bg-amber-500/10",
    dot: "bg-amber-400",
  },
  Low: {
    label: "Low",
    className: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/10",
    dot: "bg-emerald-400",
  },
};

export function AlertBadge({ level, className }: AlertBadgeProps) {
  const cfg = CONFIG[level];
  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5 font-medium text-xs", cfg.className, className)}
    >
      <span className={cn("inline-block h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </Badge>
  );
}
