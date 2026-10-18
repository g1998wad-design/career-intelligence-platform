import type { Project } from "@/types/project";

export const projects: Project[] = [
  // ---------------------------------------------------------------------
  // FLAGSHIP 1 — AI-Powered Financial Audit Automation
  // ---------------------------------------------------------------------
  {
    slug: "ai-audit-automation",
    order: 1,
    depth: "flagship",
    heroKicker: "Flagship case study",
    title: "AI-Powered Financial Audit Automation",
    cardSummary:
      "A governed audit application that combines AI-assisted document extraction with deterministic financial controls, two-way reconciliation, exception management, and exportable evidence.",
    oneSentenceOverview:
      "Built an AI-assisted audit application that transforms a fragmented, document-heavy review process into a structured workflow for extracting evidence, applying business rules, reconciling records, and escalating exceptions.",
    tags: [
      "Python",
      "Streamlit",
      "SQL",
      "Snowflake",
      "Document AI",
      "Financial Controls",
      "Reconciliation",
      "Human-in-the-Loop",
    ],
    keyInsight:
      "The correct automation target was not merely the clicks. It was the decision system behind the audit.",
    executiveSummary: [
      "Built an AI-assisted audit application that transforms a fragmented, document-heavy review process into a structured workflow for extracting evidence, applying business rules, reconciling records, and escalating exceptions.",
      "The design keeps AI and financial controls strictly separated: an AI layer reads unstructured support packets and proposes candidate fields, while a deterministic rules engine owns every decision that can be expressed as a clear control. AI never silently decides a financial exception.",
    ],
    businessProblem: {
      heading: "Business problem",
      body: [
        "The original audit depended on a reviewer moving manually across multiple systems and artifacts. A typical review required an operational payment extract, a dashboard or workbook, individual PDF support packets, a shared document repository, messages, and process knowledge retained by experienced reviewers.",
        "The problem was not simply that one task took too many clicks. It was orchestration debt: evidence, rules, and judgment were scattered across people and tools instead of living in one governed system.",
      ],
    },
    constraintsAndRisks: [
      "Evidence was distributed across structured and unstructured sources.",
      "Reviewers repeatedly opened documents and compared the same categories of fields.",
      "Identifiers appeared in inconsistent formats, including leading zeros, punctuation differences, aliases, and varying invoice layouts.",
      "Business rules were partly documented and partly remembered.",
      "Exception summaries had to be rewritten manually in language appropriate for process owners.",
      "Work scaled roughly with document volume because each packet required individual inspection.",
      "A reviewer could identify a suspected discrepancy but still need to distinguish a confirmed issue from insufficient evidence.",
    ],
    priorStateWorkflow: [
      "Generate or receive a daily payment extract.",
      "Filter to records within the audit scope.",
      "Find the corresponding PDF support packet.",
      "Inspect invoice details, coding, approvals, dates, addresses, and totals.",
      "Reconcile the structured population against the document population in both directions.",
      "Write and communicate exceptions, including threshold-based callouts.",
    ],
    myRole: [
      "I mapped the existing review process end-to-end: the payment extract, the support-packet repository, the reconciliation steps, and the exception write-ups that previously depended on individual reviewer judgment.",
      "I translated the review decisions reviewers were already making into explicit, deterministic rules, and drew the boundary between what a rule could decide and what required AI-assisted extraction or human review.",
      "I designed the data flow and normalization layer, developed the prototype, tested it against representative edge cases (missing packets, partial extraction, duplicate identifiers), and refined the interface around reviewer feedback.",
    ],
    discovery: [
      "Discovery started with the artifacts the review actually depended on: the daily payment extract, the PDF support packets, the shared document repository, and the exception language reviewers used when writing up a finding.",
      "The key discovery insight was that the review was a decision system, not a checklist — reviewers were already applying consistent rules, just inconsistently and without a record of how each decision was reached.",
    ],
    architecture: [
      ["Payment CSV / XLSX", "PDF Support Packets"],
      ["Schema Validation", "Document Extraction"],
      ["Normalization Layer"],
      ["Deterministic Control Engine"],
      ["Two-Way Reconciliation"],
      ["Exception and Evidence Layer"],
      ["Reviewer UI", "Exportable Results"],
    ],
    dataModel: {
      intro:
        "The AI layer produces structured candidate fields from unstructured documents. It does not make final control decisions when a rule can be expressed deterministically.",
      groups: [
        {
          title: "AI-extracted candidate fields",
          description: "Produced by the document AI layer for human and rule review.",
          examples: [
            "Supplier name",
            "Invoice number",
            "Invoice date",
            "Invoice amount",
            "Tax amount",
            "Approval evidence",
            "Coding lines",
            "Business unit or entity indicator",
            "Address evidence",
            "Confidence or extraction status",
          ],
        },
        {
          title: "Normalization rules",
          description: "Applied before any comparison or rule evaluation.",
          examples: [
            "Convert voucher and invoice identifiers to comparable strings",
            "Preserve leading zeros when identifiers are not numeric measures",
            "Normalize whitespace, case, punctuation, and common aliases",
            "Standardize date formats",
            "Parse amounts as decimal values rather than floating-point values",
            "Normalize owner initials and user mappings through configuration, not hard-coded logic",
          ],
        },
      ],
    },
    rulesAndLogic: {
      intro:
        "Deterministic controls own every decision that can be expressed as a known rule. AI-assisted extraction feeds those rules; it does not bypass them.",
      rules: [
        "Is the payment method within audit scope?",
        "Does every in-scope structured record have a corresponding support packet?",
        "Does every support packet map to a structured record?",
        "Does the invoice amount match the structured amount within an approved tolerance?",
        "Does the invoice identifier match after normalization?",
        "Does the payment date or invoice date require follow-up?",
        "Is required coding evidence present?",
        "Is approval evidence present?",
        "Does a payment exceed a configured review threshold?",
        "Is the record excluded by an explicit, configurable exception category?",
      ],
      statusExamples: [
        { status: "PASS", description: "Evidence supports the rule." },
        { status: "FAIL", description: "Evidence shows a confirmed mismatch." },
        {
          status: "REVIEW",
          description: "Evidence is incomplete, ambiguous, or extraction confidence is insufficient.",
        },
        { status: "EXCLUDED", description: "The transaction is outside the configured audit scope." },
      ],
    },
    userExperience: {
      intro:
        "Missing AI output is never treated as proof of an error — it becomes REVIEW unless a deterministic completeness rule clearly establishes a failure.",
      modules: [
        "Upload panel for payment file and PDF packets",
        "Input validation summary",
        "Selected-document test mode",
        "Full-audit mode",
        "Reconciliation diagnostics",
        "Exception summary by category",
        "Owner mapping configuration",
        "Detailed evidence drawer",
        "Download buttons for complete results and exceptions",
      ],
    },
    testing: [
      "Schema tests for required and optional columns",
      "Unit tests for identifier and amount normalization",
      "Known-case tests for matching and mismatching identifiers",
      "Two-way population tests",
      "Tests for duplicate document identifiers",
      "Tests for records with no support packet",
      "Tests for support packets with no structured record",
      "Tests for partial AI extraction",
      "Tests for multi-line coding",
      "Tests that verify uncertain extraction produces REVIEW, not a false FAIL",
      "Regression fixtures built from fully synthetic examples",
    ],
    codeSamples: [
      {
        title: "Synthetic extracted document output",
        language: "json",
        code: `[
  {
    "voucher_id": "00018427",
    "invoice_id": "INV-1048",
    "supplier_name": "Supplier Alpha",
    "invoice_amount": 2840.50,
    "approval_found": true,
    "coding_lines": [
      {"account": "610100", "department": "D120", "amount": 2840.50}
    ],
    "extraction_status": "complete"
  },
  {
    "voucher_id": "00018428",
    "invoice_id": "SB-7781",
    "supplier_name": "Supplier Bravo",
    "invoice_amount": 6725.00,
    "approval_found": false,
    "coding_lines": [],
    "extraction_status": "partial"
  }
]`,
      },
      {
        title: "Normalization",
        language: "python",
        code: `from decimal import Decimal, InvalidOperation
import re


def normalize_identifier(value: object) -> str:
    """Normalize an identifier without converting away meaningful leading zeros."""
    if value is None:
        return ""
    text = str(value).strip().upper()
    text = re.sub(r"\\s+", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def normalize_amount(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    cleaned = re.sub(r"[^0-9.\\-]", "", str(value))
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None`,
      },
      {
        title: "Two-way reconciliation",
        language: "python",
        code: `from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationResult:
    matched: set[str]
    structured_only: set[str]
    document_only: set[str]


def reconcile_populations(
    structured_ids: list[str],
    document_ids: list[str]
) -> ReconciliationResult:
    structured = {normalize_identifier(x) for x in structured_ids if x}
    documents = {normalize_identifier(x) for x in document_ids if x}

    return ReconciliationResult(
        matched=structured & documents,
        structured_only=structured - documents,
        document_only=documents - structured,
    )`,
      },
      {
        title: "Rule result",
        language: "python",
        code: `from dataclasses import dataclass
from typing import Literal

Status = Literal["PASS", "FAIL", "REVIEW", "EXCLUDED"]


@dataclass
class RuleResult:
    rule_name: str
    status: Status
    message: str
    evidence: dict


def evaluate_support_presence(
    voucher_id: str,
    document_ids: set[str]
) -> RuleResult:
    normalized = normalize_identifier(voucher_id)
    if normalized in document_ids:
        return RuleResult(
            rule_name="support_presence",
            status="PASS",
            message="A matching support packet was found.",
            evidence={"voucher_id": normalized},
        )

    return RuleResult(
        rule_name="support_presence",
        status="FAIL",
        message="No matching support packet was found.",
        evidence={"voucher_id": normalized},
    )`,
      },
    ],
    syntheticTables: [
      {
        caption: "Synthetic payment population",
        columns: ["voucher_id", "supplier_name", "invoice_id", "payment_method", "gross_amount", "payment_date", "owner_code"],
        rows: [
          ["00018427", "Supplier Alpha", "INV-1048", "EFT", "2840.50", "2026-03-14", "RVA"],
          ["00018428", "Supplier Bravo", "SB-7781", "CHECK", "6725.00", "2026-03-14", "LKM"],
          ["00018429", "Supplier Charlie", "2026-0312", "EFT", "1198.20", "2026-03-14", "RVA"],
        ],
      },
      {
        caption: "Synthetic result output",
        columns: ["voucher_id", "status", "exception_type", "public_message"],
        rows: [
          ["00018427", "PASS", "None", "No exception identified"],
          ["00018428", "REVIEW", "Approval evidence", "Approval could not be confirmed from the supplied packet"],
          ["00018429", "FAIL", "Missing support", "No matching support packet was found for this in-scope record"],
        ],
      },
    ],
    resultsLanguage:
      "The prototype consolidated document review, reconciliation, control execution, and exception reporting into one governed workflow. It shifted the reviewer experience from opening every record to focusing on exceptions and uncertain evidence.",
    technicalDecisions: [
      {
        title: "AI extracts, rules decide",
        explanation:
          "The AI layer produces structured candidate fields. It does not make final control decisions when rules can be expressed deterministically.",
      },
      {
        title: "Decimal arithmetic for money",
        explanation:
          "Amounts are parsed as decimal values rather than floating-point values so financial comparisons stay exact.",
      },
      {
        title: "Configuration over hard-coded mappings",
        explanation:
          "Owner initials and user mappings are normalized through configuration rather than hard-coded logic, so the rule set can change without a code change.",
      },
      {
        title: "Uncertainty is not failure",
        explanation:
          "Missing or low-confidence AI output is never treated as proof of an error. It becomes REVIEW unless a deterministic completeness rule clearly establishes a failure.",
      },
    ],
    challengesAndTradeoffs: [
      "AI is useful for reading unstructured documents but should not silently own financial control decisions.",
      "Exact matching is transparent but brittle; fuzzy matching increases recall but can create false positives.",
      "Document layouts vary, so an extraction schema needs both structure and uncertainty handling.",
      "Configuration improves maintainability but introduces governance requirements around who can change rules.",
      "A portfolio demo should use synthetic PDFs generated specifically for the site.",
    ],
    whatILearned: [
      "A control is only as trustworthy as its ability to explain itself — every PASS, FAIL, and REVIEW needed to carry the evidence behind it, not just the verdict.",
      "Separating probabilistic extraction from deterministic decisions was the single highest-leverage design choice; it made the system both more accurate and easier for reviewers to trust.",
    ],
    whatThisDemonstrates: [
      "Applied AI grounded in a real operational workflow",
      "Separation of probabilistic extraction from deterministic controls",
      "Financial reconciliation design",
      "Human-in-the-loop product thinking",
      "Python application architecture",
      "Stakeholder-driven requirements discovery",
      "Exception-oriented UX",
      "Auditability and evidence retention",
    ],
    confidentialityNote:
      "Selected enterprise projects completed in a professional setting. Details, interfaces, and data have been anonymized or recreated with synthetic examples to protect confidential information.",
  },

  // ---------------------------------------------------------------------
  // FLAGSHIP 2 — Procurement Contract Workflow Automation
  // ---------------------------------------------------------------------
  {
    slug: "contract-workflow-automation",
    order: 2,
    depth: "flagship",
    heroKicker: "Flagship case study",
    title: "Procurement Contract Workflow Automation",
    cardSummary:
      "A Python-based monthly workflow that ingests a new contract-management export, standardizes the data, removes duplicates, carries forward prior review context, validates the output, and creates an auditable review workbook.",
    oneSentenceOverview:
      "Designed a configurable automation pipeline that converts a recurring spreadsheet-heavy contract review process into a repeatable monthly workflow with historical continuity and visible validation outputs.",
    tags: ["Python", "pandas", "openpyxl", "Data Validation", "Workflow Automation", "Procurement", "Auditability"],
    keyInsight: "Preserve human review knowledge while refreshing system-owned fields from the newest source.",
    executiveSummary: [
      "Designed a configurable automation pipeline that converts a recurring spreadsheet-heavy contract review process into a repeatable monthly workflow with historical continuity and visible validation outputs.",
      "The pipeline treats every column as owned by either the source system, the reviewer, or a derived calculation — and never lets a fresh export silently erase review history.",
    ],
    businessProblem: {
      heading: "Business problem",
      body: [
        "A new contract-management export arrived each month. The team needed a stable review workbook containing contract metadata, supplier information, owners, dates, statuses, category information, technology classification, review fields, and prior notes.",
        "The difficult requirement was historical continuity. The current export contained the latest system state, but the review team had added context in prior versions. Without automation, reviewers had to compare files manually, remove duplicate rows, perform lookups, and re-enter or carry forward notes.",
      ],
    },
    myRole: [
      "I mapped the existing monthly workbook process and identified which columns were system-owned, which were reviewer-owned, and which needed to be derived — a distinction the prior manual process had never made explicit.",
      "I designed the carry-forward and validation logic, built the pipeline, tested it against representative edge cases (new contracts, removed contracts, duplicate keys), and refined the workbook outputs so reviewers could trust what had changed and why.",
    ],
    discovery: [
      "Discovery focused on where review knowledge actually lived from month to month: which fields reviewers edited by hand, which fields the source system always overwrote, and which values were calculated rather than entered.",
      "That mapping became the ownership model the entire pipeline is built around.",
    ],
    architecture: [
      ["Current Export", "Prior Reviewed Workbook"],
      ["Column Standardization", "Historical Field Selection"],
      ["Key Validation"],
      ["Deduplication and Matching"],
      ["Carry Forward Notes", "New Record Defaults"],
      ["Derived Calculations"],
      ["Review Workbook + Validation Report"],
      ["Versioned Archive"],
    ],
    dataModel: {
      intro: "Columns are separated into three ownership groups so a refresh never overwrites human judgment.",
      groups: [
        {
          title: "Source-system fields",
          description: "Always refreshed from the latest export.",
          examples: ["Contract ID", "Contract title", "Supplier", "Contract owner", "Status", "Effective date", "Expiration date", "Category", "Current contract value"],
        },
        {
          title: "Reviewer-maintained fields",
          description: "Carried forward from the prior reviewed workbook when the stable key matches.",
          examples: ["Review notes", "Payment terms assessment", "Technology / non-technology classification", "Supplier capability notes", "Risk flags", "Follow-up owner", "Follow-up status"],
        },
        {
          title: "Derived fields",
          description: "Calculated by the pipeline.",
          examples: ["Days to expiration", "Renewal window", "Missing-required-field flag", "Duplicate-key flag", "New / existing / removed record classification", "Carry-forward match status"],
        },
      ],
    },
    userExperience: {
      intro:
        "The reviewer-facing surface for this pipeline is the workbook itself: dedicated tabs for current review, exceptions, and the run's own audit trail.",
      modules: [
        "Current Review",
        "Validation Issues",
        "New Records",
        "Removed Records",
        "Duplicate Records",
        "Carry Forward Audit",
        "Run Summary (run ID, source filenames, timestamp, row and match counts, validation issue count)",
      ],
    },
    codeSamples: [
      {
        title: "Recommended Python project structure",
        language: "text",
        code: `contract-workflow-demo/
├── app.py
├── pyproject.toml
├── README.md
├── config/
│   ├── columns.yml
│   └── rules.yml
├── src/
│   ├── ingest.py
│   ├── normalize.py
│   ├── validate.py
│   ├── deduplicate.py
│   ├── carry_forward.py
│   ├── derive.py
│   ├── workbook.py
│   ├── archive.py
│   └── logging_config.py
├── tests/
│   ├── test_normalize.py
│   ├── test_validate.py
│   ├── test_carry_forward.py
│   └── fixtures/
├── sample_data/
│   ├── current_export.csv
│   └── prior_review.csv
└── output/`,
      },
      {
        title: "Column standardization",
        language: "python",
        code: `import pandas as pd

COLUMN_ALIASES = {
    "contract workspace id": "contract_id",
    "cw id": "contract_id",
    "supplier name": "supplier",
    "contract status": "status",
    "start date": "effective_date",
    "end date": "expiration_date",
}


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {
        column: COLUMN_ALIASES.get(column.strip().lower(), column.strip().lower())
        for column in df.columns
    }
    return df.rename(columns=renamed)`,
      },
      {
        title: "Validation",
        language: "python",
        code: `REQUIRED_COLUMNS = {
    "contract_id",
    "contract_title",
    "supplier",
    "status",
    "effective_date",
    "expiration_date",
}


def validate_schema(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")

    if "contract_id" in df.columns and df["contract_id"].isna().any():
        errors.append("One or more records have no contract ID.")

    if "contract_id" in df.columns and df["contract_id"].duplicated().any():
        errors.append("Duplicate contract IDs were detected.")

    return errors`,
      },
      {
        title: "Carry-forward merge",
        language: "python",
        code: `REVIEWER_COLUMNS = [
    "contract_id",
    "review_notes",
    "payment_terms_review",
    "technology_flag",
    "supplier_capabilities",
    "follow_up_status",
]


def carry_forward_review_fields(
    current: pd.DataFrame,
    prior_reviewed: pd.DataFrame,
) -> pd.DataFrame:
    history = prior_reviewed[REVIEWER_COLUMNS].drop_duplicates("contract_id")

    merged = current.merge(
        history,
        on="contract_id",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    merged["record_classification"] = merged["_merge"].map({
        "both": "existing",
        "left_only": "new",
    })

    return merged.drop(columns="_merge")`,
      },
    ],
    syntheticTables: [
      {
        caption: "Synthetic current export",
        columns: ["contract_id", "contract_title", "supplier", "status", "effective_date", "expiration_date", "category", "current_value"],
        rows: [
          ["CW-10021", "Analytics Platform Renewal", "Supplier Alpha", "Active", "2026-01-01", "2026-12-31", "Software", "125000"],
          ["CW-10022", "Facilities Maintenance", "Supplier Bravo", "Active", "2025-07-01", "2027-06-30", "Facilities", "84000"],
          ["CW-10023", "Research Subscription", "Supplier Charlie", "Draft", "2026-04-01", "2027-03-31", "Professional Services", "36000"],
        ],
      },
      {
        caption: "Synthetic prior-review fields",
        columns: ["contract_id", "review_notes", "payment_terms_review", "technology_flag", "supplier_capabilities", "follow_up_status"],
        rows: [
          ["CW-10021", "Confirm renewal pricing", "Net 30", "Technology", "Enterprise analytics platform", "Open"],
          ["CW-10022", "No issue identified", "Net 45", "Non-Technology", "Preventive maintenance", "Closed"],
          ["CW-09999", "Confirm termination documentation", "Net 30", "Non-Technology", "Archived service", "Open"],
        ],
      },
    ],
    testing: [
      "CW-10021: current contract fields refreshed; prior notes carried forward.",
      "CW-10022: current fields refreshed; closed review context retained.",
      "CW-10023: identified as new; reviewer fields initialized blank.",
      "CW-09999: absent from current export; written to a removed-record report rather than silently deleted.",
    ],
    resultsLanguage:
      "The automation replaced manual workbook comparison and repeated lookups with a repeatable pipeline that refreshes system data while preserving historical review context. It also created explicit validation and audit outputs so that exceptions could be reviewed rather than hidden inside spreadsheet logic.",
    technicalDecisions: [
      { title: "Stable business key, not row position", explanation: "Never use row position as identity. Use a stable business key." },
      { title: "Reviewer fields are never silently overwritten", explanation: "Never overwrite reviewer fields with blank source values." },
      { title: "No silent data loss", explanation: "Do not silently discard duplicates, and do not silently delete records that disappeared from the latest extract." },
      { title: "Immutable raw input", explanation: "Keep raw input immutable so every run can be traced back to its source file." },
      { title: "Full audit logging", explanation: "Log every carry-forward decision." },
      { title: "Always validate", explanation: "Write a validation workbook even when the run succeeds." },
      { title: "Configuration over code", explanation: "Keep configuration separate from code when business-managed fields change over time." },
    ],
    whatILearned: [
      "The hardest part of this automation wasn't the pandas logic — it was deciding, explicitly, who owns each column. Once that ownership model existed, deduplication, carry-forward, and validation all became straightforward.",
      "Writing a validation workbook on every run, not just failed ones, turned out to matter more than any single rule: it made the pipeline's behavior visible even when nothing went wrong.",
    ],
    whatThisDemonstrates: [
      "Translating spreadsheet operations into software modules",
      "Data ownership and source-of-truth design",
      "Historical state management",
      "Configurable ETL",
      "Excel automation with business-friendly outputs",
      "Audit logging and exception handling",
      "Procurement domain understanding",
    ],
    confidentialityNote:
      "Selected enterprise projects completed in a professional setting. Details, interfaces, and data have been anonymized or recreated with synthetic examples to protect confidential information.",
  },

  // ---------------------------------------------------------------------
  // FLAGSHIP 3 — Legacy-to-Cloud ERP Migration Analytics
  // ---------------------------------------------------------------------
  {
    slug: "erp-migration-analytics",
    order: 3,
    depth: "flagship",
    heroKicker: "Flagship case study",
    title: "Legacy-to-Cloud ERP Migration Analytics",
    cardSummary:
      "A unified analytics model for monitoring operational activity as business units transition from a legacy ERP to a cloud ERP, without double-counting overlapping data.",
    oneSentenceOverview:
      "Built reporting logic that preserves historical continuity across an ERP migration while ensuring the cloud system becomes authoritative after each business unit's transition.",
    tags: ["Snowflake", "SQL", "Tableau", "Data Modeling", "ERP Migration", "Analytics Engineering", "Business Logic"],
    keyInsight:
      "At the business-unit and month level, when cloud ERP data exists, use the cloud ERP and exclude the legacy ERP for that same business-unit/month combination.",
    executiveSummary: [
      "Built reporting logic that preserves historical continuity across an ERP migration while ensuring the cloud system becomes authoritative after each business unit's transition.",
      "The model's governing rule is a single, explicit source-precedence pattern applied at the correct grain — business unit and month — so overlapping source data never gets double-counted.",
    ],
    businessProblem: {
      heading: "Business problem",
      body: [
        "Operational reporting needed to span two ERP systems during a phased migration. Historical activity remained in the legacy system while new activity began appearing in the cloud system. A simple union would risk double-counting months where both sources contained records.",
      ],
    },
    constraintsAndRisks: [
      "Preserve legacy history before migration.",
      "Use cloud-system records after migration.",
      "Avoid double-counting overlapping company-month combinations.",
      "Support different migration dates by business unit.",
      "Standardize activities whose labels differed across systems.",
      "Preserve the ability to explain which source supplied each metric.",
      "Support monthly counts, shares, year-over-year comparisons, activity mix, and transition narratives.",
    ],
    myRole: [
      "I mapped how activity data differed between the legacy and cloud ERP systems — not just in values, but in category labels, grain, and timing of availability by business unit.",
      "I designed the source-precedence rule and the semantic mapping layer, built and tested the SQL against representative overlap scenarios, and worked with the reporting team to translate the model into Tableau views that read as one continuous timeline rather than two disconnected systems.",
    ],
    discovery: [
      "The discovery problem was establishing exactly what changed at migration: not just the source system, but category definitions, structures, and the business-unit-specific cutover dates.",
      "That led directly to the governing rule: source selection has to be decided at the business-unit/month grain, not at the row level or the dataset level, or double-counting becomes possible.",
    ],
    dataModel: {
      intro:
        "A semantic mapping table harmonizes activity labels that differ by source system into one canonical category before any comparison happens.",
      groups: [
        {
          title: "Canonical activity categories",
          description: "Each raw, system-specific label maps to exactly one canonical category.",
          examples: ["Automated Matching", "Specialist Review", "Business Review"],
        },
      ],
    },
    rulesAndLogic: {
      intro: "Source selection is resolved once, at the business-unit/month grain, before any downstream aggregation.",
      rules: [
        "At the business-unit and month level, when cloud ERP data exists, use the cloud ERP and exclude the legacy ERP for that same business-unit/month combination.",
        "Every raw activity label must map to exactly one canonical category before aggregation.",
        "Source-selection decisions must be queryable, not implicit in a BI tool filter.",
      ],
    },
    testing: [
      "No business-unit/month should retain both source systems after precedence logic.",
      "Every raw activity must map to one canonical category.",
      "Counts must remain non-negative.",
      "Shares must sum to approximately 100% by business-unit/month.",
      "YoY comparisons should require a valid prior-year value.",
      "Source-selection decisions should be queryable.",
      "Migration boundaries should not create artificial totals through duplication.",
    ],
    codeSamples: [
      {
        title: "Source precedence",
        language: "sql",
        code: `WITH company_month_source AS (
    SELECT
        business_unit,
        month,
        MAX(CASE WHEN source_system = 'Cloud ERP' THEN 1 ELSE 0 END)
            AS has_cloud_data
    FROM activity_source
    GROUP BY business_unit, month
),
selected_activity AS (
    SELECT a.*
    FROM activity_source a
    JOIN company_month_source s
      ON a.business_unit = s.business_unit
     AND a.month = s.month
    WHERE
        (s.has_cloud_data = 1 AND a.source_system = 'Cloud ERP')
        OR
        (s.has_cloud_data = 0 AND a.source_system = 'Legacy ERP')
)
SELECT *
FROM selected_activity;`,
      },
      {
        title: "Activity share",
        language: "sql",
        code: `SELECT
    business_unit,
    month,
    activity_type,
    SUM(activity_count) AS activity_count,
    SUM(activity_count)
      / NULLIF(SUM(SUM(activity_count)) OVER (
          PARTITION BY business_unit, month
        ), 0) AS activity_share
FROM selected_activity
GROUP BY business_unit, month, activity_type;`,
      },
      {
        title: "Year-over-year change",
        language: "sql",
        code: `WITH monthly AS (
    SELECT
        business_unit,
        month,
        SUM(activity_count) AS total_activity
    FROM selected_activity
    GROUP BY business_unit, month
)
SELECT
    business_unit,
    month,
    total_activity,
    LAG(total_activity, 12) OVER (
        PARTITION BY business_unit
        ORDER BY month
    ) AS prior_year_activity,
    (total_activity - prior_year_activity)
      / NULLIF(prior_year_activity, 0) AS yoy_change
FROM monthly;`,
      },
    ],
    syntheticTables: [
      {
        caption: "Synthetic activity source data",
        columns: ["business_unit", "month", "source_system", "activity_type", "activity_count"],
        rows: [
          ["Business Unit A", "2026-05-01", "Legacy ERP", "Automated Matching", "18400"],
          ["Business Unit A", "2026-05-01", "Cloud ERP", "Automated Matching", "17950"],
          ["Business Unit A", "2026-05-01", "Cloud ERP", "Specialist Review", "6120"],
          ["Business Unit B", "2026-05-01", "Legacy ERP", "Specialist Review", "4880"],
          ["Business Unit B", "2026-06-01", "Legacy ERP", "Specialist Review", "5015"],
          ["Business Unit B", "2026-06-01", "Cloud ERP", "Specialist Review", "4920"],
        ],
      },
      {
        caption: "Synthetic semantic mapping (fictional labels)",
        columns: ["source_system", "raw_activity", "canonical_activity", "display_order"],
        rows: [
          ["Legacy ERP", "AUTO_MATCH", "Automated Matching", "1"],
          ["Cloud ERP", "PREDICTED_MATCH", "Automated Matching", "1"],
          ["Legacy ERP", "SPECIALIST", "Specialist Review", "2"],
          ["Cloud ERP", "MANUAL_REVIEW", "Specialist Review", "2"],
          ["Legacy ERP", "BUSINESS_REVIEW", "Business Review", "3"],
          ["Cloud ERP", "RECEIPT_ACTION", "Business Review", "3"],
        ],
      },
    ],
    userExperience: {
      intro:
        "The Tableau layer is designed to read as one continuous reporting timeline, with the source-system handoff visible but never treated as a process discontinuity.",
      modules: [
        "Migration timeline — one continuous time axis, colored by source system",
        "100% activity-mix bars — canonical categories colored consistently across both source systems",
        "Source transition marker — a subtle annotation at each business unit's migration boundary",
        "Dynamic narrative — a short generated summary of the largest drivers of month-over-month change",
      ],
    },
    resultsLanguage:
      "The model created a consistent reporting layer across a phased ERP transition. It preserved historical comparability, made the source-selection rule explicit, and supported both trend analysis and activity-mix reporting without counting the same company-month twice.",
    technicalDecisions: [
      {
        title: "Resolve precedence before aggregating",
        explanation: "Combining sources before choosing the authoritative one can introduce duplication; precedence has to be resolved first, at the business-unit/month grain.",
      },
      {
        title: "Harmonize labels before comparing",
        explanation: "A system transition changes category semantics, not just the source. A semantic mapping layer keeps canonical categories comparable across both systems.",
      },
    ],
    challengesAndTradeoffs: [
      "A system transition is not only a source change. Definitions, data structures, and category semantics can change too.",
      "Source precedence is simple to explain but must be applied at the correct grain, or it silently breaks.",
      "Choosing a source before confirming category completeness can hide missing activity.",
      "Dynamic narratives should explain material movements without implying causality the data doesn't establish.",
    ],
    whatILearned: [
      "A migration is rarely just a data-source swap — the categories themselves shift meaning, and a model that only handles the source change will still produce misleading trends.",
      "Making the source-selection decision queryable, rather than leaving it as an implicit filter inside a dashboard, made the model far easier to defend when stakeholders asked 'which system is this number from?'",
    ],
    designNote: {
      heading: "On the dynamic narrative",
      body: [
        "The brief for this project calls for a short, auto-generated sentence summarizing the largest drivers of change each month — for example, noting which canonical category contributed most to a year-over-year shift and when a business unit's reporting source transitioned. That sentence is generated from the underlying synthetic figures for demonstration purposes only; it is not a literal output logged from a production system, and real figures were never used to produce it.",
      ],
    },
    whatThisDemonstrates: [
      "Migration-aware analytical modeling",
      "Source precedence and grain control",
      "SQL window functions",
      "Semantic harmonization",
      "Tableau storytelling",
      "Data-quality controls",
      "Business-facing narrative design",
    ],
    confidentialityNote:
      "Selected enterprise projects completed in a professional setting. Details, interfaces, and data have been anonymized or recreated with synthetic examples to protect confidential information.",
    chart: "erp-migration",
  },

  // ---------------------------------------------------------------------
  // SUPPORTING 4 — Corporate Card Monitoring and Controls Analytics
  // ---------------------------------------------------------------------
  {
    slug: "corporate-card-monitoring",
    order: 4,
    depth: "supporting",
    heroKicker: "Supporting project",
    title: "Corporate Card Monitoring and Controls Analytics",
    cardSummary: "A monitoring framework that compares card usage patterns with assigned limits and surfaces records requiring review.",
    oneSentenceOverview:
      "Built a controls-oriented view of card utilization, spend behavior, and configurable monitoring signals, standing up a reusable analytical model from fragmented periodic files.",
    tags: ["SQL", "Tableau", "Financial Controls", "Risk Analytics", "Spend Analytics"],
    executiveSummary: [
      "Corporate card reporting depended on fragmented periodic files and manual analysis. The objective was to create a reusable analytical view of spend, limits, usage patterns, and potential control exceptions.",
    ],
    businessProblem: {
      heading: "Business problem",
      body: [
        "Corporate card reporting depended on fragmented periodic files and manual analysis. The objective was to create a reusable analytical view of spend, limits, usage patterns, and potential control exceptions.",
      ],
      bullets: [
        "Monthly spend versus credit limit",
        "Average and maximum monthly spend",
        "Utilization ratio",
        "Number of purchases",
        "Repeated transactions or declines within a configurable period",
        "Dormant cards and large changes in spend behavior",
        "Category concentration and potential limit-review candidates",
      ],
    },
    myRole: [
      "I defined the monitoring signals from configurable, fictional thresholds, built the SQL model, and designed the language used to describe exceptions so it stayed descriptive rather than accusatory.",
    ],
    designNote: {
      heading: "Critical wording",
      body: [
        "These are monitoring signals, not accusations of fraud or policy violations. The model intentionally uses 'monitoring signal', 'review candidate', and 'exception for review' — never 'fraud detected', 'noncompliant employee', or any language that makes a personnel judgment.",
      ],
    },
    codeSamples: [
      {
        title: "Monitoring signal query",
        language: "sql",
        code: `SELECT
    cardholder_id,
    month,
    credit_limit,
    total_spend,
    transaction_count,
    decline_count,
    total_spend / NULLIF(credit_limit, 0) AS utilization_ratio,
    CASE
        WHEN total_spend / NULLIF(credit_limit, 0) >= 0.90
            THEN 'Review high utilization'
        WHEN decline_count >= 3
            THEN 'Review repeated declines'
        WHEN transaction_count = 0
            THEN 'Review inactivity'
        ELSE 'No configured signal'
    END AS monitoring_signal
FROM monthly_card_summary;`,
      },
    ],
    syntheticTables: [
      {
        caption: "Synthetic monthly card summary (thresholds are fictional and configurable)",
        columns: ["cardholder_id", "month", "credit_limit", "total_spend", "transaction_count", "decline_count"],
        rows: [
          ["CARDHOLDER-001", "2026-01-01", "10000", "4280.15", "17", "0"],
          ["CARDHOLDER-002", "2026-01-01", "5000", "4875.90", "28", "4"],
          ["CARDHOLDER-003", "2026-01-01", "15000", "980.00", "3", "0"],
        ],
      },
    ],
    resultsLanguage:
      "The analysis brought spend, usage, and credit-limit context into a single monitoring view, enabling reviewers to prioritize cards with unusual or high-utilization patterns instead of assessing every account identically.",
    whatThisDemonstrates: [
      "Risk and controls analytics design",
      "SQL-based monitoring signal logic",
      "Responsible, non-accusatory exception language",
      "Reusable analytical modeling from fragmented source files",
    ],
    confidentialityNote:
      "Selected enterprise projects completed in a professional setting. Details, interfaces, and data have been anonymized or recreated with synthetic examples to protect confidential information.",
    chart: "card-utilization",
  },

  // ---------------------------------------------------------------------
  // SUPPORTING 5 — Conversational Analytics with a Semantic Layer
  // ---------------------------------------------------------------------
  {
    slug: "conversational-analytics",
    order: 5,
    depth: "supporting",
    heroKicker: "Proof of concept",
    title: "Conversational Analytics with a Semantic Layer",
    cardSummary: "A natural-language analytics proof of concept that lets business users ask governed questions over curated procurement and finance data.",
    oneSentenceOverview:
      "Used a governed semantic layer to translate natural-language business questions into analytical queries over curated procurement and finance data.",
    tags: ["Snowflake Cortex Analyst", "Semantic Modeling", "SQL", "Natural Language Analytics", "Governance"],
    executiveSummary: [
      "Business users often needed an analyst to answer common questions even when the underlying data already existed. Direct natural-language querying is only useful if business terms, relationships, metrics, and filters are governed first.",
    ],
    businessProblem: {
      heading: "Business problem",
      body: [
        "Business users often needed an analyst to answer common questions even when the underlying data already existed. Direct natural-language querying is useful only if business terms, relationships, metrics, and filters are governed.",
      ],
    },
    myRole: [
      "I defined the semantic model — approved tables, joins, metric definitions, synonyms, and time dimensions — and prototyped the question-to-SQL flow against curated, governed data.",
    ],
    architecture: [
      ["Business Question"],
      ["Semantic Model (approved tables, joins, metrics, synonyms, time dimensions)"],
      ["Generated SQL"],
      ["Governed Data Warehouse"],
      ["Answer + Query Transparency"],
    ],
    codeSamples: [
      {
        title: "Synthetic semantic-model definition",
        language: "yaml",
        code: `name: procurement_analytics

tables:
  - name: purchase_orders
    base_table: demo.procurement.purchase_orders
    dimensions:
      - name: supplier
        expr: supplier_name
        synonyms: [vendor, partner]
      - name: category
        expr: spend_category
      - name: order_date
        expr: order_date
        data_type: date
    measures:
      - name: ordered_spend
        expr: ordered_amount
        default_aggregation: sum
      - name: invoiced_spend
        expr: invoiced_amount
        default_aggregation: sum`,
      },
    ],
    userExperience: {
      intro: "Example questions the semantic model is designed to answer:",
      modules: [
        "What was ordered spend by category last quarter?",
        "Which suppliers had the greatest increase in invoiced spend?",
        "Show monthly requisition volume for the current year.",
        "Compare ordered and invoiced spend by business unit.",
      ],
    },
    designNote: {
      heading: "Governance principles",
      bullets: [
        "Restrict the model to approved fields.",
        "Define metrics once.",
        "Include synonyms for business language.",
        "Validate generated SQL.",
        "Display filters and assumptions.",
        "Prevent access to sensitive row-level fields.",
        "Provide a safe fallback when the question cannot be answered from the semantic model.",
      ],
    },
    resultsLanguage:
      "The proof of concept demonstrated how a semantic layer can translate business language into governed analytical queries, reducing the gap between operational questions and warehouse data while preserving metric definitions and access controls.",
    whatThisDemonstrates: [
      "Semantic modeling for governed natural-language analytics",
      "Metric and synonym definition design",
      "Query transparency and guardrails",
      "Proof-of-concept scoping and honest labeling",
    ],
    confidentialityNote:
      "Selected enterprise projects completed in a professional setting. Details, interfaces, and data have been anonymized or recreated with synthetic examples to protect confidential information.",
  },

  // ---------------------------------------------------------------------
  // SUPPORTING 6 — Enterprise Finance and Procurement BI
  // ---------------------------------------------------------------------
  {
    slug: "enterprise-bi",
    order: 6,
    depth: "supporting",
    heroKicker: "Supporting project",
    title: "Enterprise Finance and Procurement BI",
    cardSummary: "A collection of interactive decision-support dashboards for spend, requisitions, savings, forecasts, supplier activity, and operational performance.",
    oneSentenceOverview:
      "Designed interactive reporting products for spend, procurement performance, forecasts, and operational metrics, standardized from disparate spreadsheet sources.",
    tags: ["Tableau", "Excel", "SQL", "Data Visualization", "Procurement Analytics", "Finance Analytics"],
    executiveSummary: [
      "A collection of interactive decision-support dashboards for spend, requisitions, savings, forecasts, supplier activity, and operational performance, presented as one multi-dashboard case study rather than a gallery of unrelated charts.",
    ],
    businessProblem: {
      heading: "Business problem",
      body: ["Recurring spreadsheet reporting across spend, procurement performance, and forecasting needed to become interactive and filterable, without losing trust in the underlying numbers."],
    },
    myRole: [
      "I standardized the disparate source files into one data model, built the dashboards, and worked through how refreshability and access needed to change as file count and data volume grew.",
    ],
    userExperience: {
      intro: "Three dashboard stories made up the collection:",
      modules: [
        "Spend analytics — spend by supplier, category, and business unit; monthly trend; top suppliers; ordered vs. invoiced amount",
        "Procurement performance — requisition volume and trend, savings categories, approval/cycle-time metrics, category and supplier concentration",
        "Forecast and operational analytics — budget vs. actual, variance amount and percentage, monthly operational volume, exception trend, dynamic filters and drill-downs",
      ],
    },
    syntheticTables: [
      {
        caption: "Synthetic spend data",
        columns: ["month", "business_unit", "category", "supplier", "ordered_amount", "invoiced_amount"],
        rows: [
          ["2026-01-01", "Unit A", "Software", "Supplier Alpha", "85000", "79250"],
          ["2026-01-01", "Unit A", "Facilities", "Supplier Bravo", "42000", "41800"],
          ["2026-02-01", "Unit B", "Professional Services", "Supplier Charlie", "67000", "63200"],
        ],
      },
    ],
    designNote: {
      heading: "Design lesson",
      bullets: [
        "Who needed the information",
        "What decision the dashboard supported",
        "How disparate files were standardized",
        "How refreshability and user access were managed",
        "How performance degraded as file count and data volume increased",
        "Why a warehouse-backed model is more scalable than many spreadsheet connections",
      ],
    },
    resultsLanguage:
      "The dashboard portfolio converted recurring spreadsheet reporting into interactive, filterable decision-support products. The broader lesson was that visualization quality depends on the reliability, grain, ownership, and refresh strategy of the underlying data model.",
    whatThisDemonstrates: [
      "Multi-dashboard product thinking over isolated charts",
      "Data standardization from disparate spreadsheet sources",
      "Refresh and access-model design",
      "Finance and procurement domain fluency",
    ],
    confidentialityNote:
      "Selected enterprise projects completed in a professional setting. Details, interfaces, and data have been anonymized or recreated with synthetic examples to protect confidential information.",
  },
];
