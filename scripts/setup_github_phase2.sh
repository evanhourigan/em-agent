#!/usr/bin/env bash
set -euo pipefail

require() { command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }; }
require gh
require git

OWNER_REPO=$(git remote get-url --push origin 2>/dev/null | sed -E 's#(git@github.com:|https://github.com/)##; s/.git$//')
OWNER=${OWNER_REPO%%/*}
REPO=${OWNER_REPO##*/}

PROJECT_TITLE="EM Agent — Phase 1" # keep Phase 2 items on same board for now

# Ensure milestone exists
MILESTONE_TITLE="Phase 2 — Metrics & Analytics"
MILESTONE_ID=$(gh api -X GET repos/$OWNER/$REPO/milestones --jq ".[] | select(.title==\"$MILESTONE_TITLE\").number" | head -n1 || true)
if [[ -z "$MILESTONE_ID" ]]; then
  MILESTONE_ID=$(gh api repos/$OWNER/$REPO/milestones -f title="$MILESTONE_TITLE" -f state=open --jq '.number')
  echo "Created milestone #$MILESTONE_ID"
else
  echo "Milestone exists: #$MILESTONE_ID"
fi

create_issue() {
  local title="$1"; shift
  local body="$1"; shift
  local area_label="$1"; shift
  local type_label="$1"; shift

  local exist_url
  exist_url=$(gh issue list --repo "$OWNER/$REPO" --search "$title in:title state:open" --json url --jq '.[0].url' || true)
  if [[ -n "$exist_url" ]]; then
    echo "Issue exists: $exist_url"
    echo "$exist_url"; return 0
  fi

  local output
  output=$(gh issue create \
    --repo "$OWNER/$REPO" \
    --title "$title" \
    --body "$body" \
    --label "phase:2" \
    --label "$area_label" \
    --label "$type_label" \
    --milestone "$MILESTONE_TITLE" \
    --project "$PROJECT_TITLE")
  local url
  url=$(echo "$output" | grep -Eo 'https://github.com/[^ ]+/issues/[0-9]+' | tail -n1)
  echo "$url"
}

# Ensure labels for phase:2 exist
if ! gh label view "phase:2" --repo "$OWNER/$REPO" >/dev/null 2>&1; then
  gh label create "phase:2" --color "5319e7" --description "Phase 2 work" --repo "$OWNER/$REPO" -f
fi

# Define Phase 2 issues
I1_TITLE="[Phase 2] dbt models for DORA & sprint metrics"
I1_BODY=$'Create initial dbt models for lead time, deploy frequency, change fail rate, MTTR, WIP/aging.\n\nAcceptance:\n- dbt project skeleton with profiles for local Postgres.\n- Models + seeds or views to compute core metrics.\n- Docs and example queries.\n\nRefs: ARCHITECTURE.md → Phase 2'
create_issue "$I1_TITLE" "$I1_BODY" "area:metrics" "type:feature" >/dev/null

I2_TITLE="[Phase 2] Backfill jobs and retention policy"
I2_BODY=$'Implement backfill scripts/jobs to populate metrics from stored events; add retention policy and time-zone correctness.\n\nAcceptance:\n- Backfill runnable locally.\n- Retention windows configurable.\n- TZ handling documented and tested.\n\nRefs: ARCHITECTURE.md → Phase 2'
create_issue "$I2_TITLE" "$I2_BODY" "area:metrics" "type:task" >/dev/null

I3_TITLE="[Phase 2] Grafana dashboards + JSON exports"
I3_BODY=$'Ship initial dashboards for delivery/flow/quality; include JSON exports committed to repo.\n\nAcceptance:\n- 3 dashboards present and viewable against local data.\n- JSON exported and versioned.\n\nRefs: ARCHITECTURE.md → Phase 2'
create_issue "$I3_TITLE" "$I3_BODY" "area:metrics" "type:feature" >/dev/null

echo "Phase 2 issues created and added to project: $PROJECT_TITLE"
