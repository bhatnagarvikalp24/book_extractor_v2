# ── Stage 1: Build Next.js frontend (static export) ──────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend serves the static frontend ────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend to where _find_frontend_dir() expects it:
# backend/app/main.py → 3 levels up = /app → /app/frontend/out
COPY --from=frontend-builder /build/out ./frontend/out

WORKDIR /app/backend

# Railway injects $PORT automatically
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
