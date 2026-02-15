FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        git \
        libmagic1 \
        libmagic-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip
