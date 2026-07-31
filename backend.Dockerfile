# Use a slim Python image with wheels available for the ML stack.
FROM python:3.11-slim

# Set working directory
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    XDG_CACHE_HOME=/app/.cache \
    ANONYMIZED_TELEMETRY=False \
    OMP_NUM_THREADS=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download and warm Chroma's lightweight ONNX embedding model at build time
# so the first user upload does not pay that cold-start cost.
RUN python - <<'PY'
import chromadb

client = chromadb.EphemeralClient()
collection = client.get_or_create_collection("warmup")
collection.upsert(ids=["warmup"], documents=["warm up embedding model"])
collection.query(query_texts=["warmup"], n_results=1)
PY

# Copy the rest of the application
COPY backend/ .

# Expose port
EXPOSE 8000

# Cloud platforms such as Render inject PORT at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
