# Career Fit Explainer

A multi-agent system that investigates one job/resume pair across fragmented
data sources and returns an evidence-backed apply/skip recommendation, with
full citations and a reproducible run trace.

Built for the **Open Agent Hackathon 2026**, track **"The Agent That Can
Explain Why."** It sits on top of this repo's existing job data (the same
`mock_scenarios/jobs.json` used elsewhere in the pipeline) rather than
replacing it: the scrape/tailor/autofill pipeline gets jobs in front of a
candidate, and this agent explains *why* a specific job is or isn't worth
their time before they spend an application on it.

## Why this shape

A single LLM call that reads a job description and a resume and returns a
score is a prompt wrapper, not an agent system. This does more:

- **Four independent data sources**, queried instead of concatenated into
  one mega-prompt: the job posting + its (separately sourced) detailed
  requirements, the candidate's resume, third-party company signals, and
  market salary data.
- **A real retry loop.** `CompanySignalAgent` first looks for a signal no
  older than 30 days. If it finds nothing, the Evaluator doesn't just accept
  a low-confidence answer -- it sends the agent back with instructions to
  widen the lookback window to 365 days. For two of the three sample jobs
  that recovers a real signal; for the third, it confirms there genuinely is
  none, and the system says so instead of fabricating one.
- **A Risk agent that escalates, and a Planner that listens.** When
  `RiskAgent` flags a high-severity gap (a big experience shortfall, or
  skill overlap under 50%), `PlannerAgent.refine()` turns that into an
  explicit instruction the Explainer is required to surface -- the
  escalate-then-refine loop the hackathon rubric asks for, not a fixed
  pipeline.
- **Every fact is cited back to its source table and row.** The LLM
  (when configured) only rewrites already-validated structured facts into
  prose -- it cannot introduce a fact that isn't in the trace.

```
PlannerAgent.initial_plan()
        |
        v
JobRequirementsAgent --+
ResumeMatchAgent -------+--> findings (confidence + citations)
CompanySignalAgent -----+        |
MarketContextAgent -----+        v
                           EvaluatorAgent
                         (confidence < 0.5? retry once, with feedback)
                                  |
                                  v
                             RiskAgent
                      (experience gap / skill gap / EEO-sensitive ask)
                                  |
                                  v
                       PlannerAgent.refine()
                 (HIGH risk -> explicit Explainer instruction)
                                  |
                                  v
                            ExplainerAgent
              (verdict + confidence + cited reasons + narrative)
```

## Sponsor technology

- **Zetaris** (`zetaris_client.py`) is the data-access layer every agent
  queries through. In local/demo mode it federates four independently
  shaped JSON sources (`mock_scenarios/jobs.json`,
  `job_requirements_detail.json`, `company_notes.json`,
  `market_salary.json`) plus the resume into one in-memory SQL surface --
  exactly the federation Zetaris's Lightning REST API / JDBC / Python-Spark
  SDK provides over heterogeneous real backends. Set `ZETARIS_ENDPOINT` +
  `ZETARIS_API_KEY` and `query()` transparently switches to posting the same
  SQL at the real Lightning endpoint -- no agent code changes.
- **Meterless** (`meterless_client.py`) wraps every single agent step in
  `meter.step(agent_name)` -- the only metering code anywhere in the
  package. It always writes a local usage trace (`logs/meterless_usage.jsonl`)
  and forwards it to Meterless's usage-ingest endpoint when
  `METERLESS_API_KEY` is set, so per-agent cost/latency is visible without
  any agent being aware metering exists.
- **Cursor** was the development environment for this package.
- **NVIDIA**: the pluggable `Reasoner` in `llm.py` is the integration point
  for an NVIDIA-hosted/accelerated model (e.g. via NIM) as a drop-in
  alternative to `AnthropicReasoner` -- same `narrate(system, user)`
  interface, swappable with no orchestrator changes.

## Running it

```bash
python3 -m career_fit_agent.cli --list-jobs
python3 -m career_fit_agent.cli --job-id MOCK_LI_GREENHOUSE_001
python3 -m unittest tests.test_career_fit_agent -v
```

No API keys are required -- the demo runs fully offline against
`mock_scenarios/`. Set the variables in `.env.example` to point at live
Zetaris/Meterless/Anthropic services instead.

Sample runs for all three mock jobs (one clean `apply`, one `apply_with_caveats`
with a retried company signal, one `skip` with a real missing-signal gap) are
committed under `sample_runs/`.
