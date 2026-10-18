import Link from "next/link";
import { ArrowRight } from "lucide-react";
import Container from "@/components/Container";
import ProjectCard from "@/components/ProjectCard";
import { hero, positioningStatement, professionalSummary, supportingStatement } from "@/content/site";
import { getFlagshipProjects, getSupportingProjects } from "@/lib/projects";

export default function Home() {
  const flagships = getFlagshipProjects();
  const supporting = getSupportingProjects();

  return (
    <>
      <Container className="pt-20 pb-16 sm:pt-28">
        <h1 className="max-w-3xl text-4xl font-bold tracking-tight text-text sm:text-5xl">
          {hero.headline}
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted">{hero.subheadline}</p>
        <div className="mt-8 flex flex-wrap gap-4">
          <Link
            href={hero.primaryCta.href}
            className="inline-flex items-center gap-2 rounded-full bg-accent-blue px-6 py-3 text-sm font-semibold text-bg transition-opacity hover:opacity-90"
          >
            {hero.primaryCta.label}
            <ArrowRight aria-hidden="true" size={16} />
          </Link>
          <Link
            href={hero.secondaryCta.href}
            className="inline-flex items-center gap-2 rounded-full border border-border px-6 py-3 text-sm font-semibold text-text transition-colors hover:border-accent-blue/60"
          >
            {hero.secondaryCta.label}
          </Link>
        </div>
      </Container>

      <Container className="py-10">
        <div className="grid gap-6 rounded-xl border border-border bg-surface p-8 sm:grid-cols-2">
          <p className="text-lg font-medium leading-relaxed text-text">{positioningStatement}</p>
          <div className="space-y-4 text-sm leading-relaxed text-muted">
            <p>{supportingStatement}</p>
            <p>{professionalSummary}</p>
          </div>
        </div>
      </Container>

      <Container className="py-10">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-accent-cyan">
          Flagship case studies
        </h2>
        <div className="mt-6 grid gap-6 md:grid-cols-3">
          {flagships.map((project) => (
            <ProjectCard key={project.slug} project={project} featured />
          ))}
        </div>
      </Container>

      <Container className="py-10">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-accent-cyan">
          Supporting projects
        </h2>
        <div className="mt-6 grid gap-6 md:grid-cols-3">
          {supporting.map((project) => (
            <ProjectCard key={project.slug} project={project} />
          ))}
        </div>
      </Container>

      <Container className="py-16">
        <div className="flex flex-col items-start justify-between gap-6 rounded-xl border border-border bg-surface p-8 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-xl font-semibold text-text">Want the full picture?</h2>
            <p className="mt-1 max-w-md text-sm text-muted">
              See how I approach discovery, data modeling, and governed automation across every project.
            </p>
          </div>
          <Link
            href="/work"
            className="inline-flex shrink-0 items-center gap-2 rounded-full border border-border px-6 py-3 text-sm font-semibold text-text transition-colors hover:border-accent-blue/60"
          >
            View all work
            <ArrowRight aria-hidden="true" size={16} />
          </Link>
        </div>
      </Container>
    </>
  );
}
