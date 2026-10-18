import type { Metadata } from "next";
import Container from "@/components/Container";
import Reveal from "@/components/Reveal";
import { aboutBody, aboutClosing, aboutHeading, aboutSkillAreas, approachCards } from "@/content/about";

export const metadata: Metadata = {
  title: "About",
  description:
    "How Gurkirat Singh approaches process discovery, data modeling, applied AI, and building systems people can trust.",
};

export default function AboutPage() {
  return (
    <Container className="py-16">
      <h1 className="max-w-2xl text-3xl font-bold tracking-tight text-text sm:text-4xl">
        {aboutHeading}
      </h1>
      <div className="mt-6 max-w-2xl space-y-4 text-lg leading-relaxed text-muted">
        {aboutBody.map((p) => (
          <p key={p}>{p}</p>
        ))}
      </div>

      <h2 className="mt-14 text-sm font-semibold uppercase tracking-widest text-accent-cyan">
        What I work with
      </h2>
      <ul className="mt-5 grid gap-3 sm:grid-cols-2">
        {aboutSkillAreas.map((item) => (
          <li
            key={item}
            className="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-muted"
          >
            {item}
          </li>
        ))}
      </ul>

      <p className="mt-10 max-w-2xl text-lg leading-relaxed text-text">{aboutClosing}</p>

      <h2 className="mt-14 text-sm font-semibold uppercase tracking-widest text-accent-cyan">
        How I approach a project
      </h2>
      <div className="mt-6 grid gap-5 sm:grid-cols-2">
        {approachCards.map((card) => (
          <Reveal key={card.title} className="h-full">
            <div className="h-full rounded-xl border border-border bg-surface p-6">
              <h3 className="text-base font-semibold text-text">{card.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{card.description}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </Container>
  );
}
