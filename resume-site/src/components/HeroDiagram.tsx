import { CheckCircle2, FileSpreadsheet, FileText, LayoutDashboard, Mail, User } from "lucide-react";
import type { CSSProperties } from "react";

const NODES = [
  { Icon: FileSpreadsheet, x: -120, y: -70, rotate: -18, delay: 0 },
  { Icon: FileText, x: 110, y: -90, rotate: 14, delay: 90 },
  { Icon: Mail, x: -130, y: 60, rotate: 10, delay: 180 },
  { Icon: LayoutDashboard, x: 120, y: 80, rotate: -12, delay: 270 },
  { Icon: User, x: 0, y: -120, rotate: 6, delay: 360 },
];

export default function HeroDiagram() {
  return (
    <div
      aria-hidden="true"
      className="relative mx-auto h-[220px] w-[220px] shrink-0 sm:h-[260px] sm:w-[260px]"
    >
      <div className="hero-hub absolute top-1/2 left-1/2 flex h-14 w-14 items-center justify-center rounded-2xl border border-accent-blue/40 bg-accent-blue/10">
        <CheckCircle2 className="text-accent-blue" size={24} />
      </div>
      {NODES.map(({ Icon, x, y, rotate, delay }, i) => (
        <div
          key={i}
          className="hero-node absolute top-1/2 left-1/2 flex h-11 w-11 items-center justify-center rounded-xl border border-border bg-surface-light"
          style={
            {
              "--fx": `${x}px`,
              "--fy": `${y}px`,
              "--frot": `${rotate}deg`,
              animationDelay: `${delay}ms`,
            } as CSSProperties
          }
        >
          <Icon className="text-muted" size={18} />
        </div>
      ))}
    </div>
  );
}
