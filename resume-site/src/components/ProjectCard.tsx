import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { Project } from "@/types/project";
import Tag from "./Tag";

export default function ProjectCard({
  project,
  featured = false,
}: {
  project: Project;
  featured?: boolean;
}) {
  return (
    <Link
      href={`/work/${project.slug}`}
      className={`group flex h-full flex-col justify-between rounded-xl border border-border bg-surface p-6 transition-colors hover:border-accent-blue/60 ${
        featured ? "md:p-8" : ""
      }`}
    >
      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-accent-cyan">
          {project.heroKicker}
        </p>
        <h3 className={`font-semibold tracking-tight text-text ${featured ? "text-2xl" : "text-lg"}`}>
          {project.title}
        </h3>
        <p className="text-sm leading-relaxed text-muted">{project.cardSummary}</p>
        <div className="flex flex-wrap gap-2 pt-1">
          {project.tags.slice(0, featured ? 6 : 4).map((tag) => (
            <Tag key={tag} label={tag} />
          ))}
        </div>
      </div>
      <div className="mt-6 flex items-center gap-1.5 text-sm font-medium text-accent-blue transition-transform group-hover:translate-x-1">
        View case study
        <ArrowRight aria-hidden="true" size={16} />
      </div>
    </Link>
  );
}
