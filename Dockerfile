FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create non-root user for security
RUN useradd -u 1000 -m -s /bin/bash appuser

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application packages
COPY Backend/ ./Backend/
COPY Database/ ./Database/
COPY RAG/ ./RAG/
COPY run_worker.py ./

# Set ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables
ENV PYTHONPATH=/app:/app/Backend \
    PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: run FastAPI application via uvicorn
CMD ["uvicorn", "app:app", "--app-dir", "/app/Backend", "--host", "0.0.0.0", "--port", "8000"]
