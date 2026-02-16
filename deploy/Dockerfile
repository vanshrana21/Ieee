# Phase 11 — Dockerfile
# Production-ready container for Moot Court Tournament Platform

FROM python:3.11-slim-bookworm as builder

# Build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim-bookworm

# Security: Run as non-root user
RUN groupadd -r mootcourt && useradd -r -g mootcourt mootcourt

# Runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /home/mootcourt/.local

# Set environment
ENV PATH=/home/mootcourt/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy application code
COPY --chown=mootcourt:mootcourt backend/ ./backend/
COPY --chown=mootcourt:mootcourt deploy/gunicorn.conf.py ./

# Create necessary directories
RUN mkdir -p /app/logs /app/uploads && chown -R mootcourt:mootcourt /app

# Switch to non-root user
USER mootcourt

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start with Gunicorn
CMD ["gunicorn", "-c", "gunicorn.conf.py", "backend.main:app"]
