# Claude Code Context Recovery File - TEMPLATE
**Last Updated**: [TIMESTAMP]
**Project**: [PROJECT_NAME]
**Session**: [SESSION_NUMBER/NAME]

## 🎯 Current State

### Project Metrics
- **Current Progress**: [METRIC] (e.g., 37% test coverage, 5 features complete)
- **Starting Point**: [BASELINE]
- **Goal**: [TARGET]
- **Remaining**: [GAP]

### Current Task
- **Working On**: [CURRENT TASK]
- **Status**: [in_progress/blocked/completed]
- **Blockers**: [ANY BLOCKERS]

## ✅ Recently Completed Work

### Latest Session
- **Date**: [DATE]
- **Completed**:
  - [ ] [TASK 1]
  - [ ] [TASK 2]
  - [ ] [TASK 3]

### Key Achievements
1. [ACHIEVEMENT 1 with metrics]
2. [ACHIEVEMENT 2 with metrics]
3. [ACHIEVEMENT 3 with metrics]

## 📂 Key Files Modified

### Created
```
[file1] - [description]
[file2] - [description]
```

### Modified
```
[file1] - [what changed]
[file2] - [what changed]
```

## 🔍 Current Project State

### [METRIC 1 NAME] (e.g., Test Coverage)
```
✅ Excellent (>90%): [items]
✅ Good (70-90%): [items]
✅ Moderate (50-70%): [items]
⚠️  Needs Work (<50%): [items]
```

### [METRIC 2 NAME] (e.g., Features Completed)
```
✅ Done: [count]
🔄 In Progress: [count]
⏳ TODO: [count]
```

## ⚠️ Known Issues & Blockers

### Current Blockers
- [ ] [BLOCKER 1] - [impact and workaround]
- [ ] [BLOCKER 2] - [impact and workaround]

### Known Limitations
- **[LIMITATION 1]**: [description and solution]
- **[LIMITATION 2]**: [description and solution]

## 📋 Next Steps

### Immediate (Session N+1)
1. [ ] [NEXT TASK 1]
2. [ ] [NEXT TASK 2]
3. [ ] [NEXT TASK 3]

### Short Term
- [ ] [TASK]
- [ ] [TASK]

### Long Term
- [ ] [TASK]
- [ ] [TASK]

## 🚀 How to Resume This Session

### Quick Start Commands
```bash
# [Command to check project state]
[your command here]

# [Command to run tests/build/etc]
[your command here]

# [Command to view progress]
[your command here]
```

### Recent Git Commits
```bash
git log --oneline -5

# Latest commits:
[commit 1]
[commit 2]
[commit 3]
```

### What to Tell New Claude Session
```
I'm working on [PROJECT_NAME]. We're currently [CURRENT_STATE].

Please read:
1. .claude/CONTEXT.md - Current state
2. [OTHER_DOC_1] - [description]
3. [OTHER_DOC_2] - [description]

Current status: [STATUS]. Goal: [GOAL].
Next step: [NEXT_STEP]

Let's continue where we left off!
```

## 📊 Progress Tracking

### Sessions Completed
- ✅ **Session 1**: [work done] - [metric achieved]
- ✅ **Session 2**: [work done] - [metric achieved]
- ⏳ **Session N**: [current work]

### Progress Trajectory
```
Baseline:   [METRIC]
Session 1:  [METRIC] (+X)
Session 2:  [METRIC] (+Y)
Target:     [METRIC] (+Z remaining)
```

## 🔄 Recovery Instructions

**If context is lost**:

1. Read this file (`.claude/CONTEXT.md`)
2. Read recent documentation:
   - [DOC_FILE_1]
   - [DOC_FILE_2]
3. Check recent commits: `git log --oneline -10`
4. Review current branch: `git status`
5. Use "What to Tell New Claude Session" above

**Key Context Files**:
- `.claude/CONTEXT.md` - This file (always check first!)
- `[PROJECT_DOC_1]` - [description]
- `[PROJECT_DOC_2]` - [description]
- Git history - Complete audit trail

---

## 📝 Customization Notes

**Replace these placeholders when using this template**:
- `[PROJECT_NAME]` - Your project name
- `[TIMESTAMP]` - Current date/time
- `[SESSION_NUMBER/NAME]` - Current session identifier
- `[METRIC]` - Your project's key metrics (coverage, features, etc.)
- `[CURRENT_TASK]` - What you're working on right now
- `[NEXT_STEP]` - What to do next

**Add project-specific sections as needed**:
- Testing strategy
- Deployment status
- Dependencies
- Architecture decisions
- Design patterns
- Performance metrics
- etc.
