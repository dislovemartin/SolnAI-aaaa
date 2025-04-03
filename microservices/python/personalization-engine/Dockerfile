FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04 as base

# Set working directory
WORKDIR /app

# Install Python and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set Python to use UTF-8 encoding
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY app /app/app

# Create non-root user for security
RUN useradd -m -s /bin/bash appuser
RUN chown -R appuser:appuser /app
USER appuser

# Configure environment variables
ENV PORT=8002 \
    HOST=0.0.0.0 \
    PYTHONPATH=/app \
    LOG_LEVEL=INFO

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
