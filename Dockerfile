# Multi-service Dockerfile for PriceAgent
# Runs Next.js frontend and FastAPI backend

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies and Node.js
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy frontend and install dependencies
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install --production=false

# Copy frontend source and build
COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# Copy application code
COPY src/ ./src/
COPY start.sh .
RUN chmod +x start.sh

# Create data directory
RUN mkdir -p /app/data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Expose port (Railway provides PORT env var)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Run both services
CMD ["./start.sh"]
