export const aboutHeading = "I build at the boundary between operations and engineering.";

export const aboutBody = [
  "I started with business analysis and visualization, but the most interesting problems rarely ended at a dashboard. The recurring pattern was a business process spread across spreadsheets, documents, email, dashboards, and individual memory. Solving those problems required more than reporting. It required understanding the workflow, defining the source of truth, identifying deterministic rules, deciding where AI was appropriate, and building an interface that people could trust.",
];

export const aboutSkillAreas = [
  "Process discovery and stakeholder interviews",
  "Data analysis and dimensional thinking",
  "SQL and warehouse modeling",
  "Python automation",
  "Applied AI for unstructured information",
  "Deterministic controls for governed decisions",
  "Tableau and Streamlit product interfaces",
  "Testing, documentation, and change adoption",
];

export const aboutClosing =
  "I care about systems that are understandable. A useful automation should show what it received, which rules it applied, what it could not determine, and why a record requires attention.";

export const approachCards = [
  {
    title: "Understand the real workflow",
    description:
      "Observe how the process actually operates, including spreadsheets, side conversations, workarounds, edge cases, and undocumented decisions.",
  },
  {
    title: "Separate rules from interpretation",
    description:
      "Use deterministic logic for known controls. Use AI where information is unstructured or contextual. Do not make probabilistic models responsible for decisions that can be expressed clearly.",
  },
  {
    title: "Design for exceptions",
    description:
      "The goal is not to hide complexity. It is to direct human attention to the records that genuinely need judgment.",
  },
  {
    title: "Make the system auditable",
    description:
      "Preserve raw inputs, normalized values, rule results, uncertainty, configuration, and downloadable evidence.",
  },
  {
    title: "Build for adoption",
    description:
      "A technically correct solution fails if users cannot understand it, challenge it, or fit it into their operating rhythm.",
  },
];
