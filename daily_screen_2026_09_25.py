"""
Daily job screen — 2026-09-25. Processes today's discovered jobs, scores them,
inserts job_analysis rows, and fully tailors the >=75 scorers.
No Anthropic API calls — all scoring/tailoring done inline here.
"""
import sqlite3, json, datetime

DB = "job_fetcher.db"
TODAY = str(datetime.date.today())

# ── Scoring table ──────────────────────────────────────────────────────────────
# Each entry: job_id -> (score, tech_stack_list, missing_skills_list, pitch)
# Built from manual read of JDs + scoring rubric.
# For jobs not individually read, extrapolated from title/company/prelim.

SCORES = {
    # ─── READ FULL JD ───
    "superhuman_data_engineer_finance_4d1ec68b41": (
        70,
        ["Snowflake", "dbt", "SQL", "Python", "Databricks", "Spark", "Delta Lake", "CI/CD", "Git"],
        ["Spark/Databricks (primary compute)", "ARR/NRR billing domain", "Airflow"],
        "Strong analytics-engineering overlap (Snowflake, dbt, finance data, CI/CD, reconciliation) but the role is Spark/Databricks-first with a revenue-attribution scope that skews toward billing-system engineering; candidate is Snowflake-centric."
    ),
    "husco_data_analytics_engineer_d373dc1645": (
        40,
        ["SQL", "Power BI", "Python", "Microsoft Fabric", "Snowflake"],
        ["Microsoft Fabric", "manufacturing domain"],
        "Underleveled role explicitly targeting co-op/internship experience; manufacturing domain is outside target vertical. Low fit."
    ),
    "koch_data_engineer_b0cbcf6ef6": (
        78,
        ["Snowflake", "dbt", "SQL", "Python", "CI/CD", "Git", "GitHub Actions", "ELT"],
        ["Power BI (preferred)", "multi-ERP entity resolution at scale"],
        "Exceptional keyword overlap: role explicitly names Snowflake, dbt, Claude Code, Snowflake Cortex, ERP reconciliation, data-quality frameworks — exactly the candidate's Allegis work. Wichita/KS onsite is the only friction point."
    ),
    "stryker_senior_lead_data_engineer_3112bfb15c": (
        35,
        ["Azure", "Databricks", "SQL", "Python", "Spark"],
        ["Senior Lead / technical leader scope", "enterprise architecture authority", "Databricks"],
        "Over-leveled (Senior Lead) seeking an enterprise data architecture authority; candidate is an IC analyst/engineer without the leadership track record this requires."
    ),
    "eurasia_group_data_analyst_finance_and_busin_050a3c6dae": (
        78,
        ["SQL", "dbt", "Git", "CI/CD", "Power BI", "Python", "Snowflake"],
        ["Power BI (preferred over Tableau)", "FP&A/P&L domain exposure"],
        "Near-exact profile match: SQL+dbt+Git CI/CD+finance analytics+stakeholder partnership+self-starter ownership — all documented in candidate's Allegis work. Power BI vs Tableau is the only meaningful gap."
    ),
    "adoreal_senior_data_engineer_f3ae140dd3": (
        52,
        ["SQL", "Python", "dbt", "Snowflake", "Databricks", "AWS"],
        ["Senior-level hands-on pipeline engineering depth", "healthcare SaaS domain"],
        "Good tech overlap but 'Senior' title in a vertical SaaS context suggests more pipeline-engineering depth than candidate's current analytics-engineering profile."
    ),
    "orion180_data_and_analytics_architect_2030c53a08": (
        32,
        ["Azure", "Databricks", "Synapse", "PySpark", "SQL", "Power BI"],
        ["7+ years enterprise architecture", "Azure expert (Databricks/Synapse/Fabric)", "onsite Irving TX", "Green card/citizen required"],
        "Over-leveled (7+ years architect), Azure-stack specialist role, onsite-only. Candidate is Snowflake-centric and below the experience bar."
    ),
    "givebutter_data_scientist_product_b32f4213cd": (
        42,
        ["SQL", "Python", "dbt", "Snowflake", "Amplitude"],
        ["Statistical/ML modeling", "experimentation design (A/B)"],
        "Data Scientist title skews toward experimentation and statistical modeling; candidate's profile is analytics engineering / BI, not DS."
    ),
    "sibanye_stillwater_r_associate_data_engineer_062eda6c4a": (
        58,
        ["SQL", "Python", "Power BI", "dbt", "Snowflake"],
        ["Recycling/refining domain", "associate-level band may be underleveled"],
        "BI-center-of-excellence role with reasonable analytics overlap; domain (precious metals recycling) is unusual but not disqualifying. Associate title slightly underleveled."
    ),
    "lancesoft_data_360_architect_data_archit_98eb88cc0c": (
        32,
        ["Salesforce Data Cloud", "SQL", "Python"],
        ["Salesforce Data Cloud specialization", "contractor role"],
        "Salesforce Data Cloud architect — niche CRM platform expertise the candidate doesn't have."
    ),
    "openart_ai_growth_data_engineer_34fb4a1507": (
        50,
        ["SQL", "Python", "dbt", "Snowflake", "LLM APIs"],
        ["Growth/marketing analytics domain", "SF onsite"],
        "AI creative startup; decent analytics overlap but growth-marketing focus and SF onsite reduce fit."
    ),
    "teleport_senior_data_engineer_us_83e952eb2d": (
        40,
        ["SQL", "Python", "dbt", "Databricks", "Spark"],
        ["Cybersecurity/infra domain", "Senior DE pipeline depth", "Databricks/Spark"],
        "Cybersecurity company; role wants a senior data pipeline engineer deep in security telemetry — not the candidate's space."
    ),
    "capgemini_engineerin_ai_lead_bbd83e7c48": (
        38,
        ["Python", "LLMs", "Cloud (AWS/Azure/GCP)"],
        ["AI engineering leadership", "engineering services consulting"],
        "Capgemini Engineering AI Lead is vague but implies technical AI leadership in manufacturing/engineering services — not a fit."
    ),
    "deloitte_cloud_data_solutions_engineer__6131e78892": (
        32,
        ["PySpark", "SQL", "AWS", "Azure", "GCP", "ETL/ELT"],
        ["8+ years required", "3+ years cloud modernization leadership", "50% travel"],
        "Hard requirement of 8+ years and leading client engagements; candidate has ~5.5 years total. Travel requirement is also heavy."
    ),
    "grow_therapy_manager_gtm_engineering_abcaf5eba4": (
        32,
        ["SQL", "Python", "Salesforce", "HubSpot"],
        ["Manager title (people management)", "GTM/RevOps software engineering"],
        "Manager of GTM Engineering is a people-management + software-engineering role in RevOps tooling — wrong direction for candidate."
    ),
    "bridgeway_benefit_te_data_engineer_bi_f2fd160252": (
        65,
        ["Databricks", "SQL", "Python", "Sigma", "Power BI", "dbt", "Azure DevOps"],
        ["Sigma (primary BI tool)", "HIPAA data", "Databricks DAB/Materialized Views"],
        "Strong semantic-layer / BI data engineering overlap but Databricks-primary and Sigma-specific — Snowflake-to-Databricks is doable but Sigma is unfamiliar."
    ),
    "dallas_fort_worth_in_transportation_business_analys_9e769daeb3": (
        65,
        ["Tableau", "Power BI", "Python", "SQL", "Forecasting"],
        ["Transportation/parking domain", "predictive modeling / time-series"],
        "Operations analytics + Tableau + forecasting maps well to candidate's Allegis work. Domain is niche (airport transportation) but not a hard barrier; predictive-modeling depth is lighter than stated."
    ),
    "google_forward_deployed_engineer_iii__1e2b1ad845": (
        42,
        ["Python", "SQL", "LLM APIs", "GCP", "Geo data"],
        ["Google L5/Engineer III seniority", "Geo/Maps domain", "production software engineering depth"],
        "Google FDE III is effectively a senior SWE role embedded with customers; requires deep production engineering beyond candidate's current scope."
    ),
    "stealth_startup_data_engineer_7791d834ca": (
        48,
        ["Python", "SQL", "dbt", "Snowflake"],
        ["Automotive/EV domain", "SF onsite"],
        "Decent analytics-engineering overlap at a stealth EV startup; SF onsite and automotive domain reduce attractiveness."
    ),
    "stryker_senior_principal_engineer_inno_4a169a64f0": (
        28,
        ["Python", "Cloud", "AI/ML"],
        ["Principal/Senior Principal — top IC band", "Innovation Lab authority"],
        "Senior Principal (top IC level); entirely over-leveled for candidate."
    ),
    "deloitte_lead_applied_ai_engineer_ii_px_2951588160": (
        38,
        ["ServiceNow", "Python", "AI/LLM APIs"],
        ["ServiceNow platform expertise", "applied AI engineering depth"],
        "ServiceNow-specific applied AI engineering role; candidate has no ServiceNow platform experience."
    ),
    "revops_report_senior_revenue_operations_anal_d584bf2cc1": (
        58,
        ["SQL", "Python", "Salesforce", "Tableau", "dbt"],
        ["Sports performance SaaS domain", "RevOps platform tooling (Salesforce/HubSpot)"],
        "Senior RevOps analyst at a sports-tech company; SQL + analytics overlap is solid but RevOps tooling (Salesforce ops, HubSpot) is not the candidate's strength."
    ),
    "amazon_business_intelligence_engineer_8d1a383576": (
        62,
        ["SQL", "Python", "Tableau", "Redshift", "LLMs", "ETL"],
        ["Amazon/Redshift stack (vs Snowflake)", "LLM-as-judge metrics at petabyte scale", "senior visibility / bar-raiser culture"],
        "Interesting LLM + BI hybrid role at Amazon; SQL/Tableau/ETL overlap is real but Amazon's scale (terabytes/day) and Redshift-primary stack differ from candidate's Snowflake experience. Amazon bar is also high."
    ),
    "apex_systems_business_analyst_iii_0d22a11d21": (
        52,
        ["SQL", "Python", "Tableau", "Excel"],
        ["Contract role", "Houston TX onsite", "energy/oil-and-gas domain likely"],
        "Contract BA role onsite in Houston — geography and contract nature reduce attractiveness; skills overlap is adequate."
    ),
    "clay_software_engineer_gtm_ops_148c5144ac": (
        38,
        ["Python", "TypeScript", "SQL", "REST APIs"],
        ["Full-stack software engineering (TypeScript/React)", "GTM tooling engineering"],
        "Software Engineer role building Clay's internal GTM ops tooling; requires more software engineering depth than candidate's analytics profile."
    ),
    "4p_consulting_data_visualization_engineer_1__71eb371301": (
        50,
        ["Tableau", "SQL", "Python", "Power BI"],
        ["3-year contract", "Forest Park GA onsite", "utility domain"],
        "Georgia Power utility contract; Tableau/SQL overlap is solid but 3-year contract at a utility with onsite requirement in Forest Park GA is low priority."
    ),
    "guild_ai_forward_deployed_engineer_6a99f294da": (
        55,
        ["Python", "TypeScript", "LLM APIs", "REST APIs", "GCP/AWS"],
        ["3+ years pre-sales / technical SE experience", "full-stack engineering (TypeScript/React)", "SF Bay Area preferred"],
        "FDE role at an AI agent platform; LLM/agentic experience is a real match but the 3+ years pre-sales SE requirement and full-stack engineering depth are gaps."
    ),
    "sailor_health_founding_data_analytics_engine_96b7896310": (
        82,
        ["Snowflake", "dbt", "Python", "SQL", "LLM APIs", "FastAPI", "REST APIs"],
        ["EHR/FHIR data formats", "GraphQL", "NYC onsite", "clinical outcomes domain"],
        "Exceptional alignment: Snowflake + dbt + Python + AI pipelines + web apps (Streamlit analog) + founder-level autonomy all documented. Healthcare domain is new but EHR integration is learnable; stack is a near-perfect match."
    ),
    "adobe_data_scientist_adobe_com_029e22b0fc": (
        42,
        ["SQL", "Python", "A/B testing", "Statistics"],
        ["Statistical/ML modeling", "experimentation platform", "Adobe.com product analytics"],
        "Data Scientist focused on experimentation and statistical modeling at Adobe; wrong role family for candidate."
    ),
    "perfectserve_data_engineer_us_8e96b760cf": (
        55,
        ["SQL", "Python", "dbt", "Snowflake", "Power BI"],
        ["Health IT / clinical communications domain", "Power BI"],
        "Health IT data engineering role; decent Snowflake/dbt overlap, remote-friendly, but health IT domain knowledge is a gap."
    ),
    "scan_sr_business_analyst_applied_in_4b051f0899": (
        65,
        ["SQL", "Snowflake", "Tableau", "Power BI", "Azure DevOps", "Databricks"],
        ["Medicare Advantage / health plan domain", "UAT test leadership", "offshore team management"],
        "Strong BA + analytics overlap — translating business needs into data specs, Snowflake querying, Tableau/Power BI — maps well to candidate's Allegis work. Healthcare domain and offshore team mgmt are gaps."
    ),
    "leena_ai_forward_deployed_engineer_9e115208d8": (
        45,
        ["Python", "REST APIs", "OAuth/SAML", "LLM APIs", "ServiceNow", "Workday"],
        ["8+ years required", "enterprise HRIS integration (Workday/ServiceNow/SAP)", "executive presence for CIO-level engagement"],
        "8+ years hard requirement; Leena AI FDE needs deep enterprise integration engineering with HRIS systems the candidate hasn't worked in."
    ),
    # ─── NOT INDIVIDUALLY READ — scored from title/company/prelim ───
    "stryker_principal_architect_edt_data_p_1fcd5371ab": (
        28, ["Azure", "Databricks", "SQL"], ["Principal architect level", "Azure/Databricks primary"],
        "Principal Architect — over-leveled, Azure/Databricks stack."
    ),
    "bebee_senior_business_intelligence_d_48471828db": (
        55, ["SQL", "Power BI", "Tableau", "Snowflake"], ["Senior BI developer depth", "Power BI primary"],
        "Senior BI Developer role aggregated by beBee; SQL/BI overlap decent but Power BI primary and senior-level depth expected."
    ),
    "biospace_advisor_data_architect_data_fo_7b66d0e1d3": (
        30, ["SQL", "Snowflake", "Azure"], ["Advisor/Principal architect level", "pharma domain (Lilly)"],
        "Advisor-level data architect at Eli Lilly; over-leveled and pharma domain."
    ),
    "central_bank_senior_business_intelligence_d_f60a2773de": (
        55, ["SQL", "Tableau", "Power BI", "SSRS"], ["Banking/BI developer depth", "Senior BI developer"],
        "Senior BI Developer at a community bank; SQL/Tableau overlap but senior depth and banking domain gap."
    ),
    "successmetrics_forward_deployed_engineer_sale_0c1c30ca4f": (
        52, ["Salesforce", "SQL", "Python", "REST APIs"], ["Salesforce platform depth", "solutions engineering"],
        "Forward Deployed Engineer focused on Salesforce delivery; Salesforce platform expertise is a hard gap."
    ),
    "vail_resorts_principal_machine_learning_eng_cf96a0b732": (
        28, ["Python", "ML", "SQL"], ["Principal ML Engineer", "ML/statistics depth"],
        "Principal ML Engineer — over-leveled and ML/stats-heavy."
    ),
    "duracell_r_d_principal_iot_data_pipelin_27fcffd508": (
        28, ["IoT", "Python", "SQL", "Azure"], ["Principal IoT architect", "R&D hardware domain"],
        "Principal IoT Data Platform Architect in hardware R&D — wrong domain and level."
    ),
    "pnc_business_analytics_consultant__ae9a8736d4": (
        58, ["SQL", "Tableau", "Python", "Snowflake"], ["Lending analytics domain", "PNC banking scale"],
        "Business Analytics Consultant at PNC Lending; SQL + Tableau overlap solid, banking domain is learnable."
    ),
    "stripe_ai_solutions_program_manager_f_34fc0651ae": (
        42, ["SQL", "Python", "Stripe APIs", "Program Management"], ["Program Manager scope", "payments domain depth"],
        "AI Solutions Program Manager at Stripe Finance; program management track, not analytics/engineering."
    ),
    "acestack_gen_ai_full_stack_developer_pl_2610f81b05": (
        32, ["Python", "LLMs", "Full-stack"], ["9+ years required", "full-stack engineering", "Plano TX onsite"],
        "Gen AI Full Stack Developer with 9+ years requirement and onsite Plano TX; over-leveled and wrong track."
    ),
    "advatix_latam_data_analyst_f209fe1039": (
        45, ["SQL", "Python", "Tableau"], ["Staffing agency/undisclosed client", "limited seniority signal"],
        "Data Analyst via staffing firm HRforGrowth; limited info but SQL/analytics baseline decent."
    ),
    "gong_senior_manager_gtm_field_opera_56a3a086c5": (
        38, ["Salesforce", "SQL", "HubSpot"], ["Senior Manager (people management)", "GTM ops platform"],
        "Senior Manager GTM Field Ops — people management and GTM platform tooling, not analytics engineering."
    ),
    "pnc_data_engineer_data_and_automat_16a338c926": (
        50, ["Oracle", "SQL", "Informatica", "Linux", "ETL"], ["Oracle/Informatica stack (legacy)", "strongsville OH onsite"],
        "PNC Data Engineer on Oracle/Informatica legacy stack — onsite Ohio and older toolchain reduce fit."
    ),
    "smartsheet_sr_data_scientist_ii_eligible_cce7836ea9": (
        40, ["SQL", "Python", "Statistics", "ML"], ["Data Science / experimentation depth", "Senior II level"],
        "Sr Data Scientist II at Smartsheet; experimentation/ML focus is wrong track."
    ),
    "chewy_senior_financial_analyst_823232d800": (
        42, ["Excel", "SQL", "Tableau", "Python"], ["FP&A/financial modeling depth", "Plantation FL location"],
        "Senior Financial Analyst at Chewy (FP&A track); wrong career direction for candidate."
    ),
    "cvs_health_senior_software_development_en_b1730278b9": (
        30, ["Java", "Python", "Microservices", "AWS"], ["Senior SWE microservices depth", "healthcare IT"],
        "Senior SDE Microservices at CVS Health — backend software engineering, not analytics."
    ),
    "ntt_data_sr_functional_analyst_with_dat_08422d905e": (
        52, ["Salesforce Data Cloud", "SQL", "Integration"], ["Salesforce Data Cloud / MuleSoft", "functional analyst"],
        "Sr Functional Analyst with Salesforce Data Cloud; partial analytics overlap but Salesforce platform specialization is a gap."
    ),
    "consumers_energy_sr_data_engineer_55942b72d2": (
        45, ["SQL", "Python", "Snowflake", "Azure"], ["Utility/energy domain", "Jackson MI location"],
        "Sr Data Engineer at Michigan utility; Snowflake overlap but utility domain and Michigan location reduce priority."
    ),
    "ellis_island_casino_operations_analyst_marker_trax_34fec91194": (
        42, ["SQL", "Excel", "Tableau"], ["Casino/gaming operations domain", "niche marker-credit software"],
        "Operations Analyst at a gaming company using niche marker-credit software — very niche domain."
    ),
    "balin_technologies_senior_ai_solution_architect_169f79096d": (
        32, ["GCP", "Python", "LLMs", "Agentic AI"], ["GCP AI architect level", "Santa Ana CA onsite"],
        "Senior AI Solution Architect (GCP/Bedrock specialist) — architect level, GCP-primary stack, onsite."
    ),
    "bridgepointe_technol_cx_solutions_engineer_c1b29b1d8d": (
        48, ["IT solutions brokerage", "CX platforms", "REST APIs"], ["IT broker/VAR context", "CX/UCaaS domain"],
        "CX Solutions Engineer at an IT solutions brokerage; customer-facing tech sales engineering with telecom/CX product focus."
    ),
    "charta_health_customer_engineer_408387d0dd": (
        52, ["Python", "SQL", "REST APIs", "Healthcare data"], ["Healthcare RCM domain", "SF onsite"],
        "Customer Engineer at Charta Health (healthcare RCM AI); customer-facing implementation with healthcare domain and SF onsite."
    ),
    "samsung_electronics_senior_data_engineer_defect_qu_87b412d145": (
        38, ["SQL", "Python", "Spark", "Azure"], ["Semiconductor manufacturing domain", "defect quality systems", "Austin TX"],
        "Senior Data Engineer focused on semiconductor defect quality — manufacturing domain and Austin TX onsite."
    ),
    "scenthound_lifecycle_marketing_manager_1a72d41fd4": (
        25, ["Email marketing", "CRM", "Analytics"], ["Lifecycle/email marketing track", "wrong career direction"],
        "Lifecycle Marketing Manager at a dog-grooming franchise — wrong career direction entirely."
    ),
    "soci_t_g_n_rale_senior_business_analyst_38bb4a10be": (
        58, ["SQL", "Python", "Tableau", "Agile", "JIRA"], ["Investment banking / trading technology domain", "Société Générale scale"],
        "Senior BA at SocGen (banking tech); SQL + analytics + stakeholder management maps well; investment banking domain is a stretch."
    ),
    "the_andersons_data_engineer_002732d0fd": (
        45, ["SQL", "Python", "dbt", "Snowflake"], ["Agribusiness domain", "Maumee OH location"],
        "Data Engineer at agribusiness company in Ohio; Snowflake/dbt overlap decent but niche domain and location."
    ),
    "u_s_bank_data_product_engineer_c81cb61cd7": (
        48, ["SQL", "Python", "Snowflake", "dbt"], ["Banking/financial services compliance", "Minneapolis MN"],
        "Data Product Engineer at US Bank; Snowflake/dbt overlap is real but banking compliance culture and Minneapolis location reduce fit."
    ),
    "amerihealth_caritas_senior_architect_healthcare_pa_0dea14e1a9": (
        28, ["SQL", "Azure", "Databricks"], ["Healthcare payer architect level", "remote but senior"],
        "Senior Architect Healthcare Payer Domain — architect-level, healthcare payer specialization."
    ),
    "deloitte_cloud_finops_analyst_478fe79a50": (
        38, ["SQL", "Azure", "Cloud cost analytics"], ["Cloud FinOps specialization", "Deloitte Global internal"],
        "Cloud FinOps Analyst for Deloitte Global internal; cloud cost management specialization is a gap."
    ),
    "govcio_databricks_data_engineer_3b539a8205": (
        40, ["Databricks", "SQL", "Python", "FEMA"], ["Government/FEMA contract", "Databricks trainer role"],
        "Databricks Data Engineer / Training Instructor on a FEMA contract — GovCon context and Databricks-trainer role are not ideal."
    ),
    "healthleap_ai_forward_deployed_engineer_18082f9130": (
        52, ["Python", "LLM APIs", "REST APIs", "Healthcare AI"], ["Clinical AI domain", "SF onsite"],
        "Forward Deployed Engineer at HealthLeap (clinical AI); LLM/agentic overlap and FDE role family is a fit but SF onsite and clinical domain."
    ),
    "nesnah_ventures_business_intelligence_analyst_141189db51": (
        52, ["SQL", "Tableau", "Power BI", "Excel"], ["La Crosse WI location", "portfolio company analytics"],
        "BI Analyst at a private equity portfolio operator in La Crosse WI; SQL/Tableau overlap decent but location is a barrier."
    ),
    "revops_report_sales_operations_manager_d6027466b8": (
        38, ["Salesforce", "SQL", "HubSpot"], ["Sales Ops Manager — people/process management", "Creswell OR"],
        "Sales Operations Manager for L.A.B. Golf — sales ops / CRM management track, wrong direction."
    ),
    "semper_valens_soluti_ai_engineer_sr_4607259634": (
        22, ["Python", "AI/ML", "Secret Clearance"], ["Secret Clearance required", "DoD/CECOM"],
        "AI Engineer SR at APG MD requiring Secret Clearance — clearance-gated, disqualified."
    ),
    "university_of_utah_data_engineers_59a25fcc7b": (
        42, ["SQL", "Python", "dbt", "Snowflake"], ["Academic/university context", "Salt Lake City UT"],
        "Data Engineers at University of Utah analytics office; public university pay scale and SLC location reduce priority."
    ),
    "aimpoint_digital_senior_analytics_consultant_20_8bc59de398": (
        60, ["SQL", "dbt", "Snowflake", "Python", "Tableau"], ["Analytics consulting", "billable client work", "Atlanta GA"],
        "Senior Analytics Consultant at a boutique analytics firm; strong tech overlap (Snowflake, dbt, Tableau) but consulting billing model and Atlanta base."
    ),
    "burtch_works_manager_data_engineer_505521a548": (
        35, ["SQL", "Python", "Spark", "Databricks"], ["Manager / data engineering leadership", "Queens NY"],
        "Manager of Data Engineering at a hospitality company; management track is premature for candidate."
    ),
    "carters_ai_engineer_manager_ai_develop_6aa80eaff4": (
        35, ["Python", "LLMs", "ML", "AWS"], ["AI Engineering Manager", "Atlanta GA"],
        "AI Engineer Manager at Carter's (children's apparel); manager track and retail domain."
    ),
    "citi_genai_tech_senior_lead_28bc0fbdde": (
        40, ["Python", "LLMs", "SQL", "Cloud"], ["GenAI Tech Lead / senior leadership", "Tampa FL"],
        "GenAI Tech Senior Lead at Citi — tech leadership track in banking, above candidate's current level."
    ),
    "granules_pharmaceuti_logistics_analyst_d34dae13fe": (
        30, ["SQL", "Excel", "SAP"], ["Pharma logistics/supply chain domain", "Chantilly VA"],
        "Logistics Analyst at pharma company — supply chain ops role, wrong direction."
    ),
    "hach_quality_data_analyst_onsite_in_ac3b4a35d3": (
        38, ["SQL", "Python", "Tableau"], ["Water quality instruments domain", "Loveland CO onsite"],
        "Quality Data Analyst at a water analytics equipment company onsite in Colorado — niche manufacturing domain."
    ),
    "innova_software_serv_data_engineer_databricks_spark_39da6e0f84": (
        48, ["Databricks", "Spark", "Python", "SQL"], ["12+ month contract", "Databricks/Spark primary", "SF hybrid"],
        "Senior DE contract via staffing firm; Databricks/Spark-primary role candidate hasn't used deeply."
    ),
    "roi_agency_data_analyst_334085e329": (
        38, ["SQL", "Excel", "GIS"], ["Public utility / PUD domain", "The Dalles OR location"],
        "Energy Data Analyst at a public utility in rural Oregon — niche domain and remote location."
    ),
    "sotalent_total_portfolio_analytics_inve_d8dd465b9f": (
        35, ["SQL", "Python", "Portfolio analytics", "Investment AI"], ["Investment management domain", "Milwaukee WI"],
        "Total Portfolio Analytics & Investment AI Strategy Lead — investment management specialization required."
    ),
    "tatari_senior_solutions_engineer_ece7bd79dd": (
        48, ["SQL", "Python", "TV advertising analytics", "REST APIs"], ["TV/streaming advertising domain", "senior SE depth"],
        "Senior Solutions Engineer at a TV advertising analytics company; partially customer-facing but TV/media domain is niche."
    ),
    "caterpillar_data_engineer_physical_ai_plat_7e4dfc958b": (
        40, ["Python", "SQL", "IoT", "Azure"], ["Physical AI / industrial IoT", "manufacturing domain", "Irving TX"],
        "Data Engineer for Caterpillar's Physical AI Platform — industrial IoT/manufacturing domain."
    ),
    "experis_data_consultant_iii_b3633ea664": (
        52, ["SQL", "Python", "dbt", "Snowflake"], ["Financial services domain", "Pennington NJ (JPMorgan likely)"],
        "Data Consultant III at Experis (staffing) for a financial-services client; SQL/Snowflake overlap is real, consulting staffing model is a concern."
    ),
    "hcltech_solutions_manager_7d15685126": (
        48, ["SQL", "Python", "client delivery", "stakeholder management"], ["HCLTech forward-deployed delivery", "Charlotte NC"],
        "Solutions Manager (FDE-style role) at HCLTech; customer-facing delivery with some analytics overlap but IT outsourcing context."
    ),
    "mindzunite_forward_deployed_engineer_0ad9e4a0b8": (
        45, ["Python", "SQL", "LLM APIs", "REST APIs"], ["Unknown product domain", "early-stage company"],
        "Forward Deployed Engineer at a 500-person scale-up; limited product info but FDE family is a fit."
    ),
    "motorola_solutions_senior_sales_operations_analys_cf4ecad8d2": (
        40, ["SQL", "Salesforce", "Excel", "Tableau"], ["Sales operations / CRM analytics", "public safety tech"],
        "Senior Sales Operations Analyst at Motorola Solutions; RevOps/CRM analytics track is a stretch for candidate."
    ),
    "newfund_forward_deployed_engineering_l_da0ad0f647": (
        42, ["Python", "LLM APIs", "TypeScript", "REST APIs"], ["FDE Lead / senior level", "Aircall product (VoIP)"],
        "Forward Deployed Engineering Lead for Aircall — lead/senior level in VoIP/CX product; partial FDE family overlap."
    ),
    "prologis_lead_forward_deployed_engineer_18cbbb8699": (
        45, ["Python", "SQL", "REST APIs", "LLMs"], ["Lead-level FDE", "commercial real estate AI platform"],
        "Lead FDE at Prologis (largest global industrial REIT); real estate/logistics domain but FDE family is a fit."
    ),
    "rippling_manager_forward_deployed_engin_e14f9ac857": (
        35, ["Python", "TypeScript", "REST APIs", "HR tech"], ["Manager track (people leadership)", "SF onsite"],
        "Manager of Forward Deployed Engineering at Rippling — management track and SF onsite."
    ),
    "salesforce_data_analytics_senior_lead_2b35b679ef": (
        40, ["SQL", "Python", "Tableau", "Salesforce"], ["Senior Lead / senior level", "Tableau-product domain"],
        "Data Analytics Senior Lead at Salesforce (likely internal Tableau analytics team) — senior level expected."
    ),
    "vetsource_senior_business_analyst_supply_f150710bba": (
        50, ["SQL", "Oracle Cloud SCM", "Agile", "Tableau"], ["Oracle Cloud SCM specialization", "pet healthcare domain"],
        "Senior BA Supply Chain at Vetsource; Oracle Cloud SCM focus is specialized, pet healthcare domain is learnable."
    ),
    "walmart_principal_data_analyst_investi_38c24f7e98": (
        38, ["SQL", "Python", "Tableau", "Spark"], ["Principal/senior level", "Fraud investigations domain", "Bentonville AR"],
        "Principal Data Analyst (Investigations) at Walmart — principal level, fraud domain, Bentonville AR."
    ),
    "cenacle_leadership_g_data_analyst_9a9e9d1111": (
        48, ["SQL", "Python", "Tableau", "Power BI"], ["Small consulting group", "limited company info"],
        "Data Analyst at Cenacle Leadership Group; generic DA role with standard SQL/BI skills overlap."
    ),
    "ciyis_snowflake_engineer_architect_9f9fbf847e": (
        58, ["Snowflake", "SQL", "dbt", "Python", "Azure"], ["Snowflake architect depth", "Atlanta GA"],
        "Snowflake Engineer/Architect at a consulting firm; very strong Snowflake keyword overlap, architect label may not mean 7+ years."
    ),
    "deloitte_penetration_tester_c58b0a33ac": (
        18, ["Security testing", "Python"], ["Penetration testing / cybersecurity", "completely wrong domain"],
        "Penetration Tester — entirely wrong domain, no fit."
    ),
    "deloitte_solution_architect_1cad24e53c": (
        32, ["SQL", "Cloud", "Architecture"], ["Solution Architect level", "Deloitte Global internal"],
        "Solution Architect at Deloitte Global — architect level, internal services."
    ),
    "knoxville_technology_ai_developer_tickle_college_of_0c667d78d5": (
        48, ["Python", "SQL", "LLMs", "AI automation"], ["University IT / academic context", "Knoxville TN"],
        "AI Developer at UT Knoxville's data analytics department; Python/LLM overlap is good but academic pay scale and Knoxville location."
    ),
    "mauer_auto_group_ai_data_engineer_686c46f6cd": (
        42, ["SQL", "Python", "AI/ML", "Snowflake"], ["Auto dealership domain", "small company"],
        "AI Data Engineer at a 3-dealership auto group; interesting AI+data scope at small company but auto dealership domain and limited scale."
    ),
    "u_s_bank_software_engineer_1_ai_python__43b9c62b40": (
        35, ["Python", "LLMs", "RAG", "CI/CD"], ["Software Engineer 1 (SWE track)", "backend LLM engineering"],
        "SWE 1 (AI/Python/LLM) at US Bank — software engineering track, not analytics."
    ),
    "cerebras_erp_engineer_business_systems_b938b4e4cc": (
        55, ["SQL", "ERP systems", "Python", "NetSuite"], ["AI chip/compute startup", "Sunnyvale CA", "ERP/business systems domain"],
        "ERP Engineer Business Systems at Cerebras (AI chip company); interesting ERP domain overlap with PeopleSoft/Oracle Fusion experience, Sunnyvale onsite."
    ),
    "deloitte_technical_product_manager_delo_94d8f30101": (
        38, ["Product Management", "SQL", "Cloud"], ["Technical PM track", "Deloitte Global internal"],
        "Technical Product Manager at Deloitte Global internal — PM track, not engineering/analytics."
    ),
    "international_commercial_business_analytics__4d3a21225e": (
        52, ["SQL", "Python", "Tableau", "Power BI"], ["Truck manufacturer (International)", "Lisle IL"],
        "Commercial Business Analytics Analyst at International (truck manufacturer); decent SQL/BI overlap but manufacturing/trucking domain and Illinois location."
    ),
    "leidos_operational_energy_data_analys_e9646bc40c": (
        35, ["SQL", "Python", "Energy data"], ["Defense/government contractor", "DoD Air Force energy"],
        "Operational Energy Data Analyst at Leidos supporting DoD Air Force — GovCon context, energy domain."
    ),
    "the_new_york_times_senior_manager_audience_produc_f2b2035ed3": (
        38, ["SQL", "Python", "Tableau", "Analytics"], ["Senior Manager / leadership track", "Wirecutter product"],
        "Senior Manager Audience & Product Analytics at NYT Wirecutter — management track above candidate's current band."
    ),
    "u_s_bank_quantitative_analyst_artificia_10b04ac952": (
        35, ["Python", "Statistics", "ML", "SQL"], ["Quantitative/ML analyst depth", "Minneapolis MN"],
        "Quantitative Analyst AI/ML at US Bank — stats/ML depth required, wrong track."
    ),
    "airlines_reporting_c_data_insights_analyst_ii_d9dffdf746": (
        58, ["SQL", "Python", "Tableau", "Power BI"], ["Travel/aviation data domain", "Arlington VA"],
        "Data & Insights Analyst II at ARC (airline settlement clearing house); SQL/analytics overlap is solid, Arlington VA is near candidate's Maryland base — reasonable fit."
    ),
    "constellation_brands_product_manager_revenue_growth_c18c58f42a": (
        38, ["SQL", "Excel", "Tableau", "Product Management"], ["Revenue Growth Management / Product track", "CPG/alcohol domain"],
        "Product Manager Revenue Growth Management at Constellation Brands — product management track in CPG, wrong direction."
    ),
    "deloitte_people_insights_visier_platfor_c60bff4804": (
        38, ["Visier", "SQL", "HR analytics"], ["Visier HRMS platform specialization", "People analytics"],
        "People Insights Visier Platform Manager at Deloitte Global — Visier HR platform specialist role, internal."
    ),
    "deloitte_senior_analyst_data_modernizat_e72804f4a1": (
        48, ["SQL", "dbt", "Snowflake", "GenAI"], ["Deloitte Global internal / consulting", "data modernization practice"],
        "Senior Analyst Data Modernization at Deloitte Global; dbt/Snowflake/GenAI overlap is real but internal Deloitte consulting role."
    ),
    "envoy_solutions_engineering_intern_e5094681dc": (
        28, ["Python", "REST APIs", "SQL"], ["Internship level", "workplace management SaaS"],
        "Solutions Engineering Intern at Envoy — internship level, underleveled for candidate."
    ),
    "nisource_lead_data_and_analytics_develo_f3ae2665be": (
        50, ["SQL", "Python", "Tableau", "Snowflake"], ["Natural gas utility domain", "Columbus OH", "Lead level"],
        "Lead Data and Analytics Developer at NiSource (utility); Tableau/Snowflake overlap decent but utility domain and Columbus OH location."
    ),
    "oag_aviation_worldwi_senior_client_solutions_engine_731278db13": (
        52, ["SQL", "Python", "REST APIs", "Aviation data"], ["Aviation/travel data", "customer-facing solutions engineering"],
        "Senior Client Solutions Engineer at OAG (aviation intelligence); customer-facing technical role with analytics; travel data domain is niche."
    ),
    "revops_report_revenue_operations_manager_mar_c01246f22a": (
        38, ["Salesforce", "HubSpot", "SQL", "Marketing Ops"], ["Marketing RevOps manager track", "Linnworks product"],
        "Revenue Operations Manager Marketing at Linnworks — marketing ops/CRM management track."
    ),
    "salesforce_svp_global_solution_engineerin_8ccec3dcc5": (
        22, ["Tableau", "Solution Engineering"], ["SVP level — extremely over-leveled"],
        "SVP Global Solution Engineering, Tableau at Salesforce — massively over-leveled executive role."
    ),
    "snowflake_associate_solution_engineer_7cc1a726e7": (
        62, ["Snowflake", "SQL", "Python", "REST APIs", "dbt"], ["Pre-sales / solutions engineering track", "Snowflake platform sales context"],
        "Associate Solution Engineer at Snowflake; Snowflake product knowledge is strong, pre-sales SE track is a reasonable stretch for candidate."
    ),
    "sonata_software_nort_sr_functional_analyst_oracle_f_8b03bc5588": (
        52, ["Oracle Fusion", "SQL", "Agile"], ["Oracle Fusion HCM/H2R specialization", "functional analyst track"],
        "Sr Functional Analyst Oracle Fusion H2R at Sonata Software; Oracle Fusion overlap with candidate's PeopleSoft migration work is real but HCM/H2R is not their domain."
    ),
    "t_mobile_business_analysis_manager_949a401e57": (
        38, ["SQL", "Tableau", "Excel", "Business Analysis"], ["Manager track", "Frisco TX location"],
        "Business Analysis Manager at T-Mobile — management track and Frisco TX onsite."
    ),
    "texas_a_m_university_ris_senior_data_analyst_889b00b19c": (
        42, ["SQL", "Python", "Tableau"], ["Academic/university context", "research administration domain"],
        "RIS Senior Data Analyst at Texas A&M — academic research administration, low pay scale, College Station TX."
    ),
    "the_home_depot_manager_people_analytics_306b262325": (
        35, ["SQL", "Python", "Tableau", "HR analytics"], ["Manager HR Analytics — leadership track", "Atlanta GA"],
        "Manager People Analytics at Home Depot — HR analytics management track."
    ),
    "the_new_york_times_senior_program_manager_people__e7456a65de": (
        32, ["SQL", "HR analytics", "Program Management"], ["Program Manager track", "People Data domain"],
        "Senior Program Manager People Data at NYT — program management track in HRIS/people analytics."
    ),
    "accenture_forward_deployed_engineering_m_ea8f9224a1": (
        35, ["Python", "TypeScript", "REST APIs", "client delivery"], ["FDE Manager (people management)", "Accenture GovCon context"],
        "Forward Deployed Engineering Manager at Accenture — management track in GovCon delivery."
    ),
    "barclays_data_analyst_avp_a6a4007d27": (
        45, ["SQL", "Python", "ML", "NLP"], ["Banking/AVP level", "Whippany NJ", "ML/NLP depth required"],
        "Data Analyst AVP at Barclays; banking domain + ML/NLP depth requirements push this above candidate's analytics-engineering profile."
    ),
    "fox_senior_staff_orchestration_eng_fedb552e48": (
        28, ["Python", "Orchestration", "Cloud"], ["Staff/Senior Staff engineering level", "media/streaming domain"],
        "Senior Staff Orchestration Engineer at Fox — staff-level backend engineering, media domain."
    ),
    "glean_founding_forward_deployed_engi_7fb44a39a5": (
        50, ["Python", "LLM APIs", "REST APIs", "Enterprise SaaS"], ["Founding FDE — high bar for engineering depth", "Mountain View CA"],
        "Founding Forward Deployed Engineer at Glean (Work AI); strong LLM/agentic overlap and FDE family fit but founding FDE role demands full-stack engineering depth."
    ),
    "google_ai_strategy_lead_9405082649": (
        35, ["Python", "SQL", "Strategy", "LLMs"], ["AI Strategy Lead — business strategy track", "Google seniority bar"],
        "AI Strategy Lead at Google — strategy/bizdev track at a high-bar company, not engineering/analytics."
    ),
    "logic_forward_deployed_engineering_m_b88e744bf9": (
        35, ["Python", "TypeScript", "client delivery"], ["FDE Manager (Accenture Flex)", "government context"],
        "Forward Deployed Engineering Manager via Logic Inc (Accenture Flex) — management + GovCon."
    ),
    "mistral_revenue_operations_inference_l_74e6efb6c7": (
        40, ["SQL", "Python", "Revenue Operations", "LLM APIs"], ["Revenue Operations specialization", "SF"],
        "Revenue Operations Inference Lead at Mistral — RevOps track at an AI company."
    ),
    "molina_healthcare_senior_servicenow_engineer_ai__91087ae0a7": (
        32, ["ServiceNow", "Python", "AI"], ["ServiceNow platform specialist", "healthcare IT"],
        "Senior ServiceNow Engineer AI Enablement at Molina Healthcare — ServiceNow platform specialization."
    ),
    "norc_at_the_universi_sas_data_scientist_i_health_da_625fadf367": (
        35, ["SAS", "SQL", "Health data"], ["SAS (legacy statistical tool)", "health data research"],
        "SAS Data Scientist I at NORC — SAS/legacy stack, academic research context."
    ),
    "northrop_grumman_data_scientist_9bc086c2ef": (
        32, ["Python", "ML", "SQL", "Secret Clearance"], ["Secret Clearance preferred", "defense domain"],
        "Data Scientist at Northrop Grumman — defense domain, clearance preferred, ML/stats depth."
    ),
    "openai_machine_learning_engineer_core_3bb4392010": (
        35, ["Python", "ML", "Experimentation", "Statistics"], ["ML Engineer — ML/stats depth", "OpenAI bar is exceptionally high"],
        "ML Engineer Core Experimentation at OpenAI — ML/stats depth and OpenAI's exceptional hiring bar make this a poor fit."
    ),
    "sim_forward_deployed_engineer_6ce74531f4": (
        48, ["Python", "LLM APIs", "REST APIs", "knowledge graphs"], ["SF onsite", "early-stage AI agent startup"],
        "Forward Deployed Engineer at Sim (AI agent for knowledge work); FDE family is a fit, SF onsite is the friction."
    ),
    "tata_consultancy_ser_sap_data_analytics_architect_779a728067": (
        32, ["SAP BDC", "SAP BW", "Power BI", "SQL"], ["SAP Data & Analytics architect", "SAP ecosystem specialization"],
        "SAP Data & Analytics Architect at TCS — SAP-specific role requiring deep SAP platform expertise."
    ),
    "the_new_york_times_senior_manager_revenue_analyti_d689aba062": (
        35, ["SQL", "Python", "Tableau", "Analytics"], ["Senior Manager — leadership track", "NYT Wirecutter"],
        "Senior Manager Revenue Analytics at NYT Wirecutter — management track."
    ),
    "deloitte_manager_enterprise_data_domain_e664294016": (
        38, ["SQL", "dbt", "Snowflake", "Data modeling"], ["Manager track", "Deloitte Global internal data governance"],
        "Manager Enterprise Data Domain Modeling at Deloitte Global — management track with data governance focus."
    ),
    "deloitte_salesforce_alliance_operations_9da579478a": (
        28, ["Salesforce", "Project Management", "PMO"], ["Salesforce Alliance / PMO track", "24-month secondment"],
        "Salesforce Alliance Operations PMO Manager at Deloitte — Salesforce alliance management, wrong direction."
    ),
    "hcltech_enterprise_architect_810ec84002": (
        32, ["SQL", "Cloud", "Architecture", "client delivery"], ["Enterprise Architect level", "HCLTech delivery"],
        "Enterprise Architect at HCLTech — architect-level in IT outsourcing context."
    ),
    "hyatt_senior_ai_engineer_search_pers_e5ffb1180f": (
        40, ["Python", "LLMs", "Search", "Personalization"], ["Senior AI Engineer — LLM/search depth", "hospitality domain"],
        "Senior AI Engineer (Search/Personalization/Agents) at Hyatt — senior ML/AI engineer track in hospitality."
    ),
    "logic_agentic_operations_engineer_64_711ad87412": (
        38, ["Python", "AI agents", "ML"], ["Accenture Flex / GovCon context", "Philadelphia PA"],
        "Agentic Operations Engineer via Logic Inc (Accenture Flex) — GovCon AI engineering."
    ),
    "mastercard_senior_software_engineer_6b365249c1": (
        30, ["Java", "Python", "Microservices", "Cloud"], ["Senior SWE", "payments platform", "Arlington VA"],
        "Senior Software Engineer at Mastercard — backend SWE track in payments platform."
    ),
    "rafay_technical_enablement_architect_7d8b1ab8a4": (
        32, ["GPU Platform", "Kubernetes", "Cloud"], ["GPU/ML infra platform", "technical enablement architect"],
        "Technical Enablement Architect for Rafay GPU Platform — GPU/ML infrastructure, niche area."
    ),
    "accenture_agentic_operations_engineer_64_28562dbee9": (
        38, ["Python", "AI agents", "ML"], ["Accenture Flex / GovCon", "Philadelphia PA"],
        "Agentic Operations Engineer at Accenture (same role as Logic Inc listing above) — GovCon AI engineering."
    ),
    "albertsons_companies_senior_real_estate_and_market__d19f33c11a": (
        38, ["SQL", "GIS", "Excel", "Tableau"], ["Real estate / site selection domain", "Boise ID"],
        "Senior Real Estate and Market Insights Analyst at Albertsons — real estate market analytics, niche domain."
    ),
    "matlen_silver_generative_ai_engineer_2b7f675d6e": (
        38, ["Python", "MongoDB", "Redis", "LLMs"], ["Application development focus", "USC/GC only", "contract"],
        "Generative AI Engineer contract role via Matlen Silver; application dev focus with citizenship restriction."
    ),
    "palantir_technologie_forward_deployed_infrastructur_70c5a047a1": (
        30, ["Python", "Infrastructure", "Kubernetes"], ["Internship level", "US Government clearance likely"],
        "Forward Deployed Infrastructure Engineer Internship at Palantir — internship level, infra/DevOps focus."
    ),
    "resorts_world_las_ve_analyst_revenue_strategy_794321e84d": (
        50, ["SQL", "Python", "Tableau", "Excel"], ["Casino/gaming revenue strategy", "Las Vegas NV"],
        "Revenue Strategy Analyst at Resorts World Las Vegas; SQL/analytics overlap decent, Las Vegas location and gaming domain are unusual."
    ),
    "salesforce_associate_evaluations_manager_3faaea03c5": (
        35, ["Program Management", "SQL", "Evaluations"], ["Program Manager / evaluations track", "Salesforce internal"],
        "Associate Evaluations Manager at Salesforce — program management, AI evaluation track."
    ),
    "sectra_cardiology_engineering_lead_9769bba5b7": (
        28, ["Cardiology software", "HL7/DICOM"], ["Cardiology/healthcare imaging domain", "clinical engineering"],
        "Cardiology Engineering Lead at Sectra — medical imaging software, entirely wrong domain."
    ),
    "sentara_cloud_architect_manager_8d127da2cd": (
        28, ["Azure", "Cloud Architecture"], ["Cloud Architect Manager level", "healthcare IT"],
        "Cloud Architect Manager at Sentara (health system) — cloud architecture management, wrong track."
    ),
    "snowflake_solution_engineer_enterprise_a_ed9fdff7d5": (
        58, ["Snowflake", "SQL", "Python", "dbt", "REST APIs"], ["Enterprise pre-sales / solutions engineering", "Nashville TN"],
        "Solution Engineer Enterprise Acquisition at Snowflake; strong Snowflake product knowledge is a real asset, pre-sales SE track is a stretch but interesting FDE-adjacent role."
    ),
    "t_mobile_sr_analyst_broadband_operation_c8c34a8d7c": (
        45, ["SQL", "Python", "Tableau", "Power BI"], ["Broadband operations analytics", "Bellevue WA"],
        "Sr Analyst Broadband Operational Insights at T-Mobile; SQL/analytics overlap decent but telecom ops domain and Bellevue WA location."
    ),
    "u_s_bank_marketing_performance_business_cfb70fe5f8": (
        42, ["SQL", "Python", "Tableau", "Marketing Analytics"], ["Marketing analytics / performance measurement", "SF"],
        "Marketing Performance & Business Insights at US Bank — marketing analytics track in banking."
    ),
    "adventhealth_research_data_analyst_ii_b447edac02": (
        42, ["SQL", "Python", "Tableau", "SAS"], ["Healthcare research domain", "Orlando FL"],
        "Research Data Analyst II at AdventHealth — healthcare research analytics, lower seniority band."
    ),
    "agave_senior_software_engineer_e395d3d23d": (
        28, ["Python", "TypeScript", "APIs", "Backend"], ["Senior SWE", "construction SaaS APIs"],
        "Senior Software Engineer at Agave (construction SaaS) — backend SWE, wrong track."
    ),
    "apex_systems_lead_business_data_analyst_gcp_80bc31268d": (
        52, ["SQL", "GCP", "BigQuery", "Python"], ["GCP/BigQuery primary stack", "Minneapolis MN onsite"],
        "Lead Business Data Analyst GCP+BigQuery via Apex Systems; SQL/analytics overlap but GCP/BigQuery stack is a gap and Minneapolis onsite."
    ),
    "b2b_matrix_senior_ai_machine_learning_eng_bbd757dd0f": (
        32, ["Python", "ML", "LLMs", "Production ML"], ["ML engineering depth", "contract role"],
        "Senior AI/ML Engineer contract — production ML systems depth required, wrong track."
    ),
    "cencora_intern_technical_business_anal_d7e2e14b8f": (
        25, ["SQL", "Business Analysis", "Agile"], ["Intern level", "underleveled"],
        "Intern Technical BA at Cencora — intern level, disqualified as underleveled."
    ),
    "circana_ai_staff_engineer_chicago_il_o_4bdc84dcbb": (
        35, ["Python", "AI/ML", "Spark", "Chicago IL"], ["Staff engineer level", "CPG/retail data domain"],
        "AI Staff Engineer at Circana (CPG data analytics) — staff-level ML engineering in CPG data."
    ),
    "cognizant_principal_ai_technical_archite_fdcc1b773a": (
        30, ["Python", "AWS Bedrock", "Agentic AI"], ["Principal architect level", "AWS Bedrock specialization"],
        "Principal AI Technical Architect (AWS Bedrock) at Cognizant — principal-level, AWS Bedrock specialist."
    ),
    "farmer_focus_fp_a_analyst_254898f365": (
        42, ["Excel", "SQL", "Python", "FP&A"], ["FP&A track", "chicken/protein farming domain"],
        "FP&A Analyst at Farmer Focus (poultry company) — FP&A finance track in an unusual domain."
    ),
    "jpmorganchase_business_analysis_associate_i_cc30a7f92b": (
        55, ["SQL", "Python", "Tableau", "Excel"], ["Fraud Strategy and Analytics domain", "Tampa FL"],
        "Business Analysis Associate I at JPMorgan (Fraud Strategy) — solid BA + analytics overlap, JPMorgan culture and Tampa location are reasonable, fraud domain is learnable."
    ),
    "milsoft_utility_solu_data_analyst_programmer_b29be37570": (
        38, ["SQL", "Python", "Excel"], ["Electric utility software", "Abilene TX", "small company"],
        "Data Analyst/Programmer at a small utility software vendor in Abilene TX — niche product company."
    ),
    "one80_intermediaries_risk_management_services_assoc_949cc1bec5": (
        35, ["Excel", "SQL", "Insurance data"], ["Insurance brokerage / risk management", "niche domain"],
        "Risk Management Services Associate at One80 Intermediaries — insurance/risk management niche."
    ),
    "revops_report_sales_operations_associate_5064f1bba8": (
        38, ["Salesforce", "SQL", "Excel"], ["Sales Operations Associate — junior level", "AI safety company (Gray Swan)"],
        "Sales Operations Associate at Gray Swan (AI safety) — junior RevOps role."
    ),
    "teaching_strategies_senior_full_stack_engineer_sma_5a79c9708d": (
        28, ["Python", "TypeScript", "Full-stack"], ["Senior Full Stack SWE", "EdTech domain"],
        "Senior Full Stack Engineer at Teaching Strategies (EdTech) — backend SWE, wrong track."
    ),
    "the_home_depot_senior_data_scientist_online_m_3056174eab": (
        38, ["SQL", "Python", "ML", "Statistics"], ["Senior DS / ML modeling depth", "retail/ecommerce domain"],
        "Senior Data Scientist Online & Marketing at Home Depot — ML/stats depth and retail domain."
    ),
    "walbridge_project_financial_analyst_f86882cf0a": (
        35, ["Excel", "SQL", "Financial Analysis", "Construction ERP"], ["Construction domain", "Detroit MI", "FP&A/project finance"],
        "Project Financial Analyst at Walbridge (construction) — project finance in construction, wrong direction."
    ),
    "warner_music_group_data_scientist_2f993a649a": (
        38, ["SQL", "Python", "ML", "Streaming analytics"], ["Data Scientist — ML/stats track", "music/entertainment domain"],
        "Data Scientist at Warner Music Group — ML/stats track in entertainment."
    ),
}

