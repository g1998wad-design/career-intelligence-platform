import { CheckCircle2, XCircle, AlertTriangle, MinusCircle } from "lucide-react";
import type { RuleStatus } from "@/types/project";

const STATUS_CONFIG: Record<
  RuleStatus,
  { icon: typeof CheckCircle2; className: string }
> = {
  PASS: { icon: CheckCircle2, className: "text-accent-green border-accent-green/40 bg-accent-green/10" },
  FAIL: { icon: XCircle, className: "text-[#ff8a8a] border-[#ff8a8a]/40 bg-[#ff8a8a]/10" },
  REVIEW: { icon: AlertTriangle, className: "text-accent-orange border-accent-orange/40 bg-accent-orange/10" },
  EXCLUDED: { icon: MinusCircle, className: "text-muted border-border bg-surface" },
};

export default function StatusChip({ status }: { status: RuleStatus }) {
  const { icon: Icon, className } = STATUS_CONFIG[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold tracking-wide ${className}`}
    >
      <Icon aria-hidden="true" size={14} />
      {status}
    </span>
  );
}
