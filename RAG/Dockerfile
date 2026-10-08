FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create non-root user
RUN useradd -u 1000 -m -s /bin/bash appuser

# Dependencies
COPY RAG/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY RAG/ ./RAG/

# Set permissions
RUN chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    RAG_PORT=8001

EXPOSE 8001

CMD ["python", "-m", "RAG"]
