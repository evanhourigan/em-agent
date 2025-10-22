# How to Automatically Save Context in Claude Code

## Option 1: User Prompt Submit Hook (Recommended)

Claude Code can run commands automatically after you submit a message. This is the best way to auto-update context.

### Setup Steps

1. **Create a hook script** (`.claude/hooks/update-context.sh`):

```bash
#!/bin/bash
# Auto-update context file after each user message

CONTEXT_FILE=".claude/CONTEXT.md"
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

# Update timestamp in context file
if [ -f "$CONTEXT_FILE" ]; then
    sed -i.bak "s/\*\*Last Updated\*\*:.*/\*\*Last Updated**: $TIMESTAMP/" "$CONTEXT_FILE"
    rm -f "$CONTEXT_FILE.bak"
fi

# Optional: Auto-commit context changes
if git diff --quiet "$CONTEXT_FILE"; then
    exit 0
else
    git add "$CONTEXT_FILE"
    git commit -m "chore(context): auto-update context timestamp" --no-verify
fi
```

2. **Make it executable**:
```bash
chmod +x .claude/hooks/update-context.sh
```

3. **Configure in settings**:

Create/edit `.claude/settings.local.json`:
```json
{
  "hooks": {
    "user-prompt-submit": ".claude/hooks/update-context.sh"
  }
}
```

### How It Works
- **When**: After every message you send to Claude
- **What**: Updates timestamp, auto-commits context changes
- **Benefit**: Always have up-to-date context without manual intervention

---

## Option 2: Git Commit Hook

Use git's pre-commit hook to update context before commits.

### Setup Steps

1. **Create pre-commit hook** (`.git/hooks/pre-commit`):

```bash
#!/bin/bash
# Update context file before each commit

CONTEXT_FILE=".claude/CONTEXT.md"

if [ -f "$CONTEXT_FILE" ]; then
    # Get coverage from latest test run
    COVERAGE=$(pytest tests/gateway/ -q --cov=services/gateway --cov-report=term 2>&1 | grep "TOTAL" | awk '{print $NF}' || echo "N/A")

    # Update coverage in context
    sed -i.bak "s/\*\*Current Coverage\*\*:.*/\*\*Current Coverage**: $COVERAGE/" "$CONTEXT_FILE"
    rm -f "$CONTEXT_FILE.bak"

    # Stage updated context
    git add "$CONTEXT_FILE"
fi
```

2. **Make it executable**:
```bash
chmod +x .git/hooks/pre-commit
```

### How It Works
- **When**: Before each git commit
- **What**: Updates coverage metrics in context
- **Benefit**: Context always reflects latest committed state

---

## Option 3: Manual Slash Command

Create a custom slash command for quick context updates.

### Setup Steps

1. **Create slash command** (`.claude/commands/save-context.md`):

```markdown
Update the .claude/CONTEXT.md file with current progress:

1. Get current test coverage:
   ```bash
   PYTHONPATH=/Users/evan/code/ema/em-agent pytest tests/gateway/ -q --cov=services/gateway --cov-report=term | grep "TOTAL"
   ```

2. Count test results:
   ```bash
   PYTHONPATH=/Users/evan/code/ema/em-agent pytest tests/gateway/ -q --tb=no 2>&1 | tail -1
   ```

3. Update .claude/CONTEXT.md with:
   - Current timestamp
   - Latest coverage percentage
   - Test counts (passing/failing/skipped/errors)
   - Recent git commits (git log --oneline -5)
   - Current todo list state

4. Commit the updated context:
   ```bash
   git add .claude/CONTEXT.md
   git commit -m "chore(context): manual context update"
   ```

Confirm completion and show the updated coverage metrics.
```

### How to Use
Simply type `/save-context` in Claude Code to trigger the update.

---

## Option 4: Periodic Auto-Update Script

Create a background script that updates context periodically.

### Setup Steps

1. **Create update script** (`.claude/scripts/auto-update-context.sh`):

```bash
#!/bin/bash
# Periodically update context file (run in background)

CONTEXT_FILE=".claude/CONTEXT.md"
INTERVAL=300  # Update every 5 minutes

while true; do
    if [ -f "$CONTEXT_FILE" ]; then
        TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

        # Update timestamp
        sed -i.bak "s/\*\*Last Updated\*\*:.*/\*\*Last Updated**: $TIMESTAMP/" "$CONTEXT_FILE"
        rm -f "$CONTEXT_FILE.bak"

        # Auto-commit if changes
        if ! git diff --quiet "$CONTEXT_FILE"; then
            git add "$CONTEXT_FILE"
            git commit -m "chore(context): auto-update $(date +%H:%M)" --no-verify
        fi
    fi

    sleep $INTERVAL
done
```

