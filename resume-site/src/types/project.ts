export type ProjectDepth = "flagship" | "supporting";

export type RuleStatus = "PASS" | "FAIL" | "REVIEW" | "EXCLUDED";

export type StatusExample = {
  status: RuleStatus;
  description: string;
};

export type ProjectSection = {
  heading: string;
  body?: string[];
  bullets?: string[];
};

export type CodeSample = {
  title: string;
  language: string;
  code: string;
};

export type SyntheticTable = {
  caption: string;
  columns: string[];
  rows: string[][];
};

export type DecisionPoint = {
  title: string;
  explanation: string;
};

export type ChartKind = "erp-migration" | "card-utilization";

export type Project = {
  slug: string;
  order: number;
  depth: ProjectDepth;
  heroKicker: string;
  title: string;
  cardSummary: string;
  oneSentenceOverview: string;
  tags: string[];
  keyInsight?: string;
  executiveSummary: string[];
  businessProblem: ProjectSection;
  priorStateWorkflow?: string[];
  constraintsAndRisks?: string[];
  myRole: string[];
  discovery?: string[];
  architecture?: string[][];
  dataModel?: {
    intro?: string;
    groups: { title: string; description?: string; examples: string[] }[];
  };
  rulesAndLogic?: {
    intro: string;
    rules: string[];
    statusExamples?: StatusExample[];
  };
  userExperience?: {
    intro: string;
    modules: string[];
  };
  testing?: string[];
  codeSamples?: CodeSample[];
  syntheticTables?: SyntheticTable[];
  resultsLanguage: string;
  technicalDecisions?: DecisionPoint[];
  challengesAndTradeoffs?: string[];
  whatILearned?: string[];
  designNote?: ProjectSection;
  whatThisDemonstrates: string[];
  confidentialityNote: string;
  chart?: ChartKind;
  interactiveDemo?: "audit-rules";
};