con = sqlite3.connect(DB)

# Get all today's discovered jobs
rows = con.execute("""
    SELECT job_id, lower(company)||'|'||lower(title) as key, company, title
    FROM jobs
    WHERE status='discovered'
      AND date(first_seen_at,'localtime') = date('now','localtime')
""").fetchall()

# Build dedup map: key -> canonical job_id, and all_job_ids_for_key
dedup_canonical = {}
dedup_all = {}
for job_id, key, company, title in rows:
    if key not in dedup_canonical:
        dedup_canonical[key] = job_id
    if key not in dedup_all:
        dedup_all[key] = []
    dedup_all[key].append(job_id)

print(f"Total discovered: {len(rows)}, Unique pairs: {len(dedup_canonical)}")

processed = 0
skipped_no_score = 0
errors = []

for key, canonical_id in dedup_canonical.items():
    all_ids = dedup_all[key]

    if canonical_id not in SCORES:
        # Score not defined — use preliminary_score / 2 as fallback
        prelim = con.execute("SELECT preliminary_score, title, company FROM jobs WHERE job_id=?", (canonical_id,)).fetchone()
        score = int((prelim[0] or 50) * 0.85)
        tech = ["SQL", "Python"]
        missing = ["Unknown — description not individually reviewed"]
        pitch = f"Auto-scored from preliminary_score {prelim[0]}; not individually reviewed this run."
        skipped_no_score += 1
    else:
        score, tech, missing, pitch = SCORES[canonical_id]

    try:
        # Insert job_analysis row for canonical job_id
        con.execute("""
            INSERT OR REPLACE INTO job_analysis
                (job_id, match_score, tech_stack, missing_skills, pitch, processed_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (canonical_id, score, json.dumps(tech), json.dumps(missing), pitch))

        # Update status to 'analyzed' for ALL job_ids in this group
        for jid in all_ids:
            con.execute("UPDATE jobs SET status='analyzed' WHERE job_id=?", (jid,))

        processed += 1
    except Exception as e:
        errors.append(f"{canonical_id}: {e}")

con.commit()
print(f"Processed {processed} unique jobs ({skipped_no_score} auto-scored). Errors: {len(errors)}")
if errors:
    for e in errors[:5]:
        print(" ERR:", e)

# Verify >=75 jobs
high_scores = con.execute("""
    SELECT ja.job_id, j.title, j.company, ja.match_score
    FROM job_analysis ja
    JOIN jobs j ON j.job_id = ja.job_id
    WHERE ja.match_score >= 75
      AND ja.job_id IN (
          SELECT job_id FROM jobs
          WHERE date(first_seen_at,'localtime') = date('now','localtime')
      )
    ORDER BY ja.match_score DESC
""").fetchall()
print(f"\nJobs scoring >=75 (need full tailoring): {len(high_scores)}")
for r in high_scores:
    print(f"  {r[3]:3d}  {r[2]} — {r[1]}")

con.close()
EOF