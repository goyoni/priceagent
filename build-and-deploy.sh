#!/bin/bash
# build-and-deploy.sh - Build frontend and push to GitHub for Railway deployment

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== PriceAgent Build & Deploy ==="
echo

# Step 1: Build frontend
echo "1. Building frontend..."
cd frontend
npm install
npm run build
cd ..
echo "   ✓ Frontend built successfully"
echo

# Step 2: Stage and commit
echo "2. Committing changes..."
git add -A
if git diff --cached --quiet; then
    echo "   No changes to commit"
else
    git commit -m "Build: update frontend static files $(date +%Y-%m-%d)"
    echo "   ✓ Changes committed"
fi
echo

# Step 3: Push to GitHub
echo "3. Pushing to GitHub..."
git push
echo "   ✓ Pushed to GitHub"
echo

echo "=== Deploy Complete ==="
echo
echo "Railway will automatically redeploy from the new commit."
echo "Check status at: https://railway.app/dashboard"
