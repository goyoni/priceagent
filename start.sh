#!/bin/bash
#
# Start script for Railway deployment
# Runs both Next.js frontend (port 3000) and FastAPI backend (PORT from Railway)
#

set -e

echo "=== Starting PriceAgent ==="

# Start Next.js in background on port 3000
echo "Starting Next.js frontend on port 3000..."
cd frontend
PORT=3000 npm run start &
NEXTJS_PID=$!
cd ..

# Wait for Next.js to be ready
echo "Waiting for Next.js to start..."
sleep 5

# Verify Next.js is running
if ! kill -0 $NEXTJS_PID 2>/dev/null; then
    echo "ERROR: Next.js failed to start"
    exit 1
fi
echo "Next.js is running"

# Start FastAPI on Railway's PORT (defaults to 8000)
echo "Starting FastAPI backend on port ${PORT:-8000}..."
exec python -m src.main
