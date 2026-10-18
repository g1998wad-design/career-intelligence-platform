import type { Metadata } from "next";
import Container from "@/components/Container";
import ProjectCard from "@/components/ProjectCard";
import { getFlagshipProjects, getSupportingProjects } from "@/lib/projects";

export const metadata: Metadata = {
  title: "Selected Work",
  description:
    "Case studies in AI-assisted financial audit automation, procurement workflow automation, ERP migration analytics, and enterprise BI — anonymized and reconstructed with synthetic data.",
};

export default function WorkPage() {
  const flagships = getFlagshipProjects();
  const supporting = getSupportingProjects();

  return (
    <Container className="py-16">
      <h1 className="text-3xl font-bold tracking-tight text-text sm:text-4xl">Selected Work</h1>
      <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted">
        Six case studies spanning applied AI, financial controls, data modeling, and enterprise
        analytics. The first three are flagship projects with full architecture, rule logic, and
        tradeoffs; the rest are shorter supporting work.
      </p>

      <h2 className="mt-12 text-sm font-semibold uppercase tracking-widest text-accent-cyan">
        Flagship case studies
      </h2>
      <div className="mt-6 grid gap-6 md:grid-cols-3">
        {flagships.map((project) => (
          <ProjectCard key={project.slug} project={project} featured />
        ))}
      </div>

      <h2 className="mt-14 text-sm font-semibold uppercase tracking-widest text-accent-cyan">
        Supporting projects
      </h2>
      <div className="mt-6 grid gap-6 md:grid-cols-3">
        {supporting.map((project) => (
          <ProjectCard key={project.slug} project={project} />
        ))}
      </div>
    </Container>
  );
}
