#!/usr/bin/env bash
set -euo pipefail

# Create labels, milestone, user Project (v2), and Phase 1 issues, then add issues to the project.

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }
}

require gh
require git

OWNER_REPO=$(git remote get-url --push origin 2>/dev/null | sed -E 's#(git@github.com:|https://github.com/)##; s/.git$//' )
OWNER=${OWNER_REPO%%/*}
REPO=${OWNER_REPO##*/}

echo "Using repo: $OWNER/$REPO"

echo "Checking GitHub auth..."
gh auth status >/dev/null

# Labels (name|color|desc)
LABELS=(
  "phase:1|0e8a16|Phase 1 work"
  "type:feature|1d76db|Feature"
  "type:task|c2e0c6|Task"
  "type:bug|d73a4a|Bug"
  "type:infra|5319e7|Infrastructure"
  "type:doc|006b75|Documentation"
  "area:gateway|fbca04|Gateway/API"
  "area:db|0b3d91|Database"
  "area:connectors|c5def5|Connectors"
  "area:workers|5319e7|Workers"
  "area:metrics|1d76db|Metrics"
  "area:ui|a2eeef|UI"
  "area:infra|bfdadc|Infra"
)

for entry in "${LABELS[@]}"; do
  IFS='|' read -r NAME COLOR DESC <<<"$entry"
  if gh label view "$NAME" --repo "$OWNER/$REPO" >/dev/null 2>&1; then
    echo "Label exists: $NAME"
  else
    gh label create "$NAME" --color "$COLOR" --description "$DESC" --repo "$OWNER/$REPO" -f
  fi
done

# Milestone
MILESTONE_TITLE="Phase 1 — Ingestion & Normalization"
MILESTONE_ID=$(gh api -X GET repos/$OWNER/$REPO/milestones --jq ".[] | select(.title==\"$MILESTONE_TITLE\").number" | head -n1 || true)
if [[ -z "$MILESTONE_ID" ]]; then
  MILESTONE_ID=$(gh api repos/$OWNER/$REPO/milestones -f title="$MILESTONE_TITLE" -f state=open --jq '.number')
  echo "Created milestone #$MILESTONE_ID"
else
  echo "Milestone exists: #$MILESTONE_ID"
fi

# Project (user-level Projects v2)
PROJECT_TITLE="EM Agent — Phase 1"
# Newer gh versions return an object with a "projects" array
PROJECT_NUMBER=$(gh project list --owner "$OWNER" --format json --jq ".projects[] | select(.title==\"$PROJECT_TITLE\").number" | head -n1 || true)
if [[ -z "$PROJECT_NUMBER" ]]; then
  PROJECT_NUMBER=$(gh project create --owner "$OWNER" --title "$PROJECT_TITLE" --format json --jq '.number')
  echo "Created project #$PROJECT_NUMBER"
  # Add default views/fields are handled by GitHub; no extra fields required here
else
  echo "Project exists: #$PROJECT_NUMBER"
fi

create_issue() {
  local title="$1"; shift
  local body="$1"; shift
  local labels_csv="$1"; shift
  local area_label="$1"; shift

  local exist_url
  exist_url=$(gh issue list --repo "$OWNER/$REPO" --search "$title in:title state:open" --json url --jq '.[0].url' || true)
  if [[ -n "$exist_url" ]]; then
    echo "Issue exists: $exist_url"
    echo "$exist_url"
    return 0
  fi

  # Create issue and add to project by title (-p). Older gh versions don't support --json here.
  local output
  output=$(gh issue create \
    --repo "$OWNER/$REPO" \
    --title "$title" \
    --body "$body" \
    --label "phase:1" \
    --label "$area_label" \
    $(printf -- '--label %s ' $labels_csv) \
    --milestone "$MILESTONE_TITLE" \
    --project "$PROJECT_TITLE")
  # Extract URL from the last line of output
  local url
  url=$(echo "$output" | grep -Eo 'https://github.com/[^ ]+/issues/[0-9]+' | tail -n1)
  if [[ -z "$url" ]]; then
    # Fallback: print entire output for debugging and exit nonzero
    echo "$output"
    echo "Failed to parse created issue URL" >&2
    exit 1
  fi
  echo "Created issue: $url"
  echo "$url"
}

add_to_project() { :; }

# Issues derived from ARCHITECTURE.md Phase 1 WBS

I1_TITLE="[Phase 1] 1.1 Alembic setup and base migration"
I1_BODY=$(cat <<'EOF'
Add Alembic to the repo and create initial migration plumbing.

Acceptance:
- Alembic installed and configured with SQLAlchemy 2.x engine.
- `migrations/` added with env script.
- Base migration created and runnable via Make target.

Refs: ARCHITECTURE.md → Phase 1 — 1.1
EOF
)
I1_URL=$(create_issue "$I1_TITLE" "$I1_BODY" "type:infra" "area:db")
add_to_project "$I1_URL"

I2_TITLE="[Phase 1] 1.2 SQLAlchemy session scaffolding"
I2_BODY=$(cat <<'EOF'
Introduce a request-scoped/session utility and update healthcheck to exercise a roundtrip.

Acceptance:
- Session helper/context in gateway.
- Simple unit or curl validation passes.

Refs: ARCHITECTURE.md → Phase 1 — 1.2
EOF
)
I2_URL=$(create_issue "$I2_TITLE" "$I2_BODY" "type:feature" "area:db")
add_to_project "$I2_URL"

I3_TITLE="[Phase 1] 1.3 Projects model/schemas/repo/router + migration"
I3_BODY=$(cat <<'EOF'
Implement a thin vertical to verify stack: `projects` table, Pydantic schemas, repo/service, CRUD router.

Acceptance:
- Table with id, key, name, timestamps.
- Endpoints: POST/GET list/GET by id/PUT(or PATCH)/DELETE.
- Migration created and applied; basic tests or curl steps documented.

Refs: ARCHITECTURE.md → Phase 1 — 1.3
EOF
)
I3_URL=$(create_issue "$I3_TITLE" "$I3_BODY" "type:feature" "area:gateway")
add_to_project "$I3_URL"

I4_TITLE="[Phase 1] 1.4 Webhook intake stubs (GitHub/Jira) + idempotency"
I4_BODY=$(cat <<'EOF'
Create signed webhook endpoints and persist raw payloads to `events_raw` with dedupe and headers captured.

Acceptance:
- `/webhooks/github` HMAC stub with shared secret and idempotency key.
- `/webhooks/jira` JWT or shared-secret stub.
- `events_raw` table and minimal ingestion path.

Refs: ARCHITECTURE.md → Phase 1 — 1.4
EOF
)
I4_URL=$(create_issue "$I4_TITLE" "$I4_BODY" "type:feature" "area:gateway")
add_to_project "$I4_URL"

I5_TITLE="[Phase 1] 1.5 Identity mapping skeleton"
I5_BODY=$(cat <<'EOF'
Add `identities` table and utilities to map external identities (GitHub/Slack) to internal users.

Acceptance:
- `identities` table with external_type, external_id, user_id, metadata.
- Mapper utility functions for GitHub and Slack forms.

Refs: ARCHITECTURE.md → Phase 1 — 1.5
EOF
)
I5_URL=$(create_issue "$I5_TITLE" "$I5_BODY" "type:feature" "area:db")
add_to_project "$I5_URL"

echo "All set. Project #$PROJECT_NUMBER populated with Phase 1 issues."


