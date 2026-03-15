# =============================================================================
# ConductorAI Dockerfile
# =============================================================================
# Multi-stage build for minimal production image.
#
# Usage:
#   docker build -t conductorai:latest .
#   docker run --rm conductorai:latest python -c "from conductor import ConductorAI; print('OK')"
#
# This Dockerfile packages ConductorAI as a library. To use it in
# production, extend this image with your application:
#
#   FROM conductorai:latest
#   COPY app.py .
#   CMD ["python", "app.py"]
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — install dependencies and build the wheel
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir build setuptools wheel

# Copy only what's needed for the build
COPY pyproject.toml .
COPY src/ src/
COPY readme.md README.md

# Build the wheel
RUN python -m build --wheel --outdir /build/dist

# ---------------------------------------------------------------------------
# Stage 2: Runtime — minimal image with the installed package
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Labels
LABEL org.opencontainers.image.title="ConductorAI"
LABEL org.opencontainers.image.description="Multi-Agent AI Framework"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.licenses="MIT"

# Security: create non-root user
RUN groupadd --system conductor && \
    useradd --system --no-create-home --gid conductor conductor

WORKDIR /app

# Install the wheel from builder stage
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm -rf /tmp/*.whl

# Health check: verify the package imports correctly
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["python", "-c", "from conductor.facade import ConductorAI; print('healthy')"]

# Switch to non-root user
USER conductor

# No default CMD — this is a library image.
# Users extend it with their own application entry point.
CMD ["python", "-c", "from conductor.facade import ConductorAI; print('ConductorAI ready')"]
