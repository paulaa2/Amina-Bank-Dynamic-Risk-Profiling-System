import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { GovernanceStatus } from "@/lib/mock-data";

const STATUS_CONFIG: Record<GovernanceStatus, { label: string; className: string }> = {
  DETECTED: {
    label: "Detected",
    className: "border-rose-500/20 bg-rose-500/10 text-rose-400",
  },
  UNDER_REVIEW: {
    label: "Under Review",
    className: "border-amber-500/20 bg-amber-500/10 text-amber-400",
  },
  FOUR_EYES_PENDING: {
    label: "Four-Eyes Pending",
    className: "border-violet-500/20 bg-violet-500/10 text-violet-400",
  },
  RESOLVED_MITIGATED: {
    label: "Resolved — Mitigated",
    className: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
  },
  ESCALATED_TO_REGULATOR: {
    label: "Escalated",
    className: "border-slate-700 bg-slate-800 text-slate-400",
  },
};

export function GovernanceBadge({
  status,
  className,
}: {
  status: GovernanceStatus | string;
  className?: string;
}) {
  const cfg =
    STATUS_CONFIG[status as GovernanceStatus] ?? {
      label: status,
      className: "border-slate-700 bg-slate-800 text-slate-400",
    };
  return (
    <Badge
      variant="outline"
      className={cn("text-xs font-medium", cfg.className, className)}
    >
      {cfg.label}
    </Badge>
  );
}
