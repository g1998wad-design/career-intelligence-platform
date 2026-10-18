import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { Project } from "@/types/project";
import { getAdjacentProject, getRelatedProjects } from "@/lib/projects";
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
import AuditRulesDemo from "./AuditRulesDemo";
import CaseStudyNav, { type NavItem } from "./CaseStudyNav";

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

/** Mirrors the conditional sections actually rendered below, so the nav never drifts from reality. */
function buildNavItems(project: Project): NavItem[] {
  const items: NavItem[] = [
    { id: "executive-summary", label: "Executive summary" },
    { id: "business-problem", label: project.businessProblem.heading || "Business problem" },
  ];
  if (project.priorStateWorkflow) items.push({ id: "prior-state-workflow", label: "Prior-state workflow" });
  if (project.constraintsAndRisks) items.push({ id: "constraints-risks", label: "Constraints and risks" });
  items.push({ id: "my-role", label: "My role" });
  if (project.discovery) items.push({ id: "discovery", label: "Discovery and requirements" });
  if (project.architecture) items.push({ id: "architecture", label: "Solution architecture" });
  if (project.dataModel) items.push({ id: "data-model", label: "Data model" });
  if (project.rulesAndLogic) items.push({ id: "rules-logic", label: "Rules and decision logic" });
  if (project.interactiveDemo) items.push({ id: "try-it", label: "Try the rules engine" });
  if (project.userExperience) items.push({ id: "user-experience", label: "User experience" });
  if (project.testing) items.push({ id: "testing", label: "Testing and validation" });
  if (project.codeSamples?.length) items.push({ id: "code-samples", label: "Code samples" });
  if (project.syntheticTables?.length) items.push({ id: "synthetic-data", label: "Synthetic data" });
  if (project.chart) items.push({ id: "visualizing", label: "Visualizing the pattern" });
  items.push({ id: "results", label: "Results and value" });
  if (project.technicalDecisions) items.push({ id: "technical-decisions", label: "Technical decisions" });
  if (project.challengesAndTradeoffs) items.push({ id: "challenges", label: "Challenges and tradeoffs" });
  if (project.whatILearned) items.push({ id: "what-i-learned", label: "What I learned" });
  return items;
}

export default function CaseStudy({ project }: { project: Project }) {
  const next = getAdjacentProject(project.slug);
  const related = getRelatedProjects(project.slug);
  const isFlagship = project.depth === "flagship";
  const navItems = isFlagship ? buildNavItems(project) : [];
  const hasNav = navItems.length > 0;

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

      <Container className={hasNav ? "lg:grid lg:grid-cols-[200px_1fr] lg:items-start lg:gap-12" : undefined}>
        {hasNav && <CaseStudyNav items={navItems} />}

        <div className="divide-y divide-border/60">
          <CaseStudySection id="executive-summary" heading="Executive summary" kicker="01">
            {project.executiveSummary.map((p) => (
              <p key={p}>{p}</p>
            ))}
          </CaseStudySection>

          <CaseStudySection
            id="business-problem"
            heading={project.businessProblem.heading || "Business problem"}
            kicker="02"
          >
            {project.businessProblem.body?.map((p) => <p key={p}>{p}</p>)}
            {project.businessProblem.bullets && <Bullets items={project.businessProblem.bullets} />}
          </CaseStudySection>

          {project.priorStateWorkflow && (
            <CaseStudySection id="prior-state-workflow" heading="Prior-state workflow" kicker="03">
              <NumberedSteps items={project.priorStateWorkflow} />
            </CaseStudySection>
          )}

          {project.constraintsAndRisks && (
            <CaseStudySection id="constraints-risks" heading="Constraints and risks" kicker="04">
              <Bullets items={project.constraintsAndRisks} />
            </CaseStudySection>
          )}

          <CaseStudySection id="my-role" heading="My role" kicker="05">
            <Bullets items={project.myRole} />
          </CaseStudySection>

          {project.discovery && (
            <CaseStudySection id="discovery" heading="Discovery and requirements" kicker="06">
              {project.discovery.map((p) => (
                <p key={p}>{p}</p>
              ))}
            </CaseStudySection>
          )}

          {project.architecture && (
            <CaseStudySection id="architecture" heading="Solution architecture" kicker="07">
              <ArchitectureDiagram stages={project.architecture} />
            </CaseStudySection>
          )}

          {project.dataModel && (
            <CaseStudySection id="data-model" heading="Data model" kicker="08">
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
            <CaseStudySection id="rules-logic" heading="Rules and decision logic" kicker="09">
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

          {project.interactiveDemo === "audit-rules" && (
            <CaseStudySection id="try-it" heading="Try the rules engine">
              <AuditRulesDemo />
            </CaseStudySection>
          )}

          {project.userExperience && (
            <CaseStudySection id="user-experience" heading="User experience" kicker="10">
              <p>{project.userExperience.intro}</p>
              <Bullets items={project.userExperience.modules} />
            </CaseStudySection>
          )}

          {project.testing && (
            <CaseStudySection id="testing" heading="Testing and validation" kicker="11">
              <Bullets items={project.testing} />
            </CaseStudySection>
          )}

          {project.codeSamples && project.codeSamples.length > 0 && (
            <CaseStudySection id="code-samples" heading="Code samples" kicker="12">
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
            <CaseStudySection id="synthetic-data" heading="Synthetic data" kicker="13">
              <div className="space-y-6">
                {project.syntheticTables.map((table) => (
                  <SyntheticDataTable key={table.caption} {...table} />
                ))}
              </div>
            </CaseStudySection>
          )}

          {project.chart && (
            <CaseStudySection id="visualizing" heading="Visualizing the pattern" kicker="14">
              {project.chart === "erp-migration" && <ErpMigrationChart />}
              {project.chart === "card-utilization" && <CardUtilizationChart />}
            </CaseStudySection>
          )}

          <CaseStudySection id="results" heading="Results and value" kicker="15">
            <p>{project.resultsLanguage}</p>
          </CaseStudySection>

          {project.technicalDecisions && (
            <CaseStudySection id="technical-decisions" heading="Technical decisions" kicker="16">
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
            <CaseStudySection id="challenges" heading="Challenges and tradeoffs" kicker="17">
              <Bullets items={project.challengesAndTradeoffs} />
            </CaseStudySection>
          )}

          {project.whatILearned && (
            <CaseStudySection id="what-i-learned" heading="What I learned" kicker="18">
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
        </div>
      </Container>

      <Container className="space-y-6 pt-4 pb-20">
        {related.length > 0 && (
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-accent-cyan">
              Related work
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              {related.map((r) => (
                <Link
                  key={r.slug}
                  href={`/work/${r.slug}`}
                  className="group flex flex-col justify-between rounded-xl border border-border bg-surface p-5 transition-colors hover:border-accent-blue/60"
                >
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-widest text-accent-cyan">
                      {r.heroKicker}
                    </p>
                    <h3 className="mt-1 text-base font-semibold text-text">{r.title}</h3>
                    <p className="mt-1 text-sm text-muted">{r.cardSummary}</p>
                  </div>
                  <div className="mt-4 flex items-center gap-1.5 text-sm font-medium text-accent-blue transition-transform group-hover:translate-x-1">
                    View case study
                    <ArrowRight aria-hidden="true" size={16} />
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {next && (
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
        )}
      </Container>
    </article>
  );
}
