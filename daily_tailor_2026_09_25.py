"""
Tailoring pass for the 3 jobs scoring >=75 from the 2026-09-25 screen.
Writes tailored_summary, tailored_skills, tailored_resume_bullets into job_analysis.
"""
import sqlite3, json

DB = "job_fetcher.db"
con = sqlite3.connect(DB)

# ─────────────────────────────────────────────────────────────────────────────
# JOB 1: Sailor Health — Founding Data & Analytics Engineer (82)
#
# Company type: 25-person healthcare AI startup (NYC, Soho office). Founder context:
# move fast, build from scratch, own everything. Recruiters scan for:
# "founding", "greenfield", "from scratch", "Snowflake + dbt", "Python", "AI/ML",
# "clinical outcomes", "EHR", "autonomy", "product-minded engineer"
#
# Tailoring strategy: lead with Career Intelligence Platform (most directly analogous —
# greenfield AI system built from scratch, Snowflake+dbt+Python+LLM APIs). Then Allegis
# AI work. Use "data stack from scratch", "clinical" framing where honest (outcome
# tracking / data-quality monitoring is analogous). Don't claim FHIR/EHR.
# ─────────────────────────────────────────────────────────────────────────────

SAILOR_SUMMARY = "Analytics & AI Engineer with hands-on experience building Snowflake + dbt data stacks from greenfield, shipping autonomous LLM pipelines, and delivering AI-powered data products used in production. Built a full career-intelligence platform (Python, FastAPI, LLM APIs, vector search, Snowflake) from scratch as a solo founder-engineer; at Allegis Group, designed Snowflake semantic layers, dbt transformation frameworks, and an AI-powered AP audit platform (Snowflake Cortex) that eliminated 85% of manual review work. Driven by direct, high-ownership roles where data engineering connects directly to outcomes."

SAILOR_SKILLS = [
    "Snowflake", "dbt", "SQL", "Python", "FastAPI", "LLM APIs",
    "OpenAI APIs", "Gemini API", "Vector Search", "REST APIs", "GitHub Actions",
    "CI/CD", "Streamlit", "Data Modeling", "Semantic Layers", "Data Quality Monitoring",
    "ELT Architecture", "Workflow Automation", "LLM Observability", "RAGAS", "LangFuse"
]

# Bullets: ordered most-relevant-first for a healthcare AI startup building from scratch.
# All XYZ format: result first, method second. No bolding.
# Company-tone: startup/founder verbs (Built, Cut, Achieved, Improved, Validated, Drove)
SAILOR_BULLETS = [
    {
        "company": "Career Intelligence Platform (personal project, in progress)",
        "bullets": [
            "Cut manual research effort ~70% and grew to 10+ active users by building and shipping an AI-powered career intelligence platform (Python, Next.js, SQL, vector search, LLM APIs) that scores 10,000+ job postings — designed as a greenfield Snowflake + dbt + Python data stack built from scratch.",
            "Achieved zero manual intervention per job by designing a self-correcting, autonomous LLM agent pipeline that scrapes, scores, and applies to postings end-to-end.",
            "Improved resume-job alignment ~50% by building AI-driven evaluation pipelines that generate fit scores and skill-gap analyses from unstructured text.",
            "Prevented quality and pipeline regressions before production by building an LLM evaluation and observability harness (FastAPI, RAGAS, LangFuse, PostHog) with 50+ automated test cases.",
            "Validated sub-3-second P95 API response times under load by deploying the platform to AWS (ECS Fargate, RDS/pgvector, Terraform) with CI/CD and autoscaling."
        ]
    },
    {
        "company": "Allegis Group",
        "bullets": [
            "Minimized manual invoice review by 85% by building an AI-powered AP audit platform (Snowflake Cortex, Python, Streamlit) that reconciles invoices against payments and auto-clears compliant transactions.",
            "Delivered governed, trusted datasets across finance reporting domains by building Snowflake/dbt transformation workflows with dimensional modeling, automated data-quality testing, and Git-based CI/CD.",
            "Cut report generation time from 10 hours to a couple of clicks by leading a PeopleSoft-to-Oracle Fusion ERP migration across 11 companies, building Snowflake/dbt reconciliation frameworks.",
            "Built 7 Streamlit dashboards used by 3 teams across legacy and modern ERP systems by designing reusable Snowflake semantic layers for payments, lockbox, cash application, and Treasury analytics.",
            "Cut procurement review prep effort by 80% by building automated data-quality pipelines in Python, SQL, and Snowflake to validate contract ingestion and detect anomalies.",
            "Drove self-service analytics adoption across 300+ employees by delivering AI and analytics enablement sessions."
        ]
    },
    {
        "company": "KPMG",
        "bullets": [
            "Increased operational efficiency 50% by migrating data from 1,900 vendors across multiple SKUs.",
            "Recommended targeted solutions to the Chief Transformation Officer of one of the largest banks in the Middle East by conducting an ITIL gap analysis.",
            "Increased outsourced operational value 12% via a Global Capability Centre overhaul by leading an action plan that enabled the world's largest digital automation firm to adopt Industry 4.0 tech (IoT, AI, VR)."
        ]
    }
]

