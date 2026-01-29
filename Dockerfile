# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12.6
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        curl \
        build-essential \
        libmagic1 \
        libmagic-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY backend/app ./backend/app
COPY scripts ./scripts
COPY sitecustomize.py ./sitecustomize.py

RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /srv/app

USER appuser

ENV PYTHONPATH=/srv/app/backend

ENTRYPOINT ["/srv/app/scripts/docker-entrypoint.sh"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
