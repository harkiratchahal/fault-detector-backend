# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Postgres, MySQL, and building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Create uploads dir and set permissions
RUN mkdir -p /app/uploads

# Expose port
EXPOSE 8000

# Set sensible defaults via env, override at runtime as needed
ENV LOG_LEVEL=info \
    CORS_ALLOW_ORIGINS=* \
    UPLOAD_DIR=/app/uploads

# Gunicorn with Uvicorn workers for FastAPI
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "main:app"]