# ─────────────────────────────────────────────────────────────────────────────
# JOB 2: Koch Data Engineer (78)
#
# Company type: Koch Industries family (large, private, Wichita KS, Market-Based-Management
# culture). Koch recruiters scan for: "ownership", "data products", "ELT", "Snowflake",
# "dbt", "AI-ready data", "Snowflake Cortex", "Claude Code", "entity resolution",
# "cross-system reconciliation", "business stakeholder partnership", "entrepreneurial",
# "results-oriented". Koch explicitly named Claude Code and Snowflake Cortex in JD.
# Multiple Koch job posts consistently emphasize "ownership" and "entrepreneur mentality."
#
# Tailoring: lead with ERP reconciliation / cross-system work (exact match to "multi-ERP
# entity resolution" and "cross-system reconciliation"). Then AI-ready / Cortex bullets.
# Mirror "data product" and "deliver and own" framing from JD.
# ─────────────────────────────────────────────────────────────────────────────

KOCH_SUMMARY = "Analytics Engineer with a track record of owning and delivering Snowflake + dbt data products end-to-end — from ELT pipeline design and ERP reconciliation frameworks to AI-ready semantic layers and automated data-quality testing. At Allegis Group, led a PeopleSoft-to-Oracle Fusion migration across 11 companies using Snowflake, dbt, and Git-based CI/CD; built an AI-powered audit platform with Snowflake Cortex; and delivered 22+ dashboards across Treasury, Procurement, and Finance. Employee of the Year and Rising Star Award recipient."

KOCH_SKILLS = [
    "Snowflake", "dbt", "SQL", "Python", "ELT Architecture", "CI/CD", "Git",
    "GitHub Actions", "Dimensional Modeling", "Data Modeling", "Semantic Layers",
    "Data Quality Monitoring", "Reconciliation Logic", "Source-to-Target Mapping",
    "Snowflake Cortex", "Databricks", "MLflow", "Streamlit",
    "Oracle Fusion", "PeopleSoft", "ERP Migration", "KPI Standardization",
    "Workflow Automation", "Anomaly Detection", "REST APIs"
]

