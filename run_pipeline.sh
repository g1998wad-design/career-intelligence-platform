#!/bin/zsh
# LaunchAgent entry point. Runs 9am-7pm every 2 hours (see
# com.jsbasics.jobpipeline.plist). Scrape only -- analyze_jobs.py's
# API-based scoring is no longer used (Anthropic API credits exhausted,
# and we've moved to agent-driven scoring/tailoring instead, see
# manual_analyze.py + the "job-analysis" scheduled task).
set -eu
cd /Users/gurkiratsingh/JS_BASICS
exec .venv/bin/python3 -u pipeline_runner.py --scrape-hours-old 3 --scrape-only >> pipeline_scheduled.log 2>&1
