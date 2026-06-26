# Backend API image: FastAPI over the in-memory metrics table.
# Build context is the REPO ROOT (needs pipeline/ + data/processed/metrics.parquet):
#   docker build -f backend/Dockerfile -t ham-api .
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Runtime deps only (the heavy pipeline/ETL deps are not imported at serve time).
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore -r backend/requirements.txt
RUN adduser --disabled-password --gecos "" appuser

# data.py imports pipeline.taxonomy (pure-python); copy the package for that import.
COPY pipeline/ pipeline/
COPY backend/ backend/

# The scored table. Gitignored + reproducible via `make data`; must exist in the build
# context. For large/rotating data, mount it instead and delete this COPY.
COPY data/processed/metrics.parquet data/processed/metrics.parquet

# Override at deploy time with the real site origin(s), comma-separated.
ENV ALLOWED_ORIGINS=http://localhost:8080
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"

USER appuser
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
