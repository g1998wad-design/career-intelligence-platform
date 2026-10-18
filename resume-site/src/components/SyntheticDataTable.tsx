import type { SyntheticTable } from "@/types/project";
import { syntheticDataLabel } from "@/content/site";

export default function SyntheticDataTable({ caption, columns, rows }: SyntheticTable) {
  return (
    <figure className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[640px] border-collapse text-left text-sm">
          <caption className="bg-surface px-4 py-2 text-left text-sm font-medium text-text">
            {caption}
            <span className="ml-2 font-normal text-muted">({syntheticDataLabel})</span>
          </caption>
          <thead>
            <tr className="bg-surface-light">
              {columns.map((col) => (
                <th key={col} scope="col" className="whitespace-nowrap px-4 py-2 font-mono text-xs font-medium uppercase tracking-wide text-muted">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-t border-border">
                {row.map((cell, j) => (
                  <td key={j} className="whitespace-nowrap px-4 py-2 font-mono text-xs text-muted">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
