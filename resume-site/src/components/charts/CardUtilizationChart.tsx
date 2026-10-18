"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { syntheticDataLabel } from "@/content/site";

// Utilization ratio computed directly from the synthetic monthly card summary
// rows in the case study (total_spend / credit_limit). No cardholders or
// values beyond that table are introduced here.
const data = [
  { cardholder: "CARDHOLDER-001", utilization: Math.round((4280.15 / 10000) * 1000) / 10 },
  { cardholder: "CARDHOLDER-002", utilization: Math.round((4875.9 / 5000) * 1000) / 10 },
  { cardholder: "CARDHOLDER-003", utilization: Math.round((980 / 15000) * 1000) / 10 },
];

export default function CardUtilizationChart() {
  return (
    <figure className="space-y-2 rounded-lg border border-border bg-surface p-4">
      <figcaption className="px-2 text-sm font-medium text-text">
        Utilization ratio by cardholder{" "}
        <span className="font-normal text-muted">({syntheticDataLabel})</span>
      </figcaption>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
            <XAxis dataKey="cardholder" stroke="#9fb0c5" fontSize={12} tickLine={false} />
            <YAxis
              stroke="#9fb0c5"
              fontSize={12}
              tickLine={false}
              unit="%"
              domain={[0, 100]}
            />
            <Tooltip
              contentStyle={{ background: "#0d1b2e", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
              labelStyle={{ color: "#f5f7fb" }}
              formatter={(value) => [`${value}%`, "Utilization"]}
            />
            <ReferenceLine
              y={90}
              stroke="#f4a261"
              strokeDasharray="4 4"
              label={{ value: "Review threshold (90%)", position: "insideTopRight", fill: "#f4a261", fontSize: 11 }}
            />
            <Bar dataKey="utilization" name="Utilization" fill="#5b8cff" radius={4} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="px-2 text-xs text-muted">
        CARDHOLDER-002 crosses the configured review threshold and would surface as a review candidate.
      </p>
    </figure>
  );
}
