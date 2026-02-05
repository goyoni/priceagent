#!/bin/bash
#
# Start script for Railway deployment
# Runs both Next.js frontend (port 3000) and FastAPI backend (Railway PORT)
#

set -e

echo "=== Starting PriceAgent ==="
echo "Railway PORT: ${PORT:-not set}"

# Save Railway's PORT for FastAPI
FASTAPI_PORT="${PORT:-8000}"

# Start Next.js in background on port 3000 (override Railway's PORT)
echo "Starting Next.js frontend on port 3000..."
cd frontend

# Unset PORT to avoid conflicts, explicitly set to 3000
unset PORT
export PORT=3000

npm run start &
NEXTJS_PID=$!
cd ..

# Wait for Next.js to be ready (check with curl)
echo "Waiting for Next.js to start..."
for i in {1..30}; do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo "Next.js is ready!"
        break
    fi
    if ! kill -0 $NEXTJS_PID 2>/dev/null; then
        echo "ERROR: Next.js process died"
        exit 1
    fi
    echo "  Waiting... ($i/30)"
    sleep 1
done

# Final check
if ! curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "WARNING: Next.js may not be fully ready, continuing anyway..."
fi

# Restore PORT for FastAPI
export PORT="$FASTAPI_PORT"

# Start FastAPI on Railway's PORT
echo "Starting FastAPI backend on port ${PORT}..."
exec python -m src.main
