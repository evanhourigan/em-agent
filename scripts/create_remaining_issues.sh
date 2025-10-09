#!/bin/zsh
set -euo pipefail

# Requirements: gh (authenticated), jq
if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI not found. Install from https://cli.github.com/ and authenticate (gh auth login)." >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq not found. Install via brew install jq (macOS)." >&2
  exit 1
fi

GH_REPO="evanhourigan/em-agent"

echo "Fetching existing issues from $GH_REPO ..."
gh issue list -R "$GH_REPO" --limit 500 --json title,number > .tmp_issues.json
jq -r '.[].title' .tmp_issues.json | sort -u > .tmp_existing_titles.txt

cat > .tmp_new_issues.json <<'JSON'
[
  {"title":"OTel tracing across gateway/runners/RAG","body":"Add tracing middleware and spans.","labels":["phase:6","type:infra","area:gateway"]},
  {"title":"Prom metrics: approval latency/override/slack errors","body":"Custom counters/histograms + Grafana.","labels":["phase:6","type:infra","area:gateway"]},
  {"title":"Rate limits, payload size limits, graceful shutdown","body":"Harden APIs.","labels":["phase:6","type:infra","area:gateway"]},
  {"title":"Secrets hardening guidance (Vault/SOPS roadmap)","body":"Docs + optional integration.","labels":["phase:6","type:docs","area:infra"]},
  {"title":"MCP server exposing core tools","body":"signals.evaluate, reports.*, rag.search, approvals.*, slack.post_*","labels":["phase:4","type:feature","area:gateway"]},
  {"title":"Agent loop (LLM planner + MCP tools + approvals)","body":"Provider wrappers, guardrails, Slack entrypoint.","labels":["phase:4","type:feature","area:gateway"]},
  {"title":"OPA policies replace YAML","body":"Bundles, eval, versioning.","labels":["phase:4","type:feature","area:gateway"]},
  {"title":"RAG: pgvector persistence + hybrid search","body":"Schema, ingestion, similarity search.","labels":["phase:4","type:feature","area:rag"]},
  {"title":"Crawlers: Confluence/Repos (delta sync)","body":"Docs → documents table; backfills.","labels":["phase:4","type:feature","area:rag"]},
  {"title":"Event bus (NATS/Kafka) for ingestion/eval","body":"Decouple webhooks from processing.","labels":["phase:4","type:infra","area:infra"]},
  {"title":"Workers (Celery) + Temporal workflows","body":"Durable jobs, external signals, timers.","labels":["phase:4","type:infra","area:workers"]},
  {"title":"Slack app OAuth install + token rotation","body":"Productionize Slack app.","labels":["phase:5","type:feature","area:gateway"]},
  {"title":"Slack UX: modals, pagination, ephemeral","body":"Polish UX for approvals/triage.","labels":["phase:5","type:feature","area:gateway"]},
  {"title":"dbt: DuckDB/BigQuery targets (optional)","body":"Warehouse targets.","labels":["phase:2","type:feature","area:metrics"]},
  {"title":"More flow metrics + Grafana panels","body":"Flow efficiency, review latency.","labels":["phase:2","type:feature","area:metrics"]},
  {"title":"Admin UI: approvals/jobs/signals/RAG search","body":"Minimal operator UI (auth later).","labels":["phase:5","type:feature","area:ui"]},
  {"title":"E2E tests: Slack signatures, approvals, RAG","body":"Smoke + regression.","labels":["phase:6","type:test","area:ci"]}
]
JSON

echo "Would create (titles):"
comm -23 <(jq -r '.[].title' .tmp_new_issues.json | sort -u) .tmp_existing_titles.txt || true

echo "Creating missing issues..."
jq -c '.[]' .tmp_new_issues.json | while read -r row; do
  title=$(echo "$row" | jq -r '.title')
  if grep -Fxq "$title" .tmp_existing_titles.txt; then
    echo "skip: $title (exists)"
  else
    body=$(echo "$row" | jq -r '.body')
    labels=$(echo "$row" | jq -r '.labels | join(",")')
    echo "create: $title"
    gh issue create -R "$GH_REPO" -t "$title" -b "$body" -l "$labels"
  fi
done

echo "Done."


