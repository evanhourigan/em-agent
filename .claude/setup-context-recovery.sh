#!/bin/bash
# Global Context Recovery Setup Script
# Use this in ANY repository to set up automatic context saving

set -e

echo "🚀 Setting up Claude Code Context Recovery System..."
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get project info
read -p "Project name (e.g., 'em-agent refactoring'): " PROJECT_NAME
read -p "Initial goal/metric (e.g., '70% test coverage'): " PROJECT_GOAL

# 1. Create .claude directory
echo -e "${BLUE}Creating .claude directory structure...${NC}"
mkdir -p .claude/hooks
mkdir -p .claude/scripts

# 2. Copy template and customize
echo -e "${BLUE}Creating CONTEXT.md from template...${NC}"
if [ -f "$(dirname "$0")/CONTEXT_TEMPLATE.md" ]; then
    cp "$(dirname "$0")/CONTEXT_TEMPLATE.md" .claude/CONTEXT.md

    # Replace placeholders
    TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
    sed -i.bak "s/\[TIMESTAMP\]/$TIMESTAMP/g" .claude/CONTEXT.md
    sed -i.bak "s/\[PROJECT_NAME\]/$PROJECT_NAME/g" .claude/CONTEXT.md
    sed -i.bak "s/\[PROJECT_GOAL\]/$PROJECT_GOAL/g" .claude/CONTEXT.md
    sed -i.bak "s/\[SESSION_NUMBER\/NAME\]/Session 1/g" .claude/CONTEXT.md
    rm -f .claude/CONTEXT.md.bak

    echo -e "${GREEN}✓ Created .claude/CONTEXT.md${NC}"
else
    echo -e "${YELLOW}⚠ Template not found, creating basic CONTEXT.md${NC}"
    cat > .claude/CONTEXT.md << EOF
# Claude Code Context Recovery File
**Last Updated**: $TIMESTAMP
**Project**: $PROJECT_NAME

## Current State
- Working on: [Initial setup]
- Goal: $PROJECT_GOAL

## Next Steps
- [ ] Define project structure
- [ ] Set initial baseline
- [ ] Start first task

## How to Resume
Tell Claude: "Read .claude/CONTEXT.md and continue where we left off"
EOF
    echo -e "${GREEN}✓ Created basic .claude/CONTEXT.md${NC}"
fi

# 3. Copy or create AUTO_CONTEXT_GUIDE
echo -e "${BLUE}Setting up context guide...${NC}"
if [ -f "$(dirname "$0")/AUTO_CONTEXT_GUIDE.md" ]; then
    cp "$(dirname "$0")/AUTO_CONTEXT_GUIDE.md" .claude/
    echo -e "${GREEN}✓ Copied AUTO_CONTEXT_GUIDE.md${NC}"
else
    echo -e "${YELLOW}⚠ Guide not found, creating basic version${NC}"
    cat > .claude/AUTO_CONTEXT_GUIDE.md << 'EOF'
# Auto Context Guide
See: https://github.com/[your-template-repo] for full guide

## Quick Setup
1. Create .claude/hooks/update-context.sh
2. Add to .claude/settings.local.json: {"hooks": {"user-prompt-submit": ".claude/hooks/update-context.sh"}}
3. Update context at milestones
EOF
    echo -e "${GREEN}✓ Created basic guide${NC}"
fi

# 4. Create auto-update hook
echo -e "${BLUE}Creating auto-update hook...${NC}"
cat > .claude/hooks/update-context.sh << 'HOOK_SCRIPT'
#!/bin/bash
# Auto-update context file after each user message

CONTEXT_FILE=".claude/CONTEXT.md"
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

if [ -f "$CONTEXT_FILE" ]; then
    # Update timestamp
    sed -i.bak "s/\*\*Last Updated\*\*:.*/\*\*Last Updated**: $TIMESTAMP/" "$CONTEXT_FILE"
    rm -f "$CONTEXT_FILE.bak"

    # Optional: Auto-commit (uncomment if desired)
    # if ! git diff --quiet "$CONTEXT_FILE"; then
    #     git add "$CONTEXT_FILE"
    #     git commit -m "chore(context): auto-update $(date +%H:%M)" --no-verify
    # fi
fi
HOOK_SCRIPT

chmod +x .claude/hooks/update-context.sh
echo -e "${GREEN}✓ Created update-context.sh hook${NC}"

# 5. Create or update settings.local.json
echo -e "${BLUE}Configuring Claude Code settings...${NC}"
SETTINGS_FILE=".claude/settings.local.json"

if [ -f "$SETTINGS_FILE" ]; then
    echo -e "${YELLOW}⚠ settings.local.json exists. Manual update needed:${NC}"
    echo '   Add: "hooks": {"user-prompt-submit": ".claude/hooks/update-context.sh"}'
else
    cat > "$SETTINGS_FILE" << 'EOF'
{
  "hooks": {
    "user-prompt-submit": ".claude/hooks/update-context.sh"
  }
}
EOF
    echo -e "${GREEN}✓ Created settings.local.json with hook configured${NC}"
fi

# 6. Create .gitignore entry for settings.local.json (optional)
if [ -f ".gitignore" ]; then
    if ! grep -q "settings.local.json" .gitignore; then
        echo -e "${BLUE}Adding settings.local.json to .gitignore...${NC}"
        echo ".claude/settings.local.json" >> .gitignore
        echo -e "${GREEN}✓ Updated .gitignore${NC}"
    fi
fi

# 7. Initial commit
echo ""
echo -e "${BLUE}Creating initial context commit...${NC}"
read -p "Commit context files to git? (y/n): " COMMIT_CHOICE

if [ "$COMMIT_CHOICE" = "y" ] || [ "$COMMIT_CHOICE" = "Y" ]; then
    git add .claude/CONTEXT.md .claude/AUTO_CONTEXT_GUIDE.md .claude/hooks/update-context.sh

    # Add settings if not gitignored
    if ! grep -q "settings.local.json" .gitignore 2>/dev/null; then
        git add .claude/settings.local.json
    fi

    git commit -m "feat(context): set up automatic context recovery system

- Created .claude/CONTEXT.md for state tracking
- Set up auto-update hook
- Project: $PROJECT_NAME
- Goal: $PROJECT_GOAL" || echo -e "${YELLOW}⚠ Nothing to commit or commit failed${NC}"

    echo -e "${GREEN}✓ Created git commit${NC}"
fi

# 8. Success message
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✨ Context Recovery System Setup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}What was created:${NC}"
echo "  ✓ .claude/CONTEXT.md - Your save file"
echo "  ✓ .claude/AUTO_CONTEXT_GUIDE.md - Instructions"
echo "  ✓ .claude/hooks/update-context.sh - Auto-update hook"
echo "  ✓ .claude/settings.local.json - Hook configuration"
echo ""
echo -e "${BLUE}How it works:${NC}"
echo "  • Context file auto-updates after each message to Claude"
echo "  • Timestamp updates automatically"
echo "  • Manual updates at milestones recommended"
echo ""
echo -e "${BLUE}If you lose context:${NC}"
echo '  Just say: "Read .claude/CONTEXT.md and continue"'
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Update .claude/CONTEXT.md with your current task"
echo "  2. Start working with Claude Code"
echo "  3. Context auto-saves after each message!"
echo ""
echo -e "${BLUE}Manual update command:${NC}"
echo "  .claude/hooks/update-context.sh"
echo ""
echo -e "${YELLOW}💡 Tip: Update CONTEXT.md at major milestones for best recovery${NC}"
echo ""
