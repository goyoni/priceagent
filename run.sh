#!/bin/bash
#
# Run the full stack: Python backend + Next.js frontend
#
# Usage: ./run.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Agent Dashboard - Full Stack Runner  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js is not installed${NC}"
    echo "Please install Node.js from https://nodejs.org/"
    echo "Or use: brew install node"
    exit 1
fi

# Check for npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}Error: npm is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Node.js $(node --version) found"
echo -e "${GREEN}✓${NC} npm $(npm --version) found"

# Install frontend dependencies if needed
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo ""
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    cd "$FRONTEND_DIR"
    npm install
    cd "$PROJECT_DIR"
    echo -e "${GREEN}✓${NC} Frontend dependencies installed"
fi

# Install Python dependencies if needed
echo ""
echo -e "${YELLOW}Checking Python dependencies...${NC}"
pip install -q sqlalchemy[asyncio] --trusted-host pypi.org --trusted-host files.pythonhosted.org 2>/dev/null || true
echo -e "${GREEN}✓${NC} Python dependencies ready"

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start Next.js frontend in background
echo ""
echo -e "${YELLOW}Starting Next.js frontend...${NC}"
cd "$FRONTEND_DIR"
npm run dev > /dev/null 2>&1 &
FRONTEND_PID=$!
cd "$PROJECT_DIR"

# Wait for frontend to start
sleep 3

if kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Frontend running at http://localhost:3000"
else
    echo -e "${RED}✗${NC} Frontend failed to start"
fi

# Start Python backend
echo ""
echo -e "${YELLOW}Starting Python backend...${NC}"
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Dashboard: http://localhost:3000     ${NC}"
echo -e "${GREEN}  API:       http://localhost:8000     ${NC}"
echo -e "${GREEN}  Old UI:    http://localhost:8000/dashboard ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Run Python backend in foreground
python -m src.main
