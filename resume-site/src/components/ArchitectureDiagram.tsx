import { ArrowDown } from "lucide-react";

export default function ArchitectureDiagram({ stages }: { stages: string[][] }) {
  const description = stages
    .map((stage) => stage.join(" and "))
    .join(", then ");

  return (
    <div className="rounded-lg border border-border bg-surface p-6">
      <p className="sr-only">Architecture flow: {description}.</p>
      <div aria-hidden="true" className="flex flex-col items-stretch gap-2">
        {stages.map((stage, i) => (
          <div key={i} className="flex flex-col items-center gap-2">
            <div className="flex w-full flex-wrap items-stretch justify-center gap-3">
              {stage.map((node) => (
                <div
                  key={node}
                  className="flex-1 min-w-[180px] rounded-md border border-border bg-surface-light px-4 py-3 text-center text-sm font-medium text-text"
                >
                  {node}
                </div>
              ))}
            </div>
            {i < stages.length - 1 && (
              <ArrowDown className="text-accent-blue" size={18} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
