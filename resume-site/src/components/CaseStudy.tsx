import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { Project } from "@/types/project";
import { getAdjacentProject } from "@/lib/projects";
import Container from "./Container";
import Tag from "./Tag";
import CaseStudySection from "./CaseStudySection";
import ArchitectureDiagram from "./ArchitectureDiagram";
import CodeBlock from "./CodeBlock";
import SyntheticDataTable from "./SyntheticDataTable";
import StatusChip from "./StatusChip";
import ConfidentialityNote from "./ConfidentialityNote";
import ErpMigrationChart from "./charts/ErpMigrationChart";
import CardUtilizationChart from "./charts/CardUtilizationChart";

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-2 pl-5">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function NumberedSteps({ items }: { items: string[] }) {
  return (
    <ol className="space-y-2">
      {items.map((item, i) => (
        <li key={item} className="flex gap-3">
          <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-surface-light text-xs font-semibold text-accent-cyan">
            {i + 1}
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ol>
  );
}

export default function CaseStudy({ project }: { project: Project }) {
  const next = getAdjacentProject(project.slug);

  return (
    <article>
      <Container className="pt-14 pb-10">
        <p className="text-xs font-semibold uppercase tracking-widest text-accent-cyan">
          {project.heroKicker}
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-text sm:text-4xl">
          {project.title}
        </h1>
        <p className="mt-4 max-w-3xl text-lg leading-relaxed text-muted">
          {project.oneSentenceOverview}
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          {project.tags.map((tag) => (
            <Tag key={tag} label={tag} />
          ))}
        </div>
        {project.keyInsight && (
          <blockquote className="mt-8 border-l-2 border-accent-blue pl-5 text-lg italic leading-relaxed text-text">
            &ldquo;{project.keyInsight}&rdquo;
          </blockquote>
        )}
      </Container>

      <Container className="divide-y divide-border/60">
        <CaseStudySection heading="Executive summary" kicker="01">
          {project.executiveSummary.map((p) => (
            <p key={p}>{p}</p>
          ))}
        </CaseStudySection>

        <CaseStudySection heading={project.businessProblem.heading || "Business problem"} kicker="02">
          {project.businessProblem.body?.map((p) => <p key={p}>{p}</p>)}
          {project.businessProblem.bullets && <Bullets items={project.businessProblem.bullets} />}
        </CaseStudySection>

        {project.priorStateWorkflow && (
          <CaseStudySection heading="Prior-state workflow" kicker="03">
            <NumberedSteps items={project.priorStateWorkflow} />
          </CaseStudySection>
        )}

        {project.constraintsAndRisks && (
          <CaseStudySection heading="Constraints and risks" kicker="04">
            <Bullets items={project.constraintsAndRisks} />
          </CaseStudySection>
        )}

        <CaseStudySection heading="My role" kicker="05">
          <Bullets items={project.myRole} />
        </CaseStudySection>

        {project.discovery && (
          <CaseStudySection heading="Discovery and requirements" kicker="06">
            {project.discovery.map((p) => (
              <p key={p}>{p}</p>
            ))}
          </CaseStudySection>
        )}

        {project.architecture && (
          <CaseStudySection heading="Solution architecture" kicker="07">
            <ArchitectureDiagram stages={project.architecture} />
          </CaseStudySection>
        )}

        {project.dataModel && (
          <CaseStudySection heading="Data model" kicker="08">
            {project.dataModel.intro && <p>{project.dataModel.intro}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              {project.dataModel.groups.map((group) => (
                <div key={group.title} className="rounded-lg border border-border bg-surface p-5">
                  <h3 className="text-sm font-semibold text-text">{group.title}</h3>
                  {group.description && <p className="mt-1 text-sm text-muted">{group.description}</p>}
                  <ul className="mt-3 flex flex-wrap gap-2">
                    {group.examples.map((ex) => (
                      <li
                        key={ex}
                        className="rounded-md border border-border bg-surface-light px-2.5 py-1 text-xs text-muted"
                      >
                        {ex}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </CaseStudySection>
        )}

        {project.rulesAndLogic && (
          <CaseStudySection heading="Rules and decision logic" kicker="09">
            <p>{project.rulesAndLogic.intro}</p>
            <Bullets items={project.rulesAndLogic.rules} />
            {project.rulesAndLogic.statusExamples && (
              <div className="grid gap-3 pt-2 sm:grid-cols-2">
                {project.rulesAndLogic.statusExamples.map((ex) => (
                  <div
                    key={ex.status}
                    className="flex items-start gap-3 rounded-lg border border-border bg-surface p-4"
                  >
                    <StatusChip status={ex.status} />
                    <p className="text-sm text-muted">{ex.description}</p>
                  </div>
                ))}
              </div>
            )}
          </CaseStudySection>
        )}

        {project.userExperience && (
          <CaseStudySection heading="User experience" kicker="10">
            <p>{project.userExperience.intro}</p>
            <Bullets items={project.userExperience.modules} />
          </CaseStudySection>
        )}

        {project.testing && (
          <CaseStudySection heading="Testing and validation" kicker="11">
            <Bullets items={project.testing} />
          </CaseStudySection>
        )}

        {project.codeSamples && project.codeSamples.length > 0 && (
          <CaseStudySection heading="Code samples" kicker="12">
            <p className="text-sm text-muted">
              Illustrative portfolio code written to demonstrate the design, not employer source code.
            </p>
            <div className="space-y-6">
              {project.codeSamples.map((sample) => (
                <CodeBlock key={sample.title} {...sample} />
              ))}
            </div>
          </CaseStudySection>
        )}

        {project.syntheticTables && project.syntheticTables.length > 0 && (
          <CaseStudySection heading="Synthetic data" kicker="13">
            <div className="space-y-6">
              {project.syntheticTables.map((table) => (
                <SyntheticDataTable key={table.caption} {...table} />
              ))}
            </div>
          </CaseStudySection>
        )}

        {project.chart && (
          <CaseStudySection heading="Visualizing the pattern" kicker="14">
            {project.chart === "erp-migration" && <ErpMigrationChart />}
            {project.chart === "card-utilization" && <CardUtilizationChart />}
          </CaseStudySection>
        )}

        <CaseStudySection heading="Results and value" kicker="15">
          <p>{project.resultsLanguage}</p>
        </CaseStudySection>

        {project.technicalDecisions && (
          <CaseStudySection heading="Technical decisions" kicker="16">
            <div className="grid gap-4 sm:grid-cols-2">
              {project.technicalDecisions.map((d) => (
                <div key={d.title} className="rounded-lg border border-border bg-surface p-5">
                  <h3 className="text-sm font-semibold text-text">{d.title}</h3>
                  <p className="mt-1 text-sm text-muted">{d.explanation}</p>
                </div>
              ))}
            </div>
          </CaseStudySection>
        )}

        {project.challengesAndTradeoffs && (
          <CaseStudySection heading="Challenges and tradeoffs" kicker="17">
            <Bullets items={project.challengesAndTradeoffs} />
          </CaseStudySection>
        )}

        {project.whatILearned && (
          <CaseStudySection heading="What I learned" kicker="18">
            <Bullets items={project.whatILearned} />
          </CaseStudySection>
        )}

        {project.designNote && (
          <CaseStudySection heading={project.designNote.heading}>
            {project.designNote.body?.map((p) => <p key={p}>{p}</p>)}
            {project.designNote.bullets && <Bullets items={project.designNote.bullets} />}
          </CaseStudySection>
        )}

        <CaseStudySection heading="What this demonstrates">
          <div className="flex flex-wrap gap-2">
            {project.whatThisDemonstrates.map((item) => (
              <Tag key={item} label={item} />
            ))}
          </div>
        </CaseStudySection>

        <CaseStudySection heading="Privacy note">
          <ConfidentialityNote note={project.confidentialityNote} />
        </CaseStudySection>
      </Container>

      {next && (
        <Container className="pt-4 pb-20">
          <Link
            href={`/work/${next.slug}`}
            className="group flex items-center justify-between rounded-xl border border-border bg-surface p-6 transition-colors hover:border-accent-blue/60"
          >
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-accent-cyan">
                Next project
              </p>
              <p className="mt-1 text-lg font-semibold text-text">{next.title}</p>
            </div>
            <ArrowRight
              aria-hidden="true"
              size={20}
              className="shrink-0 text-accent-blue transition-transform group-hover:translate-x-1"
            />
          </Link>
        </Container>
      )}
    </article>
  );
}
