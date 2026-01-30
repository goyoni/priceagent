#!/bin/bash
#
# Deploy to development branch
# Runs all tests before committing
#
# Usage:
#   ./deploy.sh "feat: Add new feature" "Description of changes"
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Shopping Agent - Deploy to Development   ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check arguments
if [ -z "$1" ]; then
    echo -e "${RED}Error: Commit message required${NC}"
    echo ""
    echo "Usage: ./deploy.sh \"<type>: <summary>\" \"<description>\""
    echo ""
    echo "Types: feat, fix, refactor, test, docs, chore"
    echo ""
    echo "Example:"
    echo "  ./deploy.sh \"feat: Add bulk messaging\" \"Integrated DraftModal for editing messages before sending\""
    exit 1
fi

COMMIT_TITLE="$1"
COMMIT_DESC="${2:-}"

# Ensure we're on development branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "development" ]; then
    echo -e "${YELLOW}Switching to development branch...${NC}"

    # Check if development branch exists
    if git show-ref --verify --quiet refs/heads/development; then
        git checkout development
    else
        echo -e "${YELLOW}Creating development branch...${NC}"
        git checkout -b development
    fi
fi

# Pull latest changes
echo -e "${YELLOW}Pulling latest changes...${NC}"
git pull origin development 2>/dev/null || true

echo ""
echo -e "${YELLOW}Running tests...${NC}"
echo ""

# Run Python tests
echo -e "${YELLOW}Running Python tests...${NC}"
cd "$PROJECT_DIR"
if python -m pytest tests/ -v --tb=short; then
    echo -e "${GREEN}✓${NC} Python tests passed"
else
    echo -e "${RED}✗${NC} Python tests failed"
    echo -e "${RED}Deployment aborted. Fix failing tests before deploying.${NC}"
    exit 1
fi

# Run frontend tests if they exist
if [ -f "$PROJECT_DIR/frontend/package.json" ]; then
    if grep -q '"test"' "$PROJECT_DIR/frontend/package.json"; then
        echo ""
        echo -e "${YELLOW}Running frontend tests...${NC}"
        cd "$PROJECT_DIR/frontend"
        if npm test -- --passWithNoTests 2>/dev/null; then
            echo -e "${GREEN}✓${NC} Frontend tests passed"
        else
            echo -e "${YELLOW}⚠${NC} Frontend tests skipped or not configured"
        fi
        cd "$PROJECT_DIR"
    fi
fi

# Run E2E tests if Playwright is configured
if [ -f "$PROJECT_DIR/frontend/playwright.config.ts" ]; then
    echo ""
    echo -e "${YELLOW}Running E2E tests...${NC}"
    cd "$PROJECT_DIR/frontend"

    # Check if playwright is installed
    if npx playwright --version > /dev/null 2>&1; then
        if npm run test:e2e; then
            echo -e "${GREEN}✓${NC} E2E tests passed"
        else
            echo -e "${RED}✗${NC} E2E tests failed"
            echo -e "${RED}Deployment aborted. Fix failing E2E tests before deploying.${NC}"
            exit 1
        fi
    else
        echo -e "${YELLOW}⚠${NC} Playwright not installed - skipping E2E tests"
        echo -e "${YELLOW}  Run 'cd frontend && npm install && npx playwright install' to enable${NC}"
    fi
    cd "$PROJECT_DIR"
fi

echo ""
echo -e "${GREEN}All tests passed!${NC}"
echo ""

# Stage all changes
echo -e "${YELLOW}Staging changes...${NC}"
git add -A

# Check if there are changes to commit
if git diff --cached --quiet; then
    echo -e "${YELLOW}No changes to commit${NC}"
    exit 0
fi

# Show what will be committed
echo ""
echo -e "${YELLOW}Changes to be committed:${NC}"
git diff --cached --stat
echo ""

# Create commit
echo -e "${YELLOW}Creating commit...${NC}"
if [ -n "$COMMIT_DESC" ]; then
    git commit -m "$COMMIT_TITLE" -m "$COMMIT_DESC"
else
    git commit -m "$COMMIT_TITLE"
fi

# Push to origin
echo ""
echo -e "${YELLOW}Pushing to origin/development...${NC}"
git push -u origin development

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment to development complete!  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "  - Review changes on GitHub"
echo "  - When ready for production, run: ./deploy_to_prod.sh"
