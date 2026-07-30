# Use a slim Python image with wheels available for the ML stack.
FROM python:3.11-slim

# Set working directory
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Preload runtime models during the image build to reduce cold-start time.
RUN python - <<'PY'
from sentence_transformers import SentenceTransformer
import spacy

SentenceTransformer("all-MiniLM-L6-v2")
spacy.load("en_core_web_sm")
PY

# Copy the rest of the application
COPY backend/ .

# Expose port
EXPOSE 8000

# Cloud platforms such as Render inject PORT at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