# XYZ format. Koch tone: ownership / results / entrepreneurial verbs.
KOCH_BULLETS = [
    {
        "company": "Allegis Group",
        "bullets": [
            "Cut report generation time from 10 hours to a couple of clicks by leading a PeopleSoft-to-Oracle Fusion ERP migration across 11 companies, building Snowflake/dbt reconciliation frameworks.",
            "Aligned reporting definitions across 5 systems and domains (PeopleSoft, Oracle Fusion, Treasury, Procurement, and Finance) by developing canonical data models and KPI harmonization frameworks.",
            "Delivered governed, trusted datasets across finance reporting domains by building Snowflake/dbt transformation workflows with dimensional modeling, automated data-quality testing, and Git-based CI/CD.",
            "Minimized manual invoice review by 85% by building an AI-powered AP audit platform (Snowflake Cortex, Python, Streamlit) that reconciles invoices against payments and auto-clears compliant transactions.",
            "Cut procurement review prep effort by 80% by building automated data-quality pipelines in Python, SQL, and Snowflake to validate contract ingestion and detect anomalies.",
            "Built 7 Streamlit dashboards used by 3 teams by designing reusable Snowflake semantic layers — enabling self-serve analytics across legacy and modern ERP systems.",
            "Cut query execution time by 40%, speeding up executive dashboards, by optimizing Snowflake data models and SQL transformations.",
            "Eliminated a recurring manual process with 100% testing accuracy by embedding with stakeholders to diagnose it, then building and handing off an AI proof-of-concept (Snowflake Cortex, Databricks, MLflow, LLMs)."
        ]
    },
    {
        "company": "Career Intelligence Platform (personal project, in progress)",
        "bullets": [
            "Cut manual research effort ~70% and grew to 10+ active users by building and shipping an AI-powered career intelligence platform (Python, Next.js, SQL, vector search, LLM APIs) that scores 10,000+ job postings.",
            "Achieved zero manual intervention per job by designing a self-correcting, autonomous LLM agent pipeline that scrapes, scores, and applies to postings end-to-end.",
            "Enabled natural-language querying from any MCP-compatible AI client by building and deploying an MCP server that exposes job-search and scoring data as callable tools."
        ]
    },
    {
        "company": "KPMG",
        "bullets": [
            "Increased operational efficiency 50% by migrating data from 1,900 vendors across multiple SKUs.",
            "Improved a client's projected IT infrastructure efficiency 50% over 5 years by developing 70 targeted recommendations.",
            "Improved resource utilization 15% and reduced operations cost 5% by streamlining a digital transformation PMO using Agile."
        ]
    }
]

# ─────────────────────────────────────────────────────────────────────────────
# JOB 3: Eurasia Group — Data Analyst, Finance and Business Insights (78)
#
# Company type: mid-size global research/advisory firm (~200-400 people). Not a
# large enterprise. Standard JD tailoring applies (single JD signal is reliable).
# JD keywords: "SQL and dbt", "Git-based workflows", "CI/CD", "Power BI",
# "finance and business acumen", "FP&A, commercial, revenue operations",
# "self-starter", "independent ownership", "80/20 mindset",
# "translate vague ideas into business questions", "stakeholder partnership",
# "professional services analytics."
#
# Tailoring strategy: lead with finance analytics + dbt + stakeholder ownership.
# Mirror "finance and business insights", "scalable data models", "stakeholder partnership".
# Note Tableau as equivalent to Power BI (explicitly listed as preferred, not required).
# ─────────────────────────────────────────────────────────────────────────────

EURASIA_SUMMARY = "Finance Analytics Engineer with hands-on SQL + dbt + Git CI/CD experience building governed reporting layers, finance data products, and stakeholder-facing dashboards. At Allegis Group, partnered directly with Finance, Treasury, and Procurement stakeholders to translate ambiguous business problems into scalable Snowflake + dbt analytical solutions — delivering 22+ dashboards and driving self-service analytics adoption across 3 teams. Strong finance and business acumen developed across ERP migration, cash flow forecasting, and corporate card spend analytics. Self-starting ownership model; no day-to-day oversight needed."

EURASIA_SKILLS = [
    "SQL", "dbt", "Git", "CI/CD", "GitHub Actions", "Snowflake",
    "Python", "Tableau", "Streamlit",
    "Dimensional Modeling", "Data Modeling", "Semantic Layers",
    "Reconciliation Logic", "KPI Standardization", "Data Lineage",
    "ERP Migration", "Treasury Analytics", "Procurement Analytics",
    "Spend Analytics", "Executive Reporting", "Dashboard Development",
    "Stakeholder Management", "Workflow Automation"
]