2. **Run in background** (optional):
```bash
nohup .claude/scripts/auto-update-context.sh > /dev/null 2>&1 &
```

---

## Best Practice: Milestone Commits

**Recommended Approach**: Manually update context at key milestones.

### When to Update Context

1. ✅ **After completing a major task** (e.g., testing a router)
2. ✅ **Before switching tasks** (e.g., from testing to fixing)
3. ✅ **After fixing multiple failures**
4. ✅ **End of work session**
5. ✅ **Before long breaks**

### Quick Update Command
```bash
# Quick context update
cat > .claude/CONTEXT.md << 'EOF'
# Claude Code Context Recovery File
**Last Updated**: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

## Current State
- Coverage: $(pytest tests/gateway/ -q --cov=services/gateway 2>&1 | grep "TOTAL" | awk '{print $NF}')
- Last Commit: $(git log -1 --oneline)
- Working On: [YOUR CURRENT TASK]

## Next Steps
- [YOUR NEXT STEPS]
EOF

git add .claude/CONTEXT.md
git commit -m "chore(context): milestone update - [DESCRIPTION]"
```

---

## Context Recovery Best Practices

### 1. Use Descriptive Commit Messages
Every commit is a context checkpoint:
```bash
git commit -m "test(okr): add 13 tests for objectives and key results (67% coverage)"
```

### 2. Keep Multiple Context Files
- `.claude/CONTEXT.md` - Current state (this file)
- `SESSION_X_SUMMARY.md` - Detailed session summaries
- `REFACTORING_PROGRESS.md` - Overall project progress
- Git history - Complete audit trail

### 3. Document Key Decisions
When you make important decisions, document them:
```markdown
## Key Decisions Made
- **2025-10-21**: Skipped password hashing tests due to passlib/bcrypt incompatibility
- **2025-10-21**: Use hard delete in projects router (not soft delete)
```

### 4. Use Git Tags for Major Milestones
```bash
git tag -a "phase3-session2-complete" -m "37% coverage, 7 routers tested"
git push origin phase3-session2-complete
```

---

## What to Share When Context Is Lost

### Quick Recovery Template

```
Hi Claude! I lost context mid-session. Here's where we are:

**Project**: em-agent refactoring, Phase 3 test coverage expansion

**Current State**:
- Read .claude/CONTEXT.md for latest state
- Read SESSION_2_SUMMARY.md for recent work
- Coverage: [X]% (goal: 70%)

**Last Working On**: [TASK]

**Next Step**: [NEXT TASK]

**Recent Commits**:
[paste: git log --oneline -5]

Please continue from where we left off!
```

### Files to Check
1. `.claude/CONTEXT.md` - Current state (always check this first!)
2. `SESSION_X_SUMMARY.md` - Latest session details
3. `REFACTORING_PROGRESS.md` - Overall progress
4. `git log --oneline -10` - Recent work

---

## Troubleshooting

### Context File Not Updating
- Check hook file is executable: `chmod +x .claude/hooks/update-context.sh`
- Check settings.local.json syntax
- Check hook script has no errors: `.claude/hooks/update-context.sh`

### Git Commits Too Frequent
- Adjust hook to only commit on significant changes
- Use `git diff --quiet` to check for actual changes
- Increase update interval in periodic script

### Hook Not Running
- Verify settings path: `.claude/settings.local.json`
- Check Claude Code version supports hooks
- Look for errors in Claude Code output

---

## Example Workflow

### Start of Session
1. Read `.claude/CONTEXT.md`
2. Check latest commits: `git log --oneline -5`
3. Verify coverage: `pytest tests/gateway/ -q --cov=services/gateway`

### During Session
- Context auto-updates via hook (Option 1)
- OR manually update at milestones (Best Practice)

### End of Session
1. Update CONTEXT.md with final state
2. Create SESSION_X_SUMMARY.md if significant work done
3. Commit: `git commit -m "chore(context): end of session X"`
4. Optional: Tag milestone

### If Context Lost
1. Read `.claude/CONTEXT.md` first
2. Share the "Quick Recovery Template" with new Claude
3. Continue from documented "Next Steps"

---

**Recommendation**: Use **Option 1 (User Prompt Submit Hook)** for automatic updates,
combined with **Best Practice (Milestone Commits)** for detailed documentation.
