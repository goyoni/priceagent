#!/bin/bash
#
# Deploy to production (merge development -> main)
#
# ⚠️  USER ONLY - This script should only be run by the user, not by Claude
#
# Usage:
#   ./deploy_to_prod.sh [version]
#
# Example:
#   ./deploy_to_prod.sh           # Auto-increment patch version
#   ./deploy_to_prod.sh v1.2.0    # Specific version
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  PriceAgent - Deploy to Production    ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Safety check - ensure we're not in CI or automated context
if [ -n "$CI" ] || [ -n "$CLAUDE_CODE" ]; then
    echo -e "${RED}Error: This script should only be run manually by a human${NC}"
    echo "Production deployments require manual approval."
    exit 1
fi

# Confirm with user
echo -e "${YELLOW}⚠️  WARNING: This will deploy to PRODUCTION${NC}"
echo ""
read -p "Are you sure you want to continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

# Ensure we start from development branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "development" ]; then
    echo -e "${YELLOW}Switching to development branch...${NC}"
    git checkout development
fi

# Pull latest development
echo ""
echo -e "${YELLOW}Pulling latest development...${NC}"
git pull origin development

# Run all tests one more time
echo ""
echo -e "${YELLOW}Running final test suite...${NC}"
cd "$PROJECT_DIR"
if ! python -m pytest tests/ -v --tb=short; then
    echo -e "${RED}✗${NC} Tests failed! Cannot deploy to production."
    exit 1
fi
echo -e "${GREEN}✓${NC} All tests passed"

# Get version
if [ -n "$1" ]; then
    VERSION="$1"
else
    # Get latest tag and increment
    LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
    # Extract version numbers
    VERSION_NUM=${LATEST_TAG#v}
    IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION_NUM"
    PATCH=$((PATCH + 1))
    VERSION="v${MAJOR}.${MINOR}.${PATCH}"
fi

echo ""
echo -e "${YELLOW}Deploying version: ${VERSION}${NC}"

# Build frontend before merge (ensures frontend/out is up to date)
echo ""
echo -e "${YELLOW}Building frontend...${NC}"
cd "$PROJECT_DIR/frontend"
if npm run build; then
    echo -e "${GREEN}✓${NC} Frontend built"
else
    echo -e "${RED}✗${NC} Frontend build failed"
    echo -e "${RED}Deployment aborted. Fix build errors before deploying.${NC}"
    exit 1
fi
cd "$PROJECT_DIR"

# Commit frontend build if there are changes
if ! git diff --quiet frontend/out/; then
    echo -e "${YELLOW}Committing frontend build...${NC}"
    git add frontend/out/
    git commit -m "chore: Rebuild frontend for ${VERSION}"
fi

# Switch to main and merge
echo ""
echo -e "${YELLOW}Switching to main branch...${NC}"
git checkout main

echo -e "${YELLOW}Pulling latest main...${NC}"
git pull origin main

echo -e "${YELLOW}Merging development into main...${NC}"
# Use -X theirs for frontend/out to avoid build hash conflicts
if ! git merge development -m "Release ${VERSION}: Merge development into main"; then
    echo -e "${YELLOW}Merge conflict detected, resolving frontend/out conflicts...${NC}"
    # Accept development's version for all frontend/out conflicts
    git checkout --theirs frontend/out/ 2>/dev/null || true
    git add frontend/out/
    # Clean up any deleted files that conflict
    git diff --name-only --diff-filter=U | while read file; do
        if [[ "$file" == frontend/out/* ]]; then
            git add "$file" 2>/dev/null || git rm "$file" 2>/dev/null || true
        fi
    done
    git commit -m "Release ${VERSION}: Merge development into main"
fi

# Tag the release
echo -e "${YELLOW}Creating release tag...${NC}"
git tag -a "$VERSION" -m "Release ${VERSION}"

# Push to origin
echo ""
echo -e "${YELLOW}Pushing to origin...${NC}"
git push origin main
git push origin "$VERSION"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Production deployment complete!      ${NC}"
echo -e "${GREEN}  Version: ${VERSION}                  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Summary:"
echo "  - Built frontend for production"
echo "  - Merged development -> main"
echo "  - Created tag: ${VERSION}"
echo ""
echo "To run production:"
echo "  ./run.sh"
