#!/bin/bash
#
# Run the full stack: Python backend + Next.js frontend
#
# Usage: ./run.sh [--with-logging]
#
# Options:
#   --with-logging    Start Grafana/Loki logging stack
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$PROJECT_DIR/frontend"
WITH_LOGGING=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --with-logging)
            WITH_LOGGING=true
            shift
            ;;
    esac
done

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

# Start logging stack if requested
LOGGING_STARTED=false
if [ "$WITH_LOGGING" = true ]; then
    echo ""
    echo -e "${YELLOW}Starting Grafana/Loki logging stack...${NC}"

    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed (required for --with-logging)${NC}"
        echo "Install Docker from https://www.docker.com/get-started"
    else
        cd "$PROJECT_DIR/infra"
        if docker-compose -f docker-compose.logging.yml up -d; then
            LOGGING_STARTED=true
            echo -e "${GREEN}✓${NC} Logging stack started"
            echo -e "    Grafana: http://localhost:3001 (admin/admin)"
            echo -e "    Loki:    http://localhost:3100"

            # Set environment variables for logging
            export LOG_EXTERNAL_ENABLED=true
            export LOG_EXTERNAL_ENDPOINT=http://localhost:3100/loki/api/v1/push
            export LOG_EXTERNAL_LABELS='{"app":"priceagent","env":"development"}'
        else
            echo -e "${YELLOW}⚠${NC} Failed to start logging stack - continuing without it"
        fi
        cd "$PROJECT_DIR"
    fi
fi

# Build frontend for production (serves on port 8000)
echo ""
echo -e "${YELLOW}Building frontend...${NC}"
cd "$FRONTEND_DIR"
if npm run build; then
    echo -e "${GREEN}✓${NC} Frontend built (static files in frontend/out/)"
else
    echo -e "${RED}✗${NC} Frontend build failed"
    exit 1
fi
cd "$PROJECT_DIR"

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
    if [ "$LOGGING_STARTED" = true ]; then
        echo -e "${YELLOW}Stopping logging stack...${NC}"
        cd "$PROJECT_DIR/infra"
        docker-compose -f docker-compose.logging.yml down 2>/dev/null || true
        cd "$PROJECT_DIR"
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
echo -e "${GREEN}  App:       http://localhost:8000     ${NC}"
echo -e "${GREEN}  Dev:       http://localhost:3000     ${NC}"
echo -e "${GREEN}  API:       http://localhost:8000/agent ${NC}"
if [ "$LOGGING_STARTED" = true ]; then
echo -e "${GREEN}  Grafana:   http://localhost:3001     ${NC}"
echo -e "${GREEN}  Loki:      http://localhost:3100     ${NC}"
fi
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Run Python backend in foreground
python -m src.main
