# Multi-stage build for Laqta Studio
# Stage 1: Build the React + TypeScript frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# Stage 2: Runtime environment with Python 3.11 & FFmpeg (with libass)
FROM python:3.11-slim AS runtime
WORKDIR /app

# Install system dependencies (FFmpeg with libass for subtitle burning)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libass9 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml ./
COPY qatta/ ./qatta/
COPY backend/ ./backend/

# Install Laqta package and local ASR dependencies
RUN pip install --no-cache-dir -e ".[asr]"

# Copy built studio frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Set environment
ENV PYTHONUNBUFFERED=1 \
    QATTA_BIND_HOST=0.0.0.0 \
    QATTA_BIND_PORT=8000

EXPOSE 8000

# Run FastAPI studio server
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
