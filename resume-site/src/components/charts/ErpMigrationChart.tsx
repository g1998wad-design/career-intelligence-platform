"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { syntheticDataLabel } from "@/content/site";

// Aggregated directly from the synthetic activity_source rows in the case study
// (Business Unit A / May 2026, Business Unit B / May + June 2026). No months or
// values beyond that table are introduced here.
const data = [
  { period: "Unit A — May 2026", legacy: 18400, cloud: 24070, selected: "Cloud ERP" },
  { period: "Unit B — May 2026", legacy: 4880, cloud: 0, selected: "Legacy ERP" },
  { period: "Unit B — June 2026", legacy: 5015, cloud: 4920, selected: "Cloud ERP" },
];

export default function ErpMigrationChart() {
  return (
    <figure className="space-y-2 rounded-lg border border-border bg-surface p-4">
      <figcaption className="px-2 text-sm font-medium text-text">
        Legacy vs. cloud activity by business-unit/month{" "}
        <span className="font-normal text-muted">({syntheticDataLabel})</span>
      </figcaption>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
            <XAxis dataKey="period" stroke="#9fb0c5" fontSize={12} tickLine={false} />
            <YAxis stroke="#9fb0c5" fontSize={12} tickLine={false} />
            <Tooltip
              contentStyle={{ background: "#0d1b2e", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
              labelStyle={{ color: "#f5f7fb" }}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#9fb0c5" }} />
            <Bar dataKey="legacy" name="Legacy ERP" fill="#9fb0c5" radius={4} />
            <Bar dataKey="cloud" name="Cloud ERP" fill="#2dd4bf" radius={4} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="px-2 text-xs text-muted">
        Per the source-precedence rule, reporting uses Cloud ERP whenever it has data for that
        business-unit/month, and Legacy ERP only when Cloud ERP has none — shown above for Unit B, May 2026.
      </p>
    </figure>
  );
}