# XYZ format. Eurasia Group is an advisory/research firm — tone: analytical, precise,
# independent, "translate ambiguity into insight". Verbs: Delivered, Aligned, Secured,
# Enabled, Identified, Built.
EURASIA_BULLETS = [
    {
        "company": "Allegis Group",
        "bullets": [
            "Delivered governed, trusted datasets across finance reporting domains by building Snowflake/dbt transformation workflows with dimensional modeling, automated data-quality testing, and Git-based CI/CD.",
            "Aligned reporting definitions across 5 systems and domains (PeopleSoft, Oracle Fusion, Treasury, Procurement, and Finance) by developing canonical data models and KPI harmonization frameworks.",
            "Enabled 3 teams to self-serve standardized metrics via Tableau, eliminating ad hoc data requests, by building finance data products on governed Snowflake semantic layers.",
            "Identified $9M+ in savings opportunities by building a Snowflake-based corporate card analytics platform processing 10M+ transactions, using automated alerting and spend monitoring.",
            "Secured 4 weeks of forward visibility into incoming vendor cash flow by building a Tableau-based cash flow forecasting model for Allegis Group Treasury.",
            "Cut report generation time from 10 hours to a couple of clicks by leading a PeopleSoft-to-Oracle Fusion ERP migration across 11 companies, building Snowflake/dbt reconciliation frameworks.",
            "Reduced manual validation effort by 60% and improved auditability of downstream reporting by building automated data-quality and testing frameworks.",
            "Cut query execution time by 40%, speeding up executive dashboards, by optimizing Snowflake data models and SQL transformations."
        ]
    },
    {
        "company": "Career Intelligence Platform (personal project, in progress)",
        "bullets": [
            "Improved resume-job alignment ~50% by building AI-driven evaluation pipelines that generate fit scores and skill-gap analyses from unstructured resumes and job descriptions.",
            "Cut prospect-research time per lead from minutes to seconds by building a GTM automation engine (Apollo API, Clay/Clearbit, Claude-driven personalization) that processed 1,000+ prospects across ICP segments."
        ]
    },
    {
        "company": "KPMG",
        "bullets": [
            "Recommended targeted solutions to the Chief Transformation Officer of one of the largest banks in the Middle East by conducting an ITIL gap analysis.",
            "Increased operational efficiency 50% by migrating data from 1,900 vendors across multiple SKUs.",
            "Improved resource utilization 15% and reduced operations cost 5% by streamlining a digital transformation PMO using Agile."
        ]
    }
]

# ─────────────────────────────────────────────────────────────────────────────
# Write tailoring to DB
# ─────────────────────────────────────────────────────────────────────────────

updates = [
    (
        "sailor_health_founding_data_analytics_engine_96b7896310",
        SAILOR_SUMMARY, json.dumps(SAILOR_SKILLS), json.dumps(SAILOR_BULLETS)
    ),
    (
        "koch_data_engineer_b0cbcf6ef6",
        KOCH_SUMMARY, json.dumps(KOCH_SKILLS), json.dumps(KOCH_BULLETS)
    ),
    (
        "eurasia_group_data_analyst_finance_and_busin_050a3c6dae",
        EURASIA_SUMMARY, json.dumps(EURASIA_SKILLS), json.dumps(EURASIA_BULLETS)
    ),
]

for job_id, summary, skills, bullets in updates:
    con.execute("""
        UPDATE job_analysis
        SET tailored_summary = ?,
            tailored_skills = ?,
            tailored_resume_bullets = ?,
            processed_at = datetime('now')
        WHERE job_id = ?
    """, (summary, skills, bullets, job_id))
    print(f"Tailored: {job_id}")

con.commit()

# Verify
for job_id, _, _, _ in updates:
    row = con.execute("""
        SELECT ja.match_score, ja.tailored_summary IS NOT NULL, j.title, j.company
        FROM job_analysis ja JOIN jobs j ON j.job_id=ja.job_id
        WHERE ja.job_id=?
    """, (job_id,)).fetchone()
    print(f"  ✓ {row[3]} — {row[2]}: score={row[0]}, tailored={bool(row[1])}")

con.close()
