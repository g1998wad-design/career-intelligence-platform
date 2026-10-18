import type { ReactNode } from "react";

export default function CaseStudySection({
  id,
  heading,
  kicker,
  children,
}: {
  id?: string;
  heading: string;
  kicker?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="space-y-5 border-t border-border/60 py-10 first:border-t-0 first:pt-0">
      <div>
        {kicker && (
          <p className="text-xs font-semibold uppercase tracking-widest text-accent-cyan">{kicker}</p>
        )}
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-text">{heading}</h2>
      </div>
      <div className="space-y-4 text-[15px] leading-relaxed text-muted">{children}</div>
    </section>
  );
}
