# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12.6
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        bash \
        curl \
        build-essential \
        libmagic1 \
        libmagic-dev \
        pkg-config \
        libreoffice \
        poppler-utils \
        fonts-dejavu-core \
        fonts-noto-core \
        fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY requirements.txt ./
# setuptools базового образа (70.3.0) уязвим к CVE-2025-47273 (fix 78.1.1) —
# поднимаем вместе с pip до установки зависимостей.
RUN python -m pip install --upgrade pip "setuptools>=78.1.1" \
    && pip install -r requirements.txt

RUN fc-cache -f

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
