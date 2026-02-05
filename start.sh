#!/bin/bash
#
# Start script for Railway deployment
# Python (FastAPI) manages Next.js as a subprocess
#

set -e

echo "=== Starting PriceAgent ==="
echo "Railway PORT: ${PORT:-not set}"

# Verify frontend build exists
if [ ! -d "/app/frontend/.next" ]; then
    echo "ERROR: Next.js build not found at /app/frontend/.next"
    echo "Build may have failed during Docker image creation"
    exit 1
fi

echo "Next.js build found"
echo "Starting FastAPI (which will spawn Next.js)..."

# Run FastAPI - it will start Next.js as a subprocess
exec python -m src.main
