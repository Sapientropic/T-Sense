# syntax=docker/dockerfile:1

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY channel_lists ./channel_lists
COPY profiles ./profiles
COPY scripts ./scripts
COPY templates ./templates

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

RUN if command -v useradd >/dev/null 2>&1; then \
        useradd --create-home --shell /usr/sbin/nologin tgcs; \
    else \
        adduser -D -h /home/tgcs -s /sbin/nologin tgcs; \
    fi

USER tgcs
WORKDIR /workspace

ENTRYPOINT ["tgcs"]
CMD ["quickstart", "jobs"]
