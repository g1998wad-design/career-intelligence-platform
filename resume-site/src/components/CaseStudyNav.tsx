"use client";

import { useEffect, useState } from "react";

export type NavItem = { id: string; label: string };

export default function CaseStudyNav({ items }: { items: NavItem[] }) {
  const [activeId, setActiveId] = useState<string>(items[0]?.id ?? "");

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;

    const elements = items
      .map((item) => document.getElementById(item.id))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;

    const ratios = new Map<string, number>();

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          ratios.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0);
        });
        setActiveId((prev) => {
          let bestId = prev;
          let bestRatio = 0;
          ratios.forEach((ratio, id) => {
            if (ratio > bestRatio) {
              bestRatio = ratio;
              bestId = id;
            }
          });
          return bestRatio > 0 ? bestId : prev;
        });
      },
      { rootMargin: "-120px 0px -55% 0px", threshold: [0, 0.25, 0.5, 0.75, 1] }
    );

    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [items]);

  if (items.length === 0) return null;

  return (
    <>
      <div className="sticky top-16 z-40 -mx-6 border-b border-border/60 bg-bg/95 px-6 backdrop-blur-sm lg:hidden">
        <nav aria-label="Case study sections" className="flex gap-2 overflow-x-auto py-2.5">
          {items.map((item) => {
            const isActive = activeId === item.id;
            return (
              <a
                key={item.id}
                href={`#${item.id}`}
                aria-current={isActive ? "true" : undefined}
                className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors ${
                  isActive
                    ? "border-accent-blue/60 bg-accent-blue/10 text-text"
                    : "border-border text-muted hover:text-text"
                }`}
              >
                {item.label}
              </a>
            );
          })}
        </nav>
      </div>

      <nav aria-label="Case study sections" className="hidden lg:block">
        <div className="sticky top-24 space-y-1">
          {items.map((item) => {
            const isActive = activeId === item.id;
            return (
              <a
                key={item.id}
                href={`#${item.id}`}
                aria-current={isActive ? "true" : undefined}
                className={`block rounded-md border-l-2 px-3 py-1.5 text-sm transition-colors ${
                  isActive
                    ? "border-accent-blue font-medium text-text"
                    : "border-transparent text-muted hover:text-text"
                }`}
              >
                {item.label}
              </a>
            );
          })}
        </div>
      </nav>
    </>
  );
}
